#pragma once

#if !defined(_WIN32)
#error "mdvm_windows_utf8.h is for Windows targets only"
#endif

#include <stddef.h>
#include <stdlib.h>
#include <windows.h>

/*
 * Strict allocation helpers for UTF-8-facing native boundaries.  The caller
 * owns the returned buffer and releases it with free().  Invalid Unicode is
 * rejected rather than reinterpreted through the process ANSI code page.
 */
static inline wchar_t* mdvm_utf8_to_utf16_alloc(const char* utf8) {
  if (utf8 == NULL) {
    SetLastError(ERROR_INVALID_PARAMETER);
    return NULL;
  }
  int length = MultiByteToWideChar(
      CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, NULL, 0);
  if (length == 0) {
    return NULL;
  }
  wchar_t* utf16 = (wchar_t*)malloc((size_t)length * sizeof(wchar_t));
  if (utf16 == NULL) {
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return NULL;
  }
  if (MultiByteToWideChar(
          CP_UTF8, MB_ERR_INVALID_CHARS, utf8, -1, utf16, length) == 0) {
    DWORD error = GetLastError();
    free(utf16);
    SetLastError(error);
    return NULL;
  }
  return utf16;
}

static inline char* mdvm_utf16_to_utf8_alloc(const wchar_t* utf16) {
  if (utf16 == NULL) {
    SetLastError(ERROR_INVALID_PARAMETER);
    return NULL;
  }
  int length = WideCharToMultiByte(
      CP_UTF8, WC_ERR_INVALID_CHARS, utf16, -1, NULL, 0, NULL, NULL);
  if (length == 0) {
    return NULL;
  }
  char* utf8 = (char*)malloc((size_t)length);
  if (utf8 == NULL) {
    SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return NULL;
  }
  if (WideCharToMultiByte(
          CP_UTF8, WC_ERR_INVALID_CHARS, utf16, -1, utf8, length, NULL, NULL) == 0) {
    DWORD error = GetLastError();
    free(utf8);
    SetLastError(error);
    return NULL;
  }
  return utf8;
}
