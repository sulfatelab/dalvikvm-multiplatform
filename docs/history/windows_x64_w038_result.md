# Windows x64 W-038 native result

**Date:** 2026-08-07

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS - managed boot-OAT exception walking and fatal boot-OAT
unwind/minidump execution are proven; numbered steps 6 and 10 remain partial
only for their other stated breadth**

## Scope and conclusion

W-038 closes the previously listed managed-exception/fatal-stack-walk gap with
two JIT-disabled native processes:

- an ordinary call to a currently published, registered boot-OAT method throws
  an explicit managed exception; the exception is caught, its nonempty Java
  stack contains the selected boot-OAT method, and the method retains the exact
  entrypoint;
- a currently published, registered boot-OAT sorting method calls a native
  comparator that raises a fatal access violation; ART's bounded live
  `RtlVirtualUnwind` trace reaches the exact armed OAT `RUNTIME_FUNCTION`, makes
  forward stack progress through it, reaches the unhandled-exception filter,
  and writes exactly one valid `MDMP` minidump.

The accepted managed target was `Integer.parseInt(String)`. The fatal target
was `Arrays.sort(Object[], Comparator)`, whose exact registered boot-OAT frame
appeared at trace frame 6. The authoritative markers were:

```text
W038_MANAGED_EXCEPTION_PASS target=int java.lang.Integer.parseInt(java.lang.String) type=explicit caught=1 trace=nonempty trace_target=1 entry_unchanged=1 jit=disabled
W038BootOatManagedExceptionProbe PASS exception=caught trace=target entry=oat jit=disabled
W038_FATAL_ARM target=void java.util.Arrays.sort(java.lang.Object[], java.util.Comparator) oat_base=0x60b20718 begin=0xc896c8 end=0xc89764 jit=disabled
W038_FATAL_CRASH_ENTER native_callback=1
ART_WINDOWS_X64_UNWIND_TRACE frame=6 pc=0x617a9e6a rsp=0x73ba72f560 lookup=1 image=0x60b20718 begin=0x00c896c8 end=0x00c89764 unwind=0x0123cb34
ART_WINDOWS_X64_UNWIND_TRACE step=6 kind=virtual next_pc=0x7ffdae47c0fb next_rsp=0x73ba72f5b0 establisher=0x73ba72f5a8
ART_WINDOWS_X64_UNWIND_TRACE end frames=20 reason=zero_pc final_pc=0x0 final_rsp=0x73ba72fd60
ART Win32 UEF: exception 0xc0000005 at 0x7ffdbbb73010 access=1 fault_addr=0x1234
ART Win32 crash: minidump written
```

The fatal child exited with the expected access-violation status
`0xC0000005`; all required markers were present and no forbidden marker was
present. The outer gate accepted two completed cases.

## Root cause and repair

The repeated adapter PC initially seen in the live trace was legitimate: two
nterp frames used the same adapter record while their RSP values increased.
The real defect was incomplete PE metadata on the adapter. Its synthetic stack
allocation skipped the dynamic nterp frame, but it did not restore the
nterp-saved nonvolatile registers. The following boot-OAT record therefore saw
the wrong caller RBP and could not reconstruct its own frame.

Every Windows x64 nterp compiled-invoke adapter now describes the saved RBX,
RBP, and R12-R15 slots in addition to its runtime-sized synthetic allocation.
For example, the first adapter carries:

```asm
.seh_stackalloc 88
.seh_savereg %rbx, 40
.seh_savereg %rbp, 48
.seh_savereg %r12, 56
.seh_savereg %r13, 64
.seh_savereg %r14, 72
.seh_savereg %r15, 80
```

For a gap of 72 bytes, the corresponding record is:

```asm
.seh_stackalloc 152
.seh_savereg %rbx, 104
.seh_savereg %rbp, 112
.seh_savereg %r12, 120
.seh_savereg %r13, 128
.seh_savereg %r14, 136
.seh_savereg %r15, 144
```

The normal-return continuation remains in its original reserved slot. No
second return slot or alternative managed-execution path was added.

Public `NterpWindowsInvokeAdapterStart` and
`NterpWindowsInvokeAdapterEnd` range markers allow the Windows boundary
reviewer to audit all 187 adapters. The reviewer requires the exact record
count, zero-prologue metadata, the allocation sequence, all six register-save
offsets, and contiguous unwind ranges. The rebuilt native W-010 structural
stage passes 8/8 with this audit.

## Source identity

The native overlay used:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
bundle  C:\mdvm-unified-20260730\bundle
```

The deployed root baseline was
`f55d97a81f7c353d2a222c83ebaa3496eed3405d`. The accepted adapter repair is
nested ART commit `c2ac04128f186388f43162e71fc268452cf1d959`, based on
`03d55ca0174dbf39b54444ce5fdf4a55e5dce331`. The containing root commit owns
the managed/native probe, catalog entry, structural reviewer extension,
accepted record, and submodule update.

The final native-tested W-038 inputs had these SHA-256 values:

```text
tests/CMakeLists.txt
0bc6248d6f00506f5f25cd1f33ecb6bf73c7ead88b7c3d13b8f322f0210bb613

tests/cases/aot-exception-fatal-unwind/W038BootOatFatalUnwindProbe.java
0cb56dcb4b333cd6d8fcdd13253845dd5561fe6bd103bb319358a2b5c1e15afd

tests/cases/aot-exception-fatal-unwind/W038BootOatManagedExceptionProbe.java
74db29ce7c58f6c986d52b4290666146b0ff148722a23147c7f2ca1c07c4cf01

tests/cases/aot-exception-fatal-unwind/probe.cc
473ffea9626ca39a25b1c4f13a468ce2d50a151e60cfa25b2a23e7433223b4ec

tests/cases/aot-exception-fatal-unwind/run.py
3bf02acbf6294df7b202f945772c49c523f3894ee5e275d31d258fad22633ee7

vendor/art/runtime/interpreter/mterp/x86_64ng/main.S
b3900c776fabe5b40311cab1a8e1eab10aaae605280c6542f6bf3df33c8932b2

vendor/art/runtime/nterp_helpers.cc
2e5913e3638db3ef1c832e47e8658635185d4efcad4b35b6f1e9736597176189
```

## Native commands and results

The focused gate and affected-stage regression used the repository frontend:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w038 \
  --parallel 16

python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w030 --stage w031 --stage w032 \
  --stage w036 --stage w037 --stage w038 \
  --parallel 16

python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w010 --stage w038 \
  --parallel 16
```

The final W-038 case passed `1/1` in 2.47 seconds. The affected regression
passed all nine CTest cases:

```text
W-030  2/2 PASS
W-031  1/1 PASS
W-032  3/3 PASS
W-036  1/1 PASS
W-037  1/1 PASS
W-038  1/1 PASS (two child processes)
9/9 PASS
```

After the final comment-only source wording cleanup, the combined W-010/W-038
run passed 9/9 in 21.76 seconds. W-010 passed 8/8, including the 187-record
boundary audit in 5.83 seconds; W-038 passed 1/1 in 2.47 seconds. This final run
used the source and cache hashes below.

The final W-036 and W-037 manifests also recorded exit 0, no missing or
forbidden markers, and all seven intentional launcher mismatches rejected.
W-037 again observed a nonzero aligned paired relocation, one recovered
boot-OAT null fault, and the same BSS root through eight completed collections.

Fresh `agent01` regression evidence passed:

```text
Focused reviewer/catalog Python tests               10/10 PASS
Python host and bp2cmake suite                     320/320 PASS
linux-x86_64-gnu configure and target audit        PASS
  2,090 compile commands; 2,174 Ninja commands; 33 product links
full linux-x86_64-gnu build and boot generation    PASS
Linux catalog                                       15/15 PASS
x86-64 mterp source generation                     PASS
```

The broad Python run also corrected a stale repository-inventory baseline and
added the required adjacent `RESULT.md` records for W-031, W-032, W-036,
W-037, and W-038. All 36 native-source case directories and all 54 managed Java
sources now satisfy the catalog ownership check.

## Accepted cache set and minidump

Both W-038 children used the same path-sensitive cache set:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `3bbae80f2ade644d28ab05c199f6584af0546bf6631efc24ef347997674ccd6c` |
| `boot.oat` | 20,169,288 | `0f9763bf3a2bd388906d5aed0faef6da914f586518600839ee2f57c827eef2fc` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

Exactly one dump was present. It began with `MDMP`, was 1,207,378 bytes, and
had SHA-256
`cb3fced5b6a2f5ee428e0baded0cd7a6ae0e26b06f7fa01531841eb19c1d1838`.

## Disposition

- Keep W-038 as the native managed-exception and fatal boot-OAT stack-walk
  regression.
- Keep step 6 `PARTIAL` only for `.oat_unwind.windows`
  corruption/fallback injection and actual XMM-bearing boot-AOT frame
  execution.
- Keep step 10 `PARTIAL` for concrete relocation/fault/root variants and other
  explicitly untested execution breadth; do not continue to list the W-038
  exception/fatal-walk contract as missing.
- Product boot-AOT selection, successful whole-transaction imageless fallback,
  ART-level negative identity diagnostics, baseline measurements, W-033, and
  the OAT-1/OAT-2 decision remain separate open work.
