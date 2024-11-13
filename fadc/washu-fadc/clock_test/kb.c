/* Miscellaneous tty routines 
 *
 * echo_off, echo_on, set_keypress(int noecho), reset_keypress(),
 * int keypress()
 *
 * Originally from the unix programmer's FAQ. The html
 * version was found at http://www.whitefang.com/unix/faq_toc.html
 *
 * Slightly modified by Marty Olevitch, Aug 1999
 */

#include <stdlib.h>
#include <stdio.h>
#include <errno.h>

#include <termios.h>
#include <string.h>

#include <sys/select.h>

static struct termios Old;
static struct termios Old_echo;

void 
echo_off(void)
{
    struct termios new;
    tcgetattr(0, &Old_echo);
    memcpy(&new, &Old_echo, sizeof(struct termios));
    new.c_lflag &= (~ECHO);
    tcsetattr(0, TCSANOW, &new);
}

void 
echo_on(void)
{
    tcsetattr(0, TCSANOW, &Old_echo);
}

void 
set_keypress(int noecho)
{
    struct termios new;

    tcgetattr(0, &Old);

    memcpy(&new, &Old, sizeof(struct termios));

    /* Disable canonical mode, and set buffer size to 1 byte */
    new.c_lflag &= (~ICANON);
    new.c_cc[VTIME] = 0;
    new.c_cc[VMIN] = 1;

    if (noecho) {
	new.c_lflag &= (~ECHO);
    }

    tcsetattr(0, TCSANOW, &new);
}

void 
reset_keypress(void)
{
    tcsetattr(0, TCSANOW, &Old);
}

int
kbhit(void)
{
    struct timeval t;
    fd_set f;

    t.tv_sec = t.tv_usec = 0L;
    FD_ZERO(&f);
    FD_SET(0, &f);
    if (select(1, &f, NULL, NULL, &t) == -1) {
	return -1;
    }
    return FD_ISSET(0, &f);
}
