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

LINUXLIBS = -lvme -lm
CFLAGS =  -ggdb -I../libfadc -L../libfadc -Wall 
HDR = 

# LOCATION OF LIBFADC LIBRARY:
LIBFADCDIR = ../libfadc
LIBFADC = -L$(LIBFADCDIR) -I$(LIBFADCDIR) -lfadc


all:	l3serial
#all:	clock_test magic link

clock_test: clock_test.c
	$(CC) $(CFLAGS) clock_test.c  $(LINUXLIBS) $(LIBFADC) -o clock_test

clean::
	-rm -f magic l3serial clock_test *.o *.err *.a *.lib \#* .\#* *~

magic: magic.c
	$(CC) $(CFLAGS) magic.c  $(LINUXLIBS) $(LIBFADC) -o magic

l3serial: l3serial.c kb.o
	$(CC) $(CFLAGS) l3serial.c  kb.o $(LINUXLIBS) $(LIBFADC) -o l3serial

kb.o:	kb.h

link:
	rm -f ../bin/clock_test
	rm -f ../bin/magic
	(cd ../bin; ln -s ../clock_test/magic .)
	(cd ../bin; ln -s ../clock_test/clock_test .)
