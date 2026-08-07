# dalvikvm-multiplatform

ART / Dalvik multiplatform product tree for **GNU/Linux** and **Win32 on x64**.

This repository is the single entrypoint: a recursive clone yields **all project-controlled
source dependencies** needed to build and test ART on those hosts. Host toolchains
(Clang/LLVM, Windows SDK headers via xwin/windows_x64-dev-env, optional Wine for PE gates)
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
    external/{boringssl,cpu_features,dlmalloc,fmtlib,lzma,oj-libjdwp,tinyxml2,vixl}/
    java-external/{bouncycastle,conscrypt,fdlibm,okhttp}/
    r8/r8.jar                 # prebuilt D8/R8 (not a nested repo)
    external/fmtlib            # canonical path; legacy alias is not required
  compat/
    include/                  # product POSIX/Win prelude headers (kept on main)
    java-stubs/ openjdk_fdlibm/ src/
  tools/                      # portable build/provision/audit frontends
  tests/                      # target-aware probes, host checks, records
  overlay/                    # port policies
  docs/
    history/                  # completed migration/design records
    windows-port-notes/       # audited Windows bring-up knowledge
  *.md                        # project documentation; see Documentation map
```

### Folded Windows sources (no main `compat/windows/{art,libcore}`)

| Former product overlay | Nested home (`artmp_*`) |
|------------------------|-------------------------|
| `compat/windows/art/*_windows.cc` | `vendor/art/runtime/multiplatform/windows/` |
| `openjdkjvm_memory_windows.cc` | `vendor/art/openjdkjvm/` |
| Windows x64 build stubs | `vendor/art/multiplatform/windows/` |
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

Product forks use `sulfatelab/dalvikvm-multiplatform_<name>` over SSH. The
unmodified VIXL dependency is pinned directly from the official AOSP repository.

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
| `vendor/external/vixl` | `vixl` | official `android-16.0.0_r4` pin |
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

## Supported Windows x64 toolchain and ABI

Windows artifacts are built with this selected toolchain:

- **Compiler driver:** LLVM `clang` / `clang++`.
- **Linker:** LLVM LLD selected by Clang with `-fuse-ld=lld` (the build does
  not invoke `lld-link` as a separate driver).
- **Platform headers and import libraries:** Windows SDK and MSVC SDK content,
  provisioned in a regular-file target bundle bound to the canonical target
  ID in `.art-build.local.toml`.
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
[win32_art_port.md](win32_art_port.md) for the complete toolchain and platform
design.

## Windows x64 process mitigation requirement

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

## Unified product frontend

```text
python tools/build_art.py init-local-config
python tools/build_art.py configure --target-id linux-x86_64-gnu
python tools/build_art.py audit --target-id linux-x86_64-gnu
python tools/build_art.py build --target-id linux-x86_64-gnu --cmake-target dalvikvm
python tools/build_art.py stage --target-id linux-x86_64-gnu
python tools/build_art.py clean --target-id linux-x86_64-gnu
```

Use `windows-x86_64-msvc` with the same commands after binding its target bundle
in the ignored `.art-build.local.toml`. Configure, build, and stage run the
same generated-command audit automatically; `audit` exposes it as a focused
gate. Linux x86-64 currently has nine runnable catalog gates and three
compile-only artifacts. Experimental `linux-aarch64-gnu` uses the same
frontend after binding its sysroot/runtime roots and an exact `qemu-aarch64`
executable under `[target_runners]` in the ignored TOML. Its current W-004
scope is intentionally only imageless Hello plus show-version; an emulator
binding does not broaden any other test selector. Retained historical shell
scripts are not product build entry points and are not required on a native
Windows host. `clean` removes only the selected target/build/variant directory,
requires a matching frontend ownership manifest, preserves siblings, and is a
successful no-op when that exact tree does not exist. It uses Python filesystem
APIs and remains available for recognized targets whose generation status is
currently unavailable. When `--parallel` is omitted, `build` and `test` use 32
jobs on non-Windows hosts and 16 on Windows hosts; Windows rejects higher
values to protect the 16 GiB native VM. The resolved value is applied to both
direct builds and Ninja work requested by `test`. CTest execution stays at one
scheduler slot because several runtime gates are memory-heavy or process-wide.

## Continuous integration

The checked-in `Unified ART build` workflow runs four self-hosted cells through
`tools/ci_art.py`: host contracts, the Linux product, a Linux-hosted Windows
cross build, and the native Windows product/catalog. Product cells always use
a fresh `out/ci/<run-key>/<cell>` root, verify deterministic generation, build
twice to require a Ninja no-op, and stage the audited regular-file package.
Linux and Windows native cells also run their applicable test catalogs.

Each runner service must define `ART_BUILD_CI_CONFIG` as the absolute path of a
regular machine-local TOML file outside the checkout. It uses the same schema
as `.art-build.local.toml` and overrides matching developer-local bindings;
the workflow supplies `ART_BUILD_CI_RUN_KEY`. No real toolchain, SDK, bundle,
or output path is stored in Git. Private sibling submodules require the
`ART_CI_CHECKOUT_TOKEN` repository secret until an equivalent read credential
is configured for the runner.

## Documentation map

These root documents are part of the project context. Automated and LLM-based
work should read the relevant design document before changing the corresponding
subsystem. [unified_art_build.md](unified_art_build.md) is the authoritative
build-refactor tracker, while [win32_open_items.md](win32_open_items.md) tracks
Windows runtime-port work.

| Document | Purpose |
|----------|---------|
| [unified_art_build.md](unified_art_build.md) | Live unified build-system refactor tracker, closed target identity model, test applicability, and acceptance contract |
| [bp2cmake_linux_scope.md](bp2cmake_linux_scope.md) | Historical Linux scope, Android.bp-to-CMake converter design, and Linux native/runtime bring-up record |
| [win32_art_port.md](win32_art_port.md) | Overall native Windows x64 architecture, toolchain policy, phased implementation record, and current platform position |
| [win32_filesystem.md](win32_filesystem.md) | Implemented Option H Windows path/filesystem model, mixed-path rules, classpath separator policy, and NIO.2 boundary |
| [win32_faults_and_stacks.md](win32_faults_and_stacks.md) | Authoritative W-010/W-014 design for Windows x64 VEH/sigchain adaptation, implicit managed faults, stack bounds/protection, and the required CET-shadow-stack-disabled process contract |
| [win32_aot_oat.md](win32_aot_oat.md) | Early boot-only Windows AOT design: Linux-identical ART ELF identity, 64-KiB Windows artifact alignment, the implemented low-divergence private-copy baseline, the conditional OAT-2 replacement candidate, LZ4 boot-image strategy, unwind/CFG transports, and acceptance gates |
| [win32_aot_oat_tracker.md](win32_aot_oat_tracker.md) | Live Windows AOT/OAT implementation sequence, accepted W-028 through W-032 evidence, per-generation cache-set integrity, and remaining unwind/dispatch/CFG-allocation/product-integration work |
| [win32_heap_memory.md](win32_heap_memory.md) | Closed W-013 design for ART-owned virtual memory, embedded dlmalloc, MoreCore, low-address policy, and native acceptance |
| [win32_jit_memory.md](win32_jit_memory.md) | Current Windows x64 JIT memory design, unnamed pagefile-section dual view, historical failure analysis, and W-025 residual work |
| [win32_libcore_os_natives.md](win32_libcore_os_natives.md) | Current implementation map for Windows x64 `libcore.io.Linux`/Os natives, including implemented and intentional ENOSYS methods |
| [win32_open_items.md](win32_open_items.md) | Living authoritative tracker for open workarounds, product gaps, host-validation gaps, non-goals, and closed-item history |
| [win32_tls_jit_entrypoints.md](win32_tls_jit_entrypoints.md) | Implemented x86_64 TLS, managed ABI, quick invoke, nterp, and native/managed JIT contracts; interaction with the separate managed-fault/stack design; notes for other ISAs |

## Migration history

See [docs/history/git_repo_migrate.md](docs/history/git_repo_migrate.md) for the
completed nested-repository and de-overlay plan, push order, and checklist.

## Push order (after GitHub repos exist)

1. Push each nested `artmp_android-16.0.0_r4` to `dalvikvm-multiplatform_<name>`.
2. Push main with matching gitlinks.

Do not push from agent automation unless explicitly asked; prefer SSH agent on the operator machine.
