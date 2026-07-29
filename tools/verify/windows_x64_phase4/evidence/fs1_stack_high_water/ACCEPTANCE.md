# FS-1 native Windows stack high-water acceptance

**State:** ACCEPTED
**Date:** 2026-07-29
**Host:** Microsoft Windows Server 2025 Datacenter Evaluation, x64, build 26100

## Issued package

```text
dist/windows_x64_fs1_stack_high_water.zip
size=53459106
sha256=22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe
```

The SHA-256 matched before and after transfer. The PowerShell runner verified
the package's complete internal `SHA256SUMS.txt` before starting either
runtime. The runner used absolute Windows paths, cleared the ART mode
environment before each child, and ran Release and Debug switch, nterp, and
threshold-zero JIT processes.

## Probe contract

FS-1 is compiled only with `ART_WIN32_STACK_HIGH_WATER=1`. Probe state is a
fixed-size, thread-owned scalar record. The overflow path performs direct RSP
stores without formatting or allocation at these points:

- failing generated explicit check;
- quick throw entry and completed save-all frame;
- common throw entry, expanded stack end, exception-construction entry,
  constructed exception, and restored default stack end; and
- quick exception delivery and long-jump frame.

Formatting, arithmetic, and completeness checks run only after Java catches
the `StackOverflowError`. The structural gate verifies that product `art.dll`
has neither the probe export nor probe asm offsets, while the instrumented
objects contain all direct stores. It also verifies seven nterp checks and the
optimizing failure branch.

## Accepted native result

`RESULT_FS1.txt` contains six PASS process records, no FAIL record, and ends
in `OVERALL PASS`:

```text
Release switch minimum_native_margin=6784
Release nterp  minimum_native_margin=7536
Release jit    minimum_native_margin=7616
Debug   switch minimum_native_margin=69744
Debug   nterp  minimum_native_margin=37168
Debug   jit    minimum_native_margin=37232
```

Every process emitted exactly four complete records in `main-1`, `main-2`,
`child-1`, `child-2` order. Each record passed phase, sequence, boundary,
reserve, and margin arithmetic. Both JIT methods were compiled where required.
`DMP_SCAN.txt` contains `NO_DMP_FILES`, and the accepted logs contain no ART
fatal VEH/UEF marker.

The final-source Wine reruns also pass with no dump-state change:

```text
Release switch=7536 nterp=7520 jit=7616
Debug   switch=69728 nterp=37216 jit=37232
```

## Native Debug diagnosis

The first native Debug run failed all engines with `STATUS_STACK_OVERFLOW`
while Wine passed. The captured dump's final exception mapped to
`art::gc::Heap::CheckPreconditionsForAllocObject` at
`runtime/gc/heap.cc:4555`, during `StackOverflowError` construction. This
showed that the normal 8192-byte ART recovery reserve was exhausted by
Clang-O0 Microsoft-ABI frames; the generated explicit check itself remained
correct.

A controlled 20,480-byte reserve made Debug switch pass, but nterp and JIT
still crossed the native boundary by approximately 8208 and 8196 bytes. The
accepted fix therefore uses 40 KiB only for non-`NDEBUG` Windows x86_64. It
leaves Release/product and every non-Windows build at 8192 bytes and leaves a
measured native Debug margin greater than 37 KiB on both quick engines.

Under Wine, Debug recursion can remain outside a safepoint beyond ART's
two-second default, so the probe runner uses
`-XX:ThreadSuspendTimeout=30000`. This is probe timing isolation, not a
product runtime change.

## Retained evidence

- `RESULT_FS1.txt`: exact native aggregate result.
- `WINDOWS_VERSION.txt`: accepted host identity.
- `DMP_SCAN.txt`: recursive accepted-package dump scan.
- `ARCHIVE_SHA256SUMS.txt`: immutable issued archive identity.

Full runtime logs and the package remain in ignored build/distribution storage;
large binaries, PDBs, and ZIP files are not committed.
