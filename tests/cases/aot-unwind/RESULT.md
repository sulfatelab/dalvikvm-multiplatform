# Windows boot-OAT unwind result

The Windows x86-64 W-031 case validates registered boot-OAT unwind metadata
and JIT-disabled managed/JNI execution.

| Build | Runtime | Last checked |
|---|---|---|
| verified | PASS on Windows Server 2025 build 26100 | 2026-08-07 |

The accepted native gate resolves managed, JNI, and all seven trampoline
records, completes a synthetic `RtlVirtualUnwind`, and successfully calls the
selected managed and JNI bodies. Full artifact identities and evidence are in
[`docs/evidence/windows_x64_w031_result.md`](../../../docs/evidence/windows_x64_w031_result.md).
