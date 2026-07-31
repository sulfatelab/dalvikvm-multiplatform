#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
REPEATS="${REPEATS:-2}"
TIMEOUT="${TIMEOUT:-120}"

bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" W002OsrProbe
python3 "$REPO/tests/support/windows/check_w002_managed_entries.py" --build "$BUILD"

run_one() {
  local interpreter_mode="$1"
  local iteration="$2"
  local log="${TMPDIR:-/tmp}/w002-osr-default-${interpreter_mode}-${iteration}.log"
  local rc

  if (
    cd "$BUILD"
    if [[ "$interpreter_mode" == "switch" ]]; then
      export ART_WINDOWS_X64_NTERP=0
    else
      unset ART_WINDOWS_X64_NTERP
    fi
    export ART_WINDOWS_X64_JIT_FILTER="W002OsrProbe.osrLoop"
    export ART_WINDOWS_X64_JIT_LOG_COMPILES=1
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
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
    printf 'W-002 OSR default/%s run=%s FAIL exit=%s log=%s\n' \
      "$interpreter_mode" "$iteration" "$rc" "$log" >&2
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

  printf 'W-002 OSR default/%s run=%s PASS\n' \
    "$interpreter_mode" "$iteration"
}

for interpreter_mode in default switch; do
  for iteration in $(seq 1 "$REPEATS"); do
    run_one "$interpreter_mode" "$iteration"
  done
done

printf 'W-002 OSR acceptance: default JIT memory, default nterp and switch, %s repeat(s): PASS\n' \
  "$REPEATS"
