#!/usr/bin/env bash
set -euo pipefail

# Verify the Win64 compiled-JNI/FastNative convention split.
# Set EXPECT_FIXED=0 to reproduce the historical pre-split failure contract.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
EXPECT_FIXED="${EXPECT_FIXED:-1}"
CLOSED_LOG="${TMPDIR:-/tmp}/win64-fastnative-gate-closed.log"
OPEN_LOG="${TMPDIR:-/tmp}/win64-fastnative-gate-open.log"

bash "$REPO/tools/verify/win64_phase4/build_one.sh" FastNativeAbiProbe

run_probe() {
  local log="$1"
  shift
  cd "$BUILD"
  env \
    ANDROID_ROOT=run \
    ANDROID_ART_ROOT=run \
    ANDROID_I18N_ROOT=run \
    ANDROID_DATA=run/data \
    ICU_DATA=run/icu \
    WINEDEBUG="${WINEDEBUG:--all}" \
    ART_WIN64_JIT_FILTER=System.arraycopy \
    "$@" \
    timeout -k 1 8 "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -Xno-sig-chain \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      -cp "$RUN/fastnativeabiprobe.jar" FastNativeAbiProbe \
      >"$log" 2>&1
}

set +e
run_probe "$CLOSED_LOG"
closed_rc=$?
run_probe "$OPEN_LOG" ART_WIN64_JIT_NATIVE=1
open_rc=$?
set -e

closed_ok=false
if [[ $closed_rc -eq 0 ]] &&
   grep -qF "FastNativeAbiProbe OK" "$CLOSED_LOG" &&
   grep -qF "main end exception=0" "$CLOSED_LOG" &&
   ! grep -qF "method=void java.lang.System.arraycopy" "$CLOSED_LOG"; then
  closed_ok=true
fi

open_ok=false
if [[ $open_rc -eq 0 ]] &&
   grep -qF "method=void java.lang.System.arraycopy" "$OPEN_LOG" &&
   grep -qF "FastNativeAbiProbe OK" "$OPEN_LOG" &&
   grep -qF "main end exception=0" "$OPEN_LOG"; then
  open_ok=true
fi

historical_failure=false
if [[ $open_rc -ne 0 ]] &&
   grep -qF "method=void java.lang.System.arraycopy" "$OPEN_LOG" &&
   ! grep -qF "FastNativeAbiProbe OK" "$OPEN_LOG"; then
  historical_failure=true
fi

printf 'gate_closed_exit=%s gate_closed_ok=%s\n' "$closed_rc" "$closed_ok"
printf 'gate_open_exit=%s gate_open_ok=%s historical_failure=%s\n' \
  "$open_rc" "$open_ok" "$historical_failure"
printf 'expected_mode=%s\n' "$([[ $EXPECT_FIXED == 1 ]] && echo fixed || echo historical-failure)"
printf 'gate_closed_log=%s\n' "$CLOSED_LOG"
printf 'gate_open_log=%s\n' "$OPEN_LOG"

if [[ $closed_ok != true ]]; then
  exit 1
fi
if [[ $EXPECT_FIXED == 1 && $open_ok != true ]]; then
  exit 1
fi
if [[ $EXPECT_FIXED != 1 && $historical_failure != true ]]; then
  exit 1
fi
