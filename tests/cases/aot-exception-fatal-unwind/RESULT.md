# Windows boot-OAT exception and fatal-unwind result

The Windows x86-64 W-038 case proves managed-exception and fatal stack walking
through currently published, registered boot-OAT methods with JIT disabled.

| Build | Runtime | Last checked |
|---|---|---|
| verified | PASS on Windows Server 2025 build 26100 | 2026-08-07 |

The managed child catches an explicit exception whose nonempty Java trace
names the selected boot-OAT method and verifies that its entrypoint is
unchanged. The fatal child reaches the exact armed boot-OAT function through
`RtlVirtualUnwind`, reaches ART's UEF, and creates exactly one valid `MDMP`.
Full hashes and evidence are in
[`docs/history/windows_x64_w038_result.md`](../../../docs/history/windows_x64_w038_result.md).
