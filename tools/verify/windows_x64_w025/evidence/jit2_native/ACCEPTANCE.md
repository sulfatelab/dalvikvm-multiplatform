# JIT-2 native Windows acceptance evidence

**Status:** PASS

**Accepted:** 2026-07-29

## Identity

- Build host: `agent01`.
- Native host: Windows Server 2025 Datacenter Evaluation x64, version
  10.0.26100, build 26100.
- Windows PowerShell: 5.1.26100.7462.
- Root commit in package: `b2ea7e89ffda2392bb495b23d612a0bfa0bd0f53`.
- ART commit in package: `146016f83e5c6df8481eab6119f30c9077141179`.
- Issued package SHA-256:
  `10e5a6d376f4743af75f3fb2ceaf58390422ef860c375305b5bd59f5e98a8580`.
- Returned review archive SHA-256:
  `3d32e3a15f4e4ad8b5e98a769ea02e638abeb975755064177b1a4d3a6bf9364e`.

The issued hash matched after SSH/SCP transfer and before extraction. The
returned archive preserves portable ZIP paths and passes CRC, path-safety,
symlink, immutable package-identity, manifest, and structural-report checks.

## Result

The W-025 runner completed nine child cases with 14 PASS records, zero FAIL
records, and `OVERALL PASS`. Every child exited zero without timeout. The
native cases accepted:

- unnamed 64 MiB and 1 GiB pagefile-section mappings with a contiguous low
  R/RX primary, an unrestricted RW alias, `MEM_MAPPED`, no RWX, and no mapped
  filename;
- complete low-VA fragmentation, clean constrained-map rejection, no high
  fallback, reservation release, and low-map recovery;
- a 1 GiB `SEC_COMMIT` charge and successful primary/alias views;
- generated-code execution and actual ART JIT compilation under CFG; and
- `ProhibitDynamicCode` rejection of both J-2 and J-1 executable mappings with
  `ERROR_DYNAMIC_CODE_BLOCKED` (1655), followed by graceful execution without
  a JIT cache, plus a separate `-Xusejit:false` control.

The JIT temporary directory remained empty, forbidden-log scanning passed,
and the recursive dump scan returned `NO_DMP_FILES`.

Independent Linux-side review returned:

```text
W-025 JIT-2 native host result review: PASS cases=9 aggregate_pass=14 failures=0 archive_sha256=3d32e3a15f4e4ad8b5e98a769ea02e638abeb975755064177b1a4d3a6bf9364e
```

The complete issued and returned archives remain in the ignored `dist/`
workspace. Their identities are retained in `ARCHIVE_SHA256SUMS.txt`; compact
raw stdout, host/package identity, the structural report, aggregate result,
and dump scan are retained beside this document.
