#pragma once
#if !defined(_WIN32)
#include_next <sys/resource.h>
#else
#include <stdint.h>
#include <sys/time.h>
#define RLIMIT_CPU 0
#define RLIMIT_FSIZE 1
#define RLIMIT_DATA 2
#define RLIMIT_STACK 3
#define RLIMIT_CORE 4
#define RLIMIT_RSS 5
#define RLIMIT_NOFILE 7
#define RLIMIT_AS 9
#define RLIMIT_NPROC 6
#define RLIMIT_MEMLOCK 8
#define RLIM_INFINITY (~0ULL)
typedef uint64_t rlim_t;
struct rlimit {
  rlim_t rlim_cur;
  rlim_t rlim_max;
};
struct rusage {
  struct timeval ru_utime;
  struct timeval ru_stime;
  long ru_maxrss;
  long ru_ixrss;
  long ru_idrss;
  long ru_isrss;
  long ru_minflt;
  long ru_majflt;
  long ru_nswap;
  long ru_inblock;
  long ru_oublock;
  long ru_msgsnd;
  long ru_msgrcv;
  long ru_nsignals;
  long ru_nvcsw;
  long ru_nivcsw;
};
#define RUSAGE_SELF 0
#define RUSAGE_CHILDREN -1
#define RUSAGE_THREAD 1
#define PRIO_PROCESS 0
#define PRIO_PGRP 1
#define PRIO_USER 2
#define PRIO_MIN -20
#define PRIO_MAX 20
#ifdef __cplusplus
extern "C" {
#endif
int getrlimit(int resource, struct rlimit* rlim);
int setrlimit(int resource, const struct rlimit* rlim);
int getrusage(int who, struct rusage* usage);
int getpriority(int which, int who);
int setpriority(int which, int who, int prio);
#ifdef __cplusplus
}
#endif
#endif
