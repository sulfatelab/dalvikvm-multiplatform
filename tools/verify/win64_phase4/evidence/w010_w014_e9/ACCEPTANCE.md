# W-010/W-014 E9 native acceptance

**State:** ACCEPTED
**Date:** 2026-07-28
**Host:** Microsoft Windows Server 2025 Datacenter Evaluation, x64, build 26100

## Issued package

```text
dist/win64_w010_w014_e9_native.zip
sha256=2b84c911dfbe23dd5dd13917a0fb4a63bdbf90901172f74dfe642ed1fd20f16f
stage=E9-configured-guarantee-explicit-stack-checks
```

The returned full package matched the issued identity and payload. The
independent reviewer reported:

```text
W-010/W-014 native Stage E result:
PASS (build=26100, pass_records=30, dumps=5, return=full-package)
```

## Accepted result

`RESULT_W010_W014.txt` contains 30 PASS records, no FAIL record, and ends in
`OVERALL PASS`. In particular:

- switch, nterp, and threshold-zero JIT managed stack overflow return through
  Java `StackOverflowError` handling;
- handled NPE/SOE processes contain no ART fatal VEH/UEF/minidump marker and
  `HANDLED_DMP_SCAN.txt` contains `NO_HANDLED_DMP_FILES`;
- static, JIT J-2/J-1, and OSR J-2/J-1 deliberate fatal AVs each reach the
  required fatal path and create one valid dump; and
- `FATAL_DMP_SCAN.txt` records exactly five valid named dumps.

The native page probe reports the initial zero stack guarantee raised and
queried back as 16,384 bytes on both the main and pthread-created threads:

```text
stack_guarantee label=main before=0 configured=16384 minimum=16384
stack_guarantee label=pthread before=0 configured=16384 minimum=16384
```

This accepts the E9 accounting contract on the measured 4 KiB-page host:

```text
configured guarantee = max(existing guarantee, 4 * system page size)
excluded low = inaccessible memory prefix
             + page-rounded configured guarantee
             + one moving PAGE_GUARD page
stack_end = low + excluded low + ART's unchanged 8192-byte reserve
```

Linux retains its existing implicit `RSP - 8192` probe. Win64 uses an explicit
pre-prologue `RSP < Thread::stack_end_` check and tail-jumps through the same
ART stack-overflow throw entrypoint. Windows retains ownership of stack growth
and guard-page state. The fixed-page selection/protection machinery remains
only for direct diagnostic page-state tests.

## Historical failure retained

E8 used `max(inaccessible prefix, guarantee)` and still failed all three
managed-SOE paths. Its returned bundle is retained outside the repository at
`/tmp/w010_w014_e8_result.zip`, SHA-256
`3c5fb26da6882e4fb3643a4575fef03b5cf4569ebe45a51e16086658aefd587b`.
Controlled native measurements then proved that the guarantee is above a
separate terminal prefix and that one moving guard page must also be debited.

## Remaining scope

This acceptance does not claim CET user-shadow-stack support, debugger-quality
dump reconstruction, forced incompatible CET-policy coverage, handler
high-water/stack-budget coverage, dynamic-function-table sampling or churn,
exception-unwind XMM coverage, the brief interpreter pending range, or broad
embedding/predecessor-UEF coverage. Those remain W-010/W-014 or W-025 host
matrix items; they do not reopen the accepted E9 managed-SOE mechanism.
