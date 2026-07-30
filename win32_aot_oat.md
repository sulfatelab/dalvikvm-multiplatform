# Windows AOT and OAT design

Status: selected design baseline (2026-07-30). This document records the
current ART OAT/VDEX/image contracts and the selected Windows AOT artifact and
loader design. Windows keeps OAT in a restricted ELF64 coat and loads it
through an ART-owned, OAT-only loader. PE32+ OAT is rejected.

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
3. Windows OAT remains ELF64. A dedicated loader preserves ART's exact boot
   reservation, load-bias, independent-instance, BSS, dynamic-anchor, and
   VDEX contracts without becoming a general Windows ELF dynamic linker.
4. PE32+ OAT is rejected. `LoadLibraryExW` cannot consume an ART-owned
   reservation or force an independent instance of the same artifact. A
   manual PE loader would add a new writer and relocation format without
   receiving normal DLL-loader behavior.
5. The first correctness implementation privately copies validated `PT_LOAD`
   bytes into an ART-owned reservation, zeroes BSS, applies final R/RX/RW
   protections, registers Windows x64 unwind data, and publishes entrypoints
   last.
6. A later, separately versioned 64-KiB-aligned ELF layout may use Windows
   placeholders and data-file/pagefile views to recover cross-process code
   sharing. It must match the private-copy loader exactly.
7. Selected validation and segment-layout algorithms may be copied and ported
   from Bionic's `linker_phdr.cpp`, retaining its BSD attribution. The full
   Bionic linker, `soinfo`, dependency, relocation, namespace, TLS,
   constructor, and symbol-interposition machinery are rejected.
8. The loader accepts only an exact Windows OAT-ELF profile. It cannot load
   `libjiagu.so`, a normal ELF DSO, or an arbitrary Android/Linux OAT.
9. Executable-memory capability is an explicit ART product prerequisite. The
   `ProhibitDynamicCode`/ACG operating mode is a non-goal, as are equivalent
   policies that forbid ART's JIT pagefile section or OAT RX mappings. Mapping
   failures remain fail-closed, but such a process is unsupported.

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

The dedicated Windows loader replaces only the narrow Bionic mapping role. It
does not replace `OatFileBase::ComputeFields()`, `LoadVdex()`, `Setup()`, image
relocation, or higher-level publication.

## Selected Windows architecture

### Artifact ownership

| Artifact | Selected treatment | Owner |
|---|---|---|
| OAT | Restricted ELF64 with Windows x64 quick code and unwind data | Dedicated OAT loader |
| VDEX | Read-mostly data, initially populated in the existing `oatdex` range | `VdexFile` inside OAT transaction |
| ART image | Reserved mapping, copy/decompression and ART relocation | `ImageSpace` |

The loader is not exported as `dlopen`, and no other subsystem can ask it to
load an ELF file.

### Explicit non-goals

- PE32+ OAT, `WOAT`, and both normal and manual PE OAT loading.
- A general `.so` loader, including `libjiagu.so`.
- `DT_NEEDED`, PLT/GOT binding, REL/RELA/JMPREL, IFUNC, text relocation, TLS,
  constructors/destructors, symbol interposition, or namespaces.
- Private `Ldrp*`, undocumented loader-list manipulation, or kernel `Zw*`
  interfaces.
- `ProhibitDynamicCode`/ACG compatibility or any policy bypass such as
  `AllowThreadOptOut`.
- Automatic Windows module enumeration, Authenticode image treatment, or
  debugger/profiler behavior equivalent to a DLL.

CFG remains required. CET user shadow stacks remain unsupported under the
existing Windows process contract.

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

Acceptable reuse is limited to:

| Area | Treatment |
|---|---|
| ELF identity, header, and program-table validation | Port selected `ElfReader` logic and harden it |
| Checked file ranges and load-span/load-bias calculation | Port algorithms with complete overflow checks |
| Segment zero-fill and PHDR containment rules | Reuse semantics, not POSIX calls |
| POSIX `mmap(MAP_FIXED)` backend | Do not copy |
| `soinfo`, dependencies, relocations, namespaces, TLS, constructors | Do not copy or implement |
| OAT anchor lookup | Parse only the restricted dynamic table in the dedicated loader; keep `OatFileBase::ComputeFields()` unchanged |
| Logical OAT validation | Keep existing `OatFile` setup logic; make independent upstream-quality bounds fixes separately |
| Windows reservation/protection/unwind/CFG/lifetime | New documented Win32 implementation |

Bionic's `linker_phdr.cpp` is BSD-licensed. Copied code retains its copyright,
conditions, disclaimer, source provenance, pinned tag, and required binary
distribution notice.

Bionic remains a compatibility-oriented DSO loader. Windows OAT must be
stricter: malformed alignment, W+X, unknown tags, and unsupported layouts are
hard failures regardless of target SDK.

## Restricted Windows OAT-ELF profile

### ELF header and program headers

Accept only:

- ELF64, little-endian, `ET_DYN`, `EM_X86_64`;
- exact Windows ART coat/quick-ABI identity;
- `e_entry == 0`;
- exact ELF/program-header structure sizes;
- a nonzero bounded header count no larger than the writer maximum;
- one `PT_PHDR`, one or more `PT_LOAD`, exactly one `PT_DYNAMIC`, and only
  versioned allowed notes;
- R, RX, and RW segments, never W+X or execute-without-read;
- `p_filesz <= p_memsz`;
- canonical power-of-two alignment for the coat version;
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
oatdex, oatdexlastword
```

Validate complete dynamic/string/symbol/hash ranges, exact entry sizes, bounded
counts, in-range NUL termination, bucket/chain indexes and termination,
uniqueness, binding/type, and containment in the correct R/RX/RW segment.

Because the anchor set is tiny, a bounded validated symbol scan is preferable
to a general unbounded hash walk. A future Windows ELF note may duplicate a
compact region descriptor, but the coat remains ELF.

### Version gates

Windows artifacts carry independent identities for:

1. logical OAT metadata;
2. Windows OAT-ELF coat, mapping alignment, quick ABI, and unwind encoding; and
3. VDEX/ART image formats and cross-artifact checksums.

Also validate compiler/runtime build, pointer size, ISA/features, boot class
path, image requirement, compiler filter, and class-loader context. Unknown
versions or flags reject; they are never guessed.

## Windows mapping design

### 4-KiB ELF versus 64-KiB views

Windows protects committed pages at ordinary page boundaries but requires
file-view offsets and bases to satisfy the allocation granularity, normally
64 KiB. The current Windows `MemMap` file path cannot map over an occupied
`VirtualAlloc` reservation and cannot reproduce POSIX `MAP_FIXED` for arbitrary
4-KiB ELF offsets.

Do not mechanically port Bionic's:

```text
reserve complete PROT_NONE span
MAP_FIXED each PT_LOAD over the reservation
```

The Windows backend has two explicit implementations.

### OAT-1: private-copy correctness loader

OAT-1 uses one ART-owned private allocation and works with the current 4-KiB
ELF layout, exact boot placement, duplicate instances, and existing committed
`PAGE_NOACCESS` reservations.

Load transaction:

1. Open OAT through one stable file-region handle and deny mutation according
   to cache policy.
2. Validate raw ELF headers, tables, ranges, coat identity, dynamic anchors,
   and unwind data without executable memory.
3. Calculate span/load bias with checked arithmetic.
4. Consume the exact caller reservation or create a correctly aligned low/
   unrestricted reservation as required.
5. Commit only declared load pages; leave gaps no-access.
6. Make destinations writable and non-executable, read validated bytes from the
   retained handle, and zero every `p_memsz - p_filesz` byte including BSS.
   Keep only the validated `oatdex` aperture writable for the later handoff.
7. Validate mapped dynamic anchors, apply final protections to all other OAT
   ranges, flush executable ranges, and register/validate unwind and CFG.
8. Return the unpublished loader handle to `OatFileBase`.
9. Open VDEX through a stable handle, populate and validate it in the exact
   `oatdex` aperture, then apply its final data protection.
10. Run existing logical OAT/dex/BSS/class-loader setup and image validation/
    relocation.
11. Publish the generated-code range, roots, and method entrypoints only after
    the complete artifact set succeeds.

OAT-1 is the correctness oracle. It avoids placeholder splitting, file-view
alignment, overlap, fragmented ownership, and replacement rollback.

Costs:

- private code and copied VDEX consume per-process commit;
- startup performs reads and copies;
- normal DLL signing, module enumeration, image telemetry, and automatic unwind
  discovery do not apply; and
- manual executable pages receive more AV/EDR scrutiny.

These costs are accepted for bring-up. Production enablement requires measured
startup and memory results.

### OAT-2: shared 64-KiB ELF views

OAT-2 remains ELF but uses a new coat version and aligns every backing/
protection group to the Windows allocation granularity.

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

`SEC_IMAGE` is not used. OAT-2 must produce the same addresses, bytes, anchors,
BSS/VDEX contents, protections, unwind, and execution as OAT-1. OAT-1 remains
the oracle until authoritative native equivalence passes.

### Placement and duplicate instances

Boot OAT must begin at the image-recorded address after the selected relocation
delta. Hints are never exact guarantees. Collision, fragmentation, overflow,
or a different returned address rejects image-backed AOT without touching
unrelated memory.

Application OAT may use another valid base subject to low-address and code
reach constraints. Each logical load gets independent BSS, roots, dex-cache
slots, and image-specific relocation state. OAT-2 may share only immutable
physical pages.

Every signed-32-bit RIP-relative/branch encoding and unsigned-32-bit OAT/
`CodeInfo` offset must remain representable. Generation and load reject rather
than truncate.

### VDEX and image mapping

OAT-1 preserves `oatdex` by copying/populating VDEX in that range. This avoids
an immediate adjacency refactor and 64-KiB exact-view problem.

OAT-2 may map an aligned VDEX view there or adopt an independently versioned
separate mapping only after proving that code, image relocation, dex-cache
setup, and class unloading do not depend on adjacency.

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
6. run `ElfBuilder` with the selected Windows coat/layout policy;
7. emit only restricted dynamic anchors and no ELF imports/relocations;
8. emit bounded Windows function/unwind tables in read-only loadable data;
9. emit matching ART image/cross-artifact identity; and
10. flush, close, reopen, validate, then atomically publish immutable cache
    files.

OAT-1 retains ordinary logical segment alignment. OAT-2 emits the 64-KiB view
group alignment and padding under a different coat version.

Output is deterministic for checksummed fields. Build paths, timestamps,
debug-only data, and command lines are normalized or excluded by explicit rule.

## Loader components and ownership

Keep responsibilities separate:

1. `WindowsOatElfLoader`: the ART-facing handle and transaction owner. Its
   private validator is the bounded parser for the restricted ELF/dynamic
   profile.
2. `WindowsOatElfMapping`: an internal detail of that loader for reservation,
   OAT-1 copy or OAT-2 views, protections, cache flush, ownership, and
   rollback.
3. Existing `OatFileBase`: OAT anchor requirements, dex, BSS, VDEX, image, and
   class-loader semantics. `ElfOatFile` remains only the generic
   non-executable/host fallback, not a Windows executable-OAT path.
4. `WindowsAotUnwindRegistry`: fixed function-table validation and
   `RtlAddFunctionTable`/`RtlDeleteFunctionTable` lifetime.
5. Existing generated-code registry: fault/stack readers and publication
   ordering shared with nterp/JIT.

Do not hide the OAT mapper behind general POSIX `mmap` emulation. One explicit
transaction owner owns either the private allocation or the complete view/
placeholder set.

## Upstream-thin code-change plan

### Compatibility shape

From `OatFile`'s perspective, `WindowsOatElfLoader` serves the narrow role that
`android_dlopen_ext()` serves on Android, but it is deliberately not named or
exported as `dlopen`. The semantic correspondence is:

| Android/Bionic operation | Windows OAT-only operation |
|---|---|
| `android_dlopen_ext(path, RTLD_NOW, extinfo)` | `WindowsOatElfLoader::Open(source, options)` |
| `ANDROID_DLEXT_FORCE_LOAD` | Inherent: every `Open()` creates a distinct handle and mapping |
| `ANDROID_DLEXT_RESERVED_ADDRESS` | Exact consumption of the caller's validated ART reservation |
| `dlsym(handle, anchor)` | `handle->FindDynamicSymbolAddress(anchor)` |
| `dladdr(anchor)` | `handle->BaseAddress()` |
| `dl_iterate_phdr()` map discovery | Handle-owned validated segment descriptors and `MemMap`s |
| `dlclose(handle)` | RAII destruction with reverse-order unregister and rollback |
| Bionic namespace selection | None: imports, dependencies, and search paths are rejected |

The handle remains internal to ART. It must not accept ordinary `.so` callers,
return a Windows `HMODULE`, enter the PEB loader lists, or emulate global ELF
symbol lookup.

### File boundary

Add `runtime/oat/windows_oat_elf_loader.h` and
`runtime/oat/windows_oat_elf_loader.cc`, built only for the Windows target. The
header exposes one move-only/RAII handle with only these concepts:

- open a stable file region obtained from a path/ZIP entry or duplicated fd;
- exact reservation and `low_4gb` options;
- lookup of a named OAT dynamic anchor;
- loaded base and validated span queries; and
- close/rollback by destruction.

The `.cc` owns all restricted-ELF parsing, selected Bionic-derived
`ElfReader`/program-header algorithms, checked load-bias calculation, OAT-1
population, final protection, unwind/CFG integration, map ownership, and
failure unwind. Keep the copied BSD notices and exact AOSP tag/function
provenance in this file and in distribution notices. Do not place copied
Bionic code in `elf_file_impl.h`, `mem_map_windows.cc`, or a fake Win32
`dlfcn` layer.

The open operation must acquire one stable file identity before parsing and
retain or duplicate the underlying Windows handle until all bytes are
populated. Path reopening after validation is forbidden. ZIP/SDM support uses
ART's existing `OS::OpenFileDirectlyOrFromZip()` to produce a bounded file
region; the OAT loader does not become a ZIP loader.

### Thin changes to upstream ART files

Keep `runtime/oat/oat_file.h` unchanged. In `runtime/oat/oat_file.cc`, make
only locally guarded integration changes:

1. Include the Windows loader header under `ART_TARGET_WINDOWS`.
2. Reuse the existing `DlOpenOatFile` state machine. On Windows, its handle is
   a `WindowsOatElfLoader` RAII object rather than a Bionic `void*` handle.
3. Delegate `Load()`, `FindDynamicSymbolAddress()`, `ComputeElfBegin()`, and
   destruction to that handle. `PreLoad()` and `PreSetup()` are Windows
   no-ops because the handle already owns and describes its mappings.
4. Permit the Windows backend to satisfy `low_4gb` and exact-reservation
   requests. Do not weaken the existing Android/host dlopen checks.
5. Add the Windows implementation of the fd `Load()` overload and select it
   for executable fd-based OAT. It must duplicate the source handle and apply
   the same identity and bounds checks as path-based loading.
6. After a Windows executable load is rejected, return the error. Never fall
   back to `ElfOatFile`, because that would bypass the restricted profile,
   unwind/CFG registration, stable-file transaction, and fail-closed policy.
   Preserve `ElfOatFile` for non-executable inspection/cross-compilation.
7. Apply the same no-bypass rule to `OpenFromSdm()` and any later executable
   entry point.

Do not fork `OatFileBase::ComputeFields()`, `Setup()`, dex/BSS interpretation,
class-loader checks, or public `OatFile` APIs. Keep Android, Linux-host, and
Fuchsia control flow unchanged outside the guarded calls. The desired merge
shape is a few obvious Windows dispatch blocks around an otherwise upstream
`oat_file.cc`, with all policy and mechanics in the dedicated file.

`runtime/oat/elf_file.cc` and `elf_file_impl.h` require no Windows executable
loader changes for OAT-1. Generic parser hardening may still be contributed as
separate, platform-independent correctness work, but the Windows security
boundary must not depend on carrying a large downstream `ElfFile` fork.

### VDEX handoff without widening `OatFile`

There is one necessary adjacent Windows change. The ELF `.dex` section is
`SHT_NOBITS`; Android first obtains zero pages from Bionic and then replaces
them with VDEX using `mmap(MAP_FIXED)`. A Windows OAT-1 private allocation
cannot be replaced in-place by `MapViewOfFileEx()`.

Preserve the existing `OatFileBase::LoadVdex()` call and `oatdex` contract.
Add a Windows-private-copy reuse path in `VdexFile::OpenAtAddress()` backed by
a narrowly named Windows `MemMap` helper. When `mmap_reuse=true` identifies a
validated subrange of the loader's private allocation, copy the stable VDEX
file bytes into that writable range, validate them there, apply the final data
protection, and return a `MemMap` sharing the allocation owner. Reject partial
ranges, aliases, changed file identity, misalignment, size disagreement, or a
range not owned by the current OAT transaction.

This keeps `oat_file.cc` unaware of the Windows copy mechanism and preserves
the upstream order `ComputeFields -> LoadVdex -> Setup`. OAT-2 may replace this
helper with aligned placeholder/file views only after equivalence is proved;
it must not change the `OatFileBase` contract.

### Implementation sequence

1. Add characterization tests for Android/Linux-host loader selection,
   duplicate instances, reservation handling, dynamic anchors, path/ZIP and fd
   inputs, fallback, and teardown before changing dispatch.
2. Add the dedicated Windows loader and parser tests while it is unreachable
   from `OatFile`. Start with raw validation, checked span/load bias, stable
   file identity, OAT-1 copy/zero-fill, and complete failure rollback.
3. Add the thin `DlOpenOatFile` Windows delegation and executable no-fallback
   rule. Confirm all non-Windows tests and generated diffs remain unchanged.
4. Add the VDEX private-copy reuse handoff and cross-artifact size/identity
   tests, then exercise path, ZIP/SDM, and fd entry points.
5. Add final R/RX/RW protection, instruction-cache flush, Windows x64 unwind,
   CFG, generated-code range integration, and reverse-order teardown. The
   handle may become executable before `OatFileBase::Setup()` finishes, but no
   method entrypoint may be published; any later failure destroys the handle
   and unregisters everything.
6. Add malformed-ELF/VDEX fuzzing, duplicate-load and unload races, injected
   failure at every transaction stage, and authoritative Windows Server 2025
   gates before enabling executable OAT.
7. Add Windows writer/coat identity and unwind emission only after the loader
   accepts synthetic restricted artifacts. Keep writer changes independent of
   Android's ELF output path.

Review each upstream ART update against two invariants: no Windows executable
OAT can reach `ElfOatFile`, and no copied linker policy leaks out of
`windows_oat_elf_loader.cc`.

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
Windows dispatch must preserve or explicitly replace. They do not relax the
future Windows no-fallback rule. In particular, the current fd and SDM fallback
results are baselines that must change when Windows executable OAT is wired to
`WindowsOatElfLoader`.

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

## Publication and unload

Load state advances only in this order:

```text
stable handles and raw validation
  -> exact non-executable population
  -> mapped ELF/anchor validation
  -> final OAT protections except the VDEX aperture, then cache flush
  -> unwind registration and CFG validation
  -> return an unpublished loader handle to OatFileBase
  -> VDEX exact population, validation, and data protection
  -> OAT setup plus image validation and relocation
  -> generated-code range publication
  -> roots and method entrypoints
```

This matches the existing `android_dlopen_ext()` shape: executable mappings
exist before `OatFileBase::Setup()`, but no `ArtMethod`, root, image field, or
generated-code range reader can acquire them. Failure after loader return
destroys the RAII handle, reverses the completed prefix, and returns no
executable `OatFile`.

Unload reverses publication:

1. prevent new entrypoint acquisition;
2. clear/redirect method entrypoints and roots;
3. remove the code range;
4. wait until no thread can execute, deoptimize, inspect metadata, walk, or
   dispatch an exception through it;
5. call `RtlDeleteFunctionTable`;
6. release VDEX/image/BSS/code mappings; and
7. retire registry/cache state.

If quiescence or function-table deletion cannot be proved, retain the mapping
rather than leave a stale pointer into freed memory.

## Trust-boundary hardening

### Required dedicated-loader hardening

The private parser in `windows_oat_elf_loader.cc` must provide:

- checked program/section-table add/multiply arithmetic;
- exact header entry sizes;
- bounded program-header count and loaded span;
- checked file/virtual/range/rounding/load-bias/base arithmetic;
- canonical alignment and congruence;
- segment/page overlap rejection;
- unconditional W+X rejection;
- exactly one fully contained `PT_DYNAMIC` with an entry-size multiple;
- program-header and dynamic-tag allowlists;
- full-range string/symbol/hash/dynamic/anchor validation;
- bounded terminating scans;
- unique role-correct anchors; and
- errors instead of fatal `CHECK` behavior for malformed files.

Selected Bionic validation is useful but not sufficient. Fuzz raw parsing and
mapped-anchor validation separately without executable pages. Do not obtain
these guarantees by expanding the downstream diff in `elf_file.cc` or
`elf_file_impl.h`. Equivalent generic `ElfFile` fixes remain desirable only
when they are platform-independent and independently testable.

### File identity and cache

Eligible artifacts live in an ACL-controlled local cache. Reject relative,
current-directory, device/UNC, remote, and reparse paths unless a later policy
explicitly allows them. Identify files by stable volume/file identity plus
cryptographic runtime/content identity, not path spelling alone.

Retain the validated handles, deny write/delete sharing under cache policy,
verify final path/file ID, and execute only bytes read from those handles.
Writers create new files, flush/close, reopen/validate, and atomically publish
checksum/version names. Never overwrite a live eligible artifact.

### Range and integer rules

All offsets, counts, sizes, addresses, alignments, and roundings use checked
operations before pointer construction. Reject:

- any header/table/range outside the actual file or loaded span;
- count-times-size, sign conversion, zero-wrap, rounding, load-bias, or
  base-plus-offset overflow;
- `p_filesz > p_memsz` or file bytes past EOF;
- no load segments or an oversized/near-4-GiB span;
- overlapping file/virtual/page ranges or conflicting permissions;
- truncated, cyclic, unterminated, or out-of-range dynamic metadata;
- OAT/VDEX/image tables escaping their owning region;
- duplicate/missing/unknown required regions or anchors;
- writable unwind metadata after publication; and
- executable bytes outside both a validated RX segment and ART code range.

Non-loadable debug data may be ignored only when it cannot affect execution,
lookup, unwind, or checksums.

## Windows unwind, faults, and CFG

ELF mappings are not Windows modules. Every non-leaf AOT function needs a
`RUNTIME_FUNCTION`/`UNWIND_INFO` matching its actual Windows x64 prologue,
epilogues, stack allocation, frame register, and nonvolatile GPR/XMM saves.

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
frames. Unload deletes the table before releasing metadata/code and verifies
lookup disappearance.

CFG is required. Every indirect quick/JNI/trampoline/method target must be
legal for CFG-instrumented callers. Use documented
`SetProcessValidCallTargets` where necessary; do not disable CFG or broadly
authorize unvalidated bytes.

DEP/NX and W^X are mandatory. OAT-1 writes only while non-executable and makes
code final RX. OAT-2 has RX code and no writable executable alias. VDEX, image,
BSS, dynamic, and unwind pages are never executable.

### Execmem product requirement

`ProhibitDynamicCode`/ACG is not a compatibility gate. A negative probe may
confirm clean Windows rejection, but success under that policy is neither
promised nor pursued. Deployment must permit ART-created executable memory for
the JIT and OAT loader. Do not add `AllowThreadOptOut` or a mitigation bypass.

The current runtime may defensively continue without a JIT cache after a
mapping failure. That behavior does not make a `ProhibitDynamicCode` process a
supported product configuration.

### Debugger and security tools

ELF OAT is absent from normal PE module enumeration, image-load telemetry,
automatic static unwind discovery, and normal Authenticode image treatment.
ART must publish a code/module record for debuggers, profilers, symbolizers,
and dumps, containing artifact identity, base/span, methods, and unwind state.

Manual executable mappings may receive AV/EDR scrutiny. This is an accepted
architecture risk, not a reason to reintroduce manual PE. Stable cache paths,
ACLs, hashes, deterministic output, protection sequences, and native
observations must be documented.

## Risk register

| Risk | Initial severity | Control |
|---|---:|---|
| Parser memory-safety failure | High | Restricted profile, checked arithmetic, bounded scans, fuzzing |
| Literal POSIX mapping port | Critical | No `MAP_FIXED` emulation; use OAT-1 |
| 4-KiB/64-KiB confusion | High | Private copy first; versioned OAT-2 |
| Incorrect x64 unwind | Critical | Generate, validate, register, exercise, delete |
| CFG rejects entrypoints | High | Server 2025 target/execution gates |
| `ProhibitDynamicCode`/ACG | Incompatible by design | Execmem prerequisite; fail closed, no support claim |
| Shared BSS/root state | High | Private logical instances and stress tests |
| VDEX exact placement | High | OAT-1 copy; aligned OAT-2 or proven refactor |
| Boot exact address failure | High | Consume reservation and verify exact result |
| Use-after-unmap/unwind | Critical | Unpublish, quiesce, delete table, release |
| Private-copy memory/startup | High operational | Measure; OAT-2 after equivalence |
| No normal DLL identity | Medium/high | ART module/dump/symbol records |
| AV/EDR false positive | Medium/high | Stable deterministic cache/mapping behavior |
| OAT/compiler drift | High | Exact build/version/feature identity |
| Bionic drift | Medium | Pin tag, copied boundary, provenance tests |
| BSD notice omitted | Low | Preserve source and binary notices |
| Rollback corrupts reservation | High | Prevalidation, transaction owner, failure injection |

The aggregate risk is medium/high. It remains lower than PE for ART semantic
correctness because it preserves the writer, offsets, reservation, load bias,
BSS, anchors, and companions. OAT-1 minimizes mapping risk and maximizes memory
cost; OAT-2 trades more mapping/rollback risk for sharing.

## Required gates

Before claiming Windows AOT support, require:

- deterministic Windows `dex2oat` output and artifact hashes;
- parser fuzzing for truncation, overflow, overlap, cycles, bad strings/
  symbols, W+X, forbidden tags, wrong ABI/version, and unwind corruption;
- exact boot reservation, deliberate collision, low-address exhaustion,
  relocation delta, and multi-component image tests;
- independently placed app OAT and two identical-byte instances with isolated
  BSS/dex-cache/root/relro state;
- VDEX and ART-image positive/mismatch/truncation/relocation cases;
- `VirtualQuery` proof of R/RX/RW/no-access and no W+X stage;
- execution after `FlushInstructionCache`;
- function-table add/lookup/virtual-unwind/exception/delete/disappearance;
- CFG-enabled real quick/JNI/trampoline/method indirect calls;
- a negative `ProhibitDynamicCode` test proving clean unsupported-policy
  rejection, never reported as supported execution;
- failure injection and load/unload/address-reuse churn;
- concurrent execution, stack walking, GC, roots, deoptimization, faults, JNI,
  reflection, class initialization/unloading, and fatal dumps;
- stable-handle/cache replacement, alias, hard-link, reparse, partial
  publication, recovery, and cleanup cases; and
- private-copy cost, then exact OAT-1/OAT-2 equivalence if OAT-2 is built.

Windows Server 2025 x64 build 26100 is authoritative. Record OS build,
mitigation policy, runtime/compiler/artifact hashes, file identity, base/load
bias, reservation/protection maps, unwind and CFG results, dump scan, and
archive hash. Linux protects shared semantics; Wine is structural only.

The previous PE/`SEC_IMAGE` probe is historical rejection evidence. It must
not grow into another PE prototype.

## Open implementation items

1. Define the Windows OAT-ELF coat identity and exact OAT-1 profile.
2. Add the private validator in `WindowsOatElfLoader`; do not route Windows
   executable OAT through generic `ElfFile`.
3. Record copied Bionic functions, pinned tag, BSD headers, and binary notice.
4. Implement OAT-1 exact-reservation/private-copy loading without POSIX
   `MAP_FIXED` emulation.
5. Preserve and validate initial `oatdex`/VDEX semantics.
6. Generate/validate/register Windows x64 AOT unwind for methods/trampolines.
7. Implement CFG, cache flush, publication, quiescent unload, and failure
   injection.
8. Define immutable cache, ACL, identity, alias, rollback, symbol, and cleanup
   policy.
9. Run fuzz, Linux, Wine, and authoritative Server 2025 gates before enabling
   executable OAT.
10. Measure OAT-1. Implement 64-KiB OAT-2 only if justified and equivalent.
11. Select boot, app, or combined enablement after those results.

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
