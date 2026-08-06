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
W-030's private-copy loader is nested ART commit
`fd6accf065a550fc1e436cb9f28617b466f7593e`; its root generator, launcher,
probe, and tests are commit `a0400259954d95161f45c74d3a8a4317a3427a62`.

## Current position

Numbered implementation-sequence step 1 is `COMPLETE`. The tree builds a
native Windows x64 `dex2oat.exe`, registers the shell-free W-028 no-image
operation gate, and emits Windows-target OAT/image ELF segments with 64-KiB
alignment while retaining `kMaxPageSize = 16384` and
`ART_PAGE_SIZE_AGNOSTIC=1`. The cross-built compiler and all of its ART runtime
consumers share one `artbase.dll` state owner. Two authoritative native
build-26100 executions pass and produce byte-identical, structurally valid OAT
265 and VDEX 027 artifacts; a post-correction Wine diagnostic produces the
same bytes. The sanitized result is
[`docs/history/windows_x64_w028_result.md`](docs/history/windows_x64_w028_result.md).

Numbered step 2 is `PARTIAL`. W-029 now pins and validates a single-component,
package-relative generation/startup identity contract. It passes on the
authoritative native host and deliberately rejects seven case, separator,
physical-path, and topology mismatches. W-030 makes generation, the staged
manifest, and the experimental package-root launcher consume the contract, and
native ART accepts the canonical set. The step remains partial only because
the seven negative cases are launcher-level pre-spawn checks rather than
ART-level mismatch diagnostics. The accepted preflight is
[`docs/history/windows_x64_w029_result.md`](docs/history/windows_x64_w029_result.md),
and the native loading evidence is
[`docs/history/windows_x64_w030_result.md`](docs/history/windows_x64_w030_result.md).

Steps 4 and 5 are `COMPLETE` for boot-only OAT-1. The Windows-only
private-copy helper is wired into both validation-only and executable ELF
segment loading and into reused VDEX placement. The native W-030 primitive
probe and canonical boot startup cover exact private ownership, range checks,
R/RX/RW protections, no-access gaps, zero fill, source privacy, executable
cache flushing, validation-only opens, executable opens, and `oatdex` reuse.
Linux retains its original fixed file-mapping path.

Steps 8 and 9 are `PARTIAL`. Windows now generates and stages an LZ4
`boot.art`, ordinary ELF `boot.oat`, and VDEX, then launches with exact
`-Ximage:runtime/boot-image/boot.art` and rejects silent imageless fallback.
Linux remains uncompressed. Repeated forced generation is not byte-
reproducible: `boot.vdex` stays stable, but `boot.art` and OAT `.text` change,
including in three `-j1` trials. The gate is experimental rather than normal
product selection and does not exercise successful fallback. It also uses
`-Xint`, so it proves loading rather than real boot-OAT execution.

The earlier `runtime/oat/oat_file_test.cc` additions are a pre-dispatch loader
characterization suite. They support sequence step 3 and do not constitute
numbered step 1 or executable Windows OAT loading.

## Implementation sequence

| Step | State | Implemented position | Remaining exit condition |
|---:|---|---|---|
| 1. Native trivial no-image `dex2oat` compile | `COMPLETE` | W-028 builds `dex2oat`, `boot.jar`, and `hello.jar`; runs a deterministic single-JAR `speed` compile with watchdog and forced swap; validates ELF64/ET_DYN/x86-64, Linux ART OSABI/ABI/flags, 64-KiB `PT_LOAD`, OAT 265, and the complete four-section VDEX 027 envelope; two native runs and a post-correction Wine diagnostic produce byte-identical outputs | Retain W-028 as a regression gate; no step-1 exit condition remains |
| 2. Stable generation/startup identities | `PARTIAL` | W-029 pins one `boot` component, logical `/system/framework/boot.jar`, package `runtime/boot.jar`, explicit package-relative `-Ximage:runtime/boot-image/boot.art`, and the x86-64 ART/OAT/VDEX package paths; W-030 makes generation, manifest, staging, and startup consume the record, and native ART accepts the canonical set | Add ART-level negative diagnostics; the existing seven-case matrix is launcher-level and rejects before spawn |
| 3. Pre-dispatch characterization and trampoline regression | `PARTIAL` | Characterization tests exist in `oat_file_test.cc` and the shared trampoline lowering has been source-reviewed | Close H-005 by running the focused tests; add Linux-`GS`/Windows-`R15` disassembly and resolution/quick-to-interpreter execution gates |
| 4. Windows private-copy `ElfOatFile` mapping | `COMPLETE` | Windows `ElfFileImpl::Load()` privately copies every file-backed `PT_LOAD` into the existing ART-owned private allocation; W-030 covers validation-only and executable opens, rejected foreign/section/unaligned/range inputs, exact address, R/RX/RW, no-access gaps, zero fill, owner sharing, source privacy, and cache flush | Retain W-030; no boot-only step-4 exit condition remains |
| 5. VDEX aperture and ownership | `COMPLETE` | Windows reused VDEX mappings use the same checked private-copy primitive for the exact `oatdex` bytes, return an owner-sharing slice, and pass canonical boot startup through `ComputeFields -> LoadVdex -> Setup` | Retain the native end-to-end gate; add broader rollback injection with product-level fallback work |
| 6. `.oat_unwind.windows` | `NOT STARTED` | Writer format, machine value, checksum, anchors, validation, and registration lifetime are specified | Implement emission through `WindowsAotUnwindRegistry`; pass structural, lookup, virtual-unwind, exception, and stack-walk gates |
| 7. `.oat_cfg.windows` | `NOT STARTED` | Independent format and observation/explicit mode split are specified | Implement collection/serialization/parser; pass observation mode; keep explicit mode gated on the separate committed-allocation feasibility proof |
| 8. Boot ART/OAT/VDEX generation and staging | `PARTIAL` | W-030 exercises native `ImageWriter`, emits Windows LZ4 `boot.art` plus matching OAT/VDEX, validates hashes/identity, and stages the exact single-component topology; canonical startup passes | Diagnose and fix repeated-artifact nondeterminism; `boot.vdex` is stable but `boot.art` and OAT `.text` differ even at `-j1` |
| 9. Experimental selection and fallback | `PARTIAL` | W-030 explicitly selects the staged set, runs from package root, rejects seven launcher mismatches, and fails if ART silently enters imageless startup | Integrate a reviewed product option and exercise successful missing/stale/wrong-target/cross-artifact whole-transaction fallback |
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

The runner changes into that managed result directory and passes the relative
`--oat-file=probe.oat`. ART's ELF writer uses that logical name for
`DT_SONAME`, so the OAT identity does not depend on a native or Wine physical
output path.

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

## Step 2 implementation record

### Selected single-component identity

`tools/windows_aot_identity.py` is the canonical preflight source for the
initial x86-64 boot-only package:

- one `boot` component;
- generation `--dex-location=/system/framework/boot.jar` and startup
  `-Xbootclasspath-locations:/system/framework/boot.jar`;
- physical package JAR `runtime/boot.jar`;
- explicit startup `-Ximage:runtime/boot-image/boot.art`, resolved from the
  package root; and
- physical `runtime/boot-image/x86_64/boot.art`, `.oat`, and `.vdex` files.

The forward-slash image value is deliberately relative and contains no drive,
build, or staging root. ART's existing image lookup inserts `x86_64` between
the image directory and basename. An existing Linux x86-64 boot set was loaded
successfully with this relative form as a path-resolution diagnostic; the
Linux launcher itself remains unchanged.

W-028 imports its boot, probe-dex, and relative OAT identities from the same
module and serializes the selected contract in `result.json`. Its native OAT
and VDEX hashes remain unchanged.

### W-029 preflight and remaining boundary

W-029 is a `host-review` gate because it compares product strings and package
topology without executing target ART. It requires an exact canonical pair and
rejects boot-class-path and image-location case changes, backslash spellings,
physical `C:/...` substitutions, and an added boot component. Diagnostics name
the mismatched field and preserve both values without normalization.

The gate passes under both the Linux-hosted Windows cross configuration and
native Server 2025. This closes the design choice, not sequence step 2. The
real Windows `ImageWriter` command, staged manifest, and experimental launcher
now consume it through W-030, and ART accepts the canonical startup. ART-level
negative mismatch diagnostics remain before the step becomes `COMPLETE`.

## W-030 implementation record

### Narrow Windows private copy

`MemMap::MapFileAtAddressPrivateCopy()` is a Windows-only operation, not a
general `MAP_FIXED` emulator. Before changing protection or bytes it requires a
non-empty page-aligned checked destination inside one ART-owned `MEM_PRIVATE`
allocation, a valid non-negative file range, and no arithmetic overflow. It
rejects section views and foreign allocations. It temporarily exposes only
RW/NX, copies the exact file bytes, restores the caller's R, RX, or RW/NX
protection, and flushes the instruction cache for executable ranges. The
returned `MemMap` slice shares the original allocation owner.

Windows `ElfFileImpl::Load()` uses this operation for every non-empty
file-backed `PT_LOAD`; validation-only and executable `ElfOatFile` opens
therefore have one mapping contract. Anonymous segment tails and gaps continue
through the existing Windows reuse path. `VdexFile::OpenAtAddress()` uses the
same operation only when Windows reuses the OAT `oatdex` aperture. The Linux
branches are byte-for-byte the prior `MapFileAtAddress(..., reuse=true)` flow.

The native `windows_w030_private_copy_probe` independently checks foreign,
unaligned, section-view, and out-of-file rejection; exact address and bytes;
R/NX, RX, and RW/NX final pages; adjacent `PAGE_NOACCESS` gaps; anonymous zero
fill; shared owner lifetime; private mutation; and executable cache flush. It
then relies on the boot gate to prove both ELF open modes and VDEX reuse end to
end. This completes sequence steps 4 and 5 for boot-only OAT-1.

### LZ4 boot image, staging, and startup

The existing Windows image reservation is one whole-span committed private
allocation. An initial uncompressed W-030 run could not replace its 4-KiB-
aligned image subrange with a file view, logged `mmap(... boot.art ...) failed:
Invalid argument`, and entered imageless fallback. Managed `Hello` still
completed, demonstrating why exit status alone is insufficient. Windows boot
generation now selects ART's existing LZ4 image format, which decompresses
into anonymous memory and avoids that file-view operation. Linux generation
remains uncompressed.

The generator records compiler parallelism, image format, the exact W-029
identity, generation options, boot-JAR hash, and all artifact hashes. The
launcher revalidates those records, stages canonical package topology, runs
from the package root, and passes exact
`-Ximage:runtime/boot-image/boot.art`. It rejects the seven shared identity
mismatches before spawning ART, requires managed start/end markers, and treats
imageless/failure markers as a gate failure even with exit 0. The accepted
native run emits:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 3,006,016 | `5bdf0b80011dac18ca4bbeaca3cb1ab9bec2a353dfc9bce889aeb2042e81c9f6` |
| `boot.oat` | 18,834,112 | `94344c9539576fbaa57aaaae38900adcd5041d63c0aeb308e81c48e210cbafe9` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

This makes steps 8 and 9 useful but partial. Forced repeats at normal
parallelism and three serial `-j1` attempts all start successfully, yet
`boot.art` hashes and OAT `.text` sizes/hashes change while `boot.vdex` remains
stable. Serial generation is therefore not a fix and the configured Windows
parallelism remains 16. W-030 is also an explicit experimental gate rather
than normal product selection, and it detects but does not exercise successful
imageless fallback. Its `-Xint` launcher proves loading, not execution from
boot-OAT RX code.

## Evidence log

| Date | Environment | Result | Interpretation |
|---|---|---|---|
| 2026-08-06 | agent01 Linux-hosted `windows-x86_64-msvc` cross-build | `dex2oat` and W-028 dependencies build; target-binding audit accepts 2,081 compile commands, 2,126 Ninja commands, and 30 product links | Target compile/link and graph evidence only |
| 2026-08-06 | PE inspection of the cross-build | `dex2oat.exe`, `art-dex2oat.dll`, and `art.dll` import `artbase.dll`; the DLL exports the required logging, flags, allocator, and `MemMap` data | Confirms removal of duplicate process state at the PE boundary |
| 2026-08-06 | Wine 10 development run | The shared-base fix clears `MemMap::IsInitialized()`; one-time watchdog-mutex initialization clears the next hang; `MemMap::Sync()` and the anonymous VDEX working-copy/final-publish path clear the live-mapping resize failure; binary `FdFile` mode clears CRT newline corruption | Useful causal diagnostic evidence, never native acceptance |
| 2026-08-06 | Repeated Wine 10 compiler diagnostic before the stable-OAT-name correction | Two identical invocations complete in about 0.54 s each and produce byte-identical 66,888-byte OAT and 1,000-byte VDEX files; validation reports ELF64/ET_DYN/x86-64, Linux OSABI 3/ABI 0/flags 0, four non-W+X 64-KiB `PT_LOAD` segments, OAT 265, and a four-section/one-DEX VDEX 027 | Proved the operation but exposed a physical output path in ELF `DT_SONAME`; diagnostic only |
| 2026-08-06 | Fresh Linux current-source compile plus coherent Linux baseline generation | The affected `mem_map.cc`, `fd_file.cc`, and `oat_writer.cc` paths compile for `linux-x86_64-gnu`; the Linux no-image baseline remains four non-W+X 16-KiB `PT_LOAD` segments with the same ELF identity, OAT 265, and VDEX 027 | Confirms the new branches are Windows-scoped and retains the Linux layout baseline |
| 2026-08-06 | Windows Server 2025 build 26100 | A fresh coherent native build and target-binding audit pass; W-028 passes twice in 0.64/0.61 s and emits the same 66,888-byte OAT and 1,000-byte VDEX on both runs | **Authoritative step-1 acceptance**; see [`docs/history/windows_x64_w028_result.md`](docs/history/windows_x64_w028_result.md) |
| 2026-08-06 | Post-correction Wine diagnostic | Relative `probe.oat` removes the physical path from `DT_SONAME`; the OAT and VDEX hashes exactly match both authoritative native runs | Cross-environment reproducibility diagnostic; not the acceptance authority |
| 2026-08-06 | Fresh Linux-hosted Windows cross configuration | W-029 passes 1/1 in 0.06 s; the target-binding audit remains 2,081 compile commands, 2,126 Ninja commands, and 30 product links | Cross-host preflight evidence for step 2 |
| 2026-08-06 | Windows Server 2025 build 26100 | W-029 passes 1/1 in 0.13 s after a no-op build and rejects all seven intentional mismatches; W-028 then passes 1/1 in 0.68 s with unchanged artifact hashes | **Authoritative identity-preflight acceptance**; step 2 remains partial; see [`docs/history/windows_x64_w029_result.md`](docs/history/windows_x64_w029_result.md) |
| 2026-08-06 | Windows Server 2025 build 26100 | W-030 private-copy probe passes in 0.08 s and reports 4-KiB pages, 64-KiB allocation granularity, checked range/ownership, R/RX/RW, no-access gaps, zero fill, private source, shared owner, and cache flush | **Authoritative steps 4/5 primitive acceptance** |
| 2026-08-06 | Windows Server 2025 build 26100 | W-030 generates the LZ4 boot set and canonical startup passes in 1.13 s; both W-030 gates pass 2/2, ART exits 0 with all required markers, no forbidden fallback marker, and seven launcher mismatches rejected | **Authoritative boot-only loading acceptance**; steps 8/9 partial and step 10 open; see [`docs/history/windows_x64_w030_result.md`](docs/history/windows_x64_w030_result.md) |
| 2026-08-06 | Windows Server 2025 build 26100 forced-repeat characterization | Normal parallel and three `-j1` generations all start successfully; VDEX remains stable while `boot.art` and OAT `.text` size/hash change | Windows boot-compiler determinism defect; step 8 remains partial and serial generation is rejected as a workaround |

The two accepted native runs and the post-correction Wine diagnostic have
SHA-256
`fa03ad2f48f7a83bc8c6ddbf42620454f336d8c870e339771fc3edc88eb615f7`
for OAT and
`cc1b8db5d41a00c51a380c27020e69e97cf987e0e0ee9b44a0b7995c703073c1`
for VDEX. The coherent Linux baseline has OAT SHA-256
`255c99f89dc3c131bdb2f19d1c5c209a4e37ddeda0be435830f0c36f9e331a4e`
and the same VDEX hash. The Linux and Wine roles remain regression and
diagnostic evidence; native Server 2025 is the acceptance authority.

## Immediate work queue

1. Implement `.oat_unwind.windows` emission, validation, registration, and
   native managed/JNI/trampoline unwind gates without changing Linux OAT.
2. Implement `.oat_cfg.windows` serialization/parser and the native CFG
   observation gate; keep explicit-target mode behind its separate allocation
   feasibility proof.
3. Diagnose Windows boot-generation nondeterminism, retaining the recorded
   compiler parallelism and stable VDEX evidence; do not adopt `-j1` as a
   workaround.
4. Prove representative methods actually execute from boot-OAT RX ranges with
   JIT disabled, then exercise relocation, JNI, faults, GC/roots, and unwind.
5. Integrate reviewed product selection plus successful whole-transaction
   imageless fallback and ART-level negative identity diagnostics.
6. Promote the cross-target 16-/64-KiB artifact comparison into an automated
   regression, close H-005, and add the two-target trampoline regression.

Do not begin application OAT, OAT-2, successful-load unloading, explicit CFG
enforcement, or security hardening merely to close an early boot-only step.
