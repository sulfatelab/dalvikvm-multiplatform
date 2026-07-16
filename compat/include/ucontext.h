#pragma once
#if !defined(_WIN32)
#include_next <ucontext.h>
#else
#include <stdint.h>
/* Minimal Linux-like ucontext for ART signal/seccomp paths. */
enum {
  REG_R8 = 0,
  REG_R9,
  REG_R10,
  REG_R11,
  REG_R12,
  REG_R13,
  REG_R14,
  REG_R15,
  REG_RDI,
  REG_RSI,
  REG_RBP,
  REG_RBX,
  REG_RDX,
  REG_RAX,
  REG_RCX,
  REG_RSP,
  REG_RIP,
  REG_EFL,
  REG_CSGSFS,
  REG_ERR,
  REG_TRAPNO,
  REG_OLDMASK,
  REG_CR2
};
typedef struct {
  uint64_t gregs[23];
} mcontext_t;
typedef struct ucontext {
  unsigned long uc_flags;
  struct ucontext* uc_link;
  mcontext_t uc_mcontext;
} ucontext_t;
#endif
