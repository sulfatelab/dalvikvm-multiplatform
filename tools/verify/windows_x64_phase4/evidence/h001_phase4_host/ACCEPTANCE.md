# H-001 scoped Phase-4 host acceptance

**State:** ACCEPTED for the available native host subset
**Date:** 2026-07-30
**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

The FS-2 multiplatform PE package was rerun on the native Windows host for the
H-001 scope: GC stress, thread-heavy execution, handle-leak checks, the
uncaught Java abort path, and the native AV/minidump path. All five required
checks passed:

```text
PASS gcstress       gcstress.ok=true / GcStressProbe.done=ok
PASS threadheavy    threadheavy.ok=true / ThreadHeavyProbe.done=ok
PASS handleleak     handleleak.ok=true / HandleLeakProbe.done=ok
PASS crashabort     phase4-abort-ok / PASS crashabort
PASS crashnative    VEH + UEF + minidump written; exit=-1073741819
OVERALL PASS (H-001 scoped subset)
```

The legacy `scripts\run_all_host.cmd` was also exercised. It reached zero for
every in-scope process, but its aggregate result was `OVERALL FAIL` because the
out-of-scope DNS probe returned 1. That network-dependent failure does not
invalidate this H-001 subset; its raw `run_dns.log` remains on the Windows
workspace for diagnosis.

The selected raw logs are retained beside this file. The host is Server 2025.
The former Windows 10 host is no longer available after the lab environment
change, and the authoritative-host policy makes a second-host repeat
unnecessary for H-002/FS-4. See
`tools/verify/windows_x64_phase4/HOST_GATE_POLICY.md`.
