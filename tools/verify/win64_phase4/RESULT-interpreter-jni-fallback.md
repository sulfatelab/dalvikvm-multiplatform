# Win64 legacy InterpreterJni fallback reachability audit

**Status:** PASS under Wine; deletion remains gated on Windows 10
**Date:** 2026-07-24 17:47:36 CST
**Updated:** 2026-07-24 18:21:01 CST
**Host:** agent01

## Question

The early Win64 port expanded `InterpreterJni` with many PE-specific shorties
and a direct JNI resolver because Phase 2/3 did not yet have working quick/JNI
entrypoints. Those entrypoints, compiled JNI, direct CriticalNative calls,
method-tracing transitions, and JVMTI forced interpretation now work.

This audit asks whether any current runtime-started Wine path still reaches the
legacy fallback. It does not delete the fallback based only on Wine evidence.

## Shared boot artifact

Linux and Win64 consume the same dex and annotation bytes:

```text
path   build/win64_phase1/run/boot.jar
sha256 3cbe9a7f0e4596229c0c5e229e6655463373b1445922b9557286313a28a35a2a
size   3436578 bytes
entries classes.dex, classes2.dex, java/security/security.properties
```

There is no Windows-specific boot jar that could require a different native
shorty table or different `@FastNative` / `@CriticalNative` metadata. Remaining
platform differences are in native entrypoint selection and ABI handling.

## Source audit

`InterpreterJni` itself is upstream ART testing/image-writing fallback code; it
should not be deleted wholesale. Compared with the `android-16.0.0_r4` version,
the current `runtime/interpreter/interpreter.cc` has 599 insertions and 28
deletions. Most of that delta is the old expanded shorty and direct-resolution
workaround.

There are exactly two calls to `InterpreterJni`:

1. `EnterInterpreterFromInvoke`, retained by upstream for native invocation
   during testing and image writing.
2. `ArtInterpreterToInterpreterBridge`, where the early Win64 port allowed a
   runtime-started native method to enter `InterpreterJni`. Upstream instead
   asserts that this native bridge case occurs only before runtime startup and
   routes it to `UnstartedRuntime::Jni`.

Normal `-Xint` and JVMTI force only Java callers into the interpreter. Native
methods keep their JNI compiler/generated entrypoints, matching Linux ART.

## Opt-in tripwire experiment

Both runtime-started calls can be replaced with distinct `LOG(FATAL)`
tripwires by configuring the Win64 build with
`MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE=ON`. The definition is source-scoped to
`runtime/interpreter/interpreter.cc`; the product default is OFF. The package
script always restores and rebuilds the shared tree in product mode before it
exits.

The Win64 `art` and `dalvikvm` targets built successfully. With both calls
disabled, Clang reported `InterpreterJni` as unused, confirming there was no
third call site.

The tripwire build passed:

| Probe | Result |
|------|--------|
| Math CriticalNative, dual-view threshold zero | 1/1 |
| Math CriticalNative, J-1 threshold zero | 1/1 |
| Math CriticalNative, Win64 `-Xint` | 1/1 |
| Direct and unresolved CriticalNative, dual-view | 2/2 signature/float plus 1/1 tracing |
| Direct and unresolved CriticalNative, J-1 | 2/2 signature/float plus 1/1 tracing |
| Normal/FastNative native gate closed | 0/7 compiled, all values pass |
| Normal/FastNative native gate open | 7/7 compiled, all values pass |
| Normal/FastNative method tracing | 7/7 compiled, all values pass |
| JVMTI forced interpreter, dual-view | 1/1 |
| JVMTI forced interpreter, J-1 | 1/1 |

No tripwire fired. In particular, Win64 `-Xint` and real JVMTI single-step
transitions do not use the legacy native interpreter detour.

The build was then reconfigured with the option OFF, `git diff --check` passed,
and Win64 `art.dll`, `dalvikvm.exe`, and `openjdkjvmti.dll` were rebuilt
successfully. Final product-mode Math controls passed in dual-view, J-1,
Win64 `-Xint`, Linux `-Xint`, and Linux threshold-zero JIT modes.

`tools/win64/host_package/package_win64_w024_tripwire.sh` builds the opt-in
binary, runs the complete Wine matrix, writes the native Windows command files,
packages all dependencies, and restores product mode. Generated command files
are checked for unresolved shell placeholders and use quoted package-relative
paths. Native-host execution follows `W024_HOST_CHECKLIST.md`.

The first package review found that the not-yet-run host command files contained
literal `${name}` and `${jar}` fragments: in an unquoted shell heredoc, the
Windows path separator immediately before `$` suppressed parameter expansion.
That defect did not affect the direct Wine harnesses listed above, but it would
have made the native-host package unusable. Generation now uses a doubled
backslash before expanded values, quotes `%~dp0\..` for paths containing spaces,
and rejects any command file that retains an unresolved `${...}` placeholder.

The generated `scripts\run_all_w024.cmd` was then executed through Wine's
`cmd.exe` from a package path containing spaces. All nine command-file cases
returned zero and the driver ended with `OVERALL PASS`, confirming the command
syntax, marker checks, `%~dp0` path handling, and package-relative class/native
paths before native Windows transfer.

## Conclusion

The expanded PE `InterpreterJni` shorties and direct resolver are not product
paths under the current Wine matrix. They are legacy defensive fallbacks from
the pre-quick/JNI port and are candidates for restoring to the upstream
`android-16.0.0_r4` implementation.

Wine cannot close this item. A real Windows 10 run is still required because PE
loader behavior, unwind metadata, system mitigations, and native scheduling can
differ from Wine. The deletion stage should:

1. repeat the same tripwire matrix on Windows 10;
2. restore `ArtInterpreterToInterpreterBridge` to the upstream pre-start-only
   invariant;
3. reduce `InterpreterJni` and its resolver to upstream behavior, retaining
   only independently demonstrated Windows requirements;
4. rebuild Win64 and Linux, then rerun Math, direct/unresolved CriticalNative,
   normal/FastNative, method tracing, JVMTI, JIT smoke, and the Linux shared-boot
   gate;
5. remove W-011/W-012 only after those checks pass.

Native Windows instructions:

- `W024_HOST_CHECKLIST.md`
