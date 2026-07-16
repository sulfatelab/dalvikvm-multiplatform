#include <windows.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#ifndef ENOSYS
#define ENOSYS 40
#endif
#ifndef ESRCH
#define ESRCH 3
#endif
#ifndef EAGAIN
#define EAGAIN 11
#endif
#ifndef ETIMEDOUT
#define ETIMEDOUT 138
#endif
#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <link.h>
#include <time.h>
#ifndef PATH_MAX
#define PATH_MAX 260
#endif
struct utsname { char sysname[65],nodename[65],release[65],version[65],machine[65],domainname[65]; };

typedef unsigned long long rlim_t;
struct rlimit { rlim_t rlim_cur; rlim_t rlim_max; };
struct rusage {
  struct timeval ru_utime;
  struct timeval ru_stime;
  long ru_maxrss, ru_ixrss, ru_idrss, ru_isrss;
  long ru_minflt, ru_majflt, ru_nswap, ru_inblock, ru_oublock;
  long ru_msgsnd, ru_msgrcv, ru_nsignals, ru_nvcsw, ru_nivcsw;
};
struct statvfs { unsigned long f_bsize,f_frsize; unsigned long long f_blocks,f_bfree,f_bavail,f_files,f_ffree,f_favail; unsigned long f_fsid,f_flag,f_namemax; };
typedef struct { const char* dli_fname; void* dli_fbase; const char* dli_sname; void* dli_saddr; } Dl_info;
#include <sys/stat.h>
struct FTW { int base; int level; };


/* --- pthread --- */
typedef CRITICAL_SECTION pthread_mutex_t;
typedef int pthread_mutexattr_t;
typedef DWORD pthread_t;
typedef DWORD pthread_key_t;
typedef LONG pthread_once_t;

int pthread_mutex_init(pthread_mutex_t* m, const pthread_mutexattr_t* a) {
  (void)a; InitializeCriticalSection(m); return 0;
}
int pthread_mutex_destroy(pthread_mutex_t* m) { DeleteCriticalSection(m); return 0; }
int pthread_mutex_lock(pthread_mutex_t* m) { EnterCriticalSection(m); return 0; }
int pthread_mutex_unlock(pthread_mutex_t* m) { LeaveCriticalSection(m); return 0; }
int pthread_mutex_trylock(pthread_mutex_t* m) {
  return TryEnterCriticalSection(m) ? 0 : EBUSY;
}
int pthread_key_create(pthread_key_t* k, void (*d)(void*)) {
  (void)d; DWORD t = TlsAlloc(); if (t == TLS_OUT_OF_INDEXES) return EAGAIN;
  *k = t; return 0;
}
int pthread_key_delete(pthread_key_t k) { return TlsFree(k) ? 0 : EINVAL; }
void* pthread_getspecific(pthread_key_t k) { return TlsGetValue(k); }
int pthread_setspecific(pthread_key_t k, const void* v) {
  return TlsSetValue(k, (LPVOID)v) ? 0 : EINVAL;
}
pthread_t pthread_self(void) { return GetCurrentThreadId(); }
int pthread_equal(pthread_t a, pthread_t b) { return a == b; }
int pthread_once(pthread_once_t* once, void (*init)(void)) {
  if (InterlockedCompareExchange(once, 1, 0) == 0) init();
  return 0;
}

/* --- dirent --- */
struct dirent { unsigned long d_ino; char d_name[260]; };
struct DIR { HANDLE h; WIN32_FIND_DATAA f; int first; struct dirent ent; };
typedef struct DIR DIR;

DIR* opendir(const char* name) {
  char pattern[MAX_PATH + 4];
  _snprintf(pattern, sizeof(pattern), "%s\\*", name);
  DIR* d = (DIR*)calloc(1, sizeof(DIR));
  if (!d) return NULL;
  d->h = FindFirstFileA(pattern, &d->f);
  if (d->h == INVALID_HANDLE_VALUE) { free(d); return NULL; }
  d->first = 1;
  return d;
}
struct dirent* readdir(DIR* d) {
  if (!d) return NULL;
  if (!d->first) {
    if (!FindNextFileA(d->h, &d->f)) return NULL;
  }
  d->first = 0;
  memset(d->ent.d_name, 0, sizeof(d->ent.d_name));
  strncpy(d->ent.d_name, d->f.cFileName, sizeof(d->ent.d_name) - 1);
  return &d->ent;
}
int closedir(DIR* d) {
  if (!d) return -1;
  FindClose(d->h);
  free(d);
  return 0;
}

int ftw(const char* path, int (*fn)(const char*, const struct stat*, int), int fd_limit) {
  (void)path; (void)fn; (void)fd_limit; return -1;
}
int nftw(const char* path, int (*fn)(const char*, const struct stat*, int, struct FTW*),
         int fd_limit, int flags) {
  (void)path; (void)fn; (void)fd_limit; (void)flags; return -1;
}

int flock(int fd, int operation) { (void)fd; (void)operation; return 0; }
int pthread_setname_np(unsigned long t, const char* name) { (void)t; (void)name; return 0; }

#include <io.h>
typedef long long off64_t;
typedef intptr_t ssize_t;
ssize_t pread(int fd, void* buf, size_t count, long long offset) {
  long long cur = _lseeki64(fd, 0, 1);
  if (cur < 0) return -1;
  if (_lseeki64(fd, offset, 0) < 0) return -1;
  int n = _read(fd, buf, (unsigned int)count);
  _lseeki64(fd, cur, 0);
  return n;
}
ssize_t pwrite(int fd, const void* buf, size_t count, long long offset) {
  long long cur = _lseeki64(fd, 0, 1);
  if (cur < 0) return -1;
  if (_lseeki64(fd, offset, 0) < 0) return -1;
  int n = _write(fd, buf, (unsigned int)count);
  _lseeki64(fd, cur, 0);
  return n;
}

static char g_dlerror[256];
void* dlopen(const char* filename, int flag) {
  (void)flag;
  if (!filename) return GetModuleHandleA(NULL);
  HMODULE h = LoadLibraryA(filename);
  if (!h) snprintf(g_dlerror, sizeof(g_dlerror), "LoadLibraryA(%s) failed: %lu", filename, GetLastError());
  else g_dlerror[0]=0;
  return (void*)h;
}
int dlclose(void* handle) {
  if (!handle) return -1;
  return FreeLibrary((HMODULE)handle) ? 0 : -1;
}
void* dlsym(void* handle, const char* symbol) {
  HMODULE h = (HMODULE)handle;
  if (!h) h = GetModuleHandleA(NULL);
  void* p = (void*)GetProcAddress(h, symbol);
  if (!p) snprintf(g_dlerror, sizeof(g_dlerror), "GetProcAddress(%s) failed", symbol);
  else g_dlerror[0]=0;
  return p;
}
char* dlerror(void) { return g_dlerror[0] ? g_dlerror : NULL; }

void* mmap(void* addr, size_t length, int prot, int flags, int fd, long long offset) {
  (void)addr;(void)prot;(void)flags;(void)fd;(void)offset;
  void* p = VirtualAlloc(NULL, length, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE);
  return p ? p : (void*)(intptr_t)-1;
}
int munmap(void* addr, size_t length) {
  (void)length;
  return VirtualFree(addr, 0, MEM_RELEASE) ? 0 : -1;
}
int mprotect(void* addr, size_t len, int prot) {
  DWORD old_prot = 0;
  DWORD np = PAGE_NOACCESS; /* PROT_NONE */
  const int r = (prot & 1) != 0; /* PROT_READ */
  const int w = (prot & 2) != 0; /* PROT_WRITE */
  const int x = (prot & 4) != 0; /* PROT_EXEC */
  if (x && w) np = PAGE_EXECUTE_READWRITE;
  else if (x && r) np = PAGE_EXECUTE_READ;
  else if (x) np = PAGE_EXECUTE;
  else if (w) np = PAGE_READWRITE;
  else if (r) np = PAGE_READONLY;
  else np = PAGE_NOACCESS;
  if (!VirtualProtect(addr, len, np, &old_prot)) {
    errno = EINVAL;
    return -1;
  }
  return 0;
}
int madvise(void* addr, size_t length, int advice) {
  /* Best-effort only. Do NOT MEM_DECOMMIT ART heap maps: that breaks subsequent
     VirtualProtect(PROT_NONE) fencing and can invalidate morecore regions.
     Prefer DiscardVirtualMemory when available; otherwise no-op (pages stay
     committed; ART also memsets when kMadviseZeroes is false). */
  (void)advice;
  if (addr == NULL || length == 0) return 0;
  typedef DWORD (WINAPI *DiscardFn)(PVOID, SIZE_T);
  static DiscardFn discard_fn = NULL;
  static int resolved = 0;
  if (!resolved) {
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    if (k32) discard_fn = (DiscardFn)GetProcAddress(k32, "DiscardVirtualMemory");
    resolved = 1;
  }
  if (discard_fn) {
    (void)discard_fn(addr, length);
  }
  return 0;
}

char* __cxa_demangle(const char* mangled, char* buf, size_t* n, int* status) {
  (void)mangled; (void)buf; (void)n;
  if (status) *status = -1;
  return NULL;
}

/* SRWLOCK unlock needs knowledge of lock mode; track via TLS is heavy.
   Phase 1: release exclusive if possible by using Try* is unavailable.
   Use a simple CRITICAL_SECTION for rwlock on Windows Phase1. */

int pthread_rwlock_init(CRITICAL_SECTION* l, const int* a){(void)a; InitializeCriticalSection(l); return 0;}
int pthread_rwlock_destroy(CRITICAL_SECTION* l){ DeleteCriticalSection(l); return 0;}
int pthread_rwlock_rdlock(CRITICAL_SECTION* l){ EnterCriticalSection(l); return 0;}
int pthread_rwlock_wrlock(CRITICAL_SECTION* l){ EnterCriticalSection(l); return 0;}
int pthread_rwlock_unlock(CRITICAL_SECTION* l){ LeaveCriticalSection(l); return 0;}

struct iovec { void* iov_base; size_t iov_len; };
ssize_t readv(int fd, const struct iovec* iov, int iovcnt) {
  ssize_t total=0;
  for(int i=0;i<iovcnt;i++){
    int n=_read(fd, iov[i].iov_base, (unsigned)iov[i].iov_len);
    if(n<0) return total?total:-1;
    total+=n; if((size_t)n<iov[i].iov_len) break;
  }
  return total;
}
ssize_t writev(int fd, const struct iovec* iov, int iovcnt) {
  ssize_t total=0;
  for(int i=0;i<iovcnt;i++){
    int n=_write(fd, iov[i].iov_base, (unsigned)iov[i].iov_len);
    if(n<0) return total?total:-1;
    total+=n; if((size_t)n<iov[i].iov_len) break;
  }
  return total;
}

int tgkill(int tgid, int tid, int sig) {
  (void)tgid; (void)tid; (void)sig;
  return -1;
}
int kill(int pid, int sig) { (void)pid; (void)sig; return -1; }
ssize_t process_vm_readv(int pid, const struct iovec* local_iov, unsigned long liovcnt,
                         const struct iovec* remote_iov, unsigned long riovcnt, unsigned long flags) {
  (void)pid; (void)local_iov; (void)liovcnt; (void)remote_iov; (void)riovcnt; (void)flags;
  return -1;
}

long ptrace(int request, ...) { (void)request; return -1; }


/* CRT uses _aligned_malloc; free with free() is wrong for that path —
 * ART 64-bit (__LP64__) should not call this. Provided for residual call sites. */
int posix_memalign(void** memptr, size_t alignment, size_t size) {
  if (!memptr || alignment == 0 || (alignment & (alignment - 1)) != 0) {
    return EINVAL;
  }
  if (alignment < sizeof(void*)) alignment = sizeof(void*);
  void* p = _aligned_malloc(size, alignment);
  if (!p) return ENOMEM;
  *memptr = p;
  return 0;
}


int usleep(useconds_t usec) {
  /* Sleep granularity is ms; round up. */
  DWORD ms = (DWORD)((usec + 999) / 1000);
  if (ms == 0 && usec > 0) ms = 1;
  Sleep(ms);
  return 0;
}


/* --- expanded pthread cond / timed rwlock / getuid (Phase 1) --- */
int pthread_rwlock_tryrdlock(CRITICAL_SECTION* l) {
  return TryEnterCriticalSection(l) ? 0 : EBUSY;
}
int pthread_rwlock_trywrlock(CRITICAL_SECTION* l) {
  return TryEnterCriticalSection(l) ? 0 : EBUSY;
}
static DWORD mdvm_timespec_to_ms_from_now(const struct timespec* abs_ts) {
  if (!abs_ts) return INFINITE;
  FILETIME ft; GetSystemTimeAsFileTime(&ft);
  unsigned long long now100 = ((unsigned long long)ft.dwHighDateTime << 32) | ft.dwLowDateTime;
  now100 -= 116444736000000000ULL;
  unsigned long long now_ns = now100 * 100ULL;
  unsigned long long abs_ns = (unsigned long long)abs_ts->tv_sec * 1000000000ULL +
                              (unsigned long long)abs_ts->tv_nsec;
  if (abs_ns <= now_ns) return 0;
  unsigned long long delta_ms = (abs_ns - now_ns) / 1000000ULL;
  if (delta_ms > 0xffffffffULL) return INFINITE;
  return (DWORD)delta_ms;
}
int pthread_rwlock_timedrdlock(CRITICAL_SECTION* l, const struct timespec* abs_ts) {
  DWORD ms = mdvm_timespec_to_ms_from_now(abs_ts);
  DWORD start = GetTickCount();
  for (;;) {
    if (TryEnterCriticalSection(l)) return 0;
    if (ms == 0) return ETIMEDOUT;
    if (ms != INFINITE && (GetTickCount() - start) >= ms) return ETIMEDOUT;
    Sleep(1);
  }
}
int pthread_rwlock_timedwrlock(CRITICAL_SECTION* l, const struct timespec* abs_ts) {
  return pthread_rwlock_timedrdlock(l, abs_ts);
}
int pthread_condattr_init(int* a) { if (a) *a = 0; return 0; }
int pthread_condattr_destroy(int* a) { (void)a; return 0; }
int pthread_condattr_setclock(int* a, int clock_id) { if (a) *a = clock_id; return 0; }
int pthread_cond_init(CONDITION_VARIABLE* c, const int* a) {
  (void)a; InitializeConditionVariable(c); return 0;
}
int pthread_cond_destroy(CONDITION_VARIABLE* c) { (void)c; return 0; }
int pthread_cond_wait(CONDITION_VARIABLE* c, CRITICAL_SECTION* m) {
  return SleepConditionVariableCS(c, m, INFINITE) ? 0 : EINTR;
}
int pthread_cond_timedwait(CONDITION_VARIABLE* c, CRITICAL_SECTION* m, const struct timespec* abs_ts) {
  DWORD ms = mdvm_timespec_to_ms_from_now(abs_ts);
  if (SleepConditionVariableCS(c, m, ms)) return 0;
  if (GetLastError() == ERROR_TIMEOUT) return ETIMEDOUT;
  return EINTR;
}
int pthread_cond_signal(CONDITION_VARIABLE* c) { WakeConditionVariable(c); return 0; }
int pthread_cond_broadcast(CONDITION_VARIABLE* c) { WakeAllConditionVariable(c); return 0; }
unsigned int getuid(void) { return 0; }
unsigned int geteuid(void) { return 0; }


int dladdr(const void* addr, Dl_info* info) {
  (void)addr;
  if (!info) return 0;
  info->dli_fname = "unknown";
  info->dli_fbase = NULL;
  info->dli_sname = NULL;
  info->dli_saddr = NULL;
  /* Best-effort: module containing address. */
  HMODULE mod = NULL;
  if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                         GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                         (LPCSTR)addr, &mod) && mod) {
    static char path[MAX_PATH];
    if (GetModuleFileNameA(mod, path, MAX_PATH)) {
      info->dli_fname = path;
      info->dli_fbase = (void*)mod;
    }
  }
  return info->dli_fbase != NULL;
}

long sysconf(int name) {
  SYSTEM_INFO si; GetSystemInfo(&si);
  if (name == 2 /*_SC_CLK_TCK*/) return 1000;
  if (name == 30 || name == 39) return (long)si.dwPageSize;
  if (name == 83 || name == 84) return (long)si.dwNumberOfProcessors;
  if (name == 85) {
    MEMORYSTATUSEX ms; ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) {
      DWORD ps = si.dwPageSize ? si.dwPageSize : 4096;
      return (long)(ms.ullTotalPhys / ps);
    }
    return -1;
  }
  errno = EINVAL; return -1;
}

int pipe(int fds[2]) {
  if (_pipe(fds, 4096, 0x8000) != 0) return -1;
  return 0;
}

int poll(struct pollfd* fds, unsigned long nfds, int timeout) {
  /* Minimal stub: no network readiness; treat as timeout or error. */
  (void)fds; (void)nfds;
  if (timeout == 0) return 0;
  if (timeout > 0) Sleep((DWORD)timeout);
  return 0;
}

int waitpid(int pid, int* status, int options) {
  (void)pid; (void)options;
  if (status) *status = 0;
  return -1;
}
int wait(int* status) { return waitpid(-1, status, 0); }

int statvfs(const char* path, struct statvfs* buf) {
  (void)path;
  if (!buf) return -1;
  memset(buf, 0, sizeof(*buf));
  buf->f_bsize = 4096; buf->f_frsize = 4096;
  buf->f_blocks = 1<<20; buf->f_bfree = 1<<19; buf->f_bavail = 1<<19;
  buf->f_namemax = 255;
  return 0;
}
int fstatvfs(int fd, struct statvfs* buf) { (void)fd; return statvfs(".", buf); }


/* Process APIs not in UCRT (exec* exist in process.h with different types — do not redefine). */
int fork(void) { errno = ENOSYS; return -1; }
int setpgid(int pid, int pgid) { (void)pid; (void)pgid; errno = ENOSYS; return -1; }
int getppid(void) { return 0; }
int getpgrp(void) { return (int)GetCurrentProcessId(); }
int waitid(int idtype, int id, void* infop, int options) {
  (void)idtype; (void)id; (void)infop; (void)options; errno = ENOSYS; return -1;
}
int ioctl(int fd, unsigned long request, ...) {
  (void)fd; (void)request; errno = ENOSYS; return -1;
}


int getrlimit(int resource, struct rlimit* rlim) {
  (void)resource;
  if (!rlim) return -1;
  rlim->rlim_cur = rlim->rlim_max = (~0ULL);
  return 0;
}
int setrlimit(int resource, const struct rlimit* rlim) {
  (void)resource; (void)rlim; return 0;
}
int getrusage(int who, struct rusage* usage) {
  (void)who;
  if (!usage) return -1;
  memset(usage, 0, sizeof(*usage));
  return 0;
}


int uname(struct utsname* buf) {
  if (!buf) return -1;
  memset(buf, 0, sizeof(*buf));
  strncpy(buf->sysname, "Windows", sizeof(buf->sysname)-1);
  strncpy(buf->nodename, "localhost", sizeof(buf->nodename)-1);
  strncpy(buf->release, "10.0", sizeof(buf->release)-1);
  strncpy(buf->version, "Win64", sizeof(buf->version)-1);
  strncpy(buf->machine, "x86_64", sizeof(buf->machine)-1);
  return 0;
}


/* --- threads / process (match pthread.h / link.h) --- */
typedef struct {
  void* (*start)(void*);
  void* arg;
} mdvm_thread_start_t;

static DWORD WINAPI mdvm_thread_trampoline(void* p) {
  mdvm_thread_start_t* s = (mdvm_thread_start_t*)p;
  void* (*fn)(void*) = s->start;
  void* arg = s->arg;
  free(s);
  fn(arg);
  return 0;
}

int pthread_create(pthread_t* t, const pthread_attr_t* attr, void* (*start)(void*), void* arg) {
  (void)attr;
  mdvm_thread_start_t* s = (mdvm_thread_start_t*)malloc(sizeof(*s));
  if (!s) return EAGAIN;
  s->start = start; s->arg = arg;
  DWORD tid = 0;
  HANDLE h = CreateThread(NULL, 0, mdvm_thread_trampoline, s, 0, &tid);
  if (!h) { free(s); return EAGAIN; }
  if (t) *t = (pthread_t)tid;
  CloseHandle(h);
  return 0;
}

int pthread_join(pthread_t t, void** retval) {
  if (retval) *retval = NULL;
  HANDLE h = OpenThread(SYNCHRONIZE, FALSE, (DWORD)t);
  if (!h) return ESRCH;
  WaitForSingleObject(h, INFINITE);
  CloseHandle(h);
  return 0;
}

int pthread_detach(pthread_t t) { (void)t; return 0; }

int pthread_attr_init(pthread_attr_t* attr) {
  if (!attr) return EINVAL;
  attr->detachstate = 0; attr->stackaddr = NULL; attr->stacksize = 0; attr->guardsize = 4096;
  return 0;
}
int pthread_attr_destroy(pthread_attr_t* attr) { (void)attr; return 0; }
int pthread_attr_setdetachstate(pthread_attr_t* attr, int s) {
  if (!attr) return EINVAL; attr->detachstate = s; return 0;
}
int pthread_attr_setstack(pthread_attr_t* attr, void* stackaddr, size_t stacksize) {
  if (!attr) return EINVAL;
  attr->stackaddr = stackaddr; attr->stacksize = stacksize; return 0;
}
int pthread_attr_setstacksize(pthread_attr_t* attr, size_t stacksize) {
  if (!attr) return EINVAL;
  attr->stacksize = stacksize; return 0;
}
int pthread_attr_getstack(const pthread_attr_t* attr, void** stackaddr, size_t* stacksize) {
  if (!attr) return EINVAL;
  if (stackaddr) *stackaddr = attr->stackaddr;
  if (stacksize) *stacksize = attr->stacksize ? attr->stacksize : (size_t)(1u << 20);
  return 0;
}
int pthread_attr_getguardsize(const pthread_attr_t* attr, size_t* guardsize) {
  if (!attr) return EINVAL;
  if (guardsize) *guardsize = attr->guardsize ? attr->guardsize : 4096;
  return 0;
}
int pthread_getattr_np(pthread_t t, pthread_attr_t* attr) {
  (void)t;
  if (pthread_attr_init(attr) != 0) return EINVAL;
  /* Estimate current thread stack via VirtualQuery of a stack local. */
  volatile char stack_probe;
  MEMORY_BASIC_INFORMATION mbi;
  if (VirtualQuery((LPCVOID)&stack_probe, &mbi, sizeof(mbi)) == 0) {
    attr->stackaddr = NULL;
    attr->stacksize = 1u << 20;
    attr->guardsize = 4096;
    return 0;
  }
  /* AllocationBase is low end of the reserved stack region; RegionSize from base
     to high end of committed+reserved chain is incomplete — walk to end. */
  char* base = (char*)mbi.AllocationBase;
  size_t total = 0;
  MEMORY_BASIC_INFORMATION cur;
  char* p = base;
  for (;;) {
    if (VirtualQuery(p, &cur, sizeof(cur)) == 0) break;
    if (cur.AllocationBase != mbi.AllocationBase) break;
    total += cur.RegionSize;
    p = (char*)cur.BaseAddress + cur.RegionSize;
    if (total > (64u << 20)) break; /* safety */
  }
  if (total < (256u << 10)) total = 1u << 20;
  attr->stackaddr = base;
  attr->stacksize = total;
  attr->guardsize = 4096;
  return 0;
}
int pthread_kill(pthread_t t, int sig) { (void)t; (void)sig; return 0; }
int unshare(int flags) { (void)flags; errno = ENOSYS; return -1; }
int getpriority(int which, int who) { (void)which; (void)who; return 0; }
int setpriority(int which, int who, int prio) { (void)which; (void)who; (void)prio; return 0; }
int dl_iterate_phdr(int (*callback)(struct dl_phdr_info*, size_t, void*), void* data) {
  (void)callback; (void)data; return 0;
}

void* mremap(void* old_addr, size_t old_size, size_t new_size, int flags, ...) {
  (void)old_addr; (void)old_size; (void)new_size; (void)flags;
  errno = ENOSYS;
  return (void*)(intptr_t)-1;
}
/* ART low-4g linear scan uses msync success as "page is mapped".
   Return 0 only when the address is committed; ENOMEM when free/reserved. */
int msync(void* addr, size_t length, int flags) {
  (void)flags;
  if (addr == NULL) {
    errno = ENOMEM;
    return -1;
  }
  uint8_t* p = (uint8_t*)addr;
  uint8_t* end = p + (length ? length : 1);
  while (p < end) {
    MEMORY_BASIC_INFORMATION mbi;
    SIZE_T got = VirtualQuery(p, &mbi, sizeof(mbi));
    if (got == 0) {
      errno = ENOMEM;
      return -1;
    }
    if (mbi.State != MEM_COMMIT) {
      errno = ENOMEM;
      return -1;
    }
    uint8_t* region_end = (uint8_t*)mbi.BaseAddress + mbi.RegionSize;
    if (region_end <= p) {
      errno = ENOMEM;
      return -1;
    }
    p = region_end;
  }
  return 0;
}
int fcntl(int fd, int cmd, ...) {
  (void)fd; (void)cmd; return 0;
}
int memfd_create(const char* name, unsigned int flags) {
  (void)name; (void)flags; errno = ENOSYS; return -1;
}

char* realpath(const char* path, char* resolved) {
  char buf[MAX_PATH];
  DWORD n = GetFullPathNameA(path ? path : "", MAX_PATH, buf, NULL);
  if (n == 0 || n >= MAX_PATH) return NULL;
  if (resolved) {
    strncpy(resolved, buf, 259);
    resolved[259] = 0;
    return resolved;
  }
  char* out = (char*)malloc((size_t)n + 1);
  if (!out) return NULL;
  memcpy(out, buf, (size_t)n + 1);
  return out;
}

int pthread_getname_np(pthread_t t, char* buf, size_t len) {
  (void)t;
  if (!buf || len == 0) return EINVAL;
  strncpy(buf, "thread", len - 1);
  buf[len - 1] = 0;
  return 0;
}
