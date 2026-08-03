# Windows AOT and OAT design

Status: early bring-up design baseline (2026-08-03). This document records the
current ART OAT/VDEX/image contracts and the selected Windows AOT artifact and
loader design. Windows keeps the same ELF64 coat and page-size-agnostic layout
that ART currently emits for Linux. An ART-owned, OAT-only private-copy path
loads it; PE32+ OAT is rejected.

Windows OAT generation and executable loading are not implemented yet.
Implementation stage 1, the pre-dispatch characterization suite, is now in the
tree; it does not enable Windows AOT. The supported Windows product remains
imageless nterp/JIT while this independent future track is open. The
authoritative implementation gate is Windows Server 2025 Datacenter
Evaluation, x64 build 26100. Linux and Wine remain development and structural
gates; the former Windows 10 lab host is unavailable.

The source snapshot is `vendor/art` at
`android-16.0.0_r4-76-g4eab6e7423`.

## Executive decision

1. OAT, VDEX, and ART images are internal compiled-cache formats. They are not
   public stable ABIs. A matching runtime/compiler build generates and loads
   them; incompatible artifacts are regenerated.
2. The logical OAT records remain useful on Windows. The current executable
   coat and loading contract are tightly coupled to ELF program headers,
   dynamic symbols, load bias, BSS, image reservations, and VDEX placement.
3. Windows OAT remains the ordinary ART ELF64 format. `EI_OSABI`,
   `EI_ABIVERSION`, `e_flags`, program-header structure, and
   `kElfSegmentAlignment` remain exactly those emitted by the current Linux
   ART writer. In particular, both products retain
   `ART_PAGE_SIZE_AGNOSTIC=1`, so the current x86-64 `PT_LOAD` alignment is
   16 KiB. There is no separate Windows ELF coat identity or literal 4-KiB
   Windows layout.
4. PE32+ OAT is rejected. `LoadLibraryExW` cannot consume an ART-owned
   reservation or force an independent instance of the same artifact. A
   manual PE loader would add a new writer and relocation format without
   receiving normal DLL-loader behavior.
5. The first implementation is boot-only. It reuses the existing
   `ElfOatFile`/`OatFileBase` transaction where practical and adds only the
   Windows private-copy, VDEX, protection, cache-flush, and unwind mechanics
   that the current `MAP_FIXED`-style path cannot provide.
6. OAT-1 consumes the existing committed ART boot reservation. It retains the
   current Windows `MemMap` whole-span `MEM_RESERVE | MEM_COMMIT` semantics,
   privately copies `PT_LOAD` bytes, zeroes BSS, leaves gaps `PAGE_NOACCESS`,
   applies final R/RX/RW protections, registers Windows x64 unwind data, and
   publishes entrypoints last.
7. AOT unwind is required for usable Windows stack walking. CFG behavior is
   TBD and shall be characterized on the authoritative native host; CFG is not
   yet a bring-up requirement or a support claim.
8. Application OAT, successful-load unloading, shared-view/OAT-2 work, and
   cache/adversarial-input security hardening are outside the early bring-up
   scope. Security-sensitive product enablement requires a later review.
9. The full Bionic linker, `soinfo`, dependency, relocation, namespace, TLS,
   constructor, and symbol-interposition machinery remain rejected. Reuse the
   existing ART ELF reader first; copy selected Bionic algorithms only if a
   concrete correctness gap requires them.
10. Executable-memory capability is an ART product prerequisite. The initial
    design makes no `ProhibitDynamicCode`/ACG compatibility claim.

Terminology: older project discussion sometimes used “Windows OAT” for the
rejected PE32+ coat proposal. In this document it means the ordinary ART ELF
container, with Linux-identical ELF header/layout policy, carrying
Windows-targeted x86-64 quick code and Windows unwind metadata.

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

This project's own Windows unwind section adds one more entry to that list: the
`.oat_unwind` section and its two anchors require an OAT version increment in
the same change, so a pre-section Windows artifact rejects by version instead
of by a missing anchor. Because the version is shared with Linux ART, the bump
also invalidates existing Linux artifacts; that is the established upstream
behavior for any layout change and needs no separate compatibility path.

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

The Windows product adds one read-only loadable section, `.oat_unwind`, holding
the AOT `RUNTIME_FUNCTION` equivalents and their `UNWIND_INFO` bytes. It is
specified under "AOT unwind format and transport" and is absent from Linux and
Android output.

The dynamic table currently needs only `DT_HASH`, `DT_STRTAB`, `DT_SYMTAB`,
`DT_SYMENT`, `DT_STRSZ`, `DT_SONAME`, and `DT_NULL`. There are no normal DSO
imports or ELF relocation dependencies.

### OAT writer lifecycle

`OatWriter` and `ElfBuilder` jointly:

1. reserve/write VDEX headers, checksums, DEX, verifier dependencies, and
   lookup tables;
2. emit `OatHeader`, key/value data, dex records, class/method tables, maps,
   BSS mappings, and image-relro metadata;
3. finalize compiled-code and method offsets;
4. emit quick code and trampolines;
5. assign ELF virtual/file offsets and dynamic anchors;
6. emit BSS and optional DEX virtual ranges;
7. finalize checksums and ELF headers; and
8. emit the matching ART image where requested.

OAT offsets are often 32-bit. Windows does not implicitly widen them.

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
actual OAT relocation range. Those semantics are a principal reason not to
delegate placement to `LoadLibraryExW`.

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
| OAT | Current ART ELF64 with Windows x64 quick code and unwind data | `ElfOatFile` plus a Windows private-copy mapping helper |
| VDEX | Read-mostly data, initially populated in the existing `oatdex` range | `VdexFile` inside OAT transaction |
| ART image | Reserved mapping, copy/decompression and ART relocation | `ImageSpace` |

The private-copy helper is not exported as `dlopen`. It is selected only by
the Windows executable-OAT path and does not become a general ELF DSO loader.

### Explicit non-goals

- PE32+ OAT, `WOAT`, and both normal and manual PE OAT loading.
- A general `.so` loader, including `libjiagu.so`.
- `DT_NEEDED`, PLT/GOT binding, REL/RELA/JMPREL, IFUNC, text relocation, TLS,
  constructors/destructors, symbol interposition, or namespaces.
- Private `Ldrp*`, undocumented loader-list manipulation, or kernel `Zw*`
  interfaces.
- Application OAT, application images, duplicate-instance/class-unloading
  semantics, and successful boot-OAT unloading in the initial milestone.
- Shared 64-KiB file views or a separately versioned OAT-2 layout.
- Cache threat modeling, hostile-input hardening, Authenticode treatment, and
  debugger/profiler behavior equivalent to a DLL in early bring-up.
- `ProhibitDynamicCode`/ACG compatibility or policy bypasses.

CFG is TBD. The initial native execution tests shall record the process CFG
policy and observed indirect-call behavior without declaring CFG support or
requiring a mitigation bypass. CET user shadow stacks remain unsupported
under the existing Windows process contract.

## Why PE32+ OAT is rejected

### `LoadLibraryExW` mismatch

`LoadLibraryExW` performs a complete PE load but cannot:

- consume an existing ART reservation at a caller-selected exact address;
- accept an already validated file handle or in-memory/archive entry;
- force a fresh instance of the same physical module; or
- preserve current VDEX replacement and per-instance BSS semantics without a
  broad ART image/code-generation redesign.

The Server 2025 design probe confirmed:

- a normal PE loaded and exposed exports/unwind metadata;
- loading one absolute path twice returned one module address;
- copied paths produced instances only by becoming different physical files;
- an existing preferred-base reservation was left untouched;
- requested-address `SEC_IMAGE` views lacked normal loader unwind discovery;
  and
- independently requested image views did not establish a supported per-view
  relocation contract.

These are rejection results, not undocumented mechanisms to exploit.

### Manual PE has no useful advantage

`SEC_IMAGE` and `MapViewOfFile3` do not perform the loader transaction. Image
views cannot replace placeholders, and a mapped image does not automatically
receive imports, TLS, entrypoint calls, module-list state, per-view rebasing,
CFG/load-config processing, or dynamic unwind registration.

A manual PE design would need a new writer, sections, descriptor, base
relocations, parser, mapper, protections, unwind, CFG, rollback, exact
placement, and instance model. It would retain most manual-ELF integration
risks while discarding ART's existing ELF writer/reader contract. It is
rejected.

`LdrLoadDll` retains normal module semantics. `NtCreateSection` and
`NtMapViewOfSection` are mapping primitives, not a complete load. Private
`Ldrp*` and user-mode `Zw*` dependencies are unacceptable. No native API
closes the contract.

## Bionic reuse boundary

Do not copy the full Bionic linker. It solves dependency graphs, namespaces,
relocations, TLS, constructors, interposition, CFI shadow, link maps, ZIP/APK
loading, GNU properties, RELRO sharing, and Android compatibility policy.

The smallest-diff implementation starts with ART's existing
`ElfOatFile`/`ElfFile` parser, loaded-size calculation, dynamic-symbol lookup,
and `OatFileBase` transaction. The Windows-only addition supplies private
population of the already committed reservation, final protections, VDEX
copy ownership, cache flush, and AOT unwind registration.

If implementation or characterization finds a concrete correctness gap,
selected Bionic algorithms may be copied under this boundary:

| Area | Treatment |
|---|---|
| ELF identity, header, dynamic symbols, and program headers | Reuse existing ART implementation first |
| Checked file ranges and load-span/load-bias calculation | Add focused correctness checks; copy selected Bionic algorithms only where demonstrated necessary |
| Segment zero-fill and PHDR containment rules | Reuse semantics, not POSIX calls |
| POSIX `mmap(MAP_FIXED)` backend | Do not copy |
| `soinfo`, dependencies, relocations, namespaces, TLS, constructors | Do not copy or implement |
| OAT anchor lookup | Reuse `ElfFile::FindDynamicSymbolAddress()`; `OatFileBase::ComputeFields()` changes only by resolving the two additive `oatunwind` anchors |
| Logical OAT validation | Keep existing `OatFile` setup logic |
| Windows reservation/protection/VDEX/unwind | Add an OAT-only private-copy helper; CFG remains TBD |

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
- the current page-size-agnostic writer alignment,
  `kElfSegmentAlignment == 16384`;
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
oatunwind, oatunwindlastword
```

`oatunwind`/`oatunwindlastword` are the two anchors added for the AOT unwind
table. They are required whenever the artifact contains quick code and must
resolve inside an R segment.

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
64 KiB. ART retains `ART_PAGE_SIZE_AGNOSTIC=1`: `kMinPageSize` is 4 KiB,
`kMaxPageSize` and `kElfSegmentAlignment` are 16 KiB, and the current Linux
`boot.oat` uses `PT_LOAD.p_align == 0x4000`. This is the layout Windows keeps.

The current Windows `MemMap` file path cannot map a file view over an occupied
`VirtualAlloc` reservation and cannot reproduce POSIX `MAP_FIXED` for 16-KiB
ELF offsets that are not 64-KiB file-view aligned. OAT-1 avoids the mismatch by
copying into the existing private allocation; it does not change the writer.

Do not mechanically port Bionic's:

```text
reserve complete PROT_NONE span
MAP_FIXED each PT_LOAD over the reservation
```

Only the private-copy implementation is in the early bring-up scope.

### OAT-1: private-copy correctness loader

OAT-1 uses the existing ART-owned private allocation and works with the current
16-KiB-aligned, page-size-agnostic ELF layout, exact boot placement, and
existing committed `PAGE_NOACCESS` reservation.

Load transaction:

1. Open OAT through the existing path/fd boot-artifact APIs.
2. Validate ELF headers, tables, ranges, Linux-identical ELF identity, dynamic
   anchors, paired boot metadata, and unwind data without executable memory.
3. Calculate span/load bias with checked arithmetic.
4. Consume the exact prefix of the caller's remaining boot-image reservation.
5. Retain the current Windows `MemMap` whole-span commit. Make only declared
   load destinations writable and non-executable; leave gaps committed but
   `PAGE_NOACCESS`.
6. Read the declared bytes from the opened artifact and zero every
   `p_memsz - p_filesz` byte including BSS.
   Keep only the validated `oatdex` aperture writable for the later handoff.
7. Validate mapped dynamic anchors, apply final protections to all other OAT
   ranges, flush executable ranges, then validate `.oat_unwind` and register it
   as one multi-entry function table based at `oatdata`. Record CFG
   observations but do not gate bring-up on an unresolved CFG design.
8. Return the unpublished mapping owner to `OatFileBase`.
9. Open VDEX through the existing transaction, populate and validate it in the
   exact `oatdex` aperture, then apply its final data protection.
10. Run existing logical OAT/dex/BSS/class-loader setup and image validation/
    relocation.
11. Publish the generated-code range, roots, and method entrypoints only after
    the complete artifact set succeeds.

OAT-1 avoids placeholder splitting, file-view alignment, fragmented ownership,
and replacement rollback.

#### Whole-span commit decision

| Allocation model | Advantages | Costs |
|---|---|---|
| Existing whole-span `MEM_RESERVE | MEM_COMMIT` | No new `MemMap` state; directly consumes the boot reservation; one shared owner; simple protection and failure cleanup | Commit charge includes no-access gaps |
| Reserve span, commit declared ranges | Avoids commit charge for gaps | Requires new reserve/commit APIs, conflicts with the already committed boot reservation, and adds partial-state ownership and rollback |

OAT-1 selects whole-span commit. R, RX, BSS, and `oatdex` pages must all be
committed, so reserve-only primarily saves alignment gaps. Measure total boot
commit before considering a later optimization.

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

It requires:

- 64-KiB-congruent file offsets and virtual addresses;
- padding between R, RX, copy-on-write, BSS, and VDEX groups;
- one `VirtualAlloc2` placeholder reservation;
- exact placeholder splitting;
- `MapViewOfFile3(..., MEM_REPLACE_PLACEHOLDER, ...)` data/pagefile views;
- RX code with no writable executable alias;
- private/COW image-relro and BSS;
- an owner for all views and remaining placeholders; and
- idempotent reverse-order rollback.

`SEC_IMAGE` remains rejected. No OAT-2 implementation or equivalence gate is
required before boot OAT works.

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
3. emit `OatQuickMethodHeader`, `CodeInfo`, maps, method offsets, trampolines,
   and Windows unwind descriptions;
4. build VDEX and checksums;
5. run the shared logical OAT writer;
6. run the existing `ElfBuilder` with the same Linux-identical ELF identity
   and page-size-agnostic alignment; do not add a Windows coat switch;
7. emit only restricted dynamic anchors and no ELF imports/relocations,
   including the two new `oatunwind` anchors;
8. emit the bounded read-only `.oat_unwind` section with one entry per unique
   code range, the shared trampoline record, and deduplicated `UNWIND_INFO`
   bytes;
9. emit the matching boot ART image and cross-artifact checksums; and
10. stage `boot.art`, `boot.oat`, and `boot.vdex` in a Windows-target-specific
    product directory.

`ART_PAGE_SIZE_AGNOSTIC=1` remains in both Linux and Windows compiler/runtime
definitions. A generation test shall compare the relevant ELF header fields
and `PT_LOAD.p_align` with Linux ART and require the current 16-KiB alignment.

The ELF container is Linux-identical, but the quick code inside it is not.
Enabling unwind emission for AOT also applies the §7.9.3 `RBP` frame-anchor
rule to Windows AOT methods, so Windows boot OAT code for a given DEX input
differs from Linux boot OAT code by that anchor, its forced spill, and the
resulting `spill_mask`. This is an intended consequence of the frame rule, not
a coat difference: header identity, alignment, anchors, and layout policy stay
the same. Generation tests compare ELF identity and layout, never code bytes,
between the two targets.

The initial artifacts are trusted build outputs, not a mutable application
cache. Cache publication, replacement, and adversarial-input policy are
deferred.

The product plan must still select and test the initial boot topology: either
one `boot.art/oat/vdex` component or the complete multi-component layout
emitted by the Windows build. The loader must not silently support only the
first component when the staged image header declares more.

## Loader components and ownership

Keep responsibilities separate:

1. Existing `ElfOatFile`/`ElfFile`: ELF parsing, loaded-span calculation,
   dynamic anchors, path/fd inputs, and the ART-facing owner.
2. A narrow Windows OAT private-copy helper: consumption of the boot
   reservation, byte population, zero-fill, gap/final protections, cache
   flush, shared allocation ownership, and pre-publication rollback.
3. Existing `OatFileBase`: OAT anchor requirements, dex, BSS, VDEX, image, and
   class-loader semantics.
4. A Windows VDEX reuse helper: copy into `oatdex` and return a `MemMap` slice
   sharing the OAT allocation owner.
5. `WindowsAotUnwindRegistry`: `.oat_unwind` validation, one multi-entry
   `RtlAddFunctionTable`/`RtlDeleteFunctionTable` lifetime, and the
   representative lookup/virtual-unwind proof.
6. Existing generated-code registry: fault/stack readers and publication
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

1. Select `ElfOatFile` for Windows executable boot OAT instead of trying to
   make Windows `dlopen` consume the ELF.
2. Add a Windows-only private-copy mapping mode below that path, preferably as
   a narrow helper invoked by `ElfFileImpl::Load()` rather than a fork of
   `OatFileBase` or a second ELF parser.
3. Preserve the existing path and fd open logic and dynamic-symbol lookup.
4. Consume the exact caller reservation prefix and expose the same base,
   segment, BSS, and `oatdex` addresses expected by `ElfOatFile`.
5. Keep `runtime/oat/oat_file.h`, `OatFileBase::Setup()`, dex/BSS
   interpretation, and public `OatFile` APIs unchanged. `ComputeFields()` takes
   one additive change: resolving the two `oatunwind` anchors alongside the
   anchors it already resolves, using the same optional-section idiom. This is
   the one place that knows the mapped anchor addresses, so resolving them
   elsewhere would mean duplicating its symbol lookup. The addition is
   target-neutral and inert on Linux and Android, where the section is absent
   and both pointers stay null.
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
2. fixed unwind descriptions for every non-leaf OAT trampoline/runtime stub;
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
  return kIsTargetWindows && GetInstructionSet() == InstructionSet::kX86_64;
}
```

`kIsTargetWindows` is a build-time constant of the binary being compiled, not a
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
On x86-64 each one is a single `gs:`-relative indirect `jmp` followed by
`int3` — it allocates no stack, saves no register, and never returns. Such a
function is a leaf with a zero-size prologue. Windows requires a record for it
anyway, because an exception raised inside the `jmp` (or a walk that lands on
it) must be able to continue past the frame:

| OAT code range | Shape | Record |
|---|---|---|
| The seven `DO_TRAMPOLINE` stubs | tail `jmp` via `gs`, no frame | one shared leaf `UNWIND_INFO`: version 1, flags 0, prologue size 0, zero unwind codes, no frame register |
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

### Serialized table

Add one read-only loadable section, `.oat_unwind`, emitted by `ElfBuilder`
after `.data.img.rel.ro` and before `.bss`. It is never executable and never
writable after load. Two placements that look more natural are both wrong, and
the existing assertions are what rule them out:

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

Placing it last among the `PROGBITS` sections keeps both invariants untouched and
adds one `WriteState` (`kWriteUnwind`) between `kWriteDataImgRelRo` and
`kWriteHeader`, with a `WriteUnwind()` that mirrors `WriteDataImgRelRo()`:
`ChecksumUpdatingOutputStream`, then a `CheckOatSize()` call. Since the whole
file is one ELF image, offsets relative to `oatdata` stay valid regardless of
placement, and the section sits beyond `oatlastword` alongside `.bss` and
`.dex`, so nothing that parses the OAT code range is affected. It must precede
`.bss`, which is `SHT_NOBITS` and contributes no file bytes.

The placement costs at most one page. `Section::AddSection()` page-aligns a
section whose `phdr_flags_` differ from the previous section's, and
`MakeProgramHeaders()` merges adjacent `PT_LOAD`s only when flags match and
neither is `.bss`-like. Following `PF_R|PF_W` data with `PF_R` starts a new
segment; when `.data.img.rel.ro` is absent the predecessor is `PF_R|PF_X` text
and a new segment starts anyway. No explicit `phdr_flags_` assignment is needed,
since `PF_R` is already the default.

The section is self-describing and fully validated before use:

```text
OatUnwindHeader {            // 32 bytes, 4-byte aligned
  uint32_t magic;            // 'o','u','w','\n'
  uint32_t version;          // starts at 1; bumped with the OAT version
  uint32_t entry_count;
  uint32_t entries_offset;   // section-relative, 4-byte aligned
  uint32_t unwind_offset;    // section-relative, 4-byte aligned
  uint32_t unwind_size;
  uint32_t code_begin;       // oatexec range, relative to oatdata
  uint32_t code_end;         // exclusive; both bound every entry
}
OatUnwindEntry[entry_count] {     // 12 bytes each, sorted by begin_offset
  uint32_t begin_offset;          // relative to oatdata, inclusive
  uint32_t end_offset;            // relative to oatdata, exclusive
  uint32_t unwind_info_offset;    // relative to oatdata, 4-byte aligned
}
uint8_t unwind_info_blobs[unwind_size];   // deduplicated UNWIND_INFO bytes
```

Design points, each chosen against a rejected alternative:

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
  cross builds. `OatUnwindEntry` is the same three 32-bit fields in the same
  order, so the runtime can build the SDK array by a checked field-by-field
  copy rather than a reinterpret cast. Nothing depends on the layouts being
  identical.
- **Entries are sorted and non-overlapping in the file.** Windows requires a
  sorted table for binary search. Sorting at write time makes the runtime
  check an O(n) verification rather than a sort, and a sort failure is a
  writer bug the loader should surface rather than repair.
- **The unwind blobs are deduplicated but the entries are not.** Every code
  range gets exactly one entry; identical frame shapes share one blob.
- **The table is one registration, not one per method.** The JIT uses one
  one-entry table per allocation because allocations come and go. Boot OAT is
  a single process-lifetime range, so one multi-entry registration is both
  cheaper and simpler to unregister.

Two new dynamic anchors make the section discoverable through the existing
`ElfFile::FindDynamicSymbolAddress()` path, extending `DynamicSymbol` and
keeping the restricted allow-list closed:

```text
oatunwind, oatunwindlastword
```

The names follow the existing all-lowercase, no-separator convention
(`oatbsslastword`, `oatdataimgrelrolastword`). Both are appended after
`kOatDexLastWord` in `ElfBuilder::DynamicSymbol` and added to
`GetDynamicSymbolName()`; `kLast` moves to `kOatUnwindLastWord` so
`kDynamicSymbolCount` grows with them. `kDynamicEntriesCount` is unrelated and
does not change: these are `.dynsym` entries, not `.dynamic` entries.

The loader rejects an OAT that has quick code but no `oatunwind`, and rejects
`oatunwind` outside an R segment. Because the anchors are additive and the
section is new, the OAT version must be incremented in the same change; a
stale artifact then rejects by version rather than by a missing anchor.

### Writer integration and dedup-safe offsets

The writer already assigns final code offsets and already deduplicates
identical compiled code, so two methods can share one code range. The unwind
table must key on the final code range, not on the method.

`CompiledMethodStorage::DeduplicateCode()` interns identical code bytes to a
single allocation, and `InitCodeMethodVisitor` then dedups on the code *pointer*
(`CodeOffsetsKeyComparator` compares `GetQuickCode().data()`, per its own
comment "Code is deduplicated by CompilerDriver"). Two methods therefore share a
code offset exactly when they share that pointer, and the writer already tracks
this in its `deduped` flag. Under `--deduplicate-code=false` no interning
happens, every method keeps a distinct pointer, and every method gets its own
entry; both modes are correct under the rules below.

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
   `OatWriter::GetUnwindSize()` alongside the existing `GetCodeSize()` and
   `GetBssSize()` getters, and pass it as one more `PrepareDynamicSection()`
   argument through `ElfWriter`, `ElfWriterQuick`, and `ElfBuilder`. Because
   every code offset is final once `InitOatCodeDexFiles()` returns, the table is
   fully computable there; nothing later moves the ranges it describes.
4. Add `.oat_unwind` to `ElfBuilder` as a `Section` member declared and
   constructed between `data_img_rel_ro_` and `bss_` — `SHT_PROGBITS`,
   `SHF_ALLOC` without `SHF_EXECINSTR`, `kElfSegmentAlignment` since it always
   opens a new segment — and call `AllocateVirtualMemory()` on it in
   `PrepareDynamicSection()` in that same position, because declaration order in
   `sections_` is what fixes segment layout. Follow the established
   conditional-add pattern: when the size is zero, emit neither the section nor
   its anchors, exactly as `.bss` and `.dex` do. Add the
   two anchors in `PrepareDynamicSection()` with `dynsym_.Add(..., STB_GLOBAL,
   STT_OBJECT)`, giving `oatunwind` the section address and full size, and
   `oatunwindlastword` the last four bytes with size 4, matching the existing
   `oatbss`/`oatbsslastword` pair.
5. Write the bytes from a new `OatWriter::WriteUnwind()` reached through a new
   `WriteState::kWriteUnwind` placed after `kWriteDataImgRelRo`, so the buffer is
   emitted last among the `PROGBITS` sections and before the header is finalized.
   Mirror `WriteDataImgRelRo()`: wrap the stream in
   `ChecksumUpdatingOutputStream`, account the padding and payload in a
   `size_oat_unwind_*` stat pair for the `DO_STAT` block, and finish with
   `CheckOatSize()`. In `dex2oat.cc`, add a size-guarded
   `StartUnwind()`/`EndUnwind()` pair on `ElfWriter` after the existing
   `.data.img.rel.ro` block and before `WriteHeader()`, matching how that block is
   itself guarded on `GetDataImgRelRoSize() != 0u`.

   The state transitions are the subtle part, because both preceding sections are
   optional and each currently jumps straight to `kWriteHeader` when empty. Route
   every such branch through the unwind state instead: `WriteCode()` selects
   `kWriteDataImgRelRo`, else `kWriteUnwind` if the unwind size is nonzero, else
   `kWriteHeader`; `WriteDataImgRelRo()` selects `kWriteUnwind` if nonzero, else
   `kWriteHeader`; and `WriteUnwind()` always advances to `kWriteHeader`. Each
   branch that ends a section without a successor keeps its existing
   `CheckOatSize()` call, so the size assertion still runs exactly once on the
   final section.
6. Reject at write time rather than emit a broken table: an entry outside the
   `oatexec` range, a range that overlaps its neighbour, a blob that is not
   4-byte aligned, an entry count or section size that does not fit in 32
   bits, or any method with a nonempty frame and no bytes.

The section is part of the OAT checksum, so a truncated or edited table fails
the existing checksum gate before the loader parses it.

### Runtime registration

`WindowsAotUnwindRegistry` mirrors the JIT registry's ownership shape but with
one multi-entry table. It lives beside `jit_unwind_windows` in
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

Registration happens at step 7 of the OAT-1 transaction, after final
protections and `FlushInstructionCache` and before the loader returns an
unpublished owner.

The section bounds come from `OatFileBase::ComputeFields()`, which already
resolves every other anchor pair and is the only place that knows the mapped
addresses. Add `unwind_begin_`/`unwind_end_` there using the established idiom:
a null `oatunwind` means no section and sets both to null, a present `oatunwind`
with a missing `oatunwindlastword` is a hard error, and the end pointer is
readjusted with `+= sizeof(uint32_t)` because the `lastword` symbol addresses the
final four bytes rather than one-past-the-end. That `+4` convention is why the
writer gives `oatunwindlastword` size 4 at `address + size - 4`.

Registration then must, in order:

1. validate the header magic, version, and that every declared subrange lies
   inside the section;
2. validate `code_begin`/`code_end` against the mapped `oatexec` range
   resolved from the dynamic anchors;
3. validate each entry: `begin_offset < end_offset`, both inside the code
   range, entries sorted and non-overlapping, and `unwind_info_offset`
   4-byte aligned and inside the section;
4. validate each referenced `UNWIND_INFO`: version 1, no unsupported flags,
   a code count that fits the declared bytes, prologue size within 255,
   frame register and scaled offset within range, `UWOP_*` codes recognized,
   descending prologue offsets, correct 2-byte tail padding, and a chained or
   handler record only where it is itself in range and acyclic;
5. allocate the SDK `RUNTIME_FUNCTION` array in stable native storage, copy
   the three fields per entry with checked arithmetic, and keep the exact
   pointer for later deletion;
6. call `RtlAddFunctionTable(table, entry_count, oatdata_address)`; and
7. prove the registration with `RtlLookupFunctionEntry()` on a representative
   PC from each record kind — a quick method, a JNI stub, and a trampoline —
   requiring the returned base and all three fields to match, then
   `RtlVirtualUnwind()` on one managed frame.

Any failure unregisters, frees the array, and fails the load. The caller then
discards the whole unpublished transaction and continues imageless. A
successful boot keeps the table registered for process lifetime; teardown
unregisters before the shared mapping owner releases the code or the section,
which is the same ordering rule the JIT registry uses.

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
- a writer gate: sorted, non-overlapping, in-range entries and a
  checksum-covered section;
- a layout gate, since the section's placement is what keeps the existing
  assertions true: `.text` still starts at `oatdata + executable_offset`,
  `data_img_rel_ro_start_` still equals the page-aligned end of code, and
  `.oat_unwind` still precedes `.bss` — asserted with and without
  `.data.img.rel.ro` present, because the predecessor section and therefore the
  segment split differ between those two cases;
- a loader gate: each malformed-table class above rejects the load and falls
  back imageless, with no function table left registered;
- a native gate on Server 2025: `RtlLookupFunctionEntry()` resolves a
  representative quick, JNI, and trampoline PC, and `RtlVirtualUnwind()`
  restores the `RBP`-anchored frame from a boot-OAT method; and
- a native exception gate: a managed throw, a translated NPE, and a fatal dump
  each walk through boot-OAT frames with correct nonvolatile restoration.

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
  unwind data.

Early bring-up selects the existing imageless nterp/JIT product as the
fallback. A failed attempt must discard the entire unpublished boot image/OAT
transaction and continue imageless; this behavior requires a native test and
must not be inferred from a successful `-showversion` smoke run.

### Implementation sequence

1. Execute the existing characterization tests, closing H-005 rather than
   relying only on syntax/build evidence.
2. Add the Windows private-copy mode under `ElfOatFile` and test exact
   reservation consumption, byte copy, zero-fill, whole-span ownership,
   protections, and failure cleanup with generated structural artifacts.
3. Add the VDEX private-copy handoff and validate exact aperture size,
   ownership, and `ComputeFields -> LoadVdex -> Setup` ordering.
4. Implement the specified AOT unwind transport in order: the
   `EmitWindowsX64UnwindInfo()` predicate, the `CompiledMethod` array and its
   dedup, the `OatWriter` entry collection and `.oat_unwind` emission with the
   two new anchors and an OAT version bump, then `WindowsAotUnwindRegistry`.
5. Build and stage the Windows `boot.art`, `boot.oat`, and `boot.vdex` set with
   unchanged ELF identity/alignment and the selected boot-component topology.
6. Integrate experimental startup selection and verified imageless fallback.
7. On Server 2025, prove representative method entrypoints lie inside the
   boot OAT RX range and execute without JIT compilation; exercise VDEX,
   image relocation, JNI, faults, stack walking, and unwind lookup.
8. Record CFG policy/behavior and OAT-1 startup/commit measurements without
   blocking the initial milestone on OAT-2 or security work.

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

## Publication, rollback, and lifetime

Load state advances only in this order:

```text
opened boot artifacts and structural validation
  -> exact non-executable population
  -> mapped ELF/anchor validation
  -> final OAT protections except the VDEX aperture, then cache flush
  -> .oat_unwind validation, table registration, lookup proof, CFG observation
  -> return an unpublished mapping owner to OatFileBase
  -> VDEX exact population, validation, and data protection
  -> OAT setup plus image validation and relocation
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
unwind metadata.

## Correctness validation and deferred security

Early bring-up consumes trusted boot artifacts produced and staged by the
matching Windows product build. The implementation reuses existing ART ELF,
OAT, VDEX, and image validation, adding focused checks required by the Windows
copy operation:

- checked loaded-span, load-bias, destination, and file-range arithmetic;
- `p_filesz <= p_memsz` and bytes within the opened file region;
- the Linux-identical ELF header fields and 16-KiB segment alignment;
- non-overlapping R/RX/RW load ranges with no W+X segment;
- exact containment of the dynamic anchors, `oatdex`, and unwind table;
- exact reservation-prefix and VDEX-aperture sizes; and
- matching OAT/VDEX/image versions and checksums before publication.

Cache ACLs, path aliases/reparse points, mutation races, hostile-input parser
hardening, cryptographic identity, fuzzing as a security gate, signing, and
AV/EDR policy are explicitly deferred. Correctness fixes that are small,
platform-independent, and useful upstream remain welcome; they are not a
prerequisite for the first trusted boot.

## Windows unwind, faults, and CFG

ELF mappings are not Windows modules. Every AOT function needs a
`RUNTIME_FUNCTION`/`UNWIND_INFO` matching its actual Windows x64 prologue,
epilogues, stack allocation, frame register, and nonvolatile GPR/XMM saves.
This includes the tail-`jmp` trampolines, which take the shared zero-prologue
leaf record rather than no record at all. "AOT unwind format and transport"
above is the concrete design; the requirements restated here are the
acceptance conditions it must satisfy.

Validate before registration:

- sorted non-overlapping functions and `BeginAddress < EndAddress`;
- all 32-bit code/unwind RVAs within registered ranges;
- unwind version, flags, code count, padding, frame register/offset,
  handler/chained record, bounds, acyclicity, and alignment;
- read-only non-executable unwind metadata; and
- functions entirely within RX OAT segments.

After final protection, call `FlushInstructionCache`, then
`RtlAddFunctionTable`. Prove representative PCs with
`RtlLookupFunctionEntry`/`RtlVirtualUnwind` before publication.

The JIT registry supplies ordering precedent, but AOT gates must cover quick,
runtime, JNI, deoptimization, managed exception, translated NPE/SOE, and fatal
frames. Failure before publication unregisters the table; a successful boot
keeps it registered for process lifetime.

CFG remains TBD. Native tests record the process mitigation policy and execute
real indirect quick/JNI/trampoline/method targets. Do not add
`SetProcessValidCallTargets`, disable CFG, or declare CFG compatibility until
those observations establish the required behavior and a separate design
decision selects an integration.

OAT-1 writes only while non-executable and makes code final RX. VDEX, image,
BSS, dynamic, and unwind pages are never executable. These final permissions
are retained as ordinary mapping correctness even though security hardening is
out of the early scope.

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
| 4-/16-/64-KiB confusion | High | Keep `ART_PAGE_SIZE_AGNOSTIC=1`, require 16-KiB ELF alignment, and use private copy across the 64-KiB Windows view boundary |
| Incorrect x64 unwind | Critical | Generate, transport, validate, register, and exercise every code kind, including the leaf trampolines |
| Windows AOT code diverges from Linux by the `RBP` anchor | Medium | Accepted consequence of the §7.9.3 frame rule; compare ELF identity and layout across targets, never code bytes |
| Dedup merges code with mismatched unwind bytes | High | One entry per unique code range; a byte-mismatch on a deduplicated offset fails the `dex2oat` run |
| CFG rejects entrypoints | Open | Record native policy and real indirect-call results; design remains TBD |
| VDEX exact placement/ownership | High | OAT-1 copy into `oatdex` with an owner-sharing `MemMap` slice |
| Boot exact address failure | High | Consume reservation and verify exact result |
| Failed load leaves partial image/OAT state | Critical | One unpublished transaction; discard it before imageless fallback |
| Private-copy memory/startup | High operational | Whole-span commit for simplicity; measure before optimizing |
| Wrong cross-OS boot artifacts staged | High | Windows-target-specific staging plus image/OAT checksums and actual AOT execution tests |
| Boot topology mismatch | High | Explicitly select and test single- or multi-component output |
| Upstream divergence | High | Reuse `ElfOatFile`, `ElfFile`, `OatFileBase`, and the unchanged `ElfBuilder` path |

The aggregate early-bring-up risk is medium/high. It remains lower than PE for
ART semantic correctness because it preserves the writer, offsets,
reservation, load bias, BSS, anchors, and companion artifacts. OAT-1 minimizes
mapping and divergence risk at the cost of per-process commit and copying.

## Required gates

Before claiming Windows AOT support, require:

- native Windows x64 `dex2oat.exe` generation of the selected boot component
  set and deterministic checksummed fields;
- ELF-header comparison proving Linux-identical OSABI/ABI version/flags and
  16-KiB `PT_LOAD` alignment with `ART_PAGE_SIZE_AGNOSTIC=1`;
- exact boot reservation, deliberate collision, relocation-delta, and selected
  single- or multi-component image tests;
- VDEX and ART-image positive/mismatch/truncation/relocation cases;
- `VirtualQuery` proof of R/RX/RW/no-access and no W+X stage;
- execution after `FlushInstructionCache`;
- function-table add/lookup/virtual-unwind and exception/stack-walk coverage for
  compiled methods, JNI stubs, and trampolines, plus the `.oat_unwind`
  writer/loader/dedup gates listed under "Unwind gates";
- proof that representative `ArtMethod` entrypoints lie in the boot OAT RX
  range and execute without JIT compilation;
- real quick/JNI/trampoline/method indirect calls while recording, but not yet
  gating on, the native CFG policy;
- missing, mismatched, reservation-failure, VDEX-failure, setup-failure, and
  unwind-registration-failure cases that continue with imageless nterp/JIT;
- focused GC, roots, deoptimization, translated fault, JNI, reflection, class
  initialization, and fatal-dump execution through boot OAT;
- behavioral execution of the Stage 1 tests currently blocked by H-005; and
- OAT-1 startup time, total committed span, and working-set measurements.

Windows Server 2025 x64 build 26100 is authoritative. Record OS build,
mitigation policy, runtime/compiler/artifact hashes, base/load bias,
reservation/protection maps, unwind and CFG observations, actual AOT
entrypoints, fallback results, and archive hash. Linux protects shared
semantics; Wine is structural only.

The previous PE/`SEC_IMAGE` probe is historical rejection evidence. It must
not grow into another PE prototype.

## Open implementation items

1. Keep and test the current Linux-identical ELF identity and
   page-size-agnostic 16-KiB segment alignment on Windows.
2. Prototype the OAT-1 private-copy mapping under existing
   `ElfOatFile`/`ElfFile`; introduce a separate parser only if this proves
   unworkable without larger changes.
3. Implement exact-reservation whole-span private-copy loading without POSIX
   `MAP_FIXED` emulation.
4. Preserve `oatdex` semantics with a VDEX copy and shared allocation owner.
5. Implement the specified AOT unwind transport: the Windows-and-x86-64
   emission predicate replacing the `IsJitCompiler()` gate, the
   `CompiledMethod` unwind array, dedup-safe `OatWriter` entries, the
   `.oat_unwind` section and anchors, and `WindowsAotUnwindRegistry`.
6. Build native Windows `dex2oat.exe`, define its boot-generation command and
   target-specific staging, and select the initial boot-component topology.
7. Add experimental boot selection and explicit whole-transaction imageless
   fallback.
8. Close H-005 and prove behavioral loader contracts, then prove real boot-OAT
   entrypoints execute on Server 2025.
9. Characterize CFG and measure OAT-1 commit/startup cost.
10. Defer application OAT, unloading, OAT-2, cache security, hostile-input
    hardening, and rich tooling integration to separately reviewed work.

PE32+ OAT is not an open item. Reconsidering it requires an explicit owner
decision and a new design revision.

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

- [CreateFileMappingW](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw)
- [MapViewOfFile3](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3)
- [VirtualAlloc2](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2)
- [VirtualProtect](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect)
- [FlushInstructionCache](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-flushinstructioncache)
- [RtlAddFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable)
- [RtlDeleteFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtldeletefunctiontable)
- [RtlVirtualUnwind](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtlvirtualunwind)
- [SetProcessValidCallTargets](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-setprocessvalidcalltargets)
- [Process dynamic-code policy](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-process_mitigation_dynamic_code_policy)
