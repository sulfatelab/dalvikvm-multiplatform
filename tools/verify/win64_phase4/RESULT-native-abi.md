# Win64 CriticalNative / FastNative ABI analysis gate

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/win64_phase1` RelWithDebInfo.

## Current baseline

`run_native_abi_probe.sh` is now an acceptance test for the compiled-JNI
convention split. Set `EXPECT_FIXED=0` only when reproducing the historical
pre-split behavior.

| Mode | Result |
|------|--------|
| Native-method JIT gate closed | PASS: `FastNativeAbiProbe OK`, exit 0 |
| `ART_WIN64_JIT_NATIVE=1`, filter `System.arraycopy` | PASS: compiled stub, `FastNativeAbiProbe OK`, exit 0 |

Command:

```sh
bash tools/verify/win64_phase4/run_native_abi_probe.sh
```

The historical gate-open run timed out while Wine received repeated faults
after the first bad compiled-JNI call. The pre-split evidence was that
`System.arraycopy(Object,int,Object,int,int)` compiled successfully and the
probe failed before its success marker; a focused `PerfSmokeProbe` reported
`NullPointerException: src == null` at the same transition. The current split
passes both the control and gate-open runs.

## Root cause

The x86-64 JNI compiler has two conventions at once:

1. Incoming ART managed ABI: `RDI = ArtMethod*`, Java core arguments in
   `RSI/RDX/RCX/R8/R9`, and floating arguments in `XMM0..XMM7` using a
   separate floating register sequence.
2. Outgoing Win64 native ABI: unified argument ordinals select
   `RCX/RDX/R8/R9` or `XMM0..XMM3`, followed by stack arguments after the
   mandatory 32-byte shadow area.

Before this stage, ART commit `f87f5de9d3` correctly added the second
convention, but reused its register arrays and limits in
`X86_64ManagedRuntimeCallingConvention`. The JNI stub consequently read the
first Java core argument from `RDX` instead of `RSI`, allowed only three Java
core register arguments after the method register, and treated managed
floating arguments after `XMM3` as stack values. The implementation now keeps
separate managed and native arrays/limits.

For `System.arraycopy`, the real managed input is `src` in `RSI` and
`srcPos == 0` in `RDX`; the bad stub reads `RDX` as `src`, producing a null
source. `StringFactory.newStringFromBytes` fails analogously because its
`byte[] data` is in `RSI` while `high == 0` is in `RDX`.

## Implementation confirmation

The landed split keeps the managed limits at six core/eight floating registers
and uses the Win64 four-slot table only for native destinations and scratch
registers. It produces:

- filtered `System.arraycopy` `PerfSmokeProbe`: exit 0, `perf.ok=true`;
- unrestricted `ART_WIN64_JIT_NATIVE=1` Hello: exit 0 with compiled
  `StringFactory.newStringFromBytes`;
- `FastNativeAbiProbe`: exit 0 after compiled `System.arraycopy`.

This also exercises seven outgoing native arguments, including the Win64
shadow area and three stack arguments. The native-JIT gate remains a diagnostic
override while mixed-FP, high managed-FP ordinal, unresolved app-JNI, and
normal/Fast/Critical state-transition coverage are added.

Direct optimizing-compiler CriticalNative calls are a separate W-024 path.
The Win64 visitor and unresolved critical dlsym `r11` defects are now fixed and
covered by `RESULT-critical-native.md`. W-024 remains open for unresolved mixed
dlsym coverage, broader state-transition tests, product demotions, and removal
of the native-JIT diagnostic gate.
