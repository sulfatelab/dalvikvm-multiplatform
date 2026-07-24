#!/usr/bin/env bash
set -euo pipefail
# P4 JIT matrix — run CEnc/float/Math/Io probes under JIT (no -Xint).
# Verifies managed JIT does not regress any existing workload.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
TIMEOUT=60
PASS=0
FAIL=0

red()  { echo -e "\033[31m$*\033[0m"; }
green(){ echo -e "\033[32m$*\033[0m"; }
cyan() { echo -e "\033[36m$*\033[0m"; }

# Run probe; verify markers in output.
run_one() {
  local jar="$1" cls="$2" label="$3"; shift 3
  local markers=("$@")

  local outfile
  outfile=$(mktemp)

  cd "$BUILD"
  ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run \
  ANDROID_DATA=run/data ICU_DATA=run/icu \
  ART_WIN64_JIT_LOG_COMPILES=1 \
  WINEDEBUG="${WINEDEBUG:--all}" \
  timeout "$TIMEOUT" wine64 ./dalvikvm.exe \
    -Xbootclasspath:run/boot.jar \
    -Xbootclasspath-locations:run/boot.jar \
    -Ximage:/nonexistent-no-boot-image \
    -Xno-sig-chain \
    -XjdwpProvider:none \
    -Xms64m -Xmx512m \
    -cp "$jar" "$cls" \
    > "$outfile" 2>&1 || true

  local ncomp
  ncomp=$(grep -c "Win64 CompileMethod done success=1" "$outfile" 2>/dev/null) || ncomp=0

  cyan "--- $label ($cls) compiles=$ncomp ---"

  local fail=0
  for marker in "${markers[@]}"; do
    if grep -qF "$marker" "$outfile"; then
      green "  PASS '$marker'"
      PASS=$((PASS + 1))
    else
      red "  FAIL '$marker'"
      FAIL=$((FAIL + 1))
      fail=1
    fi
  done

  if [ "$fail" -ne 0 ]; then
    echo "  --- tail (no filter) ---"
    tail -8 "$outfile"
  fi
  rm -f "$outfile"
}

# --------------------------------------------------------------------
cyan "=== P4 JIT Matrix ==="

# Silent probes: main ended without exception
MAIN_OK="main end exception=0"
run_one "$RUN/CEnc.jar"   CEnc   "CEnc"   "$MAIN_OK"
run_one "$RUN/CEnc2.jar"  CEnc2  "CEnc2"  "$MAIN_OK"
run_one "$RUN/CELike.jar" CELike "CELike" "$MAIN_OK"
run_one "$RUN/CFloat.jar" CFloat "CFloat" "$MAIN_OK"

# Float probes with explicit output markers
run_one "$RUN/FloatProbe.jar" FloatProbe "FloatProbe" "FloatProbe OK"
run_one "$RUN/IFloat.jar"    IFloat    "IFloat"       "IFloat OK"
run_one "$RUN/JLFloat.jar"   JLFloat   "JLFloat"      "$MAIN_OK"
run_one "$RUN/RFloat.jar"    RFloat    "RFloat"       "$MAIN_OK"
run_one "$RUN/SFloat.jar"    SFloat    "SFloat"       "$MAIN_OK"

# Math
run_one "$RUN/MathProbe.jar" MathProbe "MathProbe" "MathProbe.done=ok"

# Io / Net
run_one "$RUN/IoProbe.jar"  IoProbe  "IoProbe"  "IoProbe.done=ok"
run_one "$RUN/NetProbe.jar" NetProbe "NetProbe" "NetProbe.done=ok"

# Stability: GC + throw
run_one "$RUN/gcprobe.jar"    GcProbe    "GcProbe"    "GcProbe.done=ok"
# ThrowProbe intentionally throws RuntimeException with marker text
run_one "$RUN/throwprobe.jar" ThrowProbe "ThrowProbe" "phase3-throw-ok"

# --------------------------------------------------------------------
echo ""
echo "========================================="
echo "  P4 JIT MATRIX: $PASS passed, $FAIL failed"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
  red "SOME TESTS FAILED"
  exit 1
else
  green "ALL P4 JIT MATRIX TESTS PASSED"
  exit 0
fi
