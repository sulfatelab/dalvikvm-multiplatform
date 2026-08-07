# Windows ordinary boot-OAT dispatch result

The Windows x86-64 W-036 case directly observes ordinary managed dispatch at a
currently published, registered boot-OAT entrypoint with JIT disabled.

| Build | Runtime | Last checked |
|---|---|---|
| verified | PASS on Windows Server 2025 build 26100 | 2026-08-07 |

The accepted native gate selects `Integer.parseInt(String)` and records exactly
one hardware execute-breakpoint hit at its current boot-OAT RX entry PC, with
zero unrelated single-step exceptions. Full evidence is in
[`docs/history/windows_x64_w036_result.md`](../../../docs/history/windows_x64_w036_result.md).
