# Windows x64 MemMap low-4G allocator: VirtualQuery free-region search

**Date:** 2026-07-16  
**Status:** superseded; do not reapply
**Historical file:** `vendor/art/libartbase/base/mem_map_windows.cc`

Nested ART commit `2fa301a13b` replaced this scan with Windows 10
`VirtualAlloc2` address requirements and explicit mapping policy. That current
implementation is authoritative for all Windows architectures. The scan below
is useful only to explain the original failure or to study a hypothetical
pre-Windows-10 fallback, which is outside this project's supported baseline.

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

## Evidence

After relink, LOS multi-KB allocation smoke:

```text
los.ok=true live=64 ...
```

Explicit `System.gc()` still can stall under wine CMS (separate issue; do not block LOS fix).
