# Windows x64 W-029 native result

**Date:** 2026-08-06
**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100
**Status:** **PASS — step-2 identity preflight accepted; sequence step 2 remains partial**

## Scope

W-029 is a host-side preflight for the boot-only Windows AOT generation/startup
identity contract. It pins the first boot-set topology and exact path strings,
then requires deterministic diagnostics for deliberate mismatches. It does not
generate a Windows boot image, invoke `ImageWriter`, start ART with that image,
or prove that ART itself reports the same mismatch cases. Those remain the
exit conditions for implementation-sequence step 2.

## Source identity

The native gate reused the accepted W-028 compiler workspace and applied the
committed W-029 overlay:

```text
accepted root base  ef507bb9b63f0184c0bf11a1d9d98c0ae8d819f8
W-029 overlay       6a9b27149e0aa93468d15f7370c8f5a1352675d4
ART                 681f2f38a295602a1d04e21febb63b7e26e19103
```

The three overlaid native-gate files matched the committed local SHA-256
identities:

```text
tools/run_dex2oat_no_image.py  dbaf123c0e1302ce9b062ee42362dbc6b5f729f9cc61712154f8647ff9cbee4c
tools/windows_aot_identity.py   f1559d7411d76338e72543d80028dc277ca9c6ac9d24fbae48beb09e481b2024
tests/CMakeLists.txt             7f9d53860795026f4706f8b90d1aea73566429f3b38c4dce3b5ce9e7f0a9b7e8
```

The target-binding audit remained unchanged at 2,081 compile commands, 2,126
Ninja commands, and 30 product links. Reconfiguration succeeded, and the
W-029 stage build returned `ninja: no work to do.`

## Selected contract

The initial boot-only Windows set has one `boot` component:

```text
logical boot JAR       /system/framework/boot.jar
package boot JAR       runtime/boot.jar
startup image option   -Ximage:runtime/boot-image/boot.art
package boot image     runtime/boot-image/x86_64/boot.art
package boot OAT       runtime/boot-image/x86_64/boot.oat
package boot VDEX      runtime/boot-image/x86_64/boot.vdex
```

The launcher will use the package root as its working directory and always
pass the explicit package-relative `-Ximage:` value. ART inserts the x86-64 ISA
directory when resolving the image. The boot-class-path text remains the same
ASCII bytes at generation and startup; it is not case-folded, separator-
normalized, or replaced with a physical package path.

## Native gate

The authoritative command was:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --build-type RelWithDebInfo \
  --output-root <native-output-root> \
  --parallel 2 \
  --stage w029
```

CTest passed 1/1 in 0.13 seconds. The canonical generation/startup records
matched byte-for-byte, and all seven intentional mismatches produced the
expected field-specific diagnostic:

```text
boot-class-path: case, separator, physical absolute path
image-location:  case, separator, physical absolute path
topology:        unexpected second component
```

## W-028 regression

W-028 was rerun from the same native tree after its logical constants were
moved to the shared identity contract. It passed 1/1 in 0.68 seconds. Only the
manifest gained the selected identity record; artifact bytes remained:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `probe.oat` | 66,888 | `fa03ad2f48f7a83bc8c6ddbf42620454f336d8c870e339771fc3edc88eb615f7` |
| `probe.vdex` | 1,000 | `cc1b8db5d41a00c51a380c27020e69e97cf987e0e0ee9b44a0b7995c703073c1` |

## Disposition

The W-029 preflight is accepted and the identity choice is no longer open.
Sequence step 2 remains `PARTIAL`: the Windows boot-image generator and
experimental launcher must consume this exact contract, a generated artifact
must retain the strings, and native ART startup must accept the canonical set
and diagnose intentional mismatches before this step becomes complete.
