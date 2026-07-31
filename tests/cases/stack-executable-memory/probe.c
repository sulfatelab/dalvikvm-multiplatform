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

#include <malloc.h>
#include <process.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>

enum {
  kThreadStackSize = 2u * 1024u * 1024u,
  kFrameSize = 8192u,
  kMarkerSize = 64u,
};

static const DWORD kGuardPageException = 0x80000001u;

typedef struct RegionSnapshot {
  uintptr_t base;
  uintptr_t allocation_base;
  size_t size;
  DWORD state;
  DWORD protect;
  DWORD type;
  int valid;
} RegionSnapshot;

typedef struct MarkerSnapshot {
  size_t matching_bytes;
  size_t first_mismatch;
  uint64_t checksum;
  int readable;
} MarkerSnapshot;

typedef struct ProbeObservation {
  DWORD thread_id;
  uintptr_t stack_low;
  uintptr_t stack_high;
  uintptr_t selected_page;
  size_t page_size;
  size_t excluded_low_size;
  DWORD original_state;
  DWORD original_protect;
  DWORD original_type;
  void* original_bytes;
  uintptr_t guard_before;
  DWORD guard_before_protect;
  uintptr_t guard_after;
  DWORD guard_after_protect;
  RegionSnapshot before_rx;
  RegionSnapshot terminal_page;
  RegionSnapshot caught_page;
  RegionSnapshot after_reset_page;
  RegionSnapshot after_restore_page;
  MarkerSnapshot marker_before;
  MarkerSnapshot marker_terminal;
  MarkerSnapshot marker_caught;
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
  int reset_attempted;
  int reset_ok;
  int restore_ok;
  int unexpected_return;
} ProbeObservation;

static ProbeObservation* g_active_observation;
static volatile LONG g_recurse = 1;
static volatile uint8_t g_recursion_sink;

static uint8_t PatternByte(size_t offset) {
  return (uint8_t)(((offset * 131u) + 0x5au) ^ (offset >> 3u));
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

static int IsReadable(const RegionSnapshot* region) {
  DWORD base;
  if (!region->valid || region->state != MEM_COMMIT ||
      (region->protect & (PAGE_GUARD | PAGE_NOACCESS)) != 0u) {
    return 0;
  }
  base = region->protect & 0xffu;
  return base == PAGE_READONLY || base == PAGE_READWRITE ||
         base == PAGE_WRITECOPY || base == PAGE_EXECUTE_READ ||
         base == PAGE_EXECUTE_READWRITE || base == PAGE_EXECUTE_WRITECOPY;
}

static MarkerSnapshot CaptureMarker(uintptr_t address,
                                    const RegionSnapshot* region) {
  MarkerSnapshot result;
  const volatile uint8_t* bytes = (const volatile uint8_t*)address;
  size_t i;
  memset(&result, 0, sizeof(result));
  result.first_mismatch = kMarkerSize;
  if (!IsReadable(region)) {
    return result;
  }
  result.readable = 1;
  result.checksum = UINT64_C(1469598103934665603);
  for (i = 0u; i < kMarkerSize; ++i) {
    const uint8_t actual = bytes[i];
    if (actual == PatternByte(i)) {
      ++result.matching_bytes;
    } else if (result.first_mismatch == kMarkerSize) {
      result.first_mismatch = i;
    }
    result.checksum ^= actual;
    result.checksum *= UINT64_C(1099511628211);
  }
  return result;
}

static int FindGuard(uintptr_t low,
                     uintptr_t high,
                     uintptr_t* address,
                     DWORD* protect) {
  uintptr_t cursor = low;
  while (cursor < high) {
    MEMORY_BASIC_INFORMATION memory;
    uintptr_t base;
    uintptr_t next;
    memset(&memory, 0, sizeof(memory));
    if (VirtualQuery((const void*)cursor, &memory, sizeof(memory)) == 0u) {
      return 0;
    }
    base = (uintptr_t)memory.BaseAddress;
    if ((memory.Protect & PAGE_GUARD) != 0u) {
      *address = base;
      *protect = memory.Protect;
      return 1;
    }
    next = base + (uintptr_t)memory.RegionSize;
    if (next <= cursor || next > high) {
      return 0;
    }
    cursor = next;
  }
  *address = 0u;
  *protect = 0u;
  return 1;
}

// Match the historical ART diagnostic selector without depending on ART.
// Preserve the terminal page and adjacent no-access/guard prefix, then choose
// the first reserved or ordinary committed read/write page above it.
static int SelectPage(ProbeObservation* observation) {
  uintptr_t candidate = observation->stack_low + observation->page_size;
  while (candidate < observation->stack_high) {
    MEMORY_BASIC_INFORMATION memory;
    uintptr_t base;
    uintptr_t end;
    DWORD base_protect;
    int preserve;
    memset(&memory, 0, sizeof(memory));
    if (VirtualQuery((const void*)candidate, &memory, sizeof(memory)) == 0u) {
      observation->setup_error = GetLastError();
      return 0;
    }
    base = (uintptr_t)memory.BaseAddress;
    end = base + (uintptr_t)memory.RegionSize;
    if ((uintptr_t)memory.AllocationBase != observation->stack_low ||
        base > candidate || end <= candidate || end > observation->stack_high) {
      observation->setup_error = ERROR_INVALID_ADDRESS;
      return 0;
    }
    base_protect = memory.Protect & 0xffu;
    preserve = memory.State == MEM_COMMIT &&
               (base_protect == PAGE_NOACCESS ||
                (memory.Protect & PAGE_GUARD) != 0u);
    if (preserve) {
      candidate = end;
      continue;
    }
    if (candidate + observation->page_size + 3u * observation->page_size >
        observation->stack_high) {
      observation->setup_error = ERROR_INSUFFICIENT_BUFFER;
      return 0;
    }
    if (memory.State != MEM_RESERVE &&
        !(memory.State == MEM_COMMIT && memory.Type == MEM_PRIVATE &&
          memory.Protect == PAGE_READWRITE)) {
      observation->setup_error = ERROR_INVALID_DATA;
      return 0;
    }
    observation->selected_page = candidate;
    observation->excluded_low_size = (size_t)(candidate - observation->stack_low);
    observation->original_state = memory.State;
    observation->original_protect = memory.Protect;
    observation->original_type = memory.Type;
    return 1;
  }
  observation->setup_error = ERROR_NOT_FOUND;
  return 0;
}

static int InstallDirtyRxPage(ProbeObservation* observation) {
  uint8_t* page;
  size_t i;
  DWORD old_protect;
  if (!SelectPage(observation)) {
    return 0;
  }
  page = (uint8_t*)observation->selected_page;
  if (observation->original_state == MEM_RESERVE) {
    if (VirtualAlloc(page,
                     observation->page_size,
                     MEM_COMMIT,
                     PAGE_READWRITE) != page) {
      observation->setup_error = GetLastError();
      return 0;
    }
  } else {
    observation->original_bytes =
        HeapAlloc(GetProcessHeap(), 0u, observation->page_size);
    if (observation->original_bytes == NULL) {
      observation->setup_error = ERROR_OUTOFMEMORY;
      return 0;
    }
    memcpy(observation->original_bytes, page, observation->page_size);
  }
  for (i = 0u; i < observation->page_size; ++i) {
    page[i] = PatternByte(i);
  }
  if (!FlushInstructionCache(GetCurrentProcess(), page, observation->page_size) ||
      !VirtualProtect(page,
                      observation->page_size,
                      PAGE_EXECUTE_READ,
                      &old_protect)) {
    observation->setup_error = GetLastError();
    return 0;
  }
  observation->page_installed = 1;
  observation->before_rx = SnapshotRegion(observation->selected_page);
  observation->marker_before =
      CaptureMarker(observation->selected_page, &observation->before_rx);
  if (observation->before_rx.state != MEM_COMMIT ||
      observation->before_rx.protect != PAGE_EXECUTE_READ ||
      observation->marker_before.matching_bytes != kMarkerSize) {
    observation->setup_error = ERROR_INVALID_DATA;
    return 0;
  }
  return 1;
}

static int RestorePage(ProbeObservation* observation) {
  RegionSnapshot current = SnapshotRegion(observation->selected_page);
  DWORD ignored;
  if (!current.valid) {
    observation->restore_error = ERROR_INVALID_ADDRESS;
    return 0;
  }
  if (observation->original_state == MEM_RESERVE) {
    if (current.state == MEM_COMMIT &&
        !VirtualFree((void*)observation->selected_page,
                     observation->page_size,
                     MEM_DECOMMIT)) {
      observation->restore_error = GetLastError();
      return 0;
    }
  } else {
    if (current.state != MEM_COMMIT ||
        !VirtualProtect((void*)observation->selected_page,
                        observation->page_size,
                        PAGE_READWRITE,
                        &ignored)) {
      observation->restore_error = GetLastError();
      return 0;
    }
    memcpy((void*)observation->selected_page,
           observation->original_bytes,
           observation->page_size);
    if (!VirtualProtect((void*)observation->selected_page,
                        observation->page_size,
                        observation->original_protect,
                        &ignored)) {
      observation->restore_error = GetLastError();
      return 0;
    }
  }
  observation->after_restore_page = SnapshotRegion(observation->selected_page);
  return 1;
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
    observation->terminal_page = SnapshotRegion(observation->selected_page);
    observation->marker_terminal = CaptureMarker(
        observation->selected_page, &observation->terminal_page);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

static int CatchTerminalException(DWORD code) {
  return code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_STACK_OVERFLOW
             ? EXCEPTION_EXECUTE_HANDLER
             : EXCEPTION_CONTINUE_SEARCH;
}

__declspec(noinline) static void ConsumeStack(uint32_t depth) {
  volatile uint8_t block[kFrameSize];
  block[0] = (uint8_t)depth;
  block[kFrameSize / 2u] = (uint8_t)(depth >> 8u);
  if (InterlockedCompareExchange(&g_recurse, 1, 1) != 0) {
    ConsumeStack(depth + 1u);
  }
  g_recursion_sink ^= block[(depth * 97u) & (kFrameSize / 2u - 1u)];
}

__declspec(noinline) static void RunRecursion(ProbeObservation* observation) {
  __try {
    ConsumeStack(0u);
    observation->unexpected_return = 1;
  } __except (CatchTerminalException(GetExceptionCode())) {
    observation->caught_code = GetExceptionCode();
    observation->caught_page = SnapshotRegion(observation->selected_page);
    observation->marker_caught =
        CaptureMarker(observation->selected_page, &observation->caught_page);
  }
}

static unsigned __stdcall ProbeWorker(void* opaque) {
  ProbeObservation* observation = (ProbeObservation*)opaque;
  SYSTEM_INFO system_info;
  ULONG_PTR low = 0u;
  ULONG_PTR high = 0u;
  observation->thread_id = GetCurrentThreadId();
  GetCurrentThreadStackLimits(&low, &high);
  observation->stack_low = (uintptr_t)low;
  observation->stack_high = (uintptr_t)high;
  GetSystemInfo(&system_info);
  observation->page_size = (size_t)system_info.dwPageSize;
  if (!FindGuard(observation->stack_low,
                 observation->stack_high,
                 &observation->guard_before,
                 &observation->guard_before_protect) ||
      !InstallDirtyRxPage(observation)) {
    return 2u;
  }

  g_active_observation = observation;
  MemoryBarrier();
  RunRecursion(observation);
  MemoryBarrier();
  g_active_observation = NULL;

  if (observation->caught_code == EXCEPTION_STACK_OVERFLOW) {
    observation->reset_attempted = 1;
    observation->reset_ok = _resetstkoflw() != 0;
  }
  observation->after_reset_page = SnapshotRegion(observation->selected_page);
  FindGuard(observation->stack_low,
            observation->stack_high,
            &observation->guard_after,
            &observation->guard_after_protect);
  observation->restore_ok = RestorePage(observation);
  if (observation->original_bytes != NULL) {
    HeapFree(GetProcessHeap(), 0u, observation->original_bytes);
    observation->original_bytes = NULL;
  }
  return 0u;
}

static const char* ProtectionName(DWORD protect) {
  switch (protect & 0xffu) {
    case PAGE_NOACCESS: return "PAGE_NOACCESS";
    case PAGE_READONLY: return "PAGE_READONLY";
    case PAGE_READWRITE: return "PAGE_READWRITE";
    case PAGE_WRITECOPY: return "PAGE_WRITECOPY";
    case PAGE_EXECUTE: return "PAGE_EXECUTE";
    case PAGE_EXECUTE_READ: return "PAGE_EXECUTE_READ";
    case PAGE_EXECUTE_READWRITE: return "PAGE_EXECUTE_READWRITE";
    case PAGE_EXECUTE_WRITECOPY: return "PAGE_EXECUTE_WRITECOPY";
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

static void PrintMarker(const char* label, const MarkerSnapshot* marker) {
  printf("marker label=%s readable=%d matching=%zu/%u first_mismatch=%zu "
         "checksum=0x%016llx\n",
         label,
         marker->readable,
         marker->matching_bytes,
         (unsigned)kMarkerSize,
         marker->first_mismatch,
         (unsigned long long)marker->checksum);
}

int main(void) {
  ProbeObservation observation;
  PVOID handler;
  unsigned int thread_id = 0u;
  uintptr_t raw_thread;
  HANDLE thread;
  DWORD worker_exit = 0u;
  int failures = 0;
  memset(&observation, 0, sizeof(observation));
  handler = AddVectoredExceptionHandler(1u, ObserveException);
  if (handler == NULL) {
    fprintf(stderr, "FAIL AddVectoredExceptionHandler error=%lu\n",
            (unsigned long)GetLastError());
    return 1;
  }
  raw_thread = _beginthreadex(NULL,
                             kThreadStackSize,
                             ProbeWorker,
                             &observation,
                             STACK_SIZE_PARAM_IS_A_RESERVATION,
                             &thread_id);
  if (raw_thread == 0u) {
    fprintf(stderr, "FAIL _beginthreadex error=%lu\n",
            (unsigned long)GetLastError());
    RemoveVectoredExceptionHandler(handler);
    return 1;
  }
  thread = (HANDLE)raw_thread;
  if (WaitForSingleObject(thread, 30000u) != WAIT_OBJECT_0 ||
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

  printf("dirty_rx_stack stack_low=%p stack_high=%p stack_size=%zu "
         "selected=%p page_size=%zu excluded_low=%zu original_state=0x%lx "
         "original_protect=0x%lx original_type=0x%lx\n",
         (void*)observation.stack_low,
         (void*)observation.stack_high,
         observation.stack_high - observation.stack_low,
         (void*)observation.selected_page,
         observation.page_size,
         observation.excluded_low_size,
         (unsigned long)observation.original_state,
         (unsigned long)observation.original_protect,
         (unsigned long)observation.original_type);
  printf("guard before=%p before_protect=0x%lx after=%p after_protect=0x%lx "
         "exceptions=%ld guard_exceptions=%ld\n",
         (void*)observation.guard_before,
         (unsigned long)observation.guard_before_protect,
         (void*)observation.guard_after,
         (unsigned long)observation.guard_after_protect,
         observation.exception_count,
         observation.guard_exception_count);
  printf("terminal caught=0x%08lx observed=0x%08lx access_type=%llu "
         "rip=%p rsp=%p fault=%p fault_minus_page=%lld rsp_minus_page=%lld "
         "unexpected_return=%d\n",
         (unsigned long)observation.caught_code,
         (unsigned long)observation.terminal_code,
         (unsigned long long)observation.terminal_access_type,
         (void*)observation.terminal_rip,
         (void*)observation.terminal_rsp,
         (void*)observation.terminal_fault_address,
         (long long)(observation.terminal_fault_address - observation.selected_page),
         (long long)(observation.terminal_rsp - observation.selected_page),
         observation.unexpected_return);
  PrintRegion("before_rx", &observation.before_rx);
  PrintMarker("before_rx", &observation.marker_before);
  PrintRegion("at_terminal", &observation.terminal_page);
  PrintMarker("at_terminal", &observation.marker_terminal);
  PrintRegion("in_handler", &observation.caught_page);
  PrintMarker("in_handler", &observation.marker_caught);
  PrintRegion("after_reset", &observation.after_reset_page);
  PrintRegion("after_restore", &observation.after_restore_page);
  printf("recovery reset_attempted=%d reset_ok=%d restore_ok=%d "
         "setup_error=%lu restore_error=%lu worker_exit=%lu\n",
         observation.reset_attempted,
         observation.reset_ok,
         observation.restore_ok,
         (unsigned long)observation.setup_error,
         (unsigned long)observation.restore_error,
         (unsigned long)worker_exit);

  if (worker_exit != 0u || !observation.page_installed ||
      observation.caught_code == 0u ||
      observation.caught_code != observation.terminal_code ||
      observation.unexpected_return || !observation.restore_ok ||
      (observation.caught_code == EXCEPTION_STACK_OVERFLOW &&
       !observation.reset_ok)) {
    failures++;
  }
  printf("win32_stack_growth_rx_probe failures=%d\n", failures);
  if (failures != 0) {
    return 1;
  }
  puts("win32_stack_growth_rx_probe OK");
  return 0;
}
