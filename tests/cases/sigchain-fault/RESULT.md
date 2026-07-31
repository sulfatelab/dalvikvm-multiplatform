# Sigchain fault result

The probe raises real page faults through Windows sigchain and uses the shared
x86-64 fault stub from `../stack-page-growth/fault_x86_64.S`. It is exact
`windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | pending unified behavioral gate | 2026-07-31 |

No source copy or filesystem link is used. A future architecture requires an
explicit adjacent assembly implementation and independent acceptance.
