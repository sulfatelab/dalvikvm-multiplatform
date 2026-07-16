#pragma once
#if !defined(_WIN32)
#include_next <sys/ioctl.h>
#else
#ifdef __cplusplus
extern "C" {
#endif
int ioctl(int fd, unsigned long request, ...);
#ifdef __cplusplus
}
#endif
#endif
