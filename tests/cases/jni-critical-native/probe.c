#include <jni.h>

static volatile jint g_calls;
static volatile jint g_dlsym_calls;

static jlong CriticalZero(void) {
  g_calls |= 1;
  return 7;
}

static jlong CriticalSixLongs(jlong a, jlong b, jlong c, jlong d, jlong e, jlong f) {
  g_calls |= 2;
  return a + 3 * b + 5 * c + 7 * d + 11 * e + 13 * f;
}

static jdouble CriticalSixDoubles(
    jdouble a, jdouble b, jdouble c, jdouble d, jdouble e, jdouble f) {
  g_calls |= 4;
  return a + 2.0 * b + 3.0 * c + 4.0 * d + 5.0 * e + 6.0 * f;
}

static jdouble CriticalMixed(
    jlong a, jdouble b, jint c, jdouble d, jlong e, jdouble f) {
  g_calls |= 8;
  return (jdouble)a + 2.0 * b + 3.0 * (jdouble)c + 4.0 * d +
      5.0 * (jdouble)e + 6.0 * f;
}

static jint CriticalMixed32(jint a, jfloat b, jint c, jfloat d, jint e, jfloat f) {
  g_calls |= 16;
  return a + (jint)(2.0f * b) + 3 * c + (jint)(4.0f * d) +
      5 * e + (jint)(6.0f * f);
}

static jfloat CriticalFloatReturn(jfloat a, jint b) {
  g_calls |= 32;
  return a + 2.0f * (jfloat)b;
}

static jint NormalCalls(JNIEnv* env, jclass klass) {
  (void)env;
  (void)klass;
  return g_calls;
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
  (void)reserved;
  JNIEnv* env = NULL;
  if ((*vm)->GetEnv(vm, (void**)&env, JNI_VERSION_1_6) != JNI_OK) {
    return JNI_ERR;
  }

  jclass probe = (*env)->FindClass(env, "CriticalNativeProbe");
  if (probe == NULL) {
    return JNI_ERR;
  }

  const JNINativeMethod methods[] = {
      {"zero", "()J", (void*)CriticalZero},
      {"sixLongs", "(JJJJJJ)J", (void*)CriticalSixLongs},
      {"sixDoubles", "(DDDDDD)D", (void*)CriticalSixDoubles},
      {"mixed", "(JDIDJD)D", (void*)CriticalMixed},
      {"mixed32", "(IFIFIF)I", (void*)CriticalMixed32},
      {"floatReturn", "(FI)F", (void*)CriticalFloatReturn},
      {"calls", "()I", (void*)NormalCalls},
  };
  if ((*env)->RegisterNatives(
          env, probe, methods, (jint)(sizeof(methods) / sizeof(methods[0]))) != JNI_OK) {
    return JNI_ERR;
  }
  return JNI_VERSION_1_6;
}

jlong Java_CriticalNativeDlsymProbe_zero(void) {
  g_dlsym_calls |= 1;
  return 7;
}

jlong Java_CriticalNativeDlsymProbe_sixLongs(
    jlong a, jlong b, jlong c, jlong d, jlong e, jlong f) {
  g_dlsym_calls |= 2;
  return a + 3 * b + 5 * c + 7 * d + 11 * e + 13 * f;
}

jdouble Java_CriticalNativeDlsymProbe_sixDoubles(
    jdouble a, jdouble b, jdouble c, jdouble d, jdouble e, jdouble f) {
  g_dlsym_calls |= 4;
  return a + 2.0 * b + 3.0 * c + 4.0 * d + 5.0 * e + 6.0 * f;
}

jdouble Java_CriticalNativeDlsymProbe_mixed(
    jlong a, jdouble b, jint c, jdouble d, jlong e, jdouble f) {
  g_dlsym_calls |= 8;
  return (jdouble)a + 2.0 * b + 3.0 * (jdouble)c + 4.0 * d +
      5.0 * (jdouble)e + 6.0 * f;
}

jint Java_CriticalNativeDlsymProbe_mixed32(
    jint a, jfloat b, jint c, jfloat d, jint e, jfloat f) {
  g_dlsym_calls |= 16;
  return a + (jint)(2.0f * b) + 3 * c + (jint)(4.0f * d) +
      5 * e + (jint)(6.0f * f);
}

jfloat Java_CriticalNativeDlsymProbe_floatReturn(jfloat a, jint b) {
  g_dlsym_calls |= 32;
  return a + 2.0f * (jfloat)b;
}

jint Java_CriticalNativeDlsymProbe_callMask(void) {
  return g_dlsym_calls;
}
