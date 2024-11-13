/*
      cernfadc.c                                                            
      9/26/2018                                                         
      CERN run fadc data acquisition program  

      uses libfadc routines
      
      Hardware notes:

      This version uses A32 bit addressing and D32 bit data transfers.
	  
	  Uses a clock/trig board (first board) and 3 FADC boards
	  
	  Clock/trig board address: 0xf0ff0000 (first board flag set)
	  FADC board 7 address: 0xf0f70000
	  FADC board 8 address: 0xf0f80000
	  FADC board 9 address: 0xf0f90000 (last board flag set)	  

      VME memory-mapped I/O window set to 0xf0fb0000 - 0xf0ffffff.
      Window address set in /etc/modules.conf and initialized at bootup in vme program. 
      vmeUniverse program must be running in background for this program to run.

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
int Boardnum7 = 7;
int Boardnum8 = 8;
int Boardnum9 = 9;
int Firstboard = -1;  /* default to clock board*/
int Lastboard = 9;
int User_specified_cblt = 0;

double get_time();
void crate_menu();
void reset_keypress(void);
void set_keypress(void);
void read_event(void);
int getkey();
void getargs( int argc, char **argv );
void printword(unsigned long wd);

int Current_mode = FULL_MODE;  /* read all 10 chans */

struct termios stored_settings;

unsigned long *clkbd_lptr;   /* pointer for D32 CLKBD transfers    */
unsigned long *fadc_lptr;
unsigned long *fadc_lptr7;
unsigned long *fadc_lptr8;
unsigned long *fadc_lptr9;

int Boardnum;

int main(int argc, char **argv) {

    int i, first, last, tries;
	int board_no, chan, newboard, mode;
    unsigned long j,k;
    unsigned long *lptr;
    unsigned long nwords, pattern, pattern2,n2words, nerrors;
	unsigned long newlevel, newoffset, newwidth;
	
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
    numboards = 0;
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
	fadc_lptr7 =  fadc_get_fadc_lptr(Boardnum7);
	fadc_lptr8 =  fadc_get_fadc_lptr(Boardnum8);
    fadc_lptr9 =  fadc_get_fadc_lptr(Boardnum9);

    printf("lptr addr for FADC bd %d = 0x%08lx\n", Boardnum,
	   (unsigned long) fadc_lptr);	
    printf("lptr addr for FADC bd %d = 0x%08lx\n", Boardnum7,
	   (unsigned long) fadc_lptr7);
    printf("lptr addr for FADC bd %d = 0x%08lx\n", Boardnum8,
	   (unsigned long) fadc_lptr8);
    printf("lptr addr for FADC bd %d = 0x%08lx\n", Boardnum9,
	   (unsigned long) fadc_lptr9);
    printf("lptr addr for CLK bd = 0x%08lx\n", (unsigned long) clkbd_lptr);


    /* Set event number and clear out event */

    fadc_set_mode(Boardnum7, WORD_MODE);	     
    wr_evt_no(fadc_lptr7, 0xac000000); 
    fadc_set_mode(Boardnum8, WORD_MODE);	     
    wr_evt_no(fadc_lptr8, 0xac000000); 
    fadc_set_mode(Boardnum9, WORD_MODE);	     
    wr_evt_no(fadc_lptr9, 0xac000000); 
    fadc_set_mode( Boardnum7, Current_mode );
    fadc_set_mode( Boardnum8, Current_mode );
    fadc_set_mode( Boardnum9, Current_mode );	
    fadc_evt_clr();

    /* set up for "enterless" key grabbing */
    set_keypress();

    /* display Menu */
    
    quit = 0;
    while(!quit){
		printf("\033[01;32m");
		printf("   ====  Commands (from Analysis Computer):  ====\n");
		printf(" w: set Data Width     u: set Re-read Width     y: set HiLo Width \n");
		printf(" d: set Data Lookback  r: set Re-read Lookback  b: set HiLo Lookback \n");		
		printf(" e: set Area Width     a: set Area Lookback     c: set CFD Thresh \n");		
		printf(" m: set Mode           z: set 0-Sup Level       p: clear Scalers \n");
		/* need to add: CFD Width */
		
		printf("\n   ====  Get Event Data (send to Analysis Computer):  ====\n");
		printf(" 1: Event Clear      2: Event Clear & Read Event CBLT \n");
		printf(" 3: Read Event CBLT  4: Re-read Event CBLT \n");				
		printf(" 5: Read Event WORD  6: Read Scalers \n");
		
		printf(" C: Crate menu       x: EXIT \n");
		printf(" \033[0m COMMAND: " );
 
/*		Not used now (and may be deleted):
		printf(" h: Read Headers     M: Buffer Ram Test  i: check dead time\n");
		printf(" 8: Ped command      0: dump command     s: slots with bds\n"); 
*/
		c = getkey();
		printf("\n\n");

	switch(c){

    /*  *************  Commands (from Analysis Computer)  ************** */

	case 'w':
		/* set data width on all boards*/
		printf("Enter Data Width for all boards: ");
		scanf("%ld", &newwidth );
		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			fadc_set_data_width( board_no, newwidth );
			fadc_set_mode(board_no, Current_mode);
		}	
		getkey();
		break;

	case 'u':
		/* set re-read width on all boards*/
		printf("Enter Re-read Width for all boards: ");
		scanf("%ld", &newwidth );
		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			fadc_set_reread_width( board_no, newwidth );
			fadc_set_mode(board_no, Current_mode);
		}
		getkey();
		break;

	case 'y':
		/* set HiLo width on all boards*/
		printf("Enter HiLo Width for all boards: ");
		scanf("%ld", &newwidth );
		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			fadc_set_hilo_width( board_no, newwidth );
			fadc_set_mode(board_no, Current_mode);
		}
		getkey();
		break;

	case 'd':
		/* set data offset lookback on all boards */
		printf("Enter data lookback for all boards: ");
		scanf("%ld", &newoffset );

		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);		
			for (chan = 0; chan <10; chan++){
				fadc_set_data_offset(board_no, chan, newoffset);
			}
			fadc_set_mode(board_no, Current_mode);			
		}
		getkey();
		break;
	
	case 'r':
		/* set re-read offset lookback on all boards */
		printf("Enter re-read lookback for all boards: ");
		scanf("%ld", &newoffset );

		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);		
			for (chan = 0; chan <10; chan++){
				fadc_set_reread_offset(board_no, chan, newoffset);
			}
			fadc_set_mode(board_no, Current_mode);			
		}
		getkey();
		break;
		
	case 'a':
		/* set area offset lookback on all boards */
		printf("Enter Area Lookback for all boards: ");
		scanf("%ld", &newoffset );

		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);		
			for (chan = 0; chan <10; chan++){
				fadc_set_area_offset(board_no, chan, newoffset);
			}
			fadc_set_mode(board_no, Current_mode);			
		}
		getkey();
		break;

	case 'b':
		/* set HiLo offset lookback on all boards */
		printf("Enter HiLo Lookback for all boards: ");
		scanf("%ld", &newoffset );

		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			fadc_set_hilo_offset(board_no, FADC_ALL, newoffset);
			fadc_set_mode(board_no, Current_mode);
		}
		getkey();
		break;

	case 'c':
		/* set CFC thresh level on all boards */
		printf("Enter CFD Thresh for all boards: ");
		scanf("%ld", &newlevel );

		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			for (chan = 0; chan <10; chan++){
				fadc_set_cfd_thresh(board_no, chan, newlevel);
			}
			fadc_set_mode(board_no, Current_mode);
		}
		getkey();
		break;
		
	case 'e':
		/* set Area Width on all boards */
		printf("Enter Area Width for all boards: ");
		scanf("%ld", &newwidth );

		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			for (chan = 0; chan <10; chan++){
				fadc_set_area_width(board_no, chan, newwidth);
			}
			fadc_set_mode(board_no, Current_mode);
		}
		getkey();
		break;		
	
	case 'm': 
		/* set fadc mode */
		/* there are 4 modes: FADC_MODE (zero suppress), QADC_MODE (rarely used),
		   FULL_MODE (all chans), and WORD_MODE (used when setting parameters) */ 
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
	    break;
		
	case 'z':
		/* set zero-suppress discrim level (set Area Discrim Level)*/
		printf("Enter new Zero-Suppress Threshold: ");
		scanf( "%lu", &newlevel );
		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode(board_no, WORD_MODE);
			fadc_set_area_discrim(board_no, FADC_ALL, newlevel);
			fadc_set_mode(board_no, Current_mode);
		}
		printf("Set zero-supress thresholds to %lu on all chans\n",
		       newlevel);
	    break;
		
	case 'p':
	    /* Clear scalers on all boards */
		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){
			fadc_set_mode( board_no, WORD_MODE );
		}
		fadc_multicast_clear_trigger_scaler();
		for (board_no = Boardnum7; board_no <= Boardnum9; board_no++){		
			fadc_set_mode( board_no, Current_mode );
		}	
		printf("Scalers cleared\n");
	    break;


    /* ***********************   Get Event Data   ******************* */
	
	case '1':
	    /* evt clr */
	    fadc_evt_clr();
	    printf("Evt clr command\n\n");    
	    break;
		
	case '2':
	    /* evt clr & read status & get CBLT event data */
	    fadc_evt_clr();
		printf("Event Clear command\n");
	
		/* wait for event to come in */
		tries = 0;
		while(fadc_got_event() == 0) {
			tries++;
			usleep(10);
			if (tries > 1000) {
				printf("Event timeout. Make sure the pulser is pulsing!\n");
				break;
			}
		}
		/* read event using CBLT transfer */
		first=32;
		last=32;
		if (tries<1000){	
			printf("DMA Read...\n");		
			ncbltwords = fadc_cblt();
			if (ncbltwords>=0)
				printf("Words read in cblt: %d\n",ncbltwords);
				
			if (ncbltwords > 0 && ncbltwords <= 128) {
				printf("Words read in cblt: %d\n", ncbltwords);
				for (i=0; i < ncbltwords; i++){
					printword(dmabuffer[i]);
					if ((i+1)%8==0) printf("\n");
				}			
			}
			
			if (ncbltwords > 0 && ncbltwords > 128) {
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
			}
			else if (ncbltwords == -1) 
				printf("DMA transfer failed!\n");
			else if (ncbltwords == -2)
				printf("DMA transfer timed out waiting for BERR*\n");
		}
		printf("\n\n");
		printf("Type '$' to dispay the entire CBLT buffer\n");
	    break;		
	
	case '3': 
		/* Read Event using CBLT */
		first=32;
		last=32;

		/* wait for event to come in */
		tries = 0;
		while(fadc_got_event() == 0) {
			tries++;
			usleep(10);
			if (tries > 1000) {
				printf("Event timeout. Make sure the pulser is pulsing\n");
				break;
			}
		}
		/* read event using CBLT transfer */
		if (tries<1000){	
			printf("DMA Read...\n");		
			ncbltwords = fadc_cblt();	      

			if (last > ncbltwords) last = 1;
		
			if (ncbltwords>=0)
				printf("Words read in cblt: %d\n",ncbltwords);
			else if (ncbltwords == -1) 
				printf("DMA transfer failed!\n");
			else if (ncbltwords == -2)
				printf("DMA transfer timed out waiting for BERR*\n");
			else 
				printf("STRANGE NCBLTWORDS! : %d\n", ncbltwords);	       
		
			if (ncbltwords > 128) {
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
			else if (ncbltwords >0 && ncbltwords <= 128) {
				for (i=0; i<ncbltwords; i++) {
					printword(dmabuffer[i]);
					if ((i+1)%8==0)printf("\n");
				}
				printf("\n\n");
			}
			else {
				printf("No data in buffer\n");
			}
		}
		printf("Type '$' to dispay the entire CBLT buffer\n");	    
	    break;
		
	case '4':
		/* Re-read Event using CBLT */		
	    fadc_request_reread();
	    printf("Sent reread command\n");

		/* wait for re-read event to be done */
		tries = 0;
		while(fadc_got_event() == 0) {
			tries++;
			usleep(10);
			if (tries > 1000) {
				printf("Re-read Event timeout\n");
				break;
			}
		}
		
		first=32;
		last=32;		
		/* read event using CBLT transfer */
		if (tries<1000){	
			printf("DMA Read...\n");		
			ncbltwords = fadc_cblt();
			if (ncbltwords>=0)
				printf("Words read in cblt: %d\n",ncbltwords);
				
			if (ncbltwords > 0 && ncbltwords <= 128) {
				printf("Words read in cblt: %d\n", ncbltwords);
				for (i=0; i < ncbltwords; i++){
					printword(dmabuffer[i]);
					if ((i+1)%8==0) printf("\n");
				}			
			}
			
			if (ncbltwords > 0 && ncbltwords > 128) {
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
			}
			else if (ncbltwords == -1) 
				printf("DMA transfer failed!\n");
			else if (ncbltwords == -2)
				printf("DMA transfer timed out waiting for BERR*\n");
		}
		printf("\n\n");
		printf("Type '$' to dispay the entire CBLT buffer\n");
	    break;
		
	case '5':
		/* Read Event using word mode */
	    read_event();
	    break;
		
	case '6':
	    /* Read chan scalers on all boards */
		for (board_no = Boardnum7; board_no<=Boardnum9; board_no++){
			fadc_set_mode( board_no, WORD_MODE );
			printf("Board No %d:\n", board_no);
			for (i=0; i<10; i++) {
				j = fadc_get_trigger_scaler(board_no, i);
				printf("scaler on ch %d = 0x%08lx, %lu\n", i, j, j);
			}
			fadc_set_mode(board_no, Current_mode);
		}
	    break;

    /* ******************   Other Stuff (may be deleted)  ***************** */
	
	case '$':
		/* print the entire CBLT buffer */
		printf("Entire CBLT buffer (%d) words:\n",ncbltwords);
		for (i=0; i<ncbltwords&&i<DMA_BUFSIZE; i++) {
		    printword(dmabuffer[i]);
		    if ((i+1)%8==0) printf("\n");
		}
		printf("\n");
	    break;

	case '%':
	    {
	    /* clear the CBLT buffer */
	    for (i=0; i<DMA_BUFSIZE; i++) {  
	      dmabuffer[i] = 0xBADBEEF0;
	    }
	    printf("CBLT buffer set to 0xBADBEEF0\n");
	    }
	    break;
	
	case 'h':
		/* Read Event Headers */
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

	case 'M':
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
		
	case 's':
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
	    break;
	    
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

		printf("Measuring dead time for %d events. please wait...\n", nevents);		

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
		
	case 'C':
	    crate_menu();
	    break;
		
	case '8':
	    fadc_request_pedestal();
	    printf("Sent pedestal command\n");
	    read_event();
	    break;
		
	case '0':
	    fadc_request_dump();
	    printf("Sent dump command\n");
	    read_event();
	    break;
		
    case 'x':
	    printf("\n exiting program \n");
	    quit = 1;
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
	printf("  W. set CFD width \n");
	printf("  R. set CFD RateFB \n");
	printf("  d. set CFD moDe \n");
	printf("  p. set Pedestal offset\n");
	printf("  P. set Pedestal width\n");
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
	case 'W':   
	    {
		unsigned long newval;
		printf("Enter new CFD WIDTH: ");
		scanf( "%lu", &newval );
		printf("Setting ALL channels on ALL boards to %lu...\n",
		       newval);
		fadc_set_cfd_width( FADC_ALL, FADC_ALL, newval );
		return;
	    }
	case 'R':   
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
		
	case 'm':
	    return;
	default:
	    printf("\n unused key '%c' \n", c);
	    break;
	    
	}
    }

}


void read_event() {    
    int nwords, i, tries, board_no;
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
		for (board_no = 7; board_no<=9; board_no++){
			nwords = fadc_data_available(board_no);
			printf("WORDS IN BUFFER: %d\n",nwords);
			if (board_no == 7)
				fadc_lptr = fadc_lptr7;
			if (board_no == 8)
				fadc_lptr = fadc_lptr8;
			if (board_no == 9)
				fadc_lptr = fadc_lptr9;	
			if (nwords > 0) {	    
				for (i=0, lptr=fadc_lptr; i<nwords; i++,lptr++){
					printword(*lptr);
					if ((i+1)%8==0) printf("\n");
				}
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
