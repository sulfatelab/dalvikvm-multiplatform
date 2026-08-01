# Sigchain fault result

The probe raises real page faults through Windows sigchain and uses the shared
x86-64 fault stub from `../stack-page-growth/fault_x86_64.S`. It is exact
`windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 build 26100 | 2026-08-01 12:35:42 |

The unified native W-010 stage passed twice. Both recognized faults returned
zero, the ART action ran three times, both foreign handlers ran twice in the
required order, and frame SEH caught the unrecognized fault both before and
after removing the ART action. The final stage build was a Ninja no-op.

No source copy or filesystem link is used. The Linux-hosted Windows cross stage
also builds the same regular files. A future architecture requires an explicit
adjacent assembly implementation and independent acceptance.
