#include <stdint.h>

#include <initializer_list>
#include <iostream>
#include <string_view>
#include <vector>

#include "utils/x86_64/windows_x64_unwind_info.h"

namespace {

using art::x86_64::WindowsX64UnwindInfoBuilder;

int g_failures = 0;
int g_cases = 0;

void Expect(bool condition, std::string_view message) {
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    ++g_failures;
  }
}

void ExpectBytes(const std::vector<uint8_t>& actual,
                 std::initializer_list<uint8_t> expected,
                 std::string_view message) {
  Expect(actual == std::vector<uint8_t>(expected), message);
}

void TestEmpty() {
  ++g_cases;
  WindowsX64UnwindInfoBuilder builder;
  builder.Enable();
  builder.Finalize(/*prologue_size=*/ 0u);
  Expect(builder.IsValid(), "empty descriptor is valid");
  ExpectBytes(builder.GetData(), {1u, 0u, 0u, 0u, 0u, 0u, 0u, 0u},
              "empty descriptor has the required eight-byte extent");
}

void TestAnchoredSmallFrame() {
  ++g_cases;
  WindowsX64UnwindInfoBuilder builder;
  builder.Enable();
  builder.RecordPushNonvolatile(/*RBX=*/ 3u, /*code_offset=*/ 1u);
  builder.RecordPushNonvolatile(/*RBP=*/ 5u, /*code_offset=*/ 2u);
  builder.RecordPushNonvolatile(/*R12=*/ 12u, /*code_offset=*/ 4u);
  builder.RecordStackAllocation(/*size=*/ 40u, /*code_offset=*/ 8u);
  builder.RecordSetFramePointer(/*RBP=*/ 5u, /*scaled_offset=*/ 0u, /*code_offset=*/ 11u);
  builder.Finalize(/*prologue_size=*/ 11u);
  Expect(builder.IsValid(), "anchored small frame is valid");
  ExpectBytes(builder.GetData(),
              {1u, 11u, 5u, 5u,
               11u, 0x03u,
               8u, 0x42u,
               4u, 0xc0u,
               2u, 0x50u,
               1u, 0x30u,
               0u, 0u},
              "anchored small frame uses descending offsets and ALLOC_SMALL");
}

void TestLargeAllocations() {
  ++g_cases;
  WindowsX64UnwindInfoBuilder scaled;
  scaled.Enable();
  scaled.RecordStackAllocation(/*size=*/ 512u, /*code_offset=*/ 4u);
  scaled.Finalize(/*prologue_size=*/ 4u);
  Expect(scaled.IsValid(), "scaled ALLOC_LARGE frame is valid");
  ExpectBytes(scaled.GetData(), {1u, 4u, 2u, 0u, 4u, 0x01u, 64u, 0u},
              "512-byte frame uses scaled ALLOC_LARGE");

  WindowsX64UnwindInfoBuilder unscaled;
  unscaled.Enable();
  unscaled.RecordStackAllocation(/*size=*/ 0x80000u, /*code_offset=*/ 7u);
  unscaled.Finalize(/*prologue_size=*/ 7u);
  Expect(unscaled.IsValid(), "unscaled ALLOC_LARGE frame is valid");
  ExpectBytes(unscaled.GetData(),
              {1u, 7u, 3u, 0u,
               7u, 0x11u,
               0u, 0u,
               8u, 0u,
               0u, 0u},
              "large frame uses unscaled 32-bit ALLOC_LARGE and slot padding");
}

void TestEveryNonvolatileGpr() {
  ++g_cases;
  constexpr uint8_t kNonvolatileRegisters[] = {3u, 5u, 6u, 7u, 12u, 13u, 14u, 15u};
  for (uint8_t reg : kNonvolatileRegisters) {
    WindowsX64UnwindInfoBuilder builder;
    builder.Enable();
    builder.RecordPushNonvolatile(reg, /*code_offset=*/ 2u);
    builder.Finalize(/*prologue_size=*/ 2u);
    Expect(builder.IsValid(), "nonvolatile push is valid");
    Expect(builder.GetData().size() == 8u, "single push descriptor is eight bytes");
    if (builder.GetData().size() == 8u) {
      Expect(builder.GetData()[4] == 2u, "push retains its instruction-end offset");
      Expect(builder.GetData()[5] == static_cast<uint8_t>(reg << 4),
             "push uses the PE register number as OpInfo");
    }
  }
}

void TestFixedRspCriticalNativeShape() {
  ++g_cases;
  WindowsX64UnwindInfoBuilder builder;
  builder.Enable();
  builder.RecordStackAllocation(/*size=*/ 72u, /*code_offset=*/ 4u);
  builder.Finalize(/*prologue_size=*/ 4u);
  Expect(builder.IsValid(), "fixed-RSP CriticalNative descriptor is valid");
  ExpectBytes(builder.GetData(), {1u, 4u, 1u, 0u, 4u, 0x82u, 0u, 0u},
              "CriticalNative descriptor has no frame register");
}

void TestNonvolatileXmmSaves() {
  ++g_cases;
  WindowsX64UnwindInfoBuilder builder;
  builder.Enable();
  builder.RecordStackAllocation(/*size=*/ 64u, /*code_offset=*/ 4u);
  builder.RecordSaveXmm128(/*XMM12=*/ 12u, /*stack_offset=*/ 32u, /*code_offset=*/ 10u);
  builder.RecordSaveXmm128(/*XMM15=*/ 15u, /*stack_offset=*/ 24u, /*code_offset=*/ 16u);
  builder.Finalize(/*prologue_size=*/ 16u);
  Expect(builder.IsValid(), "nonvolatile XMM saves are valid");
  ExpectBytes(builder.GetData(),
              {1u, 16u, 6u, 0u,
               16u, 0xf9u, 24u, 0u, 0u, 0u,
               10u, 0xc8u, 2u, 0u,
               4u, 0x72u},
              "XMM saves select scaled and far encodings and descending offsets");
}

template <typename Fn>
void ExpectInvalid(Fn fn, std::string_view message) {
  WindowsX64UnwindInfoBuilder builder;
  builder.Enable();
  fn(&builder);
  builder.Finalize(/*prologue_size=*/ 255u);
  Expect(!builder.IsValid(), message);
  Expect(builder.GetData().empty(), "invalid descriptor exposes no bytes");
}

void TestInvalidInputs() {
  ++g_cases;
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordPushNonvolatile(/*RAX=*/ 0u, 1u);
  }, "volatile GPR push is rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordStackAllocation(/*size=*/ 12u, 1u);
  }, "unaligned allocation is rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordPushNonvolatile(/*RBX=*/ 3u, 2u);
    builder->RecordPushNonvolatile(/*RBP=*/ 5u, 1u);
  }, "non-increasing code offsets are rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordPushNonvolatile(/*RBX=*/ 3u, 1u);
    builder->RecordPushNonvolatile(/*RBX=*/ 3u, 2u);
  }, "duplicate GPR saves are rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordStackAllocation(8u, 1u);
    builder->RecordStackAllocation(8u, 2u);
  }, "duplicate fixed allocations are rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordSetFramePointer(/*RAX=*/ 0u, 0u, 1u);
  }, "volatile frame register is rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordSaveXmm128(/*XMM5=*/ 5u, /*stack_offset=*/ 16u, /*code_offset=*/ 1u);
  }, "volatile XMM save is rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordSaveXmm128(/*XMM12=*/ 12u, /*stack_offset=*/ 16u, /*code_offset=*/ 1u);
    builder->RecordSaveXmm128(/*XMM12=*/ 12u, /*stack_offset=*/ 32u, /*code_offset=*/ 2u);
  }, "duplicate XMM saves are rejected");
  ExpectInvalid([](WindowsX64UnwindInfoBuilder* builder) {
    builder->RecordPushNonvolatile(/*RBX=*/ 3u, 256u);
  }, "operation beyond byte-sized prologue is rejected");

  WindowsX64UnwindInfoBuilder short_prologue;
  short_prologue.Enable();
  short_prologue.RecordPushNonvolatile(/*RBX=*/ 3u, 2u);
  short_prologue.Finalize(/*prologue_size=*/ 1u);
  Expect(!short_prologue.IsValid(), "operation beyond final prologue is rejected");

  WindowsX64UnwindInfoBuilder long_prologue;
  long_prologue.Enable();
  long_prologue.Finalize(/*prologue_size=*/ 256u);
  Expect(!long_prologue.IsValid(), "prologue beyond 255 bytes is rejected");

  WindowsX64UnwindInfoBuilder double_finalize;
  double_finalize.Enable();
  double_finalize.Finalize(/*prologue_size=*/ 0u);
  double_finalize.Finalize(/*prologue_size=*/ 0u);
  Expect(!double_finalize.IsValid(), "descriptor cannot be finalized twice");
}

}  // namespace

int main() {
  TestEmpty();
  TestAnchoredSmallFrame();
  TestLargeAllocations();
  TestEveryNonvolatileGpr();
  TestFixedRspCriticalNativeShape();
  TestNonvolatileXmmSaves();
  TestInvalidInputs();
  std::cout << "win32_jit_unwind_info_probe failures=" << g_failures
            << " cases=" << g_cases << '\n';
  if (g_failures == 0) {
    std::cout << "win32_jit_unwind_info_probe OK\n";
  }
  return g_failures == 0 ? 0 : 1;
}
