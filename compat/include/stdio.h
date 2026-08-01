#pragma once

#include_next <stdio.h>

#if defined(_WIN32)
#include <sys/types.h>
#ifdef __cplusplus
extern "C" {
#endif
ssize_t getline(char** lineptr, size_t* capacity, FILE* stream);
#ifdef __cplusplus
}
#endif
#endif
