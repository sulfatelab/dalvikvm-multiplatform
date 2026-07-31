# CET stack-policy result

The probe validates Windows CET policy queries relevant to ART stack handling.
Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The shell-free native gate passed on Windows Server 2025 build 26100. The live
query reported `actual=disabled`, flags `0x00000100`, zero known incompatible
fields, and the final PASS marker. The probe also exercised its internal named
incompatible, safe/reserved, invalid-policy, and older-Windows decision
matrix. Its sanitized result contains one completed iteration and no host
path. No Windows AArch64 or ARM64EC behavior is inferred.
