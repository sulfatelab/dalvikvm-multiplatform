#!/usr/bin/env bash
# Build, verify, and package focused W-003 acceptance for native Windows 10+.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PRODUCT_BUILD="${PRODUCT_BUILD:-$REPO/build/win64_phase1}"
FRAME_BUILD="${FRAME_BUILD:-$REPO/build/win64_w003_frames}"
FRAME_NATIVE_BUILD="${FRAME_NATIVE_BUILD:-$REPO/build/win64_w003_frame_probe}"
XMM_NATIVE_BUILD="${XMM_NATIVE_BUILD:-$REPO/build/win64_w003_xmm_sentinel}"
OUT="${1:-$REPO/dist/win64_w003_host}"
JOBS="${JOBS:-32}"
WINEDEBUG="${WINEDEBUG:--all}"

cmake --build "$PRODUCT_BUILD" --target art dalvikvm -j"$JOBS"

structural_output="$(
  python3 "$REPO/tools/verify/win64_phase1/check_w003_quick_boundaries.py" \
    --win-build "$PRODUCT_BUILD" --linux-build "$REPO/build/native"
)"
printf '%s\n' "$structural_output"

PRODUCT_BUILD="$PRODUCT_BUILD" \
BUILD="$FRAME_BUILD" \
NATIVE_BUILD="$FRAME_NATIVE_BUILD" \
REPEATS=2 \
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_w003_frame_probe.sh"

BUILD="$PRODUCT_BUILD" \
NATIVE_BUILD="$XMM_NATIVE_BUILD" \
REPEATS=2 \
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_w003_xmm_sentinel.sh"

required_build_files=(
  "$PRODUCT_BUILD/dalvikvm.exe"
  "$PRODUCT_BUILD/art.dll"
  "$PRODUCT_BUILD/run/boot.jar"
  "$FRAME_BUILD/art.dll"
  "$FRAME_BUILD/run/w003frameprobe.jar"
  "$FRAME_NATIVE_BUILD/libw003frameprobe.dll"
  "$PRODUCT_BUILD/run/w003xmmsentinelprobe.jar"
  "$XMM_NATIVE_BUILD/libw003xmmsentinel.dll"
)
for path in "${required_build_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing W-003 package artifact: $path" >&2
    exit 1
  fi
done

"$REPO/tools/win64/host_package/package_win64_phase3.sh" "$OUT"

cp -a "$OUT/art.dll" "$OUT/art.product.dll"
cp -a "$FRAME_BUILD/art.dll" "$OUT/art.frame-probe.dll"
cp -a "$FRAME_NATIVE_BUILD/libw003frameprobe.dll" "$OUT/"
cp -a "$XMM_NATIVE_BUILD/libw003xmmsentinel.dll" "$OUT/"
cp -a "$FRAME_BUILD/run/w003frameprobe.jar" "$OUT/run/"
cp -a "$PRODUCT_BUILD/run/w003xmmsentinelprobe.jar" "$OUT/run/"
mkdir -p "$OUT/run/data" "$OUT/logs"
printf '%s\n' 'Runtime-writable ART data directory; package generation leaves it clean.' \
  >"$OUT/run/data/README.txt"

cp -a "$REPO/tools/verify/win64_phase4/host/RUN_W003_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/win64_phase4/W003_HOST_CHECKLIST.md" "$OUT/"

product_exports="$(llvm-readobj --coff-exports "$PRODUCT_BUILD/art.dll")"
frame_exports="$(llvm-readobj --coff-exports "$FRAME_BUILD/art.dll")"
product_probe_exports="$(grep -cF 'Name: art_w003_frame_probe_' <<<"$product_exports" || true)"
frame_probe_exports="$(grep -cF 'Name: art_w003_frame_probe_' <<<"$frame_exports" || true)"

frame_obj="$(find "$FRAME_BUILD/CMakeFiles/art.dir" \
  -name 'quick_entrypoints_x86_64.S.obj' -print -quit)"
frame_symbols="$(llvm-readobj --symbols "$frame_obj")"
frame_counter_symbols=0
for symbol in \
    art_w003_frame_probe_refs_only \
    art_w003_frame_probe_refs_and_args \
    art_w003_frame_probe_all_callee_saves \
    art_w003_frame_probe_everything; do
  if grep -qF "Name: $symbol" <<<"$frame_symbols"; then
    frame_counter_symbols=$((frame_counter_symbols + 1))
  fi
done

frame_jni_exports="$(llvm-readobj --coff-exports \
  "$FRAME_NATIVE_BUILD/libw003frameprobe.dll" | \
  grep -cF 'Name: Java_W003FrameProbe_' || true)"
xmm_jni_exports="$(llvm-readobj --coff-exports \
  "$XMM_NATIVE_BUILD/libw003xmmsentinel.dll" | \
  grep -cF 'Name: Java_W003XmmSentinelProbe_runXmmSentinel' || true)"
xmm_obj="$(find "$XMM_NATIVE_BUILD/CMakeFiles/w003xmmsentinel.dir" \
  -name 'w003_xmm_sentinel_x86_64.S.obj' -print -quit)"
xmm_unwind_saves="$(llvm-readobj --unwind "$xmm_obj" | grep -c 'SAVE_XMM128' || true)"

if [[ "$product_probe_exports" -ne 0 ||
      "$frame_probe_exports" -ne 2 ||
      "$frame_counter_symbols" -ne 4 ||
      "$frame_jni_exports" -ne 3 ||
      "$xmm_jni_exports" -ne 1 ||
      "$xmm_unwind_saves" -ne 6 ]]; then
  echo "invalid W-003 structural report values" >&2
  exit 1
fi

cat >"$OUT/W003_STRUCTURAL_REPORT.txt" <<EOF
status=PASS
checker_output=$structural_output
product_probe_exports=$product_probe_exports
frame_probe_exports=$frame_probe_exports
frame_counter_symbols=$frame_counter_symbols
frame_jni_exports=$frame_jni_exports
xmm_jni_exports=$xmm_jni_exports
xmm_unwind_saves=$xmm_unwind_saves
product_art_sha256=$(sha256sum "$OUT/art.product.dll" | awk '{print $1}')
frame_art_sha256=$(sha256sum "$OUT/art.frame-probe.dll" | awk '{print $1}')
frame_probe_dll_sha256=$(sha256sum "$OUT/libw003frameprobe.dll" | awk '{print $1}')
xmm_probe_dll_sha256=$(sha256sum "$OUT/libw003xmmsentinel.dll" | awk '{print $1}')
host_llvm_tools_required=no
EOF

cat >"$OUT/BUILD_INFO.txt" <<EOF
created=$(date '+%Y-%m-%d %H:%M:%S %z')
host=$(hostname)
root_branch=$(git -C "$REPO" branch --show-current)
root_commit=$(git -C "$REPO" rev-parse HEAD)
art_branch=$(git -C "$REPO/vendor/art" branch --show-current)
art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)
product_build=$PRODUCT_BUILD
frame_build=$FRAME_BUILD
windows_minimum_build=17134
native_frame_repeats=2
native_xmm_repeats=2
EOF

clean_runtime_outputs() {
  find "$OUT/logs" -mindepth 1 -type f -delete
  find "$OUT/run/data" -mindepth 1 ! -name README.txt -delete
  find "$OUT" -type f \( -iname '*.dmp' -o -iname '*.trace' \) -delete
  cp -a "$OUT/art.product.dll" "$OUT/art.dll"
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

python3 "$REPO/tools/verify/win64_phase1/check_win32_cet_contract.py" \
  --build "$PRODUCT_BUILD" \
  --pe-root "$OUT"

clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/win64_phase4/check_w003_host_package.py" "$OUT"
python3 "$REPO/tools/verify/win64_phase4/smoke_w003_host_package_wine.py" "$OUT"
clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/win64_phase4/check_w003_host_package.py" "$OUT"

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
echo "W003_HOST_PACKAGE_PASS path=$OUT.zip bytes=$(stat -c %s "$OUT.zip")"
