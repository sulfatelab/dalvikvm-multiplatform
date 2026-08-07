# Windows x64 W-039 native result

**Date:** 2026-08-08

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS — semantic unwind corruption, registration lifetime, and
diagnosed whole-transaction imageless fallback are proven; numbered step 6
remains partial only for actual XMM-bearing boot-AOT frame execution**

## Scope and conclusion

W-039 closes the `.oat_unwind.windows` corruption/ordinary-rollback condition
with one generated cache set and two linked native checks:

- 23 independently checksummed corruptions cover the serialized header and
  checksum, function entries, version-1 AMD64 `UNWIND_INFO` operations, and
  odd-slot padding;
- validation-only and executable `OatFile::Open()` reject every corruption
  with an unwind-specific diagnostic;
- canonical executable opens register the first entry through
  `RtlLookupFunctionEntry()`, and OAT destruction removes that entry before the
  mapping is released; and
- replacing the staged boot OAT with each corruption produces ART's diagnosed
  imageless fallback, exit zero, and an empty boot image-space list. The
  canonical OAT is restored in the runner's cleanup path.

The authoritative markers were:

```text
W039_UNWIND_CORRUPTION_PASS cases=23 opens=50 validation_only=25 executable=25 lifecycle=clean
W039_UNWIND_FALLBACK_MATRIX_PASS cases=23 diagnostics=unwind image_spaces=0
```

The 50 native opens comprise four canonical opens and 46 corrupt rejections,
split evenly between validation-only and executable mode. The fallback matrix
records 23/23 unwind diagnoses, 23/23 imageless-fallback markers, 23/23 empty
boot image-space checks, and 23 zero exits.

This is the ordinary unpublished-load failure path. It does not weaken the
fatal invariant for a failed `RtlDeleteFunctionTable()` call after a table has
been registered.

## Corruption coverage

The generated cases are grouped as follows:

| Layer | Cases | Mutations |
|---|---:|---|
| Header/checksum | 12 | magic, version, header size, target machine, entry size/count/offset, unwind offset/size, code begin/end, checksum |
| Function entries | 7 | before-code, overlap, empty, after-code, unaligned info, info before blob, info at section end |
| `UNWIND_INFO` and padding | 4 | unsupported version, volatile register, unsupported operation, nonzero odd-slot padding |

The host validator now mirrors the runtime parser's supported operation set,
multi-slot lengths, nonvolatile GPR/XMM classes, descending prologue offsets,
frame-register consistency, odd-slot padding, and zero trailing-byte checks.
That prevents the corpus generator from accepting a canonical descriptor that
the runtime would reject for a semantic reason unrelated to the intended
mutation.

## Source identity

The native overlay used:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
bundle  C:\mdvm-unified-20260730\bundle
```

The local root baseline before W-039 was
`d7887662cfa1eda2676aca6907d8f376d5a71af2`. W-039 requires no nested ART
change; the accepted nested snapshot remains
`c2ac04128f186388f43162e71fc268452cf1d959`. The existing native source tree
was updated with the exact W-039 files below before configuration and testing.
Local and native SHA-256 values matched:

```text
tests/CMakeLists.txt
11d0061846d1428cf14db8407a60a216419a00594c8eca11ce69fe36aeda9e31

tools/run_dex2oat_no_image.py
a34bb616d6237297a1d6002f6d74767fc6994682343eaf7e144f52e0ed55e386

tools/run_windows_boot_image.py
24b37608626b8c78737a17764f815ec85d3bf3c890ae34b64a19ba31681331a7

tests/cases/aot-unwind-corruption/probe.cc
e5bc6efc2ce3872c348ead9b12905abcfc0957905fa4cc4d669e4888fe65c454

tests/cases/aot-unwind-corruption/W039BootOatUnwindCorruptionProbe.java
56ce839843a021048cb1da6064de4892be3ed7369f2f55332bfd382350cb5bec

tests/cases/aot-unwind-corruption/W039BootOatUnwindFallbackProbe.java
98d75dd111393ad9d6d11bc24d12e6d1655f39a93f28815a24e784e15942e8f0
```

The native probe DLL was 57,344 bytes with SHA-256
`f9bd3c34c2c986a609dc83d52b18f981558d5161aaf1d772f5d836a4c2daa03c`.

## Native commands and results

The focused gate and affected-stage regression used the repository frontend:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w039 \
  --parallel 16

python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w030 --stage w031 --stage w032 \
  --stage w036 --stage w037 --stage w038 --stage w039 \
  --parallel 16
```

The focused W-039 gate passed `1/1` in 22.37 seconds. The fresh affected-stage
run passed all ten CTest cases in 35.19 seconds:

```text
W-030  2/2 PASS
W-031  1/1 PASS
W-032  3/3 PASS
W-036  1/1 PASS
W-037  1/1 PASS
W-038  1/1 PASS
W-039  1/1 PASS
10/10 PASS
```

Fresh `agent01` development evidence passed:

```text
Focused W-039 host/catalog Python tests             39/39 PASS
Python host and bp2cmake suite                     322/322 PASS
Linux-hosted windows-x86_64-msvc W-039 cross-build       PASS
  2,093 compile commands; 2,130 Ninja commands; 31 product links
root git diff --check                                    PASS
```

## Accepted cache set

The focused native run recorded this path-sensitive cache set:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `9e9dc2c7e022974ce92ed084c761b6b5b42e98314126b5649e85a7aa22c2a2ff` |
| `boot.oat` | 20,169,440 | `03014b82139b30a586e8c6f68824e94c2eed087b95633a4333c7d824dd16d155` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

These values identify the accepted generation. ART/OAT outputs remain
path-sensitive cache artifacts and are not required to match another
generation byte for byte.

## Disposition

- Retain W-039 as the semantic corruption, real-open, registration-lifetime,
  and unwind-fallback regression.
- Keep numbered step 6 `PARTIAL` only for an actual XMM-bearing boot-AOT frame
  that proves nonvolatile restoration. W-037/W-038 do not substitute for that
  check.
- Credit W-039 as one successful-fallback member of step 9. Reviewed product
  selection and missing/stale/wrong-target/cross-artifact fallback remain.
- Keep the finite step-10 execution matrix and OAT-1 measurement/W-033
  decision work separate from this accepted transport result.
