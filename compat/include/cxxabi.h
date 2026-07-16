#pragma once
#if !defined(_WIN32)
#include_next <cxxabi.h>
#else
#ifdef __cplusplus
namespace __cxxabiv1 {
extern "C" {
char* __cxa_demangle(const char*, char*, size_t*, int*);
}
}
namespace abi = __cxxabiv1;
#endif
#endif
