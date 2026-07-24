# Shared Math CriticalNative restoration result

**Status:** PASS under Wine and Linux
**Date:** 2026-07-24
**Scope:** W-024 product demotion and PE registration-table removal

## Source result

`Math.ceil(double)` and `Math.floor(double)` are native and annotated
`@CriticalNative` again. The portable Java stand-ins and their `ART-WinNT`
comments are removed.

`Math.c` now has one registration table for ELF and PE. The Windows-only
wrappers, `_WIN32` branch, and `gMethodsWin` table are removed; `ceil` and
`floor` are present in the common table with the other Math native methods.

The two restored libcore files exactly match their state before multipath
workaround commit `f16cd44db5fe`:

```text
ojluni/src/main/java/java/lang/Math.java
ojluni/src/main/native/Math.c
```

This is deliberately the Android 16 branch baseline. Its pure-C
`FAST_NATIVE_METHOD` macro expands to the same `JNINativeMethod` record as the
later cosmetic `CRITICAL_NATIVE_METHOD` spelling; no later-AOSP source drift is
needed for this fix.

An audit of local Win64 libcore commits and `ART-WinNT` markers found no other
CriticalNative/FastNative Java demotion. Existing annotated native surfaces
remain intact; the only explicit pure-Java demotion was Math ceil/floor.

## Focused acceptance

`MathCriticalProbe` verifies that reflection reports both methods as native.
For 23 edge inputs it compares direct and reflective calls against
`StrictMath`, preserving exact raw bits for finite values, infinities, and
signed zero while accepting any NaN payload. It then executes 2,000 direct-call
rounds to exercise compiled callers.

```text
dual run=1..3 PASS
j1 run=1..3 PASS
xint run=1..3 PASS
linux-xint PASS
linux-jit PASS
Math CriticalNative acceptance: dual=3/3 j1=3/3 xint=3/3 linux-xint=1/1 linux-jit=1/1
```

The current deterministic checksum is:

```text
0x2900b87ac0cf269a
```

The script also rejects a reintroduced `gMethodsWin`/`_WIN32` branch or missing
native declarations/common registrations.

## Regression verification

The same rebuilt source and shared boot artifact passed:

- Win64 `libopenjdk.dll` build;
- Linux `libopenjdk.so` build;
- JIT smoke, 12/12, including default-silent compile diagnostics;
- JIT matrix, 14/14, including `MathProbe.done=ok`;
- CriticalNative direct/signature acceptance, 6/6 plus 3/3 instrumentation in
  each memory mode;
- JVMTI forced-interpreter acceptance, 3/3 in each memory mode;
- Win64 `ZipProbe`/HashMap and conscrypt `SslProviderProbe`;
- Linux `ZipProbe`/HashMap and L-005 imageless Hello.

The current Linux converter does not build `libjavacrypto.so`, so a Linux
conscrypt provider run is not available in that graph. This is a native-module
packaging difference, not a boot-jar difference or a CriticalNative blocker.

## Shared boot artifact

The final jar includes the shared filesystem selector, conscrypt, and OkHttp.
Win64 staging, `/tmp/vm`, and the Linux L-005 run consumed identical bytes:

```text
sha256 3cbe9a7f0e4596229c0c5e229e6655463373b1445922b9557286313a28a35a2a
size   3436578 bytes
entries classes.dex, classes2.dex, java/security/security.properties
```

Linux and Win64 do not have separate boot jars; only their native modules
differ by platform.

## Command

```text
tools/verify/win64_phase4/run_math_critical_probe.sh
```

Related files:

- `run_math_critical_probe.sh`
- `src/MathCriticalProbe.java`
- `RESULT-critical-native.md`
- `RESULT-jvmti-force.md`
- `../../../win32_open_items.md` W-024
