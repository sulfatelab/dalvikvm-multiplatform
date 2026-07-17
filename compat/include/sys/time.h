#pragma once
#if !defined(_WIN32)
#include_next <sys/time.h>
#else
#ifndef _WINSOCKAPI_
#include <winsock2.h>
#endif
/* timeval comes from winsock2 */
#ifdef __cplusplus
extern "C" {
#endif
int gettimeofday(struct timeval* tv, void* tz);
#ifdef __cplusplus
}
#endif
#endif
