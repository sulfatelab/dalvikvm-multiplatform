#include <malloc.h>
#include <process.h>
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#include "stack_windows.h"

namespace {

constexpr size_t kThreadStackSize = 2u * 1024u * 1024u;
constexpr DWORD kGuardPageException = 0x80000001u;

enum class ProbeMode {
  kBaseline,
  kProtected,
  kWritable,
  kDirect,
};

struct RegionSnapshot {
  uintptr_t base = 0u;
  size_t size = 0u;
  DWORD state = 0u;
  DWORD protect = 0u;
  DWORD type = 0u;
  bool valid = false;
};

struct ProbeObservation {
  ProbeMode mode = ProbeMode::kBaseline;
  size_t requested_guarantee = 0u;
  ULONG guarantee_before = 0u;
  ULONG guarantee_previous = 0u;
  ULONG guarantee_after = 0u;
  DWORD guarantee_error = 0u;
  bool guarantee_query_before_ok = false;
  bool guarantee_set_ok = false;
  bool guarantee_query_after_ok = false;
  DWORD thread_id = 0u;
  uintptr_t stack_low = 0u;
  uintptr_t stack_high = 0u;
  uintptr_t fixed_page = 0u;
  uintptr_t guard_before = 0u;
  DWORD guard_before_protect = 0u;
  uintptr_t guard_after = 0u;
  DWORD guard_after_protect = 0u;
  art::Win32StackPageRecord page_record;
  art::Win32StackPageSelection saved_selection;
  const char *setup_failure = nullptr;
  uint32_t setup_error = 0u;
  const char *protect_before_reset_failure = nullptr;
  uint32_t protect_before_reset_error = 0u;
  const char *protect_after_reset_failure = nullptr;
  uint32_t protect_after_reset_error = 0u;
  const char *restore_failure = nullptr;
  uint32_t restore_error = 0u;
  bool page_installed = false;
  bool page_unprotected = false;
  bool protect_before_reset_attempted = false;
  bool protect_before_reset_ok = false;
  bool protect_after_reset_attempted = false;
  bool protect_after_reset_ok = false;
  bool restore_ok = false;
  bool reset_attempted = false;
  bool reset_ok = false;
  bool unexpected_return = false;
  DWORD caught_code = 0u;
  volatile LONG exception_count = 0;
  volatile LONG guard_exception_count = 0;
  volatile LONG terminal_claimed = 0;
  DWORD terminal_code = 0u;
  uintptr_t terminal_rip = 0u;
  uintptr_t terminal_rsp = 0u;
  uintptr_t terminal_fault_address = 0u;
  uintptr_t last_guard_fault_address = 0u;
  RegionSnapshot fixed_at_terminal;
  RegionSnapshot fixed_before_reset;
  RegionSnapshot fixed_after_protect;
  RegionSnapshot fixed_after_reset;
};

ProbeObservation *g_active_observation = nullptr;
volatile LONG g_failures = 0;
volatile LONG g_recurse = 1;
volatile uint8_t g_recursion_sink = 0u;

extern "C" uint8_t Win32StackPageFaultRead(const volatile uint8_t *page);

const char *ModeName(ProbeMode mode) {
  switch (mode) {
  case ProbeMode::kBaseline:
    return "baseline";
  case ProbeMode::kProtected:
    return "protected";
  case ProbeMode::kWritable:
    return "writable";
  case ProbeMode::kDirect:
    return "direct";
  }
  return "unknown";
}

bool ParseMode(const char *value, ProbeMode *mode) {
  if (std::strcmp(value, "baseline") == 0) {
    *mode = ProbeMode::kBaseline;
  } else if (std::strcmp(value, "protected") == 0) {
    *mode = ProbeMode::kProtected;
  } else if (std::strcmp(value, "writable") == 0) {
    *mode = ProbeMode::kWritable;
  } else if (std::strcmp(value, "direct") == 0) {
    *mode = ProbeMode::kDirect;
  } else {
    return false;
  }
  return true;
}

void Fail(const char *mode, const char *detail, DWORD error = 0u) {
  std::fprintf(stderr,
               "FAIL win32_stack_growth_probe mode=%s detail=%s error=%lu\n",
               mode, detail, static_cast<unsigned long>(error));
  InterlockedIncrement(&g_failures);
}

RegionSnapshot SnapshotRegion(uintptr_t address) {
  RegionSnapshot result;
  if (address == 0u) {
    return result;
  }
  MEMORY_BASIC_INFORMATION memory = {};
  if (VirtualQuery(reinterpret_cast<const void *>(address), &memory,
                   sizeof(memory)) == 0u) {
    return result;
  }
  result.base = reinterpret_cast<uintptr_t>(memory.BaseAddress);
  result.size = static_cast<size_t>(memory.RegionSize);
  result.state = memory.State;
  result.protect = memory.Protect;
  result.type = memory.Type;
  result.valid = true;
  return result;
}

void PrintRegion(const char *label, const RegionSnapshot &region) {
  std::printf("region label=%s valid=%d base=%p size=%zu state=0x%lx "
              "protect=0x%lx type=0x%lx\n",
              label, region.valid ? 1 : 0,
              reinterpret_cast<void *>(region.base), region.size,
              static_cast<unsigned long>(region.state),
              static_cast<unsigned long>(region.protect),
              static_cast<unsigned long>(region.type));
}

bool FindGuard(uintptr_t low, uintptr_t high, uintptr_t *guard_address,
               DWORD *guard_protect) {
  uintptr_t cursor = low;
  while (cursor < high) {
    MEMORY_BASIC_INFORMATION memory = {};
    if (VirtualQuery(reinterpret_cast<const void *>(cursor), &memory,
                     sizeof(memory)) == 0u) {
      return false;
    }
    const uintptr_t base = reinterpret_cast<uintptr_t>(memory.BaseAddress);
    if ((memory.Protect & PAGE_GUARD) != 0u) {
      *guard_address = base;
      *guard_protect = memory.Protect;
      return true;
    }
    const uintptr_t next = base + static_cast<uintptr_t>(memory.RegionSize);
    if (next <= cursor) {
      return false;
    }
    cursor = next;
  }
  *guard_address = 0u;
  *guard_protect = 0u;
  return true;
}

LONG WINAPI ObserveException(EXCEPTION_POINTERS *exception) {
  ProbeObservation *observation = g_active_observation;
  if (observation == nullptr ||
      observation->thread_id != GetCurrentThreadId() || exception == nullptr ||
      exception->ExceptionRecord == nullptr) {
    return EXCEPTION_CONTINUE_SEARCH;
  }

  EXCEPTION_RECORD *record = exception->ExceptionRecord;
  InterlockedIncrement(&observation->exception_count);
  uintptr_t fault_address = 0u;
  if (record->NumberParameters >= 2u) {
    fault_address = static_cast<uintptr_t>(record->ExceptionInformation[1]);
  }
  if (record->ExceptionCode == kGuardPageException) {
    InterlockedIncrement(&observation->guard_exception_count);
    observation->last_guard_fault_address = fault_address;
  }
  if ((record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION ||
       record->ExceptionCode == EXCEPTION_STACK_OVERFLOW) &&
      InterlockedCompareExchange(&observation->terminal_claimed, 1, 0) == 0) {
    observation->terminal_code = record->ExceptionCode;
    observation->terminal_fault_address = fault_address;
    if (exception->ContextRecord != nullptr) {
      observation->terminal_rip =
          static_cast<uintptr_t>(exception->ContextRecord->Rip);
      observation->terminal_rsp =
          static_cast<uintptr_t>(exception->ContextRecord->Rsp);
    }
    observation->fixed_at_terminal = SnapshotRegion(observation->fixed_page);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

int CatchTerminalException(DWORD code) {
  return code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_STACK_OVERFLOW
             ? EXCEPTION_EXECUTE_HANDLER
             : EXCEPTION_CONTINUE_SEARCH;
}

__declspec(noinline) void ConsumeStack(uint32_t depth) {
  volatile uint8_t block[8192];
  block[0] = static_cast<uint8_t>(depth);
  block[4096] = static_cast<uint8_t>(depth >> 8u);
  if (InterlockedCompareExchange(&g_recurse, 1, 1) != 0) {
    ConsumeStack(depth + 1u);
  }
  const uint8_t value = block[(depth * 97u) & 4095u];
  g_recursion_sink = static_cast<uint8_t>(g_recursion_sink ^ value);
}

__declspec(noinline) void RunFaultingOperation(ProbeObservation *observation) {
  __try {
    if (observation->mode == ProbeMode::kDirect) {
      volatile uint8_t *page =
          reinterpret_cast<volatile uint8_t *>(observation->fixed_page);
      g_recursion_sink = Win32StackPageFaultRead(page);
    } else {
      ConsumeStack(0u);
    }
    observation->unexpected_return = true;
  } __except (CatchTerminalException(GetExceptionCode())) {
    observation->caught_code = observation->terminal_code;
    observation->fixed_before_reset = SnapshotRegion(observation->fixed_page);
    if (observation->mode == ProbeMode::kWritable) {
      observation->protect_before_reset_attempted = true;
      observation->protect_before_reset_ok = art::ProtectWin32StackPage(
          &observation->page_record, &observation->protect_before_reset_failure,
          &observation->protect_before_reset_error);
      observation->fixed_after_protect =
          SnapshotRegion(observation->fixed_page);
    }
  }
}

unsigned __stdcall ProbeWorker(void *opaque) {
  ProbeObservation *observation = static_cast<ProbeObservation *>(opaque);
  observation->thread_id = GetCurrentThreadId();
  ULONG guarantee_before = 0u;
  observation->guarantee_query_before_ok =
      SetThreadStackGuarantee(&guarantee_before) != 0;
  observation->guarantee_before = guarantee_before;
  if (!observation->guarantee_query_before_ok) {
    observation->guarantee_error = GetLastError();
    return 4u;
  }
  if (observation->requested_guarantee != 0u) {
    ULONG requested = static_cast<ULONG>(observation->requested_guarantee);
    observation->guarantee_set_ok = SetThreadStackGuarantee(&requested) != 0;
    observation->guarantee_previous = requested;
    if (!observation->guarantee_set_ok) {
      observation->guarantee_error = GetLastError();
      return 5u;
    }
  } else {
    observation->guarantee_set_ok = true;
    observation->guarantee_previous = observation->guarantee_before;
  }
  ULONG guarantee_after = 0u;
  observation->guarantee_query_after_ok =
      SetThreadStackGuarantee(&guarantee_after) != 0;
  observation->guarantee_after = guarantee_after;
  if (!observation->guarantee_query_after_ok) {
    observation->guarantee_error = GetLastError();
    return 6u;
  }
  ULONG_PTR low = 0u;
  ULONG_PTR high = 0u;
  GetCurrentThreadStackLimits(&low, &high);
  observation->stack_low = static_cast<uintptr_t>(low);
  observation->stack_high = static_cast<uintptr_t>(high);

  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);
  const size_t page_size = static_cast<size_t>(system_info.dwPageSize);
  FindGuard(observation->stack_low, observation->stack_high,
            &observation->guard_before, &observation->guard_before_protect);

  if (observation->mode != ProbeMode::kBaseline) {
    observation->page_installed = art::InstallWin32StackPage(
        observation->stack_low, observation->stack_high, page_size, page_size,
        3u * page_size, &observation->page_record, &observation->setup_failure,
        &observation->setup_error);
    if (!observation->page_installed) {
      return 2u;
    }
    observation->fixed_page = observation->page_record.selection.page_begin;
    observation->saved_selection = observation->page_record.selection;
    if (observation->mode == ProbeMode::kWritable) {
      observation->page_unprotected = art::UnprotectWin32StackPage(
          &observation->page_record, &observation->setup_failure,
          &observation->setup_error);
      if (!observation->page_unprotected) {
        return 3u;
      }
    }
  }

  g_active_observation = observation;
  MemoryBarrier();
  RunFaultingOperation(observation);
  MemoryBarrier();
  g_active_observation = nullptr;

  if (observation->caught_code == EXCEPTION_STACK_OVERFLOW) {
    observation->reset_attempted = true;
    observation->reset_ok = _resetstkoflw() != 0;
  }
  observation->fixed_after_reset = SnapshotRegion(observation->fixed_page);
  FindGuard(observation->stack_low, observation->stack_high,
            &observation->guard_after, &observation->guard_after_protect);

  if (observation->mode == ProbeMode::kWritable &&
      !observation->protect_before_reset_ok) {
    observation->protect_after_reset_attempted = true;
    observation->protect_after_reset_ok = art::ProtectWin32StackPage(
        &observation->page_record, &observation->protect_after_reset_failure,
        &observation->protect_after_reset_error);
  }

  if (observation->page_installed) {
    observation->restore_ok = art::RestoreWin32StackPage(
        &observation->page_record, &observation->restore_failure,
        &observation->restore_error);
  } else {
    observation->restore_ok = true;
  }
  return 0u;
}

void PrintObservation(const ProbeObservation &observation) {
  const char *mode = ModeName(observation.mode);
  std::printf("stack_guarantee requested=%zu before=%lu previous=%lu after=%lu "
              "query_before_ok=%d set_ok=%d query_after_ok=%d error=%lu\n",
              observation.requested_guarantee,
              static_cast<unsigned long>(observation.guarantee_before),
              static_cast<unsigned long>(observation.guarantee_previous),
              static_cast<unsigned long>(observation.guarantee_after),
              observation.guarantee_query_before_ok ? 1 : 0,
              observation.guarantee_set_ok ? 1 : 0,
              observation.guarantee_query_after_ok ? 1 : 0,
              static_cast<unsigned long>(observation.guarantee_error));
  std::printf(
      "stack_growth mode=%s stack_low=%p stack_high=%p stack_size=%zu fixed=%p "
      "guard_before=%p guard_before_protect=0x%lx guard_after=%p "
      "guard_after_protect=0x%lx\n",
      mode, reinterpret_cast<void *>(observation.stack_low),
      reinterpret_cast<void *>(observation.stack_high),
      observation.stack_high - observation.stack_low,
      reinterpret_cast<void *>(observation.fixed_page),
      reinterpret_cast<void *>(observation.guard_before),
      static_cast<unsigned long>(observation.guard_before_protect),
      reinterpret_cast<void *>(observation.guard_after),
      static_cast<unsigned long>(observation.guard_after_protect));
  if (observation.page_installed) {
    const art::Win32StackPageSelection &selection = observation.saved_selection;
    std::printf("fixed_page mode=%s excluded=%zu original_state=0x%lx "
                "original_protect=0x%lx "
                "original_type=0x%lx installed=%d unprotected=%d\n",
                mode, selection.excluded_low_size,
                static_cast<unsigned long>(selection.original_state),
                static_cast<unsigned long>(selection.original_protect),
                static_cast<unsigned long>(selection.original_type),
                observation.page_installed ? 1 : 0,
                observation.page_unprotected ? 1 : 0);
  }
  std::printf(
      "terminal mode=%s caught=0x%08lx observed=0x%08lx rip=%p rsp=%p fault=%p "
      "exceptions=%ld guard_exceptions=%ld last_guard_fault=%p "
      "unexpected_return=%d\n",
      mode, static_cast<unsigned long>(observation.caught_code),
      static_cast<unsigned long>(observation.terminal_code),
      reinterpret_cast<void *>(observation.terminal_rip),
      reinterpret_cast<void *>(observation.terminal_rsp),
      reinterpret_cast<void *>(observation.terminal_fault_address),
      observation.exception_count, observation.guard_exception_count,
      reinterpret_cast<void *>(observation.last_guard_fault_address),
      observation.unexpected_return ? 1 : 0);
  PrintRegion("fixed_at_terminal", observation.fixed_at_terminal);
  PrintRegion("fixed_before_reset", observation.fixed_before_reset);
  PrintRegion("fixed_after_protect", observation.fixed_after_protect);
  PrintRegion("fixed_after_reset", observation.fixed_after_reset);
  std::printf(
      "recovery mode=%s protect_before_reset_attempted=%d "
      "protect_before_reset_ok=%d "
      "protect_before_reset_error=%lu protect_before_reset_failure=%s "
      "reset_attempted=%d reset_ok=%d protect_after_reset_attempted=%d "
      "protect_after_reset_ok=%d protect_after_reset_error=%lu "
      "protect_after_reset_failure=%s restore_ok=%d restore_error=%lu "
      "restore_failure=%s\n",
      mode, observation.protect_before_reset_attempted ? 1 : 0,
      observation.protect_before_reset_ok ? 1 : 0,
      static_cast<unsigned long>(observation.protect_before_reset_error),
      observation.protect_before_reset_failure != nullptr
          ? observation.protect_before_reset_failure
          : "none",
      observation.reset_attempted ? 1 : 0, observation.reset_ok ? 1 : 0,
      observation.protect_after_reset_attempted ? 1 : 0,
      observation.protect_after_reset_ok ? 1 : 0,
      static_cast<unsigned long>(observation.protect_after_reset_error),
      observation.protect_after_reset_failure != nullptr
          ? observation.protect_after_reset_failure
          : "none",
      observation.restore_ok ? 1 : 0,
      static_cast<unsigned long>(observation.restore_error),
      observation.restore_failure != nullptr ? observation.restore_failure
                                             : "none");
}

} // namespace

int main(int argc, char **argv) {
  if (argc < 2 || argc > 3) {
    std::fprintf(stderr, "usage: win32_stack_growth_probe.exe "
                         "<baseline|protected|writable|direct> "
                         "[stack-guarantee-bytes]\n");
    return 2;
  }
  ProbeObservation observation;
  if (!ParseMode(argv[1], &observation.mode)) {
    std::fprintf(stderr, "unknown stack-growth mode: %s\n", argv[1]);
    return 2;
  }
  if (argc == 3) {
    char *end = nullptr;
    const unsigned long long parsed = std::strtoull(argv[2], &end, 0);
    if (end == argv[2] || *end != '\0' ||
        parsed > std::numeric_limits<ULONG>::max()) {
      std::fprintf(stderr, "invalid stack guarantee: %s\n", argv[2]);
      return 2;
    }
    observation.requested_guarantee = static_cast<size_t>(parsed);
  }

  PVOID handler = AddVectoredExceptionHandler(1u, ObserveException);
  if (handler == nullptr) {
    Fail(argv[1], "AddVectoredExceptionHandler failed", GetLastError());
    return 1;
  }

  unsigned int thread_id = 0u;
  uintptr_t raw_thread = _beginthreadex(
      nullptr, static_cast<unsigned int>(kThreadStackSize), ProbeWorker,
      &observation, STACK_SIZE_PARAM_IS_A_RESERVATION, &thread_id);
  if (raw_thread == 0u) {
    Fail(argv[1], "_beginthreadex failed", GetLastError());
    RemoveVectoredExceptionHandler(handler);
    return 1;
  }
  HANDLE thread = reinterpret_cast<HANDLE>(raw_thread);
  if (WaitForSingleObject(thread, 30000u) != WAIT_OBJECT_0) {
    Fail(argv[1], "worker did not finish", GetLastError());
    CloseHandle(thread);
    RemoveVectoredExceptionHandler(handler);
    return 1;
  }
  DWORD worker_exit = 0u;
  if (!GetExitCodeThread(thread, &worker_exit)) {
    Fail(argv[1], "GetExitCodeThread failed", GetLastError());
  }
  CloseHandle(thread);
  if (RemoveVectoredExceptionHandler(handler) == 0u) {
    Fail(argv[1], "RemoveVectoredExceptionHandler failed", GetLastError());
  }

  PrintObservation(observation);
  if (worker_exit != 0u) {
    Fail(argv[1],
         observation.setup_failure != nullptr ? observation.setup_failure
                                              : "worker setup failed",
         observation.setup_error != 0u ? observation.setup_error : worker_exit);
  }
  if (observation.unexpected_return || observation.caught_code == 0u ||
      observation.terminal_code != observation.caught_code) {
    Fail(argv[1],
         "terminal exception was not consistently observed and caught");
  }
  if (observation.caught_code == EXCEPTION_STACK_OVERFLOW &&
      !observation.reset_ok) {
    Fail(argv[1], "_resetstkoflw failed after STATUS_STACK_OVERFLOW");
  }
  if (!observation.restore_ok) {
    Fail(argv[1],
         observation.restore_failure != nullptr ? observation.restore_failure
                                                : "page restoration failed",
         observation.restore_error);
  }
  if (observation.mode == ProbeMode::kWritable &&
      !observation.protect_before_reset_ok &&
      !observation.protect_after_reset_ok) {
    std::puts("stack_growth_finding writable_page_could_not_be_reprotected=1");
  }

  std::printf("win32_stack_growth_probe mode=%s failures=%ld worker_exit=%lu\n",
              ModeName(observation.mode), g_failures,
              static_cast<unsigned long>(worker_exit));
  if (g_failures != 0) {
    return 1;
  }
  std::puts("win32_stack_growth_probe OK");
  return 0;
}
