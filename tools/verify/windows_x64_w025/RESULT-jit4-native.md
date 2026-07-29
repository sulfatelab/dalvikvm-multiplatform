# W-025 JIT-4 final native regression acceptance

**Status:** PASS; JIT-4 complete

**Date:** 2026-07-29

**Build host:** agent01

**Native host:** Windows Server 2025 Datacenter Evaluation x64, build 26100

## Outcome

The default J-2 pagefile-section dual view has passed the final native
regression gate. The 28 child cases produced 34 aggregate PASS records, zero
failures, and `OVERALL PASS`. The gate did not execute a J-1 arm:
`default_memory_mode=j2` and `j1_cases=0`.

This closes JIT-4 and authorizes JIT-5 removal of
`ART_WINDOWS_X64_JIT_DUAL=0` and the Windows single-view diagnostic branch.
It does not claim that J-1 is already absent. W-025 remains open until that
removal and its Windows, Wine, and Linux regressions pass.

## Native coverage

The independently accepted archive covers:

- the exact 12-record JIT smoke, including verbose compile filtering and
  default-silent diagnostics;
- the exact 14-workload JIT matrix, including the intentional
  `ThrowProbe` exit-1 exception contract;
- both `ART_WINDOWS_X64_JIT=0` and `-Xusejit:false` controls;
- default CriticalNative and default normal/FastNative ABI/tracing, with all
  seven normal/FastNative targets compiled exactly once;
- nterp and switch-interpreter OSR;
- eight J-2 lifecycle/collection/reuse cycles with concurrent unwind lookup;
  and
- static, threshold-zero compiled-JIT, and OSR fatal origins.

The lifecycle cross-regression reports:

```text
cycles=8
collections=8
compilations=216
exact_reuse=192
live_lookups=85938
dead_lookups=855876
transition_lookups=859362
virtual_unwinds=85944
missing_live=0
stale_dead=0
unwind_failures=0
callback_tables=0
jni_values=pass
```

All nonfatal logs passed forbidden-marker review. `jit-temp` remained empty
and the run left no trace files.

## Fatal and dump result

All three fatal cases reached the required origin before the deliberate native
access violation. ART's VEH and UEF ran and each case created one new valid
`MDMP` file:

| Origin | Bytes | SHA-256 |
|--------|------:|---------|
| Static | 747,247 | `fe1d43e147b2e113190ddae1cc7976ce07394f4bf563a8e93f28317f4d70a73c` |
| Threshold-zero JIT | 749,981 | `125ebf5156a323ad7c6e2d766788c5fc4666d3b764010159c625fc04627dfdb2` |
| OSR | 745,891 | `40e5dffb4edf86fca090ef4f27c6fbb1055bdde92a2483933584ceb539fa2fa3` |

## Gate defects found and corrected

The first package attempt faulted before `jit_ready` because phase 1 staged a
stale `libopenjdk.dll`. It read the retired
`ART_WIN64_CRASH_NATIVE_WARMUP` key while the current runner exported
`ART_WINDOWS_X64_CRASH_NATIVE_WARMUP`. Root `fd1de38d236f` rebuilt and staged
the current module and hardened source/package validation against the retired
key.

Candidate 1 then exposed two checker errors, not runtime failures. The smoke
runner searched for a truncated `StringFactory` compile marker, and the matrix
required a zero exit from `ThrowProbe` even though that probe intentionally
throws `RuntimeException("phase3-throw-ok")`. Root `a095f93d684` now requires
the complete return-type-qualified marker and the exact exit-1 exception
contract. PowerShell parser validation and the final native archive both pass.

## Package and independent review

The final package records root commit
`a095f93d684c39a7454919255aa7fa508497f38d` and ART commit
`43f866830eee0ee666b1cf3e9d2b3abffc45180b`. Its issued ZIP SHA-256 is
`411671ab378dab9fa4c4732934deb575d7dfb5873b5ab75ffe605514afcc8cf1`.
The returned ZIP SHA-256 is
`843391f11e22225516162b25de0412d790c9ea669d0383a996e739aae8480096`.

Independent review returned:

```text
W-025 JIT-4 native host result review: PASS cases=28 aggregate_pass=34 failures=0 fatal_dumps=3 archive_sha256=843391f11e22225516162b25de0412d790c9ea669d0383a996e739aae8480096
```

Immutable identities and compact native records are archived in
[`evidence/jit4_native/`](evidence/jit4_native/).

## Next gate

JIT-5 is next. Remove `ART_WINDOWS_X64_JIT_DUAL=0` and its single-view Windows
diagnostic branch, then run the post-removal Windows, Wine, and Linux
regressions. Update W-025 to closed only after those regressions pass.
