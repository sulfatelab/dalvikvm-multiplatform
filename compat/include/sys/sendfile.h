#pragma once
#include <stddef.h>
#include <stdint.h>
#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED
#endif
#ifdef __cplusplus
extern "C" {
#endif
ssize_t sendfile(int out_fd, int in_fd, long long* offset, size_t count);
ssize_t sendfile64(int out_fd, int in_fd, long long* offset, size_t count);
#ifdef __cplusplus
}
#endif
