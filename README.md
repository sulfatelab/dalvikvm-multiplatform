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
  docs: win64_art_port.md, win32_filesystem.md, win32_tls_jit_entrypoints.md, win32_open_items.md, win32_libcore_os_natives.md, bp2cmake_linux_scope.md; archived/: git_repo_migrate.md, shared_bootjar_runtime_os_detection.md
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
| ART / libcore base pin | Android tag `android-16.0.0_r4` (ART base `1690c69…`, libcore base `1c599b6…`) |

AOSP-touching changes land on nested `artmp_*` branches. Main records the nested commit
SHA as a gitlink (mode `160000`). Prefer branches over long-lived patch/overlay trees.

## Nested repository map

GitHub naming: `sulfatelab/dalvikvm-multiplatform_<name>` (SSH).

| Path | Nested name | Branch | Pinned SHA (short) |
|------|-------------|--------|--------------------|
| `vendor/art` | `art` | `artmp_android-16.0.0_r4` | `90e063dfcd1b` |
| `vendor/external/boringssl` | `boringssl` | `artmp_android-16.0.0_r4` | `2f815a1e2e77` |
| `vendor/external/cpu_features` | `cpu_features` | `artmp_android-16.0.0_r4` | `6dd8c6baeeff` |
| `vendor/external/dlmalloc` | `dlmalloc` | `artmp_android-16.0.0_r4` | `a46e67742a8c` |
| `vendor/external/fmtlib` | `fmtlib` | `artmp_android-16.0.0_r4` | `59e0c195b177` |
| `vendor/external/lzma` | `lzma` | `artmp_android-16.0.0_r4` | `a54a4227fc88` |
| `vendor/external/oj-libjdwp` | `oj-libjdwp` | `artmp_android-16.0.0_r4` | `d6da5a269a49` |
| `vendor/external/tinyxml2` | `tinyxml2` | `artmp_android-16.0.0_r4` | `457bf28c570c` |
| `vendor/icu` | `icu` | `artmp_android-16.0.0_r4` | `f0b56faf06b0` |
| `vendor/java-external/bouncycastle` | `bouncycastle` | `artmp_android-16.0.0_r4` | `bcb46fde6479` |
| `vendor/java-external/conscrypt` | `conscrypt` | `artmp_android-16.0.0_r4` | `1d3f90421247` |
| `vendor/java-external/fdlibm` | `fdlibm` | `artmp_android-16.0.0_r4` | `3712afa2cd33` |
| `vendor/java-external/okhttp` | `okhttp` | `artmp_android-16.0.0_r4` | `788860d05111` |
| `vendor/libbase` | `libbase` | `artmp_android-16.0.0_r4` | `e914db1d758c` |
| `vendor/libcore` | `libcore` | `artmp_android-16.0.0_r4` | `73fd5f198807` |
| `vendor/libnativehelper` | `libnativehelper` | `artmp_android-16.0.0_r4` | `edb7a45e81bb` |
| `vendor/libprocinfo` | `libprocinfo` | `artmp_android-16.0.0_r4` | `1c617ca29fb6` |
| `vendor/libziparchive` | `libziparchive` | `artmp_android-16.0.0_r4` | `a710e1e46346` |
| `vendor/logging` | `logging` | `artmp_android-16.0.0_r4` | `c29f3eeaa37e` |
| `vendor/unwinding` | `unwinding` | `artmp_android-16.0.0_r4` | `3012b1dca8e3` |

Pinned SHAs above are the values recorded at first main commit of this multiplatform tree.
Update them by committing inside the nested repo, then `git add <path>` on main.

## Host toolchain notes (not shipped here)

- **Compiler:** native Clang/LLVM + `lld` (no MSVC `cl`, no MinGW as primary).
- **Windows SDK headers/libs:** MSVC SDK content via `xwin` / `win64-dev-env` (headers from the SDK; not the MSVC compiler).
- **64-bit only** for the WinNT/Win64 port.
- **Wine64** optional for Linux-hosted PE smoke gates.
- **C++ runtime for PE:** libc++ / compiler-rt as documented in `win64_art_port.md`.

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

## Migration plan

See [archived/git_repo_migrate.md](archived/git_repo_migrate.md) for the full nested-repo / de-overlay plan,
push order, and checklist. Sibling tree `../dalvikvm-linux` remains a local fallback until
multiplatform gates are fully proven.

## Push order (after GitHub repos exist)

1. Push each nested `artmp_android-16.0.0_r4` to `dalvikvm-multiplatform_<name>`.
2. Push main with matching gitlinks.

Do not push from agent automation unless explicitly asked; prefer SSH agent on the operator machine.
