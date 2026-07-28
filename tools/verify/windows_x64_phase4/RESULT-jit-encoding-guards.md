# JIT relative metadata encoding guards

**Status:** PASS; JIT-1 complete

**Date:** 2026-07-29

**Build host:** agent01

**Native host:** Windows Server 2025 Datacenter Evaluation x64, build 26100

## Outcome

ART `146016f83e5c6df8481eab6119f30c9077141179` now rejects JIT metadata
addresses that cannot be represented by their existing fields:

- `jit_encoding.h` checks signed-int32 x86_64 JIT-root displacements, including
  root-table arithmetic overflow;
- x86_64 validates string, class, and MethodType root patches before writing
  any disp32 field;
- the optimizing compiler releases its reserved JIT code/data allocation when
  validation rejects a compilation; and
- `JitMemoryRegion::CommitCode()` checks that non-null CodeInfo is below the
  code and within uint32 range before copying code or constructing the method
  header.

The encoded format and successful-layout bytes are unchanged. Deterministic
positive/negative disp32 boundaries, arithmetic overflow, invalid entry size,
CodeInfo direction, uint32 maximum, overflow, and null-output cases are covered
in `jit_memory_region_test.cc` and by the standalone header check used by this
tree's CMake-only gate.

## Local verification

| Gate | Result |
|------|--------|
| Standalone deterministic encoder check | `JIT_ENCODING_CHECK_PASS` |
| Windows x64 `art.dll` and `dalvikvm.exe` build | PASS |
| Linux `libart.so` and `dalvikvm` build | PASS |
| Wine JIT smoke | 12/12 PASS |
| Wine JIT matrix | 14/14 PASS |
| PE unwind-info encoder probe | 6 cases, 0 failures |
| Dynamic unwind registry probe | 0 failures |
| JIT unwind lifecycle | J-2 and J-1 PASS, one collection each |
| Linux imageless Hello | L-005 PASS |
| Linux GC stress | PASS |
| W-004 package structure and Wine preflight | PASS |

The W-004 preflight also passed CriticalNative in both memory modes, all seven
normal/FastNative targets and tracing records, and the two expected JVMTI
compiled targets in both memory modes.

## Native Windows acceptance

The final package records root commit
`f18d1b53cb3033c87a8ca07361025578bfd4ec14` and ART commit
`146016f83e5c6df8481eab6119f30c9077141179`. Its SHA-256 was verified after
transfer to `administrator@10.127.137.62` before extraction.

The packaged PowerShell runner returned `OVERALL PASS` with 22 child cases,
28 aggregate PASS records, zero failures, no timeout, and zero nonzero child
exits. Coverage includes nterp `-Xint`, corrected dual-view JIT, threshold-zero
managed compilation, dual/J-1 CriticalNative, normal/FastNative and JVMTI
transitions, GC/thread/handle stress, and ten independent default-JIT starts.
Trace and forbidden-log scans passed; the recursive dump scan returned
`NO_DMP_FILES`.

`review_w004_host_result.py` independently accepted the portable returned ZIP:

```text
W-004 native host result review: PASS cases=22 aggregate_pass=28 failures=0 archive_sha256=63c8068028a184ffd432c65ac29005216189139fc8d9df36b0c043b6e34e3534
```

Immutable identities and the aggregate native result are archived in
[`evidence/jit1_encoding_guards/`](evidence/jit1_encoding_guards/).

## Next gate

JIT-2 is now unblocked: build the combined W-025 native package for mapping
protections, no-filesystem/no-RWX assertions, CFG and dynamic-code policy,
low-VA failure, and large `SEC_COMMIT` pressure. Collection/reuse with
concurrent lookup and virtual-unwind sampling remains JIT-3/FS-3.
