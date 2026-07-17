# Python codegen driver (replaces historical AOSP Gradle tasks)

AOSP ART historically generated headers/sources from Gradle:
`generateArtOpCxxSrc`, `generateArtMterpAsmSrc`, `generateArtAsmDefinitions`,
`generateArtAsmHeader`. This multipath tree drops Gradle; `bp2cmake/codegen.py`
reproduces those steps in pure Python — one driver, no JVM, runnable standalone
or wired into CMake.

## The three generation kinds

1. **operator_out** — `art/tools/generate_operator_out.py <reldir> <header>`
   per header → `<gensrc>/<reldir>/<header>.operator_out.cc`. Sets in
   `OPERATOR_OUT_SETS` (libartbase / libdexfile / runtime), mirroring the
   Gradle `genInfoList`.
2. **mterp asm** — `gen_mterp.py <out> <inputs...>` over the 8 `*.S` files in
   `art/runtime/interpreter/mterp/<arch>ng/` → `mterp_<arch>.S`.
3. **asm_defines** — TWO-STAGE: `clang++ -S asm_defines.cc` (with the runtime's
   include + define context, incl. the art.go knobs) → assembly text carrying
   `>>NAME val neg<<` markers, then `make_header.py <s>` → `asm_defines.h`.

## Usage

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake.codegen_main \
    --root <repo>/vendor --gensrc <out-dir> --arch x86_64 --clang clang++
```

Validated output (2026-06-20, clang-21): 33 operator_out.cc, mterp_x86_64.S
(8868 lines), asm_defines.h (188 #defines). `--only operator_out|mterp|
asm_defines` runs a single kind.

## How it relates to the emitter

The Layer 3 emitter ALSO emits operator_out as CMake `add_custom_command`s (used
by the per-module verify harnesses so far). This driver is the alternative /
complement for the runtime: asm_defines + mterp are awkward to express as pure
CMake custom commands (the asm_defines compile needs libart's full include/
define context), so staging them with this driver before/at configure time is
cleaner. The runtime harness will set `MDVM_GENSRC_DIR` to the driver's output.
The asm_defines define-set here is the single source of truth for the runtime
behavioral overlay (CMS GC, ART_TARGET_LINUX, base addresses) and must stay in
sync with the libart overlay entry when that lands.
