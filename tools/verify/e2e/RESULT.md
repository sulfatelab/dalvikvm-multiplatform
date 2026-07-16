# End-to-end run — result: full native stack built; blocked on libart<->libcore skew

Date: 2026-06-20 (updated). VM: converter-built dalvikvm, RelWithDebInfo, clang-21.

## Status: the ENTIRE native stack now builds from Android.bp

The converter (with multi-root + filegroup + glob expansion) builds the complete
graph from one command, including the javacorenatives the VM dlopens at startup:
  dalvikvm + libart + 17 support libs
  + libjavacore.so, libopenjdk.so, libicu_jni.so   (VM loads these, runtime.cc:2193)
  + libicuuc/libicui18n/libicu/icu_jni/stubdata/androidicuinit, libcrypto
    (boringssl, 228 srcs, non-FIPS), libfdlibm, libandroidio, libopenjdkjvm.
All from Android.bp via bp2cmake. Build: RelWithDebInfo, 0 errors.

## Where Hello.main() still fails (root cause pinned)

The VM boots, GC, imageless fallback, registers JNI natives... then dies the
same way as before the javacorenatives existed:

  jni_internal.cc:2657] Failed to register native method
    java.lang.Class.getRecordAnnotationElement(...) in boot.jar
  -> java.lang.Throwable.toString recurses ~252 deep
  -> real StackOverflow
  -> art::ThrowStackOverflowError handler SIGSEGVs (fault addr nil)  [EXIT 139]

Root cause = libart<->libcore VERSION SKEW *within the archive*:
  - libart `runtime/native/java_lang_Class.cc:982` registers
    `Class.getRecordAnnotationElement` (a FAST_NATIVE_METHOD).
  - This 2023 `libcore/ojluni/.../java/lang/Class.java` does NOT declare it.
  - RegisterNatives fails -> early exception -> Throwable.toString recursion.

This is NOT a converter/overlay/codegen defect (every lib builds and loads). The
art and libcore submodules were pinned at slightly different AOSP points where
this native method's presence disagrees. Fix = bump art + libcore to a coherent
snapshot (the project's standing submodule-update goal).

## Secondary finding: ART's stack-overflow handler crashes (flagged to human)

Independently of the trigger, ART's OWN `ThrowStackOverflowError` path SIGSEGVs
instead of throwing cleanly when the interpreter hits a deep Java recursion. That
is a real ART-on-GNU/Linux failure-path bug (stack guard / sigaltstack / implicit
SO check on glibc), worth investigating separately. Reported via notify-human.

## Converter capabilities added this milestone (all committed, 29 tests pass)

- multi-root loading (--extra-root DIR:CMAKEVAR; module.root_var path prefixes)
- filegroup expansion (:name -> filegroup's srcs; genrule/gensrcs NOT inlined)
- glob expansion (srcs ["*.cpp"] against the real fs; +exclude_srcs)
- load boringssl sources.bp (libcrypto_sources cc_defaults)
- function-like macro defines (__INTRODUCED_IN(x)=) emitted as compile OPTIONS,
  since CMake COMPILE_DEFINITIONS can't round-trip name parens

## Reproduce

generate (native/generate.sh passes libcore/ICU/fdlibm extra roots) ->
cmake RelWithDebInfo -> ninja -> /tmp/vm staging -> dalvikvm -cp hello.jar Hello.
