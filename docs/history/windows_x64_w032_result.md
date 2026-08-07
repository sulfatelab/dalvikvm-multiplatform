# Windows x64 W-032 native result

**Date:** 2026-08-07

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS — CFG metadata and forced-policy observation work; numbered
steps 7 and 11 remain partial**

## Scope and conclusion

W-032 is the first native boot-OAT CFG observation gate. The Windows x64
writer emits `.oat_cfg.windows` beside `.oat_unwind.windows`, the runtime
validates the target manifest on both OAT open paths, and a CFG-instrumented PE
caller enters representative quick and compiled-JNI boot-OAT bodies while the
launcher forces CFG on. The observation path never calls
`SetProcessValidCallTargets()` and therefore does not claim fine-grained target
enforcement.

The authoritative markers were:

```text
W032_CFG_STRUCTURE_PASS cfg_flags=2 guard_dispatch=present dynamic_anchors=2 target_api_calls=0
W032_CFG_TABLE_PASS machine=0x8664 targets=42657 quick_candidates=42375 jni_candidates=280 trampoline_candidates=7 checksum=8a4f8dc2
W032_CFG_OBSERVATION_PASS cfg_enabled=1 cfg_strict=0 cfg_export_suppression=0 guard_dispatch=verified guarded_quick=pass guarded_jni=pass target_api_calls=0
W032AotCfgProbe PASS
```

The implemented transport and live observation make both numbered steps
useful, but not complete. The exhaustive header/entry mutation matrix through
both ART open modes and the eight-combination ELF layout matrix remain to be
automated for step 7. The separate invalid-by-default allocation experiment,
commit/padding/startup measurements, and any explicit-target decision remain
for step 11.

## Source identity

The native overlay was deployed at:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
```

Its checked-in baselines were root
`62a9783905c9ff03b7fcc6ac9e4dbe50907bf51c` and nested ART
`ba16ea923a9156ef5cbaebfabbc1dceba069889f`. The final nested W-032
implementation is
`30db175a1240780c23c674e5bf29d281570becfd`; the containing root commit owns
the runner, probe, tests, documentation, and submodule update.

Selected final overlay files had SHA-256:

```text
vendor/art/runtime/multiplatform/windows/aot_cfg_windows.cc
a8e5eab0423b64e4e444e1e79dce0131193c0372c9cc4d0042e1a383b4c4a608

tests/cases/aot-cfg/probe.cc
45624c38701d0f83d3528dc27a978b48c79c52e480e08f113da069477e4bf83a

tests/cases/aot-cfg/guarded_invoke_x86_64.S
e54efc2ec8565f4dfcf53a0a6b2473a1921afe7507b7c70e7bc8a5a75fa5c705

tools/run_windows_boot_image.py
06fd27a0f66e266a6d3101befb646816a33269f5ffc66433fcf1e8dc776c0347

tests/support/windows/check_w032_cfg_contract.py
a8355af55fff9541bf3b338a9735641a4ea39a13a73a736844dbac199f70174f
```

## Native commands and result

After deploying the final formatted sources, the affected stage was rebuilt:

```text
cmake.exe --build C:\mdvm-w028-8d3037c\out\windows-x86_64-msvc\RelWithDebInfo \
  --target art-test-stage-w032 -j 16
```

The existing Ninja dependency log emitted its known `premature end of file;
recovering` warning. The 45-action rebuild completed successfully and produced
a fresh path-sensitive boot cache set. The authoritative tests were then run
verbosely:

```text
ctest.exe \
  --test-dir C:\mdvm-w028-8d3037c\out\windows-x86_64-msvc\RelWithDebInfo \
  -V -R ^art\.w032\.
```

Result:

```text
art.w032.windows_w032_cfg_structure  PASS  0.20 s
art.w032.managed_w032_aot_cfg        PASS  1.39 s
2/2 PASS
```

Fresh agent01 regression evidence also passed:

```text
Python bp2cmake/tool suite                         224/224 PASS
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
| `boot.art` | 2,940,464 | `657d778fb3fb645e7fa6c19ca4cdd7c7ca2a72414824b0e5f773008c2836dc2c` |
| `boot.oat` | 20,169,416 | `62fd1ed085ff65d0c1aca14e64196137131e5af08c8ae9c580308fb9dd6aa788` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

The manifest's validated CFG measurements were:

| Quantity | Value |
|---|---:|
| Format version | 1 |
| PE/COFF machine | `0x8664` (`IMAGE_FILE_MACHINE_AMD64`) |
| Section bytes | 341,304 |
| Unique targets | 42,657 |
| Quick candidates | 42,375 |
| JNI candidates | 280 |
| Trampoline candidates | 7 |
| Indirect-callable thunk candidates | 0 |
| Code begin/end | 3,602,664 / 18,601,981 |
| Adler-32 | `8a4f8dc2` |

Candidate counts can overlap because one deduplicated address may carry more
than one role. These figures characterize one passing cache set. ART/OAT
outputs are path-sensitive caches, so neither these values nor the artifact
hashes define a cross-generation byte-reproducibility requirement.

The final CFG probe DLL was 25,600 bytes with SHA-256
`b5bcaadb84bb8969182aec18df0cebbd491125b755802fcca89a40ccb47f05e3`.

## Disposition

- Step 7 is `PARTIAL`: the writer, ELF transport, loader parser, policy
  snapshot, structural validator, and live executable-open gate work; the
  exhaustive two-open-mode corruption and eight-case layout matrices remain.
- Step 11 is `PARTIAL`: forced-CFG observation and guarded incoming quick/JNI
  calls pass with default-valid OAT-1 executable pages; the separate allocation
  feasibility and resource measurements remain.
- This result does not enable explicit targets, outgoing quick-code CFG
  instrumentation, application OAT, OAT-2, unloading, XFG, or security
  hardening.
