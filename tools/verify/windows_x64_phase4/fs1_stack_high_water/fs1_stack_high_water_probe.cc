#include <windows.h>

#include <jni.h>

#include <cstdio>

namespace {

using DumpHighWater = int (*)(const char* label);

void ThrowAssertion(JNIEnv* env, const char* message) {
  jclass assertion = env->FindClass("java/lang/AssertionError");
  if (assertion != nullptr) {
    env->ThrowNew(assertion, message);
  }
}

}  // namespace

extern "C" __declspec(dllexport) jboolean JNICALL
Java_FS1StackHighWaterProbe_dumpHighWater(JNIEnv* env, jclass, jstring label) {
  HMODULE art = GetModuleHandleW(L"art.dll");
  if (art == nullptr) {
    ThrowAssertion(env, "art.dll is not loaded");
    return JNI_FALSE;
  }
  auto dump = reinterpret_cast<DumpHighWater>(
      GetProcAddress(art, "artWin32DumpStackOverflowHighWater"));
  if (dump == nullptr) {
    ThrowAssertion(env, "instrumented ART high-water export is missing");
    return JNI_FALSE;
  }
  const char* chars = env->GetStringUTFChars(label, nullptr);
  if (chars == nullptr) {
    return JNI_FALSE;
  }
  const int result = dump(chars);
  env->ReleaseStringUTFChars(label, chars);
  if (result == 0) {
    std::fprintf(stderr, "FS-1 incomplete high-water record\n");
    return JNI_FALSE;
  }
  return JNI_TRUE;
}
