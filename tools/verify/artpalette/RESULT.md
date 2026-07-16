# First ART core module (libartpalette) — result

Date: 2026-06-20. Toolchain: clang 21, cmake 4.2, ninja 1.13.

## What was validated

`libartpalette` (`art_cc_library`) converted from its Android.bp, compiled, and
linked: `libartpalette.so` NEEDs libbase.so + liblog.so. It is the only ART leaf
with NO generated sources, so it validates the ART path WITHOUT the codegen
pipeline.

## Layer 1 ART extensions proven by this build

ART modules inherit `art_defaults`, which is a normal `cc_defaults` in
`art/build/Android.bp` — so its full cflag set flows automatically. The genuinely
art.go/soong-specific bits needed new Layer 1 handling, now done + unit-tested:

- **soong_config_variables**: `art_defaults` sets `enabled: false` and re-enables
  via `soong_config_variables.source_build.enabled: true`. We resolve
  `source_build=true` (we build from source), so ART modules are enabled.
- **codegen select**: `codegen: { x86_64:{...}, x86:{...}, ... }` collapsed to
  the enabled arches; x86_64 host pulls x86_64 + x86 (art.go default).
- **avx2 select**: `arch.<a>.avx2.{cflags}` gated off by default (host assumes
  sse4.2 only, matching the archive).

Generated artpalette flags confirm correctness: full art_defaults set,
`-msse4.2 -mpopcnt` (target.linux_x86), `-DART_ENABLE_CODEGEN_x86_64/x86`,
`palette_fake.cc` (host fake, not the dlopen loader), `base log` deps. `-Werror`
/ `-Wthread-safety` / `-Wmissing-noreturn` dropped by global overlay policy.

## NEXT STEP (clearly scoped): the generated-source pipeline

Most ART modules (libartbase, libdexfile, runtime, ...) list `generated_sources`
(e.g. `art_libartbase_operator_srcs`, `dexfile_operator_srcs`) and
`generated_headers`. These are genrule/gensrcs outputs from the Python codegen
(`generate_operator_out.py`, `gen_mterp.py`, `make_header.py`). The emitter does
NOT yet handle `generated_sources`/`generated_headers`. Implementing that — as
CMake custom commands or a pre-build step that stages the gensrc tree — is the
prerequisite for converting the rest of the ART core. libartpalette was chosen
first precisely because it sidesteps this.

## UPDATE — generated-source pipeline DONE (2026-06-20)

The emitter now models `gensrcs` modules: for each, it resolves the
`python_binary_host` tool and emits one `add_custom_command` per input header
(staged under `${MDVM_GENSRC_DIR}`), wired into the consuming target's sources.
Validated end-to-end: `generate_operator_out.py` runs, and its output
`instruction_set.h.operator_out.cc` COMPILES — but only after supplying the
art.go-injected defines (next paragraph). 20 unit tests pass (added gensrcs).

### Two follow-ups surfaced for the full libartbase link

1. **art.go defines must be PUBLIC, not PRIVATE.** `ART_STACK_OVERFLOW_GAP_*`
   and `ART_FRAME_SIZE_LIMIT` (art.go:103-167; in NO .bp) are now in the
   libartbase overlay entry — confirming Layer 2 owns the Go knobs. BUT
   `instruction_set.h` is a PUBLIC header included by consumers (libdexfile,
   runtime), so these defines must propagate. The archive did this via
   `$<TARGET_PROPERTY:artbase,COMPILE_DEFINITIONS>`. The overlay/emitter needs a
   PUBLIC-define channel (today add_defines emits PRIVATE). Small emitter change.
2. **libcap is a host dev dependency.** libartbase links `libcap` (base/utils.cc
   capget/capset). Host has libcap.so.2 but the harness will need the dev
   headers/symlink. A host-package prerequisite, not a converter issue.

