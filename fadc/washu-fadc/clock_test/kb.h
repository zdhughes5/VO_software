/* kb.h - kbhit() equivalent for posix */

void echo_off(void);
void echo_on(void);
void set_keypress(int noecho);
void reset_keypress(void);
int kbhit(void);
