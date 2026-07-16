#pragma once
#if defined(_WIN32)
#include <windows.h>
static inline int sched_yield(void) { SwitchToThread(); return 0; }
#define CLONE_VM 0x00000100
#define CLONE_FS 0x00000200
#define CLONE_FILES 0x00000400
#define CLONE_SIGHAND 0x00000800
#define CLONE_PTRACE 0x00002000
#define CLONE_VFORK 0x00004000
#define CLONE_PARENT 0x00008000
#define CLONE_THREAD 0x00010000
#define CLONE_NEWNS 0x00020000
#define CLONE_SYSVSEM 0x00040000
#define CLONE_SETTLS 0x00080000
#define CLONE_PARENT_SETTID 0x00100000
#define CLONE_CHILD_CLEARTID 0x00200000
#define CLONE_DETACHED 0x00400000
#define CLONE_UNTRACED 0x00800000
#define CLONE_CHILD_SETTID 0x01000000
#define CLONE_NEWCGROUP 0x02000000
#define CLONE_NEWUTS 0x04000000
#define CLONE_NEWIPC 0x08000000
#define CLONE_NEWUSER 0x10000000
#define CLONE_NEWPID 0x20000000
#define CLONE_NEWNET 0x40000000
#define SCHED_OTHER 0
#define SCHED_FIFO 1
#define SCHED_RR 2
struct sched_param { int sched_priority; };
static inline int sched_getscheduler(int pid) { (void)pid; return SCHED_OTHER; }
static inline int sched_setscheduler(int pid, int policy, const struct sched_param* p) { (void)pid;(void)policy;(void)p; return 0; }
static inline int sched_getparam(int pid, struct sched_param* p) { if(p) p->sched_priority=0; (void)pid; return 0; }

#else
#include_next <sched.h>
#endif
