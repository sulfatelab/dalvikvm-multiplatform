# Python codegen driver (replaces historical AOSP Gradle tasks)

AOSP ART historically generated headers/sources from Gradle:
`generateArtOpCxxSrc`, `generateArtMterpAsmSrc`, `generateArtAsmDefinitions`,
`generateArtAsmHeader`. This multipath tree drops Gradle; `bp2cmake/codegen.py`
reproduces those steps in pure Python — one driver, no JVM, runnable standalone
or wired into CMake.

## The four generation kinds

1. **aconfig** — parses ART/libcore `.aconfig` declarations and emits the C++
   feature-flag headers required by android-16 ART.
2. **operator_out** — `art/tools/generate_operator_out.py <reldir> <header>`
   per header → `<gensrc>/<reldir>/<header>.operator_out.cc`. Sets in
   `OPERATOR_OUT_SETS` (libartbase / libdexfile / runtime), mirroring the
   Gradle `genInfoList`.
3. **mterp asm** — `gen_mterp.py <out> <inputs...>` over the 8 `*.S` files in
   `art/runtime/interpreter/mterp/<arch>ng/` → `mterp_<arch>.S`.
4. **asm_defines** — TWO-STAGE: `clang++ -S asm_defines.cc` (with the runtime's
   include + define context, incl. the art.go knobs) → assembly text carrying
   `>>NAME val neg<<` markers, then `make_header.py <s>` → `asm_defines.h`.

Generated files are installed only when their content changes. Re-running
configure therefore preserves timestamps for identical aconfig, operator-out,
mterp, and asm-definition output and does not force unrelated ART objects to
rebuild.

## Usage

```
PYTHONPATH=tools/bp2cmake python3 -m bp2cmake.codegen_main \
    --root <repo>/vendor --gensrc <out-dir> --arch x86_64 --clang clang++
```

Validated output (2026-06-20, clang-21): two ART aconfig headers, 33
operator_out.cc files, mterp_x86_64.S (8868 lines), and asm_defines.h (188
#defines). `--only aconfig|operator_out|mterp|asm_defines` runs a single kind.

## How it relates to the emitter

The Layer 3 emitter ALSO emits operator_out as CMake `add_custom_command`s (used
by the per-module verify harnesses so far). This driver is the alternative /
complement for the runtime: asm_defines + mterp are awkward to express as pure
CMake custom commands (the asm_defines compile needs libart's full include/
define context), so staging them with this driver before/at configure time is
cleaner. The runtime harness will set `MDVM_GENSRC_DIR` to the driver's output.
The asm_defines define-set here is the single source of truth for the runtime
behavioral overlay (CMS GC, `ART_TARGET_LINUX` or `ART_TARGET_WINDOWS` via
`--os`, base addresses) and must stay in sync with the libart overlay.

For PE (`--os windows` / `asm_target_os=windows`), codegen swaps
`ART_TARGET_LINUX` for `ART_TARGET_WINDOWS` and prefers
`--target=x86_64-pc-windows-msvc` so offsets match the PE Runtime layout.
Cross-build callers pass their libc++, UCRT, SDK, and CRT include roots with
repeatable `--target-include` arguments.
Notably `RUNTIME_INSTRUMENTATION_OFFSET` is **0x328** on PE vs **0x340** on
Linux host; shipping the wrong header causes nterp/quick AVs on Wine.
