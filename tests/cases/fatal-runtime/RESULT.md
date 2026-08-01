# Fatal runtime managed probes

`CrashAbortProbe.java` and `CrashNativeProbe.java` are the managed entrypoints
for the Windows fatal-abort and native-crash/unwind checks. They were retained
from the Phase-4 bring-up suite and are currently applicable only to
`windows-x86_64-msvc`.

## Unified native acceptance

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `windows-x86_64-msvc` | yes | verified | verified | 2026-08-01 12:35:42 |

The shell-free unified W-010 stage passed twice on Windows Server 2025 build
26100. The abort case required a nonzero exit, the managed exception markers,
and no dump. The native-crash gate separately exercised static, threshold-zero
JIT, and real switch-OSR origins. Each required VEH and UEF delivery, a nonzero
exit, and exactly one new minidump larger than 4096 bytes with an `MDMP` header;
the aggregate therefore accepted exactly three dumps. JIT/OSR compilation and
handoff markers were mandatory, and unexpected continuation/completion markers
were forbidden.

All runner state and dumps remain below the ignored target output. Aggregate
JSON records hashes and sizes but no absolute paths. The final native stage
build and the second Linux-hosted Windows cross stage build were Ninja no-ops.
Other targets remain non-applicable.
