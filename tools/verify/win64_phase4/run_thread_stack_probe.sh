#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-180}"

cmake --build "$BUILD" --target win32_thread_stack_probe -j"${JOBS:-32}"

log="${TMPDIR:-/tmp}/win32-thread-stack-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_thread_stack_probe.exe
) >"$log" 2>&1

grep -qF "win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128" "$log"
grep -qF "win32_thread_stack_probe OK" "$log"
cat "$log"
