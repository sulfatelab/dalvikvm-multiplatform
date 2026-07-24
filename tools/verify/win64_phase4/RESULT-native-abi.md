# Win64 compiled normal/FastNative ABI result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/win64_phase1` RelWithDebInfo.

## Result

The focused compiled-JNI acceptance gate now passes the mixed/high-FP matrix:

| Mode | Result |
|------|--------|
| Native-method JIT gate closed | PASS: exit 0, exact values, 0/7 native targets compiled |
| `ART_WIN64_JIT_NATIVE=1` | PASS: exit 0, exact values, 7/7 native targets compiled |

Command:

```sh
bash tools/verify/win64_phase4/run_native_abi_probe.sh
```

The final focused result was repeated for five complete process runs. Every
run reported:

```text
gate_closed_exit=0 gate_closed_ok=true compiled_targets=0/7
gate_open_exit=0 gate_open_ok=true compiled_targets=7/7 historical_failure=false
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

The registered static signature is `(JDIFJDIFDDI)D`. The unresolved signature
adds a trailing boolean, `(JDIFJDIFDDIZ)D`, so it cannot reuse the registered
JNI thunk and must compile independently. Instance methods use
`(Ljava/lang/Object;JDIFJDIFDDI)D`.

The exact accepted line is:

```text
FastNativeAbiProbe values normalRegistered=743.75 fastRegistered=1743.75 normalDlsym=2755.75 fastDlsym=3755.75 normalInstance=4743.75 fastInstance=5743.75 calls=63
```

## Regression verification

The same ART build passed:

- Win64 `art` and `dalvikvm` build;
- CriticalNative dual-view and J-1 acceptance, 6/6 each in this run;
- pthread_once stress, 10/10;
- JIT smoke, 10/10;
- JIT matrix, 14/14;
- native Linux `nativeloader`, `art`, `openjdkjvm`, and `dalvikvm` build;
- Linux L-005 imageless Hello using the exact Win64-staged shared multipath
  `boot.jar` bytes.

## Remaining scope

The mixed/high-FP normal/FastNative ABI and unresolved app-JNI coverage are no
longer W-024 blockers. The native-JIT gate remains temporarily because W-024
still includes broader registration/unregistration and instrumentation state
transitions, restoration of the Math/libcore native demotions, cleanup of
diagnostic policy/logging, and real Windows 10 acceptance.
