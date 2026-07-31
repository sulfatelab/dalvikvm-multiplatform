# Stack page and growth result

This case owns the page-state probe, recursive growth probe, and their one
shared `fault_x86_64.S` implementation. Both targets are exact
`windows-x86_64-msvc`.

| Target | Build | Runtime | Last checked |
|---|---|---|---|
| page | verified | verified | 2026-08-01 |
| growth | verified | verified | 2026-08-01 |

The unified cross catalog compiled the same assembly file for both targets
without a copy, symlink, junction, or generated source alias. AArch64 and
ARM64EC need explicit architecture variants and separate results.

The page-state executable now has a shell-free native gate. It passed on the
authoritative Server 2025 host in 0.22 seconds with all eight selection cases,
64 reserved-stack restorations, 64 committed-stack restorations, and 258
faults:

```text
selection_cases count=8
reserved_case size=1048576 iterations=64
win32_stack_page_probe failures=0 committed_restore_iterations=64 reserved_restore_iterations=64 faults=258
win32_stack_page_probe OK
```

Its sanitized JSON record contains one completed iteration, zero failed
marker/exit/timeout checks, and no host path.

The checked-in runtime matrix runs `baseline`, `protected`, `writable`, and
`direct` four times each. On the same host all 16/16 iterations passed. The
first three modes consistently caught `0xc00000fd`; `direct` caught
`0xc0000005`. Every run reported zero probe failures, a zero worker exit, and
successful restoration. The matrix, arguments, exact marker contracts, and
per-case sanitized results are owned beside this source rather than by a
phase-local shell runner.
