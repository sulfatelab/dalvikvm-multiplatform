# Win64 Phase 4 — RESULT

**Status:** **WINE COMPLETE; FOCUSED NATIVE SUBSETS ACCEPTED** — A5–A8 and managed/native JIT hardening gates pass; W-002, W-003, W-004, and W-024 native closure matrices are accepted; W-010 Stages C-D, full-width XMM6-XMM15 static boundaries, split OSR unwind, and dynamic-JIT registration/lifecycle/fatal dispatch are focused-Wine verified and product implicit null/SO translation is active
**Date:** 2026-07-27
**Depends on:** Phase 3 complete (real Win10 G12 goldens)

## Scope (from win64_art_port §Phase 4)

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
| W-003 attributed frame families | **PASS, 8/8** | `run_w003_frame_probe.sh` |
| W-003 historical XMM6-XMM11 / W-010 full XMM6-XMM15 sentinel | **PASS, 6/6** | `run_w003_xmm_sentinel.sh` (`selfTestMask=63`, `fullSelfTestMask=1023`) |
| W-002 OSR matrix | **PASS, 8/8** | `run_w002_osr_probe.sh` |
| W-002 attached-thread matrix | **PASS, 8/8** | `run_w002_attach_probe.sh`; each raw thread now detaches, uses native stack, and reattaches |
| W-014 thread reservation/lifetime/fixed page | **PASS** | `run_thread_stack_probe.sh` |
| W-010 fault record/context adapter | **PASS** | `run_fault_adapter_probe.sh` (`failures=0 cases=8`; live probe `calls=2 first=0 second=0`) |
| W-010 JIT unwind serializer | **PASS, 6/6** | `run_jit_unwind_info_probe.sh` |
| W-010 JIT runtime registry | **PASS** | `run_jit_unwind_registry_probe.sh` (lookup, virtual unwind, delete, re-register) |
| W-010 JIT collection/reuse lifecycle | **PASS, J-2/J-1** | `run_jit_unwind_lifecycle.sh` (real collection, lookup disappearance, exact address reuse) |
| W-010 active nterp/JIT managed faults | **PASS** | `run_w010_managed_fault_probe.sh` (started-runtime no-chain rejection; 64 read + 64 write NPEs; repeated main/child SOEs in nterp and threshold-zero JIT; no handled-fault diagnostics/dump change) |
| W-010 threshold-zero JIT fatal dispatch | **PASS, J-2/J-1** | `run_jit_fatal_unwind.sh` (VEH, UEF, changed/new valid `MDMP`) |
| W-010 OSR-origin fatal dispatch | **PASS, J-2/J-1** | `run_osr_fatal_unwind.sh` (real switch OSR jump, VEH, UEF, new valid `MDMP`) |
| W-010/W-014 native package preflight | **PASS under Wine** | `package_win64_w010_w014.sh` (30-record runner, five fatal origins, per-case dump preservation, final package checker) |
| Full suite | **PASS** | `run_all_wine_gates.sh` |

Evidence: `evidence/all_wine_gates.txt`, `evidence/crashnative.txt`

### Native crash evidence (wine)

```text
ART Win64 VEH: exception 0xc0000005 ...
ART Win64 UEF: exception 0xc0000005 ...
ART Win64 crash: minidump written to .../run/crash/art-....dmp
PASS native_crash_aborts
```

## Landed code

| Item | Location |
|------|----------|
| UEF + MiniDumpWriteDump | `vendor/art/runtime/multiplatform/windows/runtime_windows.cc` (links `dbghelp`) |
| Phase 4 probes | `tools/verify/win64_phase4/src/*` |
| Native AV JNI | `tools/win64/jni_stubs/win_runtime_natives.c` |
| W-002 OSR adapters | `quick_entrypoints_x86_64.S`; `mterp/x86_64ng/main.S` |
| W-002 probes and native package | `run_w002_*.sh`; `package_win64_w002.sh` |
| W-003 XMM boundary and structural gate | `quick_entrypoints_x86_64.S`; `check_w003_quick_boundaries.py` |
| W-003 attributed frame-family gate | `w003_frame_probe/`; `run_w003_frame_probe.sh` |
| W-003 XMM runtime sentinel | `w003_xmm_sentinel/`; `run_w003_xmm_sentinel.sh` |
| W-003 native package and evidence | `package_win64_w003.sh`; `evidence/w003_host/ACCEPTANCE.md` |
| W-014 Stages A-B stack/pthread/page gate | `../win64_phase1/win32_thread_stack_probe.c`; `../win64_phase1/win32_stack_page_probe.cc`; `../win64_phase1/win32_stack_page_fault_probe.S`; `run_thread_stack_probe.sh` |
| W-010 Stage C adapter and probes | `../win64_phase1/win32_fault_record_probe.cc`; `../win64_phase1/win32_sigchain_probe.cc`; `run_fault_adapter_probe.sh`; `vendor/art/runtime/multiplatform/windows/sigchain_windows.cc` |
| W-010 Stage D activation and stress | `src/W010ManagedFaultProbe.java`; `run_w010_managed_fault_probe.sh`; common runtime null/SO flags and early nterp range registration |
| W-010 dynamic-JIT PE unwind | `runtime/multiplatform/windows/jit_unwind_windows.*`; `runtime/jit/{jit_code_cache,jit_memory_region}.*`; `run_jit_unwind_{info,registry,lifecycle}.sh`; `run_jit_fatal_unwind.sh` |
| W-010 static OSR PE unwind | `quick_entrypoints_x86_64.S`; `../win64_phase1/win32_osr_unwind_probe.cc`; `run_osr_unwind_probe.sh`; `check_win32_boundary_unwind.py` |
| W-010/W-014 native Stage E package | `package_win64_w010_w014.sh`; `host/RUN_W010_W014_HOST.ps1`; `check_w010_w014_host_package.py`; `review_w010_w014_host_result.py`; `W010_W014_HOST_CHECKLIST.md` |

## Host

Rebuild package (includes Phase 4 jars/scripts):

```bash
bash tools/win64/host_package/package_win64_phase3.sh
# Windows: scripts\run_all_host.cmd  (now includes gcstress/threadheavy/handleleak/perfsmoke)
# Optional: scripts\run_crashabort.cmd
```

Focused W-002 native acceptance:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/win64/host_package/package_win64_w002.sh
# Native PowerShell: .\scripts\RUN_W002_HOST.ps1
```

Focused W-003 native acceptance:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/win64/host_package/package_win64_w003.sh
# Native PowerShell: .\scripts\RUN_W003_HOST.ps1
```

The accepted Windows 10 build 19044 return has 19/19 PASS records over 14
children, clean fatal/dump scans, 8/8 attributed frame runs, and 6/6 XMM
sentinel runs. See `evidence/w003_host/ACCEPTANCE.md`.

Focused W-010/W-014 native Stage E candidate:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/win64/host_package/package_win64_w010_w014.sh
# Native PowerShell: .\scripts\RUN_W010_W014_HOST.ps1
```

The Linux-side preflight passes package integrity, the complete Wine matrix,
all five fatal origins, per-case preservation of valid minidumps, and the final
clean-package checker. Native execution and returned-evidence review remain
required; a Wine package smoke is not native acceptance.

## Non-goals

- Windows NIO.2
- Production perf parity with Linux
- Treating Wine as a substitute for an explicitly required native-host gate

## Next

- Complete W-014 Stages A-B/E native acceptance and W-010 native Stage E
  acceptance on Windows 10/current Windows: generated nterp/JIT NPE/SOE,
  foreign VEH/SEH/debugger ordering, stack-budget measurements, fatal
  predecessor-UEF/dump behavior, dynamic-table churn/sampling, and
  HSP-disabled/forced-policy cases. Repeat the split OSR/invoke unwind, full
  XMM6-XMM15 normal-return probes, JIT-origin fatal path, and OSR-origin fatal
  path on native Windows.
- Complete W-025 broader JIT-mapping native acceptance and hardening

## W-010 Stage D activation re-run (2026-07-27)

Win64 now enables common implicit null and stack-overflow checks, keeps x86_64
implicit suspend checks off, registers stack before null, and registers
nterp's immutable code range before startup can publish nterp entrypoints.
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
Win64 `art`/`dalvikvm`, Linux `art`/`dalvikvm`,
`dalvikvm -showversion`, and shared-boot imageless Hello also pass. Wine is
development evidence; native Windows Stage E remains required. See
[`RESULT-w010-managed-faults.md`](RESULT-w010-managed-faults.md).

## W-010 static OSR unwind re-run (2026-07-27)

`art_quick_osr_stub` now has two contiguous static PE runtime-function ranges.
The first uses fixed-bottom R12 while the copy body moves RSP downward, then
sets RBP to the copied RSP immediately before the OSR jump. This reproduces the
normal Win64 JIT frame anchor without changing generated JIT code. The second
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

Rebuilt PE in-tree (`build/win64_phase1`) from `dalvikvm-multiplatform` with
win64-dev-env + wine64 10.0.

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

The helper-based Win64 `LOAD_RUNTIME_INSTANCE` was replaced by a direct
same-image load of `Runtime::instance_`. The rebuilt Phase 4 aggregate passes,
including its new structural/source/dependency gate, with 574 direct
relocations and zero retired-helper references. Full focused results and the
accepted native-Windows closure are recorded in
[`RESULT-w004-runtime-load.md`](RESULT-w004-runtime-load.md).

## W-002 managed-entry re-run (2026-07-26)

The quick/switch OSR stub now keeps its Microsoft C++ entry, converts arguments
inside assembly, preserves Win64 nonvolatiles, and publishes rSELF in r15.
Windows nterp OSR now uses `NterpFree` and a separate return adapter instead
of assuming that nterp and compiled callee-save layouts match.

Focused Wine acceptance passes:

- structural/source/PE object inspection;
- OSR 2/2 in each dual/J-1 and default-nterp/switch pair;
- attached-thread JNI 2/2 in the same four pairs, with 16 native threads per
  process; and
- the complete Phase 4 aggregate.

The complete Phase 3 aggregate, Win64 build, Linux full build, Linux
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
[`RESULT-w003-quick-frames-analysis.md`](RESULT-w003-quick-frames-analysis.md)
and [`evidence/w003_host/ACCEPTANCE.md`](evidence/w003_host/ACCEPTANCE.md).

The accepted native evidence above remains the historical XMM6-XMM11
checkpoint. W-010 has since expanded only the Windows boundary adapter to
XMM6-XMM15; focused Wine passes 6/6 with the retained `selfTestMask=63` and
authoritative `fullSelfTestMask=1023`. Native repetition remains W-010 Stage E.
