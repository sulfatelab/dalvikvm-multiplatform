# Direct CriticalNative ABI result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/windows_x64_phase1` RelWithDebInfo.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | verified | verified | 2026-08-02 |
| `windows-x86_64-msvc` | yes | verified | verified | 2026-08-02 |
| `windows-aarch64-msvc` | not yet declared | pending | pending | — |
| `windows-arm64ec-msvc` | not yet declared | pending | pending | — |

The shared C/Java source is accepted only for the two exact target IDs above.
That evidence does not admit either AArch64 target or any other platform,
architecture, or ABI.

## Unified exact-target acceptance (2026-08-02)

The shared shell-free `stage:w003` gate passed on Linux x86-64 GNU and native
Windows Server 2025 x86-64 MSVC. On each target it ran four processes: default
and method-instrumented execution for both library-name and absolute-path
loading. Every process ran the registered and unresolved signature matrix with
exact values; the instrumented pair also proved tracing mode
`0 -> nonzero -> 0`, exact during/after values, and trace-file deletion.

The fresh Linux stage passed 2/2 including the adjacent normal/FastNative gate,
and its immediate repeat was a Ninja no-op. The fresh native Windows build
completed 1,492 actions at 16 jobs, passed product W-003 4/4, then repeated as
a Ninja no-op and passed 4/4 again. Each CriticalNative aggregate records four
successful runs, zero dumps, and no machine absolute paths. Full source/output
scans found no symlink or reparse point. The declaration lists the exact Linux
and Windows IDs; it does not broaden runtime acceptance to AArch64 or ARM64EC.

## Result

The Windows x64 optimizing-compiler direct `@CriticalNative` convention now matches
the Microsoft x64 ABI while preserving the existing Linux/SysV path.

The focused acceptance harness passed all repeated process runs, including
method-tracing transitions:

| Mode | Threshold-zero `FloatProbe` | Registered + unresolved signatures | Method tracing during/after |
|------|-----------------------------|------------------------------------|-----------------------------|
| Default corrected dual view | 3/3 | 3/3 | 3/3 |
| J-1 diagnostic view | 3/3 | 3/3 | 3/3 |

Current exact-target reproductions use 32 jobs on agent01 and 16 jobs on the
16 GiB Windows VM:

```text
python tools/build_art.py test --target-id linux-x86_64-gnu --build-type RelWithDebInfo --stage w003 --parallel 32
python tools/build_art.py test --target-id windows-x86_64-msvc --build-type RelWithDebInfo --stage w003 --parallel 16
```

The retired compatibility harness required both the probe success marker and
`main end exception=0`. Its historical final summary was:

```text
CriticalNative acceptance: dual=6/6 float+signature runs + 3/3 instrumentation; j1=6/6 float+signature runs + 3/3 instrumentation
```

## Root causes

Two independent Windows x64 ABI defects combined in the unresolved `()J` path:

1. `CriticalNativeCallingConventionVisitorX86_64` used the upstream SysV
   layout. A zero-argument call reserved no outgoing bytes even though
   `GetCriticalNativeDirectCallFrameSize("J")` correctly expected the Windows x64
   32-byte shadow area. The dlsym stub consequently placed its
   SaveRefsAndArgs frame 32 bytes too high for stack walking.
2. `art_jni_dlsym_lookup_critical_stub` kept the caller PC live in `r11`, but
   the PE form of `LOAD_RUNTIME_INSTANCE` then used `r11` as scratch. After the
   stack-layout fix exposed this second defect, the stub attempted to return to
   `Runtime*`.

The first mixed-signature unresolved probe then exposed a separate native-load
plumbing defect. Windows x64 `Runtime.nativeLoad` used a direct
`LoadLibraryA` + `JNI_OnLoad` shortcut. That loaded and initialized the DLL but
did not add it to `JavaVMExt::libraries_`, so ART could not resolve exported
`Java_*` names for the app class loader. The Windows x64 missing-native soft stubs
returned zero, which initially looked like another calling-convention failure.

## Implementation

The optimizing visitor now has a narrow Windows-target branch:

- one unified argument ordinal chooses `RCX/RDX/R8/R9` for integer-like values
  or `XMM0..XMM3` for floating values;
- later arguments use 8-byte stack slots after the mandatory 32-byte home
  area;
- the stack offset starts at `kNativeShadowSpaceSize`, so even `()J` reserves
  the home area;
- the existing SysV GPR/FPR sequences are unchanged for Linux.

The original W-024 implementation made the unresolved critical dlsym stub
reload the saved caller PC from its existing frame slot immediately after the
Windows `LOAD_RUNTIME_INSTANCE` expansion. That kept the common macro and
non-Windows assembly unchanged. W-004 later replaced the Windows helper with a
direct same-image data load that does not clobber `r11`, then removed the local
reload as obsolete; the stack-layout fix remains unchanged.

Windows x64 `JVM_NativeLoad` now delegates through `art.dll!ART_LoadNativeLibrary`,
which follows AOSP `OpenjdkJvm.cc` and calls `JavaVMExt::LoadNativeLibrary`.
The host native loader also recognizes drive-qualified, root-qualified, and UNC
Windows paths, so absolute `System.load` paths are not prefixed with `./`.
Linux keeps the existing `/` absolute-path test and loader behavior unchanged.

The public Windows `java.library.path` remains semicolon-separated. Libcore
parses that form, while `BaseDexClassLoader.getLdLibraryPath()` deliberately
normalizes the internal ART search list to colon separators on every host; the
native loader therefore retains its existing `:` split.

JIT dump disassembly confirmed that generated Windows x64 calls reserve the home
area, use unified register ordinals, and place spilled arguments at
`rsp+0x20` and `rsp+0x28`.

## Coverage

`FloatProbe` covers the unresolved first-use dlsym path for a no-argument long
return under `-Xjitthreshold:0`.

`CriticalNativeProbe` initializes the class, registers direct entrypoints from
`JNI_OnLoad`, warms a managed caller, and then executes these signatures from
compiled code:

- `()J`;
- six integer arguments, including two stack arguments;
- six doubles, including two stack arguments;
- mixed `J/D/I/D/J/D` unified ordinals;
- mixed 32-bit integer/float arguments;
- integer, long, float, and double returns.

`CriticalNativeDlsymProbe` executes the same mixed, floating, spilled, and
scalar-return shapes without `RegisterNatives`. Every entrypoint is resolved by
its exported `Java_CriticalNativeDlsymProbe_*` name through ART's library
registry. The harness alternates `System.loadLibrary` and absolute
`System.load`, and supplies a Windows semicolon-separated library path whose
first existing directory is empty, verifying fallback to the second entry.

Each signature iteration also starts non-sampling method tracing after the
initial direct and unresolved calls. The harness verifies tracing mode
`0 -> 1 -> 0`, repeats both registered and unresolved CriticalNative suites
while tracing is active, repeats them after tracing stops, and requires exact
values in every phase in both memory modes. This covers ART's transition to a
debuggable runtime, pre-tracing JIT invalidation, and entry/exit
instrumentation installation around the CriticalNative callers.

The trace file is relative to the Wine run directory, deleted by Java after
tracing, and removed defensively by the harness on process exit. Acceptance
verifies that no trace artifact remains.

The exact accepted value lines are:

```text
CriticalNativeProbe values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeDlsymProbe values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeProbe tracing values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeDlsymProbe tracing values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeProbe postTracing values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeDlsymProbe postTracing values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeProbe tracingMode before=0 during=1 after=0 traceFileDeleted=true
```

The probe DLL uses CMake `WINDOWS_EXPORT_ALL_SYMBOLS` because Android's
`JNIEXPORT` visibility attribute alone does not create a PE export for
`JNI_OnLoad` in this toolchain.

## Legacy interpreter fallback reachability

Linux and Windows x64 consume identical boot.jar dex and annotation bytes, so a
Windows-only boot-native shorty set cannot explain or justify the old expanded
`InterpreterJni` table.

An opt-in build replaced both runtime-started calls to `InterpreterJni` with
fatal tripwires. It passed Windows x64 `-Xint` Math, direct and unresolved
CriticalNative in both memory modes, method tracing, the 7/7 compiled
normal/FastNative matrix, and the real JVMTI forced-interpreter transition.
Clang reported `InterpreterJni` unused when those two calls were disabled,
confirming there was no hidden third call site. The build was then restored to
the product-default tripwire-OFF mode and the final Windows x64 binaries were rebuilt.

The same packaged tripwire matrix subsequently passed on native Windows 10
build 19044, authorizing fallback cleanup. Detailed evidence and the cleanup
sequence are in
`../../../docs/history/windows_x64_w024_interpreter_jni_result.md`.

## Final W-024 status

Native Windows 10 acceptance, native-JIT gate removal, upstream interpreter
fallback restoration, and post-change Linux/Windows x64 regressions are complete.
Math.ceil/floor and the shared ELF/PE registration table are restored; see
`../math-critical/RESULT.md`. Registered
and unresolved CriticalNative calls also pass the JVMTI forced-interpreter
transition in both memory modes; see
`../../../docs/history/windows_x64_phase4_jvmti_force_result.md`.

## Regression verification

The same ART build also passed:

- Windows x64 `art` and `dalvikvm` build;
- unified `managed_native_abi`: default 7/7 mixed/high-FP normal/FastNative checks
  across rebinding and method-tracing phases with no extra target compilation;
- the now-retired Phase-4 JVMTI runner: 3/3 dual-view and 3/3 J-1
  forced-interpreter transitions over registered and unresolved normal,
  FastNative, and CriticalNative calls; current reproduction uses the unified
  `../jvmti-force/run.py` gate and only the supported fail-closed J-2 path;
- the historical Phase-4 JIT smoke: 12/12, including default-silent compile
  diagnostics; its supported controls now run in unified W-025;
- the historical Phase-4 JIT workload matrix: 14/14; canonical Math/IO/Net/
  GC/throw workloads now run in unified W-025;
- native Linux `nativeloader`, `art`, `openjdkjvm`, and `dalvikvm` build;
- Linux L-005 imageless Hello on the same shared multipath `boot.jar` bytes
  staged for Windows x64.

The final repeated matrix initially exposed an unrelated pre-existing
`pthread_once` early-return race in the parent compatibility layer. That race
was fixed and given a separate 32-thread stress test; see
`../pthread-once/RESULT.md`. No
CriticalNative workaround was added for it.

Related files:

- `probe.c`
- `CriticalNativeProbe.java`
- `CriticalNativeDlsymProbe.java`
- `../../../tests/support/w003_managed_gate.py`
- `../../../vendor/art/openjdkjvm/OpenjdkJvm.cc`
- `../../../vendor/art/openjdkjvm/openjdkjvm_memory_windows.cc`
- `../../../win32_open_items.md` W-024
