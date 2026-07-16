/* Force-included on Win64 Phase 0 TUs. */
#pragma once

#ifndef _WIN32
#error "mdvm_win64_prelude.h is for Windows targets only"
#endif

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOGDI
#define NOGDI
#endif
#ifndef _CRT_SECURE_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#endif

/* Winsock2 before windows.h: single timeval/pollfd definition. */
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <windows.h>
#ifdef CONST
#undef CONST
#endif
#ifdef __reserved
#undef __reserved
#endif
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <io.h>
#include <stdio.h>

/* POSIX reentrant RNG; Windows CRT has no rand_r. */
#ifdef __cplusplus
extern "C" {
#endif
static inline int rand_r(unsigned int* seed) {
  /* Linear congruential; not crypto. Seed updated. */
  unsigned int s = seed ? *seed : 1u;
  s = s * 1103515245u + 12345u;
  if (seed) *seed = s;
  return (int)((s >> 16) & 0x7fff);
}
#ifdef __cplusplus
}
#endif


#ifndef _MDVM_MODE_T_DEFINED
typedef unsigned short mode_t;
#define _MDVM_MODE_T_DEFINED 1
#endif

#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED
#endif

#ifndef _PID_T_DEFINED
typedef int pid_t;
#define _PID_T_DEFINED
#endif
#ifndef _ID_T_DEFINED
typedef int id_t;
#define _ID_T_DEFINED
#endif

/* Large-file types used by libziparchive / Android. */
#ifndef off64_t
typedef int64_t off64_t;
#endif

#ifndef strncasecmp
#define strncasecmp _strnicmp
#endif
#ifndef strcasecmp
#define strcasecmp _stricmp
#endif

#ifdef ERROR
#undef ERROR
#endif

/* File mode tests (sys/stat.h on Windows is incomplete vs POSIX). */
#include <sys/stat.h>
#ifndef S_ISREG
#define S_ISREG(m) (((m) & _S_IFMT) == _S_IFREG)
#endif
#ifndef S_ISDIR
#define S_ISDIR(m) (((m) & _S_IFMT) == _S_IFDIR)
#endif
#ifndef S_ISCHR
#define S_ISCHR(m) (((m) & _S_IFMT) == _S_IFCHR)
#endif
#ifndef S_ISBLK
#define S_ISBLK(m) (0)
#endif
#ifndef S_ISFIFO
#define S_ISFIFO(m) (0)
#endif
#ifndef S_ISLNK
#define S_ISLNK(m) (0)
#endif
#ifndef S_ISSOCK
#define S_ISSOCK(m) (0)
#endif

/* Map large-file I/O names. */
#ifndef lseek64
#define lseek64 _lseeki64
#endif
#ifndef fseeko
#define fseeko _fseeki64
#endif
#ifndef fseeko64
#define fseeko64 _fseeki64
#endif
#ifndef ftello
#define ftello _ftelli64
#endif
#ifndef ftello64
#define ftello64 _ftelli64
#endif
#ifndef ftruncate
#define ftruncate(fd, len) _chsize_s((fd), (len))
#endif

#ifndef PATH_MAX
#define PATH_MAX 260
#endif
#ifndef S_IRUSR
#define S_IRUSR _S_IREAD
#define S_IWUSR _S_IWRITE
#define S_IXUSR 0
#define S_IRGRP 0
#define S_IWGRP 0
#define S_IXGRP 0
#define S_IROTH 0
#define S_IWOTH 0
#define S_IXOTH 0
#define S_IRWXU (_S_IREAD|_S_IWRITE)
#define S_IRWXG 0
#define S_IRWXO 0
#define S_IXOTH 0
#endif

#include <sys/time.h>

#ifndef O_RDONLY
#define O_RDONLY 0
#define O_WRONLY 1
#define O_RDWR 2
#endif
#ifndef O_ACCMODE
#define O_ACCMODE 3
#endif


/* AOSP / glibc-isms used without includes. */
#ifndef uint
typedef unsigned int uint;
#endif
#ifndef useconds_t
typedef unsigned int useconds_t;
#endif
#ifndef __suseconds_t_defined
typedef long suseconds_t;
#define __suseconds_t_defined 1
#endif

/*
 * ART gates 64-bit runtime layouts on __LP64__. Windows x64 is LLP64
 * (long=32, pointer=64), so clang does not define __LP64__. Force it so
 * ART takes pointer-width-64 paths (monitor pool, heap, quasi-atomic).
 * Document LLP64 risk for %ld/pointer format assumptions in later phases.
 */
#ifndef __LP64__
#define __LP64__ 1
#endif

/* Prefer C11 aligned_alloc / CRT; declare posix_memalign for leftover call sites. */
#ifdef __cplusplus
extern "C" {
#endif
int posix_memalign(void** memptr, size_t alignment, size_t size);
#ifdef __cplusplus
}
#endif

#include <unistd.h>
#include <sched.h>
#include <pthread.h>
#include <ucontext.h>
#include <elf.h>
#include <link.h>
#include <signal.h>

#include <direct.h>
#ifndef mkdir
#define mkdir(path,mode) _mkdir(path)
#endif

/* minwindef.h defines CONST as const; ART dex opcodes use identifier CONST. */
#ifdef CONST
#undef CONST
#endif
#ifdef __reserved
#undef __reserved
#endif

#ifndef O_CLOEXEC
#define O_CLOEXEC 0x80000
#endif
#ifndef O_DIRECTORY
#define O_DIRECTORY 0x10000
#endif
#ifndef getpagesize
static inline int getpagesize(void) {
  SYSTEM_INFO si; GetSystemInfo(&si); return (int)si.dwPageSize;
}
#endif

/* Host-generated ART offset tables may not match Windows layout yet. */
#ifdef ASM_DEFINE
#undef ASM_DEFINE
#endif
/* If art redefine macros later, this may need to be after their define.
 * Provide a softer helper used if we redefine. */

/* XSI strerror_r for Windows CRT. */
#ifdef __cplusplus
extern "C" {
#endif
#ifndef strerror_r
static inline int mdvm_strerror_r(int errnum, char* buf, size_t buflen) {
  if (!buf || buflen == 0) return 22;
  if (strerror_s(buf, buflen, errnum) != 0) {
    snprintf(buf, buflen, "errno %d", errnum);
  }
  return 0;
}
#define strerror_r mdvm_strerror_r
#endif
#ifdef __cplusplus
}
#endif
