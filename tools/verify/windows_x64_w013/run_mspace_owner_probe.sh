#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="$REPO/build/windows_x64_phase1"
PROBE="$BUILD/windows_x64_w013_mspace_owner_probe.exe"
DLMALLOC_SPACE="$REPO/vendor/art/runtime/gc/space/dlmalloc_space.cc"
JIT_REGION="$REPO/vendor/art/runtime/jit/jit_memory_region.cc"

if ! rg -q 'lock_\.AssertHeld' "$DLMALLOC_SPACE"; then
  echo 'W013_MSPACE_OWNER_FAIL: heap mspace external-lock assertion is missing' >&2
  exit 1
fi
if ! rg -q 'Locks::jit_lock_->AssertHeld' "$JIT_REGION"; then
  echo 'W013_MSPACE_OWNER_FAIL: JIT mspace external-lock assertion is missing' >&2
  exit 1
fi

cmake --build "$BUILD" --target windows_x64_w013_mspace_owner_probe -j16
WINEDEBUG="${WINEDEBUG:--all}" wine "$PROBE" success

run_death_case() {
  local mode="$1"
  local expected="$2"
  local log
  local status
  log="$(mktemp "/tmp/mdvm_w013_owner_${mode}.XXXXXX.log")"
  set +e
  WINEDEBUG="${WINEDEBUG:--all}" timeout 30 wine "$PROBE" "$mode" >"$log" 2>&1
  status=$?
  set -e
  if [[ "$status" -eq 0 || "$status" -eq 124 ]]; then
    tail -n 100 "$log" >&2
    rm -f "$log"
    echo "W013_MSPACE_OWNER_FAIL: $mode returned status $status" >&2
    exit 1
  fi
  if ! rg -q "$expected" "$log"; then
    tail -n 100 "$log" >&2
    rm -f "$log"
    echo "W013_MSPACE_OWNER_FAIL: $mode missed expected diagnostic: $expected" >&2
    exit 1
  fi
  rm -f "$log"
  echo "W013_MSPACE_OWNER_DEATH_PASS mode=$mode status=$status"
}

run_death_case missing-provider 'Unattached ART mspace'
run_death_case use-after-detach 'Unattached ART mspace'
run_death_case wrong-owner-detach 'state->extp == provider'
run_death_case double-attach 'state->extp == nullptr'

echo 'W013_MSPACE_OWNER_PROBE_PASS success=1 death=4'
