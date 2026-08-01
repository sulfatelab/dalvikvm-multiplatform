# W-025 JIT-2 native mapping and policy acceptance

**Status:** PASS; JIT-2 complete

**Date:** 2026-07-29

**Build host:** agent01

**Native host:** Windows Server 2025 Datacenter Evaluation x64, build 26100

## Outcome

The default Windows x64 JIT mapping now has native closure evidence at its
64 MiB default and 1 GiB supported maximum. Actual ART mappings are one unnamed
pagefile-backed section exposed as a contiguous low `[data R][code RX]`
primary and a complete unrestricted `[data RW][code RW]` alias. The native
audit observed `MEM_MAPPED`, no RWX region, no mapped filename, successful
target compilation, and exact capacity/role records at both sizes.

The standalone policy cases additionally prove complete low-address-space
fragmentation and recovery, 1 GiB `SEC_COMMIT` accounting, and generated-code
execution under CFG. A child created with `ProhibitDynamicCode` reports the
policy as active and rejects both the J-2 `MapViewOfFile3` operation and the
J-1 `VirtualProtect` transition with `ERROR_DYNAMIC_CODE_BLOCKED` (1655). ART
reports that no JIT code cache was created and continues successfully. A
separate `-Xusejit:false` child succeeds without attempting JIT-cache creation.

## Local verification

| Gate | Result |
|------|--------|
| Windows x64 targets build | PASS |
| W-025 source contract | PASS |
| CFG load configuration | `CF_INSTRUMENTED` and function table present |
| Reproducible package and manifest | PASS |
| Wine standalone section mapping | PASS |
| Wine actual ART 64 MiB mapping audit | PASS |
| Wine full-span low-VA reservation check | PASS |

## Native Windows acceptance

The final package records root commit
`b2ea7e89ffda2392bb495b23d612a0bfa0bd0f53` and ART commit
`146016f83e5c6df8481eab6119f30c9077141179`. Its issued ZIP SHA-256 is
`10e5a6d376f4743af75f3fb2ceaf58390422ef860c375305b5bd59f5e98a8580`.

The PowerShell runner returned `OVERALL PASS` with nine child cases, 14
aggregate PASS records, zero failures, no timeouts, an empty `jit-temp`, clean
forbidden-log scanning, and `NO_DMP_FILES`. Selected native observations were:

| Case | Native observation |
|------|--------------------|
| Low-VA failure | 2 full-span reservations; constrained map rejected with error 8; no high fallback; recovery passed |
| 1 GiB pressure | Commit delta 1,075,838,976 bytes; low primary and RW alias passed |
| 64 MiB ART mapping | R/RX/RW roles, unnamed `MEM_MAPPED`, compiled target, success |
| 1 GiB ART mapping | R/RX/RW roles, unnamed `MEM_MAPPED`, compiled target, success |
| CFG | Standalone generated call and actual ART JIT mapping report `cfg_enabled=1` and pass |
| Dynamic-code policy | J-2 and J-1 executable operations rejected with error 1655; runtime continued without a JIT cache |

The returned archive independently passed identity, payload, child-log,
policy-marker, dump, trace, and JIT-temporary-file review:

```text
W-025 JIT-2 native host result review: PASS cases=9 aggregate_pass=14 failures=0 archive_sha256=3d32e3a15f4e4ad8b5e98a769ea02e638abeb975755064177b1a4d3a6bf9364e
```

This summary retains the immutable package/archive identities and independent
review conclusion. The package-era per-process log bundle was removed after
the same contracts migrated to the unified W-025 stage.

## Next gate

JIT-3/FS-3 is next: stress default J-2 allocation, compilation, invalidation,
collection, exact-address reuse, unwind-table deletion/re-registration, and
concurrent `RtlLookupFunctionEntry()` plus virtual-unwind sampling. J-1 remains
only as a comparison arm until that stress and the final default-path
regression archive pass.
