#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
REPEATS="${REPEATS:-2}"
TIMEOUT="${TIMEOUT:-120}"

bash "$REPO/tools/verify/win64_phase4/build_one.sh" W002OsrProbe
python3 "$REPO/tools/verify/win64_phase1/check_w002_managed_entries.py" --build "$BUILD"

run_one() {
  local memory_mode="$1"
  local dual="$2"
  local interpreter_mode="$3"
  local iteration="$4"
  local log="${TMPDIR:-/tmp}/w002-osr-${memory_mode}-${interpreter_mode}-${iteration}.log"
  local rc

  if (
    cd "$BUILD"
    if [[ "$interpreter_mode" == "switch" ]]; then
      export ART_WIN64_NTERP=0
    else
      unset ART_WIN64_NTERP
    fi
    export ART_WIN64_JIT_DUAL="$dual"
    export ART_WIN64_JIT_FILTER="W002OsrProbe.osrLoop"
    export ART_WIN64_JIT_LOG_COMPILES=1
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -Xno-sig-chain \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      -verbose:jit -Xjitwarmupthreshold:100 -Xjitthreshold:100 \
      -cp "$RUN/w002osrprobe.jar" W002OsrProbe
  ) > "$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  if [[ $rc -ne 0 ]] ||
     ! grep -qF "warmup_threshold=100, optimize_threshold=100" "$log" ||
     ! grep -qF "W002OsrProbe OK checksum=65553463744" "$log" ||
     ! grep -qF "kind=Baseline" "$log" ||
     ! grep -qF "kind=Osr" "$log" ||
     ! grep -qF "Jumping to long W002OsrProbe.osrLoop(int)" "$log" ||
     ! grep -qF "main end exception=0" "$log"; then
    printf 'W-002 OSR %s/%s run=%s FAIL exit=%s log=%s\n' \
      "$memory_mode" "$interpreter_mode" "$iteration" "$rc" "$log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  if [[ "$interpreter_mode" == "switch" ]]; then
    if ! grep -qF "Done running OSR code for long W002OsrProbe.osrLoop(int)" "$log"; then
      printf 'W-002 switch OSR completion marker missing: %s\n' "$log" >&2
      tail -120 "$log" >&2
      return 1
    fi
  elif grep -qF "Done running OSR code for long W002OsrProbe.osrLoop(int)" "$log"; then
    printf 'W-002 nterp run unexpectedly used the switch OSR return path: %s\n' "$log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  printf 'W-002 OSR %s/%s run=%s PASS\n' \
    "$memory_mode" "$interpreter_mode" "$iteration"
}

for memory_and_dual in "dual:1" "j1:0"; do
  memory_mode="${memory_and_dual%%:*}"
  dual="${memory_and_dual##*:}"
  for interpreter_mode in default switch; do
    for iteration in $(seq 1 "$REPEATS"); do
      run_one "$memory_mode" "$dual" "$interpreter_mode" "$iteration"
    done
  done
done

printf 'W-002 OSR acceptance: dual and J-1, default nterp and switch, %s repeat(s): PASS\n' \
  "$REPEATS"
