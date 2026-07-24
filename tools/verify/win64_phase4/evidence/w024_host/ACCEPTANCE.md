# W-024 native Windows acceptance evidence

**Status:** PASS — native-host reachability gate complete
**Run date:** 2026-07-24
**Reviewed on:** 2026-07-24

## Host and package

- Windows 10 Enterprise LTSC 2021, version 2009, build 19044.
- Parent commit: `e7f90935c7b1909fe528a8441fa5014bcd666b95`.
- ART commit: `1a75ad10a3ee28910a7b46184a0a7628f96da72a`.
- Tripwire: `MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE=ON`.
- Shared `boot.jar`: 3,436,578 bytes, SHA-256
  `3cbe9a7f0e4596229c0c5e229e6655463373b1445922b9557286313a28a35a2a`.
- The returned `BUILD_INFO.txt` and `MANIFEST.json` are byte-identical to the
  package retained on `agent01`. All 169 manifest entries match the retained
  package by size and SHA-256.

## Runtime result

All nine native-Windows cases returned `exit=0` and
`logs/RESULT_W024.txt` ends in `OVERALL PASS`:

- Math CriticalNative: corrected dual view, J-1, and `-Xint`.
- Registered and unresolved CriticalNative with method tracing: dual view and
  J-1.
- Compiled normal/FastNative ABI, rebinding, and method tracing: dual view and
  J-1.
- JVMTI single-step forced interpretation: dual view and J-1.

The dual-view cases each created one 64 MiB J-2 mapping; the J-1 cases did not.
Every probe printed its expected result marker and
`main end exception=0`. No log contains the fatal InterpreterJni tripwire,
fatal/check/assert failure, access violation, or nonzero process exit.

With `ART_WIN64_JIT_LOG_COMPILES=1`, each normal/FastNative run compiled all
seven required targets exactly once before execution. Each JVMTI run compiled
the registered normal and FastNative targets exactly once and compiled no
CriticalNative target, matching ART's debuggable-runtime policy. Values remain
identical before, during, and after the single-step transition.

The corrected PowerShell recursive `*.dmp` scan returned `NO_DMP_FILES`. Its
content was transmitted in the supervisor console after the first attempted
scan used PowerShell's incompatible `dir` alias; `DMP_SCAN.txt` records the
successful scan result.

## Scope of this pass

This closes the W-024 real-Windows fallback-reachability gate. It does not by
itself close W-011, W-012, or W-024. The authorized next stage is to restore
the upstream pre-start-only interpreter bridge invariant, reduce the legacy
InterpreterJni resolver/shorties, remove the diagnostic native-JIT gate, then
rebuild Linux and Win64 and rerun the full regression matrix.
