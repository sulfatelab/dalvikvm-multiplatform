# JIT-3/FS-3 native Windows acceptance evidence

**Status:** PASS

**Accepted:** 2026-07-29

## Identity

- Build host: `agent01`.
- Native host: Windows Server 2025 Datacenter Evaluation x64, version
  10.0.26100, build 26100.
- Windows PowerShell: 5.1.26100.7462.
- Root commit in package: `a741cfa8ab8e6388fcb78cae9b3c4c0ec63e898a`.
- ART commit in package: `43f866830eee0ee666b1cf3e9d2b3abffc45180b`.
- Issued package SHA-256:
  `8446a41d72aba32e19ce53cba8ac4b518b182bdebcd68c8023ce6e2ac6d0759f`.
- Returned review archive SHA-256:
  `dcd3062a95a00296ca939062cc52fb7907405cc7c4e08ae72723a318063284fd`.

The issued hash matched after SSH/SCP transfer and before extraction. The
returned archive uses portable ZIP paths and passes CRC, path-safety, symlink,
immutable package-identity, manifest, source-report, child-log, dump, trace,
and JIT-temporary-file review.

## Result

The W-025 runner completed four child cases with nine aggregate PASS records,
zero FAIL records, and `OVERALL PASS`. Every child exited zero without timeout.
Across the default J-2 stress, J-1 comparison, and two additional J-2 runs it
completed 52 collection cycles, 1,344 optimizing/JNI compilations, and 1,248
exact code-address reuses.

Concurrent native sampling recorded 696,929 stable-live lookups, 5,909,811
stable-dead lookups, 6,740,836 transition lookups, and 696,969 successful
virtual unwinds. Every case returned `missing_live=0`, `stale_dead=0`,
`unwind_failures=0`, and `callback_tables=0`. Per-case maximum lookup times
ranged from 122,800 ns to 706,100 ns. The integer mean was below one
`QueryPerformanceCounter` tick and therefore printed as 0 ns; this is a timer-
resolution bound, not a claim that lookup has zero cost.

All 16 managed and eight normal-JNI targets retained exact values before and
after collection/reuse. In particular, `jni_values=pass` covers the float and
double return regression fixed by ART `43f866830e`. The JIT temporary directory
remained empty, forbidden-log scanning passed, and the recursive dump scan
returned `NO_DMP_FILES`.

Independent Linux-side review returned:

```text
W-025 JIT-3 native host result review: PASS cases=4 aggregate_pass=9 failures=0 collections=52 compilations=1344 exact_reuse=1248 archive_sha256=dcd3062a95a00296ca939062cc52fb7907405cc7c4e08ae72723a318063284fd
```

The complete issued and returned archives remain in the ignored `dist/`
workspace. Their identities are retained in `ARCHIVE_SHA256SUMS.txt`; compact
raw stdout, host/package identity, source report, aggregate result, dump scan,
and independent-review record are retained beside this document.
