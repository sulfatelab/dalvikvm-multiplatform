#pragma once
#if defined(_WIN32)
/* Minimal Android/bionic cdefs for Windows host builds of liblog headers. */

#ifndef __BEGIN_DECLS
#ifdef __cplusplus
#define __BEGIN_DECLS extern "C" {
#define __END_DECLS }
#else
#define __BEGIN_DECLS
#define __END_DECLS
#endif
#endif

#ifndef __printflike
#define __printflike(fmtarg, firstvararg)
#endif
#ifndef __format_arg
#define __format_arg(x)
#endif
#ifndef __wur
#define __wur
#endif
#ifndef __INTRODUCED_IN
#define __INTRODUCED_IN(x)
#endif
#ifndef __attribute_unused__
#define __attribute_unused__ __attribute__((__unused__))
#endif
#ifndef __unused
#define __unused __attribute__((__unused__))
#endif
#ifndef __predict_false
#define __predict_false(exp) __builtin_expect((exp) != 0, 0)
#endif
#ifndef __predict_true
#define __predict_true(exp) __builtin_expect((exp) != 0, 1)
#endif

#else
#include_next <sys/cdefs.h>
#endif
