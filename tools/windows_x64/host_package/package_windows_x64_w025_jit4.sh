#!/usr/bin/env bash
# Build, verify, and package the W-025 JIT-4 final native regression.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
OUT="${1:-$REPO/dist/windows_x64_w025_jit4_host}"
JOBS="${JOBS:-16}"
WINEDEBUG="${WINEDEBUG:--all}"
TEMP_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" w025-jit4-package.XXXXXX)"
trap 'rm -rf "$TEMP_ROOT"' EXIT
BASE="$TEMP_ROOT/w004-base"

cmake --build "$BUILD" --target art openjdkjvmti -j"$JOBS"
bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" W002OsrProbe
bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" CrashNativeProbe
bash "$REPO/tools/verify/windows_x64_w025/build_w025_jit3_probe.sh"

python3 -B "$REPO/tools/verify/windows_x64_w025/check_w025_jit4_source.py" \
  --repo "$REPO" --build "$BUILD"

# The existing W-004 package provides the native/JVMTI artifacts and repeats
# its focused Wine gate before JIT-4 adds the remaining final-regression cases.
BUILD="$BUILD" JOBS="$JOBS" WINEDEBUG="$WINEDEBUG" \
  bash "$REPO/tools/windows_x64/host_package/package_windows_x64_w004.sh" "$BASE"

WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_jit_smoke.sh"
WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_jit_matrix.sh"
REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/windows_x64_phase4/run_w002_osr_probe.sh"
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/windows_x64_w025/run_w025_jit3_preflight.sh"
cp -a "$BUILD/art.dll" "$BUILD/run/art.dll"
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/windows_x64_phase4/run_jit_fatal_unwind.sh"
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/windows_x64_phase4/run_osr_fatal_unwind.sh"

rm -rf "$OUT"
cp -a "$BASE" "$OUT"

matrix_jars=(
  CEnc.jar CEnc2.jar CELike.jar CFloat.jar FloatProbe.jar IFloat.jar
  JLFloat.jar RFloat.jar SFloat.jar MathProbe.jar ioprobe.jar netprobe.jar
  gcprobe.jar throwprobe.jar
)
for jar in "${matrix_jars[@]}"; do
  cp -a "$BUILD/run/$jar" "$OUT/run/"
done
for jar in w002osrprobe.jar crashnativeprobe.jar w025jitlifecyclestressprobe.jar; do
  cp -a "$BUILD/run/$jar" "$OUT/run/"
done
cp -a "$BUILD/libw025jitlifecyclestressprobe.dll" "$OUT/"
cp -a "$REPO/tools/verify/windows_x64_w025/host/RUN_W025_JIT4_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/windows_x64_w025/W025_JIT4_HOST_CHECKLIST.md" "$OUT/"

mkdir -p "$OUT/logs" "$OUT/jit-temp" "$OUT/run/data" "$OUT/run/crash"
printf '%s\n' 'Runtime-writable ART data directory; package generation leaves it clean.' \
  >"$OUT/run/data/README.txt"
printf '%s\n' 'JIT-4 fatal cases preserve exactly three valid minidumps here.' \
  >"$OUT/run/crash/README.txt"

python3 -B "$REPO/tools/verify/windows_x64_w025/check_w025_jit4_source.py" \
  --repo "$REPO" --build "$BUILD" >"$OUT/W025_JIT4_SOURCE_REPORT.txt"

cat >"$OUT/BUILD_INFO.txt" <<EOF
created=$(date '+%Y-%m-%d %H:%M:%S %z')
host=$(hostname)
root_branch=$(git -C "$REPO" branch --show-current)
root_commit=$(git -C "$REPO" rev-parse HEAD)
art_branch=$(git -C "$REPO/vendor/art" branch --show-current)
art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)
windows_x64_build=$BUILD
windows_minimum_build=17134
jit4_cases=28
jit4_aggregate_pass=34
jit4_default_memory_mode=j2
jit4_j1_cases=0
jit4_smoke_records=12
jit4_matrix_records=14
jit4_lifecycle_cycles=8
jit4_fatal_minidumps=3
EOF

clean_runtime_outputs() {
  find "$OUT/logs" -mindepth 1 -delete
  find "$OUT/jit-temp" -mindepth 1 -delete
  find "$OUT/run/data" -mindepth 1 ! -name README.txt -delete
  find "$OUT/run/crash" -mindepth 1 ! -name README.txt -delete
  find "$OUT" -type f \( -name '*.trace' -o -name '*.dmp' \) -delete
}

write_manifests() {
  OUT_DIR="$OUT" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OUT_DIR"])
files = []
for path in sorted(root.rglob("*")):
    relative = path.relative_to(root)
    if (
        path.is_file()
        and "logs" not in relative.parts
        and "jit-temp" not in relative.parts
        and path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}
        and path.suffix.lower() not in {".dmp", ".trace"}
    ):
        data = path.read_bytes()
        files.append({
            "path": relative.as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
(root / "MANIFEST.json").write_text(
    json.dumps({"files": files, "count": len(files)}, indent=2) + "\n",
    encoding="utf-8",
)
PY
  (
    cd "$OUT"
    find . -type f \
      ! -path './logs/*' \
      ! -path './jit-temp/*' \
      ! -name SHA256SUMS.txt \
      ! -name '*.dmp' \
      ! -name '*.trace' \
      -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS.txt
  )
}

clean_runtime_outputs
write_manifests
python3 -B "$REPO/tools/verify/windows_x64_phase1/check_win32_cet_contract.py" \
  --build "$BUILD" --pe-root "$OUT"
python3 -B "$REPO/tools/verify/windows_x64_w025/check_w025_jit4_host_package.py" "$OUT"

OUT_DIR="$OUT" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["OUT_DIR"])
archive = root.parent / (root.name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and "logs" not in relative.parts
            and "jit-temp" not in relative.parts
            and path.suffix.lower() not in {".dmp", ".trace"}
        ):
            output.write(path, path.relative_to(root.parent))
print(f"package={root}")
print(f"archive={archive}")
PY

sha256sum "$OUT.zip" >"$OUT.zip.sha256"
echo "W025_JIT4_HOST_PACKAGE_PASS path=$OUT.zip bytes=$(stat -c %s "$OUT.zip")"
