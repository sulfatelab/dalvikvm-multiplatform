# Windows AOT and OAT design

Status: design baseline (2026-07-30).  This document records the current Linux
OAT/VDEX/image formats and the proposed Windows AOT artifact model.  It does
not claim that Windows PE OAT generation or loading is implemented.  The
authoritative native acceptance host for the future implementation is Windows
Server 2025 Datacenter Evaluation, x64 build 26100; Linux and Wine remain
development and structural gates.

The relevant source snapshot is the `vendor/art` submodule at
`android-16.0.0_r4-75-g365cd83ec3`.  The current project is imageless plus
interpreter/JIT on Windows.  AOT is an independent future track.

## Executive conclusions

1. OAT is an ART implementation artifact, not a public stable application
   binary interface.  The magic and version fields are deliberately visible,
   but the runtime and compiler require an exact matching version and layout.
2. The logical OAT records are relatively compact and reusable across
   containers.  The current executable container is not portable: it is an
   ELF shared-object layout with ELF program headers, dynamic symbols, and
   `dlopen`/`ElfFile` loading assumptions.
3. The format changes often enough that a Windows port must not promise to load
   arbitrary Linux or future Android OAT files.  It must publish and validate a
   project-owned Windows container version together with the ART, compiler,
   instruction-set, VDEX, and image identities.
4. The recommended Windows design preserves the useful logical OAT metadata,
   emits it in a PE/COFF-backed image with explicit OAT region descriptors, and
   uses an ART-owned PE mapper.  The normal Windows DLL loader is not the
   authority for OAT lifetime, reservation, relocation, or multiple instances.

## Is OAT public and stable?

### What is stable enough to reuse

The following concepts are the durable ART contract within one matching ART
runtime/compiler build:

- `OatHeader` magic (`oat\n`), version, instruction set and instruction-set
  feature bitmap;
- the OAT checksum and key/value store (compiler filter, class path, boot class
  path and checksums, image requirement, and related build identity);
- per-dex records (`OatDexFile`), dex checksums/locations, class offsets, method
  offset records, and compiled/interpreted class state;
- `OatQuickMethodHeader`, `CodeInfo`, stack maps, dex-register maps, and the
  association between an `ArtMethod` and its compiled entrypoint;
- optional relocation/BSS metadata used to connect code to an ART image and to
  lazily resolved methods, types, strings, and GC roots.

These are implementation contracts between `dex2oat`, the compiler, the ART
runtime, and tools such as `oatdump`.  They are not a Java API, JNI ABI, or
third-party interchange format.

### What is not stable

The following are volatile and must be treated as internal:

- the size and field layout of packed structs;
- the meaning and ordering of offsets after a compiler/runtime change;
- quick entrypoint and `QuickEntryPoints` layout;
- code-generation ABI, instruction-set feature assumptions, and relocation
  encodings;
- the ELF/PE section and program-header arrangement;
- dynamic-symbol names used as loader anchors;
- VDEX sections, verifier dependency encoding, type-lookup tables, and whether
  DEX is embedded in OAT or stored only in VDEX;
- ART image section ordering, object layout, pointer size, and relocation rules.

The project must therefore treat an OAT file like a compiled cache: generate it
with the same ART/compiler snapshot that will load it, reject mismatches, and
regenerate it after an incompatible runtime or compiler change.

### Does the structure change often?

Yes, although not every ART commit changes the on-disk format.  In the current
upstream history, loader-visible changes include:

| Date | Upstream change | Consequence |
|---|---|---|
| 2024-04 | Renamed `.data.bimg.rel.ro` to `.data.img.rel.ro` | Loader/writer symbol and section contract changed. |
| 2024-10 | Stored app-image methods in `.data.img.rel.ro` | Relocation/BSS layout changed. |
| 2024-12 | Reduced `.rodata` alignment | ELF placement and alignment assumptions changed. |
| 2025-01 | Moved dynamic sections to the start of OAT | ELF file layout and loader discovery changed. |
| 2025-02 | Incremented odex/OAT version to avoid a released version collision | Old artifacts were intentionally rejected. |
| 2026-01 | Removed a VDEX section from OAT | OAT/VDEX coupling and OAT version changed. |
| 2026-03 | Bumped OAT version after a revert | Even a reverted semantic change required invalidating artifacts. |

The source itself makes the policy explicit: `OatHeader::CheckOatVersion()`
compares the compiler/runtime version, and `OatHeaderSizeCheck` says that a
packed-size change is a reason to bump `kOatVersion`.

The current project snapshot has:

| Artifact | Magic/version in this tree | Independent version gate |
|---|---|---|
| OAT logical header | `oat\n`, `265\0` | `OatHeader::IsValid()` / `CheckOatVersion()` |
| VDEX | `vdex`, `027\0`, four section descriptors | `VdexFileHeader::IsValid()` |
| ART image | `art\n`, `118\0` | `ImageHeader::IsValid()` |

Those values describe this pinned source snapshot only.  They are not a
Windows compatibility promise and should not be copied as a permanent Windows
format number.

## Current Linux artifact set

A normal ART AOT boot build produces three related artifacts:

```text
boot.art    ART heap/image: preinitialized objects, classes, tables, roots, bitmap
boot.oat    ELF/ET_DYN-style executable image: OAT metadata and quick code
boot.vdex   VDEX: DEX (when embedded), checksums, verifier dependencies, lookup tables
```

Application compilation commonly uses `.odex` or `.oat` naming, but the
logical roles are the same.  The project helper
[`tools/bootimage/build.sh`](tools/bootimage/build.sh) invokes Linux
`build/native/dex2oat` with `--image`, `--oat-file`, a fixed base, and the
`x86_64` instruction set.  The recorded Linux image-backed Hello run is in
[`tools/verify/e2e/RESULT-bootimage.md`](tools/verify/e2e/RESULT-bootimage.md).

### Linux OAT as an ELF container

The OAT file is not a raw header followed by code.  It is an ELF image whose
loadable segments carry ART-owned data and executable code.  The exact byte
offsets are generated for each build, but the current conceptual regions are:

| Region/anchor | Contents and purpose |
|---|---|
| ELF header/program headers | ELF identity, machine, load segments, alignment, and dynamic segment. |
| `.rodata` / `oatdata` | `OatHeader`, key/value store, class offsets, `OatClass` records, index-BSS mappings, OAT maps, per-dex records, and metadata tables. |
| `.text` / `oatexec` | Quick compiled methods, compiler/runtime trampolines, method headers, and code-info/stack-map payloads. |
| `oatlastword` | End marker used to determine the end of the data or code region without relying on ELF section headers at runtime. |
| `.data.img.rel.ro` / `oatdataimgrelro*` | Boot/app image relocation entries; writable while relocation is applied and read-only afterwards. |
| `.bss` / `oatbss*` | Runtime-resolved `ArtMethod` slots, GC roots, and related BSS mappings. It has memory size but normally no file bytes. |
| Optional DEX region / `oatdex*` | Embedded DEX payload in formats/options that retain it; other builds use the separate VDEX DEX section. |
| `.dynstr`, `.dynsym`, `.hash`, `.dynamic` | Dynamic-symbol metadata used by `dlopen` and by ART's internal ELF loader to find the anchors above. |
| Optional debug sections | Build ID, DWARF/minidebug data, and symbolization support; not required for execution. |

The current `ElfBuilder` creates the regions with distinct read, execute, and
read/write program-header flags.  The dynamic section repeats region addresses
and sizes because a running loader cannot depend on ELF section headers.  The
runtime resolves anchors such as `oatdata`, `oatexec`, `oatbss`, and `oatdex` by
dynamic symbol lookup.

The logical offsets inside the OAT data are mostly 32-bit offsets.  For
example, `OatHeader` records the OAT dex-file table offset, BCP-BSS information
offset, executable offset, trampoline offsets, and `base_oat_offset_`.  The
current validation requires the executable offset plus the base offset to meet
the ELF segment alignment.  This is one of the places where a Windows port
must remove ELF-specific meaning rather than blindly reuse a field.

### OAT metadata sequence generated by `OatWriter`

The current writer's lifecycle is the most useful description of the logical
format:

1. Read the input DEX/JAR sources and reserve the VDEX header, section headers,
   and checksums.
2. Write/open DEX files in VDEX and build type-lookup tables.
3. Start OAT read-only data and record the OAT-data start offset.
4. Emit `OatHeader` and the key/value store, then dex-layout support data.
5. Prepare layout: class offsets, OAT classes, index-BSS mappings, OAT maps,
   per-dex records, BCP-BSS records, compiled-code offsets, and image-relro
   layout.
6. Emit the read-only data and compiled `.text` code.
7. Emit image relocation data when present, finalize checksums, and close OAT.
8. `ImageWriter` emits the corresponding `.art` image when this is a boot,
   boot-extension, or app-image compile.

The exact order and padding are container details.  The semantic dependency is
important: code offsets and metadata must be finalized together, and image
checksums/ranges must refer to the exact OAT image that will be loaded.

### Current Linux VDEX layout

`VdexFile` documents the file directly:

```text
VdexFileHeader
VdexSectionHeader[4]
  section 0: checksum array (one uint32 checksum per DEX)
  section 1: optional concatenated DEX files
  section 2: verifier dependencies
  section 3: type-lookup-table data
```

Verifier dependencies contain per-DEX offsets, class assignability data,
string tables, and alignment padding.  The section table carries offsets and
sizes, so loaders can bounds-check every region.  VDEX has its own version and
can evolve independently of OAT; a matching OAT checksum and matching DEX
checksums are still required for execution.

### Current Linux ART image layout

The `.art` file is an ART heap image, not an executable container.  Its header
has `art\n`/`118\0`, image reservation/base/size, image and OAT checksums, OAT
address ranges, pointer size, image roots, and a fixed enumeration of logical
sections:

```text
Objects, ArtFields, ArtMethods, ImTables, IMTConflictTables,
RuntimeMethods, JniStubMethods, InternedStrings, ClassTable,
StringReferenceOffsets, DexCacheArrays, Metadata, ImageBitmap
```

The image header also records the expected OAT range and checksum.  Boot images
reserve address space for the image and its OAT files; app images may map OAT
separately.  Relocation updates the recorded ranges and image references, but
the current implementation expresses alignment in terms of
`kElfSegmentAlignment`.  That dependency must be replaced or parameterized for
Windows.

## Current Linux loading path

`OatFile::Open()` first requires the associated VDEX to exist.  It then:

1. Tries `DlOpenOatFile` for an executable OAT.  On Linux this uses the system
   dynamic loader and `dl_iterate_phdr` to find the mapped `PT_LOAD` ranges and
   dynamic symbols.
2. Falls back to `ElfOatFile`, which uses ART's `ElfFile` implementation to
   parse ELF headers/program headers and map the loadable segments itself.  The
   fallback is needed for cross-compilation, low-address/reserved mappings,
   non-executable loads, and cases where `dlopen` cannot be used.
3. Validates OAT magic, exact version, instruction set, header size, all offset
   bounds, alignment, dynamic-region anchors, and BSS ordering.
4. Maps VDEX, associates each OAT dex record with a DEX file, checks DEX
   checksums and boot-classpath/class-loader identity, and loads verifier/type
   lookup data.
5. Temporarily makes `.data.img.rel.ro` writable to apply image relocations,
   then changes it back to read-only.
6. Loads/validates the ART image, verifies its recorded OAT checksum and address
   ranges, and publishes compiled entrypoints only after the code ranges and
   metadata are safe for readers.

This two-loader structure is a useful Windows design precedent: the logical
`OatFile` setup can remain shared, while `DlOpenOatFile` and `ElfOatFile` become
Windows PE loader implementations with the same validation obligations.

## Proposed Windows OAT container

### Design goals

- Preserve the logical OAT metadata and method/code-info contracts where they
  are independent of ELF.
- Make every executable/data/unwind/relocation region explicit and bounds
  checked.
- Support Windows x64 PE32+, native exception unwinding, multiple mapped
  instances, low-address reservations where required by codegen, and safe
  unload.
- Keep `.vdex` and `.art` as independently versioned artifacts, while binding
  all three with checksums and boot-classpath identity.
- Reject Linux ELF OAT, a different Windows container version, a different ISA
  feature bitmap, and incompatible image/VDEX artifacts before publishing any
  managed entrypoint.

### Recommended model: PE-backed OAT with an ART-owned mapper

The recommended model is a valid PE32+ image containing ART-specific sections,
but not a normal application DLL.  `dex2oat` emits the PE headers and section
table; ART maps and owns the image lifetime.  This preserves the useful PE
metadata and standard unwind/relocation encodings without giving `LoadLibrary`
authority over reservations, duplicate loads, or teardown.

The Windows container has two layers:

1. A **Windows OAT container header** (`WOAT`) that describes the PE image and
   all ART regions.  It is the Windows equivalent of the ELF dynamic-anchor
   contract.
2. The existing logical OAT header and tables, stored in the metadata region,
   with a Windows container tag/version and Windows-specific interpretation of
   region RVAs.

The exact packed C++ definition must be frozen only when the first writer and
loader are implemented.  The required v0 fields are:

| Field | Requirement |
|---|---|
| Magic and container version | Distinguish `WOAT` from Linux `oat\n`; reject unknown major versions. |
| PE machine and pointer size | AMD64 / 64-bit only for this product. |
| Flags and ISA-feature bitmap | Must match the runtime and compiler that load the file. |
| OAT metadata RVA/size | Bounds of `OatHeader`, key/value store, class/method tables, and maps. |
| Text RVA/size | Compiled code and trampolines; all method code offsets are relative to this region. |
| Relro RVA/size and app-image split | Relocation data, including the boundary between boot and app-image entries. |
| BSS RVA/size and method/root offsets | Runtime slots and their subranges. |
| DEX RVA/size (optional) | Embedded DEX, if the selected format keeps it; otherwise zero and use VDEX. |
| Unwind RVA/size | `.pdata`/`.xdata` records associated with compiled code. |
| Base/preferred image address and mapping size | Preferred placement and reservation contract; actual load address is separately validated. |
| OAT/VDEX/image checksums and identity | Cross-artifact consistency before execution. |
| Region table | File RVA, virtual RVA, file size, memory size, alignment, and required protection for each region. |

The proposed PE section mapping is:

| PE section | Role | Initial/final protection |
|---|---|---|
| `.oatmeta` | `WOAT`, logical OAT header, read-only metadata, maps, and dex records | R / R |
| `.text` | Quick compiled methods and trampolines | RX / RX |
| `.oatrel` | Image/BSS relocation data | RW during relocation / R afterwards |
| `.oatbss` | Optional zero-filled method/root slots | RW / RW |
| `.oatdex` | Optional embedded DEX | R / R |
| `.pdata`, `.xdata` | Windows unwind descriptors and unwind bytecode | R / R |
| `.reloc` | PE base-relocation records | R / R |
| Debug sections | CodeView/DWARF or project debug metadata | R or non-loadable |

Section names are implementation choices; the region table, not a section name,
is the compatibility contract.  PE section characteristics must not permit
write+execute pages.  The code cache's existing low R/RX plus RW-alias rules do
not automatically apply to a file-backed AOT image.

### Why not use `LoadLibrary` as the OAT loader?

The Linux implementation already demonstrates why ART needs an internal path:

- boot images may require a specific reservation and base;
- the same OAT may be loaded at multiple addresses for independent dex caches;
- app-image and BSS relocation must be controlled by ART;
- the code range must remain registered until every `ArtMethod` and unwind user
  is gone;
- the loader must support non-executable or inspection-only opens; and
- the Windows process must register and delete dynamic `RUNTIME_FUNCTION`
  ranges with the same lifetime as the mapped code.

The native Windows loader can still be used as a structural PE parser or as a
future optimized path, but it must not be the only correctness path.  The first
implementation should be an ART-owned mapper that reserves memory, copies or
maps section pages, applies PE relocations, sets page protections, and resolves
the explicit `WOAT` region table.

### Relocations, code range, and unwind contract

The Windows writer/loader must define all three independently:

1. **PE image relocations.**  The `.reloc` directory adjusts absolute addresses
   when the preferred base is unavailable.  The loader validates every target
   is inside a writable relocation-bearing region before applying it.
2. **ART image relocations.**  The logical `.oatrel` table updates image and
   app-image references.  It is writable only for the relocation transaction,
   then becomes read-only.
3. **Generated-code unwind.**  `.pdata` entries point to `.xdata` unwind data;
   the mapped image must be visible to `RtlLookupFunctionEntry`/`RtlVirtualUnwind`
   for the entire code lifetime.  Dynamically mapped images register their
   records with `RtlAddFunctionTable` and remove them with
   `RtlDeleteFunctionTable` before releasing code memory.

The existing Windows JIT work already validates runtime-function registration,
deletion, XMM preservation, and code-cache lifecycle.  AOT must use the same
unwind and range-publication rules.  The range must be published before any
managed entrypoint is installed, and unpublished before teardown.

### Address and ABI requirements

The Windows x86_64 compiler emits the project's managed ABI, not the ordinary
MS x64 C++ ABI.  AOT code must therefore be generated by the same codegen and
entrypoint configuration used by the accepted JIT path.  The design must also
choose and test:

- preferred boot-image/OAT base and relocation policy;
- whether direct code/data references require a low contiguous reservation;
- signed 32-bit displacement limits for JIT/AOT roots and branches;
- 32-bit offset overflow checks for `CodeInfo`, maps, and region descriptors;
- pointer-size and `ArtMethod` layout identity between `.art` and `.oat`;
- no CET user shadow-stack dependency, matching the current Windows process
  contract.

The Linux boot helper's `--base=0x70000000` is evidence of a tested Linux image
base, not a Windows base requirement.  Windows ASLR, PE image alignment, and
the x86_64 code-range constraints must be measured on Server 2025.

## Windows generation lifecycle

The intended Windows-native `dex2oat.exe` flow is:

1. Validate the boot class path, input DEX/JAR checksums, compiler filter, ISA,
   feature bitmap, pointer size, and class-loader context.
2. Compile methods with the Windows x86_64 quick compiler and produce
   `OatQuickMethodHeader`, `CodeInfo`, stack maps, method offsets, and unwind
   records.
3. Build the VDEX sections and checksums.
4. Run the logical OAT writer: header/KV store, class/method tables, maps, dex
   records, BSS maps, code, and image-relro data.
5. Allocate PE RVAs, align regions, emit `.oatmeta`, `.text`, `.oatrel`,
   `.oatbss`, optional `.oatdex`, `.pdata/.xdata`, and `.reloc`.
6. Fill the `WOAT` region table and cross-artifact checksums, then finalize the
   PE headers and section characteristics.
7. Emit the `.art` image with its OAT checksum/range and the same pointer-size,
   class-layout, and boot-image component identity.
8. Run an offline validator before the artifact is eligible for a native gate.

The writer must be deterministic for all fields that participate in checksums.
Build paths, timestamps, debug-only data, and command lines must be either
normalized or explicitly excluded from deterministic checksums, as the current
OAT key/value policy already does for selected fields.

## Windows loading lifecycle

The intended `OatFile::Open()` Windows path is:

1. Locate `.oat`, `.vdex`, and (when required) `.art`; reject missing or
   mismatched companion artifacts before mapping executable pages.
2. Parse and bounds-check PE headers: AMD64 machine, optional-header size,
   image size, section RVAs, raw sizes, alignment, relocation directory, and
   absence of unsupported imports/characteristics.
3. Read `WOAT` and validate the container version, ISA/features, pointer size,
   region table, logical OAT magic/version, header offsets, and all checksums.
4. Reserve the preferred or an allowed relocated address with `VirtualAlloc`.
   Enforce low-address/contiguous requirements when codegen requires them.
5. Map/copy sections, apply PE base relocations, and verify that every target is
   within the declared writable relocation ranges.
6. Set `.oatmeta`/`.oatdex`/unwind pages read-only, `.text` RX, `.oatrel` R after
   ART image relocation, and `.oatbss` RW.  No W+X transition is permitted.
7. Register `.pdata/.xdata` with the Windows runtime-function APIs, publish the
   code range, and resolve the logical OAT anchors from the region table.
8. Map and validate VDEX, associate DEX files, check boot-classpath/class-loader
   identity, and initialize BSS and image relocations.
9. Load/relocate `.art`, verify its OAT checksum and ranges, then install AOT
   entrypoints.  If any step fails, discard the mapping and leave the imageless
   interpreter/JIT path available.
10. On unload, remove method entrypoints and code ranges, unregister unwind
    tables, release aliases/reservations, and only then unmap PE sections.

The loader must provide inspection-only and non-executable modes for tooling,
but those modes must never publish AOT entrypoints.

## Versioning and compatibility policy for Windows

Windows artifacts need at least three independent version checks:

1. **Logical OAT version** for the packed OAT metadata and compiler/runtime
   semantics.
2. **Windows container version** for PE section/region descriptors, relocation
   policy, and unwind encoding.
3. **Companion versions** for VDEX and ART image headers.

The Windows loader must reject, rather than reinterpret, a major-version
mismatch, an unknown region/flag, a different instruction-set feature bitmap,
an incompatible boot-classpath checksum, a stale image checksum, or a
pointer-size/layout mismatch.  A minor-version compatibility rule is only safe
after a concrete backward-compatible field policy and tests exist.

Windows PE OAT is therefore a new platform artifact.  It must not be described
as “the same OAT file as Linux” merely because it reuses `OatHeader` concepts.
Linux ELF OAT remains a separate format and is not a Windows acceptance input.

## Required validation and native gates

Before claiming Windows AOT support, add structural and runtime checks for:

- PE/WOAT header and section bounds, alignment, characteristics, and version
  rejection;
- OAT/VDEX/ART checksum and boot-classpath identity;
- preferred-base and relocated-base boot images;
- low-address allocation failure and recovery;
- every relocation class, including image relro and BSS slots;
- `.pdata/.xdata` lookup, virtual unwind, exception delivery, and table removal;
- interpreter fallback for non-compiled methods and failed/unsupported OAT;
- JNI, GC, class initialization, reflection, JIT-after-AOT, OSR, deoptimization,
  and repeated start/stop cycles;
- truncated, corrupted, wrong-ISA, wrong-version, wrong-pointer-size, and
  mismatched-companion artifacts;
- no W+X mappings, no stale runtime-function records, and no code-range use
  after unload.

The final acceptance package must run on Windows Server 2025 build 26100.  A
Linux dex2oat result, a Wine PE smoke, or a Windows 10 historical bundle can
support development history but cannot close the Windows AOT gate.

## Open implementation items

1. Freeze the `WOAT` header and region-table schema after the first writer/loader
   prototype.
2. Split `ElfWriter`/`ElfFile` assumptions from shared logical OAT code and add
   Windows PE writer/loader interfaces.
3. Decide whether embedded DEX remains supported or whether Windows always
   requires a separate VDEX.
4. Implement PE relocation and ART image-relocation handling with explicit
   read-only transitions.
5. Generate and register PE unwind records for every AOT code range.
6. Define the Windows preferred base, relocation limits, and multi-instance
   loading behavior.
7. Build Windows-native `dex2oat`, produce `.art/.oat/.vdex`, and run the full
   Server 2025 gate matrix.
8. Decide how AOT interacts with the current imageless/JIT product model:
   boot-image-only AOT, optional application AOT, or both with JIT fallback.

Until these items are closed, AOT/OAT remains deferred and the supported Windows
product path is imageless boot with nterp and managed/native JIT.
