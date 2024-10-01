/* fadc.h */
#ifndef _FADC_H
#define _FADC_H

#include <vme/vme.h>
#include <vme/vme_api.h>

#define FADC_ALL	-1 //!< Use all channels or boards. 
#define FADC_MAX_BOARDS	17 //!< Max. no. of FADC boards in bus. 

enum operating_modes {
    FADC_MODE   =    0,    //!< reads chans hit: data & area     
    QADC_MODE   =    1,    //!< reads chans hit: area only       
    FULL_MODE   =    2,    //!< reads all 10 chans: data & area  
    WORD_MODE   =    3     //!< sequencer disabled, no reads     
};


enum cfd_types {
    CFD_UTAH,              //!< In fadc_set_cfd_type(), sets Utah interface*/
    CFD_WASHU              //!< In fadc_set_cfd_type(), sets WashU interface*/
};

enum default_settings {
    AREA_DISCRIM = 5,	//!< digital discrim threshold 0 - 255 
    AREA_OFFSET = 130,	//!< pulse to trig delay offset in bytes (2 nS/byte) 
    AREA_WIDTH = 16,	//!< pulse width in bytes (2 nS/byte) 
    CFD_WUTHRESH = 2440,//!< WashU CFD thresh value
    CFD_WUOFFS = 2400,  //!< WashU CFD offset value
    CFD_RATEFB = 100,   //!< 7 bit Potentiometer on CFD 
    CFD_THRESH = 3000,  //!< 12 bit threshold DAC on CFD 
    CFD_WIDTH = 1497,   //!< 12 bit L1 trigger width DAC on CFD 
    CFD_MODE = 1,       //!< 1 bit mode (1=cfd 0=discrim) 
    CFD_DEL = 0,        //!< programmable delay 
    DATA_OFFSET = 8,	//!< data offset in bytes 
    DATA_WIDTH = 32,	//!< pulse data width in 32-bit words 
};

#define CLOCKBOARD -1

#ifdef __cplusplus
extern "C" {
#endif
    
    void fadc_ignore_board(int boardnum); 

    void fadc_set_initial_values(unsigned long _data_width, 
				 unsigned long _area_width,
				 unsigned long _area_offset, 
				 unsigned long _area_discrim);

    int fadc_init(void);
    void fadc_exit(void);
    int fadc_detect_board( int boardnum );
    int fadc_is_board_present( int boardnum );

    int fadc_save_settings( int boardnum, char *filename );
    int fadc_load_settings( int boardnum, char *filename );
    
    int fadc_disable_channel( int boardnum, int chan );
    int fadc_enable_channel( int boardnum, int chan );
    int fadc_is_channel_disabled( int boardnum, int chan );
    void fadc_set_mode(int boardnum, int mode);

    /* Routines for Clock/Trigger and broadcast commands */
    
    unsigned long fadc_data_available(int boardnum);
    int fadc_got_event(void);
    void fadc_evt_clr(void);
    int fadc_get_max_evt_size(int boardnum);
    unsigned long fadc_get_serial_number( int boardnum );
    unsigned long fadc_get_livetime_scaler();
    unsigned long fadc_get_elapsed_scaler();

    /* Data Transfer */
    int fadc_num_boards(void);
    int fadc_memcpy(unsigned long *dest, int boardnum, unsigned long nwords);
    unsigned long* fadc_alloc_cblt_buffer(int maxwords, int first, int last);
    int fadc_cblt();

    /* Settings */
    
    unsigned long fadc_get_data_width( int boardnum );
    void fadc_set_data_width( int boardnum, unsigned long val );

    unsigned long fadc_get_pedestal_width( int boardnum );
    void fadc_set_pedestal_width( int boardnum, unsigned long val );

    unsigned long fadc_get_reread_width( int boardnum );
    void fadc_set_reread_width( int boardnum, unsigned long val );

    unsigned long fadc_get_hilo_width( int boardnum );
    void fadc_set_hilo_width( int boardnum, unsigned long val );

    unsigned long fadc_get_area_discrim(int boardnum, int chan);
    void fadc_set_area_discrim(int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_area_offset(int boardnum, int chan);
    void fadc_set_area_offset(int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_data_offset(int boardnum, int chan);
    void fadc_set_data_offset(int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_area_width(int boardnum, int chan);
    void fadc_set_area_width(int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_reread_offset(int boardnum, int chan);
    void fadc_set_reread_offset(int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_hilo_offset(int boardnum, int chan);
    void fadc_set_hilo_offset(int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_pedestal_offset(int boardnum, int chan);
    void fadc_set_pedestal_offset(int boardnum, int chan, unsigned long val);

    unsigned long fadc_get_trigger_scaler(int boardnum, int chan);
    int fadc_clear_trigger_scaler(int boardnum, int chan);
    void fadc_multicast_clear_trigger_scaler();

    void fadc_verbose(int state);
    
    int fadc_buffer_ram_test(int boardnum);
    
    int fadc_set_cfd_delay( int boardnum, int chan, unsigned long val );
    unsigned long fadc_get_cfd_delay( int boardnum, int chan );
    
    /* Routines for low-level access of the FADC board */
    unsigned long* fadc_get_fadc_lptr( int boardnum );
    unsigned long* fadc_get_clk_lptr(void);
    unsigned long* fadc_get_magic_lptr(void);
    unsigned long* fadc_get_l3serial_lptr(void);

    /* window requests */

    void fadc_request_pedestal();
    void fadc_request_reread();
    void fadc_request_dump();
        
    /* Utah CFD routines */
    int fadc_set_cfd_ratefb( int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_cfd_ratefb( int boardnum, int chan);
    int fadc_set_cfd_thresh( int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_cfd_thresh( int boardnum, int chan );
    int fadc_set_cfd_width( int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_cfd_width( int boardnum, int chan);
    int fadc_set_cfd_mode( int boardnum, int chan, unsigned long mode );

    
    /* washu CFD routines */
    unsigned long fadc_get_cfd_wuthresh( int boardnum, int chan);
    int fadc_set_cfd_wuthresh( int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_cfd_wuoffs( int boardnum, int chan);
    int fadc_set_cfd_wuoffs( int boardnum, int chan, unsigned long val);
    int fadc_set_cfd_type( int boardnum, int chan, unsigned long val);
    unsigned long fadc_get_cfd_type( int boardnum, int chan );

    void set_pedvar_reset();
    void set_pedvar_1khz();
    void set_pedvar_2khz();
    void set_pedvar_4khz();
    void set_pedvar_8khz();
    void set_pedvar_16khz();
    void set_pedvar_off();

    /* for debugging */
    vme_bus_handle_t fadc_get_bus_handle();
    vme_dma_handle_t fadc_get_dma_handle();
    
#ifdef __cplusplus
}
#endif

#endif /* _FADC_H */


