#pragma once
#if !defined(_WIN32)
#include_next <sys/wait.h>
#else
#include <stdint.h>
#include <signal.h>
#define WNOHANG 1
#define WUNTRACED 2
#define WCONTINUED 8
#define WEXITED 4
#define WSTOPPED 2
#define WNOWAIT 0x01000000
#define P_PID 1
#define P_PGID 2
#define P_ALL 0
#define CLD_EXITED 1
#define CLD_KILLED 2
#define CLD_DUMPED 3
#define CLD_STOPPED 5
#define CLD_CONTINUED 6
#define WEXITSTATUS(s) (((s) >> 8) & 0xff)
#define WTERMSIG(s) ((s) & 0x7f)
#define WSTOPSIG(s) (((s) >> 8) & 0xff)
#define WIFEXITED(s) (((s) & 0x7f) == 0)
#define WIFSIGNALED(s) (((s) & 0x7f) != 0 && ((s) & 0x7f) != 0x7f)
#define WIFSTOPPED(s) (((s) & 0xff) == 0x7f)
#define WIFCONTINUED(s) ((s) == 0xffff)
#ifdef __cplusplus
extern "C" {
#endif
int waitpid(int pid, int* status, int options);
int wait(int* status);
int waitid(int idtype, int id, siginfo_t* infop, int options);
#ifdef __cplusplus
}
#endif
#endif
