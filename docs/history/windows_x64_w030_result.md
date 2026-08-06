# Windows x64 W-030 native result

**Date:** 2026-08-06

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100
(`Microsoft Windows [Version 10.0.26100.32230]`)

**Status:** **PASS — private-copy steps 4/5 and boot generation step 8
complete; selection step 9 partial**

Acceptance interpretation corrected 2026-08-07: ART/OAT artifacts are
path-sensitive cache outputs. Byte identity across separate generations is not
an acceptance requirement; one manifest must instead bind and validate the
matching set produced by that generation.

## Scope and conclusion

W-030 is the first native Windows boot-image/OAT loading gate. It first tests
the Windows-only checked private-copy primitive directly, then generates and
stages the W-029 single-component boot set and starts ART from the package
root. The two gates passed 2/2:

```text
windows_w030_private_copy_probe  PASS  0.07 s
windows_w030_boot_image_startup  PASS  1.13 s
```

This completes implementation-sequence step 4, the boot-only scope of step 5,
and step 8. The launcher is an explicit experimental gate rather than product
selection with proven successful imageless fallback, so step 9 remains
partial. The startup uses `-Xint`; it proves validation-only and executable
ELF/VDEX/image loading, not execution of a method from the boot-OAT RX range.
Unwind, CFG observation, real AOT execution, and measurements are not claimed.

## Source identity

The accepted native overlay was built from:

```text
root baseline             4a65328
root W-030 implementation a0400259954d95161f45c74d3a8a4317a3427a62
no-byte-identity policy   1a9aa837ad2fb697d246855c695d44f2b53c69e8
ART baseline              681f2f38a295602a1d04e21febb63b7e26e19103
ART private-copy commit   fd6accf065a550fc1e436cb9f28617b466f7593e
```

The final local and native-overlay sources matched byte-for-byte:

```text
tests/CMakeLists.txt
d58155b3743f676bf336dbdaf29b53c0b313e263034a55e9c4dfadd17ae6e1cb

tests/cases/aot-private-copy/probe.cc
cf6a37acf75c46d3ab4e30d0e350b8d524d5d5be5323ba2c278dd018f8764d60

tools/build_boot_image.py
8ca10d73fc5434604f2f3404b6c5d844acf42942828c8c7138f13cdfb2ea8aee

tools/run_dex2oat_no_image.py
97b0d3719f2387b837740cc837c4405d4e471605221d0080f4499822b072d7d4

tools/windows_aot_identity.py
29c091923095c885bb3c9e19ac74d343888a0e8a1b0c84cddcfcf3ef09ab65f9

tools/run_windows_boot_image.py
9ffe0f2085919444f1f24a41d9f377b6c26b9ea469d6be0b6dd18ff40b8d5912

vendor/art/libartbase/base/mem_map.h
ba783c638f01a0494d0623f2ccbad73f136e4f1e94ed57f1393c7e6180c743f2

vendor/art/libartbase/base/mem_map_windows.cc
2ce8f6a1d7f18993b1d07bacc23cd56b2b651504131d47d4aa58c074b6542b56

vendor/art/runtime/oat/elf_file.cc
3a889628fdfc017142df919770970f453a24f2746836fe2fb2b1c6c6bf796801

vendor/art/runtime/vdex_file.cc
ce2c2997f010a526e0e8851c8c2aa11f38b0dbd72b75495fa78b24862ead5974
```

The final target-binding audit accepted 2,082 compile commands, 2,126 Ninja
commands, and 30 product links.

## Private-copy gate

`MemMap::MapFileAtAddressPrivateCopy()` accepts only a page-aligned checked
file range inside one ART-owned `MEM_PRIVATE` allocation. It temporarily uses
RW/NX, copies the exact bytes, restores the loader-selected R, RX, or RW/NX
protection, and flushes executable ranges. Windows ELF loading uses it for
file-backed `PT_LOAD` bytes in validation-only and executable opens. Reused
Windows VDEX mappings use it for the `oatdex` aperture. Linux retains its
original `MapFileAtAddress(..., reuse=true)` paths.

The direct native marker was:

```text
W030_PRIVATE_COPY_PASS page=4096 allocation_granularity=65536 range=checked protections=R_RX_RW gaps=noaccess zero_fill=verified ownership=shared source=private cache=flushed
```

The probe covers foreign allocation, section-view, unaligned-address, and
file-bounds rejection; exact placement and bytes; R/NX, RX, and RW/NX final
pages; no-access gaps; anonymous zero fill; shared owner lifetime; source-file
privacy; and executable cache flushing. The boot gate then covers the loader
and VDEX integration end to end.

## Image format diagnosis

The first native run generated an uncompressed `boot.art`. ART could not
replace the already committed private Windows boot reservation with the file
view and logged:

```text
mmap(... boot.art ...) failed: Invalid argument
Attempting to fall back to imageless running
InitWithoutImage
```

Managed `Hello` still completed, validating the gate's rule that a zero exit is
insufficient. Windows generation now selects ART's existing LZ4 format so the
image is decompressed into anonymous memory. Linux generation remains
uncompressed; no shared image-format default changed.

## Canonical generation and startup

The generator and launcher consume the same W-029 record:

```text
component topology   single: boot
logical boot JAR     /system/framework/boot.jar
package boot JAR     runtime/boot.jar
startup image        runtime/boot-image/boot.art
physical boot set    runtime/boot-image/x86_64/boot.{art,oat,vdex}
image format         lz4
parallelism          16
```

The launcher validates the manifest, boot-JAR hash, artifact set, sizes and
hashes; stages only the canonical topology; runs from `package`; and passes
exact `-Ximage:runtime/boot-image/boot.art`. It rejects all seven W-029
identity mismatches before spawn and rejects the imageless fallback markers.
The accepted result records:

```text
actual_exit: 0
missing_markers: []
forbidden_markers: []
launcher_rejected_mismatches: 7
```

The final accepted artifacts were:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `e344c202362867aead20cd4c1d30281bc2b902ec84cda433ca58ee0089dae4b6` |
| `boot.oat` | 18,754,624 | `73367849da408025f67a795e0618d7f062e9f82029351523bbdb99516360d6bc` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

W-028 and W-029 regressions passed from the final no-forced-determinism overlay
in 0.64 and 0.12 seconds respectively.

## Repeated-generation characterization

During the initial investigation, normal-parallel and three `-j1` generations
under the now-removed `--force-determinism` request all loaded and started
successfully. `boot.vdex` remained byte-identical, while `boot.art` hashes and
`boot.oat` `.text` sizes varied. The corrected generator no longer requests
forced byte determinism. Normal Windows parallelism remains 16 and is recorded
in every manifest.

This variation is expected to be acceptable for path-sensitive cache
artifacts. The contract is per-generation set integrity: logical locations are
intentional, the manifest records the three matching artifact sizes/hashes,
and the launcher revalidates that exact set before startup. Cross-generation
byte comparison is neither a step-8 gate nor a reason to force serial
generation.

## Disposition

- Step 2 remains `PARTIAL`: canonical generation/startup is accepted, while
  intentional negative cases are launcher-level rather than ART diagnostics.
- Steps 4 and 5 are `COMPLETE` for boot-only OAT-1.
- Step 8 is `COMPLETE`: generation, per-set manifest binding, validation,
  staging, and canonical startup pass; cross-generation byte identity is not
  required.
- Step 9 is `PARTIAL`: fallback is detected and rejected by an experimental
  gate; normal selection and successful fallback are not integrated.
- Steps 6, 7, 10, and 11 remain open: unwind, CFG, real boot-OAT execution, and
  measurements.
