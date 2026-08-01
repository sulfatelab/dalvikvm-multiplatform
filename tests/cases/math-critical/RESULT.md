# Shared Math CriticalNative restoration result

**Status:** PASS in the unified Linux and native Windows W-004 stages
**Date:** 2026-08-01
**Scope:** W-024 product demotion, PE registration-table removal, and maintained
CriticalNative interpreter/JIT acceptance

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

An audit of local Windows x64 libcore commits and `ART-WinNT` markers found no other
CriticalNative/FastNative Java demotion. Existing annotated native surfaces
remain intact; the only explicit pure-Java demotion was Math ceil/floor.

## Unified focused acceptance

`MathCriticalProbe` verifies that reflection reports both methods as native.
For 23 edge inputs it compares direct and reflective calls against
`StrictMath`, preserving exact raw bits for finite values, infinities, and
signed zero while accepting any NaN payload. It then executes 2,000 direct-call
rounds to exercise compiled callers.

The case-local, shell-free `run.py` runs both `-Xint` and threshold-zero JIT
twice. It accepts only the exact `linux-x86_64-gnu` and
`windows-x86_64-msvc` target IDs. Windows JIT runs enable the narrow
`MathCriticalProbe` compiler filter and require an explicit successful compile
record; Linux uses its ordinary JIT diagnostics. Every child must report the
native modifiers, 23 edge cases, 2,000 rounds, the exact checksum, clean ART
termination, and no fatal or dump marker.

On Windows Server 2025 x86-64, two consecutive unified W-004 invocations
started from `ninja: no work to do.` and passed 26/26. The Math matrix passed
in 5.59 and 5.64 seconds. On Linux x86-64, the fresh 1,586-edge W-004 build and
its no-op repeat passed 5/5; the four-process Math matrix completed in 1.31
seconds. A Linux-hosted Windows cross run rebuilt 66 affected test/JVMTI edges,
passed the W-004 source/object reviewer, and immediately repeated as a Ninja
no-op. PE runtime execution remains a native-Windows gate, not a cross-host
claim.

The current deterministic checksum is:

```text
0x2900b87ac0cf269a
```

The live W-004 reviewer invokes the shared W-024 source audit, which rejects a
reintroduced `gMethodsWin`/`_WIN32` branch or missing native declarations and
common registrations. The runner writes one portable aggregate `result.json`,
rejects filesystem links/reparse points in its work tree, and records no
machine absolute paths.

## Historical regression verification

The same rebuilt source and shared boot artifact passed:

- Windows x64 `libopenjdk.dll` build;
- Linux `libopenjdk.so` build;
- JIT smoke, 12/12, including default-silent compile diagnostics;
- JIT matrix, 14/14, including `MathProbe.done=ok`;
- CriticalNative direct/signature acceptance, 6/6 plus 3/3 instrumentation in
  each memory mode;
- JVMTI forced-interpreter acceptance, 3/3 in each memory mode;
- Windows x64 `ZipProbe`/HashMap and conscrypt `SslProviderProbe`;
- Linux `ZipProbe`/HashMap and L-005 imageless Hello.

The current Linux converter does not build `libjavacrypto.so`, so a Linux
conscrypt provider run is not available in that graph. This is a native-module
packaging difference, not a boot-jar difference or a CriticalNative blocker.

## Shared boot artifact

The final jar includes the shared filesystem selector, conscrypt, and OkHttp.
Windows x64 staging, `/tmp/vm`, and the Linux L-005 run consumed identical bytes:

```text
sha256 3cbe9a7f0e4596229c0c5e229e6655463373b1445922b9557286313a28a35a2a
size   3436578 bytes
entries classes.dex, classes2.dex, java/security/security.properties
```

Linux and Windows x64 do not have separate boot jars; only their native modules
differ by platform.

## Maintained commands

```text
python3 tools/build_art.py test --target-id linux-x86_64-gnu --build-type RelWithDebInfo --stage w004 --parallel 32
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w004 --parallel 16
```

Related files:

- `run.py`
- `MathCriticalProbe.java`
- `../../../tests/cases/jni-critical-native/RESULT.md`
- `../jvmti-force/RESULT.md`
- `../../../win32_open_items.md` W-024
