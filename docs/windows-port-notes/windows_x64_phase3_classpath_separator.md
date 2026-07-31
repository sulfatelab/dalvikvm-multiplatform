# Windows x64 Phase 3 — classpath list separator (`;`)

Status: applied in nested ART commit `90e063dfcd`; do not reapply this note.

Although discovered on x86_64, this is a Windows platform rule and applies to
every Windows architecture and ABI.

## Constant
`vendor/art/libartbase/base/globals.h` — `kClassPathListSeparator` is `';` when `ART_TARGET_WINDOWS`.

## Files
- `vendor/art/runtime/runtime_options.def` — `ParseStringList/IntList<';'>` under `ART_TARGET_WINDOWS`
- `vendor/art/runtime/parsed_options.cc` — `ArtPathStringList` / `ArtPathIntList`
- `vendor/art/runtime/runtime.cc` — `Split`/`Join` with `kClassPathListSeparator`
- `vendor/art/libartbase/base/file_utils.cc` — mainline BCP split

## Product
`path.separator` / multi-jar lists use `;` on Windows x64. Linux remains `:`.
