#!/usr/bin/env bash
# Build, preflight, and package W-025 JIT-3 / FS-3 native Windows acceptance.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
OUT="${1:-$REPO/dist/windows_x64_w025_jit3_host}"

CYCLES=4 TIMEOUT=300 "$REPO/tools/verify/windows_x64_w025/run_w025_jit3_preflight.sh"
python3 "$REPO/tools/verify/windows_x64_w025/check_w025_jit3_source.py" \
  --repo "$REPO" --build "$BUILD" >"$BUILD/W025_JIT3_SOURCE_REPORT.txt"

"$REPO/tools/windows_x64/host_package/package_windows_x64_phase3.sh" "$OUT"

cp -a "$BUILD/libw025jitlifecyclestressprobe.dll" "$OUT/"
cp -a "$BUILD/run/w025jitlifecyclestressprobe.jar" "$OUT/run/"
cp -a "$BUILD/W025_JIT3_SOURCE_REPORT.txt" "$OUT/"
cp -a "$REPO/tools/verify/windows_x64_w025/host/RUN_W025_JIT3_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/windows_x64_w025/W025_JIT3_HOST_CHECKLIST.md" "$OUT/"

mkdir -p "$OUT/logs" "$OUT/jit-temp" "$OUT/run/data"
find "$OUT/logs" -mindepth 1 -type f -delete
find "$OUT/jit-temp" -mindepth 1 -delete

cat >"$OUT/README_HOST.md" <<'EOF'
# W-025 JIT-3 / FS-3 native Windows gate

Run from this directory in Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W025_JIT3_HOST.ps1
```

Expected final line: `OVERALL PASS`.

The package is self-identifying through `BUILD_INFO.txt`,
`W025_JIT3_SOURCE_REPORT.txt`, `MANIFEST.json`, and `SHA256SUMS.txt`.
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
jit3_methods=24
jit3_managed_methods=16
jit3_jni_methods=8
jit3_default_stress_cycles=24
jit3_comparison_cycles=12
jit3_repeat_cycles=8
EOF

python3 "$REPO/tools/verify/windows_x64_phase1/check_win32_cet_contract.py" \
  --build "$BUILD" --pe-root "$OUT"

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
    if (path.is_file() and
            "logs" not in relative.parts and
            "jit-temp" not in relative.parts and
            path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}):
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
    find . -type f ! -path './logs/*' ! -path './jit-temp/*' \
      ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS.txt
  )
}

write_manifests
python3 "$REPO/tools/verify/windows_x64_w025/check_w025_jit3_host_package.py" "$OUT"
python3 "$REPO/tools/verify/windows_x64_w025/smoke_w025_jit3_host_package_wine.py" "$OUT"
find "$OUT/logs" -mindepth 1 -type f -delete
find "$OUT/jit-temp" -mindepth 1 -delete
write_manifests
python3 "$REPO/tools/verify/windows_x64_w025/check_w025_jit3_host_package.py" "$OUT"

OUT_DIR="$OUT" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["OUT_DIR"])
archive = root.parent / (root.name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and "logs" not in relative.parts and "jit-temp" not in relative.parts:
            output.write(path, path.relative_to(root.parent))
print(f"package={root}")
print(f"archive={archive}")
PY
sha256sum "$OUT.zip" >"$OUT.zip.sha256"
printf 'W025_JIT3_HOST_PACKAGE_PASS path=%s bytes=%s\n' "$OUT.zip" "$(stat -c %s "$OUT.zip")"
