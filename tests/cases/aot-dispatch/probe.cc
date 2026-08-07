#include <windows.h>

#include <jni.h>

#include <atomic>
#include <cstdint>
#include <iostream>
#include <string>

#include "art_method-inl.h"
#include "oat/oat.h"
#include "scoped_thread_state_change-inl.h"

namespace {

std::atomic<HANDLE> g_worker_handle(nullptr);
std::atomic<DWORD> g_worker_thread_id(0u);
std::atomic<uintptr_t> g_expected_entry(0u);
std::atomic<DWORD64> g_saved_dr0(0u);
std::atomic<DWORD64> g_saved_dr7(0u);
volatile LONG g_dispatch_hits = 0;
volatile LONG g_wrong_single_steps = 0;
PVOID g_veh_handle = nullptr;
std::string g_target_name;

void Cleanup() {
  PVOID veh = g_veh_handle;
  g_veh_handle = nullptr;
  if (veh != nullptr) {
    RemoveVectoredExceptionHandler(veh);
  }
  HANDLE worker = g_worker_handle.exchange(nullptr, std::memory_order_acq_rel);
  if (worker != nullptr) {
    CloseHandle(worker);
  }
  g_worker_thread_id.store(0u, std::memory_order_release);
  g_expected_entry.store(0u, std::memory_order_release);
  g_saved_dr0.store(0u, std::memory_order_release);
  g_saved_dr7.store(0u, std::memory_order_release);
  InterlockedExchange(&g_dispatch_hits, 0);
  InterlockedExchange(&g_wrong_single_steps, 0);
  g_target_name.clear();
}

jboolean Fail(JNIEnv* env, const char* message) {
  std::cerr << "W036_BOOT_OAT_DISPATCH_FAIL: " << message << '\n';
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

[[noreturn]] void AbortAfterResumeFailure() {
  const DWORD error = GetLastError();
  std::cerr << "W036_BOOT_OAT_DISPATCH_FAIL: ResumeThread failed while arming "
               "the dispatch breakpoint, error="
            << error << '\n';
  std::cerr.flush();
  TerminateProcess(GetCurrentProcess(), error == ERROR_SUCCESS ? ERROR_GEN_FAILURE : error);
  __builtin_unreachable();
}

LONG CALLBACK DispatchBreakpointHandler(EXCEPTION_POINTERS* exception) {
  if (exception == nullptr || exception->ExceptionRecord == nullptr ||
      exception->ContextRecord == nullptr ||
      exception->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP ||
      GetCurrentThreadId() != g_worker_thread_id.load(std::memory_order_acquire)) {
    return EXCEPTION_CONTINUE_SEARCH;
  }

  CONTEXT* context = exception->ContextRecord;
  const uintptr_t expected = g_expected_entry.load(std::memory_order_acquire);
  const uintptr_t observed = static_cast<uintptr_t>(context->Rip);
  if (expected == 0u || observed != expected) {
    InterlockedIncrement(&g_wrong_single_steps);
    return EXCEPTION_CONTINUE_SEARCH;
  }

  context->Dr0 = g_saved_dr0.load(std::memory_order_acquire);
  context->Dr6 = 0u;
  context->Dr7 = g_saved_dr7.load(std::memory_order_acquire);
  InterlockedIncrement(&g_dispatch_hits);
  return EXCEPTION_CONTINUE_EXECUTION;
}

bool IsRegisteredBootOatEntry(art::ArtMethod* method,
                              const void** entry,
                              DWORD64* oat_base) {
  if (method == nullptr || method->IsNative() || !method->IsInvokable()) {
    return false;
  }
  const void* oat_entry = method->GetOatMethodQuickCode(art::kRuntimePointerSize);
  const void* current_entry = method->GetEntryPointFromQuickCompiledCode();
  if (oat_entry == nullptr || current_entry != oat_entry) {
    return false;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(current_entry), &image_base, nullptr);
  if (function == nullptr || image_base == 0u ||
      function->BeginAddress != reinterpret_cast<DWORD64>(current_entry) - image_base) {
    return false;
  }
  const art::OatHeader* header = reinterpret_cast<const art::OatHeader*>(image_base);
  if (!header->IsValid()) {
    return false;
  }
  *entry = current_entry;
  *oat_base = image_base;
  return true;
}

}  // namespace

extern "C" __declspec(dllexport) void JNICALL
Java_W036BootOatDispatchProbe_nativeRegisterWorker(JNIEnv* env, jclass) {
  HANDLE duplicate = nullptr;
  if (!DuplicateHandle(GetCurrentProcess(),
                       GetCurrentThread(),
                       GetCurrentProcess(),
                       &duplicate,
                       0u,
                       FALSE,
                       DUPLICATE_SAME_ACCESS)) {
    Fail(env, "DuplicateHandle failed for the worker thread");
    return;
  }
  HANDLE expected = nullptr;
  if (!g_worker_handle.compare_exchange_strong(
          expected, duplicate, std::memory_order_acq_rel, std::memory_order_acquire)) {
    CloseHandle(duplicate);
    Fail(env, "worker thread was registered more than once");
    return;
  }
  g_worker_thread_id.store(GetCurrentThreadId(), std::memory_order_release);
}

extern "C" __declspec(dllexport) jint JNICALL
Java_W036BootOatDispatchProbe_nativeArm(JNIEnv* env, jclass, jobjectArray candidates) {
  HANDLE worker = g_worker_handle.load(std::memory_order_acquire);
  if (worker == nullptr || g_worker_thread_id.load(std::memory_order_acquire) == 0u) {
    return FailIndex(env, "worker thread was not registered");
  }

  jint selected = -1;
  const void* entry = nullptr;
  DWORD64 oat_base = 0u;
  {
    art::ScopedObjectAccess soa(env);
    for (jsize index = 0; index < env->GetArrayLength(candidates); ++index) {
      jobject reflected = env->GetObjectArrayElement(candidates, index);
      art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
      env->DeleteLocalRef(reflected);
      if (IsRegisteredBootOatEntry(method, &entry, &oat_base)) {
        selected = index;
        g_target_name = method->PrettyMethod();
        break;
      }
    }
  }
  if (selected < 0 || entry == nullptr || oat_base == 0u) {
    return FailIndex(env, "no candidate retained its registered boot-OAT entrypoint");
  }

  g_expected_entry.store(reinterpret_cast<uintptr_t>(entry), std::memory_order_release);
  InterlockedExchange(&g_dispatch_hits, 0);
  InterlockedExchange(&g_wrong_single_steps, 0);
  g_veh_handle = AddVectoredExceptionHandler(1u, DispatchBreakpointHandler);
  if (g_veh_handle == nullptr) {
    return FailIndex(env, "AddVectoredExceptionHandler failed");
  }

  DWORD suspend_count = SuspendThread(worker);
  if (suspend_count == MAXDWORD) {
    Cleanup();
    return FailIndex(env, "SuspendThread failed while arming the dispatch breakpoint");
  }

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_DEBUG_REGISTERS;
  bool armed = false;
  if (GetThreadContext(worker, &context)) {
    g_saved_dr0.store(context.Dr0, std::memory_order_release);
    g_saved_dr7.store(context.Dr7, std::memory_order_release);
    if ((context.Dr7 & 3u) == 0u) {
      context.Dr0 = reinterpret_cast<DWORD64>(entry);
      context.Dr6 = 0u;
      context.Dr7 &= ~((DWORD64{3u} << 16u) | (DWORD64{3u} << 18u));
      context.Dr7 |= 1u;
      armed = SetThreadContext(worker, &context) != FALSE;
    }
  }
  if (ResumeThread(worker) == MAXDWORD) {
    // The worker may still be suspended with the breakpoint armed. Terminate
    // this isolated gate process rather than remove its VEH and deadlock in
    // the Java join path.
    AbortAfterResumeFailure();
  }
  if (!armed) {
    Cleanup();
    return FailIndex(env, "worker debug-register slot zero was unavailable or could not be armed");
  }
  return selected;
}

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W036BootOatDispatchProbe_nativeVerify(JNIEnv* env, jclass, jobject reflected) {
  const LONG hits = InterlockedCompareExchange(&g_dispatch_hits, 0, 0);
  const LONG wrong = InterlockedCompareExchange(&g_wrong_single_steps, 0, 0);
  const uintptr_t expected = g_expected_entry.load(std::memory_order_acquire);

  bool entry_unchanged = false;
  {
    art::ScopedObjectAccess soa(env);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    const void* entry = nullptr;
    DWORD64 oat_base = 0u;
    entry_unchanged = IsRegisteredBootOatEntry(method, &entry, &oat_base) &&
                      reinterpret_cast<uintptr_t>(entry) == expected;
  }

  const std::string target_name = g_target_name;
  Cleanup();
  if (hits != 1 || wrong != 0 || expected == 0u || !entry_unchanged) {
    return Fail(env, "ordinary dispatch did not execute the selected boot-OAT entrypoint exactly once");
  }

  std::cout << "W036_BOOT_OAT_DISPATCH_PASS target=" << target_name
            << " current_entry=oat rx_pc=hardware_breakpoint hits=" << hits
            << " wrong_single_steps=" << wrong << " jit=disabled\n";
  return JNI_TRUE;
}

extern "C" __declspec(dllexport) void JNICALL
Java_W036BootOatDispatchProbe_nativeCleanup(JNIEnv*, jclass) {
  Cleanup();
}
