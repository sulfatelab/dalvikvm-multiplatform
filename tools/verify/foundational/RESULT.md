# Foundational libraries validation — result

Date: 2026-06-20. Toolchain: clang/clang++ 21, cmake 4.2, ninja 1.13.
Source baseline: MinDalvikVM-Archive native tree (2023 AOSP pins).

## What was validated

bp2cmake converted all 8 foundational libraries (the ones the archive's
top-level CMakeLists builds before art/ and javacorenatives/) from their
Android.bp, and they compile AND link together — with the real converted liblog,
no stub:

| target | kind | size | links |
|--------|------|------|-------|
| base | shared | 1.1M | log |
| log | shared | 61K | (none) |
| nativehelper | shared | 37K | log |
| procinfo | shared | 53K | base |
| ziparchive | shared | 406K | base, log, host zlib |
| tinyxml2 | shared | 153K | (none) |
| lzma | shared | 234K | (none) |
| cpu_features | static | 65K | (absorbs utils) |

Cross-lib linkage confirmed via NEEDED entries (e.g. libziparchive.so ->
libbase.so + liblog.so + libz.so.1).

## Port decisions added to the overlay this round (each with a why)

- **liblog**: drop logprint.cpp + event_tag_map.cpp (need Android libcutils/
  libutils headers; matches archive's write-only liblog — audit 5.2 item 4).
- **libnativehelper**: force c_std gnu11 (strict c11 hides glibc strerror_r;
  Soong's bionic toolchain built gnu-mode so it never bit on Android).
- **libtinyxml2**: drop liblog dep + do NOT set -DDEBUG/-DANDROID_NDK (archive
  wrongly force-enabled the android logcat path on Linux — audit 5.4).
- **libcpu_features**: STATIC, absorb the 3-module split, force
  HAVE_STRONG_GETAUXVAL + HAVE_DLFCN_H (bionic-only in .bp; true on glibc too).
- **libziparchive**: point at //compat for gtest/gtest_prod.h (FRIEND_TEST only;
  we vendor no googletest).

## Converter features added this round

- cpp_std / c_std handling (model + evaluator + emitter -> -std= per language).
- set_c_std / set_cpp_std overlay overrides.
- Project-owned compat include root (${MDVM_COMPAT_INCLUDE_DIR}, //compat) for
  vendored shim headers, kept separate from the read-only AOSP tree. First
  occupant: gtest/gtest_prod.h.

## Environment findings (NOT converter defects; see toolchain-drift memory)

- clang mandatory (clang-only warning flags).
- Per-file <cstdint> drift: hex.cpp (libbase), process.cpp (libprocinfo). Shim
  scoped per-file in the harness only. Vanishes on submodule bump.

## Reproduce

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake \
    --root /home/agent/Projects/MinDalvikVM-Archive/native \
    --overlay overlay/port_policy.py \
    --module liblog --module libnativehelper --module libprocinfo \
    --module libziparchive --module libtinyxml2 --module liblzma \
    --module libcpu_features --module libbase \
    --out tools/verify/foundational/foundational.cmake
cmake -S tools/verify/foundational -B /tmp/vf -G Ninja \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build /tmp/vf
```
