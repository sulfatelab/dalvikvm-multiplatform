# Win64 Phase 4 — RESULT

**Status:** **WINE COMPLETE; FOCUSED NATIVE SUBSETS ACCEPTED** — A5–A8 and managed/native JIT hardening gates pass; W-002, W-003, W-004, and W-024 native closure matrices are accepted; W-010 Stage C adapter is focused-Wine verified and remains dormant
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
| W-003 attributed frame families | **PASS, 8/8** | `run_w003_frame_probe.sh` |
| W-003 XMM6-XMM11 sentinel | **PASS, 6/6** | `run_w003_xmm_sentinel.sh` |
| W-002 OSR matrix | **PASS, 8/8** | `run_w002_osr_probe.sh` |
| W-002 attached-thread matrix | **PASS, 8/8** | `run_w002_attach_probe.sh`; each raw thread now detaches, uses native stack, and reattaches |
| W-014 thread reservation/lifetime/fixed page | **PASS** | `run_thread_stack_probe.sh` |
| W-010 dormant fault record/context adapter | **PASS** | `run_fault_adapter_probe.sh` (`failures=0 cases=8`; live probe `calls=2 first=0 second=0`) |
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

## Non-goals

- Windows NIO.2
- Production perf parity with Linux
- Treating Wine as a substitute for an explicitly required native-host gate

## Next

- Keep W-010 dormant while implementing the atomic Stage D capability gate;
  prove generated nterp/JIT NPE/SOE and negative/chain cases before enabling
  implicit checks.
- Complete W-014 Stages A-B native acceptance and W-010 native Stage C/E
  acceptance on Windows 10/current Windows.
- Complete W-025 broader JIT-mapping native acceptance and hardening

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
