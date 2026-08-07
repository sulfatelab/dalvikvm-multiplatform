#include <windows.h>

#include <jni.h>

#include <cstdint>
#include <iostream>
#include <string>

#include "art_method-inl.h"
#include "oat/oat.h"
#include "scoped_thread_state_change-inl.h"

namespace {

uintptr_t g_exception_entry = 0u;
std::string g_exception_target;

void ResetExceptionState() {
  g_exception_entry = 0u;
  g_exception_target.clear();
}

jboolean Fail(JNIEnv* env, const char* message) {
  std::cerr << "W038_BOOT_OAT_UNWIND_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message);
  }
  return JNI_FALSE;
}

jint FailIndex(JNIEnv* env, const char* message) {
  Fail(env, message);
  return -1;
}

bool IsCurrentRegisteredBootOatMethod(art::ArtMethod* method,
                                      const void** entry,
                                      DWORD64* oat_base,
                                      RUNTIME_FUNCTION* function) {
  if (method == nullptr || method->IsNative() || !method->IsInvokable()) {
    return false;
  }
  const void* oat_entry = method->GetOatMethodQuickCode(art::kRuntimePointerSize);
  const void* current_entry = method->GetEntryPointFromQuickCompiledCode();
  if (oat_entry == nullptr || current_entry != oat_entry) {
    return false;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION registered =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(current_entry), &image_base, nullptr);
  if (registered == nullptr || image_base == 0u ||
      registered->BeginAddress != reinterpret_cast<DWORD64>(current_entry) - image_base) {
    return false;
  }
  const art::OatHeader* header = reinterpret_cast<const art::OatHeader*>(image_base);
  if (!header->IsValid()) {
    return false;
  }
  *entry = current_entry;
  *oat_base = image_base;
  *function = *registered;
  return true;
}

jint SelectCurrentBootOatMethod(JNIEnv* env,
                                jobjectArray candidates,
                                const void** entry,
                                DWORD64* oat_base,
                                RUNTIME_FUNCTION* function,
                                std::string* target) {
  art::ScopedObjectAccess soa(env);
  for (jsize index = 0; index < env->GetArrayLength(candidates); ++index) {
    jobject reflected = env->GetObjectArrayElement(candidates, index);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    env->DeleteLocalRef(reflected);
    if (IsCurrentRegisteredBootOatMethod(method, entry, oat_base, function)) {
      *target = method->PrettyMethod();
      return index;
    }
  }
  return -1;
}

}  // namespace

extern "C" __declspec(dllexport) jint JNICALL
Java_W038BootOatManagedExceptionProbe_nativeBegin(JNIEnv* env,
                                                   jclass,
                                                   jobjectArray candidates) {
  ResetExceptionState();
  const void* entry = nullptr;
  DWORD64 oat_base = 0u;
  RUNTIME_FUNCTION function = {};
  std::string target;
  const jint selected =
      SelectCurrentBootOatMethod(env, candidates, &entry, &oat_base, &function, &target);
  if (selected < 0 || entry == nullptr || oat_base == 0u) {
    return FailIndex(env, "no explicit-exception method retained registered boot-OAT code");
  }
  g_exception_entry = reinterpret_cast<uintptr_t>(entry);
  g_exception_target = target;
  return selected;
}

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W038BootOatManagedExceptionProbe_nativeVerify(JNIEnv* env,
                                                    jclass,
                                                    jobject reflected,
                                                    jboolean caught,
                                                    jboolean trace_target) {
  bool entry_unchanged = false;
  {
    art::ScopedObjectAccess soa(env);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    const void* entry = nullptr;
    DWORD64 oat_base = 0u;
    RUNTIME_FUNCTION function = {};
    entry_unchanged =
        IsCurrentRegisteredBootOatMethod(method, &entry, &oat_base, &function) &&
        reinterpret_cast<uintptr_t>(entry) == g_exception_entry;
  }

  const uintptr_t expected_entry = g_exception_entry;
  const std::string target = g_exception_target;
  ResetExceptionState();
  if (caught != JNI_TRUE || trace_target != JNI_TRUE || expected_entry == 0u ||
      !entry_unchanged) {
    return Fail(env, "explicit managed exception did not retain its boot-OAT contract");
  }

  std::cout << "W038_MANAGED_EXCEPTION_PASS target=" << target
            << " type=explicit caught=1 trace=nonempty trace_target=1"
            << " entry_unchanged=1 jit=disabled\n";
  return JNI_TRUE;
}

extern "C" __declspec(dllexport) jint JNICALL
Java_W038BootOatFatalUnwindProbe_nativeArmFatal(JNIEnv* env,
                                                jclass,
                                                jobjectArray candidates) {
  const void* entry = nullptr;
  DWORD64 oat_base = 0u;
  RUNTIME_FUNCTION function = {};
  std::string target;
  const jint selected =
      SelectCurrentBootOatMethod(env, candidates, &entry, &oat_base, &function, &target);
  if (selected < 0 || entry == nullptr || oat_base == 0u ||
      function.BeginAddress >= function.EndAddress) {
    return FailIndex(env, "no callback method retained registered boot-OAT code");
  }

  std::cout << "W038_FATAL_ARM target=" << target << " oat_base=0x" << std::hex
            << oat_base << " begin=0x" << function.BeginAddress << " end=0x"
            << function.EndAddress << std::dec << " jit=disabled\n";
  std::cout.flush();
  return selected;
}

extern "C" __declspec(dllexport) void JNICALL
Java_W038BootOatFatalUnwindProbe_nativeCrash(JNIEnv*, jclass) {
  std::cout << "W038_FATAL_CRASH_ENTER native_callback=1\n";
  std::cout.flush();
  volatile uint32_t* invalid = reinterpret_cast<volatile uint32_t*>(uintptr_t{0x1234u});
  *invalid = 0x57303338u;
}
