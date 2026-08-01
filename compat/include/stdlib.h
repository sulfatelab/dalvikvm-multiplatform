#pragma once

#include_next <stdlib.h>

#if defined(_WIN32)
#ifdef __cplusplus
extern "C" {
#endif
int posix_memalign(void** memptr, size_t alignment, size_t size);
static inline int rand_r(unsigned int* seed) {
  unsigned int state = seed != NULL ? *seed : 1u;
  state = state * 1103515245u + 12345u;
  if (seed != NULL) {
    *seed = state;
  }
  return (int)((state >> 16) & 0x7fff);
}
#ifdef __cplusplus
}
#endif
#endif
