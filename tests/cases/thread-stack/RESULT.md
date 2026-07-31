# Thread-stack result

The probe validates native Windows thread stack reservation, identity, join,
and detach behavior. Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The shell-free native gate preserves the historical exact size inventory and
stress counters. On the authoritative Server 2025 host, the unified W-014
stage passed this gate in 0.35 seconds with requested reservations of 65,536,
262,144, 1,048,576, 2,097,152, and 9,437,184 bytes:

```text
win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128
win32_thread_stack_probe OK
```

The sanitized JSON record contains one completed iteration, zero failed
marker/exit/timeout checks, and no host path.
