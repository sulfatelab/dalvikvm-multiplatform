#ifndef _CRT_SECURE_NO_WARNINGS
#define _CRT_SECURE_NO_WARNINGS
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <process.h>
#include <psapi.h>

enum {
  kThreadStackSize = 2u * 1024u * 1024u,
  kPregrowLowReserveConservative = 256u * 1024u,
  kRecursiveFrameSize = 512u,
  kRequestedGuaranteePages = 4u,
  kArtOverflowReserve = 8192u,
};

static const DWORD kGuardPageException = 0x80000001u;

typedef enum ProbeMode {
  kModeImplicit,
  kModeNative,
  kModeAttachDetach,
  kModeCommitScale,
} ProbeMode;

typedef enum TargetPolicy {
  kTargetConservative,
  kTargetE9,
} TargetPolicy;

typedef struct RegionSnapshot {
  uintptr_t base;
  uintptr_t allocation_base;
  size_t size;
  DWORD state;
  DWORD protect;
  DWORD type;
  int valid;
} RegionSnapshot;

typedef struct ProbeObservation {
  ProbeMode mode;
  TargetPolicy target_policy;
  DWORD thread_id;
  uintptr_t stack_low;
  uintptr_t stack_high;
  size_t page_size;
  size_t memory_prefix;
  ULONG guarantee_before;
  ULONG guarantee_after;
  uintptr_t guard_before;
  DWORD guard_before_protect;
  size_t guard_before_size;
  uintptr_t guard_after_pregrow;
  DWORD guard_after_pregrow_protect;
  size_t guard_after_pregrow_size;
  uintptr_t guard_after_fault;
  DWORD guard_after_fault_protect;
  size_t guard_after_fault_size;
  uintptr_t guard_after_restore;
  DWORD guard_after_restore_protect;
  size_t guard_after_restore_size;
  uintptr_t pregrow_target;
  uintptr_t pregrow_minimum;
  uint32_t pregrow_touch_count;
  uintptr_t selected_page;
  DWORD original_protect;
  RegionSnapshot before_install;
  RegionSnapshot after_install;
  RegionSnapshot at_terminal;
  RegionSnapshot in_filter;
  RegionSnapshot after_restore;
  size_t stack_commit_before;
  size_t stack_commit_after_pregrow;
  size_t stack_commit_after_install;
  size_t stack_commit_after_restore;
  size_t process_private_before;
  size_t process_private_after_pregrow;
  size_t process_private_after_restore;
  DWORD setup_error;
  DWORD restore_error;
  DWORD caught_code;
  DWORD terminal_code;
  ULONG_PTR terminal_access_type;
  uintptr_t terminal_fault_address;
  uintptr_t terminal_rip;
  uintptr_t terminal_rsp;
  volatile LONG exception_count;
  volatile LONG guard_exception_count;
  volatile LONG terminal_claimed;
  int page_installed;
  int restore_ok;
  int unexpected_return;
  int skip_fault;
  int hold_after_install;
  HANDLE hold_event;
} ProbeObservation;

static ProbeObservation* g_active_observation;
static volatile LONG g_recurse = 1;
static volatile uint8_t g_recursion_sink;

extern void Win32ImplicitStackProbe(void);
extern uint32_t Win32PregrowStack(uintptr_t target);

static const char* ModeName(ProbeMode mode) {
  switch (mode) {
    case kModeImplicit: return "implicit";
    case kModeNative: return "native";
    case kModeAttachDetach: return "attach-detach";
    case kModeCommitScale: return "commit-scale";
    default: return "unknown";
  }
}

static const char* TargetName(TargetPolicy policy) {
  return policy == kTargetE9 ? "e9" : "conservative";
}

static int ParseArgs(int argc,
                     char** argv,
                     ProbeMode* mode,
                     TargetPolicy* policy,
                     int* thread_count,
                     int* is_native_child) {
  int i;
  *mode = kModeImplicit;
  *policy = kTargetConservative;
  *thread_count = 1;
  *is_native_child = 0;
  if (argc < 2) {
    return 0;
  }
  for (i = 1; i < argc; ++i) {
    if (strcmp(argv[i], "implicit") == 0) {
      *mode = kModeImplicit;
    } else if (strcmp(argv[i], "native") == 0) {
      *mode = kModeNative;
    } else if (strcmp(argv[i], "native-child") == 0) {
      *mode = kModeNative;
      *is_native_child = 1;
    } else if (strcmp(argv[i], "attach-detach") == 0) {
      *mode = kModeAttachDetach;
    } else if (strcmp(argv[i], "commit-scale") == 0) {
      *mode = kModeCommitScale;
    } else if (strcmp(argv[i], "e9") == 0 || strcmp(argv[i], "--e9") == 0) {
      *policy = kTargetE9;
    } else if (strcmp(argv[i], "conservative") == 0 ||
               strcmp(argv[i], "--conservative") == 0) {
      *policy = kTargetConservative;
    } else if (strncmp(argv[i], "--threads=", 10) == 0) {
      *thread_count = atoi(argv[i] + 10);
      if (*thread_count <= 0) {
        return 0;
      }
    } else {
      return 0;
    }
  }
  return 1;
}

static RegionSnapshot SnapshotRegion(uintptr_t address) {
  RegionSnapshot result;
  MEMORY_BASIC_INFORMATION memory;
  memset(&result, 0, sizeof(result));
  memset(&memory, 0, sizeof(memory));
  if (address == 0u ||
      VirtualQuery((const void*)address, &memory, sizeof(memory)) == 0u) {
    return result;
  }
  result.base = (uintptr_t)memory.BaseAddress;
  result.allocation_base = (uintptr_t)memory.AllocationBase;
  result.size = (size_t)memory.RegionSize;
  result.state = memory.State;
  result.protect = memory.Protect;
  result.type = memory.Type;
  result.valid = 1;
  return result;
}

static size_t MeasureStackCommit(uintptr_t low, uintptr_t high) {
  uintptr_t cursor = low;
  size_t committed = 0u;
  while (cursor < high) {
    RegionSnapshot region = SnapshotRegion(cursor);
    uintptr_t next;
    if (!region.valid || region.base > cursor) {
      break;
    }
    if (region.state == MEM_COMMIT) {
      uintptr_t begin = region.base < low ? low : region.base;
      uintptr_t end = region.base + (uintptr_t)region.size;
      if (end > high) {
        end = high;
      }
      if (end > begin) {
        committed += (size_t)(end - begin);
      }
    }
    next = region.base + (uintptr_t)region.size;
    if (next <= cursor) {
      break;
    }
    cursor = next;
  }
  return committed;
}

static size_t MeasureProcessPrivateBytes(void) {
  PROCESS_MEMORY_COUNTERS counters;
  memset(&counters, 0, sizeof(counters));
  counters.cb = sizeof(counters);
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &counters, sizeof(counters))) {
    return 0u;
  }
  return (size_t)counters.PagefileUsage;
}

static size_t MeasureMemoryPrefix(uintptr_t low, uintptr_t high, size_t page_size) {
  uintptr_t candidate = low + page_size;
  if (candidate >= high) {
    return 0u;
  }
  while (candidate < high) {
    RegionSnapshot region = SnapshotRegion(candidate);
    uintptr_t region_end;
    DWORD base_protect;
    if (!region.valid || region.allocation_base != low || region.base > candidate) {
      break;
    }
    region_end = region.base + (uintptr_t)region.size;
    if (region_end <= candidate || region_end > high) {
      break;
    }
    base_protect = region.protect & 0xffu;
    if (region.state == MEM_COMMIT &&
        (base_protect == PAGE_NOACCESS || (region.protect & PAGE_GUARD) != 0u)) {
      candidate = region_end;
      continue;
    }
    break;
  }
  return (size_t)(candidate - low);
}

static int FindGuard(uintptr_t low,
                     uintptr_t high,
                     uintptr_t* address,
                     DWORD* protect,
                     size_t* size) {
  uintptr_t cursor = low;
  while (cursor < high) {
    RegionSnapshot region = SnapshotRegion(cursor);
    uintptr_t next;
    if (!region.valid || region.base > cursor) {
      return 0;
    }
    if ((region.protect & PAGE_GUARD) != 0u) {
      *address = region.base;
      *protect = region.protect;
      *size = region.size;
      return 1;
    }
    next = region.base + (uintptr_t)region.size;
    if (next <= cursor || next > high) {
      return 0;
    }
    cursor = next;
  }
  *address = 0u;
  *protect = 0u;
  *size = 0u;
  return 1;
}

__declspec(noinline) static void RunImplicitRecursion(uint32_t depth) {
  volatile uint8_t block[kRecursiveFrameSize];
  Win32ImplicitStackProbe();
  block[0] = (uint8_t)depth;
  block[kRecursiveFrameSize - 1u] = (uint8_t)(depth >> 8u);
  if (InterlockedCompareExchange(&g_recurse, 1, 1) != 0) {
    RunImplicitRecursion(depth + 1u);
  }
  g_recursion_sink ^= block[(depth * 31u) & (kRecursiveFrameSize - 1u)];
}

__declspec(noinline) static void RunNativeRecursion(uint32_t depth) {
  volatile uint8_t block[kRecursiveFrameSize];
  block[0] = (uint8_t)depth;
  block[kRecursiveFrameSize - 1u] = (uint8_t)(depth >> 8u);
  if (InterlockedCompareExchange(&g_recurse, 1, 1) != 0) {
    RunNativeRecursion(depth + 1u);
  }
  g_recursion_sink ^= block[(depth * 31u) & (kRecursiveFrameSize - 1u)];
}

static LONG WINAPI ObserveException(EXCEPTION_POINTERS* exception) {
  ProbeObservation* observation = g_active_observation;
  EXCEPTION_RECORD* record;
  uintptr_t fault_address = 0u;
  if (observation == NULL || observation->thread_id != GetCurrentThreadId() ||
      exception == NULL || exception->ExceptionRecord == NULL) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  record = exception->ExceptionRecord;
  InterlockedIncrement(&observation->exception_count);
  if (record->NumberParameters >= 2u) {
    fault_address = (uintptr_t)record->ExceptionInformation[1];
  }
  if (record->ExceptionCode == kGuardPageException) {
    InterlockedIncrement(&observation->guard_exception_count);
  }
  if ((record->ExceptionCode == EXCEPTION_ACCESS_VIOLATION ||
       record->ExceptionCode == EXCEPTION_STACK_OVERFLOW) &&
      InterlockedCompareExchange(&observation->terminal_claimed, 1, 0) == 0) {
    observation->terminal_code = record->ExceptionCode;
    observation->terminal_access_type =
        record->NumberParameters >= 1u
            ? record->ExceptionInformation[0]
            : (ULONG_PTR)~(ULONG_PTR)0u;
    observation->terminal_fault_address = fault_address;
    if (exception->ContextRecord != NULL) {
      observation->terminal_rip = (uintptr_t)exception->ContextRecord->Rip;
      observation->terminal_rsp = (uintptr_t)exception->ContextRecord->Rsp;
    }
    observation->at_terminal = SnapshotRegion(observation->selected_page);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

static int FilterTerminalException(EXCEPTION_POINTERS* exception,
                                   ProbeObservation* observation) {
  EXCEPTION_RECORD* record;
  uintptr_t fault_address;
  if (exception == NULL || exception->ExceptionRecord == NULL) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  record = exception->ExceptionRecord;
  if (record->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
      record->NumberParameters < 2u) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  fault_address = (uintptr_t)record->ExceptionInformation[1];
  if (fault_address < observation->selected_page ||
      fault_address >= observation->selected_page + observation->page_size) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  observation->caught_code = record->ExceptionCode;
  observation->in_filter = SnapshotRegion(observation->selected_page);
  return EXCEPTION_EXECUTE_HANDLER;
}

__declspec(noinline) static void RunFaultingOperation(
    ProbeObservation* observation) {
  __try {
    if (observation->mode == kModeImplicit) {
      RunImplicitRecursion(0u);
    } else {
      RunNativeRecursion(0u);
    }
    observation->unexpected_return = 1;
  } __except (FilterTerminalException(GetExceptionInformation(), observation)) {
  }
}

static int InstallPageAboveGuard(ProbeObservation* observation) {
  uintptr_t selected;
  RegionSnapshot before;
  DWORD old_protect = 0u;
  if (observation->guard_after_pregrow == 0u ||
      observation->guard_after_pregrow_size == 0u) {
    observation->setup_error = ERROR_NOT_FOUND;
    return 0;
  }
  selected = observation->guard_after_pregrow +
             (uintptr_t)observation->guard_after_pregrow_size;
  before = SnapshotRegion(selected);
  if (!before.valid || before.allocation_base != observation->stack_low ||
      before.state != MEM_COMMIT || before.type != MEM_PRIVATE ||
      before.protect != PAGE_READWRITE || before.base > selected ||
      before.base + (uintptr_t)before.size < selected + observation->page_size) {
    observation->setup_error = ERROR_INVALID_DATA;
    return 0;
  }
  observation->selected_page = selected;
  observation->before_install = before;
  if (!VirtualProtect((void*)selected,
                      observation->page_size,
                      PAGE_NOACCESS,
                      &old_protect)) {
    observation->setup_error = GetLastError();
    return 0;
  }
  observation->original_protect = old_protect;
  observation->page_installed = 1;
  observation->after_install = SnapshotRegion(selected);
  if (old_protect != PAGE_READWRITE ||
      observation->after_install.protect != PAGE_NOACCESS) {
    observation->setup_error = ERROR_INVALID_DATA;
    return 0;
  }
  return 1;
}

static int RestorePage(ProbeObservation* observation) {
  DWORD old_protect = 0u;
  if (!observation->page_installed) {
    return 1;
  }
  if (!VirtualProtect((void*)observation->selected_page,
                      observation->page_size,
                      observation->original_protect,
                      &old_protect)) {
    observation->restore_error = GetLastError();
    return 0;
  }
  observation->after_restore = SnapshotRegion(observation->selected_page);
  return observation->after_restore.valid &&
         observation->after_restore.protect == observation->original_protect;
}

static unsigned __stdcall ProbeWorker(void* opaque) {
  ProbeObservation* observation = (ProbeObservation*)opaque;
  SYSTEM_INFO system_info;
  ULONG_PTR low = 0u;
  ULONG_PTR high = 0u;
  ULONG requested;
  size_t ignored = 0u;
  observation->thread_id = GetCurrentThreadId();
  GetSystemInfo(&system_info);
  observation->page_size = (size_t)system_info.dwPageSize;

  observation->process_private_before = MeasureProcessPrivateBytes();

  requested = 0u;
  if (!SetThreadStackGuarantee(&requested)) {
    observation->setup_error = GetLastError();
    return 2u;
  }
  observation->guarantee_before = requested;
  requested = (ULONG)(kRequestedGuaranteePages * observation->page_size);
  if (!SetThreadStackGuarantee(&requested)) {
    observation->setup_error = GetLastError();
    return 3u;
  }
  requested = 0u;
  if (!SetThreadStackGuarantee(&requested)) {
    observation->setup_error = GetLastError();
    return 4u;
  }
  observation->guarantee_after = requested;

  GetCurrentThreadStackLimits(&low, &high);
  observation->stack_low = (uintptr_t)low;
  observation->stack_high = (uintptr_t)high;
  observation->memory_prefix =
      MeasureMemoryPrefix(observation->stack_low,
                          observation->stack_high,
                          observation->page_size);
  observation->stack_commit_before =
      MeasureStackCommit(observation->stack_low, observation->stack_high);

  if (observation->target_policy == kTargetE9) {
    /* Match the product E9 low exclusion shape:
       terminal inaccessible prefix + rounded guarantee + one moving guard. */
    observation->pregrow_target =
        observation->stack_low + observation->memory_prefix +
        (uintptr_t)observation->guarantee_after + observation->page_size;
  } else {
    observation->pregrow_target =
        observation->stack_low + kPregrowLowReserveConservative;
  }

  if (observation->pregrow_target + 8u * observation->page_size >=
          observation->stack_high ||
      observation->pregrow_target <= observation->stack_low) {
    observation->setup_error = ERROR_INSUFFICIENT_BUFFER;
    return 5u;
  }
  if (!FindGuard(observation->stack_low,
                 observation->stack_high,
                 &observation->guard_before,
                 &observation->guard_before_protect,
                 &observation->guard_before_size)) {
    observation->setup_error = ERROR_INVALID_DATA;
    return 6u;
  }

  observation->pregrow_touch_count =
      Win32PregrowStack(observation->pregrow_target);
  observation->pregrow_minimum = observation->pregrow_target;
  observation->stack_commit_after_pregrow =
      MeasureStackCommit(observation->stack_low, observation->stack_high);
  observation->process_private_after_pregrow = MeasureProcessPrivateBytes();
  if (observation->pregrow_touch_count == 0u) {
    observation->setup_error = ERROR_INVALID_DATA;
    return 7u;
  }
  if (!FindGuard(observation->stack_low,
                 observation->stack_high,
                 &observation->guard_after_pregrow,
                 &observation->guard_after_pregrow_protect,
                 &observation->guard_after_pregrow_size) ||
      observation->guard_after_pregrow == 0u ||
      observation->guard_after_pregrow > observation->guard_before) {
    observation->setup_error = ERROR_INVALID_DATA;
    return 8u;
  }
  if (!InstallPageAboveGuard(observation)) {
    return 9u;
  }
  MemoryBarrier();
  observation->stack_commit_after_install =
      MeasureStackCommit(observation->stack_low, observation->stack_high);

  printf("ready mode=%s target_policy=%s stack_low=%p stack_high=%p "
         "memory_prefix=%zu target=%p minimum=%p touches=%lu "
         "guard_before=%p guard_before_size=%zu guard_after=%p "
         "guard_size=%zu selected=%p selected_offset=0x%zx "
         "commit_before=%zu commit_after_pregrow=%zu "
         "commit_after_install=%zu private_before=%zu "
         "private_after_pregrow=%zu\n",
         ModeName(observation->mode),
         TargetName(observation->target_policy),
         (void*)observation->stack_low,
         (void*)observation->stack_high,
         observation->memory_prefix,
         (void*)observation->pregrow_target,
         (void*)observation->pregrow_minimum,
         (unsigned long)observation->pregrow_touch_count,
         (void*)observation->guard_before,
         observation->guard_before_size,
         (void*)observation->guard_after_pregrow,
         observation->guard_after_pregrow_size,
         (void*)observation->selected_page,
         (size_t)(observation->selected_page - observation->stack_low),
         observation->stack_commit_before,
         observation->stack_commit_after_pregrow,
         observation->stack_commit_after_install,
         observation->process_private_before,
         observation->process_private_after_pregrow);
  fflush(stdout);

  if (observation->hold_after_install && observation->hold_event != NULL) {
    WaitForSingleObject(observation->hold_event, INFINITE);
  }

  if (!observation->skip_fault) {
    g_active_observation = observation;
    MemoryBarrier();
    RunFaultingOperation(observation);
    MemoryBarrier();
    g_active_observation = NULL;
  }

  FindGuard(observation->stack_low,
            observation->stack_high,
            &observation->guard_after_fault,
            &observation->guard_after_fault_protect,
            &observation->guard_after_fault_size);
  observation->restore_ok = RestorePage(observation);
  FindGuard(observation->stack_low,
            observation->stack_high,
            &observation->guard_after_restore,
            &observation->guard_after_restore_protect,
            &observation->guard_after_restore_size);
  observation->stack_commit_after_restore =
      MeasureStackCommit(observation->stack_low, observation->stack_high);
  observation->process_private_after_restore = MeasureProcessPrivateBytes();
  return 0u;
}

static const char* ProtectionName(DWORD protect) {
  switch (protect & 0xffu) {
    case PAGE_NOACCESS: return "PAGE_NOACCESS";
    case PAGE_READONLY: return "PAGE_READONLY";
    case PAGE_READWRITE: return "PAGE_READWRITE";
    case PAGE_EXECUTE: return "PAGE_EXECUTE";
    case PAGE_EXECUTE_READ: return "PAGE_EXECUTE_READ";
    case PAGE_EXECUTE_READWRITE: return "PAGE_EXECUTE_READWRITE";
    default: return "UNKNOWN";
  }
}

static void PrintRegion(const char* label, const RegionSnapshot* region) {
  printf("region label=%s valid=%d base=%p allocation_base=%p size=%zu "
         "state=0x%lx protect=0x%lx protect_name=%s type=0x%lx\n",
         label,
         region->valid,
         (void*)region->base,
         (void*)region->allocation_base,
         region->size,
         (unsigned long)region->state,
         (unsigned long)region->protect,
         ProtectionName(region->protect),
         (unsigned long)region->type);
}

static void PrintObservationSummary(const ProbeObservation* observation,
                                    DWORD worker_exit) {
  printf("pregrow mode=%s target_policy=%s stack_low=%p stack_high=%p "
         "stack_size=%zu memory_prefix=%zu target=%p minimum=%p touches=%lu "
         "guarantee_before=%lu guarantee_after=%lu\n",
         ModeName(observation->mode),
         TargetName(observation->target_policy),
         (void*)observation->stack_low,
         (void*)observation->stack_high,
         observation->stack_high - observation->stack_low,
         observation->memory_prefix,
         (void*)observation->pregrow_target,
         (void*)observation->pregrow_minimum,
         (unsigned long)observation->pregrow_touch_count,
         (unsigned long)observation->guarantee_before,
         (unsigned long)observation->guarantee_after);
  printf("guard before=%p before_protect=0x%lx before_size=%zu "
         "after_pregrow=%p after_pregrow_protect=0x%lx after_pregrow_size=%zu "
         "after_fault=%p after_fault_protect=0x%lx after_fault_size=%zu "
         "after_restore=%p after_restore_protect=0x%lx after_restore_size=%zu\n",
         (void*)observation->guard_before,
         (unsigned long)observation->guard_before_protect,
         observation->guard_before_size,
         (void*)observation->guard_after_pregrow,
         (unsigned long)observation->guard_after_pregrow_protect,
         observation->guard_after_pregrow_size,
         (void*)observation->guard_after_fault,
         (unsigned long)observation->guard_after_fault_protect,
         observation->guard_after_fault_size,
         (void*)observation->guard_after_restore,
         (unsigned long)observation->guard_after_restore_protect,
         observation->guard_after_restore_size);
  printf("commit stack_before=%zu stack_after_pregrow=%zu "
         "stack_after_install=%zu stack_after_restore=%zu "
         "private_before=%zu private_after_pregrow=%zu "
         "private_after_restore=%zu\n",
         observation->stack_commit_before,
         observation->stack_commit_after_pregrow,
         observation->stack_commit_after_install,
         observation->stack_commit_after_restore,
         observation->process_private_before,
         observation->process_private_after_pregrow,
         observation->process_private_after_restore);
  printf("terminal caught=0x%08lx observed=0x%08lx access_type=%llu "
         "rip=%p rsp=%p fault=%p fault_minus_page=%lld "
         "rsp_minus_page=%lld exceptions=%ld guard_exceptions=%ld "
         "unexpected_return=%d\n",
         (unsigned long)observation->caught_code,
         (unsigned long)observation->terminal_code,
         (unsigned long long)observation->terminal_access_type,
         (void*)observation->terminal_rip,
         (void*)observation->terminal_rsp,
         (void*)observation->terminal_fault_address,
         (long long)(observation->terminal_fault_address -
                     observation->selected_page),
         (long long)(observation->terminal_rsp - observation->selected_page),
         observation->exception_count,
         observation->guard_exception_count,
         observation->unexpected_return);
  PrintRegion("before_install", &observation->before_install);
  PrintRegion("after_install", &observation->after_install);
  PrintRegion("at_terminal", &observation->at_terminal);
  PrintRegion("in_filter", &observation->in_filter);
  PrintRegion("after_restore", &observation->after_restore);
  printf("recovery installed=%d restore_ok=%d setup_error=%lu "
         "restore_error=%lu worker_exit=%lu selected_offset=0x%zx\n",
         observation->page_installed,
         observation->restore_ok,
         (unsigned long)observation->setup_error,
         (unsigned long)observation->restore_error,
         (unsigned long)worker_exit,
         observation->selected_page == 0u
             ? 0u
             : (size_t)(observation->selected_page - observation->stack_low));
}

static int EvaluateImplicitSuccess(const ProbeObservation* observation,
                                   DWORD worker_exit) {
  if (worker_exit != 0u || !observation->page_installed ||
      observation->caught_code != EXCEPTION_ACCESS_VIOLATION ||
      observation->terminal_code != observation->caught_code ||
      observation->terminal_fault_address < observation->selected_page ||
      observation->terminal_fault_address >=
          observation->selected_page + observation->page_size ||
      observation->at_terminal.protect != PAGE_NOACCESS ||
      observation->in_filter.protect != PAGE_NOACCESS ||
      observation->guard_after_fault != observation->guard_after_pregrow ||
      observation->guard_exception_count != 0 ||
      observation->unexpected_return || !observation->restore_ok) {
    return 0;
  }
  if (observation->terminal_access_type != 0u) {
    return 0;
  }
  /* Exact Linux-shaped read: fault address should equal RSP - 8192. */
  if (observation->terminal_rsp < kArtOverflowReserve ||
      observation->terminal_fault_address !=
          observation->terminal_rsp - kArtOverflowReserve) {
    return 0;
  }
  if (observation->target_policy == kTargetE9) {
    const size_t selected_offset =
        (size_t)(observation->selected_page - observation->stack_low);
    const size_t expected_ceiling =
        observation->memory_prefix + (size_t)observation->guarantee_after +
        observation->guard_after_pregrow_size + 4u * observation->page_size;
    /* The ART page must sit immediately above the post-pregrow Windows guard
       and remain inside the low E9 exclusion neighborhood. Hosts that already
       keep the stack fully committed may place it even lower than the nominal
       usable_begin formula; that is still acceptable for this experiment. */
    if (observation->selected_page <
            observation->guard_after_pregrow +
                (uintptr_t)observation->guard_after_pregrow_size ||
        selected_offset > expected_ceiling) {
      return 0;
    }
  }
  return 1;
}

static int EvaluateAttachDetachSuccess(const ProbeObservation* observation,
                                       DWORD worker_exit) {
  if (worker_exit != 0u || !observation->page_installed ||
      !observation->restore_ok || observation->setup_error != 0u) {
    return 0;
  }
  if (observation->after_restore.protect != PAGE_READWRITE) {
    return 0;
  }
  /* Irreversibility checks: pregrowth commit and lowered guard remain. */
  if (observation->stack_commit_after_restore <
          observation->stack_commit_after_pregrow ||
      observation->guard_after_restore == 0u ||
      observation->guard_after_restore > observation->guard_before) {
    return 0;
  }
  return 1;
}

static int RunNativeCollisionParent(TargetPolicy policy) {
  char executable[MAX_PATH];
  char command_line[2u * MAX_PATH + 64u];
  STARTUPINFOA startup;
  PROCESS_INFORMATION process;
  DWORD child_exit = 0u;
  DWORD expected_exit;
  DWORD wait_result;
  DWORD length = GetModuleFileNameA(NULL, executable, MAX_PATH);
  memset(&startup, 0, sizeof(startup));
  memset(&process, 0, sizeof(process));
  startup.cb = sizeof(startup);
  if (length == 0u || length >= MAX_PATH ||
      snprintf(command_line,
               sizeof(command_line),
               policy == kTargetE9 ? "\"%s\" native-child e9"
                                   : "\"%s\" native-child",
               executable) < 0) {
    fprintf(stderr, "FAIL prepare native child error=%lu\n",
            (unsigned long)GetLastError());
    return 1;
  }
  if (!CreateProcessA(NULL,
                      command_line,
                      NULL,
                      NULL,
                      FALSE,
                      0u,
                      NULL,
                      NULL,
                      &startup,
                      &process)) {
    fprintf(stderr, "FAIL CreateProcess native child error=%lu\n",
            (unsigned long)GetLastError());
    return 1;
  }
  CloseHandle(process.hThread);
  wait_result = WaitForSingleObject(process.hProcess, 30000u);
  if (wait_result != WAIT_OBJECT_0 ||
      !GetExitCodeProcess(process.hProcess, &child_exit)) {
    fprintf(stderr, "FAIL wait native child result=%lu error=%lu\n",
            (unsigned long)wait_result,
            (unsigned long)GetLastError());
    CloseHandle(process.hProcess);
    return 1;
  }
  CloseHandle(process.hProcess);
  expected_exit =
      GetProcAddress(GetModuleHandleA("ntdll.dll"), "wine_get_version") != NULL
          ? 1u
          : EXCEPTION_ACCESS_VIOLATION;
  printf("native_collision target_policy=%s child_exit=0x%08lx expected=0x%08lx\n",
         TargetName(policy),
         (unsigned long)child_exit,
         (unsigned long)expected_exit);
  if (child_exit != expected_exit) {
    return 1;
  }
  puts("win32_stack_pregrow_probe mode=native expected_fatal_collision=1");
  puts("win32_stack_pregrow_probe OK");
  return 0;
}

static int RunOneWorker(ProbeMode mode,
                        TargetPolicy policy,
                        int skip_fault,
                        ProbeObservation* observation,
                        DWORD* worker_exit_out) {
  PVOID handler;
  unsigned int thread_id = 0u;
  uintptr_t raw_thread;
  HANDLE thread;
  DWORD worker_exit = 0u;
  int failures = 0;
  memset(observation, 0, sizeof(*observation));
  observation->mode = mode;
  observation->target_policy = policy;
  observation->skip_fault = skip_fault;
  handler = AddVectoredExceptionHandler(1u, ObserveException);
  if (handler == NULL) {
    fprintf(stderr, "FAIL AddVectoredExceptionHandler error=%lu\n",
            (unsigned long)GetLastError());
    return 1;
  }
  raw_thread = _beginthreadex(NULL,
                             kThreadStackSize,
                             ProbeWorker,
                             observation,
                             STACK_SIZE_PARAM_IS_A_RESERVATION,
                             &thread_id);
  if (raw_thread == 0u) {
    fprintf(stderr, "FAIL _beginthreadex error=%lu\n",
            (unsigned long)GetLastError());
    RemoveVectoredExceptionHandler(handler);
    return 1;
  }
  thread = (HANDLE)raw_thread;
  if (WaitForSingleObject(thread, 60000u) != WAIT_OBJECT_0 ||
      !GetExitCodeThread(thread, &worker_exit)) {
    fprintf(stderr, "FAIL worker wait/error=%lu\n",
            (unsigned long)GetLastError());
    failures++;
  }
  CloseHandle(thread);
  if (RemoveVectoredExceptionHandler(handler) == 0u) {
    fprintf(stderr, "FAIL RemoveVectoredExceptionHandler error=%lu\n",
            (unsigned long)GetLastError());
    failures++;
  }
  *worker_exit_out = worker_exit;
  return failures;
}

static int RunCommitScale(TargetPolicy policy, int thread_count) {
  ProbeObservation* observations;
  HANDLE* threads;
  unsigned int* thread_ids;
  HANDLE hold_event;
  size_t private_before;
  size_t private_peak;
  size_t private_after_release;
  size_t stack_commit_sum = 0u;
  int i;
  int failures = 0;
  int created = 0;
  DWORD start_tick;
  DWORD end_tick;
  observations =
      (ProbeObservation*)calloc((size_t)thread_count, sizeof(ProbeObservation));
  threads = (HANDLE*)calloc((size_t)thread_count, sizeof(HANDLE));
  thread_ids = (unsigned int*)calloc((size_t)thread_count, sizeof(unsigned int));
  hold_event = CreateEventA(NULL, TRUE, FALSE, NULL);
  if (observations == NULL || threads == NULL || thread_ids == NULL ||
      hold_event == NULL) {
    fprintf(stderr, "FAIL allocate commit-scale state\n");
    if (hold_event != NULL) {
      CloseHandle(hold_event);
    }
    free(observations);
    free(threads);
    free(thread_ids);
    return 1;
  }
  private_before = MeasureProcessPrivateBytes();
  start_tick = GetTickCount();
  for (i = 0; i < thread_count; ++i) {
    uintptr_t raw;
    observations[i].mode = kModeCommitScale;
    observations[i].target_policy = policy;
    observations[i].skip_fault = 1;
    observations[i].hold_after_install = 1;
    observations[i].hold_event = hold_event;
    raw = _beginthreadex(NULL,
                         kThreadStackSize,
                         ProbeWorker,
                         &observations[i],
                         STACK_SIZE_PARAM_IS_A_RESERVATION,
                         &thread_ids[i]);
    if (raw == 0u) {
      fprintf(stderr, "FAIL beginthreadex scale index=%d error=%lu\n",
              i, (unsigned long)GetLastError());
      failures++;
      break;
    }
    threads[i] = (HANDLE)raw;
    created++;
  }
  /* Wait until every created worker has installed its page or failed setup. */
  for (;;) {
    int ready = 0;
    MemoryBarrier();
    for (i = 0; i < created; ++i) {
      if (observations[i].page_installed || observations[i].setup_error != 0u) {
        ready++;
      }
    }
    if (ready >= created) {
      break;
    }
    Sleep(1);
    if (GetTickCount() - start_tick > 120000u) {
      fprintf(stderr, "FAIL commit-scale ready timeout created=%d ready=%d\n",
              created, ready);
      failures++;
      break;
    }
  }
  private_peak = MeasureProcessPrivateBytes();
  for (i = 0; i < created; ++i) {
    stack_commit_sum += observations[i].stack_commit_after_install;
  }
  SetEvent(hold_event);
  for (i = 0; i < created; ++i) {
    DWORD worker_exit = 0u;
    if (threads[i] == NULL) {
      continue;
    }
    if (WaitForSingleObject(threads[i], 120000u) != WAIT_OBJECT_0 ||
        !GetExitCodeThread(threads[i], &worker_exit)) {
      failures++;
    } else if (worker_exit != 0u || !observations[i].page_installed ||
               !observations[i].restore_ok) {
      failures++;
    }
    CloseHandle(threads[i]);
  }
  end_tick = GetTickCount();
  private_after_release = MeasureProcessPrivateBytes();
  printf("commit_scale target_policy=%s threads=%d created=%d elapsed_ms=%lu "
         "private_before=%zu private_peak=%zu private_after_release=%zu "
         "private_peak_delta=%lld stack_commit_sum=%zu failures=%d\n",
         TargetName(policy),
         thread_count,
         created,
         (unsigned long)(end_tick - start_tick),
         private_before,
         private_peak,
         private_after_release,
         (long long)private_peak - (long long)private_before,
         stack_commit_sum,
         failures);
  for (i = 0; i < created && i < 8; ++i) {
    printf("commit_scale_sample index=%d selected_offset=0x%zx "
           "commit_after_pregrow=%zu commit_after_restore=%zu "
           "guard_after_restore=%p setup_error=%lu\n",
           i,
           observations[i].selected_page == 0u
               ? 0u
               : (size_t)(observations[i].selected_page -
                          observations[i].stack_low),
           observations[i].stack_commit_after_pregrow,
           observations[i].stack_commit_after_restore,
           (void*)observations[i].guard_after_restore,
           (unsigned long)observations[i].setup_error);
  }
  CloseHandle(hold_event);
  free(observations);
  free(threads);
  free(thread_ids);
  if (failures != 0 || created != thread_count) {
    return 1;
  }
  puts("win32_stack_pregrow_probe mode=commit-scale OK");
  return 0;
}

int main(int argc, char** argv) {
  ProbeMode mode;
  TargetPolicy policy;
  int thread_count = 1;
  int is_native_child = 0;
  ProbeObservation observation;
  DWORD worker_exit = 0u;
  int failures = 0;
  setvbuf(stdout, NULL, _IONBF, 0u);
  if (!ParseArgs(argc, argv, &mode, &policy, &thread_count, &is_native_child)) {
    fprintf(stderr,
            "usage: win32_stack_pregrow_probe.exe "
            "<implicit|native|attach-detach|commit-scale> "
            "[e9|conservative] [--threads=N]\n");
    return 2;
  }
  if (mode == kModeNative && !is_native_child) {
    return RunNativeCollisionParent(policy);
  }
  if (mode == kModeCommitScale) {
    return RunCommitScale(policy, thread_count);
  }
  if (is_native_child) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  }
  failures += RunOneWorker(mode == kModeAttachDetach ? kModeAttachDetach : mode,
                           policy,
                           mode == kModeAttachDetach ? 1 : 0,
                           &observation,
                           &worker_exit);
  /* For attach-detach we reuse the worker path with skip_fault. */
  if (mode == kModeAttachDetach) {
    observation.mode = kModeAttachDetach;
  }
  PrintObservationSummary(&observation, worker_exit);
  if (mode == kModeAttachDetach) {
    if (!EvaluateAttachDetachSuccess(&observation, worker_exit)) {
      failures++;
    }
  } else if (mode == kModeImplicit) {
    if (!EvaluateImplicitSuccess(&observation, worker_exit)) {
      failures++;
    }
  } else if (mode == kModeNative) {
    /* native-child is expected to die before returning here on real Windows. */
    failures++;
  }
  printf("win32_stack_pregrow_probe mode=%s target_policy=%s failures=%d\n",
         ModeName(mode), TargetName(policy), failures);
  if (failures != 0) {
    return 1;
  }
  puts("win32_stack_pregrow_probe OK");
  return 0;
}
