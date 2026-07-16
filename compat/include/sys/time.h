#pragma once
#if defined(_WIN32)
#include <windows.h>
#include <time.h>
/* timeval is provided by winsock2 (included from mdvm_win64_prelude). */
#ifndef _WINSOCK2API_
#ifndef _TIMEVAL_DEFINED
#define _TIMEVAL_DEFINED
struct timeval { long tv_sec; long tv_usec; };
#endif
#endif
#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 0
#define CLOCK_MONOTONIC 1
#endif
#ifdef __cplusplus
extern "C" {
#endif
static inline int gettimeofday(struct timeval* tv, void* tz) {
  (void)tz;
  if (!tv) return -1;
  FILETIME ft; GetSystemTimeAsFileTime(&ft);
  unsigned long long t = ((unsigned long long)ft.dwHighDateTime << 32) | ft.dwLowDateTime;
  t -= 116444736000000000ULL;
  tv->tv_sec = (long)(t / 10000000ULL);
  tv->tv_usec = (long)((t % 10000000ULL) / 10ULL);
  return 0;
}
static inline int clock_gettime(int clk, struct timespec* ts) {
  (void)clk;
  if (!ts) return -1;
  struct timeval tv; gettimeofday(&tv, 0);
  ts->tv_sec = tv.tv_sec; ts->tv_nsec = tv.tv_usec * 1000L;
  return 0;
}
static inline int nanosleep(const struct timespec* req, struct timespec* rem) {
  (void)rem;
  if (!req) return -1;
  DWORD ms = (DWORD)(req->tv_sec * 1000 + req->tv_nsec / 1000000);
  if (ms == 0 && (req->tv_sec || req->tv_nsec)) ms = 1;
  Sleep(ms);
  return 0;
}
static inline struct tm* localtime_r(const time_t* t, struct tm* out) {
  if (!t || !out) return 0;
  return localtime_s(out, t) == 0 ? out : 0;
}
static inline struct tm* gmtime_r(const time_t* t, struct tm* out) {
  if (!t || !out) return 0;
  return gmtime_s(out, t) == 0 ? out : 0;
}
static inline int mingw_gettimeofday(struct timeval* tv, void* tz) {
  return gettimeofday(tv, tz);
}
#ifdef __cplusplus
}
#endif
#else
#include_next <sys/time.h>
#endif
