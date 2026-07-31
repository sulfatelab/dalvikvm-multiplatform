# Mspace ownership result

The W-013 probe checks ART dlmalloc whole-owner lifetime and release behavior.
Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The canonical source and its product allocator dependency passed the unified
Windows cross catalog build. The authoritative Server 2025 Stage-8 CTest then
passed in 0.10 seconds and direct marker capture reported:

```text
W013_MSPACE_OWNER_PASS first_calls=5 second_calls=2
```

No other target is currently applicable.
