# Win64 managed faults and ART stack design

**Status:** W-010 Stages 0/C/D and W-014 Stages A-B implemented and locally
verified under Wine and Linux; native Windows Stage E acceptance remains
**Created:** 2026-07-26
**Updated:** 2026-07-27
**Target:** x86_64 Windows 10 build 17134+
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

The selected design is:

1. Keep ART's existing implicit null-check and implicit stack-overflow model.
   Do not add Windows-only explicit checks to optimizing code or nterp unless
   the selected design fails native stress.
2. Implement a process-wide ART managed-fault VEH with
   `AddVectoredExceptionHandler(1, ...)`. It handles only recognized,
   continuable `EXCEPTION_ACCESS_VIOLATION` records and returns
   `EXCEPTION_CONTINUE_SEARCH` for everything else.
3. Make `sigchain_windows.cc` a narrow ART-internal facade for the one special
   `SIGSEGV` action that `FaultManager` registers. Do not emulate `sigaction`,
   signal masks, or general POSIX signal delivery.
4. Pass a small non-owning Windows fault view through the x86_64 adapter. The
   view points at the real Win64 `CONTEXT` and carries the documented AV access
   kind; handlers modify the real `Rip`/`Rsp` in place. Construct only the
   small `siginfo_t` view needed by common `FaultManager`. Do not copy the
   Windows register set into a fabricated Linux `ucontext_t` and back.
5. Reuse the common `FaultManager`, generated-code range registry, handler
   ordering, null classifier, stack classifier, and quick exception
   entrypoints. Strengthen Windows stack-overflow recognition by requiring the
   AV to be a read and the fault address to be inside the current thread's
   recorded ART protected page.
6. Treat Windows `EXCEPTION_STACK_OVERFLOW`, `PAGE_GUARD`, and the moving OS
   stack guard as native Windows mechanisms. ART's managed stack probe instead
   faults on a separate fixed `PAGE_NOACCESS` page and therefore arrives as an
   access violation.
7. Discover the current system stack with
   `GetCurrentThreadStackLimits()`, reject `IsThreadAFiber()`, validate the
   complete allocation with `VirtualQuery()`, and reject attachment if the
   current SP is outside that allocation. Do not clamp, guess, or use
   undocumented TEB fields.
8. Preserve the lowest allocation page and every pre-existing bottom
   `PAGE_NOACCESS`/`PAGE_GUARD` page. Select the first suitable reserved or
   ordinary committed page above that excluded-low prefix as ART's fixed
   `PAGE_NOACCESS` page, followed by ART's existing 8 KiB x86_64 overflow
   reserve. Do not assume that `low + one page` is always available.
9. Create CRT-using ART threads with `_beginthreadex`, not raw `CreateThread`.
   For a non-zero requested stack size, pass
   `STACK_SIZE_PARAM_IS_A_RESERVATION`. Replace the current thread-ID/reopen
   join scheme with an opaque pthread control object that retains the real
   handle for joinable threads.
10. Disable caller-supplied `pthread_attr_setstack()` stacks for Windows ART
    thread pools. Pass the requested reservation size to the OS instead.
11. Activate implicit null and stack-overflow checks only as one product
    capability: VEH installed, common handlers registered, every attached
    thread has validated bounds, and every such thread has its protected page.
    A per-thread installation failure rejects that attachment or thread birth.
12. Keep fatal crash diagnostics separate from managed fault translation.
    Expected faults do not log or dump. The unhandled-exception filter writes a
    best-effort dump, then chains to the previously installed filter.
13. Do not support Windows CET user shadow stacks (Hardware-enforced Stack
    Protection) in the current Win64 ART design. Every ART process must run
    with that mitigation completely disabled; compatibility, audit, and strict
    modes are all unsupported. Build every project Win64 PE explicitly with
    `/CETCOMPAT:NO`, inspect packaged DLLs, and reject startup before managed
    threads or JIT initialization if the process policy is active.

## 2. Scope and ownership

### 2.1 W-010 owns

- Registration, promotion, and removal of the ART managed-fault VEH.
- Cooperative handler-chain semantics and debugger coexistence.
- Validation of `EXCEPTION_RECORD` and Win64 `CONTEXT`.
- Adaptation of recognized access violations to common ART fault handling.
- In-place Win64 PC/SP context access in the x86_64 fault handler.
- Implicit null-pointer translation.
- ART protected-page stack-overflow translation.
- The activation gate for generated code that depends on implicit faults.
- Separation of managed translation from fatal VEH/UEF diagnostics.

### 2.2 W-014 owns

- Current-thread stack discovery and validation.
- Stack reservation sizing for Java and ART-created native threads.
- The Windows pthread attribute and join/detach contract needed by those
  threads.
- The Windows thread-pool stack policy.
- ART stack accounting (`stack_begin_`, `stack_end_`, `stack_size_`).
- Placement, commit, protection, temporary unprotection, and restoration of
  the fixed ART page.
- Rejection policy for fibers, manual stacks, and impossible bounds.

### 2.3 Explicit non-goals

- General POSIX signal emulation on Windows.
- Windows 7 support or dynamic resolution of Windows 8+ stack APIs.
- Translating native stack exhaustion into Java `StackOverflowError`.
- Supporting caller-provided stack addresses through fibers.
- Windows ARM64 in the first implementation. The interfaces should not prevent
  it, but all concrete acceptance in this draft is Win64 x86_64.
- Perfect PE native unwinding through every quick assembly stub. Managed stack
  walking remains ART-owned; PE `.pdata`/`.xdata` is separate diagnostics
  hardening unless testing proves it is required for correctness. This
  separation is valid only under the required CET-shadow-stack-disabled
  process contract.
- Enabling implicit suspend checks on Win64 x86_64. Current ART enables that
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

Windows should preserve that sequence. The OS-specific differences are how
the fault is delivered, how PC/SP are represented, and how the fixed page is
created.

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
- Every attached non-AOT Windows thread now measures the excluded-low prefix,
  selects a suitable page, records its original state, installs and verifies
  a fixed `PAGE_NOACCESS` page, and accounts for that page in ART's published
  stack bounds. Reserved originals are committed only for the ART lifetime;
  committed-private read/write originals retain their contents.
- `ProtectStack()` and `UnprotectStack()` now implement verified state
  transitions. `Thread` teardown directly restores and verifies the original
  reserved or committed state before an external native thread can continue.

The current tree now has the active W-010 product capability:

- `sigchain_windows.cc` owns one immutable special-`SIGSEGV` action and a
  first VEH. It filters exact continuable access violations, adapts the real
  Win64 `CONTEXT`, supports promotion/removal, and continues the search for
  every unsupported or unrecognized exception.
- `runtime_windows.cc` still owns a separate diagnostic VEH. It may log fatal
  first-chance events, but it never translates managed faults. The fatal UEF
  writes a best-effort dump and chains to its predecessor, or returns search.
- Runtime initialization enables implicit null and stack-overflow checks on
  Win64 x86_64 and keeps implicit suspend checks disabled, matching ART's
  x86_64 policy. Common handlers retain Linux order: stack before null.
- Win64 registers nterp's immutable generated-code range during fault-manager
  initialization from `IsNterpSupported()`, before `Runtime::Start()` can
  publish nterp entrypoints. JIT ranges continue through common
  `Runtime::AddGeneratedCodeRange()`.
- A normal started runtime rejects `-Xno-sig-chain` on Windows exactly as on
  Linux. The option remains for genuine non-started compiler/tool runtimes.
- The focused Stage D Wine gate catches 64 read plus 64 write NPEs and repeated
  main/child SOEs in both nterp and threshold-zero JIT, with no managed-fault
  diagnostic output or dump-state change.

Stage D is therefore locally complete. Stage E must reproduce the generated
fault, handler-chain, debugger, stack-budget, fatal-UEF, and HSP policy matrix
on native Windows 10/current Windows.

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
to break on every access violation will stop on normal implicit null and stack
checks. This is not an ART handler-order bug. Native acceptance must prove that
continuing the debugger resumes into the managed exception path.

### 5.3 `PAGE_GUARD` is not ART's fixed page

Windows guard pages are one-shot alarms. On first access Windows raises
`STATUS_GUARD_PAGE_VIOLATION` and clears `PAGE_GUARD`. Windows also uses a
moving guard page to grow thread stacks. ART requires a fixed page that faults
again after every caught overflow, so its page must use `PAGE_NOACCESS` and be
explicitly unprotected/reprotected by ART.

### 5.4 ART probes should not use `EXCEPTION_STACK_OVERFLOW`

An access to `PAGE_NOACCESS` produces `EXCEPTION_ACCESS_VIOLATION`. That is the
intentional W-010 event. `EXCEPTION_STACK_OVERFLOW` represents exhaustion of
the Windows-managed stack growth mechanism and has different recovery rules,
including compiler/CRT-specific guard restoration. Translating that event as
if it were ART's pre-prologue probe would lack the required PC, SP, and frame
invariants.

### 5.5 The system stack interval is a documented API

`GetCurrentThreadStackLimits()` returns the lower and upper limits of the stack
allocated by the system for the current thread. Microsoft explicitly warns
that user-mode code can execute outside that allocation. ART therefore must
check that current SP is inside the returned interval; this also gives a clean
policy for fibers and manual stacks.

### 5.6 Commit and protection are separate operations

`VirtualAlloc(address, size, MEM_COMMIT, protection)` commits pages inside an
existing reservation. `VirtualProtect` works only on committed pages. The
implemented selector also accepts an already committed private
`PAGE_READWRITE` page, whose contents and original protection must survive
detach. The fixed-page installation sequence is therefore deterministic:

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

### 5.8 `SetThreadStackGuarantee` is secondary, not the managed design

`SetThreadStackGuarantee` reserves stack space for handling native
`EXCEPTION_STACK_OVERFLOW`. It does not create ART's fixed page, classify an
ART probe, or restore ART's stack accounting. The initial implementation
should not depend on it. It may later be evaluated for fatal native-overflow
diagnostics, separately from managed overflow correctness.

### 5.9 CET user shadow stacks conflict with ART's non-local transfers

The current Win64 ART runtime does not support CET user shadow stacks. The
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
Win64 quick assembly does not provide complete PE unwind metadata. These are
additional rejection reasons, but fixing them alone would not repair
`art_quick_do_long_jump`.

The supported process contract is therefore exact:

- `PROCESS_MITIGATION_USER_SHADOW_STACK_POLICY.Flags` must be zero whenever
  `ProcessUserShadowStackPolicy` is available;
- `EnableUserShadowStack`, `AuditUserShadowStack`,
  `SetContextIpValidation`, `AuditSetContextIpValidation`, strict mode, and
  every other current or future nonzero policy bit are rejected;
- Windows compatibility mode is not accepted merely because non-CET modules
  may be tolerated there;
- every project Win64 executable and DLL link must explicitly pass
  `/CETCOMPAT:NO`; packaged LLVM libc++ and other DLLs must also be inspected
  for absence of `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT`;
- the launcher or Windows Exploit Protection configuration must disable
  Hardware-enforced Stack Protection before process creation. ART cannot
  downgrade or disable an active policy with `SetProcessMitigationPolicy`;
- CFG remains a separate mitigation. Supporting or testing CFG does not imply
  CET shadow-stack support.

Stage 0 now implements both enforceable halves of this rule. The generated
Win64 graph, all handwritten Win64 CMake harnesses, and all direct Clang/lld
PE links pass `/CETCOMPAT:NO` explicitly. A structural verifier audits those
sources and Ninja link commands, then scans the selected build/package trees
and LLVM libc++ for the CET-compatible extended characteristic. The runtime
queries the process policy immediately after selecting the logger and before
`MemMap::Init()`, ART thread startup, nterp publication, or JIT initialization.
Every nonzero flag and every unexpected query/version failure is rejected.

Local completion is intentionally not described as native acceptance. Wine
reports the policy as disabled and exercises the allow path, but it cannot
prove Windows Exploit Protection compatibility, audit, and strict modes. A
native CET-capable Windows run must still force each rejected policy family
and prove early bounded failure with no managed execution or dump.

On Windows 10 version 2004/build 19041 and later, startup queries
`GetProcessMitigationPolicy(GetCurrentProcess(),
ProcessUserShadowStackPolicy, ...)` before creating ART threads or enabling
nterp/JIT and rejects every nonzero result with a bounded diagnostic. On older
supported Windows 10 builds, the documented policy class is unavailable; only
the expected unsupported-policy result is accepted as evidence that HSP is
unavailable. Unexpected query failures on systems that implement the policy
fail closed.

## 6. Designs considered

### 6.1 Selected: VEH adapter over the existing `FaultManager`

Windows `AddSpecialSignalHandlerFn(SIGSEGV, ...)` copies the ART action and
installs the managed-fault VEH. The VEH constructs a minimal `siginfo_t` and a
stack-local non-owning `WindowsFaultContext` that references the real
`CONTEXT*` and records the AV access kind. It passes that view to
`FaultManager::HandleSigsegvFault()` and translates the boolean result to a VEH
return value.

Advantages:

- generated code is unchanged;
- common handler order and code-range checks are unchanged;
- Java exception entrypoints are unchanged;
- Linux behavior is unchanged;
- the Windows delta is limited to one dispatcher, one x86 context view, and
  stack VM primitives.

### 6.2 Rejected for now: platform-neutral `FaultContext` refactor

A new abstract context type shared by every ISA and OS would be conceptually
clean, but it would modify common fault signatures and every architecture
handler. That creates substantially more Linux/Android regression surface
than the narrow Win64 adapter and provides little immediate value for a
single Windows ISA.

This remains a possible upstream-oriented cleanup after Win64 behavior is
proven.

### 6.3 Fallback only: explicit Windows stack and null checks

Windows-specific generated code could compare RSP with `Thread::stack_end_`
and branch to the existing throw entrypoint, and nterp could add explicit null
branches. This removes deliberate AVs and fixed-page recovery complexity.

It is not selected because ART's optimizing backends currently assume
implicit stack checks, nterp contains unconditional implicit probes, and the
result would fork hot generated-code paths from Linux. Use this only if native
Windows proves that a safe VEH path cannot fit the required stack budget or
cannot coexist with product security/debugger requirements.

### 6.4 Rejected: frame-based SEH around every ART transition

SEH wrappers around every thread or managed entry do not naturally cover all
JIT/nterp execution and would duplicate fault classification in a second
control-flow model. VEH is specifically designed for process-wide observation
before frame unwinding.

### 6.5 Rejected: native Windows guard/overflow only

Relying on moving `PAGE_GUARD`, `EXCEPTION_STACK_OVERFLOW`,
`SetThreadStackGuarantee`, or `_resetstkoflw` would change when overflow is
detected and would not preserve ART's pre-prologue frame invariant or repeated
caught-overflow behavior.

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

### 7.4 Non-owning Win64 context adaptation

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

- the common handlers modify only the saved PC and SP for current Win64
  implicit faults;
- all untouched integer and vector registers remain in the real OS context;
- rSELF in R15 is restored by Windows automatically;
- no copy-back list can accidentally omit a register;
- the stack handler can validate the documented AV access kind without
  abusing unused `siginfo_t` fields or process-global state;
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
entrypoint publication. Future PE AOT loading must prove an equivalent
publication edge before it is added to this contract.

### 7.6 Stack-overflow classification

Stack overflow remains the first generated-code handler. It succeeds only if:

```text
operation is read
fault_address == CONTEXT.Rsp - GetStackOverflowReservedBytes(kX86_64)
fault_address is within [thread.art_protected_begin,
                         thread.art_protected_end)
thread.art_protected_state == Protected
```

The protected-range check is the Windows strengthening over the existing
x86_64 equality test. No `VirtualQuery()` is needed because W-014 records the
page in `Thread` during attachment.

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

An opt-in diagnostic build may add a final observer VEH or a preallocated
record ring, but it must be off by default and must not run before the managed
translator.

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

### 8.3 Windows lower-stack layout

The selected conceptual layout is:

```text
high / GetCurrentThreadStackLimits.HighLimit
  normal native and managed frames
  ... Windows committed/reserved regions; moving PAGE_GUARD may be here ...
stack_end
  ART overflow reserve: 8 KiB on x86_64
stack_begin
  ART fixed page: committed PAGE_NOACCESS
  excluded-low prefix, left in original state:
    lowest allocation page
    any adjacent PAGE_NOACCESS/PAGE_GUARD pages
low / GetCurrentThreadStackLimits.LowLimit
```

The excluded-low prefix is not a guessed pthread guard size. It is a measured
set of bottom pages that ART refuses to repurpose. At minimum it contains the
lowest allocation page. If the following page is already `PAGE_NOACCESS` or
`PAGE_GUARD`, ART skips that complete region as well. This handles both the
usual native reserved-bottom layout and the fully committed Wine layout that
has already shown `PAGE_NOACCESS` followed by `PAGE_GUARD`.

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

The common `InitStack()` interface may describe this measured prefix as
`read_guard_size = excluded_low_bytes`, but the Windows implementation must
document that it is an excluded-low accounting value, not the size or current
location of Windows' moving guard.

### 8.4 Protected-page installation

Installation occurs during `Thread::InitStack()` after bounds validation and
before the thread publishes itself for managed execution.

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
6. Publish the page address and `Protected` state in the owning `Thread`.

If protection fails after a reserved page was committed, installation restores
and verifies the original page state before rejecting attachment. If rollback
itself cannot be verified, the populated record is retained so thread teardown
can retry direct restoration; the implementation never clears ownership of an
unrestored page.

The Windows path returns immediately after this platform operation. It does
not run Linux's recursive `VM_GROWSDOWN` touching and does not `madvise()` the
stack.

### 8.5 Protection state machine

Each attached thread records:

```text
NotInstalled
  -> Protected
  -> WritableForStackOverflow
  -> Protected
```

`UnprotectStack()` is legal only for the current thread while ART is handling
its overflow. It changes exactly the recorded page to `PAGE_READWRITE`.
`ProtectStack()` changes exactly that page back to `PAGE_NOACCESS`. Both verify
the old protection and query the exact allocation, range, private type, and
new protection before publishing the state transition.

A failed transition is not recoverable by continuing through generated code:

- installation failure rejects attach/thread birth;
- unprotect failure makes overflow construction unsafe and is fatal;
- reprotect failure would make later overflows undetectable and is fatal.

No handler path discovers the page with `VirtualQuery()`; the prevalidated
address is used directly.

### 8.6 Detach policy

ART-created Java and pool threads terminate immediately after ART unregisters
them, so Windows releases their complete stack allocation.

An externally created native thread may detach and continue. W-014 must restore
the ART page before deleting its `Thread`:

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

Native tests must cover attach, managed execution, detach, continued native
stack use, reattach, and a second detach. If exact restoration proves unsafe
after Windows guard movement, the supported policy must instead require an
attached native thread to remain attached until exit; silently leaving the
page is not acceptable.

The local Wine W-002 gate now performs that lifecycle twice on each of sixteen
raw `CreateThread` threads in every mode: attach, managed JIT callback, detach,
about 16 KiB of recursive native stack use, reattach, a second callback, and a
second detach. This proves the implemented restoration/reattach path under
Wine; native Windows guard-growth acceptance remains required.

### 8.7 Thread creation and pthread attributes

The Windows pthread shim must honor:

- `stacksize == 0`: executable default reservation;
- `stacksize != 0`: `_beginthreadex(..., stacksize, ...,
  STACK_SIZE_PARAM_IS_A_RESERVATION, ...)`;
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
overflow overhead before `pthread_create()`. Because the main thread attaches
before architecture implicit-check flags are selected, the Windows bootstrap
branch also adds one protected-page capacity so installing the
ART-owned page does not silently debit the requested stack budget. The
measured excluded-low prefix belongs to the Windows system-stack reservation
layout and is not guessed or added as another ART-owned page.

For thread pools:

```cpp
kUseCustomThreadPoolStack = !defined(__BIONIC__) && !defined(_WIN32)
```

conceptually. Windows passes `worker_stack_size` through
`pthread_attr_setstacksize()` and does not allocate a `MemMap` stack or call
`pthread_attr_setstack()`.

### 8.9 Moving Windows guard interaction

The Windows moving `PAGE_GUARD` remains under OS control and is never reused as
ART's fixed page. Depending on current commitment it may initially be far
above the selected page or adjacent to the excluded-low prefix. W-010
explicitly ignores guard-page exceptions. Native probes must show that:

- ordinary stack growth still commits pages;
- installation does not move or consume the current guard unexpectedly;
- the ART probe reaches the fixed page as an access violation;
- returning from VEH and entering the quick throw stub works with the guard's
  then-current position;
- repeated caught overflows leave both normal stack growth and the fixed ART
  page functional.

Wine observations are useful here but cannot establish native small-stack or
guard-growth behavior.

## 9. Stack-overflow event sequence

```text
generated method/nterp entry
  test [rsp - 8192]
        |
        v
fixed ART PAGE_NOACCESS page
  EXCEPTION_ACCESS_VIOLATION (read)
        |
        v
debugger first chance
        |
        v
ART managed-fault VEH
  validate record/context/r15/thread/code range
  validate exact rsp-8192 address inside recorded ART page
  context.Rip = art_quick_throw_stack_overflow
  return EXCEPTION_CONTINUE_EXECUTION
        |
        v
Windows restores original registers and Rsp, resumes at quick stub
        |
        v
artThrowStackOverflowFromCode(Thread*)
  SetStackEndForStackOverflow()
  VirtualProtect(ART page, PAGE_READWRITE)
  construct and install StackOverflowError
  ResetDefaultStackEnd()
  VirtualProtect(ART page, PAGE_NOACCESS)
        |
        v
ART long-jumps/delivers to the managed catch site
```

No Windows SEH unwind is used for the managed transition. This sequence is
supported only with CET user shadow stacks disabled; its final ART long jump
does not maintain a hardware shadow-stack pointer.

## 10. Activation and failure policy

The current independent booleans are not sufficient for Windows product
activation. Define a conceptual capability:

```text
win_managed_faults_ready =
    CET user-shadow-stack policy completely disabled
    && VEH registered
    && special SIGSEGV action published
    && x86_64 WindowsFaultContext adapter built
    && implicit null handler registered
    && implicit stack handler registered
```

Then:

- startup must query the process CET/HSP policy before creating ART threads or
  enabling JIT and reject every supported nonzero policy value;
- `implicit_null_checks_` may be true only when the capability is ready;
- `implicit_so_checks_` may be true only when it is ready and each attached
  thread installs its fixed page;
- Win64 nterp and JIT may be product-enabled only under those flags because
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

Windows has no POSIX `sigaltstack` contract for VEH. The design assumes the
exception machinery and handler consume the faulting thread's stack and must
therefore prove that the existing 8 KiB ART reserve is sufficient.

The recognized stack path must:

- avoid heap allocation;
- avoid logging and symbolization;
- avoid `VirtualQuery()` and minidump APIs;
- avoid ART mutex acquisition;
- avoid large locals and compiler-generated stack probes;
- avoid recursion except the explicit nested-fault fatal escape;
- change only the saved PC on successful stack classification.

A native probe records, in preallocated storage:

- interrupted RSP from `CONTEXT`;
- VEH entry/current SP high-water use;
- lowest SP reached before `UnprotectStack()`;
- fixed page and reserve boundaries.

Keep the shared 8 KiB value if native debug and release builds retain a clear
margin. Increase only the Windows x86_64 reserve if measurement proves it is
necessary; do not increase it speculatively.

## 12. Implementation stages

### Stage 0 — CET shadow-stack exclusion — implemented locally

- Add explicit `/CETCOMPAT:NO` to every project Win64 executable and DLL link
  target instead of relying on lld's current default.
- Inspect every packaged PE, including LLVM libc++, and reject packaging if
  `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT` is present.
- Query `ProcessUserShadowStackPolicy` at the earliest runtime initialization
  point, before managed thread creation, nterp publication, or JIT startup.
- Accept only an all-zero policy on Windows versions that implement the query;
  accept the expected unavailable-policy result on older supported Windows 10
  builds; fail closed on unexpected query failures.
- Emit a bounded diagnostic explaining that Hardware-enforced Stack Protection
  must be disabled by the launcher or Windows Exploit Protection policy before
  process creation.
- Do not use `/guard:ehcont`, dynamic EH-continuation registration, or dynamic
  CET-compatible-range registration as a substitute.

Clean completion criteria:

- generated and handwritten Win64 link commands contain `/CETCOMPAT:NO`;
- packaged PE inspection finds no CET-compatible extended characteristic;
- an HSP-disabled native process passes the startup guard;
- compatibility, audit, and strict HSP policies are rejected before managed
  execution, without relying on a late control-protection exception or dump.

Implementation and local evidence (2026-07-26):

- `GlobalPolicy.add_ldflags` injects `LINKER:/CETCOMPAT:NO` into every
  generated non-static target; static archives intentionally receive no link
  options.
- Nine handwritten Win64 CMake harnesses and three direct Clang/lld links use
  the same explicit option.
- The base Phase-3 host packager and the focused W-002/W-003/W-004/W-013
  packagers invoke the PE audit before writing their final manifests/archives.
  A synthetic `/CETCOMPAT` PE is rejected by the same package scan.
- `cet_compat.cc` separates Win32 API observation from a deterministic policy
  decision. It obtains the real build number through `RtlGetVersion`, accepts
  only zero flags, accepts `ERROR_INVALID_PARAMETER` only below build 19041,
  and fails closed for unknown versions, future nonzero bits, or unexpected
  query failures.
- `Runtime::Init()` runs the guard after logger selection and before
  `MemMap::Init()` and thread/JIT initialization. Rejection returns normal
  startup failure rather than deliberately triggering a control-protection
  exception.
- The focused policy probe covers disabled, every current policy-bit family,
  a future/reserved bit, old-build unavailability, and failure cases. Under
  Wine it reports build 19043, zero flags, and `PASS`.
- The structural/package verifier reports 9 CMake harnesses, 3 direct links,
  5 enforced host packagers, 19 Ninja PE link targets, and 20 inspected PE
  files including external LLVM `c++.dll`, all with no CET-compatible marker.
  The selected Win64 build completed 321 steps
  and `dalvikvm
  -showversion` reports `ART version 2.1.0 x86_64` under Wine.
- The complete Phase-4 Wine suite passes after the change, including W-002,
  W-003 frame/XMM matrices, GC/thread/handle stress, intentional crash gates,
  and GoldenApp. The Linux rebuild, no-op rebuild, and `dalvikvm -showversion`
  also pass.

Remaining Stage 0 acceptance:

- run the package on native Windows 10 build 19041+ with HSP disabled;
- force compatibility, audit, strict, context-IP-validation, and representative
  future/nonzero policy states in child processes and verify early rejection;
- prove rejected starts create no `.dmp` and execute no Java/JIT work.

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
- Stage D now enables product implicit null/SO checks after the Stage A-B page
  and Stage C adapter prerequisites are installed.

Local evidence (2026-07-26):

- Win64 `art`, `dalvikvm`, and the focused probe build with `-j32`.
- Wine reports exact 1 MiB default/explicit and exact 2 MiB reservations; the
  focused probe passes all identity/lifetime/rejection stress.
- Wine `Hello`, ThreadHeavy, every W-002 attach mode, and the complete Phase-4
  suite pass with clean process exit after the VEH/FLS findings.
- Linux rebuild and `dalvikvm -showversion` pass.

Remaining Stage A acceptance is native Windows validation of 64 KiB,
256 KiB, 1 MiB, 2 MiB, and over-8-MiB reservations, handle-count closure,
fiber rejection, and exit-before/after-join-or-detach timing. It must also
record Java's post-`FixStackSize()` reservations and representative ART pool
threads. Wine's `GetProcessHandleCount()` result is unavailable and cannot
close the native handle-lifetime proof point.

### Stage B — dormant fixed page — implemented locally

- `stack_windows.{h,cc}` separates allocation-free selection policy from
  Win32 memory operations. It preserves the lowest page and complete adjacent
  bottom no-access/guard regions, accepts only a reserved page or exact
  committed-private `PAGE_READWRITE` page, rejects malformed geometry and
  insufficient remaining stack, and supports the normal one-system-page ART
  protected size.
- `Thread` records the selection and state below the native-code-visible TLS
  layout. Non-AOT Windows attachment installs the page before publication,
  common stack accounting uses the measured excluded-low bytes plus the fixed
  page, and the Win64 bootstrap `FixStackSize()` compensation preserves the
  requested stack budget.
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
  mode/repeat processes. Win64 Hello, the complete Phase-4 Wine suite, the
  Linux full rebuild, `dalvikvm -showversion`, and shared-boot imageless Hello
  remain green with the Windows-only state below native-visible TLS offsets.

Local completion criteria are met. Native A-B acceptance still must capture
real Windows bottom layouts, small/default/large reservations, guard growth,
reserved-page restoration, stack budgets, and detach/reattach behavior. That
evidence belongs to Stage E and is not implied by Wine.

### Stage C — initially dormant W-010 adapter — implemented locally (2026-07-27)

- `sigchain_windows.cc` now owns the special-action facade and managed VEH
  registration, promotion, publication, and removal lifecycle. Unsupported
  signals fail clearly instead of disappearing in a stub.
- `fault_handler_windows.h` defines the non-owning real-`CONTEXT` view and the
  documented read/write access constants without leaking Windows SDK types to
  common headers.
- The x86_64 handler reads and writes `CONTEXT.Rip`/`Rsp`/`Rax` in place,
  preserves the Win64 `R15 == Thread*` managed-self invariant, rejects nested
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

### Stage D — atomic product activation — implemented locally (2026-07-27)

- Win64 x86_64 enables common implicit null and stack-overflow flags while
  leaving implicit suspend checks off.
- `FaultManager` registers stack before null, preserving Linux handler order.
- Nterp's immutable code range is registered before startup publishes nterp
  entrypoints even though Win64 deliberately keeps `CanRuntimeUseNterp()`
  false during early initialization. JIT code-cache ranges retain the common
  registration path.
- The main thread's W-014 page is installed before the capability is
  published; later non-AOT attachments install it under the enabled implicit
  stack-check flag. Installation failure rejects attachment/startup.
- The Windows exception to the normal started-runtime sigchain invariant is
  removed. Active runners no longer pass `-Xno-sig-chain`; one focused
  negative case proves started-runtime rejection.
- `W010ManagedFaultProbe` passes nterp and threshold-zero JIT modes for 64
  caught read NPEs, 64 caught write NPEs, two caught main-thread SOEs, and two
  caught child-thread SOEs. The JIT runs prove compilation of the faulting
  caller/recursive methods. Handled faults emit no diagnostic VEH/UEF marker
  and do not change `run/crash/*.dmp`.
- Unmanaged native AV still reaches fatal diagnostics. The full Phase-4 Wine
  aggregate, Win64 build, Linux full `art`/`dalvikvm` rebuild,
  `dalvikvm -showversion`, and shared-boot imageless Hello all pass.

### Stage E — native acceptance and cleanup

- Run the complete matrix below on Windows 10 build 17134+ and a current
  Windows release.
- Keep Wine as a development oracle and Linux as the behavior oracle.
- Remove obsolete diagnostic branches and update W-010/W-014 state only after
  accepted native evidence.

## 13. Required verification matrix

### 13.1 CET/HSP process policy

- Structural link-command check proves every Win64 PE link explicitly includes
  `/CETCOMPAT:NO`.
- `llvm-readobj --coff-debug-directory` or an equivalent PE parser proves
  `dalvikvm.exe`, `art.dll`, `sigchain.dll`, LLVM libc++, quick/JIT support
  DLLs, probe executables, and packaged copies omit
  `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT`.
- Native Windows with Hardware-enforced Stack Protection disabled starts and
  reaches the ordinary product gates.
- Forced compatibility, audit, and strict policies each fail during early
  startup with the documented diagnostic, before a Java method or JIT worker
  runs.
- Rejection does not produce a `.dmp` and does not depend on
  `STATUS_CONTROL_PROTECTION_VIOLATION` as the detection mechanism.
- CFG-on tests remain a separate W-025 matrix and must not change this expected
  CET rejection behavior.

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

- Nterp implicit invoke-null path that currently fails.
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
- Exact read-operation, `fault == rsp - 8192`, and protected-page containment
  records.
- Deliberate generated-code AV with the wrong address remains unhandled.
- Handler and pre-unprotect stack high-water measurements.

### 13.5 Chain and fatal diagnostics

- Foreign VEH registered before ART, after ART, and promoted by
  `EnsureFrontOfChain()`.
- Foreign handlers returning search preserve ART behavior.
- An unrecognized AV reaches a frame-based SEH handler.
- Debugger first-chance stop followed by continue reaches the Java exception.
- Handled NPE/SOE produces no first-chance dump and no `.dmp`.
- Unhandled native AV produces the expected UEF/minidump and calls the previous
  UEF.
- `EXCEPTION_GUARD_PAGE`, `EXCEPTION_STACK_OVERFLOW`, breakpoint, single-step,
  illegal-instruction, and execute AV are not consumed by ART's managed VEH.
- Runtime shutdown removes the VEH before `art.dll` can unload.

### 13.6 Cross-platform regression

- Linux `018-stack-overflow` and implicit-null tests.
- Linux generated-code range registration/removal tests.
- Shared boot.jar byte identity remains unchanged.
- Win64 nterp/JIT ABI, XMM nonvolatile, JIT dual-view, W-002, W-003, W-004,
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
| `overlay/port_policy_windows.py`, `tools/bp2cmake`, and Win64 CMake/shell harnesses | Implemented explicit `/CETCOMPAT:NO` on every generated and handwritten executable/DLL target; static archives excluded |
| `runtime/multiplatform/windows/cet_compat.{h,cc}` | Implemented process-policy observation and fail-closed decision logic, independently probeable |
| `runtime/multiplatform/windows/sigchain_windows.cc` | Implemented ART special-SIGSEGV facade, managed VEH handle, promotion/removal, immutable action publication, recursion gate, and exact exception filter |
| `runtime/multiplatform/windows/runtime_windows.cc` | Implemented earliest CET/HSP policy rejection, separate diagnostic VEH/UEF teardown, and predecessor-preserving fatal UEF chaining |
| `runtime/multiplatform/windows/fault_handler_windows.cc` | Not required; the Stage C dispatcher remains narrow enough to live in `sigchain_windows.cc` |
| `runtime/multiplatform/windows/fault_handler_windows.h` | Windows-only non-owning context view and documented AV-kind constants; no common-header Win32 leakage |
| `runtime/arch/x86/fault_handler_x86.cc` | Win64 non-owning context view, real `CONTEXT` PC/SP/RAX access, read-only stack-fault and protected-page checks |
| `runtime/thread.cc` | Implemented exact current-stack acceptance and attach failure; later common accounting plus a small `_WIN32` fixed-page installation branch |
| `runtime/multiplatform/windows/stack_windows.{h,cc}` | Implemented Stage B selection, commit/protect state machine, verified rollback, and exact original-state restoration |
| `runtime/multiplatform/windows/thread_windows.cc` | Implemented bounded `Thread` integration for Stage B; no alternate signal stack |
| `runtime/thread_pool.cc` | Implemented no-caller-allocated-stack Windows policy; requested reservation passes through pthread attributes |
| `compat/include/pthread.h` | Implemented opaque Windows `pthread_t`, numeric-ID helper, and strict attribute contract |
| `compat/src/win64_posix_stubs.c` | Implemented `_beginthreadex`, handle/result lifetime, join/detach, tagged external identity, exact current-stack bounds, and stack attributes |
| `runtime/runtime.cc` | Implemented diagnostic handler shutdown, common implicit null/SO activation, Linux-like started-runtime sigchain invariant, and early nterp range registration |
| `tools/verify/win64_phase1/check_win32_cet_contract.py` and `win32_cet_policy_probe.cc` | Implemented link/PE audit plus deterministic and actual-policy probe |
| `tools/verify/win64_phase1/win32_thread_stack_probe.c`, `win32_stack_page_probe.cc`, `win32_stack_page_fault_probe.S`, `win32_fault_record_probe.cc`, `win32_sigchain_probe.cc`, and Phase 4 probe scripts | Implemented Stage A reservation/identity/lifetime gate, Stage B synthetic selection/restore/direct-fault gate, Stage C deterministic record/live VEH gate, and Stage D nterp/JIT managed-fault stress |

The exact split between `sigchain_windows.cc` and
`fault_handler_windows.cc` is an implementation detail. There must still be
one VEH owner and one managed dispatch path.

## 15. Open proof points

These are validation questions, not permission to improvise new product
fallbacks:

1. Which bottom-region sequences occur on supported native Windows versions
   and reservation sizes, and does the measured excluded-low selection always
   find a safe non-guard candidate without weakening the terminal page?
2. How much stack do Windows exception dispatch, the ART VEH, the quick throw
   stub, and the code before `UnprotectStack()` consume in release and debug
   builds?
3. Does committing the dynamically selected page leave ordinary moving-guard
   growth intact for small, default, and large reservations?
4. Native Windows must confirm the locally passing external detach, continued
   native stack use, reattach, and second-detach path remains safe after real
   guard movement and deep managed recursion. If it does not, the supported
   contract must require attachment until thread exit.
5. Does a security product or debugger used in acceptance install a first VEH
   that consumes expected AVs? If so, this is an embedding compatibility issue,
   not a reason to weaken ART's classifier.
6. Is PE unwind metadata required for useful fatal minidumps through the two
   quick exception trampolines? It is not required merely to return
   `EXCEPTION_CONTINUE_EXECUTION` with a modified context while CET user shadow
   stacks are disabled. It cannot be used to infer CET compatibility.

## 16. Primary references and comparative implementation

Microsoft contracts:

- [`AddVectoredExceptionHandler`](https://learn.microsoft.com/windows/win32/api/errhandlingapi/nf-errhandlingapi-addvectoredexceptionhandler)
- [Vectored exception handling](https://learn.microsoft.com/windows/win32/debug/vectored-exception-handling)
- [`PVECTORED_EXCEPTION_HANDLER`](https://learn.microsoft.com/windows/win32/api/winnt/nc-winnt-pvectored_exception_handler)
- [`EXCEPTION_RECORD`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-exception_record)
- [Win64 `CONTEXT`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-context)
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
- [`SetThreadStackGuarantee`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-setthreadstackguarantee)
- [`PROCESS_MITIGATION_USER_SHADOW_STACK_POLICY`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-process_mitigation_user_shadow_stack_policy)
- [`GetProcessMitigationPolicy`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocessmitigationpolicy)
- [`/CETCOMPAT`](https://learn.microsoft.com/cpp/build/reference/cetcompat)

Comparative implementation:

- [OpenJDK HotSpot Windows OS layer](https://github.com/openjdk/jdk/blob/master/src/hotspot/os/windows/os_windows.cpp)
  uses `_beginthreadex` with reservation semantics, a first VEH, direct
  `EXCEPTION_POINTERS` context redirection, separate access-violation and
  native-stack-overflow handling, and previous-UEF chaining. It is supporting
  evidence for the Windows mechanisms, not a replacement for ART's own frame
  and exception invariants.

## 17. Final design principle

The Windows port should not make generated ART code "Windows-aware" for faults
unless Windows proves that unavoidable. It should make Windows exception and
stack services present the same narrow facts that Linux ART already expects:

```text
validated current Thread
+ validated generated PC
+ exact fault address
+ mutable saved PC/SP
+ fixed repeatable protected page
= existing ART managed exception path
```

That boundary keeps the platform difference explicit without forking the
managed runtime.
