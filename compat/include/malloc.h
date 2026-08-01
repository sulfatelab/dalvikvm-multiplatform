/* Project-owned: complete the Windows CRT malloc surface used by ART. */
#pragma once

#include_next <malloc.h>

#if defined(_WIN32) && defined(MDVM_WINDOWS_DEX2OAT_COMPAT)
#ifdef __cplusplus
extern "C" {
#endif

struct mallinfo {
  int arena;
  int ordblks;
  int smblks;
  int hblks;
  int hblkhd;
  int usmblks;
  int fsmblks;
  int uordblks;
  int fordblks;
  int keepcost;
};

static inline struct mallinfo mallinfo(void) {
  const struct mallinfo info = {0};
  return info;
}

#ifdef __cplusplus
}  // extern "C"
#endif
#endif
