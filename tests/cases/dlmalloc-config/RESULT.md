# DLMalloc configuration result

## Contract

The native W-013 probe embeds the pinned dlmalloc source with ART's Windows
mspace configuration and validates page-granular `MORECORE`, trim/regrowth,
owner-capacity failure, recovery, and `ENOMEM` behavior. It does not replace
the separate product-source audit for raw mspace creation or owner attachment.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `windows-x86_64-msvc` | yes | verified | verified | 2026-08-01 |
| `windows-aarch64-msvc` | no | not applicable | not applicable | — |
| `windows-arm64ec-msvc` | no | not applicable | not applicable | — |

The selector remains the exact currently supported Windows x86-64 MSVC
profile. The authoritative Server 2025 Stage-8 run passed the probe in 0.11
seconds as part of the 6/6 W-013 result:

```text
W013_DLMALLOC_CONFIG_PASS page=4096 granularity=4096 positive=4 negative=2 queries=8 failures=1 last_positive=8192 last_negative=-20480
```

Generated executables and logs stay outside VCS.
