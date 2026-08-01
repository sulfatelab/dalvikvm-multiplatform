# JIT section-policy result

This case owns the Windows section-policy probe and its process-policy
launcher. Their current selector is `windows` / `x86_64` / `msvc`.

| Targets | Build | Runtime | Last checked |
|---|---|---|---|
| section probe, launcher | verified | verified | 2026-08-01 |

Both canonical sources passed the unified cross catalog build and combined
source/PE reviewer. Windows Server 2025 passed the three-case standalone
matrix and four process-policy cases twice: basic R/RX/RW mapping, complete
low-VA rejection/recovery, 1 GiB `SEC_COMMIT`, generated execution and managed
JIT under CFG, fail-closed J-2 rejection under `ProhibitDynamicCode` with
error 1655, successful Hello without a JIT cache, and the explicit
`-Xusejit:false` control. Applicability does not extend to AArch64 or ARM64EC
without separate policy acceptance.
