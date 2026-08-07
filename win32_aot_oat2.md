# Windows boot OAT-2 design

Status: detailed design, not implemented (2026-08-07).

This document specifies the optional OAT-2 Windows boot mapping architecture
referenced by [`win32_aot_oat.md`](win32_aot_oat.md). OAT-2 is a loader and
address-space topology name. It is not a new shared ART OAT version, ELF OSABI,
section-name family, or public artifact format.

The name is unrelated to the historical Windows JIT "J-2" gate. Both use
paging-section aliases, but they have different owners, lifetimes, placement,
metadata, and publication rules.

The accepted OAT-1 private-copy path remains the early boot-AOT implementation
and observation-mode default. OAT-2 is considered only after the native CFG
allocation experiment proves the required Windows mapping behavior. A failed
OAT-2 transaction falls back as one unpublished boot-artifact transaction; it
never silently weakens an explicitly requested CFG mode to OAT-1.

## Decision

OAT-2 retains the current path-sensitive Windows boot cache set:

```text
boot.art                         LZ4 ART image
boot.oat                         ordinary ART ELF64 OAT
boot.vdex                        ordinary matching VDEX
.oat_unwind.windows              Windows-only unwind transport
.oat_cfg.windows                 Windows-only CFG target transport
```

It retains Linux ART's ELF identity, the shared OAT version, the existing
section-local Windows metadata versions and checksums, 64-KiB Windows artifact
alignment, `kMaxPageSize == 16384`, and `ART_PAGE_SIZE_AGNOSTIC=1`. OATs remain
path-sensitive caches; byte identity between generations is not required.

The selected Windows topology is:

```text
one combined boot address-space placeholder at the selected relocation delta
  -> split into 64-KiB primary protection groups and inaccessible gaps
  -> one unnamed pagefile-backed section for the complete combined span
  -> one temporary, unrestricted-address RW/NX construction alias
  -> exact primary section views replacing mapped placeholders:
       image mutable groups       RW, later reduced where required
       image immutable groups     R
       OAT read-only groups       R
       OAT code groups            RX + invalid CFG targets from map creation
       OAT mutable/VDEX groups    RW, later reduced where required
       padding/gaps               untouched PAGE_NOACCESS placeholders
  -> populate and relocate only through non-executable writable addresses
  -> unmap the construction alias
  -> activate exactly the serialized CFG targets
  -> register unwind and publish the complete boot set
```

One paging section, rather than one section per `PT_LOAD`, keeps physical
backing and address translation simple. Exact primary views enforce different
protections without ever mapping non-code pages executable. The temporary
alias is a construction capability only and must not survive publication.

OAT-2 does not directly map `boot.oat` as a disk-backed executable view. It
copies the checked OAT and VDEX bytes into paging-section backing. Therefore
OAT-2 is a coherent dual-view design inside one process, not a claim of
cross-process cache sharing.

## Scope

The first OAT-2 implementation is deliberately bounded:

- Windows x64 on the existing Windows 10 version 1803-or-later API baseline;
- the selected single-component boot image only;
- executable `ElfOatFile` opens selected by the boot image transaction;
- `.oat_cfg.windows` version 1 and `.oat_unwind.windows` version 1;
- no application OAT, duplicate logical instances, or successful-load unload;
- no outgoing quick-code CFG instrumentation, XFG, ACG support, or security
  certification; and
- no ARM64, ARM64EC, x86, or ARMv7 enablement without separate native gates.

Validation-only OAT opens continue to use OAT-1 private-copy mapping. They
perform the same artifact validation but do not create executable views or CFG
state. OAT-2 owns the second, executable boot open and must be selected before
the combined image/OAT reservation is created.

## Why OAT-2 exists

OAT-1 populates an already committed private reservation as RW/NX and changes
the code pages to RX with `VirtualProtect()`. Windows documents that an
ordinary change to executable protection makes locations valid CFG targets by
default. `PAGE_TARGETS_NO_UPDATE` can preserve previously established CFG
state, but does not create invalid-by-default state. `PAGE_TARGETS_INVALID` is
not supported by `VirtualProtect()`.

OAT-2 establishes the executable view with invalid targets at mapping time and
populates its backing through a separate non-executable alias. The executable
view never becomes writable and never changes protection. This is the key
semantic difference; reducing commit or enabling cross-process sharing is not
the initial reason to adopt OAT-2.

## Windows API contract

The design uses only the existing Windows 10 API baseline:

| Operation | Required API and contract |
|---|---|
| Reserve combined address space | `VirtualAlloc2(MEM_RESERVE | MEM_RESERVE_PLACEHOLDER, PAGE_NOACCESS)` |
| Split a placeholder | `VirtualFree(MEM_RELEASE | MEM_PRESERVE_PLACEHOLDER)` at checked 64-KiB boundaries |
| Create coherent backing | unnamed `CreateFileMappingW(INVALID_HANDLE_VALUE, PAGE_EXECUTE_READWRITE)` paging section |
| Create the construction alias | `MapViewOfFile3`, section offset zero, full span, `PAGE_READWRITE`, no execute permission |
| Install primary groups | `MapViewOfFile3(MEM_REPLACE_PLACEHOLDER)` with an exact base, exact placeholder size, and group-specific protection |
| Restore a mapped group to a placeholder | `UnmapViewOfFile2(MEM_PRESERVE_PLACEHOLDER)` |
| Release or merge placeholders | `VirtualFree(MEM_RELEASE)` or `MEM_RELEASE | MEM_COALESCE_PLACEHOLDERS` with exact ranges |
| Activate CFG entries | `SetProcessValidCallTargets()` with ascending 16-byte-aligned offsets |

Microsoft documents that `MEM_REPLACE_PLACEHOLDER` supports data and
pagefile-backed section views, requires `BaseAddress` and `ViewSize` to match
the placeholder exactly, and does not accept nonzero address requirements in
that replacement call. Section offsets remain 64-KiB aligned; view sizes are
page multiples. OAT-2 makes every group start and section offset 64-KiB aligned
and rounds its end to the next nonconflicting 64-KiB boundary.

The selected CFG candidate maps each code group with:

```cpp
PAGE_EXECUTE_READ | PAGE_TARGETS_INVALID
```

`PAGE_TARGETS_INVALID` is not passed to `CreateFileMappingW` and is never used
with `VirtualProtect()`. The memory-protection documentation permits it with
executable protections and explicitly excludes `VirtualProtect()` and
`CreateFileMappingW`; `MapViewOfFile3` accepts a desired page protection but
does not separately enumerate this modifier. The native allocation gate must
therefore prove that the supported SDK/OS combination accepts the composed
protection on a placeholder-replacing paging-section view and preserves exact
target behavior. Failure of that gate blocks explicit OAT-2 CFG. It does not
authorize substitution of `PAGE_TARGETS_NO_UPDATE` or a transient W+X path.

## Artifact and layout preflight

OAT-2 does not add an on-disk mode bit. Product selection and the runtime
capability gate choose the loader. Before reserving address space, a read-only
preflight validates the complete matching cache set and constructs an
immutable `WindowsBootViewPlan`.

The preflight reuses the existing ELF/OAT/VDEX/image parsers and requires:

1. one selected boot component and one relocation delta for its image and OAT;
2. the current Windows ELF profile, including 64-KiB `PT_LOAD` alignment and
   file/virtual congruence;
3. sorted, nonoverlapping R, RX, and RW `PT_LOAD` ranges with no W+X or
   conflicting shared 4-KiB page;
4. checked image, OAT, VDEX, BSS, `oatdex`, relro, unwind, and CFG ranges;
5. every primary protection-group start, combined-section offset, and
   placeholder split at a 64-KiB boundary;
6. every mapped group size rounded to a 4-KiB page and, for the initial
   implementation, to a 64-KiB placeholder boundary without overlapping the
   next group;
7. gaps represented explicitly rather than inherited from a neighboring view;
8. `.oat_cfg.windows` present and complete before an explicit-mode allocation
   is attempted; and
9. checked signed/unsigned offset and relocation representability.

The plan coalesces adjacent ranges only when their construction and final
protections, ownership role, and CFG role are identical. An RX group is never
coalesced with image data, metadata, a gap, or a writable group. Program
headers and the ART image layout authorize primary mappings; section headers
do not.

The current writer is expected to satisfy this plan without changing the
shared artifact format. If a native preflight finds an image boundary that is
not independently representable at 64 KiB, the Windows image writer may add
Windows-only padding. Such a change must retain the same OAT/image versions,
remain behind the Windows artifact-alignment guard, and pass a Linux
byte-layout regression before OAT-2 integration continues.

## Address placement

OAT-2 replaces the existing ordinary combined boot reservation; it cannot be
retrofitted over one. The selection decision therefore occurs before
`ImageSpace` reserves the boot range.

For a relocatable load, `VirtualAlloc2` receives the complete checked span,
64-KiB alignment, and the same low/high placement bounds used by the Windows
boot-image policy. The returned placeholder base determines the one image/OAT
relocation delta. For an exact load, the requested base must already be
64-KiB aligned and the returned base must equal it. A collision, out-of-range
result, or unrepresentable delta rejects the complete OAT-2 attempt.

After reservation, split the original placeholder at every group/gap boundary.
No mapping call may rely on a hint: each replacement call names the exact
placeholder base and size and verifies the exact returned address.

## Backing and mapping transaction

The transaction uses checked half-open ranges throughout. In simplified form:

```cpp
plan = PreflightBootSet(image, oat, vdex, cfg_mode);
placeholder = ReservePlaceholder(plan.base_policy, plan.span);
SplitPlaceholder(placeholder, plan.boundaries);

section = CreatePagefileSection(plan.span, PAGE_EXECUTE_READWRITE);
alias = MapWholeSection(section, PAGE_READWRITE);  // no execute permission

for (group : plan.primary_groups) {
  DWORD protection = group.is_code
      ? PAGE_EXECUTE_READ | PAGE_TARGETS_INVALID
      : group.initial_protection;  // PAGE_READONLY or PAGE_READWRITE
  group.primary = ReplaceExactPlaceholder(
      section, plan.base + group.offset, group.offset, group.size, protection);
}

PopulateImage(alias, plan);
PopulateElfLoadSegments(alias, plan);
PopulateVdex(alias, plan);
RelocateAndValidateImageAndOat(plan);
ReduceMutablePrimaryProtections(plan);
FlushInstructionCache(plan.code_groups);
VerifyVirtualLayout(plan);

UnmapConstructionAlias(alias);
CloseHandle(section);
ActivateCfgTargets(plan);
RegisterAndVerifyUnwind(plan);
PublishBootSet(plan);
```

The concrete order may map the alias before or after the primary groups, but
all resources remain unpublished and ledger-owned until the same final state
is reached. The following invariants are mandatory:

- primary code is mapped RX and invalid-by-default in its first mapping call;
- primary code is never writable and never receives `VirtualProtect()`;
- the construction alias is always RW/NX and is the only address used to copy
  code bytes;
- immutable primary pages may be populated only through the alias;
- mutable image/relro pages may begin RW and may only lose permissions;
- untouched paging-section bytes and all placeholder gaps begin zero or
  inaccessible as their plan requires;
- no code or root is published while the alias or section handle can be used
  by ordinary runtime code; and
- alias unmapping is required, not best-effort, before CFG activation.

The section's maximum protection must permit both RX and RW views, but no
mapped view is RWX. `SEC_COMMIT` is selected initially. It charges backing for
the complete combined span, while the two views share that backing. `SEC_RESERVE`
and demand commit are deferred until measurement proves full-span commit is a
material problem and a separate commit/rollback design is accepted.

## Population and ART integration

The writable alias uses one translation for every combined boot address:

```text
alias_address = alias_base + (primary_address - primary_base)
```

The existing OAT ELF parser remains authoritative for load bias, file ranges,
zero-fill tails, segment ordering, dynamic symbols, and OAT fields. On OAT-2,
the Windows file-backed copy helper writes checked `p_filesz` bytes to the
translated alias rather than temporarily changing primary protections. The
paging section supplies initial zero bytes for `p_memsz - p_filesz` and gaps;
the helper still verifies the zero-fill and protection plan.

`ComputeFields -> LoadVdex -> Setup` remains the logical OAT transaction.
`LoadVdex()` copies the matching VDEX into the translated `oatdex` aperture and
returns a primary-address slice sharing the combined owner. It does not create
a disk file view or an independent `VirtualAlloc` owner.

The LZ4 image is decompressed into writable primary image pages or their alias
translation according to the existing relocation code's narrowest integration
path. OAT code is never modified through its primary address. Image and
`.data.img.rel.ro` writes finish before their final R protection is applied.

The first implementation may leave existing image relocation writes on RW/NX
primary image pages while using the alias for immutable/OAT code population.
It need not rewrite all image relocation code to use aliases. The important
boundary is that no executable primary page is writable.

The combined mapping owner supplies non-owning `MemMap` slices to `ImageSpace`,
`ElfOatFile`, and VDEX. Those slices never independently call
`VirtualFree()` or `UnmapViewOfFile()`. Linux and the OAT-1 Windows owner path
remain unchanged. OAT-2 primary views do not share one Windows
`AllocationBase`; they must not enter OAT-1's reuse helper, which deliberately
requires one common private-allocation owner.

## Implementation surface

Keep the Windows difference in one boot-only owner rather than turning
`MemMap` into a general placeholder or section loader:

| Surface | OAT-2 responsibility |
|---|---|
| `ImageSpace::Loader` / boot layout | Select OAT-2 before reservation, request the preflight plan, and publish only the complete transaction |
| new `runtime/multiplatform/windows` helper | Own placeholder splitting, section/alias/primary views, address translation, protection verification, resource ledger, and rollback |
| `ElfFileImpl::Load()` Windows branch | Reuse the existing program-header walk and write checked file bytes through the supplied alias translation instead of creating an OAT-1 reservation |
| `OatFileBase` / `ElfOatFile` | Retain `ComputeFields -> LoadVdex -> Setup`; hold non-owning slices backed by the combined owner |
| VDEX Windows copy helper | Copy into the translated `oatdex` alias and return the existing primary-address contract |
| Windows CFG parser | Refactor the version-1 codec so file preflight and mapped validation use one implementation; do not create a second format parser |
| Windows unwind registry | Retain the existing table format/registration owner and attach it to the OAT-2 transaction before publication |
| OAT/image writers | No initial change; add Windows-only padding only if W-035 preflight proves a real 64-KiB group-boundary gap |

The helper should expose semantic operations, not raw handles, for example:

```text
ReserveAndMap(plan)
WritableAliasFor(primary_range)
PrimarySlice(range)
ReduceProtection(range, final_protection)
RemoveConstructionAlias()
ActivateCfg(table)
RegisterUnwind(table)
Publish()
Rollback()
```

Construction runs on the boot-loading thread before roots, method entrypoints,
or generated-code ranges are published. No mutator or compiler thread may see
the owner or alias. Publication transfers the stable primary slices to the
existing runtime owners; the construction methods become unavailable.

## CFG activation

OAT-2 requires CFG enabled in the process and a validated
`.oat_cfg.windows`. Observation-only startup does not need OAT-2.

After population, relocation, final protection reduction, cache flush, mapped
CFG-table validation, and construction-alias removal:

1. group every serialized target by its containing primary RX view;
2. calculate the API base and size from that exact view, not from the complete
   boot reservation;
3. translate each `oatdata`-relative target to a checked view-relative offset;
4. require its final virtual address and API offset to be 16-byte aligned on
   x86-64;
5. pass ascending unique `CFG_CALL_TARGET_INFO` records with only
   `CFG_CALL_TARGET_VALID` set;
6. verify success for every view; and
7. use a guarded PE caller to prove selected quick/JNI targets pass and a
   deliberately omitted aligned address terminates a disposable child.

No target from the ART image, read-only metadata, padding, a trampoline-internal
label, or the construction alias is submitted. A partial API failure leaves
the boot set unpublished. Cleanup unmaps the complete primary RX views, which
discards their CFG state; it does not attempt to repair and reuse a partially
activated address range.

OAT-2 only controls target validity for CFG-instrumented indirect call sites.
It does not instrument outgoing indirect branches in generated quick code and
does not imply XFG, export suppression, strict-CFG, or security-hardening
support.

## Unwind, publication, and lifetime

After CFG activation, validate and register the existing
`.oat_unwind.windows` table, verify representative lookups, and retain its
function-table owner beside the combined mapping owner. Publication is the
single transition that makes image roots, generated-code ranges, and method
entrypoints visible to the runtime.

Required publication order:

```text
all cache files pinned and preflight complete
  -> combined placeholder and section views complete
  -> image/OAT/VDEX populated and cross-validated
  -> image relocation and final non-code protections complete
  -> executable cache flushed and construction alias removed
  -> exact CFG targets activated
  -> unwind table registered and sampled
  -> image roots, code ranges, and entrypoints published
```

The accepted boot OAT remains mapped for process lifetime. Successful-load
unloading is out of scope. Orderly teardown unregisters unwind before releasing
primary views. As in OAT-1, an unexpected `RtlDeleteFunctionTable()` failure is
a runtime invariant failure; it does not block early implementation work.

## Ownership and rollback

A dedicated Windows-only owner records facts, not inferred memory state:

```text
WindowsBootSectionOwner
  combined base and span
  original relocation delta
  paging-section handle, while open
  construction alias base and size, while mapped
  ordered primary-view records
  ordered remaining-placeholder records
  final-protection and CFG state per primary view
  unwind registration owner
  publication state
```

Each acquisition appends one ledger record only after success. Cleanup is
idempotent and reverses successful operations:

1. if published, use only the separately designed orderly teardown path;
2. unregister unwind if it was registered;
3. unmap the construction alias if still present;
4. unmap each primary view in reverse order with
   `MEM_PRESERVE_PLACEHOLDER` when continued placeholder ownership is useful;
5. if preserving a view fails, retry ordinary unmap for that exact view and
   record that its address is free rather than a placeholder;
6. release each remaining split placeholder independently with size zero at
   its recorded base; coalescing is an optimization, not a cleanup prerequisite;
7. close the section handle if still open; and
8. discard all non-owning ART slices before destroying the owner.

Never call `VirtualFree()` on a mapped section view, never call
`UnmapViewOfFile2()` on an interior logical slice, and never guess ownership
from `VirtualQuery()`. A rollback fault is reported with the operation and
Windows error code. It cannot cause OAT-1 reuse of the same partially cleaned
range. If both preserve-unmap and ordinary unmap fail for the same unpublished
view, safe fallback is no longer possible in that process; treat it as a fatal
mapping invariant rather than publishing or reusing the range.

Fault injection must cover failure after every placeholder split, alias map,
primary map, population range, final protection, cache flush, CFG batch,
unwind registration, and prepublication validation. Each child must finish
with no published entrypoint, no surviving view/handle owned by the failed
transaction, and no stale CFG target at a subsequently allocated address.

## Product selection and fallback

OAT-2 starts as an explicit experimental product option, not an environment
variable hidden inside `ElfFile`:

```text
windows boot OAT loader: oat1-observe | oat2-explicit
```

`oat2-explicit` requires, before reservation:

- the supported Windows API baseline and expected 4-KiB page/64-KiB allocation
  granularity;
- CFG enabled and the required APIs available;
- a passing native `MapViewOfFile3` invalid-target capability record for the
  exact OS/architecture support tier;
- a complete matching `.oat_cfg.windows` table;
- a representable single-component boot view plan; and
- no incompatible dynamic-code prohibition.

If a preflight requirement is absent, the explicit option is rejected before
address-space mutation. If construction later fails, the complete unpublished
transaction is rolled back and the reviewed imageless fallback is selected.
It must not continue with OAT-1 under an option that promised explicit targets.

An eventual `auto` policy may choose OAT-2 only after the capability and full
boot gates are accepted. OAT-1 observation remains valid independently.

## Measurements

OAT-2 is not assumed to save memory. The native comparison must record, for
the same cache generation and logical workload:

| Quantity | Required breakdown |
|---|---|
| Reserved address space | combined primary span, mapped group bytes, gap placeholders, alias span |
| Commit charge | before section creation, after creation, after both views, after population, after alias removal |
| Working set | private/shared working set for image, OAT, VDEX, and page tables |
| Startup | preflight, reservation/split, mapping, copy/decompression, relocation, CFG, unwind, total |
| Artifact layout | payload bytes, 64-KiB padding, group count, view count |
| Resource lifetime | handle count and mapped-view count before, during, after success/failure |

Compare OAT-2 against OAT-1 and imageless startup. Two views of one paging
section must not be counted as two independent copies of backing commit, but
their page-table and working-set costs remain real. The validation-only OAT-1
open may create a temporary peak and must be included.

## Acceptance gates

Implementation is divided into three packages.

### W-033: allocation semantics

No ART integration:

- prove or reject `MapViewOfFile3(MEM_REPLACE_PLACEHOLDER,
  PAGE_EXECUTE_READ | PAGE_TARGETS_INVALID)`;
- prove exact replacement, alias coherence, invalid-by-default code, exact
  target activation, omitted-target failure, and no W+X;
- exercise split, preserve, independent release, collision, and every cleanup
  branch in disposable children; and
- compare `SEC_COMMIT` resource behavior with the existing OAT-1/JIT evidence.

This is the next implementation step. A failure may revise the selected OAT-2
API sequence; it must not change OAT-1 semantics.

### W-034: synthetic OAT-2 owner

- implement the owner/ledger and view-plan types behind Windows-only build
  guards;
- construct multiple R/RW/RX/gap primary views from one section and one alias;
- populate a synthetic ELF-like plan, flush, remove the alias, activate targets,
  register synthetic unwind, and publish only after all steps;
- run deterministic fault injection after every acquisition; and
- retain a zero-diff Linux build and the existing OAT-1 gates.

### W-035: single-component boot integration

- make `ImageSpace` select OAT-2 before combined reservation;
- reuse the existing ELF/OAT/VDEX/image parsers and checksums;
- pass validation-only OAT-1 plus executable OAT-2 opens;
- start the real LZ4 boot image with JIT disabled;
- pass guarded quick/JNI calls, target omission, unwind lookup/virtual unwind,
  VDEX/image mismatch, relocation, and complete rollback gates;
- record OAT-1/OAT-2/imageless startup and resource measurements; and
- keep the normal product default unchanged until the result is reviewed.

Application OAT, multi-component boot topology, other ISAs, successful-load
unloading, direct disk-backed sharing, outgoing quick-code CFG instrumentation,
and security hardening remain later packages.

## Rejected initial alternatives

| Alternative | Disposition |
|---|---|
| Change the shared OAT version or ELF identity | Rejected; mapping topology is not an artifact ABI change |
| Map `boot.oat` directly as several disk-backed views | Rejected initially; writable/COW data, BSS, VDEX replacement, cross-file ownership, and rollback add complexity without helping the explicit-CFG proof |
| `MapViewOfFileEx(FILE_MAP_EXECUTE | FILE_MAP_TARGETS_INVALID)` at a hinted base | Rejected; it can request invalid targets but cannot atomically replace the exact placeholder, and a hint does not satisfy ART placement |
| One full-span RX primary view, then remove execute from data | Rejected; it temporarily grants execute outside ELF-authorized code ranges |
| Private RW population followed by `VirtualProtect(..., PAGE_TARGETS_NO_UPDATE)` | Rejected; it does not establish invalid-by-default state |
| Private RX-invalid pages without a writable alias | Rejected; there is no supported no-W+X population path |
| One paging section per `PT_LOAD` | Rejected initially; it multiplies handles, aliases, offset translation, and rollback state |
| Keep the RW alias after publication | Rejected; OAT-2 has no runtime code-patching requirement |
| Fall back from requested explicit OAT-2 to OAT-1 observation | Rejected; that silently weakens the selected mode |

## Remaining blockers and design risks

The design is implementable in stages, but product enablement has four real
blockers:

1. **CFG mapping semantics:** the exact `MapViewOfFile3` plus
   `PAGE_TARGETS_INVALID` composition must pass W-033 on the supported native
   host and remain compatible with the project SDK/import contract.
2. **Combined-view boundaries:** native preflight must prove current Windows
   image and OAT groups are independently representable at 64 KiB without an
   on-disk version change.
3. **ImageSpace ownership:** the combined placeholder/section owner must be
   selected before the current ordinary boot reservation and shared safely by
   image, OAT, and VDEX slices.
4. **Rollback completeness:** partial CFG activation and partial placeholder
   replacement must leave no published pointer, stale target, leaked view, or
   reusable contaminated address range.

Commit/resource cost, antivirus behavior, debugger presentation, and startup
time are measurements and acceptance risks, not reasons to redesign the
artifact before W-033/W-034. An `RtlDeleteFunctionTable()` invariant failure,
application OAT, OAT unloading, and security hardening do not block the first
boot-only OAT-2 experiment.

## References

- [Main Windows AOT/OAT design](win32_aot_oat.md)
- [Implementation tracker](win32_aot_oat_tracker.md)
- [Microsoft `VirtualAlloc2`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2)
- [Microsoft `MapViewOfFile3`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3)
- [Microsoft `UnmapViewOfFile2`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-unmapviewoffile2)
- [Microsoft `VirtualFree`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfree)
- [Microsoft memory protection constants](https://learn.microsoft.com/en-us/windows/win32/memory/memory-protection-constants)
- [Microsoft `SetProcessValidCallTargets`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-setprocessvalidcalltargets)
