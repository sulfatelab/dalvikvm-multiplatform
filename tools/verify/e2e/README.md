# End-to-end run: execute Java bytecode on the converter-built dalvikvm

Validates the ultimate goal (`command-example.txt` pattern): the `dalvikvm` built
entirely from `Android.bp` via bp2cmake actually runs a Java program against the
boot class library.

## Pieces

- VM: `build/native/dalvikvm` + the 17 `.so`s (from `native/` top-level build).
- boot.jar: the archive's prebuilt `javalib/build/merged/output.jar` (dex'd
  libcore: classes.dex + classes2.dex). We did NOT rebuild the Java side; the
  2023 prebuilt is reused as-is.
- ICU data: `javalib/external/icu/icu4c/source/stubdata/icudt72l.dat`.
- test app: `Hello.java` -> `javac --release 8` -> `d8 --min-api 31` -> hello.jar
  (classes.dex). d8 from `~/Android/Sdk/cmdline-tools/latest/bin/d8`.

## Run

```sh
# stage (see commands in this dir's RESULT.md), then:
ANDROID_ROOT=$RUN ANDROID_ART_ROOT=$RUN ANDROID_I18N_ROOT=$RUN \
ANDROID_DATA=$RUN/data ICU_DATA=$RUN/icu LD_LIBRARY_PATH=build/native \
  build/native/dalvikvm \
    -Xbootclasspath:$RUN/boot.jar -Xbootclasspath-locations:$RUN/boot.jar \
    -Ximage:/nonexistent-no-boot-image \
    -cp $RUN/hello.jar Hello
```

No boot.art image exists, so the VM runs "imageless" — it interprets boot.jar's
dex directly. This is correct but slow on first init (no JIT image; cold
interpret of all of libcore boot init). A boot image would need dex2oat (not yet
converted).

See RESULT.md for the observed outcome.
