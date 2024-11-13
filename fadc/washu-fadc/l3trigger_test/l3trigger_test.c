/*
      l3trigger_test.c                                                        
      11/29/07
                                                               
      Test routines for the l3trigger board testing  
      This is the red board with the Parallax devel board      

      Hardware notes:

      This version uses A32 bit addressing and D32 bit data transfers.

      VME memory-mapped I/O window set to 0xf0f00000 - 0xf0ffffff.
      Window address set in /etc/modules.conf and initialized
      at bootup in vme program. 
      vmeUniverse program must be running in background for this program to run.

      l3trigger board mapped to 0xf0fe0000 (A32) like FADC board slot 9

*/

#include <vme/vme_api.h>
#include <fadc.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <ctype.h>
#include <termios.h>
#include <fadc_lowlevel.h>          /* macros for fadc board   */

void reset_keypress(void);
void set_keypress(void);
int getkey(void);
struct termios stored_settings;


int main(void)
{
    register int i;
    unsigned long *magic_lptr;   /* pointer for D32 transfers    */
    unsigned long *lptr, *rdlptr, *wrlptr;
    int c, quit;
    unsigned long status, value, j;
    char errorflag;

    fadc_init();
    fadc_verbose(1);    

    atexit(fadc_exit);

    magic_lptr = fadc_get_magic_lptr();

    set_keypress(); /* enable single-keypress */

    quit = 0;
    while(!quit){
    	printf("_______________________________________________________\n");
	printf(" L3 trigger board test menu:                           \n");
	printf("     1. write 1 word  \n");
	printf("     2. read 1 word\n");
	printf("     3. read trig rates\n");
	printf("     x. eXit                       COMMAND: ");
	
	c = getkey();

	switch(c){
	case 'x':
	    printf("\n exiting program \n");
	    quit = 1;
	    break;

	case '2':  /* read 1 word */
	  lptr = magic_lptr + 0x2002;
	  status = *lptr;
	  printf( "\n Word = 0x%08lx \n", status );    
	  break;

    	case '3':  /* read trig rates */
          lptr = magic_lptr + 0x2004;
          status = *lptr;
          printf( "\nTelescope 1 rate = %d Hz\n", status & 0xffff);
          printf( "Telescope 2 rate = %d Hz \n", status >> 16);
	  lptr = magic_lptr + 0x2005;
          status = *lptr;
          printf( "Telescope 3 rate = %d Hz \n", status & 0xffff);
          printf( "Telescope 4 rate = %d Hz \n", status >> 16);

          break;


	case '1':  /* write 1 word */
	    lptr = magic_lptr + 0x2003; 
	    *lptr = 0xbeefcafe;
	    printf("\n Wrote 0xbeefcafe to Address 0x2003\n\n");    
	    break;

	case '4':
	    lptr = magic_lptr + 0x2006;
	    *lptr = 0;
	    printf("Sent software crate trig\n");
	    break;
	    
	case '5':
	    lptr = magic_lptr + 0x2005;
	    printf("Toggling I/O register bits...\n");
	    for (i=0; i<100; i++){
	        *lptr = 7;
		for (j=0; j<10000; j++);
	        *lptr = 0;
		for (j=0; j<10000; j++);
	    }
            printf("Done\n");
	    break;
	    
	case '7':
	    for(i=0; i<100; i++) {
		lptr = magic_lptr + SOFT_EVT_CLR;
		*lptr = 0;
		lptr = magic_lptr + 0x2002;   /* crate clear */
		*lptr = 0;
		for (j=0; j<960000; j++);
		value = *(magic_lptr + 0x2004);
		printf("elapsed: 0x%08lx (%f sec)\n", value, value/32.0e6); 
	    }
	    break;
	    
	default:
	    printf("\n unused key\n");
	    break;
	}

    } /* end while */

    
    reset_keypress();

    return(0);
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
