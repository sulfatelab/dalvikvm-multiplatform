#include <jni.h>
#include <jvmti.h>

#include <stdint.h>
#include <string.h>
#include <windows.h>

static jvmtiEnv* g_jvmti;
static volatile LONG64 g_single_step_count;

static void JNICALL SingleStep(jvmtiEnv* jvmti,
                               JNIEnv* env,
                               jthread thread,
                               jmethodID method,
                               jlocation location) {
  (void)jvmti;
  (void)env;
  (void)thread;
  (void)method;
  (void)location;
  InterlockedIncrement64(&g_single_step_count);
}

JNIEXPORT jint JNICALL Agent_OnLoad(JavaVM* vm, char* options, void* reserved) {
  (void)options;
  (void)reserved;

  if ((*vm)->GetEnv(vm, (void**)&g_jvmti, JVMTI_VERSION_1_2) != JNI_OK || g_jvmti == NULL) {
    return JNI_ERR;
  }

  jvmtiCapabilities capabilities;
  memset(&capabilities, 0, sizeof(capabilities));
  capabilities.can_generate_single_step_events = 1;
  if ((*g_jvmti)->AddCapabilities(g_jvmti, &capabilities) != JVMTI_ERROR_NONE) {
    return JNI_ERR;
  }

  jvmtiEventCallbacks callbacks;
  memset(&callbacks, 0, sizeof(callbacks));
  callbacks.SingleStep = SingleStep;
  if ((*g_jvmti)->SetEventCallbacks(g_jvmti, &callbacks, sizeof(callbacks)) != JVMTI_ERROR_NONE) {
    return JNI_ERR;
  }

  return JNI_OK;
}

static jdouble NormalRegistered(JNIEnv* env,
                                jclass klass,
                                jlong a,
                                jdouble b,
                                jint c,
                                jfloat d) {
  (void)env;
  (void)klass;
  return (jdouble)a + b + (jdouble)c + (jdouble)d + 100.0;
}

static jdouble FastRegistered(JNIEnv* env,
                              jclass klass,
                              jlong a,
                              jdouble b,
                              jint c,
                              jfloat d) {
  (void)env;
  (void)klass;
  return (jdouble)a + b + (jdouble)c + (jdouble)d + 200.0;
}

static jdouble CriticalRegistered(jlong a, jdouble b, jint c, jfloat d) {
  return (jdouble)a + b + (jdouble)c + (jdouble)d + 300.0;
}

JNIEXPORT jdouble JNICALL Java_JvmtiForceProbe_normalDlsym(JNIEnv* env,
                                                           jclass klass,
                                                           jlong a,
                                                           jdouble b,
                                                           jint c,
                                                           jfloat d) {
  (void)env;
  (void)klass;
  return (jdouble)a + b + (jdouble)c + (jdouble)d + 400.0;
}

JNIEXPORT jdouble JNICALL Java_JvmtiForceProbe_fastDlsym(JNIEnv* env,
                                                         jclass klass,
                                                         jlong a,
                                                         jdouble b,
                                                         jint c,
                                                         jfloat d) {
  (void)env;
  (void)klass;
  return (jdouble)a + b + (jdouble)c + (jdouble)d + 500.0;
}

JNIEXPORT jdouble JNICALL Java_JvmtiForceProbe_criticalDlsym(jlong a,
                                                             jdouble b,
                                                             jint c,
                                                             jfloat d) {
  return (jdouble)a + b + (jdouble)c + (jdouble)d + 600.0;
}

JNIEXPORT jint JNICALL Java_JvmtiForceProbe_setSingleStep(JNIEnv* env,
                                                           jclass klass,
                                                           jboolean enable) {
  (void)klass;
  if (g_jvmti == NULL) {
    return (jint)JVMTI_ERROR_INTERNAL;
  }

  jthread current = NULL;
  jvmtiError error = (*g_jvmti)->GetCurrentThread(g_jvmti, &current);
  if (error != JVMTI_ERROR_NONE) {
    return (jint)error;
  }
  error = (*g_jvmti)->SetEventNotificationMode(
      g_jvmti,
      enable ? JVMTI_ENABLE : JVMTI_DISABLE,
      JVMTI_EVENT_SINGLE_STEP,
      current);
  (*env)->DeleteLocalRef(env, current);
  return (jint)error;
}

JNIEXPORT jlong JNICALL Java_JvmtiForceProbe_singleStepCount(JNIEnv* env, jclass klass) {
  (void)env;
  (void)klass;
  return (jlong)InterlockedCompareExchange64(&g_single_step_count, 0, 0);
}

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
  (void)reserved;
  JNIEnv* env = NULL;
  if ((*vm)->GetEnv(vm, (void**)&env, JNI_VERSION_1_6) != JNI_OK) {
    return JNI_ERR;
  }

  jclass klass = (*env)->FindClass(env, "JvmtiForceProbe");
  if (klass == NULL) {
    return JNI_ERR;
  }

  const JNINativeMethod methods[] = {
      {"normalRegistered", "(JDIF)D", (void*)NormalRegistered},
      {"fastRegistered", "(JDIF)D", (void*)FastRegistered},
      {"criticalRegistered", "(JDIF)D", (void*)CriticalRegistered},
  };
  if ((*env)->RegisterNatives(
          env, klass, methods, (jint)(sizeof(methods) / sizeof(methods[0]))) != JNI_OK) {
    return JNI_ERR;
  }
  return JNI_VERSION_1_6;
}
