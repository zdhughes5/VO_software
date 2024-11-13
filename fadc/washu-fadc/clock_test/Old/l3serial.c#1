/*
      l3serial.c                                                    
      9/19/05
                                                               
      Test routines for the L3 Serial board testing  
      
      Hardware notes:

      This version uses A32 bit addressing and D32 bit data transfers.

      VME memory-mapped I/O window set to 0xf0fb0000 - 0xf0ffffff.
      Window address set in /etc/modules.conf and initialized
      at bootup in vme program. 
      vmeUniverse program must be running in background for this program to run.

      L3 Serial board mapped to 0xf0ff0000 (A32)
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

#include "kb.h"


#ifdef NOTDEF
void reset_keypress(void);
void set_keypress(void);
struct termios stored_settings;
int getkey(void);
#endif


int main(void)
{
    unsigned long *clkbd_lptr;   /* pointer for D32 CLKBD transfers    */
    unsigned long *lptr;
    int c, quit;
    unsigned long status, j;
    unsigned long evt_no, t1_evt_type, t2_evt_type, trig_mask;

    fadc_init();
    fadc_verbose(1);    

    atexit(fadc_exit);

    clkbd_lptr = fadc_get_clk_lptr();
    evt_no = 0;
    t1_evt_type = 0;
    t2_evt_type = 0;
    trig_mask = 0;
    lptr = clkbd_lptr + 0x2000;   /* write event clear */
    *lptr = 0;
    lptr = clkbd_lptr + 0x2002;   /* write diagnostic mode */
    *lptr = 3;    /* software event type mode, L3_trig pulser input */
    
    /* Display the menu */

#ifdef NOTDEF
    set_keypress(); /* enable single-keypress */
#endif
    set_keypress(0);

    quit = 0;
    while(!quit){
	printf("_______________________________________________________\n");
	printf(" CLK/TRIG TEST Menu:                             \n");
	printf("     1.                              c. event Clear  \n");
	printf("     2. write event number           h. read Registers\n");
	printf("     3. write event type/trig mask   t. read Status Reg\n");
	printf("     4. incr Evt_type & Trig_mask    l. \n");
	printf("     5.                              s. software trig \n");
	printf("     6. 120nS TTL pulse out J21   \n");
	printf("     x. eXit                         COMMAND: ");
	fflush(stdout);
	
	//c = getkey();
	c = getchar();

	switch(c){
	case 'x':
	    printf("\n exiting program \n");
	    quit = 1;
	    break;

	case 't':  /* read clock board status */
	  lptr = clkbd_lptr + 0x2007;
	  status = *lptr;
	  printf( "\nStatus word: 0x%08lx \n", status );    
	  printf ("\tEvent Trigger  : %d \n", (int)(status & 0x1));	 
	  printf ("\tBoard Busy     : %d \n", (int)(status & 0x2)>>1);	
	  printf ("\tTelescope Busy : %d \n", (int)(status & 0x4)>>2);
	  break;
	  
	case 'c':  /* evt clr */
	    lptr = clkbd_lptr + 0x2000; /* SOFT_EVT_CLR; */
	    *lptr = 0;
	    printf("\n evt clr command issued\n");    
	    break;

	case 'l':
	    printf("\n not used\n");
	    break;
	    
	case 's':
	    lptr = clkbd_lptr + 0x2006;
	    *lptr = 0;
	    printf("\n issued Software trig\n");
	    break;
	    	    
	case '4':
	    t1_evt_type = t1_evt_type + 1;
	    if (t1_evt_type > 15)
	       t1_evt_type = 0;
	    t2_evt_type = t2_evt_type + 1;
	    if (t2_evt_type > 15)
	       t2_evt_type = 0;
	    trig_mask = trig_mask + 1;
	    if (trig_mask > 3)
	       trig_mask = 0;
	    printf("\n T1 Evt_type = %lx\n", t1_evt_type);
	    printf(" T2 Evt_type = %lx\n", t2_evt_type);
	    printf(" Trig_mask = %lx\n", trig_mask);
	    break;
	    
	case '5':
	    printf("\n not used\n");
	    break;
	    
	case '6':
	    lptr = clkbd_lptr + 0x2007;
	    *lptr = 0;
	    printf("\n issued 120nS TTL pulse out of J21 \n");
	    break;
	    
	case 'h': /* read headers */
            printf("\nRegisters: \n");
            lptr = clkbd_lptr + 0x2000; 
            j = *lptr;
            printf("Start header  : 0x%08lx\n", j);
            printf("\tSync Pattern   : 0x%lx \n", (j & 0xFFFF0000)>>16);
            printf("\tProg Board Num : %d \n", (int)(j & 0xFF00)>>8);
            printf("\tUnique ID      : %d \n", (int)(j & 0xFF));
            lptr = clkbd_lptr + 0x2001;
            j = *lptr;
            printf("\nT1 Event number = %08lx\n", j);
	    lptr = clkbd_lptr + 0x2002;
            j = *lptr;
            printf("T1 Evt_type & Trig_mask = %08lx\n", j);
	    lptr = clkbd_lptr + 0x2003;
            j = *lptr;
            printf("T2 Event number = %08lx\n", j);
	    lptr = clkbd_lptr + 0x2004;
            j = *lptr;
            printf("T2 Evt_type & Trig_mask = %08lx\n", j);
	    lptr = clkbd_lptr + 0x2007;
            j = *lptr;
            printf("\nStatus Reg = %lx\n", j);	        
            printf ("\tEvent Trigger : %d \n", (int)(j & 0x1));	 
            printf ("\tBoard Busy    : %d \n", (int)(j & 0x2)>>1);	
            printf ("\tTelescope Busy: %d \n", (int)(j & 0x4)>>2);
	    break;

	case '1': /*  */
	    printf("\n not used\n");
	    break;

	case '2': /* write event number */
	    printf("\n Wrote event number\n");
	    lptr = clkbd_lptr + 0x2004;
	    *lptr = evt_no;
	    break;

	case '3':
            lptr = clkbd_lptr + 0x2003;
	    *lptr = 0;
            printf("\n Wrote event type & trig mask\n"); 
	    break;
	    
	default:
	    printf("\n unused key\n");
	    break;
	}

    } /* end while */

    reset_keypress();

    return(0);
}


#ifdef NOTDEF
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
#endif
