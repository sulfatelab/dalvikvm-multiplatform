#!/usr/bin/env bash
# Build, verify, and package focused W-004 acceptance for native Windows 10+.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
OUT="${1:-$REPO/dist/win64_w004_host}"
JOBS="${JOBS:-16}"
WINEDEBUG="${WINEDEBUG:--all}"

cmake --build "$BUILD" --target art openjdkjvmti -j"$JOBS"

structural_output="$(
  python3 "$REPO/tools/verify/win64_phase1/check_w004_runtime_load.py" \
    --build "$BUILD"
)"
printf '%s\n' "$structural_output"

REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_critical_native_probe.sh"
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_native_abi_probe.sh"
REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_jvmti_force_probe.sh"

required_build_files=(
  "$BUILD/dalvikvm.exe"
  "$BUILD/art.dll"
  "$BUILD/openjdkjvmti.dll"
  "$BUILD/libcriticalnativeprobe.dll"
  "$BUILD/criticalnativeprobe.dll"
  "$BUILD/libnativeabiprobe.dll"
  "$BUILD/libjvmtiforceprobe.dll"
  "$BUILD/jvmtiforceprobe.dll"
  "$BUILD/run/boot.jar"
  "$BUILD/run/hello.jar"
  "$BUILD/run/FloatProbe.jar"
  "$BUILD/run/criticalnativeprobe.jar"
  "$BUILD/run/fastnativeabiprobe.jar"
  "$BUILD/run/jvmtiforceprobe.jar"
  "$BUILD/run/gcstressprobe.jar"
  "$BUILD/run/threadheavyprobe.jar"
  "$BUILD/run/handleleakprobe.jar"
)
for path in "${required_build_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing W-004 package artifact: $path" >&2
    exit 1
  fi
done

"$REPO/tools/win64/host_package/package_win64_phase3.sh" "$OUT"

cp -a "$BUILD/openjdkjvmti.dll" "$OUT/"
for dll in libcriticalnativeprobe.dll criticalnativeprobe.dll \
    libnativeabiprobe.dll libjvmtiforceprobe.dll jvmtiforceprobe.dll; do
  cp -a "$BUILD/$dll" "$OUT/"
done
for jar in FloatProbe.jar criticalnativeprobe.jar fastnativeabiprobe.jar \
    jvmtiforceprobe.jar; do
  cp -a "$BUILD/run/$jar" "$OUT/run/"
done

mkdir -p "$OUT/empty-native-dir" "$OUT/run/data" "$OUT/logs"
printf '%s\n' 'This directory intentionally contains no native library DLL.' \
  >"$OUT/empty-native-dir/README.txt"
printf '%s\n' 'Runtime-writable ART data directory; package generation leaves it clean.' \
  >"$OUT/run/data/README.txt"

cp -a "$REPO/tools/verify/win64_phase4/host/RUN_W004_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/win64_phase4/W004_HOST_CHECKLIST.md" "$OUT/"

runtime_symbol='?instance_@Runtime@art@@0PEAV12@EA'
direct_total="$(sed -n 's/.*total=\([0-9][0-9]*\)).*/\1/p' <<<"$structural_output")"
direct_quick="$(sed -n 's/.*quick=\([0-9][0-9]*\).*/\1/p' <<<"$structural_output")"
direct_jni="$(sed -n 's/.*jni=\([0-9][0-9]*\).*/\1/p' <<<"$structural_output")"
direct_nterp="$(sed -n 's/.*nterp=\([0-9][0-9]*\).*/\1/p' <<<"$structural_output")"
runtime_exports="$(llvm-readobj --coff-exports "$BUILD/art.dll" | \
  grep -cF "Name: $runtime_symbol")"
plugin_imports="$(llvm-readobj --coff-imports "$BUILD/openjdkjvmti.dll" | \
  grep -cF "Symbol: $runtime_symbol")"
if [[ -z "$direct_total" || "$direct_total" -le 0 ||
      "$runtime_exports" -ne 1 || "$plugin_imports" -ne 1 ]]; then
  echo "invalid W-004 structural report values" >&2
  exit 1
fi

cat >"$OUT/W004_STRUCTURAL_REPORT.txt" <<EOF
status=PASS
checker_output=$structural_output
direct_quick=$direct_quick
direct_jni=$direct_jni
direct_nterp=$direct_nterp
direct_total=$direct_total
retired_helper_references=0
runtime_instance_exports=$runtime_exports
openjdkjvmti_runtime_instance_imports=$plugin_imports
art_sha256=$(sha256sum "$OUT/art.dll" | awk '{print $1}')
openjdkjvmti_sha256=$(sha256sum "$OUT/openjdkjvmti.dll" | awk '{print $1}')
linux_macro=unchanged
host_llvm_tools_required=no
EOF

cat >"$OUT/BUILD_INFO.txt" <<EOF
created=$(date '+%Y-%m-%d %H:%M:%S %z')
host=$(hostname)
root_branch=$(git -C "$REPO" branch --show-current)
root_commit=$(git -C "$REPO" rev-parse HEAD)
art_branch=$(git -C "$REPO/vendor/art" branch --show-current)
art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)
win64_build=$BUILD
windows_minimum_build=17134
EOF

clean_runtime_outputs() {
  find "$OUT/logs" -mindepth 1 -type f -delete
  find "$OUT/run/data" -mindepth 1 ! -name README.txt -delete
  find "$OUT" -maxdepth 1 -type f -name '*.trace' -delete
  if [[ -d "$OUT/run/tmp_handles" ]]; then
    find "$OUT/run/tmp_handles" -mindepth 1 -delete
  fi
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
    if (path.is_file() and
            "logs" not in path.relative_to(root).parts and
            path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}):
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(root).as_posix(),
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
    find . -type f ! -path './logs/*' ! -name SHA256SUMS.txt -print0 |
      sort -z |
      xargs -0 sha256sum >SHA256SUMS.txt
  )
}

python3 "$REPO/tools/verify/win64_phase1/check_win32_cet_contract.py" \
  --build "$BUILD" \
  --pe-root "$OUT"

clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/win64_phase4/check_w004_host_package.py" "$OUT"
python3 "$REPO/tools/verify/win64_phase4/smoke_w004_host_package_wine.py" "$OUT"
clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/win64_phase4/check_w004_host_package.py" "$OUT"

OUT_DIR="$OUT" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["OUT_DIR"])
archive = root.parent / (root.name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in sorted(root.rglob("*")):
        if path.is_file() and "logs" not in path.relative_to(root).parts:
            output.write(path, path.relative_to(root.parent))
print(f"package={root}")
print(f"archive={archive}")
PY

sha256sum "$OUT.zip" >"$OUT.zip.sha256"
echo "W004_HOST_PACKAGE_PASS path=$OUT.zip bytes=$(stat -c %s "$OUT.zip")"
