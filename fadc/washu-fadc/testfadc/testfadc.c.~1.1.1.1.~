/***********************************************************************
 * testfadc.c - simple program to interactively test FADC 
 *              functionality
 * 
 * Karl Kosack, 2/21/00
 * Marty Olevitch, 12/1/00 - assume only one fadc board to be tested
 * Karl Kosack, 9/2001  - support for linux and new libfadc, lots of others
 * 
 * TODO: 
 *
 * make a struct which contains: value, value_avg, value_sigma,
 * sumvalue, sumvalue2 for storing each calculated parameter
 *      
 ***********************************************************************/

#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <libsx.h>
#include <unistd.h>	/* getopt */
#include <time.h>
#include <math.h>
#include <assert.h>
#include <signal.h>
#include <pthread.h>
#include <errno.h>

#include <gsl/gsl_fft_real.h>

#include <fadc.h>
#include "version.h"

#ifdef QNX
#include "vme_client.h"	
#else
#include <sys/time.h>
#include <vme/vme.h>
#include <vme/vme_api.h>
//#include <vmic/vme_utils.h>
#endif

/*-----------------------------------------------------*/
/* Constants */
/*-----------------------------------------------------*/
#define NUMCHANNELS 10
#define MAX_SAMPLES 10000
#define GRAPHWID 300
#define GRAPHHT 50
#define RATE_CYCLE 20
#define DEFAULT_PEDWIDTH 32
#define DEFAULT_PEDOFFS  64
#define DEFAULT_PULSEWID   32
#define DEFAULT_PULSEOFFS  0

/*-----------------------------------------------------*/
/* Structures */
/*-----------------------------------------------------*/
struct Histogram {
    int *hist;
    int underflow, overflow;
    double min, max;
    int nbins;
    double binwidth;
};

struct Measurement {

    int nsamples;
    double value;
    double sum;
    double sum2;
    double avg;
    double sigma;

};

struct GraphData {
    int num;
    unsigned char pulse[MAX_SAMPLES];
    double fftpulse[MAX_SAMPLES];
    char fft;
    char hilo;
    unsigned long area;
    unsigned long scaler;
    unsigned long prevscaler;
    double rate;
    unsigned long pedoffs,pedwidth;   /* limits for pedestal calculation */
    unsigned long pulseoffs, pulsewid; /* limits for pulse calc */
    int tpeak;
    double thresh;
    double max,min;

    struct Measurement tthresh;
    struct Measurement ped;
    struct Measurement thalfmax1;
    struct Measurement thalfmax2;
    struct Measurement softwidth;
    struct Measurement peak;
    struct Measurement p2p;
    struct Measurement softarea;
    struct Measurement trise;
    struct Measurement tfall;
    struct Measurement threshwidth;
       
    struct Histogram areahist;		      /* area histogram */
    struct Histogram peakhist;		      /* peak histogram */
    struct Histogram widthhist;		      /* pulse width histogram */
    struct Histogram thmax1hist;	      /* pulse width histogram */
    struct Histogram tthreshhist;             /* threshold crossing hist */
    struct Histogram threshwidthhist;

};

/*-----------------------------------------------------*/
/* Prototypes */
/*-----------------------------------------------------*/
void init_display( int argc, char **argv);
void init_colors();
void usage(void);
void c_redisplay(Widget w, int width, int height, void *data);
unsigned long ask_for_int( char *text, unsigned long def);
double get_time(void);
void recalc_rates(void);
void analyze_pulse(void);
void histogram_new(struct Histogram *h, double low, double high, int nbins);
void histogram_add(struct Histogram *h, double val);
void histogram_delete(struct Histogram *h);
int  histogram_write( struct Histogram *h, char *filename);
void histogram_clear( struct Histogram *h );
void shutdown(int);
int  parse_data( unsigned long *buf );
void binary_print(unsigned long word);
void dacq( void * );
void jitter( void * );
void find_pulse(int);
void warn(char *fmt, ...);
void open_param_file(void);
double find_time(double height,unsigned char *pulse,int start_time,int step );
int sign(double arg);
void c_rate_vs_threshold( Widget w, void *data );
void rate_vs_thresh( void * );
Widget make_tool_button( char *name, ButtonCB function, 
			 int where1, Widget from1,int where2, Widget from2);

void measurement_add( struct Measurement *m, double val );
void measurement_clear( struct Measurement *m );


/*-----------------------------------------------------*/
/* Globals */
/*-----------------------------------------------------*/
int Boardnum;	            /* number for our board */
unsigned long Uniqueid;     /* Unique ID number of board */
int Histchannel = 4;        /* channel to use for histograms */
int Usetext = 0;            /* flag to use text mode vs dialog box */
int Numboards = 0;          /* Number of boards reported by libfadc */
int Datawidth = 24;         /* Default data width */
int Running=0;              /* Flag for data acquisition */
int Trigger=0;              /* is triggering happening */
int Dacq = 0;               /* Flag for DACQ mode (no graphics) */
int Jitter = 0;             /* Flag for DACQ mode (no graphics) */
int Showdata=0;             /* Flag for dumping data to screen */
int View = 0;               /* Which analysis values to display */
int Ratethresh=0;     
int Cfdmode=1;     
unsigned long Eventno=0;    /* Current Event number from data stream */
long Timeout_interval=30;   /* Interval between calls to tick() */
unsigned long *Buffer;      /* Buffer for holding data */
int Buffersize;             /* size of Buffer for holding data */
double Rtime=0;             /* Previous time value for rate calculation*/
long Cycle = 0;             /* Used for determining when to do rate calc*/
long Nanalyzed=0;           /* number of analyzed events */
long Refresh=1;             /* call redisplay every N ticks */ 
FILE *Logfile, *Paramfile;
int Selected[NUMCHANNELS]={-1,-1,-1,-1,-1,-1,-1,-1,-1,-1};
char Persistent=0;
int Holdevent=0;

/*-----------------------------------------------------*/
/* Interface globals */
/*-----------------------------------------------------*/
Widget wid[100];
Widget Graph[NUMCHANNELS+1];
Widget Viewbox[NUMCHANNELS+1];
Widget Cfdcheck[NUMCHANNELS+1];
Widget Errbox[NUMCHANNELS+1];
struct GraphData Graphdata[NUMCHANNELS+1];
Widget Zoomwindow;
Widget Zoomgraph;

int Color[100];
enum widget_colors {
    SOFT_PULSE_COLOR,
    SOFT_PED_COLOR,
    SOFT_PULSE_INACTIVE_COLOR,
    SOFT_PED_INACTIVE_COLOR,
    PULSE_BG_INACTIVE_COLOR,
    TOOLBAR_COLOR,
    N_COLORS /*leave as last entry*/
};

enum widget_names {
    TOOLBAR,
    GO_BUTTON,
    ONE_EVT_BUTTON,
    EVT_CLR_BUTTON,
    SET_MENU,
    VIEW_MENU,
    VIEW_L,
    FILE_MENU,
    ANALYSIS_MENU,
    SELECT_MENU,
    ACTION_MENU,
    CLEAR_BUTTON,
    EVT_BOX,
    EVT_BOX_L,
    NAREAEVT_BOX,
    NAREAEVT_BOX_L,
    HIST_TOG,
    PERSIST_TOG,
    ANALYSIS_TOG,
    TRIGGER_L,
    OPTION_PANEL,
    PULSE_PANEL,
    READ_BUTTON,
    PED_BUTTON,
    REREAD_BUTTON,
    DUMP_BUTTON,
};

enum view_stuff {
    VIEW_SCALERS,
    VIEW_AREA,
    VIEW_RATE,
    VIEW_PED,
    VIEW_PED_AVG,
    VIEW_SOFT_AREA,
    VIEW_AREA_AVG,
    VIEW_PEAK,
    VIEW_PEAK_AVG,
    VIEW_LEADEDGE,
    VIEW_LEADEDGE_AVG,
    VIEW_WIDTH,
    VIEW_WIDTH_AVG,
    VIEW_PEAK2PEAK,
    VIEW_PEAK2PEAK_AVG,
    VIEW_RISETIME,
    VIEW_RISETIME_AVG,
    VIEW_FALLTIME,
    VIEW_FALLTIME_AVG,
    VIEW_TTHRESH,
    VIEW_TTHRESH_AVG,
    VIEW_THRESH_WIDTH,
    VIEW_THRESH_WIDTH_AVG,
    VIEW_COUNT,  /* must be last */
};

char View_label[VIEW_COUNT][50] = {"Scalers","Areas","Singles Rates",
				   "Pedestals","<Pedestals>","Software area",
				   "<Soft area>","Peak","<Peak>", 
				   "Leading Edge","<Leading Edge>",
				   "Width","<Width>","Peak2Peak","<Peak2Peak>",
				   "Rise Time", "<Rise Time>", "Fall Time", 
				   "<Fall Time>", "t_thresh","<t_thresh>",
				   "ThreshWidth","<ThreshWidth>"};
Widget viewmenu[VIEW_COUNT+1];

enum toggles {
    TOGGLE_HIST,
    TOGGLE_ANALYSIS,
    TOGGLE_PERSIST,
    NTOGGLES
};

char Toggle[NTOGGLES];

char Fft_is_doable = 0;

/*-----------------------------------------------------*/
/* MAIN */
/*-----------------------------------------------------*/
int
main( int argc, char **argv)
{
    int c;	/* for getopt */
    int i;
    unsigned long nwords;
    clock_t clk;
    struct sigaction sa;
    char text[128];
    int width=0;

    /* handle ctrl-c */
   
    sigfillset( &sa.sa_mask );
    sa.sa_flags = 0;
    sa.sa_handler = shutdown;
    if (sigaction(SIGINT, &sa, NULL) < 0) {
	perror( "sigaction SIGINT" );
	exit(1);
    }
    
    /* Get Command line args */

    Boardnum = -1;
    Numboards = fadc_num_boards();
    fprintf(stderr, "testfadc version %s\n", TESTFADC_VERSION);
    fprintf(stderr, "testfadc: libfadc is configured for %d boards\n",Numboards);
    while ((c = getopt(argc, argv, "tb:")) != -1) {
	switch(c) {
	  case 't':
	      Usetext = 1;  /* set text prompt mode for broken GetString widgets */
	      break;
	  case 'b':
	      Boardnum = atoi(optarg);
	      if (Boardnum < 0 || Boardnum >= Numboards) {
		  fprintf(stderr,
			  "testfadc: board must be between 0 - %d, not %d\n",
			  Numboards-1, Boardnum);
		  exit(1);
	      }
	      break;
	  case '?':
	  default:
	      usage();
	      exit(1);
	}
    }

    if (Boardnum == -1) {
	fprintf(stderr, 
		"testfadc: you must set the board (1-%d) using the -b option\n",
		Numboards);
	usage();
	exit(1);
    }

    /* Open log file */

    Logfile = fopen("testfadc.log", "a");
    if (Logfile == NULL) {
	perror("logfile fopen");
	exit(1);
    }

    /* Open param file */
    open_param_file();


    /* initialize hardware */
    
/*     for (i=0; i<Numboards; i++) { */
/* 	if (i != Boardnum) {  */
/* 	    fadc_ignore_board( i ) ; */
/* 	} */
/*     } */

    fadc_verbose(1);

    if (fadc_init()) {
	warn("FADC init failed!\n");
	exit(1);
    }

    /* Check if board exists... */

    if ( fadc_is_board_present(Boardnum) == 0 ) {
	warn("** Board %d was not detected in the crate!\n",Boardnum);
	warn("** If it is present, check that the address is correct\n");
	fadc_exit();
	exit(1);
    }
    

    /* Load saved board settings */
    sprintf(text,"fadc-board-%d.settings", Boardnum);
    if (fadc_load_settings( Boardnum,text )) {
	warn("No settings found for board %d, using defaults.\n", Boardnum);
    }

    Datawidth = fadc_get_data_width( Boardnum );
    
    if( fmod(log((double)Datawidth),log(2.0)) < 1e-5) {
	Fft_is_doable = 1;
	warn("Datawidth is a power of 2 - enabling FFT calculations\n");
    }

    warn("Clock/trigger board unique serial number is: %ld\n", 
	 fadc_get_serial_number(CLOCKBOARD) );

    Uniqueid = fadc_get_serial_number( Boardnum );
    warn("FADC board unique serial number is: %ld\n", Uniqueid );


    /* Initialize Graphdata structure */ 

    width = (Datawidth*4)*0.3333333;

    for(i=0; i<NUMCHANNELS; i++){
	Graphdata[i].prevscaler = 0;
	Graphdata[i].pedoffs = Datawidth*4 - width;
	Graphdata[i].pedwidth = width;
	Graphdata[i].pulseoffs = 0;
	Graphdata[i].pulsewid = width;
	Graphdata[i].thresh = 60;
	/* initialize histograms */
	/* want 0.5ns bins: 
	   nsamp = datawidth*4
	   tau = nsamp * 2  (ns)
	   nbins = tau / (0.5ns per bin)
	         = nsamp*2 / (0.5) 
		 = datawidth*4*2 / 0.5 = datawidth*16 bins  */

	histogram_new( &(Graphdata[i].areahist), 0, 5000, 500 ); 
	histogram_new( &(Graphdata[i].peakhist), 0, 255, 256 ); 
	histogram_new( &(Graphdata[i].widthhist),0,Datawidth*4, Datawidth*16); 
	histogram_new( &(Graphdata[i].thmax1hist),0,Datawidth*4,Datawidth*16); 
	histogram_new(&(Graphdata[i].tthreshhist),0,Datawidth*4,Datawidth*16);
	histogram_new(&(Graphdata[i].threshwidthhist),0,
		      Datawidth*4,Datawidth*16);
    }

    Toggle[TOGGLE_HIST] = 0;
    Toggle[TOGGLE_ANALYSIS] = 1;

    /* initialize display */

    init_display(argc, argv);

    warn("----------------------------------------------\n");

    /* Put the FADC in command mode (not acquisition) */
    fadc_set_mode(Boardnum, WORD_MODE);

    warn("Using board %d with board id %d\n", Boardnum, 
	 fadc_get_serial_number(Boardnum));
    warn("Performing FADC buffer ram test...\n");
    sleep(1);
    if (fadc_buffer_ram_test(Boardnum)) {
	warn( "*** BUFFER RAM TEST FAILED!\n");
	warn( "*** Is FADC board %d installed? If so, it may\n");
	warn( "*** be malfunctioning.\n\n");
	exit(1);
    } else {
	warn("Buffer ram test PASSED\n");
    }

    warn("Max event size: %d words\n",fadc_get_max_evt_size(Boardnum));
    Buffersize = fadc_get_max_evt_size(Boardnum) + 1000;
    Buffer = calloc(Buffersize, sizeof(unsigned long));

    warn("Clearing scalers...\n");
    fadc_clear_trigger_scaler( Boardnum, FADC_ALL );
   
    /* Start the FADC data acquisition */
    warn("entering FADC mode (acquisition started)\n");
    fadc_set_mode( Boardnum, FADC_MODE );
    fadc_evt_clr();
    

    /* Start the gui */
    ShowDisplay();
    MainLoop();

    return(0);
}


/*-----------------------------------------------------*/
/* Functions */
/*-----------------------------------------------------*/

void
open_param_file(void) {
    Paramfile = fopen("testfadc.param", "w");
    if (Paramfile == NULL) {
	perror("paramfile fopen");
	exit(1);
    }
}

void 
warn(char *format, ...) {

    char *thetime;
    time_t lt;
    va_list ptr;

    lt = time( NULL );
    thetime = ctime( &lt );
    thetime[strlen(thetime)-1] = '\0';

    fprintf(stderr,"testfadc: ");
    fprintf(Logfile,"%s: ", thetime );

    va_start( ptr, format );
    vfprintf( stderr, format, ptr );
    vfprintf( Logfile, format, ptr );
    va_end( ptr );


}

void usage(void) {

    fprintf(stderr, "USAGE: testfadc [-t] -b boardnum  \n");
    fprintf(stderr, "  -t use text console for input (if the graphical\n");
    fprintf(stderr, "     dialog boxes don't work due to a libsx bug)\n");
	    
}


/* Ask user for input */
unsigned long
ask_for_int( char *text, unsigned long def ) {

    unsigned long val;

    if (Usetext) {
	/* just use console ... */
	printf( "%s [was %d] NEW VALUE= ",text,def );
	fflush(stdout);
	scanf( "%d", &val );
	printf("VALUE = 0x%08lx\n", val);
	if (val<0) return -1;
    }
    else {
	/* use GetString */

	char *answer, defstr[20];

	sprintf( defstr, "%ld", def );
	answer = GetString( text, defstr );
	
	if (answer == NULL)
	    return -1;
	else {
	    val = atoi(answer);
	}
	
    }

    return val;
}

/* recalculate singles rates */
void
recalc_rates(void) {

    double newtime;
    double elapsed;
    unsigned long hits;
    int i;

    newtime = get_time();
    elapsed = newtime - Rtime;

    fadc_set_mode( Boardnum, WORD_MODE );

    for (i=0; i<NUMCHANNELS; i++) {
	
	Graphdata[i].scaler = fadc_get_trigger_scaler( Boardnum, i );
	//	Graphdata[i].scaler &= 0x03FFFFFF;

	if (Graphdata[i].scaler >= Graphdata[i].prevscaler)
	    hits = Graphdata[i].scaler - Graphdata[i].prevscaler;
	else {
	    hits = Graphdata[i].scaler + 
		(unsigned long)(1<<25) - Graphdata[i].prevscaler;
	    warn("Ch %d scaler wrapped: previous = 0x%lx, current = 0x%lx\n",
		   i,Graphdata[i].prevscaler,Graphdata[i].scaler);
	}

	Graphdata[i].rate = (double)hits/(double)elapsed;
	Graphdata[i].prevscaler = Graphdata[i].scaler;
    }
    
    fadc_set_mode( Boardnum, FADC_MODE );
    
    // is this needed? probably not
    //fadc_evt_clr();

    Rtime = newtime;


}

#define PEAK_THRESH 30

int sign(double arg) {

    if (arg<0) return -1;
    if (arg>=0)  return 1;
    
}

/* Helper function to search for the position on a waveform where the
 * pulse is at a given height (for rise, fall, leading edge and
 * trailing edge time calculations).  Start at start_time and proceed
 * forward if step is +1 or backward if direction is -1. Slope is the
 * slope in the direction of step (positive or negative). Results are
 * linearly interpolated */
double
find_time( double height, unsigned char *pulse, int start_time, int step ) {

    register int i;
    double t;
    int startsign;

    startsign = sign(pulse[start_time] - height);


    if (step<0) {

	/* move left until f(t)-height crosses 0 */
	for (i=start_time; i>=0 ; i--) {
	    if (sign(pulse[i] - height) != startsign) break;
	}
    
	/* Now, f(i) <height  and f(i+1) > height, so interpolate*/
	t = ((double)height - (double)pulse[i]) * 
	    (1.0/((double)(pulse[i+1]) - (double)(pulse[i]))) 
	    + (double)i; 
	
    }
    else {
	/* move right until f(t)-height = 0 */
	for (i=start_time; i<Datawidth*4; i++) {
	    if (sign(pulse[i] - height) != startsign) break;
	}

	/* now f(i) < height and f(i-1)>height, so interpolate */
	
	t = (height - (double)(pulse[i])) *
	    (1.0/((double)(pulse[i]) - (double)(pulse[i-1])))
	    + (double)i;

    }

    return t;

}


/* calculate the pedestals, pedvars, areas */
void
analyze_pulse(void) {

    int ch,i;
    double ped=0, ped2=0, area=0;
    unsigned long areawid;
    double rarea, halfmax;
    double max10,max90, tmax10, tmax90;
    struct GraphData *gd;
    unsigned long thresh,offset,width,type;
    double tthresh1,tthresh2;
    double peak;
    
    Nanalyzed++;
    
    for (ch=0; ch<NUMCHANNELS; ch++) {
	if (!fadc_is_channel_disabled(Boardnum,ch)) {
	
	    areawid = fadc_get_area_width( Boardnum,ch );
	    gd = &(Graphdata[ch]);  
	    
	    /* Calculate the pedestal value (average over pedestal window) */
	    /* the pedestals dispersion must be calculated separately from 
	       the value in the measurement_add function since it depends 
	       on all the samples */
	    
	    ped = ped2 = 0;
	    for(i=gd->pedoffs; 
		i<(gd->pedoffs+gd->pedwidth); i++){
		ped += gd->pulse[i];
		ped2+= pow((int)gd->pulse[i],2);
	    }
	    ped /= (double) gd->pedwidth;
	    ped2 /=(double) gd->pedwidth;

	    gd->ped.nsamples++;
	    gd->ped.value = ped;
	    gd->ped.sum += ped;
	    gd->ped.sum2 += ped2;  /* this is the difference (See above) */
	    gd->ped.avg = (gd->ped.sum / (double)gd->ped.nsamples);
	    gd->ped.sigma = sqrt(gd->ped.sum2 / 
				 (double) gd->ped.nsamples - 
				 (gd->ped.avg * gd->ped.avg) );	    



	    /* Calculate the area under the pulse, subtracting pedestal 
	     * and also the peak value of the pulse */
	    
	    area = 0; peak=0;
	    gd->min = 255; gd->max=0;
	    for(i=gd->pulseoffs;i<(gd->pulseoffs+gd->pulsewid); i++) {
		rarea = (int)gd->pulse[i] - ped;
		area += rarea;
		if ( rarea > peak ) { 
		    peak = rarea;
		    gd->tpeak = i;
		}
		if ((double)gd->pulse[i] > gd->max) gd->max = gd->pulse[i];
		if ((double)gd->pulse[i] < gd->min) gd->min = gd->pulse[i];

	    }


	    measurement_add( &(gd->peak), peak );
	    measurement_add( &(gd->softarea), area );
	    measurement_add( &(gd->p2p), gd->max-gd->min );

	    if (peak > gd->thresh) {

		/* First check if the pulse is contained in the pulse
                 * region, if not don't calculate the width etc.*/
		
		if (gd->pulse[gd->pulseoffs] < gd->thresh ) {

		    /* Find the threshold crossing time (for absolute
		     * leading edge time jitter calculation */
		    
		    tthresh1 = find_time( gd->thresh, gd->pulse,
					  gd->pulseoffs, 1);
		    tthresh2 = find_time( gd->thresh, gd->pulse,
					  gd->tpeak, 1);
		    
		    measurement_add( &(gd->tthresh), tthresh1 );
		    measurement_add( &(gd->threshwidth), tthresh2-tthresh1 );
		    
		}
		else {
		    tthresh1 = tthresh2 = 0;
		}

		/* Calculate the half-max times and later, the 10% and
		 * 90% max for rise and fall calculations. First go
		 * left from the peak, then right to get the halfmax
		 * times*/
	    		
		halfmax = peak/2.0 + ped;
		max10   = peak/10.0 + ped;
		max90   = peak*9.0/10.0 + ped;

		measurement_add( &(gd->thalfmax1),
				 find_time( halfmax,gd->pulse,gd->tpeak, -1));
		
		measurement_add( &(gd->thalfmax2),
				 find_time( halfmax,gd->pulse,gd->tpeak, 1));

		measurement_add( &(gd->softwidth), 
				 gd->thalfmax2.value - gd->thalfmax1.value);

		/* now find the rise time */

		tmax10 = find_time( max10, gd->pulse, gd->thalfmax1.value,-1 );
		tmax90 = find_time( max90, gd->pulse, gd->thalfmax1.value, 1 );
		measurement_add( &(gd->trise), tmax90-tmax10);
		
		/* fall time */

		tmax90 = find_time( max90, gd->pulse, gd->thalfmax2.value,-1);
		tmax10 = find_time( max10, gd->pulse, gd->thalfmax2.value,1 );
		measurement_add( &(gd->tfall), tmax10 - tmax90 );


	    }
	    else {
		/* Pulse didn't cross the threshold (peak < gd->thresh) */
		gd->thalfmax1.value = 0;
		gd->thalfmax2.value = 0;
		tthresh1 = tthresh2 = 0;
	    }
	
	    /* update the area and peak and width histograms */
	    histogram_add( &(gd->areahist), (double) area );
	    histogram_add( &(gd->peakhist), (double) (gd->peak.value) );
	    histogram_add( &(gd->widthhist),(gd->thalfmax2.value 
					     - gd->thalfmax1.value));
	    histogram_add( &(gd->thmax1hist),(gd->thalfmax1.value));
	    histogram_add( &(gd->tthreshhist), tthresh1 );
	    histogram_add( &(gd->threshwidthhist), tthresh2-tthresh1 );
	    
	    /* Calculate running area and pedestal averages */
	    
	    /* write parameters to disk */
	    /* FORMAT: columns area, peak, pedarea, ped, thalfmax1,
	       width,dthresh,doffset,dwidth,rate*/
	       
	    type = fadc_get_cfd_type( Boardnum, ch );
	    if (type == CFD_WASHU) {
		thresh = fadc_get_cfd_wuthresh( Boardnum, ch  ); 
		offset = fadc_get_cfd_wuoffs( Boardnum, ch ); 
		width = -1;
	    }
	    else { 
		thresh = fadc_get_cfd_thresh( Boardnum, ch  ); 
		offset = fadc_get_cfd_ratefb( Boardnum, ch );
 		width  = fadc_get_cfd_width( Boardnum, ch );
	    }

/* 	    fprintf( Paramfile, "%f,%f,%f,%f,%f,%f,%u,%u,%u,%d",  */
/* 		     (double)area, */
/* 		     (double)(gd->peak.value),  */
/* 		     gd->ped.value * gd->pedwidth, */
/* 		     gd->ped.value, */
/* 		     gd->thalfmax1.value, */
/* 		     gd->thalfmax2.value-gd->thalfmax1.value, */
/* 		     thresh, */
/* 		     offset, */
/* 		     width, */
/* 		     gd->rate); */
		     
/* 	    if (gd->num <9) fprintf( Paramfile,","); */
/* 	    else fprintf( Paramfile, "\n" ); */
	    
    
	}

	/* do FFT if requested */
	/* TODO: the output pulse is not in the right format! */

	if (Graphdata[ch].fft == 1) {
	    for (i=0; i<Datawidth*4; i++){
		Graphdata[ch].fftpulse[i] = (double) Graphdata[ch].pulse[i];
	    }
	    gsl_fft_real_radix2_transform( Graphdata[ch].fftpulse, 
					   1, Datawidth*4);
	    
	}

    }
}

#define MASK_SYNC 0xffff0000    /* sync word from start header */
#define OFFS_SYNC 16            /* sync word offset */
#define MASK_WORDSPERCHAN 0xff  /* words per channel mask for start hdr*/
#define MASK_EVTNUM 0x03ffffff  /* event number from evt header */
#define MASK_HITPTN 0x3ff       /* hit pattern from hit header */
#define MASK_TRIGPTN 0x000ffc00 /* trig pattern from hit header */
#define OFFS_TRIGPTN 9          /* trig pattern offset */      
#define MASK_HILOPTN 0x3ff00000 /* hi/lo pattern from hit header */
#define OFFS_HILOPTN 20         /* hi/lo pattern offset */
#define MASK_CHAN 0xF0000000    /* chan number from area hdr */
#define OFFS_CHAN 28            /* offset to channel number */
#define MASK_AREA 0x7FFFF       /* area from area header */

int
parse_data( unsigned long *buf ) {

    unsigned long start_hdr;
    unsigned long evt_hdr;
    unsigned long hit_hdr;
    unsigned long area_hdr;
    unsigned long hit_pattern;
    unsigned long trigger_pattern;
    unsigned long hilo_pattern;
    unsigned long *lptr; 
    int i,ch,realch,ndatawords;

    /* Check the sync word */

    start_hdr = buf[0];
    evt_hdr = buf[1];
    hit_hdr = buf[2];

    if ( ((start_hdr & MASK_SYNC) >> OFFS_SYNC) != 0xFADC ) {
	warn("SYNC word (0xFADC) not found!, skipping event (last good evt was %u)\n", 
	     Eventno);
	return -1;
    }


    /* get number of data words per channel */

    ndatawords = (start_hdr & MASK_WORDSPERCHAN );

    /* get the Event number */

    Eventno = (evt_hdr & MASK_EVTNUM);

    /* get the hit, hi/lo, and trigger patterns */

    hit_pattern     = hit_hdr & MASK_HITPTN;
    trigger_pattern = (hit_hdr & MASK_TRIGPTN) >> OFFS_TRIGPTN;
    hilo_pattern    = (hit_hdr & MASK_HILOPTN) >> OFFS_HILOPTN;

    /* Display the headers */

    if (Showdata) {
	printf("START header : "); binary_print( start_hdr );
	printf("EVENT header : "); binary_print( evt_hdr );
	printf("HIT header   : "); binary_print( hit_hdr );
	printf("Event Number : %d\n", Eventno );
	printf("Data Width   : %d words\n", ndatawords );
    }

    /* Now loop over channels, and check the hit pattern to see if the
     * channel returned data */

    lptr = &buf[3]; /* start of data */

    for (ch = 0; ch<10; ch++) {
	
	/* if channel ch has a hit */
	if (hit_pattern & (1<<ch)) { 

	    /* grab the next area_header */
	    area_hdr = lptr[ndatawords];
	    if (Showdata) {
		printf("CHANNEL %d ----------------------------\n", ch);
		printf("AREA header  : "); binary_print(area_hdr);
	    }

	    /* Get the reported channel number and compare */
	    realch = (area_hdr & MASK_CHAN) >> OFFS_CHAN;
	    if (realch != ch) {
		warn("*** PARSE ERROR:  Should be chan %d, but says %d\n",
		     ch,realch);
		//		return(-1);
	    }

	    /* get the hi/lo flag */
	    Graphdata[ch].hilo = (hilo_pattern & (1<<ch)) ? 1:0;

	    /* get the hardware computed area */
	    Graphdata[ch].area = area_hdr & MASK_AREA;

	    /* get the data itself */
	    memcpy( Graphdata[ch].pulse, lptr, ndatawords*sizeof(unsigned long) );
	    
	    if (Showdata) {
		printf("DATA: \n");
		for (i=0; i<ndatawords*4; i++){
		    printf("%d ", (int)Graphdata[ch].pulse[i]);
		    if ((i+1)%20==0) printf("\n");
		}
		printf("\n\n");
	    }
		
	    
	    /* jump the pointer to the next event location */
	    lptr += ndatawords+1;  

	}
	else {
	    memset( Graphdata[ch].pulse, 0, MAX_SAMPLES );
	}

    }
    return 0;

}

void
binary_print(unsigned long word) {

    unsigned long mask = 0x80000000;
    int i;
    
    printf("0x%08lx [ ", word);
    for (i=0; i<32; i++) {
	if ( (word & mask) != 0 ) printf("1") ;
	else printf("0");
	if ((i+1)%4 == 0) printf(" ");
	mask = mask >> 0x1;
    }
    printf("]\n");

}



/* tick - running loop */
void
tick( void *data, XtIntervalId *id)
{

    unsigned long nwords;
    int i;


    if (fadc_got_event()==1) {

	nwords = fadc_data_available(Boardnum);

	SetBgColor( wid[TRIGGER_L], RED );

	if (nwords) {


	    if (Showdata) {
		printf("\n\nGot %ld words of data\n", nwords);
	    }
	
	    assert( nwords <= Buffersize );
	    fadc_memcpy( Buffer, Boardnum, nwords );

	    parse_data(Buffer);
	    
	    if (Holdevent) {
		/* if event is held (not reset) - for instance for
		   reread/ped/dump commands, do nothing... */

		printf("Holding event (no clear)\n");
		Holdevent=0; /* hold event just once */
	    }
	    else {
		/* otherwise, clear the event */
		fadc_evt_clr();
	    }

	    /* do analysis calculations */
	    if (Toggle[TOGGLE_ANALYSIS]) {
		analyze_pulse();
	    }
	} 
	else {

	    warn("Got event (according to CT board), but no data on "
		 "FADC (nwords=0)\n");
	    fadc_evt_clr();

	}
    }
    else {
	SetBgColor( wid[TRIGGER_L], WHITE );
    }
    
    if (Showdata) {
	Showdata=0;
    }

    /* recalculate singles rates */
    if (Cycle % RATE_CYCLE == 0 || Showdata != 0)
	recalc_rates();
    
    /* update display if needed  */
    if (Cycle % Refresh == 0) {
	for(i=0; i<NUMCHANNELS; i++){
	    c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
	}
    }
    
    
    Cycle++;
    
    /* keep it running... */
    if(Running) {   
	AddTimeOut( Timeout_interval, (GeneralCB) tick, NULL );
    }
    
}

void
c_toggle( Widget w, void *data ) {

    int tognum = (int)data;

    if (Toggle[tognum]) Toggle[tognum] = 0;
    else Toggle[tognum] = 1;

}

void
c_one_evt( Widget w, void *data )
{
    //    fadc_evt_clr();
    Showdata=1;
    fprintf(stderr, "ONE EVENT:\n");
    if (Running == 0) 
	AddTimeOut( Timeout_interval, (GeneralCB) tick, NULL);
}


void 
c_go(Widget w, void *data ) {

    int i;
    char text[100];
    
    //    fadc_evt_clr();
    if (Running == 0) {
	int i;
	warn("STARTING display acquisition\n");
	//	printf("testfadc: STARTING display acquisition.\n");
	SetLabel( w, "STOP" );
	Running =1;

	AddTimeOut( Timeout_interval, (GeneralCB) tick, NULL);
    } else {
	
	warn("STOPPING display acquisition.\n");
	SetLabel( w, "GO" );
	Running = 0 ;
	

    }
}

void
c_save_analysis(Widget w, void *data) {

    int i;
    char text[128];

    /* TODO: ask for run identifier to tack on to filename */
    /* TODO: get yes no question */
    warn("Writing histograms to disk...\n");
    for (i=0; i<NUMCHANNELS; i++) {
	sprintf( text,"area-hist-%d.dat", i );
	histogram_write( &(Graphdata[i].areahist), text );
	sprintf( text,"peak-hist-%d.dat", i );
	histogram_write( &(Graphdata[i].peakhist), text );
	sprintf( text,"width-hist-%d.dat", i );
	histogram_write( &(Graphdata[i].widthhist), text );
	sprintf( text,"thmax1-hist-%d.dat", i );
	histogram_write( &(Graphdata[i].thmax1hist), text );
	sprintf( text, "tthresh-hist-%d.dat", i);
     	histogram_write( &(Graphdata[i].tthreshhist), text );
	sprintf( text, "threshwidth-hist-%d.dat", i);
     	histogram_write( &(Graphdata[i].threshwidthhist), text );
    }
    warn("DONE writing histograms\n");

}

void
c_save_settings(Widget w, void *data) {

    char *fname;
    char def[100];

    sprintf( def, "fadc-board-%d.settings", Boardnum);

    fname = GetString("Enter a board settings filename:", def );
    
    if (fname) {
	warn( "Saving settings to '%s'\n", fname );
	fadc_save_settings( Boardnum, fname );
    }
    
}



void 
c_clear_analysis(Widget w, void *data) {

    int i;

    for(i=0; i<NUMCHANNELS; i++){
	Graphdata[i].hilo = 0;
	Graphdata[i].fft = 0;
	histogram_clear( &(Graphdata[i].areahist) );
	histogram_clear( &(Graphdata[i].peakhist) );
	histogram_clear( &(Graphdata[i].widthhist) );
	histogram_clear( &(Graphdata[i].thmax1hist) );
	histogram_clear( &(Graphdata[i].tthreshhist) );
	measurement_clear( &(Graphdata[i].tthresh) );
	measurement_clear( &(Graphdata[i].ped) );
	measurement_clear( &(Graphdata[i].thalfmax1) );
	measurement_clear( &(Graphdata[i].thalfmax2) );
	measurement_clear( &(Graphdata[i].softwidth) );
	measurement_clear( &(Graphdata[i].threshwidth) );
	measurement_clear( &(Graphdata[i].peak) );
	measurement_clear( &(Graphdata[i].p2p) );
	measurement_clear( &(Graphdata[i].softarea) );
	measurement_clear( &(Graphdata[i].trise) );
	measurement_clear( &(Graphdata[i].tfall) );
	c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );

    }

    fadc_clear_trigger_scaler(Boardnum, FADC_ALL);

    /* reset parameter file */
    fclose(Paramfile);
    open_param_file();

    Nanalyzed = 0;
    warn("analysis reset\n");


}



void
c_exit(Widget w, void *data)
{
    warn("Shutting down FADC interface...\n");
    fcloseall();
    fadc_exit();
    free(Buffer);
    exit(0);
}

void 
c_snapshot(Widget w, void *data )
{
    /* dump data for channel for plotting purposes... */
    struct GraphData *gd;
    char outfilename[100], def[100]="pulse_dump", *basename;
    FILE *outfile;
    int i;
    int ch;
    int dw;

    basename = GetString( "Enter output name (-N.dat will be appended): ", def );
    if (basename == NULL) return;

    for (ch=0; ch<NUMCHANNELS; ch++) {
	gd = &Graphdata[ch];

	sprintf( outfilename, "%s-%d.dat", basename, ch );
	
	if(( outfile = fopen( outfilename, "w")) == NULL){
	    printf( "Snapshot error: could open output file (%s)\n", outfilename);
	    continue;
	}
	
	printf("Writing snapshot %s...\n", outfilename);
	fprintf(outfile,
		"# GNUPLOT DATA FOR CHANNEL 1: (t in ns, pulse height)\n");
	for(i=0; i< Datawidth*4; i++) {
	    fprintf( outfile, "%f\t%d\n", i*2.0, (int)(gd->pulse[i]) );
	}
	fclose(outfile);
	
    }
    printf("Done writing snapshots.\n"); 
    
}

void
c_set_area_offs( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval, oldval;
    int i;

    oldval = fadc_get_area_offset( Boardnum, 0 );
    newval = ask_for_int( "Enter area offset in nanoseconds: ", oldval);

    if (newval >= 0) {
	if (newval>4095) {
	    printf("ERROR: area offset out of range.  Not changing.\n\n");
	} else {
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_area_offset( Boardnum, i, newval );
		}
	    }
	}
    }
}

void
c_set_area_width( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval, oldval;

    oldval = fadc_get_area_width( Boardnum, 0 );
    newval = ask_for_int( "Enter area width: ", oldval);

    if (newval >= 0){
	if (newval>128) {
	    printf("ERROR: area width out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_area_width( Boardnum, i, newval );
		}
	    }
	}
    } 
    else 
	printf("Cancel.\n");
    
}

void
c_set_area_discrim( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval, oldval;

    oldval = fadc_get_area_discrim( Boardnum, 0 );
    newval = ask_for_int( "Enter area discrim (0-255): ", oldval);

    if (newval >= 0) {
	if (newval>255) {
	    printf("ERROR: area discrim out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_area_discrim( Boardnum, i, newval );
		}
	    }
	}
    }
}
 
void
c_set_data_offs( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval, oldval;

    oldval = fadc_get_data_offset( Boardnum, 0 );
    newval = ask_for_int( "Enter data offset: ", oldval);

    if (newval >= 0) {
	if (newval>4095) {
	    printf("ERROR: data offset out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_data_offset( Boardnum, i, newval);
		}
	    }
	}
    }
}
 
void
c_set_cfd_wuthresh( Widget w, void *data)
{
    char *answer, def[20]; 
    unsigned long newval,oldval;

    oldval = fadc_get_cfd_wuthresh( Boardnum, 0  );
    newval = ask_for_int( "Enter WU CFD threshold: ", oldval); 

    if (newval >= 0) {
	if (newval>4095) {
	    printf("ERROR: data offset out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_cfd_wuthresh( Boardnum, i, newval);
		}
	    }
	}
    }
    
}

void
c_set_cfd_wuoffs( Widget w, void *data)
{
    char *answer, def[20]; 
    unsigned long newval,oldval;

    oldval = fadc_get_cfd_wuoffs( Boardnum, 0  );
    newval = ask_for_int( "Enter WU CFD offset: ", oldval); 

    if (newval >= 0) {
	if (newval>4095) {
	    printf("ERROR: data offset out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_cfd_wuoffs( Boardnum, i, newval);
		}
	    }
	}
    }

}
 
void
c_set_cfd_ratefb( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval,oldval;

    oldval = fadc_get_cfd_ratefb( Boardnum, 0 );
    newval = ask_for_int( "Enter CFD rate feedback setting (0-127): ", oldval);

    if (newval >= 0) {
	if (newval>=128) {
	    printf("ERROR: cfd ratefb out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]){ 
		    fadc_set_cfd_ratefb(Boardnum, i, newval);
		}
	    }
	}
    }
    else 
	printf ("Cancel\n");
}

void
c_set_cfd_width( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval,oldval;

    oldval = fadc_get_cfd_width( Boardnum, 0 );
    newval = ask_for_int( "Enter CFD width DAC (12 bits): ", oldval);

    if (newval>=0) {
	if (newval>=4096) {
	    printf("ERROR: cfd ratefb out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_cfd_width(Boardnum, i, newval);
		}
	    }
	}
    }
}

void
c_set_cfd_thresh( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval,oldval;

    oldval = fadc_get_cfd_thresh( Boardnum, 0 );
    newval = ask_for_int( "Enter CFD thresh DAC (12 bits): ", oldval);

    if (newval >= 0) {
	if (newval>=4096) {
	    printf("ERROR: cfd thresh out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_cfd_thresh(Boardnum, i, newval);
		}
	    }
	}
    }
}

void
c_set_cfd_delay( Widget w, void *data)
{
    char *answer, def[20];
    unsigned long newval,oldval;

    oldval = fadc_get_cfd_delay( Boardnum, 0 );
    newval = ask_for_int( "Enter CFD thresh DAC (12 bits): ", oldval);

    if (newval >= 0) {
	if (newval>=8) {
	    warn("ERROR: CFD delay out of range.  Not changing.\n\n");
	} else {
	    int i;
	    for(i=0; i<NUMCHANNELS; i++) {
		if (Selected[i]) {
		    fadc_set_cfd_delay(Boardnum, i, newval);
		}
	    }
	}
    }
}


void 
c_buf_ram_test( Widget w, void *data ) {

    int result;

    result = fadc_buffer_ram_test( Boardnum );

    if (result) {
	GetYesNo("Buffer RAM test FAILED! \nSee the console for more info.");	
    }
    else {
	GetYesNo("Buffer RAM test PASSED!");
    }


}

void
c_issue_read(Widget w, void *data) {

    Holdevent = 1; /* hold event (one-shot) */
    c_one_evt( w,NULL );

}

void 
c_issue_ped(Widget w, void *data ) {
    int i;
    int olddwidth;
    
    fadc_request_pedestal();
    Holdevent = 1; /* hold event (one-shot) */
    
    olddwidth = Datawidth;
    Datawidth = fadc_get_pedestal_width(Boardnum);
    c_one_evt( w,NULL );
    Datawidth = olddwidth;

}


void 
c_issue_reread(Widget w, void *data ) {
    int i;

    fadc_request_reread();
    Holdevent = 1; /* hold event (one-shot) */
    c_one_evt( w,NULL );

}

void 
c_issue_dump(Widget w, void *data ) {
    int i;

    fadc_request_dump();
    Holdevent = 1; /* hold event (one-shot) */
    c_one_evt( w,NULL );

}



void
update_view(struct GraphData *gd) {
    
    char text[100], text2[100];
    unsigned long viewval;
    
    /* display the selected "view" value */
    switch (View) {
	
    case VIEW_SCALERS:
	viewval = gd->scaler;
	sprintf(text,"%d", (int)viewval);
	text2[0] = '\0';
	break;
	
    case VIEW_AREA:
	viewval = gd->area;
	sprintf(text,"%ld", viewval);
	text2[0] = '\0';
	break;
	
    case VIEW_RATE:
	sprintf(text,"%f", gd->rate);
	text2[0] = '\0';
	break;
	
    case VIEW_PED:
	sprintf(text,"%f", gd->ped.value);
	text2[0] = '\0';
	break;
	
    case VIEW_PED_AVG:
	sprintf(text,"%f", gd->ped.avg);
	sprintf(text2,"(%f)", gd->ped.sigma);
	break;
	
    case VIEW_SOFT_AREA:
	sprintf(text,"%f", gd->softarea.value);
	text2[0] = '\0';
	break;
	
    case VIEW_AREA_AVG:
	sprintf(text,"%f", gd->softarea.avg);
	sprintf(text2,"(%f)", gd->softarea.sigma);
	break;
	
    case VIEW_PEAK:
	sprintf(text,"%f", gd->peak.value);
	text2[0] = '\0';
	break;
	
    case VIEW_PEAK_AVG:
	sprintf(text,"%f", gd->peak.avg);
	sprintf(text2,"(%f)", gd->peak.sigma);
	break;	   
	
    case VIEW_LEADEDGE:
	sprintf(text,"%f", gd->thalfmax1.value);
	text2[0] = '\0';
	break;

    case VIEW_LEADEDGE_AVG:
	sprintf(text,"%f", gd->thalfmax1.avg);
	sprintf(text2,"(%f)", gd->thalfmax1.sigma);
	break;	   

    case VIEW_WIDTH:
	sprintf(text,"%f", gd->softwidth.value);
	text2[0] = '\0';
	break;
	
    case VIEW_WIDTH_AVG:
	sprintf(text,"%f", gd->softwidth.avg);
	sprintf(text2,"(%f)", gd->softwidth.sigma);
	break;

    case VIEW_THRESH_WIDTH:
	sprintf(text,"%f", gd->threshwidth.value);
	text2[0] = '\0';
	break;
	
    case VIEW_THRESH_WIDTH_AVG:
	sprintf(text,"%f", gd->threshwidth.avg);
	sprintf(text2,"(%f)", gd->threshwidth.sigma);
	break;
	   
    case VIEW_PEAK2PEAK:
	sprintf(text, "%f", gd->p2p.value);
	text2[0] = '\0';
	break;

    case VIEW_PEAK2PEAK_AVG:
	sprintf(text, "%f", gd->p2p.avg);
	sprintf(text2,"(%f)", gd->p2p.sigma);
	break;

    case VIEW_RISETIME:
	sprintf(text, "%f", gd->trise.value);
	text2[0] = '\0';
	break;

    case VIEW_RISETIME_AVG:
	sprintf(text, "%f", gd->trise.avg);
	sprintf(text2,"(%f)", gd->trise.sigma);
	break;

    case VIEW_FALLTIME:
	sprintf(text, "%f", gd->tfall.value);
	text2[0] = '\0';
	break;

    case VIEW_FALLTIME_AVG:
	sprintf(text, "%f", gd->tfall.avg);
	sprintf(text2,"(%f)", gd->tfall.sigma);
	break;


    case VIEW_TTHRESH:
	sprintf(text, "%f", gd->tthresh.value);
	text2[0] = '\0';
	break;

    case VIEW_TTHRESH_AVG:
	sprintf(text, "%f", gd->tthresh.avg);
	sprintf(text2,"(%f)", gd->tthresh.sigma);
	break;


    }
    SetLabel(Viewbox[gd->num], text);
    SetLabel(Errbox[gd->num], text2);
}

void
c_redisplay(Widget w, int width, int height, void *data)
{
    int i;
    float xscale, fftyscale; 
    float yscale;
    struct GraphData *gd;
    unsigned long areawid, datawid;
    int dis;
    float yh, xh;
    char text[100];

    GetDrawAreaSize( &width, &height );

    xscale = (float)width/((float)Datawidth*4.0);
    yscale = (float)height/(float)256;
    //    fftyscale = (float)height/8;
    fftyscale = (float)height/16384;

    SetDrawArea(w);
    gd = (struct GraphData *) data;

    if (!Selected[gd->num]) {
	SetBgColor( w,Color[PULSE_BG_INACTIVE_COLOR]);
	SetBorderColor( w,WHITE );
    }
    else{ 
	SetBgColor( w,WHITE );
	SetBorderColor( w,BLACK );
    }

    SetLineWidth(1);

    SetColor( BLACK );
    if (!Toggle[TOGGLE_PERSIST]) ClearDrawArea();

    dis = fadc_is_channel_disabled( Boardnum, gd->num );
    
    if( dis == 1) { /* if disabled */
	sprintf( text, "Channel %d Disabled",gd->num );
	DrawText( text, 10,10 );
    } 
    else if (dis < 0) {
	sprintf( text, "Channel %d CHANNEL OUT OF RANGE!",gd->num );
	DrawText( text, 10,10 );
    }
    else {

	update_view(gd);

	if (!Toggle[TOGGLE_PERSIST]) {

	    
	    if (gd->fft == 0) {
		/* Draw the Pulse and pedestal regions */
		if (!Selected[gd->num]) 
		    SetColor(Color[SOFT_PED_INACTIVE_COLOR]);
		else SetColor(Color[SOFT_PED_COLOR]);
		DrawFilledBox(xscale*gd->pedoffs,0,
			      xscale*(gd->pedwidth),height);
		
		if (!Selected[gd->num]) 
		    SetColor(Color[SOFT_PULSE_INACTIVE_COLOR]);
		else SetColor(Color[SOFT_PULSE_COLOR]);
		DrawFilledBox(xscale*gd->pulseoffs,0,
			      xscale*(gd->pulsewid),height);
		
	    }
	    
	    /* Draw the x-axis tick marks */
	    if (Selected[gd->num])	SetColor( RED );
	    else SetColor( 0x880000 );
	    for(i=0; i<Datawidth; i++) {
		DrawLine( i*xscale*4, 0, i*xscale*4, height);
	    }
	    
	    /* Draw the area width marker */
	    areawid = fadc_get_area_width( Boardnum, gd->num );
	    SetColor(BLUE);
	    DrawLine(xscale*areawid,0,xscale*areawid,height);

	    /* Draw the fft center  marker */
	    if (gd->fft) {
		SetColor(GREEN);
		DrawLine(xscale*Datawidth*2,0,xscale*Datawidth*2,height);
	    }
	    
	    /* Draw the channel number label */
	    if (Selected[gd->num])   SetColor( BLUE );
	    else SetColor( 0x888888 );
	    
	    if (gd->fft)
		sprintf( text, "CH%d (FFT)",gd->num);
	    else
		sprintf( text, "CH%d",gd->num);	    

	    DrawText( text, 10,10 );


	}

	/* Draw the waveform */
	if (gd->hilo == 1)
	    SetColor(RED);
	else
	    SetColor(BLACK);
	SetLineWidth(2);

	if (!gd->fft) {
	    /* Draw regular time-domain pulse */
	    for (i=0; i<Datawidth*4-1; i++){
		DrawLine( i*xscale, height - gd->pulse[i]*yscale, 
			  (i+1)*xscale, height - gd->pulse[i+1]*yscale);
	    }

	    for (i=0; i<Datawidth*4; i++) {
		SetColor(RED);
		DrawPixel( i*xscale, height-gd->pulse[i]*yscale );
	    }

	}
	else {
	    /* draw FFT pulse */
	    for (i=1; i<Datawidth*2; i++){
		//		DrawLine( (Datawidth*2+i-1)*xscale, 
		//			  height - log10(pow(gd->fftpulse[i-1],2))*fftyscale, 
		//			  (Datawidth*2+i)*xscale, 
		//			  height - log10(pow(gd->fftpulse[i],2))*fftyscale);

		DrawLine( (Datawidth*2+i-1)*xscale, 
			  height - (pow(gd->fftpulse[i-1],2))*fftyscale, 
			  (Datawidth*2+i)*xscale, 
			  height - (pow(gd->fftpulse[i],2))*fftyscale);
	    }
	    for (i<Datawidth*2; i>1; i--){
		//		DrawLine((i-1)*xscale, 
		//			 height - log10(pow(gd->fftpulse[Datawidth*2-i+1],2))*fftyscale,
		//			 (i)*xscale, 
		//			 height - log10(pow(gd->fftpulse[Datawidth*2-i],2))*fftyscale);

		DrawLine((i-1)*xscale, 
			 height - (pow(gd->fftpulse[Datawidth*2-i+1],2))*fftyscale,
			 (i)*xscale, 
			 height - (pow(gd->fftpulse[Datawidth*2-i],2))*fftyscale);
	    }

	}


	/* Draw the peak histogram */
	if (Toggle[TOGGLE_HIST]) {
	    SetLineWidth(1);
	    SetColor(0x999999);
	    for(i=0; i< gd->peakhist.nbins; i++) {
		
		yh = height - ((gd->peakhist.binwidth*i 
				+ gd->peakhist.min) + gd->ped.value) *yscale;
		
		xh = gd->peakhist.hist[i]/10.0;
		
		DrawLine( width, yh, width-xh, yh);
		
	    }
	}	
	SetLineWidth(2);
	SetColor(RED);
	DrawLine( width,height-gd->peak.value*yscale-gd->ped.value*yscale,
		  width-2, height-gd->peak.value*yscale-gd->ped.value*yscale);

	/* draw the measurements */

	SetLineWidth(1);
	SetColor(YELLOW);

	DrawLine( (gd->tpeak-1)*xscale,height-gd->peak.value*yscale-gd->ped.value*yscale,
		  (gd->tpeak+1)*xscale, height-gd->peak.value*yscale-gd->ped.value*yscale);

	DrawLine( (gd->thalfmax1.value)*xscale,0,
		  (gd->thalfmax1.value)*xscale, height);

	DrawLine( (gd->thalfmax2.value)*xscale,0,
		  (gd->thalfmax2.value)*xscale, height);



    }

    /* update evt numbers */
    sprintf(text,"%d", Eventno);
    SetStringEntry(wid[EVT_BOX], text);
    sprintf(text,"%d", Nanalyzed);
    SetStringEntry(wid[NAREAEVT_BOX], text);

}

void
c_set_refresh(Widget w, void *data) {
    
    int newval;

    newval = ask_for_int( "How many events do you want to process before a screen refresh?", Refresh);
    
    Refresh = newval;
    

}

void
c_set_tthresh_threshold(Widget w, void *data) {

    int newval,i;

    
    newval = ask_for_int( "Please enter the new threshold for the t_thresh calculation:", Graphdata[0].thresh);

    if (newval >=0 && newval <= 255){
	for(i=0; i<NUMCHANNELS; i++) {
	    if (Selected[i]) {
		Graphdata[i].thresh = newval;
	    }
	}
    }

    else
	warn("t_thresh threshold out of range, not changing\n");

}

void
c_close_zoom(Widget w, void *data) {

    CloseWindow();

}

void
c_zoom_channel(Widget w, void *data) {

    struct GraphData *zoomdata;
    int chan;
    Widget close, graph;

    chan = (int) data;
    
    //    if (Zoomwindowopen == 1)
    //	return;

    Zoomwindow = MakeWindow("Big Channel", 
			    SAME_DISPLAY, 
			    NONEXCLUSIVE_WINDOW);
    
    zoomdata = &(Graphdata[chan]);    
    graph = MakeDrawArea( 640,480, c_redisplay, zoomdata);
    close = MakeButton( "CLOSE", c_close_zoom, NULL );
    SetWidgetPos( close, PLACE_UNDER, graph, NO_CARE, NULL);
    
    ShowDisplay();
    
}



void
c_clicked_channel(Widget w, int which_button, int x, int y, void *data)
{
    struct GraphData *gd;
    gd = (struct GraphData *) data;

    /* Enable/disable the channel... */
    if (which_button == 3) {
	if (fadc_is_channel_disabled(Boardnum,gd->num) == 0) {
	    fadc_disable_channel(Boardnum,gd->num);
	    warn("Disabled channel %d\n",gd->num);
	} else {
	    fadc_enable_channel(Boardnum,gd->num);
	    warn("Enabled channel %d\n",gd->num);
	}
	c_redisplay( Graph[gd->num], GRAPHWID, GRAPHHT, &Graphdata[gd->num] );
    }
    else if (which_button == 2) {
	c_zoom_channel( w, (void *)(gd->num) );
    }
    else if (which_button == 1){
	Selected[gd->num] = ~Selected[gd->num];
	c_redisplay( Graph[gd->num], GRAPHWID, GRAPHHT, &Graphdata[gd->num] );
    }

}

void
c_set_view( Widget w, void *data ){
    int i;
    char text[100];

    View = (int) data;
    for (i=0; i<VIEW_COUNT; i++) {
	if (i==View) 
	    SetMenuItemChecked(viewmenu[i], 1);
	else
	    SetMenuItemChecked(viewmenu[i], 0);
	
    }

    sprintf(text, "Viewing: %s", View_label[View]);
    SetLabel( wid[VIEW_L], text );

    /* update display */
    for(i=0; i<NUMCHANNELS; i++){
	c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
    }

}

void
c_set_pulsebox_offs( Widget w, void *data ) {
    int i,val;
    val = ask_for_int( "Enter Pulse Box offset: ", Graphdata[0].pulseoffs);
    if (val<Datawidth*4 && val>=0) {
	for (i=0; i<NUMCHANNELS; i++) {
	    Graphdata[i].pulseoffs = val;
	    c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
	}
    }
}

void
c_set_pulsebox_width( Widget w, void *data ) {
    int i,val;
    val = ask_for_int( "Enter Pulse Box width: ", Graphdata[0].pulsewid);
    if (val<Datawidth*4 && val>=0) {
	for (i=0; i<NUMCHANNELS; i++) {
	    Graphdata[i].pulsewid = val;
	    c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
	}
    }
}

void
c_set_pedbox_offs( Widget w, void *data ) {
    int i,val;
    val = ask_for_int( "Enter Pedestal Box offset: ", Graphdata[0].pedoffs);
    if (val<Datawidth*4 && val>=0) {
	for (i=0; i<NUMCHANNELS; i++) {
	    Graphdata[i].pedoffs = val;
	    c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
	}
    }
}

void
c_set_pedbox_width( Widget w, void *data ) {
    int i,val;
    val = ask_for_int( "Enter Pedestal Box width: ", Graphdata[0].pedwidth);
    if (val<Datawidth*4 && val>=0) {
	for (i=0; i<NUMCHANNELS; i++) {
	    Graphdata[i].pedwidth = val;
	    c_redisplay(Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
	}
    }
}

struct JitterTestInfo {

    char filename[128];
    int cfdchan;
    int readchan;

};

void
c_cfd_jitter_test( Widget w, void *data ) {

    pthread_t jitterthread;
    pthread_attr_t jitterattr;
    char text[1024] = "";
    int answer;
    struct JitterTestInfo info;

    sprintf(info.filename,"cfd-jitter-test.dat");

    if (Running) c_go(wid[GO_BUTTON],NULL);

    strcat( text, "CFD jitter test: this test will vary the width of\n" );
    strcat( text, "the CFD output pulse and measure the pulse <Width> and\n" );
    strcat( text, "dispersion. \n\n");
    strcat( text, "Do you want to continue?\n");
    
    answer = GetYesNo( text );

    if (answer==0) {
	return;
    }
    
    info.cfdchan = ask_for_int( "Enter CFD Channel number:", 0);
    info.readchan = ask_for_int( "Enter Channel where CFD output is fed:", 1);

    Jitter = 1;
    pthread_create( &jitterthread, NULL, (void *)jitter, &info );
    
    GetYesNo( "CFD Jitter test in progress. Press Okay or Cancel to stop it\n" );

    Jitter = 0;



}


void
jitter(void *arg) {

    FILE *fp;
    char *filename;
    unsigned long width=0;
    struct JitterTestInfo *info;
    int i;

    info = (struct JitterTestInfo *) arg;
    filename = (char *) arg;
    fp = fopen( filename, "w" );

    warn("STARTING JITTER TEST\n");

    for (width=0; width<4096; width+=16) {

	printf("JITTER: CFD %d width = %d\n", info->cfdchan, (int)width); 

	fadc_set_cfd_width( Boardnum, info->cfdchan, width );

	/* reset analysis */
	
	c_clear_analysis( 0, NULL );

	/* grab 100 events */

	for (i=0; i<100; i++) {
	    if (Jitter == 0) return;
	    c_one_evt( 0, NULL );
	}

	/* write out statistics */
	
	fprintf( fp, "%d\t%f\t%f\n", 
		 (int)width, 
		 Graphdata[info->readchan].softwidth.avg,
		 Graphdata[info->readchan].softwidth.sigma );

    }

    fclose(fp);
    warn("CFD Jitter test complete. Data written to '%s'\n", info->filename);


}

void
c_rate_vs_discrim( Widget w, void *data ) {

    pthread_t thread;
    pthread_attr_t attr;
    
    Ratethresh = 1;
    Cfdmode = 0;
    pthread_create( &thread, NULL, (void *)rate_vs_thresh, NULL );    
    GetYesNo( "Running rate vs discrim threshold..  Click OK to stop" );
    Ratethresh=0;
    pthread_join( thread, NULL );

}

void
c_rate_vs_cfd( Widget w, void *data ) {

    pthread_t thread;
    pthread_attr_t attr;
    
    Ratethresh = 1;
    Cfdmode = 1;
    pthread_create( &thread, NULL, (void *)rate_vs_thresh, NULL );    
    GetYesNo( "Running rate vs CFD threshold..  click OK to stop " );
    Ratethresh=0;
    pthread_join( thread, NULL );

}



void rate_vs_thresh( void *arg ) {

    FILE *ratefile;
    unsigned long start=0, end=4095, step=1;
    unsigned long thresh;
    int sleeptime = 0.5e6; // in microseconds
    int i;

    warn("Starting rate vs. threshold test\n");
    
    fadc_verbose(0);
    fadc_set_cfd_mode( Boardnum, FADC_ALL, (unsigned long)Cfdmode );
    ratefile = fopen("RateVsThreshold.dat", "w");

    for ( thresh = start; thresh <=end; thresh += step) {

	if (Ratethresh == 0) break;

	fadc_set_cfd_thresh( Boardnum, FADC_ALL, thresh );

	usleep(50);

	recalc_rates();
	usleep(sleeptime);
	recalc_rates();

	for (i=0; i<10; i++) {
	    if (Graphdata[i].rate < 0) {
		warn("Scaler wrapped, Trying again...\n");
		thresh -= step;
		continue;
	    }
	}

	fprintf( ratefile, "%d\t", (int)thresh );
	for (i=0; i<10; i++) {
	    fprintf( ratefile, "%f\t", Graphdata[i].rate );
	}
	fprintf( ratefile, "\n");
	fflush(ratefile);

	fprintf( stdout, "%d ", (int)thresh );
	for (i=0; i<10; i++) {
	    fprintf( stdout, "%f ", Graphdata[i].rate );
	}
	fprintf(stdout, "\n");
	fflush(stdout);
	
    }

    fclose(ratefile);
    warn("Done with rate-vs-threshold test.\n");
    fadc_verbose(1);

}

void
c_acquire_data( Widget w, void *data ) {

    pthread_t dacqthread;
    pthread_attr_t dacqattr;
    char text[512] = "testfadc is now in DACQ mode.";
    char *filename;

    warn( "stopping display... \n" );
    if (Running) c_go(wid[GO_BUTTON],NULL);

    filename = GetString("Data Acquisition: Please choose a filename where \nyou want the binary data to be written", "fadc-data.raw");

    if (filename == NULL) { 
	warn("DACQ mode canceled, no data written\n");
	return;
    }
    

    warn( "starting data acquisition thread...\n" );
    Dacq = 1;
    pthread_create( &dacqthread, NULL, (void *) dacq, "fadc-data.raw" );

    strcat(text,"Data is being written\nto the disk and all graphics ");
    strcat(text, "display is disabled. \nPress [Okay] or [Cancel] to ");
    strcat(text, "stop acquisition \nand resume the graphics display.");
    GetYesNo(text);
    
    Dacq = 0;
    warn("waiting for Dacq thread to exit...\n");
    pthread_join( dacqthread, NULL );


}

void
dacq(void *arg) {
    
    int i;
    FILE *fp;
    char *filename;
    unsigned long nwords;
    unsigned long maxwords;

    filename = (char *) arg;

    maxwords = fadc_get_max_evt_size(Boardnum);
    fp = fopen(arg, "wb");
    
    warn("IN DACQ MODE... writing to '%s'\n",filename);
    fadc_evt_clr();

    while(1) {

	/* TODO: use a phread condition variable for this */
	if (Dacq == 0) {
	    printf( "Exiting DACQ mode\n");
	    fclose(fp);
	    pthread_exit(0);
	}

	if (fadc_got_event() == 1) {

	    nwords = fadc_data_available(Boardnum);

	    if (nwords > 0 && nwords <= maxwords) {
		
		//		warn("DEBUG: nwords = %d\n", (int)nwords);
		fadc_memcpy( Buffer, Boardnum, nwords );

		if ( (Buffer[0] & 0xffff0000) == 0xfadc0000) {
		    fwrite( Buffer, sizeof(unsigned long), nwords, fp );
		}
		else {
		    warn("DACQ: Skipping event - wrong SYNC word! (0x%08lx)\n", 
			 Buffer[0]);
		}

	    }

	    fadc_evt_clr();

	}
    }
}

void
c_cfdtype( Widget w, void *data ) {

    unsigned long type;
    int chan;

    chan = (int) data;

    printf("SETTING TYPE FOR %d\n", chan );

    type = fadc_get_cfd_type( Boardnum, chan );

    if (type == CFD_WASHU) {
	SetLabel( w, "Ut" );
	fadc_set_cfd_type( Boardnum, chan, CFD_UTAH );
    }
    else {
	SetLabel( w, "WU" );
	fadc_set_cfd_type( Boardnum, chan, CFD_WASHU );
    }


}


void
c_find_pulse( Widget w, void *data ) {
    
    int ch;

    if (Running) c_go(wid[GO_BUTTON],NULL);

    ch = ask_for_int( "On which channel do you want to look for a pulse?", 4);
    if (ch < 0 || ch >= NUMCHANNELS) return;
    
    find_pulse( ch );

}

void
c_select_all( Widget w, void *data ) {
    int i;
    for(i=0; i<10; i++) {
	Selected[i] = -1;
	c_redisplay( Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
    }
}

void
c_select_none( Widget w, void *data ) {
    int i;
    for(i=0; i<10; i++) {
	Selected[i] = 0;
	c_redisplay( Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
    }
}

void
c_select_inv( Widget w, void *data ) {
    int i;
    for(i=0; i<10; i++) {
	Selected[i] = ~Selected[i];
	c_redisplay( Graph[i], GRAPHWID, GRAPHHT, &Graphdata[i] );
    }
}


void
c_close_about( Widget w, void *data ) {

    CloseWindow();

}

void 
c_toggle_fft( Widget w, void *data ) {

    int chan = (int) data;

    /* test for power of 2 */
    if (Fft_is_doable == 0) {
	warn("Couldn't enable FFT - Datawidth must be a power of 2!\n");
	SetToggleState(w, 0);
	return;
    }

    if (Graphdata[chan].fft == 0)
	Graphdata[chan].fft = 1;
    else
	Graphdata[chan].fft = 0;


    c_redisplay(Graph[chan], GRAPHWID, GRAPHHT, &Graphdata[chan] );


}

void
c_about( Widget w, void *data ) {

    Widget aboutbox, abouttext,closebutton;
    char text[2048];

    text[0] = '\0';
    strcat(text, "testfadc - program to test single FADC board\n\n");
    strcat(text, "AUTHOR: Karl Kosack, Washington University\n");
    strcat(text, "EMAIL : kosack@hbar.wustl.edu\n"); 
    strcat(text, "TEL   : (314) 935-5035 (WashU)\n"); 

    aboutbox = MakeWindow( "About", SAME_DISPLAY, EXCLUSIVE_WINDOW );

    abouttext = MakeTextWidget( text, 0, 0, 400,200 ); 
    closebutton = MakeButton( "CLOSE", c_close_about, NULL );
    SetWidgetPos( closebutton, PLACE_UNDER, abouttext, NO_CARE, NULL );

    ShowDisplay();

}

void
c_evt_clr( Widget w, void *data ) {

  fadc_evt_clr();
  warn("Issued an EVENT CLEAR\n");

}


/**
 * Go through a range of lookback offsets to find the pulse
 */
void
find_pulse(int ch) {

    unsigned long oldoffs,offs = 0, nwords;
    char found = 0;
    char text[256];

    oldoffs = fadc_get_data_offset(Boardnum, ch );

    /* first check if the rate is high enough to locate a pulse */

    warn("find pulse: Checking ch%d singles rate...\n",ch);
    recalc_rates();
    sleep(2);
    recalc_rates();
    warn("find pulse: singles rate=%f\n", 
	   Graphdata[ch].rate);

    if (Graphdata[ch].rate < 1.0) {
	sprintf(text, "Sorry, the singles rate is not high enough channel %d\n",ch);
	strcat(text,"Are you sure a pulse is being sent there?\n");
	strcat(text, "Maybe the CFD is not triggering?");
	GetYesNo(text); 
	return;
    }
    
    /* now vary the area offset from 0 to 2048 in big steps to look for a pulse */

    warn("find pulse: Looking for pulse... PLEASE WAIT!\n");
    for (offs = 0; offs < 1024 ; offs += Graphdata[ch].pulsewid){

	fadc_set_data_offset(Boardnum, FADC_ALL, offs);

	fadc_evt_clr();
	usleep(1000);
	while(fadc_got_event() == 0);
	nwords = fadc_data_available(Boardnum);
	if (nwords) {
	    assert(nwords <= Buffersize);
	    fadc_memcpy( Buffer, Boardnum, nwords );
	    parse_data(Buffer);
	    analyze_pulse();
	}

	if (Graphdata[ch].peak.value > 15.0) {
	    found=1;
	    break;
	}

    }
    
    if (found) {
	warn("Area offset should be around %d ns\n", (int) offs);
	sprintf(text, "Found the pulse! You may need to adjust the\n"); 
	strcat(text,"area offset or the pulse box offset to center it\n");
	strcat(text,"in the green 'pulse box' region.");
	GetYesNo( text  );
    }
    else {
	warn("couldn't find a pulse\n");
	fadc_set_data_offset(Boardnum, FADC_ALL, oldoffs);
	GetYesNo("No pulse could be found on the requested channel.\n");
    }
	    
}




/* init_display - create widgets, etc. */
void 
init_display( int argc, char **argv) {

    int i;
    Widget temp;
    unsigned long val;
    Widget fftbutton[10];

    if (OpenDisplay(argc, argv) == FALSE){
	printf("Couldn't open display! \n\n");
	exit(1);
    }


    init_colors();

    wid[FILE_MENU] = MakeMenu("File *");
    MakeMenuItem( wid[FILE_MENU], "About...", c_about, NULL );
    MakeMenuItem( wid[FILE_MENU], "Save current settings...", c_save_settings, NULL);    
    MakeMenuItem( wid[FILE_MENU], "Save waveforms...", c_snapshot , NULL);    
    MakeMenuItem( wid[FILE_MENU], "Write histograms", c_save_analysis , NULL);    
    MakeMenuItem( wid[FILE_MENU], "Exit", c_exit , NULL);    

    wid[SELECT_MENU] = MakeMenu("Select *");
    SetWidgetPos( wid[SELECT_MENU], PLACE_RIGHT, 
		wid[FILE_MENU],NO_CARE,NULL );
    MakeMenuItem( wid[SELECT_MENU], "All", c_select_all, NULL);    
    MakeMenuItem( wid[SELECT_MENU], "None", c_select_none, NULL);    
    MakeMenuItem( wid[SELECT_MENU], "Inverse", c_select_inv, NULL);    

    wid[SET_MENU] = MakeMenu("Set *");
    SetWidgetPos( wid[SET_MENU], PLACE_RIGHT, 
		wid[SELECT_MENU],NO_CARE,NULL );

    wid[VIEW_MENU] = MakeMenu( "View *" );
    SetWidgetPos(wid[VIEW_MENU], PLACE_RIGHT, wid[SET_MENU], NO_CARE, NULL);

    wid[ANALYSIS_MENU] = MakeMenu( "Analysis *" );
    SetWidgetPos(wid[ANALYSIS_MENU], PLACE_RIGHT, wid[VIEW_MENU], NO_CARE, NULL);
    
    wid[ACTION_MENU] = MakeMenu( "Actions *" );
    SetWidgetPos(wid[ACTION_MENU], PLACE_RIGHT, wid[ANALYSIS_MENU], NO_CARE, NULL);

    wid[GO_BUTTON]   = make_tool_button("  GO  ", c_go, 
					PLACE_UNDER, wid[FILE_MENU], 
					NO_CARE, NULL );

    wid[ONE_EVT_BUTTON] = make_tool_button("One Evt", c_one_evt
					   , PLACE_UNDER, wid[FILE_MENU],  
					   PLACE_RIGHT, wid[GO_BUTTON] );

    wid[CLEAR_BUTTON] = make_tool_button("Reset Analysis", c_clear_analysis,
					 PLACE_UNDER, wid[FILE_MENU],  
					 PLACE_RIGHT, wid[ONE_EVT_BUTTON] );

    wid[VIEW_L] = MakeLabel( "Viewing: scalers      " );
    SetWidgetPos( wid[VIEW_L], PLACE_UNDER, wid[FILE_MENU],  
		  PLACE_RIGHT, wid[CLEAR_BUTTON] );
    SetFgColor( wid[VIEW_L], BLUE );

    wid[HIST_TOG] = MakeToggle("Hist",Toggle[TOGGLE_HIST], 
				  NULL, c_toggle, (void*)TOGGLE_HIST);
    SetWidgetPos( wid[HIST_TOG], PLACE_UNDER, wid[FILE_MENU],  
		  PLACE_RIGHT, wid[VIEW_L] );
    SetBorderColor(wid[HIST_TOG],Color[TOOLBAR_COLOR]); SetBgColor(wid[HIST_TOG],Color[TOOLBAR_COLOR]);
    wid[PERSIST_TOG] = MakeToggle("Pers",Toggle[TOGGLE_PERSIST], 
				  NULL, c_toggle, (void*)TOGGLE_PERSIST);
    SetWidgetPos( wid[PERSIST_TOG], PLACE_UNDER, wid[FILE_MENU],  
		  PLACE_RIGHT, wid[HIST_TOG] );
    SetBorderColor(wid[PERSIST_TOG],Color[TOOLBAR_COLOR]); SetBgColor(wid[PERSIST_TOG],Color[TOOLBAR_COLOR]);

    /* Set menu */
    MakeMenuItem( wid[SET_MENU], "Area Offset", c_set_area_offs , NULL);
    MakeMenuItem( wid[SET_MENU], "Area Width", c_set_area_width , NULL);
    MakeMenuItem( wid[SET_MENU], "Area Discrim (0-suppress)", c_set_area_discrim , NULL);
    MakeMenuItem( wid[SET_MENU], "Data Offset (Lookback time)", c_set_data_offs , NULL);
    MakeMenuItem( wid[SET_MENU], "CFD thresh", c_set_cfd_thresh , NULL);
    MakeMenuItem( wid[SET_MENU], "CFD width", c_set_cfd_width , NULL);
    MakeMenuItem( wid[SET_MENU], "CFD rate fb", c_set_cfd_ratefb , NULL);
    MakeMenuItem( wid[SET_MENU], "CFD delay", c_set_cfd_delay , NULL);
/*      MakeMenuItem( wid[SET_MENU], "WU CFD thresh", c_set_cfd_wuthresh , NULL); */
/*      MakeMenuItem( wid[SET_MENU], "WU CFD offs", c_set_cfd_wuoffs , NULL); */

    MakeMenuItem( wid[ANALYSIS_MENU], "Set pulse box offset", 
		  c_set_pulsebox_offs, NULL);
    MakeMenuItem( wid[ANALYSIS_MENU], "Set pulse box width", 
		  c_set_pulsebox_width, NULL);    
    MakeMenuItem( wid[ANALYSIS_MENU], "Set pedestal box offset", 
		  c_set_pedbox_offs, NULL);    
    MakeMenuItem( wid[ANALYSIS_MENU], "Set pedestal box width", 
		  c_set_pedbox_width, NULL);    
    MakeMenuItem( wid[ANALYSIS_MENU], "Set t_thresh threshold", 
		  c_set_tthresh_threshold, NULL);    

    /* View menu */
    for (i=0; i<VIEW_COUNT; i++) {
	viewmenu[i] = MakeMenuItem( wid[VIEW_MENU], View_label[i],
					   c_set_view, (void *) i);
    }

    /* Actions menu */
    MakeMenuItem( wid[ACTION_MENU], "Aquire Data...", c_acquire_data, NULL);
    MakeMenuItem( wid[ACTION_MENU], "Buffer Ram test...", c_buf_ram_test , NULL);
    MakeMenuItem( wid[ACTION_MENU], "Find pulse...", c_find_pulse , NULL);
    MakeMenuItem( wid[ACTION_MENU], "CFD Jitter Test...", c_cfd_jitter_test , NULL);
    MakeMenuItem( wid[ACTION_MENU], "Rate vs CFD Thresh...", c_rate_vs_cfd, NULL);
    MakeMenuItem( wid[ACTION_MENU], "Rate vs Discrim Thresh...", c_rate_vs_discrim, NULL);


    SetMenuItemChecked(viewmenu[VIEW_SCALERS],1);

    wid[PULSE_PANEL] = MakeForm(TOP_LEVEL_FORM, 
				PLACE_UNDER, wid[GO_BUTTON],
				NO_CARE, NULL);

    SetForm(wid[PULSE_PANEL]);

    for(i=0; i<NUMCHANNELS; i++){
	Graphdata[i].num = i;
	Graph[i] = MakeDrawArea(GRAPHWID, GRAPHHT, c_redisplay, &Graphdata[i]);
	Viewbox[i] = MakeLabel("   0x00000000   ");
	Errbox[i]  = MakeLabel("   0000000000   ");

/* 	val = fadc_get_cfd_type( Boardnum, i ); */
/* 	if (val == CFD_WASHU) */
/* 	    Cfdcheck[i]  = MakeButton("WU", c_cfdtype, (void*)i ); */
/* 	else */
/* 	    Cfdcheck[i]  = MakeButton("Ut", c_cfdtype, (void*)i ); */
	
	fftbutton[i] = MakeToggle("FFT", 0, NULL,c_toggle_fft, (void*)i );
	if (Fft_is_doable == 0) {
	    SetFgColor( fftbutton[i], Color[PULSE_BG_INACTIVE_COLOR] );
	}


	SetBgColor( Cfdcheck[i], WHITE ); 
	

	SetButtonDownCB( Graph[i], c_clicked_channel );
	if(i == 0) {
	    SetWidgetPos(Graph[i], NO_CARE,NULL, NO_CARE,NULL);
	    SetWidgetPos( Viewbox[i], 
			  PLACE_RIGHT,Graph[i],
			  NO_CARE,NULL);
/* 	    SetWidgetPos(Cfdcheck[i], PLACE_UNDER, wid[GO_BUTTON],  */
/* 			 PLACE_RIGHT,Viewbox[i]); */
	    SetWidgetPos(fftbutton[i], NO_CARE, NULL,
			 PLACE_RIGHT, Viewbox[i]);

	} else {
	    SetWidgetPos(Graph[i], PLACE_UNDER, Graph[i-1], NO_CARE,NULL);
	    SetWidgetPos( Viewbox[i], PLACE_RIGHT,Graph[i],
			  PLACE_UNDER,Graph[i-1]);
/* 	    SetWidgetPos(Cfdcheck[i], PLACE_UNDER, Graph[i-1],  */
/* 			 PLACE_RIGHT,Viewbox[i]); */
	    SetWidgetPos(fftbutton[i], PLACE_UNDER, Graph[i-1], 
			 PLACE_RIGHT, Viewbox[i]);
	}
	SetWidgetPos( Errbox[i],PLACE_UNDER,Viewbox[i],PLACE_RIGHT,Graph[i]);

	SetFgColor(Errbox[i],RED);
	
    }

    SetForm(TOP_LEVEL_FORM);

    wid[EVT_BOX] = MakeStringEntry("XXXXX", 100,NULL,NULL);
    wid[EVT_BOX_L] = MakeLabel("Event Number:");
    SetWidgetPos( wid[EVT_BOX_L], PLACE_UNDER, wid[PULSE_PANEL],
		  NO_CARE,NULL);
    SetWidgetPos( wid[EVT_BOX], PLACE_UNDER, wid[PULSE_PANEL],
		  PLACE_RIGHT,wid[EVT_BOX_L]);

    wid[NAREAEVT_BOX] = MakeStringEntry("XXXXX", 100,NULL,NULL);
    wid[NAREAEVT_BOX_L] = MakeLabel("Analyzed evts:");
    SetWidgetPos( wid[NAREAEVT_BOX_L], PLACE_UNDER, wid[PULSE_PANEL],
		  PLACE_RIGHT,wid[EVT_BOX]);
    SetWidgetPos( wid[NAREAEVT_BOX], PLACE_UNDER, wid[PULSE_PANEL],
		  PLACE_RIGHT,wid[NAREAEVT_BOX_L]);

    
    wid[TRIGGER_L] = MakeLabel("TRIG");
    SetWidgetPos( wid[TRIGGER_L], PLACE_UNDER, wid[PULSE_PANEL],
		  PLACE_RIGHT,wid[NAREAEVT_BOX]);

    /*****************/
    /* Options Panel */
    /*****************/    

    wid[OPTION_PANEL] = MakeForm(TOP_LEVEL_FORM, 
				 PLACE_UNDER, wid[PERSIST_TOG],
				 PLACE_RIGHT, wid[PULSE_PANEL]);
    SetBgColor( wid[OPTION_PANEL], GetNamedColor("orange"));
    SetForm(wid[OPTION_PANEL]);
    temp = MakeLabel( "Controls:" );
    SetBgColor( temp, GetNamedColor("orange"));
    SetBorderColor( temp, GetNamedColor("orange"));

    wid[EVT_CLR_BUTTON] = make_tool_button("Evt Clear", c_evt_clr, 
					   PLACE_UNDER, temp, NO_CARE, NULL);

    wid[READ_BUTTON] = make_tool_button(    "Read     ", c_issue_read, 
				       PLACE_UNDER, wid[EVT_CLR_BUTTON],
				       NO_CARE, NULL);

    wid[PED_BUTTON] = make_tool_button(    "Pedestal ", c_issue_ped, 
				       PLACE_UNDER, wid[READ_BUTTON],
				       NO_CARE, NULL);

    wid[REREAD_BUTTON] = make_tool_button( "Reread   ", c_issue_reread, 
					  PLACE_UNDER, wid[PED_BUTTON],
					  NO_CARE, NULL);

    wid[DUMP_BUTTON] = make_tool_button(   "Dump     ", c_issue_dump, 
				       PLACE_UNDER, wid[REREAD_BUTTON],
				       NO_CARE, NULL);

}

Widget
make_tool_button( char *name, ButtonCB function, 
		 int where1, Widget from1,int where2, Widget from2) {

    Widget w;

    w = MakeButton( name, function, NULL );
    SetWidgetPos( w, where1,from1,where2,from2 );
    SetBorderColor(w,Color[TOOLBAR_COLOR]);
    SetBgColor(w,Color[TOOLBAR_COLOR]);

    return w;

}

/* return the time in microseconds*/
double
get_time() {

    double time=0;

#ifdef QNX
    
    /* TODO: put POSIX time functions here */
    printf("ERROR: get_time() Need to write a get_time function for QNX!\n");
    return 0;

#else
    
    struct timeval tv;
    struct timezone tz;

    gettimeofday( &tv,&tz);
    
    time = tv.tv_sec + (double)tv.tv_usec/1.0e6;
    
    return time;
    
#endif

}


/**
 * Initialize Histogramming: */
void 
histogram_new(struct Histogram *h, double min, double max, int nbins){

    int i;

    h->hist = calloc( nbins,  sizeof(int) );
    h->min = min;
    h->max = max;
    h->nbins = nbins;

    /* zero the histogram */
    
    for (i=0; i<nbins; i++) 
	h->hist[i] = 0;
    
    h->underflow = 0;
    h->overflow = 0;

    h->binwidth = abs(min-max)/(double)nbins;

}

void 
histogram_add(struct Histogram *h, double val) {

    int bin;

    if (val > h->max) h->overflow++;
    else if (val < h->min) h->underflow++;
    else {
	
	bin = (int)((val - h->min)*(double)(h->nbins) / (h->max - h->min));
	h->hist[bin]++;

    }
    
}

void 
histogram_delete(struct Histogram *h) {
    free(h->hist);
}

int
histogram_write( struct Histogram *h, char *filename ) {

    int i;
    double val;
    FILE *fp;

    fp = fopen( filename, "w" );
    if (fp == NULL) {
	perror("histogram_write: fopen");
	return -1;
    }

    fprintf(fp, "# (%s) HISTOGRAM FOR PLOTTING IN GNUPLOT\n", filename);
    fprintf(fp, "# NUMBER OF BINS = %d\n",h->nbins);
    fprintf(fp, "# UNDERFLOW = %d  OVERFLOW=%d \n", h->underflow,h->overflow);
    fprintf(fp, "# --------------------------------------------------------\n");

    for (i=0; i<h->nbins; i++) {
	
	val = (double)i * ((h->max - h->min)/(double)(h->nbins)) + h->min;
	fprintf( fp, "%f\t%d\n", val, h->hist[i] );

    }

    fclose(fp);
    printf( "Histogram written to '%s'\n", filename );

}

/**
 * Zero the specified histogram
 */
void
histogram_clear( struct Histogram *h ) {

    int i;
    for(i=0; i<h->nbins; i++) {
	h->hist[i] = 0;
    }
    h->underflow = 0;
    h->overflow = 0;

}

void 
measurement_add( struct Measurement *m, double val ) {

    m->nsamples++;
    m->value = val;
    m->sum  += val;
    m->sum2 += val*val;
    m->avg = (m->sum / (double)m->nsamples);
    m->sigma = sqrt(m->sum2 / (double) m->nsamples - (m->avg * m->avg) );

}

void 
measurement_clear( struct Measurement *m ) {

    m->nsamples = 0;
    m->value = 0;
    m->avg = 0;
    m->sigma = 0;
    m->sum = 0;
    m->sum2 = 0;

}


void
shutdown(int n) {

    printf( "Shutting down FADC interface...\n");
    fadc_exit();
    free(Buffer);
    printf("Writing settings:\n");
    printf("Goodbye.\n");
    exit(0);

}



void 
init_colors(void) {

    int i;

    GetStandardColors();

    for (i=0; i<N_COLORS; i++) {
	Color[i] = BLACK;
    }

    Color[SOFT_PULSE_COLOR] = GetNamedColor("LightGreen");
    Color[SOFT_PED_COLOR] = GetNamedColor("khaki");

    Color[SOFT_PULSE_INACTIVE_COLOR] = GetNamedColor("DarkOliveGreen");
    Color[SOFT_PED_INACTIVE_COLOR] = GetNamedColor("goldenrod");

    Color[PULSE_BG_INACTIVE_COLOR] = GetNamedColor("grey40");

    Color[TOOLBAR_COLOR] = GetNamedColor("LightSeaGreen");


}
