# Win64 MemMap low-4G allocator: VirtualQuery free-region search

**Date:** 2026-07-16  
**File:** `vendor/art/libartbase/base/mem_map_windows.cc` (gitignored vendor tree)

## Problem

Large-object allocations (`MemMap::MapAnonymous(..., low_4gb=true)`) failed under wine with:

```text
VirtualAlloc(..., low4g=1) failed
Large object allocation failed: Failed anonymous mmap(...): Invalid argument
```

The previous low-4G path scanned preferred bases in **16MB steps**. Under wine address-space fragmentation, that often only hit reserved regions and never found a free hole large enough for small LOS maps (~16–64KiB).

## Fix

For anonymous non-fixed maps that need the low 4GiB:

1. Walk the low 4GiB with `VirtualQuery`.
2. On `MEM_FREE` regions, align to allocation granularity and try `VirtualAlloc` at the first hole that fits.
3. Fallback: `VirtualAlloc(NULL, ...)` then reject if the result is not entirely below 4GiB.

## Rebuild (targeted)

```bash
# compile only mem_map_windows.cc.obj (see agent notes / manual clang++ flags)
# then:
llvm-lib /OUT:build/win64_phase1/artbase.lib <artbase objs including updated mem_map_windows>
bash /tmp/link_art2.sh   # or equivalent art.dll link
```

## Evidence

After relink, LOS multi-KB allocation smoke:

```text
los.ok=true live=64 ...
```

Explicit `System.gc()` still can stall under wine CMS (separate issue; do not block LOS fix).
