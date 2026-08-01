/* Project-owned: complete the Windows CRT sys/types surface used by AOSP. */
#pragma once

#include_next <sys/types.h>

#if defined(_WIN32)
#include <stdint.h>

#ifndef _MDVM_MODE_T_DEFINED
typedef unsigned short mode_t;
#define _MDVM_MODE_T_DEFINED 1
#endif

#ifndef _SSIZE_T_DEFINED
typedef intptr_t ssize_t;
#define _SSIZE_T_DEFINED 1
#endif

#ifndef _PID_T_DEFINED
typedef int pid_t;
#define _PID_T_DEFINED 1
#endif
#endif
