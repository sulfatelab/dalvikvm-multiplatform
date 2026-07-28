#include <pthread.h>
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <iterator>

#include "stack_windows.h"

namespace {

using art::Win32MemoryRegion;
using art::Win32StackLayout;
using art::Win32StackPageRecord;
using art::Win32StackPageSelection;
using art::Win32StackPageState;

constexpr int kRestoreIterations = 64;
constexpr int kReservedRestoreIterations = 64;

struct FakeLayout {
  const Win32MemoryRegion* regions;
  size_t count;
};

volatile LONG g_failures;
volatile LONG g_expected_faults;
volatile uintptr_t g_expected_page;

extern "C" uint8_t Win32StackPageFaultRead(const volatile uint8_t* page);
extern "C" char Win32StackPageFaultInstruction;
extern "C" char Win32StackPageFaultResume;

void Fail(const char* test, const char* detail) {
  std::fprintf(stderr,
               "FAIL %s: %s (winerr=%lu)\n",
               test,
               detail,
               GetLastError());
  InterlockedIncrement(&g_failures);
}

bool FakeQuery(uintptr_t address, Win32MemoryRegion* region, void* context) {
  FakeLayout* layout = static_cast<FakeLayout*>(context);
  for (size_t i = 0; i < layout->count; ++i) {
    const Win32MemoryRegion& candidate = layout->regions[i];
    const uintptr_t end = candidate.base_address + candidate.region_size;
    if (address >= candidate.base_address && address < end) {
      *region = candidate;
      return true;
    }
  }
  return false;
}

bool SelectFake(const Win32MemoryRegion* regions,
                size_t count,
                uintptr_t low,
                uintptr_t high,
                size_t page_size,
                size_t protected_size,
                size_t minimum_above,
                Win32StackPageSelection* selection) {
  FakeLayout layout{regions, count};
  const char* failure = nullptr;
  return art::SelectWin32StackPage(low,
                                   high,
                                   page_size,
                                   protected_size,
                                   minimum_above,
                                   FakeQuery,
                                   &layout,
                                   selection,
                                   &failure);
}

bool InspectFake(const Win32MemoryRegion* regions,
                 size_t count,
                 uintptr_t low,
                 uintptr_t high,
                 size_t page_size,
                 size_t minimum_usable_size,
                 Win32StackLayout* layout) {
  FakeLayout fake_layout{regions, count};
  const char* failure = nullptr;
  return art::InspectWin32StackLayout(low,
                                      high,
                                      page_size,
                                      minimum_usable_size,
                                      FakeQuery,
                                      &fake_layout,
                                      layout,
                                      &failure);
}

void CheckDeterministicSelection() {
  constexpr uintptr_t low = 0x100000u;
  constexpr size_t page = 4096u;
  constexpr uintptr_t high = low + 1024u * 1024u;
  constexpr size_t minimum_above = 3u * page;
  Win32StackPageSelection selection;

  const Win32MemoryRegion reserved[] = {
      {low, low, high - low, MEM_RESERVE, 0u, 0u},
  };
  if (!SelectFake(reserved,
                  std::size(reserved),
                  low,
                  high,
                  page,
                  page,
                  minimum_above,
                  &selection) ||
      selection.page_begin != low + page || selection.excluded_low_size != page ||
      selection.original_state != MEM_RESERVE) {
    Fail("selection-reserved", "did not choose the first reserved page above the bottom page");
  }

  const Win32MemoryRegion guarded[] = {
      {low, low, page, MEM_COMMIT, PAGE_NOACCESS, MEM_PRIVATE},
      {low + page, low, page, MEM_COMMIT, PAGE_READWRITE | PAGE_GUARD, MEM_PRIVATE},
      {low + 2u * page, low, high - low - 2u * page,
       MEM_COMMIT, PAGE_READWRITE, MEM_PRIVATE},
  };
  if (!SelectFake(guarded,
                  std::size(guarded),
                  low,
                  high,
                  page,
                  page,
                  minimum_above,
                  &selection) ||
      selection.page_begin != low + 2u * page ||
      selection.excluded_low_size != 2u * page ||
      selection.original_protect != PAGE_READWRITE) {
    Fail("selection-guarded", "did not preserve adjacent no-access/guard regions");
  }

  const Win32MemoryRegion combined_noaccess[] = {
      {low, low, 2u * page, MEM_COMMIT, PAGE_NOACCESS, MEM_PRIVATE},
      {low + 2u * page, low, high - low - 2u * page,
       MEM_COMMIT, PAGE_READWRITE, MEM_PRIVATE},
  };
  if (!SelectFake(combined_noaccess,
                  std::size(combined_noaccess),
                  low,
                  high,
                  page,
                  page,
                  minimum_above,
                  &selection) ||
      selection.page_begin != low + 2u * page) {
    Fail("selection-combined", "did not preserve a multi-page bottom no-access region");
  }

  const Win32MemoryRegion read_only[] = {
      {low, low, page, MEM_COMMIT, PAGE_READWRITE, MEM_PRIVATE},
      {low + page, low, high - low - page, MEM_COMMIT, PAGE_READONLY, MEM_PRIVATE},
  };
  if (SelectFake(read_only,
                 std::size(read_only),
                 low,
                 high,
                 page,
                 page,
                 minimum_above,
                 &selection)) {
    Fail("selection-readonly", "accepted a read-only candidate");
  }

  const Win32MemoryRegion mapped[] = {
      {low, low, high - low, MEM_COMMIT, PAGE_READWRITE, MEM_MAPPED},
  };
  if (SelectFake(mapped,
                 std::size(mapped),
                 low,
                 high,
                 page,
                 page,
                 minimum_above,
                 &selection)) {
    Fail("selection-mapped", "accepted a mapped rather than private candidate");
  }

  if (SelectFake(reserved,
                 std::size(reserved),
                 low,
                 low + 4u * page,
                 page,
                 page,
                 minimum_above,
                 &selection)) {
    Fail("selection-small", "accepted a layout without minimum normal stack space");
  }
  if (SelectFake(reserved,
                 std::size(reserved),
                 low,
                 high,
                 page,
                 2u * page,
                 minimum_above,
                 &selection)) {
    Fail("selection-size", "accepted a protected size larger than one system page");
  }

  const Win32MemoryRegion wrong_allocation[] = {
      {low, low + page, high - low, MEM_RESERVE, 0u, 0u},
  };
  if (SelectFake(wrong_allocation,
                 std::size(wrong_allocation),
                 low,
                 high,
                 page,
                 page,
                 minimum_above,
                 &selection)) {
    Fail("selection-allocation", "accepted a candidate from another allocation");
  }

  std::puts("selection_cases count=8");
}

void CheckReadOnlyLayoutInspection() {
  constexpr uintptr_t low = 0x200000u;
  constexpr size_t page = 4096u;
  constexpr uintptr_t high = low + 1024u * 1024u;
  constexpr size_t minimum_usable = 3u * page;
  Win32StackLayout layout;

  const Win32MemoryRegion reserved[] = {
      {low, low, high - low, MEM_RESERVE, 0u, 0u},
  };
  if (!InspectFake(reserved,
                   std::size(reserved),
                   low,
                   high,
                   page,
                   minimum_usable,
                   &layout) ||
      layout.allocation_base != low || layout.usable_begin != low + page ||
      layout.excluded_low_size != page) {
    Fail("layout-reserved", "did not exclude exactly the terminal bottom page");
  }

  const Win32MemoryRegion guarded[] = {
      {low, low, page, MEM_COMMIT, PAGE_NOACCESS, MEM_PRIVATE},
      {low + page, low, page, MEM_COMMIT, PAGE_READWRITE | PAGE_GUARD, MEM_PRIVATE},
      {low + 2u * page, low, high - low - 2u * page,
       MEM_COMMIT, PAGE_READWRITE, MEM_PRIVATE},
  };
  if (!InspectFake(guarded,
                   std::size(guarded),
                   low,
                   high,
                   page,
                   minimum_usable,
                   &layout) ||
      layout.usable_begin != low + 2u * page || layout.excluded_low_size != 2u * page) {
    Fail("layout-guarded", "did not exclude the complete bottom guard prefix");
  }

  if (InspectFake(reserved,
                  std::size(reserved),
                  low,
                  low + 3u * page,
                  page,
                  minimum_usable,
                  &layout)) {
    Fail("layout-small", "accepted a layout without the requested usable stack");
  }
  std::puts("layout_cases count=3");
}

LONG WINAPI PageFaultHandler(EXCEPTION_POINTERS* exception) {
  if (exception == nullptr || exception->ExceptionRecord == nullptr ||
      exception->ContextRecord == nullptr) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  EXCEPTION_RECORD* record = exception->ExceptionRecord;
  CONTEXT* context = exception->ContextRecord;
  if (record->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
      record->NumberParameters < 2u || record->ExceptionInformation[0] != 0u ||
      record->ExceptionInformation[1] != g_expected_page ||
      reinterpret_cast<uintptr_t>(record->ExceptionAddress) !=
          reinterpret_cast<uintptr_t>(&Win32StackPageFaultInstruction) ||
      context->Rip != reinterpret_cast<DWORD64>(&Win32StackPageFaultInstruction)) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  context->Rax = 0u;
  context->Rip = reinterpret_cast<DWORD64>(&Win32StackPageFaultResume);
  InterlockedIncrement(&g_expected_faults);
  return EXCEPTION_CONTINUE_EXECUTION;
}

bool AccessFaults(volatile uint8_t* page) {
  const LONG before = g_expected_faults;
  g_expected_page = reinterpret_cast<uintptr_t>(page);
  const uint8_t value = Win32StackPageFaultRead(page);
  g_expected_page = 0u;
  return value == 0u && g_expected_faults == before + 1;
}

bool CheckActualPage(const char* label, int iterations) {
  pthread_attr_t attr;
  pthread_t self = pthread_self();
  if (self == nullptr || pthread_getattr_np(self, &attr) != 0) {
    Fail(label, "could not discover current stack bounds");
    return false;
  }
  void* stack_base = nullptr;
  size_t stack_size = 0u;
  if (pthread_attr_getstack(&attr, &stack_base, &stack_size) != 0) {
    Fail(label, "could not read current stack bounds");
    return false;
  }
  pthread_attr_destroy(&attr);

  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);
  const size_t page_size = static_cast<size_t>(system_info.dwPageSize);
  const uintptr_t low = reinterpret_cast<uintptr_t>(stack_base);
  const uintptr_t high = low + stack_size;
  const size_t minimum_above = 3u * page_size;

  size_t first_excluded = 0u;
  uint32_t first_original_state = 0u;
  uint32_t first_original_protect = 0u;
  for (int i = 0; i < iterations; ++i) {
    Win32StackPageRecord record;
    const char* failure = nullptr;
    uint32_t win32_error = 0u;
    if (!art::InstallWin32StackPage(low,
                                    high,
                                    page_size,
                                    page_size,
                                    minimum_above,
                                    &record,
                                    &failure,
                                    &win32_error)) {
      Fail(label, failure != nullptr ? failure : "page installation failed");
      return false;
    }
    Win32StackPageSelection saved = record.selection;
    if (i == 0) {
      first_excluded = saved.excluded_low_size;
      first_original_state = saved.original_state;
      first_original_protect = saved.original_protect;
    }
    volatile uint8_t* page = reinterpret_cast<volatile uint8_t*>(saved.page_begin);
    if (record.state != Win32StackPageState::kProtected || !AccessFaults(page)) {
      Fail(label, "installed page did not fault as PAGE_NOACCESS");
    }
    if (!art::UnprotectWin32StackPage(&record, &failure, &win32_error)) {
      Fail(label, failure != nullptr ? failure : "page unprotect failed");
      return false;
    }
    const uint8_t original = *page;
    *page = static_cast<uint8_t>(original ^ 0x5au);
    if (*page != static_cast<uint8_t>(original ^ 0x5au)) {
      Fail(label, "writable page did not retain a test byte");
    }
    *page = original;
    if (!art::ProtectWin32StackPage(&record, &failure, &win32_error) || !AccessFaults(page)) {
      Fail(label, failure != nullptr ? failure : "page reprotect failed");
      return false;
    }
    if (!art::RestoreWin32StackPage(&record, &failure, &win32_error)) {
      Fail(label, failure != nullptr ? failure : "page restoration failed");
      return false;
    }

    Win32MemoryRegion restored;
    if (!art::QueryWin32Memory(saved.page_begin, &restored, nullptr) ||
        restored.allocation_base != saved.allocation_base ||
        (saved.original_state == MEM_RESERVE
             ? restored.state != MEM_RESERVE
             : restored.state != MEM_COMMIT ||
                 restored.type != saved.original_type ||
                 restored.protect != saved.original_protect)) {
      Fail(label, "page did not match its original state after restoration");
      return false;
    }
  }

  std::printf("page_case label=%s stack=%zu excluded=%zu original_state=0x%lx "
              "original_protect=0x%lx iterations=%d\n",
              label,
              stack_size,
              first_excluded,
              static_cast<unsigned long>(first_original_state),
              static_cast<unsigned long>(first_original_protect),
              iterations);
  return true;
}

void CheckReservedAllocation() {
  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);
  const size_t page_size = static_cast<size_t>(system_info.dwPageSize);
  const size_t allocation_size = 1024u * 1024u;
  void* allocation = VirtualAlloc(nullptr, allocation_size, MEM_RESERVE, PAGE_NOACCESS);
  if (allocation == nullptr) {
    Fail("reserved", "could not create the reserved allocation");
    return;
  }

  const uintptr_t low = reinterpret_cast<uintptr_t>(allocation);
  const uintptr_t high = low + allocation_size;
  for (int i = 0; i < kReservedRestoreIterations; ++i) {
    Win32StackPageRecord record;
    const char* failure = nullptr;
    uint32_t win32_error = 0u;
    if (!art::InstallWin32StackPage(low,
                                    high,
                                    page_size,
                                    page_size,
                                    3u * page_size,
                                    &record,
                                    &failure,
                                    &win32_error)) {
      Fail("reserved", failure != nullptr ? failure : "page installation failed");
      break;
    }
    volatile uint8_t* page =
        reinterpret_cast<volatile uint8_t*>(record.selection.page_begin);
    if (record.selection.original_state != MEM_RESERVE || !AccessFaults(page)) {
      Fail("reserved", "reserved page did not commit and fault as PAGE_NOACCESS");
    }
    if (!art::UnprotectWin32StackPage(&record, &failure, &win32_error)) {
      Fail("reserved", failure != nullptr ? failure : "page unprotect failed");
      break;
    }
    *page = static_cast<uint8_t>(i);
    if (*page != static_cast<uint8_t>(i) ||
        !art::ProtectWin32StackPage(&record, &failure, &win32_error) ||
        !AccessFaults(page)) {
      Fail("reserved", failure != nullptr ? failure : "page reprotect failed");
      break;
    }
    if (!art::RestoreWin32StackPage(&record, &failure, &win32_error)) {
      Fail("reserved", failure != nullptr ? failure : "page restoration failed");
      break;
    }
    Win32MemoryRegion restored;
    if (!art::QueryWin32Memory(low + page_size, &restored, nullptr) ||
        restored.allocation_base != low || restored.state != MEM_RESERVE) {
      Fail("reserved", "page was not decommitted to MEM_RESERVE");
      break;
    }
  }

  if (VirtualFree(allocation, 0u, MEM_RELEASE) == 0u) {
    Fail("reserved", "could not release the reserved allocation");
  }
  std::printf("reserved_case size=%zu iterations=%d\n",
              allocation_size,
              kReservedRestoreIterations);
}

void* PthreadWorker(void*) {
  return CheckActualPage("pthread", 1) ? reinterpret_cast<void*>(0x51a7u) : nullptr;
}

}  // namespace

int main() {
  PVOID handler = AddVectoredExceptionHandler(1u, PageFaultHandler);
  if (handler == nullptr) {
    Fail("veh", "could not install the direct page-fault observer");
    return 1;
  }
  CheckDeterministicSelection();
  CheckReadOnlyLayoutInspection();
  CheckActualPage("main", kRestoreIterations);
  CheckReservedAllocation();

  pthread_attr_t attr;
  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 2u * 1024u * 1024u);
  pthread_t thread = nullptr;
  if (pthread_create(&thread, &attr, PthreadWorker, nullptr) != 0) {
    Fail("pthread", "could not create the page-probe worker");
  }
  pthread_attr_destroy(&attr);
  void* result = nullptr;
  if (thread != nullptr &&
      (pthread_join(thread, &result) != 0 || result != reinterpret_cast<void*>(0x51a7u))) {
    Fail("pthread", "page-probe worker did not join cleanly");
  }

  if (RemoveVectoredExceptionHandler(handler) == 0u) {
    Fail("veh", "could not remove the direct page-fault observer");
  }

  std::printf("win32_stack_page_probe failures=%ld committed_restore_iterations=%d "
              "reserved_restore_iterations=%d faults=%ld\n",
              g_failures,
              kRestoreIterations,
              kReservedRestoreIterations,
              g_expected_faults);
  if (g_failures != 0) {
    return 1;
  }
  std::puts("win32_stack_page_probe OK");
  return 0;
}
