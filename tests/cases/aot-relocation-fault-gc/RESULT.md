# Windows relocated boot-OAT fault and root result

The Windows x86-64 W-037 case combines relocated boot-OAT execution, managed
null-fault recovery, and BSS GC-root survival with JIT disabled.

| Build | Runtime | Last checked |
|---|---|---|
| verified | PASS on Windows Server 2025 build 26100 | 2026-08-07 |

The accepted native gate requires a nonzero aligned paired image/OAT
relocation, recovers one low-address access violation from ordinary registered
boot-OAT code as `NullPointerException`, and preserves one non-null BSS root
through eight completed explicit collections. Full evidence is in
[`docs/evidence/windows_x64_w037_result.md`](../../../docs/evidence/windows_x64_w037_result.md).
