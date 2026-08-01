// Toolchain-compatibility prelude for the Linux openjdkjvmti DSO only.
#pragma once

#ifndef __linux__
#error "mdvm_openjdkjvmti_linux_prelude.h is for Linux targets only"
#endif
#ifndef __cplusplus
#error "mdvm_openjdkjvmti_linux_prelude.h requires C++"
#endif

#include <cstddef>
#include <cstdio>
#include <cstring>

// Bionic exposes nullptr_t in the global namespace.  Current host C++
// libraries correctly expose only std::nullptr_t, while the pinned ART JVMTI
// sources still use both spellings.
using std::nullptr_t;

// glibc 2.38 added strlcpy.  Suppress ART's older host fallback when the
// system declaration exists; older glibc continues to use the fallback.
#if defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 38)
#define ART_LIBARTBASE_BASE_STRLCPY_H_ 1
#endif
