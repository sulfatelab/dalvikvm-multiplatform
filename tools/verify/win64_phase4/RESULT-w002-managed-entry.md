# W-002 managed-entry repair

**Status:** PASS — NATIVE WINDOWS R2 ACCEPTED; W-002 CLOSED

**Date:** 2026-07-26

**Host:** agent01

## Outcome

The Win64 rSELF design remains `r15`; Windows GS remains the TEB and
`InitCpu` correctly does not replace it. The residual failures were local ABI
and frame-layout defects in switch and nterp OSR transitions, not a reason to
change the managed Thread model.

The repaired paths now preserve the normal ART/Linux structure:

- platform C++ calls keep their platform ABI;
- Windows-only conversion stays at the assembly boundary;
- managed code observes rSELF in r15;
- Linux assembly remains on its original instruction path; and
- native attached threads publish rSELF only when they cross the existing
  quick-invoke boundary.

Native R2 accepts the complete managed-entry contract on Windows 10 build
19044. The deterministic default-nterp workload now enters compiled OSR in
both JIT memory modes, while switch OSR and attached-thread entry retain their
previously passing behavior. W-002 is closed.

## Quick/switch OSR root cause and fix

`jit.cc` declares and calls `art_quick_osr_stub` as an ordinary C++
function. On Windows this supplies:

- rcx: copied stack;
- rdx: copied-stack size;
- r8: compiled native PC;
- r9: result pointer;
- stack argument 5: shorty; and
- stack argument 6: `Thread*`.

The assembly body previously consumed the SysV register layout directly and
never published the explicit `Thread*` into r15.

The Windows prologue now:

1. saves rdi and rsi, which are Microsoft nonvolatile;
2. reads the two stack arguments after accounting for those saves;
3. converts the six arguments into the shared SysV-shaped body;
4. saves the native caller's r15 in the common callee-save block;
5. publishes `Thread*` into r15 before the OSR jump; and
6. restores r15/rsi/rdi before returning through the native C++ caller.

The Win64 CFA is 96 bytes. Linux retains the original 80-byte CFA and does not
execute the Windows conversion.

## Nterp OSR root causes and fix

The first nterp defect was an assembly call to `free` with its pointer in rdi
and without Microsoft x64 shadow space. Windows now calls `NterpFree`, the
existing assembly-facing SysV-to-Microsoft bridge.

Using only that bridge removed the UCRT ABI violation but exposed a second
failure. Compiled OSR returned with an invalid restoration stack because the
Linux transition treats nterp's save block as the compiled OSR callee-save
frame. That assumption is valid when the layouts match. It is invalid on
Windows because:

- nterp saves r15 as part of its native/nonvolatile state;
- managed r15 is pinned as rSELF; and
- the Win64 optimizing compiler excludes r15 from its compiled spill set.

The Windows nterp transition now keeps the original nterp save block as a
return adapter and copies the full compiled OSR frame below it. Compiled code
returns to the adapter, which removes alignment padding, restores
XMM12–XMM15 and rbx/rbp/r12–r15, and returns to the original managed caller.
The compiled result stays in rax/xmm0.

Linux retains its original direct frame reuse and libc `free`.

## Attached-thread contract

`AttachCurrentThread` and `AttachCurrentThreadAsDaemon` establish
`Thread::Current()` in ART's C++ TLS. They must not reserve or overwrite a
native caller's r15. JNI `CallStaticLongMethod` enters through
`ArtMethod::Invoke`, whose Win64 quick boundary preserves native r15 and
publishes the attached `Thread*` for managed code.

Each attach process:

- warms and JIT-compiles `W002AttachProbe.attachedCallback`;
- creates eight regular and eight daemon Win32 threads;
- attaches each thread through the matching JNI API;
- enters the pre-JITed Java callback;
- verifies `Thread.currentThread()` and daemon state;
- allocates Java objects;
- validates an exact 64-bit return value;
- detaches; and
- requires `GetEnv == JNI_EDETACHED`.

## Permanent gates

| Gate | Purpose |
|------|---------|
| `check_w002_managed_entries.py` | Source, Win64 object, relocation, r15 compiler, CFA, `NterpFree`, and Linux-path invariants |
| `run_w002_osr_probe.sh` | Baseline compile, OSR compile, jump, exact checksum, switch/nterp return-path distinction |
| `run_w002_attach_probe.sh` | Regular/daemon native attach into a pre-JITed Java callback |
| `run_all_wine_gates.sh` | Runs all three W-002 gates before the broader Phase 4 suite |

The structural gate requires:

- the normal platform ABI on the C++ declaration;
- ordered Microsoft-to-SysV conversion and r15 publication in source and PE
  object code;
- preservation of Win64 rdi/rsi and the Linux 80-byte CFA;
- the Windows 96-byte CFA;
- exactly one nterp relocation to `NterpFree` and no raw `free` relocation;
- the Windows nterp return-adapter sequence;
- Win64 compiler Thread accesses through r15; and
- r15 excluded from the Win64 compiled callee-save set.

## Focused Wine results

### OSR

| JIT memory | Interpreter | Result |
|------------|-------------|--------|
| Corrected dual view | Default nterp | 2/2 |
| Corrected dual view | Switch | 2/2 |
| J-1 diagnostic | Default nterp | 2/2 |
| J-1 diagnostic | Switch | 2/2 |

All eight processes report:

- `warmup_threshold=100, optimize_threshold=100`;
- baseline compilation;
- OSR compilation;
- `Jumping to long W002OsrProbe.osrLoop(int)`;
- `W002OsrProbe OK checksum=65553463744`; and
- `main end exception=0`.

Switch runs additionally report the switch OSR completion marker. Nterp runs
must not use that return path.

### Attached threads

| JIT memory | Interpreter | Result |
|------------|-------------|--------|
| Corrected dual view | Default nterp | 2/2 |
| Corrected dual view | Switch | 2/2 |
| J-1 diagnostic | Default nterp | 2/2 |
| J-1 diagnostic | Switch | 2/2 |

All eight processes compile the callback, report
`W002AttachProbe OK completed=16`, and finish with no exception. This is 128
successful native-thread attach/callback/detach lifecycles across the focused
matrix: 64 regular and 64 daemon.

## Broader regression results

| Control | Result |
|---------|--------|
| Complete Win64 build, `-j32` | PASS |
| Full Phase 3 Wine aggregate | PASS all gates |
| Full Phase 4 Wine aggregate | PASS all gates |
| JIT smoke | 12/12 |
| JIT matrix | 14/14 |
| Normal/FastNative default and tracing | 7/7 + 7/7 |
| CriticalNative dual and J-1 | 4/4 signature + 2/2 instrumentation per mode |
| JVMTI forced interpreter dual and J-1 | 2/2 per mode |
| Complete Linux build, `-j32` | PASS |
| Linux shared-boot imageless Hello | PASS |
| Linux GC stress | PASS |
| Linux nterp baseline-to-OSR transition | PASS with exact checksum |

The clean Linux rebuild exposed an unrelated compatibility-header issue:
`compat/include/sys/sendfile.h` was overriding glibc's `sendfile64`
prototype. The header is now Windows-only and uses the system header on Linux.
Both Linux and Windows hybrid libcore builds pass after that correction.

## Native Windows package

Generate the issued package with:

```bash
JOBS=32 WINEDEBUG=-all \
  bash tools/win64/host_package/package_win64_w002.sh
```

Package generation:

- rebuilds ART;
- reruns the structural and 16-process focused Wine matrix;
- stages product PE artifacts and both W-002 jars/DLL;
- embeds an artifact-bound structural report;
- validates the manifest and required PE exports;
- runs all eight mode pairs once from the staged package under Wine;
- cleans runtime outputs;
- regenerates and rechecks the final manifest; and
- creates `dist/win64_w002_host.zip`.

The R2 staged package smoke passes 8/8 processes, and ZIP integrity passes.
The native runner repeats every pair twice, enforces Windows build 17134 or
later, validates package hashes and structural-report artifact identities,
scans fatal markers, and recursively rejects any `*.dmp`.

See [W002_HOST_CHECKLIST.md](W002_HOST_CHECKLIST.md). Accept returned evidence
with:

```bash
python3 tools/verify/win64_phase4/review_w002_host_result.py \
  /path/to/returned.zip --issued dist/win64_w002_host
```

The accepted native result has 21 PASS records over 16 child processes and
ends in `OVERALL PASS`.

## Native Windows R1 result

R1 evidence is `/tmp/w002-run1.zip`, SHA-256
`0a1fa8ac02a3eba7d536d539c8fc77ad7c596e93e85c3bbc07191ba66e6e6b81`.
It was produced on Windows 10 Enterprise LTSC build 19044 x64 with PowerShell
5.1. The evidence archive and the issued package have identical
`BUILD_INFO.txt`, `MANIFEST.json`, `SHA256SUMS.txt`, and
`W002_STRUCTURAL_REPORT.txt` metadata.

The native result contains 17 PASS and 4 FAIL records:

| Control | Native R1 result |
|---------|------------------|
| Host and package identity | PASS |
| Artifact-bound structural report | PASS |
| Attached threads, all four mode pairs, two repeats | PASS, 8/8 |
| Switch OSR, dual and J-1, two repeats | PASS, 4/4 |
| Default-nterp OSR, dual and J-1, two repeats | INCOMPLETE, 0/4 required jumps |
| Fatal-log scan | PASS |
| Recursive crash-dump scan | PASS, `NO_DMP_FILES` |

All 16 child processes exited zero without a timeout. Every OSR process
returned the exact checksum and `main end exception=0`. Both dual/default
runs and J-1/default run 2 completed baseline and OSR compilation, but the
loop ended without `Jumping to long W002OsrProbe.osrLoop(int)`. J-1/default
run 1 completed baseline compilation before the loop ended.

The R1 command supplied `-Xjitthreshold:100` but not
`-Xjitwarmupthreshold`. Its runtime configuration therefore reported
`warmup_threshold=65535, optimize_threshold=100`. Native nterp completed the
300,000-iteration loop before asynchronous OSR installation was followed by
another hotness check that could enter compiled code. The slower Wine runs
had enough time to make the same workload pass, so the previous gate was
timing-dependent.

R2 must explicitly lower the warmup threshold and lengthen the exact-checksum
workload. This is a test-determinism correction. R1 contains no evidence of a
crash, runtime corruption, bad result, or failure in the nterp return adapter;
that adapter remains unaccepted on native Windows until R2 records the jump.

The R2 reviewer accepts this evidence-only return form after exact byte
comparison of `BUILD_INFO.txt`, `MANIFEST.json`, `SHA256SUMS.txt`, and
`W002_STRUCTURAL_REPORT.txt`. If any non-identity payload file is returned,
the reviewer requires the complete issued payload and re-hashes every file;
partial payloads are rejected. Strict log, result-record, fatal-marker, and
dump checks remain unchanged.

## Deterministic R2 correction and verification

R2 makes the timing contract explicit instead of relying on Wine being slower
than a native host:

- every OSR command supplies `-Xjitwarmupthreshold:100` and
  `-Xjitthreshold:100`;
- every OSR log must confirm
  `warmup_threshold=100, optimize_threshold=100`;
- the loop runs 2,000,000 iterations and must return exact checksum
  `65553463744`; and
- the native runner still requires baseline compile, OSR compile, the OSR jump,
  clean return, interpreter-specific return markers, and no fatal log or dump.

The revised pre-issue verification passes:

| Control | R2 result |
|---------|-----------|
| Reviewer and OSR contract unit tests | PASS, 7/7 |
| Source and PE object structural gate | PASS |
| Focused Wine OSR, four mode pairs, two repeats | PASS, 8/8 |
| Focused Wine attach, four mode pairs, two repeats | PASS, 8/8 |
| Complete Win64 build, `-j32` | PASS |
| Complete Linux build, `-j32` | PASS |
| Linux shared-boot imageless Hello and GC stress | PASS |
| Linux nterp baseline/OSR/jump/checksum | PASS with thresholds 100/100 and checksum `65553463744` |
| Full Phase 3 Wine aggregate | PASS all gates |
| Full Phase 4 Wine aggregate | PASS all gates |
| R1 evidence-only identity handling | PASS; review proceeds to the genuine `OVERALL FAIL` result instead of reporting a missing payload |

R2 does not alter ART runtime code or the Windows/Linux managed-entry design.
It removes nondeterminism from the acceptance workload and fixes the offline
evidence transport contract.

## Native Windows R2 acceptance

The accepted run started at `2026-07-26 14:37:55` on Windows 10 Enterprise
LTSC x64 build 19044 with Windows PowerShell 5.1.19041.7548. It used issued
root commit `5cc3e2b52834b42f2f9b135ce2bbb2fd5dcd43ec` and ART commit
`0bc7b10e1ca53df2e0c3bd9bbc3291c6513862e2`.

`RESULT_W002.txt` contains 21 PASS records, zero FAIL records, and final
`OVERALL PASS`:

- host OS, package integrity, and the artifact-bound structural report pass;
- all 8/8 OSR processes exit zero without timeout;
- all four default-nterp runs report thresholds 100/100, baseline and OSR
  compilation, the OSR jump, checksum `65553463744`, and clean return without
  the switch completion marker;
- all four switch runs report the same common markers plus their required
  switch completion marker;
- all 8/8 attach processes compile the callback, complete 16 regular/daemon
  thread lifecycles each, and return cleanly;
- fatal-marker scanning passes; and
- recursive dump scanning reports `NO_DMP_FILES`.

The returned archive `/tmp/w002-r2-log.zip` has SHA-256
`2c49fe7161f96e98ae74dcd4e610eee775dfff21234673c902c7d4bf58e5df7e` and
passes ZIP integrity testing. It omitted the root `MANIFEST.json` while the
evidence files were copied, so the unchanged strict reviewer correctly
reported the missing identity file. This is a transport omission rather than
a host-run failure:

- `PASS package_integrity` proves the manifest existed and matched its issued
  hash during the native run;
- returned `BUILD_INFO.txt`, `SHA256SUMS.txt`, and
  `W002_STRUCTURAL_REPORT.txt` are byte-identical to the issued package;
- the exact returned sums record manifest SHA-256
  `e48211612ce16c84acca6af1aca3f749b4c88112f99e31d76b0ace2bd519e125`;
  and
- adding only that retained byte-identical manifest produces
  `/tmp/w002-r2-log-normalized.zip`, SHA-256
  `8aea7af225f154678d50ea7b329ce8574242c2e8cea8c947170c4a58f916bc03`,
  which passes ZIP integrity and the unchanged strict reviewer as an
  evidence-only return.

No runtime log or result record was altered during normalization. See
[`evidence/w002_host/ACCEPTANCE.md`](evidence/w002_host/ACCEPTANCE.md).
This evidence satisfies the final native-host gate and closes W-002.
