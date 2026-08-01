#include <windows.h>
#include <dbghelp.h>

#include <stdint.h>

#include <cstring>
#include <iostream>
#include <string>

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

class ArtSymbols {
 public:
  explicit ArtSymbols(HMODULE art) : art_(art), process_(GetCurrentProcess()) {
    SymSetOptions(SymGetOptions() | SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME);
    initialized_ = SymInitializeW(process_, nullptr, FALSE) != FALSE;
    Expect(initialized_, "DbgHelp initializes a private symbol session");
    if (!initialized_) {
      return;
    }

    wchar_t image_path[32768] = {};
    DWORD length = GetModuleFileNameW(art_, image_path, 32768u);
    Expect(length != 0u && length < 32768u, "art.dll image path resolves");
    if (length == 0u || length >= 32768u) {
      return;
    }
    loaded_base_ = SymLoadModuleExW(process_,
                                    nullptr,
                                    image_path,
                                    L"art",
                                    reinterpret_cast<DWORD64>(art_),
                                    0u,
                                    nullptr,
                                    0u);
    Expect(loaded_base_ == reinterpret_cast<DWORD64>(art_),
           "DbgHelp loads the adjacent art.pdb");
  }

  ArtSymbols(const ArtSymbols&) = delete;
  ArtSymbols& operator=(const ArtSymbols&) = delete;

  ~ArtSymbols() {
    if (initialized_) {
      SymCleanup(process_);
    }
  }

  uint8_t* Resolve(const wchar_t* name, const char* label) const {
    if (loaded_base_ == 0u) {
      return nullptr;
    }
    SYMBOL_INFO_PACKAGEW package = {};
    package.si.SizeOfStruct = sizeof(SYMBOL_INFOW);
    package.si.MaxNameLen = MAX_SYM_NAME;
    std::wstring qualified = L"art!";
    qualified.append(name);
    const bool found = SymFromNameW(process_, qualified.c_str(), &package.si) != FALSE;
    ExpectForSymbol(found, label, "PDB symbol resolves");
    if (!found) {
      return nullptr;
    }
    ExpectForSymbol(package.si.ModBase == reinterpret_cast<DWORD64>(art_),
                    label,
                    "PDB symbol belongs to art.dll");
    return package.si.ModBase == reinterpret_cast<DWORD64>(art_)
               ? reinterpret_cast<uint8_t*>(package.si.Address)
               : nullptr;
  }

 private:
  HMODULE art_;
  HANDLE process_;
  bool initialized_ = false;
  DWORD64 loaded_base_ = 0u;
};

void TestInvokeUnwind(const ArtSymbols& symbols, const wchar_t* name, const char* label) {
  auto* entry = symbols.Resolve(name, label);
  ExpectForSymbol(entry != nullptr, label, "address resolves");
  if (entry == nullptr) {
    return;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
  ExpectForSymbol(function != nullptr, label, "runtime-function entry resolves");
  if (function == nullptr) {
    return;
  }
  const uint8_t* unwind = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  const uint8_t prologue_size = unwind[1];
  ExpectForSymbol(prologue_size != 0u, label, "prologue is nonempty");
  ExpectForSymbol((unwind[3] & 0x0fu) == 5u, label, "frame register is RBP");

  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  VirtualStack stack(system_info.dwPageSize);
  ExpectForSymbol(stack.address != nullptr, label, "synthetic stack allocation succeeds");
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
  ExpectForSymbol(context.Rip == kReturnAddress, label, "restores return address");
  ExpectForSymbol(context.Rsp == entry_rsp + 8u, label, "restores caller RSP");
  ExpectForSymbol(context.Rbp == kRbp && context.Rdi == kRdi && context.Rsi == kRsi &&
                      context.Rbx == kRbx && context.R12 == kR12 && context.R13 == kR13 &&
                      context.R14 == kR14 && context.R15 == kR15,
                  label,
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
  ExpectForSymbol(xmms_match, label, "restores XMM6-XMM15");
}

size_t TestGenericJniUnwind(const ArtSymbols& symbols) {
  constexpr const char* kSymbol = "art_quick_generic_jni_trampoline";
  auto* entry = symbols.Resolve(L"art_quick_generic_jni_trampoline", kSymbol);
  ExpectForSymbol(entry != nullptr, kSymbol, "address resolves");
  if (entry == nullptr) {
    return 0u;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
  ExpectForSymbol(function != nullptr, kSymbol, "runtime-function entry resolves");
  if (function == nullptr) {
    return 0u;
  }
  auto* function_begin = reinterpret_cast<uint8_t*>(image_base + function->BeginAddress);
  auto* function_end = reinterpret_cast<uint8_t*>(image_base + function->EndAddress);
  ExpectForSymbol(function_begin == entry, kSymbol, "runtime-function starts at symbol");
  ExpectForSymbol(function_end > function_begin, kSymbol, "runtime-function range is nonempty");

  const uint8_t* unwind = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  const uint8_t prologue_size = unwind[1];
  ExpectForSymbol((unwind[0] & 0x7u) == 1u, kSymbol, "unwind info uses version 1");
  ExpectForSymbol(prologue_size == 121u, kSymbol, "prologue covers the R12 anchor");
  ExpectForSymbol((unwind[3] & 0x0fu) == 12u, kSymbol, "frame register is R12");
  ExpectForSymbol((unwind[3] >> 4u) == 0u, kSymbol, "frame offset is zero");

  // This is the Windows x64 indirect native call and its return PC. The run-3
  // native stack captured the same return at trampoline + 0xc5.
  constexpr uint8_t kNativeCall[] = {
      0x41u, 0xffu, 0xd3u,              // call *%r11
      0x4cu, 0x89u, 0xffu,              // mov %r15, %rdi
  };
  uint8_t* native_call = FindBytes(function_begin, function_end, kNativeCall);
  ExpectForSymbol(native_call != nullptr, kSymbol, "native call return is found");
  if (native_call == nullptr) {
    return 0u;
  }
  uint8_t* native_return = native_call + 3u;
  const size_t native_return_offset = static_cast<size_t>(native_return - entry);
  ExpectForSymbol(native_return_offset == 0xc5u,
                  kSymbol,
                  "native call return matches captured offset");

  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  VirtualStack stack(static_cast<size_t>(system_info.dwPageSize) * 4u);
  ExpectForSymbol(stack.address != nullptr, kSymbol, "synthetic stack allocation succeeds");
  if (stack.address == nullptr) {
    return native_return_offset;
  }

  // Completed Windows x64 GenericJNI frame:
  //   88 bytes of pushes + 112-byte save area = 200-byte canonical frame;
  //   R12 anchors the additional 5120-byte reserved area;
  //   a no-stack-argument normal JNI call uses 32-byte shadow plus cookie and
  //   alignment, placing its variable native RSP 48 bytes below managed_sp.
  uintptr_t entry_rsp = reinterpret_cast<uintptr_t>(
      stack.address + static_cast<size_t>(system_info.dwPageSize) * 4u - 512u);
  entry_rsp = (entry_rsp & ~uintptr_t{15u}) + 8u;
  constexpr uintptr_t kCanonicalFrameSize = 200u;
  constexpr uintptr_t kReservedAreaSize = 5120u;
  constexpr uintptr_t kNativeCallAreaSize = 48u;
  const uintptr_t managed_sp = entry_rsp - kCanonicalFrameSize;
  const uintptr_t reserved_sp = managed_sp - kReservedAreaSize;
  const uintptr_t native_rsp = managed_sp - kNativeCallAreaSize;

  constexpr uint64_t kReturnAddress = UINT64_C(0x3456789abcdef012);
  constexpr uint64_t kRbp = UINT64_C(0x1020304050607080);
  constexpr uint64_t kRdi = UINT64_C(0x1122334455667788);
  constexpr uint64_t kRsi = UINT64_C(0x8877665544332211);
  constexpr uint64_t kRbx = UINT64_C(0x2233445566778899);
  constexpr uint64_t kR12 = UINT64_C(0x33445566778899aa);
  constexpr uint64_t kR13 = UINT64_C(0x445566778899aabb);
  constexpr uint64_t kR14 = UINT64_C(0x5566778899aabbcc);
  constexpr uint64_t kR15 = UINT64_C(0x66778899aabbccdd);

  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;
  *reinterpret_cast<uint64_t*>(entry_rsp - 8u) = kR15;
  *reinterpret_cast<uint64_t*>(entry_rsp - 16u) = kR14;
  *reinterpret_cast<uint64_t*>(entry_rsp - 24u) = kR13;
  *reinterpret_cast<uint64_t*>(entry_rsp - 32u) = kR12;
  *reinterpret_cast<uint64_t*>(entry_rsp - 40u) = UINT64_C(0x9192939495969798);
  *reinterpret_cast<uint64_t*>(entry_rsp - 48u) = UINT64_C(0x8182838485868788);
  *reinterpret_cast<uint64_t*>(entry_rsp - 56u) = kRsi;
  *reinterpret_cast<uint64_t*>(entry_rsp - 64u) = kRbp;
  *reinterpret_cast<uint64_t*>(entry_rsp - 72u) = kRbx;
  *reinterpret_cast<uint64_t*>(entry_rsp - 80u) = UINT64_C(0x7172737475767778);
  *reinterpret_cast<uint64_t*>(entry_rsp - 88u) = UINT64_C(0x6162636465666768);
  *reinterpret_cast<uint64_t*>(managed_sp) = kRdi;

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_FULL;
  context.Rip = reinterpret_cast<DWORD64>(native_return);
  context.Rsp = native_rsp;
  context.Rbp = context.Rbx = context.R13 = context.R14 = context.R15 =
      UINT64_C(0xcccccccccccccccc);
  context.Rdi = context.Rsi = UINT64_C(0xdddddddddddddddd);
  context.R12 = reserved_sp;

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
  ExpectForSymbol(context.Rip == kReturnAddress, kSymbol, "restores return address");
  ExpectForSymbol(context.Rsp == entry_rsp + 8u, kSymbol, "restores caller RSP");
  ExpectForSymbol(context.Rbp == kRbp, kSymbol, "restores RBP from variable native RSP");
  ExpectForSymbol(context.Rdi == kRdi, kSymbol, "restores RDI from variable native RSP");
  ExpectForSymbol(context.Rsi == kRsi, kSymbol, "restores RSI from variable native RSP");
  ExpectForSymbol(context.Rbx == kRbx, kSymbol, "restores RBX from variable native RSP");
  ExpectForSymbol(context.R12 == kR12, kSymbol, "restores R12 from variable native RSP");
  ExpectForSymbol(context.R13 == kR13, kSymbol, "restores R13 from variable native RSP");
  ExpectForSymbol(context.R14 == kR14, kSymbol, "restores R14 from variable native RSP");
  ExpectForSymbol(context.R15 == kR15, kSymbol, "restores R15 from variable native RSP");
  return native_return_offset;
}

size_t TestExecuteSwitchImplUnwind(const ArtSymbols& symbols) {
  constexpr const char* kSymbol = "ExecuteSwitchImplAsm";
  auto* entry = symbols.Resolve(L"ExecuteSwitchImplAsm", kSymbol);
  ExpectForSymbol(entry != nullptr, kSymbol, "address resolves");
  if (entry == nullptr) {
    return 0u;
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
  ExpectForSymbol(function != nullptr, kSymbol, "entry runtime-function record resolves");
  if (function == nullptr) {
    return 0u;
  }
  auto* function_begin = reinterpret_cast<uint8_t*>(image_base + function->BeginAddress);
  auto* function_end = reinterpret_cast<uint8_t*>(image_base + function->EndAddress);
  ExpectForSymbol(function_begin == entry, kSymbol, "runtime-function starts at symbol");
  ExpectForSymbol(function_end > function_begin, kSymbol, "runtime-function range is nonempty");

  const uint8_t* unwind = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  ExpectForSymbol((unwind[0] & 0x7u) == 1u, kSymbol, "unwind info uses version 1");
  ExpectForSymbol(unwind[1] == 5u, kSymbol, "prologue covers RBX save and home area");
  ExpectForSymbol((unwind[3] & 0x0fu) == 0u, kSymbol, "frame is RSP-based");

  constexpr uint8_t kCallAndEpilogue[] = {
      0xffu, 0xd6u,                    // call *%rsi
      0x48u, 0x83u, 0xc4u, 0x20u,     // add $32, %rsp
      0x5bu,                           // pop %rbx
      0xc3u,                           // ret
  };
  uint8_t* call = FindBytes(function_begin, function_end, kCallAndEpilogue);
  ExpectForSymbol(call != nullptr, kSymbol, "call and canonical epilogue are found");
  if (call == nullptr) {
    return 0u;
  }
  uint8_t* post_call = call + 2u;
  const size_t call_return_offset = static_cast<size_t>(post_call - entry);
  ExpectForSymbol(call_return_offset == 0xdu, kSymbol, "call return has expected offset");

  DWORD64 body_image_base = 0u;
  PRUNTIME_FUNCTION body_function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(call), &body_image_base, nullptr);
  ExpectForSymbol(body_function == function && body_image_base == image_base,
                  kSymbol,
                  "body resolves to the wrapper runtime-function record");
  DWORD64 epilogue_image_base = 0u;
  PRUNTIME_FUNCTION epilogue_function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(post_call), &epilogue_image_base, nullptr);
  ExpectForSymbol(epilogue_function == function && epilogue_image_base == image_base,
                  kSymbol,
                  "epilogue resolves to the wrapper runtime-function record");
  if (body_function == nullptr || epilogue_function == nullptr) {
    return call_return_offset;
  }

  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  VirtualStack stack(system_info.dwPageSize);
  ExpectForSymbol(stack.address != nullptr, kSymbol, "synthetic stack allocation succeeds");
  if (stack.address == nullptr) {
    return call_return_offset;
  }

  uintptr_t entry_rsp = reinterpret_cast<uintptr_t>(stack.address + system_info.dwPageSize - 512u);
  entry_rsp = (entry_rsp & ~uintptr_t{15u}) + 8u;
  const uintptr_t body_rsp = entry_rsp - 40u;
  constexpr uint64_t kReturnAddress = UINT64_C(0x456789abcdef0123);
  constexpr uint64_t kRbx = UINT64_C(0x3141592653589793);
  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;
  *reinterpret_cast<uint64_t*>(entry_rsp - 8u) = kRbx;

  CONTEXT body_context = {};
  body_context.ContextFlags = CONTEXT_FULL;
  body_context.Rip = reinterpret_cast<DWORD64>(call);
  body_context.Rsp = body_rsp;
  body_context.Rbx = UINT64_C(0xcccccccccccccccc);
  PVOID handler_data = nullptr;
  DWORD64 establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   body_image_base,
                   body_context.Rip,
                   body_function,
                   &body_context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  ExpectForSymbol(body_context.Rip == kReturnAddress, kSymbol, "body restores return address");
  ExpectForSymbol(body_context.Rsp == entry_rsp + 8u, kSymbol, "body restores caller RSP");
  ExpectForSymbol(body_context.Rbx == kRbx, kSymbol, "body restores RBX");

  CONTEXT epilogue_context = {};
  epilogue_context.ContextFlags = CONTEXT_FULL;
  epilogue_context.Rip = reinterpret_cast<DWORD64>(post_call);
  epilogue_context.Rsp = body_rsp;
  epilogue_context.Rbx = UINT64_C(0xdddddddddddddddd);
  handler_data = nullptr;
  establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   epilogue_image_base,
                   epilogue_context.Rip,
                   epilogue_function,
                   &epilogue_context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  ExpectForSymbol(epilogue_context.Rip == kReturnAddress,
                  kSymbol,
                  "epilogue restores return address");
  ExpectForSymbol(epilogue_context.Rsp == entry_rsp + 8u,
                  kSymbol,
                  "epilogue restores caller RSP");
  ExpectForSymbol(epilogue_context.Rbx == kRbx, kSymbol, "epilogue restores RBX");
  return call_return_offset;
}

struct InterpreterBridgeUnwindResult {
  size_t call_return_offset;
  size_t pending_offset;
};

InterpreterBridgeUnwindResult TestInterpreterBridgeUnwind(const ArtSymbols& symbols) {
  constexpr const char* kSymbol = "art_quick_to_interpreter_bridge";
  auto* entry = symbols.Resolve(L"art_quick_to_interpreter_bridge", kSymbol);
  ExpectForSymbol(entry != nullptr, kSymbol, "address resolves");
  if (entry == nullptr) {
    return {};
  }

  DWORD64 image_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
  ExpectForSymbol(function != nullptr, kSymbol, "primary runtime-function record resolves");
  if (function == nullptr) {
    return {};
  }
  auto* function_begin = reinterpret_cast<uint8_t*>(image_base + function->BeginAddress);
  auto* function_end = reinterpret_cast<uint8_t*>(image_base + function->EndAddress);
  ExpectForSymbol(function_begin == entry, kSymbol, "primary range starts at symbol");
  ExpectForSymbol(function_end > function_begin, kSymbol, "primary range is nonempty");

  const uint8_t* unwind = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  ExpectForSymbol((unwind[0] & 0x7u) == 1u, kSymbol, "primary unwind info uses version 1");
  ExpectForSymbol(unwind[1] == 21u, kSymbol, "primary prologue covers the 200-byte frame");
  ExpectForSymbol((unwind[3] & 0x0fu) == 0u, kSymbol, "primary frame is RSP-based");

  constexpr size_t kCallReturnOffset = 0x82u;
  uint8_t* call_return = entry + kCallReturnOffset;
  constexpr uint8_t kPostCallRestore[] = {
      0xf3u, 0x0fu, 0x7eu, 0x44u, 0x24u, 0x10u,  // movq 16(%rsp), %xmm0
  };
  ExpectForSymbol(call_return[-5] == 0xe8u, kSymbol, "captured call is direct rel32");
  ExpectForSymbol(std::memcmp(call_return, kPostCallRestore, sizeof(kPostCallRestore)) == 0,
                  kSymbol,
                  "captured +0x82 return starts the restore sequence");

  constexpr uint8_t kFixedRestore[] = {
      0x48u, 0x8bu, 0x4cu, 0x24u, 0x70u,  // mov 112(%rsp), %rcx
  };
  uint8_t* fixed_restore = FindBytes(function_begin, function_end, kFixedRestore);
  ExpectForSymbol(fixed_restore != nullptr, kSymbol, "fixed-offset GPR restore is found");

  constexpr uint8_t kNormalEpilogue[] = {
      0x48u, 0x81u, 0xc4u, 0xc8u, 0x00u, 0x00u, 0x00u,  // add rsp, 200
      0xc3u,                                              // ret
  };
  uint8_t* normal_epilogue = FindBytes(function_begin, function_end, kNormalEpilogue);
  ExpectForSymbol(normal_epilogue != nullptr, kSymbol, "normal canonical epilogue is found");

  constexpr uint8_t kPendingEpilogue[] = {
      0x48u, 0x81u, 0xc4u, 0xc8u, 0x00u, 0x00u, 0x00u,  // add rsp, 200
      0xebu, 0x00u,                                       // jmp pending range
  };
  uint8_t* pending_epilogue = FindBytes(function_begin, function_end, kPendingEpilogue);
  ExpectForSymbol(pending_epilogue != nullptr, kSymbol, "pending tail epilogue is found");

  DWORD64 pending_image_base = 0u;
  PRUNTIME_FUNCTION pending_function = RtlLookupFunctionEntry(
      reinterpret_cast<DWORD64>(function_end), &pending_image_base, nullptr);
  ExpectForSymbol(pending_function != nullptr, kSymbol, "pending runtime-function record resolves");
  ExpectForSymbol(pending_function != function, kSymbol, "pending range has a distinct record");
  ExpectForSymbol(pending_image_base == image_base, kSymbol, "pending range belongs to art.dll");
  if (pending_function == nullptr) {
    return {kCallReturnOffset, static_cast<size_t>(function_end - entry)};
  }
  auto* pending_begin =
      reinterpret_cast<uint8_t*>(pending_image_base + pending_function->BeginAddress);
  auto* pending_end =
      reinterpret_cast<uint8_t*>(pending_image_base + pending_function->EndAddress);
  const size_t pending_offset = static_cast<size_t>(pending_begin - entry);
  ExpectForSymbol(pending_begin == function_end, kSymbol, "pending range is contiguous");
  ExpectForSymbol(pending_offset == 0x140u, kSymbol, "pending range starts at expected offset");
  ExpectForSymbol(pending_end > pending_begin, kSymbol, "pending range is nonempty");
  const uint8_t* pending_unwind =
      reinterpret_cast<const uint8_t*>(pending_image_base + pending_function->UnwindData);
  ExpectForSymbol((pending_unwind[0] & 0x7u) == 1u,
                  kSymbol,
                  "pending unwind info uses version 1");
  ExpectForSymbol(pending_unwind[1] == 21u,
                  kSymbol,
                  "pending prologue covers the 88-byte frame");
  ExpectForSymbol((pending_unwind[3] & 0x0fu) == 0u,
                  kSymbol,
                  "pending frame is RSP-based");

  SYSTEM_INFO system_info = {};
  GetSystemInfo(&system_info);
  VirtualStack stack(system_info.dwPageSize);
  ExpectForSymbol(stack.address != nullptr, kSymbol, "synthetic stack allocation succeeds");
  if (stack.address == nullptr || fixed_restore == nullptr || normal_epilogue == nullptr ||
      pending_epilogue == nullptr) {
    return {kCallReturnOffset, pending_offset};
  }

  uintptr_t entry_rsp = reinterpret_cast<uintptr_t>(stack.address + system_info.dwPageSize - 512u);
  entry_rsp = (entry_rsp & ~uintptr_t{15u}) + 8u;
  constexpr uintptr_t kPrimaryFrameSize = 200u;
  constexpr uintptr_t kPendingFrameSize = 88u;
  const uintptr_t primary_rsp = entry_rsp - kPrimaryFrameSize;
  const uintptr_t pending_rsp = entry_rsp - kPendingFrameSize;

  constexpr uint64_t kReturnAddress = UINT64_C(0x56789abcdef01234);
  constexpr uint64_t kRbp = UINT64_C(0x1020304050607080);
  constexpr uint64_t kRsi = UINT64_C(0x1122334455667788);
  constexpr uint64_t kRbx = UINT64_C(0x2233445566778899);
  constexpr uint64_t kR12 = UINT64_C(0x33445566778899aa);
  constexpr uint64_t kR13 = UINT64_C(0x445566778899aabb);
  constexpr uint64_t kR14 = UINT64_C(0x5566778899aabbcc);
  constexpr uint64_t kR15 = UINT64_C(0x66778899aabbccdd);

  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;
  *reinterpret_cast<uint64_t*>(primary_rsp + 128u) = kRbx;
  *reinterpret_cast<uint64_t*>(primary_rsp + 136u) = kRbp;
  *reinterpret_cast<uint64_t*>(primary_rsp + 144u) = kRsi;
  *reinterpret_cast<uint64_t*>(primary_rsp + 168u) = kR12;
  *reinterpret_cast<uint64_t*>(primary_rsp + 176u) = kR13;
  *reinterpret_cast<uint64_t*>(primary_rsp + 184u) = kR14;
  *reinterpret_cast<uint64_t*>(primary_rsp + 192u) = kR15;

  auto expect_caller = [&](const CONTEXT& context, const char* point) {
    ExpectForSymbol(context.Rip == kReturnAddress, kSymbol, point);
    ExpectForSymbol(context.Rsp == entry_rsp + 8u, kSymbol, "restores caller RSP");
    ExpectForSymbol(context.Rbp == kRbp && context.Rsi == kRsi && context.Rbx == kRbx &&
                        context.R12 == kR12 && context.R13 == kR13 && context.R14 == kR14 &&
                        context.R15 == kR15,
                    kSymbol,
                    "restores primary nonvolatile GPRs");
  };
  auto unwind_primary = [&](uint8_t* pc, const char* point) {
    CONTEXT context = {};
    context.ContextFlags = CONTEXT_FULL;
    context.Rip = reinterpret_cast<DWORD64>(pc);
    context.Rsp = primary_rsp;
    context.Rbp = context.Rsi = context.Rbx = context.R12 = context.R13 = context.R14 =
        context.R15 = UINT64_C(0xcccccccccccccccc);
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
    expect_caller(context, point);
  };
  unwind_primary(call_return, "call-return unwind restores return address");
  unwind_primary(fixed_restore, "fixed-restore unwind restores return address");

  CONTEXT entry_context = {};
  entry_context.ContextFlags = CONTEXT_FULL;
  entry_context.Rip = reinterpret_cast<DWORD64>(entry);
  entry_context.Rsp = entry_rsp;
  entry_context.Rbp = kRbp;
  entry_context.Rsi = kRsi;
  entry_context.Rbx = kRbx;
  entry_context.R12 = kR12;
  entry_context.R13 = kR13;
  entry_context.R14 = kR14;
  entry_context.R15 = kR15;
  PVOID handler_data = nullptr;
  DWORD64 establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   image_base,
                   entry_context.Rip,
                   function,
                   &entry_context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  expect_caller(entry_context, "entry unwind restores return address");

  for (uint8_t* epilogue : {normal_epilogue, pending_epilogue}) {
    CONTEXT epilogue_context = {};
    epilogue_context.ContextFlags = CONTEXT_FULL;
    epilogue_context.Rip = reinterpret_cast<DWORD64>(epilogue);
    epilogue_context.Rsp = primary_rsp;
    epilogue_context.Rbp = kRbp;
    epilogue_context.Rsi = kRsi;
    epilogue_context.Rbx = kRbx;
    epilogue_context.R12 = kR12;
    epilogue_context.R13 = kR13;
    epilogue_context.R14 = kR14;
    epilogue_context.R15 = kR15;
    handler_data = nullptr;
    establisher_frame = 0u;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                     image_base,
                     epilogue_context.Rip,
                     function,
                     &epilogue_context,
                     &handler_data,
                     &establisher_frame,
                     nullptr);
    expect_caller(epilogue_context, "epilogue unwind restores return address");
  }

  *reinterpret_cast<uint64_t*>(pending_rsp + 40u) = kRbx;
  *reinterpret_cast<uint64_t*>(pending_rsp + 48u) = kRbp;
  *reinterpret_cast<uint64_t*>(pending_rsp + 56u) = kR12;
  *reinterpret_cast<uint64_t*>(pending_rsp + 64u) = kR13;
  *reinterpret_cast<uint64_t*>(pending_rsp + 72u) = kR14;
  *reinterpret_cast<uint64_t*>(pending_rsp + 80u) = kR15;
  CONTEXT pending_context = {};
  pending_context.ContextFlags = CONTEXT_FULL;
  pending_context.Rip = reinterpret_cast<DWORD64>(pending_begin + pending_unwind[1]);
  pending_context.Rsp = pending_rsp;
  pending_context.Rbp = pending_context.Rbx = pending_context.R12 = pending_context.R13 =
      pending_context.R14 = pending_context.R15 = UINT64_C(0xdddddddddddddddd);
  handler_data = nullptr;
  establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   pending_image_base,
                   pending_context.Rip,
                   pending_function,
                   &pending_context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  ExpectForSymbol(pending_context.Rip == kReturnAddress,
                  kSymbol,
                  "pending body restores return address");
  ExpectForSymbol(pending_context.Rsp == entry_rsp + 8u,
                  kSymbol,
                  "pending body restores caller RSP");
  ExpectForSymbol(pending_context.Rbp == kRbp && pending_context.Rbx == kRbx &&
                      pending_context.R12 == kR12 && pending_context.R13 == kR13 &&
                      pending_context.R14 == kR14 && pending_context.R15 == kR15,
                  kSymbol,
                  "pending body restores nonvolatile GPRs");
  return {kCallReturnOffset, pending_offset};
}

}  // namespace

int main() {
  HMODULE art = LoadLibraryW(L"art.dll");
  Expect(art != nullptr, "art.dll loads");
  if (art == nullptr) {
    std::cerr << "LoadLibraryW error=" << GetLastError() << '\n';
    return 1;
  }

  ArtSymbols symbols(art);
  TestInvokeUnwind(symbols, L"art_quick_invoke_stub", "art_quick_invoke_stub");
  TestInvokeUnwind(
      symbols, L"art_quick_invoke_static_stub", "art_quick_invoke_static_stub");
  const size_t generic_jni_native_return = TestGenericJniUnwind(symbols);
  const size_t switch_impl_call_return = TestExecuteSwitchImplUnwind(symbols);
  const InterpreterBridgeUnwindResult interpreter_bridge = TestInterpreterBridgeUnwind(symbols);

  auto* osr = symbols.Resolve(L"art_quick_osr_stub", "art_quick_osr_stub");
  Expect(osr != nullptr, "art_quick_osr_stub address resolves");
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
  Expect(function_begin == osr, "runtime-function entry starts at the OSR symbol");
  Expect(function_end > function_begin, "runtime-function range is nonempty");

  const uint8_t* unwind_info = reinterpret_cast<const uint8_t*>(image_base + function->UnwindData);
  const uint8_t version = unwind_info[0] & 0x7u;
  const uint8_t prologue_size = unwind_info[1];
  const uint8_t frame_register = unwind_info[3] & 0x0fu;
  const uint8_t frame_offset = unwind_info[3] >> 4u;
  Expect(version == 1u, "OSR unwind info uses version 1");
  Expect(prologue_size != 0u && function_begin + prologue_size < function_end,
         "OSR unwind prologue size is in range");
  Expect(frame_register == 12u, "OSR unwind frame register is R12");
  Expect(frame_offset == 0u, "OSR unwind frame offset is zero");

  // Select an instruction after the variable RSP subtraction. This proves the
  // PE record recovers the fixed frame through R12 instead of trusting RSP or
  // the RBP value reserved for the copied JIT frame.
  constexpr uint8_t kVariableBody[] = {
      0x83u, 0xe9u, 0x08u,              // sub ecx, 8
      0x48u, 0x29u, 0xccu,              // sub rsp, rcx
      0x48u, 0x89u, 0xe7u,              // mov rdi, rsp
      0xf3u, 0xa4u,                     // rep movsb
      0x48u, 0x89u, 0xe5u,              // mov rbp, rsp
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
  context.Rip = reinterpret_cast<DWORD64>(variable_body + 11u);
  context.Rsp = variable_rsp;
  context.Rbp = UINT64_C(0xbbbbbbbbbbbbbbbb);
  context.R12 = fixed_rsp;
  context.Rbx = context.R13 = context.R14 = context.R15 = UINT64_C(0xcccccccccccccccc);
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
            << " entry_frame_register=R12"
            << " compiled_frame_register=RBP"
            << " entry_frame_offset=" << static_cast<unsigned>(frame_offset) * 16u
            << " return_prologue=0"
            << " fixed_frame=248"
            << " xmm_count=10"
            << " invoke_records=2"
            << " generic_jni_records=1"
            << " generic_jni_native_return=0x" << std::hex << generic_jni_native_return
            << std::dec
            << " switch_impl_records=1"
            << " switch_impl_call_return=0x" << std::hex << switch_impl_call_return
            << std::dec
            << " interpreter_bridge_records=2"
            << " interpreter_bridge_call_return=0x" << std::hex
            << interpreter_bridge.call_return_offset
            << " interpreter_bridge_pending=0x" << interpreter_bridge.pending_offset
            << std::dec
            << " interpreter_bridge_frame=200"
            << " interpreter_bridge_pending_frame=88"
            << " variable_rsp_delta=" << fixed_rsp - variable_rsp << '\n';
  if (g_failures == 0) {
    std::cout << "win32_osr_unwind_probe OK\n";
  }
  FreeLibrary(art);
  return g_failures == 0 ? 0 : 1;
}
