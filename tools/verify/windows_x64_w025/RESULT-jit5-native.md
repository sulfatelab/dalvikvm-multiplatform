# W-025 JIT-5 removal and native acceptance

**Status:** PASS; JIT-5 and W-025 complete

**Date:** 2026-07-29

**Native host:** Windows Server 2025 Datacenter Evaluation x64, build 26100

## Outcome

ART `389158d46f1e982c7d10d63093a42c8aa41fc2a6` removes the Windows
`ART_WINDOWS_X64_JIT_DUAL` opt-out and the executable single-view J-1
fallback. The pagefile-section dual mapping is now the only Windows JIT memory
path. Section creation or partial view construction failure returns an error
and disables JIT cache creation; it cannot downgrade W^X. The common
non-Windows single-view fallback is unchanged.

The exact native package passed 29 cases and 36/36 aggregate records. Its
retired-key negative test set `ART_WINDOWS_X64_JIT_DUAL=0` and still observed
J-2 creation, compilation, Hello, and clean exit. Source/package checks also
proved that the opt-out and fallback strings are absent from source and the
rebuilt `art.dll`.

## Regression coverage

- Post-removal Wine JIT smoke: 14/14.
- Wine JIT matrix: 14/14.
- Wine default native ABI, CriticalNative, JVMTI, nterp/switch OSR and attach,
  lifecycle/unwind, threshold-zero JIT fatal, and OSR fatal gates: PASS.
- Full Linux rebuild, imageless Hello, GC stress, and Math JIT/`-Xint`
  controls: PASS.
- Native smoke/matrix/JIT-disabled/default ABI/OSR suite: PASS.
- Native eight-cycle lifecycle: eight collections, 216 compilations, 192
  exact reuses, 120,654 virtual unwinds, and zero missing/stale/failed records.
- Native static, threshold-zero JIT, and OSR fatal origins: three valid dumps;
  `jit-temp` empty and no trace.

## Identity and review

Issued SHA-256:
`7b35eab8001ee2ba4881985b63d8df6921a954e023f8e70289f964499f57cd32`.

Accepted returned SHA-256:
`2bddf51924a7ca6b9719ffde433e859007465babf6bf2ca7a12f417eecd6289f`.

Independent review:

```text
W-025 JIT-5 native host result review: PASS cases=29 aggregate_pass=36 failures=0 fatal_dumps=3 archive_sha256=2bddf51924a7ca6b9719ffde433e859007465babf6bf2ca7a12f417eecd6289f
```

Compact evidence is under
[`evidence/jit5_native/`](evidence/jit5_native/).

## Closure decision

W-025 is closed. No remaining product or diagnostic Windows path selects J-1.
Historical result files may retain J-1 references because they document gates
run before removal. CET user shadow-stack support remains a separate explicit
non-goal under W-010, not residual W-025 work.
