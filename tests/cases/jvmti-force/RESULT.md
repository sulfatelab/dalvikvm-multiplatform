# JVMTI force-interpreter result

The unified JNI/JVMTI gate exercises thread-scoped forced-interpreter
transitions through ART's separately loaded `openjdkjvmti` runtime plugin. Its
current selector is exactly `windows-x86_64-msvc`; this result does not claim
Windows x86, ARMv7, AArch64, ARM64EC, or Linux applicability.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 x86-64 | 2026-08-01 |

The Linux-hosted Windows graph generated 33 modules from 260 Blueprint files,
built the agent, managed JAR, `art.dll`, and `openjdkjvmti.dll`, and passed the
W-004 structural reviewer. Its identical repeat was a Ninja no-op.

On the authoritative Windows Server 2025 host, the unified `stage:w004` gate
passed 6/6 and its final identical repeat reported `ninja: no work to do.` The
JVMTI runner completed three independent processes. Every process preserved
all six expected native values before, during, and after the forced-interpreter
window; recorded positive single-step transitions; compiled each normal and
FastNative target exactly once; compiled no CriticalNative target in the
debuggable runtime; exited zero; and reached `main end exception=0`. The
aggregate record reports three completed runs and zero dumps.

Windows keeps `openjdkjvmti.dll` as a DSO, equal to Linux topology. A generated
regular-file PE header overlay marks the 23 source-level ART API declarations
needed by the plugin; two template instantiations make that 24 C++ exports, and
the two inline allocation paths add explicit `mspace_malloc` and
`mspace_usable_size` exports. This adds exactly 26 entries without restoring
`WINDOWS_EXPORT_ALL_SYMBOLS` on `art.dll`; the accepted RelWithDebInfo DLL has
1,964 exports. The reviewer also verifies 563 quick, 10 nterp, and one JNI
direct `Runtime::instance_` relocations, plus explicit Ninja dependencies on
the shared x86-64 assembly support inputs.

The accepted native artifact hashes were:

- `art.dll`: `fd5693a1e6406627840419b588a16028c80aefa7ad2be2f25fc526329eaecf23`
- `openjdkjvmti.dll`: `c0f925c65784621118a7578fae6f46146170800a1129c183badbbb8a38fb28b0`
- `libjvmtiforceprobe.dll`: `5b253786adde0c099e552925c17c13684538bf6dabcebf12f4c992a037bb3f9e`
- `jvmtiforceprobe.jar`: `8dde420468b05b5502748c3bd35642a56b949c5cb317ea0562f89c313b8db0d8`

All 24 JSON results in the native output were free of machine absolute paths;
the refreshed source tree and build tree contained zero reparse points and no
dump files. No binary artifact is retained in VCS. After this acceptance, the
standalone JVMTI CMake graph and Bash/Wine runner were removed; retained
aggregate packages acquire these inputs from the configured unified build.
