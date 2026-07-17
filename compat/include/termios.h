#pragma once
#if !defined(_WIN32)
#include_next <termios.h>
#else
#include <stdint.h>
typedef unsigned int tcflag_t;
typedef unsigned char cc_t;
typedef unsigned int speed_t;
#define NCCS 32
struct termios {
  tcflag_t c_iflag;
  tcflag_t c_oflag;
  tcflag_t c_cflag;
  tcflag_t c_lflag;
  cc_t c_cc[NCCS];
};
#define TCSANOW 0
#define TCSAFLUSH 2
#define ECHO 0000010
#define ICANON 0000002
#define ISIG 0000001
#define VMIN 16
#define VTIME 17
#ifdef __cplusplus
extern "C" {
#endif
int tcgetattr(int fd, struct termios* t);
int tcsetattr(int fd, int optional_actions, const struct termios* t);
#ifdef __cplusplus
}
#endif
#endif
