#!/usr/bin/env bash
# Build, verify, and package focused W-002 acceptance for native Windows 10+.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
OUT="${1:-$REPO/dist/windows_x64_w002_host}"
JOBS="${JOBS:-16}"
WINEDEBUG="${WINEDEBUG:--all}"

cmake --build "$BUILD" --target art -j"$JOBS"

structural_output="$(
  python3 "$REPO/tests/support/windows/check_w002_managed_entries.py" --build "$BUILD"
)"
printf '%s\n' "$structural_output"

REPEATS=2 WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_w002_osr_probe.sh"
REPEATS=2 WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_w002_attach_probe.sh"

required_build_files=(
  "$BUILD/dalvikvm.exe"
  "$BUILD/art.dll"
  "$BUILD/libw002attachprobe.dll"
  "$BUILD/run/boot.jar"
  "$BUILD/run/w002osrprobe.jar"
  "$BUILD/run/w002attachprobe.jar"
)
for path in "${required_build_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing W-002 package artifact: $path" >&2
    exit 1
  fi
done

"$REPO/tools/windows_x64/host_package/package_windows_x64_phase3.sh" "$OUT"

cp -a "$BUILD/libw002attachprobe.dll" "$OUT/"
cp -a "$BUILD/run/w002osrprobe.jar" "$OUT/run/"
cp -a "$BUILD/run/w002attachprobe.jar" "$OUT/run/"
mkdir -p "$OUT/run/data" "$OUT/logs"
printf '%s\n' 'Runtime-writable ART data directory; package generation leaves it clean.' >"$OUT/run/data/README.txt"

cp -a "$REPO/tools/verify/windows_x64_phase4/host/RUN_W002_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/windows_x64_phase4/W002_HOST_CHECKLIST.md" "$OUT/"

attach_exports="$(llvm-readobj --coff-exports "$BUILD/libw002attachprobe.dll")"
for symbol in JNI_OnLoad Java_W002AttachProbe_runAttachMatrix; do
  if [[ "$(grep -cF "Name: $symbol" <<<"$attach_exports")" -ne 1 ]]; then
    echo "invalid W-002 attach export: $symbol" >&2
    exit 1
  fi
done

cat >"$OUT/W002_STRUCTURAL_REPORT.txt" <<EOF
status=PASS
checker_output=$structural_output
attach_exports=2
art_sha256=$(sha256sum "$OUT/art.dll" | awk '{print $1}')
attach_dll_sha256=$(sha256sum "$OUT/libw002attachprobe.dll" | awk '{print $1}')
linux_quick_osr_path=unchanged
host_llvm_tools_required=no
EOF

cat >"$OUT/BUILD_INFO.txt" <<EOF
created=$(date '+%Y-%m-%d %H:%M:%S %z')
host=$(hostname)
root_branch=$(git -C "$REPO" branch --show-current)
root_commit=$(git -C "$REPO" rev-parse HEAD)
art_branch=$(git -C "$REPO/vendor/art" branch --show-current)
art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)
windows_x64_build=$BUILD
windows_minimum_build=17134
native_matrix_repeats=2
EOF

clean_runtime_outputs() {
  find "$OUT/logs" -mindepth 1 -type f -delete
  find "$OUT/run/data" -mindepth 1 ! -name README.txt -delete
  find "$OUT" -maxdepth 1 -type f -name '*.trace' -delete
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
    if (
        path.is_file()
        and "logs" not in path.relative_to(root).parts
        and path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}
    ):
        data = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
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

python3 "$REPO/tests/support/windows/check_win32_cet_contract.py" \
  --build "$BUILD" \
  --pe-root "$OUT"

clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/windows_x64_phase4/check_w002_host_package.py" "$OUT"
python3 "$REPO/tools/verify/windows_x64_phase4/smoke_w002_host_package_wine.py" "$OUT"
clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/windows_x64_phase4/check_w002_host_package.py" "$OUT"

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
echo "W002_HOST_PACKAGE_PASS path=$OUT.zip bytes=$(stat -c %s "$OUT.zip")"
