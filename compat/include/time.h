#pragma once
#if !defined(_WIN32)
#include_next <time.h>
#else
#include_next <time.h>
#ifndef CLOCK_REALTIME
#define CLOCK_REALTIME 0
#define CLOCK_MONOTONIC 1
#endif
#ifndef _CLOCKID_T_DEFINED
typedef int clockid_t;
#define _CLOCKID_T_DEFINED
#endif
#ifdef __cplusplus
extern "C" {
#endif
int clock_gettime(clockid_t clk_id, struct timespec* tp);
int nanosleep(const struct timespec* req, struct timespec* rem);
struct tm* localtime_r(const time_t* timep, struct tm* result);
#ifdef __cplusplus
}
#endif
#endif
