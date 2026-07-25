#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
SOURCE="$REPO/vendor/art/libartbase/base/mem_map_windows.cc"
BUILD="$REPO/build/win64_phase1"
PROBE="$BUILD/win64_w013_mem_map_probe.exe"

if rg -n 'Walk free regions|Fallback: let the OS pick|want_low_4gb.*start == nullptr' "$SOURCE"; then
  echo "W013_MEM_MAP_POLICY_FAIL: implicit/manual low-address allocation remains" >&2
  exit 1
fi

for required in VirtualAlloc2 MEM_ADDRESS_REQUIREMENTS AcquireWindowsMapOwner; do
  if ! rg -q "$required" "$SOURCE"; then
    echo "W013_MEM_MAP_POLICY_FAIL: missing $required" >&2
    exit 1
  fi
done

cmake --build "$BUILD" --target win64_w013_mem_map_probe -j16
WINEDEBUG="${WINEDEBUG:--all}" wine "$PROBE"
