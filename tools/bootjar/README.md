# boot.jar build (from vendor/libcore beta-4)

Rebuilds the boot class library to MATCH the bumped libart (android-u-beta-4-gpl).
The archive's 2023 boot.jar (`MinDalvikVM-Archive/javalib/build/merged/output.jar`)
has incompatible class layouts (e.g. java.lang.String objectSize 771 vs the 779
beta-4 libart expects), which ART's InitWithoutImage coherence check rejects.

## Usage

    bash tools/vendor-sync.sh    # also fetches AOSP's r8.jar into vendor/r8/
    bash tools/bootjar/build.sh  # javac vendor/libcore + icu4j -> /tmp/bootbuild/classes
    bash tools/bootjar/dex.sh    # AOSP r8 (platform-build) -> /tmp/bootbuild/boot.jar

Requires: **JDK 17 javac** (`/usr/lib/jvm/java-17-openjdk-amd64`, the AOSP-era
compiler — javac 21's class v65 / newer attributes are rejected by the AOSP r8
8.1.31 dexer), AOSP's r8.jar (vendor/r8, fetched by vendor-sync.sh),
vendor/libcore (vendor-sync.sh), and the archive's icu4j + android-annotation-stub
sources.

## Why AOSP's r8, JDK 17, -g:none

To stay aligned with AOSP (the tested oracle), the boot classpath is dexed by
AOSP's OWN r8 prebuilt (platform/prebuilts/r8 @ android-u-beta-1-gpl) using
`--android-platform-build` -- the bootclasspath-aware mode libcore's `dxflags`
(`--core-library`) imply, which KEEPS core java.* classes (e.g.
`java.lang.Record`, which beta-4 ART requires in WellKnownClasses). The modern
Android SDK d8 (9.0.32) silently strips `java.lang.Record` even in platform-build
mode.

Toolchain pairing: compile with **JDK 17 javac** (the AOSP-era compiler) and
`-g:none`. The AOSP r8 8.1.31 cannot read javac-21 class files (v65) -- it NPEs
on their enum/attribute encodings; JDK 17 (v61) output dexes cleanly.

## What it compiles

vendor/libcore core modules (ojluni [the java.base patch], libart, dalvik, luni,
xml, json) + the two lambda stubs (LambdaMetafactory, SerializedLambda) +
android_icu4j (icu4j + libcore_bridge) + the archive's android-annotation-stub,
all with `javac --system=none --patch-module java.base=.../ojluni/src/main/java
-XDstringConcat=inline`. Excluded (not needed to boot + run a plain Java program,
and would drag in okhttp/conscrypt/bouncycastle): libcore/net/http/{Dns,
HttpURLConnectionFactory}.java and the okhttp/conscrypt/bouncycastle trees.

This is a minimal boot.jar -- enough to boot ART and run core Java. A full
boot.jar (TLS, crypto providers, OkHttp) would add those external trees.
