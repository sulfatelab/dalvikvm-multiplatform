# Stack pre-growth result

The diagnostic probe and `implicit_fault_x86_64.S` exercise exact x86-64
pre-growth and implicit-fault behavior. The selector is
`windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | pending unified diagnostic gate | 2026-07-31 |

Windows AArch64 and ARM64EC are non-applicable; they require distinct assembly
and acceptance rather than inheriting x86-64 evidence.
