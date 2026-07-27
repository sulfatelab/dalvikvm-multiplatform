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

void ExpectForSymbol(bool condition, const char* symbol, const char* message) {
  if (!condition) {
    std::cerr << "FAIL: " << symbol << ' ' << message << '\n';
    ++g_failures;
  }
}

void TestInvokeUnwind(HMODULE art, const char* symbol) {
  auto* entry = reinterpret_cast<uint8_t*>(GetProcAddress(art, symbol));
  ExpectForSymbol(entry != nullptr, symbol, "export resolves");
  if (entry == nullptr) {
    return;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
  ExpectForSymbol(function != nullptr, symbol, "runtime-function entry resolves");
  if (function == nullptr) {
    return;
  }
  const uint8_t* unwind = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  const uint8_t prologue_size = unwind[1];
  ExpectForSymbol(prologue_size != 0u, symbol, "prologue is nonempty");
  ExpectForSymbol((unwind[3] & 0x0fu) == 5u, symbol, "frame register is RBP");

  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  VirtualStack stack(system_info.dwPageSize);
  ExpectForSymbol(stack.address != nullptr, symbol, "synthetic stack allocation succeeds");
  if (stack.address == nullptr) {
    return;
  }

  uintptr_t entry_rsp = reinterpret_cast<uintptr_t>(stack.address + system_info.dwPageSize - 512u);
  entry_rsp = (entry_rsp & ~uintptr_t{15u}) + 8u;
  const uintptr_t fixed_rsp = entry_rsp - 240u;
  const uintptr_t variable_rsp = fixed_rsp - 256u;
  constexpr uint64_t kReturnAddress = UINT64_C(0x23456789abcdef01);
  constexpr uint64_t kRbp = UINT64_C(0x1020304050607080);
  constexpr uint64_t kRdi = UINT64_C(0x1122334455667788);
  constexpr uint64_t kRsi = UINT64_C(0x8877665544332211);
  constexpr uint64_t kRbx = UINT64_C(0x2233445566778899);
  constexpr uint64_t kR12 = UINT64_C(0x33445566778899aa);
  constexpr uint64_t kR13 = UINT64_C(0x445566778899aabb);
  constexpr uint64_t kR14 = UINT64_C(0x5566778899aabbcc);
  constexpr uint64_t kR15 = UINT64_C(0x66778899aabbccdd);

  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;
  *reinterpret_cast<uint64_t*>(entry_rsp - 8u) = kRdi;
  *reinterpret_cast<uint64_t*>(entry_rsp - 16u) = kRsi;
  *reinterpret_cast<uint64_t*>(entry_rsp - 184u) = kRbp;
  *reinterpret_cast<uint64_t*>(entry_rsp - 192u) = UINT64_C(0xa1a2a3a4a5a6a7a8);
  *reinterpret_cast<uint64_t*>(entry_rsp - 200u) = UINT64_C(0xb1b2b3b4b5b6b7b8);
  *reinterpret_cast<uint64_t*>(entry_rsp - 208u) = kRbx;
  *reinterpret_cast<uint64_t*>(entry_rsp - 216u) = kR12;
  *reinterpret_cast<uint64_t*>(entry_rsp - 224u) = kR13;
  *reinterpret_cast<uint64_t*>(entry_rsp - 232u) = kR14;
  *reinterpret_cast<uint64_t*>(entry_rsp - 240u) = kR15;

  M128A saved_xmms[10] = {};
  for (size_t index = 0; index < 10u; ++index) {
    saved_xmms[index] = MakeM128(
        UINT64_C(0x6060606060606060) + index,
        static_cast<int64_t>(UINT64_C(0x7070707070707070) + index));
    StoreM128(entry_rsp - 176u + index * 16u, saved_xmms[index]);
  }

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_FULL;
  context.Rip = reinterpret_cast<DWORD64>(entry + prologue_size);
  context.Rsp = variable_rsp;
  context.Rbp = fixed_rsp;
  context.Rbx = context.R12 = context.R13 = context.R14 = context.R15 =
      UINT64_C(0xcccccccccccccccc);
  context.Rdi = context.Rsi = UINT64_C(0xdddddddddddddddd);
  context.Xmm6 = context.Xmm7 = context.Xmm8 = context.Xmm9 = context.Xmm10 = context.Xmm11 =
      context.Xmm12 = context.Xmm13 = context.Xmm14 = context.Xmm15 =
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
  ExpectForSymbol(context.Rip == kReturnAddress, symbol, "restores return address");
  ExpectForSymbol(context.Rsp == entry_rsp + 8u, symbol, "restores caller RSP");
  ExpectForSymbol(context.Rbp == kRbp && context.Rdi == kRdi && context.Rsi == kRsi &&
                      context.Rbx == kRbx && context.R12 == kR12 && context.R13 == kR13 &&
                      context.R14 == kR14 && context.R15 == kR15,
                  symbol,
                  "restores nonvolatile GPRs");
  const M128A* restored[] = {
      &context.Xmm6,
      &context.Xmm7,
      &context.Xmm8,
      &context.Xmm9,
      &context.Xmm10,
      &context.Xmm11,
      &context.Xmm12,
      &context.Xmm13,
      &context.Xmm14,
      &context.Xmm15,
  };
  bool xmms_match = true;
  for (size_t index = 0; index < 10u; ++index) {
    xmms_match = xmms_match && EqualM128(*restored[index], saved_xmms[index]);
  }
  ExpectForSymbol(xmms_match, symbol, "restores XMM6-XMM15");
}

}  // namespace

int main() {
  HMODULE art = LoadLibraryW(L"art.dll");
  Expect(art != nullptr, "art.dll loads");
  if (art == nullptr) {
    std::cerr << "LoadLibraryW error=" << GetLastError() << '\n';
    return 1;
  }

  TestInvokeUnwind(art, "art_quick_invoke_stub");
  TestInvokeUnwind(art, "art_quick_invoke_static_stub");

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
      0x48u, 0x81u, 0xc4u, 0xf8u, 0x00u, 0x00u, 0x00u,  // add rsp, 248
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
  const uintptr_t fixed_rsp = entry_rsp - 248u;
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
  *reinterpret_cast<uint64_t*>(entry_rsp - 192u) = UINT64_C(0xa1a2a3a4a5a6a7a8);
  *reinterpret_cast<uint64_t*>(entry_rsp - 200u) = UINT64_C(0xb1b2b3b4b5b6b7b8);
  *reinterpret_cast<uint64_t*>(entry_rsp - 208u) = kRbx;
  *reinterpret_cast<uint64_t*>(entry_rsp - 216u) = kR12;
  *reinterpret_cast<uint64_t*>(entry_rsp - 224u) = kR13;
  *reinterpret_cast<uint64_t*>(entry_rsp - 232u) = kR14;
  *reinterpret_cast<uint64_t*>(entry_rsp - 240u) = kR15;
  *reinterpret_cast<uint64_t*>(entry_rsp - 248u) = 0u;

  const M128A saved_xmms[] = {
      MakeM128(UINT64_C(0x0606060606060606), INT64_C(0x1616161616161616)),
      MakeM128(UINT64_C(0x0707070707070707), INT64_C(0x1717171717171717)),
      MakeM128(UINT64_C(0x0808080808080808), INT64_C(0x1818181818181818)),
      MakeM128(UINT64_C(0x0909090909090909), INT64_C(0x1919191919191919)),
      MakeM128(UINT64_C(0x0a0a0a0a0a0a0a0a), INT64_C(0x1a1a1a1a1a1a1a1a)),
      MakeM128(UINT64_C(0x0b0b0b0b0b0b0b0b), INT64_C(0x1b1b1b1b1b1b1b1b)),
      MakeM128(UINT64_C(0x0c0c0c0c0c0c0c0c), INT64_C(0x1c1c1c1c1c1c1c1c)),
      MakeM128(UINT64_C(0x0d0d0d0d0d0d0d0d), INT64_C(0x1d1d1d1d1d1d1d1d)),
      MakeM128(UINT64_C(0x0e0e0e0e0e0e0e0e), INT64_C(0x1e1e1e1e1e1e1e1e)),
      MakeM128(UINT64_C(0x0f0f0f0f0f0f0f0f), INT64_C(0x1f1f1f1f1f1f1f1f)),
  };
  for (size_t index = 0; index < 10u; ++index) {
    StoreM128(entry_rsp - 184u + index * 16u, saved_xmms[index]);
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
      context.Xmm12 = context.Xmm13 = context.Xmm14 = context.Xmm15 =
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
  Expect(EqualM128(context.Xmm12, saved_xmms[6]), "variable-stack unwind restores XMM12");
  Expect(EqualM128(context.Xmm13, saved_xmms[7]), "variable-stack unwind restores XMM13");
  Expect(EqualM128(context.Xmm14, saved_xmms[8]), "variable-stack unwind restores XMM14");
  Expect(EqualM128(context.Xmm15, saved_xmms[9]), "variable-stack unwind restores XMM15");

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
      return_context.Xmm10 = return_context.Xmm11 = return_context.Xmm12 =
          return_context.Xmm13 = return_context.Xmm14 = return_context.Xmm15 =
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
             EqualM128(return_context.Xmm11, saved_xmms[5]) &&
             EqualM128(return_context.Xmm12, saved_xmms[6]) &&
             EqualM128(return_context.Xmm13, saved_xmms[7]) &&
             EqualM128(return_context.Xmm14, saved_xmms[8]) &&
             EqualM128(return_context.Xmm15, saved_xmms[9]),
         "return-range unwind restores XMM6-XMM15");

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
  epilogue_context.Xmm12 = saved_xmms[6];
  epilogue_context.Xmm13 = saved_xmms[7];
  epilogue_context.Xmm14 = saved_xmms[8];
  epilogue_context.Xmm15 = saved_xmms[9];
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
             EqualM128(epilogue_context.Xmm11, saved_xmms[5]) &&
             EqualM128(epilogue_context.Xmm12, saved_xmms[6]) &&
             EqualM128(epilogue_context.Xmm13, saved_xmms[7]) &&
             EqualM128(epilogue_context.Xmm14, saved_xmms[8]) &&
             EqualM128(epilogue_context.Xmm15, saved_xmms[9]),
         "epilogue unwind preserves already-restored XMM registers");

  std::cout << "win32_osr_unwind_probe failures=" << g_failures
            << " prologue=" << static_cast<unsigned>(prologue_size)
            << " entry_frame_offset=" << static_cast<unsigned>(frame_offset) * 16u
            << " return_prologue=0"
            << " fixed_frame=248"
            << " xmm_count=10"
            << " invoke_records=2"
            << " variable_rsp_delta=" << fixed_rsp - variable_rsp << '\n';
  if (g_failures == 0) {
    std::cout << "win32_osr_unwind_probe OK\n";
  }
  FreeLibrary(art);
  return g_failures == 0 ? 0 : 1;
}
