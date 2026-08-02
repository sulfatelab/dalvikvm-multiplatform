# Managed runtime stress probes

This case owns the handle-leak, performance-smoke, and heavy-thread managed
sources. Their applicability is deliberately per probe:

| Probe | Accepted exact target IDs |
|---|---|
| `HandleLeakProbe` | `linux-x86_64-gnu`, `linux-aarch64-gnu`, `windows-x86_64-msvc` |
| `PerfSmokeProbe` | `linux-x86_64-gnu`, `linux-aarch64-gnu`, `windows-x86_64-msvc` |
| `ThreadHeavyProbe` | `linux-x86_64-gnu`, `linux-aarch64-gnu`, `windows-x86_64-msvc` |

Historical Wine success does not broaden any probe to another platform,
target architecture, or target ABI. Each target in the table has independent
behavioral acceptance.

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

On 2026-08-02, ThreadHeavyProbe was then admitted independently on the same two
Linux targets. The unchanged graphs retained their 2,089/2,113 compile-command,
2,172/2,196 Ninja-command, and 32-product-link audits. A fresh 1,861-edge
x86-64 W-004 build passed 8/8 in 3.06 seconds, including ThreadHeavy in 0.37
seconds; the true Ninja no-op repeat passed 8/8 in 3.10 seconds, including
ThreadHeavy in 0.35 seconds. A fresh 1,626-edge AArch64 W-004 build passed 7/7
in 89.47 seconds, including ThreadHeavy in 2.03 seconds; the true Ninja no-op
repeat passed 7/7 in 88.64 seconds, including ThreadHeavy in 1.99 seconds.

Both ThreadHeavy records require the exact 24-thread, 3,000-iteration, 72,000
counter result, successful sleeper interruption, exact-zero process exit, and
the complete final marker set. They use app JAR SHA-256
`c85612b911e6597c18f60f205072815cf8c7254e1c384a2ffce348083d6f8a76`
and the same boot JAR hash recorded above. The AArch64 record contains only the
normalized external-runner identity, while x86-64 records native execution.
Neither result contains an absolute machine path, and no filesystem link was
found in either source or result tree.

HandleLeakProbe was then admitted independently on both Linux targets. The
unchanged AArch64 graph retained 38 modules, 262 Blueprint files, 2,113 compile
commands, 2,196 Ninja commands, and 32 product links. Its fresh 1,627-edge
W-004 build passed 8/8 in 99.23 seconds, including HandleLeak in 2.56 seconds;
the true Ninja no-op repeat passed 8/8 in 99.55 seconds, again including
HandleLeak in 2.56 seconds. The unchanged x86-64 graph retained 37 modules,
262 Blueprint files, 2,089 compile commands, 2,172 Ninja commands, and 32
product links. Its fresh 1,862-edge W-004 build passed 9/9 in 3.53 seconds,
including HandleLeak in 0.36 seconds; the no-op repeat passed 9/9 in 3.59
seconds, including HandleLeak in 0.34 seconds.

Both HandleLeak records require exact-zero exit, 400 completed file cycles, 80
completed socket cycles, the persisted `handle-final` marker, the final
`handleleak.ok=true` and `HandleLeakProbe.done=ok` markers, and
`main end exception=0`. They use app JAR SHA-256
`87290d82c206dfa67a430cee8c3e9958c5c6544a22ce8428adea46f58853c81b`
and the same boot JAR hash recorded above. The AArch64 manifest records only
normalized `qemu-aarch64` identity and x86-64 records native execution; neither
manifest contains an absolute machine path, and neither result tree contains a
filesystem link.
