# Windows AOT/OAT implementation tracker

Status: active, boot-only early bring-up (updated 2026-08-07).

This file tracks implementation and evidence for the design in
[`win32_aot_oat.md`](win32_aot_oat.md). It does not replace that document's
format, mapping, unwind, CFG, rollback, or acceptance contracts. The current
Windows product remains imageless nterp/JIT unless an explicitly experimental
boot-AOT path is selected and every required gate for that path passes.

## Status and evidence rules

| State | Meaning |
|---|---|
| `NOT STARTED` | No implementation intended to satisfy the step has landed. |
| `DESIGNED` | A reviewed implementation contract and gate sequence exist, but implementation has not started. |
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
W-031's unwind writer/registry is nested ART commit
`ba16ea923a9156ef5cbaebfabbc1dceba069889f`; its root gate and accepted record
are commit `48c2b785ca6878044f2e5ca1aa556d0c4ae4928f`.
W-032's CFG target writer/parser is nested ART commit
`30db175a1240780c23c674e5bf29d281570becfd`; its containing root commit owns
the forced-policy runner, guarded probe, structural gate, accepted record, and
submodule update.
W-036's Windows startup correction is nested ART commit
`03d55ca0174dbf39b54444ce5fdf4a55e5dce331`; its containing root commit owns
the hardware-breakpoint dispatch probe, catalog entry, accepted record, and
submodule update.
W-037 requires no nested ART change; its containing root commit owns the
relocation/fault/GC-root probe, catalog entry, and accepted record against that
same nested snapshot.
W-038's nterp compiled-invoke adapter repair is nested ART commit
`c2ac04128f186388f43162e71fc268452cf1d959`, based on
`03d55ca0174dbf39b54444ce5fdf4a55e5dce331`. Its containing root commit owns
the managed/native probe, catalog entry, structural reviewer extension,
accepted record, and submodule update.
Commit `1a9aa837ad2fb697d246855c695d44f2b53c69e8` removes the
`--force-determinism` request from both OAT generators; manifests still bind
each generated cache set.

## Current position

Numbered implementation-sequence step 1 is `COMPLETE`. The tree builds a
native Windows x64 `dex2oat.exe`, registers the shell-free W-028 no-image
operation gate, and emits Windows-target OAT/image ELF segments with 64-KiB
alignment while retaining `kMaxPageSize = 16384` and
`ART_PAGE_SIZE_AGNOSTIC=1`. The cross-built compiler and all of its ART runtime
consumers share one `artbase.dll` state owner. Two authoritative native
build-26100 executions pass with structurally valid OAT 265 and VDEX 027
artifacts. Those particular runs happened to produce the same bytes, but
cross-generation byte identity is not a step-1 acceptance condition. The
sanitized result is
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

Step 6 is `PARTIAL`. The Windows x64 boot compiler now emits managed, JNI, and
seven trampoline entries into `.oat_unwind.windows`; identical descriptors are
deduplicated. The writer finalizes the section-local Adler-32 checksum and two
dynamic anchors without changing the shared OAT version or Linux output. Both
open modes validate the exact anchor-derived R segment, RX code bounds,
checksum, header, entries, and supported version-1 `UNWIND_INFO`; executable
opens additionally register one stable `RUNTIME_FUNCTION` array, verify sample
lookups, and delete it before releasing memory. Native W-031 proves managed,
JNI, and all seven trampoline lookups plus synthetic `RtlVirtualUnwind`, while
the managed launcher passes managed and JNI runtime calls with JIT disabled.
W-038 now passes an explicit managed throw and a fatal live unwind through the
exact armed boot-OAT function to ART's UEF and one valid minidump. The step
remains partial only for corruption/fallback injection and stronger XMM-bearing
boot-AOT frame coverage.

Step 8 is `COMPLETE`, and step 9 is `PARTIAL`. Windows now generates and stages
an LZ4 `boot.art`, ordinary ELF `boot.oat`, and VDEX, then launches with exact
`-Ximage:runtime/boot-image/boot.art` and rejects silent imageless fallback.
Linux remains uncompressed. The manifest binds the exact path-sensitive
ART/OAT/VDEX set produced by one generation; cross-generation byte identity is
not required. Repeated-generation variation, including in three `-j1` trials,
is retained only as characterization. The gate is experimental rather than
normal product selection and does not exercise successful fallback. It also
uses `-Xint`, so it proves loading rather than real boot-OAT execution.

Step 10 is `PARTIAL`. W-031 proves that the boot OAT contains locatable managed
and JNI bodies and that corresponding runtime calls pass while JIT is disabled.
W-036 narrows the Windows post-start nterp visitor to methods still on the
switch-interpreter bridge, preserving already-published AOT entrypoints. Its
native gate observes ordinary `Integer.parseInt(String)` dispatch exactly once
at the method's current registered boot-OAT RX entry PC, with JIT disabled and
without directly invoking the OAT body. W-037 then requires a nonzero
64-KiB-aligned image relocation and the same boot-OAT delta, observes one
low-address access violation inside registered OAT RX code from an ordinary
null call to `Arrays.sort(int[])`, allows ART to recover it as a
`NullPointerException`, and preserves the same non-null OAT BSS GC root through
eight completed explicit `System.gc()` rounds. W-038 then selects registered
boot-OAT methods for an explicit managed throw and a fatal native callback. The
managed Java trace names its target; the fatal live Windows walk reaches the
exact armed OAT record, progresses through it, reaches ART's UEF, and writes one
valid `MDMP`. Relocation, fault, root, and other explicitly untested execution
variants remain before the step is complete. The accepted records are
[`docs/history/windows_x64_w036_result.md`](docs/history/windows_x64_w036_result.md),
[`docs/history/windows_x64_w037_result.md`](docs/history/windows_x64_w037_result.md),
and
[`docs/history/windows_x64_w038_result.md`](docs/history/windows_x64_w038_result.md).

Step 7 is now `COMPLETE`; step 11 remains `PARTIAL`. W-032 emits and validates
`.oat_cfg.windows`, records CFG policy, and uses a PE-audited CFG-instrumented
caller in a forced-CFG process to enter representative quick and compiled-JNI
boot-OAT bodies. The authoritative Server 2025 gate passes with all seven
trampolines represented and no target-state API calls. Its 18-case semantic
corruption corpus is rejected through both real open modes, and its eight-case
production-`ElfBuilder` layout matrix passes. The separate OAT-1
allocation/resource characterization remains for step 11.
Fine-grained explicit targets are not enabled because the current committed
RW/NX-to-RX transition has default-valid CFG semantics. CFG metadata does not
instrument outgoing indirect branches in generated quick code. The accepted
record is
[`docs/history/windows_x64_w032_result.md`](docs/history/windows_x64_w032_result.md).

The OAT-2 replacement candidate is `DESIGNED`, not selected or implemented.
Its design is merged into [`win32_aot_oat.md`](win32_aot_oat.md). It does not
change the shared OAT version or Windows cache bytes. It would replace the
executable boot transaction with one placeholder-partitioned,
pagefile-section-backed image/OAT span, exact R/RW/RX primary views, and one
temporary RW/NX construction alias. W-033 is now an allocation, efficiency,
and divergence decision gate. W-034/W-035 are conditional, not automatic next
steps. The product will not retain an OAT-1/OAT-2 selector: retain OAT-1 if the
candidate is not materially better, or remove the OAT-1 executable path if the
candidate is ultimately selected. Explicit CFG alone does not justify the
additional loader topology during early bring-up.

The earlier `runtime/oat/oat_file_test.cc` additions are a pre-dispatch loader
characterization suite. They support sequence step 3 and do not constitute
numbered step 1 or executable Windows OAT loading.

## Implementation sequence

| Step | State | Implemented position | Remaining exit condition |
|---:|---|---|---|
| 1. Native trivial no-image `dex2oat` compile | `COMPLETE` | W-028 builds `dex2oat`, `boot.jar`, and `hello.jar`; runs a single-JAR `speed` compile with watchdog and forced swap; validates ELF64/ET_DYN/x86-64, Linux ART OSABI/ABI/flags, 64-KiB `PT_LOAD`, OAT 265, and the complete four-section VDEX 027 envelope; repeated accepted runs happened to produce the same bytes | Retain W-028 as an operation/structure regression gate; cross-generation byte identity is not required |
| 2. Stable generation/startup identities | `PARTIAL` | W-029 pins one `boot` component, logical `/system/framework/boot.jar`, package `runtime/boot.jar`, explicit package-relative `-Ximage:runtime/boot-image/boot.art`, and the x86-64 ART/OAT/VDEX package paths; W-030 makes generation, manifest, staging, and startup consume the record, and native ART accepts the canonical set | Add ART-level negative diagnostics; the existing seven-case matrix is launcher-level and rejects before spawn |
| 3. Pre-dispatch characterization and trampoline regression | `PARTIAL` | Characterization tests exist in `oat_file_test.cc` and the shared trampoline lowering has been source-reviewed | Close H-005 by running the focused tests; add Linux-`GS`/Windows-`R15` disassembly and resolution/quick-to-interpreter execution gates |
| 4. Windows private-copy `ElfOatFile` mapping | `COMPLETE` | Windows `ElfFileImpl::Load()` privately copies every file-backed `PT_LOAD` into the existing ART-owned private allocation; W-030 covers validation-only and executable opens, rejected foreign/section/unaligned/range inputs, exact address, R/RX/RW, no-access gaps, zero fill, owner sharing, source privacy, and cache flush | Retain W-030; no boot-only step-4 exit condition remains |
| 5. VDEX aperture and ownership | `COMPLETE` | Windows reused VDEX mappings use the same checked private-copy primitive for the exact `oatdex` bytes, return an owner-sharing slice, and pass canonical boot startup through `ComputeFields -> LoadVdex -> Setup` | Retain the native end-to-end gate; add broader rollback injection with product-level fallback work |
| 6. `.oat_unwind.windows` | `PARTIAL` | Managed/JNI/seven-trampoline emission, deduplication, checksum, anchors, validation-only parsing, executable registration/lifetime, sample lookup, synthetic `RtlVirtualUnwind`, and JIT-disabled managed/JNI runtime calls pass W-031; W-038 passes explicit managed-exception and fatal boot-OAT walking to UEF/minidump | Add corruption/fallback injection and stronger XMM-bearing boot-AOT frame execution |
| 7. `.oat_cfg.windows` | `COMPLETE` | W-032 independently collects sorted quick/JNI/seven-trampoline targets, merges deduplicated roles, emits the checksum and anchors, parses both open modes, rejects 18 semantic corruptions through validation-only and executable opens, passes all eight metadata/data-img-rel-ro layouts, records policy, and passes forced-CFG guarded quick/JNI calls without target-state API calls | Retain the W-032 transport, corruption, layout, and observation gates; explicit-target allocation is a separate step-11 concern |
| 8. Boot ART/OAT/VDEX generation and staging | `COMPLETE` | W-030 exercises native `ImageWriter`, emits Windows LZ4 `boot.art` plus matching OAT/VDEX, binds the path-sensitive set with one manifest, validates hashes/identity, stages the exact single-component topology, and passes canonical startup | Retain per-generation set integrity; cross-generation byte identity is intentionally not required |
| 9. Experimental selection and fallback | `PARTIAL` | W-030 explicitly selects the staged set, runs from package root, rejects seven launcher mismatches, and fails if ART silently enters imageless startup | Integrate a reviewed product option and exercise successful missing/stale/wrong-target/cross-artifact whole-transaction fallback |
| 10. Real boot-OAT execution | `PARTIAL` | W-031 locates underlying managed/JNI bodies; W-036 observes ordinary `Integer.parseInt(String)` dispatch exactly once at its current registered boot-OAT entry PC; W-037 proves a paired nonzero aligned image/OAT relocation, one recovered access violation from a null `Arrays.sort(int[])` call inside registered OAT RX code, and one BSS root surviving eight completed explicit GC rounds; W-038 proves explicit managed-exception and fatal boot-OAT walking, all with JIT disabled | Cover concrete relocation, fault, root, and other execution variants outside the accepted W-036/W-037/W-038 focused cases on Server 2025 |
| 11. CFG observation and loader decision | `PARTIAL` | W-032 forces CFG on, verifies the PE guard dispatch, enters exact quick/JNI boot-OAT targets, records policy, and proves current OAT-1 default-valid usability with zero target API calls | Run W-033's private-copy/candidate allocation matrix; record reservation, commit, padding, startup, working set, source/ownership complexity, and Linux semantic impact; then explicitly stop or conditionally authorize W-034. No dual-loader product mode is permitted |

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
forced swap-file thresholds, a per-run result manifest, and a target-local
runtime root. The gate is shell-free and deletes only its exact link-free managed
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
| `boot.art` | 2,940,464 | `e344c202362867aead20cd4c1d30281bc2b902ec84cda433ca58ee0089dae4b6` |
| `boot.oat` | 18,754,624 | `73367849da408025f67a795e0618d7f062e9f82029351523bbdb99516360d6bc` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

This completes step 8 and makes step 9 useful but partial. ART/OAT files are
path-sensitive cache artifacts, so byte identity across separately generated
sets is not an acceptance requirement. Earlier normal-parallel and three
serial `-j1` runs made with the now-removed `--force-determinism` request all
started successfully while `boot.art`/OAT bytes varied; that result is
non-blocking characterization, not a compiler defect or reason to serialize.
The configured Windows parallelism remains 16. W-030 is an explicit
experimental gate rather than normal product selection, and it detects but
does not exercise successful imageless fallback. Its `-Xint` launcher proves
loading, not execution from boot-OAT RX code.

## W-031 implementation record

The compiler's existing SDK-independent Windows x64 unwind builder now applies
to JIT, boot image, and boot image extension compilation. `CompiledMethod`
retains the emitted byte array, and `OatWriter` records one sorted entry per
final code range, rejects inconsistent deduplication, adds the seven primary
boot trampolines, interns identical descriptors, and writes the Windows-only
section after `.data.img.rel.ro`. The shared OAT version and Linux writer
layout remain unchanged.

The checksum field is byte offset 44. The writer leaves it zero while hashing
the complete finalized section, then stores the Adler-32 result. The loader
recomputes the same stream as prefix, four zero bytes, and suffix. Dynamic
anchors supply section bounds, which must be file-backed by one exact `PF_R`
`PT_LOAD`. Runtime code bounds are
`Begin() + OatHeader::GetExecutableOffset()` through `End()` (exclusive) and must
be file-backed by one exact `PF_R | PF_X` `PT_LOAD`. `Begin()` is `oatdata`;
`End()` is one-past the word addressed by `oatlastword`.

The version-1 parser accepts flags-zero x64 `UNWIND_INFO` only. It supports
nonvolatile GPR pushes/saves, small and large allocation operations, frame
pointer setup, near/far XMM128 saves, and machine frames. Handler/chained
records are not accepted. Executable opens copy checked entries into one
stable native `RUNTIME_FUNCTION` array, call `RtlAddFunctionTable()`, and prove
sample lookup results. Validation-only opens perform the same parsing without
registration. `RtlDeleteFunctionTable()` failure remains fatal.

Windows unwind-enabled managed frames use 16-byte nonvolatile-XMM slots and
full-width `movdqu` spills/restores. W-025's native gate proves 128-bit XMM
restoration. W-031 proves one managed entry, one JNI entry, all seven
trampoline entries, and synthetic virtual unwind, followed by successful
managed/JNI runtime calls with JIT disabled:

```text
W031_AOT_UNWIND_PASS managed_candidates=1 jni_candidates=1 trampolines=7 virtual_unwind=pass
W031AotUnwindProbe PASS managed_call=pass jni_call=pass
```

The accepted boot OAT measured:

| Quantity | Value |
|---|---:|
| `.oat_unwind.windows` bytes | 515,736 |
| Function entries | 42,663 |
| Unique `UNWIND_INFO` blobs | 163 |
| Serialized code begin/end | 3,602,760 / 18,602,077 |
| Section checksum | `f34e9e18` |
| PE/COFF machine | `0x8664` (`IMAGE_FILE_MACHINE_AMD64`) |

These measurements supersede the pre-XMM characterization. They are one
accepted path-sensitive cache generation, not a byte-reproducibility baseline.
The sanitized native record is
[`docs/history/windows_x64_w031_result.md`](docs/history/windows_x64_w031_result.md).

## W-036 implementation record

The Windows x64 post-start nterp visitor exists to repair invokable managed
methods which remained on the switch-interpreter bridge while nterp was
unavailable during early startup. W-036 makes that scope explicit: the visitor
now skips every method whose current entrypoint is not the switch bridge. This
preserves compiled boot-image entrypoints while leaving the imageless bridge
repair intact.

The managed gate starts a dedicated worker and selects a core method only when
its current quick entrypoint equals its underlying OAT quick code and begins an
exact registered Windows unwind record in the boot OAT. The main thread arms a
one-shot x64 hardware execute breakpoint on that worker. The worker invokes
the selected method through an ordinary Java call; a first-priority VEH
observes the exact PC, restores the prior debug-register state, and resumes.
The probe never replaces an `ArtMethod` entrypoint and never directly calls the
OAT code pointer.

Server 2025 passes with JIT disabled:

```text
W036_BOOT_OAT_DISPATCH_PASS target=int java.lang.Integer.parseInt(java.lang.String) current_entry=oat rx_pc=hardware_breakpoint hits=1 wrong_single_steps=0 jit=disabled
W036BootOatDispatchProbe PASS dispatch=ordinary rx_pc=observed jit=disabled
```

This closes the representative ordinary-dispatch condition within step 10.
The pre-W-037 boundary remained relocation, fault, GC/root, exception, and
fatal stack-walk coverage. The final regression cache set measured 2,940,464-byte
`boot.art`, 20,169,448-byte `boot.oat`, and 8,309,376-byte `boot.vdex`; its hashes and
the complete gate contract are recorded in
[`docs/history/windows_x64_w036_result.md`](docs/history/windows_x64_w036_result.md).

## W-037 implementation record

W-037 extends ordinary boot-OAT execution in one JIT-disabled native process.
It reads the persisted boot-image header and compares it with the live
`ImageSpace`, requiring a nonzero relocation divisible by the Windows 64-KiB
artifact alignment and the same delta for the live boot OAT. It accepts a
candidate only when the current `ArtMethod` entrypoint still equals its
underlying OAT quick code and resolves through the registered Windows function
table. The accepted cache selects `Arrays.sort(int[])`.

A first-priority observing VEH counts only access violations on the test thread
whose PC lies in the boot-OAT RX range. It never modifies the context or claims
the exception. The ordinary Java null call produces exactly one such
low-address fault; ART's existing handler recovers it as a caught
`NullPointerException` with a nonempty Java stack trace. Before that call, the
probe creates a JNI weak reference to one non-null OAT BSS GC root. After
allocation pressure and eight explicit `System.gc()` rounds, the heap's
completed-GC counter has advanced by at least eight, the selected BSS slot
remains non-null and identifies the same object, and the selected method still
publishes the exact registered OAT entrypoint captured before the call.

Server 2025 reports:

```text
W037_BOOT_OAT_EXECUTION_PASS target=void java.util.Arrays.sort(int[]) relocation=nonzero_aligned delta=-253952000 oat=paired fault=managed_oat hits=1 fault_address=low gc_rounds=8 gc_completed=8 bss_roots=1 root_same=1 jit=disabled
W037BootOatRelocationFaultGcProbe PASS relocation=observed fault=recovered gc_roots=survived jit=disabled
```

This closes the focused nonzero-relocation, null-fault recovery, and BSS-root
survival case. Step 10 remains `PARTIAL`: this one run does not establish every
relocation sign/topology, implicit-fault form, or root slot/collector
combination. The complete native record is
[`docs/history/windows_x64_w037_result.md`](docs/history/windows_x64_w037_result.md).

## W-038 implementation record

W-038 closes the explicit managed-exception/fatal-stack-walk condition without
replacing an `ArtMethod` entrypoint or directly calling OAT code. Its managed
child selects `Integer.parseInt(String)` only while the current entrypoint
equals the underlying boot-OAT code and begins an exact registered Windows
function. An ordinary invalid call throws `NumberFormatException`; the
nonempty Java trace contains the selected method, and native verification
requires the exact entrypoint to remain published.

The fatal child selects registered
`Arrays.sort(Object[], Comparator)` boot-OAT code and supplies a comparator
whose native callback raises a hardware access violation. With ART's bounded
fatal trace enabled, `RtlVirtualUnwind` reaches the exact armed OAT
`RUNTIME_FUNCTION` at frame 6, advances RSP from `0x73ba72f560` to
`0x73ba72f5b0`, crosses all remaining ART/executable/OS frames, and ends at zero
PC after 20 frames. ART's UEF runs and writes exactly one valid 1,207,378-byte
`MDMP`.

Bring-up isolated the defect to the nterp-to-compiled PE boundary. The repeated
adapter PC represented two legitimate nterp frames with increasing RSP, but
the adapter's synthetic allocation skipped the nterp frame without restoring
its saved nonvolatile registers. The following OAT frame therefore saw the
wrong RBP. All 187 dynamic-gap adapters now describe saved RBX, RBP, and
R12-R15 as well as the allocation, while retaining the existing normal-return
continuation slot. Public range markers allow the structural reviewer to check
the exact count, allocation and save-offset sequences, zero prologues, and
contiguous ranges. The rebuilt native W-010 stage passes 8/8 with the enhanced
audit.

Server 2025 reports:

```text
W038_MANAGED_EXCEPTION_PASS target=int java.lang.Integer.parseInt(java.lang.String) type=explicit caught=1 trace=nonempty trace_target=1 entry_unchanged=1 jit=disabled
W038BootOatManagedExceptionProbe PASS exception=caught trace=target entry=oat jit=disabled
W038_FATAL_ARM target=void java.util.Arrays.sort(java.lang.Object[], java.util.Comparator) oat_base=0x60b20718 begin=0xc896c8 end=0xc89764 jit=disabled
ART_WINDOWS_X64_UNWIND_TRACE frame=6 pc=0x617a9e6a rsp=0x73ba72f560 lookup=1 image=0x60b20718 begin=0x00c896c8 end=0x00c89764 unwind=0x0123cb34
ART_WINDOWS_X64_UNWIND_TRACE step=6 kind=virtual next_pc=0x7ffdae47c0fb next_rsp=0x73ba72f5b0 establisher=0x73ba72f5a8
ART_WINDOWS_X64_UNWIND_TRACE end frames=20 reason=zero_pc final_pc=0x0 final_rsp=0x73ba72fd60
ART Win32 UEF: exception 0xc0000005 at 0x7ffdbbb73010 access=1 fault_addr=0x1234
```

W-038 passes 1/1 in 2.47 seconds, with its two child contracts complete and
one minidump. This accepts the managed-exception/fatal-walk condition for steps
6 and 10. The steps remain `PARTIAL` only for their other stated exit
conditions. The complete native record is
[`docs/history/windows_x64_w038_result.md`](docs/history/windows_x64_w038_result.md).

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
| 2026-08-06 | Windows Server 2025 build 26100 | W-030 generates the LZ4 boot set and canonical startup passes in 1.13 s; both W-030 gates pass 2/2, ART exits 0 with all required markers, no forbidden fallback marker, and seven launcher mismatches rejected | **Authoritative boot-only loading acceptance**; step 8 complete, step 9 partial, and step 10 open; see [`docs/history/windows_x64_w030_result.md`](docs/history/windows_x64_w030_result.md) |
| 2026-08-06 | Windows Server 2025 build 26100 repeated-generation characterization with the superseded forced-determinism request | Normal parallel and three `-j1` generations all start successfully; VDEX remains stable while `boot.art` and OAT `.text` size/hash change | Non-blocking path-sensitive cache variation; per-generation manifest integrity, not cross-generation byte identity, is the contract |
| 2026-08-07 | Windows Server 2025 build 26100, no forced byte determinism | W-030 private-copy probe passes in 0.07 s; canonical LZ4 boot startup passes in 1.13 s, and W-028/W-029 pass in 0.64/0.12 s | **Authoritative correction acceptance**; steps 4/5/8 complete, step 9 partial, and step 10 open |
| 2026-08-07 | Fresh agent01 Linux and Linux-hosted Windows builds | Full Linux graph and 15/15 catalog gates pass; the full Windows cross graph builds; focused Python harness tests pass 21/21 | Shared compiler/writer/runtime changes compile on both targets and retain the Linux runtime baseline |
| 2026-08-07 | Windows Server 2025 build 26100 | W-025 passes 9/9, W-030 passes 2/2, and W-031 passes 1/1; W-031 reports managed/JNI runtime calls plus 42,663 registered entries, seven trampolines, and synthetic virtual unwind | **Authoritative unwind implementation evidence**; step 6 and step 10 are partial; this pre-W-032 checkpoint is superseded for CFG status by the next row |
| 2026-08-07 | Windows Server 2025 build 26100 plus fresh agent01 Linux regression | W-032 passes 3/3 with a CFG-instrumented PE caller, forced policy, 42,649 unique targets, guarded quick/JNI calls, 18 semantic corruptions rejected through 38 real opens, and all eight metadata/relro layouts accepted; the Python suite passes 225/225, full Linux build/boot generation passes, and Linux catalog passes 15/15 | **Authoritative CFG transport and observation evidence**; step 7 complete and step 11 partial; explicit-target allocation/resource characterization remains |
| 2026-08-07 | Windows Server 2025 build 26100 | W-036 passes 1/1 with JIT disabled; ordinary `Integer.parseInt(String)` dispatch hits its exact current registered boot-OAT RX entry PC once, with zero unrelated single-step exceptions | **Authoritative representative ordinary-dispatch evidence**; step 10 remains partial only for relocation, fault, GC/root, exception, and fatal-walk breadth; see [`docs/history/windows_x64_w036_result.md`](docs/history/windows_x64_w036_result.md) |
| 2026-08-07 | Windows Server 2025 build 26100 affected-stage regression plus fresh agent01 Linux regression | W-030 passes 2/2, W-031 passes 1/1, W-032 passes 3/3, and W-036 passes 1/1 against a fresh path-sensitive cache set; the Python suite passes 225/225, full Linux build/boot generation passes, and Linux catalog passes 15/15 | **7/7 native regression PASS** after preserving boot-AOT entrypoints; loading, unwind, CFG observation/corruption/layout, ordinary dispatch, and the shared Linux baseline remain compatible |
| 2026-08-07 | Windows Server 2025 build 26100 | W-037 passes 1/1 in 1.29 s; an ordinary null `Arrays.sort(int[])` call under a nonzero 64-KiB-aligned image/OAT relocation produces exactly one registered boot-OAT access violation recovered as `NullPointerException`, and one non-null BSS root remains identical through eight completed explicit collections | **Authoritative focused relocation/fault/root evidence**; at this pre-W-038 checkpoint, step 10 still lacked broader exception/fatal walking and variants outside the focused case; see [`docs/history/windows_x64_w037_result.md`](docs/history/windows_x64_w037_result.md) |
| 2026-08-07 | Windows Server 2025 build 26100 affected-stage regression plus fresh agent01 Linux regression | W-030 passes 2/2, W-031 passes 1/1, W-032 passes 3/3, W-036 passes 1/1, and W-037 passes 1/1 in 1.28 s against a fresh cache set; the Python suite passes 227/227, full Linux build/boot generation passes, and Linux catalog passes 15/15 | **8/8 native regression PASS**; the initial and final W-037 generations observe distinct valid relocation deltas and cache bytes while loading, unwind, CFG, dispatch, fault recovery, root survival, and the shared Linux baseline remain compatible |
| 2026-08-07 | Windows Server 2025 build 26100 | W-038 passes 1/1 in 2.47 s: the explicit managed exception retains its registered boot-OAT entrypoint and names the target in its Java trace; the fatal child unwinds through the exact armed boot-OAT frame, reaches ART's UEF, and creates one valid 1,207,378-byte `MDMP` | **Authoritative managed-exception/fatal-walk evidence**; this closes that listed step-6/step-10 gap while both steps remain partial for their other stated breadth; see [`docs/history/windows_x64_w038_result.md`](docs/history/windows_x64_w038_result.md) |
| 2026-08-07 | Windows Server 2025 build 26100 affected-stage regression | W-030 passes 2/2, W-031 passes 1/1, W-032 passes 3/3, W-036 passes 1/1, W-037 passes 1/1, and W-038 passes 1/1; the enhanced W-010 adapter structural audit separately passes 8/8 | **9/9 boot-OAT regression PASS** with all 187 nterp compiled-invoke adapter records audited; loading, unwind, CFG, dispatch, fault/root, managed-exception, and fatal-walk behavior remain compatible |
| 2026-08-07 | Fresh agent01 Linux regression | Focused Python passes 10/10; the full host/bp2cmake suite passes 320/320; Linux configure audits 2,090 compile commands, 2,174 Ninja commands, and 33 product links; full build/boot generation and the 15/15 Linux catalog pass; x86-64 mterp generation succeeds | Shared nterp/runtime and catalog changes retain the Linux baseline; stale case-inventory counts and missing adjacent AOT result records are corrected |

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

1. Retain W-037's focused paired relocation, managed null-fault, and BSS-root
   gate plus W-038's managed-exception/fatal-walk gate. Add relocation,
   fault/root, or other execution variants only where a concrete untested
   product contract requires them.
2. Add `.oat_unwind.windows` corruption/fallback injection and an actual
   XMM-bearing boot-AOT frame execution gate.
3. Integrate reviewed product boot-AOT selection plus successful
   whole-transaction imageless fallback and ART-level negative identity
   diagnostics.
4. Measure the implemented private-copy baseline: startup stages, reservation,
   commit, working set, padding, mapping count, and current Windows/shared ART
   source delta. Promote the cross-target 16-/64-KiB artifact comparison into
   an automated regression, close H-005, and add the two-target trampoline
   regression.
5. Only after the baseline is usable and measured, run W-033 as an isolated
   allocation/protection and architecture-decision characterization. Prove or
   reject exact placeholder replacement, RX-invalid primary views, RW/NX alias
   coherence, target activation, omitted-target failure, and rollback. Compare
   resource costs and projected code/semantic divergence with OAT-1; do not
   infer support from `PAGE_TARGETS_NO_UPDATE` or the JIT gate.
6. Record a stop/proceed decision after W-033. Keep OAT-1 unless the candidate
   shows a material efficiency or required semantic benefit that justifies the
   extra topology. Explicit CFG alone is insufficient during early bring-up.
   Only a reviewed proceed decision authorizes W-034.

Do not begin W-035 real boot integration before W-033 records a proceed
decision and W-034 passes. A W-035 review must select one executable loader and
remove the losing path; it must not add a runtime OAT-1/OAT-2 selector. Do not
begin application OAT, successful-load unloading, outgoing quick-code CFG
instrumentation, or security hardening merely to close an early boot-only
step.
