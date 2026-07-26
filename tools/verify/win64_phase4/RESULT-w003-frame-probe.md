# W-003 attributed quick-frame family probe

**Status:** NATIVE WINDOWS ACCEPTED — W-003 closed

**Date:** 2026-07-26

**Host:** agent01

## Outcome

The opt-in W-003 probe now attributes execution to all four x86-64 ART
runtime callee-save frame families without changing product artifacts:

- refs-only;
- refs-and-args;
- all-callee-saves; and
- save-everything.

Two complete runs pass in `-Xint`, forced switch interpreter, nterp, and
threshold-zero JIT modes. Nterp and JIT each independently report positive
counts for all four families. The interpreted modes remain useful controls:
they complete the same workloads, but their C++ interpreter paths do not
necessarily enter the refs-only or all-callee-saves quick stubs.

## Instrumentation design

The normal build leaves `MDVM_W003_FRAME_PROBE` disabled. An instrumented
build defines `ART_W003_FRAME_PROBE` only for
`quick_entrypoints_x86_64.S` and adds one counter at each canonical SETUP
family. Each increment is atomic and enclosed by `pushfq`/`popfq`, preserving
the entrypoint's incoming condition flags. The counters and the two snapshot
exports exist only when both `_WIN32` and `ART_W003_FRAME_PROBE` are defined.

The instrumented DLL exports:

```text
art_w003_frame_probe_reset
art_w003_frame_probe_snapshot
```

The runner rejects either export or any counter symbol in the rebuilt product
Win64 object. The rebuilt Linux object also contains no probe symbols. Thus
the probe is a diagnostic build feature, not a product code path or runtime
workaround.

## Workloads and attribution

The managed probe uses deterministic named phases:

- refs-only: contended monitors, thread transitions, and allocation pressure;
- refs-and-args: 2,000 generic JNI calls with an exact checksum;
- all-callee-saves: separately logged class-cast and array-store throws;
- save-everything: bounds throws and method-tracing/instrumentation hooks.

The class-cast, array-store, and bounds subtests each catch exactly 1,000
exceptions. The JNI phase returns exactly `2001000`; all processes finish
with `main end exception=0`.

Representative final phase counters from the two-repeat run are:

| Mode | Refs-only phase | Refs-and-args phase | Throw phase | Tracing phase |
|------|-----------------|---------------------|-------------|---------------|
| `-Xint` | `refs_only=0` | `refs_and_args=2001` | `all_callee_saves=0` | `everything=1` |
| switch | `refs_only=0` | `refs_and_args=2001` | `all_callee_saves=0` | `everything=1` |
| nterp | `refs_only=4113..4155` | `refs_and_args=2001` | `all_callee_saves=2000`, `everything=1000` | `everything=1` |
| JIT | `refs_only=4101` | `refs_and_args=2` | `all_callee_saves=2000`, `everything=1028` | `everything=1` |

Counts outside the named target family are expected because Java logging,
JNI snapshots, compilation, exception delivery, and tracing also use quick
frames. Acceptance therefore requires positive attributed counters at the
intended phases instead of brittle exact totals.

## Nterp implicit-null isolation

The first draft also executed `null.hashCode()` and crashed in nterp. The
instrumented fault address resolved to `nterp_op_invoke_virtual+0x3a`, the
implicit class load through a zero receiver. A null-only probe then reproduced
the same fault at `nterp_op_invoke_virtual+0x3a` in the ordinary,
non-instrumented product DLL.

This is not counter corruption. On the current Windows path,
`FaultManager::Init(false)` does not install ART's POSIX generated-code fault
handler, while `ArtVectoredHandler` only logs an access violation and returns
`EXCEPTION_CONTINUE_SEARCH`. The implicit nterp null check is therefore not
translated into `NullPointerException`.

That fault-to-managed-exception work belongs to W-010. W-003 deliberately
excludes the implicit-null subtest and retains explicit class-cast,
array-store, and bounds paths. This is test-scope isolation, not a product
fallback; no null-check workaround was added to ART or nterp.

## Verification

Primary command:

```bash
REPEATS=2 bash tools/verify/win64_phase4/run_w003_frame_probe.sh
```

Result:

```text
W-003 frame probe int run=1 PASS
W-003 frame probe int run=2 PASS
W-003 frame probe switch run=1 PASS
W-003 frame probe switch run=2 PASS
W-003 frame probe nterp run=1 PASS
W-003 frame probe nterp run=2 PASS
W-003 frame probe jit run=1 PASS
W-003 frame probe jit run=2 PASS
W-003 four-family functional matrix: int/switch/nterp/JIT, 2 repeat(s): PASS
```

Post-probe controls:

```text
Win64 product art/dalvikvm rebuild: PASS
Linux art/dalvikvm rebuild: PASS
W-003 PE/ELF structural parity: PASS (212 functions, 401 traps)
W-002 managed-entry structural check: PASS
W-004 Runtime-load structural check: PASS
Linux imageless Hello: PASS, exit 0
W-003 XMM sentinel: PASS, 2/2 nterp + 2/2 switch + 2/2 JIT
Full Phase 4 Wine aggregate: PASS
```

## Native Windows package

The focused native-host package is built and verified with:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/win64/host_package/package_win64_w003.sh
```

The pipeline reruns the structural checker, the 8-process frame matrix, and
the 6-process XMM matrix before staging. It then checks package hashes and PE
exports, runs one independent Wine smoke per mode from the staged tree,
restores the product `art.dll`, removes runtime output, rebuilds the manifests,
and checks the final package again. The completed pipeline reports:

```text
W-003 host package check: PASS
W-003 host package Wine smoke: PASS
W003_HOST_PACKAGE_PASS path=.../dist/win64_w003_host.zip
```

The package carries `art.product.dll`, the opt-in `art.frame-probe.dll`, both
JNI probe DLLs and jars, a precomputed structural report, full SHA-256
manifests, and [W003_HOST_CHECKLIST.md](W003_HOST_CHECKLIST.md). Its PowerShell
runner requires Windows build 17134 or newer and no compiler, JDK, LLVM tools,
or network connection. It runs 8 frame processes plus 6 XMM processes, scans
all logs for fatal markers, recursively scans the package for dumps, and
restores the product ART variant even on failure.

The accepted native run returns exit 0, exactly 19 `PASS` records,
`OVERALL PASS`, and `NO_DMP_FILES`. The native logs remain external evidence;
they are not pre-populated in the issued archive.

## Native Windows acceptance and closure

Native Windows 10 build 19044 passes the complete packaged matrix: 8/8 frame
processes, 6/6 XMM processes, 19/19 PASS records, clean fatal-marker scan, and
`NO_DMP_FILES`. Nterp and JIT independently reach all four frame families; all
six native XMM runs return `mask=0 selfTestMask=63 iterations=128`. The JIT
logs explicitly confirm construction of the Windows pagefile-section J-2
dual view and successful workload compilation.

The accepted package and returned evidence are documented in
[evidence/w003_host/ACCEPTANCE.md](evidence/w003_host/ACCEPTANCE.md). W-003 is
closed. PE quick-assembly unwind and generated-fault translation remain with
W-010 as documented in the main W-003 analysis.
