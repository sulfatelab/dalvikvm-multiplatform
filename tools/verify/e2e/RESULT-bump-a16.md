# art + libcore bump: android-u-beta-4-gpl -> android-16.0.0_r4

Date: 2026-06-21 (updated 2026-07-14). Bumps the vendored AOSP snapshot forward ~3 major versions
(Android 14 U beta, Jun 2023 -> Android 16 stable r4, Oct 2025), the project's
long-standing "bump submodules to current AOSP" goal. art + libcore + the r8
dexer all move to the coherent `android-16.0.0_r4` tag (latest stable Android 16;
android-17.0.0_r1 also exists but r4 is the mature stable cut). Archive
foundational libs (libbase/liblog/.../ICU/fdlibm/boringssl) stay archive-pinned.

## What the bump touched

tools/vendor-sync.sh: TAG -> android-16.0.0_r4; r8.jar fetched at the SAME tag
(was android-u-beta-1). Vendor patches reconciled (see vendor-patches): 0001,
0007, 0008, 0010 OBSOLETE (fixed upstream / dexlayout removed); 0002 guard
updated for the new `[[maybe_unused]]` form; 0003/0004/0005/0009 still apply.
New: 0011-0013 host shims (fmt::streamed, libunwindstack, HIDDEN visibility),
**0014 InlinedVector size_ init** (the getDeclaredFields crash).

bp2cmake Layer 1 (the durable converter work — see the a16-bump-converter-syntax
memory):
- **select() expressions**: parse + resolve Soong's `select(cond, {pat: val})`
  (replaces many `soong_config_variables: {}`). Lexer/AST/parser/evaluator +
  Config.select_condition_value. All host selects resolve to `default`.
- **lib#impl variant tags**: strip Soong `#impl`/`#tag` from dep names.
- **gensrc + codegen rooting**: operator_out/mterp/asm_defines now root at the
  bumped vendor art (MDVM_ART_ROOT_DIR), not the stale archive native/art.
- **aconfig**: new bp2cmake/aconfig.py generates the com_android_art[_rw]_flags.h
  headers from .aconfig (no aconfig tool on host); flags default disabled.

Overlay / build (Layer 2 + harness):
- art.go drift: ART_FRAME_SIZE_LIMIT 1736->1744; +ART_PAGE_SIZE_AGNOSTIC=1;
  dropped dead ART_DEFAULT_COMPACT_DEX_LEVEL. CMS GC force retained (CMC needs
  userfaultfd).
- C++ standard 17 -> 20 (A16 uses std::ostringstream::view() etc.).
- //compat shim android-base/stringify.h (+ <filesystem> in the prelude).
- libartbase: drop the aconfig static libs (headers are header-only).
- per-file COMPILE_OPTIONS now honor global drop_cflags (-Werror was re-armed
  on host -> C++20 -Wdeprecated-literal-operator in fmtlib).

## Status

**Native side: COMPLETE.** The full dalvikvm native graph (28 shared libs +
dalvikvm + dex2oat) builds from android-16.0.0_r4 Android.bp via bp2cmake, 0
errors. `LD_LIBRARY_PATH=build/native build/native/dalvikvm -showversion` ->
`ART version 2.1.0 x86_64`. dex2oat + libart-compiler + libart-dex2oat all link.

**boot.jar: COMPLETE.** Rebuilt from android-16.0.0_r4 libcore: JDK 21 javac
(A16 libcore uses Java 21 switch pattern-matching), 5932 classes, dexed with the
A16 r8 9.0.10 keeping java.lang.Record (emitRecordAnnotationsInDex). Java-side
aconfig Flags classes + FlaggedApi stub generated (bp2cmake.aconfig --java).
3.1 MB, Record present.

**Hello.main(): FIXED (2026-07-14).** Imageless run succeeds:

```
$ dalvikvm -Xbootclasspath:.../boot.jar -Ximage:/nonexistent ... Hello
Hello from dalvikvm!
java.version=0
EXIT=0
```

### Root cause of the getDeclaredFields crash (patch 0014)

Narrowed via registers + disassembly, not GC:

- Crash: `SIGSEGV` in `art::mirror::Field::CreateFromArtField+66` (`mov (%rsi),%eax`)
  with **rsi=0** — a null `ArtField*`.
- Call chain: `InitNativeMethods` -> libopenjdk `JNI_OnLoad` ->
  `register_java_net_Inet6Address` -> `GetFieldID` -> CHM init ->
  `Unsafe.objectFieldOffset(Class, name)` -> `Class.getDeclaredFields` ->
  `CreateFromArtField`.
- ConcurrentHashMap has **37 fields** (27 static + 10 instance).
- `Class::GetDeclaredFields` collects into `InlinedVector<ArtField*, 8>`.
- A16's new `InlinedVector` never initialized `size_`. With size > 8 it spills
  to heap and `GetArray()` returns `{data, size_}` — garbage `size_` made the
  second loop walk far past the real field list into null pointers.
- Explains the Heisenbug: `fprintf` zeroed stack and "fixed" size_; also the
  earlier OOME allocating a multi-GB `Field[]` (garbage length). Independent of
  heap size and of CMS vs MS.

**Fix (vendor patch 0014):** construct `InlinedVector` with `size_(0)` and
default-member-init `size_ = 0u`. Wired into `tools/vendor-sync.sh`.

## Reproduce (imageless)

```sh
bash tools/bootjar/build.sh && bash tools/bootjar/dex.sh
# stage boot.jar + hello.jar + ICU under /tmp/vm/run (see tools/bootimage/run.sh)
ANDROID_ROOT=/tmp/vm/run ANDROID_ART_ROOT=/tmp/vm/run ANDROID_I18N_ROOT=/tmp/vm/run \
ANDROID_DATA=/tmp/vm/run/data ICU_DATA=/tmp/vm/run/icu LD_LIBRARY_PATH=build/native \
  build/native/dalvikvm \
    -Xbootclasspath:/tmp/vm/run/boot.jar -Xbootclasspath-locations:/tmp/vm/run/boot.jar \
    -Ximage:/nonexistent-no-boot-image \
    -cp /tmp/vm/run/hello.jar Hello
```

Optional next: `tools/bootimage/build.sh` + `run.sh` for the fast image-backed path.
