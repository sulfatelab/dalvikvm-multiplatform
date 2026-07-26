# W-003 native Windows R1 acceptance evidence

**Status:** PASS — W-003 closed

**Run date:** 2026-07-26 17:17:00

**Reviewed on:** 2026-07-26

## Host and package identity

- Windows 10 Enterprise LTSC x64, version 10.0.19044, build 19044.
- Windows PowerShell 5.1.19041.7548.
- Root branch: `main`.
- Root commit: `79c4f18fff8e510b579b27f66967e48e93393ecd`.
- ART branch: `artmp_android-16.0.0_r4`.
- ART commit: `1b2afe73fafcffda1891e4d925a870c3ed328cbe`.
- Issued package SHA-256:
  `59d2e85926bbbed59e02c2c07e79b7362b4d60f1a08cd62093938053dbd81289`.
- Returned archive `/tmp/w003-log-r1.zip` SHA-256:
  `e4f76840ae12153f73cca1101a59e421d2a0e4de1f9fd0cd54f9c915cd3d6eb8`.

The returned evidence-only archive has 51 safe entries, passes ZIP integrity
testing, and contains no absolute or parent-traversal path. Its
`BUILD_INFO.txt`, `MANIFEST.json`, `SHA256SUMS.txt`, and root structural report
are byte-for-byte identical to the issued package metadata. The structural
report copied under `logs` is also identical to the root report. The native
runner reports `PASS package_integrity` and `PASS structural_report`.

## Structural contract

The accepted report records:

- zero W-003 probe exports in product ART;
- two probe-control exports in instrumented ART;
- all four frame-counter symbols in the instrumented quick object;
- all three frame-probe JNI exports;
- the XMM-sentinel JNI export;
- all six `SAVE_XMM128` unwind operations in the sentinel wrapper; and
- matched PE/ELF quick-entrypoint trap distributions: 212 functions and 401
  shared traps, with no Windows-only SETUP trap.

The product, instrumented ART, frame-probe DLL, and XMM-sentinel DLL hashes in
the report match the issued package manifest.

## Runtime result

`RESULT_W003.txt` contains exactly 19 PASS records, zero FAIL records, and
final `OVERALL PASS`. All 14 child processes exit zero without timeout,
launch error, missing marker, counter error, or pending exception. The
combined logs contain the exact corresponding raw stdout and stderr streams.

The native frame-family matrix passes twice in every mode. Target counters at
the accepted phase are:

| Mode | Refs-only | Refs-and-args | All-callee-saves | Everything |
|------|----------:|--------------:|-----------------:|-----------:|
| `-Xint`, 2/2 | 0 | 2001 | 0 | 1 |
| switch, 2/2 | 0 | 2001 | 0 | 1..5 |
| nterp, 2/2 | 4100..4124 | 2001 | 2000 | 1 |
| threshold-zero JIT, 2/2 | 4101 | 2 | 2000 | 1 |

Zero refs-only and all-callee-saves counts in the two C++ interpreter controls
are expected. Nterp and JIT independently produce positive attributed counts
for all four families. Every process reports the exact workload checksums and
terminal checksum `4554857990073223`. Both JIT runs contain successful
compilation records for the W-003 frame workload.

The native XMM6-XMM11 sentinel passes 2/2 in nterp, switch, and threshold-zero
JIT modes. Every process reports:

```text
mask=0 selfTestMask=63 iterations=128
W003XmmSentinelProbe OK
main end exception=0
```

Both JIT runs successfully compile
`W003XmmSentinelProbe.managedCallback(double, ... double)`.

## Diagnostic review

The native JIT logs first record the expected unavailable POSIX
`memfd_create()` attempt and then explicitly report:

```text
Win64 JIT dual-view (J-2) created
```

Therefore the native JIT cases use the corrected unnamed pagefile-section
dual view, not the J-1 diagnostic fallback. Fast compilation attempts that
cannot handle a method are followed by successful baseline compilation.

Other repeated diagnostics are known harness or Windows-port messages: the
deliberately nonexistent boot image followed by imageless fallback, the
Windows `SetCloseOnExec` no-op, unavailable sentinel fault-page reservation,
noncanonical dex-location/odex warnings, and unimplemented CPU-time logging.
They do not alter the exact probe results or process exits.

Independent case-insensitive scanning finds none of the fatal, access
violation, VEH, UEF, or `STATUS_ACCESS_VIOLATION` markers. Recursive dump
scanning reports `NO_DMP_FILES`; the return contains no `.dmp` or `.trace`
file.

## Scope boundary and closure

The frame workload deliberately excludes nterp implicit-null translation.
That fault reproduces in ordinary product ART and remains owned by W-010; no
W-003 product workaround was added. Explicit class-cast, array-store, and
bounds paths remain covered.

This evidence satisfies the final W-003 native-host closure condition: no
Windows-only SETUP trap, all four frame families attributed under nterp and
JIT, Microsoft XMM6-XMM11 preservation proven at the native boundary, clean
fatal/dump scans, and successful native Windows repetition.
