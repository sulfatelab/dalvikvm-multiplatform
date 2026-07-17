# Win64 Phase 4 — RESULT

**Status:** **WINE COMPLETE** — A5–A8 hardening gates PASS under wine64; host Phase-4 re-run recommended  
**Date:** 2026-07-16  
**Depends on:** Phase 3 complete (real Win10 G12 goldens)

## Scope (from win64_art_port §Phase 4)

- GC stress, multi-thread stress, crash dumps, resource/handle leaks
- Performance smoke (TLS/interpreter-level, not full JIT)
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

## Host

Rebuild package (includes Phase 4 jars/scripts):

```bash
bash tools/win64/host_package/package_win64_phase3.sh
# Windows: scripts\run_all_host.cmd  (now includes gcstress/threadheavy/handleleak/perfsmoke)
# Optional: scripts\run_crashabort.cmd
```

## Non-goals

- Full JIT/dex2oat (Phase 5)
- Windows NIO.2
- Production perf parity with Linux

## Next

- Host re-run Phase 4 subset on real Windows (recommended for full product claim)
- Phase 5 optional JIT

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
