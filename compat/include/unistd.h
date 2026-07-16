/* Project-owned: Win64 shim; on other OS forward to system. */
#pragma once
#if defined(_WIN32)
#include <errno.h>
#include <io.h>
#include <direct.h>
#include <process.h>
#include <stddef.h>
#include <stdint.h>

/*
 * UCRT already declares POSIX-ish names (write/read/close/access/lseek/...)
 * under !__STDC__ (see corecrt_io.h). Do NOT #define write->_write etc:
 * that rewrites C++ member names like std::ostream::write into ostream::_write
 * and breaks linking against libc++.
 */

#ifndef useconds_t
typedef unsigned int useconds_t;
#endif
#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED
#endif
#ifndef STDIN_FILENO
#define STDIN_FILENO 0
#define STDOUT_FILENO 1
#define STDERR_FILENO 2
#endif
#ifndef F_OK
#define F_OK 0
#define X_OK 1
#define W_OK 2
#define R_OK 4
#endif

#ifdef __cplusplus
extern "C" {
#endif

__declspec(dllimport) void __stdcall Sleep(unsigned long dwMilliseconds);
ssize_t pread(int fd, void* buf, size_t count, long long offset);
ssize_t pwrite(int fd, const void* buf, size_t count, long long offset);
int usleep(useconds_t usec);

#ifndef _SC_PAGESIZE
#define _SC_PAGESIZE 30
#define _SC_PAGE_SIZE _SC_PAGESIZE
#define _SC_NPROCESSORS_CONF 83
#define _SC_NPROCESSORS_ONLN 84
#define _SC_PHYS_PAGES 85
#define _SC_CLK_TCK 2
#endif
long sysconf(int name);
int pipe(int fds[2]);
unsigned int getuid(void);
unsigned int geteuid(void);

pid_t fork(void);
int setpgid(pid_t pid, pid_t pgid);
pid_t getppid(void);
pid_t getpgrp(void);
int unshare(int flags);
char* realpath(const char* path, char* resolved);
/* access/close/read/write/lseek/unlink/getcwd/getpid/isatty: UCRT */

#ifdef __cplusplus
}
#endif

static inline unsigned sleep(unsigned seconds) {
  Sleep(seconds * 1000u);
  return 0;
}

#ifdef __cplusplus
#ifndef TEMP_FAILURE_RETRY
#define TEMP_FAILURE_RETRY(exp)            \
  ({                                       \
    decltype(exp) _rc;                     \
    do {                                   \
      _rc = (exp);                         \
    } while (_rc == -1 && errno == EINTR); \
    _rc;                                   \
  })
#endif
#endif
#else
#include_next <unistd.h>
#endif
