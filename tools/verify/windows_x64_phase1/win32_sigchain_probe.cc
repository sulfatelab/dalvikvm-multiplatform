#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <iterator>

#include "runtime/multiplatform/windows/fault_handler_windows.h"
#include "sigchain.h"

namespace {

extern "C" uint8_t Win32StackPageFaultRead(const volatile uint8_t* page);
extern "C" char Win32StackPageFaultInstruction;
extern "C" char Win32StackPageFaultResume;

volatile LONG g_calls = 0;
volatile LONG g_action_calls = 0;
volatile LONG g_foreign_before_calls = 0;
volatile LONG g_foreign_after_calls = 0;
volatile LONG g_sequence_count = 0;
volatile LONG g_sequence[4] = {};
volatile uintptr_t g_expected_page = 0u;

bool HandlePageFault(int sig, siginfo_t* info, void* opaque) {
  InterlockedIncrement(&g_action_calls);
  if (sig != SIGSEGV || info == nullptr ||
      reinterpret_cast<uintptr_t>(info->si_addr) != g_expected_page || opaque == nullptr) {
    return false;
  }
  art::WindowsFaultContext* context = static_cast<art::WindowsFaultContext*>(opaque);
  if (context->context == nullptr || context->access_type != art::kWin32FaultRead ||
      context->context->Rip != reinterpret_cast<DWORD64>(&Win32StackPageFaultInstruction)) {
    return false;
  }
  context->context->Rax = 0u;
  context->context->Rip = reinterpret_cast<DWORD64>(&Win32StackPageFaultResume);
  InterlockedIncrement(&g_calls);
  return true;
}

void RecordForeignCall(LONG value) {
  const LONG index = InterlockedIncrement(&g_sequence_count) - 1;
  if (index >= 0 && index < static_cast<LONG>(std::size(g_sequence))) {
    g_sequence[index] = value;
  }
}

LONG WINAPI ForeignBefore(EXCEPTION_POINTERS* exception) {
  if (exception != nullptr && exception->ExceptionRecord != nullptr &&
      exception->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
    InterlockedIncrement(&g_foreign_before_calls);
    RecordForeignCall(1);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

LONG WINAPI ForeignAfter(EXCEPTION_POINTERS* exception) {
  if (exception != nullptr && exception->ExceptionRecord != nullptr &&
      exception->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
    InterlockedIncrement(&g_foreign_after_calls);
    RecordForeignCall(2);
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

__declspec(noinline) bool ReadCaughtByFrameSeh(const volatile uint8_t* page) {
  __try {
    static_cast<void>(Win32StackPageFaultRead(page));
    return false;
  } __except (GetExceptionCode() == EXCEPTION_ACCESS_VIOLATION
                  ? EXCEPTION_EXECUTE_HANDLER
                  : EXCEPTION_CONTINUE_SEARCH) {
    return true;
  }
}

}  // namespace

int main() {
  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);
  const size_t page_size = static_cast<size_t>(system_info.dwPageSize);
  void* allocation = VirtualAlloc(nullptr,
                                  page_size,
                                  MEM_RESERVE | MEM_COMMIT,
                                  PAGE_READWRITE);
  if (allocation == nullptr) {
    std::fprintf(stderr, "FAIL allocation error=%lu\n", GetLastError());
    return 1;
  }
  DWORD old_protect = 0u;
  if (!VirtualProtect(allocation, page_size, PAGE_NOACCESS, &old_protect)) {
    std::fprintf(stderr, "FAIL protect error=%lu\n", GetLastError());
    return 1;
  }

  PVOID foreign_before = AddVectoredExceptionHandler(0u, ForeignBefore);
  if (foreign_before == nullptr) {
    std::fprintf(stderr, "FAIL foreign-before registration error=%lu\n", GetLastError());
    return 1;
  }

  art::SigchainAction action = {};
  action.sc_sigaction = HandlePageFault;
  g_expected_page = reinterpret_cast<uintptr_t>(allocation);
  art::AddSpecialSignalHandlerFn(SIGSEGV, &action);
  PVOID foreign_after = AddVectoredExceptionHandler(0u, ForeignAfter);
  if (foreign_after == nullptr) {
    std::fprintf(stderr, "FAIL foreign-after registration error=%lu\n", GetLastError());
    return 1;
  }
  const uint8_t first = Win32StackPageFaultRead(
      reinterpret_cast<const volatile uint8_t*>(allocation));
  art::EnsureFrontOfChain(SIGSEGV);
  const uint8_t second = Win32StackPageFaultRead(
      reinterpret_cast<const volatile uint8_t*>(allocation));

  void* unrecognized = VirtualAlloc(nullptr,
                                    page_size,
                                    MEM_RESERVE | MEM_COMMIT,
                                    PAGE_READWRITE);
  if (unrecognized == nullptr ||
      !VirtualProtect(unrecognized, page_size, PAGE_NOACCESS, &old_protect)) {
    std::fprintf(stderr, "FAIL unrecognized-page setup error=%lu\n", GetLastError());
    return 1;
  }
  const bool frame_caught_with_action = ReadCaughtByFrameSeh(
      reinterpret_cast<const volatile uint8_t*>(unrecognized));
  art::RemoveSpecialSignalHandlerFn(SIGSEGV, HandlePageFault);
  g_expected_page = 0u;
  const bool frame_caught_after_remove = ReadCaughtByFrameSeh(
      reinterpret_cast<const volatile uint8_t*>(unrecognized));

  VirtualProtect(allocation, page_size, PAGE_READWRITE, &old_protect);
  VirtualFree(allocation, 0u, MEM_RELEASE);
  VirtualFree(unrecognized, 0u, MEM_RELEASE);
  RemoveVectoredExceptionHandler(foreign_after);
  RemoveVectoredExceptionHandler(foreign_before);

  std::printf("win32_sigchain_probe calls=%ld first=%u second=%u action_calls=%ld "
              "foreign_before=%ld foreign_after=%ld frame_with_action=%d "
              "frame_after_remove=%d sequence=%ld,%ld,%ld,%ld\n",
              g_calls,
              static_cast<unsigned>(first),
              static_cast<unsigned>(second),
              g_action_calls,
              g_foreign_before_calls,
              g_foreign_after_calls,
              frame_caught_with_action,
              frame_caught_after_remove,
              g_sequence[0],
              g_sequence[1],
              g_sequence[2],
              g_sequence[3]);
  if (g_calls != 2 || first != 0u || second != 0u || g_action_calls != 3 ||
      g_foreign_before_calls != 2 || g_foreign_after_calls != 2 ||
      !frame_caught_with_action || !frame_caught_after_remove ||
      g_sequence_count != 4 || g_sequence[0] != 1 || g_sequence[1] != 2 ||
      g_sequence[2] != 1 || g_sequence[3] != 2) {
    std::puts("win32_sigchain_probe FAIL");
    return 1;
  }
  std::puts("win32_sigchain_probe OK");
  return 0;
}
