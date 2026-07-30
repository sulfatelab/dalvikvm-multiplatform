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
3. one handwritten CMake product entry point;
4. one Python command-line frontend for generation, configuration, build,
   test, staging, and reproducibility checks;
5. CMake's single-configuration `Ninja` generator on Linux and Windows build
   hosts, for native and cross targets; and
6. the LLVM Clang GNU-style driver plus LLD for every compile and link.

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
          out/<preset>/generated/art_graph.cmake
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
- Makefile, NMake, Visual Studio, and Ninja Multi-Config CMake generators; and
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
- Make the product graph smaller and easier to audit without deleting useful
  Windows verification probes.

### Non-goals

- Translating every Soong feature or every module in the AOSP tree.
- Supporting Android/bionic as a target in this pipeline.
- Supporting 32-bit or non-x86-64 targets in the initial migration.
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
| Linux | Linux x86-64 | native | explicit or validated native Linux SDK/sysroot |
| Linux | Windows x86-64 | cross | Windows SDK/UCRT, MSVC-ABI libraries, libc++/compiler-rt as selected by the profile |
| Windows | Windows x86-64 | native | the same target ABI contract and an explicit Windows SDK |
| Windows | Linux x86-64 | cross | an explicit Linux sysroot; never libraries found from the Windows host |

All four cells use the same Python frontend, `bp2cmake`, overlay factory,
CMake source tree, target names, and Ninja build flow. A cell may be enabled in
CI only when its target SDK/sysroot is provisioned. In particular,
Windows-to-Linux must fail at configuration if no Linux sysroot was supplied;
falling back to host headers or libraries is forbidden.

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
8. generated CMake and generated sources live under the preset's binary tree.
9. `RelWithDebInfo` with `-O2` is the default product configuration. Other
   product build types are rejected unless the frontend explicitly enables a
   developer configuration such as `Debug`.
10. no configure-time or generation-time check executes a target binary while
    cross-compiling.
11. the logical shared/static target topology is identical between Linux and
    Windows unless a reviewed manifest records a platform exception.
12. `art-compiler` is always a CMake `SHARED` target.

## Proposed repository layout

The names are illustrative, but ownership boundaries are mandatory:

```text
CMakePresets.json
native/
  CMakeLists.txt                 one product entry point
  cmake/
    Common.cmake                validation and common target policy
    Codegen.cmake               generated-source targets
    Dependencies.cmake          target dependency imports
    PlatformLinux.cmake         Linux semantic mappings
    PlatformWindows.cmake       Windows semantic mappings
    Packaging.cmake             target-tree staging
    toolchains/
      LinuxLLVM.cmake
      WindowsLLVM.cmake
overlay/
  art_port_policy.py            one target-aware overlay factory
tools/
  build_art.py                  one user/CI frontend
  bp2cmake/                     one evaluator and emitter
out/
  <preset>/
    generated/
      art_graph.cmake
      graph_manifest.json
      inputs.sha256
    gensrc/
    stage/
    CMakeCache.txt
    build.ninja
    build_manifest.json
```

Target SDK locations belong in environment variables, command arguments, or an
untracked `CMakeUserPresets.json`; they must not be embedded as
`/home/...` paths in checked-in files.

## One profile, one graph generator, one overlay

### Profile model

`tools/build_art.py` should resolve a typed profile and pass the same profile to
both `bp2cmake` and CMake. At minimum it contains:

```text
profile_id
build_host_os
target_os
target_arch
target_triple
aosp_build_kind = host
sysroot_or_sdk
clang_root
cxx_runtime
compiler_runtime
build_type
root_modules
source_roots
capabilities
```

`build_host_os` controls only executable suffixes, path handling, and host-tool
discovery. `target_os` controls Blueprint selects and target policy. The target
graph for `windows-x86_64` must therefore be the same whether generation runs
on Linux or Windows.

The serialized profile should have separate `build_host` and `target`
sections. `bp2cmake` consumes only the target, AOSP-build-kind, source, and
policy projection. The graph digest excludes build-host paths and uses
normalized relative paths with `/` separators, while the outer build manifest
records the complete build-host/tool environment. This keeps a target graph
host-independent without losing provenance.

The profile should replace independent `--os`, overlay filename, hand-entered
root-module lists, and CMake cache fragments. Command-line overrides are
allowed, but the resolved profile is serialized into the build manifest.

### Overlay factory

Replace two top-level policy objects with one factory, conceptually:

```python
def make_overlay(target: TargetProfile) -> Overlay:
    policy = common_art_policy(target)
    if target.os == "linux":
        policy.merge(linux_policy(target))
    elif target.os == "windows":
        policy.merge(windows_policy(target))
    else:
        raise UnsupportedTarget(target.os)
    return policy.validate()
```

This is one Python overlay module and one schema. It may contain clearly named
Linux and Windows sections, but modules are declared once and refined by
target. A module cannot have unrelated definitions in separate files.

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
- target ABI definitions;
- target system libraries;
- platform compatibility sources;
- linker security mappings; and
- DLL export policy.

The overlay validator should reject conflicting keys, duplicate target names,
an unknown module exception, or a platform override that changes a common
module kind without an explicit `topology_exception` reason. The hard-coded
test/fuzz/benchmark/sample exclusions should move from `bp2cmake.__main__` into
the product profile.

### Deterministic output

`bp2cmake` should write atomically and deterministically to
`out/<preset>/generated/art_graph.cmake`. It should also write a machine-readable
graph manifest containing, for each module:

- Blueprint name and CMake target name;
- module kind;
- normalized, sorted source list;
- public/private includes and definitions;
- generated sources;
- link dependencies; and
- each overlay rule that changed the normalized Blueprint module.

Paths in the generated CMake should use project CMake variables rather than
machine-specific absolute prefixes. The input digest should cover all loaded
`Android.bp`/`sources.bp` files, source-root identities, generator source,
profile, and overlay source.

Generation needs two explicit modes:

- `--write`: atomically replace outputs whose content changed; and
- `--check`: generate in memory and fail if an output or manifest differs.

No generated product CMake snapshot should be committed after migration. CI's
`--check` gate proves that a configured build tree is current instead.

## One CMake entry point

`native/CMakeLists.txt` should be target-neutral. Its order should be:

1. validate the generator, single-config build type, compiler frontend, target
   triple, SDK/sysroot, and LLD selection;
2. load the resolved profile and target dependency manifest;
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

## CMake presets and Ninja

`CMakePresets.json` should use hidden inheritance layers for common Ninja/Clang
policy and target policy, then expose the supported matrix. Suggested preset
names are:

```text
linux-x64-on-linux
windows-x64-on-linux
windows-x64-on-windows
linux-x64-on-windows
```

Each preset has its own `out/<preset>` binary directory. The checked-in preset
contains no developer-specific absolute paths. A user preset supplies
`MDVM_CLANG_ROOT`, `MDVM_TARGET_SYSROOT`, or `MDVM_WINDOWS_SDK_ROOT`.

Every configure preset must set `generator` to exactly `Ninja`. Corresponding
build and test presets inherit the same name. `tools/build_art.py` invokes
`cmake --preset`, `cmake --build --preset --parallel`, and `ctest --preset`;
it must not synthesize a Make, NMake, Visual Studio, or Multi-Config fallback.

The public command shape is identical on both hosts:

```text
python tools/build_art.py configure --preset <matrix-preset>
python tools/build_art.py build     --preset <matrix-preset> --target art-compiler
python tools/build_art.py test      --preset <matrix-preset>
python tools/build_art.py stage     --preset <matrix-preset>
python tools/build_art.py check-generated --preset <matrix-preset>
```

Only the operating system's Python executable spelling may differ. There
should be no `.sh` versus `.bat` product logic split.

The `configure` operation has one fixed sequence: resolve and validate the
profile, run `bp2cmake --write`, invoke the matching CMake configure preset with
the generated-graph/profile paths, then write the build manifest. Calling CMake
directly is an expert/debug flow and requires an already checked generated
graph; it must not trigger a second, subtly different generator implementation.

## LLVM toolchain contract

### Common contract

Both toolchain files must configure:

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
currently does.
That cost is preferable to accidentally introducing a DSO cycle during the
unification migration. In particular, do not make `art.dll` import
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
- target OS/architecture/triple;
- canonical Clang paths and `--version` output;
- CMake and Ninja versions;
- LLD selection;
- SDK/sysroot identity and version/digest;
- C/C++ runtime selection;
- build type and effective optimization/debug policy; and
- generated module topology digest.

The frontend compares the manifest before every configure/build. A mismatch
must require a new preset directory or explicit cache recreation; it must not
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

- use `out/<preset>/bootjar`, never shared `/tmp/bootbuild` state;
- treat javac and D8 failures as fatal;
- declare the selected JDK, R8/D8, Java sources, aconfig inputs, and target
  profile in a manifest;
- write atomically; and
- stage into `out/<preset>/stage` without also copying to unrelated Linux and
  Windows directories.

The boot jar can remain logically shared when its bytecode is deliberately
multi-platform. Its producer and outputs still belong to one preset so a failed
or partial invocation cannot contaminate another target build.

## Migration plan

### Phase 1: freeze and compare current graphs

- Add manifest output and `--check` mode to `bp2cmake`.
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

### Phase 3: introduce one product CMake entry point

- Extract common policy, codegen, dependency imports, platform mappings, and
  staging into focused CMake modules.
- Configure all supported matrix cells through presets and
  `tools/build_art.py`.
- Move Phase-1 probe executables to a test subtree that links the product graph.
- Remove product target/source duplication from verification CMake files.

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
  Ninja Multi-Config; and
- shell-only boot-jar staging with ignored failures and shared `/tmp` output.

Useful probes and result documents should remain. They become tests of the
unified product targets instead of alternative ways to build those targets.

### Phase 6: optimize after parity

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

- `bp2cmake` unit tests pass for both target profiles.
- Generating twice produces no diff and identical digests.
- Linux-host and Windows-host generation of the same target profile produces
  equivalent graph manifests.
- every preset reports exactly `Ninja`, one build type, Clang GNU frontend, the
  intended target triple, and LLD;
- forbidden tool/generator names do not occur in CMake caches or Ninja command
  rules; and
- cross builds contain no undeclared build-host include or library path.

### Command-line audit

Audit `compile_commands.json` and `ninja -t commands` for every matrix cell:

- compile rules start with the configured plain Clang driver;
- C++ and final C++ links use `clang++`;
- shared-library links contain driver-level `-shared` and `-fuse-ld=lld`;
- Linux executable compile/link rules show the expected `-fPIE`/`-pie` result;
- Windows image rules show the required PE ASLR flags through the driver; and
- no rule invokes GCC, G++, MinGW, Clang-CL, CL, Make, NMake, a Visual Studio
  tool, `ld.lld`, or `lld-link` directly.

### Artifact and topology validation

- the common module-kind manifest matches across Linux and Windows except for
  reviewed exceptions;
- Linux produces and loads `libart-compiler.so`;
- Windows produces `art-compiler.dll` and `art-compiler.lib`, and a consumer
  links and loads through the import library;
- LLVM object inspection confirms the target file format, architecture,
  imports/exports, and PIE/ASLR properties;
- staged executables resolve only staged target DSOs plus approved platform
  libraries; and
- the Windows product has no static compiler fallback or cyclic DLL imports.

### Build and runtime validation

- clean `RelWithDebInfo` builds pass for each provisioned matrix cell;
- native Linux and native Windows smoke tests pass;
- cross-built artifacts pass the same smoke tests under an explicit target
  runner where available; no runner is used during configure;
- incremental no-op builds execute no compile/link/generation commands;
- changing an `Android.bp`, overlay rule, codegen input, or target ABI setting
  rebuilds exactly the affected graph/output; and
- boot-jar failure stops the product build and cannot leave a successful-looking
  staged artifact.

## Risks and controls

| Risk | Effect | Control |
|---|---|---|
| Build host leaks into target selection | wrong sources and ABI | one serialized profile; graph equivalence across hosts |
| Cross build finds host headers/libs | links successfully but is invalid | sysroot-only root modes and path audit |
| Literal Linux flag reuse on Windows | ignored options or broken PE link | common semantic properties with platform mapping |
| Export-all hides an incomplete DLL ABI | unstable or missing imports/data | annotations/`.def` allowlist and ABI probe |
| Static fallback masks DLL defects | unequal products | topology validator makes `art-compiler SHARED` mandatory |
| Compiler DSO creates a cycle with `art` | loader/link failure | preserve current aggregate topology first; import graph gate |
| Object-library dedup uses wrong import/export context | invalid Windows objects | defer until symbol ownership is designed and tested |
| Configure executes target helper | cross build fails or uses emulator accidentally | classify host tools; compile target layout with `-S` only |
| Stale generated snapshot | unreviewed source/dependency drift | build-tree generation, digest, and `--check` |
| Stale CMake cache | wrong SDK, flags, or optimization | per-preset directory and build fingerprint |
| Shared `/tmp` boot state | cross-target contamination | preset-local atomic output |

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
explicit and mechanically validated.
