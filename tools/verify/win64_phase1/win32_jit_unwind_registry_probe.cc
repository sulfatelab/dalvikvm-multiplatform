#include <windows.h>

#include <stdint.h>

#include <cstring>
#include <iostream>
#include <vector>

#include "runtime/multiplatform/windows/jit_unwind_windows.h"
#include "utils/x86_64/win64_unwind_info.h"

namespace {

using art::jit::Win64JitUnwindRegistry;
using art::x86_64::Win64UnwindInfoBuilder;

int g_failures = 0;

void Expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    ++g_failures;
  }
}

class VirtualAllocation {
 public:
  explicit VirtualAllocation(size_t size)
      : address_(static_cast<uint8_t*>(
            VirtualAlloc(nullptr, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE))) {}

  ~VirtualAllocation() {
    if (address_ != nullptr) {
      VirtualFree(address_, 0u, MEM_RELEASE);
    }
  }

  uint8_t* Get() const { return address_; }

 private:
  uint8_t* address_;
};

}  // namespace

int main() {
  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  const size_t page_size = system_info.dwPageSize;
  VirtualAllocation allocation(2u * page_size);
  Expect(allocation.Get() != nullptr, "two-page allocation succeeds");
  if (allocation.Get() == nullptr) {
    return 1;
  }

  uint8_t* base = allocation.Get();
  uint8_t* unwind_info = base + 64u;
  uint8_t* code = base + page_size;
  const std::vector<uint8_t> machine_code = {
      0x55u,                                      // push rbp
      0x48u, 0x83u, 0xecu, 0x20u,                // sub rsp, 32
      0x48u, 0x89u, 0xe5u,                       // mov rbp, rsp
      0xb8u, 0x2au, 0x00u, 0x00u, 0x00u,         // mov eax, 42
      0x48u, 0x89u, 0xecu,                       // mov rsp, rbp
      0x48u, 0x83u, 0xc4u, 0x20u,                // add rsp, 32
      0x5du,                                      // pop rbp
      0xc3u,                                      // ret
  };

  Win64UnwindInfoBuilder builder;
  builder.Enable();
  builder.RecordPushNonvolatile(/*RBP=*/ 5u, /*code_offset=*/ 1u);
  builder.RecordStackAllocation(/*size=*/ 32u, /*code_offset=*/ 5u);
  builder.RecordSetFramePointer(/*RBP=*/ 5u, /*scaled_offset=*/ 0u, /*code_offset=*/ 8u);
  builder.Finalize(/*prologue_size=*/ 8u);
  Expect(builder.IsValid(), "probe unwind descriptor is valid");
  Expect(!builder.GetData().empty(), "probe unwind descriptor is nonempty");
  if (!builder.IsValid() || builder.GetData().empty()) {
    return 1;
  }

  std::memcpy(unwind_info, builder.GetData().data(), builder.GetData().size());
  std::memcpy(code, machine_code.data(), machine_code.size());
  DWORD old_protect = 0u;
  Expect(VirtualProtect(base, page_size, PAGE_READONLY, &old_protect) != FALSE,
         "xdata page becomes read-only");
  Expect(VirtualProtect(code, page_size, PAGE_EXECUTE_READ, &old_protect) != FALSE,
         "code page becomes executable and read-only");
  Expect(FlushInstructionCache(GetCurrentProcess(), code, machine_code.size()) != FALSE,
         "instruction cache flush succeeds");

  Win64JitUnwindRegistry registry;
  Expect(!registry.Register(code, 0u, unwind_info, base), "zero-sized code is rejected");
  Expect(!registry.Register(code, machine_code.size(), unwind_info + 1u, base),
         "misaligned unwind info is rejected");
  Expect(!registry.Register(code, machine_code.size(), unwind_info, code + 1u),
         "base above code is rejected");
  Expect(registry.Register(code, machine_code.size(), unwind_info, base),
         "runtime-function registration succeeds");
  Expect(registry.Size() == 1u, "registry owns one runtime-function entry");
  Expect(!registry.Register(code, machine_code.size(), unwind_info, base),
         "duplicate code registration is rejected");

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(code + 8u), &image_base, nullptr);
  Expect(function != nullptr, "RtlLookupFunctionEntry finds registered code");
  Expect(image_base == reinterpret_cast<DWORD64>(base), "lookup reports the selected base");
  if (function != nullptr) {
    Expect(function->BeginAddress == page_size, "lookup begin offset matches code");
    Expect(function->EndAddress == page_size + machine_code.size(),
           "lookup end offset is exclusive");
    Expect(function->UnwindData == 64u, "lookup unwind offset matches xdata");
  }

  using ProbeFunction = int (*)();
  Expect(reinterpret_cast<ProbeFunction>(code)() == 42, "registered generated function executes");

  alignas(16) uint8_t stack[256] = {};
  uintptr_t entry_rsp =
      (reinterpret_cast<uintptr_t>(stack + sizeof(stack) - 32u) & ~uintptr_t{15u}) + 8u;
  constexpr uint64_t kSavedRbp = UINT64_C(0x1122334455667788);
  constexpr uint64_t kReturnAddress = UINT64_C(0x123456789abcdef0);
  *reinterpret_cast<uint64_t*>(entry_rsp - 8u) = kSavedRbp;
  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
  context.Rip = reinterpret_cast<DWORD64>(code + 8u);
  context.Rsp = entry_rsp - 40u;
  context.Rbp = context.Rsp;
  PVOID handler_data = nullptr;
  DWORD64 establisher_frame = 0u;
  if (function != nullptr) {
    RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                     image_base,
                     context.Rip,
                     function,
                     &context,
                     &handler_data,
                     &establisher_frame,
                     nullptr);
    Expect(context.Rip == kReturnAddress, "virtual unwind restores the return address");
    Expect(context.Rsp == entry_rsp + 8u, "virtual unwind pops the return address");
    Expect(context.Rbp == kSavedRbp, "virtual unwind restores caller RBP");
  }

  Expect(registry.Unregister(code), "runtime-function deletion succeeds");
  Expect(registry.Size() == 0u, "registry is empty after deletion");
  image_base = 0u;
  Expect(RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(code + 8u), &image_base, nullptr) ==
             nullptr,
         "lookup no longer finds deleted generated code");

  Expect(registry.Register(code, machine_code.size(), unwind_info, base),
         "runtime-function re-registration succeeds");
  Expect(registry.Clear(), "registry teardown removes all entries");
  Expect(registry.Size() == 0u, "registry teardown leaves no entries");

  std::cout << "win32_jit_unwind_registry_probe failures=" << g_failures << '\n';
  if (g_failures == 0) {
    std::cout << "win32_jit_unwind_registry_probe OK\n";
  }
  return g_failures == 0 ? 0 : 1;
}
