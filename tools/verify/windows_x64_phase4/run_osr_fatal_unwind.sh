#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-120}"

if [[ ! -f "$BUILD/art.dll" || ! -f "$RUN/art.dll" ]] ||
   ! cmp -s "$BUILD/art.dll" "$RUN/art.dll"; then
  printf 'built and staged art.dll must exist and match before OSR fatal-unwind testing\n' >&2
  exit 1
fi

bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" CrashNativeProbe
python3 "$REPO/tools/verify/windows_x64_phase1/check_win32_boundary_unwind.py" \
  --art-dll "$BUILD/art.dll"
mkdir -p "$RUN/crash"

run_one() (
  local mode="$1"
  local log="${TMPDIR:-/tmp}/win32-osr-fatal-unwind-${mode}.log"
  local rc
  local temp_dir
  local before_file
  local new_file

  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' EXIT
  before_file="$temp_dir/before.json"
  new_file="$temp_dir/new-files.txt"
  python3 - "$RUN/crash" "$before_file" <<'PY'
import glob
import json
import os
import sys

root, output = sys.argv[1:]
snapshot = {}
for path in glob.glob(os.path.join(root, "*.dmp")):
    stat = os.stat(path)
    snapshot[path] = [stat.st_size, stat.st_mtime_ns]
with open(output, "w", encoding="utf-8") as stream:
    json.dump(snapshot, stream, sort_keys=True)
PY

  if (
    cd "$BUILD"
    unset ART_WINDOWS_X64_CRASH_NATIVE_WARMUP
    export ART_WINDOWS_X64_NTERP=0
    export ART_WINDOWS_X64_JIT_FILTER=CrashNativeProbe.osrCrashLoop
    export ART_WINDOWS_X64_JIT_LOG_COMPILES=1
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -verbose:jit -Xjitwarmupthreshold:100 -Xjitthreshold:100 \
      -Xms64m -Xmx512m \
      -cp "$RUN/crashnativeprobe.jar" CrashNativeProbe osr
  ) >"$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  python3 - "$RUN/crash" "$before_file" >"$new_file" <<'PY'
import glob
import json
import os
import sys

root, before_path = sys.argv[1:]
with open(before_path, encoding="utf-8") as stream:
    before = json.load(stream)
for path in sorted(glob.glob(os.path.join(root, "*.dmp"))):
    stat = os.stat(path)
    if before.get(path) != [stat.st_size, stat.st_mtime_ns]:
        print(path)
PY

  if [[ $rc -eq 0 || $rc -eq 124 ]] ||
     ! grep -qF 'CrashNativeProbe.osr_armed count=2000000' "$log" ||
     ! grep -qF 'warmup_threshold=100, optimize_threshold=100' "$log" ||
     ! grep -qF 'kind=Baseline' "$log" ||
     ! grep -qF 'kind=Osr' "$log" ||
     ! grep -qE 'Windows x64 CompileMethod done success=1 method=long CrashNativeProbe\.osrCrashLoop\(int\)' "$log" ||
     ! grep -qF 'Jumping to long CrashNativeProbe.osrCrashLoop(int)' "$log" ||
     ! grep -qF 'ART Win32 VEH: exception 0xc0000005' "$log" ||
     ! grep -qF 'ART Win32 UEF: exception 0xc0000005' "$log" ||
     ! grep -qF 'ART Win32 crash: minidump written to ' "$log" ||
     grep -qF 'Done running OSR code for long CrashNativeProbe.osrCrashLoop(int)' "$log" ||
     grep -qF 'CrashNativeProbe.osr_unexpected_return' "$log" ||
     grep -qF 'CrashNativeProbe.unexpected_continue' "$log"; then
    printf 'Windows x64 OSR-origin fatal unwind %s FAIL exit=%s log=%s\n' \
      "$mode" "$rc" "$log" >&2
    tail -200 "$log" >&2
    return 1
  fi

  grep -qF 'Windows x64 JIT dual-view (J-2) created' "$log"

  local valid_dump=0
  while IFS= read -r dump; do
    if [[ -n "$dump" ]] && python3 - "$dump" <<'PY'
import os
import sys

path = sys.argv[1]
with open(path, "rb") as stream:
    valid = stream.read(4) == b"MDMP"
raise SystemExit(0 if valid and os.path.getsize(path) > 32 else 1)
PY
    then
      valid_dump=1
      break
    fi
  done <"$new_file"
  if [[ $valid_dump -ne 1 ]]; then
    printf 'Windows x64 OSR-origin fatal unwind %s created no valid new MDMP dump\n' \
      "$mode" >&2
    tail -200 "$log" >&2
    return 1
  fi

  printf 'Windows x64 OSR-origin fatal unwind %s PASS\n' "$mode"
)

run_one default
printf 'Windows x64 OSR-origin fatal unwind acceptance: default J-2 PASS\n'
