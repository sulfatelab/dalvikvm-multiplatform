# JIT section-policy result

This case owns the Windows section-policy probe and its process-policy
launcher. Their current selector is `windows` / `x86_64` / `msvc`.

| Targets | Build | Runtime | Last checked |
|---|---|---|---|
| section probe, launcher | verified | pending unified behavioral gate | 2026-07-31 |

Both canonical sources passed the unified cross catalog build. Applicability
does not extend to AArch64 or ARM64EC without separate policy acceptance.
