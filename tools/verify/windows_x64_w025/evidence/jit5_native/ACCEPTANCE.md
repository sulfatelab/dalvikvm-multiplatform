# JIT-5 native Windows acceptance evidence

**Status:** PASS

**Accepted:** 2026-07-29

## Identity

- Build host: `agent01`.
- Native host: Windows Server 2025 Datacenter Evaluation x64, version
  10.0.26100, build 26100.
- Windows PowerShell: 5.1.26100.7462.
- Root commit recorded by the issued package:
  `6b5625f4867a1a0e852d316ed5af722c34612048`.
- ART JIT-5 commit:
  `389158d46f1e982c7d10d63093a42c8aa41fc2a6`.
- Issued package SHA-256:
  `7b35eab8001ee2ba4881985b63d8df6921a954e023f8e70289f964499f57cd32`.
- Accepted returned archive SHA-256:
  `2bddf51924a7ca6b9719ffde433e859007465babf6bf2ca7a12f417eecd6289f`.

The issued hash matched after transfer and before extraction. Independent
review accepted ZIP CRC/path safety, immutable package identity and manifest
hashes, the exact child set and exits, runtime markers, dump identities and
format, and clean trace/JIT-temp state.

## Removal result

The source and rebuilt `art.dll` contain neither
`ART_WINDOWS_X64_JIT_DUAL` nor the retired
`falling back to single-view (J-1)` diagnostic. Windows section creation or
view construction now fails closed instead of entering an executable
single-view path. The common non-Windows single-view fallback remains.

The native negative test deliberately sets the retired key to zero. It still
creates the J-2 pagefile-section dual mapping, compiles `StringBuilder`, prints
Hello, and exits zero. This demonstrates that an inherited deployment
environment cannot reactivate J-1.

## Regression result

The runner completed 29 native child cases with 36 aggregate PASS records,
zero FAIL records, and `OVERALL PASS`. Coverage includes the 14-record
post-removal smoke, 14-workload matrix, both JIT-disabled controls, default
CriticalNative and 7/7 normal/FastNative ABI paths, nterp/switch OSR, eight
collection/reuse cycles, and static/JIT/OSR fatal origins.

The lifecycle case recorded eight collections, 216 compilations, 192 exact
address reuses, 120,648 live lookups, 1,080,878 dead lookups, 1,102,642
transition lookups, and 120,654 successful virtual unwinds. It reported
`missing_live=0`, `stale_dead=0`, `unwind_failures=0`,
`callback_tables=0`, and `jni_values=pass`.

All three fatal origins reached VEH and UEF and created one valid `MDMP` each.
The files are 745,645, 745,067, and 750,705 bytes. `jit-temp` stayed empty and
no trace remained.

Independent Linux-side review returned:

```text
W-025 JIT-5 native host result review: PASS cases=29 aggregate_pass=36 failures=0 fatal_dumps=3 archive_sha256=2bddf51924a7ca6b9719ffde433e859007465babf6bf2ca7a12f417eecd6289f
```

The complete issued and returned archives remain in the ignored `dist/`
workspace. This directory retains compact immutable identity, source,
aggregate, host, dump, review, and marker records.

## Closure

The native result, post-removal Wine gates, full Linux rebuild, imageless
Hello, and Linux GC stress close JIT-5 and W-025. Historical J-1 evidence stays
as a record of bring-up and comparison testing; current documentation and
active runners no longer promise or select that path.
