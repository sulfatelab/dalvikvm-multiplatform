# Stack executable-memory result

The probe checks Windows stack growth across executable-memory policy. Its
current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The shell-free native gate passed on Windows Server 2025 build 26100. The
selected stack page was `PAGE_EXECUTE_READ`, retained all 64 marker bytes,
converted back to ordinary read/write stack memory during growth, caught
`0xc00000fd`, reset stack overflow state, restored the page, and reported zero
failures. Its sanitized result contains one completed iteration and no host
path. No other target is currently applicable.
