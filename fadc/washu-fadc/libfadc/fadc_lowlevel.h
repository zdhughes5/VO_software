/*
      fadc_lowlevel.h                                                        
      Macros for the 10 chan FADC board & Xycom proto bd  

      CONFIGURATION FOR 3 BOARDS:
      -------------------------------------------------------
      FADC 3    = WinBase
      FADC 2    = WinBase + 0x4000 words
      FADC 1    = WinBase + 0x8000 words
      CLK BRD   = WinBase + 0xC000 words

	In general:
	FADC N    = WinBase
	FADC N-1  = WinBase + 0x4000 words
	...
	FADC 2    = WinBase + ((N-2) * 0x4000) words
	FADC 1    = WinBase + ((N-1) * 0x4000) words
	CLK BRD   = WinBase + (N+1    * 0x4000) words = 0x10000

*/

#ifndef _MISC_H
#define _MISC_H

#define FADC_OFFSET     0x4000    /* VME window offset for general bd   */
#define VME_WINDOW_SIZE 0x100000   /* size of VME window (in bytes)*/

/* note: lptr offsets are in words, not absolute address space
         so they are shifted right 2 spaces */

/* macros for DP gate array registers */

#define WR_EVT_NO       0x20a1    /* lptr offset for event number     */
#define WR_BD_NO        0x20a2    /* lptr offset for board number     */
#define WR_MODE         0x20a3    /* lptr offset for mode             */
#define WR_WIDTH        0x20a4    /* lptr offset for data width       */
#define WR_DATA_WIDTH   0x38a4    /* lptr offset for data+hilo width  */
#define WR_OTHER_WIDTH  0x38a5    /* lptr offset for ped+reread width */
#define RD_STATUS_HDR   0x20a4    /* lptr offset for status hdr       */
#define RD_BD_ID_HDR    0x20a5    /* lptr offset for board id hdr     */
#define RD_START_HDR    0x20a0    /* lptr offset for start hdr        */
#define RD_EVT_HDR      0x20a1    /* lptr offset for evt hdr          */
#define RD_HIT_HDR      0x20a2    /* lptr offset for hit hdr          */
#define RD_AREA_HDR     0x20a3    /* lptr offset for area hrd         */
#define TEMP_HI_FLAG    0x1000    /* heatsink temp is too high        */
#define WR_CLR_SCALAR   0x38cc    /* clear all channel scalars (multi)*/
#define WR_CLR_ADR_CNTR 0x27fc    /* clear buffer address counter*/
#define WR_PED_CMD      0x38cd    /* issue pedestal command (multi)*/
#define WR_REREAD_CMD   0x38ce    /* issue reread command (multi)*/
#define WR_DUMP_CMD     0x38cf    /* issue reread dump command (multi)*/


/* clk bd macros */
#define RD_CLK_STATUS   0x2007    /* Clk/triggerboard status offset  */
#define SOFT_EVT_CLR    0x2000    /* sends EVT Clear to board */
#define WR_EVENT_CLEAR  0x3ffc    /* lptr offset for event clear cmd */
#define WR_CRATE_CLEAR  0x2002    /* lptr offset for crate clear command */
#define RD_CLK_BDNUM    0x2002    /* writable clock board number register */
#define WR_CLK_BDNUM    0x2001    /* writable clock board number register */
#define RD_CLK_EVENTNUM 0x2001    /* Read the L3 event number */
#define RD_CLK_TRIGCODE 0x2002    /* clock trigger code register */
#define WR_CLK_TRIGCODE 0x2003    /* clock trigger code register */
#define WR_CLK_CLR_SCALERS 0x2004 /* write a 0 to clear the scalars */
#define RD_CLK_GPSMARK  0x2003    /* read gps second mark scaler */
#define RD_CLK_ELAPSED  0x2004    /* read elapsed time scaler */
#define RD_CLK_LIVETIME 0x2005    /* read elapsed time scaler */
#define RD_CLK_START_HDR 0x2000   /* Clk/trig board start header */

#define GOT_EVENT       1         /* event status flag                */
#define FADC_BUSY       2         /* flag indicating FADC's are busy  */

/* CBLT macros */

#define CBLT_START      0x3ffd    /* lptr offset for start cblt       */
#define CBLT_NWORDS     0x20a4    /* lptr offset for nwords register  */

/* macros for chan gate array registers */
#define CH0             0x2000    /* lptr offset for chan 0           */
#define CH1             0x2010    /* lptr offset for chan 1           */
#define CH2             0x2020    /* lptr offset for chan 2           */
#define CH3             0x2030    /* lptr offset for chan 3           */
#define CH4             0x2040    /* lptr offset for chan 4           */
#define CH5             0x2050    /* lptr offset for chan 5           */
#define CH6             0x2060    /* lptr offset for chan 6           */
#define CH7             0x2070    /* lptr offset for chan 7           */
#define CH8             0x2080    /* lptr offset for chan 8           */
#define CH9             0x2090    /* lptr offset for chan 9           */
#define CH_DATA         0x0       /* subadr for rd ch data            */
#define CH_AREA         0x1
#define CH_STOP_ADR     0x2
#define CH_SCALER       0x3
#define CH_DACS         0x1       /* subadr for dacs + delay + inh   */
#define CH_OFFSETS      0x2       /* subadr for area offset + area width
                                     + data offset */ 
#define CH_DATA_OFFS    0x5       /* subadr for hilo and data offsets */ 
#define CH_OTHER_OFFS   0x4       /* subadr for hilo and data offsets */ 
#define CH_AREA_DISCRIM 0x3       /* subadr for area discrim + ch_disable*/
#define CH_CLR_SCALER   0xc


#define WR_PEDVAR_RST      0xd    /* issue command to reset pedvar module */
#define WR_PEDVAR_1KHZ     0x6    /* issue command to enable pedvar module and set integration window frequency to 1 KHz*/
#define WR_PEDVAR_2KHZ     0x7    /* issue command to enable pedvar module and set integration window frequency to 2 KHz*/
#define WR_PEDVAR_4KHZ     0x8    /* issue command to enable pedvar module and set integration window frequency to 4 KHz*/
#define WR_PEDVAR_8KHZ     0x9    /* issue command to enable pedvar module and set integration window frequency to 8 KHz*/
#define WR_PEDVAR_16KHZ    0xa    /* issue command to enable pedvar module and set integration window frequency to 16 KHz*/
#define WR_PEDVAR_OFF      0xb    /* issue command to disable pedvar module */

struct ChanSettings {
    unsigned long area_width;
    unsigned long area_offs;
    unsigned long data_offs;     /* data offset in bytes */
    unsigned long hilo_offs;     /* hilo offset in bytes */
    unsigned long reread_offs;   /* reread offset in bytes */
    unsigned long ped_offs;      /* reread offset in bytes */
    unsigned long area_discrim;
    unsigned long cfd_wuthresh;
    unsigned long cfd_wuoffs;
    unsigned long cfd_ratefb;
    unsigned long cfd_thresh;
    unsigned long cfd_width;
    unsigned long cfd_mode;
    unsigned long cfd_del;
    unsigned long cfd_inh;
    unsigned long ch_disable;
    unsigned long cfd_type;
    unsigned long revision;      /* gate array version */
};

struct BoardSettings {
    int active;		/* nonzero if this board is to be used */
    unsigned long *lptr;	/* pointer for D32 FADC transfers    */    
    unsigned long data_width;   /* normal amount of data to return */
    unsigned long hilo_width;   /* width of hi-lo switch window */
    unsigned long reread_width; /* width of reread window */
    unsigned long ped_width;    /* width of pedestal window */
    unsigned long revision;     /* board revision number */
    struct ChanSettings chan[10];   /* info about each channel... */
};




/* Low level routines */

#ifdef __cplusplus
extern "C" {
#endif

void evt_clr(unsigned long *bd_lptr ) ;
void wr_evt_no(unsigned long *bd_lptr, unsigned long evt_no);
void wr_bd_no(unsigned long *bd_lptr, unsigned long bd_no);
void wr_mode(unsigned long *bd_lptr, unsigned long mode);
void wr_width(unsigned long *bd_lptr, unsigned long width);
void fill_ram(unsigned long *bd_lptr, unsigned long pattern,
	      unsigned long nwords);
void read_ram(unsigned long *bd_lptr, unsigned long nwords);
void wr_ch_dacs(unsigned long *bd_lptr, unsigned long chan,
		unsigned long cfd_wuthresh,
		unsigned long cfd_wuoffs,
		unsigned long cfd_del,
		unsigned long cfd_inh);

void wr_ch_offsets(unsigned long *bd_lptr, unsigned long chan,
		   unsigned long area_offs,
		   unsigned long area_width,
		   unsigned long data_offs);

void wr_ch_area_discrim(unsigned long *bd_lptr, unsigned long chan,
			unsigned long area_discrim, unsigned long ch_disable);
unsigned long rd_ch_scaler(unsigned long *bd_lptr, unsigned long chan);
unsigned long rd_ch_stop_adr(unsigned long *bd_lptr, unsigned long chan);

void wr_cfd_params(unsigned long *bd_lptr, int chan, unsigned long del, 
		   unsigned long rt, unsigned long thr, 
		   unsigned long wid, 
		   unsigned long mode);
int rd_clk_status(unsigned long *bd_lptr);

void clear_trigger_scaler(int bd, int ch);

#ifdef __cplusplus
}
#endif

#endif /* _MISC_H */


