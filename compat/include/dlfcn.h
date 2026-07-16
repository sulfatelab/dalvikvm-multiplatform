#pragma once
#if !defined(_WIN32)
#include_next <dlfcn.h>
#else
#include <windows.h>
#define RTLD_NOW 0
#define RTLD_LAZY 0
#define RTLD_LOCAL 0
#define RTLD_GLOBAL 0
#define RTLD_NODELETE 0
#define RTLD_NOLOAD 0
#define RTLD_DEFAULT ((void*)0)
#define RTLD_NEXT ((void*)-1)
#ifdef __cplusplus
extern "C" {
#endif
void* dlopen(const char* filename, int flag);
int dlclose(void* handle);
void* dlsym(void* handle, const char* symbol);
char* dlerror(void);
typedef struct {
  const char* dli_fname;
  void* dli_fbase;
  const char* dli_sname;
  void* dli_saddr;
} Dl_info;
int dladdr(const void* addr, Dl_info* info);
#ifdef __cplusplus
}
#endif
#endif
