#pragma once
#if !defined(_WIN32)
#include_next <signal.h>
#else
#include <stdint.h>
#include <stddef.h>
#include <ucontext.h>

typedef struct siginfo {
  int si_signo;
  int si_code;
  int si_errno;
  void* si_addr;
  int si_pid;
  int si_uid;
  int si_status;
  union {
    int sival_int;
    void* sival_ptr;
  } si_value;
  int si_syscall;
  int si_arch;
} siginfo_t;

typedef unsigned long sigset_t;
typedef sigset_t sigset64_t;

#define SIG_DFL ((void (*)(int))0)
#define SIG_IGN ((void (*)(int))1)
#define SIG_ERR ((void (*)(int))-1)

#define SA_SIGINFO 4
#define SA_RESTART 0x10000000
#define SA_ONSTACK 0x08000000
#define SA_NODEFER 0x40000000
#define SA_RESETHAND 0x80000000
#define SIG_BLOCK 0
#define SIG_UNBLOCK 1
#define SIG_SETMASK 2

#define SIGINT 2
#define SIGQUIT 3
#define SIGILL 4
#define SIGTRAP 5
#define SIGABRT 6
#define SIGBUS 7
#define SIGFPE 8
#define SIGKILL 9
#define SIGUSR1 10
#define SIGSEGV 11
#define SIGUSR2 12
#define SIGPIPE 13
#define SIGALRM 14
#define SIGTERM 15
#define SIGCHLD 17
#define SIGCONT 18
#define SIGSTOP 19
#define SIGSYS 31
#define SIGRTMIN 32
#define SIGRTMAX 64

#define SI_USER 0
#define SI_KERNEL 0x80
#define SI_QUEUE -1
#define SI_TIMER -2
#define SI_MESGQ -3
#define SI_ASYNCIO -4
#define SEGV_MAPERR 1
#define SEGV_ACCERR 2
#define BUS_ADRALN 1
#define BUS_ADRERR 2
#define BUS_OBJERR 3
#define FPE_INTDIV 1
#define FPE_INTOVF 2
#define FPE_FLTDIV 3
#define FPE_FLTOVF 4
#define FPE_FLTUND 5
#define FPE_FLTRES 6
#define FPE_FLTINV 7
#define FPE_FLTSUB 8
#define ILL_ILLOPC 1
#define ILL_ILLOPN 2
#define ILL_ILLADR 3
#define ILL_ILLTRP 4
#define ILL_PRVOPC 5
#define ILL_PRVREG 6
#define ILL_COPROC 7
#define ILL_BADSTK 8
#define TRAP_BRKPT 1
#define TRAP_TRACE 2
#define SYS_SECCOMP 1

struct sigaction {
  union {
    void (*sa_handler)(int);
    void (*sa_sigaction)(int, siginfo_t*, void*);
  };
  sigset_t sa_mask;
  int sa_flags;
  void (*sa_restorer)(void);
};

#ifdef __cplusplus
extern "C" {
#endif
static inline int sigemptyset(sigset_t* s) { if (s) *s = 0; return 0; }
static inline int sigfillset(sigset_t* s) { if (s) *s = ~0UL; return 0; }
static inline int sigaddset(sigset_t* s, int sig) {
  if (!s) return -1; *s |= (1UL << (sig % 64)); return 0;
}
static inline int sigdelset(sigset_t* s, int sig) {
  if (!s) return -1; *s &= ~(1UL << (sig % 64)); return 0;
}
static inline int sigismember(const sigset_t* s, int sig) {
  if (!s) return 0; return (*s & (1UL << (sig % 64))) != 0;
}
static inline int sigprocmask(int how, const sigset_t* set, sigset_t* oldset) {
  (void)how; (void)set; (void)oldset; return 0;
}
static inline int sigaction(int sig, const struct sigaction* act, struct sigaction* oldact) {
  (void)sig; (void)act; (void)oldact; return -1;
}
static inline int raise(int sig) { (void)sig; return -1; }
static inline const char* strsignal(int sig) { (void)sig; return "signal"; }
static inline int sigemptyset64(sigset64_t* s) { return sigemptyset(s); }
static inline int sigfillset64(sigset64_t* s) { return sigfillset(s); }
static inline int sigaddset64(sigset64_t* s, int sig) { return sigaddset(s, sig); }
static inline int sigdelset64(sigset64_t* s, int sig) { return sigdelset(s, sig); }
static inline int sigismember64(const sigset64_t* s, int sig) { return sigismember(s, sig); }
static inline int sigprocmask64(int how, const sigset64_t* set, sigset64_t* oldset) {
  return sigprocmask(how, set, oldset);
}
static inline int pthread_sigmask(int how, const sigset_t* set, sigset_t* oldset) {
  return sigprocmask(how, set, oldset);
}
static inline int pthread_sigmask64(int how, const sigset64_t* set, sigset64_t* oldset) {
  return sigprocmask(how, set, oldset);
}
static inline int sigwaitinfo64(const sigset64_t* set, siginfo_t* info) {
  (void)set; if (info) info->si_signo = 0; return -1;
}
int tgkill(int tgid, int tid, int sig);
int kill(int pid, int sig);
int pthread_kill(unsigned long thread, int sig);
#ifdef __cplusplus
}
#endif
#endif
