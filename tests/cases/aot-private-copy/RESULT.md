# Windows AOT private-copy result

The native x86-64 probe verifies the Windows-only file-to-private-allocation
operation used by boot OAT ELF segments and reused VDEX apertures. Its selector
is exact `windows-x86_64-msvc`; other targets retain their existing file
mapping path.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 build 26100 | 2026-08-07 |

The Linux-hosted Windows cross build compiled and linked
`windows_w030_private_copy_probe.exe`. On the authoritative native host the
probe passed again in 0.07 seconds on 2026-08-07 and reported:

```text
W030_PRIVATE_COPY_PASS page=4096 allocation_granularity=65536 range=checked protections=R_RX_RW gaps=noaccess zero_fill=verified ownership=shared source=private cache=flushed
```

The cases reject foreign allocations, unaligned addresses, section views, and
out-of-file ranges; require exact destination bytes and R/NX, RX, or RW/NX
protection; preserve adjacent no-access gaps and anonymous zero fill; retain
one shared allocation owner; prove source-file privacy; and exercise the
executable instruction-cache flush. The companion
`windows_w030_boot_image_startup` gate passed in the same native run, proving
validation-only and executable `ElfOatFile` opens plus VDEX reuse end to end.
It runs managed code with `-Xint`, so this result does not claim execution from
boot-OAT RX code.

Full source hashes, boot-artifact identities, and the LZ4 startup/fallback
boundary are recorded in
[`docs/evidence/windows_x64_w030_result.md`](../../../docs/evidence/windows_x64_w030_result.md).
