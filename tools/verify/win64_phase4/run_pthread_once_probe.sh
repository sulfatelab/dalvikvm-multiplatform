#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
WINE="${WINE:-wine64}"
REPEATS="${REPEATS:-10}"
TIMEOUT="${TIMEOUT:-15}"

cmake --build "$BUILD" --target win64_pthread_once_probe -j"$(nproc)"

for iteration in $(seq 1 "$REPEATS"); do
  log="${TMPDIR:-/tmp}/win64-pthread-once-${iteration}.log"
  if (
    cd "$BUILD"
    WINEDEBUG="${WINEDEBUG:--all}" timeout "$TIMEOUT" \
      "$WINE" ./win64_pthread_once_probe.exe
  ) >"$log" 2>&1 &&
     grep -qF "pthread_once_probe init_calls=1 failures=0 value=0x12345678" "$log" &&
     grep -qF "pthread_once_probe OK" "$log"; then
    printf 'pthread_once run=%s PASS\n' "$iteration"
  else
    printf 'pthread_once run=%s FAIL log=%s\n' "$iteration" "$log" >&2
    tail -50 "$log" >&2
    exit 1
  fi
done

printf 'pthread_once acceptance: %s/%s\n' "$REPEATS" "$REPEATS"
