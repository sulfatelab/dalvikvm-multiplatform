# Win32 / multiplatform — open items & temporary workarounds

**Status:** living tracker  
**Created:** 2026-07-17  
**Updated:** 2026-07-31
**Rule:** Every **temporary workaround** that future work must remove belongs here as **OPEN**.  
When the proper fix lands, mark the item **CLOSED**, move it into §Closed (sorted), and keep the full history.  
Do **not** list permanent non-goals as OPEN workarounds—list them under §Non-goals.

### Related docs

| Doc | Role |
|-----|------|
| [win32_art_port.md](win32_art_port.md) | Product phases / feasibility |
| [win32_filesystem.md](win32_filesystem.md) | Option H path model |
| [win32_faults_and_stacks.md](win32_faults_and_stacks.md) | Authoritative coupled W-010/W-014 managed-fault, VEH-chain, pthread, and ART stack design |
| [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) | Implemented x86_64 TLS / managed ABI / quick / nterp / JIT contract plus cross-ISA design record |
| [win32_jit_memory.md](win32_jit_memory.md) | JIT memory contract, historical separated-view diagnosis, and implemented Windows 10 pagefile-section design |
| [win32_aot_oat.md](win32_aot_oat.md) | Selected restricted ELF64 OAT coat, dedicated loader, PE rejection, and AOT risk/gate design |
| [win32_heap_memory.md](win32_heap_memory.md) | W-013 heap / embedded-dlmalloc ownership, low-address, and MoreCore target design |
| [win32_libcore_os_natives.md](win32_libcore_os_natives.md) | Os/`Linux` natives: Implemented / Needed / ENOSYS |
| [win32_host_gate_policy.md](win32_host_gate_policy.md) | Current native lab host and future-gate policy |
| `tools/verify/windows_x64_phase*/RESULT.md` | Gate evidence |

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

## Native lab gate policy

The former Windows 10 acceptance host is no longer available after the lab
environment change. Windows Server 2025 Datacenter Evaluation, x64 build
26100, is the sole authoritative native gate for all future test packages,
acceptance matrices, regression gates, and release claims. Wine/Linux remain
development and structural checks only. Existing Windows 10 result bundles are
historical evidence and do not provide current cross-version coverage. The
canonical policy is [win32_host_gate_policy.md](win32_host_gate_policy.md).

---

## Snapshot (2026-07-30)

| Bucket | Summary |
|--------|---------|
| Phases 0–3 | **Gate-complete** (historical P3 G12 real Win10 + wine; future reruns use the Server 2025 gate) |
| Phase 4 | **Wine complete; authoritative Windows Server 2025 build-26100 gate accepted** |
| PE libcore/ICU/openjdk | **Product-default real PE** (icu/javacore/openjdk); NIO.2 non-goal; NetProbe OK |
| Quick/JIT/TLS | **Managed and native JIT ON with the sole corrected dual view:** rSELF=r15; nterp N-1 default ON; D-1 complete (37/37 Thread sites); W-002/W-003 closed; post-removal JIT smoke 14/14 and matrix 14/14; JIT-1 encoding, JIT-2 mapping/policy, JIT-3/FS-3 lifecycle/unwind, JIT-4 default-path, and JIT-5 removal/native closure gates pass; JIT-5 accepts 29 cases and 36/36 records with three valid dumps; W-025 CLOSED; compile records opt-in |
| Memory | One unnamed pagefile section is mapped as a contiguous low R/RX primary view plus a full RW alias; native 64 MiB/1 GiB, low-VA, pressure, and CFG acceptance passes; `ProhibitDynamicCode` rejection is negative fail-closed evidence, not a supported profile; ART `389158d46f` removes J-1 and fails closed on construction errors; the retired environment key is inert |
| Heap memory | **W-013 CLOSED:** explicit MoreCore-only dlmalloc, direct mspace owners, constrained `VirtualAlloc2`, page-state operations, Linux-like metadata placement, and native R2 pressure/JIT/repeated-start acceptance PASS |
| Threads / managed faults | **W-010/W-014 core path, FS-1, FS-2, authoritative-host FS-4, FS-5 conditional disposition, and H-001 scoped host subset accepted:** E9 passes 30/30 and FS-1 passes Release/Debug switch, nterp, and JIT on authoritative Windows Server 2025 build 26100. FS-2 passes native debugger continue, named CET policy classification, exception-unwind XMM, and embedding/UEF teardown. H-001's gcstress, threadheavy, handleleak, crash-abort, and native AV/minidump subset also passes on build 26100. FS-4 repeats E9/FS-1/FS-2/FS-3, parameterized stack geometry, fiber rejection, and join/detach stress on that host; the separate Windows 10/second-host repetition is skipped by policy. FS-5 closes the pending 88-byte bridge tail conditionally because it is entered only by ART's managed pending-exception branch; structural and synthetic unwind evidence pass, but a real native fault would require product fault injection. Remaining work is reservation correlation, negative-exception cases, and debugger-quality dump-stack reconstruction. |
| AOT/OAT | Restricted ELF64 design selected. Implementation stage 1 adds pre-dispatch characterization for fallback, reservations, path/ZIP/fd inputs, duplicate instances, teardown isolation, VDEX placement, and dynamic anchors; it does not implement the OAT-1 Windows loader. Linux/Windows builds and the Server 2025 DLL-load smoke pass. H-004 tracks the glibc positive-dlopen skip; H-005 tracks focused behavioral execution outside the minimal product CMake graph. |
| Linux multiplatform | Full native rebuild, L-005 imageless Hello, and GC stress PASS after the Windows-only JIT-5 removal using the staged shared multipath `boot.jar` |

---

## Temporary workarounds (must be removed later)

### W-008 — Some product smoke still passes `-Xint` / imageless
- **State:** OPEN (partial — managed JIT suites run without `-Xint`; older interpreter-specific probes retain it)
- **Kind:** workaround (policy flags)
- **Area:** packaging / product CLI
- **Current behavior:** Product default runs with managed JIT ON through the corrected dual view. Unified `art.w025.windows_w025_jit_runtime_controls` omits `-Xint` and owns seven control cases plus canonical Math/IO/Net/GC/throw workloads; native Windows passes the expanded stage 9/9 twice. Older Phase 3, package, crash, and interpreter-specific gates may still force `-Xint` for deterministic coverage. Product CLI does not need `-Xint`. Stage D removed `-Xno-sig-chain` from active product and native-host runners; the focused W-010 gate retains one intentional negative invocation that proves a started runtime rejects it.
- **Proper fix:** Classify each remaining `-Xint` use as intentional interpreter coverage or migrate it to the default JIT path, with `ART_WINDOWS_X64_JIT=0`/`-Xint` retained only where the test specifically requires it. Imageless mode may remain until boot-image work (separate track).
- **Code anchors:** `tests/cases/jit-runtime-controls/run.py`, `tests/CMakeLists.txt`, and retained historical Phase-3 package evidence
- **Opened:** 2026-07-16
- **Updated:** 2026-08-01 — the Phase-4 smoke/matrix wrappers migrated to unified W-025; remaining review is limited to intentional `-Xint` coverage and imageless mode

### W-010 — Windows managed-fault adapter, fatal unwind, and CET exclusion
- **State:** OPEN for conditional follow-ups; core E9 managed-fault/fatal matrix is native-accepted 30/30 on build 26100
- **Kind:** workaround → candidate permanent design
- **Area:** art / exceptions
- **Current behavior:** `sigchain_windows.cc` owns one immutable special-`SIGSEGV` action and a first VEH. It translates only exact generated-code access violations such as implicit null checks; unsupported records continue through Windows. Windows x64 stack overflow is now detected before the method prologue by an explicit `RSP < Thread::stack_end_` check in optimizing code and nterp, with equality allowed and an overflow tail-jump through `Thread::pThrowStackOverflow`. Linux keeps its unchanged implicit `RSP - 8192` path. `runtime_windows.cc` separately owns best-effort fatal VEH/UEF/minidump diagnostics and predecessor chaining.
- **Current test isolation:** W-003's attributed frame probe still excludes its historical implicit-null subtest, but `W010ManagedFaultProbe` covers the product path. No explicit nterp null check or forced-interpreter fallback was added. The Windows x64-only explicit stack check is the accepted low-divergence exception forced by native Windows stack-growth semantics.
- **Selected design:** Windows does not emulate general POSIX sigchain. The narrow facade implements only the special `SIGSEGV` action registered by common `FaultManager`. The x86_64 context adapter modifies the real Windows x64 `CONTEXT` for recognized AV-based faults, validates `R15 == Thread*`, prevents recursive dispatch, and returns search for all others. Stack overflow no longer depends on VEH classification, a fixed page, `EXCEPTION_STACK_OVERFLOW`, or `_resetstkoflw`; explicit generated checks enter the common quick throw path before Windows exhausts its native recovery region. Moving `PAGE_GUARD`, execute AV, breakpoints, illegal instructions, and native/unregistered AVs are never converted to Java exceptions.
- **Chain / diagnostics contract:** debugger first-chance notification remains before ART as Windows documents. ART registers first and `EnsureFrontOfChain()` may best-effort promote it after JNI load, but unrecognized faults always continue to later VEH/SEH handlers. Expected implicit faults do not log or dump. Fatal UEF/minidump handling is separate and must call the previously installed UEF rather than replace host policy silently. PE runtime-function data is required for Windows dispatch to cross native/managed boundaries; it is not merely optional dump hardening.
- **Activation:** implicit null handling still requires the managed VEH and published special action. Windows x64 stack checks require validated guarantee-aware `Thread::stack_end_` bounds but no installed fixed page. A normal started runtime rejects `-Xno-sig-chain` exactly as Linux does; only genuine non-started compiler/tool runtimes retain the option.
- **CET/HSP contract:** Win32 ART does not support CET user shadow stacks (Hardware-enforced Stack Protection). `art_quick_do_long_jump` restores an older regular `RSP` and executes `ret` without synchronizing CET's protected return stack, affecting ordinary managed throws, deoptimization, JNI exception delivery, and W-010 implicit throws. W-010's `CONTEXT.Rip`/`Rsp` edits also conflict with context-IP validation. Every project PE link must explicitly use `/CETCOMPAT:NO`; packaged DLLs must omit `IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT`; startup must reject every defined incompatible `ProcessUserShadowStackPolicy` field before ART threads/JIT. Compatibility, audit, strict, context-IP-validation, and non-CET-binary fields are unsupported. `CetDynamicApisOutOfProcOnly` is allowed because it does not enable HSP or context-IP validation; `ReservedFlags` is ignored because reserved bits have no defined meaning. CFG remains distinct from CET and its W-025 JIT-2 compile/execute matrix is native-accepted; `/guard:ehcont`, dynamic continuation targets, CET-compatible JIT ranges, IBT, or `-fcf-protection` are not fixes.
- **Current CET state:** Stage 0 is implemented and FS-2 is native-accepted. Generator policy applies `LINKER:/CETCOMPAT:NO` to every generated non-static target, and the unified test catalog applies the same option to every PE probe. The reviewer rejects raw PE link scripts and legacy shell packagers, then audits every PE target's actual Ninja command and output marker. `Runtime::Init()` queries `ProcessUserShadowStackPolicy` after logger selection and before `MemMap::Init()`, ART threads, nterp, or JIT. It constructs an incompatibility mask from named SDK fields, accepts `CetDynamicApisOutOfProcOnly` and reserved fields, accepts `ERROR_INVALID_PARAMETER` only below Windows build 19041, and fails closed on unexpected query/version failures. Native build 26100 accepts raw `flags=0x00000100` as `CetDynamicApisOutOfProcOnly`, accepts reserved bits, and rejects all nine forced named-incompatible policy cases before Java/JIT with no dump.
- **First combined native candidate:** `/tmp/log-w010-w014-osr-host-20260727-6.zip` matches the issued package identity but is not accepted: review returns 9 PASS and 21 FAIL. The raw-policy rejection above prevented ART startup and cascaded through managed/JIT cases. Independent native successes remain useful evidence: static OSR/RBP lookup and live unwind, stack-page restoration, exact fault-record filtering, foreign-VEH/frame-SEH behavior, and join/detach handle stability all passed. The same run also exposed the separate W-014 small-reservation probe defect described below.
- **Second combined native candidate:** `/tmp/log-windows_x64_w010_w014_host-run2.zip` matches the issued package and returns 20 PASS and 12 FAIL on Windows 10 Enterprise LTSC build 19044. CET classification, exact small reservations, stable handles, direct stack-page restoration, fault records, sigchain/frame-SEH, nterp/JIT NPE, OSR live unwind, six XMM sentinel runs, and no-chain rejection pass. Switch/nterp/JIT SOE terminate with `STATUS_STACK_OVERFLOW`; the JIT access is exactly `RSP - 0x2000`, but Windows' moving guard wins before ART's page AV. Switch recovery also sees the temporarily writable ART page with unexpected protection and error 13. Static, JIT J-2/J-1, and OSR J-2/J-1 fatal AVs all reach VEH, then exit without UEF or dump. Their identical behavior means JIT unwind is not the first diagnosis.
- **Third native diagnostic result:** `/tmp/diag-log-windows_x64_w010_w014_host-run3.zip` matches the issued package and completes the isolated matrix on build 19044. Baseline/protected/writable recursion reaches `STATUS_STACK_OVERFLOW`; direct protected-page access still AVs. At protected-mode termination the selected page belongs to a 2,093,056-byte committed `PAGE_READWRITE` region, proving Windows stack growth consumed its protection. Writable mode re-protects successfully before `_resetstkoflw()`, so run-2 error 13 was secondary recovery-state fallout. Standalone main/worker/chained UEF dispatch passes and frame SEH consumes its own AV as expected. The late JNI probe identifies ART's filter in `art.dll` as its predecessor immediately before the crash, then only `ART Win32 VEH` runs: neither late nor ART UEF runs, and dump creation is never reached. UEF replacement, the runner, debugger attachment, and dump-path/API failure are ruled out.
- **GenericJNI repair:** captured addresses map the native return site to `art_quick_generic_jni_trampoline + 0xc5`; an `art_jni_dlsym_lookup_stub` address is also present but may be saved data/function-pointer state. A realistic virtual-unwind case builds the completed 200-byte frame, 5120-byte R12-anchored reserved area, and variable normal-JNI native RSP. It found that RDI was physically saved at `R12 + 0x1400` while `.xdata` described offset zero. The record is repaired, structural audit requires `SAVE_NONVOL RDI, offset=0x1400`, and Wine restores caller RIP/RSP plus all nonvolatile GPRs. Native run 4 proves the repair is insufficient to restore fatal UEF dispatch by itself.
- **Exception-shape diagnostic:** `CrashNativeProbe` provides a continuable JNI `RaiseException(EXCEPTION_ACCESS_VIOLATION)`, the existing JNI hardware AV, and a hardware AV on a JNI-created `_beginthreadex` worker with no ART frames on the crashing thread. The diagnostic runner records late/ART UEF, VEH, dump, exit shape, and worker markers separately. Wine reaches late UEF, ART UEF, and minidump creation for all three; native run 4 instead isolates the failure to the two JNI-thread managed/GenericJNI chains.
- **Fourth native diagnostic result:** `/tmp/diag_w010_w014_host-run4.zip` exactly matches the repaired GenericJNI package. JNI hardware AV and JNI `RaiseException` behave identically on build 19044: ART remains the predecessor UEF and ART's VEH runs, but neither the late UEF nor ART UEF runs and no dump is created. The JNI-created native worker, in the same initialized ART process but with no ART frames on the crashing thread, reaches the late UEF, ART UEF, and writes one valid 648,619-byte minidump. This rules out hardware/software exception shape, process-wide ART state, UEF ownership, debugger/runner behavior, and dump API/path. The failure is specific to traversal through the ART managed/GenericJNI caller chain; the repaired GenericJNI record is correct but not the complete boundary.
- **E4 live unwind diagnostic:** `ART_WINDOWS_X64_FATAL_UNWIND_TRACE=1` enables a bounded 32-frame walk from a copy of the live VEH `CONTEXT` only in the three late-UEF diagnostic children. It records module base/path/RVA, runtime-function RVAs, virtual/leaf steps, bounds, progress, and a terminal reason without changing dispatch. A direct Wine smoke crossed the native method, repaired GenericJNI, invoke stub, and ordinary ART frames, then found the first live lookup miss at `ExecuteSwitchImplAsm + 0x9` (`pop %rbx`). That wrapper pushed RBX but has no PE record, so leaf fallback consumes saved RBX as the return PC. The complete `-j32` package/Wine preflight passed twice, including all three traced modes and 14-15 valid fatal dumps before clean regeneration. Native E4 subsequently confirmed the boundary. The repair must add both Windows x64 unwind metadata and the mandatory 32-byte MSVC outgoing home area while leaving Linux/SysV unchanged.
- **Native E4 confirmation:** the exact package runs automatically on Windows Server 2025 build 26100 and reports `DIAGNOSTICS COMPLETE`. JNI hardware and raised AV traces both reach `art.dll` RVA `0x009b6089`, `ExecuteSwitchImplAsm + 0x9`, where lookup returns null; leaf fallback consumes saved RBX as PC and both UEFs are missed. The native worker unwinds through four registered frames, reaches both UEFs, and creates one valid 747,491-byte dump. Stack growth repeats the build-19044 result on current Windows. The result bundle SHA-256 is `4616e8622dba2977b5472264f099de9449aa5c8b0a4bc1d1d568f9af8c6987b8`.
- **E5 switch-wrapper repair and native result:** Windows x64 `ExecuteSwitchImplAsm` now saves RBX, reserves the required 32-byte MSVC outgoing home area, uses a canonical epilogue, and emits a PE unwind record; Linux/SysV bytes are unchanged. Structural lookup and entry/body/epilogue virtual-unwind probes pass. The exact E5 package passes on Windows build 26100, where the live post-call PC is now `ExecuteSwitchImplAsm + 0xd` with `lookup=1`. Both JNI traces cross it and four later registered ART C++ frames before the first miss at `art_quick_to_interpreter_bridge + 0x82` (`rva=0x9d3652`), the return PC after `call artQuickToInterpreterBridge`. Fatal UEF remains unreachable. The native worker again reaches both UEFs and writes one valid 747,073-byte dump. Result bundle SHA-256: `1a58bb0f318eae82882ea1bd0e5b0fa403202d02ae95a889b07a1e7b3524b3d9`.
- **Local E6 interpreter-bridge repair:** the Windows x64 primary range preserves ART's exact 200-byte save-refs-and-args layout and reports every stack change plus saved RSI/RBP/RBX/R12-R15. Fixed-offset restores keep that frame intact through the native E5 `+0x82` return PC and end in recognized `add rsp, 200; ret` or tail-jump epilogues. The pending-exception target begins a separate contiguous runtime-function range for its 88-byte save-all frame; it is not covered by the primary record. The structural audit requires both records, and the live probe virtually unwinds entry, call return, restore body, both epilogues, and pending body with `failures=0`. The complete Phase-4 Wine aggregate, W-003 frame/XMM matrices, Linux rebuild/showversion/imageless Hello, and unchanged Linux bridge disassembly pass. The E6 package label and native reviewers require `interpreter_bridge_records=2`, call return `0x82`, pending offset `0x140`, and frame sizes 200/88.
- **Native E6 result:** the archive and Python checker pass on Windows Server 2025 build 26100. JNI hardware and raised traces now report `lookup=1` at `art_quick_to_interpreter_bridge + 0x82`, then cross every remaining ART/executable/OS frame with a runtime-function record and end at zero PC after 23/24 frames. Both enter the late UEF and ART UEF and each write a valid dump; the native-worker control does the same. This closes the diagnosed fatal-dispatch lookup chain and natively accepts the primary 200-byte bridge record. The 88-byte pending record is structurally/synthetically verified but not entered by these cases. Result bundle SHA-256: `a1c6af0ceff198f6b4543aa832dbf40ced81dcf72800b77c55dd5f2959302736`.
- **Complete native E6 host matrix:** the exact package runs automatically from a fresh directory on Windows Server 2025 build 26100 and records 25/30 PASS rows. Static `-Xint`, threshold-zero JIT J-2/J-1, and switch-OSR J-2/J-1 fatal AVs all reach VEH and UEF and create five valid named 14-stream dumps. Switch managed SOE instead fails fixed-page re-protection with unexpected state/error 13 and exits `0xC0000005`; nterp and JIT reach `0xC00000FD`, with JIT reaching UEF and creating an unwanted sixth dump. The handled-log and handled-dump aggregates fail as consequences. Returned identity matches the issued package before the reviewer correctly rejects `OVERALL FAIL`. Raw result bundle SHA-256: `d6bb85c1529496cb384bebcc1495378ade0e253041e01a9605f3f6c90b8538e5`.
- **E7-E9 replacement and native acceptance:** E7 replaces Windows x64's rejected implicit fixed-page SOE with explicit pre-prologue `RSP < Thread::stack_end_` checks in optimizing code and nterp, while Linux bytes and implicit `RSP - 8192` behavior remain unchanged. E8's `max(prefix, guarantee)` accounting fails natively. Controlled build-26100 measurements prove that the guarantee is above a separate terminal prefix and below one moving guard page. E9 queries the existing `SetThreadStackGuarantee`, raises it to at least four pages while preserving larger values, queries it back, and debits `prefix + rounded guarantee + one guard` before common ART adds its 8192-byte product reserve. The immutable archive SHA-256 is `2b84c911dfbe23dd5dd13917a0fb4a63bdbf90901172f74dfe642ed1fd20f16f`. The returned full package matches the issued payload and passes 30/30 on Windows Server 2025 build 26100 with zero handled dumps and five valid fatal dumps; the independent reviewer accepts it. See `tools/verify/windows_x64_phase4/evidence/w010_w014_e9/ACCEPTANCE.md`.
- **FS-1 stack high-water acceptance:** probe-only, allocation-free RSP samples cover the failing explicit check, quick entry/frame, common throw entry, temporary stack-end expansion, exception construction/completion, restored boundary, delivery, and long jump. Product isolation rejects the probe export and offsets in the normal build. Final-source Wine Release margins are switch 7536, nterp 7520, and JIT 7616 bytes; Wine Debug margins are 69728, 37216, and 37232. Native Release margins are 6784, 7536, and 7616; native Debug margins are 69744, 37168, and 37232. The first native Debug run exposed `STATUS_STACK_OVERFLOW` while allocating `StackOverflowError`; a 20-KiB trial still left quick paths about 8 KiB short. The accepted 40-KiB non-`NDEBUG` Windows x86_64 reserve leaves more than 37 KiB on quick paths while product and non-Windows remain at 8192 bytes. Six native processes pass with four complete records each, no fatal VEH/UEF marker, and `NO_DMP_FILES`. Package SHA-256: `22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe`; see `tools/verify/windows_x64_phase4/evidence/fs1_stack_high_water/ACCEPTANCE.md`.
- **Local Stage D evidence:** the focused Wine gate passes started-runtime `-Xno-sig-chain` rejection; 64 caught read NPEs plus 64 caught write NPEs in nterp and threshold-zero JIT; two caught SOEs on the main thread plus two on a newly created child thread in both modes; 128 post-NPE and four post-SOE stack-trace/allocation recovery checks; 16 NPE and four SOE-triggered collections per run; required JIT compilation records; no managed-fault diagnostic VEH/UEF output; and no dump-state change. The focused chain probe verifies foreign VEH ordering before/after ART, promotion, search behavior, and frame-based SEH both while the ART action is present and after removal. JIT smoke remains 12/12, the complete Phase-4 aggregate passes, and Linux rebuild/showversion/shared-boot Hello pass.
- **Static and dynamic fatal result:** PE unwind records cover `art_quick_invoke_stub`, `art_quick_invoke_static_stub`, `art_quick_generic_jni_trampoline`, and two contiguous ranges for `art_quick_osr_stub`. The OSR entry range uses fixed-bottom R12 while the variable copy moves RSP, then sets RBP to copied RSP immediately before the JIT handoff; the return range describes the inherited 248-byte frame directly from RSP because OSR code reconstructs managed state before returning. This zero-prologue inherited-frame record is a deliberate Windows platform adapter, not a general called-function pattern or a fallback workaround. The emitted audit verifies exact frame anchors, allocations, GPR saves, ten completed-frame XMM offsets, and range contiguity. A live Wine probe restores RBP/RDI/RSI/RBX/R12-R15 and XMM6-XMM15 from a variable-depth OSR entry, a managed-RBP-clobbered return context, and the canonical epilogue; synthetically unwinds both invoke records; and now virtually unwinds GenericJNI from native return `+0xc5`, including the corrected RDI offset `0x1400`. The actual 8/8 OSR matrix passes. The full-width normal-return sentinel passes 2/2 in nterp, switch, and threshold-zero JIT with `fullSelfTestMask=1023`. The static `-Xint`, threshold-zero J-2/J-1 JIT-origin, and switch-OSR-origin J-2/J-1 AV gates reach initial VEH and UEF and each create a new valid `MDMP` dump. This proves fatal dispatch across both exercised dynamic chains under Wine, not debugger-quality minidump stack reconstruction or native-host acceptance.
- **Dynamic-JIT design:** [win32_faults_and_stacks.md](win32_faults_and_stacks.md) §7.9 selects a Windows-JIT-only fixed `RBP` anchor for every optimizing method, an anchored normal/FastNative JNI shape, fixed-RSP CriticalNative JNI records, explicit PE unwind serialization independent of DWARF debug-info policy, xdata in the existing primary low-4-GiB JIT data allocation, and one immutable one-entry `RtlAddFunctionTable()` registration per code allocation. Registration precedes every entrypoint/map publication; the exact table is deleted before debug-info removal, mspace reuse, or mapping teardown. Growable tables are rejected because ART allocation is not monotonic and tables cannot shrink/reorder; callback tables remain a measured scalability fallback because they require a lock-free crash-time PC index, stable reclamation, and out-of-process debugger support.
- **Dynamic-JIT implementation:** the x86_64 assembler emits explicit version-1 unwind bytes with shortest legal allocation forms, descending instruction-end offsets, even-slot padding, and validation. Optimizing Windows x64 JIT methods reserve and force-spill RBP, then establish it after the fixed allocation. Normal/FastNative JNI stubs use the same anchor and a four-register RBX/R12-R14 scratch set; CriticalNative retains a fixed-RSP record. Generation is independent of DWARF CFI, and invalid/missing enabled metadata rejects compilation before allocation. `Reserve()` adds the DWORD-aligned xdata tail after roots/stack maps; `Commit()` writes through the RW alias and registers a stable one-entry table before publication. `FreeLocked()` deletes the exact table before debug-info removal and mspace reuse, while destruction clears all entries before mapping teardown. The J-2/J-1 lifecycle gate proves invalidation retention, real collection, lookup disappearance, exact address reuse, re-registration, and replacement execution; the registry gate proves generated-frame virtual unwind.
- **Native JIT-3/FS-3 acceptance:** four J-2/J-1 processes on build 26100 complete 52 collections, 1,344 optimizing/JNI compilations, 1,248 exact address reuses, 696,929 stable-live lookups, 5,909,811 stable-dead lookups, and 696,969 successful virtual unwinds with `missing_live=0`, `stale_dead=0`, `unwind_failures=0`, `callback_tables=0`, empty JIT temp, and no dump. Independent returned-archive review passes 9/9. ART `43f866830e` also fixes the normal-JNI/nterp hard-float return regression found by the preflight: XMM0 remains authoritative instead of copying RAX's `0x5c000000` transition state into the Java result.
- **Native JIT-4 fatal/unwind cross-regression:** the final default-J-2 archive passes 28 cases and 34/34 aggregate records on build 26100 without a J-1 arm. Its lifecycle repeat completes eight collections, 216 compilations, 192 exact reuses, and 85,944 virtual unwinds with zero missing/stale/failed records. Static, threshold-zero compiled-JIT, and OSR fatal origins each reach VEH/UEF and create a valid `MDMP`; `jit-temp` is empty and no trace remains. This cross-regresses E9 and FS-3 but does not close the remaining independent W-010 proof points.
- **Remaining native acceptance:** keep the accepted E9, FS-1, FS-2, authoritative-host FS-4, FS-5 disposition, and H-001 subset as regression gates. Dynamic-JIT rollback fault injection and method-redefinition/OSR retirement extensions, Java/ART-pool reservation correlation, negative-exception cases, and debugger-quality dump-stack reconstruction remain conditional. The Windows 10/second-host repeat is explicitly skipped by policy. FS-5 records why a native exception inside the pending bridge range is impractical without product fault injection; debugger continuation, named CET rejection, exception-unwind XMM, and predecessor-UEF embedding are closed.
- **Code anchors:** `vendor/art/runtime/runtime.cc`; `runtime/multiplatform/windows/sigchain_windows.cc`; `runtime_windows.cc`; `runtime/fault_handler.{h,cc}`; `runtime/arch/x86/fault_handler_x86.cc`; `runtime/arch/x86_64/quick_entrypoints_x86_64.S`; `runtime/multiplatform/windows/jit_unwind_windows.*`; `compiler/optimizing/code_generator_x86_64.*`; `compiler/utils/x86_64/{assembler,jni_macro_assembler}_x86_64.*`; `runtime/jit/{jit_code_cache,jit_memory_region}.*`; `tests/cases/{osr-unwind,jit-unwind-registry,stack-page-growth,unhandled-exception-filter}/`; transitional checkers and managed runners under `tools/verify/windows_x64_phase4/`
- **Blocked on / design doc:** no blocker for core managed-fault delivery, FS-1 stack budget, FS-2, authoritative-host FS-4, FS-3 dynamic-table churn, or the FS-5 conditional disposition; only reservation/negative-exception/debugger-quality probes remain; [win32_faults_and_stacks.md](win32_faults_and_stacks.md)
- **Opened:** 2026-07-16
- **Updated:** 2026-07-30 — FS-1 Release/Debug switch, nterp, and JIT stack high-water acceptance passes on build 26100; the 40-KiB Debug-only reserve leaves more than 37 KiB of native margin without changing product or Linux

### W-014 — Windows stack bounds, pthread sizes, and stack guarantees

- **State:** OPEN for conditional correlation/negative/debugger-quality follow-ups; authoritative Windows Server 2025 build-26100 coverage is accepted in E9/FS-4
- **Kind:** permanent Windows adapter with remaining conditional follow-ups
- **Area:** art / threads / compat pthread
- **Current bounds behavior:** Win `GetThreadStack()` accepts only the current non-fiber system stack. The pthread facade uses `GetCurrentThreadStackLimits()`, checks current-SP containment and a committed-private `VirtualQuery(SP)` record with `AllocationBase == low`, then walks the complete contiguous `[low, high)` reservation before ART publishes the bounds. Failure rejects attachment rather than clamping or fabricating a fallback. The one-page `pthread_attr_getguardsize()` result remains only a facade compatibility value; E9 replaces it inside `InitStack()` with the complete measured prefix + configured guarantee + moving-guard sum.
- **Current allocation behavior:** `Thread::CreateNativeThread()` passes ART's post-`FixStackSize()` request through the implemented pthread attributes. The facade creates a suspended `_beginthreadex` thread, uses `STACK_SIZE_PARAM_IS_A_RESERVATION` for non-zero sizes, completes the control state before resume, and rejects invalid or caller-supplied stack addresses. Windows ART thread-pool workers no longer allocate ignored `MemMap` stacks; they pass their requested reservation to the OS.
- **Current bound behavior:** every attached thread queries its existing stack guarantee, raises it to at least four system pages while preserving a larger host value, and queries the configured value back. The platform helper measures the inaccessible low prefix with `VirtualQuery()`, page-rounds the configured guarantee, adds one moving-guard page, and reports that sum to common `InitStack()`. Common ART then places its 8192-byte product overflow-recovery reserve above the Windows-native recovery boundary; only non-`NDEBUG` Windows x86_64 uses the FS-1-measured 40-KiB reserve. A failed query, set, verification, overflow, or minimum-size check rejects attachment.
- **Generated-code integration:** x86_64 optimizing code and nterp use a narrow Windows x64-only pre-prologue comparison against `Thread::stack_end_`; equality is valid and only a lower RSP tail-jumps to `Thread::pThrowStackOverflow`. Linux retains its unchanged implicit `rsp - ART_STACK_OVERFLOW_GAP_x86_64` probe. The structural gate disassembles both targets and prevents accidental Linux divergence.
- **Windows 10 bounds contract:** Stage A implements the documented current-thread path: reject `IsThreadAFiber()` first, use `GetCurrentThreadStackLimits()` as the authoritative system-stack interval, validate alignment and current-SP containment, require `VirtualQuery(SP)` to report committed private memory with `AllocationBase == low`, and walk the complete `[low, high)` allocation with an exact end. Common `Thread::InitStack()` applies ART's minimum-size rule. The project baseline is Windows 10 build 17134+ with `_WIN32_WINNT=0x0A00`, so no Windows 7 fallback or dynamic resolution exists. TEB fields remain optional diagnostics only; every fiber and manual-stack attachment is rejected.
- **Thread-creation and identity contract:** Stage A uses `_beginthreadex`, not raw `CreateThread`, because ART callbacks execute C/C++/UCRT code. Zero uses the executable default and non-zero `pthread_attr_t::stacksize` uses reservation semantics. The opaque control object retains the real joinable handle, publishes the callback `void*` result, and gives join or detach one public completion reference. Created-thread identity is kept temporarily in module-local `TlsAlloc` storage and cleared by the trampoline. Externally created threads use allocation-free tagged tokens containing the live Windows thread ID; `pthread_equal()` compares immutable IDs across DLL-local facade copies, while `pthread_gettid_np()` is the numeric boundary. An FLS-destructor design was rejected after Wine showed that process teardown could call code from an already non-executable `art.dll`. The Windows `sun.nio.ch.NativeThread` token remains a separate OS-thread-ID contract.
- **Former fixed-page contract, retained only for diagnostics:** native protected growth proves Windows consumes the selected page as ordinary stack backing before `STATUS_STACK_OVERFLOW`. The selector/protect/restore code remains useful for direct page-state probes, but product attachment no longer installs a fixed page and managed SOE never depends on one. ART does not adopt `PAGE_GUARD` or translate `EXCEPTION_STACK_OVERFLOW`.
- **Detach contract:** product attachment does not change stack page protection, so an external native thread may detach and continue without restoring an ART-owned fixed page. The direct page-state probe still verifies exact reserved/committed restoration inside its own diagnostic scope.
- **W-010 ownership boundary:** W-014 owns bounds, stack-guarantee configuration, `_beginthreadex` reservation and pthread lifetime, and stack accounting. W-010 owns VEH/context adaptation for AV-based managed faults, explicit Windows x64 stack-check generation, quick-entrypoint redirection, and fatal unwind/diagnostics.
- **CET boundary:** guarantee-aware bounds and explicit stack checks do not provide or repair CET support. The process-wide CET/HSP exclusion and early startup check belong to W-010 because ART's shared exception/deoptimization long jump is incompatible even without an implicit stack fault.
- **Wine/Linux/native evidence (2026-07-30):** Wine passes the bounds/lifetime, direct page-state, and managed-SOE matrix. Native build 19044 validates exact small reservations and rejects fixed-page recursion. Controlled build-26100 guarantee requests prove terminal fault positions of `low+0x3000`, `+0x3000`, `+0x4000`, `+0x5000`, `+0x9000`, and `+0x11000` for requests 0, 8192, 12288, 16384, 32768, and 65536. E9's sum accounting then passes switch/nterp/JIT SOE, zero handled dumps, and the complete 30/30 runner. FS-1 measures every overflow phase in Release and Debug: native minimum margins are 6784/7536/7616 and 69744/37168/37232 bytes for switch/nterp/JIT. The final-source Linux rebuild, seven-object-probe check, and imageless Hello pass with the unchanged 8192-byte reserve.
- **Required acceptance:** FS-4's authoritative Server 2025 repeat passes
  E9/FS-1/FS-2/FS-3, parameterized guarantee geometry, fiber/manual-stack
  rejection, and join/detach stress. The separate Windows 10 repetition is
  explicitly skipped by policy. Correlate Java post-`FixStackSize()` and
  representative ART pool reservations; preserve unchanged Linux
  `018-stack-overflow` and object-level probe behavior.
- **Rejected designs:** larger clamps or fabricated fallbacks; TEB `StackLimit` as the total low bound; mechanical `mprotect` to `VirtualProtect` replacement; ART protection with `PAGE_GUARD`; fixed `PAGE_NOACCESS` recursive tripwire; direct `EXCEPTION_STACK_OVERFLOW` translation; fibers to emulate arbitrary pthread stacks; E8 `max(prefix, guarantee)` accounting. `SetThreadStackGuarantee` is selected only to reserve native dispatch space and define accounting, never as the managed event itself.
- **Microsoft contracts:** [`IsThreadAFiber`](https://learn.microsoft.com/windows/win32/api/fibersapi/nf-fibersapi-isthreadafiber), [`GetCurrentThreadStackLimits`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentthreadstacklimits), [`SetThreadStackGuarantee`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-setthreadstackguarantee), [`_beginthreadex`](https://learn.microsoft.com/cpp/c-runtime-library/reference/beginthread-beginthreadex), [thread stack size](https://learn.microsoft.com/windows/win32/procthread/thread-stack-size), [`VirtualQuery`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualquery), [`VirtualAlloc`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc), [`VirtualFree`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualfree), [`VirtualProtect`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect), [guard-page behavior](https://learn.microsoft.com/windows/win32/memory/creating-guard-pages), and [`_resetstkoflw`](https://learn.microsoft.com/cpp/c-runtime-library/reference/resetstkoflw).
- **Code anchors:** `vendor/art/runtime/thread.cc` (`FixStackSize`, `GetThreadStack`, `InitStack`, `InstallImplicitProtection`, `ProtectStack`, `UnprotectStack`); `vendor/art/runtime/runtime.cc` implicit-check policy; `vendor/art/runtime/thread_pool.cc`; `compat/src/windows_x64_posix_stubs.c` pthread functions; x86_64 optimizing and nterp stack probes; Windows VEH/runtime hooks; `tests/cases/stack-page-growth/growth_probe.cc`
- **Blocked on / design doc:** no core delivery or stack-budget blocker; only reservation correlation and other optional probes remain; [win32_faults_and_stacks.md](win32_faults_and_stacks.md) is authoritative; [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) records the managed-ABI interaction
- **Opened:** 2026-07-16
- **Updated:** 2026-07-30 — FS-1 natively accepts Release/Debug high-water margins; Windows Debug uses a measured 40-KiB reserve while product and Linux remain at 8192 bytes

### W-017 — openjdk hybrid excludes NIO.2 / async / UNIXProcess; epoll via select
- **State:** OPEN
- **Kind:** workaround / incomplete port
- **Area:** openjdk / nio
- **Current behavior:** Phase B2 builds AOSP NIO channel natives with Winsock CRT-fd shims; `epoll_*` emulated with `select`; NIO.2 UnixNativeDispatcher/WatchService/async EPollPort not registered.
- **Proper fix:** Keep NIO.2 non-goal; deepen channel/options matrix; optional IOCP epoll later if needed.
- **Code anchors:** `overlay/art_port_policy.py` (`libopenjdk` Windows delta); `native/CMakeLists.txt`; `compat/src/windows_x64_socket_posix.c`
- **Opened:** 2026-07-17

### W-026 — Windows SDM timestamp check has one-second granularity
- **State:** OPEN
- **Kind:** workaround / correctness
- **Area:** art / oat / filesystem
- **Symptom / why:** The Windows CRT `stat` surface used by the port does not expose upstream's `st_mtim`. The original port replaced the nanosecond comparison globally with `st_mtime`, weakening Linux and allowing a Windows SDM replaced within the same second to retain the same SDC identity.
- **Current behavior:** Implementation stage 1 restores upstream `st_mtim` behavior on non-Windows. Windows alone constructs a seconds-resolution `timespec` from `st_mtime` so the code still compiles; same-second replacement remains a known gap.
- **Proper fix:** Obtain the SDM modification time from a retained Windows file handle with a documented high-resolution API, use the same normalized value when writing and reading SDC, and add same-second replacement tests. Do not reopen by path after validation.
- **Code anchors:** `vendor/art/runtime/oat/oat_file.cc` (`OpenOatFileFromSdm`); `vendor/art/runtime/dex2oat_environment_test.h` (`CreateSecureDexMetadataCompanion`)
- **Blocked on / design doc:** Stable-handle/cache identity work in [win32_aot_oat.md](win32_aot_oat.md)
- **Opened:** 2026-07-30

### W-027 — Remove encoding-sensitive Win32 `*A` API calls
- **State:** OPEN
- **Kind:** debt / correctness / audit
- **Area:** Windows compatibility / ART runtime / filesystem / diagnostics
- **Symptom / why:** Win32 `*A` APIs decode paths, environment values, and host
  names through the active ANSI code page, while project-facing narrow strings
  are UTF-8. A build, runtime, dump, or DSO path containing non-ASCII text can
  therefore be corrupted even when the same path is valid through the wide API.
- **Current behavior:** The unified managed-runtime gate now converts UTF-8 DSO
  names with `MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, ...)` and calls
  `LoadLibraryW`; its null-module lookups use `GetModuleHandleW`. A preliminary
  source inventory still finds encoding-sensitive `*A` calls for directory
  enumeration, module/current-directory/full-path discovery, environment
  access, computer-name lookup, dump-directory creation, and dump-file opening.
- **Proper fix:** Define one fail-closed UTF-8/UTF-16 boundary helper, replace
  every encoding-sensitive Win32 `*A` call with its `*W` form, convert returned
  UTF-16 text back to UTF-8 explicitly, and add a generated/source audit that
  rejects new `*A` calls whenever a documented `*W` API exists. Byte-oriented
  APIs with no wide equivalent, such as `GetProcAddress`, are outside this
  suffix-pair rule and require their own byte-string contract.
- **Code anchors:** `compat/src/windows_x64_posix_stubs.c`;
  `vendor/art/runtime/multiplatform/windows/runtime_windows.cc`;
  `vendor/art/runtime/multiplatform/windows/cet_compat.cc`
- **Scheduling:** DEFERRED until the active unified build and runtime-gate
  migration builds and runs end to end; do not let this repository-wide audit
  displace the current bring-up work.
- **Blocked on / design doc:** none; finish the unified build/runtime-gate
  migration before expanding this into a repository-wide Windows API change.
- **Opened:** 2026-07-31

## Product leftovers (not single-line workarounds)

_No open product leftovers. Closed L- items live under §Closed._

## Host / validation gaps

### H-001 — Phase 4 re-run on real Windows host
- **State:** CLOSED (2026-07-30 — scoped native subset accepted on Windows Server 2025 build 26100)
- **Kind:** host-gap
- **Gap:** Wine Phase 4 PASS (incl. multiplatform rebuild 2026-07-17). The available native Server 2025 host had not yet rerun the scoped gcstress, threadheavy, handleleak, crash-native, and crash-abort subset.
- **Exit criteria:** Met for the available native host; the sanitized [H-001 result](docs/history/windows_x64_h001_phase4_result.md) records `OVERALL PASS`. The authoritative-host FS-4 repeat is also accepted; the separate Win10/second-host repetition is skipped by policy.
- **Opened:** 2026-07-16

### H-002 — Phase 3 G12 with multiplatform-built PE (not only pre-migration tree)
- **State:** CLOSED (2026-07-30 — authoritative Windows Server 2025 gate selected)
- **Kind:** host-gap
- **Gap:** Authoritative G12 used an earlier host package. FS-4 reran
  E9/FS-1/FS-2/FS-3 and the stack/lifecycle probes on Server 2025 build 26100.
- **Current evidence:** `tools/verify/windows_x64_phase4/evidence/fs4_same_host_20260730/`
- **Exit criteria:** Met under the explicit acceptance policy that treats
  Windows Server 2025 build 26100 as authoritative and skips the separate
  Windows 10/second-host repetition. This closes H-002 within that declared
  scope; it does not claim cross-version coverage.
- **Opened:** 2026-07-17
- **Closed:** 2026-07-30

### H-003 — Wine is not product acceptance
- **State:** OPEN (policy reminder, not a code fix)
- **Kind:** host-gap / process
- **Note:** Keep wine as agent01 oracle; product claims need real Windows for VEH/TEB/network.
- **Opened:** 2026-07-16

### H-004 — Linux-host positive OAT dlopen is skipped on current glibc
- **State:** OPEN
- **Kind:** host-gap / test
- **Gap:** glibc 2.41 and newer reject generated OAT without `PT_GNU_STACK` (`cannot enable executable stack as shared object requires`). `OatFileTest.DlOpenLoad` therefore accepts the error, verifies fallback, and skips its positive `dladdr`/dynamic-anchor assertions on agent01's glibc 2.43.
- **Current coverage:** The new focused cases characterize non-executable fallback, reservation consumption, fd loading, duplicate-instance isolation, SDM/ZIP fallback, VDEX placement, and teardown isolation through `ElfOatFile`. Bionic's positive `ANDROID_DLEXT_FORCE_LOAD`, reserved-address, ZIP-entry, and dynamic-anchor path still requires an Android-target run. H-005 records that this repository's minimal product graph has not executed the focused cases.
- **Exit criteria:** Run the complete OAT stage-1 test set on a matching Android target and either emit an upstream-compatible non-executable `PT_GNU_STACK` for Linux-host OAT or explicitly retain Android as the positive native-loader gate. No skipped result may be reported as positive dlopen coverage.
- **Code anchors:** `vendor/art/runtime/oat/oat_file_test.cc` (`DlOpenLoad`); `vendor/art/libelffile/elf/elf_builder.h`
- **Opened:** 2026-07-30

### H-005 — Minimal product CMake graph does not build ART gtests
- **State:** OPEN
- **Kind:** host-gap / build
- **Gap:** The unified frontend intentionally generates the product dependency closure only. It does not build `art_runtime_tests`, the ART test support libraries, GoogleTest, or the required test jars, so agent01 cannot execute the new canonical OAT characterization tests through the product build.
- **Current coverage:** The complete modified test source passes a production-flag syntax compile using the available test headers and a compatibility definition for the pre-existing `GTEST_SKIP()` use absent from fmtlib's old GoogleTest copy. Linux `art` builds; Windows x64 `oat_file.cc` compiles and `art.dll` links; the rebuilt DLL passes `dalvikvm.exe -showversion` on the authoritative Server 2025 build-26100 host. None of these is behavioral execution of the focused gtests.
- **Exit criteria:** Run the focused `OatFileTest` set with its real test data under AOSP ART host/device infrastructure, or add a maintainable opt-in CMake test closure without adding test-only dependencies to product binaries.
- **Code anchors:** `vendor/art/runtime/oat/oat_file_test.cc`; `vendor/art/runtime/Android.bp` (`art_runtime_tests_defaults`); `tools/build_art.py`; `native/CMakeLists.txt`
- **Opened:** 2026-07-30

---

## Non-goals (do not track as OPEN workarounds)

| Item | Decision |
|------|----------|
| Windows NIO.2 (`sun.nio.fs`) | Non-goal for now ([win32_filesystem.md](win32_filesystem.md)) |
| WSL2 / Wine as product runtime | Rejected |
| Win32 x86 product SKU | Out of scope (x64 first) |
| Full Android framework / zygote / binder | Out of scope |
| PE32+ OAT | Rejected; Windows OAT keeps a restricted ELF64 coat and an ART-owned OAT-only loader ([win32_aot_oat.md](win32_aot_oat.md)) |
| `ProhibitDynamicCode` / ACG ART execution | Unsupported; ART execmem is an explicit product prerequisite, with rejection tested only as a fail-closed negative boundary |
| In-process dual JIT ISA (x64+Arm64EC) | Rejected in TLS/JIT draft |
| CET user shadow stacks / Hardware-enforced Stack Protection | Unsupported for current Win32 ART; all defined incompatible HSP/context-validation fields must be disabled, while `CetDynamicApisOutOfProcOnly` and reserved fields are not treated as HSP enablement ([win32_faults_and_stacks.md](win32_faults_and_stacks.md)) |

If product reopens a non-goal, add an **L-** item and link the decision.

---

## Closed

Summary (details below; do not delete history):

- **W-002** — No managed GS / Thread base on Windows (2026-07-26) — r15 managed-self design, OSR adapters, and attached-thread entry accepted on native Windows R2
- **W-003** — Quick entrypoint SETUP frames and Microsoft XMM boundary (2026-07-26) — all four frame families and XMM6-XMM11 preservation accepted on native Windows R1
- **W-004** — `LOAD_RUNTIME_INSTANCE` direct PE singleton load (2026-07-25) — helper removed; direct same-image load passes structural, Wine, Linux, and native Windows acceptance
- **W-005** — Combined PE JNI stub DLL aliased as libjavacore/libopenjdk/libicu_jni (2026-07-17) — the unified graph builds real PE modules; the raw-link `libcombined` builder and shell stager were retired
- **W-006** — Minimal NativeConverter / ICU version shims (not full ICU4C) (2026-07-17) — product uses real icu_jni NativeConverter + icuuc/icui18n + icudt; the obsolete stub source was deleted
- **W-007** — Classic sockets / poll via Winsock `select` (not full Os/NIO) (2026-07-17) — permanent WinNT design: classic Os sockets use Winsock + **`select()`-based poll/timeouts** (not CRT-fd `WSAPoll`)
- **W-009** — Phase-1 grade `compat` POSIX/pthread stubs (2026-07-17) — hot paths hardened; remaining ENOSYS is intentional Linux-only surface
- **W-011** — Legacy expanded InterpreterJni shorty fallback (2026-07-24) — removed after Wine and native Windows tripwire acceptance; upstream pre-start-only invariant restored
- **W-012** — Legacy InterpreterJni direct JNI resolver (2026-07-24) — removed with upstream `interpreter.cc` restoration
- **W-013** — dlmalloc WIN32 / low-4GB / MORECORE choices for imageless ART (2026-07-25) — accepted design and native Windows R2 closure matrix pass
- **W-015** — openjdkjvm memory exports minimal PE surface (2026-07-17) — product ships comprehensive standalone `libopenjdkjvm.dll`
- **W-016** — ICU needs external `ICU_DATA` / `icudt72l.dat` for wine smoke (2026-07-17) — unified runtime gates stage the pinned data beside each isolated runtime; libicu_jni defaults ICU_DATA to run/icu when unset
- **W-018** — NetProbe StructLinger NPE (getsockopt SO_LINGER incomplete in javacore Win bridge) (2026-07-17) — implemented getsockoptLinger/setsockoptLinger in win_net_natives; NetProbe wine PASS
- **W-019** — Math @CriticalNative / FastNative double ABI on Windows x64 (2026-07-17; superseded 2026-07-24) — historical interpreter DD/DDD workaround replaced by Linux-like entrypoints and restored native Math surface
- **W-020** — FileChannelImpl.map0 pointer truncation on Windows x64 (LLP64) (2026-07-17) — `ptr_to_jlong(mapAddress)` instead of `(jlong)(unsigned long)`
- **W-021** — Default KeyStore type Android-compatible (AndroidCAStore) (2026-07-17)
- **W-022** — Product default CA bundle (AndroidCAStore cacerts) (2026-07-17)
- **W-023** — OkHttp Http(s)Handler on bootclasspath + ASCII IDN/Normalizer multipath (2026-07-17)
- **W-024** — Restore original CriticalNative/FastNative surfaces (2026-07-24) — ABI, binding, tracing, JVMTI, native-host acceptance, upstream fallback cleanup, and default native JIT complete
- **W-025** — Windows x64 JIT memory closure (2026-07-29) — J-1 opt-out and single-view fallback removed; fail-closed J-2-only path passes Wine, Linux, and 36/36 native aggregate records
- **L-001** — Real PE libcore / openjdk / ICU module build (2026-07-17)
- **L-002** — boringssl / conscrypt / SSL PE (2026-07-17) — product TLS stack green under wine (providers + SSLContext.init + HTTPS GET)
- **L-003** — Process/exec, rich locale, zip edge, UDP/IPv6 matrix (2026-07-17)
- **L-004** — Shrink or replace multi-name DLL staging (2026-07-17) — product ships one PE soname each: `libicu_jni`/`libjavacore`/`libopenjdk`/`libopenjdkjvm`/`libcrypto`/`libssl`/`libjavacrypto` (+ `icuuc`/`icui18n`); short-name twins removed from packaging
- **L-005** — Linux multiplatform imageless Hello / boot.jar CI gate (2026-07-17)
- **L-006** — phase1.cmake / generated Win graph pure-vendor consistency (2026-07-17)
- **D-001** — Shared boot.jar via runtime OS selection (2026-07-17)

<!-- keep full CLOSED item bodies for history -->


### W-001 — Force interpreter invoke (quick entrypoints effectively disabled)
- **State:** CLOSED (product default uses quick invoke)
- **Kind:** workaround (removed as product default)
- **Area:** art / invoke
- **Symptom / why:** Windows x64 used to force interpreter invoke until quick path was smoke-validated.
- **Current behavior:** On `_WIN32`, invokable non-proxy methods use `art_quick_invoke_*` (MS entry → SysV body, rSELF=r15) by default, matching Linux. Opt-out with `ART_WINDOWS_X64_QUICK_INVOKE=0` forces `EnterInterpreterFromInvoke`. Debugger/`-Xint` still force interpreter via normal ART paths.
- **Proper fix:** Done for product default. The separate Microsoft-nonvolatile XMM boundary gap was repaired and native-accepted under closed W-003; optional deletion of the env force path remains later cleanup.
- **Code anchors:** `vendor/art/runtime/art_method.cc`; `quick_entrypoints_x86_64.S` Win prologues; [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) §12b / §17.8
- **Blocked on:** n/a (default ON as of 2026-07-19)
- **Opened:** 2026-07-16 (Phase 2)
- **Updated:** 2026-07-19 — product default ON (Linux-like); opt-out `ART_WINDOWS_X64_QUICK_INVOKE=0`

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
- **Evidence transport note:** `<temporary>/w002-r2-log.zip` omitted root `MANIFEST.json` while copying evidence. The host-side `PASS package_integrity` proves it existed and matched during the run; returned `BUILD_INFO.txt`, `SHA256SUMS.txt`, and both structural reports exactly match the issued package, and the exact returned sums record the retained manifest hash. A normalized copy adds only that byte-identical retained manifest and passes the unchanged strict reviewer. No runtime log was changed.
- **Evidence:** [W-002 cross-case analysis](tests/stages/w002/ANALYSIS.md), [OSR/unwind result](tests/cases/osr-unwind/RESULT.md), and [attached-thread result](tests/cases/attached-thread-entry/RESULT.md)
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
- **Emitted-object finding:** With the accepted matched Linux/Windows x64 configuration, the quick PE and ELF objects have the same `int3` distribution: 212 functions and 401 instructions. Remaining traps are shared `UNIMPLEMENTED`/`UNREACHABLE`/read-barrier assertions, not Windows-only SETUP expansions. The checker compares the complete symbol/instruction multiset rather than hard-coding these snapshot totals.
- **Managed/helper ABI:** Quick assembly and JIT retain ART's Linux-shaped managed register convention. Assembly-called C++ helpers use `ART_QUICK_ENTRYPOINT_ABI` (`sysv_abi`) on Windows x64, so SETUP macros do not grow Microsoft shadow space or adopt Microsoft argument registers.
- **Native-boundary repair:** W-003 originally made `art_quick_invoke_stub`, `art_quick_invoke_static_stub`, and `art_quick_osr_stub` reserve a Windows-only 96-byte area for XMM6-XMM11, which is the accepted native R1 contract. The later W-010 exception-unwind work expands only that adapter to 160 bytes and preserves the lower 128 bits of XMM6-XMM15 before managed argument setup or OSR. The area remains outside canonical ART frames, preserves alignment, changes the Windows x64 OSR conceptual CFA to 256, and leaves Linux at 80. Native build 19044 passes all six `fullSelfTestMask=1023` normal-return sentinel runs; exception-unwind repetition remains W-010 work without reopening W-003.
- **rSELF constraint:** r15 remains the live Thread base until each frame publishes `top_quick_frame`. Runtime callee-save frames spill and restore r15 in the shared canonical slot; optimizing Windows x64 code separately reserves r15 rather than allocating it as a general callee-save.
- **Wine and structural evidence:** `check_w003_quick_boundaries.py` verifies all four SETUP source contracts, the three PE save/restore sequences, Linux absence of the Windows save area, and matched PE/ELF trap multisets. The opt-in frame probe is absent from product PE/ELF artifacts and passes 8/8 Wine processes; nterp and threshold-zero JIT each attribute refs-only, refs-and-args, all-callee-saves, and save-everything. The XMM sentinel passes 6/6 Wine processes and returns the exact `0x3f` intentional-clobber self-test mask.
- **Native R1 acceptance:** Windows 10 build 19044 returns exactly 19 PASS records and `OVERALL PASS`. All 14 children exit zero without timeout. The frame matrix passes 8/8; the XMM sentinel passes 6/6 with `mask=0 selfTestMask=63 iterations=128`; JIT logs confirm the corrected pagefile-section J-2 dual view and successful probe compilation; fatal and dump scans pass with `NO_DMP_FILES`. Package metadata and structural reports match the issued package byte for byte.
- **Unwind and W-010 scope:** W-003 closed the frame/XMM ABI defect independently of Windows exception dispatch. Later W-010 substages added emitted PE unwind records to `art_quick_invoke_stub`, `art_quick_invoke_static_stub`, `art_quick_generic_jni_trampoline`, and split OSR entry/return ranges after recursive unwind tracing proved those records are required for fatal dispatch correctness. Dynamic JIT code now has allocation-lifetime runtime-function registration as well. W-010 also owns the full XMM6-XMM15 follow-up, exact VEH/non-owning-`CONTEXT` managed-fault adapter, cooperative VEH/SEH chaining, and the independent nterp implicit-null fault formerly observed at `nterp_op_invoke_virtual+0x3a`; Stage D translates that product path in the dedicated W-010 gate. The W-003 probe still excludes only that implicit-null case and retains class-cast, array-store, and bounds paths; no W-003 product fallback was added.
- **Close bar:** Satisfied: no Windows-only SETUP trap; XMM6–XMM11 preserved at ordinary Microsoft C++-to-managed boundaries; all four frame families have focused attributed Wine and native coverage; Linux frame bodies remain unchanged; and native Windows acceptance passes.
- **Evidence:** [W-003 analysis and historical native acceptance](tests/stages/w003/ANALYSIS.md); [frame-family result](tests/cases/w003-frame-probe/RESULT.md); [XMM-sentinel result](tests/cases/w003-xmm-sentinel/RESULT.md)
- **Code anchors:** `asm_support_x86_64.S`; `quick_entrypoints_x86_64.S`; `callee_save_frame_x86_64.h`; `art_method.cc`; `jit.cc`; `ART_QUICK_ENTRYPOINT_ABI` in `libartbase/base/macros.h` and quick helper declarations
- **Depends on:** W-001 and W-002 are closed prerequisites; W-004 direct Runtime load is closed. W-010 owns the managed-fault and handler-chain work defined in [win32_faults_and_stacks.md](win32_faults_and_stacks.md).
- **Opened:** 2026-07-16
- **Closed:** 2026-07-26 — native R1 19/19 acceptance plus final evidence review


### W-004 — `LOAD_RUNTIME_INSTANCE` direct PE singleton load
- **State:** CLOSED (2026-07-25) — direct same-image load accepted on native Windows 10 build 19044
- **Kind:** resolved assembly ABI debt
- **Area:** art / asm
- **Symptom / why:** The retired Windows macro crossed the Microsoft x64 C ABI merely to read `Runtime::instance_`. It mutated the stack and flags and introduced volatile-register side effects that the Linux/other-ISA data-load macros do not have. The `rcx` destination and later `r11` caller-PC collisions required path-specific repairs; generic JNI also re-materialized `xmm0` after the helper.
- **Current behavior:** Windows x64 directly loads `?instance_@Runtime@art@@0PEAV12@EA` with one same-image RIP-relative `movq`. The accepted RelWithDebInfo objects contain 574 direct `IMAGE_REL_AMD64_REL32` relocations (563 quick, 10 generated nterp, 1 JNI), zero retired helper references, and no helper-specific `r11` or immediate `xmm0` compensation. Linux retains its original two-instruction GOT sequence.
- **Research finding:** `Runtime::instance_` is already explicitly exported/imported by `LIBART_PROTECTED`. With the selected clang GNU driver, lld, and MSVC ABI, a quoted direct reference to `?instance_@Runtime@art@@0PEAV12@EA` assembles as `IMAGE_REL_AMD64_REL32` and links inside `art.dll` to one 7-byte RIP-relative load. Same-image ASLR preserves the displacement. External consumers keep normal `dllimport`/IAT behavior.
- **Implemented proper fix:** Replaced only the Windows macro body with the direct same-image load; deleted `art_Runtime_instance_ptr`, helper-only `Runtime::InstanceLocation()`, and the obsolete helper-specific `r11`/`xmm0` compensations. Explicit dependencies make all five assembly consumers rebuild when shared assembly support changes.
- **Verification:** The live unified source/object/PE reviewer passes on native Windows and a Linux-hosted cross build. Native Windows Server 2025 passes W-003, expanded W-004 26/26, and expanded W-025 9/9 with Ninja no-op repeats; together they supersede the old composite package behavior. The accepted Windows 10 package remains historical evidence: 28 PASS records over 22 child processes with matching metadata/report and no timeout, fatal marker, trace leak, or dump.
- **Important scope:** Dynamically generated JIT code does not use this macro. Do not reuse this same-image RIP-relative sequence for the low-4-GiB JIT cache, which may be more than signed 32-bit reach from `art.dll`; that remains W-025 territory.
- **Rejected permanent designs:** Retaining/hardening the call helper; importing `art.dll` from itself; caching `Runtime*` in `Thread`. A stable C assembly label on the existing member remains the first fallback if maintaining the MS-mangled spelling becomes unacceptable; an exported `Runtime**` address cell is second fallback.
- **Evidence:** [W-004 analysis and historical native acceptance](tests/stages/w004/ANALYSIS.md); current reviewer in `tests/support/windows/check_w004_runtime_load.py`
- **Code anchors:** `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S` (`LOAD_RUNTIME_INSTANCE`); `native/CMakeLists.txt`; `tests/support/windows/check_w004_runtime_load.py`; unified `stage:w004`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-25 — implementation plus structural, Wine, Linux, and native Windows acceptance complete


### W-005 — Combined PE JNI stub DLL aliased as libjavacore/libopenjdk/libicu_jni
- **State:** CLOSED (2026-07-17) — the unified graph builds/stages real PE modules; the raw-link combined stub and shell stager were removed
- **Kind:** workaround
- **Area:** libcore-stub / packaging
- **Symptom / why:** Full ojluni + ICU4C PE ports not built; ART `InitNativeMethods` still dlopens those sonames.
- **Historical behavior:** `libcombined.dll` was copied to six names (`libjavacore.dll`, `libopenjdk.dll`, `libicu_jni.dll`, and short names), exposing about 160 hand-written `Java_*` stubs.
- **Proper fix:** Real PE modules (or fewer real DLLs) from Soong/bp2cmake Windows x64 graph: javacore, openjdk, icu_jni + icuuc/i18n, etc.; stop multi-name aliasing of one stub.
- **Code anchors:** `native/CMakeLists.txt`; `overlay/art_port_policy.py`; historical result `docs/history/windows_x64_libcore_icu_result.md`
- **Opened:** 2026-07-16 (Phase 2; expanded Phase 3)

### W-006 — Minimal NativeConverter / ICU version shims (not full ICU4C)
- **State:** CLOSED (2026-07-17) — product uses real icu_jni NativeConverter + icuuc/icui18n + icudt; the obsolete charset-stub source was deleted
- **Kind:** workaround
- **Area:** icu
- **Current behavior:** the unified graph builds real PE `icuuc.dll`, `icui18n.dll`, and `icu_jni.dll` from AOSP sources; no combined or minimal charset stub remains.
- **Proper fix:** Default package/install to real ICU PE only; remove charset exports from `libcombined`; verify full data (`ICU_DATA` / icudt) vs stubdata; complete L-001 for javacore/openjdk.
- **Code anchors:** `overlay/art_port_policy.py`; historical result `docs/history/windows_x64_libcore_icu_result.md`
- **Opened:** 2026-07-16
- **Progress:** 2026-07-17 — real ICU PE + CoreProbe wine OK with hybrid package

### W-007 — Classic sockets / poll via Winsock `select` (not full Os/NIO)
- **State:** CLOSED (2026-07-17) — permanent WinNT design: classic Os sockets use Winsock + **`select()`-based poll/timeouts** (not CRT-fd `WSAPoll`)
- **Kind:** workaround → **permanent platform design**
- **Area:** libcore-stub / net
- **Symptom / why:** Full AOSP `libcore.io.Linux` PE not used on Windows x64; real Win10 rejected CRT `_open_osfhandle` + `WSAPoll` (`WSAEINVAL` on accept poll).
- **Fix / design:**
  - Product `libjavacore` Win bridge (`win_net_natives.c`) implements classic socket surface with **`select()`** for `poll`, SO_TIMEOUT waits, and connect write-readiness.
  - NIO epoll path similarly select-emulated in `compat/src/windows_x64_socket_posix.c` (bounded `FD_SETSIZE`).
  - 2026-07-17: registered `bind`/`connect` **`SocketAddress`** overloads for `InetSocketAddress` (AF_UNIX still out of product scope).
  - 2026-07-25: removed `_get_osfhandle` + `SO_TYPE` fd probing. Win32 HANDLE and Winsock SOCKET values use independent namespaces and can alias numerically. The permanent design is an explicit process-wide socket-fd registry exported by the already required `libopenjdkjvm.dll`; javacore, openjdk, JVM I/O, NIO, socket/accept/socketpair, dup/dup2, and close paths share it. This is not a temporary heuristic or a disk-backed side channel.
- **Evidence:**
  - Host G12 (2026-07-16): net/dns/goldenapp PASS after select poll fix ([acceptance analysis](tests/cases/windows-libcore-smoke/evidence/windows-x86_64-msvc/g12_acceptance_analysis.md)).
  - Wine (2026-07-17): NetProbe, DnsProbe, UdpProbe, AsyncCloseProbe, GoldenApp, **SocketAddressProbe** PASS.
  - Wine (2026-07-25): native socket/file fd-reuse probe PASS; HandleLeak 5/5; NetProbe, IoProbe, dual-view JIT 12/12, and J-1 Hello PASS.
- **Non-goals residual:** AF_UNIX SocketAddress; full AOSP `libcore_io_Linux.cpp` (L-001 closed with Win bridge map); NIO.2.
- **Code anchors:** `tools/windows_x64/jni_stubs/win_net_natives.c`, `tools/windows_x64/jni_stubs/win_fs_natives.c`, `register_libcore_io_Linux_win.cpp`, `compat/src/windows_x64_socket_posix.c`, `compat/src/windows_x64_socket_fd_registry.c`, `compat/include/mdvm_socket_fd_registry.h`
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
- **Code anchors:** `compat/src/windows_x64_posix_stubs.c`, `compat/include/pthread.h`
- **Focused result:** `tests/cases/pthread-once/RESULT.md`
- **Opened:** 2026-07-16 (Phase 0/1)
- **Closed:** 2026-07-17
- **Updated:** 2026-07-24 — fixed `pthread_once` early-return race exposed by repeated JIT NetProbe

### W-011 — Legacy expanded InterpreterJni shorty fallback
- **State:** CLOSED (2026-07-24) — upstream interpreter fallback restored after Wine and native Windows acceptance
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** ART commit `42a03f2ea0` restores `runtime/interpreter/interpreter.cc` byte-for-byte to `android-16.0.0_r4`. `ArtInterpreterToInterpreterBridge` again enforces the upstream pre-start-only native invariant; runtime-started native calls retain JNI compiler/generated entrypoints under `-Xint`, tracing, and JVMTI.
- **Shared-artifact implication:** Linux and Windows x64 use identical `boot.jar` dex/annotation bytes (`3cbe9a7...`), so no Windows-only boot shorty or native annotation set exists to justify this expansion.
- **Proper fix:** Complete. The interpreter file has exact upstream parity and the complete Linux/Windows x64 post-change matrix passes.
- **Evidence:** `tools/verify/windows_x64_phase4/RESULT-interpreter-jni-fallback.md`; accepted native-host evidence: `tools/verify/windows_x64_phase4/evidence/w024_host/ACCEPTANCE.md`
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc` (`InterpreterJni`, `EnterInterpreterFromInvoke`, `ArtInterpreterToInterpreterBridge`)
- **Opened:** 2026-07-16
- **Closed:** 2026-07-24 — native Windows tripwire acceptance plus final Wine/Linux regression

### W-012 — Legacy InterpreterJni direct JNI resolver
- **State:** CLOSED (2026-07-24) — `ResolveJniEntryPoint` removed with the legacy fallback expansion
- **Kind:** workaround
- **Area:** art / jni
- **Current behavior:** Product and upstream fallback paths use ART's normal registered entrypoint and generated dlsym-stub policy. The Windows x64-only direct resolver no longer exists.
- **Proper fix:** Complete with ART commit `42a03f2ea0`.
- **Evidence:** `tools/verify/windows_x64_phase4/RESULT-interpreter-jni-fallback.md`, `tests/cases/jni-critical-native/RESULT.md`, `tests/cases/jni-native-abi/RESULT.md`, `tools/verify/windows_x64_phase4/evidence/w024_host/ACCEPTANCE.md`
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc`; generated JNI dlsym stubs
- **Opened:** 2026-07-16
- **Closed:** 2026-07-24 — upstream resolver behavior restored

### W-013 — dlmalloc WIN32 / low-4GB / MORECORE choices for imageless ART
- **State:** CLOSED (2026-07-25) — accepted design and native Windows R2 closure matrix pass
- **Kind:** workaround removal / platform-memory design
- **Area:** art / heap
- **Symptom / why:** dlmalloc's standalone Win32 defaults forced mmap-style `VirtualAlloc` growth outside ART's arena, risking Java objects above 4 GiB. The Phase-2 recovery workaround hid `_WIN32`/`WIN32` while including `dlmalloc.c`, preserving ART MoreCore but accidentally changing unrelated platform defaults.
- **Current behavior:** `_WIN32`/`WIN32` remain visible; dlmalloc respects ART's explicit MoreCore-only, mspace-only, externally locked configuration. Each heap and JIT mspace stores its direct owner provider in `malloc_state::extp/exts`; no runtime/global owner scan remains. Windows address policy is explicit, low/aligned allocation uses `VirtualAlloc2` constraints, logical views share whole-allocation ownership, heap page-state operations route through `MemMap`, and discard handles mixed protection including `PAGE_NOACCESS`. Runtime/compiler metadata and the card table use Linux-like anywhere placement while audited object/image/heap/JIT-primary consumers remain low. Executable JIT mspace metadata updates use `ScopedCodeCacheWrite`. Full heap capacity remains initially committed.
- **Accepted design:** ART owns virtual memory; dlmalloc manages chunks inside an owner-attached ART arena. Windows-specific address, protection, discard, and release behavior stays behind `MemMap`.
- **Low-address policy:** Java object spaces, non-moving/LOS, required image/heap ranges, and the JIT primary view remain below 4 GiB. LinearAlloc, compiler/JIT metadata arenas, and the card table are unrestricted after the encoding audit. The source gate pins the remaining required-low inventory.
- **Native acceptance:** R1 on Windows 10 build 19044 found `DiscardVirtualMemory(PAGE_NOACCESS)`, J-1 RX provider-metadata writes, socket-fd namespace aliasing, blank runner accounting, and a nondeterministic marker. ART `6253d01afc` / `27a1ac74a4`, root `c943f1f` / `caad337`, and libcore `67ec4ab8dd70` repaired them. Historical R2 returned 56 PASS, zero FAIL, complete metrics for 52 children, and `NO_DMP_FILES`. Current unified Windows Server 2025 W-013 passes 7/7 and repeats as a Ninja no-op at `--parallel 16`; Linux's exact 128-MiB gate passes 1/1 and repeats as a no-op at `--parallel 32`. The obsolete composite package producer/PowerShell runner is retired.
- **Boundary / non-goal:** Fixed file-view replacement over an ordinary `VirtualAlloc` reservation remains unsupported and unused by the imageless/JIT product path. Any future placeholder-overlay or reserve-only/lazy-commit design is separate work.
- **Code anchors:** `art-dlmalloc.{h,cc}`; `dlmalloc.c` Win32 defaults and `malloc_state::extp/exts`; `dlmalloc_space.cc`; `malloc_space.cc`; `jit_memory_region.cc`; `mem_map.{h,cc}`; `mem_map_windows.cc`; `runtime.cc`
- **Design:** [win32_heap_memory.md](win32_heap_memory.md)
- **Evidence:** `docs/history/windows_x64_w013_result.md`; returned archive SHA-256 `456e297d70c2f166308c869812ddec262fa38bc6dcd2852ea56edd5b2205078e`; external dlmalloc `f3356ce`; ART `8c900a9e4b`, `d011d72d56`, `2fa301a13b`, `9ea15456a2`, `6253d01afc`, `47567cebcc`, `1509b1f95e`, `27a1ac74a4`; root `c943f1f`, `caad337`; libcore `67ec4ab8dd70`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-25 — native Windows R2 acceptance plus final evidence review

### W-015 — openjdkjvm memory exports minimal PE surface
- **State:** CLOSED (2026-07-17) — product ships comprehensive standalone `libopenjdkjvm.dll`
- **Kind:** workaround
- **Area:** art / openjdkjvm
- **Fix / evidence:**
  - The unified `openjdkjvm` target builds the AOSP `OpenjdkJvm.cc` surface,
    while `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc` supplies the
    ART-owned heap/GC and native-load bridge.
  - Added `JVM_ActiveProcessorCount`.
  - Product `JVM_NativeLoad` delegates to `art.dll!ART_LoadNativeLibrary`; the ART-tree helper calls `JavaVMExt::LoadNativeLibrary`, preserving ART library ownership and unresolved JNI lookup.
  - The generated `openjdkjvm.dll` remains the product DSO; no standalone
    replacement source or second product graph is required.
  - The old standalone source remains temporarily because the retained
    libcore/ICU verification and package graph still references it. It is not
    part of the unified product and must be removed with that graph, not first.
  - It also owns the process-wide Windows x64 socket-fd registry because Libcore.os creates sockets in `libjavacore` while java.net stream natives consume them in `libopenjdk`. Reusing this already required bridge avoids a new product DLL and keeps classification exact across module boundaries.
  - Wine CoreProbe/GoldenApp/NetProbe with staged `libopenjdkjvm` PASS.
- **Code anchors:** `vendor/art/openjdkjvm/OpenjdkJvm.cc`;
  `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc`; `native/CMakeLists.txt`
- **Opened:** 2026-07-16
- **Closed:** 2026-07-17

---

### W-016 — ICU needs external `ICU_DATA` / `icudt72l.dat` for wine smoke
- **State:** CLOSED (2026-07-17) — unified runtime gates stage the pinned data as a regular file in each isolated runtime; libicu_jni defaults ICU_DATA to run/icu when unset
- **Kind:** workaround
- **Area:** icu / packaging
- **Symptom / why:** Linked stubdata alone yields `u_init` `U_FILE_ACCESS_ERROR` under wine; full data file works.
- **Current behavior:** Stage `run/icu/icudt72l.dat` and set `ICU_DATA=run/icu` (or absolute path). `Register.cpp` also calls `udata_setCommonData(&U_ICUDATA_ENTRY_POINT)` on Win.
- **Proper fix:** Package full ICU data in the eventual complete runtime package; every current managed runner passes an explicit staged data path.
- **Code anchors:** `vendor/icu/android_icu4j/libcore_bridge/src/native/Register.cpp`; `tests/support/runtime_gate.py`; `native/CMakeLists.txt`
- **Opened:** 2026-07-17
- **Progress:** the historical shell package required the file; the unified shell-free runners now copy it into their output-owned runtime roots and set `ICU_DATA`.

### W-018 — NetProbe StructLinger NPE (getsockopt SO_LINGER incomplete in javacore Win bridge)
- **State:** CLOSED (2026-07-17) — implemented getsockoptLinger/setsockoptLinger in win_net_natives; NetProbe wine PASS
- **Kind:** leftover / bug
- **Area:** libcore-stub / net
- **Symptom / why:** `NetProbe` fails: `StructLinger.isOn()` on null from linger get.
- **Proper fix:** Implement linger get/set in `win_net_natives` / Linux Os bridge returning real `StructLinger`.
- **Code anchors:** `tools/windows_x64/jni_stubs/win_net_natives.c`; NetProbe client path
- **Opened:** 2026-07-17

### W-019 — Math @CriticalNative / FastNative double ABI on Windows x64
- **State:** CLOSED (2026-07-17; workaround superseded 2026-07-24) — Math.ceil/floor/sqrt + HashSet wine passed after interpreter CriticalNative DD/DDD; W-024 now restores Linux-like entrypoints and the native Math surface
- **See also:** **W-024** — Math.ceil/floor and the common ELF/PE registration table are restored; the temporary interpreter shorties were subsequently deleted
- **Kind:** workaround / runtime ABI
- **Area:** libcore Math / ART interpreter JNI (Windows x64 -Xint)
- **Historical root cause:** Official AOSP CriticalNative is fine on Linux quick/generic-JNI. Windows x64 multipath formerly forced `ArtMethod::Invoke` through the interpreter; `InterpreterJniGeneric` only handled CriticalNative shorties `II`/`I`/`Z`/`ZI`. `Math.ceil` is shorty `DD` (`(D)D`), so dispatch fell through and crashed. Secondary: registering `Math_*_jni(JNIEnv*,jclass,jdouble)` under CriticalNative is the wrong ABI.
- **Historical fix:** interpreter CriticalNative `DD`/`DDD`/`FF`/`J`; `Math.c` `gMethodsWin` → `Math_ceil(jdouble)` etc.; posix stubs for the ART rebuild. W-024 removed `gMethodsWin`, restored ceil/floor native declarations, stopped routing native methods through the Windows-only interpreter detour, and finally deleted the temporary shorties.
- **Exit criteria:** `MathProbe` + `SslProviderProbe` wine PASS with rebuilt `art.dll`.
- **Code anchors:** `vendor/art/runtime/interpreter/interpreter.cc`, `vendor/libcore/ojluni/src/main/native/Math.c`, `compat/src/windows_x64_posix_stubs.c`
- **Opened:** 2026-07-17
- **Progress:** 2026-07-17 — root cause + source fix; full art PE rebuild running

### W-020 — FileChannelImpl.map0 pointer truncation on Windows x64 (LLP64)
- **State:** CLOSED (2026-07-17) — `ptr_to_jlong(mapAddress)` instead of `(jlong)(unsigned long)`
- **Kind:** bug / ABI
- **Area:** openjdk NIO / boot classpath ZIP mmap
- **Root cause:** AOSP `FileChannelImpl_map0` returned `(jlong)(unsigned long)mapAddress`. On Windows x64 LLP64 `unsigned long` is 32-bit, so mapped addresses like `0x6ffff…` were truncated (high bits zeroed). `Memory.peekByteArray` then crashed in CRT (`fault_addr=0xff0e0eec` pattern) while `VMClassLoader` clinit mapped `boot.jar` for `ClassPathURLStreamHandler`.
- **Symptom chain:** `Security.getProviders` → provider class load → `BootClassLoader.loadClass` → `findLoadedClass` path / resource handlers → ZIP mmap via NIO → AV. Earlier W-019-style AV signature was coincidental.
- **Historical supporting workaround:** Windows x64 `-Xint` once forced natives through `InterpreterJni` and kept FastNative Runnable. W-024 removed that Windows-only branch after the real JVMTI transition passed through Linux-like JNI entrypoints; the old detour aborted on mixed shorty `DJDIF`. The temporary interpreter shorties were deleted after native-host acceptance.
- **Exit criteria:** SecStep17 `BootClassLoader.loadClass` + SecStep3 `Security.getProviders` wine PASS.
- **Code anchors:** `vendor/libcore/ojluni/src/main/native/FileChannelImpl.c`; `vendor/art/runtime/interpreter/interpreter.cc`; `interpreter_common.cc`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### W-021 — Default KeyStore type Android-compatible (AndroidCAStore)
- **State:** CLOSED (2026-07-17)
- **Kind:** config / compatibility
- **Area:** JCA / conscrypt SSL defaults
- **Root cause:** Windows x64 multipath deferred BouncyCastle, so `keystore.type=BKS` could not resolve. `Security.initializeStatic()` also omitted `keystore.type`, so `KeyStore.getDefaultType()` fell back to desktop `jks`, which is not registered. `KeyManagerFactory.init(null,null)` → `KeyStore.getInstance("jks")` failed and `SSLContext.init` aborted.
- **Fix:** default `keystore.type=AndroidCAStore` (HarmonyJSSE/`TrustedCertificateKeyStoreSpi`, empty-loadable); restore loading `security.properties` on Windows after W-020; mirror in `build_conscrypt_windows_x64.sh` and boot.jar resource.
- **Exit criteria:** KeyStoreProbe + SslProviderProbe `sslcontext.init=ok` under wine.
- **Opened/Closed:** 2026-07-17

### W-022 — Product default CA bundle (AndroidCAStore cacerts)
- **State:** CLOSED (2026-07-17)
- **Kind:** packaging / product asset
- **Area:** TLS trust / AndroidCAStore
- **Root cause:** Android `TrustedCertificateStore` reads `$ANDROID_ROOT/etc/security/cacerts/<subject_hash_old>.N`. Product previously shipped empty dirs, so SSLContext.init worked but trust set was empty.
- **Fix:** generate Mozilla/system PEM bundle into OpenSSL hash_old layout (`tools/windows_x64/generate_cacerts.sh`), hermetic assets under `tools/windows_x64/assets/cacerts`, stage via `stage_run_assets.sh` as required asset (with `boot.jar` / `icudt72l.dat`). LocaleData hard-coded fallback so OpenSSLX509Certificate date parsing works without full ICU4J resource bundles in boot.jar.
- **Exit criteria:** TrustStoreProbe AndroidCAStore.size>=50 and acceptedIssuers>=50 under wine with ANDROID_ROOT=run.
- **Opened/Closed:** 2026-07-17

### W-023 — OkHttp Http(s)Handler on bootclasspath + ASCII IDN/Normalizer multipath
- **State:** CLOSED (2026-07-17)
- **Kind:** packaging / compatibility
- **Area:** java.net URL / HTTPS
- **Root cause:** Android resolves `http/https` via `com.android.okhttp.HttpHandler`/`HttpsHandler`, not packaged in multipath boot.jar. After packaging, pure-ASCII OkHttp/TLS paths still required ICU4J StringPrep/Normalizer tables not present in boot.jar.
- **Fix:** `tools/bootjar/build_okhttp_windows_x64.sh` merges repackaged OkHttp+okio into boot; `IDN.toASCII` and `java.text.Normalizer` short-circuit pure-ASCII; product ICU data preferred over stub in `libicu_jni` Register.cpp; cacerts already staged.
- **Exit criteria:** HttpsProbe handler resolution + `https://example.com/` status 200 under wine.
- **Opened/Closed:** 2026-07-17

### W-024 — Restore original @CriticalNative / @FastNative surfaces after JIT/TLS/entrypoints
- **State:** CLOSED (2026-07-24) — surfaces, ABI, transitions, native-host acceptance, and cleanup complete
- **Kind:** compiler/runtime ABI repair and retired diagnostic workarounds
- **Area:** art / libcore / JNI ABI
- **Symptom / why:** Official AOSP libcore marks many natives `@CriticalNative` or `@FastNative` (Math/StrictMath were **@FastNative → @CriticalNative** in AOSP; see libcore `d021f1d8475c`). The concrete compiler/stub ABI defects, transition coverage, product demotions, native-host validation, diagnostic gate, and defensive interpreter fallbacks are now resolved:
  1. **Fixed:** the compiled-JNI adapter now keeps incoming ART-managed registers separate from outgoing Microsoft x64 native registers.
  2. **Fixed:** optimizing direct CriticalNative calls now use unified Microsoft x64 ordinals, reserve the 32-byte shadow area, and spill after it. The original W-024 repair also preserved the unresolved dlsym caller PC across the then-current PE `r11` scratch use; W-004 later removed both the helper scratch and that local reload.
  3. **Fixed/covered:** mixed-signature unresolved app-JNI CriticalNative dlsym calls now resolve through ART's native-library registry and pass with core/FP, stack-spilled, and scalar-return shapes.
  4. **Fixed/covered:** mixed/high-FP compiled normal/FastNative stubs now pass for registered and unresolved app JNI, static and instance methods, references, six managed FP ordinals, unified Windows x64 slots, deep stack spills, and double returns.
  5. **Fixed/covered:** already-compiled normal/FastNative thunks survive class-wide `UnregisterNatives`, dlsym re-resolution, and a second `RegisterNatives` table without recompilation.
  6. **Fixed/covered:** method tracing switches the runtime `0 -> active -> 0`; all alternate normal/FastNative bindings execute during and after tracing with no extra target compile records and no trace file left behind.
  7. **Fixed/covered:** registered and unresolved CriticalNative mixed/spilled/scalar calls pass during and after method tracing in both J-1 and dual-view modes, with tracing mode restored and no trace file left behind.
  8. **Fixed/covered:** a separate Windows x64 `openjdkjvmti.dll` and thread-scoped single-step agent exercise ART's real force-interpreter/deoptimization transition. Registered and unresolved normal, FastNative, and CriticalNative calls pass 3/3 in both memory modes.
  9. Interpreter JNI historically lacked full CriticalNative shorty coverage (partially papered by **W-019** for Math `DD`/`DDD`/…). That fallback was never proof of quick/direct parity and has now been removed.
  10. **Fixed:** **Math.ceil / Math.floor** are native `@CriticalNative` methods again; the pure-Java `ART-WinNT` stand-ins are removed.
  11. **Fixed:** `Math.c` uses one common ELF/PE registration table with ceil/floor included; the Windows wrappers, `_WIN32` branch, and `gMethodsWin` are removed.
- **Current behavior:**
  - Math/StrictMath/etc. annotations remain intact, and **ceil/floor are native CriticalNative methods**. An audit of local Windows x64 libcore commits and `ART-WinNT` markers found no other CriticalNative/FastNative Java demotion.
  - Noncompiled Java callers use ART's normal quick/critical native entrypoint plumbing. The Windows x64 interpreter shorty expansion and direct resolver are deleted; the interpreter file matches `android-16.0.0_r4` exactly.
  - Forced interpretation now matches Linux ART: Java callers enter the interpreter while native methods retain JNI compiler/generated entrypoints. The former Windows-only native `InterpreterJni` detour was removed; it aborted on the mixed `DJDIF` probe shorty.
  - The compiled-JNI convention split and XMM-to-XMM argument moves are implemented. The focused normal/FastNative matrix passes with 7/7 distinct JNI thunk targets compiled, exact mixed/high-FP values, and exactly seven compile records across initial, unregistered/dlsym, and re-registered bindings.
  - The default native-compilation matrix also starts and stops non-sampling method tracing. Tracing mode changes `0 -> 1 -> 0`; all normal/FastNative methods pass during and after tracing; the temporary trace file is deleted; and the target compilation record count remains seven.
  - The CriticalNative harness also traces both registered direct calls and unresolved exported-symbol calls in J-1 and dual-view modes. Exact values pass during and after tracing, mode changes `0 -> 1 -> 0`, and no trace output remains.
  - JIT compilation of native methods follows the common ART policy by default. The `ART_WINDOWS_X64_JIT_NATIVE` exclusion/override is removed; calling convention, native binding, method-tracing, JVMTI forced-interpreter transitions, product surfaces, and native-host validation all pass.
  - `FloatProbe -Xjitthreshold:0` now passes repeatedly through the unresolved direct `System.currentTimeMillis()` / `System.nanoTime()` path in both J-1 and dual-view modes.
  - `CriticalNativeDlsymProbe` passes unresolved mixed core/FP, more-than-four-argument, stack-spilled, and scalar-return calls in both modes. The harness covers `System.loadLibrary`, absolute `System.load`, and a semicolon-separated public library path.
  - No threshold-zero, Math, native-JIT gate, or interpreter-JNI product workaround remains. Per-method compile records stay opt-in through `ART_WINDOWS_X64_JIT_LOG_COMPILES=1`.
- **Threshold-zero investigation and resolution (2026-07-24):**
  1. `GetCriticalNativeDirectCallFrameSize("J")` correctly returned 32 on Windows x64, while the old optimizing direct-call visitor reported zero and emitted no `sub rsp, 32`.
  2. The dlsym stub therefore positions its 208-byte SaveRefsAndArgs frame 32 bytes too high; the walker reads caller spill data (`0x0000000100000001`) as the next `ArtMethod*`.
  3. Adding the missing 32-byte outgoing area corrected the walk and exposed the `LOAD_RUNTIME_INSTANCE` `r11` clobber, which made native return execute `Runtime*`.
  4. The final visitor and its original local `r11` reload landed together. W-004 later replaced the helper with a direct same-image data load and removed the now-unnecessary reload. The combined acceptance harness passes 5/5 threshold-zero runs in each memory mode; earlier focused repetitions also passed 10/10 in each mode.
  5. `CriticalNativeProbe` adds registered direct-call coverage for zero, FP-only, mixed integer/FP, stack-spilled arguments, and scalar returns. It passes 5/5 in each memory mode.
  6. The first unresolved mixed probe returned zeros because the old Windows x64 `Runtime.nativeLoad` shortcut called `LoadLibraryA` and `JNI_OnLoad` without registering the DLL in `JavaVMExt::libraries_`. `JVM_NativeLoad` now delegates to `art.dll!ART_LoadNativeLibrary` and `JavaVMExt::LoadNativeLibrary`, matching AOSP ownership.
  7. Host `OpenNativeLibrary` now recognizes Windows drive, root, and UNC absolute paths. Its internal search list intentionally remains colon-separated because `BaseDexClassLoader.getLdLibraryPath()` normalizes the platform-facing semicolon list to that ART contract.
- **Compiled-JNI / FastNative research (2026-07-24):**
  1. ART's managed x86-64 call ABI is intentionally unchanged on Windows: `RDI` carries `ArtMethod*`; Java core arguments use `RSI/RDX/RCX/R8/R9`; floating arguments use `XMM0..XMM7` with a separate FP sequence. The optimizing managed code generator still emits exactly that convention.
  2. ART commit `f87f5de9d3` correctly added the outgoing Microsoft x64 JNI convention, but its Windows x64 `kCoreArgumentRegisters` and `kMax*RegisterArguments` were also consumed by `X86_64ManagedRuntimeCallingConvention`. The old stub read the first Java core argument from `RDX` instead of `RSI`, permitted only three Java core register arguments after the method register, and treated managed FP arguments after `XMM3` as stack values.
  3. For `StringFactory.newStringFromBytes(byte[],int,int,int)`, managed `RSI` holds `data` and `RDX` holds `high == 0`; the bad stub reads `RDX` as `data`, producing `NullPointerException: data == null`. For `System.arraycopy(Object,int,Object,int,int)`, the same shift reads `srcPos == 0` from `RDX` as `src`, producing `src == null` or an immediate invalid-reference fault.
  4. A filtered Wine run compiled only `System.arraycopy` and then failed before the probe success marker; with the native-method gate closed, the same probe exits 0. The older Hello T5 was a false-positive because it searched for the greeting even when `main end exception=1` followed it.
  5. The managed/native register-table split is now implemented. Filtered `System.arraycopy` PerfSmoke and unrestricted native-gate-open Hello with compiled `StringFactory.newStringFromBytes` pass.
  6. The expanded probe initially failed compilation at `Move XMM: 3, XMM: 0 unimplemented`. Its first managed FP argument arrives in `XMM0` but, after the two JNI implicit arguments and a core argument, must occupy unified Windows x64 native slot 3 in `XMM3`. `X86_64JNIMacroAssembler::Move()` now emits `movss`/`movsd` for XMM-to-XMM moves, with a focused assembler regression test.
  7. Unified `managed_native_abi` builds the dedicated PE DLL and covers registered/unresolved normal and FastNative calls, static/instance methods, references, five managed core and six managed FP ordinals, extensive stack spills, and double returns. The gate-open run compiles 7/7 distinct targets and the gate-closed control compiles 0/7; five complete focused runs passed.
  8. The expanded probe then calls `UnregisterNatives` on the compiled class, verifies dlsym phase values, installs a second six-method `RegisterNatives` table, and verifies alternate phase values. Exactly seven target compile records are permitted, proving the transitions reuse the existing compiled thunk set. Five complete transition runs passed.
  9. A third gate-open process enables method tracing through `VMDebug`, verifies tracing mode and exact values during/after tracing, deletes the trace output, and still observes exactly seven target compile records. Five complete instrumentation runs passed.
  10. The CriticalNative harness now repeats registered and unresolved mixed/spilled/scalar suites during and after method tracing in both memory modes. The default matrix passes 3/3 instrumentation runs per mode with explicit trace cleanup.
  11. The Windows x64 `openjdkjvmti` target builds all 29 upstream translation units as a separate plugin DLL. The JVMTI probe enables thread-scoped single-step, observes events only while enabled, and preserves exact values across registered/unresolved normal, FastNative, and CriticalNative calls in three runs per memory mode.
  12. PE cannot import C++ `thread_local` data, so optional ART plugins call an exported `Thread::CurrentFromGdb()` accessor while `art.dll` retains the direct TLS fast path. Explicit PE data annotations are limited to the zero-initialized ART runtime fields actually consumed by the plugin.
  13. Math.ceil/floor are restored to the exact pre-`f16cd44db5fe` source state. The shared Math registration table is also restored exactly; Windows x64 and Linux rebuild from the same source.
  14. `MathCriticalProbe` verifies native modifiers, 23 direct and reflective edge cases, signed-zero bits, 2,000 repeated calls, and source-level absence of `gMethodsWin`. The maintained case-local Python matrix runs `-Xint` and threshold-zero JIT twice for each exact Linux/Windows x86-64 target; native Windows requires a matching compile record. It passes twice in unified native Windows W-004 and in the fresh Linux W-004 build. The earlier 3/3 dual/J-1/Wine and shared-boot results remain historical evidence.
  15. Windows x64 ZipProbe/HashMap and conscrypt SslProviderProbe pass after restoration; Linux ZipProbe/HashMap and L-005 pass. The Linux converter does not currently build `libjavacrypto.so`, which is a native-module packaging difference rather than a boot-jar or CriticalNative blocker.
  16. Per-method `Windows x64 CompileMethod done` output is now opt-in. Log-dependent harnesses explicitly set `ART_WINDOWS_X64_JIT_LOG_COMPILES=1`; JIT smoke verifies a normal quiet product run.
  17. The opt-in fatal-tripwire build disabled both runtime-started `InterpreterJni` call sites. Windows x64 `-Xint`, direct/unresolved CriticalNative, normal/FastNative, method tracing, and JVMTI forced interpretation all passed under Wine; Clang reported `InterpreterJni` unused. The then-product-default OFF build and final controls passed before the option was retired. See `RESULT-interpreter-jni-fallback.md`.
  18. Because Linux and Windows x64 use identical boot.jar dex/annotation bytes, there is no Windows-only boot-native shorty set. This removed the final rationale for retaining the gate or fallback expansion; both were deleted after acceptance.
  19. The complete fatal-tripwire package passes all nine cases on Windows 10 Enterprise LTSC 2021 build 19044. Both normal/FastNative runs compile 7/7 required targets exactly once; both JVMTI runs compile the two allowed targets and no CriticalNative target; no tripwire or crash dump is observed.
- **Proper fix:**
  1. **Landed this stage:** split the JNI compiler's incoming managed convention from its outgoing native convention. The managed side remains identical to Linux ART (`RDI` method, five core Java argument registers, eight FP registers); Microsoft unified four-slot rules are used only for native destinations, out-frame sizing, and native-call scratch registers.
  2. **Landed this stage:** give the two sets of arrays and limits explicit managed/native names and add the missing XMM-to-XMM move support. The existing Windows x64 shadow/stack calculation now passes independent mixed FP/core and unresolved normal/Fast app-JNI coverage.
  3. **Landed this stage:** add compiled-JNI tests for static and instance methods, references, mixed core/FP ordinals, more than four total native arguments, more than four managed FP arguments, unresolved lookup, and returns. `FastNativeAbiProbe` now requires 7/7 default native compilation.
  4. **Landed this stage:** cover class-wide unregister/dlsym/re-register transitions without recompiling the already-compiled normal/FastNative targets.
  5. **Landed this stage:** cover non-sampling method-tracing entrypoint transitions for all compiled normal/FastNative targets during and after tracing, with explicit trace cleanup.
  6. **Landed this stage:** cover registered and unresolved CriticalNative calls during and after method tracing in both memory modes.
  7. **Landed this stage:** cover full JVMTI forced-interpreter transitions with thread-scoped single-step across registered/unresolved normal, FastNative, and CriticalNative calls in both memory modes.
  8. **Landed this stage:** add a Windows x64 branch to `CriticalNativeCallingConventionVisitorX86_64` using unified four-slot Microsoft x64 registers, a 32-byte shadow area, and stack arguments after it.
  9. **Landed this stage:** initialize the visitor stack offset with the shadow area so spilled arguments cannot overlap the home area.
  10. **Historically landed, later retired by W-004:** preserved the unresolved-stub caller PC across the old helper-based `LOAD_RUNTIME_INSTANCE` by reloading it from the existing saved return-PC slot on Windows. The direct same-image load no longer clobbers `r11`, so the reload is absent from current source.
  11. **Landed and native-host accepted:** add direct-call tests for unresolved `()J`, registered FP-only/mixed/spilled signatures, and unresolved exported mixed-signature dlsym calls.
  12. **Landed this stage:** restore **every identified** multipath Java demotion of methods originally `@CriticalNative` / `@FastNative`; Math.ceil/floor are native + `@CriticalNative` again.
  13. **Landed this stage:** re-register Math natives through one common ELF/PE table with AOSP-correct CriticalNative function pointers.
  14. **Landed:** Linux-like CriticalNative/FastNative entrypoints are the product path, the dual `gMethodsWin` table is deleted, and the PE interpreter shorty expansion is removed.
  15. **Landed this stage:** audit local Windows x64 libcore commits and `ART-WinNT` markers for other pure-Java / ABI demotions; none remain after Math ceil/floor restoration.
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
  - Math native modifiers and edge behavior pass the maintained two-repeat `-Xint`/threshold-zero-JIT matrix on native Windows and Linux x86-64. The live W-004 reviewer enforces the native declarations and common registration table on native and cross hosts; earlier shared-boot Wine results remain historical evidence.
  - Windows x64 Math/HashMap/conscrypt and Linux Math/HashMap/shared-boot smokes pass. Linux conscrypt is unavailable only because the converter graph has no `libjavacrypto.so` target.
  - The Wine fallback-reachability tripwire matrix passed without entering runtime-started `InterpreterJni`; the then-product-default OFF restoration and final Windows x64/Linux controls passed before the option was retired.
  - The native Windows 10 tripwire matrix passes all nine cases with exact required native compilation records, no fatal marker, and no crash dump.
  - ART commit `42a03f2ea0` restores upstream interpreter parity and removes the native-JIT gate.
  - The final Windows x64 build passes default native ABI 7/7, CriticalNative, JVMTI, Math, JIT smoke 12/12, JIT matrix 14/14, and all Phase 4 Wine gates.
  - The full Linux build passes L-005 shared-boot Hello and Math `-Xint`/JIT controls.
- **Code anchors:**
  - `vendor/art/compiler/optimizing/code_generator_x86_64.{h,cc}` (`CriticalNativeCallingConventionVisitorX86_64`, `PrepareCriticalNativeCall`)
  - `vendor/art/compiler/jni/quick/x86_64/calling_convention_x86_64.cc` (incoming managed vs outgoing native convention split)
  - `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc` and `assembler_x86_64_test.cc` (XMM-to-XMM argument moves)
  - `vendor/art/runtime/arch/x86_64/jni_frame_x86_64.h` (Windows x64 shadow size and direct-call frame calculation)
  - `vendor/art/runtime/arch/x86_64/jni_entrypoints_x86_64.S` (`art_jni_dlsym_lookup_critical_stub`)
  - `vendor/art/runtime/arch/x86_64/asm_support_x86_64.S` (current direct `LOAD_RUNTIME_INSTANCE`; the Windows x64 `r11` scratch was retired by W-004)
  - `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc` (`ART_LoadNativeLibrary` bridge)
  - `vendor/art/libnativeloader/native_loader.cpp` (Windows absolute paths; internal colon-separated search contract)
  - `vendor/libcore/ojluni/src/main/java/java/lang/Math.java` (restored native CriticalNative ceil/floor)
  - `vendor/libcore/ojluni/src/main/native/Math.c` (one common ELF/PE registration table)
  - `vendor/art/runtime/interpreter/interpreter.cc` (exact `android-16.0.0_r4` parity)
  - `tests/cases/jni-native-abi/` (canonical source/result) plus unified `managed_native_abi`
  - `tests/cases/jni-critical-native/` (canonical source/result) plus unified `managed_critical_native`
  - `tests/cases/jvmti-force/` plus the transitional managed runner and historical result under `tools/verify/windows_x64_phase4/`
  - `tests/cases/math-critical/` (canonical source, shell-free runner, and adjacent result) plus the live W-024 cleanup audit in `tests/support/w024_cleanup.py`
  - `tools/verify/windows_x64_phase4/RESULT-interpreter-jni-fallback.md` (accepted Wine and native-Windows tripwire reachability audit)
  - `tools/verify/windows_x64_phase4/W024_HOST_CHECKLIST.md` (native Windows 10 acceptance and returned-evidence procedure)
  - `vendor/art/openjdkjvmti/` and `native/CMakeLists.txt` (separate Windows x64 JVMTI plugin)
  - `vendor/art/runtime/{thread-current-inl.h,thread.h,interpreter/interpreter_common.cc}` (PE plugin TLS accessor and Linux-like native interpreter policy)
  - `vendor/art/runtime/jit/jit.cc` (common native compilation policy and opt-in compile-record diagnostics)
  - `vendor/art/openjdkjvm/OpenjdkJvm.cc` and
    `vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc` (`JVM_NativeLoad` and
    `ART_LoadNativeLibrary` product boundary)
  - AOSP history: `d021f1d8475c` FastNative→CriticalNative Math; multipath `f16cd44db5fe` pure-Java ceil/floor; `b9265e7b5da6` CriticalNative register fix; art `7ea144b073` / `4c17423714` interpreter Critical/FastNative bridge
- **Closed by:** ART `42a03f2ea0`; native Windows evidence under `tools/verify/windows_x64_phase4/evidence/w024_host/`; final historical regressions on 2026-07-24; unified Linux/Windows W-004 acceptance on 2026-08-01
- **Related:** W-019 (CLOSED temporary Math ABI fix), W-011/W-012 (legacy InterpreterJni fallback), W-025 (JIT memory; threshold-zero proved unrelated)
- **Opened:** 2026-07-17
- **Closed:** 2026-07-24 — upstream interpreter scope and default native-JIT policy restored after complete native-host and post-change regression acceptance

### W-025 — JIT code cache + x86_64 codegen TLS (Windows)
- **State:** CLOSED (2026-07-29) — JIT-5 removed J-1 and passed post-removal Wine, Linux, and native Windows closure gates
- **Kind:** resolved host-validation gap / removed diagnostic workaround
- **Area:** art / jit / compiler
- **Symptom / why:** The corrected path reproduces ART's Linux-visible `[data R][code RX]` contiguous primary layout with a coherent RW updater alias. JIT-1 completed direct encoding checks, JIT-2 mapping/backing/pressure/policy acceptance, JIT-3 collection/reuse plus concurrent unwind sampling, JIT-4 the final pre-removal default regression, and JIT-5 removal plus post-removal Windows/Wine/Linux acceptance. Threshold zero was resolved separately under closed W-024.
- **Current behavior:**
  - **Default corrected dual view:** one unnamed `CreateFileMappingW(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE)` section is mapped twice at offset zero. The complete primary view is below 4 GiB and split into data R plus code RX; the unrestricted alias is split into data RW plus code RW.
  - **Shared ART path:** mspace initialization, growth, address translation, commit, collection, and metadata handling remain on ART's common Linux/Windows path after mapping construction.
  - **Removed J-1 diagnostic workaround:** ART `389158d46f` removes the `ART_WINDOWS_X64_JIT_DUAL` read and prevents Windows from entering the executable single-view `VirtualAlloc` path. Section creation or partial view construction now fails closed. The retired key is inert.
  - **No disk file:** the section is unnamed and backed by the Windows paging system; no temporary filesystem object, pseudo-fd, or Windows memfd emulation is created.
  - **Native JIT-2 acceptance:** Windows Server 2025 build 26100 passes nine child cases and 14 aggregate checks at 64 MiB and 1 GiB. Low-VA failure/recovery, 1 GiB `SEC_COMMIT`, and standalone/ART CFG execution pass. The `ProhibitDynamicCode` child proves clean rejection of J-2/J-1 executable operations with no dump or JIT temporary file; it is negative evidence for an unsupported policy, not a supported runtime mode.
  - **Native JIT-3/FS-3 acceptance:** four build-26100 J-2/J-1 processes pass nine aggregate checks across 52 collections, 1,344 optimizing/JNI compilations, 1,248 exact address reuses, 696,929 stable-live lookups, 5,909,811 stable-dead lookups, and 696,969 successful virtual unwinds. Missing-live, stale-dead, and unwind-failure counts remain zero; no callback table, dump, trace, or JIT temp is present.
  - **Native JIT-4 acceptance:** 28 build-26100 default-J-2 cases pass 34/34 aggregate records across the exact 12-record smoke, 14-workload matrix, two JIT-disabled controls, default native ABIs, nterp/switch OSR, eight lifecycle cycles, and static/JIT/OSR fatal origins. The three dumps are valid, `jit-temp` is empty, no trace remains, and no J-1 arm runs. This authorizes JIT-5 removal but does not claim J-1 is already removed.
  - **Native JIT-5 acceptance:** 29 build-26100 cases pass 36/36 aggregate records after removal. Source and rebuilt `art.dll` lack the opt-out/fallback strings; setting the retired key to zero still creates J-2 and compiles Hello. Eight lifecycle cycles complete 216 compilations, 192 exact reuses, and 120,654 virtual unwinds with zero missing/stale/failed records. Static/JIT/OSR fatal origins create three valid dumps; `jit-temp` is empty and no trace remains.
  - **nterp hard-float correction:** the JIT-3 preflight showed normal JNI returns had the correct float/double in XMM0 while RAX held the Native-to-Runnable state value `0x5c000000`. The Windows nterp epilogue incorrectly copied RAX into XMM0. ART `43f866830e` restores XMM0 as the authoritative hard-float result, and all eight JNI lifecycle targets now return exact values.
  - **Historical separated-view defect:** the retired layout placed code far from roots and stack maps, overflowing signed 32-bit JIT-root displacements and uint32 CodeInfo distance. The corrected topology removes that layout.
  - **Threshold-zero stress:** resolved outside memory topology. The direct `@CriticalNative` path has Windows x64 shadow/unified-argument handling. W-024 originally added a caller-PC reload around the helper-based runtime load; W-004 subsequently replaced that helper with a direct load that does not clobber `r11` and removed the reload. Repeated J-1 and dual-view acceptance passes; W-024 is closed.
  - Native methods follow the common ART JIT policy by default. The 7/7 mixed/high-FP normal/FastNative matrix passes across rebinding and tracing; the separate CriticalNative suite passes tracing in both memory modes; the JVMTI forced-interpreter matrix passes 3/3 per mode; and restored Math CriticalNative passes dual/J-1/-Xint plus Linux controls.
- **Implemented proper fix:** Keep ART's observable layout and post-mapping JIT logic Linux-like while containing the Windows difference in the section-allocation helper:
  1. Require Windows 10 version 1803 or later and link `onecore.lib` for `MapViewOfFile3`.
  2. Create one unnamed pagefile-backed section and map the two complete views described above.
  3. Split both views logically into ART's four existing ranges without a placeholder unmap/remap transaction or Windows-only 64 KiB capacity rule.
  4. Use explicit Windows `FlushInstructionCache` and `VirtualQuery` layout/protection checks.
  5. Keep the common ART mspace and JIT lifecycle code unchanged after mapping construction.
  6. Remove the temporary opt-out and Windows single-view branch, fail closed on section construction errors, and accept post-removal Windows/Wine/Linux regressions. Completed by JIT-5.
- **Why full views:** Both mappings start at section offset zero, so custom JIT maximum sizes need only ART's existing page alignment. This avoids a Windows-only 64 KiB divider rule and avoids placeholder split/remap rollback.
- **Backing-store rule:** The selected section is backed by the Windows paging system, not by a named or temporary filesystem file. Native JIT-2 observes a 1,075,838,976-byte commit delta for the 1 GiB `SEC_COMMIT` case and accepts both mapped views.
- **Rejected fixes:** moving stack maps alone (does not fix root loads); Win-only far-root codegen plus an extended header; moving all method metadata into the code arena; forcing every alias below 4 GiB.
- **Safety checks:** mapping-time contiguity, low-4-GiB placement, logical sizes, and R/RX/RW protection roles are implemented and native-accepted at 64 MiB and 1 GiB. ART `146016f83e` checks every signed-int32 JIT-root displacement and uint32 CodeInfo construction before mutation; deterministic boundary/overflow tests and the post-change native W-004 regression pass.
- **Separate residual:** None for W-025. CET user shadow-stack support is not W-025 work: it is an explicit non-goal, and the process must run with HSP disabled under W-010's activation contract.
- **Code anchors:** `mem_map_windows.cc` constrained section mapping; `mem_map.cc` Windows in-place split ownership; `jit_memory_region.cc` corrected dual-view branch and common post-mapping logic; `utils.cc` cache flush; `code_generator_x86_64.cc` `PatchJitRootUse`; `oat_quick_method_header.h` `code_info_offset_`; `runtime/interpreter/mterp/x86_64ng/main.S` hard-float return adapter; `jit.cc` opt-in compile records; `tests/cases/jit-lifecycle-stress/probe.cc`; `art-dlmalloc.cc` `USE_LOCKS=0`
- **Verified:** post-removal JIT smoke 14/14 and matrix 14/14; default native ABI, CriticalNative, JVMTI, nterp/switch OSR and attach, lifecycle/unwind, and fatal Wine gates pass; full Linux rebuild, imageless Hello, GC stress, and Math controls pass; JIT-1 through JIT-4 evidence remains accepted; JIT-5 native build 26100 passes 29 cases and 36/36 records with source/binary removal proof, an inert retired-key test, eight lifecycle cycles, three valid dumps, empty JIT temp, and no trace
- **Design:** [win32_jit_memory.md](win32_jit_memory.md) §2–§13 (Linux low-4-GiB contract, historical diagnosis, implemented Windows 10 section design, verification, and residual work)
- **Evidence:** JIT-2 through JIT-5: `docs/history/windows_x64_w025_jit2_result.md`, `docs/history/windows_x64_w025_jit3_result.md`, `docs/history/windows_x64_w025_jit4_result.md`, and `docs/history/windows_x64_w025_jit5_result.md`; JIT-5 issued SHA-256 `7b35eab8001ee2ba4881985b63d8df6921a954e023f8e70289f964499f57cd32`, returned SHA-256 `2bddf51924a7ca6b9719ffde433e859007465babf6bf2ca7a12f417eecd6289f`
- **Opened:** 2026-07-19
- **Closed:** 2026-07-29 — JIT-5 removal and post-removal regressions pass; W-025 has no residual work

### L-001 — Real PE libcore / openjdk / ICU module build
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** build / libcore / icu
- **Gap:** ~~Windows x64 product still on libcombined / incomplete hybrid PE~~ **product PE from AOSP + multipath hybrids; no libcombined aliasing**.
- **Exit criteria:** PE DLLs built from AOSP sources without `libcombined` aliasing; GoldenApp + charset/locale smoke still pass. **Met.**
- **Fix / evidence:**
  - The unified graph and Python stage own the real PE closure: `libicu_jni`, `libjavacore`, `libopenjdk`, `libopenjdkjvm`, `icuuc`, and `icui18n`; no `libcombined` alias is accepted.
  - Hybrid `libjavacore` includes AOSP Register surface + Memory, NetworkUtilities, NativeBN (`libcrypto`), ExpatParser (static `vendor/external/expat`), AsynchronousCloseMonitor, OsConstantsHolder (multipath), Win Os bridge (`win_fs`/`win_net`/register map).
  - Hybrid `libopenjdk` ships AOSP NIO/zip/fdlibm surface + `win_close` NET_* AsyncClose wrappers (NIO.2 non-goal).
  - Wine gates (2026-07-17): `GoldenApp` (golden.ok/net.ok/done), `CoreProbe` (charset=true), `LocaleProbe`, plus L-001 probes Bn/Xml/AsyncClose/OsConstants/Dns/Net/Io.
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17
- **Progress / residual (not exit blockers):**
  - Full AOSP `libcore_io_Linux.cpp` remains **excluded by design** for Windows x64; product Os surface is the Win bridge map ([win32_libcore_os_natives.md](win32_libcore_os_natives.md): needed=0, 82 implemented, 44 ENOSYS).
  - `cbigint` unused in graph; Linux-only `android_system_OsConstantsHolder.cpp` replaced by multipath Win TU.
  - Crypto/TLS productization tracked under **L-002**; NIO.2 non-goal.
  - Historical details: `docs/history/windows_x64_libcore_icu_result.md`

### L-002 — boringssl / conscrypt / SSL PE
- **State:** CLOSED (2026-07-17) — product TLS stack green under wine (providers + SSLContext.init + HTTPS GET)
- **Kind:** leftover
- **Area:** crypto
- **Gap:** ~~Windows x64 TLS/crypto PE incomplete~~ **product PE + boot packaging complete for HTTPS smoke**.
- **Exit criteria:** HTTPS/crypto golden **or** explicit non-goal. **Met** (wine HttpsProbe status 200 + SslProviderProbe).
- **Fix / evidence:**
  - PE: `libcrypto` / `libssl` / `libjavacrypto` from hybrid CMake; staged single-soname product names.
  - Boot: `tools/bootjar/build_conscrypt_windows_x64.sh` + `build_okhttp_windows_x64.sh` → OpenSSLProvider/JSSE + OkHttp handlers + `security.properties` (AndroidCAStore).
  - Trust: product `run/etc/security/cacerts` (121 roots) via `stage_run_assets.sh`.
  - Wine (2026-07-17 reverify after ART/compat rebuild):
    - `SslProviderProbe.done=ok` (AndroidOpenSSL digests/AES-GCM/SSLContext.init)
    - `HttpsProbe.done=ok` (`https://example.com/` status 200; handlers Http/HttpsURLConnectionImpl)
- **Residual (non-exit / optional):** boringssl win-x86_64 ASM acceleration; BouncyCastle/BKS; full ICU4J IDNA tables for non-ASCII hosts; broader HTTPS golden matrix on real Win10.
- **Code anchors:** historical `docs/history/windows_x64_libcore_icu_result.md`; `tools/bootjar/build_conscrypt_windows_x64.sh`; `tools/bootjar/build_okhttp_windows_x64.sh`; `tools/windows_x64/stage_run_assets.sh`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-003 — Process/exec, rich locale, zip edge, UDP/IPv6 matrix
- **State:** PARTIAL (historical Wine matrix closed 2026-07-17; native subset reviewed 2026-08-01)
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
  - Current gate: unified W-004 runs ExecProbe and Ipv6Probe natively; the historical all-pass Wine script is retired
- **Exit criteria:** Native Exec and IPv6 **met**; Locale and Zip time out after 120 seconds, and UDP fails `DatagramSocket` construction with `setsockopt EINVAL`, so those three remain open and compile-only.
- **Non-goals / host residual:** TCP IPv4-mapped dual-stack; full ICU Collator resources; zip STORED empty-dir edges beyond DEFLATED multi-entry.
- **Code anchors:** `win_process_natives.c`, `win_net_natives.c`, `ZipFile.java` (Win CEN), `FileInputStream.c` available0, historical `interpreter.cc` 12-slot fallback, probes under `tests/cases/windows-libcore-smoke/`
- **Opened:** 2026-07-17
- **Last reviewed:** 2026-08-01

### L-004 — Shrink or replace multi-name DLL staging
- **State:** CLOSED (2026-07-17) — product ships one PE soname each: `libicu_jni`/`libjavacore`/`libopenjdk`/`libopenjdkjvm`/`libcrypto`/`libssl`/`libjavacrypto` (+ `icuuc`/`icui18n`); short-name twins removed from packaging
- **Kind:** leftover / packaging debt
- **Depends on:** L-001, W-005
- **Fix:** generated/CMake product names are canonical and the Python frontend stages only those regular-file outputs; the short-name shell copier was retired
- **Opened:** 2026-07-17

### L-005 — Linux multiplatform imageless Hello / boot.jar CI gate
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover
- **Area:** linux-host
- **Gap:** ~~After repo migration, host Linux verified `dalvikvm -showversion` only~~ **scripted gate landed**.
- **Exit criteria:** One scripted imageless Hello (or RESULT) on multiplatform `main`.
- **Fix:** The historical PASS is retained in `tests/cases/imageless-runtime/RESULT.md`: imageless `-Xint` Hello used the same shared multipath `boot.jar` bytes staged for Windows x64, and ELF selected `UnixFileSystem` at runtime. The stale shell runner was retired; current managed coverage is explicitly pending the unified Java/D8 pipeline.
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

### L-006 — phase1.cmake / generated Win graph pure-vendor consistency
- **State:** CLOSED (2026-07-17)
- **Kind:** leftover / build
- **Area:** build
- **Gap:** ~~Residual MinDalvikVM-Archive path assumptions in product scripts~~ **pure-vendor**.
- **Fix / evidence:**
  - The maintained product CMake resolves `${MDVM_NATIVE_SRC_ROOT_DIR}` to **`vendor/`**; the former Windows phase/libcore alternative graphs were retired.
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
- **Doc:** `docs/history/shared_bootjar_runtime_os_detection.md`
- **Canonical property:** `dalvik.vm.multiplatform.internal.os` = `windows` | `unix`
  - Long + `internal` intentional (not a public app API; not expected for external use)
  - Reject short `dalvik.vm.mp.os` (`mp` ambiguous)
  - Values: `windows`|`unix` (not `posix`, not `linux`) — aligns with `WinNTFileSystem` / `UnixFileSystem`
- **Injection:** `vendor/art/runtime/runtime.cc` after `PropertiesList` release (PE=`windows`, ELF=`unix` if unset)
- **Detection ladder:** `VMRuntime.properties()` → System props / `os.name` → default `unix` (`VMRuntime.isWindowsOs`)
- **Separators:** removed from `AndroidHardcodedSystemProperties`; set in `System.initUnchangeableSystemProperties`
- **Boot:** `tools/bootjar/build_windows_x64.sh` stages shared jar (no WinNT-only overlay); jar embeds both FS + `isWindowsOs`
- **Exit criteria (met):** single shared boot pipeline produces one jar used for Linux imageless Hello (L-005 PASS on shared multipath bytes)
- **Non-goals for this close:** dual-host acceptance that Windows always selects `WinNTFileSystem` and Unix always selects `UnixFileSystem` under product PE/wine — those are ordinary product smoke, not D-001 scope
- **Follow-up (orthogonal):** wine/host Hello on same bytes; PE `art.dll` inject path when PE product is rebuilt
- **Code anchors:** `dalvik/system/VMRuntime.java` (`isWindowsOs*`), `DefaultFileSystem.java`, `System.java`, `runtime.cc`, `build_windows_x64.sh`
- **Opened:** 2026-07-17
- **Closed:** 2026-07-17

## Design notes

_No open design notes. Closed D- items live under §Closed._

## Suggested next closures (priority)

1. ~~**D-001**~~ **CLOSED** — single shared boot.jar (runtime OS selection); dual-host FS smoke is not the close bar.  
2. ~~**W-001**, **W-002**, **W-003**, **W-004**, **W-011**, **W-012**, and **W-024**~~ closed; W-003 native R1 passes 19/19 records with 8/8 frame attribution, 6/6 XMM sentinel, and clean fatal/dump scans.
3. ~~**L-001**~~ — **CLOSED** real PE libcore/openjdk/ICU hybrid; residual Linux TU/bridge growth optional.  
4. ~~**W-025 JIT-5**~~ **CLOSED** — J-1 and the retired key are removed;
   post-removal Windows/Wine/Linux and native fatal/unwind closure pass.
5. ~~**W-010/W-014 FS-2**~~ **CLOSED 2026-07-30** — native build-26100
   evidence accepts debugger continue, all named forced-incompatible CET
   policies plus safe dynamic/reserved fields, exception-unwind XMM6-XMM15,
   and embedding predecessor-UEF/frame-SEH teardown. FS-1 stack budget and
   FS-3 dynamic-table churn/sampling are complete. Remaining W-010/W-014
   follow-ups are conditional reservation correlation, negative-exception,
   and debugger-quality dump-stack probes. FS-5
   conditionally closes the pending tail because no real native exception can
   enter it without product fault injection; structural and synthetic unwind
   evidence remain accepted.
6. ~~**H-001**~~ **CLOSED 2026-07-30** — scoped native Server 2025 Phase-4 subset accepted; FS-4's authoritative-host repeat also passes.
7. ~~**H-002**~~ **CLOSED 2026-07-30** — Windows Server 2025 build 26100 is the authoritative native gate; the separate Win10/second-host repetition is skipped by policy.
8. ~~**L-005** — Linux Hello gate~~ **CLOSED**.

---

## Maintenance checklist for future PRs

- [ ] New `#ifdef _WIN32` temporary behavior → new **W-** row  
- [ ] New stub JNI → update **W-005** export scope or split **W-**  
- [ ] Gate newly green on host → close matching **H-**  
- [ ] Permanent design choice (e.g. VEH forever) → move from W- to documented architecture; close workaround  
- [ ] CLOSED items: move full item into §Closed (sorted by ID); keep State CLOSED history  


*Last snapshot: 2026-07-30 - W-001/W-002/W-003/W-004/W-011/W-012/W-013/W-024/W-025, W-010/W-014 FS-2, H-001, H-002, and authoritative-host FS-4 are closed; FS-5 is conditionally closed. Nterp and the corrected pagefile-section JIT dual view are product defaults; JIT-5 removes J-1 and passes post-removal Wine/Linux plus 29 native cases and 36/36 aggregate records with source/binary absence proof, eight lifecycle cycles, three valid dumps, empty JIT temp, and no trace. W-010/W-014 E9 remains native-accepted 30/30 on Windows Server 2025 build 26100: explicit Windows x64 stack checks, guarantee-aware bounds, switch/nterp/JIT SOE, zero handled dumps, and five fatal static/JIT/OSR dumps all pass. FS-1 adds accepted Release/Debug switch/nterp/JIT stack high-water margins and no dumps; the 40-KiB Debug-only reserve leaves more than 37 KiB on quick paths while product and Linux remain at 8192 bytes. FS-2 adds native first-chance debugger continuation, named CET rejection/safe-policy acceptance, exception-XMM, and embedding/UEF teardown. FS-4 repeats E9/FS-1/FS-2/FS-3, parameterized stack geometry, fiber rejection, and join/detach stress on build 26100; the separate Win10/second-host repetition is skipped by policy; evidence is under `tools/verify/windows_x64_phase4/evidence/fs4_same_host_20260730/`. FS-5 records the accepted structural/synthetic pending-tail boundary and explains why native fault injection would alter product control flow. H-001 adds the native Server 2025 scoped Phase-4 subset. Linux's object probes and imageless Hello pass. Fixed-page recursion remains rejected and its machinery is diagnostic-only. Remaining W-010/W-014 work is reservation-correlation, negative-exception, and debugger-quality dump-stack coverage.*
