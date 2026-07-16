#pragma once
#if !defined(_WIN32)
#include_next <poll.h>
#else
#include <stdint.h>
/* Winsock2 already defines POLL* and struct pollfd when included. */
#ifndef POLLIN
#define POLLIN 0x001
#define POLLPRI 0x002
#define POLLOUT 0x004
#define POLLERR 0x008
#define POLLHUP 0x010
#define POLLNVAL 0x020
#define POLLRDNORM 0x040
#define POLLWRNORM 0x100
struct pollfd {
  int fd;
  short events;
  short revents;
};
#endif
#ifndef nfds_t
typedef unsigned long nfds_t;
#endif
#ifdef __cplusplus
extern "C" {
#endif
/* Note: winsock pollfd uses SOCKET; for CRT fds our stub is best-effort. */
int poll(struct pollfd* fds, nfds_t nfds, int timeout);
#ifdef __cplusplus
}
#endif
#endif
