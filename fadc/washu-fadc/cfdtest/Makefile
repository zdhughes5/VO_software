#
# CFLAGS - Command-Line options
#
# -c			 - Compile to object file (foo.o)
# -g  			 - Debug turned on (Add symbols, etc).
# -T1 			 - Compile with privity (poking at QNX hardware)
# -w3 			 - Whine a lot during compile (Lots of 'C' warnings)
# -I=$(INC_DIRS) - Include this path list for #include files
# -zu -Wc 		 - Disable stack checking.
#

LIBS = -L../libfadc -I../libfadc -lvme -lfadc -lm
CFLAGS =  -ggdb  -Wall 
HDR = 

all:	cfdtest calibrate-cfd

cfdtest: $(HDR) cfdtest.c
	$(CC) $(CFLAGS) cfdtest.c  $(LIBS) -o cfdtest


calibrate-cfd: $(HDR) calibrate-cfd.cpp
	g++ $(CFLAGS) calibrate-cfd.cpp  $(LIBS) -o calibrate-cfd

clean:
	-rm -f cfdtest calibrate-cfd *.o *.err *.a *.lib \#* .\#* *~


