#pragma once
#if !defined(_WIN32)
#include_next <sys/ptrace.h>
#else
#include <stdint.h>
#include <sys/types.h>
#define PTRACE_TRACEME 0
#define PTRACE_PEEKTEXT 1
#define PTRACE_PEEKDATA 2
#define PTRACE_POKETEXT 4
#define PTRACE_POKEDATA 5
#define PTRACE_CONT 7
#define PTRACE_KILL 8
#define PTRACE_SINGLESTEP 9
#define PTRACE_GETREGS 12
#define PTRACE_SETREGS 13
#define PTRACE_ATTACH 16
#define PTRACE_DETACH 17
#define PTRACE_SYSCALL 24
#define PTRACE_GETREGSET 0x4204
#define PTRACE_SETREGSET 0x4205
#ifndef NT_PRSTATUS
#define NT_PRSTATUS 1
#endif
#ifdef __cplusplus
extern "C" {
#endif
/* Match Linux glibc-ish prototype enough for integer request args. */
long ptrace(int request, ...);
#ifdef __cplusplus
}
#endif
#endif
