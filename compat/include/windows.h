#pragma once

#ifndef _WIN32
#error "The project windows.h wrapper is for Windows targets only"
#endif

#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOGDI
#define NOGDI
#endif

#include_next <windows.h>

/* Keep Windows SDK implementation macros out of portable ART sources. */
#if defined(MDVM_WINDOWS_NO_CALLBACK_MACRO) && defined(CALLBACK)
#undef CALLBACK
#endif
#if defined(__cplusplus) && defined(CONST) && !defined(MDVM_WINDOWS_KEEP_CONST_MACRO)
#undef CONST
#endif
#ifdef ERROR
#undef ERROR
#endif
#ifdef __reserved
#undef __reserved
#endif
