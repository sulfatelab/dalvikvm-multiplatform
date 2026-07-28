#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Normalize mixed separators to '\\'; optional collapse of . and .. */
int win_path_normalize(const char* in, char* out, size_t out_cap);
/* UTF-8 path -> UTF-16 for Win32; returns malloc'd wchar_t* (caller free) */
wchar_t* win_path_to_wide(const char* utf8_path);
#ifdef __cplusplus
}
#endif
