#pragma once
#if defined(_WIN32)
#include <string.h>
#ifdef __cplusplus
extern "C" {
#endif
static inline char* basename(char* path) {
  if (!path || !*path) return path;
  char* p = strrchr(path, '\\');
  char* q = strrchr(path, '/');
  if (q > p) p = q;
  return p ? p + 1 : path;
}
static inline char* dirname(char* path) {
  if (!path || !*path) return path;
  char* p = strrchr(path, '\\');
  char* q = strrchr(path, '/');
  if (q > p) p = q;
  if (!p) { path[0] = '.'; path[1] = 0; return path; }
  *p = 0;
  return path;
}
#ifdef __cplusplus
}
#endif

#else
#include_next <libgen.h>
#endif
