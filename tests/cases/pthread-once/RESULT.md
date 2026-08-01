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

## Historical diagnosis and fix

The original compatibility implementation changed one `LONG` from 0 to 1
before running the initializer. Losing threads returned immediately, so a
caller could observe partially initialized JNI state. A JIT-scheduled NetProbe
run exposed this when concurrent `AFileDescriptor_getFd()` calls let one thread
use the still-null cached `FileDescriptor.descriptor` field ID while another
thread was initializing `JniConstants`.

The maintained implementation uses three states: uninitialized, initializing,
and initialized. The winning thread runs the initializer and publishes the
final state with an interlocked exchange; other threads yield until that state
is visible. The public `pthread_once_t` representation remains a `LONG`, and no
runtime warm-up workaround was added. Ten interpreter NetProbe controls and
the later JIT/compiled-JNI matrices confirmed that the race was independent of
the CriticalNative ABI work.

Current native reproduction on the 16 GiB Windows VM is:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w014 --parallel 16
```
