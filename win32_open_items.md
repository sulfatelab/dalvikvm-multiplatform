# Win32 / multiplatform — open items & temporary workarounds

**Status:** living tracker  
**Created:** 2026-07-17  
**Updated:** 2026-07-26
**Rule:** Every **temporary workaround** that future work must remove belongs here as **OPEN**.  
When the proper fix lands, mark the item **CLOSED**, move it into §Closed (sorted), and keep the full history.  
Do **not** list permanent non-goals as OPEN workarounds—list them under §Non-goals.

### Related docs

| Doc | Role |
|-----|------|
| [win64_art_port.md](win64_art_port.md) | Product phases / feasibility |
| [win32_filesystem.md](win32_filesystem.md) | Option H path model |
| [win32_faults_and_stacks.md](win32_faults_and_stacks.md) | Authoritative coupled W-010/W-014 managed-fault, VEH-chain, pthread, and ART stack design |
| [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) | Implemented x86_64 TLS / managed ABI / quick / nterp / JIT contract plus cross-ISA design record |
| [win32_jit_memory.md](win32_jit_memory.md) | JIT memory contract, historical separated-view diagnosis, and implemented Windows 10 pagefile-section design |
| [win32_heap_memory.md](win32_heap_memory.md) | W-013 heap / embedded-dlmalloc ownership, low-address, and MoreCore target design |
| [win32_libcore_os_natives.md](win32_libcore_os_natives.md) | Os/`Linux` natives: Implemented / Needed / ENOSYS |
| `tools/verify/win64_phase*/RESULT.md` | Gate evidence |

---

## How to maintain

**Add** when you land a temporary path (compile stub, force-interpreter, fake DLL name, wine-only gate, etc.):

```markdown
### W-XXX — short title
- **State:** OPEN
- **Kind:** workaround | leftover | debt | host-gap
- **Area:** art | libcore-stub | icu | packaging | linux-host | docs | …
- **Symptom / why:** …
- **Current behavior:** …
- **Proper fix:** …
- **Code anchors:** `path:line` or symbol names
- **Blocked on / design doc:** …
- **Opened:** YYYY-MM-DD
```

**Close** when fixed:

```markdown
- **State:** CLOSED (YYYY-MM-DD) — one-line how
```

Then **move the full item** into §Closed (keep history; sort by ID prefix then number). Do not leave CLOSED bodies under Temporary workarounds / leftovers / host / design.

IDs: `W-` workaround, `L-` leftover/product gap, `H-` host/validation gap, `D-` docs/process. Numbers are stable; do not reuse.

---

## Snapshot (2026-07-26)

| Bucket | Summary |
|--------|---------|
| Phases 0–3 | **Gate-complete** (P3 G12 real Win10 + wine) |
| Phase 4 | **Wine complete**; host re-run still recommended |
| PE libcore/ICU/openjdk | **Product-default real PE** (icu/javacore/openjdk); NIO.2 non-goal; NetProbe OK |
| Quick/JIT/TLS | **Managed and native JIT ON with the corrected dual view by default:** rSELF=r15; nterp N-1 default ON; D-1 complete (37/37 Thread sites); W-002 CLOSED after native R2 passes 21/21 records; W-003 CLOSED after native R1 passes 19/19 records with 8/8 frame attribution and 6/6 XMM sentinel; JIT smoke 12/12; JIT matrix 14/14; W-004 direct Runtime singleton load native-accepted; compile records opt-in |
| Memory | One unnamed pagefile section is mapped as a contiguous low R/RX primary view plus a full RW alias; J-1 remains only as the temporary `ART_WIN64_JIT_DUAL=0` diagnostic opt-out |
| Heap memory | **W-013 CLOSED:** explicit MoreCore-only dlmalloc, direct mspace owners, constrained `VirtualAlloc2`, page-state operations, Linux-like metadata placement, and native R2 pressure/JIT/repeated-start acceptance PASS |
| Threads / managed faults | **W-014 OPEN:** stack bounds are still clamped `VirtualQuery` estimates, pthread stack attributes are ignored, and ART stack protection is disabled. **W-010 OPEN:** Stage 0 now explicitly marks every project PE `/CETCOMPAT:NO` and rejects active/nonzero HSP policy before memory/thread/JIT startup, but the VEH remains diagnostic-only, so nterp/JIT implicit faults still do not become managed Java exceptions. Native HSP compatibility/audit/strict rejection evidence remains pending. |
| Linux multiplatform | Native build and L-005 imageless Hello PASS using the exact Win64-staged shared multipath `boot.jar` bytes |

---

## Temporary workarounds (must be removed later)

### W-001 — Force interpreter invoke (quick entrypoints effectively disabled)
- **State:** CLOSED (product default uses quick invoke)
- **Kind:** workaround (removed as product default)
- **Area:** art / invoke
- **Symptom / why:** Win64 used to force interpreter invoke until quick path was smoke-validated.
- **Current behavior:** On `_WIN32`, invokable non-proxy methods use `art_quick_invoke_*` (MS entry → SysV body, rSELF=r15) by default, matching Linux. Opt-out with `ART_WIN64_QUICK_INVOKE=0` forces `EnterInterpreterFromInvoke`. Debugger/`-Xint` still force interpreter via normal ART paths.
- **Proper fix:** Done for product default. The separate Microsoft-nonvolatile XMM boundary gap was repaired and native-accepted under closed W-003; optional deletion of the env force path remains later cleanup.
- **Code anchors:** `vendor/art/runtime/art_method.cc`; `quick_entrypoints_x86_64.S` Win prologues; [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) §12b / §17.8
- **Blocked on:** n/a (default ON as of 2026-07-19)
- **Opened:** 2026-07-16 (Phase 2)
- **Updated:** 2026-07-19 — product default ON (Linux-like); opt-out `ART_WIN64_QUICK_INVOKE=0`

### W-008 — Some product smoke still passes `-Xint` / imageless / `-Xno-sig-chain`
- **State:** OPEN (partial — managed JIT suites run without `-Xint`; older product/diagnostic probes retain it)
- **Kind:** workaround (policy flags)
- **Area:** packaging / product CLI
- **Current behavior:** Product default runs with managed JIT ON through the corrected dual view. `run_jit_smoke.sh` and `run_jit_matrix.sh` deliberately omit `-Xint` and pass 12/12 and 14/14. Older Phase 3, package, crash, and generic Phase 4 runners still force `-Xint` for deterministic or interpreter-specific coverage. Product CLI (`run/dalvikvm.exe` directly) does not need `-Xint`.
- **Proper fix:** Classify each remaining `-Xint` use as intentional interpreter coverage or migrate it to the default JIT path, with `ART_WIN64_JIT=0`/`-Xint` retained only where the test specifically requires it. Imageless mode may remain until boot-image work (separate track).
- **Code anchors:** `tools/win64/host_package/package_win64_phase3.sh`, `tools/verify/win64_phase*/run_*.sh`
- **Opened:** 2026-07-16
- **Updated:** 2026-07-23 — JIT smoke and matrix run without `-Xint`; older and interpreter-specific runners still require review

### W-010 — Sigchain is a Windows stub; VEH is diagnostic-only
- **State:** OPEN (Stage 0 CET exclusion implemented locally; ART managed-fault translation is incomplete)
- **Kind:** workaround → candidate permanent design
- **Area:** art / exceptions
- **Current behavior:** `sigchain_windows.cc` is a stub. `runtime_windows.cc` installs a first-chance VEH that logs access-violation, stack, illegal-instruction, and divide faults and returns `EXCEPTION_CONTINUE_SEARCH`, plus an unhandled filter that writes a best-effort minidump. This is crash diagnostics, not ART's Linux-equivalent generated-code fault handling. In particular, nterp's implicit null load at `nterp_op_invoke_virtual+0x3a` remains an access violation instead of becoming `NullPointerException`; the failure reproduces in both instrumented and ordinary product builds.
- **Current test isolation:** W-003's attributed frame probe excludes the implicit-null subtest and documents the exclusion. It still covers class-cast, array-store, and bounds exception entrypoints. No product fallback, explicit nterp null check, or forced-interpreter workaround was added.
- **Selected design:** Windows does not emulate general POSIX sigchain. `sigchain_windows.cc` becomes the narrow facade for the one special `SIGSEGV` action registered by common `FaultManager`; a first ART VEH filters exact continuable `EXCEPTION_ACCESS_VIOLATION` records, passes a minimal `siginfo_t` plus a non-owning view of the real Win64 `CONTEXT` and AV access kind into the existing generated-code handlers, and returns search for every unrecognized exception. The x86_64 adapter modifies `CONTEXT.Rip`/`Rsp` in place, preserves R15/rSELF, keeps stack-before-null handler order, and strengthens stack recognition with read-operation and containment checks against W-014's recorded fixed page. Win64 x86_64 implicit suspend checks are not part of this scope. Native `EXCEPTION_STACK_OVERFLOW`, moving `PAGE_GUARD`, execute AV, breakpoints, illegal instructions, and native/unregistered AVs are not converted to Java exceptions.
- **Chain / diagnostics contract:** debugger first-chance notification remains before ART as Windows documents. ART registers first and `EnsureFrontOfChain()` may best-effort promote it after JNI load, but unrecognized faults always continue to later VEH/SEH handlers. Expected implicit faults do not log or dump. Fatal UEF/minidump handling is separate and must call the previously installed UEF rather than replace host policy silently.
- **Activation:** implicit null/SO flags and Win64 nterp/JIT are one capability. Product startup must not run implicit generated code unless the VEH, handlers, and per-thread W-014 page are ready. `-Xno-sig-chain` is valid only with an explicit mode that cannot execute those implicit faults, or startup rejects the combination.
- **CET/HSP contract:** Win64 ART does not support CET user shadow stacks (Hardware-enforced Stack Protection). `art_quick_do_long_jump` restores an older regular `RSP` and executes `ret` without synchronizing CET's protected return stack, affecting ordinary managed throws, deoptimization, JNI exception delivery, and W-010 implicit throws. W-010's `CONTEXT.Rip`/`Rsp` edits also conflict with context-IP validation. Every project PE link must explicitly use `/CETCOMPAT:NO`; packaged DLLs must omit `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT`; startup must reject every nonzero `ProcessUserShadowStackPolicy` before ART threads/JIT. Compatibility, audit, and strict modes are unsupported. CFG remains separate W-025 work; `/guard:ehcont`, dynamic continuation targets, CET-compatible JIT ranges, IBT, or `-fcf-protection` are not fixes.
- **Current CET state:** Stage 0 is implemented locally. Generator policy applies `LINKER:/CETCOMPAT:NO` to every generated non-static target; nine handwritten Win64 CMake harnesses and three direct Clang/lld links use the same explicit option. `Runtime::Init()` queries `ProcessUserShadowStackPolicy` after logger selection and before `MemMap::Init()`, ART threads, nterp, or JIT. It accepts only zero flags, accepts `ERROR_INVALID_PARAMETER` only below Windows build 19041, and fails closed on nonzero/future bits or unexpected query/version failures. The structural/package gate reports five enforced host packagers, 17 PE link targets, and 45 inspected PE files with no CET-compatible marker; a synthetic CET-marked PE is rejected. The focused Wine policy probe reports build 19043, zero flags, and PASS. Native HSP-disabled startup plus forced compatibility/audit/strict/context-IP-validation rejection remain the Stage 0 acceptance blocker.
- **Required acceptance:** nterp and JIT read/write implicit-null; repeated caught NPE/SOE; exact wrong-address negative cases; foreign VEH before/after/promotion; frame-based SEH for an unrecognized AV; debugger continue; handled faults produce no dump; fatal native AV chains to UEF and produces the expected dump; stack-budget measurements before W-014 unprotects its page; HSP-disabled native startup passes while compatibility/audit/strict policies reject early without a control-protection dump.
- **Code anchors:** `vendor/art/runtime/multiplatform/windows/sigchain_windows.cc`; `runtime_windows.cc`; `runtime/fault_handler.{h,cc}`; `runtime/arch/x86/fault_handler_x86.cc`; `runtime/arch/x86_64/quick_entrypoints_x86_64.S`
- **Blocked on / design doc:** shared activation and protected-page containment with W-014; [win32_faults_and_stacks.md](win32_faults_and_stacks.md)
- **Opened:** 2026-07-16
- **Updated:** 2026-07-26 — Stage 0 build marker, early fail-closed policy guard, focused probe, PE audit, Linux regression, and complete Phase-4 Wine regression implemented; native forced-policy acceptance remains

### W-011 — Legacy expanded InterpreterJni shorty fallback
- **State:** CLOSED (2026-07-24) — upstream interpreter fallback restored after Wine and native Windows acceptance
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** ART commit `42a03f2ea0` restores `runtime/interpreter/interpreter.cc` byte-for-byte to `android-16.0.0_r4`. `ArtInterpreterToInterpreterBridge` again enforces the upstream pre-start-only native invariant; runtime-started native calls retain JNI compiler/generated entrypoints under `-Xint`, tracing, and JVMTI.
- **Shared-artifact implication:** Linux and Win64 use identical `boot.jar` dex/annotation bytes (`3cbe9a7...`), so no Windows-only boot shorty or native annotation set exists to justify this expansion.
- **Proper fix:** Complete. The interpreter file has exact upstream parity and the complete Linux/Win64 post-change matrix passes.
- **Evidence:** `tools/verify/win64_phase4/RESULT-interpreter-jni-fallback.md`; accepted native-host evidence: `tools/verify/win64_phase4/evidence/w024_host/ACCEPTANCE.md`
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc` (`InterpreterJni`, `EnterInterpreterFromInvoke`, `ArtInterpreterToInterpreterBridge`)
- **Opened:** 2026-07-16
- **Closed:** 2026-07-24 — native Windows tripwire acceptance plus final Wine/Linux regression

### W-012 — Legacy InterpreterJni direct JNI resolver
- **State:** CLOSED (2026-07-24) — `ResolveJniEntryPoint` removed with the legacy fallback expansion
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** Product and upstream fallback paths use ART's normal registered entrypoint and generated dlsym-stub policy. The Win64-only direct resolver no longer exists.
- **Proper fix:** Complete with ART commit `42a03f2ea0`.
- **Evidence:** `tools/verify/win64_phase4/RESULT-interpreter-jni-fallback.md`, `tools/verify/win64_phase4/RESULT-critical-native.md`, `tools/verify/win64_phase4/RESULT-native-abi.md`, `tools/verify/win64_phase4/evidence/w024_host/ACCEPTANCE.md`
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc`; generated JNI dlsym stubs
- **Opened:** 2026-07-16
- **Closed:** 2026-07-24 — upstream resolver behavior restored

### W-014 — Windows stack bounds, pthread stack sizes, and ART protected region

- **State:** OPEN (shared Stage 0 CET prerequisite implemented locally; W-014 stack implementation and native acceptance not started)
- **Kind:** workaround / incomplete thread-stack port
- **Area:** art / threads / compat pthread
- **Current bounds behavior:** Win `GetThreadStack()` ignores its `pthread_t`, probes a current-stack local with one `VirtualQuery()`, derives an approximate interval from `AllocationBase` and the end of that single protection region, clamps it to 256 KiB–8 MiB, fabricates 1 MiB on small/query-failure cases, and always reports a 4 KiB guard. `Thread::InitStack()` consumes this interval for explicit stack checks and stack accounting.
- **Current allocation behavior:** `Thread::CreateNativeThread()` computes the Linux-like requested stack size and passes it through `pthread_attr_setstacksize()`, but the Win pthread shim discards the entire attribute object and always calls `CreateThread(..., 0, ..., 0, ...)`. Requested Java thread sizes are therefore ignored. ART thread-pool workers also allocate and protect custom `MemMap` stacks, pass them through `pthread_attr_setstack()`, and then run on unrelated default Windows stacks because that attribute is ignored.
- **Current protection behavior:** `Thread::ProtectStack()` and `UnprotectStack()` return success without changing memory on `_WIN32`; runtime initialization forces implicit SO/null/suspend checks off. This avoids the original bad-bound heap clobber, but it is not a completed stack-overflow implementation.
- **Generated-code conflict:** x86_64 optimizing code and nterp still emit the normal unconditional `rsp - ART_STACK_OVERFLOW_GAP_x86_64` probe. With no fixed ART protected page and no managed-fault VEH translation, these probes fall through to Windows stack-growth/failure behavior instead of ART's managed `StackOverflowError` path. The switch interpreter does use explicit `Thread::stack_end_` comparisons, so bad bounds affect execution modes differently.
- **Windows 10 bounds contract:** reject `IsThreadAFiber()` first, then use `GetCurrentThreadStackLimits()` as the authoritative current-thread system-stack interval. The project baseline is Windows 10 build 17134+ and already compiles with `_WIN32_WINNT=0x0A00`, so no Windows 7 fallback or dynamic resolution is required. Validate alignment, minimum size, and current-SP containment; require `VirtualQuery(SP)` to report committed private memory with `AllocationBase == low`; then walk the complete `[low, high)` allocation and require contiguous reserved/committed regions with the same allocation base and an exact end. Use TEB `StackBase`/changing `StackLimit` only for diagnostics. Reject every fiber and any manual-stack attachment instead of inventing bounds.
- **Thread-creation contract:** use `_beginthreadex`, not raw `CreateThread`, because ART callbacks execute C/C++/UCRT code. Zero uses the executable default; non-zero `pthread_attr_t::stacksize` is passed with `STACK_SIZE_PARAM_IS_A_RESERVATION`. Disable ART's custom `pthread_attr_setstack()` thread-pool mapping on Windows and pass its requested size instead. Reject non-null custom stack addresses. Replace the current `DWORD pthread_t` plus close/reopen-by-ID join scheme with an opaque ref-counted control object that retains the real handle for joinable threads, honors detach, stores the `void*` callback result, and closes the handle exactly once. Audit numeric pthread formatting/casts and expose the immutable thread ID only through a logging/naming helper; Windows `sun.nio.ch.NativeThread` keeps its separate OS-thread-ID token.
- **ART protection contract:** retain ART's Linux-like fixed one-page protected region and 8 KiB x86_64 reserve. Preserve the lowest allocation page plus every adjacent bottom `PAGE_NOACCESS`/`PAGE_GUARD` region; select the first suitable `MEM_RESERVE` or ordinary committed-private read/write page above that measured excluded-low prefix, commit it with `VirtualAlloc(MEM_COMMIT, PAGE_READWRITE)`, and protect it with `VirtualProtect(PAGE_NOACCESS)`. Never assume `low + one page` is safe and never adopt the moving guard. Record the excluded-low size and the page address/state/original state in `Thread`; W-010 validates read-operation plus containment without `VirtualQuery()` in VEH. Unprotect/reprotect only that page. Do not use one-shot `PAGE_GUARD`, Linux `VM_GROWSDOWN` recursive touching, or stack `madvise()`.
- **Detach contract:** ART-created threads terminate after unregister and let Windows release the stack. An externally created thread that detaches and continues must have the ART page restored to its original reserved/committed state before its `Thread` is deleted; otherwise the supported fallback is attachment-until-thread-exit, not a silently retained no-access page.
- **W-010 ownership boundary:** W-014 owns bounds, `_beginthreadex` reservation and pthread lifetime, stack accounting, fixed-page state, and detach restoration. W-010 owns VEH/context adaptation, exact generated-code classification, `RSP - reserved_bytes` plus page-containment validation, and quick-entrypoint redirection. The recognized VEH path remains non-allocating and small; native measurements decide whether the shared 8 KiB gap is sufficient.
- **CET boundary:** W-014's fixed page does not itself provide or repair CET support. The process-wide CET/HSP exclusion and early startup check belong to W-010's activation/build contract because ART's shared exception/deoptimization long jump is incompatible even without an implicit stack fault.
- **Wine evidence (2026-07-26):** a temporary Wine 10.0 probe found `GetCurrentThreadStackLimits()` consistent with TEB `StackBase` and `VirtualQuery(SP).AllocationBase` for 1 MiB and 2 MiB stacks. Wine represented the tested reservation as fully committed with a bottom `PAGE_NOACCESS` page followed by `PAGE_GUARD`. A requested 256 KiB reservation remained 1 MiB, so Wine cannot establish native small-stack semantics. The probe and binary were removed after analysis.
- **Required stages:** Stage 0 build/startup CET exclusion is implemented locally, with native forced-policy acceptance pending. Next: (A) fiber rejection, complete-allocation bounds helper, `_beginthreadex`, pthread handle lifetime, and thread-pool sizing; (B) measured excluded-low selection, dormant fixed-page state, and detach restoration; (C) dormant W-010 VEH/non-owning real-`CONTEXT` adapter; (D) atomic implicit-null/SO and nterp/JIT activation; (E) Wine/Linux regression plus native Windows acceptance.
- **Required acceptance:** main/default stack; Java requested versus post-`FixStackSize()` versus actual reservation; native 64 KiB/256 KiB/1 MiB/2 MiB/over-8-MiB reservations; join/detach/rapid ID-reuse stress; ART runtime/GC/JIT pools; attached `_beginthreadex` and raw `CreateThread` threads; fiber/manual-stack rejection; external detach/continue/reattach; repeated caught overflow under switch/nterp/JIT; post-overflow GC/JNI/second-overflow; moving-guard interaction; VEH/pre-unprotect stack high-water marks; Windows 10 build 17134+ and current Windows; unchanged Linux `018-stack-overflow` behavior.
- **Rejected designs:** larger clamps or fabricated fallbacks; TEB `StackLimit` as the total low bound; mechanical `mprotect` to `VirtualProtect` replacement; ART protection with `PAGE_GUARD`; relying only on `EXCEPTION_STACK_OVERFLOW`/`SetThreadStackGuarantee`; fibers to emulate arbitrary pthread stacks; Windows-specific explicit JIT/nterp checks unless the lower-divergence VEH design proves impractical.
- **Microsoft contracts:** [`IsThreadAFiber`](https://learn.microsoft.com/windows/win32/api/fibersapi/nf-fibersapi-isthreadafiber), [`GetCurrentThreadStackLimits`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentthreadstacklimits), [`_beginthreadex`](https://learn.microsoft.com/cpp/c-runtime-library/reference/beginthread-beginthreadex), [thread stack size](https://learn.microsoft.com/windows/win32/procthread/thread-stack-size), [`VirtualQuery`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualquery), [`VirtualAlloc`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc), [`VirtualFree`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualfree), [`VirtualProtect`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect), and [guard-page behavior](https://learn.microsoft.com/windows/win32/memory/creating-guard-pages).
- **Code anchors:** `vendor/art/runtime/thread.cc` (`FixStackSize`, `GetThreadStack`, `InitStack`, `InstallImplicitProtection`, `ProtectStack`, `UnprotectStack`); `vendor/art/runtime/runtime.cc` implicit-check policy; `vendor/art/runtime/thread_pool.cc`; `compat/src/win64_posix_stubs.c` pthread functions; x86_64 optimizing and nterp stack probes; Windows VEH/runtime hooks
- **Blocked on / design doc:** shared activation with W-010; [win32_faults_and_stacks.md](win32_faults_and_stacks.md) is authoritative; [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) records the managed-ABI interaction
- **Opened:** 2026-07-16
- **Updated:** 2026-07-26 — shared Stage 0 CET prerequisite implemented locally; Stage A bounds/thread-creator/pthread-lifetime work is next

### W-017 — openjdk hybrid excludes NIO.2 / async / UNIXProcess; epoll via select
- **State:** OPEN
- **Kind:** workaround / incomplete port
- **Area:** openjdk / nio
- **Current behavior:** Phase B2 builds AOSP NIO channel natives with Winsock CRT-fd shims; `epoll_*` emulated with `select`; NIO.2 UnixNativeDispatcher/WatchService/async EPollPort not registered.
- **Proper fix:** Keep NIO.2 non-goal; deepen channel/options matrix; optional IOCP epoll later if needed.
- **Code anchors:** `tools/verify/win64_libcore_icu/CMakeLists.txt` (`_OJ_SRCS` filters); `compat/src/win64_socket_posix.c`
- **Opened:** 2026-07-17

### W-024 — Restore original @CriticalNative / @FastNative surfaces after JIT/TLS/entrypoints
- **State:** CLOSED (2026-07-24) — surfaces, ABI, transitions, native-host acceptance, and cleanup complete
- **Kind:** compiler/runtime ABI repair and retired diagnostic workarounds
- **Area:** art / libcore / JNI ABI
- **Symptom / why:** Official AOSP libcore marks many natives `@CriticalNative` or `@FastNative` (Math/StrictMath were **@FastNative → @CriticalNative** in AOSP; see libcore `d021f1d8475c`). The concrete compiler/stub ABI defects, transition coverage, product demotions, native-host validation, diagnostic gate, and defensive interpreter fallbacks are now resolved:
  1. **Fixed:** the compiled-JNI adapter now keeps incoming ART-managed registers separate from outgoing Microsoft x64 native registers.
  2. **Fixed:** optimizing direct CriticalNative calls now use unified Microsoft x64 ordinals, reserve the 32-byte shadow area, and spill after it. The original W-024 repair also preserved the unresolved dlsym caller PC across the then-current PE `r11` scratch use; W-004 later removed both the helper scratch and that local reload.
  3. **Fixed/covered:** mixed-signature unresolved app-JNI CriticalNative dlsym calls now resolve through ART's native-library registry and pass with core/FP, stack-spilled, and scalar-return shapes.
  4. **Fixed/covered:** mixed/high-FP compiled normal/FastNative stubs now pass for registered and unresolved app JNI, static and instance methods, references, six managed FP ordinals, unified Win64 slots, deep stack spills, and double returns.
  5. **Fixed/covered:** already-compiled normal/FastNative thunks survive class-wide `UnregisterNatives`, dlsym re-resolution, and a second `RegisterNatives` table without recompilation.
  6. **Fixed/covered:** method tracing switches the runtime `0 -> active -> 0`; all alternate normal/FastNative bindings execute during and after tracing with no extra target compile records and no trace file left behind.
  7. **Fixed/covered:** registered and unresolved CriticalNative mixed/spilled/scalar calls pass during and after method tracing in both J-1 and dual-view modes, with tracing mode restored and no trace file left behind.
  8. **Fixed/covered:** a separate Win64 `openjdkjvmti.dll` and thread-scoped single-step agent exercise ART's real force-interpreter/deoptimization transition. Registered and unresolved normal, FastNative, and CriticalNative calls pass 3/3 in both memory modes.
  9. Interpreter JNI historically lacked full CriticalNative shorty coverage (partially papered by **W-019** for Math `DD`/`DDD`/…). That fallback was never proof of quick/direct parity and has now been removed.
  10. **Fixed:** **Math.ceil / Math.floor** are native `@CriticalNative` methods again; the pure-Java `ART-WinNT` stand-ins are removed.
  11. **Fixed:** `Math.c` uses one common ELF/PE registration table with ceil/floor included; the Windows wrappers, `_WIN32` branch, and `gMethodsWin` are removed.
- **Current behavior:**
  - Math/StrictMath/etc. annotations remain intact, and **ceil/floor are native CriticalNative methods**. An audit of local Win64 libcore commits and `ART-WinNT` markers found no other CriticalNative/FastNative Java demotion.
  - Noncompiled Java callers use ART's normal quick/critical native entrypoint plumbing. The Win64 interpreter shorty expansion and direct resolver are deleted; the interpreter file matches `android-16.0.0_r4` exactly.
  - Forced interpretation now matches Linux ART: Java callers enter the interpreter while native methods retain JNI compiler/generated entrypoints. The former Windows-only native `InterpreterJni` detour was removed; it aborted on the mixed `DJDIF` probe shorty.
  - The compiled-JNI convention split and XMM-to-XMM argument moves are implemented. The focused normal/FastNative matrix passes with 7/7 distinct JNI thunk targets compiled, exact mixed/high-FP values, and exactly seven compile records across initial, unregistered/dlsym, and re-registered bindings.
  - The default native-compilation matrix also starts and stops non-sampling method tracing. Tracing mode changes `0 -> 1 -> 0`; all normal/FastNative methods pass during and after tracing; the temporary trace file is deleted; and the target compilation record count remains seven.
  - The CriticalNative harness also traces both registered direct calls and unresolved exported-symbol calls in J-1 and dual-view modes. Exact values pass during and after tracing, mode changes `0 -> 1 -> 0`, and no trace output remains.
  - JIT compilation of native methods follows the common ART policy by default. The `ART_WIN64_JIT_NATIVE` exclusion/override is removed; calling convention, native binding, method-tracing, JVMTI forced-interpreter transitions, product surfaces, and native-host validation all pass.
  - `FloatProbe -Xjitthreshold:0` now passes repeatedly through the unresolved direct `System.currentTimeMillis()` / `System.nanoTime()` path in both J-1 and dual-view modes.
  - `CriticalNativeDlsymProbe` passes unresolved mixed core/FP, more-than-four-argument, stack-spilled, and scalar-return calls in both modes. The harness covers `System.loadLibrary`, absolute `System.load`, and a semicolon-separated public library path.
  - No threshold-zero, Math, native-JIT gate, or interpreter-JNI product workaround remains. Per-method compile records stay opt-in through `ART_WIN64_JIT_LOG_COMPILES=1`.
- **Threshold-zero investigation and resolution (2026-07-24):**
  1. `GetCriticalNativeDirectCallFrameSize("J")` correctly returned 32 on Win64, while the old optimizing direct-call visitor reported zero and emitted no `sub rsp, 32`.
  2. The dlsym stub therefore positions its 208-byte SaveRefsAndArgs frame 32 bytes too high; the walker reads caller spill data (`0x0000000100000001`) as the next `ArtMethod*`.
  3. Adding the missing 32-byte outgoing area corrected the walk and exposed the `LOAD_RUNTIME_INSTANCE` `r11` clobber, which made native return execute `Runtime*`.
  4. The final visitor and its original local `r11` reload landed together. W-004 later replaced the helper with a direct same-image data load and removed the now-unnecessary reload. The combined acceptance harness passes 5/5 threshold-zero runs in each memory mode; earlier focused repetitions also passed 10/10 in each mode.
  5. `CriticalNativeProbe` adds registered direct-call coverage for zero, FP-only, mixed integer/FP, stack-spilled arguments, and scalar returns. It passes 5/5 in each memory mode.
  6. The first unresolved mixed probe returned zeros because the old Win64 `Runtime.nativeLoad` shortcut called `LoadLibraryA` and `JNI_OnLoad` without registering the DLL in `JavaVMExt::libraries_`. `JVM_NativeLoad` now delegates to `art.dll!ART_LoadNativeLibrary` and `JavaVMExt::LoadNativeLibrary`, matching AOSP ownership.
  7. Host `OpenNativeLibrary` now recognizes Windows drive, root, and UNC absolute paths. Its internal search list intentionally remains colon-separated because `BaseDexClassLoader.getLdLibraryPath()` normalizes the platform-facing semicolon list to that ART contract.
- **Compiled-JNI / FastNative research (2026-07-24):**
  1. ART's managed x86-64 call ABI is intentionally unchanged on Windows: `RDI` carries `ArtMethod*`; Java core arguments use `RSI/RDX/RCX/R8/R9`; floating arguments use `XMM0..XMM7` with a separate FP sequence. The optimizing managed code generator still emits exactly that convention.
  2. ART commit `f87f5de9d3` correctly added the outgoing Microsoft x64 JNI convention, but its Win64 `kCoreArgumentRegisters` and `kMax*RegisterArguments` were also consumed by `X86_64ManagedRuntimeCallingConvention`. The old stub read the first Java core argument from `RDX` instead of `RSI`, permitted only three Java core register arguments after the method register, and treated managed FP arguments after `XMM3` as stack values.
  3. For `StringFactory.newStringFromBytes(byte[],int,int,int)`, managed `RSI` holds `data` and `RDX` holds `high == 0`; the bad stub reads `RDX` as `data`, producing `NullPointerException: data == null`. For `System.arraycopy(Object,int,Object,int,int)`, the same shift reads `srcPos == 0` from `RDX` as `src`, producing `src == null` or an immediate invalid-reference fault.
  4. A filtered Wine run compiled only `System.arraycopy` and then failed before the probe success marker; with the native-method gate closed, the same probe exits 0. The older Hello T5 was a false-positive because it searched for the greeting even when `main end exception=1` followed it.
  5. The managed/native register-table split is now implemented. Filtered `System.arraycopy` PerfSmoke and unrestricted native-gate-open Hello with compiled `StringFactory.newStringFromBytes` pass.
  6. The expanded probe initially failed compilation at `Move XMM: 3, XMM: 0 unimplemented`. Its first managed FP argument arrives in `XMM0` but, after the two JNI implicit arguments and a core argument, must occupy unified Win64 native slot 3 in `XMM3`. `X86_64JNIMacroAssembler::Move()` now emits `movss`/`movsd` for XMM-to-XMM moves, with a focused assembler regression test.
  7. `run_native_abi_probe.sh` now builds a dedicated PE DLL and covers registered/unresolved normal and FastNative calls, static/instance methods, references, five managed core and six managed FP ordinals, extensive stack spills, and double returns. The gate-open run compiles 7/7 distinct targets and the gate-closed control compiles 0/7; five complete focused runs passed.
  8. The expanded probe then calls `UnregisterNatives` on the compiled class, verifies dlsym phase values, installs a second six-method `RegisterNatives` table, and verifies alternate phase values. Exactly seven target compile records are permitted, proving the transitions reuse the existing compiled thunk set. Five complete transition runs passed.
  9. A third gate-open process enables method tracing through `VMDebug`, verifies tracing mode and exact values during/after tracing, deletes the trace output, and still observes exactly seven target compile records. Five complete instrumentation runs passed.
  10. The CriticalNative harness now repeats registered and unresolved mixed/spilled/scalar suites during and after method tracing in both memory modes. The default matrix passes 3/3 instrumentation runs per mode with explicit trace cleanup.
  11. The Win64 `openjdkjvmti` target builds all 29 upstream translation units as a separate plugin DLL. The JVMTI probe enables thread-scoped single-step, observes events only while enabled, and preserves exact values across registered/unresolved normal, FastNative, and CriticalNative calls in three runs per memory mode.
  12. PE cannot import C++ `thread_local` data, so optional ART plugins call an exported `Thread::CurrentFromGdb()` accessor while `art.dll` retains the direct TLS fast path. Explicit PE data annotations are limited to the zero-initialized ART runtime fields actually consumed by the plugin.
  13. Math.ceil/floor are restored to the exact pre-`f16cd44db5fe` source state. The shared Math registration table is also restored exactly; Win64 and Linux rebuild from the same source.
  14. `MathCriticalProbe` verifies native modifiers, 23 direct and reflective edge cases, signed-zero bits, 2,000 repeated calls, and source-level absence of `gMethodsWin`. It passes 3/3 in dual, J-1, and Win64 `-Xint`, plus Linux `-Xint` and threshold-zero JIT on identical boot.jar bytes.
  15. Win64 ZipProbe/HashMap and conscrypt SslProviderProbe pass after restoration; Linux ZipProbe/HashMap and L-005 pass. The Linux converter does not currently build `libjavacrypto.so`, which is a native-module packaging difference rather than a boot-jar or CriticalNative blocker.
  16. Per-method `Win64 CompileMethod done` output is now opt-in. Log-dependent harnesses explicitly set `ART_WIN64_JIT_LOG_COMPILES=1`; JIT smoke verifies a normal quiet product run.
  17. The opt-in fatal-tripwire build disabled both runtime-started `InterpreterJni` call sites. Win64 `-Xint`, direct/unresolved CriticalNative, normal/FastNative, method tracing, and JVMTI forced interpretation all passed under Wine; Clang reported `InterpreterJni` unused. The then-product-default OFF build and final controls passed before the option was retired. See `RESULT-interpreter-jni-fallback.md`.
  18. Because Linux and Win64 use identical boot.jar dex/annotation bytes, there is no Windows-only boot-native shorty set. This removed the final rationale for retaining the gate or fallback expansion; both were deleted after acceptance.
  19. The complete fatal-tripwire package passes all nine cases on Windows 10 Enterprise LTSC 2021 build 19044. Both normal/FastNative runs compile 7/7 required targets exactly once; both JVMTI runs compile the two allowed targets and no CriticalNative target; no tripwire or crash dump is observed.
- **Proper fix:**
  1. **Landed this stage:** split the JNI compiler's incoming managed convention from its outgoing native convention. The managed side remains identical to Linux ART (`RDI` method, five core Java argument registers, eight FP registers); Microsoft unified four-slot rules are used only for native destinations, out-frame sizing, and native-call scratch registers.
  2. **Landed this stage:** give the two sets of arrays and limits explicit managed/native names and add the missing XMM-to-XMM move support. The existing Win64 shadow/stack calculation now passes independent mixed FP/core and unresolved normal/Fast app-JNI coverage.
  3. **Landed this stage:** add compiled-JNI tests for static and instance methods, references, mixed core/FP ordinals, more than four total native arguments, more than four managed FP arguments, unresolved lookup, and returns. `FastNativeAbiProbe` now requires 7/7 default native compilation.
  4. **Landed this stage:** cover class-wide unregister/dlsym/re-register transitions without recompiling the already-compiled normal/FastNative targets.
  5. **Landed this stage:** cover non-sampling method-tracing entrypoint transitions for all compiled normal/FastNative targets during and after tracing, with explicit trace cleanup.
  6. **Landed this stage:** cover registered and unresolved CriticalNative calls during and after method tracing in both memory modes.
  7. **Landed this stage:** cover full JVMTI forced-interpreter transitions with thread-scoped single-step across registered/unresolved normal, FastNative, and CriticalNative calls in both memory modes.
  8. **Landed this stage:** add a Win64 branch to `CriticalNativeCallingConventionVisitorX86_64` using unified four-slot Microsoft x64 registers, a 32-byte shadow area, and stack arguments after it.
  9. **Landed this stage:** initialize the visitor stack offset with the shadow area so spilled arguments cannot overlap the home area.
  10. **Historically landed, later retired by W-004:** preserved the unresolved-stub caller PC across the old helper-based `LOAD_RUNTIME_INSTANCE` by reloading it from the existing saved return-PC slot on Windows. The direct same-image load no longer clobbers `r11`, so the reload is absent from current source.
  11. **Landed and native-host accepted:** add direct-call tests for unresolved `()J`, registered FP-only/mixed/spilled signatures, and unresolved exported mixed-signature dlsym calls.
  12. **Landed this stage:** restore **every identified** multipath Java demotion of methods originally `@CriticalNative` / `@FastNative`; Math.ceil/floor are native + `@CriticalNative` again.
  13. **Landed this stage:** re-register Math natives through one common ELF/PE table with AOSP-correct CriticalNative function pointers.
  14. **Landed:** Linux-like CriticalNative/FastNative entrypoints are the product path, the dual `gMethodsWin` table is deleted, and the PE interpreter shorty expansion is removed.
  15. **Landed this stage:** audit local Win64 libcore commits and `ART-WinNT` markers for other pure-Java / ABI demotions; none remain after Math ceil/floor restoration.
  16. **Accepted and cleaned:** both runtime-started `InterpreterJni` routes were replaced by fatal tripwires without affecting `-Xint`, tracing, or JVMTI acceptance under Wine or native Windows 10; the final source now has exact upstream fallback scope.
- **Completed exit criteria:**
  - Threshold-zero FloatProbe passes repeated J-1 and dual-view runs without a diagnostic patch.
  - Direct registered-call ABI tests cover zero, mixed, FP, stack-spilled arguments, and scalar returns.
  - Mixed-signature unresolved app-JNI CriticalNative dlsym coverage passes through both `System.loadLibrary` and absolute `System.load`.
  - `FastNativeAbiProbe` passes with 7/7 distinct normal/FastNative compiled targets, including registered/unresolved, static/instance, references, mixed FP/core, high FP ordinals, stack spills, and returns.
  - The same seven compiled targets pass class-wide unregister/dlsym/re-register transitions with exactly seven total compile records.
  - The same normal/FastNative bindings pass during and after method tracing with tracing mode restored and no trace file left behind.
  - Registered and unresolved CriticalNative suites pass during and after method tracing in both memory modes with trace cleanup.
  - Full JVMTI forced-interpreter transition coverage passes 3/3 in J-1 and dual-view modes over registered and unresolved normal, FastNative, and CriticalNative calls.
  - Math.ceil/floor are native CriticalNative methods again, and one shared registration table builds for ELF and PE.
  - Math native modifiers and edge behavior pass 3/3 dual, 3/3 J-1, 3/3 Win64 `-Xint`, Linux `-Xint`, and Linux threshold-zero JIT using identical shared boot.jar bytes.
  - Win64 Math/HashMap/conscrypt and Linux Math/HashMap/shared-boot smokes pass. Linux conscrypt is unavailable only because the converter graph has no `libjavacrypto.so` target.
  - The Wine fallback-reachability tripwire matrix passed without entering runtime-started `InterpreterJni`; the then-product-default OFF restoration and final Win64/Linux controls passed before the option was retired.
  - The native Windows 10 tripwire matrix passes all nine cases with exact required native compilation records, no fatal marker, and no crash dump.
  - ART commit `42a03f2ea0` restores upstream interpreter parity and removes the native-JIT gate.
  - The final Win64 build passes default native ABI 7/7, CriticalNative, JVMTI, Math, JIT smoke 12/12, JIT matrix 14/14, and all Phase 4 Wine gates.
  - The full Linux build passes L-005 shared-boot Hello and Math `-Xint`/JIT controls.
- **Code anchors:**
  - `vendor/art/compiler/optimizing/code_generator_x86_64.{h,cc}` (`CriticalNativeCallingConventionVisitorX86_64`, `PrepareCriticalNativeCall`)
  - `vendor/art/compiler/jni/quick/x86_64/calling_convention_x86_64.cc` (incoming managed vs outgoing native convention split)
  - `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc` and `assembler_x86_64_test.cc` (XMM-to-XMM argument moves)
  - `vendor/art/runtime/arch/x86_64/jni_frame_x86_64.h` (Win64 shadow size and direct-call frame calculation)
  - `vendor/art/runtime/arch/x86_64/jni_entrypoints_x86_64.S` (`art_jni_dlsym_lookup_critical_stub`)
  - `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S` (current direct `LOAD_RUNTIME_INSTANCE`; the Win64 `r11` scratch was retired by W-004)
  - `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc` (`ART_LoadNativeLibrary` bridge)
  - `vendor/art/libnativeloader/native_loader.cpp` (Windows absolute paths; internal colon-separated search contract)
  - `vendor/libcore/ojluni/src/main/java/java/lang/Math.java` (restored native CriticalNative ceil/floor)
  - `vendor/libcore/ojluni/src/main/native/Math.c` (one common ELF/PE registration table)
  - `vendor/art/runtime/interpreter/interpreter.cc` (exact `android-16.0.0_r4` parity)
  - `tools/verify/win64_phase4/{run_native_abi_probe.sh,src/FastNativeAbiProbe.java,native_abi/,RESULT-native-abi.md}`
  - `tools/verify/win64_phase4/{run_critical_native_probe.sh,src/CriticalNativeProbe.java,src/CriticalNativeDlsymProbe.java,critical_native/,RESULT-critical-native.md}`
  - `tools/verify/win64_phase4/{run_jvmti_force_probe.sh,src/JvmtiForceProbe.java,jvmti_force/,RESULT-jvmti-force.md}`
  - `tools/verify/win64_phase4/{run_math_critical_probe.sh,src/MathCriticalProbe.java,RESULT-math-critical.md}`
  - `tools/verify/win64_phase4/RESULT-interpreter-jni-fallback.md` (accepted Wine and native-Windows tripwire reachability audit)
  - `tools/verify/win64_phase4/W024_HOST_CHECKLIST.md` (native Windows 10 acceptance and returned-evidence procedure)
  - `vendor/art/openjdkjvmti/` and `tools/verify/win64_phase1/CMakeLists.txt` (separate Win64 JVMTI plugin)
  - `vendor/art/runtime/{thread-current-inl.h,thread.h,interpreter/interpreter_common.cc}` (PE plugin TLS accessor and Linux-like native interpreter policy)
  - `vendor/art/runtime/jit/jit.cc` (common native compilation policy and opt-in compile-record diagnostics)
  - `tools/verify/win64_libcore_icu/openjdkjvm_memory_standalone.c` (`JVM_NativeLoad` product export)
  - AOSP history: `d021f1d8475c` FastNative→CriticalNative Math; multipath `f16cd44db5fe` pure-Java ceil/floor; `b9265e7b5da6` CriticalNative register fix; art `7ea144b073` / `4c17423714` interpreter Critical/FastNative bridge
- **Closed by:** ART `42a03f2ea0`; native Windows evidence under `tools/verify/win64_phase4/evidence/w024_host/`; final Linux/Win64 regressions on 2026-07-24
- **Related:** W-019 (CLOSED temporary Math ABI fix), W-011/W-012 (legacy InterpreterJni fallback), W-025 (JIT memory; threshold-zero proved unrelated)
- **Opened:** 2026-07-17
- **Closed:** 2026-07-24 — upstream interpreter scope and default native-JIT policy restored after complete native-host and post-change regression acceptance

## Product leftovers (not single-line workarounds)

_No open product leftovers. Closed L- items live under §Closed._

## Host / validation gaps

### H-001 — Phase 4 re-run on real Windows host
- **State:** OPEN
- **Kind:** host-gap
- **Gap:** Wine Phase 4 PASS (incl. multiplatform rebuild 2026-07-17). Real Win10 Phase-4 subset (gcstress, threadheavy, handleleak, crash native/abort) not re-proven with multiplatform PE.
- **Exit criteria:** Host logs under `tools/verify/win64_phase4/evidence/host/` (or successor) OVERALL PASS.
- **Opened:** 2026-07-16

### H-002 — Phase 3 G12 with multiplatform-built PE (not only pre-migration tree)
- **State:** OPEN
- **Kind:** host-gap
- **Gap:** Authoritative G12 used earlier host package; multiplatform in-tree PE rebuild should re-package and smoke on Win10 when convenient.
- **Opened:** 2026-07-17

### H-003 — Wine is not product acceptance
- **State:** OPEN (policy reminder, not a code fix)
- **Kind:** host-gap / process
- **Note:** Keep wine as agent01 oracle; product claims need real Windows for VEH/TEB/network.
- **Opened:** 2026-07-16

---

## Non-goals (do not track as OPEN workarounds)

| Item | Decision |
|------|----------|
| Windows NIO.2 (`sun.nio.fs`) | Non-goal for now ([win32_filesystem.md](win32_filesystem.md)) |
| WSL2 / Wine as product runtime | Rejected |
| Win32 x86 product SKU | Out of scope (x64 first) |
| Full Android framework / zygote / binder | Out of scope |
| In-process dual JIT ISA (x64+Arm64EC) | Rejected in TLS/JIT draft |
| CET user shadow stacks / Hardware-enforced Stack Protection | Unsupported for current Win64 ART; must be completely disabled for the process, with compatibility/audit/strict modes rejected ([win32_faults_and_stacks.md](win32_faults_and_stacks.md)) |

If product reopens a non-goal, add an **L-** item and link the decision.

---

## Closed

Summary (details below; do not delete history):

- **W-002** — No managed GS / Thread base on Windows (2026-07-26) — r15 managed-self design, OSR adapters, and attached-thread entry accepted on native Windows R2
- **W-003** — Quick entrypoint SETUP frames and Microsoft XMM boundary (2026-07-26) — all four frame families and XMM6-XMM11 preservation accepted on native Windows R1
- **W-004** — `LOAD_RUNTIME_INSTANCE` direct PE singleton load (2026-07-25) — helper removed; direct same-image load passes structural, Wine, Linux, and native Windows acceptance
- **W-005** — Combined PE JNI stub DLL aliased as libjavacore/libopenjdk/libicu_jni (2026-07-17) — product packaging uses stage_native_modules.sh (real PE only); libcombined is legacy non-product
- **W-006** — Minimal NativeConverter / ICU version shims (not full ICU4C) (2026-07-17) — product uses real icu_jni NativeConverter + icuuc/icui18n + icudt; native_converter.c obsolete and removed from libcombined; charset stub no longer product path
- **W-007** — Classic sockets / poll via Winsock `select` (not full Os/NIO) (2026-07-17) — permanent WinNT design: classic Os sockets use Winsock + **`select()`-based poll/timeouts** (not CRT-fd `WSAPoll`)
- **W-009** — Phase-1 grade `compat` POSIX/pthread stubs (2026-07-17) — hot paths hardened; remaining ENOSYS is intentional Linux-only surface
- **W-011** — Legacy expanded InterpreterJni shorty fallback (2026-07-24) — removed after Wine and native Windows tripwire acceptance; upstream pre-start-only invariant restored
- **W-012** — Legacy InterpreterJni direct JNI resolver (2026-07-24) — removed with upstream `interpreter.cc` restoration
- **W-013** — dlmalloc WIN32 / low-4GB / MORECORE choices for imageless ART (2026-07-25) — accepted design and native Windows R2 closure matrix pass
- **W-015** — openjdkjvm memory exports minimal PE surface (2026-07-17) — product ships comprehensive standalone `libopenjdkjvm.dll`
- **W-016** — ICU needs external `ICU_DATA` / `icudt72l.dat` for wine smoke (2026-07-17) — product always stages run/icu/icudt72l.dat via tools/win64/stage_run_assets.sh (same class as boot.jar); libicu_jni defaults ICU_DATA to run/icu when unset
- **W-018** — NetProbe StructLinger NPE (getsockopt SO_LINGER incomplete in javacore Win bridge) (2026-07-17) — implemented getsockoptLinger/setsockoptLinger in win_net_natives; NetProbe wine PASS
- **W-019** — Math @CriticalNative / FastNative double ABI on Win64 (2026-07-17; superseded 2026-07-24) — historical interpreter DD/DDD workaround replaced by Linux-like entrypoints and restored native Math surface
- **W-020** — FileChannelImpl.map0 pointer truncation on Win64 (LLP64) (2026-07-17) — `ptr_to_jlong(mapAddress)` instead of `(jlong)(unsigned long)`
- **W-021** — Default KeyStore type Android-compatible (AndroidCAStore) (2026-07-17)
- **W-022** — Product default CA bundle (AndroidCAStore cacerts) (2026-07-17)
- **W-023** — OkHttp Http(s)Handler on bootclasspath + ASCII IDN/Normalizer multipath (2026-07-17)
- **W-024** — Restore original CriticalNative/FastNative surfaces (2026-07-24) — ABI, binding, tracing, JVMTI, native-host acceptance, upstream fallback cleanup, and default native JIT complete
- **L-001** — Real PE libcore / openjdk / ICU module build (2026-07-17)
- **L-002** — boringssl / conscrypt / SSL PE (2026-07-17) — product TLS stack green under wine (providers + SSLContext.init + HTTPS GET)
- **L-003** — Process/exec, rich locale, zip edge, UDP/IPv6 matrix (2026-07-17)
- **L-004** — Shrink or replace multi-name DLL staging (2026-07-17) — product ships one PE soname each: `libicu_jni`/`libjavacore`/`libopenjdk`/`libopenjdkjvm`/`libcrypto`/`libssl`/`libjavacrypto` (+ `icuuc`/`icui18n`); short-name twins removed from packaging
- **L-005** — Linux multiplatform imageless Hello / boot.jar CI gate (2026-07-17)
- **L-006** — phase1.cmake / generated Win graph pure-vendor consistency (2026-07-17)
- **D-001** — Shared boot.jar via runtime OS selection (2026-07-17)

<!-- keep full CLOSED item bodies for history -->


### W-002 — No managed GS / Thread base on Windows (`InitCpu` no-op for GS)
- **State:** CLOSED (2026-07-26) — managed-entry implementation and native Windows R2 acceptance complete
- **Kind:** resolved managed-entry ABI, TLS, OSR, and host-validation gap
- **Area:** art / TLS
- **Symptom / why:** Linux x86_64 uses `ARCH_SET_GS` so quick/nterp use `%gs:OFFSET`; Windows GS is the TEB and cannot be repurposed.
- **Current behavior:** `InitCpu` correctly leaves GS untouched. Windows managed code uses r15 as rSELF while Linux retains GS. Quick invoke and OSR boundaries publish rSELF, and nterp N-1 retains rbp as rREFS.
- **Quick OSR fix:** `art_quick_osr_stub` keeps its Microsoft-x64 C++ declaration. Its local Windows prologue converts six arguments to the shared SysV-shaped body, preserves Microsoft nonvolatile rdi/rsi/r15, and publishes the explicit `Thread*` in r15. Linux keeps its original instruction path. W-003 subsequently repaired XMM6–XMM11 preservation at this default-C++ boundary; W-002 remains closed for the accepted rSELF/OSR transition contract.
- **Nterp OSR fix:** Windows cleanup uses the `NterpFree` SysV-to-Microsoft bridge. A Windows return adapter keeps nterp's save block separate from the compiled OSR frame, then restores XMM12–XMM15 and rbx/rbp/r12–r15 after compiled code returns.
- **Attach contract:** native regular and daemon threads establish ART C++ TLS without owning caller r15. JNI invocation crosses the existing quick boundary, which preserves native r15 and publishes managed rSELF. The probe pre-JITs the Java callback and validates allocation, daemon state, exact results, detach, and `JNI_EDETACHED`.
- **Native R1:** package identity, structure, 8/8 attach, and 4/4 switch OSR passed with no fatal marker or dump. Four clean default-nterp runs missed the jump because the harness left warmup at 65535 and its 300,000-iteration loop finished before another post-compilation hotness check.
- **Deterministic R2:** every OSR runner pins warmup and optimize thresholds to 100, verifies the reported values, and runs 2,000,000 iterations with checksum `65553463744`. Unit tests, focused Wine, Phase 3/4 Wine aggregates, and Linux Hello/GC/OSR controls pass.
- **Native R2 acceptance:** Windows 10 build 19044 returns 21 PASS records and `OVERALL PASS`. All 16 children exit zero without timeout; OSR passes 8/8 across dual/J-1 and default-nterp/switch; attach passes 8/8; fatal and dump scans pass with `NO_DMP_FILES`.
- **Evidence transport note:** `/tmp/w002-r2-log.zip` omitted root `MANIFEST.json` while copying evidence. The host-side `PASS package_integrity` proves it existed and matched during the run; returned `BUILD_INFO.txt`, `SHA256SUMS.txt`, and both structural reports exactly match the issued package, and the exact returned sums record the retained manifest hash. A normalized copy adds only that byte-identical retained manifest and passes the unchanged strict reviewer. No runtime log was changed.
- **Evidence:** [RESULT-w002-managed-entry.md](tools/verify/win64_phase4/RESULT-w002-managed-entry.md), [W002_HOST_CHECKLIST.md](tools/verify/win64_phase4/W002_HOST_CHECKLIST.md), and [native acceptance](tools/verify/win64_phase4/evidence/w002_host/ACCEPTANCE.md)
- **Code anchors:** `jit.cc` `art_quick_osr_stub`; `quick_entrypoints_x86_64.S`; `mterp/x86_64ng/main.S` `NterpHotnessCheck`; `nterp.cc` `NterpFree`; `thread_x86_64.cc`; `asm_support_x86_64.S` `THREAD_*`
- **Design:** [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) §15, §17, and §17.9
- **Opened:** 2026-07-16
- **Closed:** 2026-07-26 — deterministic native R2 acceptance plus final evidence review


### W-003 — Quick entrypoint SETUP frames `int3` on Windows
- **State:** CLOSED (2026-07-26) — shared frame bodies, native-boundary XMM repair, and native Windows R1 acceptance complete
- **Kind:** resolved frame stub / latent ABI defect / validation gap
- **Area:** art / quick asm / Microsoft-to-managed boundaries
- **Historical defect:** Upstream x86-64 deliberately trapped `_WIN32` in `SETUP_SAVE_REFS_ONLY_FRAME` and `SETUP_SAVE_ALL_CALLEE_SAVES_FRAME`. `SETUP_SAVE_REFS_AND_ARGS_FRAME` and `SETUP_SAVE_EVERYTHING_FRAME` were never Windows-trapped; they already shared the non-Apple body.
- **Current frame behavior:** All four ART runtime callee-save families use the Linux-shaped frame body on Windows. Only the Thread base and Runtime singleton load differ: `THREAD_STORE_Q` addresses through r15 and `LOAD_RUNTIME_INSTANCE` uses the direct PE same-image load. Shared frame sizes and spill masks remain unchanged. Apple still traps.
- **Emitted-object finding:** With the accepted matched Linux/Win64 configuration, the quick PE and ELF objects have the same `int3` distribution: 212 functions and 401 instructions. Remaining traps are shared `UNIMPLEMENTED`/`UNREACHABLE`/read-barrier assertions, not Windows-only SETUP expansions. The checker compares the complete symbol/instruction multiset rather than hard-coding these snapshot totals.
- **Managed/helper ABI:** Quick assembly and JIT retain ART's Linux-shaped managed register convention. Assembly-called C++ helpers use `ART_QUICK_ENTRYPOINT_ABI` (`sysv_abi`) on Win64, so SETUP macros do not grow Microsoft shadow space or adopt Microsoft argument registers.
- **Native-boundary repair:** `art_quick_invoke_stub`, `art_quick_invoke_static_stub`, and `art_quick_osr_stub` reserve a Windows-only 96-byte area and preserve the lower 128 bits of XMM6–XMM11 before managed argument setup or OSR. They restore those registers before returning to the ordinary Microsoft-x64 C++ caller. XMM12–XMM15 remain covered by the ART managed convention. The area stays outside canonical ART frames, preserves alignment, and changes only the Win64 OSR conceptual CFA from 96 to 192; Linux remains 80.
- **rSELF constraint:** r15 remains the live Thread base until each frame publishes `top_quick_frame`. Runtime callee-save frames spill and restore r15 in the shared canonical slot; optimizing Win64 code separately reserves r15 rather than allocating it as a general callee-save.
- **Wine and structural evidence:** `check_w003_quick_boundaries.py` verifies all four SETUP source contracts, the three PE save/restore sequences, Linux absence of the Windows save area, and matched PE/ELF trap multisets. The opt-in frame probe is absent from product PE/ELF artifacts and passes 8/8 Wine processes; nterp and threshold-zero JIT each attribute refs-only, refs-and-args, all-callee-saves, and save-everything. The XMM sentinel passes 6/6 Wine processes and returns the exact `0x3f` intentional-clobber self-test mask.
- **Native R1 acceptance:** Windows 10 build 19044 returns exactly 19 PASS records and `OVERALL PASS`. All 14 children exit zero without timeout. The frame matrix passes 8/8; the XMM sentinel passes 6/6 with `mask=0 selfTestMask=63 iterations=128`; JIT logs confirm the corrected pagefile-section J-2 dual view and successful probe compilation; fatal and dump scans pass with `NO_DMP_FILES`. Package metadata and structural reports match the issued package byte for byte.
- **Unwind and W-010 scope:** Win64 quick assembly still emits no `.pdata`/`.xdata`; ART managed stack walking is separate. W-010 owns the exact VEH/non-owning-`CONTEXT` managed-fault adapter, cooperative VEH/SEH chaining, and the independent nterp implicit-null fault at `nterp_op_invoke_virtual+0x3a`. PE unwind metadata remains separate diagnostics hardening unless W-010 testing proves it is required for correctness. The W-003 probe excludes only that implicit-null case and retains class-cast, array-store, and bounds paths; no product fallback was added.
- **Close bar:** Satisfied: no Windows-only SETUP trap; XMM6–XMM11 preserved at ordinary Microsoft C++-to-managed boundaries; all four frame families have focused attributed Wine and native coverage; Linux frame bodies remain unchanged; and native Windows acceptance passes.
- **Evidence:** [RESULT-w003-quick-frames-analysis.md](tools/verify/win64_phase4/RESULT-w003-quick-frames-analysis.md); [RESULT-w003-frame-probe.md](tools/verify/win64_phase4/RESULT-w003-frame-probe.md); [RESULT-w003-xmm-sentinel.md](tools/verify/win64_phase4/RESULT-w003-xmm-sentinel.md); [W003_HOST_CHECKLIST.md](tools/verify/win64_phase4/W003_HOST_CHECKLIST.md); [native acceptance](tools/verify/win64_phase4/evidence/w003_host/ACCEPTANCE.md)
- **Code anchors:** `asm_support_x86_64.S`; `quick_entrypoints_x86_64.S`; `callee_save_frame_x86_64.h`; `art_method.cc`; `jit.cc`; `ART_QUICK_ENTRYPOINT_ABI` in `libartbase/base/macros.h` and quick helper declarations
- **Depends on:** W-001 and W-002 are closed prerequisites; W-004 direct Runtime load is closed. W-010 owns the managed-fault and handler-chain work defined in [win32_faults_and_stacks.md](win32_faults_and_stacks.md).
- **Opened:** 2026-07-16
- **Closed:** 2026-07-26 — native R1 19/19 acceptance plus final evidence review


### W-004 — `LOAD_RUNTIME_INSTANCE` direct PE singleton load
- **State:** CLOSED (2026-07-25) — direct same-image load accepted on native Windows 10 build 19044
- **Kind:** resolved assembly ABI debt
- **Area:** art / asm
- **Symptom / why:** The retired Windows macro crossed the Microsoft x64 C ABI merely to read `Runtime::instance_`. It mutated the stack and flags and introduced volatile-register side effects that the Linux/other-ISA data-load macros do not have. The `rcx` destination and later `r11` caller-PC collisions required path-specific repairs; generic JNI also re-materialized `xmm0` after the helper.
- **Current behavior:** Win64 directly loads `?instance_@Runtime@art@@0PEAV12@EA` with one same-image RIP-relative `movq`. The accepted RelWithDebInfo objects contain 574 direct `IMAGE_REL_AMD64_REL32` relocations (563 quick, 10 generated nterp, 1 JNI), zero retired helper references, and no helper-specific `r11` or immediate `xmm0` compensation. Linux retains its original two-instruction GOT sequence.
- **Research finding:** `Runtime::instance_` is already explicitly exported/imported by `LIBART_PROTECTED`. With the selected clang GNU driver, lld, and MSVC ABI, a quoted direct reference to `?instance_@Runtime@art@@0PEAV12@EA` assembles as `IMAGE_REL_AMD64_REL32` and links inside `art.dll` to one 7-byte RIP-relative load. Same-image ASLR preserves the displacement. External consumers keep normal `dllimport`/IAT behavior.
- **Implemented proper fix:** Replaced only the Windows macro body with the direct same-image load; deleted `art_Runtime_instance_ptr`, helper-only `Runtime::InstanceLocation()`, and the obsolete helper-specific `r11`/`xmm0` compensations. Explicit dependencies make all five assembly consumers rebuild when shared assembly support changes.
- **Verification:** Clean and incremental `-j32` builds, the structural/source/dependency gate, Phase 3/4 Wine aggregates, JIT 12/12 and 14/14, CriticalNative, normal/FastNative, JVMTI, Linux shared-boot Hello, and Linux GC stress pass. Native Windows 10 build 19044 adds 28 PASS records over 22 child processes: nterp, dual-view JIT, threshold-zero FloatProbe, dual/J-1 native ABI and JVMTI paths, GC/thread/handle stress, and ten repeated starts. Package metadata and the structural report match the issued package byte for byte; all children exit zero without timeout, fatal marker, trace leak, or dump.
- **Important scope:** Dynamically generated JIT code does not use this macro. Do not reuse this same-image RIP-relative sequence for the low-4-GiB JIT cache, which may be more than signed 32-bit reach from `art.dll`; that remains W-025 territory.
- **Rejected permanent designs:** Retaining/hardening the call helper; importing `art.dll` from itself; caching `Runtime*` in `Thread`. A stable C assembly label on the existing member remains the first fallback if maintaining the MS-mangled spelling becomes unacceptable; an exported `Runtime**` address cell is second fallback.
- **Evidence:** [RESULT-w004-runtime-load.md](tools/verify/win64_phase4/RESULT-w004-runtime-load.md), [W004_HOST_CHECKLIST.md](tools/verify/win64_phase4/W004_HOST_CHECKLIST.md), and [native acceptance](tools/verify/win64_phase4/evidence/w004_host/ACCEPTANCE.md)
- **Code anchors:** `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S` (`LOAD_RUNTIME_INSTANCE`); `tools/verify/win64_phase1/CMakeLists.txt`; `tools/verify/win64_phase1/check_w004_runtime_load.py`; `tools/win64/host_package/package_win64_w004.sh`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-25 — implementation plus structural, Wine, Linux, and native Windows acceptance complete


### W-005 — Combined PE JNI stub DLL aliased as libjavacore/libopenjdk/libicu_jni
- **State:** CLOSED (2026-07-17) — product packaging uses stage_native_modules.sh (real PE only); libcombined is legacy non-product
- **Kind:** workaround
- **Area:** libcore-stub / packaging
- **Symptom / why:** Full ojluni + ICU4C PE ports not built; ART `InitNativeMethods` still dlopens those sonames.
- **Current behavior:** `tools/win64/jni_stubs/libcombined.dll` copied to six names (`libjavacore.dll`, `libopenjdk.dll`, `libicu_jni.dll`, and short names). ~160 `Java_*` exports, hand-written (~2.3k LOC).
- **Proper fix:** Real PE modules (or fewer real DLLs) from Soong/bp2cmake Win64 graph: javacore, openjdk, icu_jni + icuuc/i18n, etc.; stop multi-name aliasing of one stub.
- **Code anchors:** `tools/win64/jni_stubs/build_combined.sh`, `tools/win64/host_package/package_win64_phase3.sh`, stage scripts in phase2 RESULT
- **Opened:** 2026-07-16 (Phase 2; expanded Phase 3)

### W-006 — Minimal NativeConverter / ICU version shims (not full ICU4C)
- **State:** CLOSED (2026-07-17) — product uses real icu_jni NativeConverter + icuuc/icui18n + icudt; native_converter.c obsolete and removed from libcombined; charset stub no longer product path
- **Kind:** workaround
- **Area:** icu
- **Current behavior:** Phase-3 package historically used `native_converter.c` stubs. **Phase A progress:** real PE `icuuc.dll` / `icui18n.dll` / `icu_jni.dll` now build from AOSP sources (`tools/verify/win64_libcore_icu/`) and can replace stub `libicu_jni` in `build/win64_phase1`. `libjavacore`/`libopenjdk` still combined stubs (may still register overlapping charset helpers until removed).
- **Proper fix:** Default package/install to real ICU PE only; remove charset exports from `libcombined`; verify full data (`ICU_DATA` / icudt) vs stubdata; complete L-001 for javacore/openjdk.
- **Code anchors:** `tools/verify/win64_libcore_icu/`, `tools/win64/jni_stubs/native_converter.c`
- **Opened:** 2026-07-16
- **Progress:** 2026-07-17 — real ICU PE + CoreProbe wine OK with hybrid package

### W-007 — Classic sockets / poll via Winsock `select` (not full Os/NIO)
- **State:** CLOSED (2026-07-17) — permanent WinNT design: classic Os sockets use Winsock + **`select()`-based poll/timeouts** (not CRT-fd `WSAPoll`)
- **Kind:** workaround → **permanent platform design**
- **Area:** libcore-stub / net
- **Symptom / why:** Full AOSP `libcore.io.Linux` PE not used on Win64; real Win10 rejected CRT `_open_osfhandle` + `WSAPoll` (`WSAEINVAL` on accept poll).
- **Fix / design:**
  - Product `libjavacore` Win bridge (`win_net_natives.c`) implements classic socket surface with **`select()`** for `poll`, SO_TIMEOUT waits, and connect write-readiness.
  - NIO epoll path similarly select-emulated in `compat/src/win64_socket_posix.c` (bounded `FD_SETSIZE`).
  - 2026-07-17: registered `bind`/`connect` **`SocketAddress`** overloads for `InetSocketAddress` (AF_UNIX still out of product scope).
  - 2026-07-25: removed `_get_osfhandle` + `SO_TYPE` fd probing. Win32 HANDLE and Winsock SOCKET values use independent namespaces and can alias numerically. The permanent design is an explicit process-wide socket-fd registry exported by the already required `libopenjdkjvm.dll`; javacore, openjdk, JVM I/O, NIO, socket/accept/socketpair, dup/dup2, and close paths share it. This is not a temporary heuristic or a disk-backed side channel.
- **Evidence:**
  - Host G12 (2026-07-16): net/dns/goldenapp PASS after select poll fix (`tools/verify/win64_phase3/evidence/host/ANALYSIS_20260716T205926.md`).
  - Wine (2026-07-17): NetProbe, DnsProbe, UdpProbe, AsyncCloseProbe, GoldenApp, **SocketAddressProbe** PASS.
  - Wine (2026-07-25): native socket/file fd-reuse probe PASS; HandleLeak 5/5; NetProbe, IoProbe, dual-view JIT 12/12, and J-1 Hello PASS.
- **Non-goals residual:** AF_UNIX SocketAddress; full AOSP `libcore_io_Linux.cpp` (L-001 closed with Win bridge map); NIO.2.
- **Code anchors:** `tools/win64/jni_stubs/win_net_natives.c`, `tools/win64/jni_stubs/win_fs_natives.c`, `register_libcore_io_Linux_win.cpp`, `compat/src/win64_socket_posix.c`, `compat/src/win64_socket_fd_registry.c`, `compat/include/mdvm_socket_fd_registry.h`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-17

### W-009 — Phase-1 grade `compat` POSIX/pthread stubs
- **State:** CLOSED (2026-07-17) — hot paths hardened; remaining ENOSYS is intentional Linux-only surface
- **Kind:** workaround → **platform compat layer** (ongoing shrink is maintenance, not open product gap)
- **Area:** compat
- **Fix / evidence:**
  - `pthread_rwlock_*` now real **SRWLOCK** shared/exclusive (was CRITICAL_SECTION exclusive-only) — ART `Mutex`/`ReaderWriterMutex` ABI rebuilt into product `art.dll`.
  - `pthread_once` now uses uninitialized/initializing/initialized states. Waiters no longer return while the winning initializer is still running; the former one-bit CAS caused intermittent null `JniConstants` field IDs during JIT-timed NetProbe socket close.
  - `uname` uses `RtlGetVersion` + computer name; `clock_gettime(CLOCK_MONOTONIC)` via QPC; `pthread_setname_np`/`getname_np` via `SetThreadDescription` when available.
  - Socket-aware `poll`/epoll already select-based (W-007); mmap/mprotect/pthread mutex/cond already real Win32.
  - Wine: `dalvikvm -showversion`, CoreProbe, NetProbe, GoldenApp PASS after ART rebuild; 32-thread `pthread_once` stress 10/10; JIT-enabled NetProbe 10/10; final JIT matrix 14/14.
- **Residual (not OPEN product work):** fork/ptrace/sendfile/tgkill etc. remain ENOSYS; further shrink only when a product path needs them.
- **Code anchors:** `compat/src/win64_posix_stubs.c`, `compat/include/pthread.h`
- **Focused result:** `tools/verify/win64_phase4/RESULT-pthread-once.md`
- **Opened:** 2026-07-16 (Phase 0/1)
- **Closed:** 2026-07-17
- **Updated:** 2026-07-24 — fixed `pthread_once` early-return race exposed by repeated JIT NetProbe

### W-013 — dlmalloc WIN32 / low-4GB / MORECORE choices for imageless ART
- **State:** CLOSED (2026-07-25) — accepted design and native Windows R2 closure matrix pass
- **Kind:** workaround removal / platform-memory design
- **Area:** art / heap
- **Symptom / why:** dlmalloc's standalone Win32 defaults forced mmap-style `VirtualAlloc` growth outside ART's arena, risking Java objects above 4 GiB. The Phase-2 recovery workaround hid `_WIN32`/`WIN32` while including `dlmalloc.c`, preserving ART MoreCore but accidentally changing unrelated platform defaults.
- **Current behavior:** `_WIN32`/`WIN32` remain visible; dlmalloc respects ART's explicit MoreCore-only, mspace-only, externally locked configuration. Each heap and JIT mspace stores its direct owner provider in `malloc_state::extp/exts`; no runtime/global owner scan remains. Windows address policy is explicit, low/aligned allocation uses `VirtualAlloc2` constraints, logical views share whole-allocation ownership, heap page-state operations route through `MemMap`, and discard handles mixed protection including `PAGE_NOACCESS`. Runtime/compiler metadata and the card table use Linux-like anywhere placement while audited object/image/heap/JIT-primary consumers remain low. Executable JIT mspace metadata updates use `ScopedCodeCacheWrite`. Full heap capacity remains initially committed.
- **Accepted design:** ART owns virtual memory; dlmalloc manages chunks inside an owner-attached ART arena. Windows-specific address, protection, discard, and release behavior stays behind `MemMap`.
- **Low-address policy:** Java object spaces, non-moving/LOS, required image/heap ranges, and the JIT primary view remain below 4 GiB. LinearAlloc, compiler/JIT metadata arenas, and the card table are unrestricted after the encoding audit. The source gate pins the remaining required-low inventory.
- **Native acceptance:** R1 on Windows 10 build 19044 found `DiscardVirtualMemory(PAGE_NOACCESS)`, J-1 RX provider-metadata writes, socket-fd namespace aliasing, blank runner accounting, and a nondeterministic marker. ART `6253d01afc` / `27a1ac74a4`, root `c943f1f` / `caad337`, and libcore `67ec4ab8dd70` repaired them. R2 from root `c909ca7` and ART `27a1ac74a4` returns 56 PASS, zero FAIL, complete metrics for 52 children, native mapping/config/owner probes, 128-MiB and 1-GiB non-moving pressure, GC/ThreadHeavy/HandleLeak, 512-MiB and 1-GiB startup, default dual-view and J-1 JIT, the fourteen-case matrix, 20/20 repeated starts, clean fatal-log scan, and `NO_DMP_FILES`.
- **Boundary / non-goal:** Fixed file-view replacement over an ordinary `VirtualAlloc` reservation remains unsupported and unused by the imageless/JIT product path. Any future placeholder-overlay or reserve-only/lazy-commit design is separate work.
- **Code anchors:** `art-dlmalloc.{h,cc}`; `dlmalloc.c` Win32 defaults and `malloc_state::extp/exts`; `dlmalloc_space.cc`; `malloc_space.cc`; `jit_memory_region.cc`; `mem_map.{h,cc}`; `mem_map_windows.cc`; `runtime.cc`
- **Design:** [win32_heap_memory.md](win32_heap_memory.md)
- **Evidence:** `tools/verify/win64_w013/RESULT.md`; `tools/verify/win64_w013/evidence/native_r2/ACCEPTANCE.md`; returned archive SHA-256 `456e297d70c2f166308c869812ddec262fa38bc6dcd2852ea56edd5b2205078e`; external dlmalloc `f3356ce`; ART `8c900a9e4b`, `d011d72d56`, `2fa301a13b`, `9ea15456a2`, `6253d01afc`, `47567cebcc`, `1509b1f95e`, `27a1ac74a4`; root `c943f1f`, `caad337`; libcore `67ec4ab8dd70`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-25 — native Windows R2 acceptance plus final evidence review

### W-015 — openjdkjvm memory exports minimal PE surface
- **State:** CLOSED (2026-07-17) — product ships comprehensive standalone `libopenjdkjvm.dll`
- **Kind:** workaround
- **Area:** art / openjdkjvm
- **Fix / evidence:**
  - Product PE from `tools/verify/win64_libcore_icu/openjdkjvm_memory_standalone.c`: memory/GC + file I/O + sockets + raw monitors + time (`JVM_*` set used by hybrid openjdk).
  - Added `JVM_ActiveProcessorCount`.
  - Product `JVM_NativeLoad` delegates to `art.dll!ART_LoadNativeLibrary`; the ART-tree helper calls `JavaVMExt::LoadNativeLibrary`, preserving ART library ownership and unresolved JNI lookup.
  - The standalone DLL remains the product soname and broad `JVM_*` surface; the ART-tree Windows file supplies ART heap/GC exports plus the narrow native-load bridge.
  - It also owns the process-wide Win64 socket-fd registry because Libcore.os creates sockets in `libjavacore` while java.net stream natives consume them in `libopenjdk`. Reusing this already required bridge avoids a new product DLL and keeps classification exact across module boundaries.
  - Wine CoreProbe/GoldenApp/NetProbe with staged `libopenjdkjvm` PASS.
- **Code anchors:** `tools/verify/win64_libcore_icu/openjdkjvm_memory_standalone.c`; stage via `stage_native_modules.sh`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-17

---

### W-016 — ICU needs external `ICU_DATA` / `icudt72l.dat` for wine smoke
- **State:** CLOSED (2026-07-17) — product always stages run/icu/icudt72l.dat via tools/win64/stage_run_assets.sh (same class as boot.jar); libicu_jni defaults ICU_DATA to run/icu when unset
- **Kind:** workaround
- **Area:** icu / packaging
- **Symptom / why:** Linked stubdata alone yields `u_init` `U_FILE_ACCESS_ERROR` under wine; full data file works.
- **Current behavior:** Stage `run/icu/icudt72l.dat` and set `ICU_DATA=run/icu` (or absolute path). `Register.cpp` also calls `udata_setCommonData(&U_ICUDATA_ENTRY_POINT)` on Win.
- **Proper fix:** Package full ICU data by default in host package scripts; verify embedded data path or always set ICU_DATA in runners.
- **Code anchors:** `vendor/icu/android_icu4j/libcore_bridge/src/native/Register.cpp`; `build/win64_phase1/run/icu/`
- **Opened:** 2026-07-17
- **Progress:** 2026-07-17 — `package_win64_phase3.sh` fails if `icudt72l.dat` missing; phase3/4 runners and install_into_phase1 default/export `ICU_DATA=run/icu`

### W-018 — NetProbe StructLinger NPE (getsockopt SO_LINGER incomplete in javacore Win bridge)
- **State:** CLOSED (2026-07-17) — implemented getsockoptLinger/setsockoptLinger in win_net_natives; NetProbe wine PASS
- **Kind:** leftover / bug
- **Area:** libcore-stub / net
- **Symptom / why:** `NetProbe` fails: `StructLinger.isOn()` on null from linger get.
- **Proper fix:** Implement linger get/set in `win_net_natives` / Linux Os bridge returning real `StructLinger`.
- **Code anchors:** `tools/win64/jni_stubs/win_net_natives.c`; NetProbe client path
- **Opened:** 2026-07-17

### W-019 — Math @CriticalNative / FastNative double ABI on Win64
- **State:** CLOSED (2026-07-17; workaround superseded 2026-07-24) — Math.ceil/floor/sqrt + HashSet wine passed after interpreter CriticalNative DD/DDD; W-024 now restores Linux-like entrypoints and the native Math surface
- **See also:** **W-024** — Math.ceil/floor and the common ELF/PE registration table are restored; the temporary interpreter shorties were subsequently deleted
- **Kind:** workaround / runtime ABI
- **Area:** libcore Math / ART interpreter JNI (Win64 -Xint)
- **Historical root cause:** Official AOSP CriticalNative is fine on Linux quick/generic-JNI. Win64 multipath formerly forced `ArtMethod::Invoke` through the interpreter; `InterpreterJniGeneric` only handled CriticalNative shorties `II`/`I`/`Z`/`ZI`. `Math.ceil` is shorty `DD` (`(D)D`), so dispatch fell through and crashed. Secondary: registering `Math_*_jni(JNIEnv*,jclass,jdouble)` under CriticalNative is the wrong ABI.
- **Historical fix:** interpreter CriticalNative `DD`/`DDD`/`FF`/`J`; `Math.c` `gMethodsWin` → `Math_ceil(jdouble)` etc.; posix stubs for the ART rebuild. W-024 removed `gMethodsWin`, restored ceil/floor native declarations, stopped routing native methods through the Windows-only interpreter detour, and finally deleted the temporary shorties.
- **Exit criteria:** `MathProbe` + `SslProviderProbe` wine PASS with rebuilt `art.dll`.
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc`, `vendor/libcore/ojluni/src/main/native/Math.c`, `compat/src/win64_posix_stubs.c`
- **Opened:** 2026-07-17
- **Progress:** 2026-07-17 — root cause + source fix; full art PE rebuild running

### W-020 — FileChannelImpl.map0 pointer truncation on Win64 (LLP64)
- **State:** CLOSED (2026-07-17) — `ptr_to_jlong(mapAddress)` instead of `(jlong)(unsigned long)`
- **Kind:** bug / ABI
- **Area:** openjdk NIO / boot classpath ZIP mmap
- **Root cause:** AOSP `FileChannelImpl_map0` returned `(jlong)(unsigned long)mapAddress`. On Win64 LLP64 `unsigned long` is 32-bit, so mapped addresses like `0x6ffff…` were truncated (high bits zeroed). `Memory.peekByteArray` then crashed in CRT (`fault_addr=0xff0e0eec` pattern) while `VMClassLoader` clinit mapped `boot.jar` for `ClassPathURLStreamHandler`.
- **Symptom chain:** `Security.getProviders` → provider class load → `BootClassLoader.loadClass` → `findLoadedClass` path / resource handlers → ZIP mmap via NIO → AV. Earlier W-019-style AV signature was coincidental.
- **Historical supporting workaround:** Win64 `-Xint` once forced natives through `InterpreterJni` and kept FastNative Runnable. W-024 removed that Windows-only branch after the real JVMTI transition passed through Linux-like JNI entrypoints; the old detour aborted on mixed shorty `DJDIF`. The temporary interpreter shorties were deleted after native-host acceptance.
- **Exit criteria:** SecStep17 `BootClassLoader.loadClass` + SecStep3 `Security.getProviders` wine PASS.
- **Code anchors:** `vendor/libcore/ojluni/src/main/native/FileChannelImpl.c`; `vendor/art/runtime/interpreter/interpreter.cc`; `interpreter_common.cc`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### W-021 — Default KeyStore type Android-compatible (AndroidCAStore)
- **State:** CLOSED (2026-07-17)
- **Kind:** config / compatibility
- **Area:** JCA / conscrypt SSL defaults
- **Root cause:** Win64 multipath deferred BouncyCastle, so `keystore.type=BKS` could not resolve. `Security.initializeStatic()` also omitted `keystore.type`, so `KeyStore.getDefaultType()` fell back to desktop `jks`, which is not registered. `KeyManagerFactory.init(null,null)` → `KeyStore.getInstance("jks")` failed and `SSLContext.init` aborted.
- **Fix:** default `keystore.type=AndroidCAStore` (HarmonyJSSE/`TrustedCertificateKeyStoreSpi`, empty-loadable); restore loading `security.properties` on Windows after W-020; mirror in `build_conscrypt_win64.sh` and boot.jar resource.
- **Exit criteria:** KeyStoreProbe + SslProviderProbe `sslcontext.init=ok` under wine.
- **Opened/Closed:** 2026-07-17

### W-022 — Product default CA bundle (AndroidCAStore cacerts)
- **State:** CLOSED (2026-07-17)
- **Kind:** packaging / product asset
- **Area:** TLS trust / AndroidCAStore
- **Root cause:** Android `TrustedCertificateStore` reads `$ANDROID_ROOT/etc/security/cacerts/<subject_hash_old>.N`. Product previously shipped empty dirs, so SSLContext.init worked but trust set was empty.
- **Fix:** generate Mozilla/system PEM bundle into OpenSSL hash_old layout (`tools/win64/generate_cacerts.sh`), hermetic assets under `tools/win64/assets/cacerts`, stage via `stage_run_assets.sh` as required asset (with `boot.jar` / `icudt72l.dat`). LocaleData hard-coded fallback so OpenSSLX509Certificate date parsing works without full ICU4J resource bundles in boot.jar.
- **Exit criteria:** TrustStoreProbe AndroidCAStore.size>=50 and acceptedIssuers>=50 under wine with ANDROID_ROOT=run.
- **Opened/Closed:** 2026-07-17

### W-023 — OkHttp Http(s)Handler on bootclasspath + ASCII IDN/Normalizer multipath
- **State:** CLOSED (2026-07-17)
- **Kind:** packaging / compatibility
- **Area:** java.net URL / HTTPS
- **Root cause:** Android resolves `http/https` via `com.android.okhttp.HttpHandler`/`HttpsHandler`, not packaged in multipath boot.jar. After packaging, pure-ASCII OkHttp/TLS paths still required ICU4J StringPrep/Normalizer tables not present in boot.jar.
- **Fix:** `tools/bootjar/build_okhttp_win64.sh` merges repackaged OkHttp+okio into boot; `IDN.toASCII` and `java.text.Normalizer` short-circuit pure-ASCII; product ICU data preferred over stub in `libicu_jni` Register.cpp; cacerts already staged.
- **Exit criteria:** HttpsProbe handler resolution + `https://example.com/` status 200 under wine.
- **Opened/Closed:** 2026-07-17

### L-001 — Real PE libcore / openjdk / ICU module build
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** build / libcore / icu
- **Gap:** ~~Win64 product still on libcombined / incomplete hybrid PE~~ **product PE from AOSP + multipath hybrids; no libcombined aliasing**.
- **Exit criteria:** PE DLLs built from AOSP sources without `libcombined` aliasing; GoldenApp + charset/locale smoke still pass. **Met.**
- **Fix / evidence:**
  - Product stages only real PE via `tools/win64/stage_native_modules.sh` (rejects `libcombined`): `libicu_jni`, `libjavacore`, `libopenjdk`, `libopenjdkjvm`, `icuuc`, `icui18n` (+ optional crypto under L-002).
  - Hybrid `libjavacore` includes AOSP Register surface + Memory, NetworkUtilities, NativeBN (`libcrypto`), ExpatParser (static `vendor/external/expat`), AsynchronousCloseMonitor, OsConstantsHolder (multipath), Win Os bridge (`win_fs`/`win_net`/register map).
  - Hybrid `libopenjdk` ships AOSP NIO/zip/fdlibm surface + `win_close` NET_* AsyncClose wrappers (NIO.2 non-goal).
  - Wine gates (2026-07-17): `GoldenApp` (golden.ok/net.ok/done), `CoreProbe` (charset=true), `LocaleProbe`, plus L-001 probes Bn/Xml/AsyncClose/OsConstants/Dns/Net/Io.
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17
- **Progress / residual (not exit blockers):**
  - Full AOSP `libcore_io_Linux.cpp` remains **excluded by design** for Win64; product Os surface is the Win bridge map ([win32_libcore_os_natives.md](win32_libcore_os_natives.md): needed=0, 82 implemented, 44 ENOSYS).
  - `cbigint` unused in graph; Linux-only `android_system_OsConstantsHolder.cpp` replaced by multipath Win TU.
  - Crypto/TLS productization tracked under **L-002**; NIO.2 non-goal.
  - Details: `tools/verify/win64_libcore_icu/RESULT.md`

### L-002 — boringssl / conscrypt / SSL PE
- **State:** CLOSED (2026-07-17) — product TLS stack green under wine (providers + SSLContext.init + HTTPS GET)
- **Kind:** leftover
- **Area:** crypto
- **Gap:** ~~Win64 TLS/crypto PE incomplete~~ **product PE + boot packaging complete for HTTPS smoke**.
- **Exit criteria:** HTTPS/crypto golden **or** explicit non-goal. **Met** (wine HttpsProbe status 200 + SslProviderProbe).
- **Fix / evidence:**
  - PE: `libcrypto` / `libssl` / `libjavacrypto` from hybrid CMake; staged single-soname product names.
  - Boot: `tools/bootjar/build_conscrypt_win64.sh` + `build_okhttp_win64.sh` → OpenSSLProvider/JSSE + OkHttp handlers + `security.properties` (AndroidCAStore).
  - Trust: product `run/etc/security/cacerts` (121 roots) via `stage_run_assets.sh`.
  - Wine (2026-07-17 reverify after ART/compat rebuild):
    - `SslProviderProbe.done=ok` (AndroidOpenSSL digests/AES-GCM/SSLContext.init)
    - `HttpsProbe.done=ok` (`https://example.com/` status 200; handlers Http/HttpsURLConnectionImpl)
- **Residual (non-exit / optional):** boringssl win-x86_64 ASM acceleration; BouncyCastle/BKS; full ICU4J IDNA tables for non-ASCII hosts; broader HTTPS golden matrix on real Win10.
- **Code anchors:** `tools/verify/win64_libcore_icu/CMakeLists.txt`; `tools/bootjar/build_conscrypt_win64.sh`; `tools/bootjar/build_okhttp_win64.sh`; `tools/win64/stage_run_assets.sh`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-003 — Process/exec, rich locale, zip edge, UDP/IPv6 matrix
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** libcore / openjdk hybrid
- **Gap:** Phase-3 product matrix for process/exec, locale (without full ICU4J bundles), zip edges, UDP IPv4, dual-stack IPv6 Os.socket bind.
- **Fix:**
  - `win_process_natives.c` CreateProcess `UNIXProcess` + openjdk OnLoad register
  - Historical Phase-3 `InterpreterJni` 12-slot workaround for multi-arg natives (`forkAndExec`, `sendtoBytes`); current product calls use JNI compiler/generated entrypoints, and W-011 removed the fallback expansion
  - UDP `recvfrom` InetSocketAddress holder fill; multicast GroupReq/IpMreqn
  - ZipFile CEN: Windows heap-read + DirectByteBuffer mirror (mmap CEN invalid under wine)
  - LocaleProbe uses Calendar/String case without ICU DecimalFormatSymbols bundles
  - Ipv6Probe: Os.socket AF_INET6 bind on raw `::` (avoid reverse-DNS hang)
  - Gate: `tools/verify/win64_phase3/run_l003_wine.sh` — OVERALL PASS
- **Exit criteria:** Process/UDP/locale/zip/IPv6 gates documented + wine green **met**.
- **Non-goals / host residual:** TCP IPv4-mapped dual-stack under wine; full ICU Collator resources; zip STORED empty-dir edges beyond DEFLATED multi-entry.
- **Code anchors:** `win_process_natives.c`, `win_net_natives.c`, `ZipFile.java` (Win CEN), `FileInputStream.c` available0, historical `interpreter.cc` 12-slot fallback, probes under `tools/verify/win64_phase3/src/`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-004 — Shrink or replace multi-name DLL staging
- **State:** CLOSED (2026-07-17) — product ships one PE soname each: `libicu_jni`/`libjavacore`/`libopenjdk`/`libopenjdkjvm`/`libcrypto`/`libssl`/`libjavacrypto` (+ `icuuc`/`icui18n`); short-name twins removed from packaging
- **Kind:** leftover / packaging debt
- **Depends on:** L-001, W-005
- **Fix:** CMake `OUTPUT_NAME` for hybrid targets; `stage_native_modules.sh` stages only product names and deletes short twins; install rejects short-name reappearance
- **Opened:** 2026-07-17

### L-005 — Linux multiplatform imageless Hello / boot.jar CI gate
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** linux-host
- **Gap:** ~~After repo migration, host Linux verified `dalvikvm -showversion` only~~ **scripted gate landed**.
- **Exit criteria:** One scripted imageless Hello (or RESULT) on multiplatform `main`.
- **Fix:** `tools/verify/linux_hello/run_imageless_hello.sh` + `RESULT.md` PASS on `build/native/dalvikvm` imageless `-Xint` Hello using the same shared multipath `boot.jar` bytes staged for Win64; ELF selects `UnixFileSystem` at runtime.
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-006 — phase1.cmake / generated Win graph pure-vendor consistency
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover / build
- **Area:** build
- **Gap:** ~~Residual MinDalvikVM-Archive path assumptions in product scripts~~ **pure-vendor**.
- **Fix / evidence:**
  - Product CMake (`tools/verify/win64_phase1`, `win64_libcore_icu`, `native/`, Linux verify) already resolved via `${MDVM_NATIVE_SRC_ROOT_DIR}` → **`vendor/`**; `phase1.cmake` has no hard-coded archive absolutes.
  - `tools/bootjar/build.sh` no longer auto-discovers sibling `MinDalvikVM-Archive(_)` for ICU/annotation stubs; requires nested `vendor/icu` + in-tree `compat/java-stubs` (expanded minimal android.annotation / android.compat.annotation set).
  - `MDVM_ARCHIVE` remains an optional non-default escape hatch only.
  - Docs/tests scrubbed: `README.md`, `native/{CMakeLists,generate}.sh`, `tools/bp2cmake` CODEGEN/codegen + unit tests point at multipath `vendor/`.
  - Historical `tools/verify/*/RESULT.md` absolute archive paths left as past evidence only (not product inputs).
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

---

### D-001 — Shared boot.jar via runtime OS selection
- **State:** CLOSED (2026-07-17)
- **Goal (actual):** **one** multipath `boot.jar` (not dual packaged jars / not “prove WinFS-on-Win and UnixFS-on-Unix” as close criteria)
- **Doc:** `archived/shared_bootjar_runtime_os_detection.md`
- **Canonical property:** `dalvik.vm.multiplatform.internal.os` = `windows` | `unix`
  - Long + `internal` intentional (not a public app API; not expected for external use)
  - Reject short `dalvik.vm.mp.os` (`mp` ambiguous)
  - Values: `windows`|`unix` (not `posix`, not `linux`) — aligns with `WinNTFileSystem` / `UnixFileSystem`
- **Injection:** `vendor/art/runtime/runtime.cc` after `PropertiesList` release (PE=`windows`, ELF=`unix` if unset)
- **Detection ladder:** `VMRuntime.properties()` → System props / `os.name` → default `unix` (`VMRuntime.isWindowsOs`)
- **Separators:** removed from `AndroidHardcodedSystemProperties`; set in `System.initUnchangeableSystemProperties`
- **Boot:** `tools/bootjar/build_win64.sh` stages shared jar (no WinNT-only overlay); jar embeds both FS + `isWindowsOs`
- **Exit criteria (met):** single shared boot pipeline produces one jar used for Linux imageless Hello (L-005 PASS on shared multipath bytes)
- **Non-goals for this close:** dual-host acceptance that Windows always selects `WinNTFileSystem` and Unix always selects `UnixFileSystem` under product PE/wine — those are ordinary product smoke, not D-001 scope
- **Follow-up (orthogonal):** wine/host Hello on same bytes; PE `art.dll` inject path when PE product is rebuilt
- **Code anchors:** `dalvik/system/VMRuntime.java` (`isWindowsOs*`), `DefaultFileSystem.java`, `System.java`, `runtime.cc`, `build_win64.sh`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

## Design notes

_No open design notes. Closed D- items live under §Closed._

## Suggested next closures (priority)

1. ~~**D-001**~~ **CLOSED** — single shared boot.jar (runtime OS selection); dual-host FS smoke is not the close bar.  
2. ~~**W-001**, **W-002**, **W-003**, **W-004**, **W-011**, **W-012**, and **W-024**~~ closed; W-003 native R1 passes 19/19 records with 8/8 frame attribution, 6/6 XMM sentinel, and clean fatal/dump scans.
3. ~~**L-001**~~ — **CLOSED** real PE libcore/openjdk/ICU hybrid; residual Linux TU/bridge growth optional.  
4. **H-001** — host Phase-4 with multiplatform package.  
5. ~~**L-005** — Linux Hello gate~~ **CLOSED**.

---

## Maintenance checklist for future PRs

- [ ] New `#ifdef _WIN32` temporary behavior → new **W-** row  
- [ ] New stub JNI → update **W-005** export scope or split **W-**  
- [ ] Gate newly green on host → close matching **H-**  
- [ ] Permanent design choice (e.g. VEH forever) → move from W- to documented architecture; close workaround  
- [ ] CLOSED items: move full item into §Closed (sorted by ID); keep State CLOSED history  


### W-025 — JIT code cache + x86_64 codegen TLS (Windows)
- **State:** OPEN (P5 implementation, Wine verification, and focused W-013/W-003 native subsets complete; broader real-Windows acceptance and residual hardening remain)
- **Kind:** host-validation gap / temporary diagnostic workaround / hardening debt
- **Area:** art / jit / compiler
- **Symptom / why:** The corrected default now reproduces ART's Linux-visible `[data R][code RX]` contiguous primary layout with a coherent RW updater alias. Remaining W-025 work is real-Windows acceptance, direct encoding-site checks, and removal of the J-1 diagnostic fallback. Threshold zero is no longer a JIT-memory unknown; its implementation work is tracked under W-024.
- **Current behavior:**
  - **Default corrected dual view:** one unnamed `CreateFileMappingW(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE)` section is mapped twice at offset zero. The complete primary view is below 4 GiB and split into data R plus code RX; the unrestricted alias is split into data RW plus code RW.
  - **Shared ART path:** mspace initialization, growth, address translation, commit, collection, and metadata handling remain on ART's common Linux/Windows path after mapping construction.
  - **Temporary J-1 diagnostic workaround:** `ART_WIN64_JIT_DUAL=0` selects the single-view `VirtualAlloc` path for comparison or emergency diagnosis. It writes code through an RX-to-RWX-to-RX transition and is not the product default.
  - **No disk file:** the section is unnamed and backed by the Windows paging system; no temporary filesystem object, pseudo-fd, or Windows memfd emulation is created.
  - **Historical separated-view defect:** the retired layout placed code far from roots and stack maps, overflowing signed 32-bit JIT-root displacements and uint32 CodeInfo distance. The corrected topology removes that layout.
  - **Threshold-zero stress:** resolved outside memory topology. The direct `@CriticalNative` path has Win64 shadow/unified-argument handling. W-024 originally added a caller-PC reload around the helper-based runtime load; W-004 subsequently replaced that helper with a direct load that does not clobber `r11` and removed the reload. Repeated J-1 and dual-view acceptance passes; W-024 is closed.
  - Native methods follow the common ART JIT policy by default. The 7/7 mixed/high-FP normal/FastNative matrix passes across rebinding and tracing; the separate CriticalNative suite passes tracing in both memory modes; the JVMTI forced-interpreter matrix passes 3/3 per mode; and restored Math CriticalNative passes dual/J-1/-Xint plus Linux controls.
- **Implemented proper fix:** Keep ART's observable layout and post-mapping JIT logic Linux-like while containing the Windows difference in the section-allocation helper:
  1. Require Windows 10 version 1803 or later and link `onecore.lib` for `MapViewOfFile3`.
  2. Create one unnamed pagefile-backed section and map the two complete views described above.
  3. Split both views logically into ART's four existing ranges without a placeholder unmap/remap transaction or Windows-only 64 KiB capacity rule.
  4. Use explicit Windows `FlushInstructionCache` and `VirtualQuery` layout/protection checks.
  5. Keep the common ART mspace and JIT lifecycle code unchanged after mapping construction.
  6. Remove the temporary `ART_WIN64_JIT_DUAL=0` opt-out after real-Windows acceptance.
- **Why full views:** Both mappings start at section offset zero, so custom JIT maximum sizes need only ART's existing page alignment. This avoids a Windows-only 64 KiB divider rule and avoids placeholder split/remap rollback.
- **Backing-store rule:** The selected section is backed by the Windows paging system, not by a named or temporary filesystem file. It can consume commit/pagefile backing, so large-capacity behavior up to 1 GiB remains an explicit test item.
- **Rejected fixes:** moving stack maps alone (does not fix root loads); Win-only far-root codegen plus an extended header; moving all method metadata into the code arena; forcing every alias below 4 GiB.
- **Safety checks:** mapping-time contiguity, low-4-GiB placement, logical sizes, and R/RX/RW protection roles are implemented. Direct signed-int32 JIT-root and uint32 CodeInfo construction checks remain open hardening.
- **Separate residual:** W-024 is closed. W-025's broader mapping, CFG/dynamic-code-policy real-host acceptance, direct-encoding hardening, and J-1 diagnostic-opt-out removal remain separate. CET user shadow-stack support is not W-025 work: it is an explicit non-goal, and the process must run with HSP disabled under W-010's activation contract.
- **Code anchors:** `mem_map_windows.cc` constrained section mapping; `mem_map.cc` Windows in-place split ownership; `jit_memory_region.cc` corrected dual-view branch and common post-mapping logic; `utils.cc` cache flush; `code_generator_x86_64.cc` `PatchJitRootUse`; `oat_quick_method_header.h` `code_info_offset_`; `jit.cc` opt-in compile records; `art-dlmalloc.cc` `USE_LOCKS=0`
- **Verified:** default corrected dual-view Hello passes with about 28–30 total successful compile records after native-JIT gate removal; JIT smoke 12/12, including default-silent compile diagnostics; JIT matrix 14/14; J-1 diagnostic Hello passes; D-1 audit complete (37/37 GS sites); threshold-zero, registered, unresolved mixed-dlsym, method-traced, and JVMTI-forced native probes pass in both memory modes; the normal/FastNative mixed/high-FP matrix compiles 7/7 targets by default and survives rebinding plus method tracing without extra target compilation; standalone section-layout probe passes coherence, execution, protection, forced low-space fragmentation, and non-64-KiB capacity cases under Wine; W-013 native R2 validates J-2 protections, metrics, pressure, and repeated starts; W-003 native R1 validates four additional threshold-zero J-2 processes with successful frame/XMM compilation and clean fatal/dump scans
- **Design:** [win32_jit_memory.md](win32_jit_memory.md) §2–§13 (Linux low-4-GiB contract, historical diagnosis, implemented Windows 10 section design, verification, and residual work)
- **Opened:** 2026-07-19
- **Updated:** 2026-07-26 — corrected pagefile-section dual view remains verified; W-013 and W-003 focused native subsets pass; temporary J-1 diagnostic opt-out, direct-encoding hardening, and broader real-Windows acceptance remain


*Last snapshot: 2026-07-26 — W-001/W-002/W-003/W-004/W-011/W-012/W-013/W-024 closed; Nterp ON; corrected pagefile-section dual view is the managed/native-JIT default (12/12 smoke, 14/14 matrix); D-1 complete; W-002 native R2 passes 21/21 records with 8/8 OSR, 8/8 attach, exact deterministic thresholds/checksum, and no fatal marker or dump; W-003 native R1 passes 19/19 records with matched PE/ELF trap parity, repaired XMM6–XMM11 invoke/OSR boundaries, 8/8 attributed frame runs, 6/6 XMM sentinel runs with exact `0x3f` self-test, explicit J-2 creation, and no fatal marker or dump; W-010 Stage 0 now has explicit `/CETCOMPAT:NO`, early fail-closed HSP policy enforcement, 45-file PE audit, and complete Wine/Linux regression while native forced-policy evidence and generated-fault translation remain open; direct CriticalNative and 7/7 mixed/high-FP normal/FastNative matrices pass unresolved dlsym, rebinding, method tracing, and JVMTI forced interpretation; W-013 native R2 passes 56/56 with complete metrics, 20/20 repeated starts, large-heap pressure, J-1/default JIT, and no dumps; Math.ceil/floor and one common ELF/PE table are restored; interpreter.cc matches upstream; compile records are opt-in; `ART_WIN64_JIT_DUAL=0` temporarily retains J-1 for diagnosis; W-025 broader real-host acceptance remains; 5 OPEN workarounds remaining.*
