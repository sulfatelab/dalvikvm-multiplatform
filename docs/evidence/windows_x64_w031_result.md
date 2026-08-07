# Windows x64 W-031 native result

**Date:** 2026-08-07

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS — boot-AOT unwind step 6 partial; real-dispatch step 10
partial**

## Scope and conclusion

W-031 is the first native executable boot-OAT unwind gate. It validates the
Windows-only `.oat_unwind.windows` transport, requires registered managed, JNI,
and all seven primary boot-trampoline entries, exercises synthetic
`RtlVirtualUnwind`, and then passes corresponding managed/JNI runtime calls
with JIT disabled. The authoritative markers were:

```text
W031_AOT_UNWIND_PASS managed_candidates=1 jni_candidates=1 trampolines=7 virtual_unwind=pass
W031AotUnwindProbe PASS managed_call=pass jni_call=pass
```

This makes implementation-sequence step 6 useful but not complete.
Corruption/fallback injection, managed exception/fatal stack walking, and
stronger execution coverage of a nonvolatile-XMM-bearing AOT frame remain.

Step 10 is also partial. Startup upgrades many eligible current entrypoints to
nterp. The probe uses `ArtMethod::GetOatMethodQuickCode()` to locate the
underlying compiled managed/JNI bodies. Its corresponding runtime calls can
still dispatch through nterp, so the result does not prove that representative
ordinary dispatch PCs remain inside the boot-OAT RX range.

CFG is independent and remains unimplemented.

## Source identity

The native overlay was deployed at:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
```

Its baseline commits were root `9fdc23a` and nested ART
`fd6accf065a550fc1e436cb9f28617b466f7593e`. The nested W-031 implementation
is `ba16ea923a9156ef5cbaebfabbc1dceba069889f`; the containing root commit owns
the runner, gate, and this result. Selected local/native-overlay files matched
byte-for-byte:

```text
tests/cases/aot-unwind/W031AotUnwindProbe.java
54ab9585fa29851fbd41937f90d3da279227a156a6d5e79160fbb47ac109bad5

tests/cases/aot-unwind/probe.cc
bc60cb87eeef2796200fed6a165a0b0b2e6564425f4beca9985cb3772d34860c

tools/run_windows_boot_image.py
008eb907f05f24c36aa0c26aa5b5f30b87929ba8495897cf955fc9c4a913747a

vendor/art/compiler/optimizing/code_generator_x86_64.cc
a84fa4746ce5af2971bbf041c9be74b4565e59b644c61cff679f007e911b6b6d

vendor/art/dex2oat/linker/elf_writer_quick.cc
e6802705c821683f56625ec81fd02586988a6d65778d4a446e7ab277e2ad3c99

vendor/art/runtime/multiplatform/windows/aot_unwind_windows.cc
b7e0b2d269dd34e880e6b5245f771741a0e297b50364bd09a72ca6eb27384347
```

## Native command and result

The final affected-stage rerun used the repository frontend:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w025 --stage w030 --stage w031 --parallel 16
```

The Server 2025 result was 12/12:

```text
W-025  9/9 PASS
W-030  2/2 PASS
W-031  1/1 PASS
```

The VM's existing Ninja dependency log emitted its known `premature end of
file; recovering` warning and rebuilt affected compiler objects. The rebuild
and all gates completed successfully.

Fresh agent01 validation also passed:

```text
focused Python harness tests                 21/21 PASS
full linux-x86_64-gnu build                 PASS
Linux catalog                               15/15 PASS
full windows-x86_64-msvc cross-build        PASS
root and nested git diff --check            PASS
```

## Transport and runtime evidence

The implemented writer:

- carries managed and JNI x64 unwind bytes in `CompiledMethod`;
- keys entries on final deduplicated code ranges;
- emits the seven primary boot trampolines;
- deduplicates identical `UNWIND_INFO` blobs;
- writes `.oat_unwind.windows` after `.data.img.rel.ro` in one read-only
  file-backed `PT_LOAD`;
- hashes the complete finalized section with the checksum field at byte 44
  treated as zero; and
- leaves the shared OAT version and Linux layout unchanged.

Both validation-only and executable opens derive bounds from dynamic anchors,
require the complete section in one exact file-backed `PF_R` `PT_LOAD`, and
require `Begin() + GetExecutableOffset()` through exclusive `End()` in one
exact file-backed `PF_R | PF_X` `PT_LOAD`. `Begin()` is `oatdata`; `End()` is
one-past the word addressed by `oatlastword`.

The version-1 parser accepts only flags-zero x64 `UNWIND_INFO`. It recognizes
nonvolatile GPR save/push operations, small/large allocation, frame-pointer
setup, near/far XMM128 saves, and machine frames; handler/chained records are
not accepted. Executable opens create one stable `RUNTIME_FUNCTION` array,
register it with `RtlAddFunctionTable()`, and verify sample lookups.
Validation-only opens never register. A failed `RtlDeleteFunctionTable()`
remains fatal so ART cannot release referenced code or metadata.

W-025 additionally proves full 128-bit nonvolatile XMM restoration. Windows
unwind-enabled managed frames use 16-byte slots and full-width `movdqu`
spills/restores, with `UWOP_SAVE_XMM128` or its far form.

## Accepted artifact and section measurements

The accepted path-sensitive cache set was:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `acfaced21898b7fe968c742cdedb80994a0a98a3505329f5f454d8ff8b4f6c32` |
| `boot.oat` | 19,827,936 | `b1d6111198cabc7914d7c87d07851fb73aa77b99959b353483ddea0207382ca9` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

The manifest's validated unwind measurements were:

| Quantity | Value |
|---|---:|
| Format version | 1 |
| PE/COFF machine | `0x8664` (`IMAGE_FILE_MACHINE_AMD64`) |
| Section bytes | 515,736 |
| Function entries | 42,663 |
| Unique `UNWIND_INFO` blobs | 163 |
| Code begin/end | 3,602,760 / 18,602,077 |
| Adler-32 | `f34e9e18` |

These figures supersede the pre-XMM characterization. OAT/ART outputs are
path-sensitive caches; this record binds one passing set and does not define a
byte-reproducibility requirement.

## Disposition

- Step 6 is `PARTIAL`: core transport, registration, lookup, virtual unwind,
  and JIT-disabled managed/JNI runtime calls pass; negative injection and
  deeper stack walking
  remain.
- Step 10 is `PARTIAL`: underlying boot-OAT bodies are locatable and the
  corresponding JIT-disabled runtime calls pass; representative ordinary
  dispatch inside boot-OAT RX ranges remains open.
- Step 7 and step 11 remain `NOT STARTED`: `.oat_cfg.windows` and the full CFG
  observation/OAT-1 measurement gate are not implemented.
- Application OAT, OAT-2, unloading, explicit CFG, and security hardening remain
  deferred.
