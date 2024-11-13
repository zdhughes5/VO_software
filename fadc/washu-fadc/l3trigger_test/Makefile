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

all:	l3trigger_test

l3trigger_test: l3trigger_test.c
	$(CC) $(CFLAGS) l3trigger_test.c  $(LINUXLIBS) $(LIBFADC) -o l3trigger_test

clean::
	-rm -f l3trigger_test *.o *.err *.a *.lib \#* .\#* *~

link:
	rm -f ../bin/l3trigger_test
	(cd ../bin; ln -s ../l3trigger_test/l3trigger_test .)
