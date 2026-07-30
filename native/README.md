# native — ART product entry point

The maintained product entry point is driven by `tools/build_art.py` for Linux
and Windows. It generates a target-resolved graph from nested `vendor/`
`Android.bp` files, then configures this directory with CMake's Ninja generator.
There is no host-specific shell or Make workflow.

## Build

```text
python tools/build_art.py configure --target-id linux-x86_64
python tools/build_art.py build --target-id linux-x86_64 --cmake-target dalvikvm
python tools/build_art.py test --target-id linux-x86_64
# -> ART version 2.1.0 x86_64
```

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
