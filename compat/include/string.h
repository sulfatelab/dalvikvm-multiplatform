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
/* XSI strerror_r */
static inline int strerror_r(int errnum, char* buf, size_t buflen) {
  if (!buf || buflen == 0) return 22; /* EINVAL */
  if (strerror_s(buf, buflen, errnum) != 0) {
    /* fallback */
#ifdef _MSC_VER
    _snprintf_s(buf, buflen, _TRUNCATE, "errno %d", errnum);
#else
    snprintf(buf, buflen, "errno %d", errnum);
#endif
    return 0;
  }
  return 0;
}
#ifdef __cplusplus
}
#endif
#endif
