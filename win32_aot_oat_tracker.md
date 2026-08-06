# Windows AOT/OAT implementation tracker

Status: active, boot-only early bring-up (updated 2026-08-06).

This file tracks implementation and evidence for the design in
[`win32_aot_oat.md`](win32_aot_oat.md). It does not replace that document's
format, mapping, unwind, CFG, rollback, or acceptance contracts. The current
Windows product remains imageless nterp/JIT unless an explicitly experimental
boot-AOT path is selected and every required gate for that path passes.

## Status and evidence rules

| State | Meaning |
|---|---|
| `NOT STARTED` | No implementation intended to satisfy the step has landed. |
| `ACTIVE` | Work is in progress and no useful step-level result is ready yet. |
| `PARTIAL` | A useful implementation or gate exists, but one or more stated exit conditions remain. |
| `BLOCKED` | Progress requires an unavailable dependency, authority, or external-state change. |
| `COMPLETE` | The implementation and all step-specific authoritative gates pass. |

Windows Server 2025 Datacenter Evaluation, x64 build 26100 is authoritative.
A Linux-hosted Windows cross-build proves target compilation and PE structure;
Wine can provide development evidence; neither can make a Windows operation or
runtime step `COMPLETE`. Linux regression evidence is required wherever shared
ART writer, ELF, OAT, VDEX, or image behavior can change.

Generated files under `out/` are disposable evidence and are never committed.
Accepted native results must record the source and nested-repository commits,
target-bundle identity, OS build, command contract, artifact hashes, and test
result in a sanitized repository record.

The first implementation slice is pinned to nested ART commit
`681f2f38a295602a1d04e21febb63b7e26e19103`
(`android-16.0.0_r4-93-g681f2f38a2`).

## Current position

Numbered implementation-sequence step 1 is `PARTIAL`. The tree now builds a
native Windows x64 `dex2oat.exe`, registers the shell-free W-028 no-image
operation gate, and emits Windows-target OAT/image ELF segments with 64-KiB
alignment while retaining `kMaxPageSize = 16384` and
`ART_PAGE_SIZE_AGNOSTIC=1`. The cross-built compiler and all of its ART runtime
consumers share one `artbase.dll` state owner. A repeated Wine diagnostic now
completes compilation and produces byte-identical, structurally valid OAT 265
and VDEX 027 artifacts. A native build-26100 execution and accepted result
record are still required.

The earlier `runtime/oat/oat_file_test.cc` additions are a pre-dispatch loader
characterization suite. They support sequence step 3 and do not constitute
numbered step 1 or executable Windows OAT loading.

## Implementation sequence

| Step | State | Implemented position | Remaining exit condition |
|---:|---|---|---|
| 1. Native trivial no-image `dex2oat` compile | `PARTIAL` | W-028 builds `dex2oat`, `boot.jar`, and `hello.jar`; runs a deterministic single-JAR `speed` compile with watchdog and forced swap; validates ELF64/ET_DYN/x86-64, Linux ART OSABI/ABI/flags, 64-KiB `PT_LOAD`, OAT 265, and the complete four-section VDEX 027 envelope; a repeated Wine diagnostic produces byte-identical outputs | Run and accept W-028 on native Server 2025 build 26100; preserve the resulting hashes and manifest |
| 2. Stable generation/startup identities | `PARTIAL` | W-028 uses candidate logical identities `/system/framework/boot.jar` and `/data/local/tmp/win32-oat-probe.jar` independently of physical package paths | Select boot-image/component topology and `-Ximage:` identity; prove byte-identical generation/startup strings and intentional mismatch diagnostics |
| 3. Pre-dispatch characterization and trampoline regression | `PARTIAL` | Characterization tests exist in `oat_file_test.cc` and the shared trampoline lowering has been source-reviewed | Close H-005 by running the focused tests; add Linux-`GS`/Windows-`R15` disassembly and resolution/quick-to-interpreter execution gates |
| 4. Windows private-copy `ElfOatFile` mapping | `NOT STARTED` | Design limits the new operation to the file-backed segment copy | Implement and test validation-only allocation and executable exact-reservation opens, gaps, zero-fill, final protections, and cache flush |
| 5. VDEX aperture and ownership | `NOT STARTED` | Owner-sharing slice and transaction ordering are specified | Implement exact private copy into `oatdex`, validation, protection, owner lifetime, and rollback |
| 6. `.oat_unwind.windows` | `NOT STARTED` | Writer format, machine value, checksum, anchors, validation, and registration lifetime are specified | Implement emission through `WindowsAotUnwindRegistry`; pass structural, lookup, virtual-unwind, exception, and stack-walk gates |
| 7. `.oat_cfg.windows` | `NOT STARTED` | Independent format and observation/explicit mode split are specified | Implement collection/serialization/parser; pass observation mode; keep explicit mode gated on the separate committed-allocation feasibility proof |
| 8. Boot ART/OAT/VDEX generation and staging | `NOT STARTED` | Windows 64-KiB artifact alignment is implemented | Select component topology; exercise `ImageWriter`; reproducibly build, validate, and stage the matching boot set |
| 9. Experimental selection and fallback | `NOT STARTED` | Whole-transaction publication/rollback ordering is specified | Add opt-in startup, compatibility rejection before trusted-layout invariants, and native imageless fallback cases |
| 10. Real boot-OAT execution | `NOT STARTED` | Required entrypoint, relocation, JNI, fault, GC, and unwind evidence is specified | Prove representative methods execute from boot-OAT RX ranges without JIT on Server 2025 |
| 11. CFG observation and OAT-1 measurements | `NOT STARTED` | Required policy, call-path, reservation, commit, padding, startup, and working-set observations are specified | Pass the native observation gate and record the measurements; explicit CFG, OAT-2, application OAT, unloading, and security remain deferred |

## Step 1 implementation record

### Target artifact alignment

`libartbase/base/globals.h` now separates Windows artifact alignment from the
runtime page-size bound:

- Linux keeps `kMaxPageSize = 16384` and therefore retains 16-KiB ELF/image
  segment alignment.
- Windows keeps the same 16-KiB `kMaxPageSize` bound, keeps
  `ART_PAGE_SIZE_AGNOSTIC=1`, and selects
  `kElfSegmentAlignment = 64 * KB` for its 64-KiB allocation granularity.
- The Windows host's ordinary virtual-memory page remains 4 KiB. The change
  does not pretend that its page size is 64 KiB and does not alter Linux ART
  output.

The W-028 parser rejects a Windows artifact unless every `PT_LOAD` has 64-KiB
alignment and ELF congruence, no load segment is W+X, the shared Linux ART ELF
identity is unchanged, and the expected OAT/VDEX versions are present.

### One process-wide `libartbase` owner

The first real compiler probe exposed a pre-writer topology defect. Windows
had statically embedded stateful `libartbase` copies in `dex2oat.exe`,
`art-dex2oat.dll`, and `art.dll`. The executable initialized its own `MemMap`
registry, then boot-JAR option parsing crossed into `art.dll` and failed
`MemMap::IsInitialized()` against a different registry. `MemMap` values also
cross these PE boundaries, so duplicating only selected initialization calls
would not establish correct ownership.

Windows now uses the same shared `libartbase` topology as Linux. The
`ART_BASE_DATA` annotation gives `artbase.dll` explicit ownership of mutable
state that CMake's automatic PE function export does not cover:

- `gAborting`, `gFlags`, and `gLogVerbosity`;
- tracked-allocator byte counters; and
- `MemMap::mem_maps_lock_` and the page-size-agnostic
  `MemMap::page_size_`.

The generated topology contract consequently has four, rather than five,
approved Linux/Windows module-kind differences. PE inspection must continue to
prove that `dex2oat.exe`, `art-dex2oat.dll`, and `art.dll` import
`artbase.dll`, including the required mutable data where referenced.

### Compiler and VDEX writer prerequisites

The operation gate exposed four additional Windows portability requirements;
all are narrow Windows behavior and leave the Linux writer flow unchanged:

- the port's `PTHREAD_MUTEX_INITIALIZER` is only a zero-valued compile
  sentinel, not an initialized `CRITICAL_SECTION`, so the `WatchDog` runtime
  mutex is initialized once before either access;
- `MemMap::Sync()` flushes file-backed views with `FlushViewOfFile()` and
  treats `VirtualAlloc` anonymous maps as having no backing file to flush;
- a new VDEX uses an anonymous compiler working copy because its `DexFile`
  pointers must remain stable while Windows forbids resizing a live file
  mapping. `FinishVdexFile()` maps a page-rounded output temporarily, copies
  the working state, appends verifier/type-lookup data, preserves invalid-body
  then valid-header flush ordering, releases the view, and truncates to the
  exact logical size; and
- `FdFile` adds `O_BINARY` on Windows, preventing MSVCRT newline translation
  from inserting bytes into ELF/OAT/VDEX output. The `ftruncate` shim now also
  follows the POSIX `0`/`-1` plus `errno` return contract.

This private working copy is a compiler-output prerequisite only. It is not
the sequence-step-4 private-copy `ElfOatFile` loader and does not make an OAT
executable.

### W-028 operation gate

`tools/run_dex2oat_no_image.py` deliberately requests an absent boot image so
the non-image application compile takes ART's diagnosed imageless fallback.
It uses a single target-neutral boot JAR and trivial input JAR, stable logical
DEX locations, the `speed` filter, two compiler workers, enabled watchdog,
forced swap-file thresholds, deterministic output, and a target-local runtime
root. The gate is shell-free and deletes only its exact link-free managed
result directory before a run.

On success it writes `stdout.txt`, `stderr.txt`, `probe.oat`, `probe.vdex`, and
`result.json`. The manifest records elapsed time, artifact sizes/hashes, ELF
identity and alignment, load-segment count, OAT/VDEX versions, VDEX section
count, and input-DEX count. Validation requires an exact VDEX size derived
from its four section ranges and the embedded DEX marker. An absent, empty,
malformed, padded, wrong-version, wrong-alignment, or unexpected `.art` output
fails the gate.

The gate is native-only in the catalog. A cross configuration still builds all
dependencies and exposes the declaration without registering a misleading
CTest execution.

## Evidence log

| Date | Environment | Result | Interpretation |
|---|---|---|---|
| 2026-08-06 | agent01 Linux-hosted `windows-x86_64-msvc` cross-build | `dex2oat` and W-028 dependencies build; target-binding audit accepts 2,081 compile commands, 2,126 Ninja commands, and 30 product links | Target compile/link and graph evidence only |
| 2026-08-06 | PE inspection of the cross-build | `dex2oat.exe`, `art-dex2oat.dll`, and `art.dll` import `artbase.dll`; the DLL exports the required logging, flags, allocator, and `MemMap` data | Confirms removal of duplicate process state at the PE boundary |
| 2026-08-06 | Wine 10 development run | The shared-base fix clears `MemMap::IsInitialized()`; one-time watchdog-mutex initialization clears the next hang; `MemMap::Sync()` and the anonymous VDEX working-copy/final-publish path clear the live-mapping resize failure; binary `FdFile` mode clears CRT newline corruption | Useful causal diagnostic evidence, never native acceptance |
| 2026-08-06 | Repeated Wine 10 compiler diagnostic | Two identical invocations complete in about 0.54 s each and produce byte-identical 66,888-byte OAT and 1,000-byte VDEX files; validation reports ELF64/ET_DYN/x86-64, Linux OSABI 3/ABI 0/flags 0, four non-W+X 64-KiB `PT_LOAD` segments, OAT 265, and a four-section/one-DEX VDEX 027 | Step-1 development evidence; native W-028 remains mandatory |
| 2026-08-06 | Fresh Linux current-source compile plus coherent Linux baseline generation | The affected `mem_map.cc`, `fd_file.cc`, and `oat_writer.cc` paths compile for `linux-x86_64-gnu`; the Linux no-image baseline remains four non-W+X 16-KiB `PT_LOAD` segments with the same ELF identity, OAT 265, and VDEX 027 | Confirms the new branches are Windows-scoped and retains the Linux layout baseline |
| Pending | Windows Server 2025 build 26100 | Run W-028 from a fresh coherent native build | Required to complete step 1 |

The repeated Wine artifacts have SHA-256
`2ca0204f5b3da51e748eeb143430d604e55c1bfb9134b1c91b9f77bc82e64c11`
for OAT and
`cc1b8db5d41a00c51a380c27020e69e97cf987e0e0ee9b44a0b7995c703073c1`
for VDEX. The coherent Linux baseline has OAT SHA-256
`255c99f89dc3c131bdb2f19d1c5c209a4e37ddeda0be435830f0c36f9e331a4e`
and the same VDEX hash. These are diagnostic baselines, not accepted native
Windows results.

## Immediate work queue

1. Run W-028 on the authoritative native host and archive a sanitized accepted
   result with artifact hashes.
2. Promote the cross-target 16-/64-KiB artifact comparison into a repeatable
   automated regression rather than relying on the recorded development run.
3. Select and gate the boot component/location identity contract.
4. Close H-005 and add the two-target trampoline regression.
5. Begin the narrow Windows private-copy file-segment operation for both
   validation-only and executable `ElfOatFile` opens.

Do not begin application OAT, OAT-2, successful-load unloading, explicit CFG
enforcement, or security hardening merely to close an early boot-only step.
