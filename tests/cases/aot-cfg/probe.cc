#include <windows.h>

#include <jni.h>

#include <cstdint>
#include <iostream>

#include "art_method-inl.h"
#include "scoped_thread_state_change-inl.h"
#include "stack.h"

extern "C" uint64_t w032_guarded_invoke_static(art::ArtMethod *method,
                                               art::Thread *self,
                                               const void *target,
                                               uint32_t first_arg);

namespace {

jboolean Fail(JNIEnv *env, const char *message) {
  std::cerr << "W032_CFG_OBSERVATION_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message);
  }
  return JNI_FALSE;
}

bool IsRegisteredOatTarget(const void *entry, DWORD64 *image_base) {
  *image_base = 0u;
  PRUNTIME_FUNCTION function = RtlLookupFunctionEntry(
      reinterpret_cast<DWORD64>(entry), image_base, nullptr);
  return function != nullptr && *image_base != 0u &&
         function->BeginAddress ==
             reinterpret_cast<DWORD64>(entry) - *image_base;
}

uint64_t GuardedInvoke(art::Thread *self, art::ArtMethod *method,
                       const void *target, uint32_t first_arg) {
  art::ManagedStack fragment;
  self->PushManagedStackFragment(&fragment);
  uint64_t result = w032_guarded_invoke_static(method, self, target, first_arg);
  self->PopManagedStackFragment(fragment);
  return result;
}

} // namespace

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W032AotCfgProbe_nativeAudit(JNIEnv *env, jclass, jobject reflected_quick,
                                 jobject reflected_jni) {
  PROCESS_MITIGATION_CONTROL_FLOW_GUARD_POLICY cfg = {};
  if (!GetProcessMitigationPolicy(GetCurrentProcess(),
                                  ProcessControlFlowGuardPolicy, &cfg,
                                  sizeof(cfg))) {
    return Fail(env, "GetProcessMitigationPolicy(CFG) failed");
  }
  if (cfg.EnableControlFlowGuard == 0u) {
    return Fail(env, "CFG is not enabled in the ART process");
  }

  art::ScopedObjectAccess soa(env);
  art::ArtMethod *quick_method =
      art::ArtMethod::FromReflectedMethod(soa, reflected_quick);
  art::ArtMethod *jni_method =
      art::ArtMethod::FromReflectedMethod(soa, reflected_jni);
  if (quick_method == nullptr || jni_method == nullptr ||
      !quick_method->IsStatic() || quick_method->IsNative() ||
      !jni_method->IsStatic() || !jni_method->IsNative()) {
    return Fail(env, "reflected quick/JNI method classification is invalid");
  }

  const void *quick_target =
      quick_method->GetOatMethodQuickCode(art::kRuntimePointerSize);
  const void *jni_target =
      jni_method->GetOatMethodQuickCode(art::kRuntimePointerSize);
  DWORD64 quick_base = 0u;
  DWORD64 jni_base = 0u;
  if (quick_target == nullptr ||
      !IsRegisteredOatTarget(quick_target, &quick_base)) {
    return Fail(
        env, "managed quick target is not an exact registered boot-OAT entry");
  }
  if (jni_target == nullptr || !IsRegisteredOatTarget(jni_target, &jni_base) ||
      jni_base != quick_base) {
    return Fail(env, "JNI target is not an exact entry in the same boot OAT");
  }

  art::Thread *self = soa.Self();
  constexpr uint32_t kNegative123 = static_cast<uint32_t>(-123);
  uint64_t quick_result =
      GuardedInvoke(self, quick_method, quick_target, kNegative123);
  if (self->IsExceptionPending() || static_cast<int32_t>(quick_result) != 123) {
    return Fail(env, "guarded managed quick invocation failed");
  }
  uint64_t jni_result = GuardedInvoke(self, jni_method, jni_target, 0u);
  if (self->IsExceptionPending() || jni_result == 0u) {
    return Fail(env, "guarded compiled JNI invocation failed");
  }

  std::cout << "W032_CFG_OBSERVATION_PASS cfg_enabled="
            << cfg.EnableControlFlowGuard << " cfg_strict=" << cfg.StrictMode
            << " cfg_export_suppression=" << cfg.EnableExportSuppression
            << " guard_dispatch=verified guarded_quick=pass guarded_jni=pass"
            << " target_api_calls=0\n";
  return JNI_TRUE;
}
