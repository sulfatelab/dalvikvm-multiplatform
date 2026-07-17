# Android annotation stubs (boot.jar javac)

Project-owned, **SOURCE/CLASS-retention** stubs for framework annotations that
android-16 libcore references but that live outside `vendor/libcore` (AOSP
frameworks / android-annotation-stub).

Used by `tools/bootjar/build.sh` so boot.jar builds are **pure-vendor**: they
do not require a sibling `MinDalvikVM-Archive` tree.

| Package | Role |
|---------|------|
| `android.annotation.*` | `@SystemApi`, `@TestApi`, `@IntDef`, `@UserIdInt`, `@FlaggedApi` |
| `android.compat.annotation.*` | `@UnsupportedAppUsage`, `@ChangeId`, `@EnabledSince`, … |

These are compile-time only glue. Runtime behavior comes from ART/libcore, not
from these annotations. Prefer expanding this tree over reintroducing archive
fallbacks for missing annotations.
