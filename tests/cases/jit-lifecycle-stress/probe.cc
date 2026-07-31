#include <windows.h>

#include <jni.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <iostream>
#include <set>
#include <vector>

#include "art_method-inl.h"
#include "jit/jit.h"
#include "jit/jit_code_cache.h"
#include "runtime.h"
#include "scoped_thread_state_change-inl.h"

namespace {

constexpr size_t kMaximumMethods = 64u;
constexpr uint64_t kModeTransition = 0u;
constexpr uint64_t kModeLive = 1u;
constexpr uint64_t kModeDead = 2u;

struct SamplerState {
  std::array<std::atomic<uintptr_t>, kMaximumMethods> entries{};
  size_t entry_count = 0u;
  LARGE_INTEGER frequency{};
  std::atomic<uint64_t> phase{0u};
  std::atomic<bool> stop{false};
  std::atomic<uint64_t> samples{0u};
  std::atomic<uint64_t> live_lookups{0u};
  std::atomic<uint64_t> dead_lookups{0u};
  std::atomic<uint64_t> transition_lookups{0u};
  std::atomic<uint64_t> virtual_unwinds{0u};
  std::atomic<uint64_t> missing_live{0u};
  std::atomic<uint64_t> stale_dead{0u};
  std::atomic<uint64_t> unwind_failures{0u};
  std::atomic<uint64_t> lookup_ticks{0u};
  std::atomic<uint64_t> maximum_lookup_ticks{0u};
  std::atomic<uint32_t> active_unwinds{0u};
};

jboolean ThrowFailure(JNIEnv* env, const char* message) {
  std::cerr << "W025_JIT3_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message);
  }
  return JNI_FALSE;
}

PRUNTIME_FUNCTION Lookup(const void* pc, DWORD64* image_base) {
  *image_base = 0u;
  return ::RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(pc), image_base, nullptr);
}

void UpdateMaximum(std::atomic<uint64_t>* maximum, uint64_t value) {
  uint64_t observed = maximum->load(std::memory_order_relaxed);
  while (observed < value &&
         !maximum->compare_exchange_weak(
             observed, value, std::memory_order_relaxed, std::memory_order_relaxed)) {
  }
}

bool VirtualUnwind(PRUNTIME_FUNCTION function, DWORD64 image_base) {
  if (function->BeginAddress >= function->EndAddress) {
    return false;
  }
  alignas(16) std::array<uint8_t, 64u * 1024u> stack{};
  const uintptr_t stack_begin = reinterpret_cast<uintptr_t>(stack.data());
  const uintptr_t stack_end = stack_begin + stack.size();
  const uintptr_t synthetic_rsp =
      (stack_begin + stack.size() / 2u) & ~static_cast<uintptr_t>(15u);

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
  context.Rip = image_base + function->EndAddress - 1u;
  context.Rsp = synthetic_rsp;
  context.Rbp = synthetic_rsp;
  PVOID handler_data = nullptr;
  DWORD64 establisher_frame = 0u;
  ::RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                     image_base,
                     context.Rip,
                     function,
                     &context,
                     &handler_data,
                     &establisher_frame,
                     nullptr);
  return context.Rsp >= stack_begin && context.Rsp <= stack_end;
}

DWORD WINAPI SamplerMain(void* argument) {
  auto* state = static_cast<SamplerState*>(argument);
  while (!state->stop.load(std::memory_order_acquire)) {
    for (size_t index = 0u; index < state->entry_count; ++index) {
      const uint64_t phase_before = state->phase.load(std::memory_order_acquire);
      const uintptr_t entry = state->entries[index].load(std::memory_order_acquire);
      if (entry == 0u) {
        continue;
      }

      LARGE_INTEGER started = {};
      LARGE_INTEGER finished = {};
      ::QueryPerformanceCounter(&started);
      DWORD64 image_base = 0u;
      PRUNTIME_FUNCTION function = Lookup(reinterpret_cast<const void*>(entry), &image_base);
      ::QueryPerformanceCounter(&finished);
      const uint64_t ticks = static_cast<uint64_t>(finished.QuadPart - started.QuadPart);
      state->lookup_ticks.fetch_add(ticks, std::memory_order_relaxed);
      UpdateMaximum(&state->maximum_lookup_ticks, ticks);

      const uint64_t phase_after_lookup = state->phase.load(std::memory_order_acquire);
      if (function != nullptr && phase_before == phase_after_lookup &&
          (phase_before & 3u) == kModeLive) {
        state->active_unwinds.fetch_add(1u, std::memory_order_acq_rel);
        if (state->phase.load(std::memory_order_acquire) == phase_before) {
          const bool unwind_ok = VirtualUnwind(function, image_base);
          state->virtual_unwinds.fetch_add(1u, std::memory_order_relaxed);
          if (!unwind_ok) {
            state->unwind_failures.fetch_add(1u, std::memory_order_relaxed);
          }
        }
        state->active_unwinds.fetch_sub(1u, std::memory_order_acq_rel);
      }

      const uint64_t phase_after = state->phase.load(std::memory_order_acquire);
      if (phase_before == phase_after) {
        switch (phase_before & 3u) {
          case kModeLive:
            state->live_lookups.fetch_add(1u, std::memory_order_relaxed);
            if (function == nullptr) {
              state->missing_live.fetch_add(1u, std::memory_order_relaxed);
            }
            break;
          case kModeDead:
            state->dead_lookups.fetch_add(1u, std::memory_order_relaxed);
            if (function != nullptr) {
              state->stale_dead.fetch_add(1u, std::memory_order_relaxed);
            }
            break;
          default:
            state->transition_lookups.fetch_add(1u, std::memory_order_relaxed);
            break;
        }
      } else {
        state->transition_lookups.fetch_add(1u, std::memory_order_relaxed);
      }
      state->samples.fetch_add(1u, std::memory_order_relaxed);
    }
    ::SwitchToThread();
  }
  return 0u;
}

void PublishPhase(SamplerState* state, uint64_t mode) {
  const uint64_t previous = state->phase.load(std::memory_order_relaxed);
  const uint64_t sequence = (previous >> 2u) + 1u;
  state->phase.store((sequence << 2u) | mode, std::memory_order_release);
}

bool StopSampler(SamplerState* state, HANDLE thread) {
  state->stop.store(true, std::memory_order_release);
  const DWORD wait = ::WaitForSingleObject(thread, 10000u);
  ::CloseHandle(thread);
  return wait == WAIT_OBJECT_0;
}

bool WaitForUnwindReaders(SamplerState* state) {
  const ULONGLONG deadline = ::GetTickCount64() + 10000u;
  while (state->active_unwinds.load(std::memory_order_acquire) != 0u) {
    if (::GetTickCount64() >= deadline) {
      return false;
    }
    ::Sleep(0u);
  }
  return true;
}

bool ReadMethods(JNIEnv* env,
                 jobjectArray reflected_methods,
                 std::vector<art::ArtMethod*>* methods) {
  const jsize count = env->GetArrayLength(reflected_methods);
  if (count <= 0 || methods->size() + static_cast<size_t>(count) > kMaximumMethods) {
    return false;
  }
  art::ScopedObjectAccess soa(env);
  for (jsize index = 0; index < count; ++index) {
    jobject reflected = env->GetObjectArrayElement(reflected_methods, index);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    env->DeleteLocalRef(reflected);
    if (method == nullptr) {
      return false;
    }
    methods->push_back(method);
  }
  return true;
}

bool CompileRound(JNIEnv* env,
                  art::jit::Jit* jit,
                  art::jit::JitCodeCache* code_cache,
                  art::Thread* self,
                  const std::vector<art::ArtMethod*>& methods,
                  const std::vector<const void*>& previous,
                  std::vector<const void*>* entries,
                  size_t* exact_reuse) {
  entries->clear();
  entries->reserve(methods.size());
  art::ScopedObjectAccess soa(env);
  for (size_t index = 0u; index < methods.size(); ++index) {
    art::ArtMethod* method = methods[index];
    if (!jit->CompileMethod(method,
                            self,
                            art::CompilationKind::kOptimized,
                            /*prejit=*/ false)) {
      return false;
    }
    const void* entry = method->GetEntryPointFromQuickCompiledCode();
    if (!code_cache->ContainsPc(entry)) {
      return false;
    }
    DWORD64 image_base = 0u;
    if (Lookup(entry, &image_base) == nullptr) {
      return false;
    }
    if (!previous.empty() && previous[index] == entry) {
      ++*exact_reuse;
    }
    entries->push_back(entry);
  }
  return true;
}

uint64_t TicksToNanoseconds(uint64_t ticks, const LARGE_INTEGER& frequency) {
  return frequency.QuadPart == 0
      ? 0u
      : (ticks * UINT64_C(1000000000)) / static_cast<uint64_t>(frequency.QuadPart);
}

}  // namespace

extern "C" JNIEXPORT jboolean JNICALL
Java_W025JitLifecycleStressProbe_nativeRun(JNIEnv* env,
                                           jclass,
                                           jobjectArray managed_methods,
                                           jobjectArray native_methods,
                                           jint cycles) {
  if (cycles <= 0 || cycles > 100) {
    return ThrowFailure(env, "cycle count is outside 1..100");
  }
  art::Runtime* runtime = art::Runtime::Current();
  art::jit::Jit* jit = runtime != nullptr ? runtime->GetJit() : nullptr;
  if (jit == nullptr) {
    return ThrowFailure(env, "ART JIT is unavailable");
  }
  art::jit::JitCodeCache* code_cache = jit->GetCodeCache();
  if (!code_cache->GetGarbageCollectCode()) {
    return ThrowFailure(env, "ART JIT code-cache collection is disabled");
  }

  std::vector<art::ArtMethod*> methods;
  if (!ReadMethods(env, managed_methods, &methods)) {
    return ThrowFailure(env, "managed reflected methods are invalid");
  }
  const size_t managed_count = methods.size();
  if (!ReadMethods(env, native_methods, &methods)) {
    return ThrowFailure(env, "native reflected methods are invalid");
  }
  const size_t native_count = methods.size() - managed_count;
  if (managed_count < 16u || native_count < 8u) {
    return ThrowFailure(env, "stress method set is incomplete");
  }

  SamplerState sampler;
  sampler.entry_count = methods.size();
  if (::QueryPerformanceFrequency(&sampler.frequency) == FALSE) {
    return ThrowFailure(env, "QueryPerformanceFrequency failed");
  }
  HANDLE sampler_thread =
      ::CreateThread(nullptr, 0u, SamplerMain, &sampler, 0u, nullptr);
  if (sampler_thread == nullptr) {
    return ThrowFailure(env, "sampler thread creation failed");
  }

  art::Thread* self = art::Thread::Current();
  std::vector<const void*> previous;
  std::vector<const void*> entries;
  size_t exact_reuse = 0u;
  size_t collection_count = 0u;
  bool ok = CompileRound(env,
                         jit,
                         code_cache,
                         self,
                         methods,
                         previous,
                         &entries,
                         &exact_reuse);
  if (ok) {
    std::set<const void*> unique(entries.begin(), entries.end());
    ok = unique.size() >= managed_count + 4u;
  }
  for (size_t index = 0u; ok && index < entries.size(); ++index) {
    sampler.entries[index].store(
        reinterpret_cast<uintptr_t>(entries[index]), std::memory_order_release);
  }
  if (ok) {
    PublishPhase(&sampler, kModeLive);
  }

  for (jint cycle = 0; ok && cycle < cycles; ++cycle) {
    ::Sleep(8u);
    PublishPhase(&sampler, kModeTransition);
    ::Sleep(2u);
    if (!WaitForUnwindReaders(&sampler)) {
      ok = false;
      break;
    }
    {
      art::ScopedObjectAccess soa(env);
      code_cache->InvalidateAllCompiledCode();
    }
    for (const void* entry : entries) {
      DWORD64 image_base = 0u;
      if (Lookup(entry, &image_base) == nullptr) {
        ok = false;
        break;
      }
    }
    if (!ok) {
      break;
    }

    code_cache->DoCollection(self);
    ++collection_count;
    for (const void* entry : entries) {
      DWORD64 image_base = 0u;
      if (Lookup(entry, &image_base) != nullptr) {
        ok = false;
        break;
      }
    }
    if (!ok) {
      break;
    }
    PublishPhase(&sampler, kModeDead);
    ::Sleep(5u);
    PublishPhase(&sampler, kModeTransition);

    previous = entries;
    if (!CompileRound(env,
                      jit,
                      code_cache,
                      self,
                      methods,
                      previous,
                      &entries,
                      &exact_reuse)) {
      ok = false;
      break;
    }
    for (size_t index = 0u; index < entries.size(); ++index) {
      sampler.entries[index].store(
          reinterpret_cast<uintptr_t>(entries[index]), std::memory_order_release);
    }
    PublishPhase(&sampler, kModeLive);
  }

  ::Sleep(8u);
  const bool sampler_stopped = StopSampler(&sampler, sampler_thread);
  const uint64_t samples = sampler.samples.load(std::memory_order_relaxed);
  const uint64_t live_lookups = sampler.live_lookups.load(std::memory_order_relaxed);
  const uint64_t dead_lookups = sampler.dead_lookups.load(std::memory_order_relaxed);
  const uint64_t transition_lookups =
      sampler.transition_lookups.load(std::memory_order_relaxed);
  const uint64_t virtual_unwinds = sampler.virtual_unwinds.load(std::memory_order_relaxed);
  const uint64_t missing_live = sampler.missing_live.load(std::memory_order_relaxed);
  const uint64_t stale_dead = sampler.stale_dead.load(std::memory_order_relaxed);
  const uint64_t unwind_failures = sampler.unwind_failures.load(std::memory_order_relaxed);
  const uint64_t lookup_ticks = sampler.lookup_ticks.load(std::memory_order_relaxed);
  const uint64_t maximum_lookup_ticks =
      sampler.maximum_lookup_ticks.load(std::memory_order_relaxed);
  const size_t expected_reuse = methods.size() * static_cast<size_t>(cycles);

  ok &= sampler_stopped && collection_count == static_cast<size_t>(cycles) &&
        exact_reuse == expected_reuse && samples != 0u && live_lookups != 0u &&
        dead_lookups != 0u && virtual_unwinds != 0u && missing_live == 0u &&
        stale_dead == 0u && unwind_failures == 0u;
  if (!ok) {
    return ThrowFailure(env, "lifecycle, reuse, or concurrent unwind invariant failed");
  }

  std::set<const void*> unique(entries.begin(), entries.end());
  const uint64_t average_ticks = samples == 0u ? 0u : lookup_ticks / samples;
  std::cout << "W025_JIT3_PASS methods=" << methods.size()
            << " managed=" << managed_count
            << " jni=" << native_count
            << " unique_allocations=" << unique.size()
            << " cycles=" << cycles
            << " collections=" << collection_count
            << " compilations=" << methods.size() * (static_cast<size_t>(cycles) + 1u)
            << " exact_reuse=" << exact_reuse
            << " live_lookups=" << live_lookups
            << " dead_lookups=" << dead_lookups
            << " transition_lookups=" << transition_lookups
            << " virtual_unwinds=" << virtual_unwinds
            << " missing_live=" << missing_live
            << " stale_dead=" << stale_dead
            << " unwind_failures=" << unwind_failures
            << " lookup_average_ns=" << TicksToNanoseconds(average_ticks, sampler.frequency)
            << " lookup_maximum_ns="
            << TicksToNanoseconds(maximum_lookup_ticks, sampler.frequency)
            << " callback_tables=0\n";
  return JNI_TRUE;
}



extern "C" JNIEXPORT jint JNICALL
Java_W025JitLifecycleStressProbe_nativeI(JNIEnv*, jclass, jint value) {
  return value * 3 + 1;
}

extern "C" JNIEXPORT jlong JNICALL
Java_W025JitLifecycleStressProbe_nativeJ(JNIEnv*, jclass, jlong value) {
  return value + 0x1234;
}

extern "C" JNIEXPORT jdouble JNICALL
Java_W025JitLifecycleStressProbe_nativeD(JNIEnv*, jclass, jdouble left, jdouble right) {
  return left + right * 2.0;
}

extern "C" JNIEXPORT jfloat JNICALL
Java_W025JitLifecycleStressProbe_nativeF(JNIEnv*, jclass, jfloat value, jint scale) {
  return value * scale + 0.5f;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_W025JitLifecycleStressProbe_nativeZ(JNIEnv*, jclass, jboolean value) {
  return value == JNI_FALSE ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jobject JNICALL
Java_W025JitLifecycleStressProbe_nativeL(JNIEnv*, jclass, jobject value) {
  return value;
}

extern "C" JNIEXPORT jlong JNICALL
Java_W025JitLifecycleStressProbe_nativeMix(
    JNIEnv*, jclass, jint i, jlong j, jdouble d, jobject value) {
  return static_cast<jlong>(i) + j + static_cast<jlong>(d * 1000.0) +
      (value == nullptr ? 0 : 7);
}

extern "C" JNIEXPORT void JNICALL
Java_W025JitLifecycleStressProbe_nativeV(
    JNIEnv* env, jclass, jintArray values, jint index) {
  const jint replacement = 0x5a5a;
  env->SetIntArrayRegion(values, index, 1, &replacement);
}
