#include <windows.h>

#include <jni.h>

#include <iostream>

#include "art_method-inl.h"
#include "jit/jit.h"
#include "jit/jit_code_cache.h"
#include "runtime.h"
#include "scoped_thread_state_change-inl.h"

namespace {

jboolean ThrowFailure(JNIEnv* env, const char* message) {
  std::cerr << "Windows x64 JIT unwind lifecycle FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message);
  }
  return JNI_FALSE;
}

PRUNTIME_FUNCTION Lookup(const void* pc, DWORD64* image_base) {
  *image_base = 0u;
  return RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(pc), image_base, nullptr);
}

}  // namespace

extern "C" __declspec(dllexport) jboolean JNICALL
Java_JitUnwindLifecycleProbe_nativeRun(JNIEnv* env, jclass, jobject reflected_method) {
  art::Runtime* runtime = art::Runtime::Current();
  art::jit::Jit* jit = runtime != nullptr ? runtime->GetJit() : nullptr;
  if (jit == nullptr) {
    return ThrowFailure(env, "ART JIT is unavailable");
  }

  art::jit::JitCodeCache* code_cache = jit->GetCodeCache();
  if (!code_cache->GetGarbageCollectCode()) {
    return ThrowFailure(env, "ART JIT code-cache collection is disabled");
  }

  art::Thread* self = art::Thread::Current();
  art::ArtMethod* method = nullptr;
  const void* old_entry = nullptr;
  {
    art::ScopedObjectAccess soa(env);
    method = art::ArtMethod::FromReflectedMethod(soa, reflected_method);
    if (method == nullptr || method->IsNative()) {
      return ThrowFailure(env, "probe method is missing or native");
    }
    if (!jit->CompileMethod(method,
                            self,
                            art::CompilationKind::kOptimized,
                            /*prejit=*/ false)) {
      return ThrowFailure(env, "initial optimized compilation failed");
    }
    old_entry = method->GetEntryPointFromQuickCompiledCode();
    if (!code_cache->ContainsPc(old_entry)) {
      return ThrowFailure(env, "initial entrypoint is outside the JIT code cache");
    }
  }

  DWORD64 old_image_base = 0u;
  if (Lookup(old_entry, &old_image_base) == nullptr) {
    return ThrowFailure(env, "initial JIT runtime-function lookup failed");
  }

  {
    art::ScopedObjectAccess soa(env);
    code_cache->InvalidateAllCompiledCode();
  }

  DWORD64 invalidated_image_base = 0u;
  if (Lookup(old_entry, &invalidated_image_base) == nullptr ||
      invalidated_image_base != old_image_base) {
    return ThrowFailure(env, "invalidation removed or changed live unwind metadata");
  }

  code_cache->DoCollection(self);

  DWORD64 deleted_image_base = 0u;
  if (Lookup(old_entry, &deleted_image_base) != nullptr) {
    return ThrowFailure(env, "collected JIT code still has a runtime-function entry");
  }

  const void* new_entry = nullptr;
  {
    art::ScopedObjectAccess soa(env);
    if (!jit->CompileMethod(method,
                            self,
                            art::CompilationKind::kOptimized,
                            /*prejit=*/ false)) {
      return ThrowFailure(env, "recompilation after collection failed");
    }
    new_entry = method->GetEntryPointFromQuickCompiledCode();
    if (!code_cache->ContainsPc(new_entry)) {
      return ThrowFailure(env, "recompiled entrypoint is outside the JIT code cache");
    }
  }

  DWORD64 new_image_base = 0u;
  if (Lookup(new_entry, &new_image_base) == nullptr || new_image_base != old_image_base) {
    return ThrowFailure(env, "recompiled JIT runtime-function lookup/base check failed");
  }
  if (new_entry != old_entry) {
    return ThrowFailure(env, "mspace did not reuse the collected code allocation");
  }

  std::cout << "Windows x64 JIT unwind lifecycle old=" << old_entry
            << " invalidated=present collected=absent reused=yes recompiled=present\n";
  return JNI_TRUE;
}
