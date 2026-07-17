#pragma once
#if !defined(_WIN32)
#include_next <poll.h>
#else
#include <winsock2.h>
#include <stdint.h>
/* Winsock2 already defines POLL* and struct pollfd. */
#ifndef nfds_t
typedef unsigned long nfds_t;
#endif
#ifdef __cplusplus
extern "C" {
#endif
int poll(struct pollfd* fds, nfds_t nfds, int timeout);
#ifdef __cplusplus
}
#endif
#endif
