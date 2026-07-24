# Win64 direct CriticalNative ABI result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/win64_phase1` RelWithDebInfo.

## Result

The Win64 optimizing-compiler direct `@CriticalNative` convention now matches
the Microsoft x64 ABI while preserving the existing Linux/SysV path.

The focused acceptance harness passed all repeated process runs:

| Mode | Threshold-zero `FloatProbe` | Registered + unresolved signature suite |
|------|-----------------------------|-----------------------------------------|
| Default corrected dual view | 5/5 | 5/5 |
| J-1 diagnostic view | 5/5 | 5/5 |

Command:

```sh
REPEATS=5 bash tools/verify/win64_phase4/run_critical_native_probe.sh
```

The harness requires both the probe success marker and
`main end exception=0`. Its final summary was:

```text
CriticalNative acceptance: dual=10/10 float+signature runs; j1=10/10
```

## Root causes

Two independent Win64 ABI defects combined in the unresolved `()J` path:

1. `CriticalNativeCallingConventionVisitorX86_64` used the upstream SysV
   layout. A zero-argument call reserved no outgoing bytes even though
   `GetCriticalNativeDirectCallFrameSize("J")` correctly expected the Win64
   32-byte shadow area. The dlsym stub consequently placed its
   SaveRefsAndArgs frame 32 bytes too high for stack walking.
2. `art_jni_dlsym_lookup_critical_stub` kept the caller PC live in `r11`, but
   the PE form of `LOAD_RUNTIME_INSTANCE` also uses `r11` as scratch. After the
   stack-layout fix exposed this second defect, the stub attempted to return to
   `Runtime*`.

The first mixed-signature unresolved probe then exposed a separate native-load
plumbing defect. Win64 `Runtime.nativeLoad` used a direct
`LoadLibraryA` + `JNI_OnLoad` shortcut. That loaded and initialized the DLL but
did not add it to `JavaVMExt::libraries_`, so ART could not resolve exported
`Java_*` names for the app class loader. The Win64 missing-native soft stubs
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

The unresolved critical dlsym stub reloads the saved caller PC from its existing
frame slot immediately after the Windows `LOAD_RUNTIME_INSTANCE` expansion.
This keeps the common macro and non-Windows assembly unchanged.

Win64 `JVM_NativeLoad` now delegates through `art.dll!ART_LoadNativeLibrary`,
which follows AOSP `OpenjdkJvm.cc` and calls `JavaVMExt::LoadNativeLibrary`.
The host native loader also recognizes drive-qualified, root-qualified, and UNC
Windows paths, so absolute `System.load` paths are not prefixed with `./`.
Linux keeps the existing `/` absolute-path test and loader behavior unchanged.

The public Windows `java.library.path` remains semicolon-separated. Libcore
parses that form, while `BaseDexClassLoader.getLdLibraryPath()` deliberately
normalizes the internal ART search list to colon separators on every host; the
native loader therefore retains its existing `:` split.

JIT dump disassembly confirmed that generated Win64 calls reserve the home
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

The exact accepted value lines are:

```text
CriticalNativeProbe values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
CriticalNativeDlsymProbe values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true
```

The probe DLL uses CMake `WINDOWS_EXPORT_ALL_SYMBOLS` because Android's
`JNIEXPORT` visibility attribute alone does not create a PE export for
`JNI_OnLoad` in this toolchain.

## Remaining scope

- Real Windows 10 acceptance is still required.
- W-024 remains open for registration/unregistration and instrumentation
  state transitions, removal of the native-JIT diagnostic gate, restoration
  of the remaining Math/libcore native demotions, and real-Windows acceptance.

## Regression verification

The same ART build also passed:

- Win64 `art` and `dalvikvm` build;
- `run_native_abi_probe.sh`: gate-closed 0/7 and gate-open 7/7 mixed/high-FP
  normal/FastNative checks;
- `run_jit_smoke.sh`: 10/10;
- `run_jit_matrix.sh`: 14/14;
- native Linux `nativeloader`, `art`, `openjdkjvm`, and `dalvikvm` build;
- Linux L-005 imageless Hello on the same shared multipath `boot.jar` bytes
  staged for Win64.

The final repeated matrix initially exposed an unrelated pre-existing
`pthread_once` early-return race in the parent compatibility layer. That race
was fixed and given a separate 32-thread stress test; see
`RESULT-pthread-once.md`. No CriticalNative workaround was added for it.

Related files:

- `run_critical_native_probe.sh`
- `src/CriticalNativeProbe.java`
- `src/CriticalNativeDlsymProbe.java`
- `critical_native/critical_native_probe.c`
- `../win64_libcore_icu/openjdkjvm_memory_standalone.c`
- `../../../win32_open_items.md` W-024
