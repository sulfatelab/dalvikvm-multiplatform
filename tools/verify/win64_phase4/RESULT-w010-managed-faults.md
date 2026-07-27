# W-010 Stage D managed-fault activation

**Status:** focused Wine and Linux managed-fault verification PASS; static
fatal-unwind boundaries PASS locally; dynamic-JIT frame anchoring and PE
serialization PASS locally; runtime registration and native Windows Stage E
acceptance remain
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
- Complete Phase-4 Wine aggregate, including the new serializer gate and the
  strengthened W-002 R15/RBP plus W-003 inline-XMM structural checks: PASS.
- Foreign-VEH ordering before/after ART, best-effort promotion, continue-search
  behavior, and frame-based SEH for an unrecognized AV: PASS.
- Static `-Xint` JNI native AV: emitted unwind audit passes for the two invoke
  stubs and generic JNI trampoline; the crash reaches initial VEH and UEF and
  creates a new valid `MDMP` minidump.
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

The static fatal result is not universal JIT-origin crash support. The first
compiler slice of the selected implementation is now present: optimizing
Win64 JIT methods force-spill and reserve RBP, establish it after their fixed
allocation, normal/FastNative JNI stubs use the same anchor, CriticalNative
keeps a fixed-RSP descriptor, and the assembler emits explicit version-1 PE
unwind bytes independently of debug CFI. Invalid or missing enabled metadata
rejects compilation before JIT allocation. `JniCompiledMethod` carries the
opaque bytes for the next stage.

Those bytes are not yet included in `JitCodeCache::Reserve()` data sizing or
registered with `RtlAddFunctionTable()`. Recursive `RtlVirtualUnwind2` tracing
therefore still sees no Windows runtime-function entry for threshold-zero JIT
code; leaf unwinding can corrupt the dispatch walk before UEF. The complete
design is documented in
[win32_faults_and_stacks.md](../../../win32_faults_and_stacks.md#79-dynamic-jit-pe-unwind-design):
a Windows-JIT-only fixed RBP anchor, explicit PE unwind bytes in the primary
JIT data view, one immutable `RtlAddFunctionTable()` entry per code allocation,
publication only after registration, and deletion before mspace reuse or
mapping teardown. Stage E must finish and stress the runtime half. It must also
extend native-to-managed boundary preservation from full-width XMM6-XMM11 to
XMM6-XMM15; ART's managed scalar XMM12-XMM15 preservation is only 64 bits and
does not by itself satisfy the Microsoft 128-bit nonvolatile contract. The OSR
stub also needs a static runtime-function record before fatal dispatch through
its variable copied-stack interval is supported.
