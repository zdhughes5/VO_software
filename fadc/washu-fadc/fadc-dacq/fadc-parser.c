/*************************************************************
 * 10/11/2001 KPK							      
 *  
 * Example program to read and parse a raw FADCdata file
 * Karl Kosack
 *
 * TODO: support mult-board data
 *
 **************************************************************/

#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <unistd.h>
#include <assert.h>
#include <string.h>
#include "fadc-parser.h"

#define MASK_SYNC 0xffff0000    /* sync word from start header */
#define OFFS_SYNC 16            /* sync word offset */
#define MASK_BOARDNUM 0x0000ff00/* board number mask */
#define OFFS_BOARDNUM 8         /* board number offset */
#define MASK_WORDSPERCHAN 0xff  /* words per channel mask for start hdr*/
#define MASK_EVTNUM 0x03ffffff  /* event number from evt header */
#define MASK_HITPTN 0x3ff       /* hit pattern from hit header */
#define MASK_TRIGPTN 0x000ffc00 /* trig pattern from hit header */
#define OFFS_TRIGPTN 9          /* trig pattern offset */      
#define MASK_HILOPTN 0x3ff00000 /* hi/lo pattern from hit header */
#define OFFS_HILOPTN 20         /* hi/lo pattern offset */
#define MASK_CHAN 0xF0000000    /* chan number from area hdr */
#define OFFS_CHAN 28            /* offset to channel number */
#define MASK_AREA 0x7FFFF       /* area from area header */


int 
get_crate_event( FILE *fp, fadccrate_t *crate, char verbose ) {

    int i,ret;
    fadcdata_t data;

    crate->curbdnum = 0;

    while (crate->curbdnum < crate->numboards) {
    
	ret = get_event( fp, &data, verbose );
	if (ret==-2) {
	    return ret;
	}
	
	if (data.boardnum != crate->curbdnum) {
	    parseerror(&data,"Data found for board %d, expected %d (skipping...)\n",
		      data.boardnum, crate->curbdnum);
	}
	else {
	    memcpy( &(crate->board[crate->curbdnum]), &data, sizeof(data));
	    crate->curbdnum++;
	}

    }

    if (verbose)  printf("---------------------------------\n\n");
	
    return 0;

}

int
get_event( FILE *fp, fadcdata_t *evt, char verbose ) {

    int i,k;
    int nonsync = -1;
    static unsigned long buf[EVENT_BUF_SIZE];    
    unsigned long start_hdr = 0;
    unsigned long event_hdr;
    unsigned long hit_hdr;
    unsigned long area_hdr;
    unsigned long chan;
    unsigned long *lptr;
    unsigned long boardnum;
    int nhits;
    int ret;
    int size,j;
    char hit[10] = {0,0,0,0,0,0,0,0,0,0};

    /* Find the START HEADER  by looking for the 0xFADC sync word */
    do {
	fread( &start_hdr, sizeof(unsigned long), 1, fp );
	if (feof(fp)) {
	    printf("EOF!\n");
	    return -2;
	}
	nonsync++;
    }  while ( (start_hdr & 0xFFFF0000) != 0xFADC0000 );

    /* Extract the board number and ndatawords per chan */
    evt->boardnum   = (start_hdr & MASK_BOARDNUM    ) >> OFFS_BOARDNUM;
    evt->boardnum--;  /* hack for right now - boards are internally numbered from 1*/
    evt->ndatawords = (start_hdr & MASK_WORDSPERCHAN);
    evt->nsamp = evt->ndatawords * sizeof(unsigned long);

    if (verbose ) {
	printf("BOARD NUMBER: %u\n", evt->boardnum );
	printf("START HEADER: "); binary_print( start_hdr );
	printf("EVENT HEADER: "); binary_print( event_hdr );
	printf("HIT   HEADER: "); binary_print( hit_hdr );
	printf("DATA WORDS  : %u\n",evt->ndatawords); 
    }
   
    /* get the event and hit headers */
    fread( &event_hdr, sizeof(unsigned long), 1, fp );
    fread( &hit_hdr, sizeof(unsigned long), 1, fp );
    
    /* extract the event number */
    evt->eventnum = event_hdr & MASK_EVTNUM;
    if (verbose) printf( "EVENT NUMBER: %d\n", (int)evt->eventnum);
    if (nonsync) parseerror(evt,"%d words skipped before event\n", nonsync);

    /* extract the zero-supress patterns */
    evt->hitpattern  = (hit_hdr & MASK_HITPTN);
    evt->trigpattern = (hit_hdr & MASK_TRIGPTN) >> OFFS_TRIGPTN;
    evt->hilopattern = (hit_hdr & MASK_HILOPTN) >> OFFS_HILOPTN;

    /* sum the hit pattern bits to find out how much data to expect... */
    nhits = 0;
    for (i=0; i<10; i++) {
	if ( evt->hitpattern & (0x1 << i) ) nhits++;
    }
    if (verbose) printf( "%d channels were hit\n", nhits );

    /* get the data... */
    ret = fread( &buf, sizeof(unsigned long), (nhits)*(evt->ndatawords + 1), fp );
    if (ret < (nhits)*(evt->ndatawords +1) || feof(fp)) {
	printf("EOF\n\n");
	return -2;
    }
	
    /* loop over channels and grab the area headers and pulse */
    for (lptr=buf,i=0; i<nhits; i++) {
	
	area_hdr = *(lptr + (evt->ndatawords));
	chan = ( area_hdr & MASK_CHAN ) >> OFFS_CHAN;
	if (verbose) {
	    printf("AREA  HEADER: "); binary_print( area_hdr );
	    printf("CHANNEL %d: \n",(int)chan);
	}
	if ( chan >= 10 ) {
	    parseerror(evt,"AREA HEADER SAYS CHANNEL = %d! Skipping event.\n",(int)chan);
	    return -1;
	}
	hit[chan] = 1;
	memcpy( &(evt->pulse[chan][0]), 
		lptr, evt->ndatawords*sizeof(unsigned long));

	if (verbose==2) {
	    printf("DATA: \n");
	    for (k=0; k<evt->ndatawords*4; k++) {
		size = ((unsigned char)evt->pulse[chan][k])/255.0*80.0;
		for (j=0; j<size; j++) {
		    printf(" ");
		}
		printf("%d\n", evt->pulse[chan][k]);
	    }
	    printf("\n\n");

	    //	    printf("DATA: ");
	    //	    for (i=0; i<evt->ndatawords; i++) {
	    //		printf("%08lx ", lptr[i]);
	    //	    }
	    //	    printf("\n\n");
	}

	lptr += evt->ndatawords + 1;
    }

    /* clear the unhit channels */
    for (i=0; i<10; i++){
	if (hit[i] == 0) {
	    memset(  &(evt->pulse[i][0]), 0, 
		     evt->ndatawords*sizeof(unsigned long)); 
	}
    }

    if (verbose) printf("\n");


    return 0;

}

void
binary_print(unsigned long word) {

    unsigned long mask = 0x80000000;
    int i;
    
    printf("0x%08lx [ ", word);
    for (i=0; i<32; i++) {
        if ( (word & mask) != 0 ) printf("1") ;
        else printf("0");
        if ((i+1)%4 == 0) printf(" ");
        mask = mask >> 0x1;
    }
    printf("]\n");

}


fadccrate_t *
new_crate( int numboards ) {

    fadccrate_t *crate;
    int i;

    crate = malloc(sizeof(fadccrate_t));
    crate->numboards = numboards;
    crate->curbdnum = 0;
    
    crate->board = calloc( numboards, sizeof(fadcdata_t) );

}

void
delete_crate( fadccrate_t *crate ) {

    free( crate->board );
    free( crate );

}


void 
parseerror(fadcdata_t *evt,char *format, ...) {

    //    char *thetime;
    //    time_t lt;
    va_list ptr;

    //    lt = time( NULL );
    //    thetime = ctime( &lt );
    //    thetime[strlen(thetime)-1] = '\0';

    printf("*** ERROR [bd %d evt %u]: ",evt->boardnum, evt->eventnum);

    va_start( ptr, format );
    vprintf( format, ptr );
    va_end( ptr );

}
