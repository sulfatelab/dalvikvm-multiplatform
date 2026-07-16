# art+libcore bump to android-u-beta-4-gpl — result

Date: 2026-06-20. RelWithDebInfo, clang-21. Archive NOT touched.

## Goal & outcome

Resolve the libart<->libcore version skew (Class.getRecordAnnotationElement,
registered by the archive's newer art, absent from its older u-preview-2 libcore)
by bumping BOTH art and libcore to a coherent snapshot.

Picked **android-u-beta-4-gpl** — the first U release where libcore's Class.java
declares getRecordAnnotationElement (Class.java:3883) and art registers it. A
real Android release, so the two are guaranteed consistent.

RESULT: the full native stack builds coherently from beta-4 and the skew is
fixed. The previously-fatal `Failed to register ... getRecordAnnotationElement`
is GONE (count 0). All libs build: libart, libjavacore, libopenjdk, libicu_jni,
libcrypto, dalvikvm.

## Mechanism (archive untouched)

- art + libcore cloned at the tag into project-owned vendor/ (gitignored, 230MB).
  Reproducible via tools/vendor-sync.sh (clones + applies the patches below).
- converter: --exclude-top art drops the archive's stale native/art; vendor art
  loaded via --extra-root vendor:MDVM_ART_ROOT_DIR (root=vendor so bp_dirs keep
  the art/ prefix). libcore extra-root -> vendor/libcore. ICU/fdlibm/the other
  native libs still come from the read-only archive.

## Toolchain drift fixed for the beta-4 sources (clang-21 / glibc-2.34..2.40)

Harness prelude (compat/include/mdvm_toolchain_prelude.h) grew
<optional>/<cstring>/<climits>/<ctime>/<limits>/<csignal>/<cmath>; applied
C/CXX-scoped to every generated target via BUILDSYSTEM_TARGETS, minus `base`
(its posix_strerror_r.cpp #undef _GNU_SOURCE). Tree-wide -Wno-error.
Vendor source patches (vendor-patches/README.md, re-applied by vendor-sync.sh):
  0001 art_method-inl.h  FillVRegs terminal-overload ambiguity (clang>=17)
  0002 class_linker.cc   bare nullptr_t -> std::nullptr_t
  0003 thread_linux.cc   constexpr kHostAltSigStackSize (MINSIGSTKSZ non-const)
  0004 thread.cc         PTHREAD_STACK_MIN long->size_t (file has #pragma error)
  0005 OpenjdkJvm.cc     JVM_IsNaN bare isnan -> std::isnan

## Remaining: boot.jar must also be rebuilt from beta-4 libcore

Running Hello.main() now reaches ART's OWN coherence check and aborts cleanly
(EXIT 134, not a crash):

  class_linker.cc:612] InitWithoutImage: Class mismatch for Ljava/lang/String;.
  ... Make sure that libcore and art projects match.
  (String objectSize=779 expected by beta-4 libart vs 771 in the old boot.jar)

The /tmp/vm boot.jar is still the archive's 2023 output.jar (built from the OLD
libcore), so its dex class layouts don't match beta-4 libart. This is ART's
intended "rebuild boot.jar to match" check -- the native bump is correct; the
Java boot classpath now needs rebuilding from vendor/libcore (beta-4) via the
javalib/d8 path. That's the next milestone for a full Hello.main() run.
