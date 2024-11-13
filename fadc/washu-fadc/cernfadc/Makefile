TARGET = cernfadc
LIBS = -lvme -L../libfadc -lfadc -lm
CFLAGS =  -ggdb -I. -Wall -I../libfadc 
HDR = 

all:	cernfadc link

$(TARGET): $(HDR) $(TARGET).c
	$(CC) $(CFLAGS) $(TARGET).c  $(LIBS) -o $(TARGET)

clean:
	-rm -f $(TARGET) *.o *.err *.a *.lib \#* .\#* *~


link:
	rm -f ../bin/cernfadc
	(cd ../bin; ln -s ../cernfadc/cernfadc .)
