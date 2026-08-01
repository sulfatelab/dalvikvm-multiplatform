# Windows x64 compiled normal/FastNative ABI result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/windows_x64_phase1` RelWithDebInfo.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `windows-x86_64-msvc` | yes | verified | verified | 2026-08-01 |
| `windows-aarch64-msvc` | not yet declared | pending | pending | — |
| `windows-arm64ec-msvc` | not yet declared | pending | pending | — |

The scalar C/JNI and Java sources are portability candidates, not evidence for
either AArch64 target. Each target requires its own ABI and runtime acceptance.

## Unified native acceptance (2026-08-01)

The authoritative shell-free `stage:w003` gate passed on Windows Server 2025
x86-64 in four processes: default and method-instrumented execution, each
repeated twice. Every process completed the initial, unregister, and
re-register value phases and emitted exactly seven successful target-method
compile records. The instrumented pair additionally completed the tracing and
post-tracing phases with mode `0 -> nonzero -> 0` and deleted its trace file.
The frame-attribution variant repeated the same matrix. Product and variant
stage repeats were Ninja no-ops and passed again.

Each aggregate JSON records four successful runs, zero dumps, and no machine
absolute paths. The declaration remains the typed
`windows`/`x86_64`/`msvc` intersection pending separate AArch64 or ARM64EC ABI
review and native runtime acceptance.

## Result

The focused compiled-JNI acceptance gate now passes the mixed/high-FP matrix:

| Mode | Result |
|------|--------|
| Default native compilation | PASS: exit 0, three exact binding phases, 7/7 targets and exactly 7 compile records |
| Default native compilation plus method tracing | PASS: tracing mode `0 -> 1 -> 0`, exact during/after values, exactly 7 target compile records |

Transitional compatibility command:

```sh
bash tools/verify/windows_x64_phase4/run_native_abi_probe.sh
```

The post-cleanup run reported:

```text
default_exit=0 default_ok=true compiled_targets=7/7 compilation_records=7
instrumentation_exit=0 instrumentation_ok=true compiled_targets=7/7 compilation_records=7
```

Earlier gate-open qualification and the accepted native-Windows tripwire run
produced the same 7/7 result before the diagnostic gate was removed.

## Root causes

The x86-64 JNI compiler has two conventions at the same stub boundary:

1. Incoming ART managed ABI: `RDI = ArtMethod*`; Java core arguments use
   `RSI/RDX/RCX/R8/R9`; floating arguments independently use `XMM0..XMM7`.
2. Outgoing Windows x64 native ABI: one unified argument ordinal chooses
   `RCX/RDX/R8/R9` or `XMM0..XMM3`; later arguments follow the mandatory
   32-byte home area on the stack.

The first defect was the already-landed convention split. The Windows x64 native
register arrays and four-slot limits had also been used by
`X86_64ManagedRuntimeCallingConvention`, shifting core inputs and treating
managed FP arguments after `XMM3` as stack values. Keeping the managed arrays
Linux-like fixed `System.arraycopy` and `StringFactory.newStringFromBytes`.

The expanded mixed-signature probe then exposed a second defect during JIT
compilation:

```text
jni_macro_assembler_x86_64.cc:399
Move XMM: 3, XMM: 0 unimplemented
```

For the probe's first `double`, the managed ABI supplies `XMM0`, while the two
implicit JNI arguments plus the preceding `long` place that value in Windows x64
native slot 3, `XMM3`. `X86_64JNIMacroAssembler::Move()` supported core-to-core
and x87-to-XMM moves but no XMM-to-XMM move. It now emits `movss` for 4-byte
values and `movsd` for 8-byte values. This is a platform-neutral x86-64
assembler capability; Linux behavior and calling conventions are unchanged.

A focused `MoveXmmRegister` assembler test checks both instruction sizes.

## Coverage

The probe builds its own PE DLL and dex jar, validates the expected PE exports,
loads the library through `System.loadLibrary`, and warms every call site with
`-Xjitthreshold:0`.

The matrix covers:

- normal JNI and `@FastNative`;
- `RegisterNatives` and unresolved exported `Java_*` dlsym lookup;
- static and instance methods;
- `jclass`, `jobject`, and an additional object argument;
- five managed core register ordinals;
- six managed FP register ordinals, including `XMM4` and `XMM5`;
- unified Windows x64 native register slots, the 32-byte home area, and extensive
  stack spills;
- float and double inputs, integral inputs, boolean input, and double returns.

After the initial warmup and compilation, the same process exercises two
binding transitions without recompiling any of the seven target methods:

1. `UnregisterNatives(FastNativeAbiProbe.class)` resets every native data
   entrypoint. The four initially registered methods then resolve exported
   `Java_*` functions through dlsym, while the two initially unresolved methods
   are also reset and resolved again. All six return the `+10000` phase values.
2. A second `RegisterNatives` installs alternate pointers for all six ABI
   methods. The already-compiled JNI thunks return the `+20000` phase values.

The default verifier requires exactly seven successful target compilation
records across all three phases. This proves the transitions execute through
the existing compiled-thunk set rather than passing because ART recompiled the
methods after each binding change.

A third process tests method-tracing instrumentation after the binding phases.
It starts non-sampling tracing through `dalvik.system.VMDebug`, verifies the
runtime tracing mode changes from 0 to 1, executes every alternate normal and
FastNative binding while tracing is active, stops tracing, verifies mode 0,
and executes the same methods again. ART's tracing path switches the runtime to
debuggable, invalidates pre-tracing JIT code, and installs entry/exit
instrumentation support. The target-method log still contains exactly seven
successful compilation records, so native target recompilation is not masking
the transition.

The trace uses a relative temporary file in the Wine run directory. Java
deletes it after tracing, the harness removes it defensively on process exit,
and the acceptance test verifies no file remains.

The registered static signature is `(JDIFJDIFDDI)D`. The unresolved signature
adds a trailing boolean, `(JDIFJDIFDDIZ)D`, so it cannot reuse the registered
JNI thunk and must compile independently. Instance methods use
`(Ljava/lang/Object;JDIFJDIFDDI)D`.

The exact accepted lines are:

```text
FastNativeAbiProbe initial normalRegistered=743.75 fastRegistered=1743.75 normalDlsym=2755.75 fastDlsym=3755.75 normalInstance=4743.75 fastInstance=5743.75 calls=63
FastNativeAbiProbe unregistered normalRegistered=10743.75 fastRegistered=11743.75 normalDlsym=12755.75 fastDlsym=13755.75 normalInstance=14743.75 fastInstance=15743.75 calls=63
FastNativeAbiProbe reregistered normalRegistered=20743.75 fastRegistered=21743.75 normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 fastInstance=25743.75 calls=63
FastNativeAbiProbe tracing normalRegistered=20743.75 fastRegistered=21743.75 normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 fastInstance=25743.75 calls=63
FastNativeAbiProbe postTracing normalRegistered=20743.75 fastRegistered=21743.75 normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 fastInstance=25743.75 calls=63
FastNativeAbiProbe tracingMode before=0 during=1 after=0 traceFileDeleted=true
```

## Regression verification

The final cleanup build passed:

- Windows x64 `art`, `dalvikvm`, and `openjdkjvmti` build;
- default compiled-JNI ABI and rebinding: 7/7 targets with exactly seven
  records;
- default compiled-JNI method tracing: 7/7 targets with exactly seven records;
- CriticalNative dual-view and J-1 acceptance, 6/6 float/signature plus 3/3
  instrumentation runs per mode;
- JVMTI forced-interpreter acceptance, 3/3 dual-view and 3/3 J-1 runs, covering
  registered and unresolved normal, FastNative, and CriticalNative calls;
- JIT smoke, 12/12, including default-silent compile diagnostics;
- JIT matrix, 14/14;
- all Phase 4 Wine gates;
- full native Linux `art` and `dalvikvm` rebuild;
- Linux L-005 imageless Hello using the exact Windows x64-staged shared multipath
  `boot.jar` bytes; and
- Math CriticalNative dual/J-1/`-Xint` plus rebuilt Linux `-Xint` and JIT
  controls.

## Final status

The mixed/high-FP normal/FastNative ABI, unresolved app-JNI,
register/unregister/re-register binding transitions, and method-tracing
instrumentation and JVMTI forced-interpreter transitions pass with native
methods compiled by default. Per-method compile records remain opt-in. Native
Windows 10 acceptance, upstream interpreter fallback restoration, native-JIT
gate removal, and post-change Linux/Windows x64 regressions are complete.
The Math/libcore native demotion is restored in
`../../../tools/verify/windows_x64_phase4/RESULT-math-critical.md`.
CriticalNative method tracing is covered by the adjacent
`../jni-critical-native/RESULT.md`; JVMTI single-step/deoptimization coverage
is recorded in
`../../../tools/verify/windows_x64_phase4/RESULT-jvmti-force.md`.

## Related files

- `probe.c`
- `FastNativeAbiProbe.java`
- `../../../tools/verify/windows_x64_phase4/run_native_abi_probe.sh`
- `../../../win32_open_items.md` W-024
