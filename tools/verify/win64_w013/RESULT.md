# W-013 Win64 heap-memory implementation

**Status:** Stages A–D PASS; Stage E and native closure stress remain OPEN
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
W013_DLMALLOC_CONFIG_PASS page=4096 granularity=4096 increment=20480
```

The probe also checks that Windows macros remain active, a maximal allocation
fails with `ENOMEM`, and `art-dlmalloc.cc` contains no `_WIN32`/`WIN32` undef.

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

## Integration verification

```text
cmake --build build/win64_phase1 --target art dalvikvm -j16
tools/verify/win64_w013/run_mem_map_policy_probe.sh
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
- Win64 W-013 address-policy/ownership probe: PASS, including the tested
  4-GiB boundary and exactly-once owner release;
- Win64 JIT smoke under Wine: 12/12 PASS;
- Win64 GCStress, ThreadHeavy, and HandleLeak under Wine: PASS;
- Linux `libart.so` and `dalvikvm`: full rebuild PASS;
- Linux L-005 imageless Hello: PASS, exit 0;
- Linux GCStress: PASS, including repeated explicit CMS collections.

Stages A through D do not close W-013. Low-VA reduction, fixed file-overlay
design if image/OAT loading needs it, native Windows commit/stress acceptance,
and the complete closure matrix remain.
