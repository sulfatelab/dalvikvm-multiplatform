#include <windows.h>

#include <jni.h>

#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <unordered_set>
#include <vector>

#include "art_method-inl.h"
#include "oat/oat_file.h"
#include "scoped_thread_state_change-inl.h"
#include "stack.h"

extern "C" uint64_t w032_guarded_invoke_static(art::ArtMethod *method,
                                               art::Thread *self,
                                               const void *target,
                                               uint32_t first_arg);

namespace {

jboolean Fail(JNIEnv *env, const std::string &message) {
  std::cerr << "W032_CFG_OBSERVATION_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message.c_str());
  }
  return JNI_FALSE;
}

bool HasCfgDiagnostic(const std::string &message) {
  return message.find("Windows OAT CFG") != std::string::npos ||
         message.find(".oat_cfg.windows") != std::string::npos ||
         message.find("oatcfgwindows") != std::string::npos;
}

bool OpenOat(const std::filesystem::path &path, bool executable,
             std::string *error_message) {
  std::unique_ptr<art::OatFile> oat_file(art::OatFile::Open(
      /*zip_fd=*/-1, path.string(), path.string(), executable,
      /*low_4gb=*/false, error_message));
  return oat_file != nullptr;
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
Java_W032AotCfgProbe_nativeAuditCorruption(JNIEnv *env, jclass) {
  const char *root_value = std::getenv("W032_CFG_CORRUPTION_ROOT");
  if (root_value == nullptr || root_value[0] == '\0') {
    return Fail(env, "W032_CFG_CORRUPTION_ROOT is missing");
  }
  const std::filesystem::path root(root_value);
  std::ifstream case_stream(root / "cases.txt");
  if (!case_stream) {
    return Fail(env, "cannot read the CFG corruption case list");
  }

  std::vector<std::string> cases;
  std::unordered_set<std::string> unique_cases;
  std::string name;
  while (std::getline(case_stream, name)) {
    if (!name.empty() && name.back() == '\r') {
      name.pop_back();
    }
    if (name.empty() ||
        name.find_first_not_of("abcdefghijklmnopqrstuvwxyz-") !=
            std::string::npos ||
        !unique_cases.insert(name).second) {
      return Fail(env, "CFG corruption case list is malformed");
    }
    cases.push_back(name);
  }
  if (!case_stream.eof() || cases.size() != 18u) {
    return Fail(env, "CFG corruption case list must contain 18 cases");
  }

  for (bool executable : {false, true}) {
    std::string error_message;
    if (!OpenOat(root / "canonical.oat", executable, &error_message)) {
      return Fail(env, std::string("canonical CFG OAT open failed: ") +
                           error_message);
    }
  }
  for (const std::string &case_name : cases) {
    for (bool executable : {false, true}) {
      std::string error_message;
      if (OpenOat(root / (case_name + ".oat"), executable, &error_message)) {
        return Fail(env, "corrupt CFG OAT was accepted: " + case_name);
      }
      if (!HasCfgDiagnostic(error_message)) {
        return Fail(env, "corrupt CFG OAT has an unrelated diagnostic: " +
                             case_name + ": " + error_message);
      }
    }
  }

  std::cout << "W032_CFG_CORRUPTION_PASS cases=18 opens=38 "
               "validation_only=19 executable=19\n";
  return JNI_TRUE;
}

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
