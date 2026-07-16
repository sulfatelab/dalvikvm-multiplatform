# Win64 Phase 3 — System.gc hang fix (ThreadCpuNanoTime + WaitOnAddress)

**Date:** 2026-07-16  
**Symptom:** Explicit `System.gc()` under wine64 CMS hung (often empty app stdout after startup).  
**Also observed:** `ThreadCpuNanoTime() unimplemented` logs; WaitOnAddress timeout false-without-error on some wine builds.

## Root causes (combined)

1. **`ThreadCpuNanoTime`** returned a sentinel / unimplemented path on Windows, confusing GC/runtime accounting.
2. **WaitOnAddress timeout** on wine could return false with `GetLastError()==0`, leaving errno unset so ART did not treat the wait as `ETIMEDOUT` (spin / hang under CMS suspend waits).
3. Sub-millisecond relative timeouts could round to **0ms** and busy-spin.

## Fix A — `vendor/art/libartbase/base/time_utils.cc`

Implement Windows `ThreadCpuNanoTime` via `GetThreadTimes` (kernel+user FILETIME → ns). On failure fall back to `NanoTime()` rather than `-1`.

```cpp
uint64_t ThreadCpuNanoTime() {
#if defined(__linux__)
  timespec now;
  if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now) != 0) {
    // TODO(415170313): For now just log an error. Once we have verified that
    // these don't happen often change this to a CHECK.
    PLOG(ERROR) << "Failed to get thread cpu time";
  }
  return static_cast<uint64_t>(now.tv_sec) * UINT64_C(1000000000) + now.tv_nsec;
#elif defined(_WIN32)
  // Windows has no CLOCK_THREAD_CPUTIME_ID. Approximate with GetThreadTimes.
  FILETIME create_t, exit_t, kernel_t, user_t;
  if (!GetThreadTimes(GetCurrentThread(), &create_t, &exit_t, &kernel_t, &user_t)) {
    return NanoTime();  // fall back to wall clock rather than -1
  }
  auto ft_to_ns = [](const FILETIME& ft) -> uint64_t {
    ULARGE_INTEGER uli;
    uli.LowPart = ft.dwLowDateTime;
    uli.HighPart = ft.dwHighDateTime;
    // FILETIME is 100ns units
    return uli.QuadPart * 100ull;
  };
  return ft_to_ns(kernel_t) + ft_to_ns(user_t);
#else
  // Approximate with wall time.
  return NanoTime();
#endif
}
```

Rebuild: compile `time_utils.cc.obj` into `artbase.lib`, then relink `art.dll`.

## Fix B — `vendor/art/runtime/base/mutex-inl.h` (Windows futex)

Key behaviors:

- Round relative timeout **up** to ms; if positive timeout rounds to 0, wait **at least 1ms**.
- On `WaitOnAddress` failure:
  - `ERROR_TIMEOUT` → `errno = ETIMEDOUT`
  - wine false-without-error (`err == 0`) → `errno = ETIMEDOUT`
  - else → `errno = EINTR`
- Keep `WakeByAddressSingle` / `WakeByAddressAll` for WAKE ops.

Representative block (reapply into Windows futex path):

```cpp
#if ART_USE_FUTEXES
#if defined(_WIN32)
// WaitOnAddress-based futex. Supports WAIT/WAKE used by ART mutexes.
// FUTEX_* constants are provided by linux/futex.h shim on Windows.
static inline int futex(volatile int *uaddr, int op, int val, const struct timespec *timeout,
                        volatile int *uaddr2, int val3) {
  (void)uaddr2; (void)val3;
  // Strip PRIVATE bit if present.
  int base_op = op & 0x7f; // ignore flags in high bits roughly
  // Linux FUTEX_PRIVATE_FLAG is 128; ops used: WAIT=0, WAKE=1, WAIT_BITSET=9, WAKE_BITSET=10
  int cmd = op & 0xf; // good enough for ART's usage patterns
  if ((op & 128) != 0) {
    // private flag; ignore
  }
  if (cmd == 0 /*FUTEX_WAIT*/ || cmd == 9 /*FUTEX_WAIT_BITSET*/) {
    DWORD ms = INFINITE;
    if (timeout != nullptr) {
      // Relative timeout (ART always passes relative timespeces into futex()).
      long long total_ms = (long long)timeout->tv_sec * 1000LL +
                           (timeout->tv_nsec + 999999LL) / 1000000LL;  // round up
      if (total_ms < 0) total_ms = 0;
      // If a positive timeout rounded to 0ms, wait at least 1ms so we don't spin forever.
      if (total_ms == 0 && (timeout->tv_sec > 0 || timeout->tv_nsec > 0)) total_ms = 1;
      if (total_ms > 0xffffffffLL) ms = INFINITE;
      else ms = (DWORD)total_ms;
    }
    // Snapshot expected value for WaitOnAddress compare.
    int expected = val;
    int observed = *uaddr;
    if (observed != expected) {
      errno = EAGAIN;
      return -1;
    }
    if (!WaitOnAddress((PVOID)uaddr, &expected, sizeof(int), ms)) {
      DWORD err = GetLastError();
      if (err == ERROR_TIMEOUT || err == ERROR_TIMEOUT /* same */) {
        errno = ETIMEDOUT;
      } else if (err == 0 || err == ERROR_SUCCESS) {
        // Some wine builds return false without setting last error on timeout.
        errno = ETIMEDOUT;
      } else {
        errno = EINTR;
      }
      return -1;
    }
    return 0;
  }
  if (cmd == 1 /*FUTEX_WAKE*/ || cmd == 10 /*FUTEX_WAKE_BITSET*/) {
    if (val == 1) {
      WakeByAddressSingle((PVOID)uaddr);
    } else {
      WakeByAddressAll((PVOID)uaddr);
    }
    return val; // "woken" count unknown; ART ignores exact count mostly
  }
  // Best-effort requeue: wake all on uaddr.
  if (cmd == 3 /*REQUEUE*/ || cmd == 4 /*CMP_REQUEUE*/) {
    WakeByAddressAll((PVOID)uaddr);
    if (uaddr2) WakeByAddressAll((PVOID)uaddr2);
    return 0;
  }
  errno = ENOSYS;
  return -1;
}
#else
static inline int futex(volatile int *uaddr, int op, int val, const struct timespec *timeout,
                        volatile int *uaddr2, int val3) {
  return syscall(SYS_futex, uaddr, op, val, timeout, uaddr2, val3);
}
#endif
#endif  // ART_USE_FUTEXES
```

Note: `mutex-inl.h` is header-only for the futex; consumers include it from `mutex.cc` / other TUs. After edit, rebuild affected objects (at least `mutex.cc.obj`) and **relink `art.dll`** (e.g. `bash /tmp/link_art2.sh`).

## Verification (wine64, 2026-07-16 post-relink)

| Probe | Result |
|-------|--------|
| GcProbe (LOS, no forced GC) | PASS `los.ok=true gc.ok=true` |
| GcForced (tiny+LOS+`System.gc`) | PASS ~1.8s `gc.forced.ok=true` |
| InterruptProbe | PASS |
| GoldenApp (includes `System.gc`) | PASS `golden.ok=true` |

Previously GcTiny / forced System.gc hung to timeout before this DLL (art.dll mtime after patches ~16:28).

## Caveats

- `Runtime.freeMemory()` / `totalMemory()` may still report 0 under imageless Win64; not treated as a hang.
- Host Windows (non-wine) still pending for GC goldens.
- Vendor tree is gitignored; keep this note for reapplication after vendor refresh.

## Repro gate

```bash
source /home/agent/Projects/win64-dev-env/env.sh
bash tools/verify/win64_phase3/build_one.sh GcForced
bash tools/verify/win64_phase3/run_gcforced.sh
bash tools/verify/win64_phase3/run_goldenapp.sh
```
