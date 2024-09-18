// gcc server.c -lfadc -lvme -lm -o server

#include <stdio.h>
#include <stdlib.h>

// VME/FADC libraries.
#include <vme/vme_api.h>
#include <fadc_lowlevel.h>  /* needed to access low-level routines */
#include <fadc.h>

#define DMA_BUFSIZE     16384   /* dma buffer size in bytes */

int Boardnum;
int Boardnum=-1;
int Boardnum7 = 7;
int Boardnum8 = 8;
int Boardnum9 = 9;
int Firstboard = -1;  /* default to clock board*/
int Lastboard = 9;

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <option>\n", argv[0]);
        fprintf(stderr, "Options: 1, 2, 4, 8, or 16\n");
        exit(1);
    }

    int option = atoi(argv[1]);
    if (option != 1 && option != 2 && option != 4 && option != 8 && option != 16) {
        fprintf(stderr, "Invalid option. Options: 1, 2, 4, 8, or 16\n");
        exit(1);
    }

    int low, high, numboards;

    fadc_init();
    fadc_verbose(1);
    atexit( fadc_exit );

    low = 999;
    high = -999;
    numboards = 0;
    for (i = 0; i < fadc_num_boards(); i++) {
        if (fadc_is_board_present(i)) {
	        if (i < low) low = i;
	        if (i >= high) high = i;
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

    printf( "CBLT: Firstboard=%d, Lastboard=%d\n", Firstboard, Lastboard);

for (i = 0; i < fadc_num_boards(); i++) {
    if (fadc_is_board_present(i)) {
        fadc_set_mode(i, WORD_MODE);
        set_pedvar_reset();

        switch (option) {
            case 1:
                set_pedvar_1khz();
                break;
            case 2:
                set_pedvar_2khz();
                break;
            case 4:
                set_pedvar_4khz();
                break;
            case 8:
                set_pedvar_8khz();
                break;
            case 16:
                set_pedvar_16khz();
                break;
            default:
                fprintf(stderr, "Unexpected option: %d\n", option);
                exit(1);
        }

        fadc_set_mode(i, FADC_MODE);
        printf("pedvar %dkHz set on board %d\n", option, i);
    }
}

    exit(0);
}