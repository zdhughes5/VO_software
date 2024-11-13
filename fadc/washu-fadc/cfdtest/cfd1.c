/**********************************************************************
 *
 *  cfd1 - testing program for cfd's                          
 *
 **********************************************************************/

#include <stdlib.h>
#include <stdio.h>

#ifdef QNX
#include "vme_client.h"	
#else
#include <vmic/vme_api.h>
//#include <vmic/vme_utils.h>
#include <sys/time.h>
#endif

#include <fadc.h>

#define RATE_PERIOD 30            /* time to count in seconds */
#define MINTHRESH  2440           /* starting threshold */
#define MAXTHRESH  2440           /* ending theshold */
#define THRESHSTEP 10             /* threshold step */
#define MAXOFFS 2400              /* starting offset */
#define MINOFFS 2400              /* ending offset */
#define OFFSSTEP -25              /* offset step (should be negative) */
#define FILENAME "thresh"         /* base filename for plots */
#define UTAH_CHAN 1

double get_time();
double calc_rate(void);
void   set_manual(void);

int Board = -1;
int Chan = -1;

int
main(int argc, char **argv) {

    int i,j, temp, nwords;
    unsigned long tmp, scaler;
    long counter=0;
    double rate;
    unsigned long thresh,offs, val;
    FILE *outfile;
    char text[128];


    /*=================================================================*/
    /* Get/check command line arguments - should be "boardnum chan" */
    /*=================================================================*/

    printf("FADC CFD test program\n=================================\n");
    if (argc < 3 || argc > 3) {
	printf("usage: cfdtest <boardnum> <chnum for cfd>");
	exit(1);
    }
    Board = atoi(argv[1]);
    Chan = atoi(argv[2]);
    if (Board <0 || Board>FADC_MAX_BOARDS)
    printf("Using board %d and CFD chan %d\n", Board, Chan);

    for( i=1 ; i<=fadc_num_boards(); i++) {
	if (i != Board) fadc_ignore_board(i);
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
	if (i != Chan) fadc_disable_channel(Board,i);
	else fadc_enable_channel(Board, i);
    }


    /* only use UTAH interface on channel 1 */
    printf("**********************************************************\n");
    if (Chan != UTAH_CHAN) {
	printf("*** USING WASHU CFD INTERFACE ON CHANNEL %d (BOARD %d)\n",
	       Chan,Board);
	fadc_set_cfd_type(Board,Chan,CFD_WASHU);
    } else {
	printf("*** USING UTAH CFD INTERFACE on CHANNEL %d (BOARD %d)\n",
	       Chan,Board);
	fadc_set_cfd_type(Board, Chan,CFD_UTAH);
    }    
    printf("**********************************************************\n");
    
    //    fadc_clear_trigger_scaler(Board,FADC_ALL);

    /* Do a RAM test first */
    /*    printf("RAM TEST: ");
    fflush(stdout);
    fadc_set_mode( Board, WORD_MODE );  
    sleep(1);
    if (fadc_buffer_ram_test(Board)){ 
	printf("FAILED!  Is FADC board %d installed? If so, it may be \n",
	       Board);
	printf(" malfunctioning.\n\n\n");
	fadc_exit();
	exit(1);
    }
    else printf("PASSED\n");
    */

    /* Put fadc into word-mode so that no processing is going on */

    printf("FADC is entering WORD mode\n");
    fadc_set_mode( Board,WORD_MODE );

    /*=================================================================*/
    /* Do some tests */
    /*=================================================================*/

    
    //    fadc_set_cfd_ratefb( Board,Chan, 64 );
    //    fadc_set_cfd_width( Board,Chan, 3500 );
    //    fadc_set_cfd_thresh( Board,Chan, 170 );
    fadc_set_cfd_dac2( Board,Chan, 2400 );
    fadc_set_cfd_dac1( Board,Chan, 2600 );

    fadc_get_cfd_ratefb( Board,Chan, &val);
    printf( "RATE FB = %d\n", (int) val);

    fadc_get_cfd_width( Board,Chan, &val);
    printf( "WIDTH   = %d\n", (int) val);

    fadc_get_cfd_thresh( Board,Chan, &val);
    printf( "THRESH  = %d\n", (int) val);

    fadc_get_cfd_dac1( Board,Chan, &val);
    printf( "WU DAC1  = %d\n", (int) val)
;
    fadc_get_cfd_dac2( Board,Chan, &val);
    printf( "WU DAC2  = %d\n", (int) val);


    printf("Done\n");

    printf( "Shutting down FADC interface.\n");
    fadc_exit();
    return 0;


}


/**
 * Calculate singles rate since last time calc_rate() was called
 */
double 
calc_rate(void) {

    static double t0=0;
    static unsigned long sc0=0;
    unsigned long sc1;
    double t1,hits,elapsed, rate=0;

    t1 = get_time();
    elapsed = t1 - t0;
    
    fadc_get_trigger_scaler(Board,Chan,&sc1);
    hits = (double)(sc1-sc0);

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
 * For debugging, allow manual input of offset and threshold
 */
void 
set_manual(void) {

    int toffs,tthresh;

    while (1) {

	printf( "Enter: offset,thresh \n");
	scanf( "%d,%d", &toffs, &tthresh );
	printf("Set to offs=%d thresh=%d\n",toffs,tthresh);
	
	fadc_set_cfd_dac2( Board,Chan, (unsigned long) toffs );
	fadc_set_cfd_dac1( Board,Chan, (unsigned long) tthresh );

    }

}

