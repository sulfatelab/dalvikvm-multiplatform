# Win64 compiled normal/FastNative ABI result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/win64_phase1` RelWithDebInfo.

## Result

The focused compiled-JNI acceptance gate now passes the mixed/high-FP matrix:

| Mode | Result |
|------|--------|
| Native-method JIT gate closed | PASS: exit 0, three exact binding phases, 0/7 native targets compiled |
| `ART_WIN64_JIT_NATIVE=1` | PASS: exit 0, three exact binding phases, 7/7 targets and exactly 7 compile records |
| Native gate open plus method tracing | PASS: tracing mode `0 -> 1 -> 0`, exact during/after values, exactly 7 target compile records |

Command:

```sh
bash tools/verify/win64_phase4/run_native_abi_probe.sh
```

The final focused result was repeated for five complete process runs. Every
run reported:

```text
gate_closed_exit=0 gate_closed_ok=true compiled_targets=0/7 compilation_records=0
gate_open_exit=0 gate_open_ok=true compiled_targets=7/7 compilation_records=7 historical_failure=false
instrumentation_exit=0 instrumentation_ok=true compiled_targets=7/7 compilation_records=7
```

## Root causes

The x86-64 JNI compiler has two conventions at the same stub boundary:

1. Incoming ART managed ABI: `RDI = ArtMethod*`; Java core arguments use
   `RSI/RDX/RCX/R8/R9`; floating arguments independently use `XMM0..XMM7`.
2. Outgoing Win64 native ABI: one unified argument ordinal chooses
   `RCX/RDX/R8/R9` or `XMM0..XMM3`; later arguments follow the mandatory
   32-byte home area on the stack.

The first defect was the already-landed convention split. The Win64 native
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
implicit JNI arguments plus the preceding `long` place that value in Win64
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
- unified Win64 native register slots, the 32-byte home area, and extensive
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

The gate-open verifier requires exactly seven successful target compilation
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

The same ART build passed:

- Win64 `art` and `dalvikvm` build;
- CriticalNative dual-view and J-1 acceptance, 6/6 float/signature plus 3/3
  instrumentation runs per mode;
- JVMTI forced-interpreter acceptance, 3/3 dual-view and 3/3 J-1 runs, covering
  registered and unresolved normal, FastNative, and CriticalNative calls;
- pthread_once stress, 10/10;
- JIT smoke, 10/10;
- JIT matrix, 14/14;
- native Linux `nativeloader`, `art`, `openjdkjvm`, and `dalvikvm` build;
- Linux L-005 imageless Hello using the exact Win64-staged shared multipath
  `boot.jar` bytes.

One regression attempt ended with a Wine client `recvmsg: Connection reset by
peer` during a J-1 CriticalNative process. It produced no ART assertion or ABI
failure; the immediate complete CriticalNative rerun passed 6/6 in both memory
modes, and the remaining regressions passed.

## Remaining scope

The mixed/high-FP normal/FastNative ABI, unresolved app-JNI,
register/unregister/re-register binding transitions, and method-tracing
instrumentation and JVMTI forced-interpreter transitions are no longer W-024
blockers. The native-JIT gate remains temporarily while W-024 cleans up the
remaining diagnostic policy/logging and obtains real Windows 10 acceptance.
The Math/libcore native demotion is restored in `RESULT-math-critical.md`.
CriticalNative method tracing is covered by
`run_critical_native_probe.sh`; JVMTI single-step/deoptimization coverage is
recorded in `RESULT-jvmti-force.md`.
