# Stack page and growth result

This case owns the page-state probe, recursive growth probe, and their one
shared `fault_x86_64.S` implementation. Both targets are exact
`windows-x86_64-msvc`.

| Targets | Build | Runtime | Last checked |
|---|---|---|---|
| page, growth | verified | pending unified behavioral gates | 2026-07-31 |

The unified cross catalog compiled the same assembly file for both targets
without a copy, symlink, junction, or generated source alias. AArch64 and
ARM64EC need explicit architecture variants and separate results.
