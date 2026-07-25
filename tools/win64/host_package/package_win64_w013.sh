#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
OUT="${1:-$REPO/dist/win64_w013_host}"
JOBS="${JOBS:-16}"

"$REPO/tools/verify/win64_w013/run_dlmalloc_config_probe.sh"
cmake --build "$BUILD" --target win64_w013_mem_map_probe win64_w013_mspace_owner_probe -j"$JOBS"
"$REPO/tools/verify/win64_w013/run_non_moving_stress.sh"

"$REPO/tools/win64/host_package/package_win64_phase3.sh" "$OUT"

cp -a "$BUILD/win64_w013_mem_map_probe.exe" "$OUT/"
cp -a "$BUILD/win64_w013_mspace_owner_probe.exe" "$OUT/"
cp -a "$BUILD/probes/W013DlmallocConfigProbe.exe" "$OUT/"
cp -a "$BUILD/run/w013nonmovingstressprobe.jar" "$OUT/run/"
for jar in CEnc.jar CEnc2.jar CELike.jar CFloat.jar FloatProbe.jar IFloat.jar \
           JLFloat.jar RFloat.jar SFloat.jar MathProbe.jar; do
  cp -a "$BUILD/run/$jar" "$OUT/run/"
done
cp -a "$REPO/tools/verify/win64_w013/host/RUN_W013_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/win64_w013/W013_HOST_CHECKLIST.md" "$OUT/"
rm -rf "$OUT/logs"
mkdir -p "$OUT/logs"

cat >"$OUT/BUILD_INFO.txt" <<EOF
created=$(date '+%Y-%m-%d %H:%M:%S %z')
host=$(hostname)
root_commit=$(git -C "$REPO" rev-parse HEAD)
art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)
dlmalloc_commit=$(git -C "$REPO/vendor/external/dlmalloc" rev-parse HEAD)
win64_build=$BUILD
EOF

OUT_DIR="$OUT" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OUT_DIR"])
files = []
for path in sorted(root.rglob("*")):
    if (path.is_file() and
            "logs" not in path.parts and
            path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}):
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
(root / "MANIFEST.json").write_text(json.dumps({"files": files, "count": len(files)}, indent=2))
PY

(
  cd "$OUT"
  find . -type f ! -path './logs/*' ! -name SHA256SUMS.txt -print0 |
    sort -z |
    xargs -0 sha256sum >SHA256SUMS.txt
)

OUT_DIR="$OUT" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["OUT_DIR"])
archive = root.parent / (root.name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in sorted(root.rglob("*")):
        if path.is_file() and "logs" not in path.parts:
            output.write(path, path.relative_to(root.parent))
print(f"W013_HOST_PACKAGE_PASS path={archive} bytes={archive.stat().st_size}")
PY
