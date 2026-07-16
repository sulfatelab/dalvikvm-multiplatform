# libart (runtime) + dalvikvm — result: COMPLETE, runnable VM

Date: 2026-06-20. Toolchain: clang 21, cmake 4.2, ninja 1.13, python 3.14.

## Outcome: SUCCESS

The full ART native build is generated end-to-end by the bp2cmake converter from
Android.bp and produces a WORKING dalvikvm:

    $ LD_LIBRARY_PATH=. ./dalvikvm -showversion
    ART version 2.1.0 x86_64        # exit 0

- `dalvikvm` (PIE executable, 136 KB Release) links the full 19-module graph.
- `libart.so` (~100 MB Release) builds with all 237 sources, 30 operator_out
  generated files, mterp_x86_64.S (8868 lines), asm_defines.h (188 defines), and
  5 assembled .S entrypoint objects.
- Runs, initializes ART, parses args, prints usage + version.

## The one authorized source change

`art/runtime/art_method-inl.h` `FillVRegs` terminal overload: removed its value
parameters (kept the `char... ArgType` template) so it differs in arity from the
recursive overload for any non-empty pack. This resolves the clang>=17
variadic-overload ambiguity (a hard error; ShortyTraits<>::Type is a non-deduced
context so partial ordering couldn't disambiguate). Behavior-preserving: the
terminal case took no value args anyway. This was the ONLY edit to the read-only
archive, authorized by the user.

## Converter improvements this milestone

- whole_static_libs absorption is now RECURSIVE (cpu_features ->
  cpu_features-utils; their CpuFeatures_*/StackLineReader_* symbols were missing
  with one-level absorption). _link_libs skips the transitive set too.
- `:name` Soong module-ref sources skipped (e.g. :libart_mterp.x86_64ng).
- compile-def values with shell-special chars quoted (ART_BASE_ADDRESS_MIN_DELTA
  =(-0x1000000)).
- absorbed whole_static sources carry the absorbed module's own cflags
  (per-source COMPILE_OPTIONS).
- overlay: add_ldflags + global drop_ldflags/drop_ldflags_containing; executable
  kind; absorb_whole_static=False option (dalvikvm links libsigchain rather than
  inlining sigchain.cc, which lacked the CHAR_BIT define).
- libdexfile absorbs external/dex_file_supp.cc so art_api::dex::g_ADexFile_*
  resolve (libunwindstack needs them; we dropped libdexfile_support -- audit).

## Build wiring notes

- ASM language: the harness project() must list ASM, and per-target prelude
  force-includes are scoped `$<$<COMPILE_LANGUAGE:C,CXX>:...>` so the .S files
  (quick_entrypoints, mterp, AsmGetRegs) are NOT fed C headers via -include.
- Build Release (-DCMAKE_BUILD_TYPE=Release): in Debug, ART's globals_unix.cc
  expects the `d`-suffixed debug libs (libartbased.so) which we don't build.

## Toolchain-drift shims (harness only; vanish on submodule bump)

prelude force-include (stdint/stddef/algorithm), strlcpy via ANDROID_HOST_MUSL
(glibc 2.38 now declares it), -Wno-strict-primary-template-shadow. All scoped to
C/CXX, none in the converter/overlay.

## Reproduce

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake \
    --root /home/agent/Projects/MinDalvikVM-Archive/native \
    --overlay overlay/port_policy.py \
    --module liblog ... --module libart --module dalvikvm \
    --out tools/verify/runtime/runtime.cmake
cmake -S tools/verify/runtime -B /tmp/vrt -G Ninja \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/vrt
LD_LIBRARY_PATH=/tmp/vrt /tmp/vrt/dalvikvm -showversion   # ART version 2.1.0 x86_64
```
