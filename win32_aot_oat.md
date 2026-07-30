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
4. VDEX and ART images are data artifacts and remain ART-owned mappings.  That
   does not force executable OAT to use the same mapping mechanism.
5. A genuine PE32+ OAT DLL loaded by `LoadLibraryExW` is the preferred Windows
   design if native prototypes prove that ART can tolerate loader-selected OAT
   placement and normal module-instance semantics.  This route delegates PE
   relocation, imports, image protections, unwind discovery, CFG/load-config
   processing, and unload bookkeeping to Windows.
6. The current ART boot-image contract does not yet satisfy that condition: it
   reserves image and OAT together below 4 GiB and relocates both with one
   delta.  Current application OAT also relies on a distinct BSS/dex-cache
   instance when the same artifact is opened more than once.
7. If exact reservation consumption or arbitrary duplicate mappings remain
   mandatory, preserving the existing ELF coat is the preferred first manual
   loader implementation.  A manually mapped PE is worth selecting only if a
   focused `SEC_IMAGE` prototype demonstrates a concrete Windows policy or
   tooling advantage; manual PE does not receive full DLL-loader behavior.

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

The Android `dlopen` success path is more capable than ordinary desktop
`dlopen`: `android_dlopen_ext()` uses `ANDROID_DLEXT_FORCE_LOAD` so the same
artifact can have independent instances, and `ANDROID_DLEXT_RESERVED_ADDRESS`
so the dynamic linker consumes ART's existing boot-image reservation.  The
host path rejects a repeated handle and falls back to `ElfOatFile` because
unique BSS/dex-cache state is required for class unloading.

Boot and application images impose different constraints:

- For a boot image, `ImageHeader::RelocateImageReferences()` changes the image
  and recorded OAT ranges by one delta.  `ImageSpace::Loader::OpenOatFile()`
  then requires the actual `OatFile::Begin()` to equal the recorded OAT-data
  address plus that image delta.  The primary header's reservation covers all
  boot image and OAT components, and addresses are currently 32-bit fields.
- For an application image, `RelocateInPlace()` already constructs a separate
  `RelocationRange` for the actual OAT data.  Independent OAT placement is
  supported, but repeated opens still need independent mutable BSS/dex-cache
  state unless that state is moved out of the module.
- The OAT ELF reserves an `oatdex`/`.dex` virtual range and the runtime can map
  the companion VDEX into that range.  A normal PE DLL loader cannot have ART
  replace one of its image ranges with an unrelated VDEX file, so a PE design
  must make VDEX addresses explicitly independent.

This is the correct Windows precedent: keep logical `OatFile` validation
shared, but retain a loader-managed fast path and an internal fallback only
where each one's semantics are actually sufficient.  A plain desktop loader
call is not an equivalent replacement for Android's extended loader.

## Windows loader/API analysis and container decision

### Design goals

- Preserve the logical OAT metadata and method/code-info contracts where they
  are independent of ELF.
- Make every executable/data/unwind/relocation region explicit and bounds
  checked.
- Support native Windows x64 exception unwinding, the placement and instance
  models required by ART, and safe unload.
- Keep `.vdex` and `.art` as independently versioned artifacts, while binding
  all three with checksums and boot-classpath identity.
- Reject a wrong coat, container version, ISA-feature bitmap, or incompatible
  image/VDEX artifact before publishing any managed entrypoint.

### Treat OAT, VDEX, and ART according to their roles

The three companions do not need one container or one loader:

| Artifact | Windows treatment | Reason |
|---|---|---|
| Executable OAT | Prefer a genuine PE32+ DLL and the normal loader if the proof gates below pass; otherwise use an ART-owned executable loader. | It contains native code, unwind metadata, relocations, and loader-visible regions. |
| VDEX | Raw, private read-mostly data mapping; copy/extract when an archive entry cannot be mapped directly. | It is a versioned data file, not an executable image. |
| ART image | ART-owned reserved mapping, direct file overlay when possible, or anonymous memory plus copy/decompression and relocation. Map its bitmap separately read-only. | It is a relocatable heap/object snapshot with low-address, checksum, GC-bitmap, and temporary-write requirements. |

On Windows, raw VDEX and uncompressed ART pages can use ordinary file-mapping
objects and `MapViewOfFile3`.  Placeholder replacement is appropriate for
these data-backed mappings.  A compressed ART image requires anonymous memory
and decompression.  These manual data mappings do **not** imply that OAT code
must also be manually mapped.

A PE OAT must remove the current `oatdex` adjacency assumption: its descriptor
records VDEX identity and logical offsets, while the `VdexFile` object owns an
independent mapping.  The runtime must never try to replace pages inside a DLL
image with VDEX pages.

### Public Windows API capability matrix

| API/mode | Executable PE prepared as a DLL? | Exact ART reservation? | Independent same-file instances? | What is missing or unsuitable? |
|---|---:|---:|---:|---|
| `LoadLibraryExW` normal load | Yes | No caller-owned reservation; a relocation-stripped image can require one fixed free base | No | Requires a path; Windows chooses a relocatable image's address and reuses the loaded module. This is the only public route here that performs the full loader transaction. |
| `DONT_RESOLVE_DLL_REFERENCES` | No safe execution contract | No | No | Skips dependency loading and `DllMain`; Microsoft says not to use it except for backward compatibility. |
| `LOAD_LIBRARY_AS_DATAFILE[_EXCLUSIVE]` | No | No | Yes | Data mapping; `GetProcAddress` cannot be used and code is not prepared for execution. |
| `LOAD_LIBRARY_AS_IMAGE_RESOURCE` | No | No | Yes | Uses PE image layout but deliberately skips static imports and normal initialization; intended for resource access. |
| `CreateFileMappingW(SEC_IMAGE)` + `MapViewOfFile3` | Only with ART completing missing loader work | Desired base parameter, but cannot replace a placeholder | Views can be created, but per-view rebasing is not a supported force-load contract | Maps PE sections as `MEM_IMAGE`; does not resolve imports, run TLS/entrypoint initialization, publish a loader module, or register unwind metadata. |
| Ordinary data mapping + ART mapper | Only if ART implements all executable-image work | Yes, including placeholder-backed raw mappings | Yes | Dynamic-code policy, relocations, protections, unwind, CFG, symbols, and lifetime all belong to ART. Works for ELF or raw/manual PE. |

`MapViewOfFile`, `MapViewOfFileEx`, `MapViewOfFile2`, and `MapViewOfFile3`
are view constructors, not DLL loaders.  The `Ex` form can request an address
but fails if the range is unavailable; the 2/3 forms add extended parameters.
`VirtualAlloc2` can reserve, split, and coalesce placeholders, but image views
cannot replace them.  `SEC_IMAGE_NO_EXECUTE` is useful only for non-executable
inspection.  `LoadPackagedLibrary`, `AddDllDirectory`, `GetModuleHandleEx`, and
the other loader-search/reference helpers do not add address-reservation or
force-new-instance semantics.

`LoadLibraryExW` has no base-address or reservation parameter; its `hFile`
parameter is reserved and must be null.  It cannot load from an existing file
handle, memory buffer, or `zip!/entry`, so an archived OAT must be materialized
under a stable, versioned absolute path before a normal load.

For a normal executable load, use an absolute path and constrained dependency
searching:

```text
LoadLibraryExW(
    absolute_oat_path,
    nullptr,
    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
        LOAD_LIBRARY_SEARCH_DEFAULT_DIRS)
```

Do not combine this with `LOAD_WITH_ALTERED_SEARCH_PATH`, and do not use any
data/resource or no-resolve flag as a shortcut to executable OAT.  An OAT PE
can retain the `.oat` suffix because an explicit filename is not required to
end in `.dll`; using `.oat.dll` is also possible if deployment tooling benefits
from a conventional suffix.

### What a normal PE load gives ART

A true PE32+ DLL, preferably import-free and linked without a DLL entrypoint,
lets Windows:

- create the image section and enforce section protections;
- choose its address and apply PE base relocations;
- resolve any declared imports and process TLS/load-configuration metadata;
- expose an immutable OAT descriptor through `GetProcAddress`;
- make the PE exception directory available to `RtlLookupFunctionEntry` and
  normal stack walking without `RtlAddFunctionTable`;
- integrate the image with loader enumeration, CFG/image policy, signing,
  debuggers, profilers, and antivirus; and
- run reference-counted teardown through `FreeLibrary`.

ART still owns logical validation, VDEX/image checks, image-relro updates, BSS
initialization, entrypoint publication, and the rule that no method points into
the image when its last module reference is released.  A mutable `.oatrel`
section can be RW during ART relocation and changed to R afterwards;
`.oatbss` remains RW.  No section may be W+X.

### What must change before normal PE can be selected

The PE fast path is preferred, but it cannot be declared correct against the
current layout without these changes and native proofs:

1. **Boot placement:** split the boot ART-image relocation delta from the OAT
   module delta.  Replace 32-bit absolute OAT range fields where necessary,
   and prove every quick-code/image/root reference remains encodable when the
   PE loader places OAT outside the low ART-image reservation.
2. **Application instances:** either move dex-cache/BSS/GC-root and image-
   specific relro state outside the PE module and teach generated code how to
   address per-`OatFile` state, or provide a safe unique materialized path for
   each required instance.  Loading the same absolute file again only
   increments one module reference.
3. **VDEX independence:** replace `oatdex` reserved-range overlay with an
   ordinary independent VDEX mapping and explicit checked offsets.
4. **File lifetime:** use immutable, checksum/version-named cache files; prove
   update, deletion, crash recovery, and class-unload behavior while Windows
   holds an image-section reference.
5. **No-entry module:** prefer no `DllMain`, static TLS, delay imports, or
   process-global constructors.  OAT initialization remains explicit ART code,
   outside loader lock.

The boot and app problems are complementary: boot is naturally single-instance
but currently requires exact coupled placement; app OAT already relocates
independently but can require distinct mutable instances.  Neither should be
assumed solved by the other's property.

### Narrow fixed-base PE variant

A relocation-stripped PE offers one constrained way to combine the normal
loader with the current exact boot layout.  Link an import-free/no-entry DLL
with its `ImageBase` equal to the compiled OAT address, reserve the surrounding
ART image ranges as split placeholders while leaving the OAT hole free, and
load OAT before overlaying the data mappings.  PE/COFF specifies that an image
with relocations stripped must load at its preferred base or fail.

This is fail-safe if every address and size is verified and a collision falls
back to imageless/JIT; it is not equivalent to relocatable product support.  It
disables boot-layout ASLR, cannot consume one atomic ART reservation, leaves a
short race for the OAT hole, complicates multi-component layouts, and does not
solve application duplicate state.  It may be a PE-0 bring-up experiment, but
accepting it as a shipped mode requires an explicit security/availability
decision and Server 2025 collision, rollback, and policy gates.  A lucky fixed
load must never be reported as proof that the relocatable PE design works.

### Server 2025 focused loader result

A disposable native probe on the authoritative Windows Server 2025 x64 host
(`10.0.26100.32230`, 2026-07-30) used a relocatable PE32+ DLL copied with a
`.oat` suffix.  It observed:

- normal `LoadLibraryExW` succeeded and `GetProcAddress` found an export;
- loading the same absolute file twice returned the same module address;
- byte-identical files at two different absolute paths with the same basename
  produced distinct module instances;
- a live reservation at the PE preferred base remained reserved and untouched;
  the loader placed the image elsewhere;
- `RtlLookupFunctionEntry` found the normal module's unwind entry;
- `MapViewOfFile3` could place a `SEC_IMAGE` view at requested low addresses,
  but its IAT remained unresolved and it had no discoverable unwind entry; and
- base-relocation bytes in requested-address `SEC_IMAGE` views reflected the
  system image bias rather than each requested view address.  Two views at
  `0x70000000` and `0x71000000` therefore did not have correct per-view
  relocation values.

The last observation is deliberately treated as a rejection result, not as an
undocumented contract to work around.  A requested base plus `SEC_IMAGE` is not
an ART equivalent of `ANDROID_DLEXT_RESERVED_ADDRESS`/`FORCE_LOAD`.

### `SEC_IMAGE`, placeholders, and manual PE

`CreateFileMappingW(..., SEC_IMAGE, ...)` requires a valid executable image;
view protections come from PE section characteristics.  `MapViewOfFile3` can
request a base address.  However, the documented `MEM_REPLACE_PLACEHOLDER`
operation supports only data/pagefile-backed section views and explicitly
excludes images.  ART cannot atomically replace part of its boot placeholder
with a `SEC_IMAGE` view.

Releasing a hole and then requesting the address is racy and, as the native
result shows, does not establish a supported per-view relocation contract.
Even a successfully placed view still lacks import binding, loader-lock
initialization, module-list bookkeeping, CFG/load-config processing guarantees,
and automatic unwind discovery.  A deliberately import-free, position-
independent PE might avoid some work, but ART must still validate the PE,
register/delete its function table, publish/unpublish code ranges, handle CFG,
and own teardown.  That is a manual executable loader, not `LoadLibraryExW`.

An ordinary, non-`SEC_IMAGE` PE mapper is less attractive: once ART copies or
maps sections, applies relocations, controls protections, and registers unwind
it has accepted essentially the same work and dynamic-code-policy exposure as
the existing ELF loader, while also creating a new writer and parser.

### Native `Nt`/`Zw`/`Ldr` and `Rtl` APIs

No native API closes the missing public contract:

- `LdrLoadDll`, `LdrGetProcedureAddress`, and `LdrUnloadDll` are ntdll loader
  internals, not the supported application ABI used by this project.
  `LdrLoadDll` still expresses normal module-loader semantics and exposes no
  supported caller-owned reservation or force-new-instance parameter.
- `NtCreateSection`/`NtMapViewOfSection` (and newer `*Ex` internals) are
  lower-level forms of section creation/mapping.  They do not by themselves
  bind imports, initialize TLS,
  call entrypoints, add loader-list state, configure CFG, or establish unload
  bookkeeping.  Their native ABI is not a replacement for `LoadLibraryExW`.
- `Zw*` spellings are primarily documented for kernel-mode drivers.  They are
  inappropriate dependencies for this user-mode runtime.
- Internal routines such as `Ldrp*` are explicitly out of scope; version
  changes, loader-lock invariants, and mitigation interactions make them an
  unacceptable product ABI.
- Header constants such as `MEM_DIFFERENT_IMAGE_BASE_OK` do not provide a
  documented application contract for independently rebasing image views.
  Presence in an SDK header is not sufficient authority to depend on it.
- Public `RtlAddFunctionTable`, `RtlDeleteFunctionTable`, and optionally
  `RtlInstallFunctionTableCallback` are appropriate for ART-owned executable
  mappings.  `RtlLookupFunctionEntry`/`RtlVirtualUnwind` are validation and
  unwind operations, not image loaders.  Normal PE modules should use their
  static exception directory instead of registering a duplicate table.
- `RtlAddGrowableFunctionTable` is documented but unnecessary for a finalized
  AOT range with a fixed table; it does not register a PE module.  Parser and
  lookup helpers such as `RtlImage*`, ImageHlp RVA routines, or
  `RtlPcToFileHeader` likewise do not perform a loader transaction and do not
  replace the project's fail-closed validator.
- `SetProcessValidCallTargets` can participate in a manual CFG design, but it
  does not perform PE load-config processing and cannot make a custom mapper
  equivalent to the loader.

Native APIs may be used in a diagnostic probe to understand Server 2025, but
the product design must depend on documented Win32/`Rtl*` contracts only.

### PE versus preserved ELF when mapping must remain manual

| Property | Loader-managed PE DLL | ART-owned `SEC_IMAGE`/manual PE | Preserved ELF + ART loader |
|---|---|---|---|
| Existing ART writer/reader reuse | Low | Low | High (`ElfBuilder`, `ElfFile`, symbols, segments already exist) |
| Exact reservation / arbitrary instances | No caller reservation; only the narrow fixed-base variant can require one address | Possible only with a proven custom strategy | Yes, matches the existing internal-loader model |
| Imports/TLS/entrypoint/load config | Windows loader | ART responsibility or deliberately absent | Deliberately absent/ART responsibility |
| Static Windows unwind discovery | Yes | No; explicitly register | No; add Windows unwind regions and explicitly register |
| CFG, signing, AV, debugger/module visibility | Best | Partial/uncertain | Weakest |
| Dynamic-code-policy exposure | Lowest | Must prove; `SEC_IMAGE` may help | Highest; executable data views can be rejected |
| New container/parser complexity | High writer work, low loader work | High writer and loader work | Low container work, Windows mapping/unwind work |
| Linux OAT byte compatibility | No | No | Container can remain ELF, but Windows code ABI/version still makes it a Windows artifact |

Therefore:

1. Prototype the loader-managed PE route first because it has the best steady-
   state Windows integration if its placement/state redesign is acceptable.
2. If exact coupled placement and arbitrary force-load semantics remain hard
   requirements, preserve ELF for the first Windows AOT bring-up and add
   Windows `.pdata`/`.xdata`-equivalent regions plus explicit `Rtl*` lifetime.
3. Do not choose manually mapped PE merely because PE is native to Windows.
   Select it only after `SEC_IMAGE`, mitigation, debugger, and exact-placement
   gates demonstrate a benefit large enough to justify both a new PE writer
   and a custom loader.

Preserving ELF does not mean accepting an Android-built OAT indiscriminately.
The contained quick code uses the Windows x64 managed/entrypoint ABI, its OAT
version and feature identity match this runtime, and the loader rejects all
other variants.

## Proposed PE OAT module, if the PE proof gates pass

The PE design is a real DLL, not a PE-shaped file that defaults to a custom
mapper.  `dex2oat` emits PE headers, an export table, normal exception and
relocation directories, and ART regions.  A single exported immutable
descriptor such as `ArtOatModuleV1` is preferred over depending on section
names.  Its payload begins with a `WOAT` magic/version and points to all
regions by RVA and size.  The existing logical `OatHeader` retains its own
`oat\n` magic/version inside the metadata region.

The module has two layers:

1. A **Windows OAT module descriptor** (`WOAT`) that describes the PE image and
   all ART regions.  It replaces the ELF dynamic-anchor lookup contract.
2. The existing logical OAT header and tables, stored in the metadata region,
   with a Windows container tag/version and Windows-specific interpretation of
   region RVAs.

The exact packed C++ definition must be frozen only when the first writer and
loader are implemented.  The required v0 fields are:

| Field | Requirement |
|---|---|
| Magic and container version | Identify the `WOAT` descriptor independently of logical `oat\n`; reject unknown major versions. |
| PE machine and pointer size | AMD64 / 64-bit only for this product. |
| Flags and ISA-feature bitmap | Must match the runtime and compiler that load the file. |
| OAT metadata RVA/size | Bounds of `OatHeader`, key/value store, class/method tables, and maps. |
| Text RVA/size | Compiled code and trampolines; all method code offsets are relative to this region. |
| Relro RVA/size and app-image split | Relocation data, including the boundary between boot and app-image entries. |
| BSS RVA/size and method/root offsets | Runtime slots and their subranges. |
| DEX RVA/size (optional) | Embedded DEX, if the selected format keeps it; otherwise zero and use VDEX. |
| Unwind RVA/size | `.pdata`/`.xdata` records associated with compiled code. |
| Preferred image base and `SizeOfImage` | Diagnostic/container identity only on the normal loader path; never claim that ART selected the actual address. |
| OAT/VDEX/image checksums and identity | Cross-artifact consistency before execution. |
| Region table | Raw file offset/size where applicable, memory RVA/size, alignment, and required protection for each region. |

The proposed PE section mapping is:

| PE section | Role | Initial/final protection |
|---|---|---|
| `.oatmeta` | `WOAT`, logical OAT header, read-only metadata, maps, and dex records | R / R |
| `.text` | Quick compiled methods and trampolines | RX / RX |
| `.oatrel` | Image/BSS relocation data | RW during relocation / R afterwards |
| `.oatbss` | Optional zero-filled method/root slots | RW / RW |
| `.oatdex` | Optional DEX bytes only; never a placeholder for an external VDEX mapping | R / R |
| `.pdata`, `.xdata` | Windows unwind descriptors and unwind bytecode | R / R |
| `.reloc` | PE base-relocation records | R / R |
| Debug sections | CodeView/DWARF or project debug metadata | R or non-loadable |

Section names are implementation choices; the exported descriptor, not a
section name, is the compatibility contract.  PE section characteristics must
not permit write+execute pages.  The code cache's low R/RX plus RW-alias rules
do not automatically apply to a loader-managed file image.  Inspection-only
tools should parse the file or use image-resource mode without ever publishing
entrypoints; runtime execution uses only the normal loader mode.

### Relocations, code range, and unwind contract

The Windows writer/loader must define all three independently:

1. **PE image relocations.**  On the preferred normal path, Windows validates
   and applies the `.reloc` directory.  ART records the actual module base and
   validates every descriptor RVA against `SizeOfImage`; it does not reapply
   PE relocations.  A manual PE experiment would instead own full relocation
   validation and application.
2. **ART image relocations.**  The logical `.oatrel` table updates image and
   app-image references.  It is writable only for the relocation transaction,
   then becomes read-only.
3. **Generated-code unwind.**  `.pdata` entries point to `.xdata` unwind data.
   A normally loaded PE exposes its exception directory through the static
   image lookup path.  ART-owned PE or ELF mappings must register their records
   with `RtlAddFunctionTable` and remove them with `RtlDeleteFunctionTable`
   before releasing code memory.

The existing Windows JIT work already validates dynamic function-table
registration, deletion, XMM preservation, and code-cache lifecycle.  AOT uses
the same range-publication ordering but must not register a duplicate dynamic
table for a normally loaded PE.  The range is published before any managed
entrypoint is installed and unpublished before teardown.

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
5. For the PE prototype, allocate RVAs and emit `.oatmeta`, `.text`,
   `.oatrel`, `.oatbss`, optional embedded DEX, `.pdata/.xdata`, `.reloc`, and
   the `ArtOatModuleV1` export.  Prefer an import-free `/NOENTRY` DLL.
6. Fill the `WOAT` descriptor and cross-artifact checksums, then finalize PE
   headers, data directories, section characteristics, and optional signing.
7. Emit the `.art` image with the redesigned independent OAT-placement fields,
   the same pointer/class layout, and matching component identity.
8. Run a raw-file validator before `LoadLibraryExW` is ever allowed to see the
   artifact.

If the PE proof gates reject the redesign, steps 5-6 retain `ElfBuilder` and
the existing dynamic anchors instead.  That Windows ELF must still contain
Windows x64 unwind records and an explicit Windows code-ABI/container identity.
The choice of coat does not alter logical OAT, VDEX, or ART checksum generation.

The writer must be deterministic for all fields that participate in checksums.
Build paths, timestamps, debug-only data, and command lines must be either
normalized or explicitly excluded from deterministic checksums, as the current
OAT key/value policy already does for selected fields.

## Loader-managed PE lifecycle

The preferred `OatFile::Open()` Windows path is:

1. Select immutable, ACL-protected, checksum/version-named `.oat`, `.vdex`, and
   optional `.art` files.  Reject a missing or mismatched companion before
   loading executable pages.
2. Parse the OAT as a raw file and bounds-check PE32+/AMD64 headers, entrypoint,
   imports, TLS, data directories, section RVAs/sizes, `WOAT`, logical OAT,
   ISA/features, and checksums.  The v0 policy should require no entrypoint,
   imports, or TLS.
3. Call `LoadLibraryExW` with the absolute path and safe search flags.  Because
   the public API accepts no validated file handle, mitigate the parse/load
   time-of-check/time-of-use window with a trusted immutable cache; then
   revalidate the mapped descriptor and identity.
4. Resolve `ArtOatModuleV1` with `GetProcAddress`, validate every RVA/size
   against the actual mapped `SizeOfImage`, record the loader-selected code
   ranges, and prove representative functions are discoverable through
   `RtlLookupFunctionEntry`.
5. Map VDEX independently, associate DEX files, and validate checksums,
   boot-class-path identity, and class-loader context.  Map/decompress and
   relocate the ART image under ART's reservation policy.
6. Initialize per-instance BSS, make image-relro writable only for the checked
   relocation transaction, restore it to read-only, and verify image/OAT
   checksums and actual ranges.
7. Publish the code range and install compiled entrypoints only after all prior
   steps succeed.  Otherwise `FreeLibrary` and retain the imageless
   interpreter/JIT path.
8. On unload, remove entrypoints and code ranges, wait out all readers, release
   per-instance data and companions, and call `FreeLibrary` last.  Confirm that
   unwind lookup no longer treats the released range as a live module.

Inspection tools parse the raw file or use a non-executable resource mapping;
those modes never publish AOT entrypoints.

## ART-owned ELF fallback lifecycle

If the PE gates show that current placement/instance semantics cannot be
redesigned safely, Windows `ElfOatFile` remains close to the current flow:

1. Validate ELF/OAT and companions as raw files before executable mapping.
2. Reserve the required low/exact range with Windows placeholders and replace
   subranges with data-backed file views for each `PT_LOAD`; use final R, RX,
   and RW protections without W+X.
3. Resolve existing dynamic anchors, map VDEX into its declared range or use
   the new independent mapping model, and apply ART image/BSS relocation.
4. Validate and register the Windows x64 function table with
   `RtlAddFunctionTable`, then publish code and entrypoints.
5. On unload, unpublish entrypoints/code, call `RtlDeleteFunctionTable`, and
   only then unmap segments and reservations.

This route needs a native `ProhibitDynamicCode`, CFG, unwind, debugger, and AV
gate.  If executable data-backed views are rejected while loader-managed image
sections succeed, that result is a strong reason to revisit the PE redesign.

## Versioning and compatibility policy for Windows

Windows artifacts need at least three independent version checks:

1. **Logical OAT version** for the packed OAT metadata and compiler/runtime
   semantics.
2. **Windows coat/container identity** for PE `WOAT` descriptors or a Windows
   ELF tag, placement policy, and unwind encoding.
3. **Companion versions** for VDEX and ART image headers.

The Windows loader must reject, rather than reinterpret, a major-version
mismatch, an unknown region/flag, a different instruction-set feature bitmap,
an incompatible boot-classpath checksum, a stale image checksum, or a
pointer-size/layout mismatch.  A minor-version compatibility rule is only safe
after a concrete backward-compatible field policy and tests exist.

Windows OAT is therefore a new platform artifact even if the fallback retains
an ELF coat.  It must not be described as “the same OAT file as Linux” merely
because it reuses `OatHeader` or ELF.  The Windows quick ABI, unwind metadata,
container identity, and exact runtime/compiler versions remain acceptance
inputs; an arbitrary Linux/Android OAT is rejected.

## Correctness invariants and edge-case disposition

The loader is fail-closed.  Any arithmetic overflow, ambiguous file identity,
unsupported directory/flag, unproved placement, or partial companion match
rejects AOT before entrypoint publication.  Falling back to nterp/JIT is a
normal recovery path; guessing at compatibility is not.

### File identity, trust, and loader side effects

| Edge case | Required disposition |
|---|---|
| Relative path, current-directory search, case/8.3 alias, junction, symlink, reparse point, hard link, UNC, or device path | Resolve and enforce a project cache-root policy. Key the module registry by stable volume/file identity plus a cryptographic content identity, not by an unnormalized string. Reject remote/device/reparse paths unless a later explicit policy and gate permits them. |
| File replaced between raw validation and `LoadLibraryExW` | Keep a read handle that denies write/delete sharing across validation and load, verify its file ID/final path, use an immutable ACL-protected cache, and revalidate the mapped `WOAT` identity. Prove that this sharing mode is compatible with the loader on Server 2025. |
| Same path now names new bytes while an old module is loaded | Never overwrite an eligible cache entry. Publish a new checksum/version-named file and module-registry key. A request must not silently receive an older loaded module. |
| Two paths or aliases name the same bytes/file | Do not assume distinct paths imply distinct instances. The native result proves separate byte copies, not hard links, reparse aliases, or file-ID aliases. Test or reject those forms. |
| Unique byte copy is used for an app instance | Keep the logical OAT/DEX location and class-loader identity separate from the physical PE materialization path. Apply cache quotas and delete the copy only after the final loader reference is gone. |
| Module must be found again after load | Retain the exact returned `HMODULE`; never reacquire an OAT by basename with `GetModuleHandle`, which is ambiguous when distinct full paths share a basename. |
| Malicious PE executes during loading before ART validation | The v0 raw validator requires PE32+/AMD64, zero entrypoint, no TLS directory/callbacks, no imports/delay imports, no CLR header, and a strict allowlist for other data directories and characteristics. Keep OAT initialization outside loader lock. |
| Export is forwarded, points outside the image, or has an unexpected ordinal/name | Require an exact undecorated `ArtOatModuleV1` data export whose address and entire descriptor lie in the declared read-only metadata region. Reject forwarders and ordinal-only discovery. |
| OAT checksum collision or untrusted cache writer | Existing ART checksums detect stale companions but are not an authenticity boundary. Use SHA-256 or a stronger project manifest/signature identity plus trusted cache ACLs when artifacts can cross a trust boundary. |
| Authenticode/catalog policy or unsigned runtime-generated artifact | Define the deployment trust model before enabling AOT. Gate `LOAD_LIBRARY_REQUIRE_SIGNED_TARGET`, code-integrity guard, and enterprise policy where applicable; do not assume a locally generated unsigned PE will load everywhere. |
| Process shutdown or loader-lock reentrancy | Do not open or close OAT from `DllMain`, TLS callbacks, or code already running under loader lock. A no-entry/no-TLS module makes startup and teardown explicit. |

The stable file handle cannot be passed to `LoadLibraryExW` (`hFile` must be
null); it is an identity/share lock, not the loader input.  If the handle-based
TOCTOU proof fails, the normal PE path remains unaccepted.

### Structural parsing and integer safety

All parsers operate on unsigned checked ranges, not trusted packed-struct
casts.  For every `offset + size`, `RVA + size`, alignment round-up, count times
element-size, and load-base plus RVA, validate overflow before addition or
multiplication.  Required rejections include:

- DOS/PE header offsets outside the file, wrong optional-header size or magic,
  wrong machine/pointer size, excessive section/directory counts, and a
  `SizeOfImage` inconsistent with the final section;
- overlapping, unordered, multiply described, sparse-with-unexpected-holes,
  misaligned, or out-of-file sections; raw size greater than available bytes;
- any W+X section, executable metadata/BSS/VDEX/ART pages, writable unwind
  records after publication, or section characteristics inconsistent with the
  `WOAT` protection contract;
- base-relocation, export, exception, load-config, resource, debug, and
  certificate directories whose file/RVA interpretation is confused or whose
  contents escape their declared bounds;
- `WOAT` regions that overlap illegally, escape `SizeOfImage`, alias headers,
  disagree with PE sections, use unknown required flags, or leave required
  bytes unaccounted for;
- `OatHeader`, per-dex/class/method tables, BSS maps, `CodeInfo`, stack maps,
  quick headers, and all 32-bit relative offsets that wrap, are unaligned, or
  point into the wrong logical region;
- VDEX section tables with duplicate/unknown required kinds, overlap, bad
  count/size arithmetic, missing external DEX, or checksum/type-table lengths
  inconsistent with the DEX headers; and
- ART headers with wrong component counts, image/bitmap/data sizes, compression
  blocks, pointer size, roots, reservation size, OAT range, or multi-image
  dependency ordering.

PE certificate-table offsets are file offsets rather than RVAs; zero-fill and
`.bss` have virtual bytes without raw bytes.  The validator must encode these
exceptions explicitly instead of applying one generic RVA rule.

### Address placement and code-generation reach

| Edge case | Required disposition |
|---|---|
| PE loads above 4 GiB while the ART heap image remains below 4 GiB | Use 64-bit native OAT addresses and independent image/OAT relocation ranges. Never truncate a module handle, code pointer, or delta into current 32-bit image-header fields. |
| Code and image are more than +/-2 GiB apart | Audit every x86-64 patcher/relocation kind. Replace invalid RIP-relative/direct-call encodings with approved indirection cells or thunks and include worst-case ASLR layouts in the native gate. |
| PE `SizeOfImage` or code span approaches 4 GiB | Reject before 32-bit RVAs, `RUNTIME_FUNCTION` RVAs, OAT code offsets, or region sizes overflow. Split artifacts only under an explicitly versioned multi-module design. |
| Preferred base is occupied, ASLR is disabled, or image reloads at a new base | Relocatable loader-managed PE must remain correct at every loader-selected base. `/FIXED` or a lucky preferred-base load cannot close that gate; the separately labeled PE-0 fixed mode must fail cleanly on collision. |
| Boot extension or multi-image component partially loads | Preserve component ordering and dependency checks. Roll back the entire uncommitted component without consuming or corrupting the remaining reservation. |
| Windows allocation granularity differs from ART/ELF/page alignment | Distinguish 64 KiB allocation granularity, hardware page size, PE `SectionAlignment`/`FileAlignment`, and logical OAT alignment. Never reuse `kElfSegmentAlignment` merely by name. |
| CPU/ISA features differ from the compiler host | Match the recorded x86-64 feature bitmap to the runtime CPU policy before publishing code; regenerate or fall back on mismatch. |

The image relocation visitor must treat heap objects/metadata, boot-image
dependencies, and actual OAT code as separate source/destination ranges.  In
particular, stored `ArtMethod` quick/JNI entrypoints and image-relro pointers
must be forwarded to the loader-selected PE address, not adjusted by the heap
image delta.

### Mutable state, concurrency, and unload

Normal module reuse makes all in-image mutable pages process-global for that
module instance.  Per-`OatFile` BSS, dex-cache slots, GC roots, and any
image-relro values that depend on a particular ART image cannot be silently
shared.  The design must either externalize all such state or prove that every
reference to the module is paired with the exact same state/image and
lifetime.  Read-only code and metadata may be shared only after this audit.

The module registry and publication protocol must handle:

- concurrent opens of the same identity without double initialization,
  reference leaks, or two owners believing they own one mutable module;
- concurrent opens of different identities with the same basename;
- a failed opener observing a module another thread has loaded but not yet
  validated/published;
- class unloading, deoptimization, JIT replacement, OSR, GC root scanning,
  stack walking, and exception delivery while AOT frames or pointers exist;
- last-reference teardown only after method entrypoints are redirected, code
  ranges unpublished, readers quiesced, per-instance roots removed, and all
  active stacks can no longer return into the module;
- `FreeLibrary` decrementing one reference rather than necessarily unloading;
  post-unload checks apply only after the process module registry proves the
  final loader reference is gone; and
- reverse-order rollback for every intermediate failure, including temporary
  page protections, VDEX/ART maps, BSS roots, module references, code-range
  publication, and dynamic function tables on the ELF path.

Use explicit acquire/release publication or the existing ART locking protocol;
plain pointer stores are not sufficient.  Never hold the class-linker/mutator
locks across loader operations without a documented lock-order audit.

### Unwind, exceptions, and process mitigations

For every non-leaf function that needs Windows unwind metadata, `.pdata` must
be sorted and non-overlapping; begin/end/unwind RVAs and chained records must be
inside the module, match emitted prologues/epilogues, and remain immutable for
the code lifetime.  Leaf functions may legitimately have no table entry, so
tests distinguish a valid leaf from missing required metadata.  Native gates
must cover `RtlLookupFunctionEntry`, `RtlVirtualUnwind`, debugger stack walk,
managed exception/deoptimization paths, VEH-translated NPE/SOE, and unwind
across mixed AOT/runtime/JNI frames.

Additional non-negotiable gates are:

- DEP/NX and no W+X at every stage; loader-managed AOT code is finalized before
  load and is never patched in place;
- CFG with every indirect quick/JNI/trampoline target usable under the chosen
  load-config/call-target policy, including strict mode and teardown;
- the project's existing CET user-shadow-stack rejection, since current ART
  long-jump/context-redirection behavior is incompatible;
- `ProhibitDynamicCode`/ACG, code-integrity guard, binary-signature policy, and
  antivirus behavior for normal PE, `SEC_IMAGE`, and executable ELF data views;
- no stale `RUNTIME_FUNCTION` records after manual unload and no duplicate
  registration for loader-managed PE; and
- instruction-cache flush only if any manual path actually changes executable
  bytes before RX publication; normal PE code must need no such mutation.

### Companion artifacts and transactional publication

The artifact triplet is published as one transaction.  A crash or cancellation
may leave temporary files but never an eligible mixed-generation set.  Write
to new names, flush file data/metadata as required, validate offline, then
atomically publish a manifest that binds every file hash, logical/container
version, compiler/runtime build identity, boot class path, ISA features, and
generation options.  Readers either select the complete old generation or the
complete new generation.

VDEX can be independently located but not weakly associated: DEX presence or
absence, external locations, per-DEX checksum/SHA identity, verifier deps, and
type tables must match the exact OAT records.  An uncompressed archive member
must meet mapping alignment; otherwise extract/copy into the immutable cache.
Map VDEX private and non-executable, allow temporary write only where current
ART behavior genuinely requires it, and restore the narrowest protection.

The ART image retains its own version and checksum, low-address/compressed-root
constraints, object/native-metadata sections, bitmap, component count, and
boot-dependency checksum.  Direct mapping uses copy-on-write semantics for
relocation; compressed images use anonymous destination memory.  No image root
or method entrypoint becomes visible to GC/class linking until image, OAT, VDEX,
bitmap, and all relocation ranges validate together.

## Required validation and native gates

Before claiming Windows AOT support, add structural and runtime checks for:

- selected-coat header/region bounds, alignment, protection, and version
  rejection;
- OAT/VDEX/ART checksum and boot-classpath identity;
- boot ART image and OAT at independent deltas, high/low PE ASLR placements,
  x86-64 displacement limits, and current-layout rejection;
- same-file repeated opens, different absolute-path instances, per-instance
  BSS/dex-cache isolation, class unloading, and reference-counted teardown;
- immutable-cache update/deletion/recovery and raw-validate/load race defenses;
- separate VDEX mappings and compressed/uncompressed ART-image mappings;
- every relocation class, including image relro and BSS slots;
- `.pdata/.xdata` lookup, virtual unwind, exception delivery, and post-unload
  disappearance, with no duplicate dynamic registration for normal PE;
- CFG enabled/disabled, `ProhibitDynamicCode`, applicable signing/image policy,
  antivirus scanning, and debugger/profiler module discovery;
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

1. Prototype a minimal import-free/no-entry PE OAT module and freeze `WOAT`
   only after `LoadLibraryExW`, descriptor, unwind, CFG, and unload gates pass.
2. Redesign boot `ImageHeader`/relocation to represent ART image and OAT with
   independent deltas and address widths; prove all code-reach constraints.
3. Move or redesign per-instance app BSS/dex-cache state, or prove a safe
   unique immutable-copy policy for repeated opens.
4. Make VDEX an independent mapping on the PE path and decide whether embedded
   DEX remains supported.
5. Split container-specific writer/loader code from logical OAT generation and
   build the Windows-native `dex2oat` PE prototype.
6. If any hard PE gate fails, select the preserved-ELF fallback before
   implementing a custom PE mapper; port exact Windows segment mapping and
   explicit unwind registration.
7. Complete ART-image raw mapping/decompression/relocation and all cross-file
   version/checksum rejection paths.
8. Produce `.art/.oat/.vdex`, run the full Server 2025 matrix, and decide
   boot-only versus app AOT with imageless/JIT fallback.

Until these items are closed, AOT/OAT remains deferred and the supported Windows
product path is imageless boot with nterp and managed/native JIT.

## Primary references

ART source contracts in this pinned tree:

- [`vendor/art/runtime/oat/oat_file.cc`](vendor/art/runtime/oat/oat_file.cc):
  `DlOpenOatFile`, `ElfOatFile`, force-load/reservation behavior, dynamic
  anchors, VDEX setup, and repeated-instance rationale.
- [`vendor/art/runtime/gc/space/image_space.cc`](vendor/art/runtime/gc/space/image_space.cc):
  boot reservation, OAT address equality checks, app-image independent OAT
  relocation, raw image mapping, and decompression.
- [`vendor/art/runtime/oat/image.cc`](vendor/art/runtime/oat/image.cc) and
  [`vendor/art/runtime/oat/image.h`](vendor/art/runtime/oat/image.h): image/OAT
  address fields, versions, reservation semantics, and relocation deltas.
- [`vendor/art/runtime/vdex_file.h`](vendor/art/runtime/vdex_file.h) and
  [`vendor/art/runtime/vdex_file.cc`](vendor/art/runtime/vdex_file.cc): VDEX
  section descriptors, validation, direct/archive mapping, and fixed-address
  overlay behavior.

Documented Microsoft contracts:

- [LoadLibraryExW](https://learn.microsoft.com/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw)
- [LoadLibraryW](https://learn.microsoft.com/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryw)
- [FreeLibrary](https://learn.microsoft.com/windows/win32/api/libloaderapi/nf-libloaderapi-freelibrary)
- [CreateFileMappingW and `SEC_IMAGE`](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-createfilemappingw)
- [MapViewOfFile3 and placeholder restrictions](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3)
- [MapViewOfFileEx](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffileex)
- [MapViewOfFile2](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile2)
- [VirtualAlloc2 and placeholders](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2)
- [PE/COFF format](https://learn.microsoft.com/windows/win32/debug/pe-format)
- [RtlAddFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtladdfunctiontable)
- [RtlDeleteFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtldeletefunctiontable)
- [RtlAddGrowableFunctionTable](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtladdgrowablefunctiontable)
- [RtlPcToFileHeader](https://learn.microsoft.com/windows/win32/api/winnt/nf-winnt-rtlpctofileheader)
- [SetProcessValidCallTargets](https://learn.microsoft.com/windows/win32/api/memoryapi/nf-memoryapi-setprocessvalidcalltargets)
