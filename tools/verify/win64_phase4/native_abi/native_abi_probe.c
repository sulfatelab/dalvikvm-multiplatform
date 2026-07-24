#include <jni.h>

static volatile jint g_calls;

static jdouble MixedValue(
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k) {
  return (jdouble)a + 2.0 * b + 3.0 * (jdouble)c + 4.0 * (jdouble)d +
      5.0 * (jdouble)e + 6.0 * f + 7.0 * (jdouble)g + 8.0 * (jdouble)h +
      9.0 * i + 10.0 * j + 11.0 * (jdouble)k;
}

static jdouble NormalRegistered(
    JNIEnv* env,
    jclass klass,
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k) {
  (void)env;
  (void)klass;
  g_calls |= 1;
  return MixedValue(a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble FastRegistered(
    JNIEnv* env,
    jclass klass,
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k) {
  (void)env;
  (void)klass;
  g_calls |= 2;
  return 1000.0 + MixedValue(a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble NormalInstance(
    JNIEnv* env,
    jobject self,
    jobject marker,
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k) {
  if (env == NULL || self == NULL || marker == NULL) {
    return -1.0;
  }
  g_calls |= 16;
  return 4000.0 + MixedValue(a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble FastInstance(
    JNIEnv* env,
    jobject self,
    jobject marker,
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k) {
  if (env == NULL || self == NULL || marker == NULL) {
    return -1.0;
  }
  g_calls |= 32;
  return 5000.0 + MixedValue(a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
  (void)reserved;
  JNIEnv* env = NULL;
  if ((*vm)->GetEnv(vm, (void**)&env, JNI_VERSION_1_6) != JNI_OK) {
    return JNI_ERR;
  }

  jclass probe = (*env)->FindClass(env, "FastNativeAbiProbe");
  if (probe == NULL) {
    return JNI_ERR;
  }

  const JNINativeMethod methods[] = {
      {"normalRegistered", "(JDIFJDIFDDI)D", (void*)NormalRegistered},
      {"fastRegistered", "(JDIFJDIFDDI)D", (void*)FastRegistered},
      {"normalInstance", "(Ljava/lang/Object;JDIFJDIFDDI)D", (void*)NormalInstance},
      {"fastInstance", "(Ljava/lang/Object;JDIFJDIFDDI)D", (void*)FastInstance},
  };
  if ((*env)->RegisterNatives(
          env, probe, methods, (jint)(sizeof(methods) / sizeof(methods[0]))) != JNI_OK) {
    return JNI_ERR;
  }
  return JNI_VERSION_1_6;
}

jdouble Java_FastNativeAbiProbe_normalDlsym(
    JNIEnv* env,
    jclass klass,
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k,
    jboolean l) {
  (void)env;
  (void)klass;
  g_calls |= 4;
  return 2000.0 + MixedValue(a, b, c, d, e, f, g, h, i, j, k) + (l ? 12.0 : 0.0);
}

jdouble Java_FastNativeAbiProbe_fastDlsym(
    JNIEnv* env,
    jclass klass,
    jlong a,
    jdouble b,
    jint c,
    jfloat d,
    jlong e,
    jdouble f,
    jint g,
    jfloat h,
    jdouble i,
    jdouble j,
    jint k,
    jboolean l) {
  (void)env;
  (void)klass;
  g_calls |= 8;
  return 3000.0 + MixedValue(a, b, c, d, e, f, g, h, i, j, k) + (l ? 12.0 : 0.0);
}

jint Java_FastNativeAbiProbe_callMask(JNIEnv* env, jclass klass) {
  (void)env;
  (void)klass;
  return g_calls;
}
