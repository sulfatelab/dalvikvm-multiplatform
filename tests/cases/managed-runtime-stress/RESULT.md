# Managed runtime stress probes

This case owns the handle-leak, performance-smoke, and heavy-thread managed
sources. Their selector is exactly the implemented Windows x86-64 MSVC
profile; historical Wine success did not broaden it to another platform,
architecture, or ABI.

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
