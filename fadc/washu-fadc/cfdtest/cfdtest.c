/**********************************************************************
 *
 *  cfdtest - calculates rate vs threshold curve for a range 
 *            of CFD offsets and 
 *
 * TODO: allow looping through all channels on a board
 *
 **********************************************************************/

#include <vme/vme_api.h>

#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <ctype.h>
#include <fadc_lowlevel.h>  /* needed to access low-level routines */
#include <fadc.h>
#include <sys/time.h>

#define MINTHRESH_UTAH  1320      /* starting threshold */
#define MAXTHRESH_UTAH  1480      /* ending theshold */
#define THRESHSTEP 1             /* threshold step */
#define MAX_SCALER_WRAPS 10

void getargs( int argc, char **argv );
void   rate_vs_thresh( FILE *fp, int chan, unsigned long min, 
		       unsigned long max );
void   rate_vs_ratefb( FILE *fp, int chan, unsigned long min, 
		       unsigned long max );
double get_time();
double calc_rate(void);
void usage(void);

int Boardnum = -1;
int Chan = -1;
unsigned long Cfdmode=1;
int Automatic = 0;
int Notthresh = 0;
char Identifier[100] = "";
unsigned long Init_ratefb =0;
unsigned long Init_width=0;
float Integrationtime = 1.0;

int Step=THRESHSTEP;
int Minthresh=-1, Maxthresh=-1;


int
main(int argc, char **argv) {

    int i;
    unsigned long val;
    FILE *outfile;
    char text[128];

    Minthresh = MINTHRESH_UTAH;
    Maxthresh = MAXTHRESH_UTAH;

    /*=================================================================*/
    /* Get/check command line arguments */
    /*=================================================================*/

    printf("FADC CFD test program\n=================================\n");
    getargs( argc, argv );

    if (Boardnum <0 || Boardnum > fadc_num_boards()) {
	usage();
	printf("Boardnum number '%d' is invalid.\n",Boardnum);
	exit(1);
    }
    if (Chan <0 || Chan>10){ 
	usage();
	printf("Channel number '%d' is invalid.\n",Chan);
	exit(1);
    }

    /*=================================================================*/
    /* Initialize FADC hardware */
    /*=================================================================*/

    
    if (fadc_init()) { 
	fprintf(stderr, "Bad fadc_init()\n");
	exit(1);
    }
    fadc_verbose(0);


    printf ("Disabling all channels but channel %d\n", Chan);
    for (i=0; i<10; i++) {
	if (i != Chan) fadc_disable_channel(Boardnum,i);
	else fadc_enable_channel(Boardnum, i);
    }

    /* set up boards */
    sprintf(text,"fadc-board-%d.settings", Boardnum);
    if (fadc_load_settings( Boardnum,text )) {
        printf("No settings found for board %d, using defaults.\n", Boardnum);
    }


    /*===================================================================*/
    /* Continue setup of FADC */
    /*===================================================================*/

    printf("CFD MODE: ");
    if (Cfdmode ==0) printf("THRESHOLD DISCRIMINATOR\n");
    else printf("CONSTANT FRACTION DISCRIMINATOR\n");
    fadc_set_cfd_mode( Boardnum, FADC_ALL, Cfdmode );

    /* Put fadc into word-mode so that no processing is going on */

    printf("FADC is entering WORD mode\n");
    fadc_set_mode( Boardnum,WORD_MODE );

    /* Clear the scalers on all channels */
    fadc_clear_trigger_scaler(Boardnum,FADC_ALL);

    /* Do a RAM test first */
    printf("RAM TEST: ");
    fflush(stdout);
    fadc_set_mode( Boardnum, WORD_MODE );  
    //    sleep(1);
/*     if (fadc_buffer_ram_test(Boardnum)){  */
/* 	printf("FAILED!  Is FADC board %d installed? If so, it may be \n", */
/* 	       Boardnum); */
/* 	printf(" malfunctioning.\n\n\n"); */
/* 	fadc_exit(); */
/* 	exit(1); */
/*     } */
/*     else printf("PASSED\n"); */

    /*=================================================================*/
    /* Now do the rate vs threshold test and write a plot */
    /*=================================================================*/


    printf("\nPerforming rate vs threshold test:\n");

    usleep(50);
    
    printf( "\nUTAH CFD:\n");	
    if (Notthresh) {
	sprintf(text, "RateVsRateFB-%s-bd%dch%d.txt", Identifier,
		(int)Boardnum,(int)Chan);
    }
    else {
	sprintf(text, "RateVsThresh-%s-bd%dch%d.txt", Identifier,
		(int)Boardnum,(int)Chan);
    }
    if(!(outfile = fopen(text, "w"))) {
	printf("Couldn't open output plot file '%s'\n",text);
	perror("fopen");
	exit(1);
    }

    fadc_set_cfd_width( Boardnum,FADC_ALL, Init_width );
    fadc_set_cfd_ratefb( Boardnum, FADC_ALL, Init_ratefb );

    val = fadc_get_cfd_width( Boardnum,Chan );
    printf( "WIDTH = %d  ", (int) val);
    fprintf( outfile, "# WIDTH = %d\n", (int) val);
    val = fadc_get_cfd_ratefb( Boardnum,Chan );
    printf( "RATE FB = %d\n", (int) val);
    fprintf( outfile, "# RATE FB = %d\n", (int) val);
    printf("Writing to %s...\n", text);
    printf( "----------------------------\n");
    
    /* Loop over threshold */
    if (Notthresh) {
	rate_vs_ratefb( outfile, Chan, Minthresh, Maxthresh );
    }
    else {
	rate_vs_thresh( outfile, Chan, Minthresh, Maxthresh );
    }
    fclose(outfile);	
    

    printf( "Shutting down FADC interface.\n");
    fadc_exit();
    return 0;


}

void
rate_vs_thresh( FILE *fp, int chan, unsigned long min, unsigned long max ) {

    unsigned long thresh;
    double rate;
    int sleeptime;
    double error;
    int wraps=0;

    printf( "VARYING THRESHOLD FROM %lu to %lu IN STEPS OF %d (%f seconds per point)\n",
	    min,max, Step, Integrationtime);


    for (thresh = min;thresh <= max; thresh += Step) {
	
	fadc_set_cfd_thresh( Boardnum,chan,thresh );

	usleep(50); 	 /* wait a bit for set up time...*/

	rate = calc_rate();  /* start rate calculation */
	sleeptime = (Integrationtime) * 1e6;
	error = (1.0/Integrationtime);
	usleep(sleeptime);  /* wait for  integration time */
	rate = calc_rate();  /* finish rate calculation */

	if (rate < 0) {

	    if(wraps > MAX_SCALER_WRAPS) {
		/* scalar wrapped to many times, skip this point */
		printf("Rate is too high for this integration time, "
		       "skipping data point at thresh=%lu\n", thresh);
		wraps=0;
		continue;
	    }
	    fprintf(stderr, " [WRAP]           \r");
	    thresh-=Step;
	    wraps++;
	    continue;
	}


	wraps=0;
	fprintf(fp, "%lu\t%g\t%g\n", thresh,rate,error);
	fflush(fp);
	fprintf(stderr, "THRESH: %4lu   RATE: %12.7f                               \r", 
	       thresh,rate);
	fflush(stdout);
	
    }	
    
}


void
rate_vs_ratefb( FILE *fp, int chan, unsigned long min, unsigned long max ) {

    unsigned long ratefb;
    double rate;
    int sleeptime;

    printf("Setting Threshold to 0 (fully open)...\n");
    fadc_set_cfd_thresh( Boardnum, chan, 0L );

    if (max >= 128) max = 128;

    printf( "VARYING RATEFB FROM %lu to %lu IN STEPS OF %d (%f seconds per point)\n",
	    min,max, Step, Integrationtime);

    for (ratefb = min;ratefb <= max; ratefb += Step) {
	
	
	fadc_set_cfd_ratefb( Boardnum,chan,ratefb );
	
	usleep(50); 	 /* wait a bit for set up time...*/

	rate = calc_rate();  /* start rate calculation */
	if (rate < 0) {
	    printf("Scaler wrapped, trying again...");
	    ratefb-=Step;
	    continue;
	}

	sleeptime = (Integrationtime) * 1e6;
	usleep(sleeptime);  /* wait for  integration time */
	rate = calc_rate();  /* finish rate calculation */
	if (rate < 0) {
	    printf("Trying again...\n");
	    ratefb-=Step;
	    continue;
	}
	fprintf(fp, "%lu\t%g\n", ratefb,rate);
	fflush(fp);
	printf("RATEFB: %4lu   RATE: %12.7f             \r", ratefb,rate);
	fflush(stdout);
	
    }	
    
}


void
getargs( int argc, char **argv ) {
    
    char bdflag =0;
    char chflag =0;
    int c;

    while (( c = getopt( argc, argv, "ORdb:c:l:u:s:i:t:r:w:" )) != -1 ) {
	switch (c) {
	  case 'b':
	      bdflag=1;
	      Boardnum = atoi(optarg);
	      break;
	  case 'c':
	      chflag=1;
	      Chan = atoi(optarg);
	      break;
	case 'l':
	    Minthresh = atoi(optarg);
	    break;
	case 'u':
	    Maxthresh = atoi(optarg);
	    break;
	case 's':
	    Step = atoi(optarg);
	    break;
	case 'i':
	    strcpy( Identifier, optarg );
	    break;
	case 'R':
	    Notthresh = 1;
	    break;
	case 't':
	    Integrationtime = atof( optarg );
	    break;
	case 'r':
	    Init_ratefb = atoi( optarg );
	    break;
	case 'w':
	    Init_width = atoi( optarg );
	    break;
	case 'd':
	    Cfdmode = 0;
	    break;
	}
    }

    if (chflag==0 || bdflag==0) {
	usage();
	if (chflag == 0 ) 
	    printf("You must specify a channel!\n");
	if (bdflag == 0 )
	    printf("You must specify a board!\n");
	exit(1);
    }


}

void
usage(void) {
    printf("usage: cfdtest -b<board> -c<channel> [-a -l<lower> -u<upper> -s<step> -i <identifier>]\n");
    printf("\t-l<lower>\tlower threshold/offset setting\n\n");
    printf("\t-u<upper>\tupper threshold/offset setting\n\n");
    printf("\t-s<step>\tthreshold/offset step\n\n");
    printf("\t-w<width>\tSet the initial cfd WIDTH to use (default=%d)\n",
	   Init_width);
    printf("\t-r<ratefb>\tSet the initial cfd RateFB to use (default=%d)\n",
	   Init_ratefb);
    printf("\t-R\tVary the RateFB instead of the threshold (only on UTAH CFD's)\n");
    printf("\t-i<identifier>\t tag to add to filename\n");
    printf("\t-t<ticks>\t rate period in 1/4 second ticks\n");
    printf("\t-d\tuse threshold discrim mode instead of CFD mode\n");
}

/**
 * Calculate singles rate since last time calc_rate() was called
 * returns rate, or -1 if scaler wrapped and rate couldn't be determined
 */
double 
calc_rate(void) {

    static double t0=0;
    static unsigned long sc0=0;
    unsigned long sc1;
    double t1,hits,elapsed, rate=0;

    t1 = get_time();
    elapsed = t1 - t0;
    
    sc1 = fadc_get_trigger_scaler(Boardnum,Chan);
    if (sc0 > sc1) {
	//	printf("sc1: %lx, sc0: %lx\n", sc1, sc0) ;
	//	Ratedivide += 1;
	t0 = t1;         /* update time */
	sc0 = sc1;       /* update scaler */
	//	hits = (double)(sc1 + (unsigned long)(1<<25) - sc0);
	return -1;
    }
    else hits = (double)(sc1-sc0);


    rate = hits/elapsed;
    
    t0 = t1;         /* update time */
    sc0 = sc1;       /* update scaler */
    return rate;

}


/**
 * return the time in microseconds
 */
double
get_time(void) {

    double time=0;

    struct timeval tv;
    struct timezone tz;

    gettimeofday( &tv,&tz);
    
    time = tv.tv_sec + (double)tv.tv_usec/1.0e6;
    
    return time;

}


