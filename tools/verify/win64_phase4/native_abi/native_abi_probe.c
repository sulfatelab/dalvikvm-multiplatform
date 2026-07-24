#include <jni.h>

static volatile jint g_calls;
static volatile jint g_dlsym_phase_offset;

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

static jdouble RecordValue(
    jint call_bit,
    jdouble offset,
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
  g_calls |= call_bit;
  return offset + MixedValue(a, b, c, d, e, f, g, h, i, j, k);
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
  return RecordValue(1, 0.0, a, b, c, d, e, f, g, h, i, j, k);
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
  return RecordValue(2, 1000.0, a, b, c, d, e, f, g, h, i, j, k);
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
  return RecordValue(16, 4000.0, a, b, c, d, e, f, g, h, i, j, k);
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
  return RecordValue(32, 5000.0, a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble AlternateNormalRegistered(
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
  return RecordValue(1, 20000.0, a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble AlternateFastRegistered(
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
  return RecordValue(2, 21000.0, a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble AlternateNormalDlsym(
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
  return RecordValue(4, 22000.0 + (l ? 12.0 : 0.0), a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble AlternateFastDlsym(
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
  return RecordValue(8, 23000.0 + (l ? 12.0 : 0.0), a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble AlternateNormalInstance(
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
  return RecordValue(16, 24000.0, a, b, c, d, e, f, g, h, i, j, k);
}

static jdouble AlternateFastInstance(
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
  return RecordValue(32, 25000.0, a, b, c, d, e, f, g, h, i, j, k);
}

static void ThrowIllegalState(JNIEnv* env, const char* message) {
  jclass exception = (*env)->FindClass(env, "java/lang/IllegalStateException");
  if (exception != NULL) {
    (*env)->ThrowNew(env, exception, message);
  }
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

JNIEXPORT jdouble JNICALL Java_FastNativeAbiProbe_normalRegistered(
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
  return RecordValue(1, g_dlsym_phase_offset, a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jdouble JNICALL Java_FastNativeAbiProbe_fastRegistered(
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
  return RecordValue(2, g_dlsym_phase_offset + 1000.0, a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jdouble JNICALL Java_FastNativeAbiProbe_normalDlsym(
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
  return RecordValue(
      4, g_dlsym_phase_offset + 2000.0 + (l ? 12.0 : 0.0), a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jdouble JNICALL Java_FastNativeAbiProbe_fastDlsym(
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
  return RecordValue(
      8, g_dlsym_phase_offset + 3000.0 + (l ? 12.0 : 0.0), a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jdouble JNICALL Java_FastNativeAbiProbe_normalInstance(
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
  return RecordValue(
      16, g_dlsym_phase_offset + 4000.0, a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jdouble JNICALL Java_FastNativeAbiProbe_fastInstance(
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
  return RecordValue(
      32, g_dlsym_phase_offset + 5000.0, a, b, c, d, e, f, g, h, i, j, k);
}

JNIEXPORT jint JNICALL Java_FastNativeAbiProbe_callMask(JNIEnv* env, jclass klass) {
  (void)env;
  (void)klass;
  return g_calls;
}

JNIEXPORT void JNICALL Java_FastNativeAbiProbe_unregisterNatives(JNIEnv* env, jclass klass) {
  if ((*env)->UnregisterNatives(env, klass) != JNI_OK) {
    ThrowIllegalState(env, "UnregisterNatives failed");
    return;
  }
  g_dlsym_phase_offset = 10000;
  g_calls = 0;
}

JNIEXPORT void JNICALL Java_FastNativeAbiProbe_registerAlternateNatives(
    JNIEnv* env, jclass klass) {
  const JNINativeMethod methods[] = {
      {"normalRegistered", "(JDIFJDIFDDI)D", (void*)AlternateNormalRegistered},
      {"fastRegistered", "(JDIFJDIFDDI)D", (void*)AlternateFastRegistered},
      {"normalDlsym", "(JDIFJDIFDDIZ)D", (void*)AlternateNormalDlsym},
      {"fastDlsym", "(JDIFJDIFDDIZ)D", (void*)AlternateFastDlsym},
      {"normalInstance", "(Ljava/lang/Object;JDIFJDIFDDI)D", (void*)AlternateNormalInstance},
      {"fastInstance", "(Ljava/lang/Object;JDIFJDIFDDI)D", (void*)AlternateFastInstance},
  };
  if ((*env)->RegisterNatives(
          env, klass, methods, (jint)(sizeof(methods) / sizeof(methods[0]))) != JNI_OK) {
    ThrowIllegalState(env, "second RegisterNatives failed");
    return;
  }
  g_calls = 0;
}
