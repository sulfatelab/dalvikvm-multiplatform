# Win64 heap memory and embedded dlmalloc design — W-013

**Status:** CLOSED — Stages A–E and native Windows R2 acceptance PASS
**Updated:** 2026-07-25
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

The Phase-2 `_WIN32`/`WIN32` masking in `art-dlmalloc.cc` was a valid recovery
workaround. Stage A removed it on 2026-07-25: Windows macros now remain visible,
dlmalloc respects the embedding policy, ART's configuration is compile-checked,
and Windows MoreCore growth uses page-size granularity. Stage B then attached
every heap and JIT mspace directly to its owner and removed global owner
discovery. Stage C replaced the implicit anonymous low-address policy and
manual hole scan with explicit `VirtualAlloc2` constraints, and added shared
whole-allocation ownership for Windows `MemMap` ranges. Stage D then routed
heap activation, deactivation, and discard through those owning mappings on
both Windows and Linux. Stage E restored Linux-like placement for metadata
arenas, LinearAlloc, and the card table, and removed the Win64-only card-mark
skip. Native Windows R2 completed the closure matrix on 2026-07-25.

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
Stage A now states and compile-checks this configuration directly instead of
obtaining it as a side effect of hiding the Windows preprocessor macros.

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

Stages A through E removed the configuration, owner-discovery, anonymous
mapping-policy, heap page-state, blanket low-metadata, and skipped-card
shortcuts. The remaining implementation divergence is:

| Area | Current behavior | Target behavior |
|------|------------------|-----------------|
| dlmalloc platform detection | Windows macros remain visible and Win32 defaults respect embedding-provided `HAVE_*` values | Complete in Stage A |
| mspace VM source | ART explicitly selects MoreCore-only, mspace-only operation on every OS | Complete in Stage A |
| granularity | Win32 contiguous MoreCore uses `dwPageSize`; standalone mmap defaults retain allocation granularity | Complete in Stage A |
| failure action | ART explicitly sets `errno = ENOMEM` and compile-checks the configuration | Complete in Stage A |
| MoreCore owner | Each mspace stores its provider in `malloc_state::extp/exts`; the callback dispatches directly without runtime or heap scans | Complete in Stage B |
| anonymous address policy | Anywhere, below-4-GiB, and exact-address requests are explicit; null/low hints no longer create an implicit low request | Complete in Stage C |
| low allocation | `VirtualAlloc2` applies `MEM_ADDRESS_REQUIREMENTS`; there is no manual hole scan or unrestricted high fallback | Complete in Stage C |
| aligned anonymous maps | Windows passes the final alignment directly to `VirtualAlloc2`; there is no over-allocation/partial-release path | Complete in Stage C |
| mapping ownership | Logical splits, reservation transfers, and reuse views share an owner keyed by `AllocationBase`; private mappings use whole `VirtualFree(MEM_RELEASE)` and section views use `UnmapViewOfFile` | Complete in Stage C |
| logical shrink | `SetSize()` and `AlignBy()` retain the whole Windows allocation, discard/deactivate excluded pages, and shrink only the logical range | Complete in Stage D |
| heap page state | dlmalloc and RosAlloc growth, shrink, clear, and page release call `MemMap::ActivateRange()`, `DeactivateRange()`, and `DiscardRange()` | Complete in Stage D |
| fixed file overlay | `MapViewOfFileEx` cannot replace an ordinary `VirtualAlloc` reservation in place | Remains unsupported; use an explicit placeholder design before enabling image/OAT paths that require this operation |
| low metadata | Runtime/compiler/JIT arenas, ordinary LinearAlloc, and the card table use anywhere mappings as on Linux | Complete in Stage E |
| invalid card address | `CardTable::MarkCard()` follows the common checked path; Windows no longer logs once and silently skips the write barrier | Complete in Stage E |

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

ART now owns a wrapper around `create_mspace_with_base()`. Its contract is:

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

The implemented behavior is:

1. call `create_mspace_with_base(base, initial_footprint, false)`;
2. store `provider` in `malloc_state::extp`;
3. store an ART validation magic in `malloc_state::exts`;
4. permit a null provider only during `DlMallocSpace` construction, where the
   constructor attaches itself before the space is published; and
5. clear or invalidate the attachment before the provider can be destroyed or
   before an owning object is moved.

`extp` and `exts` are explicitly unused extension fields in this dlmalloc
version. Using them avoids a global registry, runtime singleton lookup, heap
continuous-space scan, or special JIT ownership branch.

The MoreCore callback validates the magic and provider, then dispatches
directly to that provider. `DlMallocSpace` and `JitMemoryRegion` implement the
same small interface while retaining their existing growth logic. Heap spaces
attach in the constructor and detach on clear/destruction. JIT regions detach
and rebind both providers during move construction/assignment, and detach on
reset/destruction, so no mspace retains a pointer to the temporary region used
by `JitCodeCache::Create()`.

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

For an aligned anonymous request, Stage C passes a direct `VirtualAlloc2`
alignment requirement and allocates only the final size. Where a common ART
operation logically shrinks a mapping, Stage C retains the original Windows
owner for destruction and updates the logical `MemMap` range without an
invalid partial release. Stage D now discards those excluded pages and changes
them to `PAGE_NOACCESS` before updating the logical range. They remain part of
the committed owner allocation, so later activation does not introduce a new
commit-failure point. The complete allocation is released exactly once when
the final sharing `MemMap` is destroyed.

Mapped section views remain owned by `UnmapViewOfFile`, not `VirtualFree`.
Ownership kind must be known rather than guessed by trying both release APIs.

## 6. Heap growth and page-state operations

The common `MallocSpace::MoreCore()` sequence remains the reference behavior:

```text
positive increment: activate [old_end, new_end), then return old_end
zero increment:     return current end
negative increment: discard and deactivate [new_end, old_end), return old_end
```

Stage D adds explicit `MemMap` range operations with platform backends:

| Semantic operation | Linux backend | Windows backend |
|--------------------|---------------|-----------------|
| Activate range | `mprotect(..., PROT_READ | PROT_WRITE)` | `VirtualProtect(..., PAGE_READWRITE)` |
| Deactivate range | `mprotect(..., PROT_NONE)` | `VirtualProtect(..., PAGE_NOACCESS)` |
| Discard contents | `madvise(..., MADV_DONTNEED)` | `DiscardVirtualMemory(...)` |
| Destroy owner | `munmap` | whole `VirtualFree(..., MEM_RELEASE)` or `UnmapViewOfFile` by ownership kind |

The callers retain common growth and trimming decisions; only the backend
operation differs. Range methods validate page alignment, containment in the
owning mapping, and zero-length behavior. `MallocSpace::MoreCore()` now uses
them for positive and negative growth. dlmalloc trimming and clear, RosAlloc
page release/trim/clear, zygote-space tail setup, and Windows logical shrink
also route through the owning `MemMap`; the allocator files no longer call
`mprotect()` or `madvise()` directly for those transitions.

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

### 7.2 Audited metadata consumers

The Stage E audit produced these outcomes:

| Consumer | Placement | Reason |
|----------|-----------|--------|
| ordinary `arena_pool_` and `jit_arena_pool_` | anywhere | verifier/compiler/JIT native metadata has no compressed-reference representation |
| ordinary LinearAlloc | anywhere | 64-bit runtime `ArtMethod`, field, IMT, and dex-cache metadata uses pointer-size-aware storage; only the existing AOT cross-compilation case retains the upstream low pool |
| card table | anywhere | x86-64 card marking loads the full biased pointer from `Thread` and adds a 64-bit shifted object address; the table does not need to share the heap's address range |
| space bitmaps, read-barrier tables, allocation-info maps, reference tables, stacks, and temporary buffers | anywhere | these call sites were already unrestricted; Stage E found no Win64 blanket-low branch to remove |

The removed Phase-2 policy forced `arena_pool_`, `jit_arena_pool_`,
`linear_alloc_arena_pool_`, and the card table below 4 GiB. Stage E also
removed a Windows-only `MarkCard()` range check that logged once and returned
without marking. That was a bring-up workaround, not a safe recovery policy:
silently losing a dirty-card write can hide heap corruption.

The regression audit pins all remaining literal product low requests to eight
source files covering object spaces, heap/image reservations, the JIT primary
view, and the exact sentinel page. A new low consumer must update the audit and
state its encoding or exact-address reason.

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

**Completed:** 2026-07-25

1. Change dlmalloc's Win32 defaults to respect embedding-provided `HAVE_*` and
   failure-action definitions.
2. Select page-size granularity for Win32 MoreCore-without-mmap.
3. Define the full ART mspace configuration, including `USE_LOCKS=0`, without
   masking Windows macros.
4. Add compile-time and source-configuration checks.

Landed as external dlmalloc `f3356ce` and ART `8c900a9e4b`. Verification:

- focused Win64 allocator probe: page 4096, granularity 4096, eight break
  queries, four positive growth calls, two negative trims, one injected owner
  failure, regrowth, recovery, and `ENOMEM` behavior;
- Win64 `art.dll` and `dalvikvm.exe` rebuild;
- Win64 JIT smoke 12/12 under Wine;
- full Linux `art`/`dalvikvm` rebuild; and
- Linux imageless Hello PASS.

Evidence: `tools/verify/win64_w013/RESULT.md`.

### Stage B — attach mspaces to their owners

**Completed:** 2026-07-25

1. Add the provider interface and ART creation wrapper.
2. Store provider plus magic in `extp`/`exts`.
3. Convert heap and both JIT mspaces to the wrapper.
4. Delete `Runtime::Current()` heap/JIT discovery and continuous-space scans
   from the callback.
5. Add debug lock and lifetime assertions.

The source gate now rejects raw `create_mspace*()` calls outside
`art-dlmalloc.cc` and rejects restoration of the global owner-discovery path.
Landed as ART `d011d72d56`.
Verification covered the Win64 ART/dalvikvm build, JIT smoke 12/12, GCStress,
ThreadHeavy, HandleLeak, the Linux ART/dalvikvm build, and Linux imageless
Hello. Evidence: `tools/verify/win64_w013/RESULT.md`.

### Stage C — correct Windows anonymous mapping policy

**Completed:** 2026-07-25

1. Translate common `MemMap` requests into explicit anywhere, low, or exact
   policies.
2. Replace the manual anonymous low scan with `VirtualAlloc2` address
   requirements.
3. Implement aligned mappings without partial release.
4. Track mapping ownership kind and ensure whole-owner destruction.
5. Verify `low_4gb=false` requests are not intentionally placed low.

Landed as ART `2fa301a13b`. The Windows backend now uses `VirtualAlloc2` and
`MEM_ADDRESS_REQUIREMENTS`, permits a half-open low mapping to end exactly at
4 GiB, aligns anonymous mappings directly, reuses existing reservations with
`VirtualProtect`, and shares one release owner across logical views. The
focused Wine probe covers anywhere/low/exact placement, exact collision, zero
and overflowing requests, the 4-GiB boundary, 2-MiB alignment, 3,854-way
low-VA fragmentation, complete low-VA exhaustion without a high fallback,
recovery, reservation transfer, reuse-view lifetime, logical shrink,
exactly-once whole release, and 128 repeated owner-destruction cycles. Win64
JIT smoke 12/12, GCStress, ThreadHeavy, HandleLeak, the Linux `-j16` build, and
Linux imageless Hello also pass. Evidence:
`tools/verify/win64_w013/RESULT.md`.

Stage C intentionally does not emulate fixed file-view replacement over an
ordinary `VirtualAlloc` reservation. Windows cannot perform that operation
with `MapViewOfFileEx`; a future image/OAT path that requires it must use
placeholder reservations and an explicit rollback design. The current
imageless runtime and JIT pagefile-section path do not depend on that overlay.

### Stage D — make page-state transitions explicit

**Completed:** 2026-07-25

1. Add activate, deactivate, and discard range operations.
2. Route malloc-space growth, shrink, clear, and trim through those operations.
3. Retain full-capacity commit initially; keep native commit-pressure
   measurement in the closure matrix.

Landed as ART `9ea15456a2`. Linux maps use `mprotect()` and
`madvise(MADV_DONTNEED)` behind `MemMap`; Windows maps use `VirtualProtect()`
and `DiscardVirtualMemory()`. RosAlloc receives its owning `MemMap` so initial
discard, free-page release, trim, clear, and negative MoreCore no longer bypass
the platform abstraction. Full-capacity `MEM_RESERVE | MEM_COMMIT` remains the
policy; native Windows commit-charge measurement remains part of the closure
matrix rather than introducing lazy commitment in this stage.

The focused Wine probe performs 32 discard/deactivate/activate cycles,
including discard while `PAGE_NOACCESS`, verifies adjacent-page contents and
protections, and checks that logical shrink leaves its excluded tail
`PAGE_NOACCESS`. Win64 JIT smoke 12/12, GCStress, ThreadHeavy, HandleLeak, the
Linux `-j16` build, Linux imageless Hello, and Linux GCStress pass. Evidence:
`tools/verify/win64_w013/RESULT.md`.

### Stage E — reduce low-address use

**Completed:** 2026-07-25

1. Inventory every `low_4gb=true` call site and every Win64-only forced-low
   branch.
2. Classify the exact encoding/reference constraint.
3. Remove low placement from metadata and native storage when unneeded.
4. Add targeted range/encoding checks where a real constraint remains.

Landed as ART `47567cebcc`. Runtime/compiler/JIT arenas, ordinary LinearAlloc,
and the card table now follow the Linux anywhere policy. Java object spaces,
LOS, image/heap ranges, and the complete JIT primary view remain low; the
sentinel page remains an exact low-address request. The common unconditional
card-marking path is restored. Dedicated non-moving pressure then found the
same Phase-2 pattern around the allocation-time class write barrier;
ART `1509b1f95e` removes its range-check/log/skip branch and restores the common
unconditional barrier there as well.

`tools/verify/win64_w013/run_low_4gb_policy_probe.sh` rejects the old forced-low
branches, rejects both Windows-specific write-barrier shortcuts, and pins the
remaining required-low source inventory. The product non-moving probe churns
75,497,472 bytes of sub-LOS arrays on both Win64/Wine and Linux with stable low
addresses and post-GC regrowth. Win64 `-j16` build, JIT smoke 12/12, GCStress,
ThreadHeavy, HandleLeak, Linux `-j16` build, imageless Hello, and Linux
GCStress pass. Evidence: `tools/verify/win64_w013/RESULT.md`.

Stages A through E implement the W-013 design. Native Windows R2 passes
pressure, commit-charge, protection/extent, and repeated-start acceptance.

## 10. Verification and closure bar

### 10.1 Configuration and unit tests

- PASS: preprocessor/build check proves `HAVE_MMAP=0`, `HAVE_MORECORE=1`,
  `MORECORE_CONTIGUOUS=1`, `USE_LOCKS=0`, and Windows macros remain defined.
- PASS: source check permits raw mspace creation only inside the ART wrapper
  and requires provider magic plus attach/detach state.
- PASS under Wine: `create_mspace_with_base` create/grow/free/trim/regrow/
  failure/destroy coverage uses a mock MoreCore owner and validates
  `MoreCore(0)`, positive, negative, footprint-limit, recovery, and `ENOMEM`
  cases.
- PASS under Wine: the actual ART wrapper succeeds across provider rebind and
  deterministically terminates for wrong-owner detach, use-after-detach,
  missing provider, and double attachment.
- PASS source gate: heap and JIT providers retain their debug external-lock
  assertions. An executable missing-lock death case is not practical without a
  fully attached ART thread and is covered by product stress under the valid
  lock contract plus the source invariant.

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

- PASS under Wine and Linux: dedicated product non-moving allocation pressure
  beyond the initial footprint, using 8-KiB sub-LOS arrays, repeated GC, stable
  address checks, live-set release, and regrowth.
- PASS in the standalone embedded-dlmalloc probe: allocation/free/trim/regrow
  and injected MoreCore failure across repeated segments.
- PASS native R2: large-object and moving-space pressure.
- PASS native R2: large `-Xmx` startup and sustained allocation tests record Windows
  commit charge and failure behavior.
- PASS native R2: GCStress, ThreadHeavy, and HandleLeak.
- PASS native R2: JIT smoke and matrix in the default dual-view mode, plus the temporary J-1
  diagnostic path while it exists.
- PASS native R2: repeated cold process starts on native Windows 10 vary ASLR and low-space
  fragmentation.

The focused native package used for closure is generated by
`tools/win64/host_package/package_win64_w013.sh`. Its PowerShell runner records
the native mapping/config/owner probes, including fragmented and exhausted low
VA; non-moving pressure at 128-MiB and 1-GiB `-Xmx`; moving/LOS GC stress;
ThreadHeavy and HandleLeak; 512-MiB and 1-GiB heap startup memory metrics;
default dual-view and J-1 JIT smoke plus the fourteen-case JIT matrix; twenty
repeated default-JIT starts; host memory/pagefile data; fatal-log scanning; and
a recursive dump scan. See
`tools/verify/win64_w013/W013_HOST_CHECKLIST.md`.

### 10.4 Cross-platform regression

- Linux build after the dlmalloc configuration change.
- Linux heap unit tests and imageless Hello.
- Linux GC stress and JIT smoke sufficient to prove the common mspace wrapper
  did not change allocator semantics.

Wine remains a useful development gate but did not close W-013 by itself. The
full focused R2 matrix passed on native Windows 10 build 19044, including
sustained non-moving mspace growth, large heaps, JIT modes, repeated starts,
metrics, log scanning, and dump scanning.

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

All eight conditions are satisfied by the recorded Wine/Linux gates and native
Windows R2 evidence. No macro-masking, blanket forced-low metadata, or
skipped-card workaround remains in the product path. Acceptance details are in
`tools/verify/win64_w013/evidence/native_r2/ACCEPTANCE.md`.

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
| low-address consumer policy | `vendor/art/runtime/runtime.cc`; `vendor/art/runtime/gc/accounting/card_table.{h,cc}` |

## 13. External API references

- [VirtualAlloc2](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualalloc2)
- [MEM_ADDRESS_REQUIREMENTS](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-mem_address_requirements)
- [VirtualFree](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfree)
- [VirtualProtect](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualprotect)
- [DiscardVirtualMemory](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-discardvirtualmemory)
