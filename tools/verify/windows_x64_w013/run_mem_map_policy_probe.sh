#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
SOURCE="$REPO/vendor/art/libartbase/base/mem_map_windows.cc"
MEM_MAP_HEADER="$REPO/vendor/art/libartbase/base/mem_map.h"
BUILD="$REPO/build/windows_x64_phase1"
PROBE="$BUILD/windows_x64_w013_mem_map_probe.exe"

if rg -n 'Walk free regions|Fallback: let the OS pick|want_low_4gb.*start == nullptr' "$SOURCE"; then
  echo "W013_MEM_MAP_POLICY_FAIL: implicit/manual low-address allocation remains" >&2
  exit 1
fi

for required in VirtualAlloc2 MEM_ADDRESS_REQUIREMENTS AcquireWindowsMapOwner DiscardVirtualMemory; do
  if ! rg -q "$required" "$SOURCE"; then
    echo "W013_MEM_MAP_POLICY_FAIL: missing $required" >&2
    exit 1
  fi
done

for required in ActivateRange DeactivateRange DiscardRange; do
  if ! rg -q "$required" "$MEM_MAP_HEADER"; then
    echo "W013_MEM_MAP_POLICY_FAIL: missing MemMap::$required" >&2
    exit 1
  fi
done

if rg -n '\b(mprotect|madvise)\s*\(' \
    "$REPO/vendor/art/runtime/gc/space/malloc_space.cc" \
    "$REPO/vendor/art/runtime/gc/space/dlmalloc_space.cc" \
    "$REPO/vendor/art/runtime/gc/space/rosalloc_space.cc" \
    "$REPO/vendor/art/runtime/gc/allocator/rosalloc.cc"; then
  echo "W013_MEM_MAP_POLICY_FAIL: malloc-space page transitions bypass MemMap" >&2
  exit 1
fi

cmake --build "$BUILD" --target windows_x64_w013_mem_map_probe -j16
WINEDEBUG="${WINEDEBUG:--all}" wine "$PROBE"
