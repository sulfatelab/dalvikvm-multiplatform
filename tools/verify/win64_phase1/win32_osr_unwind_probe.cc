#include <windows.h>

#include <stdint.h>

#include <cstring>
#include <iostream>

namespace {

int g_failures = 0;

void Expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    ++g_failures;
  }
}

template <size_t kSize>
uint8_t* FindBytes(uint8_t* begin, uint8_t* end, const uint8_t (&pattern)[kSize]) {
  for (uint8_t* cursor = begin; cursor + kSize <= end; ++cursor) {
    if (std::memcmp(cursor, pattern, kSize) == 0) {
      return cursor;
    }
  }
  return nullptr;
}

M128A MakeM128(uint64_t low, int64_t high) {
  M128A value = {};
  value.Low = low;
  value.High = high;
  return value;
}

bool EqualM128(const M128A& left, const M128A& right) {
  return left.Low == right.Low && left.High == right.High;
}

void StoreM128(uintptr_t address, const M128A& value) {
  std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(value));
}

struct VirtualStack {
  explicit VirtualStack(size_t size)
      : address(static_cast<uint8_t*>(
            VirtualAlloc(nullptr, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE))) {}

  ~VirtualStack() {
    if (address != nullptr) {
      VirtualFree(address, 0u, MEM_RELEASE);
    }
  }

  uint8_t* address;
};

}  // namespace

int main() {
  HMODULE art = LoadLibraryW(L"art.dll");
  Expect(art != nullptr, "art.dll loads");
  if (art == nullptr) {
    std::cerr << "LoadLibraryW error=" << GetLastError() << '\n';
    return 1;
  }

  auto* osr = reinterpret_cast<uint8_t*>(GetProcAddress(art, "art_quick_osr_stub"));
  Expect(osr != nullptr, "art_quick_osr_stub export resolves");
  if (osr == nullptr) {
    FreeLibrary(art);
    return 1;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(osr), &image_base, nullptr);
  Expect(function != nullptr, "RtlLookupFunctionEntry finds the OSR stub");
  Expect(image_base == reinterpret_cast<DWORD64>(art), "lookup reports art.dll image base");
  if (function == nullptr) {
    FreeLibrary(art);
    return 1;
  }

  uint8_t* function_begin = reinterpret_cast<uint8_t*>(image_base + function->BeginAddress);
  uint8_t* function_end = reinterpret_cast<uint8_t*>(image_base + function->EndAddress);
  Expect(function_begin == osr, "runtime-function entry starts at the OSR export");
  Expect(function_end > function_begin, "runtime-function range is nonempty");

  const uint8_t* unwind_info = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  const uint8_t version = unwind_info[0] & 0x7u;
  const uint8_t prologue_size = unwind_info[1];
  const uint8_t frame_register = unwind_info[3] & 0x0fu;
  const uint8_t frame_offset = unwind_info[3] >> 4u;
  Expect(version == 1u, "OSR unwind info uses version 1");
  Expect(prologue_size != 0u && function_begin + prologue_size < function_end,
         "OSR unwind prologue size is in range");
  Expect(frame_register == 5u, "OSR unwind frame register is RBP");
  Expect(frame_offset == 0u, "OSR unwind frame offset is zero");

  // Select an instruction after the variable RSP subtraction. This proves the
  // PE record recovers the fixed frame through RBP instead of trusting RSP.
  constexpr uint8_t kVariableBody[] = {
      0x83u, 0xe9u, 0x08u,              // sub ecx, 8
      0x48u, 0x29u, 0xccu,              // sub rsp, rcx
      0x48u, 0x89u, 0xe7u,              // mov rdi, rsp
      0xf3u, 0xa4u,                     // rep movsb
      0xffu, 0xe2u,                     // jmp rdx
  };
  uint8_t* variable_body = FindBytes(function_begin, function_end, kVariableBody);
  Expect(variable_body != nullptr, "OSR variable-stack body is found");

  // The call is the final instruction in the entry range, so OSR code returns
  // to a second runtime-function range that describes the inherited fixed
  // frame from RSP without assuming that managed code preserved RBP.
  uint8_t* return_begin = function_end;
  DWORD64 return_image_base = 0u;
  PRUNTIME_FUNCTION return_function = RtlLookupFunctionEntry(
      reinterpret_cast<DWORD64>(return_begin), &return_image_base, nullptr);
  Expect(return_function != nullptr, "RtlLookupFunctionEntry finds the OSR return range");
  Expect(return_function != function, "OSR return range has a distinct unwind record");
  Expect(return_image_base == image_base, "OSR return range belongs to art.dll");
  uint8_t* return_end =
      return_function == nullptr
          ? return_begin
          : reinterpret_cast<uint8_t*>(return_image_base + return_function->EndAddress);
  if (return_function != nullptr) {
    Expect(reinterpret_cast<uint8_t*>(return_image_base + return_function->BeginAddress) ==
               return_begin,
           "OSR return runtime-function range starts at the call return address");
    const uint8_t* return_unwind =
        reinterpret_cast<const uint8_t*>(return_image_base + return_function->UnwindData);
    Expect((return_unwind[0] & 0x7u) == 1u, "OSR return unwind info uses version 1");
    Expect(return_unwind[1] == 0u, "OSR return inherited-frame prologue size is zero");
    Expect((return_unwind[3] & 0x0fu) == 0u, "OSR return unwind record is RSP-based");
  }

  // Identify the canonical epilogue independently. RtlVirtualUnwind must
  // recognize it instead of applying the complete inherited-frame record.
  constexpr uint8_t kCanonicalEpilogue[] = {
      0x48u, 0x81u, 0xc4u, 0xb8u, 0x00u, 0x00u, 0x00u,  // add rsp, 184
      0xc3u,                            // ret
  };
  uint8_t* epilogue = FindBytes(return_begin, return_end, kCanonicalEpilogue);
  Expect(epilogue != nullptr, "OSR canonical epilogue is found");

  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  VirtualStack stack(system_info.dwPageSize);
  Expect(stack.address != nullptr, "synthetic OSR stack allocation succeeds");
  if (stack.address == nullptr || variable_body == nullptr || return_function == nullptr ||
      epilogue == nullptr) {
    FreeLibrary(art);
    return 1;
  }

  uintptr_t entry_rsp = reinterpret_cast<uintptr_t>(stack.address + system_info.dwPageSize - 512u);
  entry_rsp = (entry_rsp & ~uintptr_t{15u}) + 8u;
  const uintptr_t fixed_rsp = entry_rsp - 184u;
  const uintptr_t variable_rsp = fixed_rsp - 256u;

  constexpr uint64_t kReturnAddress = UINT64_C(0x123456789abcdef0);
  constexpr uint64_t kRbp = UINT64_C(0x0102030405060708);
  constexpr uint64_t kRdi = UINT64_C(0x1112131415161718);
  constexpr uint64_t kRsi = UINT64_C(0x2122232425262728);
  constexpr uint64_t kRbx = UINT64_C(0x3132333435363738);
  constexpr uint64_t kR12 = UINT64_C(0x4142434445464748);
  constexpr uint64_t kR13 = UINT64_C(0x5152535455565758);
  constexpr uint64_t kR14 = UINT64_C(0x6162636465666768);
  constexpr uint64_t kR15 = UINT64_C(0x7172737475767778);
  constexpr uint64_t kVolatileRcx = UINT64_C(0x8182838485868788);
  constexpr uint64_t kVolatileR8 = UINT64_C(0x9192939495969798);

  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;
  *reinterpret_cast<uint64_t*>(entry_rsp - 8u) = kRbp;
  *reinterpret_cast<uint64_t*>(entry_rsp - 16u) = kRdi;
  *reinterpret_cast<uint64_t*>(entry_rsp - 24u) = kRsi;
  *reinterpret_cast<uint64_t*>(entry_rsp - 128u) = UINT64_C(0xa1a2a3a4a5a6a7a8);
  *reinterpret_cast<uint64_t*>(entry_rsp - 136u) = UINT64_C(0xb1b2b3b4b5b6b7b8);
  *reinterpret_cast<uint64_t*>(entry_rsp - 144u) = kRbx;
  *reinterpret_cast<uint64_t*>(entry_rsp - 152u) = kR12;
  *reinterpret_cast<uint64_t*>(entry_rsp - 160u) = kR13;
  *reinterpret_cast<uint64_t*>(entry_rsp - 168u) = kR14;
  *reinterpret_cast<uint64_t*>(entry_rsp - 176u) = kR15;
  *reinterpret_cast<uint64_t*>(entry_rsp - 184u) = 0u;

  const M128A saved_xmms[] = {
      MakeM128(UINT64_C(0x0606060606060606), INT64_C(0x1616161616161616)),
      MakeM128(UINT64_C(0x0707070707070707), INT64_C(0x1717171717171717)),
      MakeM128(UINT64_C(0x0808080808080808), INT64_C(0x1818181818181818)),
      MakeM128(UINT64_C(0x0909090909090909), INT64_C(0x1919191919191919)),
      MakeM128(UINT64_C(0x0a0a0a0a0a0a0a0a), INT64_C(0x1a1a1a1a1a1a1a1a)),
      MakeM128(UINT64_C(0x0b0b0b0b0b0b0b0b), INT64_C(0x1b1b1b1b1b1b1b1b)),
  };
  for (size_t index = 0; index < 6u; ++index) {
    StoreM128(entry_rsp - 120u + index * 16u, saved_xmms[index]);
  }

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_FULL;
  context.Rip = reinterpret_cast<DWORD64>(variable_body + 9u);
  context.Rsp = variable_rsp;
  context.Rbp = fixed_rsp;
  context.Rbx = context.R12 = context.R13 = context.R14 = context.R15 = UINT64_C(0xcccccccccccccccc);
  context.Rdi = context.Rsi = UINT64_C(0xdddddddddddddddd);
  context.Rcx = kVolatileRcx;
  context.R8 = kVolatileR8;
  context.Xmm6 = context.Xmm7 = context.Xmm8 = context.Xmm9 = context.Xmm10 = context.Xmm11 =
      MakeM128(UINT64_C(0xeeeeeeeeeeeeeeee), INT64_C(-1));

  PVOID handler_data = nullptr;
  DWORD64 establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   image_base,
                   context.Rip,
                   function,
                   &context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  Expect(context.Rip == kReturnAddress, "variable-stack unwind restores return address");
  Expect(context.Rsp == entry_rsp + 8u, "variable-stack unwind restores caller RSP");
  Expect(context.Rbp == kRbp, "variable-stack unwind restores RBP");
  Expect(context.Rdi == kRdi, "variable-stack unwind restores RDI");
  Expect(context.Rsi == kRsi, "variable-stack unwind restores RSI");
  Expect(context.Rbx == kRbx, "variable-stack unwind restores RBX");
  Expect(context.R12 == kR12, "variable-stack unwind restores R12");
  Expect(context.R13 == kR13, "variable-stack unwind restores R13");
  Expect(context.R14 == kR14, "variable-stack unwind restores R14");
  Expect(context.R15 == kR15, "variable-stack unwind restores R15");
  Expect(context.Rcx == kVolatileRcx, "variable-stack unwind leaves volatile RCX unchanged");
  Expect(context.R8 == kVolatileR8, "variable-stack unwind leaves volatile R8 unchanged");
  Expect(EqualM128(context.Xmm6, saved_xmms[0]), "variable-stack unwind restores XMM6");
  Expect(EqualM128(context.Xmm7, saved_xmms[1]), "variable-stack unwind restores XMM7");
  Expect(EqualM128(context.Xmm8, saved_xmms[2]), "variable-stack unwind restores XMM8");
  Expect(EqualM128(context.Xmm9, saved_xmms[3]), "variable-stack unwind restores XMM9");
  Expect(EqualM128(context.Xmm10, saved_xmms[4]), "variable-stack unwind restores XMM10");
  Expect(EqualM128(context.Xmm11, saved_xmms[5]), "variable-stack unwind restores XMM11");

  CONTEXT return_context = {};
  return_context.ContextFlags = CONTEXT_FULL;
  return_context.Rip = reinterpret_cast<DWORD64>(return_begin + 5u);
  return_context.Rsp = fixed_rsp;
  return_context.Rbp = UINT64_C(0xabababababababab);
  return_context.Rbx = return_context.R12 = return_context.R13 = return_context.R14 =
      return_context.R15 = UINT64_C(0xcccccccccccccccc);
  return_context.Rdi = return_context.Rsi = UINT64_C(0xdddddddddddddddd);
  return_context.Rcx = kVolatileRcx;
  return_context.R8 = kVolatileR8;
  return_context.Xmm6 = return_context.Xmm7 = return_context.Xmm8 = return_context.Xmm9 =
      return_context.Xmm10 = return_context.Xmm11 =
          MakeM128(UINT64_C(0xeeeeeeeeeeeeeeee), INT64_C(-1));
  handler_data = nullptr;
  establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   return_image_base,
                   return_context.Rip,
                   return_function,
                   &return_context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  Expect(return_context.Rip == kReturnAddress, "return-range unwind restores return address");
  Expect(return_context.Rsp == entry_rsp + 8u, "return-range unwind restores caller RSP");
  Expect(return_context.Rbp == kRbp, "return-range unwind restores RBP without an anchor");
  Expect(return_context.Rdi == kRdi && return_context.Rsi == kRsi &&
             return_context.Rbx == kRbx && return_context.R12 == kR12 &&
             return_context.R13 == kR13 && return_context.R14 == kR14 &&
             return_context.R15 == kR15,
         "return-range unwind restores nonvolatile GPRs");
  Expect(return_context.Rcx == kVolatileRcx && return_context.R8 == kVolatileR8,
         "return-range unwind leaves volatile GPRs unchanged");
  Expect(EqualM128(return_context.Xmm6, saved_xmms[0]) &&
             EqualM128(return_context.Xmm7, saved_xmms[1]) &&
             EqualM128(return_context.Xmm8, saved_xmms[2]) &&
             EqualM128(return_context.Xmm9, saved_xmms[3]) &&
             EqualM128(return_context.Xmm10, saved_xmms[4]) &&
             EqualM128(return_context.Xmm11, saved_xmms[5]),
         "return-range unwind restores XMM6-XMM11");

  CONTEXT epilogue_context = {};
  epilogue_context.ContextFlags = CONTEXT_FULL;
  epilogue_context.Rip = reinterpret_cast<DWORD64>(epilogue);
  epilogue_context.Rsp = fixed_rsp;
  epilogue_context.Rbp = kRbp;
  epilogue_context.Rdi = kRdi;
  epilogue_context.Rsi = kRsi;
  epilogue_context.Rbx = kRbx;
  epilogue_context.R12 = kR12;
  epilogue_context.R13 = kR13;
  epilogue_context.R14 = kR14;
  epilogue_context.R15 = kR15;
  epilogue_context.Xmm6 = saved_xmms[0];
  epilogue_context.Xmm7 = saved_xmms[1];
  epilogue_context.Xmm8 = saved_xmms[2];
  epilogue_context.Xmm9 = saved_xmms[3];
  epilogue_context.Xmm10 = saved_xmms[4];
  epilogue_context.Xmm11 = saved_xmms[5];
  handler_data = nullptr;
  establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   return_image_base,
                   epilogue_context.Rip,
                   return_function,
                   &epilogue_context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  Expect(epilogue_context.Rip == kReturnAddress, "epilogue unwind restores return address");
  Expect(epilogue_context.Rsp == entry_rsp + 8u, "epilogue unwind restores caller RSP");
  Expect(epilogue_context.Rbp == kRbp, "epilogue unwind restores RBP");
  Expect(epilogue_context.Rdi == kRdi && epilogue_context.Rsi == kRsi &&
             epilogue_context.Rbx == kRbx && epilogue_context.R12 == kR12 &&
             epilogue_context.R13 == kR13 && epilogue_context.R14 == kR14 &&
             epilogue_context.R15 == kR15,
         "epilogue unwind preserves already-restored nonvolatile GPRs");
  Expect(EqualM128(epilogue_context.Xmm6, saved_xmms[0]) &&
             EqualM128(epilogue_context.Xmm7, saved_xmms[1]) &&
             EqualM128(epilogue_context.Xmm8, saved_xmms[2]) &&
             EqualM128(epilogue_context.Xmm9, saved_xmms[3]) &&
             EqualM128(epilogue_context.Xmm10, saved_xmms[4]) &&
             EqualM128(epilogue_context.Xmm11, saved_xmms[5]),
         "epilogue unwind preserves already-restored XMM registers");

  std::cout << "win32_osr_unwind_probe failures=" << g_failures
            << " prologue=" << static_cast<unsigned>(prologue_size)
            << " entry_frame_offset=" << static_cast<unsigned>(frame_offset) * 16u
            << " return_prologue=0"
            << " variable_rsp_delta=" << fixed_rsp - variable_rsp << '\n';
  if (g_failures == 0) {
    std::cout << "win32_osr_unwind_probe OK\n";
  }
  FreeLibrary(art);
  return g_failures == 0 ? 0 : 1;
}
