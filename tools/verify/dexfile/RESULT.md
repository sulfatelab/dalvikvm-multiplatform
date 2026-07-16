# libdexfile — result (PUBLIC-define propagation across link boundary)

Date: 2026-06-20. Toolchain: clang 21, cmake 4.2, ninja 1.13, python 3.14.

## What was validated

`libdexfile` (`art_cc_library`) converted, built, linked: `libdexfile.so`
(2.8 MB) NEEDs libartbase + libziparchive + libartpalette + libbase + liblog +
libz + libcap.

KEY RESULT — PUBLIC-define propagation works across the link boundary:
libdexfile's OWN translation units (e.g. dex_file.cc) receive
`ART_FRAME_SIZE_LIMIT=1736` and `ART_STACK_OVERFLOW_GAP_x86_64=8192` purely
through the target's link to libartbase. These are NOT restated in libdexfile's
overlay entry — they flow via target_compile_definitions(artbase PUBLIC ...) +
target_link_libraries. This confirms the overlay's add_public_defines channel is
the right mechanism for art.go knobs consumed through public headers.

Also validated: dexfile's own operator_out gensrcs (dexfile_operator_srcs) ran
(art::operator<<(InvokeType) symbols present).

## Toolchain-drift shims (harness only)

Same clang-21/2023 drift family: dex/*.cc need <cstdint> + <algorithm>
(std::copy_n) + the stl_util Filter shadow demotion; the generated dexfile
operator_out.cc needs <cstdint> (uint32_t), applied as a dexfile target option.

## Reproduce

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake \
    --root /home/agent/Projects/MinDalvikVM-Archive/native \
    --overlay overlay/port_policy.py \
    --module liblog --module libbase --module libartpalette \
    --module libziparchive --module libartbase --module libdexfile \
    --out tools/verify/dexfile/dexfile.cmake
cmake -S tools/verify/dexfile -B /tmp/vd -G Ninja \
    -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build /tmp/vd
```
