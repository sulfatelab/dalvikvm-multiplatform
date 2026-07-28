#include <psapi.h>
#include <windows.h>

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {

constexpr uintptr_t k4GiB = UINT64_C(0x100000000);
constexpr SIZE_T kMiB = 1024u * 1024u;
constexpr SIZE_T kDefaultCapacity = 64u * kMiB;
constexpr SIZE_T kMaximumCapacity = 1024u * kMiB;

bool Check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "W025_SECTION_POLICY_FAIL: %s error=%lu\n", message,
                 ::GetLastError());
  }
  return condition;
}

uintptr_t AlignUp(uintptr_t value, size_t alignment) {
  return (value + alignment - 1u) & ~(static_cast<uintptr_t>(alignment) - 1u);
}

uintptr_t AlignDown(uintptr_t value, size_t alignment) {
  return value & ~(static_cast<uintptr_t>(alignment) - 1u);
}

bool QueryRange(const void *address, SIZE_T expected_size,
                DWORD expected_protection, void *expected_allocation_base,
                const char *label) {
  MEMORY_BASIC_INFORMATION info = {};
  if (!Check(::VirtualQuery(address, &info, sizeof(info)) == sizeof(info),
             label)) {
    return false;
  }
  const uintptr_t begin = reinterpret_cast<uintptr_t>(address);
  const uintptr_t region_begin = reinterpret_cast<uintptr_t>(info.BaseAddress);
  const bool matches =
      info.State == MEM_COMMIT && info.Type == MEM_MAPPED &&
      info.Protect == expected_protection &&
      info.AllocationBase == expected_allocation_base &&
      begin >= region_begin &&
      expected_size <= info.RegionSize - (begin - region_begin);
  if (!matches) {
    std::fprintf(
        stderr,
        "W025_SECTION_POLICY_FAIL: %s state=0x%lx type=0x%lx protect=0x%lx "
        "allocation_base=%p base=%p region_size=%zu\n",
        label, info.State, info.Type, info.Protect, info.AllocationBase,
        info.BaseAddress, static_cast<size_t>(info.RegionSize));
  }
  return matches;
}

bool HasNoMappedFilename(void *address, DWORD *observed_error) {
  wchar_t path[1024] = {};
  ::SetLastError(ERROR_SUCCESS);
  const DWORD length =
      ::GetMappedFileNameW(::GetCurrentProcess(), address, path,
                           static_cast<DWORD>(sizeof(path) / sizeof(path[0])));
  *observed_error = ::GetLastError();
  if (length != 0u) {
    std::fwprintf(
        stderr,
        L"W025_SECTION_POLICY_FAIL: mapping unexpectedly has filename %ls\n",
        path);
    return false;
  }
  return true;
}

void *MapLow(HANDLE section, SIZE_T capacity, DWORD protection) {
  SYSTEM_INFO system_info = {};
  ::GetSystemInfo(&system_info);
  MEM_ADDRESS_REQUIREMENTS requirements = {};
  requirements.LowestStartingAddress = reinterpret_cast<void *>(
      static_cast<uintptr_t>(system_info.dwAllocationGranularity));
  requirements.HighestEndingAddress = reinterpret_cast<void *>(UINT32_MAX);
  requirements.Alignment = 0u;
  MEM_EXTENDED_PARAMETER parameter = {};
  parameter.Type = MemExtendedParameterAddressRequirements;
  parameter.Pointer = &requirements;
  return ::MapViewOfFile3(section, nullptr, nullptr, 0u, capacity, 0u,
                          protection, &parameter, 1u);
}

HANDLE CreateCommittedSection(SIZE_T capacity) {
  return ::CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr,
                              PAGE_EXECUTE_READWRITE | SEC_COMMIT,
                              static_cast<DWORD>(capacity >> 32),
                              static_cast<DWORD>(capacity), nullptr);
}

bool RunMappedCase(SIZE_T capacity, bool execute_code, const char *label) {
  HANDLE section = CreateCommittedSection(capacity);
  if (!Check(section != nullptr,
             "CreateFileMappingW(pagefile, SEC_COMMIT) failed")) {
    return false;
  }
  void *primary = MapLow(section, capacity, PAGE_EXECUTE_READ);
  void *writable = ::MapViewOfFile3(section, nullptr, nullptr, 0u, capacity, 0u,
                                    PAGE_READWRITE, nullptr, 0u);
  bool ok = Check(primary != nullptr, "low primary MapViewOfFile3 failed") &&
            Check(writable != nullptr, "writable alias MapViewOfFile3 failed");
  const SIZE_T divider = capacity / 2u;
  DWORD old_protection = 0u;
  if (ok) {
    ok &= Check(reinterpret_cast<uintptr_t>(primary) < k4GiB &&
                    capacity <= k4GiB - reinterpret_cast<uintptr_t>(primary),
                "primary mapping is outside the low-4-GiB range");
    ok &= Check(::VirtualProtect(primary, divider, PAGE_READONLY,
                                 &old_protection) != FALSE,
                "VirtualProtect primary data split failed");
  }
  if (ok) {
    ok &= QueryRange(primary, divider, PAGE_READONLY, primary, "primary_data");
    ok &= QueryRange(static_cast<uint8_t *>(primary) + divider,
                     capacity - divider, PAGE_EXECUTE_READ, primary,
                     "primary_code");
    ok &= QueryRange(writable, capacity, PAGE_READWRITE, writable,
                     "writable_alias");
  }

  DWORD primary_name_error = ERROR_SUCCESS;
  DWORD alias_name_error = ERROR_SUCCESS;
  if (ok) {
    ok &= HasNoMappedFilename(primary, &primary_name_error);
    ok &= HasNoMappedFilename(writable, &alias_name_error);
  }

  if (ok && execute_code) {
    uint8_t *writable_code = static_cast<uint8_t *>(writable) + divider;
    writable_code[0] = 0xb8u; // mov eax, 42
    writable_code[1] = 42u;
    writable_code[2] = 0u;
    writable_code[3] = 0u;
    writable_code[4] = 0u;
    writable_code[5] = 0xc3u; // ret
    uint8_t *executable_code = static_cast<uint8_t *>(primary) + divider;
    ok &= Check(::FlushInstructionCache(::GetCurrentProcess(), executable_code,
                                        6u) != FALSE,
                "FlushInstructionCache failed");
    using Function = int (*)(void);
    volatile Function function = reinterpret_cast<Function>(executable_code);
    ok &= Check(function() == 42,
                "indirect execution from RX view returned wrong value");
  }

  if (ok) {
    std::printf(
        "W025_SECTION_MAPPING label=%s capacity_bytes=%zu primary=%p alias=%p "
        "roles=R_RX_RW type=MEM_MAPPED rwx=0 mapped_names=0 "
        "primary_name_error=%lu alias_name_error=%lu execute=%d\n",
        label, static_cast<size_t>(capacity), primary, writable,
        primary_name_error, alias_name_error, execute_code ? 1 : 0);
  }
  if (writable != nullptr) {
    ok &= Check(::UnmapViewOfFile(writable) != FALSE,
                "UnmapViewOfFile(alias) failed");
  }
  if (primary != nullptr) {
    ok &= Check(::UnmapViewOfFile(primary) != FALSE,
                "UnmapViewOfFile(primary) failed");
  }
  ok &= Check(::CloseHandle(section) != FALSE, "CloseHandle(section) failed");
  return ok;
}

bool ReserveExact(uintptr_t address, size_t size,
                  std::vector<void *> *reservations) {
  void *reservation = ::VirtualAlloc(reinterpret_cast<void *>(address), size,
                                     MEM_RESERVE, PAGE_NOACCESS);
  if (reservation != reinterpret_cast<void *>(address)) {
    if (reservation != nullptr) {
      ::VirtualFree(reservation, 0u, MEM_RELEASE);
    }
    return false;
  }
  reservations->push_back(reservation);
  return true;
}

bool FragmentCompleteLowRange(std::vector<void *> *reservations) {
  SYSTEM_INFO system_info = {};
  ::GetSystemInfo(&system_info);
  const size_t granularity = system_info.dwAllocationGranularity;
  const uintptr_t minimum = AlignUp(
      reinterpret_cast<uintptr_t>(system_info.lpMinimumApplicationAddress),
      granularity);
  // MEM_RESERVE does not consume commit. Use a coarse chunk so complete-low-VA
  // fragmentation stays fast on native Windows while still leaving only one
  // allocation-granularity hole between reservations.
  constexpr size_t kReserveChunk = 64u * 1024u * 1024u;

  uintptr_t cursor = minimum;
  while (cursor < k4GiB) {
    MEMORY_BASIC_INFORMATION info = {};
    if (::VirtualQuery(reinterpret_cast<void *>(cursor), &info, sizeof(info)) !=
        sizeof(info)) {
      return false;
    }
    const uintptr_t base = reinterpret_cast<uintptr_t>(info.BaseAddress);
    const uintptr_t end =
        info.RegionSize >= k4GiB - base ? k4GiB : base + info.RegionSize;
    if (end <= cursor) {
      return false;
    }
    if (info.State != MEM_FREE) {
      cursor = end;
      continue;
    }
    const uintptr_t free_begin = AlignUp(std::max(cursor, base), granularity);
    const uintptr_t free_end = AlignDown(end, granularity);
    if (free_begin >= free_end || free_end - free_begin <= granularity) {
      cursor = end;
      continue;
    }

    const uintptr_t reserve_begin = free_begin + granularity;
    size_t reserve_size = static_cast<size_t>(free_end - reserve_begin);
    reserve_size = std::min(reserve_size, kReserveChunk);
    reserve_size = static_cast<size_t>(AlignDown(reserve_size, granularity));
    if (reserve_size == 0u ||
        !ReserveExact(reserve_begin, reserve_size, reservations)) {
      return false;
    }
    cursor = reserve_begin + reserve_size;
  }
  return true;
}

bool ReleaseReservations(std::vector<void *> *reservations) {
  bool ok = true;
  for (void *reservation : *reservations) {
    ok &= ::VirtualFree(reservation, 0u, MEM_RELEASE) != FALSE;
  }
  reservations->clear();
  return ok;
}

bool RunLowFailureCase() {
  HANDLE section = CreateCommittedSection(kDefaultCapacity);
  if (!Check(section != nullptr, "low-failure section creation failed")) {
    return false;
  }
  std::vector<void *> reservations;
  reservations.reserve(8192u);
  bool ok = Check(FragmentCompleteLowRange(&reservations),
                  "low-VA fragmentation failed");
  void *rejected =
      ok ? MapLow(section, kDefaultCapacity, PAGE_EXECUTE_READ) : nullptr;
  const DWORD rejection_error =
      rejected == nullptr ? ::GetLastError() : ERROR_SUCCESS;
  ok &= Check(rejected == nullptr,
              "low mapping unexpectedly succeeded after fragmentation");

  void *high = ::MapViewOfFile3(section, nullptr, nullptr, 0u, kDefaultCapacity,
                                0u, PAGE_EXECUTE_READ, nullptr, 0u);
  ok &= Check(high != nullptr,
              "unrestricted mapping failed while low VA was fragmented");
  ok &= Check(high == nullptr || reinterpret_cast<uintptr_t>(high) >= k4GiB,
              "unrestricted mapping unexpectedly fit below 4 GiB");
  if (high != nullptr) {
    ok &= Check(::UnmapViewOfFile(high) != FALSE,
                "unmap unrestricted mapping failed");
  }

  const size_t reservation_count = reservations.size();
  ok &= Check(ReleaseReservations(&reservations),
              "low-VA reservation release failed");
  void *recovered = MapLow(section, kDefaultCapacity, PAGE_EXECUTE_READ);
  ok &= Check(recovered != nullptr,
              "low mapping did not recover after fragmentation release");
  if (recovered != nullptr) {
    ok &= Check(::UnmapViewOfFile(recovered) != FALSE,
                "unmap recovered mapping failed");
  }
  ok &= Check(::CloseHandle(section) != FALSE,
              "close low-failure section failed");
  if (ok) {
    std::printf(
        "W025_LOW_VA_PASS reservations=%zu rejected=1 rejection_error=%lu "
        "no_high_fallback=1 recovery=1\n",
        reservation_count, rejection_error);
  }
  return ok;
}

bool GetCommitBytes(uint64_t *total, uint64_t *limit) {
  PERFORMANCE_INFORMATION performance = {};
  performance.cb = sizeof(performance);
  if (!::GetPerformanceInfo(&performance, sizeof(performance))) {
    return false;
  }
  *total =
      static_cast<uint64_t>(performance.CommitTotal) * performance.PageSize;
  *limit =
      static_cast<uint64_t>(performance.CommitLimit) * performance.PageSize;
  return true;
}

bool RunCommitPressureCase() {
  uint64_t before = 0u;
  uint64_t before_limit = 0u;
  if (!Check(GetCommitBytes(&before, &before_limit),
             "GetPerformanceInfo(before) failed")) {
    return false;
  }
  HANDLE section = CreateCommittedSection(kMaximumCapacity);
  if (!Check(section != nullptr, "1-GiB SEC_COMMIT section creation failed")) {
    return false;
  }
  uint64_t after_create = 0u;
  uint64_t after_limit = 0u;
  bool ok = Check(GetCommitBytes(&after_create, &after_limit),
                  "GetPerformanceInfo(after create) failed");
  const uint64_t commit_delta =
      after_create >= before ? after_create - before : 0u;
  ok &= Check(
      commit_delta >= kMaximumCapacity / 2u,
      "1-GiB SEC_COMMIT did not produce the expected system commit charge");

  void *primary = MapLow(section, kMaximumCapacity, PAGE_EXECUTE_READ);
  void *writable =
      ::MapViewOfFile3(section, nullptr, nullptr, 0u, kMaximumCapacity, 0u,
                       PAGE_READWRITE, nullptr, 0u);
  ok &= Check(primary != nullptr, "1-GiB low primary view failed");
  ok &= Check(writable != nullptr, "1-GiB writable alias failed");
  if (primary != nullptr) {
    ok &= Check(reinterpret_cast<uintptr_t>(primary) < k4GiB &&
                    kMaximumCapacity <=
                        k4GiB - reinterpret_cast<uintptr_t>(primary),
                "1-GiB primary is outside the low range");
  }
  if (writable != nullptr) {
    ok &=
        Check(::UnmapViewOfFile(writable) != FALSE, "unmap 1-GiB alias failed");
  }
  if (primary != nullptr) {
    ok &= Check(::UnmapViewOfFile(primary) != FALSE,
                "unmap 1-GiB primary failed");
  }
  ok &= Check(::CloseHandle(section) != FALSE, "close 1-GiB section failed");

  ::Sleep(50u);
  uint64_t after_close = 0u;
  uint64_t close_limit = 0u;
  ok &= Check(GetCommitBytes(&after_close, &close_limit),
              "GetPerformanceInfo(after close) failed");
  if (ok) {
    std::printf(
        "W025_SEC_COMMIT_PASS capacity_bytes=%zu commit_before=%llu "
        "commit_after_create=%llu commit_delta=%llu commit_after_close=%llu "
        "commit_limit=%llu primary_low=1 alias=1\n",
        static_cast<size_t>(kMaximumCapacity),
        static_cast<unsigned long long>(before),
        static_cast<unsigned long long>(after_create),
        static_cast<unsigned long long>(commit_delta),
        static_cast<unsigned long long>(after_close),
        static_cast<unsigned long long>(before_limit));
  }
  return ok;
}

bool PrintPolicies() {
  PROCESS_MITIGATION_DYNAMIC_CODE_POLICY dynamic_code = {};
  PROCESS_MITIGATION_CONTROL_FLOW_GUARD_POLICY cfg = {};
  const bool ok =
      Check(::GetProcessMitigationPolicy(
                ::GetCurrentProcess(), ProcessDynamicCodePolicy, &dynamic_code,
                sizeof(dynamic_code)) != FALSE,
            "GetProcessMitigationPolicy(dynamic) failed") &&
      Check(::GetProcessMitigationPolicy(::GetCurrentProcess(),
                                         ProcessControlFlowGuardPolicy, &cfg,
                                         sizeof(cfg)) != FALSE,
            "GetProcessMitigationPolicy(CFG) failed");
  if (ok) {
    std::printf(
        "W025_POLICY_OBSERVED dynamic_prohibit=%u dynamic_thread_opt_out=%u "
        "cfg_enabled=%u cfg_strict=%u cfg_export_suppression=%u\n",
        dynamic_code.ProhibitDynamicCode, dynamic_code.AllowThreadOptOut,
        cfg.EnableControlFlowGuard, cfg.StrictMode,
        cfg.EnableExportSuppression);
  }
  return ok;
}

} // namespace

int main(int argc, char **argv) {
  std::setvbuf(stdout, nullptr, _IONBF, 0u);
  const bool basic_only = argc == 2 && std::strcmp(argv[1], "--basic") == 0;
  const bool cfg_only = argc == 2 && std::strcmp(argv[1], "--cfg-call") == 0;
  const bool low_only = argc == 2 && std::strcmp(argv[1], "--low-va") == 0;
  const bool pressure_only =
      argc == 2 && std::strcmp(argv[1], "--pressure") == 0;
  if (argc > 2 ||
      (argc == 2 && !basic_only && !cfg_only && !low_only && !pressure_only)) {
    std::fprintf(stderr, "usage: W025SectionPolicyProbe.exe "
                         "[--basic|--cfg-call|--low-va|--pressure]\n");
    return 2;
  }

  bool ok = PrintPolicies();
  if (!low_only && !pressure_only) {
    ok &= RunMappedCase(kDefaultCapacity, /*execute_code=*/true, "default");
  }
  if (low_only || argc == 1) {
    ok &= RunLowFailureCase();
  }
  if (pressure_only || argc == 1) {
    ok &= RunCommitPressureCase();
  }
  if (!ok) {
    return 1;
  }
  const char *mode =
      basic_only
          ? "basic"
          : (cfg_only ? "cfg-call"
                      : (low_only ? "low-va"
                                  : (pressure_only ? "pressure" : "full")));
  std::printf("W025_SECTION_POLICY_PASS mode=%s\n", mode);
  return 0;
}
