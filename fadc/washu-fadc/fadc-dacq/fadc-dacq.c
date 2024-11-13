/**********************************************************************
 *
 *  fadc-dacq: simple data acquisition system for VERITAS 
 *  30 channel test.  Uses pthreads and libfadc.
 *
 *  Karl Kosack, OCT 2001
 *
 **********************************************************************/

#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <pthread.h>
#include <signal.h>
#include <assert.h>

#include <vme/vme_api.h>
#include <sys/time.h>

#include <fadc.h>

/*==================================================================*/
/* Structures */
/*==================================================================*/

typedef struct RingNode {

    int id;
    int nwords;
    char status;
    pthread_mutex_t mutex;
    struct RingNode *next;
    unsigned long buffer[1024*FADC_MAX_BOARDS]; 
   

} ringnode_t;

enum ringstatus {
    EMPTY,
    FULL,
};

/*==================================================================*/
/* Prototypes */
/*==================================================================*/

void  shutdown(int);
void  getargs( int argc, char **argv );
void  usage(void);
void  init_hardware(void);
void* reader(void*);
void* writer(void*);
void  interface(void);
ringnode_t* make_ringbuffer(int n);
int ringbuffer_write_single( int board, int nwords );
int ringbuffer_write_cblt( int nwords );
void ringbuffer_destroy( ringnode_t *node );
double get_time(void);
double calc_event_rate(void);
void load_board_settings(void);

/*==================================================================*/
/* Globals */
/*==================================================================*/

#define TOTALNODES 1000
#define DEF_FILENAME "fadc-data.raw"

char Debug=0;
char Cblt=0;
char Read=0, Write=0;
int  Numboards=0;
char Active[FADC_MAX_BOARDS];
pthread_t Readerthread, Writerthread;
pthread_attr_t Readerattr, Writerattr;
ringnode_t *Writenode, *Readnode;
unsigned long Nevents=0;
unsigned long Missed=0;
unsigned long Totalnwords=0;
char Filename[128];

int Badevents = 0;
unsigned long Expectednwords[FADC_MAX_BOARDS];
unsigned long *Cbltbuffer = 0;
int Lastboard = 0;

/*==================================================================*/
/* Functions */
/*==================================================================*/

int
main( int argc, char **argv ) {

    int c,i; 
    struct sigaction sa;


    Numboards = fadc_num_boards();
    for (i=0; i<FADC_MAX_BOARDS; i++) Active[i] = 0;

    /* Get command line arguments */

    getargs( argc, argv );

    /* set up ctrl-c handler */

    //    sigfillset( &sa.sa_mask );
    //    sa.sa_flags = 0;//SA_ONESHOT;
    //    sa.sa_handler = shutdown;
    //    if (sigaction(SIGINT, &sa, NULL) < 0) {
    //        perror( "sigaction SIGINT" );
    //        exit(1);
    //    }

    /* Set up ring buffer */

    make_ringbuffer( TOTALNODES );

    /* Set up FADC interface */
    
    init_hardware();


    /* Load the fadc board settings */

    load_board_settings();

    /* set up the reader and writer threads... */

    pthread_attr_init( &Readerattr );
    pthread_attr_init( &Writerattr );

    /* set up CBLT if requested */

    if (Cblt) {
	for (i=0; i<FADC_MAX_BOARDS; i++) 
	    if (Active[i]) Lastboard = i;

	printf("*********************************************************\n");
	printf(" USING HIGH-SPEED CHAINED BLOCK TRANSFERS:\n");
	printf("    using bd %d as the 'last board' in chain\n", Lastboard);
	printf("*********************************************************\n");
    }
    else {
	printf("*********************************************************\n");
	printf(" USING LOW-SPEED WORD TRANSFERS.\n");
	printf("*********************************************************\n");
    }
       
    /* Start user interface ... */
    
    interface();

    /* Clean up */
    
    shutdown(0);

    return 0;

}


void
shutdown( int n ) {
    
    void *statusp;

    printf( "fadc-dacq: waiting for reader and writer to finish...\n");
    Read  = 0; 
    Write = 0;
    pthread_join( Readerthread, &statusp );
    pthread_join( Writerthread, &statusp );
    fadc_exit();
    ringbuffer_destroy(Readnode);
    printf( "fadc-dacq: goodbye.\n");
    exit(n);

}


void
getargs( int argc, char **argv ) {
    
    char flag=0;
    char fileflag=0;
    int c,i;
 
    while (( c = getopt( argc, argv, "o:b:vdc" )) != -1 ) {
	switch (c) {
	case 'v':
	    break;
	case 'd':
	    Debug = 1;
	    break;
	case 'b':
	    flag++;
	    i = atoi(optarg);
	    if (i < 0 || i>=Numboards) {
		fprintf( stderr, 
			 "fadc-dacq: board number must between 0 and %d\n",
			 Numboards-1);
		exit(1);
	    }
	    else {
		Active[i] = 1;
	    }
	    break;
	case 'c':
	    Cblt = 1;
	    break;
	case 'o':
	    strcpy(Filename, optarg);
	    fileflag=1;
	    break;
	    
	default:
	    usage();
	    exit(1);
	}
    }
    
    if (flag == 0) {
	usage();
	printf("You must specify at least one board!\n");
	exit(1);
    }

    if (fileflag == 0) {
	printf( "No output filename was specified. Using '%s'\n",DEF_FILENAME );
	sleep(1);
	strcpy( Filename, DEF_FILENAME );
    }
    
}


void
usage(void) {

    printf( "USAGE: fadc-dacq [-d] -b <boardnum> [-b <boardnum2> ...] -o <output file>\n" );
    printf( " Where boardnum is a number between 0 and %d \n", Numboards-1);
    printf( " If <output file> is not specified, %s is used instead\n", DEF_FILENAME);
    printf("\n");
    printf( " \t-d\tenable debug mode (bad events are printed to screen)\n");
    printf( "\n \t-c\tuse CBLT transfers instead of word transfers\n");
    printf( "\n" );
    
}

void
load_board_settings(void) {

    int i,j, enabledchans=0;
    char filename[128];
    char answer[128];

    for( i=0; i<Numboards; i++ ) {

	if (Active[i]) {

	    sprintf( filename, "fadc-board-%d.settings", i);
	    if (fadc_load_settings( i, filename )) {
		printf("\n** No settings file was detected for board %d\n", i);
		printf("** You should run 'testfadc -b %d', set up the\n", i);
		printf("** board and save its settings file.\n");
		printf("** Do you want to continue with the defaults? (y/n) ");
		scanf("%s", &answer);
		if( tolower(answer[0]) != 'y') 
		    shutdown(0);
	    }

	    // calculate expected nwords:
	    
	    enabledchans = 0;

	    for (j=0; j<10; j++) {
		if (fadc_is_channel_disabled(i,j)==0)
		    enabledchans++;
	    }

	    Expectednwords[i] = (3 + (fadc_get_data_width(i) + 1) 
				 * enabledchans);

	}

    }



}

void
init_hardware(void) {
    int i;

    for (i=0; i<=Numboards; i++) {
	if (Active[i]==0) {
	    fadc_ignore_board( i );
	}
    }
    
    fadc_set_initial_values( 16, 48, 160, 0 );

    if (fadc_init()) {
	exit(1);
    }

    /* test boards */

    fadc_verbose(0);
    fadc_set_mode( FADC_ALL, WORD_MODE );
    usleep(500);
    printf("\n");

    for (i=0 ; i < Numboards; i++) {
	if (Active[i]) {
	    printf("fadc-dacq: board %d buffer ram test: ", i);
	    fflush(stdout);
	    if (fadc_buffer_ram_test(i)) {
		printf( "FAILED\n\n");
		printf( "*** Board %d FAILED the buffer ram test!\n",i );
		printf( "*** Is the board installed? If not it may be\n");
		printf( "*** faulty.\n\n");
		shutdown(1);
	    }
	    else {
		printf( "PASSED\n" );
	    }
	}
    }

    fadc_set_mode( FADC_ALL, FADC_MODE );
    
    fadc_evt_clr();
    usleep(1000);


}


/**
 * User interface (just a text menu right now)
 */
void
interface(void) {

    int i;
    char end = 0, choice;
    char str[128];
    void *statusp;

    while(!end) {

	printf("CHOOSE: 1) start 2) stop 3) status q) quit > ");
	scanf("%s", str);
	choice = str[0];
	
	switch (choice) {
	    
	  case '1':
	      if (!Read && !Write) {
		  fadc_evt_clr();
		  Read=1; Write=1;
		  pthread_create( &Readerthread, &Readerattr, reader, NULL ); 
		  pthread_create( &Writerthread, &Writerattr, 
				  writer, Filename); 
	      }
	      break;
	  case '2':
	      Read=0; Write=0;
	      fprintf(stderr,"WAITING FOR THREADS TO FINISH...\n");
	      pthread_join( Readerthread, &statusp );
	      pthread_join( Writerthread, &statusp );
	      printf("STOP NODES: reader = %d , writer = %d\n", 
		     Readnode->id, Writenode->id);
	      break;
	  case '3':
	      printf("\n---STATUS -----------------------------------\n");
	      printf("Events processed: %d\n", Nevents);
	      printf("Buffer filled   : %d%%\n", buffer_percent());
	      printf("Processing rate : %f evts/sec)\n",calc_event_rate());
	      printf("Missed events   : %d\n", Missed);
	      printf("Data written    : %d Kb \n",
		     Totalnwords*sizeof(unsigned long)/1024);
	      printf("Bad events      : %d \n",Badevents);
	      printf("---------------------------------------------\n");
	      break;
	  case 'q':
	      return;
	  default:
	      printf("Unknown command '%c'\n", choice);
	}
	

    }

    
}


/**
 * Reader thread: continuously grabs data from the fadc's
 */
void*
reader( void *arg ) {

    unsigned long nwords;
    int i;

    printf( "reader: starting!\n");

    if (Cblt){
	Cbltbuffer = fadc_alloc_cblt_buffer( 16384, -1, Lastboard );
	printf("reader: Allocated memory for CBLT buffer.\n");
    }

    calc_event_rate();

    while (Read) {

	if ( fadc_got_event() ) {
	
	    if (Cblt) {

		/* Use Chained Block Transfer */
		nwords = fadc_cblt();
		ringbuffer_write_cblt( nwords );
		
	    }
	    else {
		
		/* Use Word transfers */

		for (i=0; i<Numboards; i++) {
		    
		    if (Active[i]) {
			nwords = fadc_data_available(i);
			ringbuffer_write_single( i, (int)nwords );
		    }
		} 
	    }
	    
	    fadc_evt_clr();	    
	    Nevents++;
	}
    }

    printf("reader: exiting. \n");

}



/**
 * Writer thread: writes data to disk
 */
void*
writer( void *arg ) {

    int i;
    static unsigned long buf[1024*FADC_MAX_BOARDS];
    int nwords;
    char *filename;
    FILE *fp;

    filename = (char *)arg;

    printf( "writer: starting! writing to '%s'\n",filename);

    fp = fopen( filename, "wb" );
    if (fp == NULL) {
	perror("fopen");
	return;
    }

    while (Write) {

	if ( (nwords = ringbuffer_read( buf ) )) {

	    if (nwords > 0) {
		fwrite( buf, sizeof(unsigned long), nwords, fp );
		Totalnwords += nwords;
	    }

	}

    }

    /* Finish up writing everything that is in the buffer */

    printf("writer: finishing up...");
    fflush(stdout);

    while( nwords != -1 ){

	nwords = ringbuffer_read( buf );
	fwrite( buf, sizeof(unsigned long), nwords, fp );
	Totalnwords += nwords;
	printf(".");
	fflush(stdout);
	
    }

    printf("writer: Wrote %d Mb of data to '%s'\n",
	   Totalnwords*4/1024/1024,filename);
    printf("writer: exiting.\n");
    fclose(fp);

}

ringnode_t *
make_ringbuffer(int n) {

    int i;
    ringnode_t *first = NULL;
    ringnode_t *prev = NULL;
    ringnode_t *newnode = NULL;

    /* Make the nodes */

    for (i=0; i<n; i++) {
			  
	prev = newnode;
	newnode = malloc( sizeof( ringnode_t ) );

	if (newnode == NULL) {
	    perror("ringbuffer malloc");
	    shutdown(1);
	}

	newnode->id = i;
	newnode->nwords = 0;
	newnode->status = EMPTY;
	newnode->next = NULL;
	pthread_mutex_init( &(newnode->mutex), NULL );

	if (i==0) { 
	    first = newnode;
	}

	if (prev != NULL) {
	    prev->next = newnode;
	}

    }    

    /* connect the last node to the first */
    newnode->next = first;

    /* set pointers to read and write nodes*/
    Readnode = Writenode = first;


    printf( "fadc-dacq: Created a %d event ring buffer (%d Kb)\n", 
	    n,(n*sizeof(ringnode_t))>>10 );

    return first;

}

int
ringbuffer_write_single( int board, int nwords ) {

    int ret=0;
    ringnode_t *next;

    pthread_mutex_lock( &(Writenode->mutex) );
    
    if (Writenode->status == EMPTY) {

	fadc_memcpy( Writenode->buffer, board, (unsigned long)nwords );
	Writenode->status = FULL;
	Writenode->nwords = nwords;
        next = Writenode->next;

	/* Check for corrupt event */
	if  (((Writenode->buffer[0] & 0xFFFF0000) != 0xFADC0000) ||
	     (nwords > Expectednwords[board])) {
	    Badevents++;
	    if (Debug) {
		int i;
	        printf("NWORDS = %d\n", Writenode->nwords);
		printf("START HEADER = 0x%08lx\n", Writenode->buffer[0]);
		printf("ALL DATA:\n");
		for(i=0; i<Writenode->nwords; i++) {
		    printf("%08lx ", Writenode->buffer[i]);
		    if ((i+1)%8==0) printf("\n");
		}
		printf("\n");
	    }
	}
   
    }
    else {
	fprintf(stderr,"** WRITE FAILED: BUFFER FULL at node %d\n", 
		Writenode->id);
	next = Writenode;
	Missed++;
	ret = 1;
    }

    pthread_mutex_unlock( &(Writenode->mutex) );
   
    Writenode = next;  /* only this function should increment Writenode */

    return ret;

}

int
ringbuffer_write_cblt( int nwords ) {

    int ret=0;
    ringnode_t *next;

    pthread_mutex_lock( &(Writenode->mutex) );
    
    if (Writenode->status == EMPTY) {

	memcpy( Writenode->buffer, Cbltbuffer, nwords*sizeof(unsigned long));
	Writenode->status = FULL;
	Writenode->nwords = nwords;
        next = Writenode->next;

    }
    else {
	fprintf(stderr,"** WRITE FAILED: BUFFER FULL at node %d\n", 
		Writenode->id);
	next = Writenode;
	Missed++;
	ret = 1;
    }

    pthread_mutex_unlock( &(Writenode->mutex) );
   
    Writenode = next;  /* only this function should increment Writenode */

    return ret;

}


/**
 * Puts one node of buffered data into buf, returns number of words copied
 */ 
int
ringbuffer_read( unsigned long *buf ) {

    int nwords;
    ringnode_t *next;

    pthread_mutex_lock( &(Readnode->mutex) );    

    if (Readnode->status == EMPTY ) {
	nwords = -1;
	next = Readnode;
    }
    else {

	nwords = Readnode->nwords;
	memcpy( buf, Readnode->buffer, nwords*sizeof(unsigned long) );
	Readnode->nwords = 0;
	Readnode->status = EMPTY;
	next = Readnode->next;

    }

    pthread_mutex_unlock( &(Readnode->mutex) );

    Readnode = next;

    return nwords;

}

/**
 * De-allocate memory for ring buffer starting at node "start"
 */
void
ringbuffer_destroy( ringnode_t *start ) {

    int count=0;
    ringnode_t *first, *prev, *cur;

    first = start;
    cur = start->next;
    prev = start;

    while (cur != first) {
	
	free(prev);

	count++;
	prev = cur;
	cur = cur->next;

    }
    
    free(first);
    count++;

    printf("fadc-dacq: %d kb memory for %d event ring buffer freed\n",
	   (count*sizeof(ringnode_t))>>10,count);


}


/**
 * Return the percentage of the ring buffer that is full
 */
int
buffer_percent(void ) {
    
    int rid, wid;
    float percent;

    wid = Writenode->id;
    rid = Readnode->id;

    if (rid>wid) wid += TOTALNODES;
    percent = (wid-rid)/(float)TOTALNODES *100.0;
    
    return (int)percent;

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

double 
calc_event_rate(void) {

    static double t0=0;
    static unsigned long nevt0=0;
    unsigned long nevt1;
    double t1,hits,elapsed, rate=0;

    nevt1 = Nevents;
    t1 = get_time();
    elapsed = t1 - t0;
    
    hits = (double)(nevt1-nevt0);

    rate = hits/elapsed;
    
    t0 = t1;             /* update time */
    nevt0 = nevt1;       /* update scaler */
    return rate;


}

