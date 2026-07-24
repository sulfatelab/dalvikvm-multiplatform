# Win64 heap memory and embedded dlmalloc design — W-013

**Status:** accepted target design; implementation remains OPEN
**Updated:** 2026-07-24
**Target baseline:** Windows 10 version 1803 or later (NTDDI_WIN10_RS4)
**Related:** [win32_open_items.md](win32_open_items.md) W-013,
[win32_jit_memory.md](win32_jit_memory.md), and
[win64_art_port.md](win64_art_port.md) §9c

## 0. Executive decision

The permanent design is:

> ART owns virtual memory; embedded dlmalloc only manages chunks inside an
> ART-owned arena.

```text
ART heap lock / JIT lock
          |
ART mspace wrapper
  mspace-only, no mmap, no internal locks
          |
owner-attached MoreCore callback
          |
MallocSpace / JitMemoryRegion
          |
MemMap platform backend
  Linux:   mmap / mprotect / madvise
  Windows: VirtualAlloc2 / VirtualProtect /
           DiscardVirtualMemory / VirtualFree
```

This keeps allocator policy common across Linux and Windows. The Windows port
implements the virtual-memory operation, address constraint, and release
semantics in `MemMap`; it does not let dlmalloc become a second virtual-memory
owner.

The current `_WIN32`/`WIN32` masking in `art-dlmalloc.cc` was a valid Phase-2
recovery workaround, but it is not the final design. W-013 remains open until
the masking, implicit low-address policy, global mspace-owner lookup, and
Windows mapping ownership gaps are removed and the closure matrix passes.

## 1. Goals and invariants

### 1.1 Required behavior

1. Keep Windows ART behavior as close to Linux ART as the operating-system VM
   models permit.
2. Keep the common heap, mspace, GC, JIT growth, and footprint-limit logic.
3. Put every Windows-specific VM operation behind `MemMap`.
4. Fail a low-address request when no complete low range exists. Never satisfy
   it with a high mapping.
5. Do not consume low address space for mappings whose pointer representation
   does not require it.
6. Preserve one external lock owner for every mspace; do not add a second,
   nested dlmalloc lock.
7. Make allocation failure deterministic and report `ENOMEM` to ART.
8. Keep the initial implementation straightforward and measurable. In
   particular, do not combine W-013 with a speculative lazy-commit redesign.

### 1.2 Permanent embedded-dlmalloc configuration

ART's embedded dlmalloc shall remain configured as:

```text
HAVE_MMAP=0
HAVE_MREMAP=0
HAVE_MORECORE=1
MORECORE_CONTIGUOUS=1
USE_LOCKS=0
ONLY_MSPACES=1
MSPACES=1
```

`MORECORE_CONTIGUOUS=1` selects the page-size growth granularity expected by
ART. `create_mspace_with_base()` marks its initial externally supplied segment
as non-contiguous internally, so later growth still follows dlmalloc's
non-contiguous MoreCore path: request bytes, query the new break with
`MoreCore(0)`, and attach the resulting segment. This is existing dlmalloc
behavior and is not a reason to use the Win32 mmap allocator.

All ART mspaces are created with `locked=false`. Heap mspaces are serialized by
`DlMallocSpace::lock_`; JIT mspaces are serialized by `Locks::jit_lock_`.
Internal dlmalloc locking is therefore redundant and risks lock-order problems.
The final code must state this configuration directly instead of obtaining it
as a side effect of hiding the Windows preprocessor macros.

## 2. What `create_mspace_with_base()` actually does

`create_mspace_with_base(base, capacity, locked)`:

1. initializes dlmalloc's process-wide size and granularity parameters if this
   is the first mspace;
2. validates that `capacity` can contain `malloc_state`, the top chunk, and
   required bookkeeping;
3. writes `malloc_state` and initial chunk metadata into the supplied range;
4. marks the supplied segment `EXTERN_BIT`, so dlmalloc does not unmap or
   release it;
5. initializes bins and the top chunk;
6. applies the requested internal-lock setting; and
7. returns without obtaining virtual memory from the operating system.

It does not call mmap, `VirtualAlloc`, or MoreCore during successful creation.
The owner can therefore be attached immediately after creation and before any
allocation can trigger growth.

This distinction is central to W-013: the base range is already an ART-owned
`MemMap`. dlmalloc receives usable bytes within that range; it does not receive
authority to create unrelated mappings.

## 3. Current implementation and remaining divergence

The Phase-2 implementation is functional enough for imageless boot and the
existing Wine/native probes, but it contains deliberate recovery shortcuts:

| Area | Current behavior | Target behavior |
|------|------------------|-----------------|
| dlmalloc platform detection | `art-dlmalloc.cc` temporarily undefines `_WIN32` and `WIN32` while including `dlmalloc.c` | Keep Windows macros visible; make dlmalloc defaults respect embedding-provided `HAVE_*` values |
| mspace VM source | ART forces MoreCore only because the Win32 default block is skipped | ART explicitly selects MoreCore-only mspaces on every OS |
| granularity | Macro masking happens to use the non-Windows page-size path | Win32 MoreCore-without-mmap explicitly uses system page size, not 64-KiB allocation granularity |
| failure action | Win32's empty default failure action is avoided accidentally | Embedded allocator explicitly sets `errno = ENOMEM` |
| MoreCore owner | Callback discovers heap/JIT ownership through `Runtime::Current()`, the JIT cache, and a continuous-space scan | Each mspace stores its provider in dlmalloc extension state |
| anonymous address policy | A null or low hint can imply low placement even when `low_4gb=false` | Anywhere, below-4-GiB, and exact-address requests are explicit |
| low allocation | `VirtualQuery` scans holes, then an unrestricted allocation may be tried and rejected | `VirtualAlloc2` applies `MEM_ADDRESS_REQUIREMENTS`; no high fallback |
| aligned anonymous maps | Common code over-allocates and partially unmaps | Windows requests alignment directly or retains one owner reservation |
| partial release | `TargetMUnmap` uses whole-allocation `VirtualFree(MEM_RELEASE)` although common paths can request a suffix/prefix release | Windows ownership records preserve the allocation base; logical shrink uses range operations and whole release occurs only at destruction |
| low metadata | Win64 currently forces ordinary arena pools, compiler metadata, LinearAlloc, and the card table low | Keep low placement only where an encoding or object-reference contract requires it |

The current code must not be described as complete merely because Hello,
GcProbe, or the JIT suites pass. `GcProbe` primarily exercises large-object
space and is not a non-moving dlmalloc pressure test.

## 4. dlmalloc integration design

### 4.1 Make the Win32 defaults embedding-safe

The Win32 configuration block in `vendor/external/dlmalloc/dlmalloc.c` shall
stop unconditionally overwriting embedding configuration. At minimum,
`HAVE_MMAP`, `HAVE_MORECORE`, and the failure action must use `#ifndef`-style
defaults. Standalone Win32 dlmalloc may retain its current VirtualAlloc-backed
mmap defaults when its embedder supplied no policy.

ART shall define the complete configuration before including `dlmalloc.c` and
retain compile-time guards that reject an accidental `HAVE_MMAP != 0` or
`HAVE_MORECORE != 1` build.

When Win32 is configured with contiguous MoreCore and without mmap,
`init_mparams()` shall choose `dwPageSize` as dlmalloc granularity. The 64-KiB
`dwAllocationGranularity` is a placement constraint for reserve/map bases, not
the correct unit for activating pages already reserved inside an ART arena.

After this change, `art-dlmalloc.cc` can include `dlmalloc.c` with `_WIN32` and
`WIN32` intact. Windows headers and platform facts remain available, while
allocator ownership remains controlled by ART.

### 4.2 Hide raw mspace creation behind an ART wrapper

Introduce an ART-owned wrapper around `create_mspace_with_base()`. Its contract
is conceptually:

```cpp
class MspaceMoreCoreProvider {
 public:
  virtual void* MoreCore(const void* mspace, intptr_t increment) = 0;
 protected:
  ~MspaceMoreCoreProvider() = default;
};

mspace ArtCreateMspaceWithBase(void* base,
                               size_t initial_footprint,
                               MspaceMoreCoreProvider* provider);
```

The concrete names may follow local ART conventions, but the behavior is
fixed:

1. call `create_mspace_with_base(base, initial_footprint, false)`;
2. store `provider` in `malloc_state::extp`;
3. store an ART validation magic in `malloc_state::exts`;
4. return only after the attachment is complete; and
5. clear or invalidate the attachment before the provider can be destroyed.

`extp` and `exts` are explicitly unused extension fields in this dlmalloc
version. Using them avoids a global registry, runtime singleton lookup, heap
continuous-space scan, or special JIT ownership branch.

The MoreCore callback validates the magic and provider, then dispatches
directly to that provider. `MallocSpace` and `JitMemoryRegion` provide the same
small interface while retaining their existing growth logic.

### 4.3 Lock contract

The wrapper always passes `locked=false`. Every mutating mspace operation must
run under the owner's existing lock:

| Owner | Required lock |
|-------|---------------|
| `DlMallocSpace` | `DlMallocSpace::lock_` |
| `JitMemoryRegion` | `Locks::jit_lock_` |

Debug builds shall assert the owner lock in the provider's MoreCore method and
at common mutation entrypoints. A source/configuration test shall reject new
raw `create_mspace*()` call sites outside the wrapper and reject an mspace
created with internal locking enabled.

This is not a general recommendation to remove allocator synchronization. It
is a single-owner locking design: ART owns synchronization and dlmalloc is an
unlocked component inside that critical section.

## 5. Explicit `MemMap` address policy

### 5.1 Three policies

The Windows backend must receive one explicit address policy:

| Policy | Meaning | Failure rule |
|--------|---------|--------------|
| Anywhere | No address constraint | Let Windows choose; do not deliberately consume low VA |
| Below 4 GiB | Entire half-open range must fit in `[0, 2^32)` | Fail with `ENOMEM`; never retry unrestricted |
| Exact address | The returned base must equal the requested base | Fail without relocating; also enforce low range when the caller requested both |

The existing public `MemMap` API can remain largely common. `MapInternal()` can
translate `addr`, `low_4gb`, reservation, and fixed/reuse state into the
explicit platform request. The Windows backend must not infer low placement
from `start == nullptr`, from a low address hint, or from absence of
`MAP_FIXED`.

All range checks must use overflow-safe half-open arithmetic. A mapping ending
exactly at `0x1'0000'0000` is valid; a mapping whose last byte is at or above
that boundary is not.

An exact request has two ownership cases. Creating a new Windows reservation
requires an allocation-granularity-aligned base. Reusing a page-aligned
subrange of an existing ART reservation is not a new reservation: transfer the
logical range from that known owner and activate/protect it in place. Do not
attempt a second overlapping `VirtualAlloc2` reservation.

### 5.2 Windows 10 implementation

Anonymous mappings use `VirtualAlloc2` with `MEM_RESERVE | MEM_COMMIT`.
Below-4-GiB mappings provide `MEM_ADDRESS_REQUIREMENTS`:

- lowest usable base at or above the process allocation granularity, leaving
  the null region unavailable;
- inclusive highest ending address `UINT32_MAX`;
- requested alignment when ART requires more than the default allocation
  granularity.

Exact new reservations pass the exact, allocation-granularity-aligned base and
validate the complete range before the system call. Exact reuse inside an ART
reservation follows the ownership-transfer path above. Anywhere mappings pass
no address requirements.

This replaces the anonymous `VirtualQuery` first-fit scan. Windows performs
the constrained search atomically inside the allocation operation, so there is
no scan-then-reserve race and no unrestricted high-address fallback.

The already implemented JIT pagefile-section path continues to use
`MapViewOfFile3` plus the same address-requirements model. It is not replaced by
anonymous heap allocation and creates no disk file.

### 5.3 Alignment and ownership

Windows cannot partially release a `VirtualAlloc` reservation with
`VirtualFree(..., MEM_RELEASE)`: the address must be the original allocation
base and the size must be zero. Therefore Windows must not implement common
over-allocate/align/shrink operations by releasing arbitrary prefixes or
suffixes.

For an aligned anonymous request, prefer a direct `VirtualAlloc2` alignment
requirement and allocate only the final size. Where a common ART operation
logically shrinks a mapping, retain the original reservation base/size for
destruction, update the logical accessible range, and deactivate or discard
the unused pages. Release the whole reservation exactly once when its owning
`MemMap` is destroyed.

Mapped section views remain owned by `UnmapViewOfFile`, not `VirtualFree`.
Ownership kind must be known rather than guessed by trying both release APIs.

## 6. Heap growth and page-state operations

The common `MallocSpace::MoreCore()` sequence remains the reference behavior:

```text
positive increment: activate [old_end, new_end), then return old_end
zero increment:     return current end
negative increment: discard and deactivate [new_end, old_end), return old_end
```

Add explicit `MemMap` range operations with platform backends:

| Semantic operation | Linux backend | Windows backend |
|--------------------|---------------|-----------------|
| Activate range | `mprotect(..., PROT_READ | PROT_WRITE)` | `VirtualProtect(..., PAGE_READWRITE)` |
| Deactivate range | `mprotect(..., PROT_NONE)` | `VirtualProtect(..., PAGE_NOACCESS)` |
| Discard contents | `madvise(..., MADV_DONTNEED)` | `DiscardVirtualMemory(...)` |
| Destroy owner | `munmap` | whole `VirtualFree(..., MEM_RELEASE)` or `UnmapViewOfFile` by ownership kind |

The callers retain common growth and trimming decisions; only the backend
operation differs. Range methods validate page alignment, containment in the
owning mapping, and zero-length behavior.

### 6.1 Initial commitment policy

For the first complete implementation, malloc spaces continue to use
`MEM_RESERVE | MEM_COMMIT` for their full capacity and then protect inactive
pages `PAGE_NOACCESS`.

This reserves system commit charge but does not make every page physically
resident. It keeps the logical behavior close to the current Linux ART path
and ensures later activation cannot fail because new commit charge is
unavailable. Windows commit accounting is stricter than a typical overcommit
Linux host, so large `-Xmx` configurations must be measured explicitly.

Reserve-only plus incremental `MEM_COMMIT` is a possible later optimization,
not part of W-013's initial fix. It changes failure timing inside MoreCore and
requires deliberate allocation-failure propagation for both dlmalloc and
RosAlloc. It shall not be introduced merely to reduce observed commit charge.

## 7. Low-4-GiB consumers

Low placement is a scarce correctness resource, not a Windows-wide default.

### 7.1 Permanent low consumers

The following ranges remain below 4 GiB where applicable:

- Java object spaces, including moving and non-moving spaces;
- large-object space object mappings;
- requested image and heap reservations whose object/reference format requires
  low addresses; and
- the complete JIT primary view described in
  [win32_jit_memory.md](win32_jit_memory.md).

### 7.2 Consumers to audit and normally release from low VA

The following are metadata or native implementation storage and should use
anywhere mappings unless a specific encoding audit proves a constraint:

- ordinary LinearAlloc storage;
- runtime, compiler, and JIT metadata arena pools;
- card tables, space bitmaps, read-barrier tables, and allocation-info maps;
- native stacks, reference tables, temporary mappings, and test buffers.

The existing Win64 blanket low placement for `arena_pool_`, `jit_arena_pool_`,
`linear_alloc_arena_pool_`, and the card table is a Phase-2 stabilization
policy, not the target architecture. Remove each constraint only after auditing
its consumers. If a field or instruction encoding truncates a pointer, fix and
validate that encoding at its construction site instead of forcing an entire
unrelated arena low.

## 8. Rejected and deferred alternatives

| Alternative | Decision |
|-------------|----------|
| Keep masking `_WIN32`/`WIN32` permanently | Rejected: it hides platform facts, changes unrelated defaults accidentally, and makes configuration depend on include tricks |
| Enable dlmalloc's Win32 mmap allocator | Rejected: it allocates outside ART's arena and can return object memory above 4 GiB |
| Let low allocation fall back high and reject afterward | Rejected: it perturbs unrelated VA state and is not an atomic constrained allocation |
| Retain the `VirtualQuery` hole scan as primary policy | Rejected for Windows 10 baseline: `VirtualAlloc2` expresses the constraint directly and avoids scan/reserve races |
| Turn on dlmalloc internal locks | Rejected: ART already owns the required heap/JIT locks; closure requires enforcing that contract |
| Force all anonymous and metadata maps low | Rejected: it hides pointer-encoding bugs and fragments scarce low VA |
| Replace dlmalloc with a Windows-only allocator | Rejected: high divergence and a second allocator behavior to validate |
| Reserve-only heap with lazy commit | Deferred pending native commit-pressure measurements and failure-propagation design |

## 9. Implementation stages

### Stage A — make allocator configuration explicit

1. Change dlmalloc's Win32 defaults to respect embedding-provided `HAVE_*` and
   failure-action definitions.
2. Select page-size granularity for Win32 MoreCore-without-mmap.
3. Define the full ART mspace configuration, including `USE_LOCKS=0`, without
   masking Windows macros.
4. Add compile-time and source-configuration checks.

### Stage B — attach mspaces to their owners

1. Add the provider interface and ART creation wrapper.
2. Store provider plus magic in `extp`/`exts`.
3. Convert heap and both JIT mspaces to the wrapper.
4. Delete `Runtime::Current()` heap/JIT discovery and continuous-space scans
   from the callback.
5. Add debug lock and lifetime assertions.

### Stage C — correct Windows anonymous mapping policy

1. Translate common `MemMap` requests into explicit anywhere, low, or exact
   policies.
2. Replace the manual anonymous low scan with `VirtualAlloc2` address
   requirements.
3. Implement aligned mappings without partial release.
4. Track mapping ownership kind and ensure whole-owner destruction.
5. Verify `low_4gb=false` requests are not intentionally placed low.

### Stage D — make page-state transitions explicit

1. Add activate, deactivate, and discard range operations.
2. Route malloc-space growth, shrink, clear, and trim through those operations.
3. Retain full-capacity commit initially and measure native commit pressure.

### Stage E — reduce low-address use

1. Inventory every `low_4gb=true` call site and every Win64-only forced-low
   branch.
2. Classify the exact encoding/reference constraint.
3. Remove low placement from metadata and native storage when unneeded.
4. Add targeted range/encoding checks where a real constraint remains.

Stages A through D are the W-013 correctness fix. Stage E is required before
W-013 closes because the current implicit policy can otherwise hide regressions
and exhaust the address range under stress.

## 10. Verification and closure bar

### 10.1 Configuration and unit tests

- Preprocessor/build check proves `HAVE_MMAP=0`, `HAVE_MORECORE=1`,
  `MORECORE_CONTIGUOUS=1`, `USE_LOCKS=0`, and Windows macros remain defined.
- Source check permits raw mspace creation only inside the ART wrapper.
- `create_mspace_with_base` create/grow/free/trim/regrow/destroy coverage uses a
  mock owner and validates `MoreCore(0)`, positive, negative, limit, and failure
  cases.
- Provider magic, wrong-owner, use-after-detach, and missing-lock checks fail
  deterministically in debug builds.

### 10.2 Windows mapping tests

- Anywhere, below-4-GiB, exact, exact-plus-low, and aligned requests.
- Overflow, zero size, exact collision, exact boundary, and a mapping ending
  exactly at 4 GiB.
- Fragmented low address space and complete low-address exhaustion.
- Proof that a low failure does not retry at a high address.
- Proof that `low_4gb=false` mappings are not deliberately allocated low.
- Repeated activate/deactivate/discard cycles with byte-content checks.
- `VirtualQuery` validation of base, extent, state, and protection after every
  transition.
- Repeated destruction with no leak, partial `MEM_RELEASE`, wrong release API,
  or double release.

### 10.3 Runtime stress

- Dedicated non-moving dlmalloc allocation pressure beyond the initial page.
- Allocation/free/trim/regrow cycles across multiple MoreCore segments.
- Large-object and moving-space pressure.
- Large `-Xmx` startup and sustained allocation tests that record Windows
  commit charge and failure behavior.
- GCStress, ThreadHeavy, and HandleLeak.
- JIT smoke and matrix in the default dual-view mode, plus the temporary J-1
  diagnostic path while it exists.
- Repeated cold process starts on native Windows 10 to vary ASLR and low-space
  fragmentation.

### 10.4 Cross-platform regression

- Linux build after the dlmalloc configuration change.
- Linux heap unit tests and imageless Hello.
- Linux GC stress and JIT smoke sufficient to prove the common mspace wrapper
  did not change allocator semantics.

Wine is a useful development gate but cannot close W-013. Closure requires the
full focused matrix on native Windows 10 or later. Existing `GcProbe` results
alone are insufficient because they do not force sustained non-moving mspace
growth.

## 11. Closure definition

W-013 can move to CLOSED only when all of the following are true:

1. Windows macros remain visible while ART's explicit MoreCore-only dlmalloc
   configuration is compile-verified.
2. No raw mspace creator bypasses the ART provider wrapper.
3. MoreCore performs direct owner dispatch without runtime/global scanning.
4. Windows address policy is explicit and `VirtualAlloc2`-constrained.
5. Windows aligned and logical-shrink paths do not perform invalid partial
   `MEM_RELEASE` operations.
6. Low VA is limited to audited consumers with documented encoding reasons.
7. The Windows, Wine, and Linux closure tests pass with recorded evidence.
8. The tracker and historical Phase-2 notes point to the landed implementation
   rather than the macro-masking workaround.

Until then, the current behavior remains a documented workaround, not a
permanent allocator policy.

## 12. Code anchors

| Topic | Path / symbol |
|-------|---------------|
| ART dlmalloc configuration | `vendor/art/runtime/gc/allocator/art-dlmalloc.{h,cc}` |
| dlmalloc Win32 defaults and extension fields | `vendor/external/dlmalloc/dlmalloc.c` (`WIN32` configuration, `malloc_state::extp/exts`) |
| mspace initialization | `create_mspace_with_base`, `init_user_mstate` |
| heap mspace creation and callback | `vendor/art/runtime/gc/space/dlmalloc_space.cc` |
| common heap growth | `vendor/art/runtime/gc/space/malloc_space.cc` (`MallocSpace::MoreCore`) |
| JIT mspaces and growth | `vendor/art/runtime/jit/jit_memory_region.cc` |
| common `MemMap` policy | `vendor/art/libartbase/base/mem_map.{h,cc}` |
| Windows VM backend | `vendor/art/libartbase/base/mem_map_windows.cc` |
| Win64 forced-low arenas | `vendor/art/runtime/runtime.cc` |

## 13. External API references

- [VirtualAlloc2](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2)
- [MEM_ADDRESS_REQUIREMENTS](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-mem_address_requirements)
- [VirtualFree](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfree)
- [VirtualProtect](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect)
- [DiscardVirtualMemory](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-discardvirtualmemory)
