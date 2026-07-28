# W-002 native Windows R2 acceptance evidence

**Status:** PASS — W-002 closed

**Run date:** 2026-07-26 14:37:55

**Reviewed on:** 2026-07-26

## Host and package identity

- Windows 10 Enterprise LTSC x64, version 10.0.19044, build 19044.
- Windows PowerShell 5.1.19041.7548.
- Root branch: `main`.
- Root commit: `5cc3e2b52834b42f2f9b135ce2bbb2fd5dcd43ec`.
- ART branch: `artmp_android-16.0.0_r4`.
- ART commit: `0bc7b10e1ca53df2e0c3bd9bbc3291c6513862e2`.
- Issued package SHA-256:
  `9efa883e1de06fe375d104b7c69be301b11c23c22d8a7e82a75ac27e56b56a4d`.
- Returned archive `/tmp/w002-r2-log.zip` SHA-256:
  `2c49fe7161f96e98ae74dcd4e610eee775dfff21234673c902c7d4bf58e5df7e`.

The returned archive passes ZIP integrity testing. Its `BUILD_INFO.txt`,
`SHA256SUMS.txt`, and root/log structural reports exactly match the issued R2
package. The native runner reports `PASS package_integrity` and
`PASS structural_report`.

## Runtime result

`RESULT_W002.txt` contains 21 PASS records, zero FAIL records, and final
`OVERALL PASS`. All 16 child processes exit zero without timeout.

The native matrix passes:

- corrected dual-view/default-nterp OSR, 2/2;
- corrected dual-view/switch OSR, 2/2;
- J-1/default-nterp OSR, 2/2;
- J-1/switch OSR, 2/2;
- attached regular/daemon threads in the same four mode pairs, 2/2 each and
  16 thread lifecycles per process.

Every OSR process reports `warmup_threshold=100, optimize_threshold=100`,
baseline and OSR compilation, the required jump, exact checksum
`65553463744`, and `main end exception=0`. Switch runs contain their completion
marker; default-nterp runs do not use the switch return path.

Every attach process compiles `W002AttachProbe.attachedCallback`, reports
`W002AttachProbe OK completed=16`, and returns without exception. Fatal-marker
scanning passes. Recursive dump scanning reports `NO_DMP_FILES`.

## Evidence transport normalization

The returned evidence ZIP omitted root `MANIFEST.json`. This was a copy-time
transport omission, not a native package-integrity failure:

- host-side `PASS package_integrity` proves the manifest existed and matched
  during the run;
- returned `SHA256SUMS.txt` is byte-identical to the issued file and records
  manifest SHA-256
  `e48211612ce16c84acca6af1aca3f749b4c88112f99e31d76b0ace2bd519e125`;
- the retained issued manifest has exactly that hash; and
- the other three required root identity files are byte-identical.

A normalized evidence archive was created by adding only the retained
byte-identical issued manifest to the extracted return. No log, result, or
other metadata file was changed. `/tmp/w002-r2-log-normalized.zip` has SHA-256
`8aea7af225f154678d50ea7b329ce8574242c2e8cea8c947170c4a58f916bc03`,
passes ZIP integrity testing, and passes the unchanged strict reviewer:

```text
W-002 native host result: PASS (build=19044, cases=16, pass_records=21, return=evidence-only)
```

This evidence satisfies the final W-002 native-host closure condition.
