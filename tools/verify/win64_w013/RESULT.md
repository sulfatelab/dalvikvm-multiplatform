# W-013 Win64 heap-memory implementation

**Status:** Stages A–E PASS; native closure stress remains OPEN
**Date:** 2026-07-25
**Host:** agent01

## Stage A — explicit embedded-dlmalloc configuration

Landed changes:

- external dlmalloc `f3356ce` makes Win32 defaults respect embedding-provided
  `HAVE_MMAP`, `HAVE_MORECORE`, and related platform definitions;
- Win32 contiguous MoreCore now uses `dwPageSize` rather than
  `dwAllocationGranularity`;
- ART `8c900a9e4b` removes `_WIN32`/`WIN32` masking and explicitly selects and
  compile-checks `HAVE_MMAP=0`, `HAVE_MREMAP=0`, `HAVE_MORECORE=1`,
  `MORECORE_CONTIGUOUS=1`, `USE_LOCKS=0`, and mspace-only operation; and
- ART explicitly sets allocation failure to `errno = ENOMEM`.

## Focused probe

Command:

```text
tools/verify/win64_w013/run_dlmalloc_config_probe.sh
```

Observed under Wine:

```text
W013_DLMALLOC_CONFIG_PASS page=4096 granularity=4096 positive=4 negative=2 queries=8 failures=1 last_positive=8192 last_negative=-20480
```

The probe now creates an mspace over a mock owner, grows it, frees and trims the
top segment, regrows it, injects an owner-side capacity failure, proves the
mspace remains usable afterward, and destroys it. It validates `MoreCore(0)`,
page-granular positive and negative increments, footprint limits, and `ENOMEM`.
The source gate also checks that Windows macros remain active, that raw mspace
creation cannot bypass ART's wrapper, and that provider magic plus
attach/detach fields remain present in `art-dlmalloc.cc`.

## Stage B — direct mspace-owner attachment

ART commit: `d011d72d56`

Landed behavior:

- all ART mspaces are created through `ArtCreateMspaceWithBase()`;
- `malloc_state::extp/exts` store an `MspaceMoreCoreProvider` and validation
  magic;
- the dlmalloc MoreCore callback validates and dispatches directly to
  `DlMallocSpace` or `JitMemoryRegion`;
- heap construction, clear, and destruction attach/detach the provider;
- JIT move construction/assignment detach the temporary provider and rebind
  both mspaces to the destination, while reset/destruction detach them; and
- the global `Runtime::Current()`/heap/JIT owner scan and
  `JitCodeCache::OwnsSpace()` path are removed.

The focused probe now also rejects raw `create_mspace*()` calls outside
`art-dlmalloc.cc` and rejects restoration of the global owner-discovery path.

The actual `art-dlmalloc.cc` wrapper is also compiled into a focused executable:

```text
tools/verify/win64_w013/run_mspace_owner_probe.sh
```

Its success case grows through one provider, trims, detaches, rebinds a second
provider, and regrows. Four subprocess death cases verify missing provider,
use-after-detach, wrong-owner detach, and double attachment all terminate with
the expected `CHECK` diagnostic. The source gate also requires the heap and JIT
external-lock assertions.

```text
W013_MSPACE_OWNER_PASS first_calls=5 second_calls=2
W013_MSPACE_OWNER_PROBE_PASS success=1 death=4
```

## Stage C — explicit Windows address policy and ownership

ART commit: `2fa301a13b`

Landed behavior:

- anonymous anywhere, below-4-GiB, and exact requests are explicit;
- low and aligned allocations use `VirtualAlloc2` with
  `MEM_ADDRESS_REQUIREMENTS`, with no manual hole scan or unrestricted high
  fallback;
- exact reuse inside an existing reservation uses `VirtualProtect` instead of
  an overlapping reservation;
- a low half-open range may end exactly at 4 GiB;
- private allocations and section views carry a shared owner keyed by
  `AllocationBase` and use `VirtualFree(MEM_RELEASE)` or `UnmapViewOfFile`,
  respectively;
- reservation transfers, logical splits, and `reuse=true` views retain that
  owner until the final view is destroyed; and
- aligned allocation, `SetSize()`, and `AlignBy()` avoid partial
  `MEM_RELEASE`.

Focused probe command:

```text
tools/verify/win64_w013/run_mem_map_policy_probe.sh
```

Observed under Wine:

```text
W013_MEM_MAP_POLICY_PASS anywhere=00007FFFFE7C0000 low=0000000000010000 boundary=tested
```

The probe validates anywhere/low/exact placement, exact collision, a mapping
ending exactly at 4 GiB, 2-MiB direct alignment, reservation transfer,
`reuse=true` shared lifetime, logical shrink without partial release, and
exactly-once final release.

Known Stage-C boundary: `MapViewOfFileEx` cannot replace an ordinary
`VirtualAlloc` reservation in place. Fixed file-backed overlay remains
unsupported rather than being emulated unsafely; the imageless runtime and JIT
pagefile-section path do not require it.

## Stage D — explicit heap page-state operations

ART commit: `9ea15456a2`

Landed behavior:

- `MemMap` exposes page-aligned `ActivateRange()`, `DeactivateRange()`, and
  `DiscardRange()` operations with containment and zero-length validation;
- Linux uses `mprotect()` and `madvise(MADV_DONTNEED)` behind those methods;
- Windows uses `VirtualProtect()` and `DiscardVirtualMemory()` while retaining
  the full committed reservation;
- positive and negative `MallocSpace::MoreCore()` transitions use the owning
  `MemMap`;
- dlmalloc trim/clear and RosAlloc initial discard, page release, trim, clear,
  and page-map release no longer call platform VM APIs directly;
- RosAlloc carries a rebased pointer to its owning `MemMap` across space
  construction; and
- Windows `SetSize()`/`AlignBy()` discard and deactivate excluded pages before
  shrinking the logical range.

The focused probe now performs 32 discard/deactivate/activate cycles. It
checks `PAGE_NOACCESS` and `PAGE_READWRITE` transitions, discard while already
no-access, adjacent-page content preservation, write-after-reactivation, and
logical-shrink tail protection.

Observed under Wine:

```text
W013_MEM_MAP_POLICY_PASS anywhere=00007FFFFE7C0000 low=0000000000010000 boundary=tested transitions=32
```

The source gate rejects direct `mprotect()`/`madvise()` calls in malloc-space,
dlmalloc-space, RosAlloc-space, and RosAlloc allocator transition paths.

## Stage E — audited low-address consumers

ART commit: `47567cebcc`

Landed behavior:

- ordinary runtime and verifier arenas use unrestricted mappings as on Linux;
- compiler/JIT metadata arenas use unrestricted mappings as on Linux;
- ordinary runtime LinearAlloc no longer creates a Win64-only low arena pool;
- the upstream AOT cross-compilation low-LinearAlloc condition remains intact;
- the card table uses an unrestricted mapping because x86-64 card marking
  loads its full biased pointer and uses a 64-bit object-derived index;
- the Windows-only `MarkCard` OOB log-and-skip path is removed, restoring the
  common checked write barrier; and
- Java object spaces, LOS, required image/heap reservations, the complete JIT
  primary view, and the exact sentinel request remain low.

Focused audit command:

```text
tools/verify/win64_w013/run_low_4gb_policy_probe.sh
```

Observed:

```text
W013_LOW_4GB_POLICY_PASS required_files=8 metadata=anywhere card_mark=unconditional nonmoving_barrier=unconditional
```

The audit rejects the retired `win64_low_4gb` branch, the retired card-mark
skip, any Windows-specific card-table behavior, and changes to the exact set of
product files containing literal required-low requests.

The first dedicated product non-moving stress run exposed one additional
Phase-2 branch in `gc/heap-inl.h`: Windows logged every non-moving allocation,
checked card-table range manually, and skipped the class write barrier when the
check failed. ART `1509b1f95e` removes that branch and restores the common
unconditional barrier. The low-address audit now rejects its return.

## Product non-moving pressure

Command:

```text
tools/verify/win64_w013/run_non_moving_stress.sh
```

The Java probe calls `VMRuntime.newNonMovableArray()` through reflection and
allocates only 8-KiB primitive arrays, below the 12-KiB LOS threshold. With
`-Xms2m -Xmx128m`, it churns 75,497,472 bytes, retains up to 1,024 live arrays,
forces GC between twelve rounds, verifies 16 anchor addresses never move,
checks sampled addresses stay below 4 GiB, clears the live set, and allocates
again to exercise post-GC regrowth.

Observed after `1509b1f95e`:

```text
W013_NON_MOVING_STRESS_PASS win64=ok linux=ok total_bytes=75497472
```

Win64 and Linux address spans were about 14.8 MiB, well beyond the 2-MiB
startup setting. Both runtimes reported `nonmoving.stable=true`,
`nonmoving.low=true`, and `nonmoving.ok=true`.

## Integration verification

```text
cmake --build build/win64_phase1 --target art dalvikvm -j16
tools/verify/win64_w013/run_dlmalloc_config_probe.sh
tools/verify/win64_w013/run_mspace_owner_probe.sh
tools/verify/win64_w013/run_mem_map_policy_probe.sh
tools/verify/win64_w013/run_low_4gb_policy_probe.sh
tools/verify/win64_w013/run_non_moving_stress.sh
tools/verify/win64_phase4/run_jit_smoke.sh
tools/verify/win64_phase4/run_gcstress.sh
tools/verify/win64_phase4/run_threadheavy.sh
tools/verify/win64_phase4/run_handleleak.sh
cmake --build build/native --target art dalvikvm -j16
tools/verify/linux_hello/run_imageless_hello.sh
tools/verify/linux_hello/run_gcstress.sh
```

Results:

- Win64 `art.dll` and `dalvikvm.exe`: build PASS;
- actual ART mspace-owner wrapper: success/rebind PASS and 4/4 expected-death
  lifetime checks PASS;
- Win64 W-013 address-policy/ownership probe: PASS, including the tested
  4-GiB boundary and exactly-once owner release;
- Win64 W-013 low-address source audit: PASS, with eight required-low product
  files and unrestricted metadata/card-table policy;
- Win64 and Linux product non-moving pressure: PASS, 75,497,472 bytes churned,
  stable low addresses, post-GC allocation recovery;
- Win64 JIT smoke under Wine: 12/12 PASS;
- Win64 GCStress, ThreadHeavy, and HandleLeak under Wine: PASS;
- Linux `libart.so` and `dalvikvm`: full rebuild PASS;
- Linux L-005 imageless Hello: PASS, exit 0;
- Linux GCStress: PASS, including repeated explicit CMS collections.

Stages A through E implement the accepted W-013 design. Fixed file-overlay over
an ordinary `VirtualAlloc` reservation remains unsupported and is not used by
the imageless/JIT path; any future image/OAT implementation that needs it must
use placeholder APIs and rollback. Native Windows commit/pressure,
protection/extent, repeated-start, and the remaining closure matrix still keep
W-013 open.
