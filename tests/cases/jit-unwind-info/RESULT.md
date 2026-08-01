# JIT unwind-info result

The probe inspects x86-64 Windows JIT unwind encoding cases. Its ABI and record
assumptions make it exact `windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The Linux-hosted Windows cross stage built the probe through the common graph.
On Windows Server 2025 the unified native gate passed all six encoding cases
twice with zero failures. AArch64 and ARM64EC need independent unwind probes.
