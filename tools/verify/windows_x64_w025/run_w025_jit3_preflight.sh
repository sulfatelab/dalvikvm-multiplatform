#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
WINE="${WINE:-wine64}"
WINEDEBUG="${WINEDEBUG:--all}"
CYCLES="${CYCLES:-4}"
TIMEOUT="${TIMEOUT:-240}"

"$REPO/tools/verify/windows_x64_w025/build_w025_jit3_probe.sh"

run_mode() {
  local mode="$1"
  local dual="$2"
  local output
  output="$(mktemp "${TMPDIR:-/tmp}/w025-jit3-${mode}.XXXXXX.log")"
  if ! (
    cd "$BUILD"
    env \
      ANDROID_ROOT=run \
      ANDROID_ART_ROOT=run \
      ANDROID_I18N_ROOT=run \
      ANDROID_DATA=run/data \
      ICU_DATA=run/icu \
      WINEDEBUG="$WINEDEBUG" \
      ART_WINDOWS_X64_JIT_DUAL="$dual" \
      ART_WINDOWS_X64_JIT_FILTER=W025JitLifecycleStressProbe \
      timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
        -Xbootclasspath:run/boot.jar \
        -Xbootclasspath-locations:run/boot.jar \
        -Ximage:/nonexistent-no-boot-image \
        -XjdwpProvider:none \
        -Xjitwarmupthreshold:65535 \
        -Xjitthreshold:65535 \
        -Xjitinitialsize:4M \
        -Xjitmaxsize:16M \
        -XX:DumpJITInfoOnShutdown \
        -Xms64m \
        -Xmx512m \
        '-Djava.library.path=.;run' \
        -cp run/w025jitlifecyclestressprobe.jar \
        W025JitLifecycleStressProbe "$CYCLES"
  ) >"$output" 2>&1; then
    tail -240 "$output" >&2
    return 1
  fi

  grep -Fq "W025_JIT3_PASS methods=24 managed=16 jni=8" "$output"
  grep -Fq "cycles=$CYCLES collections=$CYCLES" "$output"
  grep -Fq 'missing_live=0 stale_dead=0 unwind_failures=0' "$output"
  grep -Fq 'callback_tables=0' "$output"
  grep -Fq "W025JitLifecycleStressProbe PASS cycles=$CYCLES" "$output"
  if [[ "$dual" == 1 ]]; then
    grep -Fq 'Windows x64 JIT dual-view (J-2) created' "$output"
  elif grep -Fq 'Windows x64 JIT dual-view (J-2) created' "$output"; then
    printf 'W025 JIT-3 %s unexpectedly used J-2\n' "$mode" >&2
    return 1
  fi
  if grep -Eq 'W025_JIT3_FAIL|Unhandled page fault|Access violation|Check failed|Fatal signal' \
      "$output"; then
    tail -240 "$output" >&2
    return 1
  fi
  printf 'PASS %s cycles=%s\n' "$mode" "$CYCLES"
}

run_mode j2 1
run_mode j1 0
printf 'W025_JIT3_WINE_PREFLIGHT_PASS cycles=%s modes=J-2,J-1\n' "$CYCLES"
