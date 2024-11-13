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

TARGET = fadc-dacq
XLIBS = -L/usr/X11R6/lib -L/usr/local/lib -lXt -lXaw -lXext -lXmu -lsx 
LINUXLIBS = -L/usr/lib/vmic -lvme -lm -lpthread 
HEADERS = client.h consts.h handler.h version.h
CFLAGS =  -ggdb -I../libfadc  -L../libfadc
OBJS = fadc-parser.o

all: linux link

linux: $(TARGET).c $(OBJS)
	$(CC)  $(CFLAGS) -o $(TARGET) $(TARGET).c $(XLIBS) $(OBJS) -lfadc $(LINUXLIBS)

clean:
	-rm -f libfadc *~ *.o client $(TARGET)  core

tar:	clean
	(cd ../;  tar --exclude CVS -cf $(TARGET).tar $(TARGET))

parsetest: fadc-parser.o fadc-parser.c 
	$(CC)  $(CFLAGS) -o parsetest parsetest.c fadc-parser.o

link:
	rm -f ../bin/$(TARGET)
	(cd ../bin; ln -s ../$(TARGET)/$(TARGET) .)