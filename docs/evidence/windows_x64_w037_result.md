# Windows x64 W-037 native result

**Date:** 2026-08-07

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS - focused relocation, managed boot-OAT fault, and BSS
GC-root survival are proven; numbered step 10 remains partial**

## Scope and conclusion

W-037 extends W-036's ordinary boot-OAT dispatch evidence in one coherent,
JIT-disabled native process. It requires:

- a nonzero boot-image relocation divisible by the Windows 64-KiB artifact
  alignment;
- the live boot OAT to retain the same relocation delta;
- an ordinary Java null call through a method whose current entrypoint is its
  registered boot-OAT quick code;
- exactly one access violation on the test thread inside registered boot-OAT
  RX code, recovered by ART as a caught `NullPointerException`; and
- one non-null OAT BSS GC root to remain the same object through allocation
  pressure and eight explicit GC rounds.

The accepted cache selected `Arrays.sort(int[])`. The observer VEH did not
modify the exception context or claim the exception; it returned
`EXCEPTION_CONTINUE_SEARCH` so ART's existing managed-fault path performed the
recovery. The Java exception had a nonempty stack trace. The final regression
stderr recorded eight completed explicit concurrent mark-sweep collections.

The authoritative final markers were:

```text
W037_BOOT_OAT_EXECUTION_PASS target=void java.util.Arrays.sort(int[]) relocation=nonzero_aligned delta=-253952000 oat=paired fault=managed_oat hits=1 fault_address=low gc_rounds=8 gc_completed=8 bss_roots=1 root_same=1 jit=disabled
W037BootOatRelocationFaultGcProbe PASS relocation=observed fault=recovered gc_roots=survived jit=disabled
```

This closes the focused nonzero-relocation, managed-null-fault, and BSS-root
case. It does not establish every relocation sign/topology, implicit-fault
form, root slot/collector combination, broader managed exception path, or fatal
stack walk, so numbered step 10 remains `PARTIAL`.

## Source identity

The native overlay used:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
bundle  C:\mdvm-unified-20260730\bundle
```

The deployed root baseline was
`e0d65a176ca409d48539980a48faf3b78ae37397`. Nested ART remained clean at
`03d55ca0174dbf39b54444ce5fdf4a55e5dce331`; W-037 required no runtime or
nested-repository change. The containing root commit owns the probe, catalog
entry, accepted record, and consistency updates.

The final local and native-overlay probe inputs matched byte-for-byte:

```text
tests/CMakeLists.txt
7579c73672add9f6afe61f20c48408dd84c62170d32a254dda8e4ea7605da1f5

tests/cases/aot-relocation-fault-gc/probe.cc
dda6bba52745ca31d50a40c0aed34c4fda0a842419138fc8f5250e92e7210ac0

tests/cases/aot-relocation-fault-gc/W037BootOatRelocationFaultGcProbe.java
9bf946785253613bedf5bf551957fc80bb00041db519536f9aeb0046d3faf074
```

The final native probe DLL was 49,664 bytes with SHA-256
`7adea24eaf0aa01823e2f63b359ae096f85c729068d4edd1f19c4d0a2b6c94d0`.
PE relinks are not required to be byte-identical.

## Probe contract

The native setup reads the persisted `boot.art` header and compares it with the
live single `ImageSpace`. It rejects zero or misaligned relocation, and rejects
an OAT whose live base differs from the persisted OAT base by any other delta.
Candidate selection also requires:

- `ArtMethod::GetEntryPointFromQuickCompiledCode()` to equal
  `GetOatMethodQuickCode()`;
- the entrypoint to lie inside the executable OAT range; and
- `RtlLookupFunctionEntry()` to resolve the exact entry through an image base
  containing a valid OAT header.

The Java side primes four ordinary `java.util.Arrays` methods and then invokes
the selected candidate through a statically typed call. The accepted run uses
`Arrays.sort((int[]) null)`. The VEH counts only access violations on the
registered test thread and separately counts those whose PC is inside the boot
OAT RX range. Verification requires exactly one of each, a low fault address,
and a registered function containing the observed PC.

Before arming the observer, the probe scans `OatFile::GetBssGcRoots()` and
keeps only a JNI weak reference to the first non-null root. After eight rounds
of allocation pressure and `System.gc()`, it requires the heap's completed-GC
counter to advance by at least eight, the slot to remain non-null, the weak
reference to remain live, and `IsSameObject()` to identify the slot and weak
reference as the same object. It also requires the selected method to retain
the exact registered OAT entrypoint captured before execution.

## Native commands and results

The focused gate used the repository frontend:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w037 \
  --parallel 16
```

The strengthened focused execution passed `1/1` in 1.29 seconds. The existing
Ninja dependency log emitted its known `premature end of file; recovering`
warning; recovery and the redundant rebuild completed without compiler or test
failure.

The affected boot-OAT regression then repeated the strengthened gate against
the current fresh path-sensitive cache set:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w030 --stage w031 --stage w032 --stage w036 --stage w037 \
  --parallel 16

W-030  2/2 PASS
W-031  1/1 PASS
W-032  3/3 PASS
W-036  1/1 PASS
W-037  1/1 PASS
8/8 PASS
```

The final W-037 case passed in 1.28 seconds. Its result manifest records exit
0, all required markers, no forbidden marker, all seven intentional launcher
identity mismatches rejected, and `main end exception=0`.

The Linux-hosted Windows cross-build compiled the probe and complete product
graph and accepted 2,091 compile commands, 2,130 Ninja commands, and 31 product
links.

Fresh `agent01` regression evidence passed:

```text
Python bp2cmake/tool suite                         227/227 PASS
linux-x86_64-gnu configure and target audit       PASS
  2,090 compile commands; 2,174 Ninja commands; 33 product links
full linux-x86_64-gnu build and boot generation   PASS
Linux catalog                                     15/15 PASS
```

## Accepted cache sets

The initial focused coverage run used:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `8fb4c367b0d4b63c910cfd2dbc3a3a91e4b00ca56aca08854677ba863de2a65f` |
| `boot.oat` | 20,169,456 | `bc74d546a568e01f56f8305b2dd0ad73890888a31ca57cacaee15eefd378bf25` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

The final strengthened focused and affected regressions used:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `08002abc5f9e1b26c6e61410e4891e15a0c3852c47ddce758d58ad62c776d8d2` |
| `boot.oat` | 20,169,088 | `e375228d42a364fa51289e69074aef1e89c02a45e3f89e4d7019170db23cc377` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

The initial and final relocation deltas also differed (`-268763136` and
`-253952000`). The initial run covered the relocation/fault/root case; the
final strengthened runs additionally required eight completed collections and
the exact selected entrypoint to remain unchanged. These hashes bind two
passing generations; ART and OAT files remain path-sensitive cache artifacts,
and cross-generation byte identity is not an acceptance condition.

## Disposition

- Keep W-037 as the focused paired-relocation, managed-null-fault, and BSS-root
  regression.
- Keep step 10 `PARTIAL` for broader exception and fatal stack-walk execution
  plus concrete relocation/fault/root variants outside this case.
- Keep step 6 `PARTIAL` for unwind corruption/fallback injection, broader
  exception/fatal walking, and actual XMM-bearing boot-AOT frame execution.
- Product boot-AOT selection, successful whole-transaction imageless fallback,
  ART-level negative identity diagnostics, W-033 allocation measurements, and
  the OAT-1/OAT-2 decision remain separate open work.
