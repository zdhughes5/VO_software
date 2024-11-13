/***********************************************************************
 *
 *  fadc_stability - takes data from the fadc boards using CBLT
 *  continuously and checks headers for reliability Also does pulse
 *  glitch test.
 *
 ************************************************************************/

#include <stdlib.h> 
#include <stdio.h>
#include <unistd.h>
#include <fadc.h>
#include <fadc_lowlevel.h>
#include <unistd.h>
#include <signal.h>
#include <math.h>

#define CBLTBUFFERSIZE 8192
#define ERROR_TOLER 3.0   /* error bar (weight) on data points for chisqr */

void getargs( int, char **);
void usage(void);
void init_hardware();
void shutdown(int n);
double Chisqr_toler = 30.0;
int Boardnum;
int Badevents=0;
double get_pulse_chisqr( unsigned char * );
void write_pulse( FILE *fp, unsigned char * );
FILE *Glitchfile, *Goodpulsefile;
int Use_first_pulse_for_glitch = 0;
int Test_area_header = 1;
int Firstboard = 0;
int Lastboard = 10;
int User_specified_cblt =0;

int
main(int argc, char **argv) {

    int nwords;
    unsigned long count=1;
    unsigned long expected_nwords, expected_start_hdr;
    unsigned long expected_clk_hdr, expected_hitpattern;
    int i;
    int badnword_flag=0;
    unsigned long *cbltbuffer = NULL;
    int pcount=0;
    int lastbadchisqr;
    unsigned long hitpattern;
    struct sigaction sa;
    double chisqr;
    int is_first_pulse=1;
    unsigned long prevevtnum=0;
    unsigned long *lptr, *clkbd_lptr;
    unsigned long dwidth, area_hdr, area, expected_area, areasum;
    unsigned char *cptr;


    /* set up ctrl-c handler */
    sigfillset( &sa.sa_mask );
    sa.sa_flags =0;
    sa.sa_handler = shutdown;
    if (sigaction(SIGINT, &sa, NULL) < 0) {
        perror( "sigaction SIGINT" );
        exit(1);
    }
    
    getargs(argc, argv);
    
    init_hardware();

    dwidth = fadc_get_data_width(Boardnum);

    /* init CBLT */
    
    if (User_specified_cblt) {
	cbltbuffer = fadc_alloc_cblt_buffer(CBLTBUFFERSIZE,
					    Firstboard,Lastboard );
    }
    else {
	cbltbuffer = fadc_alloc_cblt_buffer( CBLTBUFFERSIZE, -1, Boardnum );
    }

    /* open glitch output file */

    Glitchfile = fopen("glitch.dat","w");
    Goodpulsefile = fopen("goodpulses.dat","w");

    printf("\n");
    if (Use_first_pulse_for_glitch == 1) {
	printf("Using first pulse for glitch test (instead of prev)\n");
    }

    fadc_evt_clr();

    /* start grabbing events */ 

    printf("ChiSqr tolerence is: %f\n",Chisqr_toler);
    printf("Starting data acquisition....\n\n");
 
    while (1) { 

	if (fadc_got_event() == 1) {

	    nwords = fadc_cblt();

	    if (is_first_pulse) {

		expected_nwords = nwords;
		expected_start_hdr = cbltbuffer[8];
		expected_clk_hdr = cbltbuffer[0];
		expected_hitpattern = cbltbuffer[10];
		expected_area = cbltbuffer[8+3+dwidth] & 0x0000ffff;
		prevevtnum = (cbltbuffer[9]&0x03FFFFFF);
		
		write_pulse( Goodpulsefile, (unsigned char*) cbltbuffer );

		is_first_pulse = 0;

	    }
	    else {
		
		if (pcount >= 1000) {
		    pcount=0;
		    fprintf(stderr,"Got %lu events so far...         \r", 
			    count-1);
		    if (count < 50000)
			write_pulse(Goodpulsefile, (unsigned char*)cbltbuffer);
		}

		/* Compare to the first pulse and check for corruption */

		// Check for corrupt event

		if  ( cbltbuffer[0] != expected_clk_hdr ) {
		    Badevents++;
		    printf("CLKHDR: Bad Clock Header at event %lu: 0x%08lx != 0x%08lx\n", 
			   count, cbltbuffer[0], expected_clk_hdr);
		}
		if( cbltbuffer[8] != expected_start_hdr ) {
		    Badevents++;
		    printf("SYNCWD: Bad FADC header at event %lu: 0x%08lx != 0x%08lx\n", 
			   count,cbltbuffer[8], expected_start_hdr );
		}
		if (nwords != expected_nwords) {
		    printf("NWORDS: Bad nwords at event %lu: %lu (0x%08lx) != %lu\n",
			   count,nwords, nwords,expected_nwords);
		}
		
		if ( (cbltbuffer[9] & 0x03FFFFFF) != prevevtnum+1 ) {
		    printf("EVTNUM: didn't increase by 1: %lu, prev was %lu\n",
			   (cbltbuffer[9]&0x03FFFFFF), prevevtnum);
		    
		}
		

		if ( cbltbuffer[10] != expected_hitpattern ) {  
		    printf("HITPTN: Bad hitpattern at event %lu: 0x%08lx != 0x%08lx\n",
			   count,cbltbuffer[10], expected_hitpattern);
		}
		
		
	    
		chisqr = get_pulse_chisqr( (unsigned char *) cbltbuffer );
		//		printf("DEBUG: chisqr=%f\n", chisqr );
		if (chisqr > Chisqr_toler) {
		    if (count == lastbadchisqr+1) {
			printf("GLITCH: Glitch detected between events ");
			printf("%lu and %lu: (chisqr=%f)\n",count-1,count,chisqr);
			/* write glitched pulse to glitch file */
			write_pulse( Glitchfile, (unsigned char *) cbltbuffer );

		    }
		    lastbadchisqr  = count;
		}
		//printf("Chisqr for event %lu: %f\n", count, chisqr);
	    

		if (Test_area_header) {

		    /* check area header */
		    
		    area_hdr = cbltbuffer[8+3+dwidth];
		    area = area_hdr & 0x0000ffff;
		    
		    cptr = (unsigned char*)cbltbuffer;
		    areasum = 0;
		    for (i=11*4;i<(11+dwidth)*4; i++) {
			areasum += cptr[i];
		    }
		    
		    if (areasum != area) {
			printf("AREASUM: fadc area doesn't agree with soft area: %lu =! %lu\n", area, areasum);
		    }
		}		    

	    }
	    
	    fadc_evt_clr();
	    
	    count++;
	    pcount++;
	    prevevtnum = (cbltbuffer[9]&0x03FFFFFF);

	    if (count >= 0x03ffffff) {
		printf("WRAP: Event number scaler reached maximum value\n");
		count=-1;
	    }  

	}

    }

}


double
get_pulse_chisqr( unsigned char *buffer) {

    register int i;
    int datawidth = fadc_get_data_width( Boardnum );
    static unsigned char firstbuffer[CBLTBUFFERSIZE*sizeof(unsigned long)];
    static int is_first_pulse = 1;

    double sum=0;
    int n;
    double chisqr;
    

    if (is_first_pulse) {
	
	/* grab the data for the first pulse */

	printf("First event data: \n");
	for (i=11*4;i<(11+datawidth)*4; i++){

	    firstbuffer[i] = buffer[i];

	    printf("%3d ", (int)buffer[i]);
	    if ((i+5)%16==0) printf("\n");
	    
	}
	printf("\n");

	is_first_pulse = 0;
	return 0;
    }

    /* Calculate Chisqr: */
    
    n=0; 
    sum=0;
    for (i=11*4;i<(11+datawidth)*4; i++){

	//	printf("%d:%d-%d \n", i, (int)buffer[i], (int)firstbuffer[i]);
	sum += (pow((double)(buffer[i]) - (double)(firstbuffer[i]), 2));
	
	n++;

    }
    
    chisqr = (sum/(double)n)/pow( ERROR_TOLER, 2 );

    if (Use_first_pulse_for_glitch == 0) {

	/* copy new buffer into first buffer */
	
	for (i=11*4;i<(11+datawidth)*4; i++){
	    firstbuffer[i] = buffer[i];
	}

    }


    return chisqr;

}


void 
init_hardware() {

    int i;
    char filename[128];
    char answer[128];
    unsigned long *lptr;

    /* Init hardware */

    if (fadc_init()) {
	printf("BAD FADC INIT\n");
	exit(1);
    }

      /* test boards */

    fadc_verbose(0);
    fadc_set_mode( FADC_ALL, WORD_MODE );
    usleep(500);
    printf("\n");
    
    printf("BUFFER RAM TEST: ");
    fflush(stdout);
    if (fadc_buffer_ram_test(Boardnum)) {
                printf( "FAILED\n\n");
                printf( "*** Board in slot %d FAILED the buffer ram test!\n",
			Boardnum );
                printf( "*** Is the board installed? If not it may be\n");
                printf( "*** faulty.\n\n");
                shutdown(1);
    }
    else {
	printf( "PASSED\n" );
    }
    

    sprintf( filename, "fadc-board-%d.settings", Boardnum );
    if (fadc_load_settings( Boardnum, filename )) {
	printf("\n** No settings file was detected for board %d\n", Boardnum);
	printf("** You should run 'testfadc -b %d', set up the\n", Boardnum);
	printf("** board and save its settings file.\n");
	printf("** Do you want to continue with the defaults? (y/n) ");
	scanf("%s", &answer);
	if( tolower(answer[0]) != 'y') 
	    exit(0);
    }

    lptr = fadc_get_fadc_lptr( Boardnum );
    wr_evt_no( lptr, 0x0 );
    

    fadc_set_mode( FADC_ALL, FADC_MODE );
    fadc_verbose(1);

    fadc_evt_clr();
    usleep(1000);


}

void
write_pulse( FILE *fp, unsigned char *buffer ) {

    int i;
    int sample =0;
    int datawidth = fadc_get_data_width( Boardnum );
    unsigned long evtnum;

    evtnum = buffer[9]&0x03FFFFFF;

    fprintf( fp, "# Event %lu\n", evtnum );
    for (i=11*4;i<(11+datawidth)*4; i++){
	fprintf( fp, "%3d %3d\n", sample, (int)buffer[i] );
	sample++;
    }
    fprintf( fp, "\n");

    fflush(fp);

}

void
usage(void) {

    printf( "USAGE: testcblt [-f] [-c <toler>] -b <boardnum>\n\n" );
    printf( "\t -f \t use first pulse for glitch test instead of previous\n");
    printf( "\t -a \t disable area check\n");
    printf( "\t -c toler \t specify chisqr tolerance (default=30.0)\n");
    exit(0);
    
}


void
getargs( int argc, char **argv ) {
    
    int c,i;
    char bdflag=0;
 
    while (( c = getopt( argc, argv, "b:fac:C" )) != -1 ) {
        switch (c) {
        case 'b':
            i = atoi(optarg);
	    Boardnum = i;
	    bdflag++;
	    break;
	case 'f':
	    Use_first_pulse_for_glitch = 1;
	    break;
	case 'a':
	    Test_area_header = 0;
	    break;
	case 'c':
	    Chisqr_toler = atof(optarg);
	    break;
	case 'C':
	    User_specified_cblt=1;
	    break;
        default:
            usage();
            exit(1);
        }
    }

    if (bdflag ==0) {
	printf("You must specify a board!");
	usage();
	exit(1);
    }

}

void
shutdown(int n) {

    printf("Shutting down...\n");
    if (Glitchfile != NULL) fclose(Glitchfile);
    if (Goodpulsefile != NULL) fclose(Glitchfile);
    fadc_exit();
    exit(0);

    

}

