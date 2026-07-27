#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-60}"

cmake --build "$BUILD" --target win32_jit_unwind_registry_probe -j"${JOBS:-32}"
log="${TMPDIR:-/tmp}/win32-jit-unwind-registry-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_jit_unwind_registry_probe.exe
) >"$log" 2>&1

grep -qF "win32_jit_unwind_registry_probe failures=0" "$log"
grep -qF "win32_jit_unwind_registry_probe OK" "$log"
cat "$log"
