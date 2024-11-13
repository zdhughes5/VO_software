//
// calibrate-cfd.cpp
// Karl Kosack
//
// Generates a rate vs threshold curve for all channels of an fadc board
//
// Eventually, should really use the Scott Wakely's VDAQ FADC
// interface, but for now I'll use libfadc

#include <iostream>
#include <fstream>
#include <iomanip>
#include <vector>
#include <fadc.h>
#include <unistd.h>
#include <sys/time.h>
#include <signal.h>

using namespace std;

struct Options {
 
    unsigned long ratefb;
    unsigned long width;
    unsigned long minimum;
    unsigned long maximum;
    double integration_time;
    int step;
    int board;
    unsigned long cfdmode;
    string identifier;

    void print() {
	cout << "OPTIONS: "<< endl;
	cout << "--------------------------------" << endl
	     << "BOARD ID   : "<<fadc_get_serial_number(board) << endl
	     << "RATEFB     : "<<ratefb << endl
	     << "WIDTH      : "<<width << endl
	     << "THRESHOLD  : "<<minimum<<" to "<< maximum << endl
	     << "STEP       : "<<step << endl
	     << "INTEGRATION: "<<integration_time << " sec"<< endl
	     << "IDENTIFIER : '"<<identifier<<"'"<< endl;
	if (cfdmode == 1) 
	    cout << "CFDMODE    : Constant Fraction Discriminator"  << endl;
	else 
	    cout << "CFDMODE    : Threshold Discriminator"  << endl;

    }
    
};

struct Reading {
    double time;
    unsigned long scaler;
};

vector<Reading> init_reading;

void startRateMeasurement( int board, int chan );
double getRate( int boardnum, int channel );
double getTime();
void printStatus( unsigned long thresh, double avgrate, char status[10] );
void getCommandLineArgs(int argc, char **argv, Options &opts);
void usage(Options &);
void writeGNUPlotFile( string filename, Options &opts );
void shutdown(int n);
int
main( int argc, char **argv ) {
 
    cout << "CALIBRATE-CFD" << endl;
    
    init_reading.resize(10);

    Options opts;
    
    // set defaults 
    opts.ratefb = 0;
    opts.width  = 0;
    opts.integration_time = 0.5;
    opts.board =13;
    opts.minimum = 1300;
    opts.maximum = 1500;
    opts.step = 1;
    opts.identifier = "run";
    opts.cfdmode = 1;

    getCommandLineArgs( argc, argv, opts );

    // init hardware

    fadc_init();
    fadc_verbose(0);
    fadc_set_cfd_width( opts.board, FADC_ALL, opts.width );
    fadc_set_cfd_ratefb( opts.board, FADC_ALL, opts.ratefb );
    fadc_set_cfd_mode( opts.board, FADC_ALL, opts.cfdmode );

    opts.print();

    // set up ctrl-c handler

    struct sigaction sa;

    sigfillset( &sa.sa_mask );
    sa.sa_flags = 0;
    sa.sa_handler = shutdown;
    if (sigaction(SIGINT, &sa, NULL) < 0) {
        perror( "sigaction SIGINT" );
        exit(1);
    }

 
    double rate[10];
    double integration_time[10]; 
    char status[10];


    // open output file:

    char filename[128];
    string mode;
    if (opts.cfdmode == 1)
	mode = "CFD";
    else
	mode = "THR";

    int boardid = fadc_get_serial_number( opts.board );

    sprintf( filename, "RateVsThresh-bd%03d-%s-%s.txt",
	     boardid,mode.c_str(),opts.identifier.c_str() );
    ofstream outfile( filename );

    cout << "writing to '"<< filename << "'..."<< endl;

    // write a gnuplot file for realtime plotting

    writeGNUPlotFile( filename, opts );

    // Loop over threshold 

    unsigned long thresh;
    double avgrate=0;

    for (thresh=opts.minimum; thresh<=opts.maximum; thresh+=opts.step) {

	// set integration time to nominal and clear status
	for (int i=0; i<10; i++) {
	    integration_time[i] = opts.integration_time;
	    status[i] = '.';
	}

	printStatus( thresh, avgrate, status );

	// program the CFDs
	
	fadc_set_cfd_thresh( opts.board, FADC_ALL, thresh );
	
	// get the initial time and scaler readings

	for (int i=0; i<10; i++) {
	    startRateMeasurement( opts.board, i );
	}

	// sleep for prescribed time

	usleep(static_cast<unsigned int>(opts.integration_time * 1.0e6));

	// get all the rates;

	for (int i=0; i<10; i++) {
	    rate[i] = getRate( opts.board, i );
	    if (rate[i]>=0) status[i] = '.';
	    else status[i] = 'W';
	}
	printStatus( thresh, avgrate, status );

	// Check for scaler wrapping or rate error and retry,
	// adjusting the integration time, until you get a measurement

	for (int i=0; i<10; i++) {
	    
	    if (rate[i]<0) {
		int flip=0;

		while (rate[i] < 0 ) {
		    flip = ~flip;
		    if (flip) status[i] = 'w';
		    else status[i] = 'W';
		    integration_time[i] *= 0.5; // decrease time
		    startRateMeasurement( opts.board, i );
		    usleep(static_cast<unsigned int>(integration_time[i]
						     * 1.0e6));
		    rate[i] = getRate( opts.board, i );
		    printStatus( thresh, avgrate, status );
		 
		}
		status[i] = '.';
	    }
	}

	// write out the rate and error
	
	avgrate=0;
	for (int i=0; i<10; i++) {
	    avgrate += rate[i];
	}
	avgrate /= 10.0;

	printStatus( thresh, avgrate, status );
	
	outfile << setw(10) << thresh << " ";
	for (int i=0; i<10; i++) {
	    outfile   << setw(10) << rate[i] << " "
		      << setw(10) << 1.0/integration_time[i]<<" ";
	}
	outfile << endl;
	outfile.flush();
	
    }
    
    cerr << "DONE."<<endl;
    outfile.close();

    fadc_exit();
    
}

void 
printStatus( unsigned long thresh, double avgrate, char status[10] ) {

    cerr.precision(4);
    cerr << "THRESHOLD: "<< setw(5) << thresh
	 << "   <rate>: "<< setw(10) << avgrate
	 << setw(10) << " " << "[";
    
    for (int i=0; i<10; i++) {
	cerr << status[i];
    }
    cerr << "]";
    cerr <<" \r";

}

void
startRateMeasurement( int board, int chan ) {

    init_reading[chan].time = getTime();
    init_reading[chan].scaler = fadc_get_trigger_scaler( board, chan );

}

double
getRate( int board, int chan ) {

    Reading current_reading;
    double elapsed;
    double hits;

    current_reading.time = getTime();
    current_reading.scaler = fadc_get_trigger_scaler( board, chan );

    if (current_reading.scaler < init_reading[chan].scaler) {
	return -1;
    }
   
    hits = static_cast<double>( current_reading.scaler - 
				init_reading[chan].scaler);
    elapsed = current_reading.time - init_reading[chan].time;

    //    cout << "DEBUG: cur= "<< current_reading.scaler<<" prev="<<init_reading[chan].scaler<<" hits="<<hits<<" elapsed="<< elapsed <<endl;

    return hits/elapsed;
	
}

void 
getCommandLineArgs(int argc, char **argv, Options &opts) {

    char bdflag =0;
    int c;

    while (( c = getopt( argc, argv, "Odb:l:u:s:i:t:r:w:" )) != -1 ) {
	switch (c) {
	  case 'b':
	      bdflag=1;
	      opts.board = atoi(optarg);
	      if (opts.board >= fadc_num_boards()) {
		  cout << "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" << endl;
		  cout << "That board number is out of range!" << endl;
		  cout << "Please enter a number from 0 to "<<fadc_num_boards()
		       << endl;
		  cout << "This is the SLOT number of the board in the crate!"
		       << endl;
		  cout << "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" << endl;
		  exit(1);
	      }
	      break;
	case 'l':
	    opts.minimum = atoi(optarg);
	    break;
	case 'u':
	    opts.maximum = atoi(optarg);
	    break;
	case 's':
	    opts.step = atoi(optarg);
	    break;
	case 'i':
	    opts.identifier=optarg;
	    break;
	case 't':
	    opts.integration_time = atof( optarg );
	    break;
	case 'r':
	    opts.ratefb = atoi( optarg );
	    break;
	case 'w':
	    opts.width = atoi( optarg );
	    break;
	case 'd':
	    opts.cfdmode = 0;
	    break;
	}
    }

    if (bdflag==0) {
	usage(opts);
	if (bdflag == 0 )
	    printf("You must specify a board!\n");
	exit(1);
    }
}

void
usage(Options &opts) {
    cout << "usage: calibrate-cfd -b<board> [other options]"<<endl<<endl ;
    cout << "\t-l<lower>\tlower threshold/offset setting"<<endl;
    cout << "\t-u<upper>\tupper threshold/offset setting"<<endl;
    cout << "\t-s<step>\tthreshold/offset step" << endl;
    cout << "\t-w<width>\tSet the initial cfd WIDTH ["<<opts.width<<"]"
	 <<endl;
    cout << "\t-r<ratefb>\tSet the initial cfd RateFB ["<<opts.ratefb<<"]"
	 <<endl;
    cout << "\t-i<identifier>\t tag to add to filename ["<<opts.identifier<<"]"
	 << endl;
    cout << "\t-t<seconds>\t integration time ["<<opts.integration_time<<"]"
	 << endl;
    cout << "\t-d\tuse threshold discrim mode instead of CFD mode" << endl;
    
    cout << "NOTE: the <board> option refers to the SLOT number of the "<<endl
	 << "FADC crate. Board 0 is the leftmost board." << endl;
    cout << endl<< "NOTE: This program generates a GNUPlot file which can be "
	 << endl
	 << "used to view the status of the calibration while it is running" 
	 << endl << endl;
}



/**
 * return the time in microseconds
 */
double
getTime(void) {

    double time=0;

    struct timeval tv;
    struct timezone tz;

    gettimeofday( &tv,&tz);
    
    time = tv.tv_sec + (double)tv.tv_usec/1.0e6;
    
    return time;

}


void 
writeGNUPlotFile( string filename,Options &opts ) {

    string plotfilename = filename + ".gpl";
    ofstream plotfile( plotfilename.c_str() );

    cout << "Writing GNUPlot file for realtime plotting." << endl;
    cout << "Type 'gnuplot "<<plotfilename<<"' from another terminal"<<endl;

    plotfile << "# GNUPlot file for real-time plotting of "<<filename<<endl;
    plotfile << "set data style errorbar" << endl
	     << "set ylabel 'Rate (Hz)'" << endl
	     << "set xlabel 'CFD Threshold'" << endl
	     << "set title 'Rate-vs-Threshold for FADC board "
	     <<opts.board<<" ";

    if (opts.cfdmode == 1) 
	plotfile <<" (CFD mode)'"<< endl;
    else 
    	plotfile <<" (threshold discrim mode)'"<< endl;

    plotfile << "set log y" << endl;
	     
    plotfile << "plot \\" << endl;
    for (int i=0; i<10; i++) {
	plotfile << "'"<<filename<<"' using 1:"<<(i+1)*2<<":"
		 <<(i+1)*2+1<<" title 'ch"<<i;
	if (i<9) plotfile <<"', \\" << endl;
	else plotfile <<endl;
    }

    plotfile << endl << "pause 2"<< endl;
    plotfile <<"reread" << endl;

    plotfile.close();
    
}


void
shutdown(int n) {
 
    cout << "TRAPPED CTRL-C" << endl << endl;
    fadc_verbose(1);
    fadc_exit();
    exit(0);
 
}
