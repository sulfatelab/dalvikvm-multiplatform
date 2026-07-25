# W-004 native Windows acceptance evidence

**Status:** PASS — W-004 closed

**Run date:** 2026-07-25

**Reviewed on:** 2026-07-25

## Host and package identity

- Windows 10 Enterprise LTSC x64, version 10.0.19044, build 19044.
- Windows PowerShell 5.1.19041.7548.
- Root commit: `c42a52550947268936a98e120e69e53d025c0e62`.
- ART commit: `34a2c1ec9200e7ddb4ab20d6bb55237f2c0f8e63`.
- Issued package SHA-256:
  `b365c2c9b320a5b11f8a150182027f54497db3059d73a129df803b50c026bd37`.
- Returned archive: `/tmp/w004-run1.zip`, SHA-256
  `f720c0ed7ccc7aeda3dbe2c5502797f82b1c58d128460ee23515d3245bea8f6d`.

The returned archive passes ZIP integrity testing. Its `BUILD_INFO.txt`,
`MANIFEST.json`, and `SHA256SUMS.txt` are byte-for-byte identical to the issued
package metadata. The returned `logs/W004_STRUCTURAL_REPORT.txt` is also
byte-for-byte identical to the issued report.

## Structural contract

The accepted report records:

- 563 direct quick-entrypoint relocations;
- 10 direct generated-nterp relocations;
- 1 direct JNI relocation;
- 574 direct `Runtime::instance_` relocations in total;
- zero references to `art_Runtime_instance_ptr`;
- exactly one `Runtime::instance_` export from `art.dll`;
- exactly one `Runtime::instance_` import in `openjdkjvmti.dll`; and
- an unchanged Linux x86-64 macro.

The recorded SHA-256 values for `art.dll` and `openjdkjvmti.dll` match the
issued package manifest.

## Runtime result

`RESULT_W004.txt` contains 28 PASS records, zero FAIL records, and ends in
`OVERALL PASS`. All 22 child processes report `exit=0`,
`expected_exit=0`, and `timed_out=False`; no launch error, missing marker, or
forbidden marker is present.

The native matrix passes:

- imageless `-Xint` nterp Hello;
- corrected dual-view JIT creation and managed compilation;
- threshold-zero `FloatProbe`;
- registered and unresolved CriticalNative calls with tracing in corrected
  dual-view and J-1 diagnostic modes;
- all seven normal/FastNative compiled-JNI targets exactly once in both modes,
  with exact values through rebinding and tracing;
- JVMTI forced-interpreter transitions in both modes, with the two allowed
  normal/FastNative targets compiled exactly once and no CriticalNative target
  compiled in the debuggable runtime;
- GC stress, ThreadHeavy, and HandleLeak; and
- ten independent default-JIT Hello starts.

`review_w004_host_result.py` independently rechecks the exact probe values,
compilation counts, stdout/stderr inclusion in every combined log, complete
expected case set, package identity, and archive safety. Trace cleanup and
fatal/access-violation scans pass. The recursive dump scan reports
`NO_DMP_FILES`; the returned archive contains no `.dmp` or trace file.

The only `E`-level ART diagnostics are expected for this harness: failure to
open the deliberately nonexistent boot image followed by imageless fallback,
and the known Windows `SetCloseOnExec` no-op. Every process reaches its success
marker and `main end exception=0`.

This evidence satisfies the final W-004 native-host closure condition.
