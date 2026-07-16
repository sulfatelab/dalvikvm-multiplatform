#pragma once
#if !defined(_WIN32)
#include_next <sys/syscall.h>
#else
/* Linux syscall numbers are meaningless on Windows; provide stubs. */
#include <stdint.h>
#define SYS_gettid 0
#define SYS_tgkill 0
#define SYS_futex 0
#define SYS_pidfd_open 0
#define SYS_pidfd_send_signal 0
#define SYS_pidfd_getfd 0
#define SYS_memfd_create 0
#define SYS_userfaultfd 0
#define __NR_ioctl 16
#define __NR_userfaultfd 323
#ifdef __cplusplus
extern "C" {
#endif
static inline long syscall(long n, ...) { (void)n; return -1; }
#ifdef __cplusplus
}
#endif
#endif
