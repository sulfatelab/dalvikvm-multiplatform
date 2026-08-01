/* java.lang.Runtime free/total/max memory + nativeGc for Windows x64 PE stubs. */
#include <jni.h>
#include <windows.h>
#include <mdvm_windows_utf8.h>
#include <process.h>
#include <limits.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "win_jni_utf.h"

typedef jlong (*jvm_long_fn)(void);
typedef void (*jvm_void_fn)(void);

static LPTOP_LEVEL_EXCEPTION_FILTER g_late_uef_predecessor;

static int module_is_art(const char* path) {
  const char* base = strrchr(path, '\\');
  if (base == NULL) base = strrchr(path, '/');
  base = base != NULL ? base + 1 : path;
  return _stricmp(base, "art.dll") == 0 || _stricmp(base, "libart.dll") == 0;
}

static LONG WINAPI late_uef_probe(EXCEPTION_POINTERS* info) {
  DWORD code = info != NULL && info->ExceptionRecord != NULL
      ? info->ExceptionRecord->ExceptionCode
      : 0;
  fprintf(stderr,
          "WIN32_LATE_UEF enter code=0x%08lx predecessor=%p\n",
          (unsigned long)code,
          (void*)g_late_uef_predecessor);
  fflush(stderr);
  if (g_late_uef_predecessor != NULL && g_late_uef_predecessor != late_uef_probe) {
    return g_late_uef_predecessor(info);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

static HMODULE art_module(void) {
  HMODULE m = GetModuleHandleW(L"art.dll");
  if (!m) m = GetModuleHandleW(L"libart.dll");
  return m;
}

static jlong call_jvm_long(const char* name) {
  HMODULE m = art_module();
  if (!m) return 0;
  jvm_long_fn fn = (jvm_long_fn)GetProcAddress(m, name);
  if (!fn) return 0;
  return fn();
}

static void call_jvm_void(const char* name) {
  HMODULE m = art_module();
  if (!m) return;
  jvm_void_fn fn = (jvm_void_fn)GetProcAddress(m, name);
  if (fn) fn();
}

__declspec(dllexport) jlong Java_java_lang_Runtime_freeMemory(JNIEnv* env, jobject thiz) {
  (void)env; (void)thiz;
  return call_jvm_long("JVM_FreeMemory");
}
__declspec(dllexport) jlong Java_java_lang_Runtime_freeMemory__(JNIEnv* env, jobject thiz) {
  return Java_java_lang_Runtime_freeMemory(env, thiz);
}

__declspec(dllexport) jlong Java_java_lang_Runtime_totalMemory(JNIEnv* env, jobject thiz) {
  (void)env; (void)thiz;
  return call_jvm_long("JVM_TotalMemory");
}
__declspec(dllexport) jlong Java_java_lang_Runtime_totalMemory__(JNIEnv* env, jobject thiz) {
  return Java_java_lang_Runtime_totalMemory(env, thiz);
}

__declspec(dllexport) jlong Java_java_lang_Runtime_maxMemory(JNIEnv* env, jobject thiz) {
  (void)env; (void)thiz;
  return call_jvm_long("JVM_MaxMemory");
}
__declspec(dllexport) jlong Java_java_lang_Runtime_maxMemory__(JNIEnv* env, jobject thiz) {
  return Java_java_lang_Runtime_maxMemory(env, thiz);
}

__declspec(dllexport) void Java_java_lang_Runtime_nativeGc(JNIEnv* env, jobject thiz) {
  (void)env; (void)thiz;
  call_jvm_void("JVM_GC");
}
__declspec(dllexport) void Java_java_lang_Runtime_nativeGc__(JNIEnv* env, jobject thiz) {
  Java_java_lang_Runtime_nativeGc(env, thiz);
}

/* Phase 4 A8: deliberate AV for crash-path smoke (not used in product paths). */
__declspec(dllexport) void Java_CrashNativeProbe_nativeSegfault(JNIEnv* env, jclass cls) {
  (void)env; (void)cls;
  const char* warmup_value = getenv("ART_WINDOWS_X64_CRASH_NATIVE_WARMUP");
  if (warmup_value != NULL) {
    char* end = NULL;
    unsigned long warmup_calls = strtoul(warmup_value, &end, 10);
    static LONG call_count;
    if (end != warmup_value && *end == '\0' && warmup_calls <= LONG_MAX &&
        InterlockedIncrement(&call_count) <= (LONG)warmup_calls) {
      return;
    }
  }
  volatile int* p = (volatile int*)0;
  *p = 0x41414141;
}
__declspec(dllexport) void Java_CrashNativeProbe_nativeSegfault__(JNIEnv* env, jclass cls) {
  Java_CrashNativeProbe_nativeSegfault(env, cls);
}

/* Software-raised AV with the same documented access-information shape. */
__declspec(dllexport) void Java_CrashNativeProbe_nativeRaiseAccessViolation(
    JNIEnv* env, jclass cls) {
  (void)env; (void)cls;
  ULONG_PTR arguments[2] = {1u, 0u};  /* write at null */
  fprintf(stderr, "WIN32_JNI_RAISE_AV code=0x%08lx\n",
          (unsigned long)EXCEPTION_ACCESS_VIOLATION);
  fflush(stderr);
  RaiseException(EXCEPTION_ACCESS_VIOLATION, 0u, 2u, arguments);
}
__declspec(dllexport) void Java_CrashNativeProbe_nativeRaiseAccessViolation__(
    JNIEnv* env, jclass cls) {
  Java_CrashNativeProbe_nativeRaiseAccessViolation(env, cls);
}

static unsigned __stdcall crash_native_worker(void* argument) {
  (void)argument;
  fprintf(stderr, "WIN32_JNI_NATIVE_WORKER enter tid=%lu\n",
          (unsigned long)GetCurrentThreadId());
  fflush(stderr);
  volatile int* p = (volatile int*)0;
  *p = 0x42424242;
  return 2u;
}

/* Real AV on a CRT-created native thread whose crashing stack has no ART frames. */
__declspec(dllexport) void Java_CrashNativeProbe_nativeWorkerSegfault(
    JNIEnv* env, jclass cls) {
  (void)env; (void)cls;
  unsigned thread_id = 0u;
  uintptr_t raw_handle = _beginthreadex(
      NULL, 0u, crash_native_worker, NULL, 0u, &thread_id);
  if (raw_handle == 0u) {
    fprintf(stderr, "WIN32_JNI_NATIVE_WORKER create_failed errno=%d\n", errno);
    fflush(stderr);
    return;
  }
  HANDLE handle = (HANDLE)raw_handle;
  fprintf(stderr, "WIN32_JNI_NATIVE_WORKER created tid=%u\n", thread_id);
  fflush(stderr);
  DWORD wait_result = WaitForSingleObject(handle, INFINITE);
  DWORD exit_code = 0u;
  GetExitCodeThread(handle, &exit_code);
  CloseHandle(handle);
  fprintf(stderr,
          "WIN32_JNI_NATIVE_WORKER unexpected_return wait=%lu exit=0x%08lx\n",
          (unsigned long)wait_result,
          (unsigned long)exit_code);
  fflush(stderr);
}
__declspec(dllexport) void Java_CrashNativeProbe_nativeWorkerSegfault__(
    JNIEnv* env, jclass cls) {
  Java_CrashNativeProbe_nativeWorkerSegfault(env, cls);
}

/* Probe-only late UEF ownership observation for W-010 fatal-dispatch diagnostics. */
__declspec(dllexport) void Java_CrashNativeProbe_nativeInstallUefProbe(
    JNIEnv* env, jclass cls) {
  (void)env; (void)cls;
  wchar_t wide_module_path[MAX_PATH] = L"unknown";
  char module_path[MAX_PATH * 3 + 1] = "unknown";
  HMODULE module = NULL;
  g_late_uef_predecessor = SetUnhandledExceptionFilter(late_uef_probe);
  if (g_late_uef_predecessor != NULL) {
    MEMORY_BASIC_INFORMATION memory;
    if (VirtualQuery((const void*)(uintptr_t)g_late_uef_predecessor,
                     &memory,
                     sizeof(memory)) != 0) {
      module = (HMODULE)memory.AllocationBase;
      DWORD length = GetModuleFileNameW(module, wide_module_path, MAX_PATH);
      if (length == 0u || length >= MAX_PATH ||
          !mdvm_utf16_to_utf8_buffer(wide_module_path, module_path, sizeof(module_path))) {
        snprintf(module_path, sizeof(module_path), "unknown-error-%lu",
                 (unsigned long)GetLastError());
      }
    }
  } else {
    snprintf(module_path, sizeof(module_path), "none");
  }
  fprintf(stderr,
          "WIN32_LATE_UEF_INSTALL predecessor=%p module=%s is_art=%d debugger=%d\n",
          (void*)g_late_uef_predecessor,
          module_path,
          module != NULL && module_is_art(module_path),
          IsDebuggerPresent() ? 1 : 0);
  fflush(stderr);
}
__declspec(dllexport) void Java_CrashNativeProbe_nativeInstallUefProbe__(
    JNIEnv* env, jclass cls) {
  Java_CrashNativeProbe_nativeInstallUefProbe(env, cls);
}


/* L-002: System.load / loadLibrary must call JNI_OnLoad so conscrypt can
 * RegisterNatives. AOSP routes this through Runtime.nativeLoad -> JVM_NativeLoad
 * in openjdkjvm; Win hybrid openjdkjvm is memory-only, so implement here. */
__declspec(dllexport) jstring Java_java_lang_Runtime_nativeLoad(
    JNIEnv* env, jclass ignored, jstring javaFilename, jobject javaLoader, jclass caller) {
  (void)ignored; (void)javaLoader; (void)caller;
  if (javaFilename == NULL) {
    return (*env)->NewStringUTF(env, "library path is null");
  }
  wchar_t* filename = win_jstring_to_utf16(env, javaFilename);
  if (filename == NULL) {
    return (*env)->NewStringUTF(env, "library path UTF-16 copy failed");
  }

  /* Prefer full ART LoadNativeLibrary if exported (future openjdkjvm). */
  typedef jstring (*jvm_native_load_fn)(JNIEnv*, jstring, jobject, jclass);
  HMODULE ojj = GetModuleHandleW(L"libopenjdkjvm.dll");
  if (!ojj) ojj = GetModuleHandleW(L"openjdkjvm.dll");
  if (ojj) {
    jvm_native_load_fn jnl =
        (jvm_native_load_fn)GetProcAddress(ojj, "JVM_NativeLoad");
    if (jnl) {
      free(filename);
      return jnl(env, javaFilename, javaLoader, caller);
    }
  }

  SetLastError(0);
  HMODULE mod = LoadLibraryW(filename);
  if (!mod) {
    char buf[512];
    snprintf(buf, sizeof(buf), "LoadLibraryW failed gle=%lu",
             (unsigned long)GetLastError());
    free(filename);
    return (*env)->NewStringUTF(env, buf);
  }

  typedef jint(JNICALL * jni_onload_fn)(JavaVM*, void*);
  jni_onload_fn onload = (jni_onload_fn)GetProcAddress(mod, "JNI_OnLoad");
  if (onload) {
    JavaVM* vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != 0 || vm == NULL) {
      free(filename);
      return (*env)->NewStringUTF(env, "GetJavaVM failed after LoadLibrary");
    }
    jint ver = onload(vm, NULL);
    if (ver == JNI_ERR) {
      free(filename);
      return (*env)->NewStringUTF(env, "JNI_OnLoad returned JNI_ERR");
    }
  }

  free(filename);
  return NULL; /* success */
}

__declspec(dllexport) jstring
Java_java_lang_Runtime_nativeLoad__Ljava_lang_String_2Ljava_lang_ClassLoader_2Ljava_lang_Class_2(
    JNIEnv* env, jclass ignored, jstring javaFilename, jobject javaLoader, jclass caller) {
  return Java_java_lang_Runtime_nativeLoad(env, ignored, javaFilename, javaLoader, caller);
}
