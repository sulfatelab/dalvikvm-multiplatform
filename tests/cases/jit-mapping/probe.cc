#include <windows.h>
#include <psapi.h>

#include <jni.h>

#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

#include "jit/jit_code_cache.h"
#include "jit/jit_memory_region.h"
#include "runtime.h"

namespace {

constexpr uintptr_t k4GiB = UINT64_C(0x100000000);

jboolean ThrowFailure(JNIEnv *env, const std::string &message) {
  std::cerr << "W025_JIT_MAPPING_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message.c_str());
  }
  return JNI_FALSE;
}

bool QueryRange(const void *address, SIZE_T expected_size,
                DWORD expected_protect, void *expected_allocation_base,
                const char *label, std::string *error) {
  MEMORY_BASIC_INFORMATION info = {};
  if (::VirtualQuery(address, &info, sizeof(info)) != sizeof(info)) {
    *error = std::string("VirtualQuery failed for ") + label;
    return false;
  }
  const uintptr_t begin = reinterpret_cast<uintptr_t>(address);
  const uintptr_t region_begin = reinterpret_cast<uintptr_t>(info.BaseAddress);
  if (info.State != MEM_COMMIT || info.Type != MEM_MAPPED ||
      info.Protect != expected_protect ||
      info.AllocationBase != expected_allocation_base || begin < region_begin ||
      expected_size > info.RegionSize - (begin - region_begin)) {
    std::ostringstream stream;
    stream << label << " mismatch state=0x" << std::hex << info.State
           << " type=0x" << info.Type << " protect=0x" << info.Protect
           << " allocation_base=" << info.AllocationBase
           << " base=" << info.BaseAddress << " region_size=0x"
           << info.RegionSize << " expected_protect=0x" << expected_protect
           << " expected_allocation_base=" << expected_allocation_base
           << " expected_size=0x" << expected_size;
    *error = stream.str();
    return false;
  }
  return true;
}

bool HasNoMappedFilename(void *allocation_base, DWORD *observed_error,
                         std::string *error) {
  wchar_t name[1024] = {};
  ::SetLastError(ERROR_SUCCESS);
  const DWORD length =
      ::GetMappedFileNameW(::GetCurrentProcess(), allocation_base, name,
                           static_cast<DWORD>(std::size(name)));
  *observed_error = ::GetLastError();
  if (length != 0u) {
    std::ostringstream stream;
    stream << "pagefile section unexpectedly has a mapped filename at "
           << allocation_base;
    *error = stream.str();
    return false;
  }
  return true;
}

} // namespace

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W025JitMappingProbe_nativeAudit(JNIEnv *env, jclass,
                                     jlong expected_capacity_bytes,
                                     jboolean require_cfg) {
  art::Runtime *runtime = art::Runtime::Current();
  art::jit::JitCodeCache *code_cache =
      runtime != nullptr ? runtime->GetJitCodeCache() : nullptr;
  art::jit::JitMemoryRegion *region =
      code_cache != nullptr ? code_cache->GetCurrentRegion() : nullptr;
  if (region == nullptr || !region->IsValid()) {
    return ThrowFailure(env, "ART JIT memory region is unavailable");
  }
  if (!region->HasDualDataMapping() || !region->HasDualCodeMapping() ||
      !region->HasCodeMapping()) {
    return ThrowFailure(env,
                        "ART did not create the complete J-2 dual mapping");
  }

  const art::MemMap *data = region->GetDataPages();
  const art::MemMap *code = region->GetExecPages();
  const size_t capacity = data->Size() + code->Size();
  if (expected_capacity_bytes <= 0 ||
      capacity != static_cast<size_t>(expected_capacity_bytes)) {
    std::ostringstream stream;
    stream << "capacity mismatch actual=" << capacity
           << " expected=" << expected_capacity_bytes;
    return ThrowFailure(env, stream.str());
  }
  if (data->End() != code->Begin() ||
      reinterpret_cast<uintptr_t>(data->Begin()) >= k4GiB ||
      reinterpret_cast<uintptr_t>(code->End()) > k4GiB) {
    return ThrowFailure(
        env, "primary data/code view is not contiguous and below 4 GiB");
  }

  uint8_t *writable = region->GetWritableDataAddress(data->Begin());
  uint8_t *writable_code = writable + data->Size();
  std::string error;
  if (!QueryRange(data->Begin(), data->Size(), PAGE_READONLY, data->Begin(),
                  "primary_data", &error) ||
      !QueryRange(code->Begin(), code->Size(), PAGE_EXECUTE_READ, data->Begin(),
                  "primary_code", &error) ||
      !QueryRange(writable, capacity, PAGE_READWRITE, writable,
                  "writable_alias", &error) ||
      !QueryRange(writable_code, code->Size(), PAGE_READWRITE, writable,
                  "writable_code_alias", &error)) {
    return ThrowFailure(env, error);
  }

  DWORD primary_name_error = ERROR_SUCCESS;
  DWORD writable_name_error = ERROR_SUCCESS;
  if (!HasNoMappedFilename(data->Begin(), &primary_name_error, &error) ||
      !HasNoMappedFilename(writable, &writable_name_error, &error)) {
    return ThrowFailure(env, error);
  }

  PROCESS_MITIGATION_DYNAMIC_CODE_POLICY dynamic_code = {};
  PROCESS_MITIGATION_CONTROL_FLOW_GUARD_POLICY cfg = {};
  if (!::GetProcessMitigationPolicy(::GetCurrentProcess(),
                                    ProcessDynamicCodePolicy, &dynamic_code,
                                    sizeof(dynamic_code)) ||
      !::GetProcessMitigationPolicy(::GetCurrentProcess(),
                                    ProcessControlFlowGuardPolicy, &cfg,
                                    sizeof(cfg))) {
    return ThrowFailure(env, "GetProcessMitigationPolicy failed");
  }
  if (require_cfg != JNI_FALSE && cfg.EnableControlFlowGuard == 0u) {
    return ThrowFailure(
        env, "CFG was required but is not enabled in the ART process");
  }

  std::cout
      << std::hex << "W025_JIT_MAPPING addresses data="
      << static_cast<void *>(data->Begin())
      << " code=" << static_cast<void *>(code->Begin())
      << " writable=" << static_cast<void *>(writable)
      << " writable_code=" << static_cast<void *>(writable_code) << std::dec
      << '\n'
      << "W025_JIT_MAPPING roles primary_data=R primary_code=RX alias_data=RW "
         "alias_code=RW type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes="
      << capacity << '\n'
      << "W025_JIT_MAPPING backing primary_name_length=0 primary_error="
      << primary_name_error
      << " alias_name_length=0 alias_error=" << writable_name_error << '\n'
      << "W025_JIT_MAPPING policy dynamic_prohibit="
      << dynamic_code.ProhibitDynamicCode
      << " dynamic_thread_opt_out=" << dynamic_code.AllowThreadOptOut
      << " cfg_enabled=" << cfg.EnableControlFlowGuard
      << " cfg_strict=" << cfg.StrictMode
      << " cfg_export_suppression=" << cfg.EnableExportSuppression << '\n'
      << "W025_JIT_MAPPING_PASS\n";
  return JNI_TRUE;
}
