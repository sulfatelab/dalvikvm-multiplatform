# Win64 CriticalNative / FastNative ABI analysis gate

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/win64_phase1` RelWithDebInfo.

## Current baseline

`run_native_abi_probe.sh` is a regression reproducer for W-024, not an
acceptance test for enabling native JIT.

| Mode | Result |
|------|--------|
| Native-method JIT gate closed | PASS: `FastNativeAbiProbe OK`, exit 0 |
| `ART_WIN64_JIT_NATIVE=1`, filter `System.arraycopy` | Expected baseline failure after the native method is compiled; probe does not reach its OK marker |

Command:

```sh
bash tools/verify/win64_phase4/run_native_abi_probe.sh
```

The gate-open run currently times out while Wine receives repeated faults
after the first bad compiled-JNI call. The stable evidence is that
`System.arraycopy(Object,int,Object,int,int)` is successfully JIT-compiled and
the probe then fails before its success marker. A separate focused run of the
existing `PerfSmokeProbe` reported `NullPointerException: src == null` at the
same transition.

## Root cause

The x86-64 JNI compiler has two conventions at once:

1. Incoming ART managed ABI: `RDI = ArtMethod*`, Java core arguments in
   `RSI/RDX/RCX/R8/R9`, and floating arguments in `XMM0..XMM7` using a
   separate floating register sequence.
2. Outgoing Win64 native ABI: unified argument ordinals select
   `RCX/RDX/R8/R9` or `XMM0..XMM3`, followed by stack arguments after the
   mandatory 32-byte shadow area.

ART commit `f87f5de9d3` correctly added the second convention, but reused its
register arrays and limits in `X86_64ManagedRuntimeCallingConvention`. The JNI
stub therefore reads the first Java core argument from `RDX` instead of
`RSI`, allows only three Java core register arguments after the method
register, and treats managed floating arguments after `XMM3` as stack values.

For `System.arraycopy`, the real managed input is `src` in `RSI` and
`srcPos == 0` in `RDX`; the bad stub reads `RDX` as `src`, producing a null
source. `StringFactory.newStringFromBytes` fails analogously because its
`byte[] data` is in `RSI` while `high == 0` is in `RDX`.

## Prototype confirmation

A temporary research patch split managed and native register tables and kept
the managed limits at six core/eight floating registers. It produced:

- filtered `System.arraycopy` `PerfSmokeProbe`: exit 0, `perf.ok=true`;
- unrestricted `ART_WIN64_JIT_NATIVE=1` Hello: exit 0 with compiled
  `StringFactory.newStringFromBytes`;
- `FastNativeAbiProbe`: exit 0 after compiled `System.arraycopy`.

This also exercises seven outgoing native arguments, including the Win64
shadow area and three stack arguments. The prototype was reverted; the native
JIT gate remains required until the complete ABI patch and mixed-FP tests are
landed.

Direct optimizing-compiler CriticalNative calls are a separate W-024 path.
Their confirmed defects are the SysV-shaped direct-call visitor and the
unresolved critical dlsym stub's live-`r11` caller-PC clobber. See
`win32_open_items.md` and `win32_jit_memory.md`.
