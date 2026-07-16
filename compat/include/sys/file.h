#pragma once
#if defined(_WIN32)
#include <sys/types.h>
#define LOCK_SH 1
#define LOCK_EX 2
#define LOCK_NB 4
#define LOCK_UN 8
#ifdef __cplusplus
extern "C" {
#endif
int flock(int fd, int operation);
#ifdef __cplusplus
}
#endif

#else
#include_next <sys/file.h>
#endif
