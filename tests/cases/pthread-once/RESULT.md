# Pthread-once result

The probe validates the Windows compatibility implementation's concurrent
`pthread_once` contract. Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The shell-free native gate runs the executable ten times and requires both the
published-value concurrency summary and final success marker on every
iteration. On the authoritative Server 2025 host, the unified W-014 stage built
its declarations in 24 Ninja actions and this gate passed 10/10 in 1.37
seconds:

```text
pthread_once_probe init_calls=1 failures=0 value=0x12345678
pthread_once_probe OK
```

Its sanitized JSON record contains ten attempted and ten completed iterations,
zero failed marker/exit/timeout checks, and no host path.
