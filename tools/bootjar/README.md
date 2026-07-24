# boot.jar build (dalvikvm-multiplatform)

Rebuilds the boot class library from nested **`vendor/libcore`** (android-16 /
`artmp_*`) so it matches libart in this multiplatform tree.

## Usage

```bash
# from repo root (dalvikvm-multiplatform)
bash tools/bootjar/build.sh       # javac -> /tmp/bootbuild/classes
bash tools/bootjar/dex.sh         # vendor/r8 -> /tmp/bootbuild/boot.jar
bash tools/bootjar/build_win64.sh # recompile shared selectors, re-dex, stage for both hosts
```

Requires:

- **JDK 21 javac** (android-16 libcore uses Java 21 language features)
- `vendor/r8/r8.jar` (in-tree prebuilt; or `MDVM_R8JAR=...`)
- Nested `vendor/libcore` + nested `vendor/icu/android_icu4j` (required)
- In-tree `compat/java-stubs` for framework annotations used by libcore

**Pure-vendor default:** `build.sh` does not look for a sibling
`MinDalvikVM-Archive` tree. Optional escape hatch only:
`MDVM_ARCHIVE=/path/to/archive` may add extra annotation sources; it is not
needed for product builds.

## Shared multipath staging

`build_win64.sh` does not create a Windows-only jar. It recompiles the shared
runtime-OS selection anchors from nested libcore, then stages identical
`boot.jar` bytes to the Win64 product run tree and the Linux L-005 run tree.

The jar contains both `UnixFileSystem` and `WinNTFileSystem`; native ART injects
`dalvik.vm.multiplatform.internal.os`, and `VMRuntime.isWindowsOs()` selects the
backend and separators at runtime.

## Why AOSP r8 + platform-build

Dex with AOSP r8 and
`-Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 --android-platform-build`
so `java.lang.Record` remains in boot dex (ART WellKnownClasses).

## Conscrypt/TLS product boot

```bash
bash tools/bootjar/build.sh            # or reuse existing /tmp/bootbuild/classes
bash tools/bootjar/build_win64.sh      # stage the shared multipath jar
bash tools/bootjar/build_conscrypt_win64.sh
```

Merges jarjar `com.android.org.conscrypt` into boot classes, embeds
`java/security/security.properties`, re-dexes, and stages
`build/win64_phase1/run/boot.jar`. Requires host `g++` + boringssl headers for
`NativeConstants`. The resulting jar remains the same shared multipath boot
format; it adds the conscrypt classes and security resources used by TLS.
