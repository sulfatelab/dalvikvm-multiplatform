# Windows x64 Phase 4 — RESULT

**Status:** **WINE COMPLETE; W-010/W-014 E9, FS-1, FS-2, AND FS-3 NATIVE ACCEPTED** — W-002,
W-003, W-004, W-024, and W-025 native matrices are accepted. W-010/W-014 E9
passes the complete 30-record runner and FS-1 passes Release/Debug switch,
nterp, and JIT stack high-water on Windows Server 2025 build 26100. Product
managed SOE has zero handled dumps; FS-1 has four complete records per mode,
positive margins, and no dump. FS-2 now also passes the native debugger,
forced-policy, embedding/UEF teardown, and exception-unwind XMM gates on that
host. FS-3/JIT-3 also passes native lifecycle churn and virtual-unwind
sampling. FS-4 repeats these gates on the same host, including parameterized
stack geometry and join/detach/fiber checks. Windows Server 2025 build 26100
is the authoritative native gate; the separate Windows 10/second-host repeat
is skipped by policy. Reservation-correlation, negative-exception, and
debugger-quality dump-stack coverage remain optional follow-ups. FS-5
conditionally closes the pending bridge tail.
**Date:** 2026-07-30
**Depends on:** Phase 3 complete (historical real Win10 G12 goldens)

**Current lab policy:** All future native Windows gates use Windows Server
2025 Datacenter Evaluation x64 build 26100. The former Windows 10 host is no
longer available; the Windows 10 records in this file are retained as
historical evidence only. See [HOST_GATE_POLICY.md](HOST_GATE_POLICY.md).

## Scope (from win32_art_port §Phase 4)

- GC stress, multi-thread stress, crash dumps, resource/handle leaks
- Performance smoke plus focused managed/native JIT, OSR, attach, ABI, tracing,
  and forced-interpreter transitions
- **Gate:** A5–A8 stable; no WSL

## Gates (wine64)

| Gate | Status | Command |
|------|--------|---------|
| P4_G1 GC stress | **PASS** | `run_gcstress.sh` |
| P4_G2 Thread heavy | **PASS** | `run_threadheavy.sh` |
| P4_G3 Handle leak smoke | **PASS** | `run_handleleak.sh` |
| P4_G4 Perf smoke | **PASS** | `run_perfsmoke.sh` |
| P4_G5 Java abort path | **PASS** | `run_crashabort.sh` |
| P4_G5b Native AV + minidump | **PASS** | `run_crashnative.sh` (VEH+UEF+`.dmp`) |
| P4_G6 GoldenApp regression | **PASS** | phase3 `run_goldenapp.sh` |
| W-002 structural managed entries | **PASS** | `check_w002_managed_entries.py` |
| W-003 quick boundary/trap parity | **PASS** | `check_w003_quick_boundaries.py` |
| W-010 static OSR/invoke lookup and virtual unwind | **PASS** | `run_osr_unwind_probe.sh` (R12-anchored variable RSP entry, explicit RBP JIT handoff, managed-clobbered RBP return, GPR plus XMM6-XMM15 restore, invoke records, epilogue) |
| W-010 GenericJNI native-return virtual unwind | **PASS** | same probe: captured `+0xc5` return, variable native RSP, 5120-byte R12 anchor, repaired RDI `offset=0x1400`, caller RIP/RSP and all nonvolatile GPRs |
| W-010 switch-wrapper unwind | **PASS on native build 26100** | E5: live `ExecuteSwitchImplAsm + 0xd` lookup succeeds after the Windows-only RBX/home-area/unwind repair |
| W-010 interpreter-bridge unwind | **PASS on native build 26100** | E6: live primary `+0x82` lookup plus all later frames reach zero PC/UEF/dump; pending record remains structural/synthetic |
| W-003 attributed frame families | **PASS, 8/8** | `run_w003_frame_probe.sh` |
| W-003 historical XMM6-XMM11 / W-010 full XMM6-XMM15 sentinel | **PASS, 6/6** | `run_w003_xmm_sentinel.sh` (`selfTestMask=63`, `fullSelfTestMask=1023`) |
| W-002 OSR matrix | **PASS, 8/8** | `run_w002_osr_probe.sh` |
| W-002 attached-thread matrix | **PASS, 8/8** | `run_w002_attach_probe.sh`; each raw thread now detaches, uses native stack, and reattaches |
| W-014 thread reservation/lifetime/guarantee-aware bounds | **PASS** | `run_thread_stack_probe.sh`; E9 raises/preserves/queries the guarantee and debits prefix + guarantee + moving guard |
| W-010 fault record/context adapter | **PASS** | `run_fault_adapter_probe.sh` (`failures=0 cases=8`; live probe `calls=2 first=0 second=0`) |
| W-010 JIT unwind serializer | **PASS, 6/6** | `run_jit_unwind_info_probe.sh` |
| W-010 JIT runtime registry | **PASS** | `run_jit_unwind_registry_probe.sh` (lookup, virtual unwind, delete, re-register) |
| W-010 JIT collection/reuse lifecycle | **PASS, J-2/J-1** | `run_jit_unwind_lifecycle.sh` (real collection, lookup disappearance, exact address reuse) |
| W-010 active nterp/JIT managed faults | **PASS on Wine and native build 26100** | `run_w010_managed_fault_probe.sh`; Windows x64 explicit pre-prologue stack checks, common implicit null handling, repeated main/child SOEs, and no handled-fault diagnostics/dump change |
| W-010 threshold-zero JIT fatal dispatch | **PASS, J-2/J-1** | `run_jit_fatal_unwind.sh` (VEH, UEF, changed/new valid `MDMP`) |
| W-010 OSR-origin fatal dispatch | **PASS, J-2/J-1** | `run_osr_fatal_unwind.sh` (real switch OSR jump, VEH, UEF, new valid `MDMP`) |
| W-010/W-014 native package preflight | **PASS under Wine** | `package_windows_x64_w010_w014.sh` (E9 30-record acceptance runner plus separate historical stack-growth/UEF diagnostics) |
| W-010/W-014 isolated failure diagnostics | **PASS on native build 19044** | runs 3-4: fixed-page SOE invalidated; UEF replacement ruled out; JNI hardware/raised AVs miss UEF while the JNI-created native worker reaches UEF/dump, isolating traversal through managed/GenericJNI frames. |
| W-010/W-014 complete E9 native host matrix | **PASS, 30/30 on build 26100** | guarantee-aware excluded-low accounting; switch/nterp/JIT managed SOE; zero handled dumps; five valid static/JIT/OSR fatal dumps |
| FS-1 Release/Debug stack high-water | **PASS on Wine and native build 26100** | `run_fs1_stack_high_water.sh`; switch/nterp/JIT, four complete records each; native Release minimum margin 6784 bytes, Debug quick minimum 37168 bytes; no dumps |
| FS-2 native debugger/CET/embedding/exception-XMM matrix | **PASS on native build 26100** | `evidence/fs2_w010_w014_native/ACCEPTANCE.md`; first-chance JIT NPE continue, explicit SOE no AV, nine incompatible CET rejections plus safe-policy acceptance, JNI UEF teardown, and 2x nterp/switch/JIT exception-XMM runs |
| Full suite | **PASS** | `run_all_wine_gates.sh` |

Evidence: `evidence/all_wine_gates.txt`, `evidence/crashnative.txt`

### Native crash evidence (wine)

```text
ART Win32 VEH: exception 0xc0000005 ...
ART Win32 UEF: exception 0xc0000005 ...
ART Win32 crash: minidump written to .../run/crash/art-....dmp
PASS native_crash_aborts
```

## Landed code

| Item | Location |
|------|----------|
| UEF + MiniDumpWriteDump | `vendor/art/runtime/multiplatform/windows/runtime_windows.cc` (links `dbghelp`) |
| Phase 4 probes | `tools/verify/windows_x64_phase4/src/*` |
| Native AV JNI | `tools/windows_x64/jni_stubs/win_runtime_natives.c` |
| W-002 OSR adapters | `quick_entrypoints_x86_64.S`; `mterp/x86_64ng/main.S` |
| W-002 probes and native package | `run_w002_*.sh`; `package_windows_x64_w002.sh` |
| W-003 XMM boundary and structural gate | `quick_entrypoints_x86_64.S`; `check_w003_quick_boundaries.py` |
| W-003 attributed frame-family gate | `../../../tests/cases/w003-frame-probe/`; `run_w003_frame_probe.sh` |
| W-003 XMM runtime sentinel | `../../../tests/cases/w003-xmm-sentinel/`; `run_w003_xmm_sentinel.sh` |
| W-003 native package and evidence | `package_windows_x64_w003.sh`; `evidence/w003_host/ACCEPTANCE.md` |
| W-014 Stages A-B stack/pthread/page gate | `../windows_x64_phase1/win32_thread_stack_probe.c`; `../windows_x64_phase1/win32_stack_page_probe.cc`; `../windows_x64_phase1/win32_stack_page_fault_probe.S`; `run_thread_stack_probe.sh` |
| W-010 Stage C adapter and probes | `../windows_x64_phase1/win32_fault_record_probe.cc`; `../windows_x64_phase1/win32_sigchain_probe.cc`; `run_fault_adapter_probe.sh`; `vendor/art/runtime/multiplatform/windows/sigchain_windows.cc` |
| W-010 Stage D activation and stress | `src/W010ManagedFaultProbe.java`; `run_w010_managed_fault_probe.sh`; common runtime null/SO flags and early nterp range registration |
| W-010 dynamic-JIT PE unwind | `runtime/multiplatform/windows/jit_unwind_windows.*`; `runtime/jit/{jit_code_cache,jit_memory_region}.*`; `run_jit_unwind_{info,registry,lifecycle}.sh`; `run_jit_fatal_unwind.sh` |
| W-010 static OSR PE unwind | `quick_entrypoints_x86_64.S`; `../windows_x64_phase1/win32_osr_unwind_probe.cc`; `run_osr_unwind_probe.sh`; `check_win32_boundary_unwind.py` |
| W-010/W-014 native Stage E package and diagnostics | `package_windows_x64_w010_w014.sh`; `host/RUN_W010_W014_HOST.ps1`; `host/RUN_W010_W014_DIAGNOSTICS.ps1`; `check_w010_w014_host_package.py`; `review_w010_w014_host_result.py`; `W010_W014_HOST_CHECKLIST.md`; `W010_W014_DIAGNOSTICS.md` |
| FS-1 stack high-water probe/package/evidence | `run_fs1_stack_high_water.sh`; `check_fs1_stack_high_water*.py`; `host/RUN_FS1_STACK_HIGH_WATER_HOST.ps1`; `package_windows_x64_fs1.sh`; `evidence/fs1_stack_high_water/ACCEPTANCE.md` |
| FS-2 debugger/CET/embedding/exception-XMM probes and evidence | `../windows_x64_phase1/win32_debugger_probe.cc`; `../windows_x64_phase1/win32_art_embedding_probe.cc`; `host/RUN_W010_W014_HOST.ps1`; `evidence/fs2_w010_w014_native/ACCEPTANCE.md` |

## Host

Rebuild package (includes Phase 4 jars/scripts):

```bash
bash tools/windows_x64/host_package/package_windows_x64_phase3.sh
# Windows: scripts\run_all_host.cmd  (now includes gcstress/threadheavy/handleleak/perfsmoke)
# Optional: scripts\run_crashabort.cmd
```

Focused W-002 native acceptance:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/windows_x64/host_package/package_windows_x64_w002.sh
# Native PowerShell: .\scripts\RUN_W002_HOST.ps1
```

Focused W-003 native acceptance:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/windows_x64/host_package/package_windows_x64_w003.sh
# Native PowerShell: .\scripts\RUN_W003_HOST.ps1
```

The accepted Windows 10 build 19044 return has 19/19 PASS records over 14
children, clean fatal/dump scans, 8/8 attributed frame runs, and 6/6 XMM
sentinel runs. See `evidence/w003_host/ACCEPTANCE.md`.

Focused W-010/W-014 native Stage E gate:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/windows_x64/host_package/package_windows_x64_w010_w014.sh
# Native PowerShell: .\scripts\RUN_W010_W014_HOST.ps1
# Failure diagnosis: .\scripts\RUN_W010_W014_DIAGNOSTICS.ps1
```

Focused FS-1 Release/Debug stack high-water gate:

```bash
bash tools/windows_x64/host_package/package_windows_x64_fs1.sh
# Native PowerShell: .\scripts\RUN_FS1_STACK_HIGH_WATER_HOST.ps1
```

The Linux-side preflight passes package integrity, the complete Wine matrix,
all fatal origins, the safe isolated diagnostics, per-case preservation of
valid minidumps, and the final clean-package checker. Wine remains development
evidence. E9's returned Windows build-26100 run below is the current native
acceptance; the E2-E8 narratives are retained as historical diagnosis.

The second returned Windows 10 build-19044 package has 20 PASS and 12 FAIL
records. It closes ordinary CET classification, exact requested reservations,
direct fixed-page restoration, NPE translation, sigchain/frame-SEH, OSR live
unwind, and six XMM6-XMM15 sentinel runs. Switch/nterp/JIT SOE all terminate
with native stack overflow before ART's fixed-page AV. Static, JIT J-2/J-1,
and OSR J-2/J-1 fatal AVs all reach VEH but not UEF/dump. Run the separate
diagnostics before changing stack delivery or JIT unwind code; the run-3 result
below supplies that evidence.

The third returned diagnostic archive,
`/tmp/diag-log-windows_x64_w010_w014_host-run3.zip`, matches the issued package and
completes the isolated matrix. Baseline/protected/writable recursion reaches
`STATUS_STACK_OVERFLOW`; direct access to the protected page still produces
the expected AV. At protected-mode termination the selected page is part of a
2,093,056-byte committed `PAGE_READWRITE` region, and writable mode can
re-protect it before `_resetstkoflw()`. The prior error 13 is secondary; normal
Windows stack growth has already consumed the fixed page as stack backing.

Standalone unhandled main-thread and worker-thread AVs reach UEF, direct
predecessor chaining reaches both filters, and frame SEH consumes its AV as
expected. The late ART probe reports its predecessor inside `art.dll`
immediately before the crash, then only the ART VEH marker appears: neither
late nor ART UEF runs, no dump marker is emitted, and no dump is created. This
rules out UEF replacement, debugger attachment, the PowerShell runner, and
dump-path/API failure. The captured return site maps to
`art_quick_generic_jni_trampoline + 0xc5`. The new realistic GenericJNI test
found RDI physically saved at `R12 + 0x1400` while `.xdata` described offset
zero. The repaired record passes structural inspection and restores caller
RIP/RSP plus every nonvolatile GPR. The earlier incorrect RDI did not corrupt
synthetic control-stack recovery, so native results still determine whether it
was the complete dispatch cause.

The follow-up diagnostic package adds continuable JNI
`RaiseException(EXCEPTION_ACCESS_VIOLATION)`, the JNI hardware AV, and a
hardware AV on a JNI-created `_beginthreadex` worker with no managed frames on
the crashing thread. All three reach late UEF, ART UEF, and a valid minidump
under Wine. The software-raised case then resumes under Wine and its exit shape
is recorded rather than treated as infrastructure failure.

The fourth returned diagnostic archive,
`/tmp/diag_w010_w014_host-run4.zip`, exactly matches that issued package. Its
stack and standalone UEF results repeat run 3. The JNI hardware and JNI-raised
AVs both report ART as the predecessor, reach ART's VEH, then exit with
`STATUS_ACCESS_VIOLATION` without entering either late or ART UEF and without
creating a dump. The JNI-created native worker reports its creation and entry,
then reaches the late UEF, ART UEF, and creates one valid 648,619-byte
minidump. Thus hardware versus software exception shape, process-wide ART
startup interaction, UEF ownership, debugger/runner behavior, and dump
creation are not the distinction. The failure requires the ART
managed/GenericJNI caller chain. The RDI repair remains correct but is not the
complete dispatch fix; the next package must trace bounded recursive native
unwind progress from the live VEH context before any further product metadata
change.

That E4 live-VEH trace was implemented behind
`ART_WINDOWS_X64_FATAL_UNWIND_TRACE=1` and enabled only for the three late-UEF
diagnostic children. It copies the context, records module-relative runtime-
function data, walks at most 32 frames, validates leaf pops and stack bounds,
and does not change dispatch. A direct Wine smoke reaches an end marker after
15 frames. Its first live lookup gap is `ExecuteSwitchImplAsm + 0x9` at the
post-call `pop %rbx`: the wrapper has pushed RBX but has no PE runtime-function
record, so leaf fallback consumes saved RBX as the return PC. The assembly was
held for native E4 confirmation; the native result below supplies it. The
repair must also account for the wrapper's missing 32-byte MSVC outgoing home
area while leaving its Linux/SysV path unchanged.

The exact-commit E4 package preflight passes the structural checker, all
handled-fault and ABI gates, all three traced late-UEF modes, static/JIT/OSR
fatal dispatch, 14-15 valid Wine minidumps across two complete runs, final dump cleanup, manifest/hash
regeneration, and the final clean-package checker. This is package readiness,
not native proof of the candidate frame.

Native E4 then confirms the candidate on Windows build 26100. JNI hardware and
raised AV traces both unwind through GenericJNI, the static invoke stub, and
ordinary ART frames to `ExecuteSwitchImplAsm + 0x9`, where runtime-function
lookup fails. Leaf fallback consumes saved RBX as PC and both UEFs are missed.
The JNI-created native worker unwinds through four registered frames, reaches
both UEFs, and creates a valid 747,491-byte dump. The result bundle SHA-256 is
`4616e8622dba2977b5472264f099de9449aa5c8b0a4bc1d1d568f9af8c6987b8`.

E5 verifies the resulting switch-wrapper repair on the same native host. The
post-call `ExecuteSwitchImplAsm + 0xd` PC now has a runtime-function record in
both JNI traces, and virtual unwind crosses it plus four later registered ART
C++ frames. The new first miss is `art_quick_to_interpreter_bridge + 0x82`
(`art.dll` RVA `0x9d3652`), immediately after its call to
`artQuickToInterpreterBridge`. The JNI cases still miss both UEFs. The native
worker reaches both UEFs and writes one valid 747,073-byte dump. The result
bundle SHA-256 is
`1a58bb0f318eae82882ea1bd0e5b0fa403202d02ae95a889b07a1e7b3524b3d9`;
see `evidence/w010_w014_e5/DIAGNOSIS.md`.

Local E6 repairs the new boundary without changing the ART frame contract. The
primary record describes the existing 200-byte save-refs-and-args frame;
fixed-offset restores end in canonical normal and pending tail-jump epilogues.
The pending target has its own contiguous record for the existing 88-byte
save-all frame. The static audit requires both ranges, and the live probe
reports `interpreter_bridge_records=2`, call return `0x82`, pending offset
`0x140`, and frame sizes 200/88 after unwinding entry, body, restore,
epilogues, and pending body. The complete Wine aggregate, W-003 frame/XMM
matrices, Linux rebuild/showversion/imageless Hello, and unchanged Linux bridge
disassembly pass.

Native E6 validates the uploaded archive and Python package checker, then
reports `lookup=1` for the primary bridge at hardware frame 11 and raised frame
12. Every later frame is registered, both walks end at zero PC after 23/24
frames, both late filters and ART UEF enter, and each JNI case writes a valid
dump. The native-worker control also passes. The returned bundle SHA-256 is
`a1c6af0ceff198f6b4543aa832dbf40ced81dcf72800b77c55dd5f2959302736`;
see `evidence/w010_w014_e6/DIAGNOSIS.md`.

The subsequent complete E6 host run records 25 of the 30 required PASS rows on
Windows Server 2025 build 26100. Static `-Xint`, threshold-zero JIT J-2/J-1,
and switch-OSR J-2/J-1 fatal AVs all enter VEH and UEF, terminate nonzero, and
produce five valid named 14-stream minidumps. Structural/CET, live unwind, all
six XMM runs, thread/page/fault/sigchain checks, no-chain rejection, and
nterp/JIT NPE also pass.

Only managed SOE remains red. Switch mode reports an unexpected fixed-page
state while protecting the page and exits with `0xC0000005`. Nterp and JIT
reach native `0xC00000FD`; nterp stops after VEH, while JIT reaches UEF and
writes an unwanted sixth dump. Those outcomes also fail the handled-log and
handled-dump aggregates. The authentic returned payload passes issued-package
identity checking; the reviewer then rejects the expected `OVERALL FAIL`.
The raw returned bundle SHA-256 is
`d6bb85c1529496cb384bebcc1495378ade0e253041e01a9605f3f6c90b8538e5`;
see `evidence/w010_w014_e6_full/DIAGNOSIS.md`.

## Accepted native E9 host result

E7 replaced the rejected fixed-page recursive-SOE path with narrow Windows x64-only
explicit pre-prologue checks in optimizing code and nterp. The check allows
`RSP == Thread::stack_end_`, branches only when RSP is below the boundary, and
tail-jumps through `Thread::pThrowStackOverflow`. Linux retains its unchanged
implicit `RSP - 8192` probe and fault translation.

E9 completes the Windows boundary contract. Each attaching thread queries its
current `SetThreadStackGuarantee` value, raises it to at least four system pages
while preserving a larger host value, queries the configured value back, and
rejects attachment if the operation cannot be verified. Stack accounting
excludes the sum of the `VirtualQuery`-measured inaccessible low prefix, the
page-rounded configured guarantee, and one moving `PAGE_GUARD` page. Common ART
code then adds its unchanged 8192-byte managed-overflow recovery reserve.

This sum, rather than E8's rejected `max(prefix, guarantee)`, follows the
native measurements: on build 26100, terminal recursion moved from
`low + 0x3000` with a zero/default request to `low + request + 0x1000` once the
request exceeded the default. The guarantee is therefore above a separate
terminal prefix, and the moving guard is an additional page.

The immutable issued archive is
`dist/windows_x64_w010_w014_e9_native.zip`, SHA-256
`2b84c911dfbe23dd5dd13917a0fb4a63bdbf90901172f74dfe642ed1fd20f16f`.
On Windows Server 2025 build 26100 the returned full payload matches the issued
identity, the runner records exactly 30 PASS rows with no failure, and the
independent reviewer reports:

```text
PASS (build=26100, pass_records=30, dumps=5, return=full-package)
```

All switch/nterp/JIT handled SOE paths pass, handled logs are free of fatal
markers, `HANDLED_DMP_SCAN.txt` says `NO_HANDLED_DMP_FILES`, and the five
intentional static/JIT/OSR fatal origins produce five valid dumps. The main and
pthread page probes both report `before=0 configured=16384 minimum=16384`.
See `evidence/w010_w014_e9/ACCEPTANCE.md`.

## FS-1 native stack high-water acceptance

The 53,459,106-byte archive with SHA-256
`22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe`
passes internal package integrity and six native child processes. Release
minimum native margins are 6784, 7536, and 7616 bytes for switch, nterp, and
JIT. Debug margins are 69744, 37168, and 37232 bytes. Every process emits four
complete main/child records; `DMP_SCAN.txt` says `NO_DMP_FILES` and the result
ends in `OVERALL PASS`.

Native Debug originally exhausted the 8192-byte reserve in
`Heap::CheckPreconditionsForAllocObject` while constructing the managed
exception. A 20-KiB trial remained about 8 KiB short on nterp/JIT. The final
40-KiB reserve is therefore limited to non-`NDEBUG` Windows x86_64 and leaves
more than 37 KiB on both quick paths; Release/product and non-Windows remain
at 8192 bytes. Product isolation, final-source Wine Release/Debug, W-010
managed faults, the combined Windows/Linux object gate, the full Linux
rebuild, and imageless Hello pass. See
`evidence/fs1_stack_high_water/ACCEPTANCE.md`.

## FS-2 native acceptance

FS-2 is accepted on the same Windows Server 2025 build 26100. The refreshed
package `dist/windows_x64_w010_w014_host_fs2.zip` passes the Linux package
checker and complete Wine smoke, then the native PowerShell runner records
`OVERALL PASS`. The result includes all nine named incompatible CET policy
rejections before Java/JIT, accepted `CetDynamicApisOutOfProcOnly` and
reserved-bit cases, debugger first-chance/continue behavior, embedding UEF and
frame-SEH teardown, and two repeats of the exception-unwind XMM sentinel in
nterp, switch, and threshold-zero JIT. The native archive SHA-256 is
`935ab419124782bf8ac98546f38c352d4a32223466f3fe962f3c64dd3afd21bd`.

The debugger NPE log records `first_chance_av stop=1` followed by
`continue=DBG_EXCEPTION_NOT_HANDLED`, `first_av=128`, `second_chance=0`, and a
clean child exit. The explicit SOE run reports no AV or stack-overflow debug
event. The embedding probe reports predecessor UEF resumption, foreign VEH and
frame-SEH calls before and after ART teardown, and no stale ART callback. The
exception sentinel reports `exceptionMask=0`, `exceptionCaught=32`, and
`exceptionSelfTestMask=1023`. Compact native logs and the complete result are
retained in `evidence/fs2_w010_w014_native/`.

## Non-goals

- Windows NIO.2
- Production perf parity with Linux
- Treating Wine as a substitute for an explicitly required native-host gate

## Next

- Keep E9's explicit Windows x64 stack checks and guarantee-aware bound accounting as
  the accepted product path; retain fixed-page operations only as direct
  diagnostics. The authoritative Windows Server 2025 build-26100 FS-4 repeat
  is archived under `evidence/fs4_same_host_20260730/`.
- Correlate Java/ART-pool reservations and add wrong-address/unsupported-
  exception negatives or debugger-quality dump-stack reconstruction if those
  remain release requirements. FS-5 records why a real pending-tail native
  fault would require product fault injection.

## W-010 Stage D activation re-run (2026-07-27)

Historical Stage D enabled common implicit null and stack-overflow checks.
E7 retains implicit null, sets Windows x64 common implicit stack checks off, and
uses explicit pre-prologue checks instead. Implicit suspend checks remain off,
and nterp's immutable code range is registered before startup publishes its
entrypoints.
Normal started runtimes reject `-Xno-sig-chain`; active product and host
runners no longer pass it.

Focused Wine acceptance passes:

- 64 caught read NPEs and 64 caught write NPEs in nterp;
- the same NPE matrix in threshold-zero JIT with the faulting caller compiled;
- two caught main-thread plus two caught child-thread SOEs in each mode, with
  the recursive JIT methods compiled;
- no managed-fault diagnostic VEH/UEF marker and no dump-state change; and
- unmanaged native AV still reaching fatal diagnostics.

The rebuilt complete Phase-4 aggregate reports `PASS all wine Phase 4 gates`.
Windows x64 `art`/`dalvikvm`, Linux `art`/`dalvikvm`,
`dalvikvm -showversion`, and shared-boot imageless Hello also pass. Wine is
development evidence; native Windows Stage E remains required. See
[`RESULT-w010-managed-faults.md`](RESULT-w010-managed-faults.md).

## W-010 static OSR unwind re-run (2026-07-27)

`art_quick_osr_stub` now has two contiguous static PE runtime-function ranges.
The first uses fixed-bottom R12 while the copy body moves RSP downward, then
sets RBP to the copied RSP immediately before the OSR jump. This reproduces the
normal Windows x64 JIT frame anchor without changing generated JIT code. The second
describes the inherited 248-byte fixed frame directly from RSP because returned
OSR code reconstructs managed state rather than preserving either stub anchor.
The return record uses exact GPR/XMM save offsets and ends in `add rsp,248; ret`.

The emitted audit verifies both records and the corrected completed-frame
XMM6-XMM15 offsets for OSR and the two invoke stubs. The live Wine probe
restores all nonvolatile GPRs and XMM6-XMM15 from a variable-depth entry
context with R12 anchoring, a return context with RBP deliberately clobbered,
and the return epilogue, and synthetically unwinds both invoke records. The
actual W-002 OSR matrix passes 8/8 across dual/J-1 and default-nterp/switch.
J-2/J-1 JIT-origin and OSR-origin fatal-unwind gates and the full Phase-4
aggregate also pass. The full normal-return sentinel passes 2/2 in nterp,
switch, and threshold-zero JIT with `fullSelfTestMask=1023`. Native Windows
must repeat these lookups/unwinds, full-width sentinel runs, and both fatal
paths.

## Multiplatform re-run (2026-07-17)

Rebuilt PE in-tree (`build/windows_x64_phase1`) from `dalvikvm-multiplatform` with
windows_x64-dev-env + wine64 10.0.

| Gate | Result |
|------|--------|
| P4_G1 GC stress | PASS |
| P4_G2 Thread heavy | PASS |
| P4_G3 Handle leak | PASS |
| P4_G4 Perf smoke | PASS |
| P4_G5 Crash abort | PASS |
| P4_G5b Crash native | PASS |
| P4_G6 GoldenApp | PASS |
| Suite | **PASS all wine Phase 4 gates** |

Evidence: `evidence/all_wine_gates.txt`

## W-004 runtime-load re-run (2026-07-25)

The helper-based Windows x64 `LOAD_RUNTIME_INSTANCE` was replaced by a direct
same-image load of `Runtime::instance_`. The rebuilt Phase 4 aggregate passes,
including its new structural/source/dependency gate, with 574 direct
relocations and zero retired-helper references. Full focused results and the
accepted native-Windows closure are recorded in
[`RESULT-w004-runtime-load.md`](RESULT-w004-runtime-load.md).

## W-002 managed-entry re-run (2026-07-26)

The quick/switch OSR stub now keeps its Microsoft C++ entry, converts arguments
inside assembly, preserves Windows x64 nonvolatiles, and publishes rSELF in r15.
Windows nterp OSR now uses `NterpFree` and a separate return adapter instead
of assuming that nterp and compiled callee-save layouts match.

Focused Wine acceptance passes:

- structural/source/PE object inspection;
- OSR 2/2 in each dual/J-1 and default-nterp/switch pair;
- attached-thread JNI 2/2 in the same four pairs, with 16 native threads per
  process; and
- the complete Phase 4 aggregate.

The complete Phase 3 aggregate, Windows x64 build, Linux full build, Linux
shared-boot Hello/GC, and Linux nterp OSR control also pass. The focused native
Windows package passes its manifest/export checks and all eight staged-package
Wine combinations. Native Windows R1 then passes package identity, structure,
all 8/8 attached-thread processes, and all 4/4 switch-OSR processes with no
fatal marker or dump. Its four clean default-nterp processes miss the OSR jump
because the runner left the nterp warmup threshold at 65535 and the short loop
finished before the asynchronous transition. R2 now pins both JIT thresholds
to 100, runs 2,000,000 iterations with checksum `65553463744`, and passes the
focused matrix, Phase 3/4 aggregates, Linux controls, package smoke, and seven
tooling tests. Native Windows R2 then passes 21/21 records on build 19044:
8/8 OSR, 8/8 attach, package/structure checks, fatal scan, and `NO_DMP_FILES`.
W-002 is closed. See
[`RESULT-w002-managed-entry.md`](RESULT-w002-managed-entry.md) and
[`evidence/w002_host/ACCEPTANCE.md`](evidence/w002_host/ACCEPTANCE.md).

## W-003 quick-frame/XMM re-run (2026-07-26)

All four quick callee-save frame families use the shared Linux-shaped body on
Windows, while the explicit Microsoft C++-to-managed invoke/OSR boundaries
preserve XMM6-XMM11 in a separate 96-byte native area. Structural inspection
finds matched PE/ELF trap distributions and no probe symbols in product ART.

Focused Wine acceptance passes 8/8 attributed frame processes and 6/6 XMM
sentinel processes. Native Windows 10 build 19044 then passes exactly 19/19
records over the same 14-process matrix. Nterp and threshold-zero JIT each
attribute all four frame families; every XMM run reports
`mask=0 selfTestMask=63 iterations=128`; JIT logs confirm the corrected
pagefile-section J-2 dual view and successful compilation; and fatal/dump
scans are clean. W-003 is closed. The independent nterp implicit-null and
PE/SEH/native-unwind work remains W-010. See
[`tests/stages/w003/ANALYSIS.md`](../../../tests/stages/w003/ANALYSIS.md)
and [`evidence/w003_host/ACCEPTANCE.md`](evidence/w003_host/ACCEPTANCE.md).

The accepted native evidence above remains the historical XMM6-XMM11
checkpoint. W-010 has since expanded only the Windows boundary adapter to
XMM6-XMM15; focused Wine passes 6/6 with the retained `selfTestMask=63` and
authoritative `fullSelfTestMask=1023`. E9 repeats all six strengthened cases on
Windows Server 2025 build 26100 and accepts them natively.
