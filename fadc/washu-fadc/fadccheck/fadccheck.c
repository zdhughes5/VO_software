/*
      cblt1.c                                                            
      12/10/02                                                         
      Test routines for the CBLT testing and temp sensor testing  

      7/6/02: KPK: updated to use libfadc routines
      
      Hardware notes:

      This version uses A32 bit addressing and D32 bit data transfers.

      VME memory-mapped I/O window set to 0xf0fb0000 - 0xf0ffffff.
      Window address set in /etc/modules.conf and initialized
      at bootup in vme program. 
      vmeUniverse program must be running in background for this program to run.

      4/24/03: PD+PR: added support for 2 FADC boards

      5/13/03: KPK, load settings from fadc .settings file
*/

/* C Library Include Files */

#include <vme/vme_api.h>

#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <ctype.h>
#include <termios.h>
#include <time.h>
#include <sys/time.h>
#include <fadc_lowlevel.h>  /* needed to access low-level routines */
#include <fadc.h>

#define MAXLLEN         80
#define MAX_FADC_BYTES  9000
#define SIGNUM          30      /* SIGUSR1 */
#define DMA_BUFSIZE     16384   /* dma buffer size in bytes */
#define STR_LEN 1024

char Berr_flag=0;
int Boardnum=-1;
int Firstboard = -1;  /* default to clock board*/
int Lastboard =9;
int User_specified_cblt = 0;

double get_time();
void crate_menu();
void reset_keypress(void);
void set_keypress(void);
void read_event(void);
int getkey();
void getargs( int argc, char **argv );
void printword(unsigned long wd);

int Current_mode = FADC_MODE;

struct termios stored_settings;

unsigned long *clkbd_lptr;   /* pointer for D32 CLKBD transfers    */
unsigned long *fadc_lptr;
unsigned long *fadc_lptr2;

int Boardnum;

int main(int argc, char **argv) {

    int i;
    unsigned long j,k;
    unsigned long *lptr;
    unsigned long nwords, pattern, pattern2,n2words, nerrors;
    unsigned long temp_flag;
    int quit;
    int low,high,numboards;
    char c;
    unsigned long *dmabuffer;
    char filename[128], answer[10];
    int ncbltwords;
		
    getargs( argc, argv );

    /* Initialize the hardware (libfadc will do all the mapping) */

    fadc_init();
    fadc_verbose(1);

    /* cause fadc_exit() to be called when the program exits */ 

    atexit( fadc_exit );

    /* choose good values for first and last board */

    low = 999;
    high = -999;
    numboards =0;
    for (i=0; i<fadc_num_boards(); i++) {
        if (fadc_is_board_present(i)) {
	    if (i<low) low = i;
	    if (i>=high) high = i;
	    numboards++;
	}
    }

    if (Boardnum == -1) Boardnum = low;

    if (numboards <= 1) {
	Firstboard = -1;
	Lastboard = Boardnum;
    }
    else {
	Firstboard = low;
	Lastboard = high;
    }
   
    /* allocate memory for cblt.  */
    
    dmabuffer = fadc_alloc_cblt_buffer(DMA_BUFSIZE,Firstboard,Lastboard);

    if (dmabuffer == NULL) {
	printf("Couldn't allocate memory for CBLT transfer\n");
	exit(1);
    }
    
    printf( "CBLT: Firstboard=%d, Lastboard=%d\n", Firstboard,Lastboard);


    /* load board settings */
    fadc_verbose(0);
    for (i=0; i<fadc_num_boards(); i++){
      if (fadc_is_board_present(i)) {
	sprintf( filename, "fadc-board-%d.settings", i );
	printf("Loading settings for board in slot %d...\n", i);
	if (fadc_load_settings( i, filename )) {
	  printf("\n** No settings file was detected for board %d\n", i);
	  printf("** You should run 'testfadc -b %d', set up the\n", i);
	  printf("** board and save its settings file.\n");
	  printf("** Do you want to continue with the defaults? (y/n) ");
	  scanf("%s", answer);
	  if( tolower(answer[0]) != 'y') {
	    exit(0);
	  }
	}
      }
    }
    fadc_verbose(1);

    /* Set some pointers to the boards for low-level access */

    clkbd_lptr = fadc_get_clk_lptr();
    fadc_lptr =  fadc_get_fadc_lptr(Boardnum);

    printf("lptr addr for FADC bd %d = 0x%08lx\n", Boardnum,
	   (unsigned long) fadc_lptr);
    printf("lptr addr for CLK bd = 0x%08lx\n", (unsigned long) clkbd_lptr);


    /* Set event number and clear out event */

    fadc_set_mode(Boardnum, WORD_MODE);	     
    wr_evt_no(fadc_lptr, 0xac000000); 
    fadc_set_mode( Boardnum, Current_mode );
    fadc_evt_clr();

    /* set up for "enterless" key grabbing */
    set_keypress();

    /* display Menu */
    
    quit = 0;
    while(!quit){
	printf("\033[01;32m");
	printf(" MAIN MENU:====[SLOT %2d, s to switch]======================\n"
	       , Boardnum);
	printf(" k: Write 1 word     l: Read 1 word      h: Read Headers\n");
	printf(" 1: Event Clear      e: Read event (WD)  4: Read Event (CBLT)\n");
	printf(" n: Clear+Read evt   m: Buffer Ram Test  b: Buffer stability \n");
	printf(" 6: Clear Scalars    7: Read Scalars     B: buffer bit walk  \n");
	printf(" d: Ramp CFD Thresh  f: Ramp CFD Width   C: Crate menu...\n"); 
	printf(" 8: Ped command      9: read command     0: dump command \n"); 
	printf(" M: set Mode         W: set data Width   i: check dead tIme\n");
        printf(" a: 1khz             v: 2 khz            j: 4 khz\n");
        printf(" o: 8 khz            q: 16 khz           p: pedvar reset\n");
        printf(" g: pedvar off        \n");
	printf(" z: Set 0-sup level  t: Read Temp flag   x: EXIT \n");
	printf(" \033[0m COMMAND: " );

/* 	scanf("%s", command); */
/* 	c = command[0]; */

	c = getkey();

	printf("\n\n");

	switch(c){
	
	case 'a':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_1khz();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar 1Khz set\n");
	    break;
	case 'v':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_2khz();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar 2Khz set\n");
	    break;
	case 'j':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_4khz();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar 4Khz set\n");
	    break;
	case 'o':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_8khz();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar 8Khz set\n");
	    break;
	case 'q':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_16khz();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar 16Khz set\n");
	    break;
	case 'p':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_reset();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar reset set\n");
	    break;
	case 'g':
	    fadc_set_mode( Boardnum, WORD_MODE );
	    set_pedvar_off();
	    fadc_set_mode( Boardnum, FADC_MODE );
	    printf("pedvar reset set\n");
	    break;
	
	case 's':
	    {
		int newboard;

		printf("Slots with boards: ");
		for(i=0; i<fadc_num_boards(); i++) {
		    if (fadc_is_board_present(i)) printf("%d ",i);
		}
		printf("\n");
		printf("Enter new slot number: ");
		scanf("%d", &newboard );
		if (newboard <0 || newboard >= fadc_num_boards()){
		    printf("That slot number is invalid");
		}
		else {
		    if (fadc_is_board_present(newboard)==0) {
			printf("\033[01;31mWARNING: board %d isn't detected, "
			       "using it anyway \033[0m\n",newboard);
		    }
		    Boardnum = newboard;
		    fadc_lptr =  fadc_get_fadc_lptr(Boardnum);
		}

	    }
	    break;

	case '1':
	    /* evt clr */
	    fadc_evt_clr();
	    printf("evt clr command issued\n\n");    
	    break;

	case '4': 
	    {

		int first=32,last=32;
	      
		printf("DMA Read...\n");
		
		ncbltwords = fadc_cblt();

		if (last > ncbltwords) last =1;
		
		if (ncbltwords>=0)
		    printf("Words read in cblt: %d\n",ncbltwords);
		else if (ncbltwords == -1) 
		    printf("DMA transfer failed!\n");
		else if (ncbltwords == -2)
		    printf("DMA transfer timed out waiting for BERR*\n");
		else 
		    printf("STRANGE NCBLTWORDS! : %d\n", ncbltwords);
	       
		
		if (ncbltwords >= 64) {
		    printf("First %d words in buffer: \n",first);
		    for (i=0; i<first; i++) {
			printword(dmabuffer[i]);
			if ((i+1)%8==0)printf("\n");
		    }
		    printf("...\n\n");

		    printf("Last %d words in buffer: ...\n",last);
		    for (i=ncbltwords-last; i<ncbltwords; i++) {
			printword(dmabuffer[i]);
			if ((i+2)%8==0)printf("\n");
		    }
		    printf("\n\n");

		}
		else if (ncbltwords >0 && ncbltwords<64) {
		    for (i=0; i<ncbltwords; i++) {
			printword(dmabuffer[i]);
			if ((i+1)%8==0)printf("\n");
		    }
		    printf("\n\n");
		}
		else {
		    printf("No data in buffer\n");
		}

		printf("Type '$' to dispay the entire CBLT buffer\n");
	    
	    }
	    break;

	case '$':
	    {
		
		printf("Entire CBLT buffer (%d) words:\n",ncbltwords);

		for (i=0; i<ncbltwords&&i<DMA_BUFSIZE; i++) {
		    printword(dmabuffer[i]);
		    if ((i+1)%8==0) printf("\n");
		}
		printf("\n");

	    }
	    break;

	case '%':
	  {
	    /* clear the CBLT buffer */
	    for (i=0; i<DMA_BUFSIZE; i++) {
	      dmabuffer[i] = 0xBADBEEF0;
	    }
	    printf("CBLT buffer set to 0xABADBEEF\n");

	  }
	  break;

	case 'z':
	    {
		unsigned long newlevel;
		printf("Enter new zero-suppress threshold: ");
		scanf( "%lu", &newlevel );

		fadc_set_mode(Boardnum,WORD_MODE);
		fadc_set_area_discrim( Boardnum, FADC_ALL, newlevel );
		fadc_set_mode(Boardnum,Current_mode);
		
		printf("Set zero-supress thresholds to %lu on all chans\n",
		       newlevel);

	    }
	    break;

	case '6':
	    /* Clear scalers */
	    fadc_set_mode( Boardnum, WORD_MODE );
	    fadc_multicast_clear_trigger_scaler();
	    fadc_set_mode( Boardnum, Current_mode );
	    printf("Scalers cleared\n");
	    break;

	case '7':
	    /* Read scalers */
	    fadc_set_mode( Boardnum, WORD_MODE );
	    for (i=0; i<10; i++) {
		j = fadc_get_trigger_scaler( Boardnum, i );
		printf("scaler on ch %d = 0x%08lx, %lu\n", i, j, j);
	    }
	    fadc_set_mode( Boardnum, Current_mode );
	    break;

	case 'b': 
	    {
		/* buffer ram stability test */
		
		int numtests=1000;

		fadc_set_mode( Boardnum, WORD_MODE );
		printf("Buffer Ram Stability test:\n");
		printf("Enter number of tests to run: ");
		scanf("%d", &numtests );

		printf("Running many buffer ram tests...\n");
		j=0; 
		fadc_verbose(0);
		for(i=0; i<numtests; i++) {
		    j += fadc_buffer_ram_test( Boardnum );
		    if (i%100) printf("\ttest %d of %d (%lu errors so far) \r",
				      i,numtests,j);
		}
		printf("\n");
		fadc_verbose(1);
		fadc_set_mode( Boardnum, Current_mode );
		getkey();
	    }
	    break;
	case 'h':
	    {

		unsigned long start,stop,offs,addr;

		/* read headers */
		printf("Clock bd headers: \n\t");
		lptr = clkbd_lptr + 0x2000;
		for (i=0;  i<8; i++){
		    printword(*lptr);
		    if ((i+1)%4==0) printf("\n\t");
		    lptr++;
		}
		printf("\n");
		/* read FADC bd headers (registers in DP gate array) */
		lptr = fadc_lptr + RD_START_HDR;
		j = *lptr;
		printf("FADC board: start hdr  = %08lx\n", j);
		lptr = fadc_lptr + RD_EVT_HDR;
		j = *lptr;
		printf("event hdr  = %08lx\n", j);
		lptr = fadc_lptr + RD_HIT_HDR;
		j = *lptr;
		printf("hit hdr    = %08lx\n", j);
		lptr = fadc_lptr + RD_AREA_HDR;
		j = *lptr;
		printf("area hdr   = %08lx\n", j);
		lptr = fadc_lptr + RD_STATUS_HDR;
		j = *lptr;
		k = *lptr & 0x0001ffff;
		printf("status hdr = %08lx    %ld words\n", j, k);
		lptr = fadc_lptr + RD_STATUS_HDR + 1;
		j = *lptr & 0x000003ff;
		printf("board id   = %ld\n", j);
		

		/* read the reread/pedestal/hilo registers */
		
		lptr = fadc_lptr + 0x2001;
		j = *lptr;
		offs = j & 0x0000ffff;
		addr = (j & 0xffff0000) >> 16;
		usleep(100);
		k = *lptr & 0xc0000000;
		lptr = fadc_lptr + 0x2002;
		usleep(100);
		j = *lptr;
		stop = j & 0x0000ffff;
		start = (j & 0xffff0000) >> 16;
		k = stop - start;
		j = addr - offs;
		printf("stop= %lx  start= %lx  offset= %lx\n", stop,start,k);
		printf("ST30_addr= %lx  ST21_addr= %lx  delta= %lx \n", 
		       addr,offs, j);
		printf("\n");


		break;
	    }
	case 't':
	    /* read hi temp flag */
	    lptr = fadc_lptr + RD_STATUS_HDR;
	    j = *lptr;
	    temp_flag =  j & 0x00020000;
	    printf("hdr = %08lx    temp flag = %08lx\n", j, temp_flag);
	    break;
	case 'm':
	    /* buf ram pattern test */
	    /* note: max size of buf ram is 8192 words */
	    fadc_set_mode(Boardnum, WORD_MODE);	  
	    printf("\nBuf ram pattern test \n");
	    nwords = 8192;
	    /* write pattern into buf ram */
	    pattern = 0x5555aaaa;
	    pattern2 = 0xaaaa5555;
	    lptr = fadc_lptr;
	    printf("Writing %lu words of %08lx %08lx patterns to buf ram\n",
		   nwords, pattern, pattern2);
	    n2words = nwords / 2;
	    for (j=0; j<n2words; j++){
		*lptr = pattern;
		lptr++;
		*lptr = pattern2;
		lptr++;
	    }
	    printf("Reading buf ram: \n");
	    lptr = fadc_lptr;
	    nerrors = 0;
	    n2words = nwords / 2;
	    for (j=0; j < n2words; j++){
		k = *lptr;
		if (j < 30)
		    printf(" %08lx ", k);
		if (k != pattern){
		    printf(" ERROR @ %lu = %08lx\n", j, k);  
		    nerrors++;
		}
		lptr++;
		k = *lptr;
		if (j < 30)
		    printf(" %08lx ", k);
		if (k != pattern2){
		    printf(" ERROR @ %lu = %08lx\n", j, k); 
		    nerrors++;
		}
		lptr++;
	    }
	    printf("\nTotal number of errors is: %lu\n", nerrors);
	    printf("\nstarting next test... please wait 5 seconds\n");-
	    sleep(4);

	    /* write incremental pattern into buf ram */
	    printf("Writing %ld words of incremental pattern to buf ram\n",nwords);
	    lptr = fadc_lptr;
	    for (j=0; j<nwords; j++){
		*lptr = j;
		lptr++;
	    }
	    printf("Reading %lu words from buf ram: \n", nwords);
	    lptr = fadc_lptr;
	    nerrors = 0;
	    for (j=0; j < nwords; j++){
		k = *lptr;
		if (j < 30)
		    printf(" %08lx ", k);
		if (k != j){
		    printf("  ERROR @ %ld :  %08lx != %08lx\n", j,j,k);
		    nerrors++;
		}
		lptr++;
	    }
	    printf("\nTotal number of errors is: %lu\n", nerrors);
	    fadc_set_mode(Boardnum, Current_mode);
	    break;
	    
	case 'B':
	    {
		unsigned long readword;
		nerrors =0;
		lptr = fadc_lptr;
		for (j=0; j<8192; j++) {
		    for (i=0; i<32; i++) {
			*lptr = 0x1 << i;
			readword = *lptr;
			if (readword != (0x1 <<i)) {
			    printf("Word %lu error: bit %d is wrong\n",j,i);
			    nerrors++;
			}
		    }
		    lptr++;
		}
		printf("Walked a bit across each of the 8192 words of buffer ram\n");
		printf("Errors found: %lu\n", nerrors);
	    }
	    break;

	case 'd':
	    {
		int chan;
		
		/* chan thr dac ramp test */
		printf("Probe on pin 6 on the CFD\n");
		printf("ENTER CHANNEL NUMBER TO TEST: ");
		scanf("%d", &chan);

		if (chan>9 || chan <0) {
		    printf("*** INVALID CHANNEL NUMBER\n");
		    break;
		}

		printf("\nchan %d thresh DAC ramp test\n", chan);
		printf("verify thresh DAC ramps up from -1.5V to +2.5V\n");

		fadc_verbose(0);
		for (i=0; i<4096; i+=40) {
		    fadc_set_cfd_thresh( Boardnum, chan, i );
		    fprintf(stderr, "THRESHOLD: %d\r", i);
		    usleep(200);
		}
		printf("\n");
		fadc_verbose(1);
	    }
	    break;
	case 'f':
	    {
		int chan;

		/* chan width dac ramp test */

		printf("Probe on pin 5 on the CFD\n");
		printf("ENTER CHANNEL NUMBER TO TEST: ");
		scanf("%d", &chan);

		if (chan>9 || chan <0) {
		    printf("*** INVALID CHANNEL NUMBER\n");
		    break;
		}

		printf("\nchan %d thresh DAC ramp test\n", chan);
		printf("verify width DAC ramps up from -1.5V to +2.5V\n");
		
		fadc_verbose(0);
		for (i=0; i<4096; i+=40) {
		    fadc_set_cfd_width( Boardnum, chan, i );
		    fprintf(stderr, "WIDTH: %d\r", i);
		    usleep(200);
		}
		printf("\n");
		fadc_verbose(1);

	    }
	    break;
	case 'M': 
	    {
		/* set fadc mode */
		int mode;
		fadc_verbose(1);
		printf("Choose a mode (0) Zero-Suppress (1) FULL mode: ");
		mode = getkey();
		if (mode == '0') {
		    Current_mode= FADC_MODE;
		    printf("Set all FADC boards in crate to FADC_MODE (0-suppress).\n");
		}
		else {
		    Current_mode = FULL_MODE;
		    printf("Set all FADC boards in crate to FULL_MODE.\n");
		}
		fadc_set_mode( FADC_ALL, Current_mode );
		fadc_verbose(0);
	    }	    
	    break;
	case 'W':
	    {
		/* set data width */
		unsigned long newwidth;
		printf("Enter data width for board in slot %d: ", Boardnum );
		scanf("%ld", &newwidth );
		fadc_set_data_width( Boardnum, newwidth );
		getkey();
		break;
	    }
	case 'i':
	    {
		/* measure dead time */

		double start_time;
		double end_time;
		double elapsed;
		double rate;
		double misfrac;
		int nevents=0;
		unsigned long elapsed_0, elapsed_1;
		unsigned long live_0, live_1;
		unsigned long delta_elapsed, delta_live;
		double deadtime;

		printf("Make sure system is triggering at a fixed rate.\n");
		printf("Please enter the trigger rate of the pulser (in Hz): ");		scanf("%lf", &rate);
		printf("Please enter number of events to collect (big is better):");
		scanf("%d", &nevents);

		printf("Measuring dead time for %d events. please wait...\n",
		       nevents);
		

		/* grab an event to make sure the scalars can be read: */

		fadc_evt_clr();
		while(fadc_got_event() == 0);

		start_time = get_time();
		elapsed_0 = fadc_get_elapsed_scaler();
		live_0 = fadc_get_livetime_scaler();		

		for (i=0; i<nevents; i++) {
                    fadc_evt_clr();
                    while(fadc_got_event() == 0) {
                        ;
                    }
                    ncbltwords = fadc_cblt();

                }

		elapsed_1 = fadc_get_elapsed_scaler();
		live_1 = fadc_get_livetime_scaler();
		end_time = get_time();
		
		
		
		elapsed = (end_time - start_time);
		misfrac = (1.0-((double)nevents)/(elapsed*rate));

		printf("Trig Rate   : %f Hz \n", rate); 
		printf("N_events    : %d \n", nevents );
		printf("\nFROM CPU MEASUREMENT: \n");
		printf("-------------------------\n");
		printf("Elapsed time: %f sec \n", elapsed); 
		printf("<t> per evt : %f sec \n", elapsed/(double)nevents);
		printf("missed %%    : %f %%\n", misfrac*100  );
		printf("dead time   : %f sec \n", elapsed/(double)nevents - (1.0/rate)*0.5 );
		
		delta_live = live_1 - live_0;
		delta_elapsed  = elapsed_1 - elapsed_0;
		deadtime = ((double)(delta_elapsed-delta_live))/32.0e6;
		elapsed =  ((double)delta_elapsed)/32.0e6;
	    
		printf("\nFROM CLK/TRIG SCALER MEASUREMENT: \n");
		printf("-------------------------\n");
		printf("elapsed_0=%lu ", elapsed_0);
		printf("elapsed_1=%lu ", elapsed_1);
		printf("live_0=%lu ", elapsed_0);
		printf("live_1=%lu \n", elapsed_1);
	       
		printf("Livetime    : %g sec\n",((double)delta_live)/32.0e6);
		printf("Elapsed time: %g sec\n",elapsed);
		printf("Dead time   : %g sec\n", deadtime);
		printf("Dead time %% : %g \n",  deadtime/elapsed*100.0);
		getkey();
	    }
	    break;
	case 'n':
	    /* clr & read status & event data */
	    fadc_evt_clr();
	    read_event();
	    break;
	case 'e':
	    read_event();
	    break;
	case 'k':
	    fadc_set_mode(Boardnum, WORD_MODE);
	    printf("\n wr 1 word 0x12345678 pattern\n");
	    lptr = fadc_lptr;
	    *lptr = 0x12345678;
	    fadc_set_mode( Boardnum, Current_mode );
	    break;
    	case 'l':
	    j = *fadc_lptr;
	    printf("\n rd 1 word = %08lx\n", j);
	    break;
    	case 'x':
	    printf("\n exiting program \n");
	    quit = 1;
	    break;
	case 'C':
	    crate_menu();
	    break;
	case '8':
	    fadc_request_pedestal();
	    printf("Sent pedestal command\n");
	    read_event();
	    break;
	case '9':
	    fadc_request_reread();
	    printf("Sent reread command\n");
	    read_event();
	    break;
	case '0':
	    fadc_request_dump();
	    printf("Sent dump command\n");
	    read_event();
	    break;
	default:
	    printf("\n unused key '%c' [%d] \n", c,c);
	    break;
	}


    } /* end while */

    reset_keypress();

    return(0);
}


void
crate_menu() {

    //    char command[256];
    char c;

    while (1) {
	printf("=CRATE MENU:==============================================\n");
	printf("These commands set ALL channels on ALL boards on the crate\n");
	printf("  t. set CFD Threshold \n");
	printf("  w. set CFD width \n");
	printf("  r. set CFD RateFB \n");
	printf("  d. set CFD moDe \n");
	printf("  p. set Pedestal offset\n");
	printf("  P. set Pedestal width\n");
	printf("  z. set Zero-supress level\n");
	printf("  W. set data Width\n");
	printf("  m. back to Main menu\n");
	printf("  CRATE COMMAND:" );
	
/* 	scanf("%s", command); */
/* 	c = command[0]; */

	c = getkey();
	
	switch(c){
	case 't':   
	    {
		unsigned long newval;
		printf("Enter new CFD THRESHOLD: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_cfd_thresh( FADC_ALL, FADC_ALL, newval );
		return;
	    }
	case 'w':   
	    {
		unsigned long newval;
		printf("Enter new CFD WIDTH: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_cfd_width( FADC_ALL, FADC_ALL, newval );
		return;
	    }
	case 'r':   
	    {
		unsigned long newval;
		printf("Enter new CFD RateFB: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_cfd_ratefb( FADC_ALL, FADC_ALL, newval );
		return;
	    }
	     
	case 'd':   
	    {
		unsigned long newval;
		printf("Enter new CFD MODE (0=threshold 1=cfd): ");
		scanf( "%lu", &newval );
		if (newval ==0 || newval == 1) {
		    printf("Setting ALL channels on ALL boards to %lu...\n",
			   newval);
		    fadc_set_cfd_mode( FADC_ALL, FADC_ALL, newval );
		}
		else {
		    printf("INVALID MODE. not setting\n");
		}
		return;
	    }
	case 'p':   
	    {
		unsigned long newval;
		printf("Enter new pedestal OFFSET: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_pedestal_offset( FADC_ALL, FADC_ALL, newval );
		return;
	    }
	case 'P':   
	    {
		unsigned long newval;
		printf("Enter new pedestal WIDTH: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_pedestal_width( FADC_ALL, newval );
		return;
	    }
	case 'z':   
	    {
		unsigned long newval;
		printf("Enter new Zero-supress level: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_area_discrim( FADC_ALL, FADC_ALL, newval );
		return;
	    }
	case 'W':   
	    {
		unsigned long newval;
		printf("Enter new data_width: ");
		scanf( "%lu", &newval );
		printf("Setting data width on ALL boards to %lu...\n",
		       newval);
		fadc_set_data_width( FADC_ALL, newval );
		getkey();
	    }
	    return;
	case 'm':
	    return;
	default:
	    printf("\n unused key '%c' \n", c);
	    break;
	    
	}
    }

}


void read_event() {
    
    int nwords,i,tries;
    unsigned long *lptr;

    tries = 0;
    while(fadc_got_event() == 0) {
	tries++;
	usleep(10);
	if (tries > 1000) {
	    printf("No event in buffer. Make sure the pulser is pulsing!\n");
	    break;
	}
    }
    if (tries<1000) {
	nwords = fadc_data_available(Boardnum);
	printf("WORDS IN BUFFER: %d\n",nwords);
	if (nwords > 0) {
	    
	    for (i=0, lptr=fadc_lptr; i<nwords; i++,lptr++) {
		printword(*lptr);
		if ((i+1)%8==0) printf("\n");
	    }
	    printf("\n\n");

	}
	    
    } 
    
} 

void set_keypress(void) {
    struct termios new_settings;
    tcgetattr(0,&stored_settings);
    new_settings = stored_settings;
    new_settings.c_lflag &= (~ICANON);
    new_settings.c_cc[VTIME] = 0;
    tcgetattr(0,&stored_settings);
    new_settings.c_cc[VMIN] = 1;
    tcsetattr(0,TCSANOW,&new_settings);
}

void reset_keypress(void) {
    tcsetattr(0,TCSANOW,&stored_settings);
}

int getkey(void) {

    int c;

    c = getchar();
    if (c==-1) c=getchar();
    printf("\n");
    return((char)c);

}


void
getargs( int argc, char **argv ) {
    
    int c;
 
    Boardnum = -1;

    while (( c = getopt( argc, argv, "b:f:l:")) != -1 ) {
        switch (c) {
        case 'b':
	    Boardnum = atoi(optarg);
	    printf("Using board %d\n",Boardnum);
	    break;
	case 'f':
	  Firstboard = atoi(optarg);
	  User_specified_cblt=1;
	  break;
	case 'l':
	  Lastboard = atoi(optarg);
	  User_specified_cblt=1;
	  break;
	case 'h':
	    printf("USAGE: fadccheck -b <slot number>\n\n");
	    printf("\t-f #\t- set firstboard to specified slot number\n");
	    printf("\t-l #\t- set lastboard to specified slot number\n");
	    break;
	}

    }

}

void 
printword(unsigned long wd) {
    if ((wd&0xFFFF0000) == 0xFADC0000) 
	printf("\033[01;33m%08lx\033[0m ", wd);
    else if ((wd&0xFFFF0000) == 0xCAFE0000) 
	printf("\033[01;35m%08lx\033[0m ", wd);
    else 
	printf("%08lx ", wd);
}


/* return the time in microseconds*/
double
get_time() {

    double time=0;

    struct timeval tv;
    struct timezone tz;

    gettimeofday( &tv,&tz);
    
    time = tv.tv_sec + (double)tv.tv_usec/1.0e6;
    
    return time;
    

}
