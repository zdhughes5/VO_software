/***********************************************************************
 *
 *  reread_stability - checks stability of ped/reread/dump commands
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

#define CBLTBUFFERSIZE 2048

void getargs( int, char **);
void usage(void);
void init_hardware();
void shutdown(int n);
int Boardnum;
int Badevents=0;
double get_pulse_chisqr( unsigned char * );
void write_pulse( FILE *fp, unsigned char * );
FILE *Glitchfile, *Goodpulsefile;

enum types {PED,REREAD};
int What_to_test = REREAD;



int
main(int argc, char **argv) {

    int nwords;
    unsigned long count=0;
    int i;
    unsigned long *cbltbuffer = NULL;
    int pcount=0;
    unsigned long hitpattern;
    struct sigaction sa;
    unsigned long prevevtnum=0;
    unsigned long pulsebuffer[2048];

    unsigned long dwidth, area_hdr, area, expected_area, areasum;
    unsigned char *cptr;
    int badcount=0, badflag=0;


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
    
    cbltbuffer = fadc_alloc_cblt_buffer( CBLTBUFFERSIZE, -1, Boardnum );

 
    /* first, grab an event */

    printf("Starting acquisition...\n\n");
    fadc_evt_clr();
    while (fadc_got_event()==0);
    fadc_cblt();
    
    fadc_verbose(0);    

    /* request a pedestal, then loop rereading events */

    while (1) { 

	if (pcount >= 1000) {
	    pcount=0;
	    fprintf(stderr,"Got %lu events, %d bad events"
		    "                            \r", 
		    count, badcount);
	}
	
	switch (What_to_test) {
	case PED:
	    fadc_request_pedestal( Boardnum );
	    break;
	case REREAD:
	    fadc_request_reread( Boardnum );
	    break;
	}
	
	while (fadc_got_event()==0);

	nwords = fadc_cblt();

	if (nwords<=0 || nwords > 500) {
	    printf("NWORDS=0x%08lx at event %d                  \n",
		   nwords,count);
	    continue;
	}

	if (count < 1) {
	    printf("Storing first event\n");
	    memcpy( pulsebuffer, cbltbuffer, 
		     nwords*sizeof(unsigned long));
	}
	else {
	    /* compare to previous */
	    
	    for (i=16; i<16+dwidth;i++) {
		badflag=0;
		if (cbltbuffer[i] != pulsebuffer[i]) {
		    printf("Bad data at word %d: 0x%08lx != 0x%08lx\n",i,
			   cbltbuffer[i], pulsebuffer[i]);
		    badflag=1;
		}
		if (badflag) badcount++;
	    }

	}
    



	//	    fadc_evt_clr();
	count++;
	pcount++;
	prevevtnum = (cbltbuffer[9]&0x03FFFFFF);
	
	if (count >= 0x03ffffff) {
	    printf("WRAP: Event number scaler reached maximum value\n");
	    count=-1;
	}  


    }

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

    printf( "USAGE: reread_stability -b <boardnum>\n\n" );
    printf( "\t -p  use PED command instead of REREAD\n");
    exit(0);
    
}


void
getargs( int argc, char **argv ) {
    
    int c,i;
    char bdflag=0;
 
    while (( c = getopt( argc, argv, "b:p" )) != -1 ) {
        switch (c) {
        case 'b':
            i = atoi(optarg);
	    Boardnum = i;
	    bdflag++;
	    break;
	case 'p':
	    What_to_test = PED;
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

