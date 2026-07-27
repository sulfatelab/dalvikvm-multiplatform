# W-010 Stage D managed-fault activation

**Status:** focused Wine and Linux managed-fault verification PASS; static and
dynamic JIT fatal-unwind dispatch PASS locally; dynamic-JIT frame anchoring,
PE serialization, xdata placement, runtime registration, collection/reuse
lifecycle, J-2/J-1 fatal dispatch, and split static OSR lookup/virtual-unwind
PASS; native Windows Stage E remains
**Date:** 2026-07-27

## Product behavior

Win64 x86_64 now uses ART's common implicit-null and implicit-stack-overflow
model:

- runtime initialization enables null and stack-overflow checks and keeps
  x86_64 implicit suspend checks disabled;
- `FaultManager` registers stack before null, matching Linux handler order;
- the main thread's W-014 fixed page exists before the managed VEH and handlers
  are published, and later non-AOT attachments install their page under the
  enabled flag;
- nterp's immutable code range is registered before `Runtime::Start()` can
  publish nterp entrypoints, despite Win64 deliberately keeping
  `CanRuntimeUseNterp()` false during early startup;
- JIT ranges retain common `Runtime::AddGeneratedCodeRange()` registration;
  and
- a normal started runtime rejects `-Xno-sig-chain` exactly as Linux does.
  Genuine non-started compiler/tool runtimes retain the option.

No Windows-only explicit null/stack check was added to nterp or optimizing
code. Successful faults still redirect through ART's common quick exception
entrypoints.

## Focused Wine gate

Command:

```bash
bash tools/verify/win64_phase4/run_w010_managed_fault_probe.sh
```

Result:

```text
W-010 -Xno-sig-chain started-runtime rejection PASS
W-010 managed fault nterp/npe PASS
W-010 managed fault nterp/so PASS
W-010 managed fault jit/npe PASS
W-010 managed fault jit/so PASS
W-010 managed fault acceptance: nterp and threshold-zero JIT NPE/SO: PASS
```

The Java probe verifies per execution mode:

- 64 caught implicit read NPEs;
- 64 caught implicit write NPEs;
- two caught main-thread SOEs;
- two caught SOEs on a newly created child thread; and
- 128 post-NPE and four post-SOE stack-trace/allocation/time recovery checks;
- 16 NPE-triggered and four SOE-triggered `System.gc()` calls; and
- a clean process exit after repeated page unprotect/reprotect cycles.

The JIT cases use zero warmup/compile thresholds and require successful compile
records for the faulting caller and recursive methods. The nterp cases disable
JIT and reject any compile record.

Handled NPE/SOE output is rejected if it contains `ART Win64 VEH`,
`ART Win64 UEF`, or a minidump marker. The gate snapshots
`run/crash/*.dmp` metadata before and after all handled-fault processes and
requires no change.

## Regression evidence

- Win64 `art` and `dalvikvm` incremental build with `-j32`: PASS.
- Win64 dynamic-JIT unwind serializer probe: 6/6 groups PASS, covering the
  minimum empty record, small and both large allocation forms, every legal
  nonvolatile GPR, an RBP-anchored frame, fixed-RSP CriticalNative shape,
  descending offsets, padding, and invalid-input rejection.
- Win64 runtime registry probe: add, exact lookup/base/range/xdata validation,
  generated-code execution, `RtlVirtualUnwind` control-state restoration,
  deletion, lookup disappearance, re-registration, and clear PASS.
- Win64 product lifecycle probe in J-2 and J-1: initial lookup, invalidation
  with metadata retained, one real code-cache collection, lookup disappearance,
  exact mspace code-address reuse, replacement registration, and replacement
  execution PASS.
- Complete Phase-4 Wine aggregate, including the new serializer gate and the
  strengthened W-002 R15/RBP plus W-003 inline-XMM structural checks: PASS.
- Foreign-VEH ordering before/after ART, best-effort promotion, continue-search
  behavior, and frame-based SEH for an unrecognized AV: PASS.
- Static `-Xint` JNI native AV: emitted unwind audit passes for the two invoke
  stubs and generic JNI trampoline; the crash reaches initial VEH and UEF and
  creates a new valid `MDMP` minidump.
- Static OSR unwind: the emitted audit verifies the RBP-anchored entry range
  and its contiguous zero-prologue RSP-based return range, including exact
  completed-frame XMM offsets. `run_osr_unwind_probe.sh` resolves both records,
  virtually unwinds from 256 bytes below the fixed frame, restores
  RBP/RDI/RSI/RBX/R12-R15 and XMM6-XMM15, repeats return unwinding with managed
  RBP deliberately clobbered, synthetically unwinds both invoke records, and
  verifies the canonical `add rsp,248; ret` epilogue. The real W-002 dual/J-1
  default/switch OSR matrix passes 8/8.
- Full-width Microsoft-XMM boundary sentinel: the Windows-only save area is
  160 bytes outside canonical ART frames; nterp, switch, and threshold-zero JIT
  each pass 2/2 with `mask=0`, retained historical `selfTestMask=63`, and
  authoritative `fullSelfTestMask=1023` for XMM6-XMM15.
- Threshold-zero JIT JNI native AV: the optimizing caller and JNI stub compile,
  both J-2 and J-1 reach initial VEH and UEF, and each run creates a changed or
  new valid `MDMP` minidump.
- JIT smoke: 12/12 PASS.
- Normal/FastNative mixed/high-FP compiled-JNI ABI: 7/7 targets PASS in both
  default and instrumentation modes after reserving RBP/R15 from JNI scratch.
- Focused CriticalNative regression with one repeat: J-2, J-1, `-Xint`, Linux
  interpreter, and Linux JIT PASS.
- Phase-3 GoldenApp: PASS.
- Linux `art` and `art-compiler` incremental build with `-j32`: PASS.
- Linux `dalvikvm -showversion`: PASS.
- Linux shared-boot imageless Hello: PASS.

## Native Stage E still required

Wine is development evidence, not native acceptance. Native Windows 10/current
Windows must still cover repeated nterp/JIT NPE/SOE, debugger first-chance
continue, foreign VEH before/after/promotion, frame-based SEH for unrecognized
AV, exact wrong-address negatives, handler stack high-water, fatal predecessor
UEF/minidump behavior, and the HSP-disabled plus forced-policy matrix.

The selected dynamic implementation is now present. Optimizing Win64 JIT
methods force-spill and reserve RBP and establish it after their fixed
allocation; normal/FastNative JNI stubs use the same anchor; CriticalNative
keeps a fixed-RSP descriptor; and the assembler emits explicit version-1 PE
unwind bytes independently of debug CFI. Invalid or missing enabled metadata
rejects compilation before JIT allocation.

`JitCodeCache::Reserve()` now sizes a DWORD-aligned xdata tail after roots and
stack maps. `Commit()` writes it through the RW data alias and registers one
stable immutable `RUNTIME_FUNCTION` before publishing any map or entrypoint.
`FreeLocked()` deletes that exact table before native debug-info removal and
mspace reuse; teardown clears every remaining registration before unmapping.
The complete design is documented in
[win32_faults_and_stacks.md](../../../win32_faults_and_stacks.md#79-dynamic-jit-pe-unwind-design):
a Windows-JIT-only fixed RBP anchor, explicit PE unwind bytes in the primary
JIT data view, one immutable `RtlAddFunctionTable()` entry per code allocation,
publication only after registration, and deletion before mspace reuse or
mapping teardown.

The threshold-zero gate proves Windows fatal dispatch reaches UEF and produces
a valid dump across the exercised optimizing/JIT-JNI path. It does not prove
debugger-quality minidump stack reconstruction or concurrent native sampling
under large dynamic-table churn. Stage E must cover those on native Windows,
repeat full-width XMM6-XMM15 normal-return and exception-unwind sentinels,
repeat both OSR runtime-function lookups/unwinds, and accept an OSR fatal path
before native fatal dispatch through its variable copied-stack interval is
supported.
