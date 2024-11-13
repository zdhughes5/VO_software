 /* libfadc.c - C library for controlling FADC boards 
 *
 * Lowlevel code was taken from d4.c by Paul Dowkontt.
 * Library created by Karl Kosack.
 * Much modified by Marty Olevitch, Winter '00-'01
 *
 * Converted to use the VMIC linux drivers for the Tundra Universe II 
 * PCI to VME bridge by Karl Kosack, Sept 2001
 *
 * Modified update_chan_offset() to work with Board ID < 4, Jan 4, 2007
 */

#include <stdio.h>
#include <stdarg.h>
#include <errno.h>
#include <unistd.h>
#include <sys/time.h> 
#include <math.h>


#include <vme/vme.h>
#include <vme/vme_api.h>

#include "fadc_lowlevel.h"	/* internal macros for fadc board */
#include "fadc.h"	        /* application interface */

/*********************************************************/
/* DEFAULT PARAMETER VALUES. */
/*********************************************************/

/* Initializes some elements of the Board struct. Establishes the number of
 * boards in the bus. However, any number of these boards may be "ignored"
 * by using the fadc_ignore_board() routine. */

#define MAXBOARDS 13
#define NO_BOARD 0xFFFFFFFF
struct BoardSettings Board[MAXBOARDS];
unsigned long Boardaddress[MAXBOARDS];

#define CLKBD_OFFSET	0xf0ff0000
#define MAGIC_OFFSET	0xf0fe0000
#define L3SERIAL_OFFSET	0xf0fd0000

enum {
    EVT_DONE_LOOP_COUNT = 1000, 
    CHAN_PER_BOARD = 10,
};




/*********************************************************/
/* GLOBAL VARIABLES */
/*********************************************************/

static unsigned long Area_discrim = AREA_DISCRIM;
static unsigned long Area_offset = AREA_OFFSET;
static unsigned long Area_width = AREA_WIDTH;
static unsigned long Cfd_wuthresh = CFD_WUTHRESH;
static unsigned long Cfd_wuoffs = CFD_WUOFFS;
static unsigned long Cfd_del = CFD_DEL;
static unsigned long Data_offset = DATA_OFFSET;
static unsigned long Data_width = DATA_WIDTH;

static unsigned long *clk_lptr;		/* pointer for clock board */
static unsigned long *magic_lptr;	/* pointer for magic board */
static unsigned long *l3serial_lptr;	/* pointer for l3serial board */
static unsigned long *first_board_lptr; /* pointer to first board in CBLT*/
static unsigned long *last_board_lptr;  /* pointer to first board in CBLT*/
static unsigned long *WinBase;		/* Pointer to the I/O window block */
vme_bus_handle_t      bus_handle;
vme_master_handle_t   window_handle;
vme_interrupt_handle_t interrupt_handle;

#define VME_BASE_ADDRESS 0xF0E00000
#define MASTER_WINDOW_SIZE 0x200000

static char Verbose = 1;
static char Initialized = 0;

unsigned long *Cblt_buffer = NULL;
vme_dma_handle_t dma_handle;
int Cblt_buffer_size=0;
int Cblt_berr_occurred=0;
int Clockboard_id=0;

int Nap_iters_per_usec=1000;

/*********************************************************/
/* PROTOTYPES FOR NON-PUBLIC FUNCTIONS: */
/*********************************************************/

static void update_all_settings(int bd);
static void set_area_offset(int b, int chan, unsigned long val);
static void set_area_discrim(int b, int chan, unsigned long val);
static void set_data_offset(int b, int chan, unsigned long val);
static void set_hilo_offset(int b, int chan, unsigned long val);
static void set_reread_offset(int b, int chan, unsigned long val);
static void set_pedestal_offset(int b, int chan, unsigned long val);
static void set_area_width(int b, int chan, unsigned long val);
static void set_cfd_delay( int bd, int ch, unsigned long val );
static void set_cfd_width( int bd, int ch, unsigned long val );
static void set_cfd_thresh( int bd, int ch, unsigned long val );
static void set_cfd_ratefb( int bd, int ch, unsigned long val );
static void set_cfd_type( int bd, int ch, unsigned long val );
static void set_cfd_wuthresh( int bd, int ch, unsigned long val );
static void set_cfd_wuoffs( int bd, int ch, unsigned long val );
static void set_cfd_mode( int bd, int ch, unsigned long val );
static void update_wu_cfds( int bd, int chan );
static void update_uu_cfds( int bd, int chan );
static void update_chan_offsets( int bd, int chan );
static void update_chan_disc( int bd, int chan );
void update_board_parameters( int bd );

void set_value_helper(int boardnum, int chan, unsigned long val, 
		      void (*setfunc)(int,int,unsigned long));

void install_interrupt_handler(void);
void remove_interrupt_handler(void);
static void sig_handler( int sig, siginfo_t *data, void *extra );

void info( char *format, ... );
void nap(int microsecs);
void napcalibrate();

/*********************************************************/
/* PUBLIC FUNCTIONS:
   /*********************************************************/

/**
 * for low-level debugging purposes only! (don't use unless you need it)
 */
vme_bus_handle_t fadc_get_bus_handle() {
    return bus_handle;
}

vme_dma_handle_t fadc_get_dma_handle() {
    return dma_handle;
}

void fadc_ignore_board(int boardnum) {

    info( "fadc_ignore_board is deprecated\n");

}

/**
 * Set FADC operating mode  
 * @param mode - either FADC_MODE, FULL_MODE, or QADC_MODE 
 */
void
fadc_set_mode(int boardnum, int mode) {

    int i;
  
    if (boardnum == FADC_ALL) {
	for (i=0; i<MAXBOARDS; i++) {
	    if (Board[i].active) {
		wr_mode( Board[i].lptr, mode );
		printf("Board %d Mode being set to %d\n", i,mode);
	    }
	}
    }
    else {
	wr_mode( Board[boardnum].lptr, mode );
	printf("Board %d Mode being set to %d\n", boardnum, mode);
    }

}

/**
 * Set initial values for data width, area offset, cfd parameters for
 * all channels and all boards.  This should be called before fadc_init()
 */
void
fadc_set_initial_values(unsigned long _data_width, unsigned long _area_width,
			unsigned long _area_offset, unsigned long _area_discrim)
{
    Data_width = _data_width;
    Area_width = _area_width;
    Area_offset = _area_offset;
    Area_discrim = _area_discrim;
}

/** 
 * Set board parameters to default values. Set up the vme
 * connection, memory pointers, initialize the boards in this bus. 
 * \returns if all went well, else -1 if the VME init failed. 
 */
int
fadc_init(void)
{
    int bd;
    int ch;
    FILE *fp;
    char oldverbose;
    int nboards=0;
    int nbadaddress=0;
    size_t window_size=MASTER_WINDOW_SIZE;
    int vown;
    unsigned long *lptr, value;
    

    napcalibrate();

    /* Board mapping Boards are now mapped according to Scott Wakely's
     * scheme - by slot, not by board id. (though it would be easy to
     * switch back to the old way) */
    
    for (bd=0; bd<MAXBOARDS; bd++) 
	Boardaddress[bd] = NO_BOARD;

    Boardaddress[0] = 0xf0f00000; // slot 0
    Boardaddress[1] = 0xf0f10000; // slot 1
    Boardaddress[2] = 0xf0f20000; // slot 2
    Boardaddress[3] = 0xf0f30000; // slot 3
    Boardaddress[4] = 0xf0f40000; // slot 4
    Boardaddress[5] = 0xf0f50000; // slot 5
    Boardaddress[6] = 0xf0f60000; // slot 6
    Boardaddress[7] = 0xf0f70000; // slot 7
    Boardaddress[8] = 0xf0f80000; // slot 8
    Boardaddress[9] = 0xf0f90000; // slot 9
    Boardaddress[10]= 0xf0fa0000; // slot 10
    Boardaddress[11]= 0xf0fb0000; // slot 11
    Boardaddress[12]= 0xf0fc0000; // slot 12

/*     Boardaddress[0] = 0xf0fd0000; */
/*     Boardaddress[1] = 0xf0fc0000; */
/*     Boardaddress[2] = 0xf0fb0000; */
/*     Boardaddress[3] = 0xf0fa0000; */
/*     Boardaddress[4] = 0xf0f90000; */
/*     Boardaddress[5] = 0xf0f80000; */
/*     Boardaddress[6] = 0xf0f70000; */
/*     Boardaddress[7] = 0xf0f60000; */
/*     Boardaddress[8] = 0xf0f50000; */
/*     Boardaddress[9] = 0xf0f40000; */
/*     Boardaddress[10]= 0xf0f30000; */
/*     Boardaddress[11]= 0xf0f20000; */
/*     Boardaddress[12]= 0xf0f10000; */
/*     Boardaddress[13]= 0xf0f00000; */
/*     Boardaddress[14]= 0xf0ef0000; */
/*     Boardaddress[15]= 0xf0ee0000; */
/*     Boardaddress[16]= 0xf0ed0000; */
/*     Boardaddress[17]= 0xf0ec0000; */
/*     Boardaddress[18]= 0xf0eb0000; */
/*     Boardaddress[19]= 0xf0ea0000; */
/*     Boardaddress[20]= 0xf0e90000; */
/*     Boardaddress[21]= 0xf0e80000; */
/*     Boardaddress[22]= 0xf0e70000; */
/*     Boardaddress[23]= 0xf0e60000; */
/*     Boardaddress[24]= 0xf0e50000; */
/*     Boardaddress[25]= 0xf0e40000; */
/*     Boardaddress[26]= 0xf0e30000; */
/*     Boardaddress[27]= 0xf0e20000; */


    /* SET UP THE VME INTERFACE */


    if(0 > vme_init(&bus_handle)) {
	perror("Error initializing the VMEbus");
	exit(1);
    }


    /* NOTE : don't use vme_acquire_bus_ownership()! It seems to break
       the CBLT transfers when used.  Not sure why. */

/*     vme_get_bus_ownership(bus_handle, &vown); */
/*     if (vown == 1) { */
/* 	info("VMEBus is currently in use by another application\n"); */
/* 	info("If you are sure no other application is using it,\n"); */
/* 	info("type 'vme_release_bus' and try again.\n"); */
/* 	vme_term(bus_handle); */
/* 	exit(1); */
/*     } */
	
/*     vme_acquire_bus_ownership(bus_handle); */

    
    if(0 > vme_master_window_create(bus_handle, &window_handle,
				    VME_BASE_ADDRESS, VME_A32SD, 
				    window_size,
				    VME_CTL_MAX_DW_32, NULL)) {
	perror("Error creating the window");
	vme_term(bus_handle);
	exit(1);
    }
    
    WinBase = (unsigned long*)vme_master_window_map(bus_handle,
						    window_handle, 0);
    if(WinBase == NULL) {
	perror("Error mapping the window");
	vme_master_window_release(bus_handle, window_handle);
	vme_term(bus_handle);
	exit(1);
    }
    
    info( "WinBase = 0x%08lx \n", WinBase );

    clk_lptr =      &WinBase[(CLKBD_OFFSET    - VME_BASE_ADDRESS)>>2];
    magic_lptr =    &WinBase[(MAGIC_OFFSET    - VME_BASE_ADDRESS)>>2];
    l3serial_lptr = &WinBase[(L3SERIAL_OFFSET - VME_BASE_ADDRESS)>>2];

    info("addr for CLK bd = 0x%08lx [+0x%04lx], vme addr: 0x%08lx\n", 
	 clk_lptr, (unsigned long)clk_lptr - (unsigned long)WinBase, 
	 ((unsigned long)(clk_lptr)-(unsigned long)(WinBase))
	 + VME_BASE_ADDRESS );

    lptr = clk_lptr + 0x2000;
    value = *lptr;
    Clockboard_id = (int)(value & 0xFF);

    info("Clock/Trigger board ID: %d\n",Clockboard_id);

    /* set defaults */
    for(bd=0; bd<MAXBOARDS; bd++) {
	Board[bd].active = 0;
	Board[bd].data_width		= Data_width;
	Board[bd].hilo_width		= 16;
	Board[bd].reread_width		= 16;
	Board[bd].ped_width		= 16;
	Board[bd].revision              = 0;

	if (Boardaddress[bd] != NO_BOARD) {
	    Board[bd].lptr = &WinBase[(Boardaddress[bd]-VME_BASE_ADDRESS)>>2];
	
	    for(ch=0; ch<10; ch++){
		Board[bd].chan[ch].area_width	= Area_width;
		Board[bd].chan[ch].area_offs	= Area_offset;
		Board[bd].chan[ch].area_discrim	= Area_discrim;
		Board[bd].chan[ch].data_offs	= Data_offset;
		Board[bd].chan[ch].area_offs	= 128;
		Board[bd].chan[ch].hilo_offs	= 128;
		Board[bd].chan[ch].ped_offs	= 128;
		Board[bd].chan[ch].reread_offs	= 128;
		Board[bd].chan[ch].cfd_width    = CFD_WIDTH;
		Board[bd].chan[ch].cfd_thresh   = CFD_THRESH;
		Board[bd].chan[ch].cfd_ratefb   = CFD_RATEFB;
		Board[bd].chan[ch].cfd_mode     = CFD_MODE;
		Board[bd].chan[ch].cfd_wuthresh	= Cfd_wuthresh;
		Board[bd].chan[ch].cfd_wuoffs	= Cfd_wuoffs;
		Board[bd].chan[ch].cfd_del	= Cfd_del;
		Board[bd].chan[ch].cfd_inh	= 0;
		Board[bd].chan[ch].ch_disable	= 0;
		Board[bd].chan[ch].cfd_type	= CFD_UTAH;
		Board[bd].chan[ch].revision	= 0;
	    }
	}
    }

    /* Detect which boards are there */
    for (bd=0; bd<MAXBOARDS; bd++) {

	if (Boardaddress[bd] != NO_BOARD) {

	    if (fadc_detect_board(bd)) {

		unsigned long id;
		id = fadc_get_serial_number(bd);

		Board[bd].active = 1;
		nboards++;
		info( "SLOT %2d: board %3d  (addr 0x%08lx)\n", bd, id,
		      Boardaddress[bd] );
	    }
	    else {
		info( "SLOT %2d:  [empty]   (addr 0x%08lx)\n", bd,
		      Boardaddress[bd] );
	    }

	}
	else {
	    info("No board address mapped for slot %d\n", bd);
	}

    }


    /* 
     * initialize FADC boards
     * TODO: combine this with update function...
     */
    for(bd=0; bd<MAXBOARDS; bd++) {
	if (Board[bd].active) {

	    info( "Initializing board %d\n", fadc_get_serial_number(bd));

	    fadc_set_mode(bd, WORD_MODE);
	    
	    /* initialize registers in DP gate array: event number, board
	     * number, data width, mode */
 	    if (Verbose>1) info("\tInit data processing gate array\n");
	    wr_evt_no(Board[bd].lptr, 0);
	    wr_bd_no(Board[bd].lptr, bd); 

	    update_board_parameters(bd);

	    /* initialize regisers in CH gate array: dacs, ch offsets, area
	     * discrim, clr scaler */
 	    if (Verbose>1) info("\tInit channel gate arrays\n"); 
	    oldverbose = Verbose;
	    fadc_verbose(0);
	    for (ch = 0; ch < CHAN_PER_BOARD; ch++){
		update_chan_offsets( bd, ch );
		nap(100);
		update_chan_disc( bd, ch );
		nap(100);
		update_uu_cfds( bd, ch );
		nap(100);
	    }
	    fadc_verbose(oldverbose);

 	    if(Verbose>1) info("\tGoing into FADC_MODE...\n"); 
	    fadc_set_mode( bd, FADC_MODE );
	    //	    nap(100);

	}
    }

    info( "%d boards were initialized.\n", nboards);
    if (nbadaddress==1) 
	info( "%d board seems to have the wrong serial number\n",nbadaddress);
    else if (nbadaddress>1)
	info( "%d boards seem to have the wrong serial number\n",nbadaddress);
    
    /* Reset the triggering */
    fadc_evt_clr();

    /* Set the initialized flag */
    Initialized = 1;

    return 0;

}

/**
 * \returns 1 if the board was deteted during fadc_init and 0 otherwise.
 */
int 
fadc_is_board_present( int boardnum ) {
    
    if (Board[boardnum].active == 1 ) return 1;
    else return 0;

}

/**
 * Attempts to see if the specified board is installed.
 */
int 
fadc_detect_board( int boardnum ) {

    unsigned long *lptr;
    unsigned long value;

    /* write a pattern to the event number register... */

    lptr = Board[boardnum].lptr + WR_EVT_NO; 
    *lptr = 0x0; 

    /* read back the value and compare */

    lptr = Board[boardnum].lptr + RD_EVT_HDR;
    value = *lptr;

    if ((value & 0x0FFFFFFF) == 0x0) 
	return 1;
    else 
	return 0;

}


/**
 * Return the number of boards we think is in the bus.  Note that not
 * all the boards have to be "active". Some of them may be ignored. 
 */
int
fadc_num_boards(void)
{
    return MAXBOARDS;
}


/**
 * Clean up memory and release VME window. 
 */
void
fadc_exit(void)
{


    if ( Cblt_buffer != NULL) 
	remove_interrupt_handler();


    if(0 > vme_master_window_unmap(bus_handle, window_handle)){
	perror("Error unmapping the window");
	vme_master_window_release(bus_handle, window_handle);
	vme_term(bus_handle);
	exit(1);
    }

    if(0 > vme_master_window_release(bus_handle, window_handle)) {
	perror("Error releasing the window");
	vme_term(bus_handle);
	exit(1);
    }

    if (Cblt_buffer != NULL) {
	if(0 > vme_dma_buffer_unmap(bus_handle, dma_handle)) {
	    perror("Error unmapping the buffer");
	    vme_dma_buffer_release(bus_handle, dma_handle);
	    vme_term(bus_handle);
	    exit(1);
	}
	
	if(0 > vme_dma_buffer_release(bus_handle, dma_handle)) {
	    perror("Error releasing the buffer");
	    vme_term(bus_handle);
	    exit(1);
	}
    }

/*     vme_release_bus_ownership(bus_handle); */
    
    if(0 > vme_term(bus_handle)) {
	perror("Error terminating");
	exit(1);
    }
    




    info("VME interface closed.\n");

}

/**
 * If any board has data available and isn't busy, return a positive
 * value, otherwise return 0. 
 */
int
fadc_got_event(void) {

    unsigned long *lptr;
    unsigned long status;
    int i;

    lptr = clk_lptr + RD_CLK_STATUS;

    for (i=0; i<EVT_DONE_LOOP_COUNT; i++) {

	status = *lptr;
	
	switch (status & 0x3) {

	  case 0x0: /* no event */
	      return 0;
	      break;
	      
	  case 0x1: /* got event, and not busy */
	      return 1;
	      break;
	      
	  case 0x2: /* Busy, but no event */
	      continue;
	      break;
	      
	  case 0x3: /* Got event, and still busy */
	      continue;
	      break;

	}
    }

    /* if we got here, then we timed out reading the status. */
    info("Timed out waiting for busy flag to go down\n");
    return 0;

}

/**
 * See if a particular board has data available.  Should be called
 * after a successful fadc_got_event().  
 *
 * @return number of words waiting in buffer.  
 */
unsigned long
fadc_data_available(int boardnum)
{
    unsigned long nwords = 0;
    unsigned long *lptr;

    if (Board[boardnum].active) {
	lptr = (Board[boardnum].lptr) + RD_STATUS_HDR;
	/* Value is masked because temperature-high bit is stuck on! */
	nwords = *lptr & 0x0fff;
    }
    return nwords;
}

/**
 * Returns the area discriminator threshold for the specified board
 * and channel.
 */
unsigned long
fadc_get_area_discrim(int boardnum, int chan)
{
    return Board[boardnum].chan[chan].area_discrim;
}

/**
 * Disable single channel chan on board boardnum, so that it returns no data. 
 * @return 0 on success, -1 if values are out of range. 
 */
int
fadc_disable_channel( int boardnum, int chan ) {

    if (Board[boardnum].active && chan >=0 && chan<10) {
	Board[boardnum].chan[chan].ch_disable = 1;
	update_chan_disc( boardnum, chan );
	info("disabled channel %d on board %d\n", chan, boardnum);
	return 0;
    }
    else {
	return -1;
    }

}

/**
 * Enable single channel chan on board boardnum.
 * @return 0 on success, -1 if values are out of range. 
 */
int
fadc_enable_channel( int boardnum, int chan ) {

    if (Board[boardnum].active && chan >=0 && chan<10) {
	Board[boardnum].chan[chan].ch_disable = 0;
	update_chan_disc( boardnum, chan );

	info( "disabled channel %d on board %d\n",  chan, boardnum );

	return 0;
    }
    else {
	return -1;
    }

}

/**
 * Returns status of channel (0 = disabled, 1=enabled, -1=out of range)
 */
int
fadc_is_channel_disabled( int boardnum, int chan ) {

    if (Board[boardnum].active && chan >=0 && chan<10)
	return (Board[boardnum].chan[chan].ch_disable);
    else
	return -1;
	   
}

/**
 * Returns the unique ID (serial number) for the specified board. 
 * \param boardnum fadc board number or CLOCKBOARD for the clock/trigger board
 *
 * \todo check this for FADC boards. 
 */
unsigned long 
fadc_get_serial_number( int boardnum ) {

    unsigned long value;

    if (boardnum == CLOCKBOARD) {
	
	value = *(clk_lptr + RD_CLK_START_HDR);
	
	return (value & 0xFF);

    }
    else {
	value = *(Board[boardnum].lptr + RD_BD_ID_HDR);
	return value;
    }

}


/**
 * used to reduce some code bloat: call to loop over boards 
 */
void
set_value_helper(int boardnum, int chan, unsigned long val, 
		 void (*setfunc)(int,int,unsigned long)){
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd=0; bd < MAXBOARDS; bd++) {
	    if (Board[bd].active) {
		setfunc(bd, chan, val);
	    }
	}
    } else {
	if (Board[boardnum].active) {
	    setfunc(boardnum, chan, val);
	}
    }
}

/**
 * Request that the next event read will return the contents of the
 * pedestal window, instead of the regular data window.  After calling
 * this, you must wait until fadc_got_event() returns 1 before reading
 * the buffer again!
 */
void
fadc_request_pedestal() {

    unsigned long *lptr;
    int i;

    lptr = clk_lptr + WR_PED_CMD;
    *lptr =0;

    info("pedestal event requested\n");

}


/**
 * Request that the next event read will return the contents of the
 * reread window, instead of the regular data window.  After calling
 * this, you must wait until fadc_got_event() returns 1 before reading
 * the buffer again!
 */
void
fadc_request_reread() {

    unsigned long *lptr;
    int i;

    lptr = clk_lptr + WR_REREAD_CMD;
    *lptr =0;
    
    info("reread event requested\n");
    

}

/**
 * Request that the next event read will return the contents of the
 * reread window, instead of the regular data window. Successive calls
 * will increment the reread window by the reread_width so that very
 * large buffers can be read out. After calling this, you must wait
 * until fadc_got_event() returns 1 before reading the buffer again!
 */
void
fadc_request_dump() {
    unsigned long *lptr;
    int i;

    lptr = clk_lptr + WR_DUMP_CMD;
    *lptr =0;

    info("dump requested\n");

}

/*----------------------------------------------------------------------*/
/*  data width */
/*----------------------------------------------------------------------*/

/**
 * Returns the number of words of data per channel for the specified board.
 */
unsigned long
fadc_get_data_width( int boardnum ) {

    if (Board[boardnum].active) {
	return Board[boardnum].data_width;	
    }
    else return -1;

}

void
fadc_set_data_width( int boardnum, unsigned long val ) {

    if (boardnum == FADC_ALL) {
	int i;
	for (i=0; i<MAXBOARDS; i++) {
	    if (Board[i].active) {
		Board[i].data_width = val;
		update_board_parameters(i);
	    }
	}
	info ("Set data width on all boards to %ld\n", val);
    }
    else {
	Board[boardnum].data_width = val;
	update_board_parameters(boardnum);
	info("Set data width on board %d to %ld\n", boardnum, val);
    }

}

/*----------------------------------------------------------------------*/
/*  area discriminator */
/*----------------------------------------------------------------------*/

/* Called by fadc_set_area_discrim() to actually set the area discrim
 * values. */
static void
set_area_discrim(int bd, int chan, unsigned long val)
{
   
    if (chan == FADC_ALL) {
	/* Set all channels on this board. */
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].area_discrim = val;
	    update_chan_disc( bd, i );
	}
	
    } 
    else {
	/* Set one channel. */
	Board[bd].chan[chan].area_discrim = val;
	update_chan_disc( bd, chan);
    }


}

/**
 * Set the area discrim for a particular board and channel. 
 * @param boardnum specific board number or FADC_ALL (set all boards)
 * @param chan specific channel number on the board or FADC_ALL  
 * @param val area discriminator value
 */
void
fadc_set_area_discrim(int boardnum, int chan, unsigned long val)
{
    if (boardnum == FADC_ALL) {
	/* Set chan on all boards to val. */
	int bd;
	for (bd=0; bd < MAXBOARDS; bd++) {
	    if (Board[bd].active) {
		set_area_discrim(bd, chan, val);
	    }
	}
    } else {
	if (Board[boardnum].active) {
	    /* Just set this one board. */
	    set_area_discrim(boardnum, chan, val);
	}
    }
}


/*----------------------------------------------------------------------*/
/*  area offset */
/*----------------------------------------------------------------------*/

/**
 * Returns the area offset for a particular board and channel
 */
unsigned long
fadc_get_area_offset(int boardnum, int chan)
{
    return Board[boardnum].chan[chan].area_offs;
}


/**
 * Set the area offset for a particular board and channel. 
 * @param boardnum specific board number or FADC_ALL (set all boards)
 * @param chan specific channel number on the board or FADC_ALL 
 * (set all channels)
 * @param val area offset value
 */
void
fadc_set_area_offset(int boardnum, int chan, unsigned long val)
{
    if (boardnum == FADC_ALL) {
	/* Set chan on all boards to val. */
	int bd;
	for (bd=0; bd < MAXBOARDS; bd++) {
	    if (Board[bd].active) {
		set_area_offset(bd, chan, val);
	    }
	}
    } else {
	if (Board[boardnum].active) {
	    /* Just set this one board. */
	    set_area_offset(boardnum, chan, val);
	}
    }
}


/* Called by fadc_set_area_offset() to actually set the area offset
 * values. */
static void
set_area_offset(int bd, int chan, unsigned long val)
{
    if (chan == FADC_ALL) {
	/* Set all channels on this board. */
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].area_offs = val;
	    update_chan_offsets( bd, i );
	}
    } else {
	/* Set one channel. */
	Board[bd].chan[chan].area_offs = val;
	update_chan_offsets( bd, chan );
    }


}


/*----------------------------------------------------------------------*/
/*  area width */
/*----------------------------------------------------------------------*/

/**
 * Returns the area width for a particular board and channel. 
 */
unsigned long
fadc_get_area_width(int boardnum, int chan)
{
    return Board[boardnum].chan[chan].area_width;
}


/**
 * Set the area width for a particular board and channel.
 * @param boardnum - specific board number or FADC_ALL (set all boards)
 * @param chan - specific channel number on the board or FADC_ALL 
 * (set all channels)
 * @param val area width value for zero-suppression
 */
void
fadc_set_area_width(int boardnum, int chan, unsigned long val)
{
    if (boardnum == FADC_ALL) {
	/* Set chan on all boards to val. */
	int bd;
	for (bd=0; bd < MAXBOARDS; bd++) {
	    if (Board[bd].active) {
		set_area_width(bd, chan, val);
	    }
	}
    } else {
	if (Board[boardnum].active) {
	    /* Just set this one board. */
	    set_area_width(boardnum, chan, val);
	}
    }
}


/* Called by fadc_set_area_offset() to actually set the area width
 * values. */
static void
set_area_width(int bd, int chan, unsigned long val)
{
    if (chan == FADC_ALL) {
	/* Set all channels on this board. */
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].area_width = val;
	    update_chan_offsets( bd, chan );
	}
    } else {
	/* Set one channel. */
	Board[bd].chan[chan].area_width = val;
	update_chan_offsets( bd, chan );
    }

}


/*----------------------------------------------------------------------*/
/*  data offset */
/*----------------------------------------------------------------------*/

/**
 * Returns the data offset for a particular board and channel . 
 */
unsigned long
fadc_get_data_offset(int boardnum, int chan)
{
    return Board[boardnum].chan[chan].data_offs;
}


/**
 * Set the data offset for a particular board and channel. 
 * @param boardnum specific board number or FADC_ALL (set all boards)
 * @param chan specific channel number on the board or FADC_ALL 
 * (set all channels)
 * @param data offset value
 */
void
fadc_set_data_offset(int boardnum, int chan, unsigned long val)
{
    if (boardnum == FADC_ALL) {
	/* Set chan on all boards to val. */
	int bd;
	for (bd=0; bd < MAXBOARDS; bd++) {
	    if (Board[bd].active) {
		set_data_offset(bd, chan, val);
	    }
	}
    } else {
	if (Board[boardnum].active) {
	    /* Just set this one board. */
	    set_data_offset(boardnum, chan, val);
	}
    }
}


/* Called by fadc_set_data_offset() to actually set the data offset
 * values. */
static void
set_data_offset(int bd, int chan, unsigned long val){
    if (chan == FADC_ALL) {
	/* Set all channels on this board. */
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].data_offs = val;
	    update_chan_offsets( bd, i );
	}
    } else {
	/* Set one channel. */
	Board[bd].chan[chan].data_offs = val;
	update_chan_offsets( bd, chan );
    }
}


/*----------------------------------------------------------------------*/
/*  reread offset */
/*----------------------------------------------------------------------*/

unsigned long
fadc_get_reread_offset(int boardnum, int chan) {
    return Board[boardnum].chan[chan].reread_offs;
}

void
fadc_set_reread_offset(int boardnum, int chan, unsigned long val){
    set_value_helper(boardnum, chan, val, set_reread_offset);
}


static void
set_reread_offset(int bd, int chan, unsigned long val) {
    if (chan == FADC_ALL) {
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].reread_offs = val;
	    update_chan_offsets( bd, i );
	}
    } else {
	Board[bd].chan[chan].reread_offs = val;
	update_chan_offsets( bd, chan );
    }

    info ("updated reread offset on channel %d to %ld\n", chan,val);

}



/*----------------------------------------------------------------------*/
/*  hilo offset */
/*----------------------------------------------------------------------*/
unsigned long
fadc_get_hilo_offset(int boardnum, int chan) {
    return Board[boardnum].chan[chan].hilo_offs;
}

void
fadc_set_hilo_offset(int boardnum, int chan, unsigned long val)
{
    set_value_helper(boardnum, chan, val, set_hilo_offset);
}


static void
set_hilo_offset(int bd, int chan, unsigned long val) {
    if (chan == FADC_ALL) {
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].hilo_offs = val;
	    update_chan_offsets( bd, i );
	}
    } else {
	Board[bd].chan[chan].hilo_offs = val;
	update_chan_offsets( bd, chan );
    }
}



/*----------------------------------------------------------------------*/
/*  pedestal offset */
/*----------------------------------------------------------------------*/
unsigned long
fadc_get_pedestal_offset(int boardnum, int chan) {
    return Board[boardnum].chan[chan].ped_offs;
}

void
fadc_set_pedestal_offset(int boardnum, int chan, unsigned long val) {
    set_value_helper(boardnum, chan, val, set_pedestal_offset);
}

static void
set_pedestal_offset(int bd, int chan, unsigned long val) {
    if (chan == FADC_ALL) {
	int i;
	for (i=0; i < CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].ped_offs = val;
	    update_chan_offsets( bd, i );
	}
    } else {
	Board[bd].chan[chan].ped_offs = val;
	update_chan_offsets( bd, chan );
    }
}

/*----------------------------------------------------------------------*/
/*  hilo width */
/*----------------------------------------------------------------------*/
unsigned long
fadc_get_hilo_width(int boardnum) {
    return Board[boardnum].hilo_width;
}

void
fadc_set_hilo_width( int boardnum, unsigned long val ) {

    if (boardnum == FADC_ALL) {
	int i;
	for (i=0; i<MAXBOARDS; i++) {
	    if (Board[i].active) {
		Board[i].hilo_width = val;
		update_board_parameters(boardnum);
	    }
	}
	info ("Set hilo width on all boards to %ld\n", val);
    }
    else {
	Board[boardnum].hilo_width = val;
	update_board_parameters(boardnum);
	info("Set hilo width on board %d to %ld\n", boardnum, val);
    }

}

/*----------------------------------------------------------------------*/
/*  reread width */
/*----------------------------------------------------------------------*/
unsigned long
fadc_get_reread_width(int boardnum) {
    return Board[boardnum].reread_width;
}

void
fadc_set_reread_width( int boardnum, unsigned long val ) {

    if (boardnum == FADC_ALL) {
	int i;
	for (i=0; i<MAXBOARDS; i++) {
	    if (Board[i].active) {
		Board[i].reread_width = val;
		update_board_parameters(boardnum);
	    }
	}
	info ("Set reread width on all boards to %ld\n", val);
    }
    else {
	Board[boardnum].reread_width = val;
	update_board_parameters(boardnum);
	info("Set reread width on board %d to %ld\n", boardnum, val);
    }

}

/*----------------------------------------------------------------------*/
/*  pedestal width */
/*----------------------------------------------------------------------*/

unsigned long
fadc_get_pedestal_width(int boardnum) {
    return Board[boardnum].ped_width;
}

void
fadc_set_pedestal_width( int boardnum, unsigned long val ) {

    if (boardnum == FADC_ALL) {
	int i;
	for (i=0; i<MAXBOARDS; i++) {
	    if (Board[i].active) {
		Board[i].ped_width = val;
		update_board_parameters(boardnum);
	    }
	}
	info ("Set pedestal width on all boards to %ld\n", val);
    }
    else {
	Board[boardnum].ped_width = val;
	update_board_parameters(boardnum);
	info("Set pedestal width on board %d to %ld\n", boardnum, val);
    }

}


/*----------------------------------------------------------------------*/
/*  CFD parameters */
/*----------------------------------------------------------------------*/
/**
 * Set programmable delay going into the CFD.   
 * @param boardnum board number or FADC_ALL
 * @param chan channel number 0..9 or FADC_ALL
 * @param val 4-bit programmable delay value
 * @return 0 on success, 1 on error
 */
int
fadc_set_cfd_delay( int boardnum, int chan, unsigned long val ) {
    
    if (boardnum == FADC_ALL) {
	
	int bd;
	
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_delay(bd,chan,val);
	}

    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_delay(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */

    }

    return 0;

}

/* used by fadc_set_cfd_delay */
static void
set_cfd_delay( int bd, int chan, unsigned long val ) {

    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_del = val;
	    update_uu_cfds( bd, chan );
	    /* Do it again, hack to fix bug when programming ch0 */
	    if(i==0) update_uu_cfds( bd, i ); 
	}
    }
    else {
	
	Board[bd].chan[chan].cfd_del = val;
	update_uu_cfds( bd, chan );
    }



}

/**
 * Returns the current CFD delay  value .
 */
unsigned long
fadc_get_cfd_delay( int boardnum, int chan ) {

    return Board[boardnum].chan[chan].cfd_del;
}


/**
 * Set CFD ratefb potentiometer value.
 * @param chan channel number 0..9 or FADC_ALL
 * @param boardnum board number or FADC_ALL
 * @param val 7-bit ratefb value
 * @return 0 on success, 1 on error
 */
int 
fadc_set_cfd_ratefb( int boardnum, int chan, unsigned long val) {

    if (val >= 128) return -2; /* out of range */
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_ratefb(bd,chan,val);
	}
    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_ratefb(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */
    }
    return 0;

}

/* used by fadc_set_cfd_ratefb */
static void 
set_cfd_ratefb( int bd, int chan, unsigned long val ) {
    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_ratefb = val;
	    update_uu_cfds( bd, i );
	    /* Do it again, hack to fix bug when programming ch0 */
	    if(i==0) update_uu_cfds( bd, i ); 
	}
    }
    else {
	Board[bd].chan[chan].cfd_ratefb = val;
	update_uu_cfds( bd, chan );
    }

}



/**
 * Returns the current CFD 7-bit potentiometer  value .
 */
unsigned long
fadc_get_cfd_ratefb( int boardnum, int chan ) {

    return Board[boardnum].chan[chan].cfd_ratefb;

}

/**
 * Set the CFD mode (0 = threshold, 1=cfd)
 */
int 
fadc_set_cfd_mode( int boardnum, int chan, unsigned long val ) {

    if (val >= 2) return -2; /* out of range */
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_mode(bd,chan,val);
	}
    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_mode(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */
    }
    return 0;

};

static void
set_cfd_mode( int bd, int chan, unsigned long val ) {

    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_mode = val;
	    update_uu_cfds( bd, i );
	    /* Do it again, hack to fix bug when programming ch0 */
	    if(i==0) update_uu_cfds( bd, i ); 
	}
    }
    else {
	Board[bd].chan[chan].cfd_mode = val;
	update_uu_cfds( bd, chan );
    }

}


/**
 * Set CFD threshold DAC value.
 * @param chan channel number 0..9 or FADC_ALL
 * @param boardnum board number or FADC_ALL
 * @param val 12-bit threshold DAC value
 * @return 0 on success, 1 on error
 */
int 
fadc_set_cfd_thresh( int boardnum, int chan, unsigned long val) {

    if (val >= 4096) return -2; /* out of range */
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_thresh(bd,chan,val);
	}
    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_thresh(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */
    }
    return 0;

}

/* used by fadc_set_cfd_thresh() */
static void 
set_cfd_thresh( int bd, int chan, unsigned long val ) {
    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_thresh = val;
	    update_uu_cfds( bd, i );
	    /* Do it again, hack to fix bug when programming ch0 */
	    if(i==0) update_uu_cfds( bd, i ); 
	}
    }
    else {
	Board[bd].chan[chan].cfd_thresh = val;
	update_uu_cfds( bd, chan );
    }

}


/**
 * Returns the current 12-bit CFD threshold DAC value .
 */
unsigned long
fadc_get_cfd_thresh( int boardnum, int chan ) {

    return Board[boardnum].chan[chan].cfd_thresh;

}

/**
 * Set CFD width DAC value.
 * @param chan channel number 0..9 or FADC_ALL
 * @param boardnum board number or FADC_ALL
 * @param val 12-bit width DAC value
 * @return 0 on success, 1 on error
 */
int 
fadc_set_cfd_width( int boardnum, int chan, unsigned long val) {
    if (val >= 4096) return -2; /* out of range */
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_width(bd,chan,val);
	}
    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_width(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */
    }
    return 0;

}

/* used by fadc_set_cfd_width() */
static void 
set_cfd_width( int bd, int chan, unsigned long val ) {
    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_width = val;
	    update_uu_cfds( bd, i );
	    /* Do it again, hack to fix bug when programming ch0 */
	    if(i==0) update_uu_cfds( bd, i ); 
	}
    }
    else {
	Board[bd].chan[chan].cfd_width = val;
	update_uu_cfds( bd, chan );
    }

}

/**
 * Returns the current 12-bit CFD trigger width DAC  value .
 */
unsigned long
fadc_get_cfd_width( int boardnum, int chan ){

    return Board[boardnum].chan[chan].cfd_width;

}

/**
 * Set CFD type. 
 * @param val either CFD_WASHU and CFD_UTAH
 */
int
fadc_set_cfd_type( int boardnum, int chan, unsigned long val) {
    

    if (boardnum == FADC_ALL) {
	int bd;
	for (bd=0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active) {
		set_cfd_type( bd, chan, val );
	    }
	}
    }
    else {
	if (Board[boardnum].active)
	    set_cfd_type( boardnum, chan, val );
	else return -1;
    }
        
    return 0;

}



static void 
set_cfd_type( int bd, int ch, unsigned long val ) {
    if (ch == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_type = val;
	}
    }
    else {
	Board[bd].chan[ch].cfd_type = val;
    }
}

/**
 * returns type of cfd 
 */
unsigned long
fadc_get_cfd_type( int boardnum, int chan ) {

    return Board[boardnum].chan[chan].cfd_type;

}



/**
 * Set Washu CFD wuthresh 
 * @param chan channel number 0..9 or FADC_ALL
 * @param boardnum board number or FADC_ALL
 * @param val 12-bit wuthresh
 * @return 0 on success, 1 on error
 */
int 
fadc_set_cfd_wuthresh( int boardnum, int chan, unsigned long val) {

    if (val > 4096) return -2; /* out of range */
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_wuthresh(bd,chan,val);
	}
    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_wuthresh(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */
    }
    return 0;

}

/* used by fadc_set_cfd_wuthresh */
static void 
set_cfd_wuthresh( int bd, int chan, unsigned long val ) {
    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_wuthresh = val;
	    update_wu_cfds( bd, i );
	}
    }
    else {
	Board[bd].chan[chan].cfd_wuthresh = val;
	update_wu_cfds( bd, chan );
    }

}

/**
 * Sets washu cfd wuthresh value
 */
unsigned long
fadc_get_cfd_wuthresh( int boardnum, int chan ) {

    return Board[boardnum].chan[chan].cfd_wuthresh;

}


/**
 * Set Washu CFD wuoffs
 * @param chan channel number 0..9 or FADC_ALL
 * @param boardnum board number or FADC_ALL
 * @param val 12-bit wuthresh
 * @return 0 on success, 1 on error
 */
int 
fadc_set_cfd_wuoffs( int boardnum, int chan, unsigned long val) {

    if (val > 4096) return -2; /* out of range */
    if (boardnum == FADC_ALL) {
	int bd;
	for (bd = 0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		set_cfd_wuoffs(bd,chan,val);
	}
    }
    else {
	if (Board[boardnum].active) {
	    set_cfd_wuoffs(boardnum, chan, val);
	}
	else  
	    return -1;   /* board not active */
    }
    return 0;

}

/* used by fadc_set_cfd_wuthresh */
static void 
set_cfd_wuoffs( int bd, int chan, unsigned long val ) {
    if (chan == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    Board[bd].chan[i].cfd_wuoffs = val;
	    update_wu_cfds( bd, i );
	}
    }
    else {
	Board[bd].chan[chan].cfd_wuoffs = val;
	update_wu_cfds( bd, chan );
    }

}

/**
 * Sets washu cfd wuthresh value
 */
unsigned long
fadc_get_cfd_wuoffs( int boardnum, int chan ) {

    return Board[boardnum].chan[chan].cfd_wuoffs;

}



/**
 * Gives the value of the largest possible event given the current
 * data width for the board. 
 */
int
fadc_get_max_evt_size(int boardnum)
{
    int size;

    if (Board[boardnum].active ==0) {
	size = -1;
    } else {
	/* +1 for area header, +3 for start-, event-, and hit-header */
	size = ((Board[boardnum].data_width + 1) * CHAN_PER_BOARD) + 3;
    }
    return size;
}

/**
 * Enable (1) or disable (0) the chatter. 
 */
void
fadc_verbose(int state)
{
    Verbose = state;
}

/**
 * Transfer nwords 32-bit words from the specified board to the memory
 * location pointed to by dest.  
 * @return 0 if all went well, or -1 if the board is inactive. 
 */
int
fadc_memcpy(unsigned long *dest, int boardnum, unsigned long nwords)
{
    unsigned long i;
    unsigned long *p;

    if (Board[boardnum].active && dest != NULL) {
	for (i=0; i<nwords; i++) {
	    dest[i] = Board[boardnum].lptr[i];
	}
	//	memcpy(dest, Board[boardnum].lptr, (size_t)(nwords) * sizeof(unsigned long));
	return 0;
    }
    return -1;
}


/**
 * Set up the CBLT (Chained Block Transfer) buffer which is internally
 * allocated by libfadc.  After you call 'nwords = fadc_cblt()', this
 * buffer will be filled with nwords worth of data from all of the
 * boards in the chain.  A signal handler to trap bus errors (BERR*)
 * is also set up in this function.  This function MUST be called
 * before any cblt's are initiated, and should only be called once.
 *
 * If the calling program is multithreaded, you must call this
 * function within your "reader" thread (not in the main program),
 * since the interaction of the signal handler which traps the BERR*
 * signal interacts in a complicated way with pthreads.
 *
 * \param maxwords maximum size of the CBLT buffer in words - should
 * be big enough to hold all the data from all the boards in the
 * chain.
 *
 * \param first index of first board in the chain (or -1 for clock board)
 * \param last  index of last board in chain (or -1 for clock board)
 *
 * \returns an unsigned long pointer to the CBLT buffer.  */
unsigned long* 
fadc_alloc_cblt_buffer( int maxwords, int first, int last ) {
   
    int i;

    /* Set up BERR* interrupt handler so the program doesn't crash
       during a CBLT (which terminates with a bus error) */
    
    install_interrupt_handler();

    /* Allocate memory */

    Cblt_buffer_size = maxwords * 4;
    
    first_board_lptr = (first >=0)? Board[first].lptr : clk_lptr;
    last_board_lptr  = (last >=0)?  Board[last].lptr  : clk_lptr;


    if(0 > vme_dma_buffer_create(bus_handle, &dma_handle, 
				 Cblt_buffer_size, 0, NULL)) {
	perror("Error creating the buffer");
	vme_term(bus_handle);
	exit(1);
    }
	
    if(NULL == (Cblt_buffer = (unsigned long*)vme_dma_buffer_map(bus_handle, 
								 dma_handle, 
								 0))) {
	perror("Error mapping the buffer");
	vme_dma_buffer_release(bus_handle, dma_handle);
	vme_term(bus_handle);
	exit(1);
    }

    for (i=0; i<maxwords; i++) {
	Cblt_buffer[i] = 0;
    }
    
    return Cblt_buffer;

}

/**
 * Initiate a Chained Block Transfer (CBLT).  All data from each board
 * in the chain will be read out and stored in the CBLT buffer that
 * was allocated with fadc_alloc_cblt_buffer().
 *
 * \returns number of words of data that were transfered.
 */ 
int 
fadc_cblt() {

    unsigned long *lptr;
    int ret;
    unsigned int status;
    int nwords;
    unsigned long temp;
    int tries;
    int i;

    /* initiate a CBLT */

    lptr = first_board_lptr + CBLT_START;   /* start cblt */
    *lptr = 0;
    
    /* Transfer the data */
    vme_dma_read(bus_handle, dma_handle, 0, VME_BASE_ADDRESS,
		    VME_A32UB, Cblt_buffer_size, 0);


    /* wait for berr* to occur: */

    while (Cblt_berr_occurred == 0) {
      tries++;
//      if (tries > 100000000) return -2;
    }
     
  /* Read the number of words transferred from the last board */
    
  lptr = last_board_lptr + CBLT_NWORDS;
  temp = *lptr;
  
  /* reset the CBLT flag now that we have read the event */
  
  Cblt_berr_occurred = 0;

  if (temp == 0xFFFFFFFF) {
    /* Looks like a VME read error. Attempt to re-read until it looks ok. 
     I bail out  after a while just incase there's a bigger problem.
     I tested this, and it looks like it always recovers after the first re-try,
     but you never know. */
    for (tries=0; tries<1000; tries++) {
      temp = *lptr;
      if (temp != 0xFFFFFFFF)    break;
    }
  }
  
  if ( (temp & 0xFFFC0000) != 0xDBF00000) {
    info("libfadc: fadc_cblt: bad cblt size header: 0x%08lx\n", temp);
    return -3;
  }
  
  nwords = (temp) & 0x1ffff;
  return nwords;
  
}



/* Write the dacs, offsets, and area discrim to the board. Uses the
 * values in the Board struct. 
 * 
 * TODO: check that the parameters are within bounds 
 */
static void
update_all_settings(int bd)
{
    int chan;

    if (!Initialized) {
	info("can't update: board %d not initialized!\n",bd);
	return;

    }

    if (Board[bd].active) {
	
	for (chan=0; chan<CHAN_PER_BOARD; chan++){  

	    if (Board[bd].chan[chan].cfd_type == CFD_WASHU ) {
		update_wu_cfds( bd, chan );
	    }

	    else { 
		/* Update Utah CFD board */
		update_uu_cfds( bd, chan);
	    }
    
	    update_chan_offsets( bd, chan );	    
	    update_chan_disc( bd, chan );

	    
	}
	
	update_board_parameters(bd);

    } 
    else {
	/* inactive */
	info("tried to write to board %d, which is marked as inactive!\n", bd);
    }

}

void
update_board_parameters( int bd ) {

    /* update data width */
    if (Board[bd].revision < 2)
	wr_width(Board[bd].lptr, Board[bd].data_width);
    else {
	/* for newer gate-arrays: update hilo , ped, reread widths
	   too */

	unsigned long *lptr;

	lptr = Board[bd].lptr + WR_DATA_WIDTH;
	*lptr = (Board[bd].hilo_width << 8) + Board[bd].data_width;

	lptr = Board[bd].lptr + WR_OTHER_WIDTH;
	*lptr = (Board[bd].reread_width << 8) + Board[bd].ped_width;
    }


}

static void
update_wu_cfds( int bd, int chan ) {
    wr_ch_dacs(Board[bd].lptr, chan,
	       Board[bd].chan[chan].cfd_wuthresh, 
	       Board[bd].chan[chan].cfd_wuoffs,
	       Board[bd].chan[chan].cfd_del, 
	       Board[bd].chan[chan].cfd_inh);   

    info("updated WU cfd registers on bd %d ch %d\n", bd, chan);

}

static void
update_uu_cfds( int bd, int chan ) {
    wr_cfd_params( Board[bd].lptr, chan,
		   Board[bd].chan[chan].cfd_del,
		   Board[bd].chan[chan].cfd_ratefb,
		   Board[bd].chan[chan].cfd_thresh,
		   Board[bd].chan[chan].cfd_width,
		   Board[bd].chan[chan].cfd_mode );

        //nap(200); /* make sure serial bit stream is fully written */
    usleep(200);  // note - i went back to usleep (which doesn't work
		  // right on the VERITAS computers) because I was
		  // apparently not waiting long enought with the nap
		  // command - it really needs to be better calibrated

    info("updated UU cfd registers on bd %d ch %d\n", bd, chan);

}

static void
update_chan_offsets( int bd, int chan ) {

    if (Board[bd].revision == 0) {
	/* This routine is only appropriate for 
	   first-generation gate-arrays */
	wr_ch_offsets(Board[bd].lptr, chan,
		      Board[bd].chan[chan].area_offs,
		      Board[bd].chan[chan].area_width,
		      Board[bd].chan[chan].data_offs);

	info( "Assuming first-gen channel gate array for board rev. 0\n");
    }
    else {
	/* This is the updated version */
	if (Board[bd].chan[chan].revision < 2) {
	    unsigned long *lptr, val, chan_offs, area_width, area_offs;
	    area_width = Board[bd].chan[chan].area_width;
	    area_offs  = Board[bd].chan[chan].data_offs;
	    chan_offs = 0x2000 + (chan * 0x10);
	    lptr = Board[bd].lptr + chan_offs + CH_OFFSETS;
	    val = (area_width << 14) + area_offs;
	    *lptr = val;
	    info("Assuming revision <2 gate arrays\n");
	}
	else {
	    /* for newer (3rd gen) gate arrays, here's the new
	       version */

	    unsigned long *lptr;
	    unsigned long chan_offs = 0x2000+(chan*0x10);

	    /* write area width + offset */
	    lptr = Board[bd].lptr + chan_offs + CH_OFFSETS;
	    *lptr = (Board[bd].chan[chan].area_width <<15) 
		+ Board[bd].chan[chan].area_offs;

	    /* write hilo offset + data offset */
	    lptr = Board[bd].lptr + chan_offs + CH_DATA_OFFS;
	    *lptr = (Board[bd].chan[chan].hilo_offs <<15) 
		+ Board[bd].chan[chan].data_offs;

	    /* write reread + ped offsets */
	    lptr = Board[bd].lptr + chan_offs + CH_OTHER_OFFS;
	    *lptr = (Board[bd].chan[chan].reread_offs <<15) 
		+ Board[bd].chan[chan].ped_offs;

	    info("updated revision >2 offsets and widths\n");

	}
    }
    
    info("updated channel params [rev%d] for bd %d chan %d \n", 
	 Board[bd].chan[chan].revision,bd, chan);	



}

static void
update_chan_disc( int bd, int chan ) {
    wr_ch_area_discrim(Board[bd].lptr, chan,
		       Board[bd].chan[chan].area_discrim,
		       Board[bd].chan[chan].ch_disable);


    info("updated channel discrim register for bd %d chan %d \n", bd, chan);

}

/**
 * Returns the value the CFD trigger scalar in the channel gate array 
 */
unsigned long
fadc_get_trigger_scaler(int boardnum, int chan ) {

    return rd_ch_scaler(Board[boardnum].lptr, chan);

}

/**
 * Multicast clear all the trigger scalers in the rack.
 */
void
fadc_multicast_clear_trigger_scaler()
{
    unsigned long *lptr;
    lptr = clk_lptr + WR_CLR_SCALAR;
    *lptr = 0;
}



/**
 * Clear the value of the trigger scaler for channel chan on board boardnum 
 */ 
int
fadc_clear_trigger_scaler(int boardnum, int chan) {

    printf("TODO: need to implement the multicast command for fadc_clear_trigger scaler. this is deprecated\n");

    if (boardnum == FADC_ALL) {
	int bd;
	for (bd=0; bd<MAXBOARDS; bd++) {
	    if (Board[bd].active)
		clear_trigger_scaler(bd, chan);
	}
    }
    else {
	if(Board[boardnum].active) {
	    clear_trigger_scaler(boardnum,chan);
	}
	else
	    return -1;
    }
    return 0;

}

void
clear_trigger_scaler(int bd, int ch) {
    
    unsigned long *lptr;
    unsigned long chan_offs;
    
    if (ch == FADC_ALL) {   /* set all channels */
	int i;
	for(i=0; i< CHAN_PER_BOARD; i++) {
	    chan_offs = 0x2000 + (i * 0x10);
	    lptr = Board[bd].lptr + chan_offs + CH_CLR_SCALER;
	    *lptr = 0;
	}
    }
    else {
	chan_offs = 0x2000 + (ch * 0x10);
	lptr = Board[bd].lptr + chan_offs + CH_CLR_SCALER;
	*lptr = 0;
    }

}


// Functions for setting the new (2018+) gate array pedvars
// For the veritas optical upgrade.
void set_pedvar_reset() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_RST;
			*lptr = 0; // We can write anything here?
		}
	}
}

void set_pedvar_1khz() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_1KHZ;
			*lptr = 0;
		}
	}
}

void set_pedvar_2khz() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_2KHZ;
			*lptr = 0;
		}
	}
}

void set_pedvar_4khz() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_4KHZ;
			*lptr = 0;
		}
	}
}

void set_pedvar_8khz() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_8KHZ;
			*lptr = 0;
		}
	}
}

void set_pedvar_16khz() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_16KHZ;
			*lptr = 0;
		}
	}
}

void set_pedvar_off() {
    
    unsigned long *lptr;
    unsigned long chan_offs;

	int bd;
	int ch;
	for (bd=0; bd<MAXBOARDS; bd++) {
		for(ch=0; ch < CHAN_PER_BOARD; ch++) {
			chan_offs = 0x2000 + (ch * 0x10);
			lptr = Board[bd].lptr + chan_offs + WR_PEDVAR_OFF;
			*lptr = 0;
		}
	}
}

/**
 * Clear event on all FADC boards in the crate. This must be called
 * after reading an event to tell the boards to continue to look for
 * triggers.  
 */
void 
fadc_evt_clr(void)
{
    unsigned long *lptr;
    
    if (Clockboard_id <= 225) {
	/* old way of clearing event */
	lptr = clk_lptr + WR_EVENT_CLEAR;
    }
    else {
	lptr = clk_lptr + SOFT_EVT_CLR;
    }
    *lptr = 0;

    lptr = clk_lptr + WR_CRATE_CLEAR;
    *lptr = 0;

}


/**
 * returns current value of the livetime scaler on the Clock/Trigger board.
 */
unsigned long 
fadc_get_livetime_scaler() {
    
    unsigned long *lptr;
    lptr = clk_lptr + RD_CLK_LIVETIME;

    return *lptr;

}

/**
 * returns current value of the elapsed time scaler on the Clock/Trigger board.
 */
unsigned long 
fadc_get_elapsed_scaler() {

    unsigned long *lptr;
    lptr = clk_lptr + RD_CLK_ELAPSED;

    return *lptr;

}

/**
 * Save all FADC board settings to a text file.
 */
int 
fadc_save_settings( int boardnum, char *filename ) {

    FILE *fp;
    int ch;
    unsigned long val,cfdtype;

    fp = fopen( filename, "w" );

    if (!fp) {
	info("Settings could not be saved because: %s\n", strerror(errno));
	return -1;
    }
    
    fprintf(fp,"# FADC BOARD SETTINGS FILE\n\n");
    fprintf(fp,"Board\t\t\t%d\n", boardnum);
    fprintf(fp,"BoardRevision\t\t%u\n", Board[boardnum].revision);
    fprintf(fp,"DataWidth\t\t%u\n", Board[boardnum].data_width);
    fprintf(fp,"HiloWidth\t\t%u\n", Board[boardnum].hilo_width);
    fprintf(fp,"RereadWidth\t\t%u\n", Board[boardnum].reread_width);
    fprintf(fp,"PedWidth\t\t%u\n", Board[boardnum].ped_width);

    for (ch=0; ch<10; ch++) {

	fprintf(fp,"\n");

	fprintf(fp,"Chan\t\t\t%d\n", ch);
	fprintf(fp,"Disabled\t\t%d\n", fadc_is_channel_disabled(boardnum,ch));
	fprintf(fp,"ChanRevision\t\t%u\n", Board[boardnum].chan[ch].revision);
	fprintf(fp,"DataOffset\t\t%u\n", Board[boardnum].chan[ch].data_offs);
	fprintf(fp,"AreaWidth\t\t%u\n", Board[boardnum].chan[ch].area_width);
	fprintf(fp,"AreaOffset\t\t%u\n", Board[boardnum].chan[ch].area_offs);
	fprintf(fp,"HiloOffset\t\t%u\n", Board[boardnum].chan[ch].hilo_offs);
	fprintf(fp,"RereadOffset\t\t%u\n", Board[boardnum].chan[ch].reread_offs);
	fprintf(fp,"PedOffset\t\t%u\n", Board[boardnum].chan[ch].ped_offs);
	fprintf(fp,"AreaDiscrim\t\t%u\n", Board[boardnum].chan[ch].area_discrim);

	if (Board[boardnum].chan[ch].cfd_type == CFD_WASHU) {
	    fprintf( fp, "CFDType\t\t\tWU\n");
	    fprintf( fp, "CFDThresh\t\t%u\n", Board[boardnum].chan[ch].cfd_wuthresh);
	    fprintf( fp, "CFDOffset\t\t%u\n", Board[boardnum].chan[ch].cfd_wuoffs);
	}
	else {
	    fprintf( fp, "CFDType\t\t\tUTAH\n");
	    fprintf( fp, "CFDThresh\t\t%u\n", Board[boardnum].chan[ch].cfd_thresh);
	    fprintf( fp, "CFDRateFB\t\t%u\n", Board[boardnum].chan[ch].cfd_ratefb);
	    fprintf( fp, "CFDWidth\t\t%u\n" , Board[boardnum].chan[ch].cfd_width);
	}

	fprintf(fp, "CFDDelay\t\t%u\n", Board[boardnum].chan[ch].cfd_del);

    }

    fclose(fp);

    info( "board %d settings saved to '%s'\n", boardnum, filename);
    
    return 0;

}

/**
 * Load FADC board settings from a text file that was generated by
 * fadc_save_settings()
 */
int 
fadc_load_settings( int boardnum, char *filename ) {

    FILE *fp;
    char line[512];
    char key[256], value[256];
    int  ival;
    unsigned long lval,type;
    int ch=0, linenum=-1;
    int bd=boardnum;

    fp = fopen( filename, "r" );
    if (fp == NULL) {
	fprintf( stderr, " couldn't open settings file '%s'\n", filename);
	return -1;
    }

    while (!feof(fp)) {

	fgets( line, 512, fp );
	linenum++;

	/* ignore comments and blank lines */
	if (line[0] == '#' || line[0] == '\n')  continue;

	/* read the key/value pair */
	sscanf( line,"%s %s", key,value);
	lval = (unsigned long) atol( value );
	ival = atoi( value );

	/* Set values */
	if ( !strcmp(key,"Board") ) {
	    //	    bd = ival; actually, don't want to do this - just
	    //leave it at boardnum
	}
	else if (!strcmp(key,"DataWidth")) { 
	    Board[bd].data_width = lval;
	} 
	else if (!strcmp(key,"HiloWidth")) { 
	    Board[bd].hilo_width = lval;
	} 
	else if (!strcmp(key,"RereadWidth")) { 
	    Board[bd].reread_width = lval;
	} 
	else if (!strcmp(key,"PedWidth")) { 
	    Board[bd].ped_width = lval;
	} 
	else if (!strcmp(key,"Chan")) {
	    ch = ival;
	}
	else if (!strcmp(key,"Disabled")) {
	    Board[bd].chan[ch].ch_disable = lval;
	}
	else if (!strcmp(key,"LookBack")) {
	    Board[bd].chan[ch].data_offs = lval;
	}
	else if (!strcmp(key,"DataOffset")) {
	    Board[bd].chan[ch].data_offs = lval;
	}
	else if (!strcmp(key,"AreaWidth")) {
	    Board[bd].chan[ch].area_width = lval;
	}
	else if (!strcmp(key,"AreaOffset")) {
	    Board[bd].chan[ch].area_offs = lval;
	}
	else if (!strcmp(key,"HiloOffset")) {
	    Board[bd].chan[ch].hilo_offs = lval;
	}
	else if (!strcmp(key,"RereadOffset")) {
	    Board[bd].chan[ch].reread_offs = lval;
	}
	else if (!strcmp(key,"PedOffset")) {
	    Board[bd].chan[ch].ped_offs = lval;
	}
	else if (!strcmp(key,"AreaDiscrim")) {
	    Board[bd].chan[ch].area_discrim = lval;
	}
	else if (!strcmp(key,"CFDType")) {
	    if ( value[0] == 'W' )
		Board[bd].chan[ch].cfd_type = CFD_WASHU;
	    else if (value[0] == 'U') 
		Board[bd].chan[ch].cfd_type = CFD_UTAH;
	    else 
		info( "unknown CFD type '%s' on line %d of '%s'\n", 
		      value, linenum, filename);
	}
	else if (!strcmp(key,"CFDThresh")) {
	    type = Board[bd].chan[ch].cfd_type ;
	    if (type == CFD_UTAH)
		Board[bd].chan[ch].cfd_thresh = lval;
	    else if (type == CFD_WASHU)
		Board[bd].chan[ch].cfd_wuthresh = lval; 
	}
	else if (!strcmp(key,"CFDOffset")) {
	    Board[bd].chan[ch].cfd_wuoffs = lval; 
	}
	else if (!strcmp(key,"CFDWidth")) {
	    Board[bd].chan[ch].cfd_width = lval; 
	}
	else if (!strcmp(key,"CFDRateFB")) {
	    Board[bd].chan[ch].cfd_ratefb = lval; 
	}
	else if (!strcmp(key,"CFDDelay")) {
	    Board[bd].chan[ch].cfd_del = lval; 
	}
	else if (!strcmp(key,"BoardRevision")) {
	    Board[bd].revision = lval; 
	}
	else if (!strcmp(key,"ChanRevision")) {
	    Board[bd].chan[ch].revision = lval; 
	}
	else {
	    info("Unknown key '%s' in settings file '%s'\n", 
		 key,filename );
	    continue;
	}
    }
    
    if (Initialized) update_all_settings( bd );
    
    fprintf( stderr, " board %d settings loaded from '%s'\n", bd, filename);
    
    return 0;
     
}

/**
 * Returns a pointer to the beginning address of the specfied FADC
 * board, for low-level board access.  
 */
unsigned long* 
fadc_get_fadc_lptr(int boardnum) {

    return Board[boardnum].lptr;

}

/**
 * Returns a pointer to the beginning address the of Clock/Trigger
 * board for low-level access.
 */
unsigned long* 
fadc_get_clk_lptr(void) {

    return clk_lptr;

}

/**
 * Returns a pointer to the beginning address the of Magic
 * board for low-level access.
 */
unsigned long* 
fadc_get_magic_lptr(void) {

    return magic_lptr;
}

/**
 * Returns a pointer to the beginning address the of L3 serial
 * board for low-level access.
 */
unsigned long* 
fadc_get_l3serial_lptr(void) {

    return l3serial_lptr;
}


/*********************************************************/
/* TESTING FUNCTIONS:   */
/*********************************************************/


/**
 * Write patterns to the FADC board buffer ram and read them back to
 * see if everything is OK.  
 * @return 0 on success, -1 on failure 
 */
int
fadc_buffer_ram_test(int boardnum) {

    unsigned long buffer[8192];
    int i;
    int nerrors = 0;
    unsigned long *lptr;
    unsigned long check;

    /* write 10101010... */
    fill_ram( Board[boardnum].lptr, 0xAAAAAAAA, 8192 );

    /* read 1010101... */
    fadc_memcpy( buffer, boardnum, 8192 );

    /* compare */
    for (i=0; i<8192; i++) {
	if (buffer[i] != 0xAAAAAAAA) {
	    if (Verbose)
		info("Buffer word %d error: 0x%08lx != 0xAAAAAAAA\n", i,
		     buffer[i]);
	    nerrors++;
	}
    }

    /* write 010101010... */
    fill_ram( Board[boardnum].lptr, 0x55555555, 8192 );

    /* read 01010101... */
    fadc_memcpy( buffer, boardnum, 8192 );

    /* compare */
    for (i=0; i<8192; i++) {
	if (buffer[i] != 0x55555555) {
	    if (Verbose)
		info("Buffer word %d error: 0x%08lx != 0xAAAAAAAA\n", i,
		     buffer[i]);
	    nerrors++;
	}
    }
    
    /* do incremental test */
    lptr = Board[boardnum].lptr;
    for (i=0; i<8192; i++) {
	*lptr = i;
	check = *lptr;
	if (check != i) {
	    info("BufferRam incremental test word %ld failed: (0x%08lx != 0x%08lx)", i, check,i);
	    nerrors++;
	}

	lptr++;
    }

    if (nerrors) {
	info("Buffer ram test reported %d errors! (%2.1f%% of ram failed)\n",  
	     nerrors, 100*nerrors/(double)16384.0);
	return -1;
    }
    else 
	info("Buffer ram test passed.\n");
    
    return 0;

}



/*********************************************************/
/* PRIVATE FUNCTIONS (low-level routines) */
/*********************************************************/

// TODO: 
/* set_error - set current error string */
//void 
//set_error(char *fmt, ...) {
//}

/* Sleep for a specified number of microseconds */
void
nap(int microsecs) {

    int i;
    for (i=0; i<Nap_iters_per_usec*microsecs; i++);
    //usleep(microsecs);

}

void
napcalibrate() {

    int i;
    double time0,time1;

    struct timeval tv0,tv1;
    struct timezone tz0,tz1;
    
    gettimeofday( &tv0,&tz1); 
    for ( i=0; i<1000000; i++);
    gettimeofday( &tv1,&tz1); 

    time0 = tv0.tv_sec + (double)tv0.tv_usec/1.0e6;
    time1 = tv1.tv_sec + (double)tv1.tv_usec/1.0e6;

    Nap_iters_per_usec = (int)(floor(1000000.0/(time1-time0))/1.0e6 );
    
  // speed hack for old cpu:
    Nap_iters_per_usec += 1000;

    info("iters per usec = %d\n", Nap_iters_per_usec);
}

/* evt_clr - send an evt_clr command (via the pd clock bd) to clear
 * all FADC bds */
void
evt_clr(unsigned long *bd_lptr)
{
    unsigned long *lptr;
    lptr = bd_lptr + SOFT_EVT_CLR;
    *lptr = 0;
}

/* wr_evt_no -initialize event number counter to 'evt_no'. */
void 
wr_evt_no(unsigned long *bd_lptr, unsigned long evt_no)
{
    unsigned long *lptr;
    lptr = bd_lptr + WR_EVT_NO;
    *lptr = evt_no;
}

/* wr_bd_no - initializes the board number of a FADC bd */
void 
wr_bd_no(unsigned long *bd_lptr, unsigned long bd_no)
{
    unsigned long *lptr;
    lptr = bd_lptr + WR_BD_NO;
    *lptr = bd_no;
}

/* wr_mode - initializes the operating mode of a FADC bd */
void 
wr_mode(unsigned long *bd_lptr, unsigned long mode)
{
    unsigned long *lptr;
    lptr = bd_lptr + WR_MODE;
    *lptr = mode;
}

/* wr_width - initializes the data width on old-style fadc gate arrays
 * NOTE: this is only for version 1 gatearrays!  It's now deprecated.
 * See update_board_parameters()
 */
void 
wr_width(unsigned long *bd_lptr, unsigned long width)
{
    unsigned long *lptr;
    lptr = bd_lptr + WR_WIDTH;
    *lptr = width;
}

/* fill_ram - writes pattern into FADC bd buf ram 
 * bd_lptr is pointer to FADC bd vme address 
 * nwords is number of words written */
void 
fill_ram(unsigned long *lptr, unsigned long pattern, unsigned long nwords)
{
    unsigned long j;
    for (j = 0; j < nwords; j++){
	*lptr = pattern;
	lptr++;
    }
    if (Verbose) {
	info("filled %ld words of FADC buffer ram with %08lx pattern\n",
	     nwords, pattern);
    }
}

/* read_ram - reads nwords of data from FADC bd buf ram */
void 
read_ram(unsigned long *lptr, unsigned long nwords)
{
    unsigned long j, k;
    if (Verbose) {
	info("\n\n reading FADC buf ram: \n");
    }
    for (j = 0; j < nwords; j++){
	k = *lptr;
	if (Verbose) {
	    info("%08lx ", k); 
	}
	lptr++;
    }
}

/* wr_ch_dacs - writes WashU CFD wuthresh, wuoffs, delay, & inhibit to a chan cfd */
void 
wr_ch_dacs(unsigned long *bd_lptr, unsigned long chan,
	   unsigned long cfd_wuthresh,
	   unsigned long cfd_wuoffs,
	   unsigned long cfd_del,
	   unsigned long cfd_inh)
{
    unsigned long *lptr, val, chan_offs, i;
    chan_offs = 0x2000 + (chan * 0x10);
    lptr = bd_lptr + chan_offs + CH_DACS;
    val = (cfd_inh << 28) + (cfd_del << 24) + (cfd_wuoffs << 12) + cfd_wuthresh;
    *lptr = val;
    nap( 50 ); /* wait for DAC serialization to finish */
}

/* 
 * write cfd parameters to Utah CFD boards (added by KPK)
 * 
 * Need to combine 3 bit delay (D) + 7 bit rate pot value (R), 3 bit
 * addr/control, 12-bit dac value (W,T), mode (M) and write out three 23 bit
 * numbers. Here are the bit pattens:
 * 
 * 31 28   24   20   16   12    8    4    0
 *  |  |    |    |    |    |    |    |    |
 *  0000 0DDD 0RRR RRRR 010W WWWW WWWW WWW0    set rate fb and width dac
 *  0000 0DDD 0RRR RRRR 110T TTTT TTTT TTT0    set rate fb and threshold dac
 *  0000 0DDD 0RRR RRRR 0000 1M00 0000 0000    set rate fb and mode
 *     \----/  \--------------------------/
 *      FADC            UTAH CFD
 */
void
wr_cfd_params(unsigned long *bd_lptr, int chan, unsigned long del, 
	      unsigned long rt, unsigned long thr, unsigned long wid, 
	      unsigned long mode) {

    unsigned long *lptr, chan_offs, val=0;
    unsigned long ctl;
    
    chan_offs = 0x2000 + (chan * 0x10);
    lptr = bd_lptr + chan_offs + CH_DACS;

    /* MASK MOVE VALUES TO THE CORRECT LOCATION */
    del  = (del & 0x7)   << 24;
    rt   = (rt & 0x7f)   << 16;
    thr  = (thr & 0xfff) << 1;
    wid  = (wid & 0xfff) << 1;
    mode = ((mode & 0x1) << 10) | 0x800;

    /* WIDTH + RATE */
    ctl = 0x2 << 13;
    val = del | rt | ctl | wid ;
    *lptr = val;
    nap(10); /* wait for serializing to happen */
    
    /* THRESHOLD + RATE */
    ctl = 0x6 << 13;
    val = del | rt | ctl | thr;
    *lptr = val;
    nap(10); /* wait for serializing to happen */
    
    /* MODE + RATE */
    ctl = 0x0 << 13;
    val = del | rt | ctl | mode ;
    *lptr = val;
    nap(10); /* wait for serializing to happen */
    
}




/* wr_ch_offsets - writes area offset, area width, & data offset in chan
 * gate array  - only used by old gate arrays */
void 
wr_ch_offsets(unsigned long *bd_lptr, unsigned long chan,
	      unsigned long area_offs,
	      unsigned long area_width,
	      unsigned long data_offs)
{
    unsigned long *lptr, val, chan_offs;
    chan_offs = 0x2000 + (chan * 0x10);
    lptr = bd_lptr + chan_offs + CH_OFFSETS;
    // KPK: removed, since data offset is not longer used
    //    val = (data_offs << 20) + (area_width << 12) + area_offs;

    val = (area_width << 12) + area_offs; /* NOTE: <<12 should be <<14 in
					     next generation of gate arrays */
    *lptr = val;
    //info("chan_offs_adr = %08lx    val = %08lx\n", chan_offs, val);
}

/* wr_ch_area_discrim - writes area discrim & chan disable in chan gate array */
void 
wr_ch_area_discrim(unsigned long *bd_lptr, unsigned long chan,
		   unsigned long area_discrim, unsigned long ch_disable)
{
    unsigned long *lptr, val, chan_offs;
    chan_offs = 0x2000 + (chan * 0x10);
    lptr = bd_lptr + chan_offs + CH_AREA_DISCRIM;
    val = (ch_disable << 16) + area_discrim;
    *lptr = val;
}

/* rd_ch_scaler - reads the cfd trig scaler in chan gate array */
unsigned long 
rd_ch_scaler(unsigned long *bd_lptr, unsigned long chan)
{
    unsigned long *lptr, chan_offs, val;
    chan_offs = 0x2000 + (chan * 0x10);
    lptr = bd_lptr + chan_offs + CH_SCALER;
    val = *lptr;
    return(val);
}

/* rd_ch_stop_adr - reads the ch gate array stop adr */
unsigned long 
rd_ch_stop_adr(unsigned long *bd_lptr, unsigned long chan)
{
    unsigned long *lptr, chan_offs, val;
    chan_offs = 0x2000 + (chan * 0x10);
    lptr = bd_lptr + chan_offs + CH_STOP_ADR;
    val = *lptr;
    return(val);
}

/* rd_clk_status - reads the evt trig status, and if evt trig, waits for
 * busy to finish; returns 0 if no trig, 1 if trig not busy, & 2 if busy
 * timeout */
int
rd_clk_status(unsigned long *bd_lptr)
{
    unsigned long *lptr, status;
    unsigned long trigger,cratebusy,ext_cratebusy;
    int i;

    lptr = bd_lptr + RD_CLK_STATUS;
    status = *lptr;// & 0x000c;

    trigger = status & 0x1;

    if (trigger == 0) {
	/* no event */
	return 0;
    }
    else {
	/* Otherwise wait for the busy flags to go away...*/

	status = *lptr; /* Added extra status read to fix race
			   condition between trigger occuring and busy
			   flag being set. Eventually this should be
			   fixed in the gate array, but this works for
			   now. */
	cratebusy = (status & 0x2) >> 1;
	ext_cratebusy = (status &0x4) >> 2;
	
	for (i=0; i< EVT_DONE_LOOP_COUNT; i++) {

	    /*  	    if (trigger==1 && cratebusy==0 && ext_cratebusy==0) { */
	    if (trigger==1 && cratebusy==0) {
		/* Got an event, and all crates are finished */
		return 1;
	    }
	    status = *lptr;// & 0x000c;
	    
	    trigger = status & 0x1;
	    cratebusy = (status & 0x2) >> 1;
	    ext_cratebusy = (status &0x4) >> 2;
	    
	}

	/* Timed out, so return 2 */
	return 2;

    }

    info( "rd_clk_status: trigger flag is wrong\n");
    return 2;
}



/*********************************************************/
/* Other functions */
/*********************************************************/

/* Output an info message if verbose is defined */
void 
info( char *format, ... ) {

    if (Verbose) {
	
	va_list ptr;
	fprintf( stderr, "libfadc: ");

	va_start( ptr, format );
	vfprintf( stderr, format, ptr );
	va_end( ptr );

    }

}

void
install_interrupt_handler(void) {

    struct sigevent event;
    struct sigaction handler_act;

    
//  event.sigev_signo = SIGUSR2;  /* signal number to emit (30 = SIGUSR1) */
    event.sigev_signo = SIGRTMIN;  /* signal number to emit (30 = SIGUSR1) */
    event.sigev_notify= SIGEV_SIGNAL;
    event.sigev_value.sival_int = 0;

    sigemptyset( &handler_act.sa_mask );
    handler_act.sa_sigaction = sig_handler;
    handler_act.sa_flags = SA_SIGINFO;

    /* Install the signal handler */

    if ( sigaction( event.sigev_signo, &handler_act, NULL )) {
	perror("install_interrupt_handler: sigaction");
	fadc_exit();
    }

    /* install interrupt handler  */

    if(0 > vme_interrupt_attach(bus_handle, 
				&interrupt_handle, 
				VME_INTERRUPT_BERR,
				0,  /* vector */ 
				VME_INTERRUPT_SIGEVENT, 
				&event)) {
	perror("Error attaching to the interrupt");
	vme_term(bus_handle);
	exit(1);
    }
    info( "VME BERR* interrupt handler was installed succesfully\n" );


}

void
remove_interrupt_handler(void) {


    if(0 > vme_interrupt_release(bus_handle, interrupt_handle)){
	perror("Error releasing the interrupt");
	exit(1);
    }
}

static void 
sig_handler( int sig, siginfo_t *data, void *extra ) {

    /* set flag saying berr* occurred */

    Cblt_berr_occurred = 1;

    /* don't run with the following uncommented - just for debugging
       (it will dlow down cblts by a large factor */

/*     fprintf(stderr,"DEBUG: libfadc: GOT BERR*\n"); */

}
