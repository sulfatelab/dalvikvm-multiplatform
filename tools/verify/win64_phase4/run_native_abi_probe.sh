#!/usr/bin/env bash
set -euo pipefail

# Reproduce the current Win64 compiled-JNI/FastNative gate behavior.
# The gate-closed control must pass. Until W-024 is fixed, opening the native
# JIT gate for System.arraycopy must compile the JNI stub and fail the probe.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
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

open_reproduced=false
if [[ $open_rc -ne 0 ]] &&
   grep -qF "method=void java.lang.System.arraycopy" "$OPEN_LOG" &&
   ! grep -qF "FastNativeAbiProbe OK" "$OPEN_LOG"; then
  open_reproduced=true
fi

printf 'gate_closed_exit=%s gate_closed_ok=%s\n' "$closed_rc" "$closed_ok"
printf 'gate_open_exit=%s gate_open_failure_reproduced=%s\n' "$open_rc" "$open_reproduced"
printf 'gate_closed_log=%s\n' "$CLOSED_LOG"
printf 'gate_open_log=%s\n' "$OPEN_LOG"

if [[ $closed_ok != true || $open_reproduced != true ]]; then
  exit 1
fi
