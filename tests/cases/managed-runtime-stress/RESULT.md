# Managed runtime stress probes

This case owns the handle-leak, performance-smoke, and heavy-thread managed
sources. Their applicability is deliberately per probe:

| Probe | Accepted exact target IDs |
|---|---|
| `HandleLeakProbe` | `windows-x86_64-msvc` |
| `PerfSmokeProbe` | `linux-x86_64-gnu`, `linux-aarch64-gnu`, `windows-x86_64-msvc` |
| `ThreadHeavyProbe` | `windows-x86_64-msvc` |

Historical Wine success does not broaden any probe to another platform,
target architecture, or target ABI. In particular, sharing this source
directory and runner does not infer Linux support for HandleLeak or
ThreadHeavy.

The unified build produces their DEX JARs with configured JDK 21 and the pinned
in-tree D8. The shared shell-free runtime gate launches each JAR through the
target `dalvikvm` in interpreter mode, uses an isolated output-owned work root,
enforces a 180-second child timeout, and checks the complete case-specific
success-marker set plus `main end exception=0`.

On 2026-08-01, Windows Server 2025 x86-64 passed HandleLeakProbe,
PerfSmokeProbe, and ThreadHeavyProbe as part of unified W-004 26/26. The first
run completed in 35.93 seconds; the identical `--parallel 16` repeat reported
`ninja: no work to do.` and passed 26/26 in 34.21 seconds. A Linux-hosted
Windows cross run with `--parallel 32` passed the W-004 structural reviewer,
and its immediate repeat was also a Ninja no-op. The superseded Phase-4
builder, generic Wine runner, aggregate Wine runner, and four managed wrappers
were then retired; retained Wine logs are historical evidence only.

On 2026-08-02, fresh Linux builds admitted only PerfSmokeProbe on the two
implemented GNU targets. The AArch64 graph generated 38 modules from 262
Blueprint files, 2,113 compile commands, 2,196 Ninja commands, and 32 product
links. Its fresh 1,625-edge W-004 build passed 6/6 in 86.74 seconds and
PerfSmoke in 1.66 seconds; the true Ninja no-op repeat passed W-004 6/6 in
86.84 seconds and PerfSmoke in 1.62 seconds. The x86-64 graph generated 37
modules from the same 262 Blueprint files, 2,089 compile commands, 2,172 Ninja
commands, and 32 product links. Its fresh 1,860-edge W-004 build passed 7/7 in
2.67 seconds and PerfSmoke in 0.23 seconds; the no-op repeat passed W-004 7/7
in 2.77 seconds and PerfSmoke in 0.24 seconds.

Both sanitized records require exact zero exit and the full marker contract,
with no missing markers. The AArch64 record identifies external
`qemu-aarch64`; the x86-64 record identifies native execution. Both use app
JAR SHA-256
`a1082b3d20b9dfbb6a9db5091df509a5cee03a52713381ab77f1ee03738c2fb8`
and boot JAR SHA-256
`45e19b8cc4a4161d7b7b011e268bf262069d9a7b70c9cfd9c37e324feb249eae`.
Neither result contains an absolute machine path, and neither source nor
result tree contains a filesystem link.
