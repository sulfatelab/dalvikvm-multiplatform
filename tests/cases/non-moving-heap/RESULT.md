# Non-moving heap managed stress probe

`W013NonMovingStressProbe.java` is the managed half of the W-013 non-moving
allocator stress. It covers low-address non-moving arrays, allocation churn,
forced collections, address stability, and post-GC regrowth.

| Target ID | Managed artifact | 128 MiB gate | 1024 MiB gate |
|---|---:|---:|---:|
| `linux-x86_64-gnu` | applicable | verified | not applicable |
| `linux-aarch64-gnu` | applicable | verified under explicit QEMU user mode | not applicable |
| `windows-x86_64-msvc` | applicable | verified | verified |

All other platform, target-architecture, and ABI combinations are explicitly
not applicable until separately admitted. The 128 MiB declaration uses three
exact target IDs; the 1024 MiB resource-pressure gate remains Windows x86-64
MSVC-specific.

The source is compiled and D8-packaged by the unified target graph. On
2026-08-01, a fresh Linux x86-64 GNU build completed 1,485 Ninja actions and
passed the shell-free 128 MiB gate in 0.27 seconds. Its identical rerun was a
Ninja no-op and passed in 0.28 seconds. The authoritative Server 2025 Stage-8
tree was also a Ninja no-op and passed the complete W-013 stage 7/7 in 5.14
seconds: 0.55 seconds at `-Xmx128m` and 1.67 seconds at `-Xmx1024m`.

All three sanitized `result.json` records contain the exact target ID, exit 0,
no missing or forbidden marker, stable JAR hashes, and no host path. The
Windows source and output trees contain zero reparse points, and the host
remained responsive.

On 2026-08-02, the same 128 MiB gate was separately admitted for experimental
`linux-aarch64-gnu`. Its command was first corrected to receive the explicit
QEMU runner and loader-root arguments already used by W-004; without those
arguments the target executable could not be launched and no allocator result
was claimed. Reconfiguration then passed audits of 2,110 compile commands,
2,196 Ninja commands, and 32 product links. The gate allocated 75,497,472
bytes, retained low addresses and stable object addresses across forced
collections, regrew after collection, printed all six required markers, and
exited zero. It passed in 2.06 seconds and repeated in 2.13 seconds, with Ninja
reporting no work before both accepted runs. The managed JAR SHA-256 was
`51394bd9b91e6204e3e50501a605a626b106bcfea267199c2cc7ec05691dad03`;
the sanitized result contains the normalized QEMU fingerprint and no machine
path. This evidence admits only the 128 MiB profile, not the Windows-specific
1024 MiB resource-pressure profile.
