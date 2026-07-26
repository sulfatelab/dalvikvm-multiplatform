#include <jni.h>
#include <stdint.h>

__declspec(align(16)) const uint64_t g_w003_xmm_patterns[12] = {
    UINT64_C(0x061524334251607f), UINT64_C(0xf6e5d4c3b2a1908f),
    UINT64_C(0x1726354453627180), UINT64_C(0xe7d6c5b4a3928170),
    UINT64_C(0x2837465564738291), UINT64_C(0xd8c7b6a594837261),
    UINT64_C(0x39485766758493a2), UINT64_C(0xc9b8a79685746352),
    UINT64_C(0x4a5968778695a4b3), UINT64_C(0xbaa9988776655443),
    UINT64_C(0x5b6a798897a6b5c4), UINT64_C(0xab9a897867564534),
};

extern jint W003XmmSentinelAssembly(
    JNIEnv* env, jclass klass, jmethodID method, jint expected, jboolean clobber);

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

JNIEXPORT jint JNICALL Java_W003XmmSentinelProbe_runXmmSentinel(
    JNIEnv* env, jclass klass, jint expected, jboolean clobber) {
  jmethodID method = (*env)->GetStaticMethodID(
      env, klass, "managedCallback", "(DDDDDDDDDDDD)I");
  if (method == NULL) {
    return 1 << 7;
  }
  return W003XmmSentinelAssembly(env, klass, method, expected, clobber);
}
