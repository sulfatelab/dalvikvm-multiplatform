# boot.jar build (dalvikvm-multiplatform)

Rebuilds the boot class library from nested **`vendor/libcore`** (android-16 /
`artmp_*`) so it matches libart in this multiplatform tree.

## Usage

```bash
# from repo root (dalvikvm-multiplatform)
bash tools/bootjar/build.sh       # javac -> /tmp/bootbuild/classes
bash tools/bootjar/dex.sh         # vendor/r8 -> /tmp/bootbuild/boot.jar
bash tools/bootjar/build_win64.sh # Option H: overlay WinNTFileSystem + re-dex
```

Requires:

- **JDK 21 javac** (android-16 libcore uses Java 21 language features)
- `vendor/r8/r8.jar` (in-tree prebuilt; or `MDVM_R8JAR=...`)
- Nested `vendor/libcore` + preferably nested `vendor/icu/android_icu4j`
- Optional archive fallback: `MDVM_ARCHIVE=../MinDalvikVM-Archive` for
  android-annotation-stub if not otherwise provided

## Win64 overlay

`build_win64.sh` recompiles WinNT path/properties sources from nested libcore:

- `vendor/libcore/multiplatform/windows/java/...` (mirrors), or
- `vendor/libcore/ojluni/src/main/java/...` (folded ojluni sources)

## Why AOSP r8 + platform-build

Dex with AOSP r8 and
`-Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 --android-platform-build`
so `java.lang.Record` remains in boot dex (ART WellKnownClasses).

## Conscrypt on Win64 boot (L-002 C2)

```bash
bash tools/bootjar/build.sh            # or reuse existing /tmp/bootbuild/classes
bash tools/bootjar/build_win64.sh      # WinNT FileSystem overlay
bash tools/bootjar/build_conscrypt_win64.sh
```

Merges jarjar `com.android.org.conscrypt` into boot classes, embeds
`java/security/security.properties`, re-dexes, and stages
`build/win64_phase1/run/boot.jar`. Requires host `g++` + boringssl headers for
`NativeConstants`. Provider init at runtime still needs W-019 (Math CriticalNative).
