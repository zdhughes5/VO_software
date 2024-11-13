
PROGS = fadc_stability reread_stability cblt_stability
LIBS = -L../libfadc -I../libfadc -lvme -lfadc -lm

all: $(PROGS) link

clean: 
	rm -f $(PROGS)

% : %.c
	gcc -o $@ $< $(LIBS) -lm


link:
	(cd ../bin; rm -f $(PROGS))
	(cd ../bin; ln -s ../fadc_stability/fadc_stability .)
	(cd ../bin; ln -s ../fadc_stability/reread_stability .)
	(cd ../bin; ln -s ../fadc_stability/cblt_stability .)
