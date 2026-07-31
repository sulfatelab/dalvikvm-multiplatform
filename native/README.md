# native — ART product entry point

The maintained product entry point is driven by `tools/build_art.py` for Linux
and Windows. It generates a target-resolved graph from nested `vendor/`
`Android.bp` files, then configures this directory with CMake's Ninja generator.
There is no host-specific shell or Make workflow.

## Build

```text
python tools/build_art.py configure --target-id linux-x86_64-gnu
python tools/build_art.py build --target-id linux-x86_64-gnu --cmake-target dalvikvm
python tools/build_art.py stage --target-id linux-x86_64-gnu
# -> ART version 2.1.0 x86_64
```

The Linux product currently has no applicable runnable catalog entries, so its
`test` command fails explicitly instead of treating an empty CTest selection as
success. Runnable Linux gates remain tracked migration work.

The same commands configure `windows-x86_64-msvc` when its target bundle is bound
in `.art-build.local.toml` under `[targets."windows-x86_64-msvc"]`. The bundle must
contain regular-file Windows SDK/UCRT, libc++, compiler-rt, zlib, lz4, and
CRT components. The LZ4 bundle must include both `lz4.h` and `lz4hc.h`;
expat is built from the pinned repository source. CMake never falls back to
host libraries.

On a native target host, compatible target-platform/target-architecture
matching enables runnable probes.
For example, this builds the virtual stage and runs its registered tests:

```text
python tools/build_art.py test --target-id windows-x86_64-msvc --stage w002
```

Cross builds still compile every selected probe but do not attempt to execute
target binaries. An empty CTest selection is an error, not a successful test.
Staging copies the complete top-level DSO closure and the pinned Windows
`c++.dll`; all staged files are regular files recorded with SHA-256 hashes.

The default build type is `RelWithDebInfo`. Required host tools are Python 3.11+,
CMake, Ninja, and the plain Clang/Clang++ GNU-style drivers; LLD is selected by
the generated target properties. Machine-specific SDK or sysroot roots belong
in the ignored repository-root `.art-build.local.toml`.

## What's hand-written vs generated

- `CMakeLists.txt` — the only maintained product CMake: project-owned glue the
  converter can't derive (host imported libs z/cap/lz4, the Python codegen
  driver invocation, and toolchain-drift shims for the 2023 sources under
  clang-21). All clearly fenced and documented inline.
- `out/<target-id>/<build-type>/generated/art_graph.cmake` — every target,
  emitted by `bp2cmake` (transitive dependency closure, deps-first).

## How it maps to the converter's 3 layers

The frontend runs Layer 1 (parse/evaluate `.bp`) + Layer 2 (target-aware
overlay) + Layer 3 (emit). The dependency closure (`bp2cmake/closure.py`)
walks the link graph from the product roots so the module list is derived, not
maintained by hand.

The per-module harnesses under `tools/verify/*` remain as focused regression
checks / RESULT records; this is the real build.
