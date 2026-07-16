#pragma once
#if !defined(_WIN32)
#include_next <sys/mount.h>
#else
#define MS_RDONLY 1
#define MS_NOSUID 2
#define MS_NODEV 4
#define MS_NOEXEC 8
#define MS_SYNCHRONOUS 16
#define MS_REMOUNT 32
#define MS_BIND 4096
#define MS_REC 16384
#define MS_PRIVATE 1<<18
#define MNT_DETACH 2
#ifdef __cplusplus
extern "C" {
#endif
int mount(const char* source, const char* target, const char* filesystemtype, unsigned long mountflags, const void* data);
int umount(const char* target);
int umount2(const char* target, int flags);
#ifdef __cplusplus
}
#endif
#endif
