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
**Date:** 2026-08-01
**Depends on:** Phase 3 complete (historical real Win10 G12 goldens)

**Current lab policy:** All future native Windows gates use Windows Server
2025 Datacenter Evaluation x64 build 26100. The former Windows 10 host is no
longer available; the Windows 10 records in this file are retained as
historical evidence only. See the
[native Windows gate policy](../../../win32_host_gate_policy.md).

## Unified W-002 acceptance (2026-08-01)

The current authoritative W-002 path is the shell-free unified frontend and
virtual stage:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w002 --parallel 16
```

A fresh Windows Server 2025 x86-64 product tree built 1,485 Ninja edges and
then passed all four W-002 CTest gates: native synthetic PE unwind, managed
entry source/object review, attached-thread entry, and OSR. The identical
command repeated with `ninja: no work to do` and passed 4/4 again.

The attach and OSR runners each executed nterp and switch twice. Attach
completed 16 native attach/callback/detach cycles per execution and compiled
the managed callback. OSR observed baseline and OSR compilation, the compiled
jump, exact checksum, and the mode-specific completion behavior. Both
aggregate result files contain four successful records, no machine path, and
no dump. Non-following scans found zero reparse points in the source and
output trees; `sshd` and `lsass.exe` remained healthy.

The explicit FS-1 `art.dll` export boundary intentionally keeps transition
stubs private. The native unwind probe now resolves their addresses from the
adjacent `art.pdb` with DbgHelp wide-character APIs before exercising
`RtlVirtualUnwind`; it no longer assumes those implementation symbols are DLL
exports.

## Unified W-003 acceptance (2026-08-01)

The current authoritative W-003 path is the shell-free unified frontend and
virtual stage. The product and its exact test-only variant use distinct
fingerprinted output directories:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w003 --parallel 16
python tools/build_art.py configure --target-id windows-x86_64-msvc --variant win32-frame-attribution --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --variant win32-frame-attribution --build-type RelWithDebInfo --stage w003 --parallel 16
```

On Windows Server 2025 x86-64, product passed 4/4 and the frame-attribution
variant passed 5/5. Both identical repeats reported `ninja: no work to do` and
passed again. The matrices comprise four CriticalNative, four normal/FastNative,
six XMM, and variant-only eight frame-family processes. All aggregate JSON
records have zero dumps and no machine absolute path.

The structural gate reports 212 quick functions, 401 traps, and twenty XMM
unwind saves. Product `art.dll` has zero W-003 exports; the variant exports
only reset and snapshot while its four cross-object counters remain internal.
Non-following scans found zero reparse points in the source and both output
trees. A final-source Linux-hosted Windows cross build completed all 1,492
edges, passed the structural CTest gate, and repeated as a Ninja no-op.

## Unified W-004 acceptance (2026-08-01)

The current authoritative W-004 path is the shell-free unified frontend and
virtual stage:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w004 --parallel 16
```

Windows Server 2025 x86-64 passed 26/26, including the retained Phase-4 GC,
heavy-thread, handle-leak, performance-smoke, and restored Math
CriticalNative contracts. HandleLeakProbe, PerfSmokeProbe, and
ThreadHeavyProbe run through the shared Python managed runtime gate in
interpreter mode. The case-local Math runner executes `-Xint` and
threshold-zero JIT twice each, requires its Windows compiler record, and runs
the W-024 source-surface cleanup audit through the live structural reviewer.
Two final invocations both reported `ninja: no work to do.` and passed 26/26
in 38.48 and 46.85 seconds; their Math matrices passed in 5.59 and 5.64
seconds. All runners use exact marker checks and isolated output-owned work
roots.

A Linux-hosted Windows cross run with `--parallel 32` rebuilt 66 affected
test/JVMTI edges and passed the W-004 structural reviewer; its immediate repeat
was a Ninja no-op and passed again in 0.64 seconds. The old generic managed
builder and Wine runner, the Math wrapper, four other per-case wrappers, and
the aggregate Wine runner were retired. Historical Wine logs remain evidence,
not a maintained reproduction path.

The old W-004 host package was a composite of W-003 native-ABI, W-004
runtime/JVMTI/stress, and W-025 JIT-control behavior. After all three unified
stages passed natively and repeated as Ninja no-ops, its Bash producer and
repository-side PowerShell runner were retired. The package checker/reviewer,
historical checklist, accepted hashes, and returned text remain readable.

## Unified W-010 acceptance (2026-08-01)

The current authoritative W-010 path is the shell-free unified frontend and
virtual stage:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w010 --parallel 16
```

Windows Server 2025 passed all eight CTest gates twice. The stage covers UEF,
fault-record, sigchain/frame-SEH, debugger NPE/SOE continuation, managed abort,
static/JIT/OSR fatal dispatch, switch/nterp/JIT managed recovery, and the exact
linked boundary-unwind records for six private stubs. The reviewer resolves
those stubs from `art.pdb`; it does not make them DLL exports. Handled paths
created no dump; the three fatal origins each created exactly one valid `MDMP`.
Aggregate JSON contains no machine absolute path. The final build was a Ninja
no-op. A Linux-hosted Windows cross stage built the same four EXEs and three
managed JARs, passed the reviewer, and also repeated as a no-op.

The standalone W-010/W-014 package producer, its package-only PowerShell
runners, and the redundant fault/managed-fault Bash runners were retired.
Accepted E9/FS evidence and package checkers remain historical records. The
fatal JIT/OSR and general JIT smoke/matrix compatibility runners were retired
after their maintained semantics moved to unified W-010/W-025 declarations.

## Scope (from win32_art_port §Phase 4)

- GC stress, multi-thread stress, crash dumps, resource/handle leaks
- Performance smoke plus focused managed/native JIT, OSR, attach, ABI, tracing,
  and forced-interpreter transitions
- **Gate:** A5–A8 stable; no WSL

## Gate history and maintained reproduction

| Gate | Status | Command |
|------|--------|---------|
| P4_G1 GC stress | **PASS in unified native stage; historical Wine PASS** | `art.w004.managed_gc_stress` |
| P4_G2 Thread heavy | **PASS in unified native stage; historical Wine PASS** | `art.w004.managed_threadheavyprobe` |
| P4_G3 Handle leak smoke | **PASS in unified native stage; historical Wine PASS** | `art.w004.managed_handleleakprobe` |
| P4_G4 Perf smoke | **PASS in unified native stage; historical Wine PASS** | `art.w004.managed_perfsmokeprobe` |
| P4_G5 Java abort path | **PASS in unified native stage; historical Wine PASS** | `art.w010.managed_crashabortprobe` |
| P4_G5b Native AV + minidump | **PASS in unified native stage; historical Wine PASS** | `art.w010.managed_crashnativeprobe`; three fatal origins, VEH+UEF, and one valid `MDMP` each |
| P4_G6 GoldenApp regression | **PASS** | historical Phase-3 evidence; maintained as `art.w004.managed_goldenapp` |
| W-002 structural managed entries | **PASS in unified native stage** | `windows_w002_managed_entry_structure` |
| W-003 quick boundary/trap parity | **PASS in unified product and variant** | `windows_w003_quick_boundary_structure` |
| W-010 static OSR/invoke lookup and virtual unwind | **PASS in unified native W-002** | `art.w002.win32_osr_unwind_probe` (R12-anchored variable RSP entry, explicit RBP JIT handoff, managed-clobbered RBP return, GPR plus XMM6-XMM15 restore, invoke records, epilogue) |
| W-010 GenericJNI native-return virtual unwind | **PASS** | same probe: captured `+0xc5` return, variable native RSP, 5120-byte R12 anchor, repaired RDI `offset=0x1400`, caller RIP/RSP and all nonvolatile GPRs |
| W-010 switch-wrapper unwind | **PASS on native build 26100** | E5: live `ExecuteSwitchImplAsm + 0xd` lookup succeeds after the Windows-only RBX/home-area/unwind repair |
| W-010 interpreter-bridge unwind | **PASS on native build 26100** | E6: live primary `+0x82` lookup plus all later frames reach zero PC/UEF/dump; pending record remains structural/synthetic |
| W-003 attributed frame families | **PASS, unified variant 8/8** | `managed_w003_frame` |
| W-003 historical XMM6-XMM11 / W-010 full XMM6-XMM15 sentinel | **PASS, unified 6/6 per tree** | `managed_w003_xmm_sentinel` (`selfTestMask=63`, `fullSelfTestMask=1023`) |
| W-002 OSR matrix | **PASS, unified 4/4 executions; historical 8/8** | `managed_w002_osr`; nterp/switch twice each |
| W-002 attached-thread matrix | **PASS, unified 4/4 executions; historical 8/8** | `managed_w002_attach`; each raw thread detaches, uses native stack, and reattaches |
| W-014 thread reservation/lifetime/guarantee-aware bounds | **PASS** | unified `stage:w014` native gates; E9 raises/preserves/queries the guarantee and debits prefix + guarantee + moving guard |
| W-010 fault record/context adapter | **PASS in unified native stage** | `win32_fault_record_probe` (`failures=0 cases=8`) plus `win32_sigchain_probe` (`calls=2 first=0 second=0`) |
| W-010 JIT unwind serializer | **PASS, 6/6** | `run_jit_unwind_info_probe.sh` |
| W-010 JIT runtime registry | **PASS** | `run_jit_unwind_registry_probe.sh` (lookup, virtual unwind, delete, re-register) |
| W-010 JIT collection/reuse lifecycle | **PASS, J-2/J-1** | `run_jit_unwind_lifecycle.sh` (real collection, lookup disappearance, exact address reuse) |
| W-010 active switch/nterp/JIT managed faults | **PASS in unified native stage** | `managed_w010_fault_recovery`; six cases, repeated main/child SOEs, and no handled-fault diagnostics or dump |
| W-010 threshold-zero JIT fatal dispatch | **PASS, J-2/J-1** | `run_jit_fatal_unwind.sh` (VEH, UEF, changed/new valid `MDMP`) |
| W-010 OSR-origin fatal dispatch | **PASS, J-2/J-1** | `run_osr_fatal_unwind.sh` (real switch OSR jump, VEH, UEF, new valid `MDMP`) |
| Historical W-010/W-014 native package preflight | **PASS under Wine** | retired E9 package producer; immutable 30-record return and diagnostics remain accepted evidence |
| W-010/W-014 isolated failure diagnostics | **PASS on native build 19044** | runs 3-4: fixed-page SOE invalidated; UEF replacement ruled out; JNI hardware/raised AVs miss UEF while the JNI-created native worker reaches UEF/dump, isolating traversal through managed/GenericJNI frames. |
| W-010/W-014 complete E9 native host matrix | **PASS, 30/30 on build 26100** | guarantee-aware excluded-low accounting; switch/nterp/JIT managed SOE; zero handled dumps; five valid static/JIT/OSR fatal dumps |
| FS-1 RelWithDebInfo/Debug stack high-water | **PASS in unified native Stage-8 and historical package on build 26100** | unified `win32-stack-high-water` variant: switch/nterp/JIT, four complete records each; current RelWithDebInfo minimum margin 6448 bytes, Debug quick minimum 37120 bytes; no dumps; structural reviewer passed |
| FS-2 native debugger/CET/embedding/exception-XMM matrix | **PASS on native build 26100** | `../../../docs/history/windows_x64_fs2_w010_w014_result.md`; first-chance JIT NPE continue, explicit SOE no AV, nine incompatible CET rejections plus safe-policy acceptance, JNI UEF teardown, and 2x nterp/switch/JIT exception-XMM runs |
| Historical full Wine suite | **PASS** | retained `evidence/all_wine_gates.txt`; the aggregate runner is retired and maintained coverage uses unified native CTest |

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
| W-025 section/process policy probes | canonical sources under `../../../tests/cases/jit-section-policy/` and unified `stage:w025` |
| Native AV JNI | `tools/windows_x64/jni_stubs/win_runtime_natives.c` |
| W-002 OSR adapters | `quick_entrypoints_x86_64.S`; `mterp/x86_64ng/main.S` |
| W-002 unified probes and reviewer | `tests/cases/{attached-thread-entry,osr-unwind}`; `tests/support/windows/{w002_managed_entry_gate,check_w002_managed_entries}.py` |
| W-003 XMM boundary and structural gate | `quick_entrypoints_x86_64.S`; `check_w003_quick_boundaries.py` |
| W-003 unified managed gates | `../../../tests/cases/{jni-critical-native,jni-native-abi,w003-frame-probe,w003-xmm-sentinel}/`; `../../../tests/support/windows/w003_managed_gate.py` |
| W-003 historical native package evidence | `../../../tests/stages/w003/ANALYSIS.md` |
| W-014 native stack/pthread/page/growth/RX/CET gates | `tests/cases/pthread-once/`; `tests/cases/thread-stack/`; `tests/cases/stack-page-growth/`; `tests/cases/stack-executable-memory/`; `tests/cases/cet-stack-policy/`; `tests/support/runtime_gate.py` |
| W-010 unified gates | `tests/cases/{unhandled-exception-filter,fault-record,sigchain-fault,debugger-fault,fatal-runtime,managed-fault-recovery}`; `tests/CMakeLists.txt` |
| W-010 Stage C adapter and probes | `tests/cases/fault-record/probe.cc`; `tests/cases/sigchain-fault/probe.cc`; `vendor/art/runtime/multiplatform/windows/sigchain_windows.cc` |
| W-010 Stage D activation and stress | `tests/cases/managed-fault-recovery/{W010ManagedFaultProbe.java,run.py}`; common runtime null/SO flags and early nterp range registration |
| W-010 dynamic-JIT PE unwind | `runtime/multiplatform/windows/jit_unwind_windows.*`; `runtime/jit/{jit_code_cache,jit_memory_region}.*`; `run_jit_unwind_{info,registry,lifecycle}.sh`; `run_jit_fatal_unwind.sh` |
| W-010 static OSR PE unwind | `quick_entrypoints_x86_64.S`; unified `tests/cases/osr-unwind/` probe; unified `windows_w010_boundary_unwind_structure` reviewer |
| Historical W-010/W-014 Stage E package evidence | `check_w010_w014_host_package.py`; `review_w010_w014_host_result.py`; `W010_W014_HOST_CHECKLIST.md`; `W010_W014_DIAGNOSTICS.md`; accepted `evidence/` records |
| FS-1 stack high-water probe/evidence | unified source, current result, and historical package identity under `tests/cases/stack-high-water`; shell-free gates and structural reviewer under `tests/support/windows` |
| FS-2 debugger/CET/embedding/exception-XMM probes and evidence | `tests/cases/debugger-fault/probe.cc`; `tests/cases/cet-stack-policy/probe.cc`; `tests/cases/art-embedding/probe.cc`; `../../../docs/history/windows_x64_fs2_w010_w014_result.md` |

## Host

The historical Phase-3/4 aggregate shell package producer was retired after
its maintained behaviors moved to the unified virtual stages. Accepted package
text and hashes remain evidence only; do not reconstruct that package flow.

Focused W-002 native acceptance:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w002 --parallel 16
```

The former standalone package producer, Bash/Wine runners, package-only
PowerShell runner, and attach-only CMake graph were retired after this path
passed natively and repeated as a Ninja no-op. Returned package evidence and
hashes remain historical records.

Focused W-003 native acceptance on the 16 GiB Windows VM:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w003 --parallel 16
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo --variant win32-frame-attribution
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --variant win32-frame-attribution --stage w003 --parallel 16
```

The accepted Windows 10 build 19044 return has 19/19 PASS records over 14
children, clean fatal/dump scans, 8/8 attributed frame runs, and 6/6 XMM
sentinel runs. That package is historical and its producer and repository-side
runner are retired; see `../../../tests/stages/w003/ANALYSIS.md`.

Focused W-010 native gate on the 16 GiB Windows VM:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w010 --parallel 16
```

The old coupled W-010/W-014 package commands below this point describe issued
historical evidence only. Their producer and repository-side PowerShell
runners are retired; do not reconstruct them for a new acceptance run.

Focused FS-1 RelWithDebInfo/Debug stack high-water gate:

```text
python tools/build_art.py configure --target-id windows-x86_64-msvc --variant win32-stack-high-water --build-type RelWithDebInfo
python tools/build_art.py test --target-id windows-x86_64-msvc --variant win32-stack-high-water --build-type RelWithDebInfo --stage w014 --parallel 16
python tools/build_art.py configure --target-id windows-x86_64-msvc --variant win32-stack-high-water --build-type Debug
python tools/build_art.py test --target-id windows-x86_64-msvc --variant win32-stack-high-water --build-type Debug --stage w014 --parallel 16
```

The former phase-local CMake graph, Bash runner/package, and PowerShell package
runner were retired after this unified path passed both build types and their
Ninja no-op repeats. The immutable returned-package hashes remain historical
evidence, not a supported alternative reproduction path.

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
see `W010_W014_DIAGNOSTICS.md`.

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
see `W010_W014_DIAGNOSTICS.md`.

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
see `W010_W014_DIAGNOSTICS.md`.

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

The unified Stage-8 revalidation uses the exact test-only
`win32-stack-high-water` variant and the common CMake/Ninja graph. Both Debug
and RelWithDebInfo passed all nine W-014 CTests on Windows Server 2025 build
26100, including the migrated structural reviewer; both immediate reruns were
Ninja no-ops and passed again. Current minimum native margins are 70848/37120/
37248 bytes for Debug switch/nterp/JIT and 6448/7568/7632 bytes for
RelWithDebInfo. Each mode emitted four complete records with exit zero and no
dump. The source projection and both output trees contained zero reparse
points. Explicit source-level `art.dll` exports reduced Debug from 80,318
auto-export candidates to 1,938 real exports; RelWithDebInfo has 1,939.

The following package record is retained as the earlier independent native
acceptance:

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
`../../../tests/cases/stack-high-water/RESULT.md`.

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
retained in `../../../docs/history/windows_x64_fs2_w010_w014_result.md`.

## Non-goals

- Windows NIO.2
- Production perf parity with Linux
- Treating Wine as a substitute for an explicitly required native-host gate

## Next

- Keep E9's explicit Windows x64 stack checks and guarantee-aware bound accounting as
  the accepted product path; retain fixed-page operations only as direct
  diagnostics. The authoritative Windows Server 2025 build-26100 FS-4 repeat
  is archived in `../../../docs/history/windows_x64_fs4_same_host_result.md`.
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

The historical rebuilt complete Phase-4 aggregate reported
`PASS all wine Phase 4 gates`; its runner is now retired.
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
[`tests/stages/w004/ANALYSIS.md`](../../../tests/stages/w004/ANALYSIS.md).

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
W-002 is closed. The durable cross-case design, R1 diagnosis, deterministic R2
correction, and accepted native result are retained in
[`tests/stages/w002/ANALYSIS.md`](../../../tests/stages/w002/ANALYSIS.md).

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
[`tests/stages/w003/ANALYSIS.md`](../../../tests/stages/w003/ANALYSIS.md).

The accepted native evidence above remains the historical XMM6-XMM11
checkpoint. W-010 has since expanded only the Windows boundary adapter to
XMM6-XMM15; focused Wine passes 6/6 with the retained `selfTestMask=63` and
authoritative `fullSelfTestMask=1023`. E9 repeats all six strengthened cases on
Windows Server 2025 build 26100 and accepts them natively.
