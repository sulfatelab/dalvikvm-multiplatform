#include <jni.h>
#include <stdint.h>
#include <windows.h>

typedef void (__cdecl* FrameProbeReset)(void);
typedef void (__cdecl* FrameProbeSnapshot)(uint64_t* counters);

static FrameProbeReset g_reset;
static FrameProbeSnapshot g_snapshot;

static void ThrowLinkError(JNIEnv* env, const char* message) {
  jclass exception = (*env)->FindClass(env, "java/lang/UnsatisfiedLinkError");
  if (exception != NULL) {
    (*env)->ThrowNew(env, exception, message);
  }
}

static int ResolveProbe(JNIEnv* env) {
  if (g_reset != NULL && g_snapshot != NULL) {
    return 1;
  }
  HMODULE art = GetModuleHandleW(L"art.dll");
  if (art == NULL) {
    ThrowLinkError(env, "instrumented art.dll is not loaded");
    return 0;
  }
  g_reset = (FrameProbeReset)GetProcAddress(art, "art_w003_frame_probe_reset");
  g_snapshot =
      (FrameProbeSnapshot)GetProcAddress(art, "art_w003_frame_probe_snapshot");
  if (g_reset == NULL || g_snapshot == NULL) {
    ThrowLinkError(env, "instrumented ART frame-probe exports are missing");
    return 0;
  }
  return 1;
}

JNIEXPORT void JNICALL Java_W003FrameProbe_resetCounters(JNIEnv* env, jclass klass) {
  (void)klass;
  if (ResolveProbe(env)) {
    g_reset();
  }
}

JNIEXPORT jlongArray JNICALL Java_W003FrameProbe_snapshotCounters(
    JNIEnv* env, jclass klass) {
  (void)klass;
  if (!ResolveProbe(env)) {
    return NULL;
  }
  uint64_t counters[4];
  g_snapshot(counters);
  jlong values[4] = {
      (jlong)counters[0],
      (jlong)counters[1],
      (jlong)counters[2],
      (jlong)counters[3],
  };
  jlongArray result = (*env)->NewLongArray(env, 4);
  if (result != NULL) {
    (*env)->SetLongArrayRegion(env, result, 0, 4, values);
  }
  return result;
}

JNIEXPORT jint JNICALL Java_W003FrameProbe_nativeEcho(
    JNIEnv* env, jclass klass, jobject marker, jint value) {
  (void)env;
  (void)klass;
  return value + (marker != NULL ? 1 : 0);
}
