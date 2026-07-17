#pragma once
#if !defined(_WIN32)
#include_next <string.h>
#include <stdio.h>
#else
#include_next <string.h>
#include <stdio.h>
#ifdef __cplusplus
extern "C" {
#endif
static inline char* strtok_r(char* str, const char* delim, char** saveptr) {
  return strtok_s(str, delim, saveptr);
}
/* XSI strerror_r */
static inline int strerror_r(int errnum, char* buf, size_t buflen) {
  if (!buf || buflen == 0) return 22; /* EINVAL */
  if (strerror_s(buf, buflen, errnum) != 0) {
    snprintf(buf, buflen, "errno %d", errnum);
    return 0;
  }
  return 0;
}
#ifdef __cplusplus
}
#endif
#endif
