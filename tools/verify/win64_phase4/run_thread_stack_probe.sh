#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-180}"

cmake --build "$BUILD" --target win32_thread_stack_probe win32_stack_page_probe -j"${JOBS:-32}"

stack_log="${TMPDIR:-/tmp}/win32-thread-stack-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_thread_stack_probe.exe
) >"$stack_log" 2>&1

grep -qF "win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128" "$stack_log"
grep -qF "requested=65536" "$stack_log"
grep -qF "requested=262144" "$stack_log"
grep -qF "requested=1048576" "$stack_log"
grep -qF "requested=2097152" "$stack_log"
grep -qF "requested=9437184" "$stack_log"
grep -qF "win32_thread_stack_probe OK" "$stack_log"
cat "$stack_log"

page_log="${TMPDIR:-/tmp}/win32-stack-page-probe.log"
(
  cd "$BUILD"
  WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
    "$WINE" ./win32_stack_page_probe.exe
) >"$page_log" 2>&1

grep -qF "selection_cases count=8" "$page_log"
grep -qF "reserved_case size=1048576 iterations=64" "$page_log"
grep -qF "win32_stack_page_probe failures=0 committed_restore_iterations=64 reserved_restore_iterations=64 faults=258" "$page_log"
grep -qF "win32_stack_page_probe OK" "$page_log"
cat "$page_log"
