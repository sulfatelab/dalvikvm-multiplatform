# W-010 Stage D managed-fault activation

**Status:** unified native W-010 gate PASS; historical Wine/Linux verification
and W-010/W-014 E9, FS-1, and FS-2 native acceptance retained
**Date:** 2026-08-01

All future native reruns use the Windows Server 2025 build-26100 lab gate. The
former Windows 10 host is unavailable; older Windows 10 records below are
historical evidence only. See the
[native Windows gate policy](../../../win32_host_gate_policy.md).

## Unified stage acceptance

The shell-free `stage:w010` gate passed twice on the authoritative Windows
Server 2025 host. It runs six isolated cases: started-runtime
`-Xno-sig-chain` rejection, switch SOE, nterp NPE/SOE, and threshold-zero JIT
NPE/SOE. The NPE cases require 64 reads, 64 writes, 128 recovery checks, and 16
GC calls. The SOE cases require two main-thread and two child-thread catches,
four recovery checks, and four GC calls. JIT cases require the exact faulting
methods to compile; switch/nterp cases reject compilation records.

All handled cases exited zero, emitted no fatal VEH/UEF or minidump marker,
and created no dump. The deliberate no-sig-chain rejection satisfied its
declared nonzero exit contract. Aggregate JSON is path-sanitized. The final
native stage build and repeated Linux-hosted cross stage build were Ninja
no-ops.

## Product behavior

Windows x64 keeps ART's common implicit-null model and uses a narrow explicit
stack-overflow boundary check where Windows stack growth cannot preserve the
Linux fixed-page event:

- runtime initialization enables implicit null checks, disables Windows x64 common
  implicit stack checks, and keeps x86_64 implicit suspend checks disabled;
- Linux retains common stack-before-null `FaultManager` order; Windows x64 stack
  overflow is detected by explicit generated code before fault dispatch;
- every attaching thread has a verified stack guarantee of at least four
  system pages; any larger existing host guarantee is preserved;
- stack bounds debit the measured inaccessible low prefix, page-rounded
  configured guarantee, and one moving-guard page before common ART adds its
  8192-byte product recovery reserve; only non-`NDEBUG` Windows x86_64 uses
  the FS-1-measured 40-KiB reserve;
- nterp's immutable code range is registered before `Runtime::Start()` can
  publish nterp entrypoints, despite Windows x64 deliberately keeping
  `CanRuntimeUseNterp()` false during early startup;
- JIT ranges retain common `Runtime::AddGeneratedCodeRange()` registration;
  and
- a normal started runtime rejects `-Xno-sig-chain` exactly as Linux does.
  Genuine non-started compiler/tool runtimes retain the option.

No Windows-only explicit null check was added. Linux retains its implicit
`RSP - 8192` stack probe. Windows x64 nterp and optimizing code instead emit the
small pre-prologue `RSP < Thread::stack_end_` check, allow equality, and
tail-jump through the same `Thread::pThrowStackOverflow` entrypoint. The
fixed-page machinery is no longer part of product SOE delivery.

## Historical focused Wine gate

The retired Bash command was:

```bash
bash tools/verify/windows_x64_phase4/run_w010_managed_fault_probe.sh
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

Handled NPE/SOE output is rejected if it contains `ART Win32 VEH`,
`ART Win32 UEF`, or a minidump marker. The gate snapshots
`run/crash/*.dmp` metadata before and after all handled-fault processes and
requires no change.

## Regression evidence

- Windows x64 `art` and `dalvikvm` incremental build with `-j32`: PASS.
- Windows x64 dynamic-JIT unwind serializer probe: 6/6 groups PASS, covering the
  minimum empty record, small and both large allocation forms, every legal
  nonvolatile GPR, an RBP-anchored frame, fixed-RSP CriticalNative shape,
  descending offsets, padding, and invalid-input rejection.
- Windows x64 runtime registry probe: add, exact lookup/base/range/xdata validation,
  generated-code execution, `RtlVirtualUnwind` control-state restoration,
  deletion, lookup disappearance, re-registration, and clear PASS.
- Windows x64 product lifecycle probe in J-2 and J-1: initial lookup, invalidation
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
- Static OSR unwind: the emitted audit verifies the R12-anchored entry range,
  explicit RBP-to-copied-RSP handoff, and its contiguous zero-prologue RSP-based
  return range, including exact completed-frame XMM offsets.
  The unified `art.w002.win32_osr_unwind_probe` gate resolves both records,
  virtually unwinds from 256
  bytes below the fixed frame with RBP clobbered, restores RBP/RDI/RSI/RBX/R12-R15
  and XMM6-XMM15, repeats return unwinding with managed RBP deliberately
  clobbered, synthetically unwinds both invoke records, and verifies the
  canonical `add rsp,248; ret` epilogue. The real W-002 dual/J-1
  default/switch OSR matrix passes 8/8.
- Full-width Microsoft-XMM boundary sentinel: the Windows-only save area is
  160 bytes outside canonical ART frames; nterp, switch, and threshold-zero JIT
  each pass 2/2 with `mask=0`, retained historical `selfTestMask=63`, and
  authoritative `fullSelfTestMask=1023` for XMM6-XMM15.
- Threshold-zero JIT JNI native AV: the optimizing caller and JNI stub compile,
  both J-2 and J-1 reach initial VEH and UEF, and each run creates a changed or
  new valid `MDMP` minidump.
- OSR-origin native AV: switch-interpreter execution compiles Baseline and Osr
  versions, logs the real OSR jump, reaches the deliberate native AV after the
  copied-stack handoff, and both J-2 and J-1 reach VEH/UEF with a new valid
  `MDMP` dump. No OSR completion or unexpected-return marker appears.
- JIT smoke: 12/12 PASS.
- Normal/FastNative mixed/high-FP compiled-JNI ABI: 7/7 targets PASS in both
  default and instrumentation modes after reserving RBP/R15 from JNI scratch.
- Focused CriticalNative regression with one repeat: J-2, J-1, `-Xint`, Linux
  interpreter, and Linux JIT PASS.
- Phase-3 GoldenApp: PASS.
- Linux `art`, `art-compiler`, and `dalvikvm` incremental build with `-j32`: PASS.
- Linux `dalvikvm -showversion`: PASS.
- Linux shared-boot imageless Hello: PASS.

## FS-1 stack high-water acceptance

FS-1 compiles fixed-size, thread-owned scalar samples only into the opt-in
instrumentation build. Direct RSP stores cover the failing explicit check,
quick entry/save frame, common throw entry, temporary stack-end expansion,
exception construction and completion, restored default boundary, quick
delivery, and long jump. Formatting and validation occur after Java catches
the `StackOverflowError`. The structural check proves that product `art.dll`
has neither the probe export nor its generated asm offsets.

Final-source Wine and native Windows both pass Release and Debug switch,
nterp, and threshold-zero JIT with four complete main/child records per
process, positive boundary margins, required JIT compilation, no fatal
VEH/UEF marker, and no new dump:

| Host/build | switch | nterp | JIT |
|------------|-------:|------:|----:|
| Wine Release | 7536 | 7520 | 7616 |
| Wine Debug | 69728 | 37216 | 37232 |
| Native Release | 6784 | 7536 | 7616 |
| Native Debug | 69744 | 37168 | 37232 |

The first native Debug run failed all engines with `STATUS_STACK_OVERFLOW` in
`art::gc::Heap::CheckPreconditionsForAllocObject` while constructing the
`StackOverflowError`. A 20-KiB trial fixed switch but left nterp/JIT roughly
8 KiB below the native boundary. The accepted 40-KiB reserve is therefore
limited to non-`NDEBUG` Windows x86_64 and leaves more than 37 KiB on both
quick paths. Release/product and non-Windows builds remain at 8192 bytes.

The native package is 53,459,106 bytes with SHA-256
`22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe`.
Its transferred hash and internal manifest pass, `DMP_SCAN.txt` contains
`NO_DMP_FILES`, and the historical aggregate ends in `OVERALL PASS`. See the
adjacent [stack high-water result](../stack-high-water/RESULT.md).

## Native Stage E acceptance and remaining matrix

E9 is accepted on Windows Server 2025 build 26100. The immutable archive
`dist/windows_x64_w010_w014_e9_native.zip` has SHA-256
`2b84c911dfbe23dd5dd13917a0fb4a63bdbf90901172f74dfe642ed1fd20f16f`.
The returned full package matches the issued identity, has 30/30 PASS records,
zero handled dumps, and five valid fatal static/JIT/OSR dumps. The reviewer
reports `PASS (build=26100, pass_records=30, dumps=5,
return=full-package)`. See
`../../../docs/history/windows_x64_w010_w014_e9_result.md`.

Native Stage E therefore no longer blocks managed NPE/SOE, stack-budget
measurement, dynamic-table sampling/churn, the five-origin fatal matrix, or
the FS-2 debugger/CET/embedding/exception-XMM proof points. The native FS-2
run on build 26100 records first-chance JIT NPE continuation, fault-free
explicit SOE debugging, all nine incompatible policy rejections, accepted
dynamic/reserved policy bits, predecessor-UEF/frame-SEH teardown, and two
repeats of the exception sentinel in nterp/switch/JIT. See
`../../../docs/history/windows_x64_fs2_w010_w014_result.md`.

FS-4's same-host repeat now passes E9/FS-1/FS-2/FS-3 plus parameterized stack
geometry and join/detach/fiber checks. Under the acceptance policy, Windows
Server 2025 build 26100 is authoritative and the separate Windows 10 repeat is
skipped. Remaining optional coverage is narrower: reservation-correlation
probes, wrong-address/unsupported-exception negatives, and debugger-quality
dump-stack reconstruction. FS-5 conditionally closes the pending bridge range
because a real native fault there would require product fault injection.
`CetDynamicApisOutOfProcOnly` and reserved policy fields remain accepted by the
startup classifier.

The selected dynamic implementation is now present. Optimizing Windows x64 JIT
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

The threshold-zero JIT-origin and switch-OSR-origin gates prove native Windows
fatal dispatch reaches UEF and produces a valid dump across both exercised
dynamic chains. FS-3 separately proves concurrent native sampling under
large dynamic-table churn. FS-2 now proves debugger continuation and
exception-unwind preservation of full-width XMM6-XMM15; debugger-quality
minidump stack reconstruction remains a separate acceptance item.

## FS-5 pending interpreter-bridge disposition

FS-5 is conditionally closed as impractical coverage. The 88-byte
`art_quick_to_interpreter_pending_exception` range is structurally valid and
synthetically unwound, but no deterministic real native exception can enter
it without changing product control flow or injecting a fault into probe-only
assembly. The live unwind probe accepts both bridge records with a 200-byte
primary frame, 88-byte pending frame, and ten XMM records; native E6/E9 fatal
coverage enters the primary `+0x82` range and completes the full static/JIT/OSR
origin matrix.

After `artQuickToInterpreterBridge` returns, assembly restores the primary
save-refs-and-args frame, tests `Thread::exception`, returns normally when it
is null, or jumps to the pending tail when it is non-null. That tail saves
callee-saved GPRs and XMM12–XMM15 before non-returning managed exception
delivery. It is reached by an ART pending-exception transition, not a Windows
native exception.

A real fault test would have to patch the product tail, make its helper raise,
or jump into the internal range with fabricated ART registers/thread state.
The first two change product semantics; the third is only another synthetic
unwind test already covered by `RtlVirtualUnwind`. No such probe is retained.
If debugger-quality coverage for this tail becomes a product requirement, it
needs an explicitly synthetic/non-product label and separately reviewed fault
injection contract.
