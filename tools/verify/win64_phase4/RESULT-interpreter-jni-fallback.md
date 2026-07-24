# Win64 legacy InterpreterJni fallback reachability audit

**Status:** PASS under Wine and native Windows 10; cleanup complete
**Date:** 2026-07-24 17:47:36 CST
**Updated:** 2026-07-24 21:08:00 CST
**Host:** agent01

## Question

The early Win64 port expanded `InterpreterJni` with many PE-specific shorties
and a direct JNI resolver because Phase 2/3 did not yet have working quick/JNI
entrypoints. Those entrypoints, compiled JNI, direct CriticalNative calls,
method-tracing transitions, and JVMTI forced interpretation now work.

This audit asks whether any current runtime-started Win64 path still reaches
the legacy fallback. Wine established the initial result; native Windows 10
then closed the host-reachability gate before cleanup.

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
was not deleted wholesale. Before cleanup, comparison with
`android-16.0.0_r4` showed 599 insertions and 28 deletions, mostly the expanded
shorty and direct-resolution workaround. ART commit `42a03f2ea0` restores the
file byte-for-byte to that upstream tag.

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

For the acceptance experiment, both runtime-started calls were replaced with
distinct `LOG(FATAL)` tripwires through
`MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE=ON`. The definition was source-scoped to
`runtime/interpreter/interpreter.cc`; the package script restored and rebuilt
the shared tree in product mode before exit. The option and generator were
retired after cleanup.

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

The historical `tools/win64/host_package/package_win64_w024_tripwire.sh` built
the opt-in binary, ran the complete Wine matrix, wrote the native Windows
command files, packaged all dependencies, and restored product mode. It was
deleted after the accepted evidence was archived. Native-host execution and
package identity remain recorded in `W024_HOST_CHECKLIST.md`.

The first package review found that the not-yet-run host command files contained
literal `${name}` and `${jar}` fragments: in an unquoted shell heredoc, the
Windows path separator immediately before `$` suppressed parameter expansion.
That defect did not affect the direct Wine harnesses listed above, but it would
have made the native-host package unusable. Generation now uses a doubled
backslash before expanded values, quotes `%~dp0\..` for paths containing spaces,
and rejected any command file that retained an unresolved `${...}` placeholder.

The generated `scripts\run_all_w024.cmd` was then executed through Wine's
`cmd.exe` from a package path containing spaces. All nine command-file cases
returned zero and the driver ended with `OVERALL PASS`, confirming the command
syntax, marker checks, `%~dp0` path handling, and package-relative class/native
paths before native Windows transfer.

## Native Windows 10 acceptance

The same packaged tripwire matrix ran on Windows 10 Enterprise LTSC 2021,
version 2009, build 19044. All nine cases returned `exit=0` and the driver ended
with `OVERALL PASS`:

- Math CriticalNative in dual-view, J-1, and `-Xint` modes;
- registered and unresolved CriticalNative plus method tracing in dual-view
  and J-1 modes;
- compiled normal/FastNative ABI, rebinding, and method tracing in dual-view
  and J-1 modes; and
- JVMTI single-step forced interpretation in dual-view and J-1 modes.

Each normal/FastNative run compiled all seven required targets exactly once
before execution. Each JVMTI run compiled the registered normal and FastNative
targets exactly once and compiled no CriticalNative target, matching ART's
debuggable-runtime rule. All transition values passed, every probe ended with
`main end exception=0`, no tripwire fired, and the recursive dump scan returned
`NO_DMP_FILES`.

The returned build information and 169-entry manifest match the retained
package exactly. The shared `boot.jar` is 3,436,578 bytes with SHA-256
`3cbe9a7f0e4596229c0c5e229e6655463373b1445922b9557286313a28a35a2a`.
Accepted raw evidence and its independent review are stored under
`evidence/w024_host/`.

## Conclusion

The expanded PE `InterpreterJni` shorties and direct resolver were not product
paths under either the Wine or native-Windows matrix. ART commit `42a03f2ea0`
removed them by restoring `interpreter.cc` byte-for-byte to
`android-16.0.0_r4`, including the upstream pre-start-only bridge invariant.
The same commit removed the native-method JIT exclusion so Win64 follows the
common ART native compilation policy by default.

The final Win64 build passed default native ABI 7/7, CriticalNative,
method-tracing, JVMTI, Math, JIT smoke 12/12, JIT matrix 14/14, and all Phase 4
Wine gates. The full Linux runtime rebuilt and passed L-005 shared-boot Hello
and Math `-Xint`/JIT controls. W-011, W-012, and W-024 are closed.

Acceptance records:

- `W024_HOST_CHECKLIST.md`
- `evidence/w024_host/ACCEPTANCE.md`
