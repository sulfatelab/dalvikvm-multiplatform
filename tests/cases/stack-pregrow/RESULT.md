# Stack pre-growth result

The diagnostic probe and `implicit_fault_x86_64.S` exercise exact x86-64
pre-growth and implicit-fault behavior. The selector is
`windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

Windows AArch64 and ARM64EC are non-applicable; they require distinct assembly
and acceptance rather than inheriting x86-64 evidence.

The source-adjacent runtime matrix preserves the historical E9 experiment in
six named cases. On Windows Server 2025 build 26100 it passed 39/39 process
runs:

- implicit Linux-shaped fault: 30/30, always selected offset `0x6000`, caught
  read AV `0xc0000005`, retained `PAGE_NOACCESS` in the filter, and restored;
- native recursive collision: child exit `0xc0000005` matched the required
  fatal outcome;
- attach/detach: 5/5, with restored read/write protection and the deliberately
  irreversible pre-growth high-water behavior;
- commit scale: 1, 10, and 100 workers all completed, with exact aggregate
  stack commits of 2,093,056 bytes per worker and zero failures.

The unified shell-free gate records per-process output and sanitized JSON. No
result contains a host path. This remains diagnostic evidence for why explicit
Windows stack checks are preferable; it does not turn pre-growth into product
policy.
