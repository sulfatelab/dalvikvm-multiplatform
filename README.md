# dalvikvm-multiplatform

ART / Dalvik multiplatform product tree for **GNU/Linux** and **Windows (Win64)**.

This repository is the single entrypoint: a recursive clone yields **all project-controlled
source dependencies** needed to build and test ART on those hosts. Host toolchains
(Clang/LLVM, Windows SDK headers via xwin/win64-dev-env, optional Wine for PE gates)
remain machine-local and are documented separately.

## Clone

```bash
git clone --recursive git@github.com:sulfatelab/dalvikvm-multiplatform.git
cd dalvikvm-multiplatform
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

> Local development treats `vendor/*` as **full nested git repositories**.  
> `.gitmodules` + gitlinks make `git clone --recursive` materialize them as submodules.

## Layout

```text
dalvikvm-multiplatform/
  vendor/
    art/ libcore/ libbase/ libnativehelper/ libprocinfo/
    libziparchive/ logging/ unwinding/ icu/
    external/{boringssl,cpu_features,dlmalloc,fmtlib,lzma,oj-libjdwp,tinyxml2}/
    java-external/{bouncycastle,conscrypt,fdlibm,okhttp}/
    r8/r8.jar                 # prebuilt D8/R8 (not a nested repo)
    fmtlib -> external/fmtlib # layout shim for generated CMake paths
  compat/
    include/                  # product POSIX/Win prelude headers (kept on main)
    java-stubs/ openjdk_inc/ src/
  tools/                      # bp2cmake, bootjar, win64, verify gates
  overlay/                    # port policies
  *.md                        # project documentation; see Documentation map
  archived/                   # completed migration/design records
```

### Folded Windows sources (no main `compat/windows/{art,libcore}`)

| Former product overlay | Nested home (`artmp_*`) |
|------------------------|-------------------------|
| `compat/windows/art/*_windows.cc` | `vendor/art/runtime/multiplatform/windows/` |
| `openjdkjvm_memory_windows.cc` | `vendor/art/openjdkjvm/` |
| Win64 build stubs | `vendor/art/multiplatform/windows/` |
| WinNT FileSystem / properties | `vendor/libcore/ojluni/...` + `vendor/libcore/multiplatform/windows/` |

`compat/include` (and product stubs) stay on **main**.

## Branch policy

| Kind | Name |
|------|------|
| Nested product branch | `artmp_android-16.0.0_r4` |
| Main default | `main` |

AOSP-touching changes land on nested `artmp_*` branches. Main tracks the
nested repositories as gitlinks (mode `160000`). Prefer branches over
long-lived patch/overlay trees.

## Nested repository map

GitHub naming: `sulfatelab/dalvikvm-multiplatform_<name>` (SSH).

| Path | Nested name | Branch |
|------|-------------|--------|
| `vendor/art` | `art` | `artmp_android-16.0.0_r4` |
| `vendor/external/boringssl` | `boringssl` | `artmp_android-16.0.0_r4` |
| `vendor/external/cpu_features` | `cpu_features` | `artmp_android-16.0.0_r4` |
| `vendor/external/dlmalloc` | `dlmalloc` | `artmp_android-16.0.0_r4` |
| `vendor/external/fmtlib` | `fmtlib` | `artmp_android-16.0.0_r4` |
| `vendor/external/lzma` | `lzma` | `artmp_android-16.0.0_r4` |
| `vendor/external/oj-libjdwp` | `oj-libjdwp` | `artmp_android-16.0.0_r4` |
| `vendor/external/tinyxml2` | `tinyxml2` | `artmp_android-16.0.0_r4` |
| `vendor/icu` | `icu` | `artmp_android-16.0.0_r4` |
| `vendor/java-external/bouncycastle` | `bouncycastle` | `artmp_android-16.0.0_r4` |
| `vendor/java-external/conscrypt` | `conscrypt` | `artmp_android-16.0.0_r4` |
| `vendor/java-external/fdlibm` | `fdlibm` | `artmp_android-16.0.0_r4` |
| `vendor/java-external/okhttp` | `okhttp` | `artmp_android-16.0.0_r4` |
| `vendor/libbase` | `libbase` | `artmp_android-16.0.0_r4` |
| `vendor/libcore` | `libcore` | `artmp_android-16.0.0_r4` |
| `vendor/libnativehelper` | `libnativehelper` | `artmp_android-16.0.0_r4` |
| `vendor/libprocinfo` | `libprocinfo` | `artmp_android-16.0.0_r4` |
| `vendor/libziparchive` | `libziparchive` | `artmp_android-16.0.0_r4` |
| `vendor/logging` | `logging` | `artmp_android-16.0.0_r4` |
| `vendor/unwinding` | `unwinding` | `artmp_android-16.0.0_r4` |

## Supported Win64 toolchain and ABI

Windows artifacts are built with this selected toolchain:

- **Compiler driver:** LLVM `clang` / `clang++`.
- **Linker:** LLVM `lld` / `lld-link`.
- **Platform headers and import libraries:** Windows SDK and MSVC SDK content,
  typically provisioned through `xwin` and `win64-dev-env`.
- **C++ standard library/STL:** LLVM `libc++`; LLVM `compiler-rt` supplies
  target runtime support.
- **Target:** 64-bit PE/COFF using the Microsoft x64 ABI
  (`x86_64-pc-windows-msvc`).

Using the Microsoft ABI does not mean using the MSVC compiler. The following
compiler/ABI paths are unsupported:

- `cl.exe` and the MSVC C/C++ compiler toolset;
- `clang-cl`;
- `clang-mingw`, MinGW GCC, or other MinGW compiler distributions;
- the MinGW/`windows-gnu` ABI and `x86_64-w64-windows-gnu` target.

Wine64 is optional for Linux-hosted PE development gates, but native Windows
evidence is required for product acceptance. See
[win64_art_port.md](win64_art_port.md) for the complete toolchain and platform
design.

## Win64 process mitigation requirement

Current x86_64 ART does not support Windows CET user shadow stacks, exposed by
Windows as Hardware-enforced Stack Protection. All defined shadow-stack,
audit, context-IP-validation, strict, and non-CET-binary policy fields must be
disabled for the entire `dalvikvm` or embedding process before it starts. The
startup guard classifies the named Windows SDK fields: it permits
`CetDynamicApisOutOfProcOnly`, which does not enable HSP, and does not assign
meaning to `ReservedFlags`. CFG is separate and is not equivalent to CET
shadow stacks. The exact contract is documented in
[win32_faults_and_stacks.md](win32_faults_and_stacks.md).

## Native source root

Build harnesses default `MDVM_NATIVE_SRC_ROOT_DIR` to **`vendor/`** in this
repo (nested multipath sources). Product CMake graphs are pure-vendor (L-006):
they must not require a sibling MinDalvikVM-Archive tree.

## Quick product scripts

```bash
# Build classes for the single shared Linux+Win64 multipath boot.jar
tools/bootjar/build.sh

# Recompile the shared OS-selection anchors, dex, and stage the same jar for both hosts
tools/bootjar/build_win64.sh

# Win64 phase1 CMake (cross from Linux; needs win64-dev-env)
# tools/verify/win64_phase1/CMakeLists.txt
```

## Documentation map

These root documents are part of the project context. Automated and LLM-based
work should read the relevant design document before changing the corresponding
subsystem; [win32_open_items.md](win32_open_items.md) is the authoritative
current-work tracker.

| Document | Purpose |
|----------|---------|
| [bp2cmake_linux_scope.md](bp2cmake_linux_scope.md) | Historical Linux scope, Android.bp-to-CMake converter design, and Linux native/runtime bring-up record |
| [win64_art_port.md](win64_art_port.md) | Overall native Win64 architecture, toolchain policy, phased implementation record, and current platform position |
| [win32_filesystem.md](win32_filesystem.md) | Implemented Option H Windows path/filesystem model, mixed-path rules, classpath separator policy, and NIO.2 boundary |
| [win32_faults_and_stacks.md](win32_faults_and_stacks.md) | Authoritative W-010/W-014 design for Win64 VEH/sigchain adaptation, implicit managed faults, stack bounds/protection, and the required CET-shadow-stack-disabled process contract |
| [win32_heap_memory.md](win32_heap_memory.md) | Closed W-013 design for ART-owned virtual memory, embedded dlmalloc, MoreCore, low-address policy, and native acceptance |
| [win32_jit_memory.md](win32_jit_memory.md) | Current Win64 JIT memory design, unnamed pagefile-section dual view, historical failure analysis, and W-025 residual work |
| [win32_libcore_os_natives.md](win32_libcore_os_natives.md) | Current implementation map for Win64 `libcore.io.Linux`/Os natives, including implemented and intentional ENOSYS methods |
| [win32_open_items.md](win32_open_items.md) | Living authoritative tracker for open workarounds, product gaps, host-validation gaps, non-goals, and closed-item history |
| [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) | Implemented x86_64 TLS, managed ABI, quick invoke, nterp, and native/managed JIT contracts; interaction with the separate managed-fault/stack design; notes for other ISAs |

## Migration history

See [archived/git_repo_migrate.md](archived/git_repo_migrate.md) for the
completed nested-repository and de-overlay plan, push order, and checklist.

## Push order (after GitHub repos exist)

1. Push each nested `artmp_android-16.0.0_r4` to `dalvikvm-multiplatform_<name>`.
2. Push main with matching gitlinks.

Do not push from agent automation unless explicitly asked; prefer SSH agent on the operator machine.
