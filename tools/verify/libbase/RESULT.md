# libbase prototype validation — result

Date: 2026-06-20. Toolchain: clang/clang++ 21, cmake 4.2, ninja 1.13.
Source baseline: MinDalvikVM-Archive native tree (2023 AOSP pins).

## What was validated

The bp2cmake converter (Layer 1 evaluator + Layer 2 overlay + Layer 3 emitter)
was run on the archive's `native/libbase/Android.bp`. The generated
`libbase.cmake` was compiled and linked in isolation (with a stub `log`).

Result: **PASS**. All 18 translation units compile; `libbase.so` (1.1 MB) links
and exports the real `android::base::*` API; `liblog.so` is correctly NEEDED.

## Generated output vs the archive's hand-written libbase.cmake

Matches the archive's intent, and is MORE correct in two audited spots:

1. Includes `errors_unix.cpp` (archive dropped it — audit 5.4 bug). Comes for
   free from Layer 1's `target.linux` resolution.
2. Applies `-Wall -Wextra` to all languages, not only C TUs (archive applied
   them only to C though libbase is all C++ — audit 5.4 bug).

Deliberate Layer 2 decisions reproduced: force SHARED, fmtlib whole_static
inlined as `src/format.cc`, drop `-Werror` globally, re-add
`-D_FILE_OFFSET_BITS=64` on Linux, name map libbase->base / liblog->log.

## Two environment findings (NOT converter defects)

Both are 2023-source vs 2026-toolchain drift and vanish on submodule update:

1. **clang required.** `-Wexit-time-destructors` / `-Wthread-safety` are
   clang-only; g++ cannot build ART. The build now hard-errors if the compiler
   is not Clang (matches the archive forcing -DCMAKE_C_COMPILER=clang).
2. **`hex.cpp` needs `<cstdint>`.** clang-21/newer-libc++ stopped transitively
   including it. Worked around with a `-include cstdint` shim scoped to that one
   file IN THIS HARNESS ONLY (a global -include would precede
   posix_strerror_r.cpp's deliberate `#undef _GNU_SOURCE`). Not in bp2cmake, not
   in the overlay.

## Reproduce

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake \
    --root /home/agent/Projects/MinDalvikVM-Archive/native \
    --overlay overlay/port_policy.py --module libbase \
    --out tools/verify/libbase/libbase.cmake
cmake -S tools/verify/libbase -B /tmp/vb -G Ninja \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build /tmp/vb
```
