# Win64 P4 JIT matrix — probe suite under managed JIT

Date: 2026-07-23. VM: agent01, Wine. Build: win64_phase1 RelWithDebInfo.

## Test: `run_jit_matrix.sh`

Runs the CEnc/float/Math/Io/Net/GC/throw probe suite under the default corrected
pagefile-backed dual-view JIT (no `-Xint`), verifying managed JIT does not
regress any existing workload.

## Results: ALL 14 PASSED

| Probe | Class | Compiles | Assertion | Result |
|-------|-------|----------|-----------|--------|
| CEnc | CEnc | 17 | main end exception=0 | **PASS** |
| CEnc2 | CEnc2 | 20 | main end exception=0 | **PASS** |
| CELike | CELike | 15 | main end exception=0 | **PASS** |
| CFloat | CFloat | 15 | main end exception=0 | **PASS** |
| FloatProbe | FloatProbe | 25 | FloatProbe OK | **PASS** |
| IFloat | IFloat | 22 | IFloat OK | **PASS** |
| JLFloat | JLFloat | 15 | main end exception=0 | **PASS** |
| RFloat | RFloat | 15 | main end exception=0 | **PASS** |
| SFloat | SFloat | 15 | main end exception=0 | **PASS** |
| MathProbe | MathProbe | 23 | MathProbe.done=ok | **PASS** |
| IoProbe | IoProbe | 34 | IoProbe.done=ok | **PASS** |
| NetProbe | NetProbe | 28 | NetProbe.done=ok | **PASS** |
| GcProbe | GcProbe | 29 | GcProbe.done=ok | **PASS** |
| ThrowProbe | ThrowProbe | 26 | phase3-throw-ok | **PASS** |

## Observations

- Every probe compiled 15–34 managed methods under JIT (Baseline tier).
- No AV, no crash, no native compile — managed JIT is stable across
  character encoding, float, math, I/O, network, GC, and exception paths.
- The default mapping is the corrected contiguous low R/RX primary view plus
  coherent RW updater alias; no filesystem-backed temporary file is used.
- M.jar excluded (contains Java .class not DEX; duplicate of MathProbe).
- ThrowProbe intentionally throws RuntimeException("phase3-throw-ok");
  the expected marker is present — correct behavior.

## Phase status

| Phase | Status |
|-------|--------|
| P3 | First compiled method — DONE (2026-07-21) |
| **P4** | **Matrix (CEnc, float, Math, Io) — DONE (2026-07-22)** |
| **P5 (Wine)** | **Corrected dual view default; 12/12 smoke and 14/14 matrix — DONE (updated 2026-07-24)** |
| P5 (real Windows) | Mapping/mitigation checks and J-1 diagnostic-opt-out cleanup — pending; focused W-024 native acceptance complete |
