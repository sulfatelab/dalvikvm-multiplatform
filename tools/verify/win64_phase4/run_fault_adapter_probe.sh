#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-60}"

cmake --build "$BUILD" --target win32_fault_record_probe win32_sigchain_probe -j"${JOBS:-32}"
log="${TMPDIR:-/tmp}/win32-fault-record-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_fault_record_probe.exe
) >"$log" 2>&1

grep -qF "win32_fault_record_probe failures=0 cases=8" "$log"
grep -qF "win32_fault_record_probe OK" "$log"
cat "$log"

sigchain_log="${TMPDIR:-/tmp}/win32-sigchain-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_sigchain_probe.exe
) >"$sigchain_log" 2>&1

grep -qF "win32_sigchain_probe calls=2 first=0 second=0" "$sigchain_log"
grep -qF "win32_sigchain_probe OK" "$sigchain_log"
cat "$sigchain_log"
