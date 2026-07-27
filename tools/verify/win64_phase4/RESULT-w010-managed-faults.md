# W-010 Stage D managed-fault activation

**Status:** focused Wine and Linux managed-fault verification PASS; static
fatal-unwind boundaries PASS locally; dynamic-JIT PE unwind and native Windows
Stage E acceptance remain
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
- Complete Phase-4 Wine aggregate, including the new gate: PASS.
- Foreign-VEH ordering before/after ART, best-effort promotion, continue-search
  behavior, and frame-based SEH for an unrecognized AV: PASS.
- Static `-Xint` JNI native AV: emitted unwind audit passes for the two invoke
  stubs and generic JNI trampoline; the crash reaches initial VEH and UEF and
  creates a new valid `MDMP` minidump.
- JIT smoke: 12/12 PASS.
- Phase-3 GoldenApp: PASS.
- Linux full `art`/`dalvikvm` rebuild with `-j32`: PASS.
- Linux `dalvikvm -showversion`: PASS.
- Linux shared-boot imageless Hello: PASS.

## Native Stage E still required

Wine is development evidence, not native acceptance. Native Windows 10/current
Windows must still cover repeated nterp/JIT NPE/SOE, debugger first-chance
continue, foreign VEH before/after/promotion, frame-based SEH for unrecognized
AV, exact wrong-address negatives, handler stack high-water, fatal predecessor
UEF/minidump behavior, and the HSP-disabled plus forced-policy matrix.

The static fatal result is not universal JIT-origin crash support. Recursive
`RtlVirtualUnwind2` tracing shows that threshold-zero JIT code currently has no
Windows runtime-function entry; leaf unwinding can corrupt the dispatch walk
before UEF. Per-method or range-accurate JIT unwind registration, concurrent
publication/removal rules, and code-cache teardown ownership remain a separate
required Stage E substage.
