# JIT unwind-registry result

The probe validates Windows x86-64 runtime-function registration and lookup.
Its exact selector is `windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The source and Windows product implementation passed the unified cross catalog
build and shell-free structural review. Windows Server 2025 passed registration,
lookup, virtual unwind, deletion, and re-registration twice with zero failures.
Other architectures require their own record format and result.
