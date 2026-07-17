#pragma once
#if !defined(_WIN32)
#include_next <sys/mman.h>
#else
#include <stddef.h>
#include <stdint.h>
#ifndef PROT_READ
#define PROT_READ 1
#define PROT_WRITE 2
#define PROT_EXEC 4
#define PROT_NONE 0
#endif
#ifndef MAP_SHARED
#define MAP_SHARED 1
#define MAP_PRIVATE 2
#define MAP_ANONYMOUS 0x20
#define MAP_ANON MAP_ANONYMOUS
#define MAP_FIXED 0x10
#define MAP_32BIT 0x40
#endif
#ifndef MAP_FAILED
#define MAP_FAILED ((void*)-1)
#endif
#ifndef MADV_DONTNEED
#define MADV_DONTNEED 4
#define MADV_WILLNEED 3
#define MADV_NORMAL 0
#ifndef MREMAP_MAYMOVE
#define MREMAP_MAYMOVE 1
#define MREMAP_FIXED 2
#define MREMAP_DONTUNMAP 4
#endif
#ifndef MS_SYNC
#define MS_SYNC 4
#define MS_ASYNC 1
#define MS_INVALIDATE 2
#endif
#ifndef MAP_ANON
#define MAP_ANON MAP_ANONYMOUS
#endif
#endif
#ifdef __cplusplus
extern "C" {
#endif
void* mmap(void* addr, size_t length, int prot, int flags, int fd, long long offset);
int munmap(void* addr, size_t length);
int mprotect(void* addr, size_t len, int prot);
int madvise(void* addr, size_t length, int advice);
void* mremap(void* old_addr, size_t old_size, size_t new_size, int flags, ...);
int msync(void* addr, size_t length, int flags);
void* mmap64(void* addr, size_t length, int prot, int flags, int fd, long long offset);
int mincore(void* addr, size_t length, unsigned char* vec);
#ifndef caddr_t
typedef char* caddr_t;
#endif
#ifdef __cplusplus
}
#endif
#endif
