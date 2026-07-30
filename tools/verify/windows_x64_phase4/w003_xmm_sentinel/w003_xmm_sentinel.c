#include <jni.h>
#include <stdint.h>

__declspec(align(16)) const uint64_t g_w003_xmm_patterns[20] = {
    UINT64_C(0x061524334251607f), UINT64_C(0xf6e5d4c3b2a1908f),
    UINT64_C(0x1726354453627180), UINT64_C(0xe7d6c5b4a3928170),
    UINT64_C(0x2837465564738291), UINT64_C(0xd8c7b6a594837261),
    UINT64_C(0x39485766758493a2), UINT64_C(0xc9b8a79685746352),
    UINT64_C(0x4a5968778695a4b3), UINT64_C(0xbaa9988776655443),
    UINT64_C(0x5b6a798897a6b5c4), UINT64_C(0xab9a897867564534),
    UINT64_C(0x6c7b8a99a8b7c6d5), UINT64_C(0x9c8b7a6958473625),
    UINT64_C(0x7d8c9baab9c8d7e6), UINT64_C(0x8d7c6b5a49382716),
    UINT64_C(0x8e9dacbbcad9e8f7), UINT64_C(0x7e6d5c4b3a291807),
    UINT64_C(0x9faebdccdbeaf908), UINT64_C(0x6f5e4d3c2b1a09f8),
};

extern jint W003XmmSentinelAssembly(
    JNIEnv* env, jclass klass, jmethodID method, jint expected, jboolean clobber);
extern void W003XmmExceptionSentinelAssembly(
    JNIEnv* env, jclass klass, jmethodID method, jboolean clobber);

volatile jint g_w003_exception_xmm_mask = -1;

jint W003InvokeManagedCallback(JNIEnv* env, jclass klass, jmethodID method) {
  return (*env)->CallStaticIntMethod(
      env,
      klass,
      method,
      1.25,
      -2.5,
      3.75,
      -4.125,
      5.5,
      -6.625,
      7.75,
      -8.875,
      9.0,
      -10.25,
      11.5,
      -12.75);
}

jint W003InvokeManagedExceptionCallback(JNIEnv* env, jclass klass, jmethodID method) {
  return (*env)->CallStaticIntMethod(
      env,
      klass,
      method,
      NULL,
      1.25,
      -2.5,
      3.75,
      -4.125,
      5.5,
      -6.625,
      7.75,
      -8.875,
      9.0,
      -10.25,
      11.5,
      -12.75);
}

JNIEXPORT jint JNICALL Java_W003XmmSentinelProbe_runXmmSentinel(
    JNIEnv* env, jclass klass, jint expected, jboolean clobber) {
  jmethodID method = (*env)->GetStaticMethodID(
      env, klass, "managedCallback", "(DDDDDDDDDDDD)I");
  if (method == NULL) {
    return 1 << 11;
  }
  return W003XmmSentinelAssembly(env, klass, method, expected, clobber);
}

JNIEXPORT void JNICALL Java_W003XmmSentinelProbe_runXmmExceptionSentinel(
    JNIEnv* env, jclass klass, jboolean clobber) {
  jmethodID method = (*env)->GetStaticMethodID(
      env,
      klass,
      "managedExceptionCallback",
      "(LW003XmmSentinelProbe$Cell;DDDDDDDDDDDD)I");
  if (method == NULL) {
    g_w003_exception_xmm_mask = 1 << 11;
    return;
  }
  g_w003_exception_xmm_mask = 1 << 30;
  W003XmmExceptionSentinelAssembly(env, klass, method, clobber);
}

JNIEXPORT jint JNICALL Java_W003XmmSentinelProbe_getXmmExceptionMask(
    JNIEnv* env, jclass klass) {
  (void)env;
  (void)klass;
  return g_w003_exception_xmm_mask;
}
