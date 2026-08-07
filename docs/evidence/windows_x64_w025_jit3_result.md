# W-025 JIT-3 / FS-3 native lifecycle and unwind acceptance

**Status:** PASS; JIT-3/FS-3 complete

**Date:** 2026-07-29

**Build host:** agent01

**Native host:** Windows Server 2025 Datacenter Evaluation x64, build 26100

## Outcome

The corrected default J-2 code cache now has native closure evidence for
concurrent compilation, invalidation, collection, exact-address reuse,
runtime-function deletion/re-registration, lookup, and virtual unwind. A J-1
comparison arm passed the same invariants; it remains diagnostic-only and is
not the product default.

The four native processes completed 52 collection cycles, 1,344 optimizing
and normal-JNI compilations, and 1,248 exact code-address reuses. Concurrent
sampling observed 696,929 stable-live lookups, 5,909,811 stable-dead lookups,
6,740,836 transition lookups, and 696,969 successful virtual unwinds, with:

```text
missing_live=0
stale_dead=0
unwind_failures=0
callback_tables=0
```

The result accepts immutable per-allocation `RtlAddFunctionTable()` records at
this load. A callback table is neither used nor justified by the observed
correctness or lookup behavior.

## JNI float/double regression found by the gate

The first lifecycle preflight exposed a separate Windows nterp return-ABI bug,
not a J-2 mapping or unwind failure. Compiled quick and normal JNI hard-float
results already returned in `XMM0`, but the Windows nterp invoke epilogue
overwrote `XMM0` from `RAX`. A normal JNI Native-to-Runnable transition leaves
the thread-state constant `0x5c000000` in `RAX`, so Java received that bit
pattern as both the float and double result even though `XMM0` was correct.

ART `43f866830e` restores the common hard-float rule: keep the result in
`XMM0` and mirror it into `RAX` only for GPR-view consumers. The final native
gate exercised 16 managed and eight normal-JNI targets through every lifecycle
cycle; all four processes returned the same managed checksum and
`jni_values=pass`. The existing compiled normal/FastNative ABI regression also
remains 7/7.

## Native Windows acceptance

| Case | Mode | Cycles | Compilations | Exact reuse | Live / dead lookup | Virtual unwind | Maximum lookup |
|------|------|-------:|-------------:|------------:|--------------------:|---------------:|---------------:|
| `jit3_j2_stress` | J-2 | 24 | 600 | 576 | 297,312 / 2,867,348 | 297,330 | 706,100 ns |
| `jit3_j1_compare` | J-1 | 12 | 312 | 288 | 153,887 / 1,237,252 | 153,896 | 130,000 ns |
| `jit3_j2_repeat_a` | J-2 | 8 | 216 | 192 | 126,245 / 804,222 | 126,253 | 122,800 ns |
| `jit3_j2_repeat_b` | J-2 | 8 | 216 | 192 | 119,485 / 1,000,989 | 119,490 | 206,700 ns |

The per-case integer average lookup time printed as 0 ns because the mean was
below one `QueryPerformanceCounter` tick before conversion. The nonzero
maximums above preserve the measured latency bound; the zero is timer
quantization, not zero-cost lookup.

The PowerShell runner returned nine PASS records, zero failures, and
`OVERALL PASS`. Every child exited zero without timeout, forbidden-log scanning
passed, `jit-temp` remained empty, and the recursive scan returned
`NO_DMP_FILES`.

## Package and independent review

The final package records root commit
`a741cfa8ab8e6388fcb78cae9b3c4c0ec63e898a` and ART commit
`43f866830eee0ee666b1cf3e9d2b3abffc45180b`. Its issued ZIP SHA-256 is
`8446a41d72aba32e19ce53cba8ac4b518b182bdebcd68c8023ce6e2ac6d0759f`.

The returned archive independently passed CRC/path safety, immutable package
identity, manifest payload hashes, exact child-set and lifecycle invariants,
J-2/J-1 mode markers, JNI values, aggregate records, host-build floor, dump,
trace, and temporary-file review:

```text
W-025 JIT-3 native host result review: PASS cases=4 aggregate_pass=9 failures=0 collections=52 compilations=1344 exact_reuse=1248 archive_sha256=dcd3062a95a00296ca939062cc52fb7907405cc7c4e08ae72723a318063284fd
```

This summary retains the immutable package/archive identities and independent
review conclusion. The package-era per-process log bundle was removed after
the same contracts migrated to the unified W-025 stage.

## Next gate and J-1 boundary

JIT-4 is next: run the final default-build native regression archive covering
the JIT smoke/matrix, JIT-disabled control, and representative managed,
normal/FastNative/CriticalNative, OSR, and fatal-unwind cases.

Do not remove `ART_WINDOWS_X64_JIT_DUAL=0` yet. The J-1 diagnostic opt-out is
scheduled for JIT-5, only after JIT-4 independently accepts the default J-2
build. Its removal must then be followed by Windows, Wine, and Linux
regressions and a documentation/open-item cleanup.
