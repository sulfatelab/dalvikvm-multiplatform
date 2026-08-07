# Historical dex2oat boot-image E2E result (2026-06-21)

A Java program now runs on the bp2cmake-converted GNU/Linux dalvikvm, backed by
a dex2oat-built boot image. VM: bumped art+libcore (android-u-beta-4-gpl) in
vendor/, built RelWithDebInfo (-O2 -g -DNDEBUG). Archive untouched.

This record preserves the commands and paths used in that bring-up session.
The shell entry points named below have since been retired; the current
shell-free replacement is `tools/build_art.py` plus the unified W-004 gates.

## Historical command transcript

    $ tools/bootimage/build.sh        # dex2oat -> boot.art/boot.oat/boot.vdex
    dex2oat took 1.544s (12.9s cpu, 32 threads)   exit=0
    $ tools/bootimage/run.sh          # dalvikvm -Ximage:.../boot.art Hello
    Hello from dalvikvm!
    java.version=0
    EXIT=0          (~30 ms wall, image mmap'd + relocated)

## Walls cleared this session (in order)

1. **dex2oat link failure — libcrypto missing its crypto core.** The converted
   libcrypto.so had 320 undefined symbols (BN_/EC_/RSA_/SHA/AES). bp2cmake can't
   follow boringssl's `srcs:[":bcm_object"]` (a cc_object). Overlay now injects
   `bcm.c` + the 15 x86_64 fipsmodule .S files (matches the archive's reference
   libcrypto.cmake). Hidden until dex2oat's hard executable link.

2. **dex2oat/dalvikvm hang linking java.util.HashMap.** `LinkMethodsHelper`'s
   `initialized_methods` BitVector sat over uninitialized alloca/arena memory
   (the preallocated-storage ctor doesn't clear). Garbage bits produced a
   `same_signature_vtable_lists[0]=0` self-loop; the vtable walk spun forever
   (guarding DCHECK_LT compiled out under NDEBUG). Latent upstream bug. Fixed by
   zeroing the buffer (vendor patch 0009). NOT a Debug-build slowness issue —
   build was RelWithDebInfo throughout.

3. **String coherence (779 vs 771).** Knock-on of #2: the buggy linker mis-built
   String's vtable to 771; old patch 0006 had forced String::ClassSize +67->+66
   to match that. With #2 fixed String links at the canonical 779, so patch 0006
   was REMOVED and string-inl.h reverted to upstream +67. CheckSystemClass(String)
   passes.

4. **java.lang.Record stripped from boot.jar.** D8 record-desugars by default,
   rewriting `java.lang.Record` -> synthetic RecordTag, so beta-4 ART's
   WellKnownClasses::Init aborted. No available r8 (8.1.31 / SDK 9.0.32) exposes
   the old dx `--core-library` flag. Fix: the r8 system property
   `-Dcom.android.tools.r8.emitRecordAnnotationsInDex=1` forces
   desugarRecordState()==OFF, emitting java.lang.Record natively. Wired into
   tools/bootjar/dex.sh. (Verified Ljava/lang/Record; present in classes.dex.)

5. **SIGSEGV invoking Daemons.start().** ArtMethod::InvokeStatic passed
   `sizeof(vregs)` as the arg byte count; for a no-arg call vregs is
   std::array<uint32_t,0>, and under libstdc++ sizeof==1 / data()==nullptr, so
   the invoke stub did `rep movsb` of 1 byte from NULL. Fixed to pass
   `vregs.size()*sizeof(uint32_t)` (vendor patch 0010). libc++/AOSP masked it.

## Artifacts recorded at the time and current disposition

- `overlay/port_policy.py` supplied the original libcrypto injection; its
  retained policy is now target-resolved by `overlay/art_port_policy.py`.
- tools/vendor-sync.sh — patch 0006 removed; patches 0009 (BitVector clear),
  0010 (invoke-stub arg size) added; all idempotent (guarded).
- `tools/bootjar/dex.sh` was replaced by the common CMake/Ninja boot-JAR edge.
- `tools/bootimage/{build.sh,run.sh}` was replaced by
  `tools/build_boot_image.py`, target capability metadata, and the W-004
  `managed_boot_image_hello` gate. The replacement keeps the primary-image
  invocation semantics while avoiding shell, `/tmp`, and ambient environment
  ownership.
- the then-current vendor patch ledger — patches documented through 0010; the
  applied forms now live in nested ART history.

## Expected (NOT defects)

- `java.version` == `"0"`: this is the hardcoded value in Android's libcore
  (ojluni System.java:1119, "java.version  (Not useful on Android)  0"). ART
  runs dex bytecode, not Java .class bytecode, so there is no JVM version to
  report — getting "0" is correct and confirms the property machinery works.
- hello.dm warning: optional dex-metadata file absent; harmless.
