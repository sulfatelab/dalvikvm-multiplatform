# JIT mapping result

The JNI DSO audits Windows JIT mapping capacity and executable-memory policy.
Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The canonical source passed the unified Windows cross catalog build. The
shell-free managed runner passed twice on Windows Server 2025 at 64 MiB and
1 GiB. Both runs observed a contiguous low R/RX primary, unrestricted RW
alias, unnamed pagefile-backed `MEM_MAPPED` storage, no RWX region, and the
compiled target method. Other architectures remain non-applicable until
independently accepted.
