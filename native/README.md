# native — top-level build for `dalvikvm`

Single entry point for the minimal ART runtime native build on GNU/Linux (glibc).
Builds the whole `dalvikvm` graph (18 targets) from the archive's `Android.bp`
via the bp2cmake converter — no hand-written per-module CMake.

## Build

```sh
./generate.sh          # Android.bp -> generated/dalvikvm.cmake (run after a
                       # submodule bump or overlay change)
cmake -S native -B build/native -G Ninja \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build/native
LD_LIBRARY_PATH=build/native build/native/dalvikvm -showversion
# -> ART version 2.1.0 x86_64
```

Requirements: clang (mandatory — ART uses clang-only flags). **Build type:
RelWithDebInfo** — ART must be -O2; `Release` here is `-O3` which miscompiles ART
(the VM misbehaves), and `Debug`'s GC is unusably slow. Also: host dev packages
`libcap-dev` + `liblz4-dev`, and a checkout of the AOSP sources at
`../MinDalvikVM-Archive/native` (override with `-DMDVM_NATIVE_SRC_ROOT_DIR=...`
or `MDVM_NATIVE_SRC_ROOT` for generate.sh).

## What's hand-written vs generated

- `CMakeLists.txt` — the ONLY hand-written CMake: project-owned glue the
  converter can't derive (host imported libs z/cap/lz4, the Python codegen
  driver invocation, and toolchain-drift shims for the 2023 sources under
  clang-21). All clearly fenced and documented inline.
- `generated/dalvikvm.cmake` — every target, emitted by `bp2cmake
  --root-module dalvikvm` (transitive dependency closure, deps-first).

## How it maps to the converter's 3 layers

`generate.sh` runs Layer 1 (parse/evaluate `.bp`) + Layer 2 (`//overlay`) +
Layer 3 (emit). The dependency closure (`bp2cmake/closure.py`) walks the link
graph from `dalvikvm` so the module list is derived, not maintained by hand —
a submodule bump just needs `./generate.sh` + rebuild.

The per-module harnesses under `tools/verify/*` remain as focused regression
checks / RESULT records; this is the real build.
