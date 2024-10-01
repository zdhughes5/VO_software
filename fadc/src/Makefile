TARGET = set_variance
LIBS = -lvme -L../libfadc -lfadc -lm
CFLAGS =  -ggdb -I. -Wall -I../libfadc 
HDR = 

all:	set_variance link

$(TARGET): $(HDR) $(TARGET).c
	$(CC) $(CFLAGS) $(TARGET).c  $(LIBS) -o $(TARGET)

clean:
	-rm -f $(TARGET) *.o *.err *.a *.lib \#* .\#* *~


link:
	rm -f ../bin/set_variance
	(cd ../bin; ln -s ../src/set_variance .)
