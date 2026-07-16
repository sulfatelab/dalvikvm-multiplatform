# libartbase — result (ART core with generated sources + art.go defines)

Date: 2026-06-20. Toolchain: clang 21, cmake 4.2, ninja 1.13, python 3.14.

## What was validated

`libartbase` (`art_cc_library`) converted from Android.bp, built, and linked:
`libartbase.so` (2.9 MB) NEEDs libziparchive/libartpalette/libbase/libz/liblog/
libcap. This is the first module exercising the FULL ART machinery:

- **gensrcs pipeline**: the 3 `art_libartbase_operator_srcs` headers are run
  through `generate_operator_out.py` via add_custom_command; the resulting
  .operator_out.cc files compile into the lib. Confirmed: the generated symbol
  `art::operator<<(ostream&, art::InstructionSet)` is present in libartbase.so.
- **art.go-injected PUBLIC defines**: ART_STACK_OVERFLOW_GAP_* (=8192) and
  ART_FRAME_SIZE_LIMIT (=1736) — in NO .bp (audit 5.1) — supplied via the
  overlay as PUBLIC so consumers including instruction_set.h also see them.
- **soong_config / codegen / avx2 selects** (from the prior checkpoint).

## Converter features added this round

- **gensrcs support** (model.GenSrcs + evaluator.resolve_gensrcs/tool_script +
  emitter add_custom_command). Key fix: pass $(in) as a tree-RELATIVE path
  (WORKING_DIRECTORY = tree root) because generate_operator_out strips the
  reldir to compute the emitted #include; an absolute path mangled it.
- **PUBLIC define channel** (overlay.add_public_defines -> target_compile_
  definitions PUBLIC), so Go knobs propagate to consumers via link deps.

## Host prerequisite installed

- `libcap-dev` (apt) — libartbase's base/utils.cc uses capget/capset; AOSP
  static_libs libcap. Mapped to the host libcap in the harness.

## Toolchain-drift shims (harness only; NOT converter/overlay)

clang-21 vs 2023 sources, all vanish on submodule bump:
- libbase/hex.cpp: -include cstdint (uint8_t)
- libartbase/base/metrics/metrics_common.cc: -include algorithm (std::all_of)
- libartbase/base/{file_utils,utils}.cc: -Wno-strict-primary-template-shadow
  (stl_util.h's `Filter` shadows a template param -- a hard error in clang-21,
  only a warning when written)

## Reproduce

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake \
    --root /home/agent/Projects/MinDalvikVM-Archive/native \
    --overlay overlay/port_policy.py \
    --module liblog --module libbase --module libartpalette \
    --module libziparchive --module libartbase \
    --out tools/verify/artbase/artbase.cmake
cmake -S tools/verify/artbase -B /tmp/va -G Ninja \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build /tmp/va
```
