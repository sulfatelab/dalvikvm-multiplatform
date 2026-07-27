#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-60}"

cmake --build "$BUILD" --target win32_osr_unwind_probe -j"${JOBS:-32}"
log="${TMPDIR:-/tmp}/win32-osr-unwind-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_osr_unwind_probe.exe
) >"$log" 2>&1

grep -qF "win32_osr_unwind_probe failures=0" "$log"
grep -qF "entry_frame_offset=0 return_prologue=0 fixed_frame=248 xmm_count=10 invoke_records=2 variable_rsp_delta=256" "$log"
grep -qF "win32_osr_unwind_probe OK" "$log"
cat "$log"
