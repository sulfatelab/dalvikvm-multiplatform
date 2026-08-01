#pragma once

#include_next <stdlib.h>

#if defined(_WIN32)
#ifdef __cplusplus
extern "C" {
#endif
int posix_memalign(void** memptr, size_t alignment, size_t size);
#ifdef __cplusplus
}
#endif
#endif
