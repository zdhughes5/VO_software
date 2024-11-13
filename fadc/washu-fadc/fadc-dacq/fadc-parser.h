#ifndef _FADC_PARSER_H
#define _FADC_PARSER_H


#define EVENT_BUF_SIZE 1024
#define MAX_NSAMP 2048


typedef struct {

    unsigned long boardnum;
    unsigned long eventnum;
    int           ndatawords;
    unsigned long hitpattern;
    unsigned long trigpattern;
    unsigned long hilopattern;
    int           nsamp;
    unsigned char pulse[10][MAX_NSAMP];
    unsigned long hardarea[10];

} fadcdata_t;


typedef struct {

    int numboards;
    int curbdnum;       
    fadcdata_t *board;

} fadccrate_t;


fadccrate_t* new_crate( int nboards );
void delete_crate( fadccrate_t *crate );
int get_event( FILE *fp, fadcdata_t *crate, char );
int get_crate_event( FILE *fp, fadccrate_t *crate, char verbose);
void binary_print(unsigned long word);
void parseerror(fadcdata_t *evt,char *format, ...);

#endif



