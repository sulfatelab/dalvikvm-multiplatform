# Windows x64 W-032 native result

**Date:** 2026-08-07

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS — CFG transport is complete; forced-policy observation
works; numbered step 11 remains partial**

## Scope and conclusion

W-032 is the first native boot-OAT CFG observation gate. The Windows x64
writer emits `.oat_cfg.windows` beside `.oat_unwind.windows`, the runtime
validates the target manifest on both OAT open paths, and a CFG-instrumented PE
caller enters representative quick and compiled-JNI boot-OAT bodies while the
launcher forces CFG on. The observation path never calls
`SetProcessValidCallTargets()` and therefore does not claim fine-grained target
enforcement. The follow-up gate also rejects 18 semantic corruptions through
real validation-only and executable `OatFile::Open()` calls and validates all
eight production-`ElfBuilder` metadata/relro layouts.

The authoritative markers were:

```text
W032_CFG_STRUCTURE_PASS cfg_flags=2 guard_dispatch=present dynamic_anchors=2 runtime_open_modes=2 corruption_cases=18 target_api_calls=0
W032_CFG_LAYOUT_PASS cases=8 relro_cases=4 metadata_segment_cases=6 shared_metadata_segment_cases=2
W032_CFG_TABLE_PASS machine=0x8664 targets=42649 quick_candidates=42367 jni_candidates=280 trampoline_candidates=7 checksum=9b1588cd
W032_CFG_OBSERVATION_PASS cfg_enabled=1 cfg_strict=0 cfg_export_suppression=0 guard_dispatch=verified guarded_quick=pass guarded_jni=pass target_api_calls=0
W032_CFG_CORRUPTION_PASS cases=18 opens=38 validation_only=19 executable=19
W032AotCfgProbe PASS
```

The implemented transport, exhaustive negative matrix, production layout
matrix, and live observation complete numbered step 7. The separate
invalid-by-default allocation experiment, commit/padding/startup measurements,
and any explicit-target decision remain for step 11.

## Source identity

The native overlay was deployed at:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
```

The follow-up matrix work was deployed from root baseline
`f1aff872725a98f514a29dcd5bc0bf0c30a08003`. The final nested W-032
implementation remains
`30db175a1240780c23c674e5bf29d281570becfd`; this record's containing root
commit owns the expanded runner, probes, tests, and documentation.

Selected final overlay files had SHA-256:

```text
vendor/art/runtime/multiplatform/windows/aot_cfg_windows.cc
a8e5eab0423b64e4e444e1e79dce0131193c0372c9cc4d0042e1a383b4c4a608

tests/cases/aot-cfg/probe.cc
279d7355b2f990ef4736abff72297070aa98832a11329e486d52475c103325e8

tests/cases/aot-cfg/layout_probe.cc
dcc00817efd739b69a13236b851c3f6ec7826e9802a248e65269f13722459d0d

tests/cases/aot-cfg/guarded_invoke_x86_64.S
e54efc2ec8565f4dfcf53a0a6b2473a1921afe7507b7c70e7bc8a5a75fa5c705

tools/run_windows_boot_image.py
44292c6d1d282330d2402df01867cabfa351ea8a48e9caf1e2b4e2df3f6f1219

tools/run_dex2oat_no_image.py
043d9dad2d071f27595132eb203b05f1c693a176a9b2ec13cefe151626e0d909

tests/support/windows/check_w032_cfg_contract.py
b9c46b017415e2411322c0c21f6bc6dffe6d82b817ca5ba454668479c4a2cf54

tests/support/windows/check_w032_cfg_layout.py
7f1c7fd338336d2b8d75b95e66cb374bb683bd8abc18463ad934ae4b2b5f2698
```

## Native commands and result

After deploying the final formatted sources, the affected stage was rebuilt:

```text
cmake.exe --build C:\mdvm-w028-8d3037c\out\windows-x86_64-msvc\RelWithDebInfo \
  --target art-test-stage-w032 -j 16
```

The existing Ninja dependency log emitted its known `premature end of file;
recovering` warning. Recovery and the stage rebuild completed successfully and
produced a fresh path-sensitive boot cache set. The authoritative tests were
then run together:

```text
ctest.exe \
  --test-dir C:\mdvm-w028-8d3037c\out\windows-x86_64-msvc\RelWithDebInfo \
  -V -R ^art\.w032\.
```

Result:

```text
art.w032.windows_w032_cfg_structure  PASS  0.16 s
art.w032.windows_w032_cfg_layout     PASS  0.26 s
art.w032.managed_w032_aot_cfg        PASS  3.21 s
3/3 PASS
```

Fresh agent01 regression evidence also passed:

```text
Python bp2cmake/tool suite                         225/225 PASS
linux-x86_64-gnu configure and target audit       PASS
  2,089 compile commands; 2,172 Ninja commands; 32 product links
full linux-x86_64-gnu build and boot generation   PASS
Linux catalog                                     15/15 PASS
root and nested git diff --check                  PASS
```

The Linux boot OAT retained the ordinary Linux ART coat: ELF64/ET_DYN/x86-64,
GNU OSABI 3, ABI version 0, flags 0, four non-W+X 16-KiB `PT_LOAD` segments,
and no Windows unwind/CFG sections or dynamic anchors.

## Transport and runtime evidence

The final writer independently collects every compiled quick/JNI target,
merges diagnostic roles when code is deduplicated, adds the seven primary boot
trampolines, and asserts that the x86-64 patcher emitted no relative or
miscellaneous thunk bytes before marking the set complete. A sorted map gives
canonical section ordering within one cache generation. The version-1
section-local Adler-32 is calculated with only its checksum field zeroed; the
shared OAT version and Linux output are unchanged.

`.oat_cfg.windows` follows `.oat_unwind.windows` in the same read-only
file-backed `PT_LOAD` and has two dynamic anchors. The narrow runtime owner
validates the header, code range, checked array size, checksum, sorted unique
targets, known roles, and final mapped-address alignment. It records CFG,
strict-mode, and export-suppression policy bits but owns no OS registration
handle and has no rollback action.

The negative gate preserves a canonical OAT/VDEX pair and creates 18 mutations
covering every serialized header field plus entry bounds, alignment, ordering,
and role bits. The canonical file opens once in each mode; each corrupt file is
rejected once with `executable=false` and once with `executable=true`, for 38
real opens total. Every rejection must carry a CFG-specific diagnostic.

The layout gate directly instantiates the production header-only `ElfBuilder`
under the Windows target definitions and emits neither, unwind-only, CFG-only,
and combined metadata, each with and without `.data.img.rel.ro`. All eight
layouts retain 64-KiB `PT_LOAD` alignment/congruence, non-W+X protections,
unchanged `oatlastword`, conditional anchors, and exactly one read-only
metadata segment whenever metadata exists. The two combined cases share that
segment between unwind and CFG.

An important implementation correction came from native generation. An
`oatdata`-relative `code_offset` need not itself be a multiple of 16 because
`oatdata` can have nonzero low address bits. The writer now checks the
congruent file offset, the runtime checks `mapped_oatdata + code_offset`, and
the out-of-process validator checks the ELF `.rodata` address plus the offset.
No Windows-only method padding or layout divergence was added.

The PE caller reports `CF_INSTRUMENTED`, `CF_FUNCTION_TABLE_PRESENT`, and a
nonzero guard dispatch pointer. Its bridge reaches the exact OAT addresses
through `__guard_dispatch_icall_fptr`. The native calls return the expected
managed `Math.abs(int)` result and a nonzero compiled `System.nanoTime()` JNI
result under forced CFG. Source and runtime evidence both report zero
`SetProcessValidCallTargets()` calls.

## Accepted artifact and section measurements

The accepted path-sensitive cache set was:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `4a2d25732c1cc8a5c79a05269e95eb3b1b5b9f02da884ed02c0a0f061ee4ce22` |
| `boot.oat` | 20,169,352 | `0a7a6e5fdf129efd9b36975b3b95f807f8ed163fb939ff19cff8cbd6e9028eb8` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

The manifest's validated CFG measurements were:

| Quantity | Value |
|---|---:|
| Format version | 1 |
| PE/COFF machine | `0x8664` (`IMAGE_FILE_MACHINE_AMD64`) |
| Section bytes | 341,240 |
| Unique targets | 42,649 |
| Quick candidates | 42,367 |
| JNI candidates | 280 |
| Trampoline candidates | 7 |
| Indirect-callable thunk candidates | 0 |
| Code begin/end | 3,602,664 / 18,600,765 |
| Adler-32 | `9b1588cd` |

Candidate counts can overlap because one deduplicated address may carry more
than one role. These figures characterize one passing cache set. ART/OAT
outputs are path-sensitive caches, so neither these values nor the artifact
hashes define a cross-generation byte-reproducibility requirement.

The final CFG probe DLL was 62,464 bytes with SHA-256
`ec4de70c9d8c76ca9804186e7840e76765e378bd83104497daf4c4dcf5499390`.
The layout probe executable was 108,544 bytes with SHA-256
`d85087fa067645d32b158130b1011dc4488fad23fe22d868948ad46e0b4dda01`.

## Disposition

- Step 7 is `COMPLETE`: the writer, ELF transport, both loader modes, policy
  snapshot, semantic corruption corpus, all eight production layouts,
  structural validator, and live executable-open gate pass.
- Step 11 is `PARTIAL`: forced-CFG observation and guarded incoming quick/JNI
  calls pass with default-valid OAT-1 executable pages; the separate allocation
  feasibility and resource measurements remain.
- This result does not enable explicit targets, outgoing quick-code CFG
  instrumentation, application OAT, OAT-2, unloading, XFG, or security
  hardening.
