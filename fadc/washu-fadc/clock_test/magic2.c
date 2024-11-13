/*
      magic_test.c                                                        
      11/29/04
                                                               
      Test routines for the MAGIC board testing  
      
      Hardware notes:

      This version uses A32 bit addressing and D32 bit data transfers.

      VME memory-mapped I/O window set to 0xf0fb0000 - 0xf0ffffff.
      Window address set in /etc/modules.conf and initialized
      at bootup in vme program. 
      vmeUniverse program must be running in background for this program to run.

      Magic board mapped to 0xf0ff0000 (A32)

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

void print_clk_headers(unsigned long*);
int test_register(unsigned long *wrlptr, unsigned long *rdlptr, int size,
		  unsigned long rdmask, int rdoffset );

void reset_keypress(void);
void set_keypress(void);
int getkey(void);
struct termios stored_settings;


int main(void)
{
    register int i;
    unsigned long *clkbd_lptr;   /* pointer for D32 CLKBD transfers    */


    unsigned long *lptr, *rdlptr, *wrlptr;
    int c, quit;
    unsigned long status, value, j;
    char errorflag;

    fadc_init();
    fadc_verbose(1);    

    atexit(fadc_exit);

    clkbd_lptr = fadc_get_clk_lptr();

    lptr = clkbd_lptr + 0x2000;   /* write event clear */
    *lptr = 0;
    lptr = clkbd_lptr + 0x2002;   /* write crate clear */
    *lptr = 0;
    
    /* Display the menu */

    set_keypress(); /* enable single-keypress */

    quit = 0;
    while(!quit){
	printf("_______________________________________________________\n");
	printf(" CLK/TRIG TEST Menu:                             \n");
	printf("     1. test writable registers    c. event Clear  \n");
	printf("     2. test scalers               h. print Headers\n");
	printf("     3. watch elapsed time         t. Trigger status\n");
	printf("     4. software trig              l. crate cLear\n");
	printf("     5. toggle i/o register        s. clear scalers\n");
	printf("     6. 25nS pulse out J20   \n");
	printf("     x. eXit                       COMMAND: ");
	
	c = getkey();

	switch(c){
	case 'x':
	    printf("\n exiting program \n");
	    quit = 1;
	    break;

	case 't':  /* read clock board status */
	  lptr = clkbd_lptr + 0x2007;
	  status = *lptr;
	  printf( "\nStatus word: 0x%08lx \n", status );    
	  printf ("Event Trigger  : %d \n", (int)(status & 0x1));	 
	  printf ("Magic bd Busy     : %d \n", (int)(status & 0x2)>>1);	
	  break;
	  
	case 'c':  /* evt clr */
	    lptr = clkbd_lptr + 0x2000; /* SOFT_EVT_CLR; */
	    *lptr = 0;
	    lptr = clkbd_lptr + 0x2002;  /* crate clear */
	    *lptr = 0;	    
	    printf("evt clr command issued\n\n");    
	    break;

	case 'l':
	    lptr = clkbd_lptr + 0x2002;
	    *lptr = 0;
	    printf("Sent CRATE CLEAR\n");
	    break;
	    
	case 's':
	    lptr = clkbd_lptr + 0x2004;
	    *lptr = 0;
	    printf("Sent CLEAR SCALERS\n");
	    break;
	    	    
	case '4':
	    lptr = clkbd_lptr + 0x2006;
	    *lptr = 0;
	    printf("Sent software crate trig\n");
	    break;
	    
	case '5':
	    lptr = clkbd_lptr + 0x2005;
	    printf("Toggling I/O register bits...\n");
	    for (i=0; i<100; i++){
	        *lptr = 7;
		for (j=0; j<10000; j++);
	        *lptr = 0;
		for (j=0; j<10000; j++);
	    }
            printf("Done\n");
	    break;
	    
	case '6':
	    lptr = clkbd_lptr + 0x2007;
	    *lptr = 0;
	    printf("25nS pulse out of J20 (bottom LEMO)\n");
	    break;
	    
	case 'h': /* Check headers */
	    print_clk_headers(clkbd_lptr);
	    break;

	case '1': /* test writable registers */

	    printf("WRITABLE REGISTER TEST:\n");
	    printf(" This test writes a 0 then a 1 to each bit of a register\n");
	    printf(" and reads back the result.  If the result doesn't match\n");
	    printf(" what was written, an error message will appear.\n\n");
	    
	    printf("Checking board number register (8 bits)...");
	    wrlptr = clkbd_lptr + 0x2001;
	    rdlptr = clkbd_lptr + 0x2000;
	    test_register( wrlptr, rdlptr, 8, 0xff00, 8 );

	    printf("Checking trigger code register (16 bits)...");
	    wrlptr = clkbd_lptr + 0x2003;
	    rdlptr = clkbd_lptr + 0x2002;
	    test_register( wrlptr, rdlptr, 16, 0xFFFF, 0 );

	    break;

	case '2': /* test scalers */

	    printf("\nChecking if scalers can be cleared...\n");
	    printf("The elapsed time does not update unless triggers\n");
	    printf("are coming in. To verify it works, put a >10 Hz \n");
	    printf("trigger signal into the board\n\n");

	    /* clear scalers */
	    wrlptr = clkbd_lptr + 0x2004;
	    *wrlptr = 0;

	    /* Test if GPS second mark is set to 0 */
	    printf("\tGPS second mark: ");
	    value = *(clkbd_lptr + 0x2003);
	    if (value != 0) 
		printf("DID NOT CLEAR (0x%08lx)\n",value);
	    else  printf("PASSED\n");

	    /* clear event, so elapsed time can be read at next trigger*/
	    lptr = clkbd_lptr + SOFT_EVT_CLR;
	    *lptr = 0;
	    lptr = clkbd_lptr + 0x2002;   /* crate clear */
	    *lptr = 0;
	    /* Test if elapse time is near 0 (it's free running, so 
	       it will never be exactly 0. */
	    errorflag=0;
	    for (i=0; i<5;i++) {
		printf("\tElapsed time: ");
		*wrlptr = 0;
		*lptr = 0;
		value = *(clkbd_lptr + 0x2004);
		printf("%f sec ", value/23.0e9);
		if ((value/32.0e9) > 0.001) {
		    printf("FAILED. Current value=0x%08lx\n", value);
		    errorflag=1;
		    usleep(50);
		}
		else { 
		    printf("PASSED on trial %d\n",i+1) ;
		    break;
		}
	    }	    
	    if(errorflag) {
		printf("\t   * Try increasing the trigger frequency. It\n");
		printf("\t   * may be that the trigger is not happening\n");
		printf("\t   * soon enough after the event clear\n\n");
	    }

	    /* Check live time scaler */
	    printf("\tLive time: ");
	    value = *(clkbd_lptr + 0x2005);
	    if (value != 0) 
		printf("FAILED TO CLEAR (0x%08lx)\n",value);
	    else  printf("PASSED\n");
	    	    
	    break;

	case '3':
	    for(i=0; i<100; i++) {
		lptr = clkbd_lptr + SOFT_EVT_CLR;
		*lptr = 0;
		lptr = clkbd_lptr + 0x2002;   /* crate clear */
		*lptr = 0;
		for (j=0; j<960000; j++);
		value = *(clkbd_lptr + 0x2004);
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

    
int 
test_register(unsigned long *wrlptr, unsigned long *rdlptr, int size,
	      unsigned long rdmask, int rdoffset ) {
    
    int i;
    unsigned long rdvalue, wrvalue;
    char errorflag;

    errorflag=0;
    for (i=0; i<size; i++) {

	/* Check for stuck bits: */
	wrvalue = 0x0;
	*wrlptr = wrvalue;
	
	rdvalue= *rdlptr;
	rdvalue = (rdvalue &rdmask) >> rdoffset;

	if (rdvalue != 0) {
	    printf("\t** Possible stuck bit! Read: 0x%08lx, should be 0x0\n", rdvalue);
	}

	/* write a 1 to this bit */
	wrvalue = 0x1 << i;
	*wrlptr = wrvalue;

	rdvalue = *rdlptr;
	rdvalue = (rdvalue & rdmask )>>rdoffset; 
	if (rdvalue != wrvalue) {
	    printf("\n\t** Problem with bit %d (should be 1): rd 0x%08lx !=",
		   i, rdvalue);
	    printf( " wr 0x%08lx\n", wrvalue); 
	    errorflag=1;
	}
	else {
	    //	    printf("%d ", i);
	}




    }
    if (!errorflag) printf("PASSED\n");
    else printf("FAILED!   **********\n");

    return errorflag;

}


void
print_clk_headers(unsigned long *clkbd_lptr) {

    unsigned long rdvalue;
    unsigned long *lptr;

    /* Print the headers...*/ 
    printf("\nHEADERS: \n");

    lptr = clkbd_lptr+0x2000; 
    rdvalue=*lptr;
    printf("start header  : 0x%08lx\n", rdvalue);
    printf("\tSYNC PATTERN   : 0x%lx \n", (rdvalue & 0xFFFF0000)>>16);
    printf("\tBOARD NUM      : %d \n", (int)(rdvalue & 0xFF00)>>8);
    printf("\tUNIQUE ID      : %d \n", (int)(rdvalue & 0xFF));

    lptr = clkbd_lptr+0x2001; 	    
    rdvalue=*lptr;
    printf("event number  : 0x%08lx (%ld)\n", rdvalue,rdvalue);

    lptr = clkbd_lptr+0x2002;	    
    rdvalue=*lptr;
    /* the first 16 bits are the trigger code, and bits 16-31 are 
       the rest of the event number (we'll call it the event code */
    printf("event code    : 0x%04lx\n", rdvalue>>16);
    printf("trigger header: 0x%04lx\n", rdvalue&0x0000FFFF);

    lptr = clkbd_lptr+0x2003;	    
    rdvalue=*lptr;
    printf("I/O input register  : 0x%08lx (%lu)\n", rdvalue,rdvalue);
    lptr = clkbd_lptr+0x2004;	    
    rdvalue=*lptr;
    printf("elapsed time  : 0x%08lx (%lu)\n", rdvalue,rdvalue);
    lptr = clkbd_lptr+0x2005;	    
    rdvalue=*lptr;
    printf("event counter    : 0x%08lx (%lu)\n", rdvalue,rdvalue);
    lptr = clkbd_lptr+0x2007;	    
    rdvalue=*lptr;
    printf("status header : 0x%08lx\n", rdvalue);
    printf ("\tTRIGGER       : %d \n", (int)(rdvalue & 0x1));	 
    printf ("\tCRATE BUSY    : %d \n", (int)(rdvalue & 0x2)>>1);	
//    printf ("\tTELESCOPE BUSY: %d \n", (int)(rdvalue & 0x4)>>2);

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
