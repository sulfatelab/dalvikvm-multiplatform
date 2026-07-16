#pragma once
#if !defined(_WIN32)
#include_next <sys/ucontext.h>
#else
#include <ucontext.h>
#endif
