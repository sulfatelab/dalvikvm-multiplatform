# G12 host goldens — PASS (2026-07-16 20:59)

Source package SHA-256:
`4f15b7808a7ff6039663d9931523a82b33c429d00a6a7b068eecb36feac58e3b`.
The returned ZIP is retained outside VCS.
Host: `<host-workdir>\windows_x64_phase3_host` (Windows 10 x86-64, real NT)

## RESULT_HOST.txt

```
OVERALL PASS
```

All script exits recorded 0; marker validation of log bodies also **PASS** (not ERRORLEVEL-only).

## Gate markers

| Gate | Evidence |
|------|----------|
| hello | `Hello from dalvikvm!`, `java.version=1.8.0` |
| props | `props.ok=true`, real `user.dir=<host-workdir>\...` |
| rtmem / core / io / oserrno | done markers PASS |
| net | `match=true echoMatch=true NetProbe.done=ok` (127.0.0.1 loopback) |
| dns | `dns.ok=true` (localhost resolves; payload via 127.0.0.1) |
| gc / gcforced | `gc.ok=true` / `gc.forced.ok=true` |
| interrupt / threadstress | PASS |
| goldenapp | `golden.ok=true net.ok=true served=32` |
| abspath | `AbsPathProbe.fails=0`, real `<absolute-test-root>\...` |
| throw | `RuntimeException: phase3-throw-ok` |

## Notes

- Dns `localhost.addr=null` but `localhost.loopback=true` / v6=true — name resolve returned a loopback Inet6 with null host string print; payload path used 127.0.0.1 successfully.
- Prior host failures (poll EINVAL, false PASS, DnsProbe hang) addressed in package used for this run.

## Phase 3

G12 real Windows host goldens: **PASS**.
