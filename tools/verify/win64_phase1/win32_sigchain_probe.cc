#include <windows.h>

#include <cstdint>
#include <cstdio>

#include "runtime/multiplatform/windows/fault_handler_windows.h"
#include "sigchain.h"

namespace {

extern "C" uint8_t Win32StackPageFaultRead(const volatile uint8_t* page);
extern "C" char Win32StackPageFaultInstruction;
extern "C" char Win32StackPageFaultResume;

volatile LONG g_calls = 0;
volatile uintptr_t g_expected_page = 0u;

bool HandlePageFault(int sig, siginfo_t* info, void* opaque) {
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

  art::SigchainAction action = {};
  action.sc_sigaction = HandlePageFault;
  g_expected_page = reinterpret_cast<uintptr_t>(allocation);
  art::AddSpecialSignalHandlerFn(SIGSEGV, &action);
  const uint8_t first = Win32StackPageFaultRead(
      reinterpret_cast<const volatile uint8_t*>(allocation));
  art::EnsureFrontOfChain(SIGSEGV);
  const uint8_t second = Win32StackPageFaultRead(
      reinterpret_cast<const volatile uint8_t*>(allocation));
  art::RemoveSpecialSignalHandlerFn(SIGSEGV, HandlePageFault);
  g_expected_page = 0u;

  VirtualProtect(allocation, page_size, PAGE_READWRITE, &old_protect);
  VirtualFree(allocation, 0u, MEM_RELEASE);

  std::printf("win32_sigchain_probe calls=%ld first=%u second=%u\n",
              g_calls,
              static_cast<unsigned>(first),
              static_cast<unsigned>(second));
  if (g_calls != 2 || first != 0u || second != 0u) {
    std::puts("win32_sigchain_probe FAIL");
    return 1;
  }
  std::puts("win32_sigchain_probe OK");
  return 0;
}
