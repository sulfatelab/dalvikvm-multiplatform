# Win64 P4 JIT matrix — probe suite under managed JIT

Date: 2026-07-22. VM: agent01, wine. Build: win64_phase1 RelWithDebInfo.

## Test: `run_jit_matrix.sh`

Runs the CEnc/float/Math/Io/Net/GC/throw probe suite under JIT (no `-Xint`),
verifying managed JIT does not regress any existing workload.

## Results: ALL 14 PASSED

| Probe | Class | Compiles | Assertion | Result |
|-------|-------|----------|-----------|--------|
| CEnc | CEnc | 18 | main end exception=0 | **PASS** |
| CEnc2 | CEnc2 | 17 | main end exception=0 | **PASS** |
| CELike | CELike | 15 | main end exception=0 | **PASS** |
| CFloat | CFloat | 15 | main end exception=0 | **PASS** |
| FloatProbe | FloatProbe | 23 | FloatProbe OK | **PASS** |
| IFloat | IFloat | 23 | IFloat OK | **PASS** |
| JLFloat | JLFloat | 15 | main end exception=0 | **PASS** |
| RFloat | RFloat | 15 | main end exception=0 | **PASS** |
| SFloat | SFloat | 15 | main end exception=0 | **PASS** |
| MathProbe | MathProbe | 24 | MathProbe.done=ok | **PASS** |
| IoProbe | IoProbe | 34 | IoProbe.done=ok | **PASS** |
| NetProbe | NetProbe | 30 | NetProbe.done=ok | **PASS** |
| GcProbe | GcProbe | 29 | GcProbe.done=ok | **PASS** |
| ThrowProbe | ThrowProbe | 22 | phase3-throw-ok | **PASS** |

## Observations

- Every probe compiled 15–34 managed methods under JIT (Baseline tier).
- No AV, no crash, no native compile — managed JIT is stable across
  character encoding, float, math, I/O, network, GC, and exception paths.
- M.jar excluded (contains Java .class not DEX; duplicate of MathProbe).
- ThrowProbe intentionally throws RuntimeException("phase3-throw-ok");
  the expected marker is present — correct behavior.

## Phase status

| Phase | Status |
|-------|--------|
| P3 | First compiled method — DONE (2026-07-21) |
| **P4** | **Matrix (CEnc, float, Math, Io) — DONE (2026-07-22)** |
| P5 | Harden (J-2, drop RWX, host Win10) — pending |

