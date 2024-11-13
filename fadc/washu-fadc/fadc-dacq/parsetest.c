/*
 *   Simple C example of using fadc-parser functions
 *
 *   Karl Kosack 2001
 *
 */

#include <stdio.h>
#include <stdlib.h>

#include "fadc-parser.h"



int
main( int argc, char **argv ) {

    FILE *fp;
    fadccrate_t *crate;
    fadcdata_t data;
    int i,num=0;
    int nboards=0;
    int verbose=0;
    
    if (argc<=2) {
	printf("usage: parsetest <numboards> <filename> [verbosity level]\n\n");
	return 1;
    }
    if (argc==4) verbose = atoi(argv[3]);
    nboards = atoi(argv[1]);


    fp = fopen( argv[2], "rb" );
    crate = new_crate( nboards );
    
    while( !get_crate_event( fp, crate, verbose ) ){

	printf( "Event Numbers: REL:%d\t\t ", num );
	for (i=0; i<nboards; i++) {
	    printf("BD%d:%u\t\t ", i, crate->board[i].eventnum );
	}
	printf("\n");
	
	num++;

    }
    
    delete_crate( crate );
    
}

