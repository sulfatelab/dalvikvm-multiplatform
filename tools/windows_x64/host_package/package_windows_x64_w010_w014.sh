#!/usr/bin/env bash
# Build, verify, and package focused W-010/W-014 Stage E acceptance for native Windows.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
LINUX_BUILD="${LINUX_BUILD:-$REPO/build/native}"
HYBRID="${MDVM_HYBRID_BUILD:-$REPO/build/windows_x64_libcore_icu}"
OUT="${1:-$REPO/dist/windows_x64_w010_w014_host}"
JOBS="${JOBS:-32}"
WINEDEBUG="${WINEDEBUG:--all}"

cmake --build "$BUILD" --target \
  art \
  win32_cet_policy_probe \
  win32_debugger_probe \
  win32_art_embedding_probe \
  win32_thread_stack_probe \
  win32_stack_page_probe \
  win32_stack_growth_probe \
  win32_uef_probe \
  win32_fault_record_probe \
  win32_sigchain_probe \
  win32_osr_unwind_probe \
  -j"$JOBS"

cmake --build "$HYBRID" --target openjdk -j"$JOBS"
bash "$REPO/tools/verify/windows_x64_libcore_icu/install_into_phase1.sh" "$HYBRID" "$BUILD"

bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" W010ManagedFaultProbe
bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" CrashNativeProbe
cp -a "$BUILD/art.dll" "$BUILD/run/art.dll"
WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_thread_stack_probe.sh"
WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_fault_adapter_probe.sh"
osr_unwind_output="$(
  WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_osr_unwind_probe.sh"
)"
printf '%s\n' "$osr_unwind_output"
osr_unwind_summary="$(
  printf '%s\n' "$osr_unwind_output" | tr -d '\r' | \
    grep '^win32_osr_unwind_probe failures=0 '
)"
WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_w010_managed_fault_probe.sh"
explicit_stack_output="$(
  python3 "$REPO/tests/support/windows/check_win32_explicit_stack_checks.py" \
    --win-build "$BUILD" \
    --linux-build "$LINUX_BUILD"
)"
printf '%s\n' "$explicit_stack_output"
WINEDEBUG="$WINEDEBUG" REPEATS=2 \
  "$REPO/tools/verify/windows_x64_phase4/run_w003_xmm_sentinel.sh"
WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_jit_fatal_unwind.sh"
WINEDEBUG="$WINEDEBUG" "$REPO/tools/verify/windows_x64_phase4/run_osr_fatal_unwind.sh"

cet_output="$(
  python3 "$REPO/tests/support/windows/check_win32_cet_contract.py" \
    --build "$BUILD"
)"
printf '%s\n' "$cet_output"

required_build_files=(
  "$BUILD/dalvikvm.exe"
  "$BUILD/art.dll"
  "$BUILD/win32_cet_policy_probe.exe"
  "$BUILD/win32_debugger_probe.exe"
  "$BUILD/win32_art_embedding_probe.exe"
  "$BUILD/win32_thread_stack_probe.exe"
  "$BUILD/win32_stack_page_probe.exe"
  "$BUILD/win32_stack_growth_probe.exe"
  "$BUILD/win32_uef_probe.exe"
  "$BUILD/win32_fault_record_probe.exe"
  "$BUILD/win32_sigchain_probe.exe"
  "$BUILD/win32_osr_unwind_probe.exe"
  "$BUILD/libw003xmmsentinel.dll"
  "$BUILD/run/boot.jar"
  "$BUILD/run/w010managedfaultprobe.jar"
  "$BUILD/run/w003xmmsentinelprobe.jar"
  "$BUILD/run/crashnativeprobe.jar"
)
for path in "${required_build_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    printf 'missing W-010/W-014 package artifact: %s\n' "$path" >&2
    exit 1
  fi
done

"$REPO/tools/windows_x64/host_package/package_windows_x64_phase3.sh" "$OUT"

boundary_unwind_output="$(
  python3 "$REPO/tests/support/windows/check_win32_boundary_unwind.py" \
    --art-dll "$OUT/art.dll"
)"
printf '%s\n' "$boundary_unwind_output"

for executable in \
  win32_cet_policy_probe.exe \
  win32_debugger_probe.exe \
  win32_art_embedding_probe.exe \
  win32_thread_stack_probe.exe \
  win32_stack_page_probe.exe \
  win32_stack_growth_probe.exe \
  win32_uef_probe.exe \
  win32_fault_record_probe.exe \
  win32_sigchain_probe.exe \
  win32_osr_unwind_probe.exe; do
  cp -a "$BUILD/$executable" "$OUT/"
done
cp -a "$BUILD/libw003xmmsentinel.dll" "$OUT/"
cp -a "$BUILD/run/w010managedfaultprobe.jar" "$OUT/run/"
cp -a "$BUILD/run/w003xmmsentinelprobe.jar" "$OUT/run/"
cp -a "$REPO/tools/verify/windows_x64_phase4/host/RUN_W010_W014_HOST.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/windows_x64_phase4/host/RUN_W010_W014_DIAGNOSTICS.ps1" "$OUT/scripts/"
cp -a "$REPO/tools/verify/windows_x64_phase4/W010_W014_HOST_CHECKLIST.md" "$OUT/"
cp -a "$REPO/tools/verify/windows_x64_phase4/W010_W014_DIAGNOSTICS.md" "$OUT/"
mkdir -p "$OUT/run/data" "$OUT/run/crash" "$OUT/logs"
printf '%s\n' 'Runtime-writable ART data directory; package generation leaves it clean.' \
  >"$OUT/run/data/README.txt"
printf '%s\n' 'Fatal-AV acceptance writes a minidump here; handled faults must not.' \
  >"$OUT/run/crash/README.txt"

cat >"$OUT/W010_W014_STRUCTURAL_REPORT.txt" <<EOF
status=PASS
cet_contract=$cet_output
boundary_unwind=$boundary_unwind_output
osr_unwind=$osr_unwind_summary
explicit_stack_checks=$explicit_stack_output
stack_overflow_delivery=explicit-rsp-below-guarantee-aware-thread-stack-end
win32_implicit_so_checks=false
windows_stack_mapping_ownership=os
windows_stack_guarantee=minimum-four-pages-preserve-larger-query-actual
windows_excluded_low=sum-memory-prefix-guarantee-moving-guard
art_stack_overflow_reserve=8192
linux_stack_probe_contract=implicit-rsp-minus-8192
windows_minimum_build=17134
requested_stack_sizes=0,65536,262144,1048576,2097152,9437184
sigchain_action_calls=3
sigchain_foreign_before_calls=2
sigchain_foreign_after_calls=2
sigchain_sequence=1,2,1,2
managed_npe_read_rounds=64
managed_npe_write_rounds=64
managed_so_main_rounds=2
managed_so_child_rounds=2
managed_recovery=stack-trace,nanoTime,identityHashCode,System.gc
xmm_boundary_registers=10
xmm_self_test_mask=1023
xmm_exception_iterations=32
xmm_exception_self_test_mask=1023
fatal_dispatch_modes=static,jit-j2,jit-j1,osr-j2,osr-j1
diagnostic_fatal_modes=jni-av,jni-raise,native-worker
fatal_unwind_trace=bounded-32-live-veh
fatal_minidumps_required=5
host_llvm_tools_required=no
dalvikvm_sha256=$(sha256sum "$OUT/dalvikvm.exe" | awk '{print $1}')
art_sha256=$(sha256sum "$OUT/art.dll" | awk '{print $1}')
sigchain_sha256=$(sha256sum "$OUT/sigchain.dll" | awk '{print $1}')
osr_probe_sha256=$(sha256sum "$OUT/win32_osr_unwind_probe.exe" | awk '{print $1}')
managed_jar_sha256=$(sha256sum "$OUT/run/w010managedfaultprobe.jar" | awk '{print $1}')
xmm_probe_sha256=$(sha256sum "$OUT/libw003xmmsentinel.dll" | awk '{print $1}')
xmm_jar_sha256=$(sha256sum "$OUT/run/w003xmmsentinelprobe.jar" | awk '{print $1}')
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
stage=E9-configured-guarantee-explicit-stack-checks
EOF

clean_runtime_outputs() {
  find "$OUT/logs" -mindepth 1 -type f -delete
  find "$OUT/run/data" -mindepth 1 ! -name README.txt -delete
  find "$OUT/run/crash" -mindepth 1 ! -name README.txt -delete
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
    relative = path.relative_to(root)
    if (
        path.is_file()
        and "logs" not in relative.parts
        and path.name not in {"MANIFEST.json", "SHA256SUMS.txt"}
    ):
        data = path.read_bytes()
        files.append(
            {
                "path": relative.as_posix(),
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
    find . -type f \
      ! -path './logs/*' \
      ! -name SHA256SUMS.txt \
      -print0 |
      sort -z |
      xargs -0 sha256sum >SHA256SUMS.txt
  )
}

python3 "$REPO/tests/support/windows/check_win32_cet_contract.py" \
  --build "$BUILD" \
  --pe-root "$OUT"

clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/windows_x64_phase4/check_w010_w014_host_package.py" "$OUT"
python3 "$REPO/tools/verify/windows_x64_phase4/smoke_w010_w014_host_package_wine.py" "$OUT"
clean_runtime_outputs
write_manifests
python3 "$REPO/tools/verify/windows_x64_phase4/check_w010_w014_host_package.py" "$OUT"

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
            and not (relative.parts[:2] == ("run", "crash") and path.suffix == ".dmp")
        ):
            output.write(path, path.relative_to(root.parent))
print(f"package={root}")
print(f"archive={archive}")
PY

sha256sum "$OUT.zip" >"$OUT.zip.sha256"
printf 'W010_W014_HOST_PACKAGE_PASS path=%s bytes=%s\n' \
  "$OUT.zip" "$(stat -c %s "$OUT.zip")"
