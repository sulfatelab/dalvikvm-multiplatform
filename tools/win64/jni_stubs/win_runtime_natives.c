/* java.lang.Runtime free/total/max memory + nativeGc for Win64 PE stubs. */
#include <jni.h>
#include <windows.h>

typedef jlong (*jvm_long_fn)(void);
typedef void (*jvm_void_fn)(void);

static HMODULE art_module(void) {
  HMODULE m = GetModuleHandleA("art.dll");
  if (!m) m = GetModuleHandleA("libart.dll");
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
  volatile int* p = (volatile int*)0;
  *p = 0x41414141;
}
__declspec(dllexport) void Java_CrashNativeProbe_nativeSegfault__(JNIEnv* env, jclass cls) {
  Java_CrashNativeProbe_nativeSegfault(env, cls);
}
