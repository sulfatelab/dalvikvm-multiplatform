# Managed runtime boot-mode result

**Status:** PASS for imageless and generated-boot-image Linux x86-64 runtime

**Latest acceptance:** 2026-08-02

## Contract

This case proves that the unified Linux x86-64 ART product can run the same
D8-produced Hello application in two explicit boot modes:

- imageless interpreter mode, with `-Ximage` pointing at an unavailable image;
- packaged-image mode, with a generated `boot.art`, `boot.oat`, and `boot.vdex`
  matched to the exact target-local boot JAR.

The adjacent GC stress source separately exercises allocation and collection
through the same isolated runtime-gate infrastructure. These results do not
claim Windows AOT/OAT support or support for another Linux architecture.

## Target status

| Target ID | Imageless | Boot image | Last accepted |
|---|---:|---:|---:|
| `linux-x86_64-gnu` | runtime-verified | runtime-verified | 2026-08-02 14:22:00 CST |
| `windows-x86_64-msvc` | runtime-verified on the authoritative native host | unsupported | 2026-08-02 |

Only `linux-x86_64-gnu` currently declares the `boot_image` capability.
Windows stages `boot_image.status = unsupported`; `art-compiler.dll` does not
imply a Windows image writer or loader.

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

Generated images, JARs, logs, result JSON, and stage trees remain under the
ignored frontend output root. No executable, DSO, image, archive, or routine
log from this acceptance is stored in VCS.
