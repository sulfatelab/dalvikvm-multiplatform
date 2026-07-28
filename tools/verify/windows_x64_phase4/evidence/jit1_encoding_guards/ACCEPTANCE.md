# JIT-1 native Windows acceptance evidence

**Status:** PASS

**Accepted:** 2026-07-29

## Identity

- Build host: `agent01`.
- Native host: Windows Server 2025 Datacenter Evaluation x64, version
  10.0.26100, build 26100.
- Windows PowerShell: 5.1.26100.7462.
- Root commit in package: `f18d1b53cb3033c87a8ca07361025578bfd4ec14`.
- ART commit in package: `146016f83e5c6df8481eab6119f30c9077141179`.
- Issued package SHA-256:
  `3e892b9290850d03d35a8ffc7e8562f59a45431ce61532012f03082622e88624`.
- Returned review archive SHA-256:
  `63c8068028a184ffd432c65ac29005216189139fc8d9df36b0c043b6e34e3534`.

The issued hash matched after SSH/SCP transfer and before extraction. The
returned archive preserves portable ZIP paths and passes CRC, path-safety,
symlink, package-metadata, and structural-report identity checks.

## Result

The W-004 runner completed 22 child cases with 28 PASS records, zero FAIL
records, and `OVERALL PASS`. All child processes exited zero without timeout.
Dual-view JIT, J-1 comparison arms, native ABI and JVMTI transitions, stress,
and ten repeated starts passed. Trace cleanup and forbidden-log scans passed.
The recursive dump scan returned `NO_DMP_FILES`.

Independent Linux-side review returned:

```text
W-004 native host result review: PASS cases=22 aggregate_pass=28 failures=0 archive_sha256=63c8068028a184ffd432c65ac29005216189139fc8d9df36b0c043b6e34e3534
```

The complete issued and returned archives remain in the ignored `dist/`
workspace. Their immutable identities are recorded in
`ARCHIVE_SHA256SUMS.txt`; the aggregate host record is retained in
`RESULT_W004.txt`.
