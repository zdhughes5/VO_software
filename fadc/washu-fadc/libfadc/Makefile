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

TARGET = libfadc
CFLAGS =  -ggdb -I../libfadc -L../libfadc
HDR =  fadc.h fadc_lowlevel.h

all: linux

linux: libfadc.o
	ar crv libfadc.a libfadc.o
	ranlib libfadc.a

libfadc.o: $(HDR) libfadc.c
	$(CC) $(CFLAGS) -c libfadc.c  

clean:
	-rm -f $(TARGET) *.o *.err *.a *.lib \#* .\#* *~

doc: clean
	doxygen libfadc.dox

backup: clean 
	(cd ..; tar cvfz $(TARGET)-`date +%Y-%m-%d`.tar.gz $(TARGET)/)


install: linux
	ln -s libfadc.a /usr/local/lib/
	ln -s fadc.h /usr/local/include/
	ln -s fadc_lowlevel.h /usr/local/include/