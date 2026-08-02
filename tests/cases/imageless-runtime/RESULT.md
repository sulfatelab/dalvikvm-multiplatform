# Managed runtime boot-mode result

**Status:** PASS for Linux x86-64 imageless/generated-image runtime and Linux
AArch64 imageless runtime

**Latest acceptance:** 2026-08-02

## Contract

This case proves that the unified ART product can run the same D8-produced
Hello application in the boot modes explicitly admitted per target:

- imageless interpreter mode, with `-Ximage` pointing at an unavailable image;
- packaged-image mode, with a generated `boot.art`, `boot.oat`, and `boot.vdex`
  matched to the exact target-local boot JAR.

The adjacent GC stress source separately exercises allocation and collection
through the same isolated runtime-gate infrastructure, but remains outside the
AArch64 selector until it has its own behavioral evidence. These results do
not claim Windows AOT/OAT support or AArch64 boot-image support.

## Target status

| Target ID | Imageless | Boot image | Last accepted |
|---|---:|---:|---:|
| `linux-x86_64-gnu` | runtime-verified | runtime-verified | 2026-08-02 14:22:00 CST |
| `linux-aarch64-gnu` | runtime-verified under explicit QEMU user mode | unsupported | 2026-08-02 19:24:29 CST |
| `windows-x86_64-msvc` | runtime-verified on the authoritative native host | unsupported | 2026-08-02 |

Only `linux-x86_64-gnu` currently declares the `boot_image` capability.
Linux AArch64 and Windows stages record `boot_image.status = unsupported`;
`art-compiler.dll` does not imply a Windows image writer or loader.

## Latest Linux AArch64 acceptance

A fresh RelWithDebInfo `linux-aarch64-gnu` product was generated, configured,
audited, and built with the unified frontend, CMake, Ninja, plain GNU-style
Clang 21.1.8 drivers, the declared regular-file GNU sysroot/runtime bundle,
configured JDK 21, and pinned D8. The 32-job build completed 2,197 Ninja edges
for the 38-module graph. The W-004 catalog exposed exactly two applicable
runtime smokes: `art_runtime_show_version` and `managed_imageless_hello`.

QEMU user mode 10.2.1 from the official Ubuntu `qemu-user` package was bound
only through ignored local TOML. The shell-free gate supplied the declared
target sysroot as the loader root. Imageless Hello printed both required
markers and exited zero in 1.56 seconds; show-version reported
`ART version 2.1.0 arm64`, and the two-test stage passed in 1.91 seconds.

The result recorded only normalized runner identity. Its hashes were:

- QEMU runner:
  `6b8505bcdd48f1ff0214630a978214d8fe770049b2515d31b160bfa0c1804ebb`
- boot JAR:
  `45e19b8cc4a4161d7b7b011e268bf262069d9a7b70c9cfd9c37e324feb249eae`
- Hello JAR:
  `097d27a70a44af1f730cfb5aef15dee04610657eefbb07dfa33ac5babe1b7c00`

Staging copied 157 declared artifacts into 158 regular files including the
manifest, validated 32 AArch64 executable/DSO identities, retained only
`$ORIGIN` runtime paths, and found no filesystem links. The immediate full
product repeat reported `ninja: no work to do`. This admits an experimental
AArch64 interpreter/runtime smoke; it does not claim GC, JNI, JIT, boot-image,
or native-AArch64-host acceptance.

A follow-up rebuilt the four common sources that owned bring-up diagnostics
plus their dependent runtime DSOs and executable. The same AArch64 W-004 slice
passed 2/2 in 1.98 seconds. Its stderr retained the accepted
`main end exception=0` marker while using target-neutral `dalvikvm InvokeMain`
and `ART Runtime::Start` prefixes; no `Windows x64` text remained. Native
Windows rebuilt the same sources and passed W-004 twice at 36/36 in 52.10 and
52.00 seconds, with the second build a Ninja no-op. Its common-prefix audit
also found zero stale architecture labels. Actual x86-64 PE/JIT diagnostics
remain explicitly scoped and were not generalized.

## Latest Linux acceptance

A fresh RelWithDebInfo product was configured and built with the unified
Python frontend, CMake, Ninja, plain GNU-style Clang 21.1.8 drivers, configured
JDK 21, and pinned D8. The 32-job build produced:

| Artifact | Size | SHA-256 |
|---|---:|---|
| `x86_64/boot.art` | 7,854,704 | `66416220813724ea36fbbf297b269145244c15a42849586bddb9921c4b4533c0` |
| `x86_64/boot.oat` | 18,901,672 | `26522f53fc8f424607ba183ff483c7e3cfa4026a7585955db347decdf42a0ea6` |
| `x86_64/boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

The boot JAR SHA-256 was
`45e19b8cc4a4161d7b7b011e268bf262069d9a7b70c9cfd9c37e324feb249eae`.
The image manifest records only the canonical logical location
`/system/framework/boot.jar`; the manifest and all three binary artifacts were
scanned and contain no repository, output, toolchain, or temporary absolute
path.

The W-004 stage passed all six Linux gates. Both `managed_imageless_hello` and
`managed_boot_image_hello` printed `Hello from dalvikvm!`, reached
`main end exception=0`, and exited zero. The image-backed runner first verified
every manifest hash and size, copied the image into an isolated regular-file
runtime root, and launched ART without a shell. The complete stage result was
6/6 in 2.34 seconds.

Product staging began from an empty directory, included exactly the three
image artifacts plus `runtime/boot-image/manifest.json`, and recorded
`boot_image.status = included`. The stage and image contain no filesystem
links. A repeated complete product build reported `ninja: no work to do`.

## Cross-target boundary check

A fresh Linux-hosted `windows-x86_64-msvc` product still completed and staged
successfully. It generated no boot-image tree, recorded
`boot_image.status = unsupported`, and repeated as a Ninja no-op. This is an
explicit unsupported result, not a skipped-success claim.

## Maintained commands

```text
python3 tools/build_art.py configure --target-id linux-x86_64-gnu
python3 tools/build_art.py build --target-id linux-x86_64-gnu --parallel 32
python3 tools/build_art.py test --target-id linux-x86_64-gnu --stage w004 --parallel 32
python3 tools/build_art.py stage --target-id linux-x86_64-gnu
```

Use the same commands with `linux-aarch64-gnu`; its exact runner executable and
sysroot remain external bindings in `.art-build.local.toml`. Its W-004 stage
contains only the two AArch64 smokes described above.

Generated images, JARs, logs, result JSON, and stage trees remain under the
ignored frontend output root. No executable, DSO, image, archive, or routine
log from this acceptance is stored in VCS.
