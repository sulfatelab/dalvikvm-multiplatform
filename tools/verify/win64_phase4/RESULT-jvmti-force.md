# Win64 JVMTI forced-interpreter result

**Status:** PASS under Wine
**Date:** 2026-07-24
**Scope:** W-024 debugger/JVMTI forced-interpreter transition

## Result

The Win64 `openjdkjvmti.dll` plugin loads through ART's normal
`-Xplugin:openjdkjvmti.dll` path. A minimal JVMTI agent enables
thread-scoped `JVMTI_EVENT_SINGLE_STEP` on the Java main thread, which exercises
ART's real `IncrementForceInterpreterCount` and deoptimization path.

The focused acceptance passed three times in each JIT-memory mode:

```text
dual run=1..3 PASS
j1 run=1..3 PASS
JVMTI forced-interpreter acceptance: dual=3/3 j1=3/3
```

Before, during, and after forced interpretation, registered and unresolved
normal JNI, `@FastNative`, and `@CriticalNative` calls returned the exact same
values:

```text
normalRegistered=137.75 fastRegistered=237.75 criticalRegistered=337.75
normalDlsym=437.75 fastDlsym=537.75 criticalDlsym=637.75
```

Single-step events rose from zero only while the event was enabled. Each
current run observed `before=0`, `during=7988`, `disabled=7993`, and
`final=7993`, proving that delivery stopped after disable. Every process ended
with `JvmtiForceProbe OK` and `main end exception=0`.

## Runtime behavior and findings

ART's Linux behavior is the correct model for Windows:

- forced interpretation applies to the Java caller;
- native methods continue through JNI compiler/generated entrypoints;
- registered and unresolved bindings remain valid across the transition;
- no signature-specific `InterpreterJni` detour is required.

The former Windows-only branch in `ShouldStayInSwitchInterpreter()` forced
native methods into `InterpreterJni`. Removing it reduces platform divergence
and avoids a fatal unsupported-shorty abort for the probe's `DJDIF` return and
arguments. The common ART behavior passes all six native calls in both memory
modes.

The debuggable runtime intentionally refuses to JIT-compile
`@CriticalNative` methods. The acceptance therefore requires exactly one
successful compile record for each registered normal/FastNative target and no
successful CriticalNative compilation. CriticalNative calls are still covered
before, during, and after forced interpretation through their supported
non-JIT path.

## Win64 plugin boundary

`openjdkjvmti` remains a separate DLL, matching the Linux shared-library
topology. All 29 upstream translation units build for Win64. The PE-specific
compatibility is narrow:

- `_msize()` supplies the Windows equivalent of `malloc_usable_size()`;
- optional plugin consumers call an exported ART accessor for
  `Thread::Current()` because PE cannot import C++ `thread_local` data;
- only the zero-initialized ART runtime fields actually referenced by the
  plugin receive explicit PE data import/export annotations.

`ArtPlugin_Initialize` and `ArtPlugin_Deinitialize` are exported from
`openjdkjvmti.dll`; the plugin does not get folded into `art.dll`.

## Shared boot artifact

Linux and Win64 do not have separate boot jars. The Wine probe and Linux L-005
gate consume the same Win64-staged shared multipath artifact:

```text
build/win64_phase1/run/boot.jar
sha256 a398657762ce19b18bf9e0ade82400cbb9ffce9e7765afb35900b03d77cff7c1
size   3146511 bytes
```

The shared-jar design and runtime OS selection are recorded in
`archived/shared_bootjar_runtime_os_detection.md`.

## Command

```text
tools/verify/win64_phase4/run_jvmti_force_probe.sh
```

Related files:

- `run_jvmti_force_probe.sh`
- `src/JvmtiForceProbe.java`
- `jvmti_force/jvmti_force_probe.c`
- `../win64_phase1/CMakeLists.txt`
- `../../../win32_open_items.md` W-024
