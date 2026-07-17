#pragma once
#if !defined(_WIN32)
#include_next <alloca.h>
#else
#include <malloc.h>
#ifndef alloca
#define alloca _alloca
#endif
#endif
