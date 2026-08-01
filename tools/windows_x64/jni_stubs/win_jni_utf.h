#pragma once

#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

/* Copy a Java UTF-16 string into a NUL-terminated Win32-owned buffer. */
static inline wchar_t* win_jstring_to_utf16(JNIEnv* env, jstring value) {
  if (env == NULL || value == NULL) return NULL;
  jsize length = (*env)->GetStringLength(env, value);
  const jchar* characters = (*env)->GetStringChars(env, value, NULL);
  if (characters == NULL) return NULL;
  wchar_t* result = (wchar_t*)malloc(((size_t)length + 1u) * sizeof(wchar_t));
  if (result != NULL) {
    memcpy(result, characters, (size_t)length * sizeof(wchar_t));
    result[length] = L'\0';
  }
  (*env)->ReleaseStringChars(env, value, characters);
  return result;
}
