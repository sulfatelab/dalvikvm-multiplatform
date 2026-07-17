#pragma once
/* Win64: no sendfile(2); declare nothing — callers must be ifndef'd or not used. */
#include <stddef.h>
#include <sys/types.h>
#ifdef __cplusplus
extern "C" {
#endif
/* ssize_t sendfile(int out_fd, int in_fd, off_t* offset, size_t count); — unimplemented */
#ifdef __cplusplus
}
#endif
