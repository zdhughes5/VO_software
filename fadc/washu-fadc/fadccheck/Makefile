TARGET = fadccheck
LIBS = -lvme -L../libfadc -lfadc -lm
CFLAGS =  -ggdb -I. -Wall -I../libfadc 
HDR = 

all:	fadccheck link

$(TARGET): $(HDR) $(TARGET).c
	$(CC) $(CFLAGS) $(TARGET).c  $(LIBS) -o $(TARGET)

clean:
	-rm -f $(TARGET) *.o *.err *.a *.lib \#* .\#* *~


link:
	rm -f ../bin/fadccheck
	(cd ../bin; ln -s ../fadccheck/fadccheck .)