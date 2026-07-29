#!/usr/bin/env bash
# Package the FS-1 stack-overflow high-water probe for native Windows acceptance.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
RELEASE_BUILD="${RELEASE_BUILD:-$REPO/build/windows_x64_fs1_release}"
DEBUG_BUILD="${DEBUG_BUILD:-$REPO/build/windows_x64_fs1_debug}"
OUT="${1:-$REPO/dist/windows_x64_fs1_stack_high_water}"

rm -rf "$OUT"
mkdir -p "$OUT/scripts" "$OUT/logs"

copy_runtime() {
  local build_type="$1"
  local source="$2"
  local dest="$OUT/${build_type,,}"
  local file

  mkdir -p "$dest/run/crash"
  for file in \
      dalvikvm.exe art.dll artpalette.dll base.dll c++.dll log.dll lzma.dll \
      nativebridge.dll nativehelper.dll nativeloader.dll procinfo.dll \
      sigchain.dll ziparchive.dll libfs1stackhighwater.dll; do
    if [[ ! -f "$source/$file" ]]; then
      printf 'missing FS-1 %s runtime file: %s\n' "$build_type" "$source/$file" >&2
      exit 1
    fi
    cp -a "$source/$file" "$dest/"
  done
  bash "$REPO/tools/windows_x64/stage_native_modules.sh" \
    "$dest" "$REPO/build/windows_x64_libcore_icu" "$source"
  bash "$REPO/tools/windows_x64/stage_run_assets.sh" "$dest" "$source"
  cp -a "$source/run/fs1stackhighwaterprobe.jar" "$dest/run/"
  if [[ "$build_type" == "Debug" ]]; then
    # ART's Debug core-native lookup follows the standard *d.dll convention.
    cp -a "$dest/libopenjdk.dll" "$dest/libopenjdkd.dll"
  fi
}

copy_runtime Release "$RELEASE_BUILD"
copy_runtime Debug "$DEBUG_BUILD"

cp -a "$REPO/tools/verify/windows_x64_phase4/host/RUN_FS1_STACK_HIGH_WATER_HOST.ps1" \
  "$OUT/scripts/"
cp -a "$REPO/tools/verify/windows_x64_phase4/check_fs1_stack_high_water.py" \
  "$OUT/scripts/"

cat >"$OUT/BUILD_INFO.txt" <<EOF
created=$(date '+%Y-%m-%d %H:%M:%S %z')
host=$(hostname)
root_branch=$(git -C "$REPO" branch --show-current)
root_commit=$(git -C "$REPO" rev-parse HEAD)
art_branch=$(git -C "$REPO/vendor/art" branch --show-current)
art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)
release_build=$RELEASE_BUILD
debug_build=$DEBUG_BUILD
probe=FS-1-stack-overflow-high-water
target_host=Windows-Server-2025-build-26100
EOF

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
        relative = path.relative_to(root)
        if path.is_file() and "logs" not in relative.parts:
            output.write(path, path.relative_to(root.parent))
print(f"package={root}")
print(f"archive={archive}")
PY

sha256sum "$OUT.zip" >"$OUT.zip.sha256"
printf 'FS1_HOST_PACKAGE_PASS path=%s bytes=%s\n' \
  "$OUT.zip" "$(stat -c %s "$OUT.zip")"
