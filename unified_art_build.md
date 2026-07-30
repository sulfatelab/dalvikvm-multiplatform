# Unified ART build design

Status: proposed design; analysis only

Date: 2026-07-30

This document defines the intended replacement for the repository's split
Linux and Windows ART build paths. It does not claim that the design is already
implemented.

## Decision

ART should have one product build pipeline:

1. one `bp2cmake` graph evaluator and emitter;
2. one target-aware Python overlay factory;
3. one maintained CMake product entry point and one shared set of CMake
   modules;
4. one Python command-line frontend for generation, configuration, build,
   test, staging, and reproducibility checks;
5. CMake's single-configuration `Ninja` generator on Linux and Windows build
   hosts, for native and cross targets; and
6. the LLVM Clang GNU-style driver plus LLD for every compile and link.

The pipeline also has no project-authored shell logic or POSIX-environment
prerequisite. Source-control aliases are normalized to regular files, and all
compiler/tool inputs and product outputs are symlink-free on both build hosts.
Python, CMake, Ninja, and native host LLVM/JDK executables are the complete
host-tool contract. Linux is not allowed to hide a dependency that a stock
Windows 10 ARM64 host cannot satisfy.

The same logical CMake targets must be produced for Linux and Windows. Platform
differences are limited to source selection, ABI definitions, system libraries,
exports, target SDK/sysroot, and the platform-correct implementation of a
common security/property requirement.

```text
Android.bp + target profile + one Python overlay
                        |
                        v
                    bp2cmake
                        |
                        v
 out/<build-host>-to-<target>/<build-type>/generated/art_graph.cmake
                        |
                        v
              CMake -G Ninja -> build.ninja
                        |
                        v
         clang/clang++ -fuse-ld=lld -> target artifacts
```

In particular, `art-compiler` is a shared library on both targets:

| Target | Required runtime artifact | Link-time artifact |
|---|---|---|
| Linux x86-64 | `libart-compiler.so` | the DSO itself |
| Windows x86-64 | `art-compiler.dll` | `art-compiler.lib` import library |

Windows must not silently substitute a static `art-compiler` when DLL exports
are incomplete. Missing exports are a port defect and must fail the build or an
ABI validation gate.

The following are deliberately unsupported:

- GCC or G++ as a compiler driver;
- MinGW, including `clang-mingw` toolchains and MinGW target triples/runtimes;
- `cl.exe`;
- `clang-cl.exe` and Clang's CL-style frontend;
- Makefile, NMake, Visual Studio, and Ninja Multi-Config CMake generators;
- Bash, `sh`, `ash`, WSL, MSYS2, Cygwin, or a POSIX utility layer as a build
  prerequisite;
- project build logic in `.sh`, `.bat`, `.cmd`, or PowerShell scripts;
- operating-system-resolved symbolic links, junctions, or other path aliases
  as compiler/tool inputs or product outputs; and
- invoking `ld.lld` or `lld-link` directly as a separate product link path.

LLD remains the linker. On a Windows target, plain `clang`/`clang++` may select
`lld-link` internally for PE/COFF, but CMake link rules must invoke the Clang
driver with GNU-style options and `-fuse-ld=lld`.

## Goals and non-goals

### Goals

- Make a build mean the same thing regardless of whether CMake and Clang run
  on Linux or Windows.
- Make the target OS/ABI explicit and independent of the build host OS.
- Derive source/dependency graphs from `Android.bp`, then apply all intentional
  port policy through one reviewed Python overlay.
- Generate build-tree CMake deterministically; do not maintain generated
  product CMake snapshots by hand.
- Use CMake target properties rather than global flag strings wherever CMake
  has a semantic representation.
- Build the same DSO topology on Linux and Windows, including
  `art-compiler.dll`.
- Keep target code generation ABI-correct during cross compilation.
- Reject stale toolchain caches and accidental host-library discovery.
- Run directly on Windows 10 ARM64 with native Windows host tools and no WSL,
  Cygwin, POSIX shell, or Make installation.
- Use no symlink or Windows junction/reparse-point dependency on Linux or
  Windows.
- Make the product graph smaller and easier to audit without deleting useful
  Windows verification probes.

### Non-goals

- Translating every Soong feature or every module in the AOSP tree.
- Supporting Android/bionic as a target in this pipeline.
- Validating 32-bit or non-x86-64 targets in the initial migration. The design
  is multi-target from the start, but the first migration gates remain Linux
  x86-64 and Windows x86-64.
- Making Linux and PE/COFF command lines byte-for-byte identical.
- Replacing libc, the platform SDK, or all platform compatibility code.
- Completing Windows AOT/OAT generation or loading merely by producing
  `art-compiler.dll`.
- Redesigning ART's runtime/compiler ownership during the first unification
  pass.

## Build host and target are separate dimensions

The current tree sometimes uses "host" to mean both the machine running the
tools and an AOSP `host_supported` target. The new system must use unambiguous
terms:

- **build host**: the OS on which Python, CMake, Ninja, and Clang execute;
- **target**: the OS, architecture, ABI, SDK/sysroot, and runtime for the
  produced ART binaries; and
- **AOSP build kind**: this project selects ART's AOSP host variant even when
  it is cross-compiled. This is not the build-host OS.

The build-host OS must never choose `target.linux` or `target.windows` branches
from `Android.bp`. Only the target profile may do that.

### Required host/target matrix

| Build host | Target | Mode | Required target environment |
|---|---|---|---|
| Linux x86-64 | Linux x86-64 | native | explicit or validated native Linux SDK/sysroot |
| Linux x86-64 | Windows x86-64 | OS/ABI cross | Windows SDK/UCRT, MSVC-ABI libraries, libc++/compiler-rt as selected by the profile |
| Windows 10 ARM64 | Windows x86-64 | architecture cross | the same target ABI contract and an explicit Windows SDK |
| Windows 10 ARM64 | Linux x86-64 | OS/architecture cross | an explicit Linux sysroot; never libraries found from the Windows host |

All four cells use the same Python frontend, `bp2cmake`, overlay factory,
CMake source tree, target names, and Ninja build flow. A cell may be enabled in
CI only when its target SDK/sysroot is provisioned. In particular,
Windows-to-Linux must fail at configuration if no Linux sysroot was supplied;
falling back to host headers or libraries is forbidden.

Windows x86-64 can remain a compatible build-host variant, but it must not be
the only Windows CI coverage. Windows 10 ARM64 is the portability baseline:
Python, CMake, Ninja, Clang/LLVM, and the JDK run as native Windows ARM64 host
programs while Clang and javac produce the requested target artifacts. The
build never executes x86-64 target binaries during configure or generation.

## One maintained CMake implementation, one configured instance per target

All target families use the same maintained [`native/CMakeLists.txt`](native/CMakeLists.txt),
the same CMake modules, the same `bp2cmake` implementation, and the same Python
overlay factory. They do **not** share one configured CMake cache or one
universal generated module graph.

For each exact target, the frontend creates a separate:

- resolved target profile;
- target-selected `art_graph.cmake`;
- CMake binary directory and `CMakeCache.txt`;
- `build.ninja` graph; and
- generated-source, artifact, and staging tree.

Conceptually:

```text
one maintained CMake implementation
              |
              +-- linux-x86_64 profile
              |     -> out/<host>-to-linux-x86_64/<type>/...
              +-- linux-aarch64 profile
              |     -> out/<host>-to-linux-aarch64/<type>/...
              +-- windows-x86_64 profile
              |     -> out/<host>-to-windows-x86_64/<type>/...
              +-- future profiles
                    -> one isolated configured instance each
```

The compiler target triple, pointer size, ABI, object format, SDK/sysroot,
selected assembly, and many compiler checks are fixed when CMake enables a
language. Reusing a binary directory for another target is therefore invalid,
even when only the CPU changes. A build directory has exactly one target
identity for its entire lifetime.

### What `bp2cmake` generates

`bp2cmake` plus the Python overlay should generate one **target-resolved**
`art_graph.cmake` per exact target. It should not generate one giant file that
contains the source lists for every target behind CMake `if()` branches.

Uniformity means that all graphs are produced by one evaluator, policy schema,
overlay composition model, and emitter, with the same logical CMake target
names and validated topology. It does not mean that Linux ARM64 and Windows
x86-64 graphs must be byte-for-byte identical. Their selected source files,
defines, system imports, assembly, exports, and security mappings necessarily
differ. Conversely, generation of the **same** target profile on different
build hosts must yield equivalent graph manifests.

The frontend should not expose a bag of independently editable `-D` switches
such as OS, CPU, bitness, ABI, triple, and object format. Those switches can
contradict one another. It accepts one canonical target ID, resolves and
validates the complete profile in Python, then gives CMake only the resolved
inputs, for example:

```text
cmake -S native -B out/windows-aarch64-to-linux-riscv64/RelWithDebInfo \
  -G Ninja \
  --toolchain native/cmake/toolchains/LLVM.cmake \
  -DART_PROFILE_FILE:FILEPATH=<absolute-path>/target_profile.cmake \
  -DART_GRAPH_FILE:FILEPATH=<absolute-path>/art_graph.cmake
```

The public frontend, rather than a user assembling that command, owns these
arguments. The same resolved profile is serialized as JSON for `bp2cmake` and
as a generated CMake data projection for the common LLVM toolchain and product
entry point. The CMake projection contains portable target semantics only; it
does not contain machine installation paths.

Generated `.cmake` files must remain simple and relocatable. In particular,
`art_graph.cmake` contains resolved target declarations, stable CMake root
variables, logical target names, and their relationships. It does not contain:

- absolute source, output, LLVM, JDK, SDK, sysroot, or dependency paths;
- build-host conditionals;
- target branches that Python has already resolved;
- shell commands or platform-specific path spelling; or
- repeated policy that belongs in a maintained CMake interface target.

The generated-file surface should be deliberately narrow:

- `target_profile.cmake` consists only of validated `set(ART_TARGET_... ...)`
  data with no filesystem bindings;
- `art_graph.cmake` uses declarative target/source/include/definition/option
  and logical dependency commands, plus calls to a small reviewed set of
  project codegen helpers; and
- generated files do not call `project()`, discover a toolchain or package,
  run `find_package()`, `execute_process()`, or `file(GLOB)`, define new
  functions/macros, perform staging/install work, or implement control-flow
  trees.

A representative emitted fragment is:

```cmake
add_library(art-compiler SHARED
  "${MDVM_SOURCE_ROOT}/art/compiler/driver/compiler_driver.cc"
  "${MDVM_GENSRC_ROOT}/art/asm/mterp/mterp_x86_64.S"
)
target_link_libraries(art-compiler PRIVATE art art-disassembler)
```

Machine-specific absolute roots are unavoidable when tools actually open an
SDK or source tree, but they are runtime bindings, not graph content. The
Python frontend passes them to CMake through a small internal cache interface;
they may appear in `CMakeCache.txt` and the build manifest, but never in an
emitted `.cmake` file. The generated files are therefore relocatable and the
same-target graph can be compared across build hosts.

### How CMake distinguishes targets

CMake has `if()`, `elseif()`, `else()`, functions, generator expressions, and
conditional `include()` support. The unified build uses them for small,
declared policy composition, not for target detection or duplicate module
graphs. A simplified shape is:

```cmake
include("${ART_PROFILE_FILE}")

if(ART_TARGET_OS STREQUAL "linux")
  include(PlatformLinux)
elseif(ART_TARGET_OS STREQUAL "windows")
  include(PlatformWindows)
elseif(ART_TARGET_RUNTIME STREQUAL "wasi")
  include(PlatformWasi)
else()
  message(FATAL_ERROR "Unsupported ART target: ${ART_TARGET_ID}")
endif()

include("${ART_GRAPH_FILE}")
```

The generated profile defines immutable, mutually validated values such as
`ART_TARGET_ID`, `ART_TARGET_OS`, `ART_TARGET_CPU_ARCH`, `ART_TARGET_ABI`, and
`ART_TARGET_OBJECT_FORMAT`. `CMAKE_SYSTEM_NAME` and
`CMAKE_SYSTEM_PROCESSOR` must agree with them, but are not sufficiently precise
to be the registry key. `CMAKE_HOST_SYSTEM_NAME` describes the build host;
`CMAKE_SYSTEM_NAME` describes the target. Similarly, CMake's `WIN32` condition
describes a Windows **target**, while `CMAKE_HOST_WIN32` describes a Windows
build host. Product source selection must never use the latter.

Architecture-specific inputs should normally be selected by the Python
overlay before graph emission. CMake conditions remain appropriate for
platform linker-property mapping, artifact suffix behavior, imported target
SDK libraries, and a small number of CMake-native platform semantics. This
keeps `native/CMakeLists.txt` from becoming a nested OS-by-architecture-by-ABI
decision tree.

## Target identity and registry

A target cannot be represented safely by one architecture string. The
resolved target schema should include at least:

```text
target_id
os_or_runtime
cpu_arch
abi
object_format
pointer_bits
endianness
target_triple
cmake_system_name
cmake_system_processor
capabilities
support_status
```

For example, ARM64EC is a Windows ABI/interoperability model over the ARM64
architecture, not a new CPU architecture. Likewise, `wasm32` only describes a
WebAssembly address width; it does not say whether the runtime contract is
WASI, a browser, or a custom embedding. A WebAssembly target ID must include
that runtime ABI.

Use canonical target IDs internally and accept user-friendly aliases only at
the frontend. Suggested canonical IDs are:

| Canonical target ID | CPU | ABI/runtime | Object format | Initial status |
|---|---|---|---|---|
| `linux-x86_64` | x86-64 | GNU/Linux profile | ELF64 | `supported` |
| `linux-aarch64` | ARM64 | GNU/Linux profile | ELF64 | `planned` |
| `linux-x86` | x86 | GNU/Linux profile | ELF32 | `planned` |
| `linux-armv7` | ARMv7 | GNU EABI hard-float fixed by this profile | ELF32 | `planned` |
| `linux-riscv64` | RISC-V 64 | GNU/Linux profile | ELF64 | `planned` |
| `windows-x86_64` | x86-64 | MSVC ABI | PE32+ | `experimental` |
| `windows-aarch64` | ARM64 | Windows ARM64 ABI | PE32+ | `planned` |
| `windows-arm64ec` | ARM64 | ARM64EC ABI | PE32+ | `planned` |
| `windows-x86` | x86 | Windows x86 ABI | PE32 | `planned` placeholder |
| `wasm32-wasi` | wasm32 | WASI | WebAssembly | `impossible_under_current_art_contract` |
| `wasm64-wasi` | wasm64 | WASI/Memory64 | WebAssembly | `impossible_under_current_art_contract` |

Windows x86-64 is the first parity target and is promoted to `supported` only
after the unified graph, DLL topology, and runtime acceptance gates pass.

Aliases such as `linux_x64`, `linux_arm64`, `windows_x64`, and
`wasm_wasm32` may be accepted, but the manifest and output path always record
the canonical ID. An alias cannot add an alternative target meaning. If a
Linux ARM soft-float ABI is ever required, it receives a distinct canonical
profile rather than changing the meaning of `linux-armv7`.

Support state is machine-readable:

- `supported`: CI must configure, compile, link, inspect, and run the
  applicable product gates;
- `experimental`: generation/configuration may work, but it is not yet a
  product contract;
- `planned`: the schema entry exists, but configuration fails with a clear
  missing capability/toolchain/port reason; and
- `impossible_under_current_art_contract`: retained for architectural
  planning, but rejected before graph generation until ART's required runtime
  contracts are redesigned.

WASM profiles initially belong to the last category. Current ART assumes
threads, native virtual memory and executable mappings/JIT, signal/fault
handling, target assembly, dynamic loading, and native DSO semantics. The
overlay must not quietly turn `SHARED` targets into static libraries or disable
these contracts until something compiles. It should fail capability validation
and list the unresolved runtime contracts. A future WASI port can change the
status only after those semantics and the intended AOT/interpreter/JIT model
are explicitly designed.

## Current-state analysis

### Linux product path

The Linux path is the closest existing model for the desired architecture:

- [`native/generate.sh`](native/generate.sh) runs `bp2cmake` over five root
  modules and writes [`native/generated/dalvikvm.cmake`](native/generated/dalvikvm.cmake).
- [`native/CMakeLists.txt`](native/CMakeLists.txt) is the handwritten product
  shell. It supplies code generation, imported libraries, compatibility flags,
  staging, and the generated graph.
- The current generated closure contains 33 modules and already emits
  `art-compiler` as `SHARED`.
- A fresh Linux conversion currently matches the checked-in generated file.

There is still drift inside this path. Comments in `native/generate.sh` and
`native/CMakeLists.txt` describe an 18-target graph even though the generated
closure contains 33 modules. Configure-time `execute_process()` code generation
is split from generated `add_custom_command()` generation. Host libraries such
as zlib, lz4, cap, and expat are discovered from the machine, which is unsafe
when this entry point is reused for a cross target.

### Windows product and verification paths

Windows is not generated through one reproducible product entry point:

- [`tools/verify/windows_x64_phase0/generate.sh`](tools/verify/windows_x64_phase0/generate.sh)
  proves that `bp2cmake --os windows` and the Windows overlay can generate a
  foundational graph.
- [`tools/verify/windows_x64_phase1/phase1.cmake`](tools/verify/windows_x64_phase1/phase1.cmake)
  contains 17 generated modules, but there is no Phase-1 generator script that
  reproduces it.
- [`tools/verify/windows_x64_phase1/CMakeLists.txt`](tools/verify/windows_x64_phase1/CMakeLists.txt)
  mixes the product graph, target environment, compatibility injections,
  staging, and 23 verification/probe executables in one large file.
- The Phase-1 graph makes `artbase`, `dexfile`, `profile`, `elffile`, and the
  compiler component static, folds compiler objects into `art.dll`, and does
  not emit a standalone `art-compiler.dll`.
- [`tools/verify/windows_x64_libcore_icu/sources.cmake`](tools/verify/windows_x64_libcore_icu/sources.cmake)
  claims to be automatically extracted, but the repository contains no
  matching extractor. Its CMake file imports Phase-1 artifacts rather than
  consuming targets from one graph.

The present Windows linker command is nevertheless useful evidence: plain
`clang++ --target=x86_64-pc-windows-msvc ... -shared -fuse-ld=lld` already
links PE DLLs. The unified design should preserve this GNU-driver shape and
remove the surrounding special build path. The currently used external
`windows_x64-dev-env` toolchain already combines plain Clang, an explicit MSVC
ABI target, LLD, xwin-provisioned SDK files, libc++, and compiler-rt; the design
should make that contract reproducible rather than relying on one workstation
path.

The checked Windows build cache also demonstrates why build directories need
fingerprints. It records `Release`/`-O3`, while current reproduction text asks
for `RelWithDebInfo`/`-O2`, and contains paths from both the older
`win64-dev-env` and newer `windows_x64-dev-env`. A successful incremental link
from such a directory is not evidence of a reproducible configuration.

### Converter and overlay split

The converter already has the right three conceptual layers: parse/evaluate,
apply port policy, then emit CMake. Its configuration supports Linux and
Windows target selects, but the policy is currently divided between
[`overlay/port_policy.py`](overlay/port_policy.py),
[`overlay/port_policy_windows.py`](overlay/port_policy_windows.py), and the two
handwritten CMake entry points.

This causes equivalent decisions to drift. For example, the Linux overlay
forces `libart-compiler` to a shared library for `dex2oat`, while the Windows
overlay forces it static and relies on absorption into `libart`. The converter
also hard-codes directory exclusions for tests, fuzzers, benchmarks, and
samples in its CLI implementation. Those exclusions are product profile
policy, not parser behavior.

### Current architecture assumptions

The vendored ART source has architecture implementations under
`runtime/arch`, compiler quick-JNI/utilities, and related compiler trees for
`arm`, `arm64`, `riscv64`, `x86`, and `x86_64`. Its mterp inputs use
`armng`, `arm64ng`, `x86ng`, and `x86_64ng`, but RISC-V uses `riscv64`
without the `ng` suffix. That source availability is evidence for the target
registry, not proof that this repository can build all five architectures.

The current conversion path remains materially x86-64-specific:

- [`tools/bp2cmake/bp2cmake/config.py`](tools/bp2cmake/bp2cmake/config.py)
  explicitly models x86-64, x86, ARM64, and ARM codegen sibling selection;
  other architecture values only fall through generic paths and are not a
  validated profile;
- [`tools/bp2cmake/bp2cmake/codegen.py`](tools/bp2cmake/bp2cmake/codegen.py)
  constructs the mterp directory as `<arch>ng`, which is wrong for RISC-V;
- the same code generator hard-codes `x86_64-pc-windows-msvc` and
  `mdvm_windows_x64_prelude.h` for target-layout assembly generation;
- both current overlays inject `mterp_x86_64.S` rather than a target-selected
  generated source;
- Linux BoringSSL policy injects a fixed set of x86-64 assembly files; and
- the Windows policy, compatibility prelude, verification graphs, and ABI
  checks are Windows x86-64-specific.

These are migration work items. A planned target must not be labeled
`supported` merely because `Config(arch=...)` accepts its spelling or an ART
source directory exists. Profile admission should check all required source,
codegen, dependency, ABI, linker, and runtime capabilities before CMake graph
generation.

### Code generation and Java staging

Python generation for aconfig, `operator_out`, mterp, and `asm_defines` is
already shared. It correctly recognizes that `asm_defines` is target-layout
sensitive: Windows and Linux produce different `Runtime` offsets. The Windows
entry point, however, reconstructs target include paths and definitions
manually.

The boot-jar scripts are not yet suitable as a common product stage:

- `tools/bootjar/build_windows_x64.sh` ignores `build.sh` failure with
  `|| true`;
- `build.sh` and `dex.sh` do not use fail-fast shell behavior; and
- every invocation reuses `/tmp/bootbuild`, allowing cross-build contamination.

Boot-jar work does not need to be folded into `bp2cmake`, but it should be an
ordinary, fail-fast stage owned by the same frontend and build directory.
Likewise, the Bash-only Linux generator and boot-jar entry points cannot be the
portable frontend for a native Windows build host.

### Symlink audit

The current checkout contains 303 filesystem symlinks:

- 279 under `vendor/art`, including 277 test aliases;
- 14 under `vendor/logging`;
- four under other `vendor/external` trees;
- one each under `vendor/libbase`, `vendor/libprocinfo`, and
  `vendor/unwinding`;
- the project-owned `vendor/fmtlib -> external/fmtlib` compatibility alias;
- two project-owned `compat/openjdk_inc/.../fdlibm` directory aliases.

Nine are already broken because formatting metadata points at the absent AOSP
`build/soong` tree. None of the repository links is absolute or escapes the
repository. The current `build/` and staging trees contain no symlinks.

Most vendored links are outside the product closure, but three root-project
links expose real portability defects. Legacy Windows generated CMake uses
`vendor/fmtlib`; the current Linux graph correctly uses
`vendor/external/fmtlib` directly. `native/CMakeLists.txt` still consumes the
fdlibm compatibility link farm to satisfy libopenjdk's relative include.

The current external `windows_x64-dev-env` path is also unsuitable: it contains
11 absolute symlinks back to the older `win64-dev-env`, including its SDK,
libraries, CRT, scripts, and CMake toolchain. The normal Linux
`/usr/bin/clang`, `/usr/bin/clang++`, and `/usr/bin/python3` names are symlink
aliases as well. A unified build must use real, canonical files/directories and
cannot rely on any of these aliases after tool discovery.

### POSIX-host assumptions

The current product path assumes a Unix userland in several places:

- graph generation is launched by `native/generate.sh` and Windows Phase 0 has
  another Bash generator;
- source provisioning is launched by `tools/vendor-sync.sh`;
- boot-jar and staging flows use Bash arrays, `source`, pipelines, shell
  redirection, `/tmp`, `rm`, `cp`, `find`, `grep`, `stat`, `strings`, and
  `timeout`;
- documentation uses `$(nproc)` and environment-activation scripts; and
- generated `operator_out` CMake commands use shell `>` redirection instead of
  passing an output path to a process: 52 commands in the current Linux graph,
  45 in Windows Phase 1, and three in Windows Phase 0.

These are hard Windows 10 ARM64 blockers without WSL. Cygwin is not a fallback;
besides being outside the desired toolchain, an adequate Cygwin environment is
not available for this ARM64 baseline.

The reusable Python codegen layer is already mostly suitable: its `_run()`
helper uses an argument vector with `subprocess.run`, captures stdout itself,
and the mterp/header generators are Python. The unified emitter should route
all generation through that layer instead of reproducing shell syntax in
CMake.

## Required invariants

The unified implementation should enforce these conditions rather than merely
document them:

1. `CMAKE_GENERATOR` is exactly `Ninja`.
2. `CMAKE_C_COMPILER_ID` and `CMAKE_CXX_COMPILER_ID` are Clang, and the
   frontend variant is GNU-style rather than MSVC-style.
3. compiler executable basenames are `clang`/`clang++` or
   `clang.exe`/`clang++.exe`; aliases resolving to GCC, Clang-CL, or MinGW are
   rejected after canonical-path and `--version` inspection.
4. every C, C++, assembly, executable-link, and DSO-link rule is launched
   through the configured Clang driver.
5. every link selects LLD with `-fuse-ld=lld`; an internal `lld-link` process
   for PE is acceptable, but a direct `lld-link` CMake rule is not.
6. target triple, target OS, CMake system name, sysroot/SDK, runtime libraries,
   and `bp2cmake` target profile agree.
7. CMake never searches build-host include or library paths for a cross target.
8. generated CMake and generated sources live under the configured target's
   binary tree.
9. `RelWithDebInfo` with `-O2` is the default product configuration. Other
   product build types are rejected unless the frontend explicitly enables a
   developer configuration such as `Debug`.
10. no configure-time or generation-time check executes a target binary while
    cross-compiling.
11. the logical shared/static target topology is identical between Linux and
    Windows unless a reviewed manifest records a platform exception.
12. `art-compiler` is always a CMake `SHARED` target for every admitted native
    target with DSO capability. A target without that contract is rejected,
    not converted to a static compiler library.
13. no project-authored build step invokes or requires Bash, `sh`, `ash`, WSL,
    MSYS2, Cygwin, Make, or a POSIX command-line utility.
14. every project-owned Python subprocess is started with an argument vector
    and shell execution disabled; no emitted CMake command payload contains
    shell redirection, a pipe, command substitution, or command chaining.
15. Git symlink entries may exist in a source checkout as real links or
    `core.symlinks=false` plain files, but a manifest-driven source normalizer
    materializes any required alias as regular files before graph emission. No
    compiler/tool input, SDK/sysroot, binary-directory, generated, staging, or
    packaged-artifact path depends on an OS-resolved symlink, junction, or
    project-controlled reparse point.
16. Windows 10 ARM64 uses native ARM64 host Python, CMake, Ninja, LLVM, and JDK
    executables. Cross-target binaries are never host tools.
17. one CMake binary directory is permanently bound to one canonical target
    ID, target triple, ABI, object format, SDK/sysroot identity, and build type.
18. Python emits a separate, fully target-resolved `art_graph.cmake` for each
    exact target; a generated graph contains no unselected target branches.
19. generated `.cmake` files contain no machine-specific absolute paths. They
    address source/generated roots through stable CMake variables and
    dependencies through logical CMake target names.
20. generating the same target from different supported build hosts produces
    equivalent graph manifests; generating different targets is allowed to
    produce different source/options/import selections.
21. a `planned` or `impossible_under_current_art_contract` profile fails
    capability validation before CMake rather than degrading DSO topology,
    disabling runtime contracts silently, or compiling host fallbacks.

## Proposed repository layout

The names are illustrative, but ownership boundaries are mandatory:

```text
CMakePresets.json                 optional common/CI convenience presets
native/
  CMakeLists.txt                 one product entry point
  cmake/
    Common.cmake                validation and common target policy
    Codegen.cmake               generated-source targets
    Dependencies.cmake          target dependency imports
    PlatformLinux.cmake         Linux semantic mappings
    PlatformWindows.cmake       Windows semantic mappings
    PlatformWasi.cmake          future WASI semantic mappings; gated
    Packaging.cmake             target-tree staging
    toolchains/
      LLVM.cmake                one target-profile-driven toolchain
overlay/
  art_port_policy.py            one target-aware overlay factory
tools/
  build_art.py                  one user/CI frontend
  target_profiles.py            canonical target registry and aliases
  path_audit.py                 symlink/reparse and Windows-name validation
  command_audit.py              shell/tool invocation validation
  bp2cmake/                     one evaluator and emitter
out/
  <build-host>-to-<target>/
    <build-type>/
      source_projection/
      generated/
        art_graph.cmake
        target_profile.cmake
        graph_manifest.json
        inputs.sha256
      gensrc/
      stage/
      CMakeCache.txt
      build.ninja
      build_manifest.json
```

Target SDK locations belong in frontend configuration, internal CMake cache
arguments, or an untracked `CMakeUserPresets.json`; they must not be embedded
in checked-in files or generated `.cmake` files.

## One profile, one graph generator, one overlay

### Profile model

`tools/build_art.py` should resolve a typed profile and pass the same profile to
both `bp2cmake` and CMake. At minimum it contains:

```text
build:
  build_host_os
  build_host_arch
  host_python
  host_cmake
  host_ninja
  host_llvm_root
  host_jdk
  sysroot_or_sdk
  build_type

target:
  target_id
  os_or_runtime
  cpu_arch
  abi
  object_format
  pointer_bits
  endianness
  target_triple
  cmake_system_name
  cmake_system_processor
  aosp_build_kind = host
  cxx_runtime
  compiler_runtime
  capabilities
  support_status

product:
  root_modules
  source_roots
  source_alias_policy = materialize_regular_files
  managed_path_policy = reject_symlinks_and_reparse_aliases
  shell_policy = no_shell
```

The build-host fields control only executable suffixes, path handling, and
host-native tool discovery/validation. `os_or_runtime`, `cpu_arch`, ABI, and
capabilities control Blueprint selects and target policy. The target graph for
`windows-x86_64` must therefore be the same whether generation runs on Linux
x86-64 or Windows 10 ARM64.

The serialized profile should have separate `build_host` and `target`
sections. `bp2cmake` consumes only the target, AOSP-build-kind, source, and
policy projection. The graph digest excludes build-host paths and uses
normalized relative paths with `/` separators, while the outer build manifest
records the complete build-host/tool environment. This keeps a target graph
host-independent without losing provenance.

The generated `target_profile.cmake` is a portable projection of the `target`
section only. Host tool, source root, SDK, sysroot, and output locations are
bound by the frontend through CMake cache variables and recorded in the build
manifest; their absolute values are not emitted into either generated CMake
file.

The profile should replace independent `--os`, overlay filename, hand-entered
root-module lists, and CMake cache fragments. Command-line overrides may bind
machine paths or build type, but may not mutate individual target identity
fields. A different ABI/triple requires a different named target profile. The
fully resolved result is serialized into the build manifest.

### Overlay factory

Replace two top-level policy objects with one factory, conceptually:

```python
def make_overlay(target: TargetProfile) -> Overlay:
    policy = common_art_policy(target)
    policy.merge(os_or_runtime_policy(target.os_or_runtime, target))
    policy.merge(object_format_policy(target.object_format, target))
    policy.merge(abi_policy(target.abi, target))
    policy.merge(architecture_policy(target.cpu_arch, target))
    policy.merge(capability_policy(target.capabilities, target))
    return policy.validate()
```

This is one Python overlay module and one schema, composed as common policy,
OS/runtime policy, object-format/ABI policy, architecture policy, and
capability policy. It may contain clearly named policy sections, but modules
are declared once and refined by target. A module cannot have unrelated
definitions in separate files, and a new architecture must not require a copy
of the whole overlay.

The common portion owns:

- name mapping;
- root modules and closure policy;
- common module kinds;
- whole-static absorption rules;
- common warnings and ART behavioral definitions;
- generated-source declarations; and
- the expected DSO/static topology.

Target portions own only actual target differences:

- Blueprint target branch;
- OS source replacement;
- architecture-specific sources and generated assembly;
- target ABI definitions;
- pointer-width and object-format behavior;
- target system libraries;
- platform compatibility sources;
- linker security mappings; and
- DSO export policy.

The overlay validator should reject conflicting keys, duplicate target names,
an unknown module exception, or a platform override that changes a common
module kind without an explicit `topology_exception` reason. The hard-coded
test/fuzz/benchmark/sample exclusions should move from `bp2cmake.__main__` into
the product profile.

### Deterministic output

`bp2cmake` should write atomically and deterministically to
`out/<build-host>-to-<target>/<build-type>/generated/art_graph.cmake`. It
should also write a machine-readable graph manifest containing, for each
module:

- Blueprint name and CMake target name;
- module kind;
- normalized, sorted source list;
- public/private includes and definitions;
- generated sources;
- link dependencies; and
- each overlay rule that changed the normalized Blueprint module.

Paths in generated CMake use project CMake variables and normalized relative
suffixes rather than machine-specific absolute prefixes. The emitter rejects
an absolute path in every emitted source, include, library, tool, output, and
custom-command field. The input digest should cover all loaded
`Android.bp`/`sources.bp` files, source-root identities, generator source,
target profile, and overlay source without hashing build-host path spellings
into the target graph identity.

Generation needs two explicit modes:

- `--write`: atomically replace outputs whose content changed; and
- `--check`: generate in memory and fail if an output or manifest differs.

No generated product CMake snapshot should be committed after migration. CI's
`--check` gate proves that a configured build tree is current instead.

## One CMake entry point

`native/CMakeLists.txt` should be target-neutral. Its order should be:

1. load and validate the portable target profile already consumed by the
   common toolchain, plus the target dependency manifest;
2. validate the generator, single-config build type, compiler frontend, target
   triple, SDK/sysroot bindings, and LLD selection;
3. define common policy interface targets;
4. define generated-source commands/targets;
5. include the generated module graph;
6. attach the small number of compatibility sources or options that cannot be
   represented in the overlay;
7. validate the final target topology; and
8. define install/staging and tests.

CMake should not contain module source lists copied from Blueprint. Probe
programs should live under a test subtree and link the product targets. A probe
must not redefine or import a second copy of the product graph.

Avoid mutable global strings such as `CMAKE_CXX_FLAGS`. Toolchain files may set
the compiler target/sysroot initialization necessary for compiler discovery;
ordinary warnings, features, definitions, security options, and platform
libraries belong on CMake targets. Recommended common interface targets are:

```text
mdvm::compile_policy
mdvm::link_policy
mdvm::platform
mdvm::sanitizer_policy
```

Generated targets link the appropriate interfaces privately or publicly.
Source-specific workarounds remain source properties only when a target-level
policy is provably too broad.

## CMake frontend, optional presets, and Ninja

Do not check in a manually duplicated build-host-by-target preset Cartesian
product. With Linux x86, ARM, ARM64, RISC-V, several Windows ABIs, and possible
WASM profiles, that list would become configuration code by repetition.

`CMakePresets.json` may provide a hidden common Ninja/Clang base and a small
number of supported CI convenience presets. The authoritative matrix comes
from the Python target registry. `tools/build_art.py` detects the build-host ID,
resolves the requested target ID, and deterministically assigns:

```text
out/<build-host-id>-to-<target-id>/<build-type>/
```

It then invokes the same maintained CMake entry point with `-G Ninja`, the
common LLVM toolchain, the generated target profile/graph paths, and the
machine-specific root bindings. It must not synthesize a Make, NMake, Visual
Studio, or Multi-Config fallback. The exact configure argument vector is
recorded in the build manifest so the dynamic frontend is no less auditable
than a static preset.

The public command shape is identical on both hosts:

```text
python tools/build_art.py configure --target-id windows-x86_64
python tools/build_art.py build --target-id windows-x86_64 --cmake-target art-compiler
python tools/build_art.py test --target-id windows-x86_64
python tools/build_art.py stage --target-id windows-x86_64
python tools/build_art.py check-generated --target-id windows-x86_64
```

Only the operating system's Python executable spelling may differ. There
should be no `.sh` versus `.bat` product logic split.

The `configure` operation has one fixed sequence: resolve and validate the
profile, bind and audit machine-specific roots, run `bp2cmake --write`, invoke
CMake with the generated graph/profile paths, then write the build manifest.
Calling CMake directly is an expert/debug flow and requires an already checked
generated graph; it must not trigger a second, subtly different generator
implementation.

## POSIX-environment-free Windows 10 ARM64 host contract

The Windows host is a normal Win32 environment, not a Unix compatibility
environment. The required host executables are native Windows ARM64 builds of:

- Python;
- CMake;
- Ninja;
- Clang/LLVM, including the LLVM inspection/archive tools; and
- a JDK when the boot jar is requested.

The Clang host executable architecture and its output target are independent.
For example, ARM64 `clang++.exe` runs on Windows 10 ARM64 with
`--target=x86_64-pc-windows-msvc` to produce `art-compiler.dll`. The matching
target SDK contains headers and libraries, not helper executables that the
build tries to run. The same separation applies to Windows-to-Linux builds.

All orchestration belongs in Python using `pathlib`, `shutil`, hashing/archive
libraries, and `subprocess.run(argv, shell=False, check=True)`. Resolve and
validate `sys.executable` once, then use the recorded final regular executable
for child Python processes rather than a symlink spelling. Timeouts use the
subprocess API; file copies, removals, scans, and byte searches use Python or
CMake built-ins. No project logic may depend on command parsing by `cmd.exe` or
PowerShell either.

CMake custom commands must pass one executable and an argument list with
`VERBATIM`. They may invoke portable `cmake -E` operations or Python helpers.
They must not contain:

- `>`, `<`, `|`, `&&`, `||`, backticks, or command substitution;
- Unix tools such as `cp`, `rm`, `mkdir`, `find`, `grep`, `sed`, `awk`,
  `stat`, `file`, `strings`, `readlink`, or `timeout`;
- environment activation through `source` or an `.sh` file;
- `/tmp`, `~`, `$HOME`, or POSIX-only path construction; or
- executable-bit or shebang assumptions for Python scripts.

`operator_out` is a concrete required fix: the emitter must call the existing
Python codegen wrapper with an explicit output argument. The wrapper captures
the upstream script's stdout and atomically writes the file; generated CMake
must not emit `python ... > output.cc`.

Use response files for long compiler, linker, javac, and D8 argument lists.
The frontend should choose a short per-build output root and validate Windows
path legality, case-fold collisions, reserved device names, trailing spaces or
dots, and configured long-path support before CMake runs. These checks apply on
Linux too so a Linux-generated graph cannot contain names that fail only on
Windows.

CI must configure and build from a stock Windows process environment with
WSL, Cygwin, MSYS2, Bash, Make, and Unix utilities absent from `PATH`. Merely
running a Python wrapper from Git Bash does not satisfy this gate. CMake may
use a native `cmd.exe /C` wrapper internally when implementing a Ninja custom
command or working directory; that implementation detail is allowed, but the
project command payload contains no batch logic or shell operators.

## LLVM toolchain contract

### Common contract

The one maintained LLVM toolchain module must configure from the resolved
target profile:

- a host-native Clang/LLVM installation, including Windows ARM64 executables
  on the Windows 10 ARM64 build host;
- `clang` for C and assembly-with-cpp;
- `clang++` for C++ and final C++ links;
- LLVM binutils (`llvm-ar`, `llvm-ranlib`, `llvm-nm`, `llvm-strip`, and related
  tools appropriate to the target);
- a target triple for every cross build and preferably every reproducible
  native build;
- the selected SDK/sysroot and only its include/library search roots; and
- LLD through the driver with `-fuse-ld=lld`.

The compiler ban applies to the driver and toolchain path, not to the target's
ABI name. `x86_64-pc-windows-msvc` is the required non-MinGW Windows ABI triple
even though neither MSVC's compiler nor Clang-CL is used.

C++ runtime selection must be explicit in the target profile. Windows can use
the already provisioned libc++/compiler-rt combination. Linux may retain a
validated target runtime initially or move to libc++ as a separately tested ABI
decision; it must not depend on whichever C++ runtime happens to be found on
the build host.

Toolchain configuration is data, not an activation script. The frontend or an
optional user preset passes regular-file roots for host LLVM and the target
SDK/sysroot.
`env.sh`, `source`, `cygpath`, registry-dependent `cl.exe` discovery, and
inherited Unix environment variables are not part of the contract.

### Representative driver commands

CMake remains responsible for the exact rule, but the audit-visible shape
should resemble:

```text
# Linux shared library
clang++ --target=x86_64-unknown-linux-gnu ... -fPIC -c compiler.cc
clang++ --target=x86_64-unknown-linux-gnu ... -shared -fuse-ld=lld \
  -o libart-compiler.so ...

# Windows shared library, from either build host
clang++.exe --target=x86_64-pc-windows-msvc ... -c compiler.cc
clang++.exe --target=x86_64-pc-windows-msvc ... -shared -fuse-ld=lld \
  -Wl,/implib:art-compiler.lib -o art-compiler.dll ...
```

On a Linux build host the Windows compiler executable normally has no `.exe`
suffix. That host spelling is not a separate toolchain design.

Assembly must also go through Clang. MASM, `ml.exe`, and `ml64.exe` are not
fallbacks. Target assembly syntax/source selection is an overlay concern.

## PIC, PIE, shared libraries, and command-line parity

The user's required command style is best expressed as equal CMake semantics
and equal Clang-driver usage. Literal ELF options are not all meaningful to a
PE linker.

| Intent | Common CMake representation | Linux/ELF result | Windows/PE result |
|---|---|---|---|
| Shared library | `add_library(name SHARED ...)` | Clang link with `-shared`, PIC objects | Clang link with `-shared`, PE DLL and import library |
| Relocatable DSO code | `POSITION_INDEPENDENT_CODE ON` | normally `-fPIC` | no literal ELF PIC flag is required; PE relocation rules apply |
| Relocatable executable | `POSITION_INDEPENDENT_CODE ON` plus `CheckPIESupported` where supported | normally `-fPIE` compile and `-pie` link | PE image with ASLR-compatible relocation data |
| ASLR/security | platform link-policy target | ELF PIE and project hardening | `/DYNAMICBASE` and `/HIGHENTROPYVA` through Clang's linker-option forwarding |

Thus `-shared` should visibly occur for both `libart-compiler.so` and
`art-compiler.dll`. Linux executables should visibly use `-fPIE` and `-pie`.
Windows executables must not be fed a meaningless ELF `-pie` merely to make logs
look alike; they must receive PE's equivalent dynamic-base/high-entropy policy
through the same GNU-style Clang driver. CMake's `LINKER:` option form should be
used so it chooses correct driver forwarding instead of a direct linker call.

This distinction is semantic parity, not an exception to unification.

## Target dependency resolution

Native `find_library()` calls are not sufficient for the matrix. Every target
profile should expose imported CMake targets for zlib, lz4, expat, libc++ or
other runtime libraries, and platform libraries. Imported targets carry target
include directories and target library files.

For cross profiles:

- set CMake root-path modes so programs are found on the build host while
  headers/packages/libraries are found only in the target sysroot;
- set `CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY` where compiler checks
  would otherwise try to link or run an executable;
- prohibit unresolved absolute paths outside the repository, Clang root, and
  declared target SDK/sysroot; and
- never make a missing target dependency an empty interface library unless it
  is a reviewed, capability-gated absence with no referenced symbols.

The profile's dependency manifest, rather than build-host discovery, should
decide whether a library is built from AOSP source or imported from the target
SDK.

## Symlink-normalized path contract

Git symlink entries are allowed to exist in the source checkout. On Linux they
may be filesystem symlinks; with Git for Windows and `core.symlinks=false`, the
same entry may be an ordinary file whose content is only the relative target
name. The build must accept both representations and produce the same graph.
It must never pass either the link or the placeholder file to a compiler.

Before `bp2cmake` scans paths, the Python frontend loads a source-alias map from
the source manifest. The evaluator resolves logical paths through that map,
without asking the OS to follow a link. After dependency closure is known and
before CMake is emitted, the frontend normalizes every required source and
declared include tree. For each Git mode `120000` entry it:

1. reads the link target from version-control metadata rather than relying on
   host filesystem resolution;
2. rejects an absolute target, repository escape, cycle, type mismatch, or
   target missing from the pinned source manifest;
3. resolves chained aliases entirely within the manifest;
4. copies the required target file or the relevant declared include/source
   tree into the target binary directory's `source_projection` as ordinary
   files/directories,
   preserving the logical relative layout; and
5. records alias, target, file modes, and content hashes in the graph inputs.

The emitter references only the regular source projection or a canonical
source path whose components and reachable declared include tree passed the
non-link scan. Code generation, CMake, Ninja, Clang, javac, and packaging never
call `readlink`, follow a junction, or compile the small text placeholder
created by Git for Windows.

The source checkout may therefore retain upstream symlinks that are not in the
product closure. Broken formatting/test links outside the closure do not fail a
product build. If a required alias cannot be normalized, the frontend fails
during source validation with the owning module, alias, and expected target;
the failure cannot surface later as a compiler syntax/file-not-found error.

The current product should still prefer canonical source locations:

- remove `vendor/fmtlib` from generated product paths and address the real
  `vendor/external/fmtlib` submodule directly;
- replace the fdlibm link farm with an explicit generated ordinary-file include
  projection or a reviewed source/include rewrite; and
- if vendored ART tests are enabled, normalize their shared Java/source aliases
  through the same regular-file projection rather than recreating links.

The product must not create, stage, or package a symlink. The same rule applies
to Windows directory junctions and other project-controlled name-surrogate
reparse points. Linux CI enforces the output/tool rule too; Linux's permissive
symlink behavior must not conceal a Windows failure.

The strict no-link scope includes every component of:

- the normalized source projection and generated include paths;
- Python, CMake, Ninja, Clang/LLVM, JDK, SDK, sysroot, and dependency paths;
- binary and generated-source directories;
- imported libraries and runtime staging inputs; and
- staged directories and archive entries.

The frontend inspects these managed path components without following them. On
POSIX it uses `lstat` semantics. On Windows it also checks reparse
attributes/tags so a junction is not mistaken for an ordinary directory.
Discovery may report a canonical real tool path, but the resolved profile and
all Ninja rules use the final regular file path. A user-supplied managed path
that still contains an alias fails before generation.

Git mode `120000` must be recorded for the root repository and every
participating submodule because `core.symlinks=false` can turn a symlink blob
into a regular text file containing only the target name. Filesystem inspection
alone would then miss the semantic link and a compiler could consume the
placeholder.

Source provisioning should move to a shell-free `tools/vendor_sync.py` that
writes a platform-neutral source manifest containing repository identities,
paths, modes, link payloads, and hashes. The build host reads that manifest
with Python and does not require a Git executable. The manifest is pinned and
checked in alongside the submodule/source lock. When a developer builds from a
live Git checkout and Git is available, an optional cross-check may
refresh/verify the manifest, but it is not part of the Windows host contract.
`bp2cmake` validates every source/include in the emitted closure against the
normalized projection, source manifest, and filesystem metadata.

The SDK/toolchain provisioner must unpack a real directory tree. The current
`windows_x64-dev-env` alias tree is rejected rather than dereferenced. Host
compiler discovery similarly records and invokes the actual LLVM executable,
not `/usr/bin/clang`-style symlink names.

Packaging performs a final non-following traversal. ZIP/JAR/TAR metadata that
encodes a symlink is rejected even if extraction on the current host would
materialize it. The build manifest records
`source_alias_policy: materialize_regular_files`,
`output_symlink_policy: reject`, and the path-audit digest.

## Host tools versus target generation

Every generator must be classified explicitly:

| Generator | Runs on build host | Uses target ABI | May execute target output |
|---|---:|---:|---:|
| aconfig Python stand-in | yes | no, except profile data | no |
| `operator_out` Python | yes | no | no |
| mterp Python | yes | target architecture selects inputs | no |
| `asm_defines` stage 1 | target Clang runs on host | yes | no; emits assembly with `-S` |
| `asm_defines` stage 2 | host Python | reads target assembly text | no |

`asm_defines` must use `CMAKE_CXX_COMPILER`, the same target triple, sysroot,
headers, definitions, language standard, and ABI-affecting options as ART. Its
output manifest should record those inputs. The Windows `0x328` versus Linux
`0x340` instrumentation-offset check is a useful target-specific assertion,
but it should be generated from/validated against the profile rather than
embedded in a Windows-only product harness.

Generated-source steps should be Ninja dependencies with declared `OUTPUT`,
`BYPRODUCTS`, `DEPENDS`, and `VERBATIM` behavior. The Python generator should
continue replacing files only when content changes. Configuration may generate
the CMake graph needed to create targets, but compilation-derived artifacts
such as `asm_defines.h` should be ordinary build graph outputs, not hidden
configure side effects.

Every generator accepts explicit input and output arguments. A generator that
only writes stdout upstream is called through the shared Python capture helper;
the CMake emitter never implements output capture with shell redirection.

If a future generator must compile and execute a helper, it needs a distinct
native host-tool target/build. It may not execute a cross-target program through
an implicit emulator during configuration.

## Shared/static topology

The graph manifest should carry the expected common topology. A practical
initial rule is:

| Logical role | Linux | Windows | Policy |
|---|---|---|---|
| Product/runtime components (`art`, `artbase`, `dexfile`, `profile`, `art-disassembler`) | shared where the Linux product graph exposes a DSO | same logical DSO | no Windows static fallback |
| Compiler (`art-compiler`) | `SHARED` | `SHARED` | mandatory parity |
| Dex2oat support (`art-dex2oat`) when enabled | `SHARED` | `SHARED` | availability may be capability-gated, kind may not drift |
| Final tools (`dalvikvm`, optional `dex2oat`) | executable | executable | same target names |
| Internal leaf aggregation with no ABI surface | static/object/interface | same logical role | platform exception requires manifest reason |
| Target SDK libraries | imported target | imported target | never copied into generated module source lists |

The migration should compare manifests rather than assume every current Linux
choice is ideal. The key rule is that a platform cannot change a logical DSO to
static just to bypass DLL export or dependency work.

## `art-compiler.dll` design

### Initial parity with the Linux graph

The current AOSP module is declared static because upstream aggregates compiler
and runtime pieces into `libart`. The Linux overlay already does two things:

1. absorbs compiler objects into `art`; and
2. emits a standalone shared `art-compiler` for compiler tools, linking it to
   `art` and `art-disassembler`.

The first Windows parity milestone should reproduce that same topology:

```text
art.dll
  contains the compiler objects required by the current libart aggregation

art-compiler.dll
  is a separate SHARED target built from the compiler module
  imports runtime symbols from art.dll
  exports the compiler API required by compiler tools
```

This compiles approximately 95 compiler translation units twice, as Linux
currently does. That cost is preferable to accidentally introducing a DSO
cycle during the unification migration. In particular, do not make `art.dll` import
`art-compiler.dll` while `art-compiler.dll` imports `art.dll`.

An object-library optimization is not automatically safe on Windows. The copy
inside `art.dll` and the copy inside `art-compiler.dll` can require different
`dllimport`/`dllexport` compilation contexts. Reusing one object set before the
symbol ownership model is proven can create invalid imports back into the DLL
being linked. Compile deduplication should therefore be a later, measured
refactor with an explicit no-cycle/ABI design.

### Export contract

`CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS` is useful for exploration but is not a
durable ABI contract. It can miss or mishandle data symbols and it exports
implementation details unpredictably as source lists change.

The preferred order is:

1. define narrow compiler API annotations that expand to default visibility on
   ELF and `__declspec(dllexport)`/`__declspec(dllimport)` on Windows;
2. set the building/importing definition per CMake target;
3. use reviewed `.def` files only for required symbols that cannot reasonably
   be annotated; and
4. have CI compare actual exports with a checked ABI allowlist.

The DLL target must have stable output properties so all hosts produce
`art-compiler.dll` plus `art-compiler.lib`. Compiler tools link the CMake target,
not a hard-coded file path. Runtime staging must place the DLL beside dependent
executables or in the declared product DLL directory.

The Windows ABI gate should use LLVM inspection tools to verify:

- the file is PE32+ x86-64;
- the import library exists and resolves a small link probe;
- required code and data exports are present;
- dependencies resolve from the staged product tree;
- no static `art-compiler` archive is used by `dex2oat` or another consumer;
  and
- loading/unloading the DLL does not rely on unresolved symbols supplied by a
  probe executable.

### Longer-term topology optimization

After parity, measure the duplicate compiler compile/link cost and map symbol
ownership. A cleaner runtime-only `art` plus `art-compiler -> art` topology may
be possible, but only if all runtime-to-compiler edges are removed or inverted
without a cycle and both JIT and compiler entry points retain their required
ownership. That is a separate ART architecture change, not a build-script
cleanup.

## Build and source manifests

Each binary directory should contain a build manifest with at least:

- source revision and submodule revisions;
- resolved profile and graph/input digest;
- build host OS/architecture;
- canonical target ID, OS/runtime, CPU architecture, ABI, object format,
  pointer width, and triple;
- canonical Clang paths and `--version` output;
- host executable formats/architectures for Python, CMake, Ninja, LLVM, and the
  JDK;
- CMake and Ninja versions;
- LLD selection;
- SDK/sysroot identity and version/digest;
- C/C++ runtime selection;
- build type and effective optimization/debug policy;
- generated module topology digest;
- shell-free command-audit digest; and
- symlink/reparse-point audit policy and digest.

The frontend compares the manifest before every configure/build. A mismatch
must require a new binary directory or explicit cache recreation; it must not
quietly continue with stale values. Separate binary directories for every
matrix cell and build type prevent the mixed Windows environment observed in
the current cache.

For reproducibility, two clean generations from identical inputs must produce
byte-identical CMake and graph manifests. Two clean builds should compare
artifacts after accounting for explicitly documented non-deterministic fields
such as platform debug-path metadata; the first gate is deterministic graph and
command generation.

## Boot jar and staging

Replace the product role of the current shell chain with a host Python stage,
for example `tools/build_bootjar.py`, invoked by `build_art.py` and represented
as a Ninja custom target when part of the full product.

It should:

- use the target binary directory's `bootjar`, never shared `/tmp/bootbuild`
  state;
- treat javac and D8 failures as fatal;
- launch `javac`/`java` with argument vectors and response files, never a shell
  command string;
- use Python timeouts, file/archive APIs, and byte inspection instead of Unix
  utilities;
- declare the selected JDK, R8/D8, Java sources, aconfig inputs, and target
  profile in a manifest;
- write atomically; and
- stage into the target binary directory's `stage` without also copying to
  unrelated Linux and Windows directories.

The boot jar can remain logically shared when its bytecode is deliberately
multi-platform. Its producer and outputs still belong to one configured build
so a failed or partial invocation cannot contaminate another target build.

## Migration plan

### Phase 1: freeze and compare current graphs

- Add manifest output and `--check` mode to `bp2cmake`.
- Add Git-mode/filesystem symlink and Windows reparse-point audits.
- Add a generated-command scanner for shells, shell operators, POSIX utilities,
  and Make-family tools.
- Capture current Linux and Windows normalized module graphs.
- Classify every kind/source/dependency difference as common policy, a genuine
  target difference, a missing Windows port, or stale handwritten state.
- Add command audits for Ninja and the Clang GNU driver before changing target
  topology.

### Phase 2: introduce the unified profile and overlay factory

- Replace the two overlay entry points with `make_overlay(profile)`.
- Move root modules and scan exclusions into the profile.
- Make build-host and target fields distinct throughout evaluator, codegen, and
  emitter APIs.
- Generate both target graphs into isolated build directories and compare their
  topology manifests.
- Split build-host tool architecture from target architecture and provision a
  regular-file Windows ARM64 host-tool bundle.

### Phase 3: introduce one product CMake entry point

- Extract common policy, codegen, dependency imports, platform mappings, and
  staging into focused CMake modules.
- Configure all supported matrix cells through `tools/build_art.py`; optional
  CI presets may call the same frontend contract.
- Move Phase-1 probe executables to a test subtree that links the product graph.
- Remove product target/source duplication from verification CMake files.
- Replace shell redirection in emitted codegen rules with explicit Python
  output arguments.
- Replace fdlibm and fmtlib compatibility aliases with canonical paths and
  regular-file generation.
- Run the first POSIX-environment-free, symlink-normalized Windows 10 ARM64
  configure/build gate.

### Phase 4: make Windows DSO topology equal

- Change the Windows compiler policy from static to shared.
- Implement and audit compiler DLL exports.
- Produce and stage `art-compiler.dll` and its import library.
- Convert other current Windows static substitutions to the common topology or
  record a temporary, owner/date-tagged exception.
- Prove that neither the runtime nor a tool introduces an `art`/`art-compiler`
  DLL dependency cycle.

### Phase 5: remove legacy product paths

After all acceptance gates pass, remove or demote the following as product
inputs:

- `native/generate.sh` and the checked-in `native/generated/dalvikvm.cmake`;
- checked-in `windows_x64_phase0/phase0.cmake` and
  `windows_x64_phase1/phase1.cmake` snapshots;
- product graph logic in Phase-0/Phase-1 verification CMake files;
- the unproducible `windows_x64_libcore_icu/sources.cmake` snapshot;
- `overlay/port_policy.py` and `overlay/port_policy_windows.py` after their
  policies are merged;
- build instructions or scripts that select Make, NMake, Visual Studio, or
  Ninja Multi-Config;
- shell-only boot-jar staging with ignored failures and shared `/tmp` output;
- all project-owned Git mode `120000` entries after canonical fmtlib/fdlibm
  paths are in service;
- environment-activation scripts and `.sh` product entry points; and
- the symlink-based `windows_x64-dev-env` alias tree from supported toolchain
  instructions.

Useful probes and result documents should remain. They become tests of the
unified product targets instead of alternative ways to build those targets.

### Phase 6: admit additional targets one at a time

- Keep registry entries for all planned targets, but enable each only after its
  profile capability gate is complete.
- Replace the `<arch>ng` mterp assumption with explicit architecture metadata
  and make generated assembly selection profile-driven.
- Remove the x86-64 triple, prelude, mterp, BoringSSL assembly, and verification
  assumptions identified in the current-state audit.
- Validate Linux AArch64, x86, ARMv7, and RISC-V64 independently; source-tree
  presence alone is not an admission gate.
- Treat Windows AArch64, ARM64EC, and x86 as separate ABI profiles with their
  own SDK, triple, exports, object inspection, and runtime gates.
- Retain WASM profiles as explicit capability failures until a runtime/DSO/JIT
  contract is designed; do not introduce a static-library compatibility mode.

### Phase 7: optimize after parity

- Profile graph generation, configure time, duplicate compilation, link time,
  and incremental rebuilds.
- Remove duplicate compiler compilation only after DLL symbol ownership and
  no-cycle constraints are proven.
- Consolidate compatibility shims when Linux/Windows source differences can be
  expressed in upstream-shaped source selection.
- Consider a common LLVM C++ runtime only as an explicit ABI migration, not as
  an accidental side effect of host tool discovery.

## Acceptance gates

### Generation and configuration

- `bp2cmake` unit tests pass for every registry profile, including explicit
  expected capability rejection for planned/blocked profiles.
- Generating twice produces no diff and identical digests.
- Linux-host and Windows-host generation of the same target profile produces
  equivalent graph manifests.
- every generated `.cmake` file is target-resolved, contains no unselected
  target branches, and passes an absolute-path rejection scan;
- each binary directory records exactly one canonical target identity and is
  rejected if target, ABI, triple, object format, SDK/sysroot, or build type is
  changed in place;
- every planned or contract-blocked profile fails before CMake with a
  capability-specific diagnostic rather than a substituted source or library
  kind;
- checkouts with real Git symlinks and with `core.symlinks=false` link-text
  files produce identical normalized source and graph digests for the product
  closure;
- every configured build reports exactly `Ninja`, one build type, Clang GNU
  frontend, the intended target triple, and LLD;
- forbidden tool/generator names do not occur in CMake caches or Ninja command
  rules;
- cross builds contain no undeclared build-host include or library path;
- Windows 10 ARM64 configures using native ARM64 host tools from a stock Windows
  environment with no POSIX layer; and
- Git-mode and filesystem audits report no unnormalized symlink/reparse-point
  path in the emitted closure, toolchain, binary tree, or stage tree.

### Command-line audit

Audit `compile_commands.json` and `ninja -t commands` for every matrix cell:

- compile rules start with the configured plain Clang driver;
- C++ and final C++ links use `clang++`;
- shared-library links contain driver-level `-shared` and `-fuse-ld=lld`;
- Linux executable compile/link rules show the expected `-fPIE`/`-pie` result;
- Windows image rules show the required PE ASLR flags through the driver;
- no rule invokes GCC, G++, MinGW, Clang-CL, CL, Make, NMake, a Visual Studio
  tool, `ld.lld`, or `lld-link` directly;
- no rule invokes a POSIX shell or Unix utility; and
- no project-authored command payload contains redirection, pipes, chaining,
  or command substitution.

### Artifact and topology validation

- the common module-kind manifest matches across Linux and Windows except for
  reviewed exceptions;
- Linux produces and loads `libart-compiler.so`;
- Windows produces `art-compiler.dll` and `art-compiler.lib`, and a consumer
  links and loads through the import library;
- LLVM object inspection confirms the target file format, architecture,
  imports/exports, and PIE/ASLR properties;
- staged executables resolve only staged target DSOs plus approved platform
  libraries;
- the Windows product has no static compiler fallback or cyclic DLL imports;
- non-following scans find no symlink, junction/name-surrogate reparse point,
  or archive symlink entry in build and staged artifacts.

### Build and runtime validation

- clean `RelWithDebInfo` builds pass for each provisioned matrix cell;
- native Linux smoke tests pass;
- Windows x86-64 and other cross-built artifacts pass smoke tests only under an
  explicit target runner or emulation environment where provisioned; the
  Windows 10 ARM64 build gate does not depend on x86-64 emulation and no runner
  is used during configure;
- incremental no-op builds execute no compile/link/generation commands;
- changing an `Android.bp`, overlay rule, codegen input, or target ABI setting
  rebuilds exactly the affected graph/output;
- boot-jar failure stops the product build and cannot leave a successful-looking
  staged artifact;
- a Linux build with shell/POSIX tools deliberately removed from the frontend's
  `PATH` still generates and builds, proving both hosts use the same contract.

## Risks and controls

| Risk | Effect | Control |
|---|---|---|
| Build host leaks into target selection | wrong sources and ABI | one serialized profile; graph equivalence across hosts |
| One CMake cache is reused for another target | stale compiler checks, pointer size, ABI, or assembly | one immutable target identity and binary directory per target/build type |
| Generated graph embeds machine paths | graph differs by host and cannot relocate | stable root variables plus absolute-path rejection in the emitter |
| Giant generated graph retains inactive target branches | wrong source or policy leaks into the closure | Python emits one fully resolved graph per exact target |
| Cross build finds host headers/libs | links successfully but is invalid | sysroot-only root modes and path audit |
| Literal Linux flag reuse on Windows | ignored options or broken PE link | common semantic properties with platform mapping |
| Export-all hides an incomplete DLL ABI | unstable or missing imports/data | annotations/`.def` allowlist and ABI probe |
| Static fallback masks DLL defects | unequal products | topology validator makes `art-compiler SHARED` mandatory |
| Compiler DSO creates a cycle with `art` | loader/link failure | preserve current aggregate topology first; import graph gate |
| Object-library dedup uses wrong import/export context | invalid Windows objects | defer until symbol ownership is designed and tested |
| Configure executes target helper | cross build fails or uses emulator accidentally | classify host tools; compile target layout with `-S` only |
| Stale generated snapshot | unreviewed source/dependency drift | build-tree generation, digest, and `--check` |
| Stale CMake cache | wrong SDK, flags, or optimization | per-target binary directory and build fingerprint |
| Shared `/tmp` boot state | cross-target contamination | binary-directory-local atomic output |
| Linux follows a symlink while Windows stores its link text | compiler sees different or invalid input | manifest-driven alias resolution and identical regular-file projection |
| Toolchain/SDK path contains a junction or symlink | non-reproducible host-dependent toolchain | regular-file toolchain package and component-wise path validation |
| Ninja rule contains `>` or a Unix utility | Windows 10 ARM64 build failure | explicit Python output APIs and shell-free command scanner |
| x86-64 helper is run on Windows ARM64 | emulation dependency or configure failure | host-tool architecture validation; never execute target outputs |
| Case/path-length difference appears only on Windows | generation or compile failure | Windows legality/case-fold checks on every host and response files |

## Relationship to Windows AOT/OAT

[`win32_aot_oat.md`](win32_aot_oat.md) explicitly states that Windows OAT
generation and executable loading are not implemented. This build design does
not change that status.

`art-compiler.dll` is necessary DSO parity and may be a prerequisite for future
compiler tools. It does not by itself provide:

- a working Windows `dex2oat.exe`;
- the selected restricted Windows OAT-ELF writer profile;
- OAT/VDEX/image transaction and relocation behavior;
- the dedicated Windows OAT loader;
- Windows quick-code unwind/CFG publication; or
- the acceptance gates in `win32_aot_oat.md`.

Until those gates pass, Windows product capability should continue to be
described as interpreter/JIT work only. The build manifest may expose
`windows_aot=false`; generating a compiler DLL must not flip it.

## Final recommendation

Proceed with unification as a graph/orchestration refactor first, then achieve
Windows DSO parity, then optimize duplicate compiler work. The success measure
is not one giant platform-conditional CMake file. It is one deterministic
target graph, one reviewed target-aware overlay, one target-neutral CMake entry
point, and one Clang/Ninja command contract whose small platform mappings are
explicit and mechanically validated. That command contract uses only native
Python/CMake/Ninja/LLVM/JDK host executables, consumes only regular canonical
paths, and works unchanged on Linux and a stock Windows 10 ARM64 host without
WSL, Cygwin, a POSIX shell, Make, or reliance on symlink resolution.
