# Mspace ownership result

The W-013 probe checks ART dlmalloc whole-owner lifetime and release behavior.
Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The canonical source and its product allocator dependency passed the unified
Windows cross catalog build. The shell-free Python gate runs the success case
and four expected-fatal subprocesses with individual timeouts, checks the
diagnostic contract, and writes a sanitized JSON record below the target build
tree.

The authoritative Server 2025 Stage-8 CTest passed the complete gate in 0.50
seconds on 2026-08-01. The encompassing W-013 stage was a Ninja no-op and
passed 7/7 in 5.31 seconds. The result contained one successful case, four
nonzero expected-death cases, every expected diagnostic, and no timeout or host
path. The VM remained responsive after all fatal subprocesses. Marker capture
reported:

```text
W013_MSPACE_OWNER_PASS first_calls=5 second_calls=2
W013_MSPACE_OWNER_GATE_PASS target=windows-x86_64-msvc success=1 death=4
```

No other target is currently applicable.
