# Win64 Phase 3 — classpath list separator (`;`)

Vendor tree is gitignored; re-apply if reset.

## Constant
`vendor/art/libartbase/base/globals.h` — `kClassPathListSeparator` is `';` when `ART_TARGET_WINDOWS`.

## Files
- `vendor/art/runtime/runtime_options.def` — `ParseStringList/IntList<';'>` under `ART_TARGET_WINDOWS`
- `vendor/art/runtime/parsed_options.cc` — `ArtPathStringList` / `ArtPathIntList`
- `vendor/art/runtime/runtime.cc` — `Split`/`Join` with `kClassPathListSeparator`
- `vendor/art/libartbase/base/file_utils.cc` — mainline BCP split

## Product
`path.separator` / multi-jar lists use `;` on Win64. Linux remains `:`.
