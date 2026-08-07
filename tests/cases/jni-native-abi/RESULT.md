# Compiled normal/FastNative ABI result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/windows_x64_phase1` RelWithDebInfo.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | verified | verified | 2026-08-02 |
| `linux-aarch64-gnu` | yes | verified | verified under explicit QEMU user mode | 2026-08-02 |
| `windows-x86_64-msvc` | yes | verified | verified | 2026-08-02 |
| `windows-aarch64-msvc` | not yet declared | pending | pending | — |
| `windows-arm64ec-msvc` | not yet declared | pending | pending | — |

The scalar C/JNI and Java sources are accepted only for the three exact target
IDs above. That evidence does not admit Windows AArch64, ARM64EC, or any other
platform, architecture, or ABI.

## Unified exact-target acceptance (2026-08-02)

The shared shell-free `stage:w003` gate passed on Linux x86-64 GNU and native
Windows Server 2025 x86-64 MSVC in four processes per target: default and
method-instrumented execution, each repeated twice. Every process completed the
initial, unregister, and re-register value phases. The instrumented pair also
completed the tracing and post-tracing phases with mode `0 -> nonzero -> 0`
and deleted its trace file. Windows additionally emitted exactly seven
successful target-method compile records per process; that diagnostic marker
format remains Windows-specific and is not claimed for Linux.

The fresh Linux stage passed 2/2 including the adjacent CriticalNative gate,
and its immediate repeat was a Ninja no-op. The fresh native Windows build
completed 1,492 actions at 16 jobs, passed product W-003 4/4, then repeated as
a Ninja no-op and passed 4/4 again. Each normal/FastNative aggregate records
four successful runs, zero dumps, and no machine absolute paths. Full
source/output scans found no symlink or reparse point. The declaration lists
only the exact x86-64 Linux and Windows IDs at this checkpoint; it did not
infer either AArch64 target or ARM64EC.

## Linux AArch64 acceptance (2026-08-02)

The normal/FastNative declaration was expanded independently after the
adjacent CriticalNative admission. Its C and Java sources contain no assembly
or x86 register contract, the Linux path does not require Windows-only compile
records, and the shell-free runner now receives the same explicit QEMU/root
arguments as the other admitted AArch64 gates.

A fresh configuration audited 2,112 compile commands, 2,196 Ninja commands,
and 32 product links. The 1,519-edge W-003 build produced the AArch64 probe DSO
and managed JAR. Four QEMU processes ran default and method-instrumented modes
twice each. Every process returned the exact mixed integer/floating values for
registered, unresolved, static, and instance normal/FastNative methods across
the initial, unregister/dlsym, and alternate re-registration phases. Both
instrumented runs additionally proved tracing mode `0 -> nonzero -> 0`, exact
during/post-tracing values, and trace-file deletion.

The normal/FastNative gate passed in 182.21 seconds. The complete two-gate
W-003 stage passed 2/2 in 369.84 seconds and repeated 2/2 in 371.60 seconds
after `ninja: no work to do`; the repeated normal/FastNative gate took 183.37
seconds. Its four aggregate records have exit zero, no missing markers, no
dumps, the normalized QEMU fingerprint, and no machine path. Source and output
scans found no filesystem links.

The accepted artifact SHA-256 values were:

- `libnativeabiprobe.so`:
  `c11c20e9d01da1a0ec23c47b68870a33e2315b2b840296b49d16a53be9fc2861`
- `fastnativeabiprobe.jar`:
  `c8bee80f432a14ffb604b40fe856ff01d0b17743c42a1b9e8b43db32e4cfbf46`

A fresh native Linux x86-64 tree audited 2,088 compile commands, 2,172 Ninja
commands, and 32 product links, built all 1,491 W-003 edges, and passed both
JNI gates 2/2 in 2.57 seconds. Its immediate no-op repeat passed 2/2 in 2.53
seconds. This admission covers the Linux AArch64 normal/FastNative mixed-call,
rebinding, JIT, and tracing contract only; it does not infer Windows AArch64,
ARM64EC, another JNI probe, or a native AArch64 build host.

## Result

The focused compiled-JNI acceptance gate now passes the mixed/high-FP matrix:

| Mode | Result |
|------|--------|
| Windows default native compilation | PASS: exit 0, three exact binding phases, 7/7 targets and exactly 7 compile records |
| Windows native compilation plus method tracing | PASS: tracing mode `0 -> 1 -> 0`, exact during/after values, exactly 7 target compile records |
| Linux default and method-traced execution | PASS: exact binding/tracing values in four processes; Windows-specific compile-record markers are not asserted |

Current exact-target reproductions use 32 jobs on agent01 and 16 jobs on the
16 GiB Windows VM:

```text
python tools/build_art.py test --target-id linux-x86_64-gnu --build-type RelWithDebInfo --stage w003 --parallel 32
python tools/build_art.py test --target-id linux-aarch64-gnu --build-type RelWithDebInfo --stage w003 --parallel 32
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w003 --parallel 16
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
The Math/libcore native demotion and maintained two-mode gate are recorded in
`../math-critical/RESULT.md`.
CriticalNative method tracing is covered by the adjacent
`../jni-critical-native/RESULT.md`; JVMTI single-step/deoptimization coverage
is recorded in
`../../../docs/evidence/windows_x64_phase4_jvmti_force_result.md`.

## Related files

- `probe.c`
- `FastNativeAbiProbe.java`
- `../../../tests/support/w003_managed_gate.py`
- `../../../win32_open_items.md` W-024
