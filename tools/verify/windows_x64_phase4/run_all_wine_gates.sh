#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/../../.." && pwd)"
export BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
export LINUX_BUILD="${LINUX_BUILD:-$REPO/build/native}"
fail=0
run() {
  local name="$1"; shift
  echo "==== GATE $name ===="
  if "$@"; then echo "PASS $name"; else echo "FAIL $name"; fail=1; fi
}
for cls in GcStressProbe ThreadHeavyProbe HandleLeakProbe PerfSmokeProbe CrashAbortProbe CrashNativeProbe; do
  bash "$ROOT/build_one.sh" "$cls"
done
cmake --build "$BUILD" --target art dalvikvm -j"${JOBS:-32}"
cp -a "$BUILD/art.dll" "$BUILD/run/art.dll"
run P4_W004_RUNTIME_LOAD python3 \
  "$REPO/tools/verify/windows_x64_phase1/check_w004_runtime_load.py" --build "$BUILD"
run P4_W002_MANAGED_ENTRIES python3 \
  "$REPO/tools/verify/windows_x64_phase1/check_w002_managed_entries.py" --build "$BUILD"
run P4_W003_QUICK_BOUNDARIES python3 \
  "$REPO/tools/verify/windows_x64_phase1/check_w003_quick_boundaries.py" \
  --win-build "$BUILD" --linux-build "$LINUX_BUILD"
run P4_W010_EXPLICIT_STACK_CHECKS python3 \
  "$REPO/tools/verify/windows_x64_phase1/check_win32_explicit_stack_checks.py" \
  --repo "$REPO" --win-build "$BUILD" --linux-build "$LINUX_BUILD"
run P4_W010_OSR_STATIC_UNWIND bash "$ROOT/run_osr_unwind_probe.sh"
run P4_W003_FRAME_FAMILIES env \
  PRODUCT_BUILD="$BUILD" \
  BUILD="$REPO/build/windows_x64_w003_frames" \
  REPEATS=2 \
  bash "$ROOT/run_w003_frame_probe.sh"
run P4_W003_XMM_SENTINEL bash "$ROOT/run_w003_xmm_sentinel.sh"
run P4_W002_OSR bash "$ROOT/run_w002_osr_probe.sh"
run P4_W002_ATTACH bash "$ROOT/run_w002_attach_probe.sh"
run P4_W024_CLEANUP_SOURCE python3 "$REPO/tests/support/w024_cleanup.py"
run P4_W014_THREAD_STACK bash "$ROOT/run_thread_stack_probe.sh"
run P4_W010_FAULT_ADAPTER bash "$ROOT/run_fault_adapter_probe.sh"
run P4_W010_JIT_UNWIND_SERIALIZER bash "$ROOT/run_jit_unwind_info_probe.sh"
run P4_W010_JIT_UNWIND_REGISTRY bash "$ROOT/run_jit_unwind_registry_probe.sh"
run P4_W010_JIT_UNWIND_LIFECYCLE bash "$ROOT/run_jit_unwind_lifecycle.sh"
run P4_W010_MANAGED_FAULTS bash "$ROOT/run_w010_managed_fault_probe.sh"
run P4_W010_JIT_FATAL_UNWIND bash "$ROOT/run_jit_fatal_unwind.sh"
run P4_W010_OSR_FATAL_UNWIND bash "$ROOT/run_osr_fatal_unwind.sh"
run P4_G1_GCSTRESS bash "$ROOT/run_gcstress.sh"
run P4_G2_THREADHEAVY bash "$ROOT/run_threadheavy.sh"
run P4_G3_HANDLELEAK bash "$ROOT/run_handleleak.sh"
run P4_G4_PERFSMOKE bash "$ROOT/run_perfsmoke.sh"
run P4_G5_CRASHABORT bash "$ROOT/run_crashabort.sh"
run P4_G5b_CRASHNATIVE bash "$ROOT/run_crashnative.sh"
# keep phase3 golden regression as stability anchor
if [[ -x "$REPO/tools/verify/windows_x64_phase3/run_goldenapp.sh" ]]; then
  run P4_G6_GOLDEN_REG bash "$REPO/tools/verify/windows_x64_phase3/run_goldenapp.sh"
fi
echo "==== SUMMARY ===="
if [[ $fail -eq 0 ]]; then echo "PASS all wine Phase 4 gates"; else echo "FAIL some wine Phase 4 gates"; fi
exit $fail
