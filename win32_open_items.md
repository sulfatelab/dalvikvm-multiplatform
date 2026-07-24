# Win32 / multiplatform — open items & temporary workarounds

**Status:** living tracker  
**Created:** 2026-07-17  
**Rule:** Every **temporary workaround** that future work must remove belongs here as **OPEN**.  
When the proper fix lands, mark the item **CLOSED**, move it into §Closed (sorted), and keep the full history.  
Do **not** list permanent non-goals as OPEN workarounds—list them under §Non-goals.

### Filename

| Name | Use |
|------|-----|
| **`win32_open_items.md`** (this file) | Preferred: leftovers **and** temporary workarounds |
| `win32_leftovers.md` | OK alias if you prefer |
| `win32_bug_tracker.md` | Prefer for defect IDs only; this file is broader |

### Related docs

| Doc | Role |
|-----|------|
| [win64_art_port.md](win64_art_port.md) | Product phases / feasibility |
| [win32_filesystem.md](win32_filesystem.md) | Option H path model |
| [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) | TLS / managed ABI / quick / JIT design (draft) |
| [win32_jit_memory.md](win32_jit_memory.md) | JIT memory contract, historical separated-view diagnosis, and implemented Windows 10 pagefile-section design |
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

## Snapshot (2026-07-24)

| Bucket | Summary |
|--------|---------|
| Phases 0–3 | **Gate-complete** (P3 G12 real Win10 + wine) |
| Phase 4 | **Wine complete**; host re-run still recommended |
| PE libcore/ICU/openjdk | **Product-default real PE** (icu/javacore/openjdk); NIO.2 non-goal; NetProbe OK |
| Quick/JIT/TLS | **Managed JIT ON with the corrected dual view by default:** rSELF=r15; nterp N-1 default ON; D-1 complete (37/37 Thread sites); JIT smoke 12/12; JIT matrix 14/14; native JIT gated; compile records opt-in |
| Memory | One unnamed pagefile section is mapped as a contiguous low R/RX primary view plus a full RW alias; J-1 remains only as the temporary `ART_WIN64_JIT_DUAL=0` diagnostic opt-out |
| Linux multiplatform | Native build and L-005 imageless Hello PASS using the exact Win64-staged shared multipath `boot.jar` bytes |

---

## Temporary workarounds (must be removed later)

### W-001 — Force interpreter invoke (quick entrypoints effectively disabled)
- **State:** CLOSED (product default uses quick invoke)
- **Kind:** workaround (removed as product default)
- **Area:** art / invoke
- **Symptom / why:** Win64 used to force interpreter invoke until quick path was smoke-validated.
- **Current behavior:** On `_WIN32`, invokable non-proxy methods use `art_quick_invoke_*` (MS entry → SysV body, rSELF=r15) by default, matching Linux. Opt-out with `ART_WIN64_QUICK_INVOKE=0` forces `EnterInterpreterFromInvoke`. Debugger/`-Xint` still force interpreter via normal ART paths.
- **Proper fix:** Done for product default. Residual: broader host re-run; optional delete of the env force path later.
- **Code anchors:** `vendor/art/runtime/art_method.cc`; `quick_entrypoints_x86_64.S` Win prologues; [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) §12b / §17.8
- **Blocked on:** n/a (default ON as of 2026-07-19)
- **Opened:** 2026-07-16 (Phase 2)
- **Updated:** 2026-07-19 — product default ON (Linux-like); opt-out `ART_WIN64_QUICK_INVOKE=0`

### W-002 — No managed GS / Thread base on Windows (`InitCpu` no-op for GS)
- **State:** OPEN (partial — rSELF path is product default; residual JNI attach / non-invoke entries)
- **Kind:** workaround / design debt
- **Area:** art / TLS
- **Symptom / why:** Linux x86_64 uses `ARCH_SET_GS` so quick/nterp use `%gs:OFFSET`. Windows GS is TEB.
- **Current behavior:** `InitCpu` does **not** touch GS (correct). Asm uses `THREAD_*` macros: r15 base on `_WIN32`, GS on Linux. rSELF published in `art_quick_invoke_*` (default ON). Nterp N-1 (`rREFS=rbp`) product default ON (§17.8).
- **Proper fix:** Keep **rSELF=r15**; audit remaining managed entries (JNI return, attach, trampolines) publish rSELF; then close when full matrix is green without GS.
- **Code anchors:** `thread_x86_64.cc`; `asm_support_x86_64.S` `THREAD_*`; `nterp.cc` (default ON; opt-out `ART_WIN64_NTERP=0`); design §6 / §12b / §15 / §16 / **§17** / **§17.8**
- **Opened:** 2026-07-16
- **Updated:** 2026-07-23 — D-1 complete: all 37 audited compiler/JNI/trampoline Thread sites route through `ThreadOffsetAddr` and r15 on Windows. The historical separated-J-2 FloatProbe failure was a memory-layout defect, not a residual GS/codegen audit item. Residual W-002 scope is JNI attach and other non-invoke entry publication of rSELF.
- **Design:** [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) **§15 N-1 LOCKED**, **§17** register-map lock; FS-self **§16** reject; **§17.8** defaults ON

### W-003 — Quick entrypoint SETUP frames `int3` on Windows
- **State:** OPEN (partial — SETUP_SAVE_REFS_ONLY / ALL_CALLEE_SAVES un-int3'd on Win)
- **Kind:** workaround (hard fail if other paths still stubbed)
- **Area:** art / quick asm
- **Symptom / why:** Apple still traps; Win now builds frames via shared SETUP with `THREAD_STORE` for top quick frame.
- **Current behavior:** `SETUP_SAVE_REFS_ONLY_FRAME` / `SETUP_SAVE_ALL_CALLEE_SAVES_FRAME` no longer `int3` on `_WIN32`. C++ helpers called as `sysv_abi` (`ART_QUICK_ENTRYPOINT_ABI`).
- **Proper fix:** Smoke the invoke→interpreter bridge; close when no Win SETUP path traps and product default uses quick invoke.
- **Code anchors:** `asm_support_x86_64.S`; `ART_QUICK_ENTRYPOINT_ABI` in macros + entrypoints
- **Depends on:** W-001 validation
- **Opened:** 2026-07-16
- **Updated:** 2026-07-18 — Win SETUP enabled

### W-004 — `LOAD_RUNTIME_INSTANCE` PE helper call (vs GOT)
- **State:** OPEN (acceptable interim; still temporary vs ideal PE codegen)
- **Kind:** workaround
- **Area:** art / asm
- **Current behavior:** Win path calls `art_Runtime_instance_ptr` with shadow space instead of `@GOTPCREL`.
- **Proper fix:** Keep helper **or** RIP-relative import of `Runtime::instance_` consistently for JIT + hand asm (document single sequence).
- **Code anchors:** `LOAD_RUNTIME_INSTANCE` in `asm_support_x86_64.S`
- **Opened:** 2026-07-16

### W-008 — Some product smoke still passes `-Xint` / imageless / `-Xno-sig-chain`
- **State:** OPEN (partial — managed JIT suites run without `-Xint`; older product/diagnostic probes retain it)
- **Kind:** workaround (policy flags)
- **Area:** packaging / product CLI
- **Current behavior:** Product default runs with managed JIT ON through the corrected dual view. `run_jit_smoke.sh` and `run_jit_matrix.sh` deliberately omit `-Xint` and pass 12/12 and 14/14. Older Phase 3, package, crash, and generic Phase 4 runners still force `-Xint` for deterministic or interpreter-specific coverage. Product CLI (`run/dalvikvm.exe` directly) does not need `-Xint`.
- **Proper fix:** Classify each remaining `-Xint` use as intentional interpreter coverage or migrate it to the default JIT path, with `ART_WIN64_JIT=0`/`-Xint` retained only where the test specifically requires it. Imageless mode may remain until boot-image work (separate track).
- **Code anchors:** `tools/win64/host_package/package_win64_phase3.sh`, `tools/verify/win64_phase*/run_*.sh`
- **Opened:** 2026-07-16
- **Updated:** 2026-07-23 — JIT smoke and matrix run without `-Xint`; older and interpreter-specific runners still require review

### W-010 — Sigchain is a Windows stub; VEH owns faults
- **State:** OPEN (may become permanent architecture — reclassify if so)
- **Kind:** workaround → candidate permanent design
- **Area:** art / exceptions
- **Current behavior:** `sigchain_windows.cc` stub; crash/null/SO paths use VEH + minidump in `runtime_windows.cc`.
- **Proper fix:** Document as permanent WinNT model **or** deepen VEH/sigchain integration tests; remove any code that still assumes Linux sigchain interposition.
- **Code anchors:** `vendor/art/runtime/multiplatform/windows/sigchain_windows.cc`, `runtime_windows.cc`
- **Opened:** 2026-07-16

### W-011 — Legacy expanded InterpreterJni shorty fallback
- **State:** OPEN (fallback is unreachable under Wine and native Windows 10; cleanup authorized)
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** Phase-2/3 added PE shorty cases while quick/JNI entrypoints were incomplete. Quick/JNI, compiled normal/FastNative, direct CriticalNative, method tracing, and JVMTI forced interpretation are now the product paths. The opt-in `MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE` build disables both runtime-started calls into `InterpreterJni`; Win64 `-Xint`, CriticalNative, normal/FastNative, tracing, and JVMTI suites all pass under Wine and native Windows 10, and Clang reports the fallback function unused. The option is source-scoped and OFF in product builds; packaging restores and verifies product mode automatically.
- **Shared-artifact implication:** Linux and Win64 use identical `boot.jar` dex/annotation bytes (`3cbe9a7...`), so no Windows-only boot shorty or native annotation set exists to justify this expansion.
- **Proper fix:** Restore `ArtInterpreterToInterpreterBridge` to upstream's pre-start-only invariant and reduce `InterpreterJni` to the `android-16.0.0_r4` implementation plus only independently proven PE requirements, then rerun the complete Linux/Win64 regression matrix.
- **Evidence:** `tools/verify/win64_phase4/RESULT-interpreter-jni-fallback.md`; accepted native-host evidence: `tools/verify/win64_phase4/evidence/w024_host/ACCEPTANCE.md`
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc` (`InterpreterJni`, `EnterInterpreterFromInvoke`, `ArtInterpreterToInterpreterBridge`)
- **Opened:** 2026-07-16
- **Updated:** 2026-07-24 — native Windows 10 tripwire matrix passes; cleanup is authorized

### W-012 — Legacy InterpreterJni direct JNI resolver
- **State:** OPEN (fallback-only; candidate removal with W-011)
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** `ResolveJniEntryPoint` bypasses the generated dlsym lookup stub only inside the legacy `InterpreterJni` fallback. Product unresolved normal/FastNative and CriticalNative calls use the repaired generated stubs and ART native-library registry; neither the Wine nor native-Windows tripwire audit reaches either fallback call site.
- **Proper fix:** Remove or reduce this helper together with W-011. Do not treat it as the product JNI lookup policy.
- **Evidence:** `tools/verify/win64_phase4/RESULT-interpreter-jni-fallback.md`, `tools/verify/win64_phase4/RESULT-critical-native.md`, `tools/verify/win64_phase4/RESULT-native-abi.md`, `tools/verify/win64_phase4/evidence/w024_host/ACCEPTANCE.md`
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc` (`ResolveJniEntryPoint`)
- **Opened:** 2026-07-16
- **Updated:** 2026-07-24 — native Windows acceptance passes; helper remains only pending fallback cleanup

### W-013 — dlmalloc WIN32 / low-4GB / MORECORE choices for imageless ART
- **State:** OPEN (may stay as permanent Win allocator policy)
- **Kind:** workaround / platform policy
- **Area:** art / heap
- **Current behavior:** WIN32 mmap/MORECORE path + low-4g constraints for compressed refs / imageless bring-up (see Phase-2 root-cause notes).
- **Proper fix:** Re-validate against real Win10 under load; document as permanent if correct; remove any Linux-only assumptions left in comments.
- **Code anchors:** dlmalloc Win path / Phase-2 docs in `win64_art_port.md` §9c
- **Opened:** 2026-07-16

### W-014 — Stack bounds via VirtualQuery + clamp (Wine-safe estimates)
- **State:** OPEN
- **Kind:** workaround
- **Area:** art / threads
- **Current behavior:** Win `GetThreadStack` uses VirtualQuery + clamps; ProtectStack skipped/no-op on `_WIN32` in places to avoid mprotect of wrong regions.
- **Proper fix:** TEB-accurate stack bounds + optional guard pages when trusted; re-enable protection carefully.
- **Code anchors:** `vendor/art/runtime/thread.cc` Win branch; `ProtectStack` `#ifdef _WIN32`
- **Opened:** 2026-07-16

### W-017 — openjdk hybrid excludes NIO.2 / async / UNIXProcess; epoll via select
- **State:** OPEN
- **Kind:** workaround / incomplete port
- **Area:** openjdk / nio
- **Current behavior:** Phase B2 builds AOSP NIO channel natives with Winsock CRT-fd shims; `epoll_*` emulated with `select`; NIO.2 UnixNativeDispatcher/WatchService/async EPollPort not registered.
- **Proper fix:** Keep NIO.2 non-goal; deepen channel/options matrix; optional IOCP epoll later if needed.
- **Code anchors:** `tools/verify/win64_libcore_icu/CMakeLists.txt` (`_OJ_SRCS` filters); `compat/src/win64_socket_posix.c`
- **Opened:** 2026-07-17

### W-024 — Restore original @CriticalNative / @FastNative surfaces after JIT/TLS/entrypoints
- **State:** OPEN (native-host gate complete; cleanup and post-change regressions remain)
- **Kind:** diagnostic gate / fallback cleanup
- **Area:** art / libcore / JNI ABI
- **Symptom / why:** Official AOSP libcore marks many natives `@CriticalNative` or `@FastNative` (Math/StrictMath were **@FastNative → @CriticalNative** in AOSP; see libcore `d021f1d8475c`). The concrete compiler/stub ABI defects, transition coverage, product demotions, and native-host validation are complete; Win64 still has a diagnostic native-JIT gate and defensive interpreter fallbacks:
  1. **Fixed:** the compiled-JNI adapter now keeps incoming ART-managed registers separate from outgoing Microsoft x64 native registers.
  2. **Fixed:** optimizing direct CriticalNative calls now use unified Microsoft x64 ordinals, reserve the 32-byte shadow area, spill after it, and preserve the unresolved dlsym caller PC across the PE `r11` scratch use.
  3. **Fixed/covered:** mixed-signature unresolved app-JNI CriticalNative dlsym calls now resolve through ART's native-library registry and pass with core/FP, stack-spilled, and scalar-return shapes.
  4. **Fixed/covered:** mixed/high-FP compiled normal/FastNative stubs now pass for registered and unresolved app JNI, static and instance methods, references, six managed FP ordinals, unified Win64 slots, deep stack spills, and double returns.
  5. **Fixed/covered:** already-compiled normal/FastNative thunks survive class-wide `UnregisterNatives`, dlsym re-resolution, and a second `RegisterNatives` table without recompilation.
  6. **Fixed/covered:** method tracing switches the runtime `0 -> active -> 0`; all alternate normal/FastNative bindings execute during and after tracing with no extra target compile records and no trace file left behind.
  7. **Fixed/covered:** registered and unresolved CriticalNative mixed/spilled/scalar calls pass during and after method tracing in both J-1 and dual-view modes, with tracing mode restored and no trace file left behind.
  8. **Fixed/covered:** a separate Win64 `openjdkjvmti.dll` and thread-scoped single-step agent exercise ART's real force-interpreter/deoptimization transition. Registered and unresolved normal, FastNative, and CriticalNative calls pass 3/3 in both memory modes.
  9. Interpreter JNI historically lacked full CriticalNative shorty coverage (partially papered by **W-019** for Math `DD`/`DDD`/…). This remains a fallback/workaround rather than proof of quick/direct parity.
  10. **Fixed:** **Math.ceil / Math.floor** are native `@CriticalNative` methods again; the pure-Java `ART-WinNT` stand-ins are removed.
  11. **Fixed:** `Math.c` uses one common ELF/PE registration table with ceil/floor included; the Windows wrappers, `_WIN32` branch, and `gMethodsWin` are removed.
- **Current behavior:**
  - Math/StrictMath/etc. annotations remain intact, and **ceil/floor are native CriticalNative methods**. An audit of local Win64 libcore commits and `ART-WinNT` markers found no other CriticalNative/FastNative Java demotion.
  - Noncompiled Java callers use ART's normal quick/critical native entrypoint plumbing. Interpreter CriticalNative shorty expansion remains only as defensive fallback pending deletion; it is not the product path.
  - Forced interpretation now matches Linux ART: Java callers enter the interpreter while native methods retain JNI compiler/generated entrypoints. The former Windows-only native `InterpreterJni` detour was removed; it aborted on the mixed `DJDIF` probe shorty.
  - The compiled-JNI convention split and XMM-to-XMM argument moves are implemented. The focused normal/FastNative matrix passes with 7/7 distinct JNI thunk targets compiled, exact mixed/high-FP values, and exactly seven compile records across initial, unregistered/dlsym, and re-registered bindings.
  - The gate-open matrix also starts and stops non-sampling method tracing. Tracing mode changes `0 -> 1 -> 0`; all normal/FastNative methods pass during and after tracing; the temporary trace file is deleted; and the target compilation record count remains seven.
  - The CriticalNative harness also traces both registered direct calls and unresolved exported-symbol calls in J-1 and dual-view modes. Exact values pass during and after tracing, mode changes `0 -> 1 -> 0`, and no trace output remains.
  - JIT compilation of all native methods is disabled by default. `ART_WIN64_JIT_NATIVE=1` remains an opt-in diagnostic override pending diagnostic/fallback cleanup and post-change regressions; calling convention, native binding, method-tracing, JVMTI forced-interpreter transitions, product surfaces, and native-host validation are no longer blockers.
  - `FloatProbe -Xjitthreshold:0` now passes repeatedly through the unresolved direct `System.currentTimeMillis()` / `System.nanoTime()` path in both J-1 and dual-view modes.
  - `CriticalNativeDlsymProbe` passes unresolved mixed core/FP, more-than-four-argument, stack-spilled, and scalar-return calls in both modes. The harness covers `System.loadLibrary`, absolute `System.load`, and a semicolon-separated public library path.
  - No threshold-zero or Math product workaround remains. Per-method compile records are opt-in through `ART_WIN64_JIT_LOG_COMPILES=1`. The remaining diagnostic workaround is the native-JIT opt-in gate, plus cleanup of now-redundant interpreter shorties.
- **Threshold-zero investigation and resolution (2026-07-24):**
  1. `GetCriticalNativeDirectCallFrameSize("J")` correctly returned 32 on Win64, while the old optimizing direct-call visitor reported zero and emitted no `sub rsp, 32`.
  2. The dlsym stub therefore positions its 208-byte SaveRefsAndArgs frame 32 bytes too high; the walker reads caller spill data (`0x0000000100000001`) as the next `ArtMethod*`.
  3. Adding the missing 32-byte outgoing area corrected the walk and exposed the `LOAD_RUNTIME_INSTANCE` `r11` clobber, which made native return execute `Runtime*`.
  4. The final visitor plus local `r11` reload are landed. The combined acceptance harness passes 5/5 threshold-zero runs in each memory mode; earlier focused repetitions also passed 10/10 in each mode.
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
  17. The opt-in fatal-tripwire build disables both runtime-started `InterpreterJni` call sites. Win64 `-Xint`, direct/unresolved CriticalNative, normal/FastNative, method tracing, and JVMTI forced interpretation all pass under Wine; Clang reports `InterpreterJni` unused. Product-default OFF restoration and final controls pass. See `RESULT-interpreter-jni-fallback.md`.
  18. Because Linux and Win64 use identical boot.jar dex/annotation bytes, there is no Windows-only boot-native shorty set. Remaining W-024 work is gate/fallback cleanup and post-change regression, not calling conventions, bindings, tracing, debugger/JVMTI forced interpretation, libcore demotions, compile-log noise, or native-host validation.
  19. The complete fatal-tripwire package passes all nine cases on Windows 10 Enterprise LTSC 2021 build 19044. Both normal/FastNative runs compile 7/7 required targets exactly once; both JVMTI runs compile the two allowed targets and no CriticalNative target; no tripwire or crash dump is observed.
- **Proper fix:**
  1. **Landed this stage:** split the JNI compiler's incoming managed convention from its outgoing native convention. The managed side remains identical to Linux ART (`RDI` method, five core Java argument registers, eight FP registers); Microsoft unified four-slot rules are used only for native destinations, out-frame sizing, and native-call scratch registers.
  2. **Landed this stage:** give the two sets of arrays and limits explicit managed/native names and add the missing XMM-to-XMM move support. The existing Win64 shadow/stack calculation now passes independent mixed FP/core and unresolved normal/Fast app-JNI coverage.
  3. **Landed this stage:** add compiled-JNI tests for static and instance methods, references, mixed core/FP ordinals, more than four total native arguments, more than four managed FP arguments, unresolved lookup, and returns. `FastNativeAbiProbe` is now a strict 0/7 gate-closed and 7/7 gate-open acceptance test.
  4. **Landed this stage:** cover class-wide unregister/dlsym/re-register transitions without recompiling the already-compiled normal/FastNative targets.
  5. **Landed this stage:** cover non-sampling method-tracing entrypoint transitions for all compiled normal/FastNative targets during and after tracing, with explicit trace cleanup.
  6. **Landed this stage:** cover registered and unresolved CriticalNative calls during and after method tracing in both memory modes.
  7. **Landed this stage:** cover full JVMTI forced-interpreter transitions with thread-scoped single-step across registered/unresolved normal, FastNative, and CriticalNative calls in both memory modes.
  8. **Landed this stage:** add a Win64 branch to `CriticalNativeCallingConventionVisitorX86_64` using unified four-slot Microsoft x64 registers, a 32-byte shadow area, and stack arguments after it.
  9. **Landed this stage:** initialize the visitor stack offset with the shadow area so spilled arguments cannot overlap the home area.
  10. **Landed this stage:** preserve the unresolved-stub caller PC across `LOAD_RUNTIME_INSTANCE` by reloading it from the existing saved return-PC slot on Windows.
  11. **Landed and native-host accepted:** add direct-call tests for unresolved `()J`, registered FP-only/mixed/spilled signatures, and unresolved exported mixed-signature dlsym calls.
  12. **Landed this stage:** restore **every identified** multipath Java demotion of methods originally `@CriticalNative` / `@FastNative`; Math.ceil/floor are native + `@CriticalNative` again.
  13. **Landed this stage:** re-register Math natives through one common ELF/PE table with AOSP-correct CriticalNative function pointers.
  14. **Partly landed:** Linux-like CriticalNative/FastNative entrypoints are the product path and the dual `gMethodsWin` table is deleted. Native Windows acceptance is complete; trim the now-redundant PE interpreter shorty expansion (**W-011**).
  15. **Landed this stage:** audit local Win64 libcore commits and `ART-WinNT` markers for other pure-Java / ABI demotions; none remain after Math ceil/floor restoration.
  16. **Accepted under Wine and native Windows 10:** both runtime-started `InterpreterJni` routes can be replaced by fatal tripwires without affecting `-Xint`, tracing, or JVMTI acceptance. Restore the upstream fallback scope in the cleanup stage.
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
  - The Wine fallback-reachability tripwire matrix passes without entering runtime-started `InterpreterJni`; product-default OFF restoration and final Win64/Linux controls pass.
  - The native Windows 10 tripwire matrix passes all nine cases with exact required native compilation records, no fatal marker, and no crash dump.
- **Remaining exit criteria:**
  - Remove the `ART_WIN64_JIT_NATIVE` diagnostic gate.
  - Delete or reduce the now-redundant W-019/W-011 interpreter shorty fallbacks and direct resolver.
  - Rebuild Linux and Win64 and pass the complete post-cleanup regression matrix.
- **Code anchors:**
  - `vendor/art/compiler/optimizing/code_generator_x86_64.{h,cc}` (`CriticalNativeCallingConventionVisitorX86_64`, `PrepareCriticalNativeCall`)
  - `vendor/art/compiler/jni/quick/x86_64/calling_convention_x86_64.cc` (incoming managed vs outgoing native convention split)
  - `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc` and `assembler_x86_64_test.cc` (XMM-to-XMM argument moves)
  - `vendor/art/runtime/arch/x86_64/jni_frame_x86_64.h` (Win64 shadow size and direct-call frame calculation)
  - `vendor/art/runtime/arch/x86_64/jni_entrypoints_x86_64.S` (`art_jni_dlsym_lookup_critical_stub`)
  - `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S` (`LOAD_RUNTIME_INSTANCE`, Win64 `r11` scratch)
  - `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc` (`ART_LoadNativeLibrary` bridge)
  - `vendor/art/libnativeloader/native_loader.cpp` (Windows absolute paths; internal colon-separated search contract)
  - `vendor/libcore/ojluni/src/main/java/java/lang/Math.java` (restored native CriticalNative ceil/floor)
  - `vendor/libcore/ojluni/src/main/native/Math.c` (one common ELF/PE registration table)
  - `vendor/art/runtime/interpreter/interpreter.cc` (`InterpreterJniGeneric` CriticalNative shorties)
  - `tools/verify/win64_phase4/{run_native_abi_probe.sh,src/FastNativeAbiProbe.java,native_abi/,RESULT-native-abi.md}`
  - `tools/verify/win64_phase4/{run_critical_native_probe.sh,src/CriticalNativeProbe.java,src/CriticalNativeDlsymProbe.java,critical_native/,RESULT-critical-native.md}`
  - `tools/verify/win64_phase4/{run_jvmti_force_probe.sh,src/JvmtiForceProbe.java,jvmti_force/,RESULT-jvmti-force.md}`
  - `tools/verify/win64_phase4/{run_math_critical_probe.sh,src/MathCriticalProbe.java,RESULT-math-critical.md}`
  - `tools/verify/win64_phase4/RESULT-interpreter-jni-fallback.md` (accepted Wine and native-Windows tripwire reachability audit)
  - `tools/verify/win64_phase4/W024_HOST_CHECKLIST.md` (native Windows 10 acceptance and returned-evidence procedure)
  - `vendor/art/openjdkjvmti/` and `tools/verify/win64_phase1/CMakeLists.txt` (separate Win64 JVMTI plugin)
  - `vendor/art/runtime/{thread-current-inl.h,thread.h,interpreter/interpreter_common.cc}` (PE plugin TLS accessor and Linux-like native interpreter policy)
  - `vendor/art/runtime/jit/jit.cc` (native gate and opt-in compile-record diagnostics)
  - `tools/verify/win64_libcore_icu/openjdkjvm_memory_standalone.c` (`JVM_NativeLoad` product export)
  - AOSP history: `d021f1d8475c` FastNative→CriticalNative Math; multipath `f16cd44db5fe` pure-Java ceil/floor; `b9265e7b5da6` CriticalNative register fix; art `7ea144b073` / `4c17423714` interpreter Critical/FastNative bridge
- **Next stage:** restore upstream interpreter fallback scope, remove the native-JIT gate, then rebuild and run post-change Linux/Win64 regressions
- **Related:** W-019 (CLOSED temporary Math ABI fix), W-011/W-012 (legacy InterpreterJni fallback), W-025 (JIT memory; threshold-zero proved unrelated)
- **Opened:** 2026-07-17
- **Updated:** 2026-07-24 — native Windows 10 tripwire acceptance passes all nine cases; host validation is complete and W-024 remains open only for fallback/gate cleanup and post-change regressions

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

If product reopens a non-goal, add an **L-** item and link the decision.

---

## Closed

Summary (details below; do not delete history):

- **W-005** — Combined PE JNI stub DLL aliased as libjavacore/libopenjdk/libicu_jni (2026-07-17) — product packaging uses stage_native_modules.sh (real PE only); libcombined is legacy non-product
- **W-006** — Minimal NativeConverter / ICU version shims (not full ICU4C) (2026-07-17) — product uses real icu_jni NativeConverter + icuuc/icui18n + icudt; native_converter.c obsolete and removed from libcombined; charset stub no longer product path
- **W-007** — Classic sockets / poll via Winsock `select` (not full Os/NIO) (2026-07-17) — permanent WinNT design: classic Os sockets use Winsock + **`select()`-based poll/timeouts** (not CRT-fd `WSAPoll`)
- **W-009** — Phase-1 grade `compat` POSIX/pthread stubs (2026-07-17) — hot paths hardened; remaining ENOSYS is intentional Linux-only surface
- **W-015** — openjdkjvm memory exports minimal PE surface (2026-07-17) — product ships comprehensive standalone `libopenjdkjvm.dll`
- **W-016** — ICU needs external `ICU_DATA` / `icudt72l.dat` for wine smoke (2026-07-17) — product always stages run/icu/icudt72l.dat via tools/win64/stage_run_assets.sh (same class as boot.jar); libicu_jni defaults ICU_DATA to run/icu when unset
- **W-018** — NetProbe StructLinger NPE (getsockopt SO_LINGER incomplete in javacore Win bridge) (2026-07-17) — implemented getsockoptLinger/setsockoptLinger in win_net_natives; NetProbe wine PASS
- **W-019** — Math @CriticalNative / FastNative double ABI on Win64 (2026-07-17; superseded 2026-07-24) — historical interpreter DD/DDD workaround replaced by Linux-like entrypoints and restored native Math surface
- **W-020** — FileChannelImpl.map0 pointer truncation on Win64 (LLP64) (2026-07-17) — `ptr_to_jlong(mapAddress)` instead of `(jlong)(unsigned long)`
- **W-021** — Default KeyStore type Android-compatible (AndroidCAStore) (2026-07-17)
- **W-022** — Product default CA bundle (AndroidCAStore cacerts) (2026-07-17)
- **W-023** — OkHttp Http(s)Handler on bootclasspath + ASCII IDN/Normalizer multipath (2026-07-17)
- **L-001** — Real PE libcore / openjdk / ICU module build (2026-07-17)
- **L-002** — boringssl / conscrypt / SSL PE (2026-07-17) — product TLS stack green under wine (providers + SSLContext.init + HTTPS GET)
- **L-003** — Process/exec, rich locale, zip edge, UDP/IPv6 matrix (2026-07-17)
- **L-004** — Shrink or replace multi-name DLL staging (2026-07-17) — product ships one PE soname each: `libicu_jni`/`libjavacore`/`libopenjdk`/`libopenjdkjvm`/`libcrypto`/`libssl`/`libjavacrypto` (+ `icuuc`/`icui18n`); short-name twins removed from packaging
- **L-005** — Linux multiplatform imageless Hello / boot.jar CI gate (2026-07-17)
- **L-006** — phase1.cmake / generated Win graph pure-vendor consistency (2026-07-17)
- **D-001** — Shared boot.jar via runtime OS selection (2026-07-17)

<!-- keep full CLOSED item bodies for history -->


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
- **Evidence:**
  - Host G12 (2026-07-16): net/dns/goldenapp PASS after select poll fix (`tools/verify/win64_phase3/evidence/host/ANALYSIS_20260716T205926.md`).
  - Wine (2026-07-17): NetProbe, DnsProbe, UdpProbe, AsyncCloseProbe, GoldenApp, **SocketAddressProbe** PASS.
- **Non-goals residual:** AF_UNIX SocketAddress; full AOSP `libcore_io_Linux.cpp` (L-001 closed with Win bridge map); NIO.2.
- **Code anchors:** `tools/win64/jni_stubs/win_net_natives.c`, `register_libcore_io_Linux_win.cpp`, `compat/src/win64_socket_posix.c`
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

### W-015 — openjdkjvm memory exports minimal PE surface
- **State:** CLOSED (2026-07-17) — product ships comprehensive standalone `libopenjdkjvm.dll`
- **Kind:** workaround
- **Area:** art / openjdkjvm
- **Fix / evidence:**
  - Product PE from `tools/verify/win64_libcore_icu/openjdkjvm_memory_standalone.c`: memory/GC + file I/O + sockets + raw monitors + time (`JVM_*` set used by hybrid openjdk).
  - Added `JVM_ActiveProcessorCount`.
  - Product `JVM_NativeLoad` delegates to `art.dll!ART_LoadNativeLibrary`; the ART-tree helper calls `JavaVMExt::LoadNativeLibrary`, preserving ART library ownership and unresolved JNI lookup.
  - The standalone DLL remains the product soname and broad `JVM_*` surface; the ART-tree Windows file supplies ART heap/GC exports plus the narrow native-load bridge.
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
- **See also:** **W-024** — Math.ceil/floor and the common ELF/PE registration table are restored; interpreter shorties remain only as defensive cleanup debt
- **Kind:** workaround / runtime ABI
- **Area:** libcore Math / ART interpreter JNI (Win64 -Xint)
- **Historical root cause:** Official AOSP CriticalNative is fine on Linux quick/generic-JNI. Win64 multipath formerly forced `ArtMethod::Invoke` through the interpreter; `InterpreterJniGeneric` only handled CriticalNative shorties `II`/`I`/`Z`/`ZI`. `Math.ceil` is shorty `DD` (`(D)D`), so dispatch fell through and crashed. Secondary: registering `Math_*_jni(JNIEnv*,jclass,jdouble)` under CriticalNative is the wrong ABI.
- **Historical fix:** interpreter CriticalNative `DD`/`DDD`/`FF`/`J`; `Math.c` `gMethodsWin` → `Math_ceil(jdouble)` etc.; posix stubs for the ART rebuild. W-024 removed `gMethodsWin`, restored ceil/floor native declarations, and stopped routing native methods through the Windows-only interpreter detour. The shorties remain only as defensive fallback until deletion.
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
- **Historical supporting workaround:** Win64 `-Xint` once forced natives through `InterpreterJni` and kept FastNative Runnable. W-024 removed that Windows-only branch on 2026-07-24 after the real JVMTI transition passed through Linux-like JNI entrypoints; the old detour aborted on mixed shorty `DJDIF`. The added interpreter shorties remain only as defensive fallback pending cleanup.
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
  - Historical Phase-3 `InterpreterJni` 12-slot workaround for multi-arg natives (`forkAndExec`, `sendtoBytes`); current product calls use JNI compiler/generated entrypoints and the fallback is pending W-011 cleanup
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
2. ~~**W-001**~~ closed; **W-002–W-003** retain residual TLS/entrypoint cleanup. **W-024** native acceptance is complete and now needs gate/fallback cleanup plus post-change regressions.
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
- **State:** OPEN (P5 implementation and Wine verification complete; real-Windows acceptance and residual hardening remain)
- **Kind:** host-validation gap / temporary diagnostic workaround / hardening debt
- **Area:** art / jit / compiler
- **Symptom / why:** The corrected default now reproduces ART's Linux-visible `[data R][code RX]` contiguous primary layout with a coherent RW updater alias. Remaining W-025 work is real-Windows acceptance, direct encoding-site checks, and removal of the J-1 diagnostic fallback. Threshold zero is no longer a JIT-memory unknown; its implementation work is tracked under W-024.
- **Current behavior:**
  - **Default corrected dual view:** one unnamed `CreateFileMappingW(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE)` section is mapped twice at offset zero. The complete primary view is below 4 GiB and split into data R plus code RX; the unrestricted alias is split into data RW plus code RW.
  - **Shared ART path:** mspace initialization, growth, address translation, commit, collection, and metadata handling remain on ART's common Linux/Windows path after mapping construction.
  - **Temporary J-1 diagnostic workaround:** `ART_WIN64_JIT_DUAL=0` selects the single-view `VirtualAlloc` path for comparison or emergency diagnosis. It writes code through an RX-to-RWX-to-RX transition and is not the product default.
  - **No disk file:** the section is unnamed and backed by the Windows paging system; no temporary filesystem object, pseudo-fd, or Windows memfd emulation is created.
  - **Historical separated-view defect:** the retired layout placed code far from roots and stack maps, overflowing signed 32-bit JIT-root displacements and uint32 CodeInfo distance. The corrected topology removes that layout.
  - **Threshold-zero stress:** resolved outside memory topology. The direct `@CriticalNative` path now has Win64 shadow/unified-argument handling and preserves its caller PC across the PE `LOAD_RUNTIME_INSTANCE` `r11` scratch. Repeated J-1 and dual-view acceptance passes; remaining W-024 scope is diagnostic/fallback cleanup and post-change regression.
  - Native gate: all native methods are excluded from JIT by default. The diagnostic `ART_WIN64_JIT_NATIVE=1` override passes the 7/7 mixed/high-FP normal/FastNative matrix across rebinding and tracing; the separate CriticalNative suite passes tracing in both memory modes; the JVMTI forced-interpreter matrix passes 3/3 per mode; and restored Math CriticalNative passes dual/J-1/-Xint plus Linux controls. Native Windows 10 acceptance passes; the gate remains opt-in pending diagnostic/fallback cleanup.
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
- **Separate residual:** Complete W-024 diagnostic/fallback cleanup before removing the native-JIT gate. Product demotions and forced-interpreter transitions pass under Wine and native Windows 10. W-025's broader mapping/mitigation real-host acceptance remains separate.
- **Code anchors:** `mem_map_windows.cc` constrained section mapping; `mem_map.cc` Windows in-place split ownership; `jit_memory_region.cc` corrected dual-view branch and common post-mapping logic; `utils.cc` cache flush; `code_generator_x86_64.cc` `PatchJitRootUse`; `oat_quick_method_header.h` `code_info_offset_`; `jit.cc` native gate and opt-in compile records; `art-dlmalloc.cc` `USE_LOCKS=0`
- **Verified:** default corrected dual-view Hello passes with about 21–24 managed compiles; JIT smoke 12/12, including default-silent compile diagnostics; JIT matrix 14/14; J-1 diagnostic Hello passes; D-1 audit complete (37/37 GS sites); threshold-zero, registered, unresolved mixed-dlsym, method-traced, and JVMTI-forced native probes pass in both memory modes; the normal/FastNative mixed/high-FP matrix compiles 7/7 targets and survives rebinding plus method tracing without extra target compilation; standalone section-layout probe passes coherence, execution, protection, forced low-space fragmentation, and non-64-KiB capacity cases under Wine (2026-07-24)
- **Design:** [win32_jit_memory.md](win32_jit_memory.md) §2–§13 (Linux low-4-GiB contract, historical diagnosis, implemented Windows 10 section design, verification, and residual work)
- **Opened:** 2026-07-19
- **Updated:** 2026-07-24 — corrected pagefile-section dual view remains verified; threshold-zero and restored CriticalNative paths pass; per-method compile records are opt-in; temporary J-1 diagnostic opt-out and real-Windows acceptance remain


*Last snapshot: 2026-07-24 — W-001 closed; nterp ON; corrected pagefile-section dual view is the managed-JIT default (12/12 smoke, 14/14 matrix); D-1 complete; direct CriticalNative and 7/7 mixed/high-FP normal/FastNative matrices pass unresolved dlsym, rebinding, method tracing, and JVMTI forced interpretation; Math.ceil/floor and one common ELF/PE table are restored; compile records are opt-in; W-024 native Windows acceptance passes; `ART_WIN64_JIT_DUAL=0` temporarily retains J-1 for diagnosis; W-025 broader real-host acceptance and W-024 native gate/fallback cleanup remain; 12 OPEN workarounds remaining.*
