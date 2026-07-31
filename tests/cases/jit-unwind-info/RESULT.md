# JIT unwind-info result

The probe inspects x86-64 Windows JIT unwind encoding cases. Its ABI and record
assumptions make it exact `windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | pending unified behavioral gate | 2026-07-31 |

The canonical source passed the unified cross catalog build. AArch64 and
ARM64EC need independent unwind probes.
