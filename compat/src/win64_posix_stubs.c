#include <winsock2.h>
#include <windows.h>
#include <fcntl.h>
#include <sys/uio.h>
#include <unistd.h>
#include <limits.h>

#include <stdlib.h>
#include <stdarg.h>
#include <termios.h>
#include <sys/mman.h>
#include <sys/sendfile.h>
#include <io.h>
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

/* iovec is in sys/uio.h; do not redefine. */
ssize_t readv(int fd, const struct iovec* iov, int iovcnt) {
  ssize_t total=0;
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  for(int i=0;i<iovcnt;i++){
    int n;
    if (s != INVALID_SOCKET && s != (SOCKET)-1) {
      n = recv(s, (char*)iov[i].iov_base, (int)iov[i].iov_len, 0);
      if (n == SOCKET_ERROR) {
        /* fall back to CRT read for non-sockets */
        n = _read(fd, iov[i].iov_base, (unsigned)iov[i].iov_len);
      }
    } else {
      n = _read(fd, iov[i].iov_base, (unsigned)iov[i].iov_len);
    }
    if(n<0) return total?total:-1;
    total+=n; if((size_t)n<iov[i].iov_len) break;
  }
  return total;
}
ssize_t writev(int fd, const struct iovec* iov, int iovcnt) {
  ssize_t total=0;
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  for(int i=0;i<iovcnt;i++){
    int n;
    if (s != INVALID_SOCKET && s != (SOCKET)-1) {
      n = send(s, (const char*)iov[i].iov_base, (int)iov[i].iov_len, 0);
      if (n == SOCKET_ERROR) {
        n = _write(fd, iov[i].iov_base, (unsigned)iov[i].iov_len);
      }
    } else {
      n = _write(fd, iov[i].iov_base, (unsigned)iov[i].iov_len);
    }
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
    if (name == 60) return 16;
  return -1;
  }
  errno = EINVAL; return -1;
}

int pipe(int fds[2]) {
  if (_pipe(fds, 4096, 0x8000) != 0) return -1;
  return 0;
}

int poll(struct pollfd* fds, unsigned long nfds, int timeout) {
  /* Socket-aware poll via select on CRT fds that wrap SOCKETs. */
  if (!fds) { errno = EINVAL; return -1; }
  fd_set rfds, wfds, efds;
  FD_ZERO(&rfds); FD_ZERO(&wfds); FD_ZERO(&efds);
  SOCKET max_s = 0;
  int saw_socket = 0;
  int ready = 0;
  for (unsigned long i = 0; i < nfds; i++) {
    fds[i].revents = 0;
    if (fds[i].fd < 0) continue;
    intptr_t h = _get_osfhandle(fds[i].fd);
    if (h == -1) { fds[i].revents = POLLNVAL; ready++; continue; }
    /* Heuristic: try select; non-sockets will fail gracefully per-fd. */
    SOCKET s = (SOCKET)h;
    if (fds[i].events & (POLLIN | POLLRDNORM | POLLPRI)) FD_SET(s, &rfds);
    if (fds[i].events & (POLLOUT | POLLWRNORM)) FD_SET(s, &wfds);
    FD_SET(s, &efds);
    if (s > max_s) max_s = s;
    saw_socket = 1;
  }
  if (!saw_socket) {
    if (timeout == 0) return ready;
    if (timeout > 0) Sleep((DWORD)timeout);
    return ready;
  }
  struct timeval tv, *ptv = NULL;
  if (timeout >= 0) {
    tv.tv_sec = timeout / 1000;
    tv.tv_usec = (timeout % 1000) * 1000;
    ptv = &tv;
  }
  int sr = select((int)max_s + 1, &rfds, &wfds, &efds, ptv);
  if (sr == SOCKET_ERROR) {
    /* If select fails (mixed non-socket handles), fall back to sleep. */
    if (timeout == 0) return ready;
    if (timeout > 0) Sleep((DWORD)timeout);
    return ready;
  }
  if (sr == 0) return ready;
  for (unsigned long i = 0; i < nfds; i++) {
    if (fds[i].fd < 0) continue;
    intptr_t h = _get_osfhandle(fds[i].fd);
    if (h == -1) continue;
    SOCKET s = (SOCKET)h;
    short rev = fds[i].revents;
    if (FD_ISSET(s, &rfds)) rev |= POLLIN;
    if (FD_ISSET(s, &wfds)) rev |= POLLOUT;
    if (FD_ISSET(s, &efds)) rev |= POLLERR;
    if (rev && !(fds[i].revents)) ready++;
    fds[i].revents = rev;
  }
  return ready;
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
  va_list ap;
  va_start(ap, request);
  void* arg = va_arg(ap, void*);
  va_end(ap);
  if (fd < 0) { errno = EBADF; return -1; }
  SOCKET s = (SOCKET)_get_osfhandle(fd);
  if (s == INVALID_SOCKET || s == (SOCKET)-1) { errno = EBADF; return -1; }
  /* FIONREAD from winsock */
  if (request == FIONREAD || request == 0x541B /* Linux FIONREAD */) {
    u_long n = 0;
    if (ioctlsocket(s, FIONREAD, &n) == SOCKET_ERROR) {
      errno = EINVAL;
      return -1;
    }
    if (arg) *(int*)arg = (int)n;
    return 0;
  }
  if (request == FIONBIO) {
    u_long nb = arg ? *(u_long*)arg : 0;
    if (ioctlsocket(s, FIONBIO, &nb) == SOCKET_ERROR) {
      errno = EINVAL;
      return -1;
    }
    return 0;
  }
  errno = ENOSYS;
  return -1;
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
  va_list ap;
  va_start(ap, cmd);
  int arg = 0;
  if (cmd == F_SETFL || cmd == F_SETFD || cmd == F_SETLK || cmd == F_SETLKW ||
      cmd == F_GETLK || cmd == F_DUPFD || cmd == F_DUPFD_CLOEXEC) {
    arg = va_arg(ap, int);
  }
  va_end(ap);
  if (fd < 0) { errno = EBADF; return -1; }
  if (cmd == F_GETFD) return 0;
  if (cmd == F_SETFD) return 0;
  if (cmd == F_GETFL) {
    /* Best-effort: report O_RDWR; O_NONBLOCK unknown without per-fd state. */
    return O_RDWR;
  }
  if (cmd == F_SETFL) {
    SOCKET s = (SOCKET)_get_osfhandle(fd);
    if (s != INVALID_SOCKET && s != (SOCKET)-1) {
      u_long nb = (arg & O_NONBLOCK) ? 1 : 0;
      if (ioctlsocket(s, FIONBIO, &nb) == SOCKET_ERROR) {
        errno = EINVAL;
        return -1;
      }
    }
    return 0;
  }
  if (cmd == F_DUPFD || cmd == F_DUPFD_CLOEXEC) {
    int n = _dup(fd);
    return n;
  }
  return 0;
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


/* ---- aliases expected by openjdk NIO/file natives ---- */
int fsync(int fd) { return _commit(fd); }
int fdatasync(int fd) { return _commit(fd); }
long long lseek64(int fd, long long off, int whence) { return _lseeki64(fd, off, whence); }
int mdvm_ftruncate(int fd, long long length) { return _chsize_s(fd, length); }
int open64(const char* path, int flags, ...) {
  va_list ap; va_start(ap, flags); int mode = va_arg(ap, int); va_end(ap);
  return _open(path, flags | _O_BINARY, mode);
}
ssize_t pread64(int fd, void* buf, size_t count, long long offset) {
  return pread(fd, buf, count, offset);
}
ssize_t pwrite64(int fd, const void* buf, size_t count, long long offset) {
  return pwrite(fd, buf, count, offset);
}


void* mmap64(void* addr, size_t length, int prot, int flags, int fd, long long offset) {
  return mmap(addr, length, prot, flags, fd, offset);
}
int mincore(void* addr, size_t length, unsigned char* vec) {
  if (!vec) { errno = EINVAL; return -1; }
  /* Best-effort: mark all pages resident if VirtualQuery says committed. */
  size_t pages = (length + 4095) / 4096;
  for (size_t i = 0; i < pages; i++) {
    MEMORY_BASIC_INFORMATION mbi;
    void* p = (char*)addr + i * 4096;
    if (VirtualQuery(p, &mbi, sizeof(mbi)) == 0 || mbi.State != MEM_COMMIT) vec[i] = 0;
    else vec[i] = 1;
  }
  return 0;
}
ssize_t sendfile(int out_fd, int in_fd, long long* offset, size_t count) {
  (void)out_fd; (void)in_fd; (void)offset; (void)count;
  errno = ENOSYS; return -1;
}
ssize_t sendfile64(int out_fd, int in_fd, long long* offset, size_t count) {
  return sendfile(out_fd, in_fd, offset, count);
}
int tcgetattr(int fd, struct termios* t) {
  (void)fd;
  if (t) memset(t, 0, sizeof(*t));
  return 0;
}
int tcsetattr(int fd, int optional_actions, const struct termios* t) {
  (void)fd; (void)optional_actions; (void)t; return 0;
}

long pathconf(const char* path, int name) {
  (void)path; (void)name;
  return 255;
}

int gettimeofday(struct timeval* tv, void* tz) {
  (void)tz;
  if (!tv) return -1;
  FILETIME ft; GetSystemTimeAsFileTime(&ft);
  ULARGE_INTEGER u; u.LowPart = ft.dwLowDateTime; u.HighPart = ft.dwHighDateTime;
  const unsigned long long EPOCH_DIFF = 116444736000000000ULL;
  unsigned long long t = (u.QuadPart - EPOCH_DIFF) / 10ULL; /* us */
  tv->tv_sec = (long)(t / 1000000ULL);
  tv->tv_usec = (long)(t % 1000000ULL);
  return 0;
}

/* ART time_utils.cc (mingw-era) expects these names on Windows. */
int mingw_gettimeofday(struct timeval* tv, void* tz) {
  return gettimeofday(tv, tz);
}
struct tm* localtime_r(const time_t* timep, struct tm* result) {
  if (!timep || !result) {
    errno = EINVAL;
    return NULL;
  }
  /* MSVC: localtime_s(result, timep) */
  if (localtime_s(result, timep) != 0) {
    return NULL;
  }
  return result;
}


int pthread_mutexattr_init(int* a) { if (a) *a = 0; return 0; }
int pthread_mutexattr_destroy(int* a) { (void)a; return 0; }
int pthread_mutexattr_settype(int* a, int t) { if (a) *a = t; return 0; }

int clock_gettime(int clk_id, struct timespec* tp) {
  (void)clk_id;
  if (!tp) return -1;
  FILETIME ft; GetSystemTimeAsFileTime(&ft);
  ULARGE_INTEGER u; u.LowPart = ft.dwLowDateTime; u.HighPart = ft.dwHighDateTime;
  const unsigned long long EPOCH_DIFF = 116444736000000000ULL;
  unsigned long long t = u.QuadPart - EPOCH_DIFF; /* 100ns */
  tp->tv_sec = (time_t)(t / 10000000ULL);
  tp->tv_nsec = (long)((t % 10000000ULL) * 100ULL);
  return 0;
}
int nanosleep(const struct timespec* req, struct timespec* rem) {
  if (!req) return -1;
  DWORD ms = (DWORD)(req->tv_sec * 1000 + (req->tv_nsec + 999999) / 1000000);
  if (ms == 0 && (req->tv_sec || req->tv_nsec)) ms = 1;
  Sleep(ms);
  if (rem) { rem->tv_sec = 0; rem->tv_nsec = 0; }
  return 0;
}
