# Windows AOT and OAT design

Status: early bring-up design baseline (revised 2026-08-06). This document records the
current ART OAT/VDEX/image contracts and the selected Windows AOT artifact and
loader design. Windows keeps the same ELF64 coat and header identity as Linux,
while using 64-KiB ELF/image segment alignment for the Windows allocation
granularity. An ART-owned, OAT-only private-copy path loads it.

Windows OAT generation and executable loading are not implemented yet.
Implementation stage 1, the pre-dispatch characterization suite, is now in the
tree; it does not enable Windows AOT. The supported Windows product remains
imageless nterp/JIT while this independent future track is open. The
authoritative implementation gate is Windows Server 2025 Datacenter
Evaluation, x64 build 26100. Linux and Wine remain development and structural
gates; the former Windows 10 lab host is unavailable.

A design review on 2026-08-05 added eleven findings. A source-level re-audit
accepted the location-string, image-mode, native-`dex2oat`, commit-charge,
dynamic-symbol, predicate, and snapshot findings; refined the CFG-alignment
finding; and rejected three proposed blockers. In particular, the claimed
`GS`-based Windows trampoline defect is false because the shared x86-64
assembler already turns the same source expression into an `R15`-relative
jump on Windows. The current verdict for every finding is recorded under
"Design review findings".

The source snapshot is `vendor/art` at
`android-16.0.0_r4-92-gffbfe48fd1`. The design was originally written against
`android-16.0.0_r4-76-g4eab6e7423`; the 16 intervening commits are W-027
Unicode and build-prelude cleanups, and the 2026-08-05 review re-verified every
source claim below against the newer snapshot. See "Design review findings".

## Executive decision

1. OAT, VDEX, and ART images are internal compiled-cache formats. They are not
   public stable ABIs. A matching runtime/compiler build generates and loads
   them; incompatible artifacts are regenerated.
2. The logical OAT records remain useful on Windows. The current executable
   coat and loading contract are tightly coupled to ELF program headers,
   dynamic symbols, load bias, BSS, image reservations, and VDEX placement.
3. Windows OAT remains the ordinary ART ELF64 format. `EI_OSABI`,
   `EI_ABIVERSION`, `e_flags`, and the program-header encoding/semantics remain
   those of the Linux ART writer. The optional Windows-only unwind and CFG
   metadata share a read-only `PT_LOAD`; they do not define a second coat.
   Both products retain
   `ART_PAGE_SIZE_AGNOSTIC=1`.
   Linux keeps the current 16-KiB `kMaxPageSize` and 16-KiB
   `kElfSegmentAlignment` unchanged. Windows has 4-KiB virtual-memory pages but
   a 64-KiB allocation granularity, so it keeps `kMaxPageSize` as an OS-page/GC
   bound and selects a target-specific 64-KiB `kElfSegmentAlignment` for ELF
   and image layout. The current source alias
   `kElfSegmentAlignment = kMaxPageSize` must therefore be split; setting the
   Windows `kMaxPageSize` to 64 KiB merely to obtain ELF alignment is rejected.
4. The first implementation is boot-only. It reuses the existing
   `ElfOatFile`/`OatFileBase` transaction where practical and adds only the
   Windows private-copy, VDEX, protection, cache-flush, and unwind mechanics
   that the current `MAP_FIXED`-style path cannot provide.
5. OAT-1 consumes the existing committed ART boot reservation. It retains the
   current Windows `MemMap` whole-span `MEM_RESERVE | MEM_COMMIT` semantics,
   privately copies `PT_LOAD` bytes, zeroes BSS, leaves gaps `PAGE_NOACCESS`,
   applies final R/RX/RW protections, registers Windows x64 unwind data, and
   publishes entrypoints last.
6. AOT unwind is required for usable Windows stack walking. CFG has two
   deliberately separate modes. Early bring-up defaults to observation mode,
   which records policy and proves real indirect OAT calls without changing
   target state. A later explicit-target mode consumes the independently
   versioned `.oat_cfg.windows` target list. That mode is not an early blocker
   and cannot be enabled until the invalid-by-default allocation sequence is
   proven with the committed OAT-1 reservation.
7. Application OAT, successful-load unloading, shared-view/OAT-2 work, and
   cache/adversarial-input security hardening are outside the early bring-up
   scope. Security-sensitive product enablement requires a later review.
8. The full Bionic linker, `soinfo`, dependency, relocation, namespace, TLS,
   constructor, and symbol-interposition machinery remain rejected. Reuse the
   existing ART ELF reader first; copy selected Bionic algorithms only if a
   concrete correctness gap requires them.
9. Executable-memory capability is an ART product prerequisite. The initial
   design makes no `ProhibitDynamicCode`/ACG compatibility claim.

In this document, “Windows OAT” means the ordinary ART ELF container with
Linux-identical ELF header identity and Windows-specific 64-KiB segment
alignment, carrying Windows-targeted x86-64 quick code and Windows unwind/CFG
metadata.

## Format stability and identity

### Internal, not public-stable

The durable concepts within one matching ART build include:

- `OatHeader` magic, version, instruction set, feature bitmap, checksum, and
  key/value store;
- per-dex records, dex identity, class offsets, method offsets, and compiled
  or interpreted class state;
- `OatQuickMethodHeader`, `CodeInfo`, stack maps, dex-register maps, and the
  association between an `ArtMethod` and compiled entrypoint;
- BSS mappings for methods, types, strings, method types, and GC roots; and
- image-relocation metadata binding code and data to the corresponding image.

The following are volatile implementation details:

- packed-struct size and field layout;
- quick entrypoint and `QuickEntryPoints` layout;
- code-generation ABI and relocation encodings;
- section/program-header arrangement and dynamic-anchor names;
- VDEX sections and verifier/type-lookup encoding;
- ART image section ordering and object layout; and
- whether DEX is embedded or supplied only through VDEX.

The project treats the complete artifact set as a compiled cache. An exact
runtime/compiler/container/ABI mismatch rejects and regenerates it.

### Current pinned versions

| Artifact | Magic/version in this tree | Validation |
|---|---|---|
| OAT logical header | `oat\n`, `265\0` | `OatHeader::IsValid()` and `CheckOatVersion()` |
| VDEX | `vdex`, `027\0` | `VdexFileHeader::IsValid()` |
| ART image | `art\n`, `118\0` | `ImageHeader::IsValid()` |

These values identify only the pinned snapshot. They are not permanent Windows
format promises.

Recent upstream changes illustrate the volatility:

| Date | Change | Loader-visible consequence |
|---|---|---|
| 2024-04 | Renamed `.data.bimg.rel.ro` to `.data.img.rel.ro` | Writer/loader symbol and section contract changed |
| 2024-10 | Stored app-image methods in `.data.img.rel.ro` | Relocation and BSS layout changed |
| 2024-12 | Reduced `.rodata` alignment | ELF layout assumptions changed |
| 2025-01 | Moved dynamic sections to the start of OAT | File layout and discovery changed |
| 2025-02 | Incremented OAT version after a released collision | Old artifacts were deliberately rejected |
| 2026-01 | Removed a VDEX section from OAT | OAT/VDEX coupling and version changed |
| 2026-03 | Bumped OAT version after a revert | Even reverted semantics invalidated artifacts |

The Windows unwind and CFG transports do not bump the shared OAT version.
Linux and Android do not emit either Windows-only section, and their OAT
format and byte layout must remain unchanged. The independently versioned
`.oat_unwind.windows` header identifies its target machine and encoding; a
Windows executable boot load rejects a quick-code artifact that lacks the
required unwind anchors. The earlier validation-only boot pass rejects it as
well.
`.oat_cfg.windows` is optional in observation mode and required only by
explicit-target mode. There are no legacy Windows AOT artifacts that require
a shared-version transition.

## Current artifact set

A normal boot-image build produces:

```text
boot.art    ART heap image: objects, classes, roots, tables, bitmap
boot.oat    ELF/ET_DYN: OAT metadata, quick code, BSS layout, anchors
boot.vdex   DEX/checksums, verifier dependencies, type-lookup data
```

Application output commonly uses `.odex` or `.oat`, but the logical roles are
the same.

### OAT ELF regions

The current `ElfBuilder` constructs these conceptual regions:

| Region/anchor | Role |
|---|---|
| ELF header and program headers | Identity, machine, load segments, alignment, and dynamic table |
| `.rodata` / `oatdata` | `OatHeader`, key/value store, dex/class/method records, maps, metadata |
| `.text` / `oatexec` | Quick code, trampolines, method headers, `CodeInfo`, stack maps |
| `oatlastword` | End marker for the OAT data/code range |
| `.data.img.rel.ro` | Boot/app image relocation entries; writable during relocation, then R |
| `.bss` / `oatbss*` | Per-instance resolved methods, dex-cache slots, and GC roots |
| `.dex` / `oatdex*` | NOBITS virtual range populated from the companion VDEX when present |
| `.dynstr`, `.dynsym`, `.hash`, `.dynamic` | Small lookup structure for the OAT anchors |
| Debug sections | Build ID and optional DWARF/minidebug data; never mapping authority |

The Windows x64 product adds one required read-only loadable section,
`.oat_unwind.windows`, holding the AOT `RUNTIME_FUNCTION` equivalents and their
`UNWIND_INFO` bytes. The platform suffix identifies Windows ownership while the
section header identifies the target machine; do not encode bitness or ISA in
the section name. The section is specified under "AOT unwind format and
transport" and is absent from Linux and Android output. Windows may also emit
the read-only `.oat_cfg.windows` section. It carries exact indirect-call target
offsets for CFG and uses the same target-machine convention; there are no
`.win32`, `.win64`, or per-ISA metadata section-name variants. It is specified
under "Windows CFG format and integration" and is also absent from Linux and
Android output.

Both sections are explicitly Windows-only. Their `target_machine` fields store
the standard 16-bit PE/COFF `Machine` value, zero-extended to `uint32_t`, from
[PE Format: Machine Types](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#machine-types).
Do not introduce an ART-local enum or numbering scheme. Version 1 accepts only
`IMAGE_FILE_MACHINE_AMD64` (`0x8664`). Other standard machine values, including
`IMAGE_FILE_MACHINE_ARM64EC`, require separately reviewed writer, loader,
unwind, CFG, and native execution gates before acceptance.

The dynamic table currently needs only `DT_HASH`, `DT_STRTAB`, `DT_SYMTAB`,
`DT_SYMENT`, `DT_STRSZ`, `DT_SONAME`, and `DT_NULL`. There are no normal DSO
imports or ELF relocation dependencies.

### OAT writer lifecycle

`OatWriter` and `ElfBuilder` jointly:

1. reserve/write VDEX headers, checksums, DEX, verifier dependencies, and
   lookup tables;
2. emit `OatHeader`, key/value data, dex records, class/method tables, maps,
   BSS mappings, and image-relro metadata;
3. finalize compiled-code, method, trampoline, and indirect-target offsets;
4. serialize any target-specific unwind and CFG metadata;
5. emit quick code and trampolines;
6. assign ELF virtual/file offsets and dynamic anchors;
7. emit BSS and optional DEX virtual ranges;
8. finalize checksums and ELF headers; and
9. emit the matching ART image where requested.

OAT offsets are often 32-bit. Windows does not implicitly widen them.

### Current and designed loaded layout

The current writer lays out allocatable regions in this order. Optional
regions disappear without changing the order of the regions that remain:

```text
ELF/program headers
  -> .dynstr/.dynsym/.hash/.dynamic       R
  -> .rodata (oatdata)                    R
  -> .text (oatexec .. oatlastword)       RX
  -> .data.img.rel.ro                     RW, optional; sealed R by Setup()
  -> .bss                                 RW, NOBITS, optional
  -> .dex                                 R, NOBITS, optional VDEX aperture
  -> non-loaded debug/section tables
```

`oatlastword` ends the logical metadata/quick-code range; it does not include
`.data.img.rel.ro`. `OatWriter::oat_size_` does include the optional
image-relocation section and its alignment, and `bss_start_` is aligned from
that size.

The Windows design inserts its metadata last among `PROGBITS` regions:

```text
ELF/program headers
  -> .dynstr/.dynsym/.hash/.dynamic       R
  -> .rodata (oatdata)                    R
  -> .text (oatexec .. oatlastword)       RX
  -> .data.img.rel.ro                     RW, optional; sealed R by Setup()
  -> .oat_unwind.windows                  R, Windows x64 boot output only
  -> .oat_cfg.windows                     R, optional Windows CFG target list
  -> .bss                                 RW, NOBITS, optional
  -> .dex                                 R, NOBITS, optional VDEX aperture
  -> non-loaded debug/section tables
```

The first emitted Windows metadata section starts a distinct R `PT_LOAD`,
whether its predecessor is RX `.text` or RW `.data.img.rel.ro`. If unwind is
present, CFG follows it at 4-byte alignment in the same R segment; if CFG is
the only metadata section, `ElfBuilder::Section::AddSection()` raises its
effective alignment to `kElfSegmentAlignment` when the program-header flags
change. Thus CFG does not create a second 64-KiB gap after unwind.
`oatlastword` stays unchanged. The Windows writer finalizes both serialized
payloads after code offsets are known, runs `InitDataImgRelRoLayout()`, assigns
the optional unwind and CFG starts in that order, advances the running offset
through both payloads, and only then assigns `oat_size_` and derives
`bss_start_`. Linux and Android never reserve these sections, their symbols,
or extra dynamic-section capacity.

### VDEX layout

The current VDEX consists of:

```text
VdexFileHeader
VdexSectionHeader[4]
  checksums
  optional concatenated DEX files
  verifier dependencies
  type-lookup-table data
```

Every section has its own offset and size. VDEX has an independent version,
but execution still requires matching OAT and DEX checksums.

### ART image layout

The ART image header records image base/reservation/size, image and OAT
checksums, OAT ranges, pointer size, roots, and sections such as:

```text
Objects, ArtFields, ArtMethods, ImTables, IMTConflictTables,
RuntimeMethods, JniStubMethods, InternedStrings, ClassTable,
StringReferenceOffsets, DexCacheArrays, Metadata, ImageBitmap
```

Boot images reserve image and OAT components together and currently relocate
recorded OAT/image ranges by one delta. Application images can use a separate
actual OAT relocation range. The Windows path must preserve that ART-owned
placement contract.

## Current Android OAT loading path

The path-based `OatFile::Open()` in this snapshot first requires the companion
VDEX to exist. It then calls `OatFileBase::OpenOatFile<DlOpenOatFile>()`. The
template fixes the order of the Android transaction:

```text
DlOpenOatFile::PreLoad()
  -> DlOpenOatFile::Load()
  -> OatFileBase::ComputeFields()
  -> DlOpenOatFile::PreSetup()
  -> OatFileBase::LoadVdex()
  -> OatFileBase::Setup()
```

The stages have the following concrete behavior:

1. `PreLoad()` counts the current `dl_iterate_phdr()` entries. This is only an
   optimization for finding the newly loaded object later.
2. `Load()` accepts only executable, non-`low_4gb` use and canonicalizes the
   path before calling `android_dlopen_ext()` with `RTLD_NOW`.
3. `ANDROID_DLEXT_FORCE_LOAD` forces a new mapping rather than reusing a prior
   handle. This is required for independent BSS/dex-cache state and class
   unloading when the same OAT is opened more than once.
4. If ART supplied a reservation, `ANDROID_DLEXT_RESERVED_ADDRESS` asks Bionic
   to place the complete object inside it. ART then finds the loaded `PT_LOAD`
   ranges with `dl_iterate_phdr()` and transfers the used prefix from the
   reservation into `DlOpenOatFile` ownership.
5. OAT outside the ART APEX is loaded in Bionic's exported system namespace.
   Search paths and namespace links are not used for OAT dependencies, but the
   permitted-path policy still applies.
6. `ComputeFields()` uses `dlsym()` to resolve `oatdata`, `oatlastword`, the
   optional image-relro and BSS anchors, and `oatdex`/`oatdexlastword`.
   `ComputeElfBegin()` separately uses `dladdr()` to recover the ELF base.
7. `PreSetup()` finds the loaded object by the segment containing `oatdata` and
   creates ART `MemMap` placeholders for its `PT_LOAD` ranges. Bionic still
   owns the actual mappings; the placeholders make the ranges visible to
   ART's memory-map accounting.
8. `LoadVdex()` calls `VdexFile::OpenAtAddress()` with the dynamic `oatdex`
   range and `mmap_reuse=true`. On Android this replaces the ELF `SHT_NOBITS`
   dex range with the companion VDEX mapping at the exact address.
9. `Setup()` validates OAT magic/version/ISA, region ordering, offsets, BSS,
   DEX, checksums, boot class path, and class-loader context. Later image and
   OAT management code performs relocation and publishes usable entrypoints.
10. Destruction calls `dlclose()` before discarding ART's reservation/map
    wrappers.

If `DlOpenOatFile` fails, the path-based API falls back to
`ElfOatFile`/`ElfFile`, ART's own generic ELF reader and segment mapper. The
fd-based `OatFile::Open()` does not try `DlOpenOatFile` at all; it selects
`ElfOatFile` directly. `OpenFromSdm()` tries the same dlopen path for the OAT
ZIP entry and then falls back to `ElfOatFile`.

The Windows path replaces only the segment-mapping operation that cannot be
expressed through the current Windows file-mapping backend. It should first
reuse `ElfOatFile`/`ElfFile` rather than reproduce their parser and symbol
lookup. It does not replace `OatFileBase::ComputeFields()`, `LoadVdex()`,
`Setup()`, image relocation, or higher-level publication.

## Selected Windows architecture

### Artifact ownership

| Artifact | Selected treatment | Owner |
|---|---|---|
| OAT | Current ART ELF64 with Windows x64 quick code, unwind data, and optional CFG targets | `ElfOatFile` plus a Windows private-copy mapping helper |
| VDEX | Read-mostly data, initially populated in the existing `oatdex` range | `VdexFile` inside OAT transaction |
| ART image | Reserved mapping, copy/decompression and ART relocation | `ImageSpace` |

The private-copy helper is not exported as `dlopen`. It is selected by both
Windows validation-only and executable `ElfOatFile` opens and does not become
a general ELF DSO loader.

### Explicit non-goals

- A general `.so` loader, including `libjiagu.so`.
- `DT_NEEDED`, PLT/GOT binding, REL/RELA/JMPREL, IFUNC, text relocation, TLS,
  constructors/destructors, symbol interposition, or namespaces.
- Application OAT, application images, duplicate-instance/class-unloading
  semantics, and successful boot-OAT unloading in the initial milestone.
- Shared 64-KiB file views or a separately versioned OAT-2 layout.
- Cache threat modeling, hostile-input hardening, Authenticode treatment, and
  debugger/profiler behavior equivalent to a DLL in early bring-up.
- `ProhibitDynamicCode`/ACG compatibility or policy bypasses.
- XFG, CFG export suppression, strict CFG policy, and fine-grained CFG
  enforcement as an early support requirement.

CFG observation mode is the initial default. Native execution tests record the
process policy and exercise real indirect targets without calling
`SetProcessValidCallTargets`, disabling CFG, or requiring a mitigation bypass.
The `.oat_cfg.windows` format and explicit-target mode are designed below, but
the latter remains gated and is not an early support claim. CET user shadow
stacks remain unsupported under the existing Windows process contract.

## Bionic reuse boundary

Do not copy the full Bionic linker. It solves dependency graphs, namespaces,
relocations, TLS, constructors, interposition, CFI shadow, link maps, ZIP/APK
loading, GNU properties, RELRO sharing, and Android compatibility policy.

The smallest-diff implementation starts with ART's existing
`ElfOatFile`/`ElfFile` parser, loaded-size calculation, dynamic-symbol lookup,
and `OatFileBase` transaction. The Windows-only addition supplies private
population of the already committed reservation, final protections, VDEX
copy ownership, cache flush, AOT unwind registration, and narrow CFG policy/
target handling.

If implementation or characterization finds a concrete correctness gap,
selected Bionic algorithms may be copied under this boundary:

| Area | Treatment |
|---|---|
| ELF identity, header, dynamic symbols, and program headers | Reuse existing ART implementation first |
| Checked file ranges and load-span/load-bias calculation | Add focused correctness checks; copy selected Bionic algorithms only where demonstrated necessary |
| Segment zero-fill and PHDR containment rules | Reuse semantics, not POSIX calls |
| POSIX `mmap(MAP_FIXED)` backend | Do not copy |
| `soinfo`, dependencies, relocations, namespaces, TLS, constructors | Do not copy or implement |
| OAT anchor lookup | Reuse `ElfFile::FindDynamicSymbolAddress()`; `OatFileBase::ComputeFields()` resolves the two required `oatunwindwindows` anchors and the two optional `oatcfgwindows` anchors under Windows-only guards |
| Logical OAT validation | Keep existing `OatFile` setup logic |
| Windows reservation/protection/VDEX/unwind/CFG | Add an OAT-only private-copy helper, unwind registry, and narrow CFG manager; do not turn them into a general loader |

Bionic's `linker_phdr.cpp` is BSD-licensed. Copied code retains its copyright,
conditions, disclaimer, source provenance, pinned tag, and required binary
distribution notice.

Bionic remains a compatibility-oriented DSO loader. Early Windows bring-up
accepts only artifacts generated and staged by the matching ART product build.
Broader hostile-input validation and a security boundary are deferred; basic
range, layout, permission, checksum, and version failures still reject for
correctness.

## Early Windows boot-OAT ELF profile

### ELF header and program headers

Accept only:

- ELF64, little-endian, `ET_DYN`, `EM_X86_64`;
- the current ART writer identity: `EI_OSABI == ELFOSABI_LINUX`,
  `EI_ABIVERSION == 0`, and the same x86-64 `e_flags` as Linux ART;
- `e_entry == 0`;
- exact ELF/program-header structure sizes;
- a nonzero bounded header count no larger than the writer maximum;
- one `PT_PHDR`, one or more `PT_LOAD`, exactly one `PT_DYNAMIC`, and only
  versioned allowed notes;
- R, RX, and RW segments, never W+X or execute-without-read;
- `p_filesz <= p_memsz`;
- the Windows page-size-agnostic writer alignment,
  `kElfSegmentAlignment == 65536`;
- checked in-file file ranges and checked in-span virtual ranges;
- required file/virtual offset congruence;
- sorted non-overlapping load ranges with no conflicting shared page; and
- a loaded span below project, ART-offset, and Windows function-table limits.

Reject `PT_INTERP`, `PT_TLS`, extended-numbering tricks, unknown load-bearing
types, overlaps, ambiguous permissions, and unrepresentable arithmetic.

Program headers alone authorize mapping. Section/debug headers never authorize
an executable range.

### Dynamic table and anchors

Allow only:

```text
DT_HASH DT_STRTAB DT_SYMTAB DT_SYMENT DT_STRSZ DT_SONAME DT_NULL
```

Reject dependency, relocation, PLT, init/fini, runpath, audit, TLS, IFUNC, and
unknown required tags. No resolver exists behind the parser.

Resolve only:

```text
oatdata, oatexec, oatlastword,
oatdataimgrelro, oatdataimgrelrolastword,
oatdataimgrelroappimage,
oatbss, oatbssmethods, oatbssroots, oatbsslastword,
oatdex, oatdexlastword,
oatunwindwindows, oatunwindwindowslastword
```

`oatunwindwindows`/`oatunwindwindowslastword` are the two anchors added for the
Windows x64 AOT unwind table. They are required for a Windows boot OAT with
quick code and must resolve inside an R segment. Both open modes validate the
pair and section; a validation-only open does not register it.

Validate complete dynamic/string/symbol/hash ranges, exact entry sizes, bounded
counts, in-range NUL termination, bucket/chain indexes and termination,
uniqueness, binding/type, and containment in the correct R/RX/RW segment.

The existing ART dynamic-symbol lookup remains the first implementation. A
new Windows descriptor or ELF note is not part of early bring-up.

### Version gates

The boot artifact transaction validates:

1. logical OAT metadata;
2. VDEX/ART image formats and cross-artifact checksums; and
3. the matching compiler/runtime build, Windows x64 quick ABI, and AOT unwind
   encoding through product staging and runtime metadata rather than a
   different ELF header.

Also validate compiler/runtime build, pointer size, ISA/features, boot class
path, image requirement, compiler filter, and class-loader context. Unknown
versions or flags reject; they are never guessed.

The ELF header alone does not distinguish a Windows x86-64 OAT from a Linux
x86-64 OAT. Early bring-up therefore loads only the boot set produced and
staged by the Windows product target and paired through the existing image/OAT
checksums. It does not claim to diagnose every incorrectly staged cross-OS
artifact from ELF identity.

## Windows mapping design

### Page-size-agnostic ELF versus Windows file views

Windows protects committed pages at ordinary page boundaries but requires
file-view offsets and bases to satisfy the allocation granularity, normally
64 KiB. ART retains `ART_PAGE_SIZE_AGNOSTIC=1`. The selected target artifact
alignment is 16 KiB on Linux and 64 KiB on Windows. Consequently a
Windows `boot.oat` uses `PT_LOAD.p_align == 0x10000`, while the Linux writer
continues to emit `0x4000` byte-for-byte as before.

These constants describe different things and must no longer be aliases on
all targets:

| Quantity | Linux | Windows |
|---|---:|---:|
| Runtime/OS page | 4 or 16 KiB | 4 KiB |
| `kMaxPageSize` OS-page bound | 16 KiB | keep 16 KiB |
| Allocation/artifact granularity | 16 KiB | 64 KiB |
| `kElfSegmentAlignment` | 16 KiB | 64 KiB |
| `ART_PAGE_SIZE_AGNOSTIC` | enabled | enabled |

`kMaxPageSize` is currently 16 KiB whenever `ART_PAGE_SIZE_AGNOSTIC` is
enabled, and `globals.h` aliases `kElfSegmentAlignment` to it. A direct
Windows-only increase to 64 KiB is the wrong implementation because
`kMaxPageSize` is not just an ELF-layout constant. Its current uses are:

- the upper bound checked against the detected runtime page in `MemMap`;
- GC/allocator sizing for the debug mark stack, rosalloc's dedicated-run
  storage, and the large-object bitmap test matrix;
- the maximum-PMD calculation used to statically validate the preferred heap
  base; at 64 KiB it becomes 512 MiB and the current 32-MiB base fails the
  assertion;
- the mark-compact dirty-card mask; 64 KiB contains 64 cards at the current
  1-KiB card size, which reaches the width of a 64-bit `size_t`; and
- test-only ZIP-entry alignment in `dex2oat_environment_test.h`.

The minimal production change is therefore to introduce a target artifact
alignment (or make `kElfSegmentAlignment` target-specific): 16 KiB for
Linux/Android and 64 KiB for Windows. Windows retains the existing
`kMaxPageSize` bound because its OS page is 4 KiB. This keeps the change scoped
to ELF/image layout instead of perturbing unrelated GC and allocator limits.

The current Windows `MemMap` file path cannot map a file view over an occupied
`VirtualAlloc` reservation. Making ELF offsets 64-KiB aligned satisfies file
view congruence but still cannot replace a committed reservation with a file
view. OAT-1 avoids that ownership mismatch by copying into the existing
private allocation.

The affected surface is narrower than a general loader rewrite, and the
implementation should not assume otherwise. `ElfFileImpl<ElfTypes>::Load()`
performs exactly three mapping operations: one `MemMap::MapAnonymous()`
`PROT_NONE` whole-span reservation, one `MemMap::MapFileAtAddress(...,
reuse=true)` per `PT_LOAD` with `p_filesz != 0`, and one
`MemMap::MapAnonymous(..., reuse=true)` per zero-fill tail. The Windows
anonymous backend already implements the reuse case: when `MAP_FIXED` names an
address whose `VirtualQuery` state is not `MEM_FREE`, it walks the requested
range, requires one common `AllocationBase`, applies `VirtualProtect()`, and
returns without creating a second reservation. The whole-span reservation and
the zero-fill tails therefore work on Windows today. Only the file-backed
segment call is unrepresentable, so the private-copy helper replaces one
operation rather than reimplementing segment mapping.

The Windows startup/profile gate records `GetSystemInfo()` and requires a
4-KiB `dwPageSize` and 64-KiB `dwAllocationGranularity` for this initial
profile. An unexpected value rejects AOT rather than silently applying the
wrong rounding rule.

Do not mechanically port Bionic's:

```text
reserve complete PROT_NONE span
MAP_FIXED each PT_LOAD over the reservation
```

Only the private-copy implementation is in the early bring-up scope.

### OAT-1: private-copy correctness loader

OAT-1 uses an ART-owned private allocation and works with the Windows
64-KiB-aligned, page-size-agnostic ELF layout.

Load transaction:

1. Open OAT through the existing path/fd APIs and structurally validate ELF
   headers, program headers, checked file/virtual ranges, and alignment before
   granting executable permission.
2. Calculate the complete span and load bias with checked arithmetic. For a
   validation-only open (`executable=false`, no reservation), allocate an
   arbitrary private span. For the later executable boot open, consume the
   exact prefix of the caller's remaining boot-image reservation.
3. Keep `ElfFileImpl::Load()` in control of the reservation, segment walk,
   anonymous zero-fill tails, load bias, and gap layout. On Windows only,
   replace each unrepresentable file-backed
   `MapFileAtAddress(..., reuse=true)` with a private-copy equivalent: make
   the destination pages temporarily RW/NX, copy exactly `p_filesz` checked
   bytes into the already committed reservation, then restore the `prot`
   calculated by the existing loader. Thus executable code becomes RX only
   after copying, validation-only code remains R/NX, and writable data remains
   RW; flush copied executable ranges. Continue using the existing anonymous
   `reuse=true` path for `p_memsz - p_filesz`; it applies the segment
   protection within one `AllocationBase`, while the fresh whole-span Windows
   allocation supplies the required initial zero bytes.
4. Leave pages outside declared load ranges committed but `PAGE_NOACCESS`, and
   retain only the validated `oatdex` aperture as writable for the later
   handoff. Validate mapped-segment and dynamic-table containment and verify
   the final R/RX/RW/no-access map. Validation-only opens never register an
   unwind table.
5. Return the unpublished mapping owner through the existing
   `ComputeFields -> LoadVdex -> Setup` path. `ComputeFields()` performs the
   ART-facing anchor resolution. Populate and validate VDEX in the exact
   `oatdex` aperture and apply its final data protection.
6. Run a new fallible post-`Setup()` finalization hook that verifies the
   `.oat_unwind.windows` checksum, target machine, and encoding and, when
   present, validates `.oat_cfg.windows`. For an executable open only,
   construct and register one function table for that OAT component and
   perform structural lookup checks.
   Observation mode only records CFG policy. Explicit-target mode additionally
   requires the CFG section and completes all target-state updates before any
   code or entrypoint publication.
7. Complete image validation/relocation and publish generated-code ranges,
   roots, and method entrypoints only after the complete artifact set succeeds.

This scope is mandatory for both boot-image passes. `BootImageLayout` first
opens each OAT with `executable=false` and no reservation solely to validate
freshness, then `ImageSpace::Loader` opens it again with the exact reservation
for use. Dispatching private-copy only for `executable=true` would leave the
first pass on an unusable Windows ELF mapping backend.

OAT-1 avoids placeholder splitting, file-view alignment, fragmented ownership,
and replacement rollback.

#### Whole-span commit decision

| Allocation model | Advantages | Costs |
|---|---|---|
| Existing whole-span `MEM_RESERVE \| MEM_COMMIT` | No new `MemMap` state; directly consumes the boot reservation; one shared owner; simple protection and failure cleanup | Commit charge includes no-access gaps |
| Reserve span, commit declared ranges | Avoids commit charge for gaps | Requires new reserve/commit APIs, conflicts with the already committed boot reservation, and adds partial-state ownership and rollback |

OAT-1 selects whole-span commit. R, RX, BSS, and `oatdex` pages must all be
committed, so reserve-only primarily saves alignment gaps. Measure total boot
commit before considering a later optimization. The Windows 64-KiB segment
alignment can make these gaps larger than Linux's 16-KiB layout, so report
payload bytes, padding bytes, reserved span, committed span, and working set
separately. The validation-only mapping incurs the same temporary private-copy
cost but is discarded immediately after freshness validation.

The alignment gaps are not the dominant term and the measurement must not be
scoped to them. Windows `MemMap` allocates every anonymous mapping with
`MEM_RESERVE | MEM_COMMIT`, so the combined boot image plus OAT reservation is
fully charged the moment it is taken, before a single byte is populated. Boot
commit is therefore driven by the total reservation the image header requests,
of which the OAT's 64-KiB padding is a small fraction. The startup measurement
must report the image reservation, the OAT prefix consumed from it, and the
padding separately, so that a future reserve-then-commit optimization is
targeted at the term that actually dominates. This is also the reason the
whole-span decision is a bring-up simplification rather than a permanent
answer: on a memory-constrained host the boot reservation, not the OAT gap
policy, is what will force the question.

Costs:

- private code and copied VDEX consume per-process commit;
- startup performs reads and copies; and
- OAT is not automatically treated as a Windows module for unwind or tooling.

These costs are accepted for bring-up. Measure startup and memory before
expanding the scope.

### Deferred shared-view/OAT-2 work

OAT-2 is not part of the current plan. A future investigation may retain ELF
while aligning backing/protection groups to the Windows allocation granularity
for cross-process sharing. It would be a separately reviewed format/layout
change and must not complicate OAT-1 bring-up.

The selected writer already provides 64-KiB-congruent `PT_LOAD` offsets and
addresses on Windows. Shared-view OAT-2 would still require:

- independently viewable 64-KiB protection/ownership groups for R, RX,
  copy-on-write, BSS, and VDEX ranges, with any additional padding they need;
- one `VirtualAlloc2` placeholder reservation;
- exact placeholder splitting;
- `MapViewOfFile3(..., MEM_REPLACE_PLACEHOLDER, ...)` data/pagefile views;
- RX code with no writable executable alias;
- private/COW image-relro and BSS;
- an owner for all views and remaining placeholders; and
- idempotent reverse-order rollback.

No OAT-2 implementation or equivalence gate is required before boot OAT works.

### Boot placement and lifetime

Boot OAT must begin at the image-recorded address after the selected relocation
delta. Hints are never exact guarantees. Collision, fragmentation, overflow,
or a different returned address rejects image-backed AOT without touching
unrelated memory.

Application placement and duplicate logical instances are deferred. A
successfully published boot OAT remains mapped for the process lifetime;
rollback is required only for a failed, unpublished transaction and orderly
process teardown.

Every signed-32-bit RIP-relative/branch encoding and unsigned-32-bit OAT/
`CodeInfo` offset must remain representable. Generation and load reject rather
than truncate.

### VDEX and image mapping

OAT-1 preserves `oatdex` by copying/populating VDEX in that range. The returned
VDEX `MemMap` must be a slice that shares the OAT reservation owner, validate
the exact aperture size, and apply final read-only protection after copying.
This avoids both an adjacency refactor and the Windows exact-view problem.

Compressed ART images remain anonymous/decompressed. Uncompressed data and
bitmap pages may use exact data views where their relocation/protection
contract is satisfied.

## Windows generation lifecycle

Windows `dex2oat.exe` shall:

1. validate input DEX/JAR, boot class path, class-loader context, compiler
   filter, ISA/features, pointer size, and build identity;
2. compile with the accepted Windows x64 quick ABI;
3. emit `OatQuickMethodHeader`, `CodeInfo`, maps, method offsets, trampolines
   in their Windows `R15` Thread-base form, Windows unwind descriptions, and
   the exact indirect-entrypoint set;
4. build VDEX and checksums;
5. run the shared logical OAT writer;
6. run the existing `ElfBuilder` with the same Linux-identical ELF identity
   and the target-specific 64-KiB page-size-agnostic artifact alignment; do
   not add a Windows coat switch;
7. emit only restricted dynamic anchors and no ELF imports/relocations,
   including the two `oatunwindwindows` anchors and, when CFG metadata is
   enabled, the two `oatcfgwindows` anchors;
8. emit the bounded read-only `.oat_unwind.windows` section with
   `target_machine == IMAGE_FILE_MACHINE_AMD64`, one entry per unique code
   range, deliberate records for the trampolines, and deduplicated
   `UNWIND_INFO` bytes;
9. optionally emit `.oat_cfg.windows` with one sorted entry per unique exact
   indirect target and an independent version/checksum;
10. emit the matching boot ART image and cross-artifact checksums; and
11. stage `boot.art`, `boot.oat`, and `boot.vdex` in a Windows-target-specific
    product directory.

`ART_PAGE_SIZE_AGNOSTIC=1` remains enabled for Linux and Windows.
Generation tests require Linux `PT_LOAD.p_align == 0x4000` and Windows
`PT_LOAD.p_align == 0x10000`, and prove that the Windows alignment selection
does not change Linux output.

The ELF coat and header identity remain Linux-style, but the Windows artifact
has target-specific alignment, anchors, unwind data, and quick code.
Enabling unwind emission for AOT also applies the §7.9.3 `RBP` frame-anchor
rule to Windows AOT methods, so Windows boot OAT code for a given DEX input
differs from Linux boot OAT code by that anchor, its forced spill, and the
resulting `spill_mask`. This is an intended consequence of the frame rule, not
a coat difference: the shared header identity stays the same while alignment,
the Windows-only anchors, and quick code are target-selected. Generation tests
compare the common identity fields, never code bytes, between the targets.

The initial artifacts are trusted build outputs, not a mutable application
cache. Cache publication, replacement, and adversarial-input policy are
deferred.

The product plan must still select and test the initial boot topology: either
one `boot.art/oat/vdex` component or the complete multi-component layout
emitted by the Windows build. The loader must not silently support only the
first component when the staged image header declares more.

### Artifact location strings are part of the cross-artifact contract

The boot class path and dex locations recorded at generation time are compared
as **text** at load time, so on Windows they are a first-class part of the
artifact contract and not a packaging detail.

`dex2oat` stores the boot class path in the `OatHeader` key/value store under
`kBootClassPathKey`, joined with `':'`. `ImageSpace` then rebuilds the expected
string with `Join(boot_class_path_locations_, ':')` and requires byte equality,
or, in the dependency case, requires the stored string to be an exact
`':'`-delimited prefix of the runtime locations through
`CheckAndCountBCPComponents()`. Neither path normalizes; neither is
case-insensitive.

Two consequences are Windows-specific and must be designed for explicitly.

1. **Spelling is load-bearing.** `C:\run\boot.jar`, `c:\run\boot.jar`,
   `C:/run/boot.jar`, and a relative `run\boot.jar` are the same file to every
   Win32 API and four different strings to this comparison. A generation and a
   runtime that disagree on drive-letter case, separator flavour, or
   absolute-versus-relative form will silently reject the boot image and fall
   back to imageless nterp/JIT. That failure looks exactly like "Windows AOT
   does not work" while every checksum matches, so it is the first thing to
   rule out during bring-up, not the last.
2. **One identity form must be pinned.** The product must pass the same exact
   boot-class-path and dex-location strings to generation and startup. A fixed
   installation may choose canonical absolute Windows paths; a relocatable
   package should instead choose stable product-logical locations through
   `--dex-location` and `-Xbootclasspath-locations`. Do not bake an absolute
   build/staging directory into a relocatable artifact, and do not case-fold or
   normalize only one side. Gate the chosen identity with deliberate separator,
   drive-case, and absolute/relative mismatches and require an explicit
   diagnosed rejection. [win32_filesystem.md](win32_filesystem.md) governs
   Win32 API paths, but these OAT identity strings need their own product rule.

The same reasoning applies to the `-Ximage:` location. Windows resolution of a
default boot image location currently runs through the `ANDROID_ROOT` path in
`file_utils.cc`, which requires that variable to be set and produces
APEX-shaped subdirectories. The product must state whether Windows staging
mirrors that layout or whether the launcher always passes an explicit
`-Ximage:` path; leaving it implicit reintroduces the same string-identity
problem at a different layer.

### Loading an image is a distinct runtime bring-up, not just OAT loading

Every accepted Windows gate to date — W-013 heap closure, W-025 JIT closure,
W-010/W-014 fault and stack acceptance, the whole W-004 catalog — ran
**imageless**. Publishing a boot OAT necessarily also publishes `boot.art`, and
that is the first time a large body of Windows runtime code executes at all:
the image space as a GC continuous space, image relocation, the interned-string
and class tables, `.data.img.rel.ro` sealing, and the boot-image method arrays.
None of it is exercised by the current product.

This deserves an explicit sub-milestone and failure-mode analysis. Ordinary
missing, version, checksum, location, mapping, and relocation failures must be
returned by `ImageSpace::LoadBootImage()` and select imageless fallback before
publication. `Heap::VerifyBootImagesContiguity()` also contains fatal
`CHECK_EQ`/`CHECK_GT` invariants over image begin, OAT begin, and
`RoundUp(GetImageSize(), kElfSegmentAlignment)`. Those post-load internal
invariants need not be converted into recoverable hostile-input checks for the
trusted bring-up scope, but native negative tests must show that expected
compatibility failures do not reach them. The fallback promise applies to
ordinary fallible validation; a violated accepted-layout invariant remains a
runtime abort.

Note also that `kElfSegmentAlignment` is not confined to the ELF writer.
Selecting 64 KiB for Windows changes `ImageWriter`, `ImageHeader`,
`ImageSpace`, `runtime_image.cc`, and the `Heap` contiguity arithmetic above,
so the boot **image** layout is target-specific for the same reason the OAT
layout is. Windows and Linux boot artifacts are consequently not
interchangeable at the layout level, independently of their checksums.

## Loader components and ownership

Keep responsibilities separate:

1. Existing `ElfOatFile`/`ElfFile`: ELF parsing, loaded-span calculation,
   dynamic anchors, path/fd inputs, and the ART-facing owner.
2. A narrow Windows OAT file-segment helper: checked byte population inside
   the reservation already created by `ElfFileImpl::Load()`, temporary RW/NX
   copy protection, restoration of the loader-computed protection, and cache
   flush. Existing anonymous mapping code retains reservation consumption,
   zero-fill-tail, gap, load-bias, and exact-address semantics; the surrounding
   transaction owns the allocation and pre-publication rollback.
3. Existing `OatFileBase`: OAT anchor requirements, dex, BSS, VDEX, image, and
   class-loader semantics.
4. A Windows VDEX reuse helper: copy into `oatdex` and return a `MemMap` slice
   sharing the OAT allocation owner.
5. `WindowsAotUnwindRegistry`: `.oat_unwind.windows` validation, one multi-entry
   `RtlAddFunctionTable`/`RtlDeleteFunctionTable` lifetime per OAT component,
   and structural lookup proof.
6. `WindowsAotCfgManager`: `.oat_cfg.windows` validation, process-policy
   observation, and the separately gated explicit target-state transaction.
   It does not own a fictitious CFG registration handle; CFG state belongs to
   the virtual memory.
7. Existing generated-code registry: fault/stack readers and publication
   ordering shared with nterp/JIT.

Do not hide the OAT mapper behind general POSIX `mmap` emulation. One explicit
transaction owner covers the private-copy allocation and all of its logical
slices.

## Upstream-thin code-change plan

### Reuse shape

The current `ElfOatFile` path already opens path and fd inputs, parses the ELF,
calculates its load span, resolves dynamic symbols, consumes an ART
reservation, and enters `ComputeFields -> LoadVdex -> Setup`. Its POSIX-style
segment replacement is the part that does not work on Windows.

The first implementation shall therefore:

1. Select `ElfOatFile` for both Windows validation-only and executable boot OAT
   opens instead of trying to make Windows `dlopen` consume the ELF.
2. Add a Windows-only private-copy mapping mode below that path, preferably as
   a narrow helper invoked by `ElfFileImpl::Load()` rather than a fork of
   `OatFileBase` or a second ELF parser.
3. Preserve the existing path and fd open logic and dynamic-symbol lookup.
4. For validation-only opens, allocate a disposable private span at any
   suitable address and keep it NX. For executable opens, consume the exact
   caller reservation prefix. In both cases expose the same base, segment,
   BSS, and `oatdex` addresses expected by `ElfOatFile`.
5. Keep `OatFileBase::Setup()`, dex/BSS interpretation, and public `OatFile`
   APIs unchanged. `oat_file.h` gains only internal unwind-bound storage/access
   needed by finalization. `ComputeFields()` takes one additive change:
   resolving the two `oatunwindwindows` anchors alongside the anchors it already
   resolves, using the same optional-section idiom. This is the one place that
   knows the mapped anchor addresses, so resolving them elsewhere would mean
   duplicating its symbol lookup. The addition is target-neutral and inert on
   Linux and Android, where the section is absent and both pointers stay null.
6. Keep Android, Linux-host, and Fuchsia behavior unchanged outside obvious
   `ART_TARGET_WINDOWS` mapping/finalization blocks.

If a prototype proves that existing `ElfFile` ownership cannot express the
private allocation without invasive changes, an isolated Windows OAT loader
may be reconsidered. That is a fallback, not the starting assumption.

### VDEX handoff without widening `OatFile`

There is one necessary adjacent Windows change. The ELF `.dex` section is
`SHT_NOBITS`; Android first obtains zero pages from Bionic and then replaces
them with VDEX using `mmap(MAP_FIXED)`. A Windows OAT-1 private allocation
cannot be replaced in-place by `MapViewOfFileEx()`.

Preserve the existing `OatFileBase::LoadVdex()` call and `oatdex` contract.
Add a Windows-private-copy reuse path in `VdexFile::OpenAtAddress()` backed by
a narrowly named Windows `MemMap` helper. When `mmap_reuse=true` identifies a
validated subrange of the OAT private allocation, copy the VDEX file bytes
into that writable range, validate them there, apply the final data
protection, and return a `MemMap` sharing the allocation owner. Reject a
partial range, misalignment, size disagreement, or a range not owned by the
current OAT transaction.

This keeps `oat_file.cc` unaware of the Windows copy mechanism and preserves
the upstream order `ComputeFields -> LoadVdex -> Setup`.

### AOT unwind transport

The current Windows unwind support is JIT-only: optimizing and JNI compilation
enable the Windows x64 unwind builder only when `IsJitCompiler()` is true, and
the JIT code cache owns registration. Boot AOT therefore needs an explicit
compiler-to-runtime transport; loader registration alone is insufficient.

The implementation plan must carry, without reusing ELF CFI ambiguously:

1. per-method and JNI `UNWIND_INFO` from the Windows x64 assembler through
   `CompiledCodeStorage`/`CompiledMethod`;
2. fixed unwind descriptions for all emitted OAT trampolines/runtime stubs;
3. unique final code offsets from `OatWriter`, accounting for deduplicated
   compiled code;
4. a bounded read-only loadable table containing `RUNTIME_FUNCTION` records
   and their unwind bytes; and
5. a discoverable OAT range or anchor that the Windows runtime validates and
   registers with `RtlAddFunctionTable` before publication.

The serialized table and `CompiledMethod` API extension are specified in
"AOT unwind format and transport" below. Representative managed, JNI,
trampoline, exception, and stack-walk paths must be covered; a single
catch-all or fabricated unwind record is not acceptable.

## AOT unwind format and transport

This section closes the transport design item. It fixes the compiler
enablement rule, the `CompiledMethod` extension, the stub coverage set, the
serialized OAT section, the anchors, and the runtime registration contract.
`win32_faults_and_stacks.md` §7.9 remains authoritative for the frame rule,
unwind-byte encoding, and the native XMM boundary; AOT reuses those decisions
and does not restate them differently.

### Compiler enablement

Windows x64 unwind emission is currently gated on `IsJitCompiler()` in three
places: `code_generator_x86_64.cc` (which also forces the `RBP` anchor into the
allocated callee-save set), `jni_compiler.cc`, and the validity rejections in
`optimizing_compiler.cc`. AOT replaces that gate with a target-and-ISA rule.

| Condition | Emit unwind info |
|---|---:|
| Windows host or `ART_TARGET_WINDOWS`, `kX86_64`, JIT | yes, unchanged |
| Windows host or `ART_TARGET_WINDOWS`, `kX86_64`, AOT | yes, new |
| Non-Windows target, any compiler | no |
| Windows target, non-x86-64 ISA | no |

The replacement predicate is a single compiler-options helper, so the three
call sites stay in sync:

```text
bool CompilerOptions::EmitWindowsX64UnwindInfo() const {
  // Windows-only, x86-64-only; no IsJitCompiler() term.
#if defined(_WIN32) || defined(ART_TARGET_WINDOWS)
  return GetInstructionSet() == InstructionSet::kX86_64;
#else
  return false;
#endif
}
```

The helper must preserve the semantics of the three existing gates.
`code_generator_x86_64.cc`, `jni_compiler.cc`, and `optimizing_compiler.cc` all
use `#if defined(_WIN32) || defined(ART_TARGET_WINDOWS)`, whereas
`globals.h`'s `kIsTargetWindows` is true only under `ART_TARGET_WINDOWS` and is
defined `false` for every host build, including a Windows host build. Writing
the predicate as `kIsTargetWindows && ...` would therefore narrow the condition
and silently disable JIT unwind emission on a Windows-host (non-`ART_TARGET`)
build, contradicting row 1 of the table above and defeating the "three call
sites stay in sync" property the helper exists to provide. The shown
compile-time `#if`, or a new common constexpr with exactly the same host-or-
target meaning, is valid; `kIsTargetWindows` alone is not.

Either spelling is a build-time property of the binary being compiled, not a
property of a requested output target: ART has no target-OS field in
`CompilerOptions`, only `GetInstructionSet()`. The predicate is therefore correct
only because Windows boot artifacts are generated by a native Windows
`dex2oat.exe` built with `ART_TARGET_WINDOWS`, which this design already
requires. A Linux-hosted `dex2oat` cross-generating a Windows OAT would silently
evaluate the predicate false and emit an artifact with no unwind data — which the
writer's own "nonempty frame with no bytes" rejection would then have to catch.
Two consequences follow and must not be lost: Linux-hosted cross *generation* of
Windows boot artifacts is out of scope (unlike cross *building* of the Windows
binaries, which is supported and exercised in CI), and adding a real target-OS
option to `CompilerOptions` is the change to make if that ever becomes a goal.

Consequences that must be accepted deliberately:

1. The `RBP` frame anchor and its forced spill now apply to Windows AOT
   methods, not only JIT methods. This is required: §7.9.2 shows a fixed-RSP
   record is insufficient for the ordinary optimizing body, and the anchor
   rule is the selected answer. It costs one reserved register in Windows AOT
   code and makes Windows boot OAT code differ from Linux boot OAT code for
   the same DEX input. That divergence is expected and is not a bug.
2. Windows AOT `spill_mask` values therefore always contain `RBP`. Stack maps,
   frame sizes, and `OatQuickMethodHeader` semantics are unchanged.
3. Invalid or missing metadata from an enabled compilation must fail the
   `dex2oat` run, not fall back per method: a per-method fallback would leave an
   executable OAT frame with no unwind record. The rejection sites and their
   failure semantics are specified under "`CompiledMethod` extension" below.

Linux and Android AOT output remains byte-for-byte unchanged, because the
predicate is false for every non-Windows target.

### `CompiledMethod` extension

`CompiledCodeStorage::CreateCompiledMethod()` is the only path from the
compiler to `dex2oat`, and `CompiledMethod` is opaque to the compiler. Add one
optional array, parallel to the existing `cfi_info` array, and do not overload
CFI:

```text
CompiledCodeStorage::CreateCompiledMethod(
    instruction_set, code, stack_map, cfi,
    windows_x64_unwind_info,   // new: ArrayRef<const uint8_t>, may be empty
    patches, is_intrinsic)

CompiledMethod::GetWindowsX64UnwindInfo() -> ArrayRef<const uint8_t>
```

Storage follows the `cfi_info` pattern exactly, which keeps the change
mechanical:

- a `const LengthPrefixedArray<uint8_t>* const windows_x64_unwind_info_` member
  on `CompiledMethod`, beside `cfi_info_`;
- `CompiledMethodStorage::DeduplicateWindowsX64UnwindInfo()` delegating to
  `AllocateOrDeduplicateArray(unwind_info, &dedupe_windows_x64_unwind_info_)`,
  with `ReleaseWindowsX64UnwindInfo()` delegating to
  `ReleaseArrayIfNotDeduplicated()`, mirroring `DeduplicateCFIInfo()` and
  `ReleaseCFIInfo()`;
- the new `ArrayRef<const uint8_t>` threaded through the `CompiledMethod`
  constructor, `SwapAllocCompiledMethod()`, and the destructor's release call.

Deduplicating the bytes is safe because every offset inside `UNWIND_INFO` is
prologue-relative rather than image-relative, so a blob is position-independent
and two methods with the same frame shape can share one. This is the same reason
CFI dedups, and identical frame shapes are common enough that it matters for
boot-image size.

The JNI path already carries the bytes in `JniCompiledMethod`; `dex2oat`'s JNI
compilation passes `jni_compiled_method.GetWindowsX64UnwindInfo()` into the
same new parameter.

There is no whole-method dedup to extend: `CompiledCode::operator==` compares
only the quick-code bytes and currently has no callers, so it must not be
treated as a dedup hook or relied on for correctness here. Dedup happens
per-array in `CompiledMethodStorage` and, for code offsets, in the writer. The
invariant that keeps that safe is one-directional and worth stating plainly:
identical code bytes imply an identical prologue and therefore identical unwind
bytes, so sharing a code range can never merge two different frame shapes. The
converse does not hold — two methods may share unwind bytes while keeping
distinct code — which is exactly why unwind blobs are interned separately from
code and referenced by offset.

Emptiness is where a silent failure would hide, so the rule is explicit. An
empty array is legal only when the predicate is false, or for a method whose
frame is provably empty. Because the predicate now forces the `RBP` anchor and
its spill, an ordinary managed method on Windows x64 cannot have an empty frame,
so an empty array from an enabled compilation is a bug, not a leaf. `dex2oat`
must reject it and fail the run rather than emit a function without unwind data.

The AOT paths have no such check today. `OptimizingCompiler::JitCompile()`
holds both existing rejections — `!jni_compiled_method.IsWindowsX64UnwindInfoValid()`
for JNI, and the `IsWindowsX64UnwindInfoValid()`/empty-but-enabled pair for
managed code — and both return `false` to skip JIT compilation. Neither
`Compile()` (through `Emit()`) nor the AOT `JniCompile()` inspects the assembler
state at all. The equivalent checks must be added at those two AOT sites, with
the opposite failure action: `JitCompile()` can decline a method and leave the
interpreter to run it, whereas AOT has already committed to emitting executable
code, so the run must fail.

### Trampoline and runtime-stub coverage

`OatWriter::InitOatCode()` emits seven trampolines through `DO_TRAMPOLINE`.
On x86-64 each one is a single Thread-relative indirect `jmp` followed by
`int3` — it allocates no stack, saves no register, and never returns. Such a
function is a leaf with a zero-size prologue. Windows can unwind a leaf without
a function-table entry. This design nevertheless emits a zero-prologue record
for uniform, explicit coverage and lookup tests; it is a deliberate ART policy,
not a Windows ABI requirement:

| OAT code range | Shape | Record |
|---|---|---|
| The seven `DO_TRAMPOLINE` stubs | tail `jmp` through the Thread base, no frame | one shared leaf `UNWIND_INFO`: version 1, flags 0, prologue size 0, zero unwind codes, no frame register |
| Quick-code methods | optimizing frame with the `RBP` anchor | per-method bytes from the assembler |
| JNI stubs from `dex2oat` | normal/FastNative use the anchor; CriticalNative is fixed-RSP | per-method bytes from the JNI compiler |
| `x86` relative-patcher thunks | none exist for x86-64 (`WriteThunks()` writes nothing) | not applicable; assert the emitted thunk size is zero |

Every trampoline record may share one deduplicated `UNWIND_INFO` blob; they
still need distinct `RUNTIME_FUNCTION` entries because their code ranges
differ. The writer must emit them from the same offsets it already records in
`OatHeader`, so a trampoline entry cannot drift from the code it describes.

`art_quick_*` assembly entrypoints, the invoke/OSR boundary stubs, and nterp
live in `art.dll`, not in OAT. They are PE functions covered by the linker's
static `.pdata`/`.xdata` and by the existing §7.10 static OSR work. The OAT
table must not attempt to describe them, and its validation must reject any
record whose range falls outside the OAT RX segments.

#### Trampoline Thread-base selection is already target-aware

`compiler/trampolines/trampoline_compiler.cc` is intentionally shared and its
x86-64 source expression looks Linux-specific:

```text
// All x86 trampolines call via the Thread* held in gs.
__ gs()->jmp(x86_64::Address::ThreadOffsetAddr(offset));
__ int3();
```

That expression is already target-aware below the call site. On Linux,
`X86_64Assembler::gs()` emits the `0x65` segment override and
`Address::ThreadOffsetAddr()` produces the absolute displacement. Under
`_WIN32` or `ART_TARGET_WINDOWS`, `gs()` deliberately emits no prefix and
`ThreadOffsetAddr()` produces `Address(R15, offset)`. The resulting Windows
stub is therefore an `R15`-relative indirect `jmp` followed by `int3`; it does
not read the TEB. No new trampoline producer or regeneration fix is required.

Keep a structural regression gate because the shared spelling is easy to
misread and either helper could drift: disassemble all seven emitted
trampolines and require a `GS`-relative jump on Linux and an `R15`-relative jump
with no `GS` prefix on Windows. Also keep the leaf-shape assertion so the shared
zero-prologue `UNWIND_INFO` remains correct. This is verification of an existing
port mechanism, not a blocker ahead of loader work.

### Serialized table

Add one read-only loadable section, `.oat_unwind.windows`, emitted by `ElfBuilder`
after `.data.img.rel.ro` and before the optional `.oat_cfg.windows` and `.bss`.
It is never executable and never writable after load. Two placements that look
more natural are both wrong, and the existing assertions are what rule them
out:

- **Not between `.rodata` and `.text`.** `dex2oat.cc` passes
  `GetOatHeader().GetExecutableOffset()` as the `rodata_size` argument to
  `PrepareDynamicSection()`, so `.text` must begin exactly at
  `oatdata + executable_offset`. Inserting anything between them shifts `.text`
  and invalidates every entrypoint offset in `OatHeader`.
- **Not between `.text` and `.data.img.rel.ro`.** `WriteDataImgRelRo()` asserts
  `DCHECK_EQ(GetOffsetFromOatDataAlignedToFile(code_end, kElfSegmentAlignment),
  data_img_rel_ro_start_)` and derives its own alignment-padding stat from that
  difference, so `.data.img.rel.ro` is required to be the first thing after the
  page-aligned end of code.

Placing Windows metadata last among the `PROGBITS` sections keeps both
invariants untouched. Unwind adds one `WriteState`
(`kWriteWindowsUnwind`) after `kWriteDataImgRelRo`, with a
`WriteWindowsUnwind()` that mirrors `WriteDataImgRelRo()`:
`ChecksumUpdatingOutputStream`, then a `CheckOatSize()` call. Since the whole
file is one ELF image, offsets relative to `oatdata` stay valid regardless of
placement, and the section sits beyond `oatlastword` alongside `.bss` and
`.dex`, so nothing that parses the OAT code range is affected. Both Windows
metadata sections must precede `.bss`, which is `SHT_NOBITS` and contributes no
file bytes.

The metadata group costs at most one segment-alignment gap.
`Section::AddSection()` raises the effective alignment of a section whose
`phdr_flags_` differ from the previous section's to `kElfSegmentAlignment`, and
`MakeProgramHeaders()` merges adjacent `PT_LOAD`s only when flags match and
neither is `.bss`-like. Following `PF_R|PF_W` data with `PF_R` starts a new
segment; when `.data.img.rel.ro` is absent the predecessor is `PF_R|PF_X` text
and a new segment starts anyway. `.oat_cfg.windows` declares only 4-byte
alignment; when it follows unwind it remains in the same R segment, and when
unwind is absent `AddSection()` raises CFG to the segment alignment. No
explicit `phdr_flags_` assignment is needed, since `PF_R` is already the
default.

The section is self-describing and fully validated before use:

```text
OatWindowsUnwindHeader {     // 48 bytes, 4-byte aligned
  uint32_t magic;            // 'o','u','w','\n'
  uint32_t version;          // 1; independent of shared OAT version
  uint32_t header_size;      // 48 in version 1
  uint32_t target_machine;   // zero-extended PE/COFF Machine value;
                             // IMAGE_FILE_MACHINE_AMD64 in version 1
  uint32_t entry_size;       // 12 for the version-1 x86_64 entry format
  uint32_t entry_count;
  uint32_t entries_offset;   // section-relative; 48 in version 1
  uint32_t unwind_offset;    // section-relative, 4-byte aligned
  uint32_t unwind_size;
  uint32_t code_begin;       // oatexec range, relative to oatdata
  uint32_t code_end;         // exclusive; both bound every entry
  uint32_t checksum;         // Adler-32 of entire section; this field is zero
                             // while calculating
}
OatWindowsX64UnwindEntry[entry_count] { // 12 bytes, sorted by begin_offset
  uint32_t begin_offset;                 // relative to oatdata, inclusive
  uint32_t end_offset;                   // relative to oatdata, exclusive
  uint32_t unwind_info_offset;           // relative to oatdata, 4-byte aligned
}
uint8_t unwind_info_blobs[unwind_size];   // deduplicated UNWIND_INFO bytes
```

Version 1 fixes `header_size`, `entry_size`, and `entries_offset` to the values
above and accepts only `target_machine == IMAGE_FILE_MACHINE_AMD64`; the upper
16 bits must be zero. The generic section and anchor names reserve one Windows
transport namespace; they do not imply that an x86-64 entry array can be parsed
as ARM64 or ARM64EC. A later machine may define a new section-local version or
machine-selected entry encoding without changing the shared OAT version or
proliferating ELF section names.

Design points, each chosen against a rejected alternative:

- **Serialization is explicit little-endian, not a native struct dump.** Write
  each `uint32_t` field at its specified offset, assert the 48-byte header and
  12-byte entry sizes in tests, and parse with checked reads. Compiler padding,
  Windows SDK packing, and host alignment are not part of the file format.
- **Offsets are relative to `oatdata`, not to the section or the ELF base.**
  The runtime registers `RtlAddFunctionTable()` with `oatdata` as
  `BaseAddress`, which mirrors the JIT rule in §7.9.6 where the primary
  mapping start is the base. This keeps every field an unsigned 32-bit value
  that the runtime can validate against the known `oatdata`/`oatlastword`
  span without knowing the ELF load bias. The 32-bit fit needs no new
  assertion: `OatHeader` already stores `executable_offset_` and every
  trampoline offset as a `uint32_t` from `oatdata`, so an OAT whose code lies
  beyond 4 GiB of `oatdata` is already unrepresentable. Unlike the JIT case in
  §7.9.6, this does not depend on where the artifact maps — only on its own
  size. That matters because OAT files load with `low_4gb=false`
  (`oat_file_manager.cc`, `oat_file_assistant.cc`, and the OAT branch of
  `image_space.cc`), unlike the JIT region and unlike the ART image heap, which
  request low-4-GiB placement for compressed references. A base-relative table
  is therefore the only correct choice here; an absolute-address table would
  need a placement guarantee the OAT loader does not make.
- **The file layout is not `RUNTIME_FUNCTION`.** A `RUNTIME_FUNCTION` is a
  Windows SDK type, and the ART writer must stay SDK-independent for Linux
  cross builds. `OatWindowsX64UnwindEntry` is the same three 32-bit fields in
  the same order as the x86-64 SDK record, so the runtime can build the SDK
  array by a checked field-by-field copy rather than a reinterpret cast.
  Nothing depends on the layouts being identical.
- **Entries are sorted and non-overlapping in the file.** Windows requires a
  sorted table for binary search. Sorting at write time makes the runtime
  check an O(n) verification rather than a sort, and a sort failure is a
  writer bug the loader should surface rather than repair.
- **The unwind blobs are deduplicated but the entries are not.** Every code
  range gets exactly one entry; identical frame shapes share one blob.
- **The section has its own checksum.** The writer computes Adler-32 over the
  complete serialized `.oat_unwind.windows` section while treating the checksum
  field as zero. The loader repeats exactly that operation before following
  offsets or parsing any `UNWIND_INFO`. Adler-32 reuses ART's existing checksum
  convention and provides an accidental-corruption gate; it is not a security
  or authenticity mechanism.
- **The table is one registration, not one per method.** The JIT uses one
  one-entry table per allocation because allocations come and go. Boot OAT is
  process-lifetime state, so one multi-entry registration per OAT component is
  both cheaper and simpler to unregister. In a multi-component boot set, only
  the primary OAT contributes the seven header trampolines; every component
  contributes its own method/JNI entries and owns its own registration. A
  single-component boot set remains the simplest first milestone.

Two new dynamic anchors make the section discoverable through the existing
`ElfFile::FindDynamicSymbolAddress()` path, extending `DynamicSymbol` and
keeping the restricted allow-list closed:

```text
oatunwindwindows, oatunwindwindowslastword
```

The names preserve ART's lowercase anchor namespace and match the generic
Windows transport; `target_machine` identifies the encoded machine. Append
`kOatUnwindWindows` and `kOatUnwindWindowsLastWord` to
`ElfBuilder::DynamicSymbol` and add their names to
`GetDynamicSymbolName()`.

Do not globally increase the dynamic-section reservation. A global
`kDynamicSymbolCount` increase changes reserved `.dynstr`/`.dynsym`/`.hash`
capacity and can shift Linux/Android layout even when no extra symbol is
emitted. Reserve capacity for the two names only when Windows x64 boot unwind
output is enabled; the emitted dynsym count and SysV hash dimensions continue
to describe the actual emitted symbols. `kDynamicEntriesCount` is unrelated
and does not change because these are `.dynsym`, not `.dynamic`, entries.
Concretely, preserve a base-symbol count ending at `kOatDexLastWord` and add
two to the reservation helper only for the Windows-unwind mode known when
`ElfWriterQuick::Start()` calls `ReserveSpaceForDynamicSection()`.

Two mechanical details make that instruction implementable rather than
aspirational.

- `kDynamicSymbolCount` is derived as `static_cast<size_t>(DynamicSymbol::kLast)
  + 1`, so merely appending enumerators changes the reserved capacity on every
  target. The new enumerators must be appended *after* `kLast`, with `kLast`
  left at `kOatDexLastWord`, and that invariant must be held by a
  `static_assert` on the base count plus a test that Linux OAT bytes are
  unchanged. Prose alone will not survive the next upstream symbol addition.
- The reservation is not a per-artifact decision. `ReserveSpaceForDynamicSection()`
  runs from `ElfWriterQuick::Start()`, long before `PrepareLayout()` has decided
  whether any unwind entries exist, and its result advances `virtual_address_`
  ahead of `.rodata`, so it fixes the address of everything that follows. The
  only input available at that point is the build-time Windows-x86-64 mode.
  Consequently a Windows OAT compiled with a filter that emits no quick code
  reserves two names it never uses. That is harmless — the reservation is
  checked with `CHECK_LE(virtual_address_, rodata_.GetAddress())`, not equality
  — but the design intent is "reserve whenever this is a Windows x86-64
  `dex2oat`", not "reserve whenever the section will exist", and the code should
  say so.

Any supported Windows boot load rejects quick code with no
`oatunwindwindows`, and rejects an anchor outside an R segment. The shared OAT
version remains `265\0`; the section header version and required-anchor check
gate this Windows-only extension without modifying Linux OAT semantics.

### Writer integration and dedup-safe offsets

The writer already assigns final code offsets and already deduplicates
identical compiled code, so two methods can share one code range. The unwind
table must key on the final code range, not on the method.

`CompiledMethodStorage::DeduplicateCode()` interns identical code bytes to a
single allocation. The writer's `CodeOffsetsKeyComparator` then compares the
quick-code pointer, VMap-table pointer, patches pointer, and intrinsic state;
it is not a quick-code-only comparator. Regardless of which equality path was
taken, the final visitor `deduped` result is authoritative for whether a fresh
code range was allocated. Under `--deduplicate-code=false` no code interning
happens, every method normally keeps a distinct pointer, and every fresh range
gets its own entry.

The visitor has a second, distinct dedup path: when `--debuggable` is set it
bypasses `dedupe_map_` entirely and instead reuses
`MultiOatRelativePatcher::GetOffset(method_ref)`, which is nonzero only when the
*same* `MethodReference` was already assigned an offset (duplicate definitions of
one method). Both paths converge on the same invariant the table needs, so the
rules below key on the visitor's `deduped` flag rather than on either mechanism:
`deduped == false` means this method owns a fresh code range and must contribute
an entry, and `deduped == true` means it shares an already-recorded range and
must not.

1. During `InitOatCodeDexFiles()`, when `InitCodeMethodVisitor` assigns a new
   offset (`deduped == false`), record a pending entry
   `(code_offset, code_size, unwind_bytes)`. When the visitor takes the
   deduplicated path, do not add a second entry; instead require that the
   method's unwind bytes are byte-identical to those already recorded for that
   offset, and fail the run if they are not. Interning makes this a pointer
   comparison in the common case, with a byte compare as the fallback.
   Identical code bytes imply an identical prologue and therefore an identical
   frame shape, so a mismatch means the transport itself is wrong and the run
   must not produce an artifact.
2. In `InitOatCode()`, add the seven trampoline entries from the offsets
   `DO_TRAMPOLINE` already computes, using the shared leaf blob. Use `offset`,
   not the `adjusted_offset` written into the header entrypoints, so the range
   matches the emitted bytes; this is the same distinction the macro already
   makes for `MethodDebugInfo::code_address`. `DO_TRAMPOLINE` runs only for
   `IsBootImage() && primary_oat_file_`, so a non-primary or app OAT
   contributes no trampoline entries and its table holds method entries only.
3. Still inside `PrepareLayout()`, after `InitOatCodeDexFiles()` has set
   `code_size_` and before `InitDataImgRelRoLayout()`, sort entries by
   `begin_offset`, assert no overlap and no zero-length range, intern the unwind
   blobs with 4-byte alignment, and finalize the serialized buffer. This slot is
   forced by the call order in `dex2oat.cc`: `PrepareLayout()` runs first and
   `ElfWriter::PrepareDynamicSection()` immediately after, so the section's size
   must already be known when the ELF layout is reserved. Expose it as
   `OatWriter::GetWindowsUnwindSize()` alongside the existing
   `GetCodeSize()` and `GetBssSize()` getters, and pass it as one more
   `PrepareDynamicSection()` argument through `ElfWriter`, `ElfWriterQuick`,
   and `ElfBuilder`. Because every code offset is final once
   `InitOatCodeDexFiles()` returns, the table is fully computable there;
   nothing later moves the ranges it describes.
4. Add `.oat_unwind.windows` to `ElfBuilder` as a `Section` member declared and
   constructed between `data_img_rel_ro_` and the optional CFG section and
   `bss_` — `SHT_PROGBITS`,
   `SHF_ALLOC` without `SHF_EXECINSTR`, `kElfSegmentAlignment` since it always
   opens a new segment — and call `AllocateVirtualMemory()` on it in
   `PrepareDynamicSection()` in that same position, because declaration order in
   `sections_` is what fixes segment layout. Follow the established
   conditional-add pattern: when the size is zero, emit neither the section nor
   its anchors, exactly as `.bss` and `.dex` do. Add the
   two anchors in `PrepareDynamicSection()` with `dynsym_.Add(..., STB_GLOBAL,
   STT_OBJECT)`, giving `oatunwindwindows` the section address and full size,
   and `oatunwindwindowslastword` the last four bytes with size 4, matching the
   existing `oatbss`/`oatbsslastword` pair.
5. Write the bytes from a new `OatWriter::WriteWindowsUnwind()` reached
   through a new `WriteState::kWriteWindowsUnwind` placed after
   `kWriteDataImgRelRo` and before `kWriteWindowsCfg`, so the buffer precedes
   optional CFG data and the header is finalized only after both.
   Mirror `WriteDataImgRelRo()`: wrap the stream in
   `ChecksumUpdatingOutputStream`, account the padding and payload in a
   `size_oat_unwind_windows_*` stat pair for the `DO_STAT` block, and finish with
   `CheckOatSize()`. In `dex2oat.cc`, add a size-guarded
   `StartWindowsUnwind()`/`EndWindowsUnwind()` pair on `ElfWriter` after
   the existing `.data.img.rel.ro` block and before the optional CFG block and
   `WriteHeader()`, matching how that block is itself guarded on
   `GetDataImgRelRoSize() != 0u`.

   The state transitions are the subtle part, because both preceding sections are
   optional and each currently jumps straight to `kWriteHeader` when empty.
   Route every such branch through the ordered metadata states instead:
   `WriteCode()` selects data-img-rel-ro, else unwind, else CFG, else header;
   `WriteDataImgRelRo()` selects unwind, else CFG, else header;
   `WriteWindowsUnwind()` selects CFG when present, else header; and
   `WriteWindowsCfg()` always advances to the header. Each
   branch that ends a section without a successor keeps its existing
   `CheckOatSize()` call, so the size assertion still runs exactly once on the
   final section.
6. Before writing, set the section checksum field to zero, calculate Adler-32
   over the finalized header, entries, alignment padding, and unwind blobs,
   then store the result. Feeding the serialized section through
   `ChecksumUpdatingOutputStream` may continue to include it in the ordinary
   generated OAT checksum.
7. Reject at write time rather than emit a broken table: an entry outside the
   `oatexec` range, a range that overlaps its neighbour, a blob that is not
   4-byte aligned, an entry count or section size that does not fit in 32
   bits, or any method with a nonempty frame and no bytes.

The ordinary OAT checksum is not the integrity gate for this section. The
runtime compares the stored OAT checksum with the value recorded in the image,
but does not recompute that checksum from mapped OAT bytes. The loader must
therefore recompute and compare the section-local checksum before parsing the
table. This is correctness validation for trusted bring-up artifacts, not
adversarial-input hardening.

### Runtime registration

`WindowsAotUnwindRegistry` mirrors the JIT registry's ownership shape but with
one multi-entry table per OAT component. It lives beside `jit_unwind_windows` in
`runtime/multiplatform/windows/`, keeps every Windows type out of common code,
and is owned by the Windows OAT mapping transaction rather than by
`JitCodeCache`.

Three properties are inherited from `WindowsX64JitUnwindRegistry` rather than
reinvented. It owns the `RUNTIME_FUNCTION` storage for as long as the table is
registered, because `RtlAddFunctionTable()` retains the caller's array rather
than copying it. It verifies its own registration with `RtlLookupFunctionEntry()`
and rolls back on any mismatch. It verifies deletion the way
`DeleteFunctionTableAndVerify()` does, by requiring a subsequent lookup on a
covered PC to return `nullptr`. The differences are that the AOT table is
registered once with `entry_count > 1`, its base address is the `oatdata`
mapping base instead of a JIT region base, and its entries are read from the
artifact instead of computed from live pointers — which is why every field must
be validated before it reaches the SDK call.

Registration happens in a new fallible post-`Setup()` finalization hook, after
final protections, `FlushInstructionCache`, `ComputeFields`, VDEX loading, and
logical OAT setup, but before any generated-code range or `ArtMethod`
entrypoint is published. Keeping it out of the raw mapping helper avoids
registering metadata for a mapping that later fails ordinary OAT/VDEX setup.
Validation-only opens parse/check the section but never register it.

The section bounds come from `OatFileBase::ComputeFields()`, which already
resolves every other anchor pair and is the only place that knows the mapped
addresses. Add `windows_unwind_begin_`/`windows_unwind_end_` there using the
established idiom: a null `oatunwindwindows` means no section and sets both to
null, a present `oatunwindwindows` with a missing
`oatunwindwindowslastword` is a hard error, and the end pointer is readjusted
with `+= sizeof(uint32_t)` because the `lastword` symbol addresses the final
four bytes rather than
one-past-the-end. That `+4` convention is why the writer gives
`oatunwindwindowslastword` size 4 at `address + size - 4`.

Registration then must, in order:

1. recompute the section-local Adler-32 with the checksum field treated as
   zero, compare it with the header, then validate magic, independent section
   version, fixed header/entry sizes, target machine, and every declared
   subrange;
2. validate `code_begin`/`code_end` against the mapped `oatexec` range
   resolved from the dynamic anchors;
3. validate each entry: `begin_offset < end_offset`, both inside the code
   range, entries sorted and non-overlapping, and `unwind_info_offset`
   4-byte aligned and inside the declared unwind-blob subrange after checked
   `oatdata`-relative address conversion;
4. validate each referenced `UNWIND_INFO`: version 1, no unsupported flags,
   a code count that fits the declared bytes, prologue size within 255,
   frame register and scaled offset within range, `UWOP_*` codes recognized,
   descending prologue offsets, correct 2-byte tail padding, and a chained or
   handler record only where it is itself in range and acyclic;
5. allocate the SDK `RUNTIME_FUNCTION` array in stable native storage, copy
   the three fields per entry with checked arithmetic, and keep the exact
   pointer for later deletion;
6. for executable opens, call
   `RtlAddFunctionTable(table, entry_count, oatdata_address)`; and
7. prove registration structurally with `RtlLookupFunctionEntry()` on one or
   more known entries, requiring the returned base and all three fields to
   match. Real managed-frame `RtlVirtualUnwind()` belongs in the native
   execution gate, not in loader registration.

An ordinary validation or registration failure fails the unpublished load. If
cleanup succeeds, the caller discards the transaction and continues imageless.
A successful boot keeps the table registered for process lifetime; teardown
unregisters before the shared mapping owner releases code or metadata.

If `RtlDeleteFunctionTable()` fails during rollback or teardown, ART aborts
with `LOG(FATAL)`/`CHECK`. It must not free the SDK table or release the code or
unwind mapping while Windows may still reference them. Elaborate recovery from
this invariant violation is deliberately not a bring-up blocker; unsafe
"continue imageless" behavior is forbidden for this one cleanup failure.

`GetRuntimeFunctionTableForRange()`-style lookups are not exposed to common
code. Windows stack walking already reaches AOT frames through the ordinary
`RtlLookupFunctionEntry()` path once the table is registered, and ART's own
walking uses the existing generated-code range.

### Unwind gates

These gates are additive to the required-gates list and are specific to the
transport:

- a `dex2oat` unit gate proving one entry per unique code range, shared
  trampoline blobs, and rejection of a nonempty frame with no bytes;
- a dedup gate: two methods compiled to identical code produce one entry;
- a writer gate: sorted, non-overlapping, in-range entries and a deterministic
  section-local checksum; flip one byte independently in the header, entry
  array, padding, and unwind blob and require both open modes to reject before
  registration;
- a layout gate, since the section's placement is what keeps the existing
  assertions true: `.text` still starts at `oatdata + executable_offset`,
  `data_img_rel_ro_start_` still equals the page-aligned end of code, and
  `.oat_unwind.windows` still precedes `.bss` — asserted with and without
  `.data.img.rel.ro` present, because the predecessor section and therefore the
  segment split differ between those two cases;
- a loader gate: each malformed-table class above rejects the load and falls
  back imageless, with no function table left registered;
- a native gate on Server 2025: `RtlLookupFunctionEntry()` resolves a
  representative quick, JNI, and trampoline PC, and `RtlVirtualUnwind()`
  restores the `RBP`-anchored frame from a boot-OAT method; and
- a native exception gate: a managed throw, a translated NPE, and a fatal dump
  each walk through boot-OAT frames with correct nonvolatile restoration.

## Windows CFG format and integration

CFG metadata is independent of unwind metadata. Unwind describes how to walk a
function after control has reached it; CFG identifies addresses that may be the
destination of an indirect call. A function-range start is not automatically
an indirect-call target, and a CFG target does not need a separate unwind
record. The writer collects and validates the two sets independently.

Use one architecture-neutral section name and anchor pair:

```text
.oat_cfg.windows
oatcfgwindows
oatcfgwindowslastword
```

Do not create `.win32`, `.win64`, or per-ISA CFG section names. The format is
generic and the header carries the standard PE/COFF machine value. The
`IMAGE_FILE_MACHINE_ARM64EC` value already distinguishes ARM64EC without a
new ART enum or section name. This naming decision does not claim ARM64,
ARM64EC, x86, or ARM32 OAT support; the initial executable profile remains
Windows x86-64.

### Serialized CFG target table

The section is an explicit little-endian byte format, never a native-struct or
Windows SDK dump:

```text
OatWindowsCfgHeader {         // 48 bytes, 4-byte aligned
  uint32_t magic;             // bytes 'o','c','f','g' (0x6766636f as LE u32)
  uint32_t version;           // 1; independent of the shared OAT version
  uint32_t header_size;       // 48 in version 1
  uint32_t target_machine;    // zero-extended PE/COFF Machine value;
                              // IMAGE_FILE_MACHINE_AMD64 in version 1
  uint32_t flags;             // kCompleteTargetSet must be set in version 1
  uint32_t entry_size;        // 8 in version 1
  uint32_t target_count;
  uint32_t targets_offset;    // section-relative; 48 in version 1
  uint32_t code_begin;        // oatdata-relative RX code bound, inclusive
  uint32_t code_end;          // oatdata-relative RX code bound, exclusive
  uint32_t checksum;          // Adler-32; this field is zero while calculating
  uint32_t reserved;          // zero in version 1
}

OatWindowsCfgTarget[target_count] { // 8 bytes, sorted by code_offset
  uint32_t code_offset;             // exact target, relative to oatdata
  uint32_t kind_flags;              // ART-owned diagnostic classification
}
```

Version 1 fixes `header_size`, `entry_size`, and `targets_offset` to the values
above and requires the section size to equal
`targets_offset + target_count * entry_size` under checked arithmetic. It
requires `target_count != 0`, `code_begin < code_end`, no unknown header or
entry flag bits, and no trailing data. The only version-1 header flag is:

```text
kCompleteTargetSet = 1u << 0
```

It asserts that the array is the complete set of indirect-callable addresses
the ART writer knows inside `[code_begin, code_end)`. Explicit-target mode
requires it; the writer always sets it when emitting version 1.

`target_machine` uses the standard PE/COFF `Machine` value described above.
The runtime requires the upper 16 bits to be zero, cross-checks the value
against the selected ART target/product identity, and rejects a mismatch.
Version 1 permits only `IMAGE_FILE_MACHINE_AMD64` in the initial Windows AOT
profile; accepting another standard value requires that machine's separately
reviewed OAT and native CFG gate.

Version-1 `kind_flags` are:

```text
1u << 0 = kQuickMethod
1u << 1 = kJniStub
1u << 2 = kBootTrampoline
1u << 3 = kIndirectCallableThunk
```

They are ART-owned diagnostics and may be ORed when deduplication gives one
address multiple roles. Never serialize `CFG_CALL_TARGET_*` SDK bits. The
runtime derives the Windows API flags itself and rejects every unknown
`kind_flags` bit.

The array contains sorted, unique, exact target offsets. Each offset is the
address Windows will see as callable after the target ISA's entrypoint
adjustment, expressed relative to `oatdata`, and must lie in both the declared
code range and an RX `PT_LOAD`. For the initial x86-64 profile the adjustment
is zero. Future tagged or adjusted ISAs must define how their callable pointer
is normalized to the instruction address accepted by the Windows CFG API as
part of that ISA's enablement gate; the loader must not guess.

Include:

- each unique compiled quick-method entrypoint, merging `kind_flags` for
  deduplicated code;
- each unique JNI stub entrypoint;
- the seven primary boot-OAT trampolines; and
- only architecture thunks that can genuinely be reached through an indirect
  call.

Exclude internal labels, exception/stack-map PCs, all instruction boundaries,
direct-branch-only relative-patcher thunks, unwind range starts that are not
callable entrypoints, and PE functions already owned by `art.dll`. An x86-64
relative patcher currently emits no thunks; assert that fact instead of adding
synthetic targets. The target list is intentionally finer than “all addresses
in every executable page.”

Like the unwind section, `.oat_cfg.windows` has its own accidental-corruption
gate. The writer serializes the complete section with `checksum` zero,
calculates Adler-32 over every byte, then stores the result. Both open modes
repeat that calculation before consuming array offsets. This does not change
shared OAT version `265\0`, does not rely on the image-recorded OAT checksum
being recomputed from mapped bytes, and is not an authenticity mechanism.

### Writer and ELF layout integration

Final CFG target addresses depend on final code offsets, deduplication,
trampoline placement, and any emitted architecture thunks. During code-layout
visitation, collect candidates in a map keyed by the final adjusted
`code_offset`; a duplicate merges only known `kind_flags`. Add the seven
trampoline candidates from the same final offsets used for the callable
`OatHeader` entrypoints, not from unwind range starts. Add a thunk only when
the relative patcher marks it indirect-callable. Sort and serialize only after
all of those offsets are final, then validate uniqueness, range containment,
32-bit fit, and completeness before exposing the section size to
`ElfWriter::PrepareDynamicSection()`.

Declare `.oat_cfg.windows` in `ElfBuilder` immediately after
`.oat_unwind.windows` and before `.bss`, as `SHT_PROGBITS`, `SHF_ALLOC`, `PF_R`,
and 4-byte aligned. If unwind is present, CFG follows it in the same R
`PT_LOAD`; if unwind is absent, `Section::AddSection()` raises the first R
section after RX/RW to `kElfSegmentAlignment`. Therefore the four required
layout combinations are:

```text
neither:      data-img-rel-ro? -> .bss
unwind only:  data-img-rel-ro? -> .oat_unwind.windows -> .bss
CFG only:     data-img-rel-ro? -> .oat_cfg.windows -> .bss
both:         data-img-rel-ro? -> .oat_unwind.windows
                                  -> .oat_cfg.windows -> .bss
```

In each case `.text` still begins at `oatdata + executable_offset`, optional
`.data.img.rel.ro` remains the first page-aligned region after code, and
`oatlastword` remains unchanged. Assign `oat_size_` only after both optional
metadata payloads; derive `bss_start_` afterward.

Add `WriteState::kWriteWindowsCfg` after `kWriteWindowsUnwind` and before
`kWriteHeader`. `WriteCode()` routes to data-img-rel-ro, unwind, CFG, or header
according to which payloads exist; data-img-rel-ro routes to unwind, CFG, or
header; unwind routes to CFG or header; CFG always routes to header. Add a
size-guarded `StartWindowsCfg()`/`EndWindowsCfg()` block and a
`WriteWindowsCfg()` using `ChecksumUpdatingOutputStream` and `CheckOatSize()`.
The conditional block, section, and emitted anchors exist only when the CFG
payload is nonempty. Dynamic-section *capacity* is different: it must be
chosen from the Windows metadata/writer mode already known at
`ElfWriterQuick::Start()`, before payload sizes are available.

Append `kOatCfgWindows` and `kOatCfgWindowsLastWord` to the restricted dynamic
symbol allow-list. The begin symbol covers the full section; the lastword
symbol names its final four bytes and the loader converts it to one-past-end
with the established `+ sizeof(uint32_t)` convention. Preserve the base
dynamic-symbol count through `kOatDexLastWord`. Keep new enum values after
`kLast`, so `kDynamicSymbolCount` remains the base count. The reservation
helper adds two-name capacity for the Windows-x86-64 unwind writer mode and
two-name capacity for a Windows CFG-capable writer mode, even if a particular
artifact later has an empty payload. `PrepareDynamicSection()` still emits
only symbols whose sections exist. Linux/Android select neither mode, so their
`.dynstr`, `.dynsym`, `.hash`, addresses, and bytes remain unchanged. Test
neither, unwind-only, CFG-only, and both, each with and without
`.data.img.rel.ro`, plus an enabled-mode/empty-payload case.

### Runtime validation and modes

`OatFileBase::ComputeFields()` resolves the optional CFG anchor pair under the
same rules as other begin/lastword pairs: both absent means no section; only
one present, an anchor outside an R segment, reversed bounds, or a section
shorter than the fixed header rejects the load. Validation then recomputes the
checksum and checks the fixed version-1 fields, target machine, known bits,
checked array size, sorted uniqueness, exact adjusted entrypoints,
Windows-required target granularity/alignment, RX containment, and allowed
kinds.
Validation-only opens perform all of those checks when the section is present
but never change process CFG state.

There are two product/runtime modes:

1. **Observation mode, the early default.** Query and record
   `ProcessControlFlowGuardPolicy`. Missing `.oat_cfg.windows` is allowed; when
   present it is validated. The private-copy loader follows its ordinary
   RW/NX population to final RX transition and does not call
   `SetProcessValidCallTargets`. Windows normally makes addresses in newly
   executable private pages valid CFG targets unless the allocation established
   invalid-by-default state, but the native gate must verify that behavior for
   OAT-1 rather than infer it from JIT. With CFG enabled, execute real indirect
   calls to quick methods, JNI stubs, all boot trampolines, and representative
   method entrypoints. Passing proves functional compatibility with the
   observed default policy; it is not a claim of fine-grained target
   enforcement.
2. **Explicit-target mode, separately gated.** Require CFG to be enabled, the
   CFG APIs to be available, and `.oat_cfg.windows` to be present and complete.
   Establish OAT code pages as CFG-invalid-by-default without ever introducing
   W+X. After code population, final RX protection, `FlushInstructionCache`,
   and complete image validation/relocation, batch
   `SetProcessValidCallTargets()` calls by validated RX mapping/page region.
   Each call uses a page-aligned base and checked region-relative offsets
   satisfying the native target granularity, and marks exactly the serialized
   offsets valid. Publish generated-code ranges, image roots, and `ArtMethod`
   entrypoints only after every batch succeeds. Any failure rejects the still
   unpublished OAT and selects imageless fallback after safe cleanup.

For the x86-64 API contract used here, every CFG offset must be 16-byte
aligned and the array passed to `SetProcessValidCallTargets()` must be in
ascending order. ART's current x86-64 code alignment is also 16 bytes. The
writer and loader therefore require sorted, unique, exact target offsets and
reject any offset that is not 16-byte aligned. Do not infer that accepting one
offset admits every address in a 16-byte region, and do not add a redundant
"one target per granule" rule: the native gate verifies the exact documented
offset semantics. A future ISA must state and test its own API and code-
alignment requirements before enabling explicit-target mode.

The second mode has a deliberate feasibility gate. `PAGE_TARGETS_INVALID` is
not a general `VirtualProtect()` modifier and cannot simply be applied after
the current committed OAT-1 reservation has been populated. Likewise,
`PAGE_TARGETS_NO_UPDATE` preserves suitable pre-existing CFG state; it does not
create invalid-by-default state. A native allocation/protection probe must
first establish the supported no-W+X sequence and show how it composes with
the already committed boot reservation. Until that passes, do not enable
explicit-target mode or claim that OAT-1 can enforce the serialized allow-list.
Observation mode remains usable and non-blocking.

CFG has no table-registration handle and no unregister operation analogous to
`RtlDeleteFunctionTable()`. Target state belongs to the virtual-memory
allocation. A failed explicit-mode transaction should release the entire
unpublished boot allocation, which discards its target state. If any design
later reuses pages without a full `MEM_RELEASE`, it must first mark every
previously valid offset invalid and prove that no stale valid target survives,
or forbid that address reuse for the process lifetime. Application OAT and
successful-load unloading remain deferred, so the first successful boot OAT
keeps its CFG state for process lifetime.

Do not disable CFG as a workaround. Existing JIT CFG acceptance is useful
precedent but does not prove boot OAT behavior. ARM64EC needs a distinct native
behavior gate for hybrid-call thunks even though it shares this section
format. XFG, export suppression, strict CFG policy, and ACG/
`ProhibitDynamicCode` require later explicit review and are not implied by
either CFG mode.

### CFG gates

- a writer gate proving sorted unique adjusted offsets, dedup-role merging,
  complete quick/JNI/trampoline coverage, deterministic output, and rejection
  of unknown kinds, internal labels, and out-of-range targets;
- a corruption gate that flips each header field, array field, and checksum and
  requires validation-only and executable opens to reject before publication;
- the eight-case ELF layout matrix: neither/unwind/CFG/both, each with and
  without `.data.img.rel.ro`, proving a single R metadata segment and unchanged
  Linux/Android output;
- a native observation-mode gate with process CFG enabled, policy recorded, no
  target API calls, and real indirect quick/JNI/trampoline/method execution;
- a native explicit-mode feasibility gate proving invalid-by-default state,
  the no-W+X transition, target granularity, page/region batching, exact target
  acceptance, and rejection of a deliberately omitted, 16-byte-aligned target;
- partial-batch and exact-address-reuse failures that leave no published
  entrypoint and no stale target state; and
- a separate native gate before any non-AMD64 machine value is accepted.

### Boot generation, selection, and fallback

The product integration must define:

- the native Windows x64 `dex2oat.exe` build target and reproducible command.
  Generation must run natively on Windows: the unwind-emission predicate keys on
  the compiler binary's own `ART_TARGET_WINDOWS`, so a Linux-hosted `dex2oat`
  cannot produce a valid Windows boot set. Cross *building* the Windows binaries
  on Linux remains supported;
- the input boot class path and compiler filter;
- the target-specific staging paths for the matching ART/OAT/VDEX set;
- whether the first staged set is single- or multi-component;
- an explicit opt-in while AOT remains experimental; and
- startup behavior when any component is missing, mismatched, cannot consume
  its exact reservation, fails VDEX/setup validation, or cannot register
  unwind data; observation mode also handles malformed optional CFG metadata,
  while explicit mode handles a missing table or target-state failure.

Early bring-up selects the existing imageless nterp/JIT product as the
fallback. A failed attempt must discard the entire unpublished boot image/OAT
transaction and continue imageless; this behavior requires a native test and
must not be inferred from a successful `-showversion` smoke run.

### Implementation sequence

The first three steps convert generation and compatibility unknowns into
evidence before transport and image integration.

1. Prove native Windows `dex2oat.exe` operation on the authoritative host with
   a real trivial single-JAR, no-image compile that produces parseable `.oat`
   and `.vdex` output. Do not use `--version`; current `dex2oat` does not
   support that option. This gate exercises option parsing, the compiler,
   watchdog, swap-file, memory-advice, and writer paths, but not `ImageWriter`.
2. Select stable textual boot-class-path, dex-location, and `-Ximage:`
   identities. A fixed installation may use canonical absolute paths; a
   relocatable package should use stable logical `--dex-location` and
   `-Xbootclasspath-locations` values. Prove generation and startup pass the
   exact same strings.
3. Execute the existing characterization tests, closing H-005 rather than
   relying only on syntax/build evidence. Add a two-target trampoline
   regression gate proving that the shared producer emits Linux `GS` Thread
   access and Windows `R15` Thread access through the target-aware assembler.
4. Add the narrow Windows private-copy replacement for file-backed
   `MapFileAtAddress(..., reuse=true)` under `ElfOatFile`. Test both
   validation-only allocation and executable reservation consumption while
   retaining the existing whole-span reservation, anonymous zero-fill,
   load-bias, gap, and protection logic.
5. Add the VDEX private-copy handoff and validate exact aperture size,
   ownership, and `ComputeFields -> LoadVdex -> Setup` ordering.
6. Implement the specified AOT unwind transport in order: the
   `EmitWindowsX64UnwindInfo()` predicate, the `CompiledMethod` array and its
   dedup, the `OatWriter` entry collection and `.oat_unwind.windows` emission
   with the two new anchors and its section-local version/checksum, then
   `WindowsAotUnwindRegistry`.
7. Implement `.oat_cfg.windows` collection, independent serialization,
   conditional ELF layout/anchors, and runtime validation. Keep observation
   mode as the default; run the explicit-target allocation feasibility probe
   as a separate gate.
8. Build and stage the Windows `boot.art`, `boot.oat`, and `boot.vdex` set with
   unchanged shared ELF header identity, Windows 64-KiB alignment, and the
   selected boot-component topology. This is the first gate that exercises
   `ImageWriter`.
9. Integrate experimental startup selection and verified imageless fallback.
   Reject expected missing, stale, wrong-target, or cross-artifact mismatches
   before entering trusted-layout `ImageSpace`/`Heap` invariants; do not turn
   those internal invariants into hostile-input recovery paths.
10. On Server 2025, prove representative method entrypoints lie inside the
    boot OAT RX range and execute without JIT compilation; exercise VDEX,
    image relocation, JNI, faults, stack walking, and unwind lookup.
11. Pass the native CFG observation-mode gate and record OAT-1 startup/commit
    measurements. Keep explicit-target CFG, OAT-2, and security work from
    blocking the initial milestone.

Review each upstream ART update against two invariants: Linux/Android ELF
generation and loading remain unchanged, and all Windows-specific mapping and
unwind behavior stays behind small target guards or new Windows-only helpers.

### Stage 1 implementation record

Stage 1 is the characterization step above, not the OAT-1 private-copy loader.
It was implemented on 2026-07-30 in `runtime/oat/oat_file_test.cc` before any
Windows executable-loader dispatch was added. It freezes these current
contracts:

| Characterization | Contract captured |
|---|---|
| `LoadOat` | A non-executable path load uses `ElfOatFile`, places VDEX at `oatdex`, and is absent from `dladdr()` module discovery |
| `LoadAtReservation` | The fallback ELF loader consumes the exact supplied reservation and preserves VDEX placement |
| `FileDescriptorLoadUsesElfOatFile` | The current fd overload selects `ElfOatFile` even when `executable=true` |
| `DuplicateLoadsHaveIndependentState` | Two logical opens have different ELF/OAT, BSS, and VDEX addresses; destroying one leaves the other valid |
| `SdmZipEntryLoad` | Android uses the ZIP-entry dlopen path; a desktop host falls back to `ElfOatFile`; both preserve VDEX placement |
| `DlOpenLoad` extensions | A successful native-linker load exposes the exact `oatdata`, `oatexec`, end-marker, image-relro, BSS, and VDEX dynamic-anchor identities through `dladdr()` |

The tests deliberately describe the upstream Android/Linux behavior that the
Windows dispatch must preserve or explicitly replace. In particular, the
current fd and SDM results are baselines for reusing `ElfOatFile`; the Windows
private-copy mode must preserve their logical OAT/VDEX behavior without the
POSIX fixed file mappings.

Verification is split accurately:

- the complete modified test source passes a production-flag syntax compile
  against the locally available test headers; the old fmtlib GoogleTest copy
  lacks the pre-existing `GTEST_SKIP()` macro, so the syntax-only invocation
  supplies that compatibility spelling;
- Linux `art` builds;
- Windows x64 `oat_file.cc` compiles and `art.dll` links; and
- the rebuilt DLL loads on the authoritative Server 2025 build-26100 host and
  `dalvikvm.exe -showversion` reports `ART version 2.1.0 x86_64`.

This is source/build/smoke evidence, not behavioral execution of the focused
gtests. The minimal product CMake graph does not contain ART's gtest support,
test jars, or `art_runtime_tests`; H-005 in `win32_open_items.md` tracks the
required AOSP Soong/`atest` or maintainable opt-in test-closure run. H-004
separately tracks the glibc 2.41+ positive-dlopen skip. W-026 tracks the one
production portability gap found while restoring the upstream SDM timestamp
comparison for non-Windows.

## Design review findings

Recorded 2026-08-05 against `vendor/art` at `android-16.0.0_r4-92-gffbfe48fd1`.
The review re-derived this document's source claims from the tree, then looked
for design gaps rather than editorial ones. The observations were then checked
independently; some are accepted, some need narrower conclusions, and some are
rejected below. This record keeps source evidence separate from disposition.

### Verified as accurate

Every sampled source claim held on the newer snapshot. The following were
checked directly and need no re-verification before implementation starts:

| Claim | Location |
|---|---|
| `kElfSegmentAlignment` is an alias of `kMaxPageSize` | `libartbase/base/globals.h` |
| The enumerated `kMaxPageSize` consumers are complete: `MemMap` bound, rosalloc, heap PMD, mark-compact card mask, bitmap and `dex2oat` environment tests | tree-wide |
| Non-Linux `GetPageSizeSlow()` returns 4096 | `libartbase/base/globals.h` |
| `Section::AddSection()` raises alignment to `kElfSegmentAlignment` when `phdr_flags_` differ from the previous section | `libelffile/elf/elf_builder.h` |
| `PrepareDynamicSection()` receives `GetOatHeader().GetExecutableOffset()` as `rodata_size` | `dex2oat/dex2oat.cc` |
| Seven `DO_TRAMPOLINE` stubs, guarded by `IsBootImage() && primary_oat_file_`, with the `offset` versus `adjusted_offset` distinction as described | `dex2oat/linker/oat_writer.cc` |
| `CodeOffsetsKeyComparator` compares quick-code, VMap, patches, and intrinsic state; the visitor's `deduped` flag is the authoritative signal | `dex2oat/linker/oat_writer.cc` |
| `CompiledCode::operator==` is declared with no callers | `dex2oat/driver/compiled_method.h` |
| The x86 relative patcher emits no thunks for x86-64 | `dex2oat/linker/x86/relative_patcher_x86_base.cc` |
| OAT loads with `low_4gb=false` while the image heap requests low placement | `oat_file_manager.cc`, `oat_file_assistant.cc`, `image_space.cc` |
| Pinned versions `265\0`, `027\0`, `118\0` and the `lastword += sizeof(uint32_t)` convention | `oat.h`, `vdex_file.h`, `image.cc`, `oat_file.cc` |
| The `cfi_info` storage and dedup pattern is the mechanical template described | `compiled_method.h`, `compiled_method_storage.h` |

The ELF placement argument — that Windows metadata cannot sit between `.rodata`
and `.text` without invalidating every `OatHeader` entrypoint offset, and
cannot sit between `.text` and `.data.img.rel.ro` without breaking
`WriteDataImgRelRo()`'s alignment assertion — was re-derived and is correct.
### Findings and disposition

| # | Review observation | Verdict | Disposition |
|---|---|---|---|
| 1 | The seven shared OAT trampolines still use the source spelling `gs()->jmp(Address::ThreadOffsetAddr(...))`, allegedly leaving Windows output `GS`-relative | **Rejected: false critical finding** | On Windows, `X86_64Assembler::gs()` emits no `0x65` prefix and `ThreadOffsetAddr()` constructs an `R15`-relative address. The existing producer is already target-aware. Retain Linux/Windows disassembly and execution gates as regression tests; no trampoline regeneration is required. |
| 2 | A proposed unwind-emission predicate based only on `kIsTargetWindows` would exclude Windows host builds | **Accepted, with wording correction** | Preserve the semantic union of host Windows and target Windows used by the current `_WIN32 \|\| ART_TARGET_WINDOWS` gates. A shared constexpr is acceptable if it expresses that union; identical preprocessor spelling is not required. |
| 3 | Boot-class-path and dex-location identity is exact `':'`-joined text, without Windows path normalization or case folding | **Accepted, with solution correction** | Generation and startup must use identical stable strings. Fixed products may choose canonical absolute paths; relocatable products should use stable logical `--dex-location`/`-Xbootclasspath-locations` identities rather than physical absolute paths. |
| 4 | Image mode reaches Windows runtime paths not covered by imageless smoke tests, while some heap/image layout invariants are fatal | **Accepted, with narrower scope** | Expected compatibility failures must reject the artifact before trusted-layout invariants. `ImageSpace::LoadBootImage()` already supports a false-return/imageless path; debug-only trusted-layout `CHECK`s such as boot-image contiguity remain internal invariants and need not become hostile-input recovery checks. |
| 5 | Native `dex2oat.exe` operation is unproven | **Accepted, with gate correction** | `--version` is unsupported. The first operational gate is a real trivial single-JAR no-image OAT/VDEX compile. It exercises compiler and watchdog paths, but does not exercise `ImageWriter`; boot-set generation does that later. |
| 6 | Whole-span Windows commit, not just 64-KiB alignment gaps, dominates reservation cost | **Accepted** | Measure the full boot-image reservation, OAT prefix, padding, committed span, and working set separately. |
| 7 | `kDynamicSymbolCount` follows `kLast`, and dynamic-section capacity is reserved in `ElfWriterQuick::Start()` before payload sizes are known | **Accepted** | Keep the base enum/count unchanged, append Windows-only values after `kLast`, and reserve optional-name capacity from writer mode known at `Start()`. Section/anchor emission remains conditional on actual payload. Prove Linux/Android byte identity. |
| 8 | CFG target alignment and exactness were insufficiently specified | **Accepted, with semantic correction** | Require ascending, unique, exact, 16-byte-aligned x86-64 offsets and test rejection of a deliberately omitted aligned target. Reject the unsupported claim that enabling one offset necessarily admits a whole 16-byte granule. |
| 9 | Fatal `RtlDeleteFunctionTable()` failure should become nonfatal during orderly exit | **Rejected as a design change** | Keep strict unregister-before-release ordering and the existing fatal invariant. A deletion failure aborts; designing a recoverable teardown exception is not an early bring-up blocker. |
| 10 | Lack of a product `oatdump`/out-of-process inspector blocks writer and layout verification | **Rejected as a blocker** | Writer/unit/runtime parser tests plus available `llvm-readelf`, `llvm-objdump`, and `llvm-nm` cover the required structure. A small inspector may be added for convenience, but is not required for bring-up. |
| 11 | The stated source snapshot was stale | **Accepted** | The header and this review now name `android-16.0.0_r4-92-gffbfe48fd1`. |

### Scope correction in the loader's favour

One finding reduces rather than adds work. `ElfFileImpl::Load()` performs only
three mapping operations, and the Windows anonymous backend already implements
the reuse-an-existing-committed-subrange case through `VirtualQuery` plus
`VirtualProtect`. The whole-span reservation and the zero-fill tails therefore
already work on Windows; only the file-backed segment call is unrepresentable.
OAT-1 replaces one operation, not a segment mapper. This is recorded under
"Page-size-agnostic ELF versus Windows file views".

### Overall assessment

The review found no critical trampoline defect. OAT-1's mapping delta is also
narrower than a new segment loader: only Windows private-copy replacement of
file-backed segment operations is new. Those conclusions reduce code-change
risk, but they do not make residual risk low. Native `dex2oat.exe` compilation,
boot `ImageWriter` output, image-mode execution, VDEX ownership, unwind
registration, and the OAT-1 protection sequence remain unproven on Server
2025. Explicit CFG additionally depends on an unresolved invalid-by-default
allocation sequence. The aggregate status therefore remains medium/high until
the operational gates pass. CFG explicit enforcement, teardown recovery from
a failed function-table deletion, security hardening, application OAT, and
OAT-2 do not block the initial boot-only observation-mode milestone.

## Publication, rollback, and lifetime

Load state advances only in this order:

```text
opened boot artifacts and structural validation
  -> exact non-executable population
  -> mapped ELF/dynamic-table validation
  -> final OAT protections except the VDEX aperture, then cache flush
  -> return an unpublished mapping owner to OatFileBase
  -> ComputeFields
  -> VDEX exact population, validation, and data protection
  -> OAT Setup
  -> .oat_unwind.windows checksum/format/target-machine validation
  -> optional .oat_cfg.windows checksum/format validation
  -> executable-only per-component table registration and structural lookup proof
  -> image validation and relocation
  -> explicit CFG target transaction, only when that separately gated mode is enabled
  -> generated-code range publication
  -> roots and method entrypoints
```

This matches the existing `android_dlopen_ext()` shape: executable mappings
exist before `OatFileBase::Setup()`, but no `ArtMethod`, root, image field, or
generated-code range reader can acquire them. Failure after loader return
destroys the mapping owner, reverses the completed prefix, and returns no
executable `OatFile`.

Successful boot OAT is process-lifetime state. General unpublication,
quiescence, class unloading, and address reuse are deferred with application
OAT. Pre-publication failure and orderly process teardown must unregister any
installed function table before the shared mapping owner releases code or
unwind metadata. Failure to delete a registered table is fatal, so ART never
releases memory still referenced by Windows. CFG has no corresponding
unregister handle: explicit-mode failure releases the complete unpublished
allocation, and any future partial reuse must invalidate and verify every old
target before reusing the address.

Keep this invariant unchanged during early bring-up, including orderly exit:
unregister before `art.dll` unload or mapping release, and abort if Windows
refuses deletion. Recovery from a failed `RtlDeleteFunctionTable()` is not a
prerequisite for the boot-only milestone.

## Correctness validation and deferred security

Early bring-up consumes trusted boot artifacts produced and staged by the
matching Windows product build. The implementation reuses existing ART ELF,
OAT, VDEX, and image validation, adding focused checks required by the Windows
copy operation:

- checked loaded-span, load-bias, destination, and file-range arithmetic;
- `p_filesz <= p_memsz` and bytes within the opened file region;
- Linux-identical ELF OSABI/ABI-version/flags and Windows 64-KiB segment
  alignment;
- non-overlapping R/RX/RW load ranges with no W+X segment;
- exact containment of the dynamic anchors, `oatdex`, unwind table, and optional
  CFG table, plus recomputed `.oat_unwind.windows` and `.oat_cfg.windows`
  checksums;
- exact reservation-prefix and VDEX-aperture sizes; and
- matching OAT/VDEX/image versions and checksums before publication.

Cache ACLs, path aliases/reparse points, mutation races, hostile-input parser
hardening, cryptographic identity, fuzzing as a security gate, signing, and
AV/EDR policy are explicitly deferred. Correctness fixes that are small,
platform-independent, and useful upstream remain welcome; they are not a
prerequisite for the first trusted boot.

## Windows unwind, faults, and CFG

ELF mappings are not Windows modules. Every non-leaf AOT function needs a
`RUNTIME_FUNCTION`/`UNWIND_INFO` matching its actual Windows x64 prologue,
epilogues, stack allocation, frame register, and nonvolatile GPR/XMM saves.
The tail-`jmp` trampolines could use Windows' leaf fallback, but this design
deliberately gives them shared zero-prologue metadata for uniform coverage.
"AOT unwind format and transport" above is the concrete design; the
requirements restated here are the acceptance conditions it must satisfy.

Validate before registration:

- sorted non-overlapping functions and `BeginAddress < EndAddress`;
- all 32-bit code/unwind RVAs within registered ranges;
- unwind version, flags, code count, padding, frame register/offset,
  handler/chained record, bounds, acyclicity, and alignment;
- read-only non-executable unwind metadata; and
- functions entirely within RX OAT segments.

After final protection and OAT/VDEX `Setup()`, call `RtlAddFunctionTable` in
the fallible finalization hook. Prove table structure with
`RtlLookupFunctionEntry` before publication; exercise `RtlVirtualUnwind` only
in the native managed-frame gates.

The JIT registry supplies ordering precedent, but AOT gates must cover quick,
runtime, JNI, deoptimization, managed exception, translated NPE/SOE, and fatal
frames. Failure before publication unregisters the table; a successful boot
keeps it registered for process lifetime.

CFG uses the architecture-neutral `.oat_cfg.windows` format and two modes
specified above. Observation mode records process policy and executes real
indirect quick/JNI/trampoline/method targets without changing target state; it
is the early default. Explicit-target mode consumes the exact list through
`SetProcessValidCallTargets`, but remains disabled until the committed OAT-1
path proves a supported invalid-by-default, no-W+X allocation sequence. Neither
mode disables CFG, and observation success is not a fine-grained-enforcement
claim.

OAT-1 writes only while non-executable and makes code final RX. VDEX, image,
BSS, dynamic, unwind, and CFG-metadata pages are never executable. These final
permissions are retained as ordinary mapping correctness even though security
hardening is out of the early scope.

### Execmem product requirement

Deployment must permit ART-created executable memory for the existing JIT and
the boot OAT copy. `ProhibitDynamicCode`/ACG and mitigation bypasses are out of
scope; they are not early compatibility gates.

### Debugger and security tools

ELF OAT is absent from normal PE module enumeration, image-load telemetry,
automatic static unwind discovery, and normal Authenticode image treatment.
The first milestone relies on ART's generated-code range and the registered
Windows function table. Rich debugger/profiler module records and security
tool policy are deferred.

## Risk register

| Risk | Initial severity | Control |
|---|---:|---|
| Literal POSIX mapping port | Critical | No `MAP_FIXED` emulation; use OAT-1 |
| 4-/16-/64-KiB confusion | High | Keep `ART_PAGE_SIZE_AGNOSTIC=1`; distinguish Windows 4-KiB OS pages from 64-KiB allocation/artifact alignment; keep Linux at 16 KiB |
| Raising `kMaxPageSize` solely for Windows layout breaks GC assumptions | High | Decouple target `kElfSegmentAlignment` and retain the Windows OS-page/GC bound |
| Incorrect x64 unwind | Critical | Generate, transport, validate, register, and exercise every code kind, including the leaf trampolines |
| Windows AOT code diverges from Linux by the `RBP` anchor | Medium | Accepted consequence of the §7.9.3 frame rule; compare ELF identity and layout across targets, never code bytes |
| Dedup merges code with mismatched unwind bytes | High | One entry per unique code range; a byte-mismatch on a deduplicated offset fails the `dex2oat` run |
| Default CFG behavior rejects OAT entrypoints | High | Observation mode records native policy and executes real quick/JNI/trampoline/method indirect calls before publication support is claimed |
| Explicit CFG cannot establish invalid-by-default state in OAT-1 | Open, non-blocking | Keep observation mode as the default; gate explicit mode on a native allocation/protection probe and never treat `PAGE_TARGETS_NO_UPDATE` as state creation |
| CFG table misses or over-admits an entrypoint | High for explicit mode | Independently checksummed `.oat_cfg.windows`, complete sorted unique exact 16-byte-aligned targets, dedup-role merging, a deliberately omitted aligned-target test, and publication only after all batches succeed |
| CFG state survives failed-load address reuse | High for explicit mode | Fully release the unpublished allocation; otherwise invalidate and verify every old target or forbid reuse |
| VDEX exact placement/ownership | High | OAT-1 copy into `oatdex` with an owner-sharing `MemMap` slice |
| Boot exact address failure | High | Consume reservation and verify exact result |
| Failed load leaves partial image/OAT state | Critical | One unpublished transaction; discard it before imageless fallback; failed function-table deletion is fatal |
| Private-copy memory/startup | High operational | Whole-span commit for simplicity; measure 64-KiB padding and committed gaps before optimizing |
| Wrong cross-OS boot artifacts staged | High | Windows-target-specific staging plus image/OAT checksums and actual AOT execution tests |
| Boot topology mismatch | High | Explicitly select and test single- or multi-component output |
| Target-aware trampoline lowering regresses | Medium | The shared producer already lowers Thread access to Linux `GS` or Windows `R15`; retain two-target disassembly plus resolution/quick-to-interpreter execution gates |
| Native `dex2oat.exe` operation is unproven | High | It links from the Windows graph but has never run. Prove a real trivial single-JAR no-image `.oat`/`.vdex` compile before boot-set output is treated as actionable; `--version` is not supported |
| Boot class path / dex location strings disagree between generation and load | High | The comparison is byte equality on `':'`-joined text with no normalization; use matching canonical absolute identities for fixed installs or stable logical identities for relocatable packages, and test intentional mismatches |
| Image-mode runtime paths have never executed on Windows | High | Every accepted gate to date is imageless; reject expected compatibility failures before trusted-layout invariants and treat successful image loading/execution as a distinct milestone |
| Boot reservation commit dominates the measured cost | Medium operational | Windows `MemMap` commits whole spans, so the image+OAT reservation, not the 64-KiB padding, is the term to report and later optimize |
| Unwind predicate narrows the existing Windows condition | Medium | Preserve the semantic union of Windows-host and Windows-target compilation; test both even if a shared constexpr replaces the current preprocessor spelling |
| `kDynamicSymbolCount` grows implicitly with the enum | Medium | It derives from `DynamicSymbol::kLast`; append Windows-only values after `kLast`, `static_assert` the base count, reserve from writer mode at `Start()`, and test Linux byte identity |
| Upstream divergence | High | Reuse `ElfOatFile`, `ElfFile`, and `OatFileBase`; conditionally gate target alignment, unwind, and CFG additions so Linux output is unchanged |

The aggregate early-bring-up risk is medium/high. Reusing ART's writer,
offsets, reservation, load bias, BSS, anchors, and companion artifacts limits
semantic divergence. OAT-1 minimizes mapping changes at the cost of
per-process commit and copying.

## Required gates

Before claiming Windows AOT support, require:

- native Windows x64 `dex2oat.exe` generation of the selected boot component
  set and deterministic checksummed fields;
- ELF-header comparison proving Linux-identical OSABI/ABI version/flags,
  Linux 16-KiB and Windows 64-KiB `PT_LOAD` alignment, and
  `ART_PAGE_SIZE_AGNOSTIC=1` on both;
- `GetSystemInfo()` proof of the expected Windows 4-KiB page and 64-KiB
  allocation granularity;
- exact boot reservation, deliberate collision, relocation-delta, and selected
  single- or multi-component image tests;
- VDEX and ART-image positive/mismatch/truncation/relocation cases;
- `VirtualQuery` proof of R/RX/RW/no-access and no W+X stage;
- execution after `FlushInstructionCache`;
- function-table add/lookup/virtual-unwind and exception/stack-walk coverage for
  compiled methods, JNI stubs, and trampolines, plus the `.oat_unwind.windows`
  writer/loader/dedup gates listed under "Unwind gates";
- proof that representative `ArtMethod` entrypoints lie in the boot OAT RX
  range and execute without JIT compilation;
- `.oat_cfg.windows` writer/parser/checksum/anchor/layout tests, with the
  section optional in observation mode and shared OAT version unchanged;
- real quick/JNI/trampoline/method indirect calls in observation mode while
  recording native CFG policy and proving no target API was called;
- validation-only and executable private-copy opens, plus missing, mismatched,
  reservation-failure, VDEX-failure, setup-failure, and ordinary
  unwind-registration-failure cases that clean up and continue with imageless
  nterp/JIT;
- focused GC, roots, deoptimization, translated fault, JNI, reflection, class
  initialization, and fatal-dump execution through boot OAT;
- behavioral execution of the Stage 1 tests currently blocked by H-005; and
- OAT-1 startup time, total committed span, and working-set measurements,
  reporting the boot image reservation, the OAT prefix consumed from it, and
  the 64-KiB padding as separate terms.

The 2026-08-05 review adds these gates, which cover generation-side
prerequisites the original list assumed rather than required:

- a trampoline regression gate: disassemble the seven emitted OAT trampolines
  on both targets and require Linux `GS` and Windows `R15` Thread addressing,
  then execute a boot-image method reached through the resolution trampoline
  and one reached through the quick-to-interpreter bridge;
- a `dex2oat` operation gate on Server 2025: a real trivial single-JAR
  no-image compile producing parseable `.oat`/`.vdex`, run before any boot-set
  generation claim; do not use the unsupported `--version` option;
- a location-string gate: prove the selected canonical-absolute or stable-
  logical identities are byte-identical at generation and startup, then vary
  separator flavour, drive-letter case, and absolute-versus-relative form and
  require intentional mismatches to be explicitly diagnosed and rejected;
- a JIT non-regression gate proving the new `EmitWindowsX64UnwindInfo()`
  predicate covers both a Windows host build and an `ART_TARGET_WINDOWS`
  build, regardless of the helper's exact spelling;
- a Linux byte-identity gate over `.dynstr`, `.dynsym`, and `.hash` proving the
  optional anchors changed no non-Windows output, plus the `static_assert` on
  the base symbol count and a Windows enabled-mode/empty-payload reservation
  case;
- an image-mode gate that deliberately supplies a mismatched or wrong-target
  artifact set and requires a diagnosed rejection/imageless fallback before
  trusted-layout `ImageSpace`/`Heap` invariants; and
- boot OAT size and a throughput comparison against the Linux boot OAT,
  recording the cost of reserving both `R15` and `RBP` in Windows AOT code.

Windows Server 2025 x64 build 26100 is authoritative. Record OS build,
mitigation policy, runtime/compiler/artifact hashes, base/load bias,
reservation/protection maps, unwind and CFG observations, actual AOT
entrypoints, fallback results, and archive hash. Linux protects shared
semantics; Wine is structural only.

## Open implementation items

1. Keep and test the Linux-identical ELF header identity, retain Linux 16-KiB
   layout, and select 64-KiB `kElfSegmentAlignment` for Windows without
   treating Windows allocation granularity as `kMaxPageSize`.
2. Prove native `dex2oat.exe` operation with a trivial single-JAR no-image
   compile on Server 2025; do not use the unsupported `--version` option.
3. Select and gate identical generation/startup boot-class-path, dex-location,
   and `-Ximage:` strings, using canonical absolute identities for a fixed
   install or stable logical identities for a relocatable package.
4. Close H-005 and prove the existing loader characterization contracts. Add
   the two-target trampoline disassembly/execution regression gate; no
   trampoline producer change is currently required.
5. Add the narrow Windows private-copy replacement for file-backed
   `MapFileAtAddress(..., reuse=true)` for both validation-only and executable
   opens under the existing `ElfOatFile`/`ElfFile` flow. Preserve the current
   anonymous whole-span reservation and zero-fill reuse paths.
6. Preserve `oatdex` semantics with a VDEX copy and shared allocation owner,
   including exact aperture sizing and rollback.
7. Implement the specified AOT unwind transport: the Windows-and-x86-64
   emission predicate replacing the `IsJitCompiler()` gate, the
   `CompiledMethod` unwind array, dedup-safe `OatWriter` entries, the
   `.oat_unwind.windows` section and anchors, and `WindowsAotUnwindRegistry`.
8. Implement the specified `.oat_cfg.windows` target collection, checksum,
   conditional anchors/layout, parser, and observation mode. Separately prove
   whether explicit-target mode can establish invalid-by-default CFG state in
   the already committed OAT-1 reservation without W+X; this does not block
   observation-mode bring-up.
9. Define the native boot-generation command, exercise `ImageWriter`, stage the
   target-specific `boot.art`/`.oat`/`.vdex` set, and select the initial boot-
   component topology.
10. Add experimental boot selection and whole-transaction imageless fallback.
    Reject expected missing, stale, wrong-target, and cross-artifact mismatch
    cases before trusted-layout image/heap invariants.
11. Prove real boot-OAT entrypoints, image relocation, JNI, faults, GC/roots,
    and unwind/stack-walk behavior on Server 2025.
12. Pass CFG observation-mode characterization and measure OAT-1 startup,
    reservation, commit, padding, and working-set cost. Defer explicit CFG,
    application OAT, unloading, OAT-2, cache security, hostile-input
    hardening, and rich tooling integration to separately reviewed work.

## Primary references

ART:

- `vendor/art/runtime/oat/oat.{h,cc}`
- `vendor/art/runtime/oat/oat_file.{h,cc}`
- `vendor/art/runtime/oat/elf_file.cc` and `elf_file_impl.h`
- `vendor/art/libelffile/elf/elf_builder.h`
- `vendor/art/dex2oat/linker/oat_writer.{h,cc}`
- `vendor/art/runtime/vdex_file.{h,cc}`
- `vendor/art/dex2oat/linker/vdex_file_writer.{h,cc}`
- `vendor/art/runtime/oat/image.{h,cc}`
- `vendor/art/dex2oat/linker/image_writer.{h,cc}`
- `vendor/art/runtime/gc/space/image_space.cc`
- `vendor/art/libartbase/base/mem_map_windows.cc`
- `vendor/art/runtime/multiplatform/windows/jit_unwind_windows.*`

Reviewed 2026-08-05 for the generation-side findings:

- `vendor/art/compiler/trampolines/trampoline_compiler.cc` (the shared x86-64
  OAT trampoline producer; its `gs()`/`ThreadOffsetAddr()` spelling is lowered
  by the target-aware assembler to Linux `GS` or Windows `R15`)
- `vendor/art/dex2oat/linker/image_writer.cc` (`GetOatAddress(StubType)`, which
  installs those trampolines as boot-image entrypoints)
- `vendor/art/libartbase/base/globals.h` (`kElfSegmentAlignment`,
  `kIsTargetWindows`, `kClassPathListSeparator`)
- `vendor/art/runtime/gc/heap.cc` (fatal image/OAT contiguity checks)
- `vendor/art/libartbase/base/file_utils.cc` (`ANDROID_ROOT`-based default boot
  image location on Windows)
- `vendor/art/dex2oat/dex2oat.cc` (`kBootClassPathKey` writer and the watchdog's
  POSIX condition-variable use)

AOT unwind transport:

- `vendor/art/compiler/driver/compiled_code_storage.h` (the compiler-side
  interface whose signature changes)
- `vendor/art/dex2oat/driver/compiled_method.{h,cc}`,
  `compiled_method-inl.h`, and `compiled_method_storage.{h,cc}`
- `vendor/art/compiler/common_compiler_test.cc` and
  `vendor/art/dex2oat/driver/compiler_driver.cc` (`CompiledCodeStorage`
  implementations and `DO_TRAMPOLINE`)
- `vendor/art/compiler/utils/x86_64/jni_macro_assembler_x86_64.cc`
- `vendor/art/compiler/optimizing/code_generator_x86_64.cc` and
  `optimizing_compiler.cc` (`IsJitCompiler()` unwind gates)
- `vendor/art/compiler/jni/quick/jni_compiler.cc`
- `vendor/art/compiler/utils/x86_64/assembler_x86_64.{h,cc}` (unwind builder)
- `vendor/art/dex2oat/linker/x86/relative_patcher_x86_base.cc` (no x86-64
  thunks)
- [x64 exception handling and unwind data](https://learn.microsoft.com/cpp/build/exception-handling-x64)

Bionic baseline:

- AOSP tag `android-16.0.0_r4`, `linker/linker_phdr.{h,cpp}` and `NOTICE`
- [Pinned Bionic linker source](https://android.googlesource.com/platform/bionic/+/refs/tags/android-16.0.0_r4/linker/)

Windows APIs:

- [PE/COFF machine types](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format#machine-types)
- [CreateFileMappingW](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw)
- [MapViewOfFile3](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3)
- [VirtualAlloc2](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2)
- [VirtualProtect](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect)
- [FlushInstructionCache](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-flushinstructioncache)
- [RtlAddFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable)
- [RtlDeleteFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtldeletefunctiontable)
- [RtlVirtualUnwind](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtlvirtualunwind)
- [SetProcessValidCallTargets](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-setprocessvalidcalltargets)
- [Memory protection constants](https://learn.microsoft.com/windows/win32/memory/memory-protection-constants)
- [Process CFG policy](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-process_mitigation_control_flow_guard_policy)
- [Process dynamic-code policy](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-process_mitigation_dynamic_code_policy)
