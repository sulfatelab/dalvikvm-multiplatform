# W-013 native Windows R2 acceptance

**Accepted:** 2026-07-25
**Host:** Windows 10 Enterprise LTSC 2021 x64, build 19044
**PowerShell:** 5.1.19041.7548
**Result:** `OVERALL PASS`

## Evidence identity

```text
returned archive: w013-log-r2.7z
returned archive SHA-256: 456e297d70c2f166308c869812ddec262fa38bc6dcd2852ea56edd5b2205078e
issued package SHA-256: 935708f339e39ef0e3f2c2f2239997adc7fa42907977b83f5870de45d3b1e0a7
root commit: c909ca797372dbd30464f7ca1279380510d0f231
ART commit: 27a1ac74a42957d68d1e21eb941e13e7976f8085
dlmalloc commit: f3356ce765ab7788e51632fcd36c4a30233ca90d
```

The returned `BUILD_INFO.txt`, `MANIFEST.json`, and `SHA256SUMS.txt` are
byte-for-byte identical to the issued R2 package metadata. The 7z archive
passes integrity testing and contains the requested complete logs plus those
three metadata files.

## Independent review

- `RESULT_W013.txt`: 56 PASS records, zero FAIL records, final
  `OVERALL PASS`.
- 52 child-process combined logs: every exit code is present and expected;
  every `timed_out` value is `False`; every `metrics_sampled` value is `True`;
  all three peak-memory fields are populated; no launch error is present.
- Native mapping probe: exact/anywhere/low placement, 4-GiB boundary,
  32 page-state transitions, 3,856 fragmented reservations, complete low-VA
  exhaustion/recovery, and 128 destruction cycles pass. Its one overflow
  diagnostic is the intentionally rejected overflow test.
- Embedded dlmalloc and actual ART mspace-owner probes pass.
- Non-moving pressure passes at both 128-MiB and 1-GiB `-Xmx`, with
  75,497,472 bytes churned, stable addresses, low-address placement, and
  post-GC regrowth.
- GCForced, GCStress, ThreadHeavy, HandleLeak, 512-MiB startup, and 1-GiB
  startup pass. HandleLeak completes 400 file cycles, 80 socket cycles, and
  the final regular-file round trip.
- Default dual-view JIT creates the corrected J-2 mapping, records 30
  successful compilations, prints Hello, and returns without exception.
- Diagnostic J-1 creates its code cache, records 26 successful compilations,
  prints Hello, and returns without exception; the R1 RX metadata-write crash
  does not recur.
- JIT disable, `-Xusejit:false`, filter, exclude, and quiet modes pass. The
  fourteen-case JIT matrix passes, including the expected exit 1 throw case.
- Twenty independent default-JIT starts pass with sampled metrics.
- Fatal/access-violation scan passes and recursive dump scan reports
  `NO_DMP_FILES`.

## Host capacity

```text
physical memory: 34,286,325,760 bytes
pagefile: C:\pagefile.sys, 9,216 MiB allocated
1-GiB non-moving peak paged bytes: 2,323,124,224
1-GiB non-moving peak working set: 1,080,135,680
1-GiB Hello peak paged bytes: 2,323,066,880
1-GiB Hello peak working set: 1,080,139,776
```

The native R2 evidence satisfies every closure condition in
`win32_heap_memory.md`. W-013 is closed; broader JIT mapping/mitigation work
remains tracked separately by W-025.
