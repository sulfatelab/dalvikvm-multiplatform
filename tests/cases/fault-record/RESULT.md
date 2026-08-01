# Fault-record adapter result

This probe checks deterministic Windows exception-record adaptation cases. Its
current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 build 26100 | 2026-08-01 12:35:42 |

The unified native W-010 stage passed this executable twice with
`failures=0 cases=8`. It accepts read and write AV records and rejects execute,
noncontinuable, short, wrong-PC, wrong-code, and missing-address records. The
final stage build was a Ninja no-op.

The canonical source also passed the Linux-hosted Windows cross stage build.
Linux, Windows AArch64, and ARM64EC are not currently applicable.
