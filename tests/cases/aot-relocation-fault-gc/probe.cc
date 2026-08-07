#include <windows.h>

#include <jni.h>

#include <atomic>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <string>

#include "art_method-inl.h"
#include "base/globals.h"
#include "gc/heap.h"
#include "gc/space/image_space.h"
#include "gc_root.h"
#include "oat/image.h"
#include "oat/oat.h"
#include "oat/oat_file.h"
#include "runtime.h"
#include "scoped_thread_state_change-inl.h"

namespace {

std::atomic<DWORD> g_fault_thread_id(0u);
std::atomic<uintptr_t> g_oat_rx_begin(0u);
std::atomic<uintptr_t> g_oat_rx_end(0u);
std::atomic<uintptr_t> g_expected_entry(0u);
volatile LONG g_thread_access_violations = 0;
volatile LONG g_oat_access_violations = 0;
std::atomic<uintptr_t> g_fault_pc(0u);
std::atomic<uintptr_t> g_fault_address(0u);
PVOID g_veh_handle = nullptr;
jweak g_bss_root_weak = nullptr;
size_t g_bss_root_index = 0u;
size_t g_bss_root_count_before = 0u;
uint32_t g_gc_count_before = 0u;
intptr_t g_relocation_delta = 0;
std::string g_target_name;

void Cleanup(JNIEnv* env) {
  PVOID veh = g_veh_handle;
  g_veh_handle = nullptr;
  if (veh != nullptr) {
    RemoveVectoredExceptionHandler(veh);
  }
  if (env != nullptr && g_bss_root_weak != nullptr) {
    env->DeleteWeakGlobalRef(g_bss_root_weak);
  }
  g_bss_root_weak = nullptr;
  g_bss_root_index = 0u;
  g_bss_root_count_before = 0u;
  g_relocation_delta = 0;
  g_target_name.clear();
  g_fault_thread_id.store(0u, std::memory_order_release);
  g_oat_rx_begin.store(0u, std::memory_order_release);
  g_oat_rx_end.store(0u, std::memory_order_release);
  g_expected_entry.store(0u, std::memory_order_release);
  g_fault_pc.store(0u, std::memory_order_release);
  g_fault_address.store(0u, std::memory_order_release);
  g_gc_count_before = 0u;
  InterlockedExchange(&g_thread_access_violations, 0);
  InterlockedExchange(&g_oat_access_violations, 0);
}

jboolean Fail(JNIEnv* env, const char* message) {
  std::cerr << "W037_BOOT_OAT_EXECUTION_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message);
  }
  return JNI_FALSE;
}

jint FailIndex(JNIEnv* env, const char* message) {
  Cleanup(env);
  Fail(env, message);
  return -1;
}

LONG CALLBACK ManagedOatFaultObserver(EXCEPTION_POINTERS* exception) {
  if (exception == nullptr || exception->ExceptionRecord == nullptr ||
      exception->ContextRecord == nullptr ||
      exception->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
      GetCurrentThreadId() != g_fault_thread_id.load(std::memory_order_acquire)) {
    return EXCEPTION_CONTINUE_SEARCH;
  }

  InterlockedIncrement(&g_thread_access_violations);
  const uintptr_t pc = static_cast<uintptr_t>(exception->ContextRecord->Rip);
  const uintptr_t rx_begin = g_oat_rx_begin.load(std::memory_order_acquire);
  const uintptr_t rx_end = g_oat_rx_end.load(std::memory_order_acquire);
  if (pc >= rx_begin && pc < rx_end) {
    InterlockedIncrement(&g_oat_access_violations);
    uintptr_t expected = 0u;
    g_fault_pc.compare_exchange_strong(
        expected, pc, std::memory_order_acq_rel, std::memory_order_acquire);
    if (exception->ExceptionRecord->NumberParameters >= 2u) {
      g_fault_address.store(
          static_cast<uintptr_t>(exception->ExceptionRecord->ExceptionInformation[1]),
          std::memory_order_release);
    }
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

bool ReadPersistedImageHeader(const char* path, art::ImageHeader* header) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream.is_open()) {
    return false;
  }
  stream.read(reinterpret_cast<char*>(header), sizeof(*header));
  return stream.good() && header->IsValid();
}

bool IsCurrentRegisteredBootOatMethod(art::ArtMethod* method,
                                      const art::OatFile* oat_file,
                                      const void** entry) {
  if (method == nullptr || method->IsNative() || !method->IsInvokable()) {
    return false;
  }
  const void* oat_entry = method->GetOatMethodQuickCode(art::kRuntimePointerSize);
  const void* current_entry = method->GetEntryPointFromQuickCompiledCode();
  if (oat_entry == nullptr || current_entry != oat_entry) {
    return false;
  }

  const art::OatHeader* oat_header =
      reinterpret_cast<const art::OatHeader*>(oat_file->Begin());
  const uintptr_t code_begin = reinterpret_cast<uintptr_t>(oat_file->Begin()) +
                               oat_header->GetExecutableOffset();
  const uintptr_t code_end = reinterpret_cast<uintptr_t>(oat_file->End());
  const uintptr_t candidate = reinterpret_cast<uintptr_t>(current_entry);
  if (candidate < code_begin || candidate >= code_end) {
    return false;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(current_entry), &image_base, nullptr);
  if (function == nullptr || image_base == 0u ||
      function->BeginAddress != candidate - image_base) {
    return false;
  }
  const art::OatHeader* registered_header =
      reinterpret_cast<const art::OatHeader*>(image_base);
  if (!registered_header->IsValid()) {
    return false;
  }
  *entry = current_entry;
  return true;
}

}  // namespace

extern "C" __declspec(dllexport) jint JNICALL
Java_W037BootOatRelocationFaultGcProbe_nativeBegin(JNIEnv* env,
                                                   jclass,
                                                   jobjectArray fault_methods,
                                                   jstring image_path) {
  Cleanup(env);
  const char* path = env->GetStringUTFChars(image_path, nullptr);
  if (path == nullptr) {
    return -1;
  }
  art::ImageHeader persisted_header;
  const bool persisted_valid = ReadPersistedImageHeader(path, &persisted_header);
  env->ReleaseStringUTFChars(image_path, path);
  if (!persisted_valid) {
    return FailIndex(env, "could not read the persisted boot-image header");
  }

  art::ScopedObjectAccess soa(env);
  art::Runtime* runtime = art::Runtime::Current();
  if (runtime == nullptr || runtime->GetHeap()->GetBootImageSpaces().size() != 1u) {
    return FailIndex(env, "runtime does not expose the expected single boot ImageSpace");
  }
  art::gc::space::ImageSpace* image_space =
      runtime->GetHeap()->GetBootImageSpaces().front();
  const art::ImageHeader& live_header = image_space->GetImageHeader();
  const art::OatFile* oat_file = image_space->GetOatFile();
  if (oat_file == nullptr || !oat_file->IsExecutable()) {
    return FailIndex(env, "boot ImageSpace has no executable OAT file");
  }

  const uintptr_t persisted_image_begin =
      reinterpret_cast<uintptr_t>(persisted_header.GetImageBegin());
  const uintptr_t live_image_begin = reinterpret_cast<uintptr_t>(image_space->Begin());
  const intptr_t relocation_delta =
      static_cast<intptr_t>(live_image_begin) - static_cast<intptr_t>(persisted_image_begin);
  if (relocation_delta == 0 ||
      relocation_delta % static_cast<intptr_t>(art::kElfSegmentAlignment) != 0 ||
      reinterpret_cast<uintptr_t>(live_header.GetImageBegin()) != live_image_begin) {
    return FailIndex(env, "boot image was not relocated by a nonzero aligned delta");
  }
  const uintptr_t expected_oat_begin =
      reinterpret_cast<uintptr_t>(persisted_header.GetOatDataBegin()) + relocation_delta;
  if (reinterpret_cast<uintptr_t>(oat_file->Begin()) != expected_oat_begin ||
      reinterpret_cast<uintptr_t>(live_header.GetOatDataBegin()) != expected_oat_begin) {
    return FailIndex(env, "boot OAT did not retain the image relocation delta");
  }

  auto bss_roots = oat_file->GetBssGcRoots();
  size_t non_null_roots = 0u;
  for (size_t index = 0u; index < bss_roots.size(); ++index) {
    if (bss_roots[index].IsNull()) {
      continue;
    }
    ++non_null_roots;
    if (g_bss_root_weak == nullptr) {
      art::ObjPtr<art::mirror::Object> root = bss_roots[index].Read();
      jobject local = soa.AddLocalReference<jobject>(root);
      g_bss_root_weak = env->NewWeakGlobalRef(local);
      env->DeleteLocalRef(local);
      if (g_bss_root_weak != nullptr) {
        g_bss_root_index = index;
      }
    }
  }
  if (bss_roots.empty() || non_null_roots == 0u || g_bss_root_weak == nullptr) {
    return FailIndex(env, "boot OAT has no trackable non-null BSS GC root");
  }

  jint selected = -1;
  const void* selected_entry = nullptr;
  for (jsize index = 0; index < env->GetArrayLength(fault_methods); ++index) {
    jobject reflected = env->GetObjectArrayElement(fault_methods, index);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    env->DeleteLocalRef(reflected);
    if (IsCurrentRegisteredBootOatMethod(method, oat_file, &selected_entry)) {
      selected = index;
      g_target_name = method->PrettyMethod();
      break;
    }
  }
  if (selected < 0 || selected_entry == nullptr) {
    return FailIndex(env, "no null-fault candidate retained a registered boot-OAT entrypoint");
  }

  const art::OatHeader* oat_header =
      reinterpret_cast<const art::OatHeader*>(oat_file->Begin());
  g_oat_rx_begin.store(
      reinterpret_cast<uintptr_t>(oat_file->Begin()) + oat_header->GetExecutableOffset(),
      std::memory_order_release);
  g_oat_rx_end.store(reinterpret_cast<uintptr_t>(oat_file->End()), std::memory_order_release);
  g_expected_entry.store(
      reinterpret_cast<uintptr_t>(selected_entry), std::memory_order_release);
  g_fault_thread_id.store(GetCurrentThreadId(), std::memory_order_release);
  g_bss_root_count_before = non_null_roots;
  g_gc_count_before = runtime->GetHeap()->GetCurrentGcNum();
  g_relocation_delta = relocation_delta;
  InterlockedExchange(&g_thread_access_violations, 0);
  InterlockedExchange(&g_oat_access_violations, 0);
  g_veh_handle = AddVectoredExceptionHandler(1u, ManagedOatFaultObserver);
  if (g_veh_handle == nullptr) {
    return FailIndex(env, "AddVectoredExceptionHandler failed for managed-fault observation");
  }
  return selected;
}

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W037BootOatRelocationFaultGcProbe_nativeVerify(JNIEnv* env,
                                                    jclass,
                                                    jobject reflected,
                                                    jboolean fault_caught,
                                                    jint gc_rounds) {
  const LONG thread_faults = InterlockedCompareExchange(&g_thread_access_violations, 0, 0);
  const LONG oat_faults = InterlockedCompareExchange(&g_oat_access_violations, 0, 0);
  const uintptr_t fault_pc = g_fault_pc.load(std::memory_order_acquire);
  const uintptr_t fault_address = g_fault_address.load(std::memory_order_acquire);
  const uintptr_t expected_entry = g_expected_entry.load(std::memory_order_acquire);
  const uint32_t gc_count_before = g_gc_count_before;
  const intptr_t relocation_delta = g_relocation_delta;
  const size_t root_count_before = g_bss_root_count_before;
  const size_t root_index = g_bss_root_index;
  const std::string target_name = g_target_name;

  bool entry_unchanged = false;
  bool root_same = false;
  size_t root_count_after = 0u;
  uint32_t gc_count_after = 0u;
  bool fault_pc_registered = false;
  {
    art::ScopedObjectAccess soa(env);
    art::Runtime* runtime = art::Runtime::Current();
    if (runtime != nullptr && runtime->GetHeap()->GetBootImageSpaces().size() == 1u) {
      gc_count_after = runtime->GetHeap()->GetCurrentGcNum();
      const art::OatFile* oat_file =
          runtime->GetHeap()->GetBootImageSpaces().front()->GetOatFile();
      if (oat_file != nullptr) {
        auto bss_roots = oat_file->GetBssGcRoots();
        for (const art::GcRoot<art::mirror::Object>& root : bss_roots) {
          root_count_after += root.IsNull() ? 0u : 1u;
        }
        if (root_index < bss_roots.size() && !bss_roots[root_index].IsNull() &&
            g_bss_root_weak != nullptr &&
            env->IsSameObject(g_bss_root_weak, nullptr) == JNI_FALSE) {
          jobject current_root =
              soa.AddLocalReference<jobject>(bss_roots[root_index].Read());
          root_same = env->IsSameObject(current_root, g_bss_root_weak) == JNI_TRUE;
          env->DeleteLocalRef(current_root);
        }
        art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
        const void* entry = nullptr;
        entry_unchanged = IsCurrentRegisteredBootOatMethod(method, oat_file, &entry) &&
                          reinterpret_cast<uintptr_t>(entry) == expected_entry;
      }
    }
    if (fault_pc != 0u) {
      DWORD64 image_base = 0u;
      PRUNTIME_FUNCTION function =
          RtlLookupFunctionEntry(static_cast<DWORD64>(fault_pc), &image_base, nullptr);
      fault_pc_registered = function != nullptr && image_base != 0u &&
                            fault_pc >= image_base + function->BeginAddress &&
                            fault_pc < image_base + function->EndAddress;
    }
  }

  const uint32_t completed_gc_rounds = gc_count_after - gc_count_before;
  Cleanup(env);
  if (fault_caught != JNI_TRUE || gc_rounds != 8 || relocation_delta == 0 ||
      thread_faults != 1 || oat_faults != 1 || fault_pc == 0u ||
      fault_address >= 64u * 1024u || !fault_pc_registered || expected_entry == 0u ||
      !entry_unchanged || completed_gc_rounds < static_cast<uint32_t>(gc_rounds) ||
      root_count_before == 0u || root_count_after < root_count_before || !root_same) {
    return Fail(env, "relocation, managed boot-OAT fault, or BSS GC-root verification failed");
  }

  std::cout << "W037_BOOT_OAT_EXECUTION_PASS target=" << target_name
            << " relocation=nonzero_aligned delta=" << relocation_delta
            << " oat=paired fault=managed_oat hits=" << oat_faults
            << " fault_address=low gc_rounds=" << gc_rounds
            << " gc_completed=" << completed_gc_rounds
            << " bss_roots=" << root_count_after
            << " root_same=1 jit=disabled\n";
  return JNI_TRUE;
}

extern "C" __declspec(dllexport) void JNICALL
Java_W037BootOatRelocationFaultGcProbe_nativeCleanup(JNIEnv* env, jclass) {
  Cleanup(env);
}
