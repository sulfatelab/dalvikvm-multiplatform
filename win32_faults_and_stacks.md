# Windows x64 managed faults and ART stack design

**Status:** W-010/W-014 E9 is native-accepted 30/30 and FS-1 Release/Debug
stack high-water acceptance passes on Windows Server 2025 build 26100.
Windows x64 uses explicit pre-prologue stack checks and guarantee-aware bounds;
switch/nterp/JIT managed SOE passes with zero handled dumps. Product Windows
and Linux retain the 8192-byte ART reserve; non-`NDEBUG` Windows x86_64 uses a
measured 40-KiB reserve and leaves more than 37 KiB of quick-path native margin.
Linux retains its implicit `RSP - 8192` probes. E5/E6 unwind repairs remain accepted,
and five static/JIT/OSR fatal origins produce valid dumps. A later E9-bound
pregrow experiment reproduces the Linux implicit read fault, but its nearly
full per-thread commit, irreversible high-water state, and fatal native
collision keep it diagnostic-only. FS-2 now closes the native debugger
first-chance/continue, named forced-policy, embedding/UEF teardown, and
exception-unwind XMM proof points on the same host. FS-5 now conditionally
closes the pending-range question: the brief 88-byte tail is structurally and
synthetically accepted, but a real native exception cannot enter it without
changing product control flow. Remaining product coverage is reservation-
correlation, negative-exception, and debugger-quality dump-stack work. The
shared JIT-3/FS-3 dynamic-table
sampling/churn gate and the JIT-5 post-removal fatal/unwind cross-regression
are native-accepted on the same build. JIT-5 removes the Windows J-1 path and
covers 29 cases, 36/36 aggregate records, eight lifecycle cycles, and three
valid static/JIT/OSR dumps. This closes W-025 without closing the independent
W-010/W-014 proof points.
The post-JIT-1 W-004 regression also passes 28/28 on the same Windows Server
2025 build 26100 with clean log, trace, and recursive dump scans.
**Created:** 2026-07-26
**Updated:** 2026-07-30
**Native gate policy:** Future native tests and acceptance gates use only
Windows Server 2025 Datacenter Evaluation x64 build 26100; the former Windows
10 lab host is unavailable. See
[native Windows gate policy](win32_host_gate_policy.md).
**Product API baseline:** x86_64 Windows 10 build 17134+
**Product model:** imageless ART with nterp and JIT; MSVC ABI artifacts built by
Clang/lld with LLVM libc++

This document is the authoritative design and implementation record for the coupled Windows
managed-fault and native-stack work tracked as W-010 and W-014. The name uses
"faults" rather than "sigchain" because Windows has no POSIX signal-chain
facility to reproduce. The Windows equivalent is a cooperative vectored
exception handler (VEH) that adapts a small, explicit set of hardware faults
to ART's existing managed-fault machinery.

The design starts from the Linux ART invariants, not from the current Windows
stubs. Its main goal is to keep generated code, managed ABI, exception
entrypoints, `FaultManager`, and Java-visible behavior as close to Linux as
Windows permits while isolating operating-system differences at narrow
boundaries.

## 1. Decision summary

The stable decisions and currently implemented candidate are:

1. Keep ART's existing implicit null-check model and Linux's existing implicit
   stack probe unchanged. On Windows x64 only, emit a narrow pre-prologue
   `RSP < Thread::stack_end_` check in optimizing code and nterp, allow
   equality, and tail-jump through the same ART overflow throw entrypoint.
2. Implement a process-wide ART managed-fault VEH with
   `AddVectoredExceptionHandler(1, ...)`. It handles only recognized,
   continuable `EXCEPTION_ACCESS_VIOLATION` records and returns
   `EXCEPTION_CONTINUE_SEARCH` for everything else.
3. Make `sigchain_windows.cc` a narrow ART-internal facade for the one special
   `SIGSEGV` action that `FaultManager` registers. Do not emulate `sigaction`,
   signal masks, or general POSIX signal delivery.
4. Pass a small non-owning Windows fault view through the x86_64 adapter. The
   view points at the real Windows x64 `CONTEXT` and carries the documented AV access
   kind; handlers modify the real `Rip`/`Rsp` in place. Construct only the
   small `siginfo_t` view needed by common `FaultManager`. Do not copy the
   Windows register set into a fabricated Linux `ucontext_t` and back.
5. Reuse the common `FaultManager`, generated-code range registry, handler
   ordering, null classifier, and quick exception entrypoints. Windows x64 managed
   stack overflow bypasses fault classification and enters the common throw
   path from its explicit generated check.
6. Treat Windows `EXCEPTION_STACK_OVERFLOW`, `PAGE_GUARD`, and the moving OS
   stack guard as native Windows mechanisms. Do not translate them as the
   managed event and do not install a product fixed page. Retain fixed-page
   selection/protection only for direct diagnostic tests.
7. Discover the current system stack with
   `GetCurrentThreadStackLimits()`, reject `IsThreadAFiber()`, validate the
   complete allocation with `VirtualQuery()`, and reject attachment if the
   current SP is outside that allocation. Do not clamp, guess, or use
   undocumented TEB fields.
8. Query each thread's stack guarantee, raise it to at least four system pages
   while preserving a larger host value, and query the configured value back.
   Exclude the sum of the inaccessible low memory prefix, the page-rounded
   configured guarantee, and one moving guard page. Common ART then places its
   8 KiB x86_64 product recovery reserve above that native boundary. A
   non-`NDEBUG` Windows x86_64 build uses 40 KiB because FS-1 proved that
   Clang-O0 Microsoft-ABI exception-allocation frames exceed the product
   reserve; Release and non-Windows builds remain at 8 KiB.
9. Create CRT-using ART threads with `_beginthreadex`, not raw `CreateThread`.
   For a non-zero requested stack size, pass
   `STACK_SIZE_PARAM_IS_A_RESERVATION`. Replace the current thread-ID/reopen
   join scheme with an opaque pthread control object that retains the real
   handle for joinable threads.
10. Disable caller-supplied `pthread_attr_setstack()` stacks for Windows ART
    thread pools. Pass the requested reservation size to the OS instead.
11. Activate implicit null handling only with the managed VEH and common
    handlers. Activate Windows x64 explicit stack checks only with validated,
    guarantee-aware thread bounds. A per-thread query, configuration, or
    layout failure rejects attachment or thread birth.
12. Keep fatal crash diagnostics separate from managed fault translation.
    Expected faults do not log or dump. The unhandled-exception filter writes a
    best-effort dump, then chains to the previously installed filter.
13. Do not support Windows CET user shadow stacks (Hardware-enforced Stack
    Protection) in the current Win32 ART design. Every defined incompatible
    shadow-stack and context-IP-validation field must be disabled;
    compatibility, audit, and strict modes are unsupported. Classify named SDK
    fields rather than treating the raw policy word as a Boolean. Build every
    project Windows x64 PE explicitly with `/CETCOMPAT:NO`, inspect packaged DLLs,
    and reject an incompatible policy before managed threads or JIT startup.
14. Provide correctness-grade Windows x64 unwind descriptions wherever Windows may
    dispatch a fatal exception across ART-managed frames. Static invoke/JNI
    boundary records and the split OSR entry/return records are implemented.
    Dynamic optimizing/JNI code uses Windows-JIT-only fixed `RBP` anchors or a
    fixed-RSP CriticalNative shape, explicit compact PE unwind bytes, xdata in
    the existing JIT data allocation, and one immutable
    `RtlAddFunctionTable` registration per code allocation owned by the JIT
    code cache.
15. Keep the pregrown `PAGE_NOACCESS` implicit-stack mechanism as a standalone
    diagnostic. Do not add an ART feature flag or product attachment path
    unless the explicit-check decision is reopened with a new requirement that
    justifies its memory, detach, and native-collision costs.

## 2. Scope and ownership

### 2.1 W-010 owns

- Registration, promotion, and removal of the ART managed-fault VEH.
- Cooperative handler-chain semantics and debugger coexistence.
- Validation of `EXCEPTION_RECORD` and Windows x64 `CONTEXT`.
- Adaptation of recognized access violations to common ART fault handling.
- In-place Windows x64 PC/SP context access in the x86_64 fault handler.
- Implicit null-pointer translation.
- Explicit Windows x64 stack-check code generation and common throw-entry transfer.
- The activation gate for generated code that depends on implicit faults.
- Separation of managed translation from fatal VEH/UEF diagnostics.

### 2.2 W-014 owns

- Current-thread stack discovery and validation.
- Stack reservation sizing for Java and ART-created native threads.
- The Windows pthread attribute and join/detach contract needed by those
  threads.
- The Windows thread-pool stack policy.
- ART stack accounting (`stack_begin_`, `stack_end_`, `stack_size_`).
- Stack-guarantee configuration/verification and Windows recovery-region
  accounting.
- Fixed-page selection/protection/restoration only for direct diagnostics.
- Rejection policy for fibers, manual stacks, and impossible bounds.

### 2.3 Explicit non-goals

- General POSIX signal emulation on Windows.
- Windows 7 support or dynamic resolution of Windows 8+ stack APIs.
- Translating native stack exhaustion into Java `StackOverflowError`.
- Supporting caller-provided stack addresses through fibers.
- Windows ARM64 in the first implementation. The interfaces should not prevent
  it, but all concrete acceptance in this draft is Windows x64.
- Full symbol-quality native unwinding through every quick assembly stub.
  Managed stack walking remains ART-owned. This does not make correctness-
  critical PE runtime-function data optional: Windows exception dispatch must
  be able to cross the native/managed boundary stubs and dynamically emitted
  JIT frames that can be present on a fatal exception path.
- Enabling implicit suspend checks on Windows x64. Current ART enables that
  mechanism on Arm64, not x86_64.
- Windows CET user shadow stacks, also exposed as Hardware-enforced Stack
  Protection. This is an explicit unsupported product configuration, not an
  open hardening task. ART interpreter `ShadowFrame` objects are unrelated to
  the hardware return-address shadow stack.

## 3. Linux behavior that Windows must preserve

Linux ART uses three layers:

1. Generated code faults deliberately:
   - an implicit null load/store accesses the first page;
   - a non-leaf method probes `SP - GetStackOverflowReservedBytes()` before
     establishing its frame.
2. `libsigchain` keeps ART's `SIGSEGV` handler at the front while preserving
   application handlers behind it.
3. `FaultManager` accepts faults only for a runnable ART thread holding the
   mutator lock with PC inside a registered generated-code range. Architecture
   handlers validate the precise fault form and redirect the saved context to
   a normal ART quick exception entrypoint.

For x86_64 stack overflow, the Linux handler validates:

```text
fault_address == interrupted_rsp - ART_STACK_OVERFLOW_GAP_x86_64
```

and replaces the saved PC with `art_quick_throw_stack_overflow`. The stack
probe runs before the callee-save prologue, so the interrupted RSP still
describes the caller frame. `ThrowStackOverflowError()` temporarily expands
ART's usable lower stack boundary, unprotects the fixed page, constructs the
exception, restores the normal boundary, and protects the page again.

Windows preserves the pre-prologue timing, caller-frame invariant, common
throw entrypoint, 8192-byte product ART recovery reserve, and Java-visible
exception. Debug Windows x86_64 deliberately uses the FS-1-measured 40-KiB
reserve; that build-only safety budget does not change product or Linux.
The unavoidable OS-specific difference is detection: Windows x64 compares RSP with
`Thread::stack_end_` explicitly because Windows stack growth cannot preserve a
fixed protected page, while Linux retains the implicit fault sequence.

## 4. Current Windows state and remaining defects

Stages A-B have removed the unsafe stack-bound, pthread-creation, and
no-op-protection workarounds:

- `GetThreadStack()` now accepts only the current non-fiber system stack,
  obtains its exact interval from `GetCurrentThreadStackLimits()`, validates
  current-SP containment and committed-private ownership, and walks the full
  allocation with `VirtualQuery()` before publishing bounds. Its temporary
  one-page `guardsize` report is not treated as an authoritative Windows guard
  or excluded-low measurement; `InitStack()` replaces it with the measured
  excluded-low prefix before publishing ART bounds.
- `pthread_create()` uses `_beginthreadex`; non-zero sizes use reservation
  semantics, custom stack addresses are rejected, joinable handles and
  callback results have real ownership, and detach closes the handle exactly
  once.
- ART-created Windows thread pools pass their requested reservation rather
  than allocating an ignored `MemMap` stack.
- Runtime teardown removes ART's diagnostic VEH while `art.dll` is still
  loaded and restores the process UEF without overwriting a filter installed
  after ART.
- Every attached Windows thread queries its current stack guarantee, raises it
  to at least four pages while preserving a larger value, and queries the
  actual configured value back. Its published bounds exclude the measured
  inaccessible prefix, rounded configured guarantee, and one moving guard
  page before common ART adds the 8192-byte product recovery reserve (40 KiB
  only for non-`NDEBUG` Windows x86_64).
- Fixed-page install/protect/unprotect/restore remains compiled for isolated
  direct page-state probes. Product attachment and teardown do not use it.

The current tree now has the active W-010 product capability:

- `sigchain_windows.cc` owns one immutable special-`SIGSEGV` action and a
  first VEH. It filters exact continuable access violations, adapts the real
  Windows x64 `CONTEXT`, supports promotion/removal, and continues the search for
  every unsupported or unrecognized exception.
- `runtime_windows.cc` still owns a separate diagnostic VEH. It may log fatal
  first-chance events, but it never translates managed faults. The fatal UEF
  writes a best-effort dump and chains to its predecessor, or returns search.
- Runtime initialization enables implicit null handling and explicit Windows x64
  stack-overflow checks while keeping implicit suspend checks disabled.
  Linux handler order and implicit probes remain unchanged.
- Windows x64 registers nterp's immutable generated-code range during fault-manager
  initialization from `IsNterpSupported()`, before `Runtime::Start()` can
  publish nterp entrypoints. JIT ranges continue through common
  `Runtime::AddGeneratedCodeRange()`.
- A normal started runtime rejects `-Xno-sig-chain` on Windows exactly as on
  Linux. The option remains for genuine non-started compiler/tool runtimes.
- The focused Stage D Wine gate catches 64 read plus 64 write NPEs and repeated
  main/child SOEs in both nterp and threshold-zero JIT, with no managed-fault
  diagnostic output or dump-state change. Every caught fault also constructs
  and consumes its managed stack trace, performs ordinary allocation/time
  operations, and resumes managed execution; the gate requests 16 collections
  across each NPE run and one collection after each of the four caught SOEs.
- Windows x64 PE unwind records now cover `art_quick_invoke_stub`,
  `art_quick_invoke_static_stub`, `art_quick_generic_jni_trampoline`, and both
  contiguous ranges of `art_quick_osr_stub`. Structural inspection verifies
  their fixed allocations, nonvolatile GPR/XMM saves, frame anchors, and the
  OSR return range's inherited 248-byte RSP frame. Wine's `-Xint` crash gate
  reaches ART's UEF and creates a valid `MDMP`, but native build 19044 does not.
  The GenericJNI gate now calls `RtlVirtualUnwind()` from the captured native-
  call return at trampoline `+0xc5` with its real 200-byte canonical frame,
  5120-byte R12-anchored reserved area, and variable native RSP. It exposed and
  repaired the RDI save offset from zero to `R12 + 0x1400`.
- The invoke and OSR native-to-managed stubs now preserve full-width
  XMM6-XMM15 in a 160-byte Windows-only adapter area. Their unwind records
  describe all ten saves at completed-frame offsets 64 through 208. ART's
  managed ABI remains unchanged and still uses 64-bit scalar XMM12-XMM15
  spills; the complete Microsoft nonvolatile state is adapted only at the
  native boundary.
- The focused OSR unwind probe resolves the exported entry record and its
  contiguous return record, unwinds from 256 bytes below the fixed frame,
  restores RBP/RDI/RSI/RBX/R12-R15 and XMM6-XMM15, proves return unwinding with
  a managed-clobbered RBP, synthetically unwinds both invoke records, and
  exercises the canonical `add rsp,248; ret` return epilogue. The actual
  dual-view/J-1 default-nterp and switch OSR matrix passes 8/8. The strengthened
  normal-return sentinel passes 2/2 in nterp, switch, and threshold-zero JIT.
- Dynamic optimizing and JNI JIT allocations now append DWORD-aligned unwind
  bytes after roots and `CodeInfo`, write them through the data RW alias, and
  expose them through the primary read-only low-4-GiB view. `JitCodeCache`
  owns a stable one-entry runtime-function table per allocation, registers it
  before any method map or entrypoint publication, unregisters before debug-
  info removal and mspace reuse, and clears all registrations before mapping
  teardown.
- Focused J-2 and J-1 lifecycle gates prove initial lookup, invalidation while
  metadata remains live, real code-cache collection, lookup disappearance,
  exact code-address reuse, re-registration at that address, and successful
  execution of the replacement method. The standalone registry gate also
  proves `RtlVirtualUnwind()` restores RBP, RSP, and RIP from a generated frame.
- A threshold-zero optimizing caller through a JIT JNI stub now reaches the
  diagnostic VEH and UEF and creates a new valid `MDMP` dump in both J-2 and
  J-1. A separate switch-interpreter OSR-origin probe compiles Baseline and
  Osr versions, jumps into the compiled loop, reaches the deliberate native AV,
  and creates a new valid dump in both J-2 and J-1. This proves live fatal
  dispatch across both exercised dynamic chains and the copied OSR stack.
  It does not prove debugger-quality minidump stack reconstruction or
  concurrent sampling under large-table churn.

The implementation is complete under Wine and native-accepted in E9 on
Windows Server 2025 build 26100 for the 30-record managed-fault/fatal matrix.
Historical E2-E6 results below document why fixed-page SOE and missing PE
unwind records were rejected or repaired. E9 passes switch/nterp/JIT managed
SOE, zero handled dumps, and all five fatal origins. FS-1 additionally accepts
allocation-free Release/Debug stack high-water records for switch, nterp, and
JIT, including the 40-KiB Debug-only reserve. JIT-3/FS-3 accepts native
dynamic-table collection/reuse churn and concurrent lookup/virtual-unwind
sampling. FS-2 is now native-accepted on that host for debugger continuation,
forced policy classification, embedding teardown, and exception-unwind XMM;
FS-5 conditionally closes the pending range, while reservation-correlation,
negative-exception, and debugger-quality dump-stack coverage remain additional
acceptance work. FS-4 now treats Windows Server 2025 build 26100 as the
authoritative native host and skips the separate Windows 10 repetition.

### 4.1 Second native Stage E result and current diagnosis

`/tmp/log-windows_x64_w010_w014_host-run2.zip` exactly matches the issued package
and ran on Windows 10 Enterprise LTSC build 19044. It returns 20 PASS and 12
FAIL records. The corrected CET classifier accepts raw `flags=0x00000100`
because the named incompatible mask is zero. Native 64 KiB and 256 KiB
reservations are exact, handle counts remain stable, and the direct stack-page
probe restores a reserved original page for 64 cycles.

The following native paths pass and are no longer hypotheses:

- split OSR lookup and live unwind;
- all six nterp/switch/JIT XMM6-XMM15 sentinel runs;
- requested stack reservation and pthread lifetime checks;
- direct fixed-page AV, selection, and restoration;
- exact fault-record filtering, sigchain ordering, foreign VEH, and frame SEH;
- nterp and threshold-zero JIT implicit read/write NPE translation; and
- started-runtime `-Xno-sig-chain` rejection.

The managed SOE failures are one failure class. Switch, nterp, and JIT all
terminate with `0xC00000FD STATUS_STACK_OVERFLOW`. Native stack layout differs
from Wine: the main page probe selects `low + 4096` from `MEM_RESERVE`, while
Wine preserves an 8192-byte bottom prefix and selects an already committed
`PAGE_READWRITE` page. A JIT failure reports an access at `RSP - 0x2000`, but
Windows classifies it as native stack overflow before ART sees a read AV in
its fixed page. The switch path additionally reports
`ART stack page was not private read/write before protect` with error 13 after
the page was temporarily writable. Run 3 resolves that observation: recursive
growth commits/reprotects the selected page as ordinary `PAGE_READWRITE`, and
pre-reset re-protection succeeds. The error 13 was secondary. A passing direct
page probe does not model recursive stack growth and cannot validate SOE.

The fatal AV failures are a separate class. Static `-Xint`, JIT J-2/J-1, and
OSR J-2/J-1 all reach `ART Win32 VEH: exception 0xc0000005`, then exit with
the AV status without an ART UEF marker or dump. Identical behavior across all
five origins is not evidence of a JIT unwind defect. The next distinction is
whether ordinary top-level dispatch is being bypassed or the fatal dalvikvm
path cannot unwind to it. Run 3 later rules out UEF replacement and narrows
that question to native exception traversal across the common boundary.

The diagnostic package now contains:

- `win32_stack_growth_probe.exe`, with baseline, protected, writable, and
  direct modes on isolated 2 MiB reservations;
- `win32_uef_probe.exe`, with frame-SEH, main-thread unhandled, predecessor
  chain, and worker-thread modes;
- `CrashNativeProbe uef`, which installs a late diagnostic UEF, identifies the
  predecessor module, and chains directly to it; and
- the issued historical package's diagnostic runner, which wrote a separate
  `diagnostic_logs` result without changing the 30-record acceptance runner.

Wine verifies the baseline/writable/direct stack modes, all four standalone
UEF modes, and the late chain where ART is the predecessor and writes a valid
dump. Wine 10.0 itself segfaults in protected recursive stack growth, so that
case is intentionally native-only. See
`docs/evidence/windows_x64_w010_w014_diagnostics.md` for the interpretation
matrix.

### 4.2 Third native diagnostic result

`diag-log-windows_x64_w010_w014_host-run3.zip` matches the issued package and
completes every isolated diagnostic on Windows build 19044. The stack result is
decisive:

- baseline, protected, and writable recursive modes terminate with
  `STATUS_STACK_OVERFLOW`; direct access to the protected page still produces
  the expected `EXCEPTION_ACCESS_VIOLATION`;
- the protected mode starts with the selected page as `PAGE_NOACCESS`, but at
  the terminal overflow `VirtualQuery()` reports a 2,093,056-byte committed
  `PAGE_READWRITE` region beginning at that page;
- the fault is above the fixed page, not an AV in it; and
- writable mode successfully re-protects the page before `_resetstkoflw()` and
  restores it afterward. The earlier error 13 was therefore a secondary ART
  state-check/recovery symptom, not the root cause.

Do not describe this as Windows moving `PAGE_GUARD` onto the fixed page. The
observed terminal state is ordinary `PAGE_READWRITE`: normal recursive stack
growth commits/reprotects the page and Windows raises stack overflow before the
Linux-style fixed-page event can occur. Selection, direct protection, and exact
restoration remain valid infrastructure, but fixed-page recursive SOE delivery
inside a Windows-owned stack reservation is invalidated.

The standalone UEF probe also closes the process-level hypotheses. Main-thread
and `_beginthreadex` worker AVs reach a UEF, direct predecessor chaining reaches
both filters, and a frame SEH handler consumes its own AV before UEF as
documented. No debugger is attached. Immediately before the ART fatal probe, a
late filter observes that its predecessor is still inside `art.dll`; the crash
then reaches `ART Win32 VEH` but reaches neither the late filter nor ART's UEF,
creates no minidump marker, and creates no dump. UEF replacement, the runner,
and dump-path/API failure are therefore ruled out at this stage.

The captured native stack contains a return address at
`art_quick_generic_jni_trampoline + 0xc5`; an adjacent
`art_jni_dlsym_lookup_stub` address is likely saved data or function-pointer
state rather than a proven call frame. This narrowed the next diagnosis to
Windows exception traversal across GenericJNI and the managed/native boundary.

The resulting realistic virtual-unwind test found one concrete defect: RDI is
physically saved before the 5120-byte reserved-area subtraction, at
`R12 + 0x1400`, while the PE record described offset zero. Caller RIP/RSP and
the pushed nonvolatile registers already restored correctly; only RDI failed.
The record now describes offset `0x1400`, and both structural inspection and
the realistic `RtlVirtualUnwind()` pass under Wine. Because the incorrect RDI
alone did not corrupt the recovered control stack in the synthetic case, native
evidence is still needed before calling it the complete UEF root cause.

The follow-up package adds JNI `RaiseException`, JNI hardware AV, and a
JNI-created `_beginthreadex` worker AV. Local Wine reaches late UEF, ART UEF,
and minidump creation in all three shapes; the continuable software-raised AV
then resumes under Wine and is recorded as an observation. Native run 4 below
provides the comparison.

### 4.3 Fourth native diagnostic result

`diag_w010_w014_host-run4.zip` exactly matches the issued repaired-
GenericJNI package. The stack-growth rows repeat run 3, including the committed
`PAGE_READWRITE` terminal region and successful pre-reset re-protection. The
standalone frame-SEH/main/chained/worker UEF rows also repeat run 3.

The three ART exception shapes isolate the remaining fatal boundary:

- the JNI hardware AV and continuable JNI
  `RaiseException(EXCEPTION_ACCESS_VIOLATION)` both report ART as the installed
  predecessor, reach `ART Win32 VEH`, then exit with
  `STATUS_ACCESS_VIOLATION` without entering either late or ART UEF and without
  creating a dump;
- the JNI-created `_beginthreadex` worker reports creation and entry, reaches
  the same ART VEH, then enters the late UEF and ART UEF and writes one valid
  648,619-byte minidump; and
- no debugger is attached, and the same package, process initialization, JNI
  library, UEF chain, dump directory, and dump API are used.

The distinction is therefore not hardware versus software exception shape,
ART startup state, UEF ownership, runner/debugger behavior, or dump creation.
It is the presence of the ART managed/GenericJNI caller chain on the crashing
thread. The repaired GenericJNI record remains a real correctness fix but is
not the complete dispatch boundary.

The next diagnostic is now implemented as a bounded, opt-in recursive native
unwind trace from a copy of the live VEH `CONTEXT`. For each frame it records
PC/RSP, the `RtlLookupFunctionEntry()` result, image base and runtime-function/
unwind RVAs, then uses `RtlVirtualUnwind()` or a validated leaf pop. It stops on
invalid stack memory, no progress, zero PC, or a small fixed frame limit, and
does not change dispatch. This identifies the first frame after GenericJNI
that Windows cannot traverse. `art_jni_dlsym_lookup_stub` currently has no PE
record, but it restores its complete temporary frame and tail-jumps to the
resolved native method. Its address in captured stack memory may therefore be
function-pointer data rather than an active frame; do not add metadata without
the recursive trace proving it is traversed.

The direct Wine E4 smoke makes that distinction. It unwinds the native crash,
GenericJNI, the static invoke stub, normal ART C++ frames, and
`ExecuteSwitchImplCpp`, then reaches `ExecuteSwitchImplAsm + 0x9` at its
post-call `pop %rbx`. `RtlLookupFunctionEntry()` returns null for that live PC.
Because the wrapper pushed RBX, leaf fallback reads saved RBX as the return PC
instead of consuming the real return address. The trace then walks stack data,
which is the exact failure shape expected from missing unwind metadata. The
previous `art_jni_dlsym_lookup_stub` stack word is therefore not the first
proven missing active frame.

The product assembly change was held until native E4 reproduced this frame.
It did, so the narrow repair is not only `.seh_pushreg`: Windows x64
`ExecuteSwitchImplAsm` also calls an MSVC-ABI C++ function without reserving
the mandatory 32-byte outgoing home area. Add the home area and matching
prologue/epilogue unwind description together under `_WIN32`, leave the
Linux/SysV body unchanged, and cover entry, body, and epilogue PCs with both
structural lookup and realistic `RtlVirtualUnwind()` tests.

The complete E4 package builds with `-j32` and passes the structural checker
and Wine smoke. All three late-UEF modes emit bounded trace begin/frame/end
records; two full fatal smokes preserve 14-15 valid minidumps before final cleanup
and clean manifest regeneration. This verifies the diagnostic transport and
non-regression surface, not the candidate frame on native Windows.

Native E4 on Windows Server 2025 build 26100 reproduces the candidate exactly.
The JNI hardware trace reaches `ExecuteSwitchImplAsm + 0x9` at frame 7 and the
raised trace reaches it at frame 8. Both report `rva=0x9b6089 lookup=0`, then
leaf fallback produces a stack address as PC and UEF dispatch is lost. The
native worker instead traverses four registered frames to zero PC, reaches both
UEFs, and writes a valid dump. Current Windows also repeats the fixed-page
stack-growth failure. The diagnostic stage is therefore closed: repair the
wrapper's Windows x64 home-area/unwind frame and verify native dispatch.

Native E5 verifies that repair. The live post-call PC is now
`ExecuteSwitchImplAsm + 0xd` with a valid runtime-function lookup in both JNI
traces, and unwind crosses the wrapper plus four later registered ART C++
frames. The new first miss is `art_quick_to_interpreter_bridge + 0x82`, the
return PC after `call artQuickToInterpreterBridge`. The bridge's normal path
has a 200-byte save-refs-and-args frame, while its pending-exception tail runs
after that frame has been removed and constructs a different save-all frame.
They require separate, range-accurate unwind descriptions. The native worker
again reaches both UEFs and writes a valid dump. Thus E5 closes the wrapper
defect but not fatal dispatch or the independent managed-SOE redesign.

Local E6 preserves the primary frame byte-for-byte through the call and keeps
ART's canonical 200-byte layout. Its PE record describes four volatile push
slots, the 112-byte fixed allocation, and saved RSI/RBP/RBX/R12-R15. Windows-
only fixed-offset loads leave the completed frame intact until either a
canonical `add rsp, 200; ret` normal epilogue or `add rsp, 200; jmp` pending
tail epilogue. The pending target begins a distinct contiguous record and
constructs the original 88-byte save-all frame; one blanket record never spans
the two shapes. `RtlVirtualUnwind()` recognizes both epilogues and restores the
caller from entry, `+0x82`, the restore body, and the completed pending body.
Linux continues to use the original setup/restore macros, and its emitted
bridge disassembly is unchanged. This made the live dispatcher crossing the
repaired range, with any later first miss reported explicitly, the native E6
acceptance criterion.

Native E6 supplies that proof. Hardware frame 11 and raised frame 12 resolve
`art_quick_to_interpreter_bridge + 0x82` to the primary range. Every later
frame reports `lookup=1`; the walks end with `reason=zero_pc` after 23 and 24
frames. Both late filters enter, chain to ART's UEF, and create valid dumps.
The native-worker control also passes. No further missing record appears in
these chains. The result accepts the primary record natively; the pending
range remains static/synthetic coverage because these fatal cases do not enter
it.

The complete E6 host runner then accepts every fatal origin on Windows Server
2025 build 26100: static `-Xint`, threshold-zero JIT J-2/J-1, and switch-OSR
J-2/J-1 each reach VEH and UEF and create a valid named minidump. It records
25/30 PASS rows overall. The remaining rows expose only managed-SOE behavior:
switch mode fails page re-protection with unexpected state/error 13 and exits
with `0xC0000005`; nterp and JIT reach `0xC00000FD`; JIT also reaches UEF and
writes an unwanted sixth dump. This closes native fatal-origin repetition but
strengthens, rather than changes, the requirement to replace fixed-page SOE
delivery.

### 4.4 E7-E9 managed-SOE replacement and acceptance

E7 replaces Windows x64's rejected fixed-page probe with explicit pre-prologue
checks in optimizing code and nterp. The generated comparison allows
`RSP == Thread::stack_end_`, branches only when RSP is below the boundary, and
tail-jumps through `Thread::pThrowStackOverflow`. Linux object inspection
proves its existing implicit `RSP - 8192` probe is unchanged.

E8 configured a native stack guarantee but treated it as overlapping the
inaccessible low prefix. Native switch/nterp/JIT SOE still failed. Controlled
build-26100 runs then measured terminal fault locations at `low + 0x3000`,
`+0x3000`, `+0x4000`, `+0x5000`, `+0x9000`, and `+0x11000` for guarantee
requests 0, 8192, 12288, 16384, 32768, and 65536. This establishes that the
guarantee lies above a separate terminal prefix and below one moving guard.

E9 therefore:

```text
minimum guarantee = 4 * system page size
configured guarantee = max(existing guarantee, minimum)
excluded low = inaccessible memory prefix
             + page-rounded configured guarantee
             + one moving PAGE_GUARD page
product stack_end = low + excluded low + ART's 8192-byte reserve
Windows Debug stack_end = low + excluded low + ART's 40960-byte reserve
```

`SetThreadStackGuarantee(0)` queries the current value. A nonzero call returns
the previous value through its argument, so ART queries, conditionally raises,
queries again, and validates the actual configured value. Larger host values
are preserved.

The immutable E9 archive SHA-256 is
`2b84c911dfbe23dd5dd13917a0fb4a63bdbf90901172f74dfe642ed1fd20f16f`.
Windows Server 2025 build 26100 returns 30/30 PASS, no handled dumps, and five
valid fatal dumps. The independent reviewer reports
`PASS (build=26100, pass_records=30, dumps=5, return=full-package)`. See
`docs/evidence/windows_x64_w010_w014_e9_result.md`.

## 5. Windows contracts and conclusions

### 5.1 VEH ordering is the Windows chain

Microsoft documents that vectored handlers:

- are process-wide rather than frame-based;
- run after the debugger's first-chance notification;
- run before frame-based unwinding;
- run in registration order;
- may resume execution by returning `EXCEPTION_CONTINUE_EXECUTION` or defer by
  returning `EXCEPTION_CONTINUE_SEARCH`.

`AddVectoredExceptionHandler(1, handler)` makes the new handler first until a
later caller also registers a first handler. Windows offers no supported API
to inspect the current VEH list. Therefore the correct coexistence contract
is cooperative: ART registers first, handles only its exact faults, and
returns search for all others. A later component that consumes ART's expected
AV before ART sees it is incompatible with any VEH-based managed runtime.

### 5.2 The debugger always sees expected faults first

Because debugger first-chance notification precedes VEH, a debugger configured
to break on every access violation will stop on normal implicit null checks.
Windows x64's explicit stack check does not deliberately fault. Native acceptance
must still prove that continuing a debugger resumes an implicit null fault into
the managed exception path.

### 5.3 `PAGE_GUARD` cannot simply be adopted as ART's page

Windows guard pages are one-shot alarms. On first access Windows raises
`STATUS_GUARD_PAGE_VIOLATION` and clears `PAGE_GUARD`; Windows also moves a
guard page to grow thread stacks. ART needs repeatable managed-overflow
delivery, so directly substituting `PAGE_GUARD` for Linux's fixed page remains
invalid. However, native build 19044 also proves that a separate
`PAGE_NOACCESS` page is not sufficient unchanged: recursive stack growth
commits/reprotects that page as ordinary `PAGE_READWRITE` and reaches native
stack overflow first.

A later standalone follow-up, `win32_stack_pregrow_probe`, shows one narrower
exception to that rule. If the thread first forces Windows' moving
guard/guarantee region down to the E9 low neighborhood with a leaf page walk,
then installs `PAGE_NOACCESS` on the first RW page above that region, the exact
Linux `testq %rax, -8192(%rsp)` read fault is stable on Windows build 26100
(30/30 at `selected_offset=0x6000`). Attach/detach page restore succeeds 5/5,
but supported APIs cannot raise the moved guard or release the stack commit.
Native recursion into the selected page exits with `0xC0000005` rather than
reaching a managed overflow path.

The held-alive scale result for 2 MiB reservations is:

| Threads | Private peak delta | Stack commit sum |
|--------:|-------------------:|-----------------:|
| 1 | 2,211,840 bytes | 2,093,056 bytes |
| 10 | 21,164,032 bytes | 20,930,560 bytes |
| 100 | 211,009,536 bytes | 209,305,600 bytes |

The cost is therefore approximately 2.0-2.1 MiB per thread, not a one-page
tripwire cost. E9 explicit checks stay the product default. The probe artifact
SHA-256 is
`bdfec88fa7dc5cbcdd9e6e556ecbd7738a2b8822662bbafc15027ca3f320f7c5`;
full records and timing are in
`docs/evidence/windows_x64_w010_w014_diagnostics.md`.

### 5.4 Native stack overflow is not ART's managed event

Native Windows reports `EXCEPTION_STACK_OVERFLOW` after consuming the fixed
page as stack backing. That event has compiler/CRT recovery rules and arrives
too late to preserve ART's pre-prologue invariant, so W-010 deliberately does
not translate it. E9 detects the boundary explicitly before prologue setup and
uses the common ART throw path while the Windows guarantee remains available.

### 5.5 The system stack interval is a documented API

`GetCurrentThreadStackLimits()` returns the lower and upper limits of the stack
allocated by the system for the current thread. Microsoft explicitly warns
that user-mode code can execute outside that allocation. ART therefore must
check that current SP is inside the returned interval; this also gives a clean
policy for fibers and manual stacks.

### 5.6 Diagnostic page commit and protection are separate operations

The direct diagnostic selector still tests Windows page-state mechanics.
`VirtualAlloc(address, size, MEM_COMMIT, protection)` commits pages inside an
existing reservation, while `VirtualProtect` works only on committed pages.
The diagnostic sequence is deterministic:

```text
reserved original:
  validate -> MEM_COMMIT/PAGE_READWRITE -> PAGE_NOACCESS
committed original:
  validate exact MEM_PRIVATE/PAGE_READWRITE -> PAGE_NOACCESS
```

### 5.7 `_beginthreadex` is the correct creator for ART threads

ART thread entry functions use the C/C++ runtime. Microsoft recommends
`_beginthreadex` for such threads, and its `initflag` supports
`STACK_SIZE_PARAM_IS_A_RESERVATION`. OpenJDK HotSpot uses the same combination
for its Windows VM threads. Raw `CreateThread` is still part of the external
attachment test matrix, but not the selected implementation of the pthread
shim.

### 5.8 `SetThreadStackGuarantee` defines the native recovery boundary

`SetThreadStackGuarantee` does not itself detect or translate managed overflow.
E9 uses it to guarantee native dispatch/recovery space below ART's separate
managed reserve and to make that boundary explicit in stack accounting. ART
queries the current value with a zero call, raises it to at least four system
pages if necessary, queries it again because the setter returns the previous
value, and validates the result. A larger existing guarantee is preserved.

The configured guarantee is page-rounded and added to, not maximized with,
the inaccessible memory prefix. One moving guard page is added separately.
This contract is based on controlled native measurements and is validated on
both main and pthread-created threads in the E9 page probe.

### 5.9 CET user shadow stacks conflict with ART's non-local transfers

The current Win32 ART runtime does not support CET user shadow stacks. The
decisive conflict is ART's ordinary x86_64 managed exception and
deoptimization transfer, not only W-010's proposed VEH context editing.

`art_quick_do_long_jump` in
`runtime/arch/x86_64/quick_entrypoints_x86_64.S` restores an older normal
stack pointer with `popq %rsp` and then executes `ret`. The prepared ART
context places the selected managed catch/deoptimization PC on that restored
normal stack. CET maintains a separate protected return-address stack. This
stub neither restores nor advances CET's shadow-stack pointer, so its final
`ret` compares different return addresses and raises a control-protection
fault.

That long-jump path is shared by ordinary explicit managed throws, implicit
NPE/SOE delivery, deoptimization, pending JNI exceptions, and runtime slow
paths. Consequently none of these narrower changes can make CET safe:

- disabling W-010 implicit-fault translation;
- leaving `CONTEXT.Rsp` unchanged for stack-overflow redirection;
- adding PE unwind metadata only to the VEH trampoline;
- enabling Intel indirect-branch tracking or `-fcf-protection`/`ENDBR`;
- registering only JIT continuation targets.

W-010 adds another incompatibility. Null translation changes both
`CONTEXT.Rip` and `CONTEXT.Rsp`, while stack translation changes
`CONTEXT.Rip`. A process with `SetContextIpValidation` can validate modified
instruction pointers during context restoration. ART's quick and JIT
continuation targets currently have no complete `/guard:ehcont` contract, and
Windows x64 quick assembly does not provide complete PE unwind metadata. These are
additional rejection reasons, but fixing them alone would not repair
`art_quick_do_long_jump`.

The supported process contract is therefore field-based, not a raw
`Flags == 0` test:

| SDK field group | ART decision | Reason |
|---|---|---|
| `EnableUserShadowStack`, `AuditUserShadowStack`, `EnableUserShadowStackStrictMode` | Reject | Current ART non-local transfers do not maintain the protected return stack. |
| `SetContextIpValidation`, `AuditSetContextIpValidation`, `SetContextIpValidationRelaxedMode` | Reject | W-010 edits saved instruction/stack pointers without a complete EH-continuation contract. |
| `BlockNonCetBinaries`, `BlockNonCetBinariesNonEhcont`, `AuditBlockNonCetBinaries` | Reject | These compatibility/audit fields belong to the unsupported CET process configuration. |
| `CetDynamicApisOutOfProcOnly` | Allow | This only restricts out-of-process use of the dynamic EH-continuation and dynamically enforced CET-compatible-range APIs; ART uses neither API. It does not enable HSP or context-IP validation. |
| `ReservedFlags` | Ignore | Reserved bits have no defined policy meaning. Treating them as HSP would repeat the raw-word bug. When a future SDK gives a bit a named field, the classifier and probe must explicitly review it. |

Consequently:

- startup rejects any defined incompatible field listed above, including an
  incompatible field mixed with `CetDynamicApisOutOfProcOnly` or reserved
  bits;
- Windows compatibility mode is not accepted merely because non-CET modules
  may be tolerated there;
- every project Windows x64 executable and DLL link must explicitly pass
  `/CETCOMPAT:NO`; packaged LLVM libc++ and other DLLs must also be inspected
  for absence of `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT`;
- the launcher or Windows Exploit Protection configuration must disable
  Hardware-enforced Stack Protection before process creation. ART cannot
  downgrade or disable an active policy with `SetProcessMitigationPolicy`;
- CFG remains a separate mitigation. Supporting or testing CFG does not imply
  CET shadow-stack support.

Stage 0 now implements both enforceable halves of this rule. The generated
Windows x64 graph, all handwritten Windows x64 CMake harnesses, and all direct Clang/lld
PE links pass `/CETCOMPAT:NO` explicitly. A structural verifier audits those
sources and Ninja link commands, then scans the selected build/package trees
and LLVM libc++ for the CET-compatible extended characteristic. The runtime
queries the process policy immediately after selecting the logger and before
`MemMap::Init()`, ART thread startup, nterp publication, or JIT initialization.
Every named incompatible field and every unexpected query/version failure is
rejected. `CetDynamicApisOutOfProcOnly` and `ReservedFlags` do not contribute
to the incompatibility mask.

Local completion is intentionally not described as native acceptance. Wine
reports the policy as disabled and exercises the allow path, but it cannot
prove Windows Exploit Protection compatibility, audit, and strict modes. A
native CET-capable Windows run must still force each rejected policy family
and prove early bounded failure with no managed execution or dump.

On Windows 10 version 2004/build 19041 and later, startup queries
`GetProcessMitigationPolicy(GetCurrentProcess(),
ProcessUserShadowStackPolicy, ...)` before creating ART threads or enabling
nterp/JIT and rejects any result containing a defined incompatible field, with
a bounded diagnostic containing both the raw flags and the extracted
incompatible mask. On older supported Windows 10 builds, the documented
policy class is unavailable; only the expected unsupported-policy result is
accepted as evidence that HSP is unavailable. Unexpected query failures on
systems that implement the policy fail closed.

FS-2 adds a test-only, one-way policy override for the native acceptance
package. `ART_WINDOWS_X64_TEST_FORCE_CET_POLICY` names one SDK policy family;
the runtime ORs the corresponding bit into the real observation and therefore
cannot hide an active mitigation or make a failed query succeed. Every named
incompatible field, `CetDynamicApisOutOfProcOnly`, and low/high/all reserved
bits are exercised through this seam. Invalid or unknown override text fails
closed as an unexpected query failure. Rejected children are required to exit
before Java/JIT work and to leave the crash directory unchanged.

## 6. Designs considered

### 6.1 Selected: VEH adapter over the existing `FaultManager`

Windows `AddSpecialSignalHandlerFn(SIGSEGV, ...)` copies the ART action and
installs the managed-fault VEH. The VEH constructs a minimal `siginfo_t` and a
stack-local non-owning `WindowsFaultContext` that references the real
`CONTEXT*` and records the AV access kind. It passes that view to
`FaultManager::HandleSigsegvFault()` and translates the boolean result to a VEH
return value.

Advantages:

- implicit-null generated code is unchanged;
- common handler order and code-range checks are unchanged;
- Java exception entrypoints are unchanged;
- Linux behavior is unchanged;
- the Windows delta is limited to one dispatcher/context view for AV faults
  plus a small explicit stack check and platform stack-bound accounting.

### 6.2 Rejected for now: platform-neutral `FaultContext` refactor

A new abstract context type shared by every ISA and OS would be conceptually
clean, but it would modify common fault signatures and every architecture
handler. That creates substantially more Linux/Android regression surface
than the narrow Windows x64 adapter and provides little immediate value for a
single Windows ISA.

This remains a possible upstream-oriented cleanup after Windows x64 behavior is
proven.

### 6.3 Selected for stack only: explicit Windows x64 stack checks

Native Windows disproved the lower-divergence fixed-page candidate. Optimizing
code and nterp therefore compare RSP with `Thread::stack_end_` before the
method prologue, allow equality, and tail-jump to the existing throw entrypoint
when below it. This is intentionally stack-only: implicit null checks remain
shared and VEH-based. Object-level audits verify that Linux keeps its original
implicit probe and that the Windows x64 branch contains the exact comparison.

### 6.4 Rejected: frame-based SEH around every ART transition

SEH wrappers around every thread or managed entry do not naturally cover all
JIT/nterp execution and would duplicate fault classification in a second
control-flow model. VEH is specifically designed for process-wide observation
before frame unwinding.

### 6.5 Rejected: native Windows guard/overflow as the managed event

Relying on moving `PAGE_GUARD`, `EXCEPTION_STACK_OVERFLOW`, or `_resetstkoflw`
would change when overflow is detected and would not preserve ART's
pre-prologue frame invariant or repeated caught-overflow behavior. E9 uses
`SetThreadStackGuarantee` only to reserve/account native recovery space below
the explicit managed boundary, not as the managed event.

### 6.6 Rejected: full POSIX sigchain emulation

Intercepting CRT `signal()`/`sigaction()`-like calls does not control Windows
VEH or SEH registration. It would create an attractive but false portability
layer. The Windows `sigchain` file should expose only the ART-internal bridge
that current common code needs.

### 6.7 Rejected: partial CET repair around VEH or the JIT cache

`/guard:ehcont` and `SetProcessDynamicEHContinuationTargets()` address
continuation-target validation; they do not synchronize the hardware shadow
stack with ART's restored managed stack. Likewise,
`SetProcessDynamicEnforcedCetCompatibleRanges()` would describe dynamic code
as CET-compatible without repairing ART's non-local transfer and is not a
valid workaround. The Windows port must not call either API to bypass the
unsupported-process check.

A future CET-support project would need to redesign every x86_64 managed
exception/deoptimization/JNI non-local transfer, establish a shadow-stack-safe
continuation protocol, emit complete static and dynamic continuation metadata,
and prove VEH, SEH, JIT collection, and native unwinding together. That would
be a distinct managed-ABI project with significant Windows divergence, not a
small W-010 or W-025 patch. The current design instead requires CET shadow
stacks to be disabled.

## 7. W-010 detailed exception design

### 7.1 Components

```text
Windows exception dispatcher
  AddVectoredExceptionHandler / RemoveVectoredExceptionHandler
  AddSpecialSignalHandlerFn(SIGSEGV) facade
  exact EXCEPTION_RECORD filtering
  optional best-effort promotion to front
              |
              v
common FaultManager
  Thread::Current / runnable / mutator-lock checks
  registered generated-code range check
  StackOverflowHandler, then NullPointerHandler
              |
              v
x86_64 context adapter
  non-owning WindowsFaultContext -> real CONTEXT.Rip / Rsp
  documented AV read/write kind (and preserved R15)
  existing quick throw entrypoints
```

The managed VEH belongs with the fault backend, not with fatal dump policy.
`runtime_windows.cc` may own initialization calls, but only one component must
own the VEH handle and lifecycle.

### 7.2 `sigchain_windows.cc` contract

The first version supports exactly the special `SIGSEGV` action ART actually
registers:

- `AddSpecialSignalHandlerFn(SIGSEGV, action)` copies the action into
  process-owned storage and installs the VEH if needed.
- A second distinct special `SIGSEGV` registration is a startup error until a
  real use case requires a fixed, lock-free action array.
- `RemoveSpecialSignalHandlerFn()` clears that action and removes the VEH when
  no managed user remains.
- `EnsureFrontOfChain(SIGSEGV)` performs best-effort promotion by registering a
  new first VEH and only then removing the old handle. It must retain the old
  registration if the new registration fails. Failure to remove the old handle
  after the new one was installed is fatal, because otherwise an untracked VEH
  callback could survive runtime teardown and later call unloaded code.
- `SkipAddSignalHandler()` has no Windows signal-interposition behavior. It is
  an explicit compatibility no-op, not an indication that external handlers
  are hidden.
- Unsupported special signal numbers fail clearly rather than disappearing in
  a stub.

The copied action's POSIX mask and `SIGCHAIN_ALLOW_NORETURN` flag have no VEH
meaning. The Windows path does not simulate them.

Registration, promotion, and removal are serialized by a process mutex that
the VEH never takes. The copied action is immutable while published and is
made visible to the VEH with release/acquire ordering. Removal first
unpublishes the action, then removes the registered VEH handle. Runtime
shutdown must already have quiesced managed threads before this removal and
must not unload `art.dll` concurrently with an in-flight callback; Windows
does not provide a safe general contract for unloading handler code while
another thread is executing it.

Promotion briefly registers the same dispatcher twice. The new first handle
is installed before the old one is removed, avoiding a fault-delivery gap. A
successful managed fault resumes from the first callback, so the older handle
is not reached. An unrecognized fault can visit both copies during that short
window; both must be side-effect-free and return search. Promotion is rare and
occurs outside normal managed-fault handling.

### 7.3 VEH fast rejection

The handler immediately returns `EXCEPTION_CONTINUE_SEARCH` if any of these is
true:

- `EXCEPTION_POINTERS`, record, or context is null;
- exception code is not `EXCEPTION_ACCESS_VIOLATION`;
- the exception is non-continuable;
- fewer than two `ExceptionInformation` values are present;
- the operation is neither documented read nor write (including execute/DEP);
- `ExceptionAddress` and `CONTEXT.Rip` are inconsistent;
- no ART special action is currently published;
- the current ART thread's managed-fault recursion marker is already set.

In particular, the handler does not consume:

- `EXCEPTION_GUARD_PAGE`;
- `EXCEPTION_STACK_OVERFLOW`;
- breakpoint or single-step exceptions;
- illegal instructions;
- divide faults;
- C++/SEH exceptions;
- access violations from native code or unregistered code ranges.

The AV operation (read or write) and inaccessible address come from the
documented `ExceptionInformation[0]` and `[1]` fields. The synthetic
`siginfo_t` uses `SIGSEGV`, `SEGV_ACCERR`, and that exact address. A
stack-local Windows-only view carries the access kind alongside a pointer to
the real `CONTEXT`; it is consumed synchronously and never retained.

After the cheap record checks, the dispatcher obtains `Thread::Current()`.
A thread without an ART `Thread` immediately continues search. Otherwise the
dispatcher sets a one-byte W-010 recursion state in that `Thread`, invokes the
published action, and clears the state before returning. A nested fault while
the state is set is never translated, preventing recursive validation loops
without introducing a second OS TLS scheme.

### 7.4 Non-owning Windows x64 context adaptation

Under `_WIN32 && __x86_64__`, `fault_handler_x86.cc` should unwrap a minimal
platform view such as:

```cpp
struct WindowsFaultContext {
  CONTEXT* context;
  ULONG_PTR access_type;  // 0 read, 1 write; execute was rejected by VEH.
};
```

Its PC and SP accessors refer to `context->Rip` and `context->Rsp`; register
updates therefore modify the OS-owned context in place. Linux and Apple retain
their existing `ucontext_t` definitions. The wrapper is not a portable
context abstraction and is not copied back after dispatch.

Declare the view and AV-kind constants in a Windows-only fault header included
by `sigchain_windows.cc` and the `_WIN32` branch of
`fault_handler_x86.cc`. Keep `FaultManager`'s existing opaque `void*` context
signature and keep Windows SDK types out of common headers. This limits Linux
source changes to a conditional x86 accessor branch rather than a cross-ISA
interface refactor.

This is preferable to fabricating a full `ucontext_t` because:

- the common null handler modifies only the saved PC and SP for current Windows x64
  AV-based implicit faults;
- all untouched integer and vector registers remain in the real OS context;
- rSELF in R15 is restored by Windows automatically;
- no copy-back list can accidentally omit a register;
- an AV handler can validate the documented access kind without abusing
  unused `siginfo_t` fields or process-global state;
- the null trampoline observes the original interrupted register set when the
  OS resumes it.

Before dispatch, Windows additionally validates that `CONTEXT.R15` equals
`Thread::Current()` for a managed x86_64 fault. This is a Windows managed-ABI
invariant and reduces false classification.

### 7.5 Generated-code and thread checks

The common `FaultManager::IsInGeneratedCode()` remains authoritative:

- current thread exists;
- state is `kRunnable`;
- shared mutator lock is held;
- saved PC lies in a registered nterp/JIT/oat range.

The Windows adapter must not use `VirtualQuery`, symbol lookup, allocation,
logging, minidump code, or a complex lock on this path. Generated-code range
publication remains lock-free for readers. For the imageless product, nterp
and JIT ranges must be registered before their entrypoints are published to
other threads.

The Linux-only `membarrier()` registration in `FaultManager::Init()` must not
emit an expected `ENOSYS` warning on Windows. Windows range safety comes from
the existing atomic list plus ordering code-range registration before managed
entrypoint publication. Future restricted ELF OAT loading must register its
validated Windows function table and code range before publishing any managed
entrypoint, and reverse that order before unmapping.

### 7.6 Stack-overflow detection

E9 does not route Windows x64 stack overflow through `FaultManager`. Optimizing code
and nterp compare the live RSP with `Thread::stack_end_` before establishing a
frame. `RSP == stack_end_` is allowed; `RSP < stack_end_` tail-jumps through
`Thread::pThrowStackOverflow`. The bound already includes the native recovery
interval plus ART's configured reserve: 8192 bytes in product and non-Windows
builds, or 40960 bytes only in a non-`NDEBUG` Windows x86_64 build.

The former read-AV, `RSP - 8192`, and fixed-page-containment classifier remains
historical/diagnostic code only. Linux retains the equivalent implicit
classification unchanged.

On success, only `CONTEXT.Rip` changes:

```text
Rip = art_quick_throw_stack_overflow
Rsp unchanged
R15 unchanged
return EXCEPTION_CONTINUE_EXECUTION
```

The quick entrypoint and `ThrowStackOverflowError()` then perform the same ART
work as Linux.

### 7.7 Null-pointer classification

If the stack handler declines, the existing null handler checks:

- fault address is in ART's implicit-null range;
- the top-of-stack `ArtMethod*` is plausible;
- the faulting PC has an oat/nterp method header;
- the decoded instruction and return PC are valid for an implicit null check.

It pushes the return PC and fault address on the interrupted stack, changes
saved SP, and changes saved PC to
`art_quick_throw_null_pointer_exception_from_signal`. The existing quick
trampoline preserves the interrupted register set, calls
`artThrowNullPointerExceptionFromSignal`, and performs ART's managed long jump.

Nested faults while validating a candidate are not recursively translated.
The recursion marker causes the nested VEH invocation to continue searching,
producing a normal fatal crash rather than an infinite handler loop.

### 7.8 Handler chaining and diagnostics

The product handler has no first-chance logging. Expected implicit faults are
normal control flow and logging from VEH can allocate, take locks, consume
stack, or alter timing.

For unrecognized faults:

1. ART VEH returns `EXCEPTION_CONTINUE_SEARCH`.
2. Later VEH and frame-based SEH handlers remain eligible.
3. The debugger receives its documented second-chance opportunity if nothing
   handles the exception.
4. The process unhandled-exception filter may write a best-effort minidump.

`SetUnhandledExceptionFilter()` replaces the previous process filter. ART must
store that returned pointer. After its best-effort dump, it calls the previous
filter when non-null and not itself and returns that filter's result; otherwise
it returns `EXCEPTION_CONTINUE_SEARCH`. The UEF is fatal diagnostics, not
W-010 managed translation, and can be replaced by an embedding application
later.

Stage A already closes the basic unload hazard: runtime teardown removes the
diagnostic VEH while `art.dll` is executable and restores ART's predecessor
only if ART is still the current UEF. If an embedding application installed a
later UEF, teardown preserves that later filter. The fatal UEF now calls the
saved predecessor after the best-effort dump when one exists, and otherwise
returns `EXCEPTION_CONTINUE_SEARCH`.

The FS-2 embedding probe exercises this contract through JNI Invocation rather
than through a product-only shortcut. It installs a foreign search VEH and a
predecessor UEF before creating ART, raises a continuable unrecognized AV to
prove ART's UEF calls the predecessor, catches a separate AV with frame-based
SEH, installs a later embedding UEF, destroys the VM, and checks that the later
UEF remains current. It then unloads the ART image when possible and repeats
the frame-SEH case; the foreign VEH must still search and no stale ART callback
may execute. The predecessor case intentionally produces one diagnostic dump;
the handled frame-SEH cases must not.

PE unwind metadata is part of exception-dispatch correctness on Windows x64, not
only minidump quality. Recursive `RtlVirtualUnwind2` tracing of the JNI fatal
probe showed the exact failure mode: without a runtime-function record,
Windows treats the current instruction as a leaf, pops whatever the managed
frame happens to contain as a return address, and may later reject the
fabricated frame before the UEF can run.

The first locally implemented boundary set is deliberately small:

- `art_quick_generic_jni_trampoline` uses `R12` as a fixed PE frame anchor
  above its 5120-byte reserved area while preserving ART's canonical managed
  `RBP` meaning.
- `art_quick_invoke_stub` and `art_quick_invoke_static_stub` schedule their
  fixed Windows x64 saves before variable argument decoding, fit the PE prologue in
  255 bytes, and use `RBP` to anchor the frame above the variable argument
  area.
- The invoke records describe RDI, RSI, RBP, RBX, R12-R15 and XMM6-XMM15; a
  structural verifier resolves the exports and checks the emitted `.pdata` /
  `.xdata` records instead of trusting assembly source annotations.
- `art_quick_osr_stub` uses one R12-anchored entry range for the fixed save
  area and variable copied-stack body. Immediately before the OSR jump it sets
  `RBP = RSP`, reproducing the anchor that normal Windows x64 JIT entry establishes
  after its prologue. The contiguous return range is RSP-based and does not
  assume OSR code preserved either anchor. The emitted verifier checks both
  records and exact save offsets; the live probe virtually unwinds the
  variable body, return body, and canonical return epilogue.

Under Wine those records make the static `-Xint` JNI crash path reach the UEF
and produce a valid minidump. Native build 19044 reaches the diagnostic VEH but
does not reach UEF even while ART still owns the UEF slot. Section 7.9
complements the static records with range-accurate one-entry
`RtlAddFunctionTable` records for dynamically generated optimizing and JNI JIT
methods, tied to the code-cache allocation lifetime. The threshold-zero J-2 and
J-1 JIT-origin and switch-OSR-origin fatal gates cross their complete exercised
chains under Wine, reach UEF, and each create a valid dump. Dumping directly from the
diagnostic VEH remains unnecessary and would not restore foreign frame-based
SEH semantics; debugger-quality dump stack reconstruction and native stress
remain native-host work.

The GenericJNI `.pdata` record covers the trampoline body with an R12 frame
anchor and a 5120-byte allocation. A realistic synthetic gate now builds the
completed 200-byte canonical frame, R12-anchored reserved area, and variable
normal-JNI outgoing RSP, then calls `RtlVirtualUnwind()` at the run-3 native-
call return PC, `art_quick_generic_jni_trampoline + 0xc5`. The first run found
that `.seh_savereg %rdi, 0` addressed the bottom of the reserved area even
though RDI is physically saved 5120 bytes above R12. The corrected record uses
offset `0x1400` and restores caller RIP/RSP plus RBP/RDI/RSI/RBX/R12-R15.
Structural inspection now requires the exact RDI offset. This closes the
isolated GenericJNI virtual-unwind coverage gap. Native run 4 nevertheless
shows the two JNI-thread exception shapes still miss UEF while the native
worker reaches it, so another frame or boundary above GenericJNI remains.

The E4 opt-in diagnostic now walks from a copy of the live context in ART's
existing diagnostic VEH. It is off by default, bounded to 32 frames, validates
stack/leaf progress, reports module-relative RVAs, and does not alter dispatch
or run before the managed translator.

### 7.9 Dynamic JIT PE unwind design

#### 7.9.1 Required result

Every executable byte emitted into the Windows x64 JIT code cache must have a
range-accurate Windows runtime-function entry before any thread can obtain an
entrypoint to it. The record must remain registered, and every byte it
references must remain allocated, until the code is no longer executable and
cannot be present on a thread stack. This applies to optimizing JIT methods,
OSR methods, and JIT-generated JNI stubs. The x86_64 fast compiler is Arm64-
only in the current tree and therefore adds no separate Windows x64 producer.

This metadata has one purpose: make Windows exception dispatch and
`RtlVirtualUnwind2()` recover the caller's control state reliably enough to
cross all managed frames and reach a native frame-based SEH handler or the
UEF. It does not replace ART stack maps, does not install a language-specific
handler on managed methods, and does not claim full debugger-quality register
reconstruction at each intermediate managed frame.

Microsoft's x64 contract requires a runtime-function entry for every function
that allocates stack space or calls another function. A missing entry is
treated as a leaf and causes the unwinder to consume `[RSP]` as a return
address. `RUNTIME_FUNCTION` and `UNWIND_INFO` must be DWORD-aligned; the
function table is sorted by `BeginAddress`; all three runtime-function fields
are unsigned 32-bit offsets from the registration base; unwind-code offsets
are instruction-end offsets in descending order; and the prologue length is
limited to 255 bytes.

#### 7.9.2 Why a fixed-RSP recipe is insufficient

The ordinary optimizing prologue is deterministic: it pushes the allocated
subset of RBX, RBP, R12, R13, and R14 on Windows, subtracts the fixed frame,
and stores any managed XMM12-XMM15 spills. The function body is not uniformly
fixed-RSP, however. The current x86_64 source contains all of these temporary
adjustments:

- direct CriticalNative calls reserve and later release their native outgoing
  area with `FinishCriticalNativeFrameSetup()`, `IncreaseFrame()`, and
  `DecreaseFrame()`;
- floating-point remainder reserves 8 or 16 bytes while using the x87 stack;
- SIMD parallel-move swaps reserve a 16-byte temporary;
- the parallel-move resolver can push and pop a scratch GPR.

Those paths are not all predictable from `HGraph::HasDirectCriticalNativeCall()`
before register allocation. A record based only on the normal body `RSP`
would still fail if an AV, breakpoint, illegal instruction, debugger stop, or
native unwind lands in one of these intervals.

JIT-generated normal and FastNative JNI stubs have a second form of the same
problem: their canonical ART frame is fixed, but they move `RSP` for the main
native outgoing area and on reference-return or suspend slow paths. A
CriticalNative JNI stub is different: its outgoing area is included in its
initial fixed allocation and the x86_64 path has no applicable x87 move, so a
fixed-RSP record is sufficient for that stub.

PE chained unwind information does not provide a clean escape hatch.
Microsoft permits chained records for noncontiguous code and delayed
`UWOP_SAVE_NONVOL` saves, but explicitly does not support a chained fragment
that adds another fixed stack allocation. Describing every temporary interval
as a separate pseudo-prologue would therefore be both fragile and outside the
documented chained-record model.

#### 7.9.3 Selected frame rule

All optimizing methods emitted by the Windows x64 JIT reserve `RBP` as a PE frame
anchor. Linux and non-JIT Windows compilation remain byte-for-byte on their
existing path.

The Windows JIT code generator shall:

1. block `RBP` from ordinary register allocation and force it into the
   allocated callee-save set, including methods that would otherwise have an
   empty frame;
2. push the caller's `RBP` through the existing ART callee-save sequence;
3. allocate the unchanged canonical ART frame and leave all ART stack-map,
   spill-mask, method-slot, and `RSP`-relative addressing rules intact;
4. set `RBP = RSP` after the fixed allocation, recording
   `UWOP_SET_FPREG` with a zero scaled offset;
5. leave `RBP` unchanged across every body-time `RSP` adjustment; and
6. restore it through the existing pop sequence on normal return.

This adds one reserved register, one forced spill, and one frame-anchor
instruction only to optimizing Windows x64 JIT methods. It does not change Java
exception checks, the managed calling convention, stack maps, Linux code
generation, or the layout expected by common ART stack walking. The cost is
some Windows-only register pressure and a small frame/code-size increase. That
cost is preferred to annotating every present and future temporary stack
adjustment.

Normal and FastNative JIT JNI stubs use the same `RBP = canonical RSP` rule.
They already spill `RBP`; the Windows scratch-register list must stop assigning
it to JNI state after the anchor is established. RBX and R12-R14 provide the
four scratch registers the current JNI compiler requires. CriticalNative JNI
stubs retain their existing fixed-RSP shape and receive a fixed-RSP unwind
record rather than an artificial managed frame.

The normal method epilogue is already in a Windows-recognizable form once
temporary body adjustments have been balanced: `add RSP, fixed`, zero or more
GPR pops, and `ret`. Managed XMM restores occur before that sequence and are
ordinary body instructions for PE purposes.

#### 7.9.4 Native XMM boundary rule

ART intentionally keeps its SysV-shaped managed x86_64 ABI on Windows.
Managed code preserves only the low 64-bit scalar state of XMM12-XMM15, while
the Microsoft x64 ABI requires the lower 128 bits of XMM6-XMM15 to survive a
native call. Expanding every managed spill slot to 128 bits would change frame
layout, stack maps, JNI frame calculations, and code size throughout the
Windows compiler.

The implemented lower-divergence rule adapts at native-to-managed entry boundaries:
the invoke and OSR stubs must save and restore the full 128-bit XMM6-XMM15
native state outside the canonical ART managed frame, and every boundary PE
record must describe the saves that can participate in Windows unwind. The
implementation now covers XMM6-XMM15; the emitted unwind verifier covers both
invoke records plus the OSR entry and return records. The unwind offsets are
relative to the completed fixed frame, not the temporary RSP used by each
store: the ten saves occupy offsets 64 through 208 after accounting for the
later 64 bytes of fixed GPR and bookkeeping state. The live OSR probe proves
that `RtlVirtualUnwind()` restores all ten values from both OSR ranges and
synthetically unwinds both invoke records. The normal-return sentinel seeds,
checks, and restores all ten registers and passes 2/2 in nterp, switch, and
threshold-zero JIT under Wine. Its historical `selfTestMask=63` marker is
retained for W-003 evidence compatibility; `fullSelfTestMask=1023` is the
authoritative XMM6-XMM15 result. Native Windows must repeat both the normal-
return and exception-unwind cases before Stage E acceptance.

FS-2 extends the sentinel with a managed callback that reads a null reference
after doing floating-point work and lets the resulting `NullPointerException`
escape through `CallStaticIntMethod`. The native assembly records the full
XMM6-XMM15 mask after ART's managed non-local transfer and before returning the
pending JNI exception. Thirty-two normal exception escapes must report
`exceptionMask=0`; a deliberate native-register clobber must report the full
`exceptionSelfTestMask=1023`. The normal-return and exception paths each carry
ten `UWOP_SAVE_XMM128` records.

Intermediate dynamic managed records describe the stack allocation, frame
anchor, and pushed nonvolatile GPRs needed to recover caller control state.
They do not pretend that ART's 64-bit scalar XMM12-XMM15 spills are valid
`UWOP_SAVE_XMM128` operations. Once Windows reaches the native-to-managed
boundary, that boundary restores the complete native nonvolatile XMM state
before any outer native SEH handler observes the context.

#### 7.9.5 Explicit unwind bytes, not DWARF translation

The existing assembler CFI is not a suitable production source for PE data:

- optimizing and JNI CFI is enabled only when `GenerateAnyDebugInfo()` is
  true, while exception correctness must not depend on debug-info policy;
- it is DWARF CFA state, not serialized PE `UNWIND_INFO`;
- it records body-time CFA changes that PE's single-prologue format cannot
  directly express; and
- parsing it later would duplicate architecture decisions already known at
  the instruction emission sites.

The x86_64 assembler shall therefore build a small explicit Windows x64 unwind
descriptor while it emits the prologue. It records actual instruction-end
offsets for pushed GPRs, the fixed allocation, and the frame-anchor
instruction, then serializes version-1 `UNWIND_INFO` bytes. It chooses the
shortest legal `UWOP_ALLOC_SMALL` or `UWOP_ALLOC_LARGE` form, emits unwind
codes in descending offset order, pads the code array to an even slot count,
and produces the minimum eight-byte structure when no operations are needed.

The compiler-facing value is an opaque byte vector plus code size; Windows SDK
types stay in the runtime registration helper. Serialization must reject, and
cause that JIT compilation to fall back, if the prologue exceeds 255 bytes, an
offset or allocation is not encodable, the frame register is inconsistent, or
the method range cannot be represented. Production generation is independent
of DWARF CFI. Tests may decode both formats and compare their common fixed-
frame facts.

#### 7.9.6 Placement and relative-address base

The placement is implemented end to end. The x86_64 assembler serializes an
SDK-independent byte vector, optimizing JIT code forces and establishes the
selected `RBP` anchor, normal/FastNative JIT JNI stubs use the same anchor, and
CriticalNative emits the fixed-RSP descriptor. Invalid or missing enabled
metadata rejects compilation before `Reserve()`. The vector is carried by
`JniCompiledMethod` or the common assembler API into `Reserve()` and `Commit()`.

The corrected J-2 layout already provides the topology PE unwind needs:

```text
primary_base
  read-only JIT data, including UNWIND_INFO
  immediately followed by executable JIT code
primary_end < 4 GiB
```

The diagnostic J-1 layout preserves the same primary data/code adjacency and
low-4-GiB rule. Each unwind blob is appended, with four-byte alignment, to the
method's existing JIT data allocation after roots and `CodeInfo`. It is written
through the RW data alias and read by Windows through the primary read-only
view. Adding bytes after `CodeInfo` does not change the code-to-stack-map
offset stored in `OatQuickMethodHeader`.

For both layouts, `RtlAddFunctionTable()` receives the primary mapping start
as `BaseAddress`. The one-entry `RUNTIME_FUNCTION` then contains:

```text
BeginAddress      = code_begin - primary_base
EndAddress        = code_end   - primary_base   // exclusive
UnwindInfoAddress = unwind_ro   - primary_base
```

The existing maximum region size is 1 GiB and the complete primary view is
below 4 GiB, so all three unsigned differences fit in 32 bits. The runtime
still checks every subtraction and alignment rather than relying on the
mapping assertion implicitly.

The `RUNTIME_FUNCTION` object itself lives in stable native registry storage;
it need not be below 4 GiB. Its referenced `UNWIND_INFO` must remain at the
registered base-relative address until deletion completes.

#### 7.9.7 Registration ownership and publication order

The implemented design uses one immutable, one-entry
`RtlAddFunctionTable()` registration per JIT code allocation. A one-entry
array is trivially sorted. The exact table pointer is retained because
`RtlDeleteFunctionTable()` requires the pointer originally registered.

Windows types and API calls live in a narrow
`runtime/multiplatform/windows/jit_unwind_windows` registry owned by
`JitCodeCache`. Common compiler and JIT interfaces pass only opaque unwind
bytes and addresses. The registry is keyed by the executable code pointer and
is protected by `Locks::jit_lock_`, matching code allocation, commit, and
free.

`JitCodeCache::Reserve()` includes the aligned unwind byte count in the data
allocation. `Commit()` uses this strict order while holding the JIT lock:

1. copy the method header and code through the writable code view;
2. copy roots, `CodeInfo`, padding, and unwind bytes through the writable data
   view and flush both mappings;
3. construct the stable one-entry runtime-function object;
4. call `RtlAddFunctionTable()` and insert the successful registration in the
   ownership map;
5. add native debug information and CHA dependencies; then
6. publish the JNI stub, OSR map, method map, saved entrypoint, or ordinary
   `ArtMethod` entrypoint.

Registration failure returns a normal JIT compilation failure while the code
is still unreachable. The caller's existing rollback calls `Free()`. Rollback
after a later CHA or commit failure uses the same unregister-before-free path.
No entrypoint or code-map insertion may precede successful registration.

#### 7.9.8 Removal, reuse, and teardown order

`FreeLocked()` is the single allocation-level removal gate. If a registration
exists for the code pointer, it must perform this order:

1. call `RtlDeleteFunctionTable()` with the exact retained table pointer;
2. remove the registry entry only after successful deletion;
3. remove native debug information;
4. free the code allocation; and
5. free the data allocation containing `UNWIND_INFO`.

Deletion failure is fail-closed: the code and data are not released or reused
while Windows may still reference them. The implementation may quarantine the
allocation and report an error during ordinary collection; teardown must not
unmap a region with a live registration and therefore treats a remaining
deletion failure as fatal.

This gate covers direct compiler rollback, `FreeAllMethodHeaders()`, code-
cache GC, JNI stub retirement, class-loader removal, method redefinition,
testing removal, and OSR cleanup. `FreeAllMethodHeaders()` remains the main
bulk funnel; it already removes CHA dependencies before allocations can be
reused. `JitCodeCache` destruction unregisters every remaining private and
shared registration before `RemoveGeneratedCodeRange()` and before either
mapping is destroyed.

ART's existing collection protocol marks code present on thread stacks before
freeing an unmarked zombie. Entry points are invalidated before collection,
and method-redefinition/testing removal already requires all threads suspended
and the code absent from stacks. These are the no-executing-code preconditions
for deletion. The Windows API supplies its own dynamic-table synchronization;
ART does not add a callback-time lock or attempt to unregister code that can
still execute.

The focused lifecycle gate exercises this product collection funnel in both
J-2 and J-1. It verifies that invalidation alone retains the lookup, collection
removes it, the mspace allocator reuses the exact code address, and recompilation
installs a resolvable replacement record before the method executes.

#### 7.9.9 Alternatives considered

`RtlAddGrowableFunctionTable()` is not selected. Its entries must remain
sorted, `RtlGrowFunctionTable()` only increases the visible count, and the
contract provides no shrink or reorder operation. ART's mspace allocator
reuses lower-address holes after rollback and collection, so a single
monotonic table would either retain stale ranges or require stopping and
rebuilding a live table.

`RtlInstallFunctionTableCallback()` is not selected for the first complete
design. It matches highly dynamic code in principle, but the callback runs in
exception/stack-walk context and Microsoft explicitly warns against deadlock
with the code generator. A correct implementation would need a preallocated,
lock-free PC index, stable record reclamation, and a packaged out-of-process
callback DLL for debugger unwinding. That is substantially more machinery
than immutable per-allocation records and creates a second crash-time lookup
path beside ART's code maps.

One callback table remains a possible future scalability replacement if a
native stress gate proves that many one-entry tables make
`RtlLookupFunctionEntry()` or sampling unacceptably slow. It must preserve the
same publication/removal invariants and cannot be adopted without explicit
concurrent collection and out-of-process debugger tests.

Multiple runtime-function fragments around every temporary `RSP` interval are
not selected. They require annotations in unrelated code-generation helpers,
are easy to miss as new moves are added, and chained unwind information cannot
describe additional fixed stack allocations in the documented model.

Changing all Windows managed frames to the Microsoft native ABI is not
selected. It would alter argument registers, callee saves, XMM widths, stack
maps, quick stubs, and shared generated-code assumptions. The selected anchor
and boundary adapters isolate the required Windows behavior without changing
Linux ART or Java-visible semantics.

Dumping from the diagnostic VEH remains diagnostics only. It cannot repair
frame-based SEH dispatch, predecessor UEF behavior, or debugger unwinding.

#### 7.9.10 Verification gates

The following local J-2 and J-1 checks pass:

- serialization tests for empty/small/large frames, every pushed GPR subset,
  zero-offset RBP anchors, normal/FastNative JNI, and fixed-RSP CriticalNative
  JNI;
- standalone add/lookup/`RtlVirtualUnwind`/delete/re-register coverage;
- production code-cache invalidation, collection, lookup disappearance, exact
  mspace address reuse, re-registration, and replacement-code execution;
- threshold-zero fatal dispatch through an optimizing caller and JIT JNI stub
  to VEH, UEF, and a new valid minidump;
- structural `.pdata`/`.xdata` inspection plus live `RtlVirtualUnwind()` of
  the OSR variable copied-stack body, inherited-frame return range, and return
  epilogue, followed by the 8/8 dual/J-1 default/switch OSR execution matrix;
  and
- normal/FastNative and CriticalNative ABI regressions plus Linux compiler and
  runtime rebuilds.

Native JIT-3/FS-3 on Windows Server 2025 build 26100 now extends the focused
lifecycle result across 52 collection cycles, 1,344 optimizing/normal-JNI
compilations, 1,248 exact address reuses, 696,929 stable-live lookups,
5,909,811 stable-dead lookups, and 696,969 successful virtual unwinds. It
reports zero missing live records, stale dead records, and unwind failures;
per-run maximum lookup time is 122,800-706,100 ns, and callback tables remain
unused. All eight JNI targets retain exact values after ART `43f866830e`
corrected the Windows nterp hard-float return adapter to preserve XMM0.

Native JIT-4 on the same build adds the final default-J-2 cross-regression. Its
28 cases and 34/34 aggregate PASS records repeat the exact smoke/matrix,
JIT-disabled controls, CriticalNative and normal/FastNative ABI paths, nterp
and switch OSR, eight lifecycle cycles, and static/JIT/OSR fatal origins. The
lifecycle repeat records eight collections, 216 compilations, 192 exact
reuses, 85,938 live lookups, 855,876 dead lookups, and 85,944 virtual unwinds
with zero missing/stale/failed records. All three fatal origins reach VEH/UEF
and create valid `MDMP` files. No J-1 arm ran, `jit-temp` remained empty, and
no trace remained.

Native JIT-5 repeats that boundary after removing the Windows J-1 opt-out and
single-view fallback. Its source/binary gate requires fail-closed section
construction and proves both retired strings are absent from `art.dll`; the
inert-key smoke sets `ART_WINDOWS_X64_JIT_DUAL=0` and still creates J-2. The
29-case, 36/36 archive repeats eight collections, 216 compilations, 192 exact
reuses, and 120,654 successful virtual unwinds with zero missing/stale/failed
records. Static, threshold-zero JIT, and OSR fatal origins again reach VEH/UEF
and produce three valid dumps. This closes W-025 while leaving the debugger,
forced-CET-policy, exception-XMM, embedding, reservation-correlation, and
second-host work below unchanged; FS-5 later records the pending-range
conditional disposition.

The remaining acceptance and stress gates are:

- compiler tests containing direct CriticalNative, FP remainder, SIMD swaps,
  and scratch spills, proving every temporary `RSP` interval unwinds from the
  fixed RBP anchor;
- a production-no-debug-info run proving PE unwind bytes do not depend on
  DWARF CFI generation;
- recursive `RtlVirtualUnwind2()` tracing through the complete fatal native AV
  chain, including the static invoke boundary and outer native frame;
- native Windows lookup/unwind and fatal-dispatch acceptance for both static
  OSR runtime-function ranges;
- a foreign frame-based SEH wrapper around a threshold-zero invocation, plus
  the existing UEF/minidump gate;
- rollback fault injection before registration, after registration, and at
  CHA rejection, proving no stale table or leaked published entrypoint;
- method-redefinition and OSR-specific extensions to the accepted optimizing/
  JNI collection churn, verifying the same deletion/reuse invariants on those
  less common retirement paths;
- native Windows repetition of the full XMM6-XMM15 boundary sentinels across
  normal return and managed exception unwind, with both ordinary and
  deliberate-clobber masks (FS-2 accepted; see the native evidence bundle);
- a debugger first-chance/continue run in which managed NPE handling completes
  after the debugger continues the AV, while explicit SOE reports no AV,
  stack-overflow, or other hardware-fault first chance event (FS-2 accepted);
- a JNI embedding run covering predecessor UEF chaining, foreign VEH/frame-SEH
  search, later-UEF preservation, and runtime teardown (FS-2 accepted); and
- Linux optimized/JNI CFI tests and full ART rebuilds, proving no non-Windows
  code-generation change.

### 7.10 Static OSR boundary unwind design

`art_quick_osr_stub` cannot use one ordinary native frame recipe from entry to
return. Before the OSR jump, its fixed 248-byte save area is stable, but the
compiled target has not executed the normal JIT prologue that establishes its
RBP frame anchor. After the jump, RBP must identify the copied compiled frame;
after the compiled method returns, it contains the managed value reconstructed
from that copied frame. One register therefore cannot serve both the static
copy stub and the dynamic JIT frame.

The implemented layout therefore has two contiguous PE runtime-function
ranges:

```text
art_quick_osr_stub entry range
  capture Microsoft stack arguments
  push native RBP/RDI/RSI
  reserve and save XMM6-XMM15
  save result/shorty slots and RBX/R12-R15
  push null ArtMethod slot
  R12 = fixed RSP
  jump around the variable-copy body
  variable-copy body: move RSP downward, copy, jump to OSR code
  immediately before jump: RBP = copied RSP
  final instruction: call variable-copy body

contiguous OSR return range
  entry RSP = original native RSP - 248
  restore from fixed RSP offsets without trusting managed RBP
  add RSP, 248
  ret
```

The call is deliberately the final instruction in the first range, so its
return address is exactly the first byte of the second range. The entry record
uses `FrameRegister=R12`, `FrameOffset=0`, and covers the variable copied-stack
interval. The final `mov RBP,RSP` is the explicit bridge to the dynamic JIT
contract; its generated code and unwind metadata remain unchanged. The return
record has a zero-length logical prologue and describes the already inherited
fixed frame with `UWOP_ALLOC_LARGE(248)`,
`UWOP_SAVE_NONVOL` for RBP/RDI/RSI/RBX/R12-R15, and `UWOP_SAVE_XMM128` for
XMM6-XMM15. Its executable body performs the same restores and ends in the
canonical `add rsp, 248; ret` epilogue.

This split is Windows-only. Linux retains the original call, shared restore
sequence, CFI state, and control flow. The Windows x64 entry still uses the same
248-byte components and the same copied managed stack; only the order of the
fixed native saves and the placement of the variable-copy body differ.

The unified W-010 `windows_w010_boundary_unwind_structure` reviewer resolves
private stub RVAs from `art.pdb` and verifies exact emitted `art.dll` records,
including the contiguous return range and completed-frame XMM offsets, without
adding DLL exports. The standalone
`win32_osr_unwind_probe` resolves both records with
`RtlLookupFunctionEntry()`, places RSP 256 bytes below the fixed frame, and
proves variable-body, R12-anchored entry unwinding with a clobbered RBP,
managed-RBP-independent return-body, and epilogue unwinding with GPR and XMM
restoration. Wine passes this live probe, the actual 8/8 OSR execution matrix,
and the J-2/J-1 OSR-origin fatal matrix. Unified native W-010 passes the linked
record audit and static/JIT/OSR fatal matrix; the zero-prologue
inherited-frame record is a deliberate platform adapter and must not be
generalized to ordinary called functions.

## 8. W-014 detailed stack design

### 8.1 Authoritative bounds helper

The helper runs only on the thread whose stack is being attached. The
`pthread_t` parameter in the current common helper does not justify inspecting
an arbitrary thread.

Algorithm:

1. Reject `IsThreadAFiber() == TRUE`. Bounds coincidence is not sufficient to
   enforce the v1 no-fiber contract because a fiber can have its own valid
   stack allocation.
2. Read a current SP value without allocating a large frame.
3. Call `GetCurrentThreadStackLimits(&low, &high)`.
4. Require:
   - `low < high` with no wrap;
   - both bounds page-aligned;
   - `low < SP < high`;
   - `high - low` fits in `size_t`.
5. Call `VirtualQuery(SP)` and require:
   - success;
   - `MEM_COMMIT`;
   - `MEM_PRIVATE`;
   - `AllocationBase == low`;
   - the SP lies inside the returned region.
6. Walk `[low, high)` with `VirtualQuery()` outside any fault context. Require
   contiguous coverage, no `MEM_FREE`, the same `AllocationBase`, and an exact
   end at `high`. Accept reserved and committed subregions because Windows
   grows stacks on demand.
7. Let common `Thread::InitStack()` apply ART's minimum-stack formula before
   publishing the attached thread.
8. Optional probes may read documented `NT_TIB.StackBase` and changing
   `StackLimit` for bounded diagnostics only. Neither participates in product
   acceptance, and undocumented `DeallocationStack` is never read.

Failure rejects attachment. There is no clamp, 1 MiB fallback, or attempt to
protect a partially trusted address. The pthread facade still reports one page
through `pthread_attr_getguardsize()` as a compatibility value, but Stage B's
platform helper replaces that input with the measured excluded-low prefix
before common ART stack accounting. ART never treats the facade value as the
Windows moving guard or as a fixed-page location.

### 8.2 Fiber and manual-stack policy

Microsoft documents that user-mode code can execute outside the system stack
allocation. ART rejects a fiber explicitly with `IsThreadAFiber()` and rejects
any other attachment whose current SP is outside `[low, high)`, using a
low-stack-safe diagnostic. This makes these unsupported in the first product:

- all active fibers, even if Windows reports internally consistent bounds;
- user-mode schedulers on manually switched stacks;
- arbitrary caller-provided `pthread_attr_setstack()` addresses.

This is safer than pretending a manual stack belongs to Windows thread-stack
growth machinery.

### 8.3 Accepted Windows lower-stack layout

E9 uses this conceptual layout:

```text
high / GetCurrentThreadStackLimits.HighLimit
  normal native and managed frames
  ... Windows committed/reserved regions; moving PAGE_GUARD may be here ...
stack_end
  ART overflow reserve: 8 KiB on x86_64
  one Windows moving PAGE_GUARD page, excluded from ART accounting
  configured SetThreadStackGuarantee region, at least four pages
  inaccessible low memory prefix measured with VirtualQuery
low / GetCurrentThreadStackLimits.LowLimit
```

The excluded-low value is not a guessed pthread guard size. The helper finds
the complete inaccessible prefix, page-rounds the verified configured
guarantee, and adds one system page for the moving guard. Each addition and the
remaining minimum usable stack are overflow-checked. No mapping or protection
is changed.

The previous fixed-page selector remains in the current tree only for direct
diagnostic tests. Its algorithm is:

The page-selection algorithm is:

```text
candidate = low + gPageSize

while candidate region is PAGE_NOACCESS or PAGE_GUARD:
    preserve the complete region
    candidate = end of region

require one page at candidate is either:
    MEM_RESERVE, or
    MEM_COMMIT + MEM_PRIVATE + ordinary PAGE_READWRITE

reject every other state/protection/type

excluded_low_bytes = candidate - low
art_page_begin = candidate
art_page_end   = art_page_begin + GetStackOverflowProtectedSize()
stack_begin    = art_page_end
stack_end      = stack_begin + GetStackOverflowReservedBytes(kX86_64)
```

Selection is bounded by the already validated allocation and must still leave
the protected size, overflow reserve, and minimum normal stack above it. It
does not scan upward past arbitrary incompatible mappings in search of a
convenient page. The first implementation supports the normal one-page
protected size. Memory-tool configurations with scaled protected sizes need
separate Windows validation before being enabled.

The diagnostic selection is bounded by the validated allocation. Its
`excluded_low_bytes` is not used as the E9 product layout. Common `InitStack()`
receives the complete E9 excluded-low sum described above.

### 8.4 Diagnostic-only protected-page installation

Product `Thread::InitStack()` does not install a fixed page. The following
state machine is retained only for `win32_stack_page_probe` and related direct
diagnostics:

For the exact target range:

1. Verify it lies wholly inside the validated stack allocation and below the
   current ART usable range.
2. Require that it is not `PAGE_GUARD` or `PAGE_NOACCESS`, then record its
   original `VirtualQuery()` state, type, and protection for detach/fatal
   diagnostics.
3. If the original page is reserved, commit it with
   `VirtualAlloc(begin, size, MEM_COMMIT, PAGE_READWRITE)` and require the exact
   returned address. Leave an already committed-private read/write candidate
   committed and preserve its contents.
4. Change it to `PAGE_NOACCESS` with `VirtualProtect()`.
5. Query it again and require `MEM_COMMIT`, the expected allocation base, and
   `PAGE_NOACCESS` without `PAGE_GUARD`.
6. Publish the page address and `Protected` state in the diagnostic record.

If protection fails after a reserved page was committed, the helper restores
and verifies the original page state before failing the diagnostic. It never
clears ownership of an unrestored test page.

The Windows diagnostic does not run Linux's recursive `VM_GROWSDOWN` touching
and does not `madvise()` the stack.

### 8.5 Diagnostic protection state machine

Each direct diagnostic record uses:

```text
NotInstalled
  -> Protected
  -> WritableForStackOverflow
  -> Protected
```

The diagnostic unprotect/protect helpers change exactly the recorded page and
verify the old/new allocation, range, type, and protection. The accepted E9
managed-overflow path does not call them.

A failed transition fails the direct diagnostic. No E9 handler path discovers
or changes this page.

### 8.6 Detach policy

ART-created Java and pool threads terminate immediately after ART unregisters
them, so Windows releases their complete stack allocation.

An externally created native thread may detach and continue. E9 has not changed
its stack mappings, so product detach has no ART-owned page to restore. The
diagnostic fixed-page test still restores its own test mutation exactly:

- if the page was originally reserved, decommit it back to `MEM_RESERVE`;
- if it was originally committed, restore its recorded base protection;
- never adopt or later reconstruct a pre-existing `PAGE_GUARD`; page selection
  excludes it from the beginning;
- never leave ART `PAGE_NOACCESS` state on a continuing detached native
  thread.

Restoration is a direct transition from either `Protected` or
`WritableForStackOverflow` to the recorded original state. It does not require
an unnecessary intermediate unprotect: `VirtualFree(MEM_DECOMMIT)` can restore
a reserved original directly, and `VirtualProtect()` can restore a committed
original directly. The result is then verified with `VirtualQuery()` before
the record is cleared.

The local Wine W-002 gate now performs that lifecycle twice on each of sixteen
raw `CreateThread` threads in every mode: attach, managed JIT callback, detach,
about 16 KiB of recursive native stack use, reattach, a second callback, and a
second detach. E9 no longer couples that product lifecycle to fixed-page
restoration; native repetition remains useful thread-lifetime coverage.

### 8.7 Thread creation and pthread attributes

The Windows pthread shim must honor:

- `stacksize == 0`: executable default reservation;
- `stacksize != 0`: `_beginthreadex(..., stacksize, ...,
  STACK_SIZE_PARAM_IS_A_RESERVATION, ...)`, with the resulting reservation
  rounded from the explicit request rather than clamped to the executable
  default;
- `PTHREAD_CREATE_JOINABLE`: retain the real thread handle until join or
  detach;
- `PTHREAD_CREATE_DETACHED`: arrange automatic control-object cleanup and
  close the handle without affecting the running thread;
- invalid sizes, overflow beyond `_beginthreadex`'s unsigned argument, and
  non-null custom stack addresses: return a real error.

Use `_beginthreadex` because the callback executes ART C/C++ and UCRT code.
The callback stores the `void*` return value in the pthread control object
before `_endthreadex`/return so `pthread_join(..., &result)` remains meaningful.

Stage A replaces the former `DWORD pthread_t` with an opaque control pointer.
Facade-created threads use a control object containing:

- immutable Windows thread ID;
- retained real handle for joinable threads;
- joinable/detached/joined state;
- callback result;
- lifetime synchronization for publication and for target exit racing with one
  valid join or detach operation.

The implemented ownership model establishes creator, public-completion, and
child references before `_beginthreadex` can run. The new thread is created
suspended so its immutable ID, handle, detach state, and callback fields are
complete before the callback executes. The trampoline records its control
object in a module-local TLS slot, calls the POSIX callback, stores the result,
clears that slot, and releases the child reference. Join or detach atomically
claims the one public completion right:

- join waits on the retained handle, reads the published callback result,
  closes the handle exactly once, and releases the public reference;
- detach closes the handle exactly once and releases the public reference;
  the child reference keeps the object alive until exit;
- a create failure releases all unpublished ownership without exposing a
  `pthread_t`;
- a second join/detach operation attempted while the control remains live
  fails deterministically rather than reopening a handle by a reusable thread
  ID. As with POSIX, simultaneous competing join/detach calls or use after the
  thread ID lifetime ends are not a supported contract.

Waiting on the thread handle supplies the result-publication ordering for
join. Detached callers have no right to inspect the result. The trampoline
may return normally from the `_beginthreadex` callback; explicit
`_endthreadex` is unnecessary unless an early non-returning path requires it.

`pthread_self()` for a thread not created by the facade returns an
allocation-free tagged token containing its live Windows thread ID. The token
has no join ownership and becomes invalid when that thread exits, matching the
normal lifetime rule for detached POSIX thread IDs. This avoids process-exit
callbacks pointing into one of the many DLL-local copies of the static compat
archive. An earlier FLS-control-object draft was rejected after Wine proved
that loader teardown could call its destructor after `art.dll` had become
non-executable, recursively faulting until native stack exhaustion.

`pthread_equal()` compares immutable Windows thread IDs, so a facade-created
control object and an external tagged token for the same live thread compare
equal even when they came from different DLL-local copies of the compat
archive. `pthread_gettid_np()` is the only numeric extraction boundary.
Thread naming uses a bounded `OpenThread` by that known-live ID; it does not
turn the ID into join ownership.

The Stage A source audit found no product numeric `pthread_t` formatting or
hashing dependency. Existing zero initialization remains portable in the
shared ART sources. The one build failure exposed an unrelated
libunwindstack typo that constructed `optional<pthread_t>` for a
`optional<pthread_key_t>` field; it is corrected to use `pthread_key_t`.
The Windows-specific `sun.nio.ch.NativeThread` continues to use its separate
Windows thread-ID token rather than exposing a pthread control pointer.

This handle work belongs in the same Stage A as stack sizing: otherwise stack
tests can pass while join remains vulnerable to termination/reuse races.

### 8.8 ART-created stack sizes

`Thread::FixStackSize()` remains the source of Java thread reservation
requests. Windows must pass that resulting value to `_beginthreadex`; it must
not reinterpret the Java constructor's requested size as the final OS
reservation. Tests record:

- the Java requested value;
- ART's post-`FixStackSize()` value;
- the exact interval returned by `GetCurrentThreadStackLimits()`;
- Windows allocation-granularity rounding.

This distinction is important because ART adds historical native headroom and
overflow overhead before `pthread_create()`. E9 does not add or install an
ART-owned page. The verified Windows native recovery interval is debited from
the actual reservation when bounds are published, and insufficient usable
space rejects attachment.

For thread pools:

```cpp
kUseCustomThreadPoolStack = !defined(__BIONIC__) && !defined(_WIN32)
```

conceptually. Windows passes `worker_stack_size` through
`pthread_attr_setstacksize()` and does not allocate a `MemMap` stack or call
`pthread_attr_setstack()`.

### 8.9 Moving Windows guard and guarantee interaction

The moving `PAGE_GUARD` remains under OS control. E9 never protects, consumes,
or tries to move it. Instead the accounting reserves one page above the
configured stack guarantee. Controlled native measurements establish that the
terminal inaccessible prefix, configured guarantee, and moving guard are
additive. `win32_stack_growth_probe` retains baseline/protected/writable/direct
modes and accepts an optional guarantee request so future Windows releases can
repeat that observation without changing product state.

## 9. Accepted Windows x64 stack-overflow event sequence

```text
generated method/nterp entry, before prologue
  compare RSP with Thread::stack_end_
        |
        +-- RSP >= stack_end_: continue normal entry
        |
        v RSP < stack_end_
tail-jump through Thread::pThrowStackOverflow
        |
        v
artThrowStackOverflowFromCode(Thread*)
  SetStackEndForStackOverflow()
  construct and install StackOverflowError
  ResetDefaultStackEnd()
        |
        v
ART long-jumps/delivers to the managed catch site
```

No deliberate Windows access violation, VEH stack classifier, fixed-page
unprotect/reprotect, native `EXCEPTION_STACK_OVERFLOW`, or SEH unwind is used
for the managed transition. The check runs before frame establishment and
uses the same ART throw entrypoint and recovery reserve as Linux. Linux keeps
its implicit fixed-page event sequence. Both remain supported only with CET
user shadow stacks disabled because ART's final long jump does not maintain a
hardware shadow-stack pointer.

## 10. Activation and failure policy

The current independent booleans are not sufficient for Windows product
activation. Define a conceptual capability:

```text
win_managed_faults_ready =
    no defined incompatible CET user-shadow-stack policy field enabled
    && VEH registered
    && special SIGSEGV action published
    && x86_64 WindowsFaultContext adapter built
    && implicit null handler registered
    && explicit Windows x64 stack checks built
    && every attached thread has verified guarantee-aware bounds
```

Then:

- startup must query the process CET/HSP policy before creating ART threads or
  enabling JIT and reject every defined incompatible policy field;
- `implicit_null_checks_` may be true only when the capability is ready;
- `implicit_so_checks_` is false on Windows x64 so common code does not install or
  classify a protected page; explicit stack checks are built unconditionally
  for Windows x64 optimizing/nterp code and require verified guarantee-aware bounds;
- Windows x64 nterp and JIT may be product-enabled only under those flags because
  their normal code contains implicit accesses;
- startup registration failure is fatal for the normal nterp/JIT product, not
  a silent continuation with inconsistent code;
- `-Xno-sig-chain` is accepted only for a runtime that does not enter normal
  `Runtime::Start()` (for example dex2oat); a started runtime rejects it
  regardless of interpreter/JIT mode;
- after product activation there is no process-wide fallback that disables
  implicit checks while already generated code exists.

The switch interpreter remains useful as an explicit-check diagnostic mode,
not as a hidden recovery path for a partially initialized VEH product.

## 11. Stack budget and handler discipline

Windows has no POSIX `sigaltstack` contract for VEH. Implicit null handling
still consumes the faulting thread's stack. Explicit stack overflow bypasses
VEH but must prove that the configured native guarantee plus ART's separate
8 KiB reserve is sufficient for the throw path.

The recognized overflow path must:

- avoid heap allocation;
- avoid logging and symbolization;
- avoid `VirtualQuery()`, page-protection changes, and minidump APIs;
- avoid ART mutex acquisition;
- avoid large locals and compiler-generated stack probes;
- avoid recursion except the explicit nested-fault fatal escape;
- enter the common throw entrypoint without establishing the rejected frame.

A native probe records, in preallocated storage:

- RSP at the explicit check;
- lowest SP reached before the stack end is temporarily expanded;
- configured guarantee, excluded-low components, and ART reserve boundaries.

Keep the shared 8 KiB value if native debug and release builds retain a clear
margin. Increase only the Windows x86_64 reserve if measurement proves it is
necessary; do not increase it speculatively.

## 12. Implementation stages

### Stage 0 — CET shadow-stack exclusion — implemented locally

- Add explicit `/CETCOMPAT:NO` to every project Windows x64 executable and DLL link
  target instead of relying on lld's current default.
- Inspect every packaged PE, including LLVM libc++, and reject packaging if
  `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT` is present.
- Query `ProcessUserShadowStackPolicy` at the earliest runtime initialization
  point, before managed thread creation, nterp publication, or JIT startup.
- Inspect the policy through fields named by the selected Windows SDK. Reject
  the defined shadow-stack, audit, context-IP-validation, strict, and
  non-CET-binary fields. Permit `CetDynamicApisOutOfProcOnly`; ignore
  `ReservedFlags`; accept the expected unavailable-policy result on older
  supported Windows 10 builds; fail closed on unexpected query failures.
- Emit a bounded diagnostic explaining that Hardware-enforced Stack Protection
  must be disabled by the launcher or Windows Exploit Protection policy before
  process creation.
- Do not use `/guard:ehcont`, dynamic EH-continuation registration, or dynamic
  CET-compatible-range registration as a substitute.

Clean completion criteria:

- generated and handwritten Windows x64 link commands contain `/CETCOMPAT:NO`;
- packaged PE inspection finds no CET-compatible extended characteristic;
- an HSP-disabled native process passes the startup guard;
- compatibility, audit, and strict HSP policies are rejected before managed
  execution, without relying on a late control-protection exception or dump.

Implementation and local evidence (2026-07-27):

- `GlobalPolicy.add_ldflags` injects `LINKER:/CETCOMPAT:NO` into every
  generated non-static target; static archives intentionally receive no link
  options.
- Nine handwritten Windows x64 CMake harnesses and three direct Clang/lld links use
  the same explicit option.
- The base Phase-3 host packager and the focused W-002/W-003/W-004/W-013
  packagers invoke the PE audit before writing their final manifests/archives.
  A synthetic `/CETCOMPAT` PE is rejected by the same package scan.
- `cet_compat.cc` separates Win32 API observation from a deterministic policy
  decision. It obtains the real build number through `RtlGetVersion`, copies
  only the named incompatible SDK fields into an incompatibility mask, accepts
  `CetDynamicApisOutOfProcOnly` and reserved bits, accepts
  `ERROR_INVALID_PARAMETER` only below build 19041, and fails closed for
  unknown versions or unexpected query failures.
- `Runtime::Init()` runs the guard after logger selection and before
  `MemMap::Init()` and thread/JIT initialization. Rejection returns normal
  startup failure rather than deliberately triggering a control-protection
  exception.
- The focused policy probe rejects every named incompatible field separately,
  accepts `CetDynamicApisOutOfProcOnly`, accepts low/high/all reserved bits,
  rejects an incompatible field mixed with safe/reserved bits, and covers
  old-build unavailability plus failure cases. Under Wine it reports build
  19043, `known_incompatible=0x00000000`, and `PASS`.
- The structural/package verifier reports 9 CMake harnesses, 3 direct links,
  6 enforced host packagers, and 27 Ninja PE link targets. It inspects 27 PE
  files in the build tree and 58 when the focused W-010/W-014 staged package
  is included, with no CET-compatible marker, including external LLVM
  `c++.dll`. The selected Windows x64 build completed 321 steps
  and `dalvikvm
  -showversion` reports `ART version 2.1.0 x86_64` under Wine.
- The complete Phase-4 Wine suite passes after the change, including W-002,
  W-003 frame/XMM matrices, GC/thread/handle stress, intentional crash gates,
  and GoldenApp. The Linux rebuild, no-op rebuild, and `dalvikvm -showversion`
  also pass.

Remaining Stage 0 acceptance:

- force compatibility, audit, strict, context-IP-validation, and other named
  incompatible policy fields in child processes and verify early rejection;
- prove rejected starts create no `.dmp` and execute no Java/JIT work.

The first native candidate on Windows build 19044 returned raw
`flags=0x00000100`. The old raw-word check rejected startup, but bit 8 is the
documented `CetDynamicApisOutOfProcOnly` field, not HSP enablement. That run is
evidence for the classifier defect, not a failed HSP configuration. The
corrected implementation reports both raw flags and `known_incompatible`.
The second native run accepts the same `0x00000100` word with
`known_incompatible=0x00000000`, closing the ordinary HSP-disabled startup
case. Reserved fields are not acceptance cases to force or interpret because
Windows defines no semantics for them.

Those native checks are the acceptance blocker. They do not block starting
Stage A because the build and early-runtime enforcement are now present.

### Stage A — bounds, creator, and pthread lifetime

- **Implemented locally:** reject `IsThreadAFiber()` and out-of-system-stack
  attachment; exact `GetCurrentThreadStackLimits()` bounds plus a complete
  allocation walk; `_beginthreadex` reservation semantics; join/detach handle
  ownership and callback result publication; custom-stack rejection; and
  reservation-based Windows thread pools.
- **Implemented probe:** `win32_thread_stack_probe` covers exact main/default,
  1 MiB, and 2 MiB intervals; self and cross-thread identity; join results;
  detach before and after exit; 512 create/join iterations; 128 detached
  iterations; raw `CreateThread`; invalid/custom attributes; and fiber
  rejection.
- **Implementation finding:** DLL-local FLS destructor callbacks are unsafe
  with a statically linked compat archive. External live threads therefore use
  allocation-free tagged ID tokens; created threads retain opaque controls,
  and equality compares immutable thread IDs across module boundaries.
- **Adjacent lifecycle repair:** runtime teardown removes the diagnostic VEH
  before `art.dll` unload and restores, rather than clobbers, a later host UEF.
- Stage D enabled the managed-fault product path after Stage A/C prerequisites;
  E7 subsequently disables Windows x64 implicit SO and selects explicit checks.

Local and returned-native evidence (2026-07-27):

- Windows x64 `art`, `dalvikvm`, and the focused probe build with `-j32`.
- Wine reports a 1 MiB default and clamps explicit 64 KiB/256 KiB reservations
  to that default, while native Windows build 19044 returns exact 64 KiB and
  256 KiB reservations. The probe now detects Wine explicitly, records that
  compatibility fallback, and requires native request-based allocation-
  granularity rounding with `wine_default_clamps=0`.
- The first native candidate passes join/detach handle closure and otherwise
  exposes no pthread lifetime failure. Its small-reservation failures were
  probe-expectation defects, not pthread implementation failures.
- Wine `Hello`, ThreadHeavy, every W-002 attach mode, and the complete Phase-4
  suite pass with clean process exit after the VEH/FLS findings.
- Linux rebuild and `dalvikvm -showversion` pass.

The second native package closes the direct requested-reservation matrix,
including exact 64 KiB and 256 KiB stacks, and again closes the exercised
join/detach handle-count point. Remaining Stage A work is representative ART
pool observation, Java post-`FixStackSize()` correlation, fiber rejection on
the real host, and detach/reattach timing under deep native guard movement.

### Stage B — fixed-page experiment — retained as diagnostic infrastructure

- `stack_windows.{h,cc}` separates allocation-free selection policy from
  Win32 memory operations. It preserves the lowest page and complete adjacent
  bottom no-access/guard regions, accepts only a reserved page or exact
  committed-private `PAGE_READWRITE` page, rejects malformed geometry and
  insufficient remaining stack, and supports the normal one-system-page ART
  protected size.
- The original candidate recorded selection/state below native-code-visible
  TLS and installed the page during attachment. E7 removes that product
  installation; only direct probes use the state record now.
- Protect, unprotect, install rollback, and detach restoration verify the
  resulting `VirtualQuery()` state. Reserved originals return to
  `MEM_RESERVE`; committed originals return to their exact type/protection.
- Windows bypasses Linux's `VM_GROWSDOWN` recursion and stack `madvise()`.
- The focused probe covers eight synthetic layout decisions, 64 cycles on the
  actual committed Wine main-stack page, 64 cycles on a real reserved
  allocation, a 2 MiB pthread stack, and 258 exact assembly-load access
  violations redirected by a tiny probe-only VEH.
- The W-002 attached-thread gate now proves detach, continued native stack
  use, reattach, and second detach on the same raw thread in all eight Wine
  mode/repeat processes. Windows x64 Hello, the complete Phase-4 Wine suite, the
  Linux full rebuild, `dalvikvm -showversion`, and shared-boot imageless Hello
  remain green with the Windows-only state below native-visible TLS offsets.

Selection, direct protection, and restoration criteria are met. Native build
19044 proves recursive guard growth defeats the fixed-page SOE contract.
Stage B is complete only as page-state diagnostic infrastructure.

The later pregrow extension does not reopen Stage B as a product stage. On
build 26100 it first commits almost the complete 2 MiB reservation and moves
the Windows guard to the E9 low neighborhood; only then can a fixed
`PAGE_NOACCESS` page preserve the Linux-shaped implicit read. Its 30/30 fault
result is retained as mechanism evidence, while 5/5 irreversible detach state,
linear commit cost, and fatal native collision reject it as the attachment
contract.

### Stage C — initially dormant W-010 adapter — implemented locally (2026-07-27)

- `sigchain_windows.cc` now owns the special-action facade and managed VEH
  registration, promotion, publication, and removal lifecycle. Unsupported
  signals fail clearly instead of disappearing in a stub.
- `fault_handler_windows.h` defines the non-owning real-`CONTEXT` view and the
  documented read/write access constants without leaking Windows SDK types to
  common headers.
- The x86_64 handler reads and writes `CONTEXT.Rip`/`Rsp`/`Rax` in place,
  preserves the Windows x64 `R15 == Thread*` managed-self invariant, rejects nested
  dispatch per thread, and requires stack faults to be reads whose exact
  address is inside the recorded protected page.
- The VEH performs allocation-free exact filtering for continuable access
  violations, builds only the small synchronous `siginfo_t` view, and returns
  search for execute faults, native/unregistered AVs, guard/stack-overflow
  exceptions, and all unrelated exceptions.
- `win32_fault_record_probe` covers eight deterministic positive/negative
  record cases. `win32_sigchain_probe` faults a real `PAGE_NOACCESS` page twice,
  verifies live context redirection and `Rax` forwarding, calls promotion
  between faults, and then removes the action. Both pass under Wine.
- At this checkpoint the runtime capability remained dormant; Stage D below
  subsequently activated the same adapter without changing generated code.
- Fatal diagnostics remain separate. The diagnostic VEH continues search, and
  the UEF writes a best-effort dump then invokes the predecessor or returns
  search.
- The complete Phase-4 Wine aggregate passes with the new W-010 gate, and the
  shared Linux `art`/`dalvikvm` rebuild plus `dalvikvm -showversion` pass.

### Stage D — managed-fault activation — implemented (2026-07-27)

- Windows x64 enables common implicit null handling while leaving implicit
  suspend checks off. E7 sets common implicit SO false and selects explicit
  generated checks for Windows x64 only.
- `FaultManager` retains common handler ordering; E9 stack overflow no longer
  depends on the stack fault classifier.
- Nterp's immutable code range is registered before startup publishes nterp
  entrypoints even though Windows x64 deliberately keeps `CanRuntimeUseNterp()`
  false during early initialization. JIT code-cache ranges retain the common
  registration path.
- E9 requires the main and every later attached thread to have a verified
  minimum four-page stack guarantee and guarantee-aware bounds before managed
  execution. Product attachment installs no fixed page.
- The Windows exception to the normal started-runtime sigchain invariant is
  removed. Active runners no longer pass `-Xno-sig-chain`; one focused
  negative case proves started-runtime rejection.
- `W010ManagedFaultProbe` passes nterp and threshold-zero JIT modes for 64
  caught read NPEs, 64 caught write NPEs, two caught main-thread SOEs, and two
  caught child-thread SOEs. The JIT runs prove compilation of the faulting
  caller/recursive methods. Handled faults emit no diagnostic VEH/UEF marker
  and do not change `run/crash/*.dmp`.
- Unmanaged native AV still reaches fatal diagnostics. The full Phase-4 Wine
  aggregate, Windows x64 build, Linux full `art`/`dalvikvm` rebuild,
  `dalvikvm -showversion`, and shared-boot imageless Hello all pass.

### Stage E — fatal unwind, native acceptance, and cleanup

- **Implemented locally:** PE unwind records for the two native invoke stubs
  and generic JNI trampoline; split R12-anchored-entry/RSP-return records for
  the OSR stub; a structural emitted-record audit; a live OSR
  lookup/virtual-unwind probe; and hardened fatal gates that require VEH, UEF,
  a minidump marker, and a newly created valid `MDMP` file. The OSR probe covers
  a variable copied-stack RSP, a clobbered RBP while the entry record uses R12,
  managed-RBP-independent return unwinding, GPR/XMM restore, and the canonical
  return epilogue. The actual dual/J-1 default/switch OSR matrix passes 8/8.
- **Dynamic compiler/runtime implementation:** the x86_64 assembler serializes
  version-1 PE unwind bytes independently of DWARF CFI, optimizing Windows x64 JIT
  methods reserve and force-spill `RBP` then establish it after the fixed
  allocation, normal/FastNative JNI stubs use the same anchor without assigning
  RBP/R15 as scratch, and CriticalNative retains a fixed-RSP descriptor. The
  serializer rejects invalid prologues and JIT compilation rejects missing or
  invalid enabled metadata before allocation. The runtime stores aligned xdata
  in the existing data allocation, registers one stable table before
  publication, unregisters before reuse, and clears before teardown. Focused
  J-2/J-1 registry, collection/reuse, and threshold-zero fatal UEF/minidump
  gates pass.
- **Historical native package:** the retired W-010/W-014 producer staged the
  coupled automated matrix and passed its Linux-side Wine preflight. Its
  PowerShell runner required 30 PASS records, covered static, J-2/J-1 JIT-origin, and
  J-2/J-1 OSR-origin fatal AVs, validates a new `MDMP` for every fatal process,
  immediately preserves each dump under a case-prefixed filename to avoid
  one-second timestamp collisions, and requires at least five returned dumps.
  The returned E9 package is accepted historical evidence. Current reproduction
  uses the shell-free unified W-010 and W-014 stages.
- **Second native result:** the corrected build-19044 run passes 20 checks and
  fails 12. CET, reservations, direct page operations, sigchain, NPE, OSR
  unwind, and XMM sentinels pass. All three SOE modes terminate with native
  stack overflow, and all five fatal AV origins miss UEF/dump after VEH.
- **Diagnostic stage:** the package adds isolated stack-growth and UEF probes
  plus a late ART UEF ownership mode under a separate PowerShell runner. The
  acceptance record count is unchanged.
- **Third native diagnostic result:** recursive protected growth changes the
  selected page from `PAGE_NOACCESS` to ordinary committed `PAGE_READWRITE`
  before `STATUS_STACK_OVERFLOW`; direct access still AVs, and pre-reset
  re-protection succeeds. Standalone main/worker/chained UEF dispatch passes,
  and the late probe proves ART still owns the UEF slot immediately before the
  crash, but neither late nor ART UEF runs after the VEH marker. Fixed-page SOE
  delivery is invalidated, UEF replacement is ruled out, and the fatal path is
  narrowed to native exception traversal across GenericJNI/managed frames.
- **GenericJNI follow-up implemented:** the live probe now virtually unwinds a
  realistic completed GenericJNI frame from the captured native-call return at
  `+0xc5`. It found and repaired RDI's PE save offset (`0` -> `0x1400` from the
  R12 frame base). Structural and live Wine checks pass. The diagnostic runner
  now compares continuable JNI `RaiseException`, JNI hardware AV, and a
  JNI-created native-worker hardware AV; all three reach UEF/dump under Wine.
- **Fourth native diagnostic result:** JNI hardware and raised AVs both stop
  after ART's VEH without entering either UEF, while the JNI-created native
  worker reaches both UEFs and creates a valid dump. Hardware/software shape,
  ART process state, UEF ownership, runner/debugger behavior, and dump creation
  are ruled out. The repaired GenericJNI record is insufficient; bounded live
  recursive unwind tracing above it is the next diagnostic.
- **E4 live trace implemented:** a bounded opt-in walk from the copied VEH
  context reports module/runtime-function RVAs and terminal progress. Wine's
  first live lookup miss is `ExecuteSwitchImplAsm + 0x9`, where the wrapper's
  saved RBX is misread by leaf fallback. The product repair was held until
  native confirmation before adding Windows x64 unwind metadata and the missing MSVC
  outgoing home area.
- **Native E4 confirmation:** Windows build 26100 reproduces the local
  `ExecuteSwitchImplAsm + 0x9` lookup miss in both JNI exception shapes. The
  native-worker chain is fully registered and reaches UEF/dump. The wrapper
  frame repair is now evidence-backed rather than speculative.
- **E5 wrapper repair and native result:** the Windows-only RBX save, 32-byte
  MSVC outgoing home area, canonical epilogue, and PE unwind record pass
  structural, Wine, Linux-parity, and native lookup/unwind checks. Native E5
  crosses `ExecuteSwitchImplAsm + 0xd`, then identifies the next first miss at
  `art_quick_to_interpreter_bridge + 0x82`. Its two distinct stack shapes are
  the next range-accurate unwind repair.
- **Local E6 bridge repair:** two contiguous runtime-function records now
  describe the unchanged 200-byte primary layout and the 88-byte pending tail.
  Fixed-offset restores and canonical normal/tail epilogues make entry,
  `+0x82`, restore-body, epilogue, and pending-body virtual unwind pass. The
  complete Wine aggregate and unchanged Linux/SysV bridge pass. Native E6
  subsequently accepted the primary record as described below.
- **Native E6 result:** both JNI traces resolve the primary bridge at `+0x82`,
  cross all later frames with `lookup=1`, terminate at zero PC, enter both
  UEFs, and write valid dumps. The primary bridge/fatal-dispatch diagnosis is
  closed. The pending record was not entered by these cases.
- **Complete native E6 host result:** all five static/JIT/OSR fatal origins
  reach VEH/UEF and create valid dumps on build 26100. The runner records
  25/30 PASS rows; only switch/nterp/JIT managed SOE and the two resulting
  handled-fault/dump aggregates fail.
- **E7 explicit-check implementation:** optimizing Windows x64 and nterp perform a
  pre-prologue `RSP < Thread::stack_end_` check and tail-jump through the common
  throw entrypoint. Equality is valid. Linux retains its implicit probe and is
  checked at object level.
- **E8 rejection:** treating the inaccessible prefix and configured guarantee
  as overlapping still fails all three native SOE modes.
- **E9 guarantee-aware acceptance:** each thread preserves or raises the
  guarantee to at least four pages, queries it back, and debits prefix plus
  rounded guarantee plus one moving guard. Windows Server 2025 build 26100
  returns 30/30 PASS, zero handled dumps, and five fatal dumps; the independent
  reviewer accepts the full returned package.
- **FS-1 stack budget accepted:** allocation-free samples cover the explicit
  check, quick entry/frame, common throw and exception-construction phases,
  restored boundary, delivery, and long jump. Release and Debug switch/nterp/
  JIT pass on native build 26100 with positive native margin and no dump.
- **FS-2 native accepted:** the Win32 debug-loop probe, one-way forced CET
  policy families, JNI embedding/UEF teardown coverage, and full-width
  XMM6-XMM15 exception-unwind sentinels pass on Windows Server 2025 build
  26100. The first-chance JIT NPE continues into Java with zero second-chance
  faults; explicit SOE remains fault-free. All nine named incompatible policy
  cases reject before Java/JIT, while dynamic/reserved fields remain accepted.
  The embedding probe verifies predecessor UEF, foreign VEH/frame-SEH, and
  later-UEF preservation through VM teardown. Native evidence is under
  `docs/evidence/windows_x64_fs2_w010_w014_result.md`.
- **Still open:** rollback injection, reservation correlation,
  negative-exception, and debugger-quality dump-stack gates. FS-5 conditionally
  closes the pending-range question because a real native fault would require
  product-tail injection or fabricated direct entry.
  Native normal-return XMM, OSR live unwind, foreign VEH/frame-SEH, managed SOE,
  stack budget, dynamic-table churn, five fatal origins, and FS-2 pass.
- Run the complete matrix below on Windows 10 build 17134+ and a current
  Windows release.
- Keep Wine as a development oracle and Linux as the behavior oracle.
- Retain obsolete fixed-page branches only where direct diagnostics exercise
  them; do not reconnect them to product attachment or managed SOE.

## 13. Required verification matrix

### 13.1 CET/HSP process policy

- Structural link-command check proves every Windows x64 PE link explicitly includes
  `/CETCOMPAT:NO`.
- `llvm-readobj --coff-debug-directory` or an equivalent PE parser proves
  `dalvikvm.exe`, `art.dll`, `sigchain.dll`, LLVM libc++, quick/JIT support
  DLLs, probe executables, and packaged copies omit
  `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT`.
- Native Windows with Hardware-enforced Stack Protection disabled starts and
  reaches the ordinary product gates even if the raw policy word contains only
  `CetDynamicApisOutOfProcOnly` or reserved bits; the log must report
  `known_incompatible=0x00000000`.
- Forced compatibility, audit, and strict policies each fail during early
  startup with the documented diagnostic, before a Java method or JIT worker
  runs.
- Forced context-IP-validation and other named incompatible fields likewise
  fail. Unit/probe coverage must accept `CetDynamicApisOutOfProcOnly` and
  reserved fields, and reject mixtures containing any incompatible field.
- The test-only forced-policy child matrix covers all nine named incompatible
  fields, safe dynamic/reserved combinations, early no-Java/no-JIT rejection,
  and no new dump per child.
- Rejection does not produce a `.dmp` and does not depend on
  `STATUS_CONTROL_PROTECTION_VIOLATION` as the detection mechanism.
- The native W-025 JIT-2 CFG-on matrix passes generated-code execution and
  actual ART JIT compilation. It remains separate from and must not change
  this expected CET rejection behavior.

### 13.2 Stack bounds and creation

- Main executable thread/default linker stack.
- Java-created threads with 0 and representative requested sizes, recording
  the post-`FixStackSize()` reservation.
- ART runtime, GC, JIT, and trace pools.
- Native `_beginthreadex` and raw `CreateThread` threads that attach to ART.
- Actual reservations of 64 KiB, 256 KiB, 1 MiB, 2 MiB, and over 8 MiB where
  the native OS supports the request.
- Joinable return value, detach-before-exit, detach-after-exit, rapid create /
  exit / ID reuse stress.
- Fiber/manual-stack attachment rejection with bounded diagnostics.
- External thread attach, managed call, detach, continued native stack use,
  reattach, and exit.

### 13.3 Implicit null

- Nterp implicit invoke-null path.
- JIT baseline and optimized implicit reads and writes.
- Repeated caught NPE with GC and JNI between iterations.
- Fault address inside and just outside the implicit-null range.
- Native AV at a low address is not translated.
- AV in an unregistered executable range is not translated.

### 13.4 Stack overflow

- Switch interpreter explicit overflow as a reference.
- Nterp and threshold-zero JIT overflow.
- Leaf/non-leaf recursion and large frame shapes.
- Repeated caught overflow, second overflow, mutual recursion, and
  `018-stack-overflow` output parity.
- GC, JNI, stack walking, and exception stack-trace creation after overflow.
- Windows x64 object-level `RSP < Thread::stack_end_` pre-prologue check with equality
  accepted, plus Linux object-level `RSP - 8192` implicit-probe preservation.
- Main and pthread guarantees queried, raised/preserved, queried back, and
  excluded-low accounting for prefix + guarantee + moving guard.
- Deliberate generated-code AV with the wrong address remains unhandled.
- Explicit-check, throw, temporary-bound expansion, and recovery stack
  high-water measurements. FS-1 accepts four complete main/child records per
  switch/nterp/JIT mode in both Release and Debug.
- The standalone pregrow probe may remain a mechanism regression, but its
  result is never counted as product managed-SOE acceptance and it installs no
  runtime feature gate.

### 13.5 Chain and fatal diagnostics

- Structural inspection resolves `art_quick_invoke_stub`,
  `art_quick_invoke_static_stub`, and `art_quick_generic_jni_trampoline` in
  the staged `art.dll` and verifies their frame anchors, allocations, saved
  nonvolatile GPRs, and saved XMM registers.
- Foreign VEH registered before ART, after ART, and promoted by
  `EnsureFrontOfChain()`.
- Foreign handlers returning search preserve ART behavior.
- An unrecognized AV reaches a frame-based SEH handler.
- Debugger first-chance stop followed by continue reaches the Java exception.
- Handled NPE/SOE produces no first-chance dump and no `.dmp`.
- A static/`-Xint` unhandled JNI native AV produces the expected initial VEH,
  UEF, predecessor-chain behavior, and a newly created valid `MDMP` minidump.
- A threshold-zero JIT-origin unhandled JNI native AV crosses registered JIT
  runtime-function data, reaches the UEF, and produces the same valid dump.
  This passes locally in J-2 and J-1. A foreign frame-based SEH wrapper and
  debugger-quality reconstruction of that dump remain native acceptance items.
- `EXCEPTION_GUARD_PAGE`, `EXCEPTION_STACK_OVERFLOW`, breakpoint, single-step,
  illegal-instruction, and execute AV are not consumed by ART's managed VEH.
- Runtime shutdown removes the VEH before `art.dll` can unload.

### 13.6 Cross-platform regression

- Linux `018-stack-overflow` and implicit-null tests.
- Linux generated-code range registration/removal tests.
- Shared boot.jar byte identity remains unchanged.
- Windows x64 nterp/JIT ABI, XMM nonvolatile, JIT dual-view, W-002, W-003, W-004,
  W-013, and W-024 acceptance subsets remain green.

### 13.7 Deterministic host-side tests

Keep Win32 API acquisition separate from policy so the dangerous decisions
are testable without deliberately crashing a product process:

- feed synthetic `EXCEPTION_RECORD`/context views into the fast filter and
  cover read, write, execute, non-continuable, short-information, wrong-PC,
  recursion, and unpublished-action cases;
- make bottom-page selection consume a captured list of
  `MEMORY_BASIC_INFORMATION`-like records and test reserved, fully committed,
  adjacent guard/no-access, incompatible type/protection, overflow, and
  too-small-stack layouts;
- model pthread control transitions and assert one handle close, one public
  completion claimant, result visibility after join, and safe child exit
  before/after creator publication;
- retain structural Linux checks proving no Windows SDK type or branch enters
  non-x86 common fault paths and Linux context access remains unchanged.

These tests complement rather than replace native Windows fault, guard-growth,
and debugger evidence.

## 14. Code placement and status

| File | Responsibility and current status |
|------|------------------------|
| `overlay/art_port_policy.py`, `tools/bp2cmake`, and Windows x64 CMake/test graphs | Implemented explicit `/CETCOMPAT:NO` on every generated and handwritten executable/DLL target; static archives excluded |
| `runtime/multiplatform/windows/cet_compat.{h,cc}` | Implemented process-policy observation and fail-closed decision logic, independently probeable |
| `runtime/multiplatform/windows/sigchain_windows.cc` | Implemented ART special-SIGSEGV facade, managed VEH handle, promotion/removal, immutable action publication, recursion gate, and exact exception filter |
| `runtime/multiplatform/windows/runtime_windows.cc` | Implemented earliest CET/HSP policy rejection, separate diagnostic VEH/UEF teardown, and predecessor-preserving fatal UEF chaining |
| `runtime/multiplatform/windows/fault_handler_windows.cc` | Not required; the Stage C dispatcher remains narrow enough to live in `sigchain_windows.cc` |
| `runtime/multiplatform/windows/fault_handler_windows.h` | Windows-only non-owning context view and documented AV-kind constants; no common-header Win32 leakage |
| `runtime/arch/x86/fault_handler_x86.cc` | Windows x64 non-owning context view and real `CONTEXT` PC/SP/RAX access for AV-based managed faults; fixed-page stack classification is not the E9 product path |
| `runtime/arch/x86_64/quick_entrypoints_x86_64.S` | Implemented PE unwind records for the two native invoke stubs, generic JNI trampoline, and split OSR entry/return ranges; GenericJNI now records RDI at completed-frame offset `0x1400` from its R12 anchor and passes realistic native-return virtual unwind; OSR uses R12 for the static copy anchor and sets RBP to copied RSP before the JIT handoff; preserves full-width XMM6-XMM15 in Windows-only boundary adapters with completed-frame unwind offsets; native normal-return sentinel and OSR live unwind pass, while repaired fatal dispatch still needs exception-unwind repetition |
| `compiler/utils/x86_64/windows_x64_unwind_info.h`, `assembler_x86_64.*`, and `compiler/optimizing/code_generator_x86_64.{h,cc}` | Implemented SDK-independent version-1 PE serializer plus Windows-JIT-only forced `RBP` anchor; Linux and non-JIT code paths unchanged |
| `compiler/jni/quick/jni_compiler.*`, calling-convention files, and `compiler/utils/x86_64/jni_macro_assembler_x86_64.*` | Implemented RBP-anchored normal/FastNative JIT stubs, fixed-RSP CriticalNative descriptors, reserved-frame scratch selection, and opaque metadata carry independent of DWARF CFI |
| `runtime/multiplatform/windows/jit_unwind_windows.{h,cc}` and `runtime/jit/jit_code_cache.*` | Implemented stable one-entry dynamic-function registry, publish-after-register rule, exact deletion, unregister-before-free/reuse, and clear-before-teardown ownership |
| `runtime/jit/jit_memory_region.*` | Implemented overflow-checked aligned xdata tail in each existing data allocation, written through the RW alias and referenced through the primary low-4-GiB view |
| `tests/cases/jit-lifecycle-stress/probe.cc` and its adjacent `RESULT.md` | Native-accepted JIT-3/FS-3 optimizing/JNI compile-invalidate-collect-reuse stress with concurrent lookup/virtual unwind and independent returned-archive review |
| `docs/evidence/windows_x64_w025_jit4_result.md` | Native-accepted JIT-4 default-J-2 final regression, including eight lifecycle cycles and three valid static/JIT/OSR fatal dumps with independent returned-archive review |
| `docs/evidence/windows_x64_w025_jit5_result.md` | Native-accepted JIT-5 removal proof: Windows J-1 absent, retired key inert, fail-closed source/binary contract, eight lifecycle cycles, and three valid fatal dumps with independent review |
| `runtime/thread.cc` | Implemented exact current-stack acceptance and attach failure; Windows x64 performs no fixed-page installation and adjusts common bounds by the platform-reported excluded-low sum |
| `runtime/multiplatform/windows/stack_windows.{h,cc}` | Read-only E9 layout inspection accounts for inaccessible prefix + configured guarantee + moving guard; Stage-B select/protect/restore helpers remain diagnostic-only |
| `runtime/multiplatform/windows/thread_windows.cc` | Queries, raises/preserves, re-queries, and validates the four-page minimum guarantee, then supplies guarantee-aware layout accounting; no alternate signal stack |
| `compiler/optimizing/code_generator_x86_64.cc` and nterp x86_64 assembly | E7 Windows x64-only explicit pre-prologue stack-end checks; Linux implicit probes remain unchanged and both objects are structurally audited |
| `runtime/thread_pool.cc` | Implemented no-caller-allocated-stack Windows policy; requested reservation passes through pthread attributes |
| `compat/include/pthread.h` | Implemented opaque Windows `pthread_t`, numeric-ID helper, and strict attribute contract |
| `compat/src/windows_x64_posix_stubs.c` | Implemented `_beginthreadex`, handle/result lifetime, join/detach, tagged external identity, exact current-stack bounds, and stack attributes |
| `runtime/runtime.cc` | Implemented diagnostic handler shutdown, managed null/SO capability activation, Linux-like started-runtime sigchain invariant, early nterp range registration, and Windows x64 explicit-SO selection |
| `tests/support/windows/check_win32_cet_contract.py` and `tests/cases/cet-stack-policy/probe.cc` | Implemented link/PE audit plus deterministic and actual-policy probe |
| `tests/support/windows/check_win32_boundary_unwind.py`, `tests/cases/{osr-unwind,fatal-runtime}/`, and the retained OSR leaf diagnostic | Unified exact emitted boundary-record audit, live split-OSR lookup/virtual-unwind/epilogue gate, and static/JIT/OSR fatal gates requiring new valid minidumps |
| Canonical native sources under `tests/cases/{thread-stack,stack-page-growth,unhandled-exception-filter,fault-record,sigchain-fault,jit-unwind-info,jit-unwind-registry}/` plus transitional Phase-4 runners | Implemented Stage A reservation/identity/lifetime gate, Stage B synthetic selection/restore/direct-fault gate, native recursive-growth and standalone-UEF diagnostics, Stage C deterministic record/live VEH gate, Stage D nterp/JIT managed-fault stress, and Stage E static OSR, serialization, runtime registry, collection/reuse lifecycle, and threshold-zero fatal-dispatch coverage |
| `tests/cases/stack-pregrow/probe.c` and `implicit_fault_x86_64.S` | Diagnostic-only E9-bound pre-growth, exact Linux-shaped implicit read, attach/restore irreversibility, fatal native collision, and held-alive commit-scale evidence; not linked into ART |

The exact split between `sigchain_windows.cc` and
`fault_handler_windows.cc` is an implementation detail. There must still be
one VEH owner and one managed dispatch path.

## 15. Open proof points

These are validation questions, not permission to improvise new product
fallbacks:

1. **Resolved by FS-4 policy decision:** Windows Server 2025 build 26100 is
   the authoritative native acceptance host. Its E9/FS-1/FS-2/FS-3 and stack/
   lifecycle repeat passed; the separate Windows 10 repetition is explicitly
   skipped. This does not reopen fixed-page delivery.
2. How much stack do the explicit quick throw, stack-end expansion, exception
   construction, and long-jump path consume in release and debug builds, and
   what margin remains above the configured native guarantee?
3. Do future supported Windows builds preserve the measured additive layout
   of inaccessible prefix + configured guarantee + one moving guard page?
   Repeat the parameterized growth probe when adding a host baseline.
4. Native Windows should repeat external detach, continued native stack use,
   reattach, and second detach under deep guard movement. E9 changes no page
   protection during this lifecycle.
5. Does a security product or debugger used in acceptance install a first VEH
   that consumes expected AVs? If so, this is an embedding compatibility issue,
   not a reason to weaken ART's classifier.
6. **Resolved for the FS-3 acceptance boundary:** the section 7.9 one-entry
   dynamic-table design remains correct under native Windows compilation/
   collection churn and concurrent sampling. Four J-2/J-1 cases cover 24
   simultaneously published methods, 52 collections, 1,344 registrations,
   1,248 exact address reuses, 696,929 stable-live lookups, 5,909,811
   stable-dead lookups, and 696,969 successful virtual unwinds with no missing,
   stale, or failed record. Per-run maximum lookup time is 122,800-706,100 ns,
   so the callback alternative remains unjustified. Neither static nor dynamic
   unwind data implies CET user-shadow-stack compatibility. JIT-5's sole J-2
   path repeats eight cycles and 120,654 unwinds after J-1 removal with the
   same zero missing/stale/failed result.
7. Normal-return XMM6-XMM15 passes natively. Does the adapter also preserve
   full width during exception unwind through several optimizing/JNI frames?
8. **Resolved by FS-5 (conditional coverage):** native E6 resolves
   `art_quick_to_interpreter_bridge + 0x82`, and the full host matrix accepts
   static, JIT J-2/J-1, and OSR J-2/J-1 fatal origins. The 88-byte pending
   range begins only after `artQuickToInterpreterBridge` returns with
   `Thread::exception` set; it is a managed state transition, not a native
   exception entry point. The existing structural probe verifies both PE
   records and synthetic `RtlVirtualUnwind` from the pending body and
   epilogue. A real native fault would require a product-tail fault injection
   or a fabricated direct jump, so FS-5 is closed as impractical conditional
   coverage. See
   `tests/cases/managed-fault-recovery/RESULT.md`.

### JIT-1 shared native cross-regression — 2026-07-29

The direct signed-int32 JIT-root and uint32 CodeInfo construction guards in ART
`146016f83e` do not change the managed-fault or unwind format. The rebuilt
runtime passed the local JIT smoke, matrix, unwind-info, unwind-registry, and
J-2/J-1 collection-lifecycle gates. Its focused W-004 package then passed all
22 child cases and 28 aggregate records on Windows Server 2025 build 26100,
including dual-view JIT, J-1 CriticalNative/native-ABI/JVMTI comparison arms,
GC/thread/handle stress, and ten clean default-JIT starts. Log and trace scans
pass and the recursive dump scan reports `NO_DMP_FILES`.

This is a cross-regression for the already accepted E9 fault/unwind design; it
does not replace the 30-record E9 fatal/managed-fault archive. The independently
reviewed identities and result are archived under
`docs/evidence/windows_x64_w025_jit1_result.md`.

### JIT-2 shared native cross-regression - 2026-07-29

The W-025 mapping/policy package records a clean native boundary before the
shared JIT-3/FS-3 churn gate. On Windows Server 2025 build 26100, standalone
generated code and an actual 64 MiB ART JIT mapping execute with CFG enabled;
the default and 1 GiB ART mappings compile the target method with registered
R/RX primary and RW alias roles. Complete low-VA rejection/recovery and 1 GiB
`SEC_COMMIT` pressure also pass without an access violation or dump.

With `ProhibitDynamicCode`, Windows rejects both the J-2 executable mapping and
J-1 executable-protection transition with error 1655. ART creates no JIT cache
and continues successfully; the separate `-Xusejit:false` control also passes.
This is fail-closed negative evidence only. ART-created executable memory is an
explicit product prerequisite for JIT and future restricted-ELF OAT; running
under `ProhibitDynamicCode`/ACG is a non-goal and is not a supported product
configuration.
The runner returns 14/14 aggregate checks, clean forbidden-log scanning,
`NO_DMP_FILES`, and an empty JIT temporary directory. This was the prerequisite
mapping/policy boundary; the separate FS-3 result below adds collection/reuse
sampling. Neither replaces E9 fatal-origin unwind acceptance. JIT-2's
independently reviewed identities and conclusion remain in
`docs/evidence/windows_x64_w025_jit2_result.md`.

### JIT-3 / FS-3 shared native acceptance - 2026-07-29

The lifecycle load gate passed four processes on Windows Server 2025 build
26100: a 24-cycle default J-2 stress, a 12-cycle J-1 comparison, and two
independent eight-cycle J-2 repeats. Together they compiled 1,344 optimizing
and normal-JNI allocations, forced 52 real code-cache collections, and reused
the exact old code address 1,248 times. Registration preceded each replacement
publication, and stable sampling observed 696,929 live lookups plus 696,969
successful virtual unwinds without a missing table. After retirement it
observed 5,909,811 dead lookups without a stale table; transition samples were
classified separately.

All four cases report `missing_live=0`, `stale_dead=0`,
`unwind_failures=0`, and `callback_tables=0`. Per-case maximum
`RtlLookupFunctionEntry()` latency ranges from 122,800 ns to 706,100 ns. The
integer mean rounds to 0 ns because it is below one
`QueryPerformanceCounter` tick; that is a resolution bound, not zero cost.
The runner also returns `jni_values=pass`, nine aggregate PASS records, an
empty JIT temporary directory, and `NO_DMP_FILES`.

The issued package records root `a741cfa8ab8e6388fcb78cae9b3c4c0ec63e898a`
and ART `43f866830eee0ee666b1cf3e9d2b3abffc45180b`. Its SHA-256 is
`8446a41d72aba32e19ce53cba8ac4b518b182bdebcd68c8023ce6e2ac6d0759f`;
the independently accepted returned archive SHA-256 is
`dcd3062a95a00296ca939062cc52fb7907405cc7c4e08ae72723a318063284fd`.
The compact acceptance conclusion remains in
`docs/evidence/windows_x64_w025_jit3_result.md`. This closes FS-3; it
does not replace E9 fatal-origin acceptance or the remaining debugger,
forced-policy, exception-XMM, pending-range, embedding, reservation-correlation,
and second-host work.

### JIT-4 shared native fatal/unwind cross-regression - 2026-07-29

The final default-build W-025 archive passed 28 cases and 34/34 aggregate
records on Windows Server 2025 build 26100. It intentionally used only the
default J-2 pagefile-section dual view; `j1_cases=0`. The nonfatal side repeats
the exact 12-record smoke, 14-workload matrix, JIT-disabled controls, default
CriticalNative, default normal/FastNative 7/7, and nterp/switch OSR paths.

Its eight-cycle lifecycle repeat compiled 216 optimizing/normal-JNI
allocations, forced eight collections, and reused 192 exact addresses.
Concurrent sampling completed 85,938 stable-live lookups, 855,876 stable-dead
lookups, 859,362 transition lookups, and 85,944 successful virtual unwinds
with `missing_live=0`, `stale_dead=0`, `unwind_failures=0`, and
`callback_tables=0`; JNI values remained exact.

The static, threshold-zero compiled-JIT, and OSR fatal cases each reached the
required origin, entered ART's VEH and UEF, and produced a new valid `MDMP`.
Their sizes are 747,247, 749,981, and 745,891 bytes. `jit-temp` remained empty
and no trace remained. This is a shared regression for the accepted E9 fatal
and JIT-3/FS-3 dynamic-unwind designs; it does not replace the E9 30-record
archive or close the independent debugger, forced-policy, exception-XMM,
pending-range, embedding, reservation-correlation, or second-host work.

The issued package records root
`a095f93d684c39a7454919255aa7fa508497f38d` and ART
`43f866830eee0ee666b1cf3e9d2b3abffc45180b`, with issued SHA-256
`411671ab378dab9fa4c4732934deb575d7dfb5873b5ab75ffe605514afcc8cf1`.
The independently accepted returned archive SHA-256 is
`843391f11e22225516162b25de0412d790c9ea669d0383a996e739aae8480096`.
The compact acceptance conclusion remains in
`docs/evidence/windows_x64_w025_jit4_result.md`.

### JIT-5 post-removal native fatal/unwind cross-regression - 2026-07-29

ART `389158d46f1e982c7d10d63093a42c8aa41fc2a6` removes the
`ART_WINDOWS_X64_JIT_DUAL` read and prevents Windows from reaching the common
single-view branch. Failure to create the pagefile section or any complete
logical view now returns the construction error. The JIT-5 source/package gate
also scans the rebuilt `art.dll` and rejects either retired string while
confirming that the common non-Windows single-view fallback remains.

Windows Server 2025 build 26100 passes 29 native cases and 36/36 aggregate
records. The retired-key process explicitly sets the old value to zero but
still records J-2 creation, compilation, Hello, and exit zero. The default ABI,
nterp/switch OSR, smoke, matrix, and JIT-disabled controls all pass.

The eight-cycle lifecycle process compiles 216 optimizing/normal-JNI
allocations, forces eight collections, reuses 192 exact code addresses, and
records 120,648 live lookups, 1,080,878 dead lookups, 1,102,642 transition
lookups, and 120,654 successful virtual unwinds. It reports
`missing_live=0`, `stale_dead=0`, `unwind_failures=0`,
`callback_tables=0`, and `jni_values=pass`.

Static, threshold-zero compiled-JIT, and switch-OSR fatal cases each reach ART
VEH and UEF and produce a valid `MDMP`; their sizes are 745,645, 745,067, and
750,705 bytes. `jit-temp` remains empty and no trace remains. The issued
archive SHA-256 is
`7b35eab8001ee2ba4881985b63d8df6921a954e023f8e70289f964499f57cd32`;
the independently accepted returned archive SHA-256 is
`2bddf51924a7ca6b9719ffde433e859007465babf6bf2ca7a12f417eecd6289f`.
The compact acceptance conclusion remains in
`docs/evidence/windows_x64_w025_jit5_result.md`.

This closes W-025 and cross-regresses the accepted E9 and FS-3 behavior. It
does not replace E9's 30-record core archive or close the independent
W-010/W-014 debugger, forced-policy, exception-XMM, pending-range, embedding,
reservation-correlation, or second-host work.

### FS-1 stack high-water acceptance - 2026-07-30

FS-1 is an opt-in measurement build, not a product instrumentation path.
`MDVM_FS1_STACK_HIGH_WATER=ON` passes
`ART_WIN32_STACK_HIGH_WATER=1` to both target compilation and the
layout-sensitive `asm_defines` generator. The product build uses the same
source with that definition absent. Structural inspection requires the normal
`art.dll` to omit the dump export and every high-water asm definition while
requiring the instrumented DLL and objects to contain them.

Each attached thread owns one fixed-size scalar record containing stack
geometry, sequence/active fields, and ten RSP slots. The overflow path does no
allocation, locking, symbol lookup, string construction, or formatting for
the measurement. Generated optimizing/nterp code and quick assembly directly
store RSP; common C++ uses inline scalar stores. The sampled phases are:

1. the failing explicit pre-prologue check;
2. quick throw entry and the completed save-all frame, when applicable;
3. common throw entry and temporary stack-end expansion;
4. entry to `StackOverflowError` construction and successful construction;
5. restoration of the default stack end; and
6. quick delivery and the long-jump frame, when applicable.

After Java catches the exception, the probe-only JNI library resolves the
opt-in export and requests formatting. The validator requires exactly four
records in `main-1`, `main-2`, `child-1`, `child-2` order, consecutive
per-thread sequences, every path-specific phase, exact geometry/reserve
arithmetic, a positive margin to both guarantee and native boundaries, the
expected switch/quick shape, required JIT compilation records, and no fatal
VEH/UEF marker. Dump state is compared across the complete Wine run and
recursively scanned by the native runner.

The final-source Wine gates pass with these minimum native margins:

| Build | switch | nterp | JIT |
|-------|-------:|------:|----:|
| Release | 7536 | 7520 | 7616 |
| Debug | 69728 | 37216 | 37232 |

Windows Server 2025 build 26100 passes the immutable native package with these
minimum margins:

| Build | switch | nterp | JIT |
|-------|-------:|------:|----:|
| Release | 6784 | 7536 | 7616 |
| Debug | 69744 | 37168 | 37232 |

The initial native Debug build failed all three engines with
`0xC00000FD STATUS_STACK_OVERFLOW` even though Wine passed. Its captured dump
mapped the final exception to
`art::gc::Heap::CheckPreconditionsForAllocObject` at `runtime/gc/heap.cc:4555`
while constructing `StackOverflowError`. This identified exhaustion of the
recovery interval rather than a missed explicit check. A controlled
20,480-byte trial made switch pass but left nterp and JIT approximately 8208
and 8196 bytes below the native boundary. The selected 40-KiB non-`NDEBUG`
Windows x86_64 reserve adds a three-page margin over that measured need. It
leaves more than 37 KiB on both native quick paths and does not alter Release,
product, or non-Windows builds, which remain at 8192 bytes.

Wine Debug also passes `-XX:ThreadSuspendTimeout=30000` because O0 recursion
can remain outside a safepoint beyond ART's two-second default under Wine.
That flag is isolated to the FS-1 Debug runner. Native Debug enablement also
exposed and repaired COFF flag-registry initialization ordering, Windows
absolute-path recognition, source-level flag reload caller identification,
an unsafe class-loader diagnostic, and Debug PE export-count overflow. The
probe package supplies the standard debug `libopenjdkd.dll` alias. None of
these changes adds a product fault handler or changes Release stack geometry.

The native runner records six PASS child processes, four complete records per
process, `NO_DMP_FILES`, and `OVERALL PASS`. The 53,459,106-byte archive
SHA-256 is
`22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe`;
the hash matched after transfer and its internal manifest passed before
execution. Compact evidence is under
`tests/cases/stack-high-water/RESULT.md`.

Post-FS-1 regressions pass: the product explicit-check object gate, nterp/JIT
W-010 managed NPE/SOE Wine gate, full Linux rebuild, Linux object's seven
unchanged implicit probes, and shared-boot imageless Linux Hello. FS-1 closes
the handler/throw stack-budget proof point. FS-2 is now accepted on the same
build-26100 host; compact native evidence is under
`docs/evidence/windows_x64_fs2_w010_w014_result.md`.

### FS-4 same-host repeat — 2026-07-30

The accepted Windows Server 2025 build-26100 host was rebooted and the
E9/FS-2, FS-1, and JIT-3/FS-3 packages were rerun from fresh extraction
directories. All three native runners returned `OVERALL PASS`. The combined
E9/FS-2 run retained six intentional fatal/embedding dumps, reported
`NO_HANDLED_DMP_FILES`, and passed debugger, CET/HSP, managed-fault,
embedding, XMM, and structural records. FS-1 passed Release and Debug
switch/nterp/JIT with four records per mode; minimum margins were Release
6528/7552/7632 and Debug 69568/37216/37232 bytes. JIT-3/FS-3 passed its J-2
stress, J-1 comparison, and two J-2 repeats with clean JIT-temp and dump
scans.

The additional native stack checks passed all 16 parameterized combinations
of baseline/protected/writable/direct diagnostic growth modes at guarantee
requests 0, 8192, 16384, and 65536 bytes. The thread-stack probe accepted
reservations from 64 KiB through 9 MiB, completed 512 joins and 128 detach
stress cases, and rejected an active fiber. The page-state probe passed eight
selection cases, five layout cases, 16 KiB configured guarantees, 64 committed
and 64 reserved restorations, and 258 direct faults. Compact raw results and
the host identity are under
`docs/evidence/windows_x64_fs4_same_host_result.md`.

Per the acceptance-policy decision, this closes FS-4 on the authoritative
Windows Server 2025 build-26100 host. A local SSH inventory found no second
supported Windows host; the only other listener (`10.127.137.60`) identifies as
Ubuntu and rejects the available Windows credentials. The separate Windows 10
repetition is intentionally skipped and is not an FS-4 exit criterion.

### FS-5 pending interpreter-bridge range — 2026-07-30

FS-5 is conditionally closed as impractical coverage. The bridge's primary
200-byte range and the separate 88-byte pending range both have validated PE
runtime-function records, and `win32_osr_unwind_probe` passes the live lookup
and synthetic body/epilogue unwind checks. Native E6/E9 fatal traces exercise
the primary bridge at `+0x82` across static, JIT, and OSR origins, with the
expected ART VEH/UEF and dump behavior.

The pending range is reached only by the `Thread::exception != null` branch
after `artQuickToInterpreterBridge` returns. Its tail prepares an
all-callee-save frame and calls the non-returning pending-exception delivery
helper; it is not entered by a Windows native exception. Injecting an invalid
access or jumping directly into that internal tail would change product
control flow or fabricate ART state, so it would not be acceptance evidence.
The accepted primary/fatal matrix is therefore the closure boundary. The
reproducible reasoning and output are recorded in
`tests/cases/managed-fault-recovery/RESULT.md`.

### Next execution schedule — dependency order

This schedule closes product proof points before optional mechanism research.
It is evidence-gated rather than date-gated. FS-3 was split into an independent
JIT closure package and completed before FS-1; FS-1, FS-2, and the
authoritative-host FS-4 repeat are now accepted, and FS-5 is conditionally
closed. Remaining work is limited to the optional reservation/negative/
debugger-quality follow-ups.

| Order | Work | Exit gate |
|------:|------|-----------|
| FS-1 (done) | Add allocation-free high-water instrumentation around the explicit check, quick throw, temporary stack-end expansion, exception construction, and non-local transfer; run release and debug builds | Accepted 2026-07-30: Wine and native Release/Debug switch, nterp, and JIT have positive margins; native quick Debug retains more than 37 KiB with the 40-KiB Debug-only reserve; four records per mode and no dumps |
| FS-2 (done) | Extend the combined native package with debugger first-chance/continue, every named forced-incompatible CET policy, foreign VEH/frame-SEH/predecessor-UEF embedding, and XMM6-XMM15 sentinels during exception unwind | Accepted 2026-07-30 on build 26100: NPE continues into Java, explicit SOE remains fault-free, incompatible CET starts reject before Java/JIT with no dump, foreign search handlers coexist, and full-width XMM state survives unwind |
| FS-3 (done) | With JIT-1 encoding and JIT-2 mapping/policy prerequisites complete, share the JIT closure load test: compile, invalidate, collect, reuse, and re-register many optimizing/JNI allocations while another thread performs lookup and virtual unwind | Accepted 2026-07-29: 52 collections, 1,344 compilations, 1,248 exact reuses, and 696,969 virtual unwinds complete with no missing/stale/failed record; callback tables remain unnecessary |
| FS-4 (closed by policy) | Run FS-1 through FS-3, E9, parameterized guarantee geometry, fiber/manual-stack rejection, and deep detach/continue/reattach lifecycle on the authoritative host | Closed 2026-07-30 by decision: Windows Server 2025 build 26100 is authoritative; the Windows 10/second-host repetition is skipped. Evidence: `docs/evidence/windows_x64_fs4_same_host_result.md` |
| FS-5 (closed conditional) | Attempt the brief pending bridge-range exception only if a deterministic probe can enter it without changing product control flow | Closed 2026-07-30: the pending tail is entered only by ART's managed pending-exception branch; structural and synthetic unwind checks pass, while a real native fault would require product fault injection or fabricated direct entry. See `tests/cases/managed-fault-recovery/RESULT.md` |

The history follow-ups—fatal-dump instrumentation with RSP inside the pregrown
ART page, an ART implicit-stack feature flag, and a HotSpot-style
`STATUS_STACK_OVERFLOW` prototype—are deliberately deferred. Start that
research track only if a new product requirement reopens the accepted explicit
check design; none is a prerequisite for W-010/W-014 closure.

## 16. Primary references and comparative implementation

Microsoft contracts:

- [`AddVectoredExceptionHandler`](https://learn.microsoft.com/windows/win32/api/errhandlingapi/nf-errhandlingapi-addvectoredexceptionhandler)
- [Vectored exception handling](https://learn.microsoft.com/windows/win32/debug/vectored-exception-handling)
- [`PVECTORED_EXCEPTION_HANDLER`](https://learn.microsoft.com/windows/win32/api/winnt/nc-winnt-pvectored_exception_handler)
- [`EXCEPTION_RECORD`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-exception_record)
- [Windows x64 `CONTEXT`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-context)
- [`SetUnhandledExceptionFilter`](https://learn.microsoft.com/windows/win32/api/errhandlingapi/nf-errhandlingapi-setunhandledexceptionfilter)
- [`GetCurrentThreadStackLimits`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentthreadstacklimits)
- [`IsThreadAFiber`](https://learn.microsoft.com/windows/win32/api/fibersapi/nf-fibersapi-isthreadafiber)
- [Thread stack size](https://learn.microsoft.com/windows/win32/procthread/thread-stack-size)
- [`_beginthreadex`](https://learn.microsoft.com/cpp/c-runtime-library/reference/beginthread-beginthreadex)
- [`VirtualQuery`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualquery)
- [`VirtualAlloc`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc)
- [`VirtualFree`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualfree)
- [`VirtualProtect`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect)
- [Creating guard pages](https://learn.microsoft.com/windows/win32/memory/creating-guard-pages)
- [`_resetstkoflw`](https://learn.microsoft.com/cpp/c-runtime-library/reference/resetstkoflw)
- [`SetThreadStackGuarantee`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-setthreadstackguarantee)
- [`PROCESS_MITIGATION_USER_SHADOW_STACK_POLICY`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-process_mitigation_user_shadow_stack_policy)
- [`GetProcessMitigationPolicy`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocessmitigationpolicy)
- [`/CETCOMPAT`](https://learn.microsoft.com/cpp/build/reference/cetcompat)
- [x64 exception handling and unwind data](https://learn.microsoft.com/cpp/build/exception-handling-x64)
- [x64 prolog and epilog rules](https://learn.microsoft.com/cpp/build/prolog-and-epilog)
- [`RtlAddFunctionTable`](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable)
- [`RtlDeleteFunctionTable`](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtldeletefunctiontable)
- [`RtlAddGrowableFunctionTable`](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtladdgrowablefunctiontable)
- [`RtlGrowFunctionTable`](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtlgrowfunctiontable)
- [`RtlInstallFunctionTableCallback`](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtlinstallfunctiontablecallback)

Comparative implementation:

- [LLVM ORC COFF platform runtime](https://github.com/llvm/llvm-project/blob/main/compiler-rt/lib/orc/coff_platform.cpp)
  registers each immutable COFF `.pdata` range with `RtlAddFunctionTable()`
  and deletes it with the exact same pointer. ART uses the same API pair but
  owns one immutable entry per independently collected JIT allocation.
- [OpenJDK HotSpot Windows OS layer](https://github.com/openjdk/jdk/blob/master/src/hotspot/os/windows/os_windows.cpp)
  uses `_beginthreadex` with reservation semantics, a first VEH, direct
  `EXCEPTION_POINTERS` context redirection, separate access-violation and
  native-stack-overflow handling, and previous-UEF chaining. It is supporting
  evidence for the Windows mechanisms, not a replacement for ART's own frame
  and exception invariants.

## 17. Final design principle

Keep generated ART code unchanged where Windows can present the same facts
safely. Where native stack growth fundamentally differs, isolate the smallest
audited platform delta: a pre-prologue RSP comparison and guarantee-aware
thread bound. Everything after detection remains ART's existing throw,
recovery-reserve, and managed-exception path, and Linux's implicit mechanism
remains unchanged.
