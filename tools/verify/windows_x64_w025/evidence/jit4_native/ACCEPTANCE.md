# JIT-4 native Windows acceptance evidence

**Status:** PASS

**Accepted:** 2026-07-29

## Identity

- Build host: `agent01`.
- Native host: Windows Server 2025 Datacenter Evaluation x64, version
  10.0.26100, build 26100.
- Windows PowerShell: 5.1.26100.7462.
- Root commit in package:
  `a095f93d684c39a7454919255aa7fa508497f38d`.
- ART commit in package:
  `43f866830eee0ee666b1cf3e9d2b3abffc45180b`.
- Issued package SHA-256:
  `411671ab378dab9fa4c4732934deb575d7dfb5873b5ab75ffe605514afcc8cf1`.
- Returned review archive SHA-256:
  `843391f11e22225516162b25de0412d790c9ea669d0383a996e739aae8480096`.

The issued hash matched after transfer and before extraction. Independent
review accepted ZIP CRC and path safety, immutable package identity, manifest
payload hashes, the exact child set and exit contracts, every required
runtime marker, dump identity and format, the host-build floor, and the
absence of trace and temporary JIT files.

## Result

The W-025 runner completed 28 native child cases with 34 aggregate PASS
records, zero FAIL records, and `OVERALL PASS`. It used only the default J-2
dual view; `j1_cases=0`, so this result authorizes removal of the diagnostic
opt-out but does not claim that J-1 has already been removed.

The archive covers the exact 12-record JIT smoke, exact 14-workload matrix,
both `ART_WINDOWS_X64_JIT=0` and `-Xusejit:false` controls, default
CriticalNative, default normal/FastNative 7/7 compilation, nterp and switch
OSR, eight collection/reuse cycles, and fatal static, threshold-zero JIT, and
OSR origins.

The lifecycle case completed eight collections, 216 optimizing/normal-JNI
compilations, and 192 exact address reuses. Concurrent sampling recorded
85,938 stable-live lookups, 855,876 stable-dead lookups, 859,362 transition
lookups, and 85,944 successful virtual unwinds, with:

```text
missing_live=0
stale_dead=0
unwind_failures=0
callback_tables=0
jni_values=pass
```

The three expected fatal processes exited with access violation status only
after reaching their required static, compiled-JIT, or OSR origin. VEH and UEF
diagnostics ran and produced three new valid `MDMP` files of 747,247, 749,981,
and 745,891 bytes. The JIT temporary directory remained empty and no trace
file remained.

Independent Linux-side review returned:

```text
W-025 JIT-4 native host result review: PASS cases=28 aggregate_pass=34 failures=0 fatal_dumps=3 archive_sha256=843391f11e22225516162b25de0412d790c9ea669d0383a996e739aae8480096
```

The complete issued and returned archives remain in the ignored `dist/`
workspace. Their identities and the compact host, source, aggregate, dump,
review, and key-marker records are retained beside this document.

## Gate corrections made before acceptance

The first package attempt exposed a stale staged `libopenjdk.dll` that still
read `ART_WIN64_CRASH_NATIVE_WARMUP`; the current runner exports
`ART_WINDOWS_X64_CRASH_NATIVE_WARMUP`. Root commit `fd1de38d236f` rebuilt and
staged the current module and made source/package checks reject the retired
key.

Candidate 1 then exposed two expectation defects rather than runtime defects:
the smoke check omitted `java.lang.String` from the `StringFactory` method
marker, and the matrix treated `ThrowProbe`'s intentional
`RuntimeException("phase3-throw-ok")` as a zero-exit success. Root commit
`a095f93d684` requires the complete compile marker and accepts only exit 1,
`main end exception=1`, and the exact exception type/message for that case.

## Next gate

JIT-5 may now remove `ART_WINDOWS_X64_JIT_DUAL=0` and the Windows J-1
single-view diagnostic branch. W-025 closes only after the post-removal
Windows, Wine, and Linux regressions pass and the documentation no longer
promises J-1 availability.
