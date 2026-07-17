#pragma once
#if !defined(_WIN32)
#include_next <sys/ioctl.h>
#else
/* Ensure Winsock FIONREAD visible when available. */
#include <winsock2.h>
#ifndef FIONREAD
#define FIONREAD 0x4004667F
#endif
#ifdef __cplusplus
extern "C" {
#endif
int ioctl(int fd, unsigned long request, ...);
#ifdef __cplusplus
}
#endif
#endif
