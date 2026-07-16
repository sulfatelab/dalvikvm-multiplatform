# boot.jar rebuilt from vendor/libcore (beta-4) — result + String ClassSize finding

Date: 2026-06-20. VM: bumped libart (beta-4, RelWithDebInfo). Archive untouched.

## What works now

boot.jar rebuilt from vendor/libcore (beta-4) via tools/bootjar/{build,dex}.sh:
javac (0 errors, 5655 classes) + d8 -> 3.4 MB single-dex boot.jar. The
getRecordAnnotationElement native-registration skew (the previous blocker) is
fully resolved by the art+libcore bump.

## Remaining blocker: ART InitWithoutImage CheckSystemClass(String) — 8-byte size delta

Booting still aborts (EXIT 134, clean ART abort) at:
  class_linker.cc CheckSystemClass: java.lang.String mismatch
  c1 (libart's pre-built String) objectSize=779; c2 (dex-loaded) objectSize=771.
Both have identical instance fields (2: count, hash), vtable (70), direct
methods (57). The 8-byte delta = 2 vtable slots * 4 bytes.

### Root cause (found, in vendor/art/runtime/mirror/string-inl.h:31-42)

`String::ClassSize()` hardcodes the vtable entry count and it is gated on
USE_D8_DESUGAR:
    #ifdef USE_D8_DESUGAR
      vtable_entries = Object::kVTableLength + 67;   // 2 CharSequence default-method
    #else                                            // lambdas (chars/codePoints)
      vtable_entries = Object::kVTableLength + 69;   // become DIRECT under d8 desugar
    #endif
i.e. libart's compiled-in expected String size depends on whether the boot dex
was built with d8 lambda desugaring. The 8-byte (2-method) delta is exactly
those two CharSequence lambdas. So libart's `USE_D8_DESUGAR` setting and the
actual desugaring state of our d8'd boot.jar DISAGREE by 2 methods.

We DO define USE_D8_DESUGAR=1 for libart (verified on 334 TUs incl.
class_linker.cc). So the mismatch is the *other* direction: the boot.jar's String
does not have the method count libart expects under the D8 path. Likely d8
`--min-api 31` did not desugar the CharSequence default-method lambdas the way
the beta-4 build assumed (or vice-versa).

## Options to resolve (need a decision)

1. **Reconcile d8 desugaring with USE_D8_DESUGAR.** Make the boot.jar's String
   method shape match libart's +67 expectation: try d8 with explicit desugaring
   flags / a lower --min-api, or toggle libart's USE_D8_DESUGAR to the +69 path
   and match. A few build iterations; cheapest if it lands.
2. **Generate a boot image with dex2oat** (the proper ART startup path). A boot
   .art/.oat precomputes all class layouts, so InitWithoutImage + CheckSystemClass
   is never exercised. This is how AOSP actually runs ART, and sidesteps the
   whole imageless-coherence problem -- but dex2oat is itself a large unconverted
   target (compiler/, dex2oat/) and a new sub-project.

The native stack + boot.jar both BUILD coherently from beta-4; this is the last
gap to a running Java program, and it is a known-fragile imageless-startup check
rather than a converter/build defect.

## UPDATE: String mismatch RESOLVED (vendor patch 0006)

Root cause was NOT d8 desugaring (tried min-api 23/24/31 -- no effect on the
779/771 sizes) and NOT fields (both 2). It was libart's hardcoded
`String::ClassSize` (string-inl.h) over-counting this beta-4 libcore's String
vtable by one slot: the dump's "779" entry is libart's pre-built bare String
shell (AllocClass(String::ClassSize)), "771" is the fully-linked dex String.
Patched the USE_D8_DESUGAR vtable_entries from +67 to +66 (patch 0006).

Result: the String mismatch is GONE. The VM no longer aborts at
InitWithoutImage/CheckSystemClass -- it proceeds into boot class init and
interprets (imageless). Remaining hurdle is now SPEED: imageless cold boot-class
init in the pure interpreter is very slow (minutes); running with a long timeout
+ -Xusejit:true to see if Hello.main() completes. A dex2oat boot image would
make startup fast (and precompute these layouts), but the patch already gets us
past the coherence wall.

## UPDATE 2: past CheckSystemClass; now blocked on d8 stripping java.lang.Record

With patch 0006 the VM advances all the way into `WellKnownClasses::Init`, then
aborts:
  well_known_classes.cc:176] Couldn't find class: java/lang/Record
  -> NoClassDefFoundError -> Runtime::Abort (EXIT 134)

Root cause: **d8 silently refuses to emit `java.lang.Record` (and other java.*
core classes) into a dex** -- it has a hardcoded core-library prune list and
this cmdline-tools d8 has no `--core-library` override. Verified: d8 of ONLY
Record.class yields a dex WITHOUT it. The archive's old boot.jar also lacked
Record, but the OLD art's WellKnownClasses didn't require it; beta-4 art does
(records support). So:
  - the bump is coherent and correct;
  - the boot.jar is missing a class d8 won't dex.

## UPDATE 3 (AOSP-aligned attempt): JDK17 + AOSP r8 dexes everything except Record

Per the "stay aligned with AOSP" steer:
- Fetched AOSP's OWN dexer: platform/prebuilts/r8 @ android-u-beta-1-gpl
  (r8.jar, D8 8.1.31), via tools/vendor-sync.sh.
- Installed JDK 17 (the AOSP-era javac) -- r8 8.1.31 NPEs on javac-21 (v65) enum
  class files; JDK 17 (v61) dexes cleanly.
- Dexed with `--android-platform-build` (the bootclasspath mode).
Result: javac 0 errors / 5686 classes, d8 exit 0, 3.0 MB single-dex boot.jar,
all enums fine (RoundingMode kept) -- BUT `java.lang.Record` is STILL stripped.

`--android-platform-build` alone does NOT keep Record; only the `--core-library`
flag does, and NEITHER available dexer exposes it:
  - modern SDK d8 9.0.32: no --core-library (rejected); strips Record.
  - AOSP r8 8.1.31 (this prebuilt): no --core-library CLI flag, no public
    coreLibrary() builder method, no "core-library" string in the jar.
libcore's own dxflags (JavaLibrary.bp:169) ARE `--android-platform-build` +
`--core-library`, so the flag is correct -- we just lack an r8 build that has it.

## The AOSP-true path is a dex2oat boot image (recommended)

AOSP never runs the boot classpath imageless. It builds a boot IMAGE (boot.art/
.oat) with **dex2oat**, which:
  - is fed the boot dex jars and resolves/lays out all classes ahead of time,
    so InitWithoutImage + CheckSystemClass (the String 779/771 wall) is never
    run, and
  - handles core java.* classes correctly (no d8 --core-library dance), and
  - makes startup fast (no slow imageless cold interpret).
dex2oat is part of ART (art/dex2oat/, art/compiler/) -- both already vendored in
vendor/art but NOT yet converted by bp2cmake. Converting + running dex2oat to
produce a boot image is the AOSP-aligned way to clear BOTH remaining walls
(Record + String coherence) at once. It is the recommended next milestone.

Everything below dex2oat is coherent: bumped art+libcore build, boot.jar
compiles+dexes (sans the one Record-stripping d8 limitation), VM reaches
WellKnownClasses::Init.
