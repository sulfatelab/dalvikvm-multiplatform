#!/usr/bin/env bash
set -euo pipefail
# JIT smoke test — verify managed JIT compiles under wine with the native-JIT gate.
#
# Tests:
#   T1 – JIT code cache created (no soft-fail)
#   T2 – Managed methods get JIT-compiled
#   T3 – Hello output is correct
#   T4 – Native methods are NOT JIT-compiled by default (new gate)
#   T5 – ART_WIN64_JIT_NATIVE=1 compiles and executes the native stub
#   T6 – ART_WIN64_JIT=0 disables all compile
#   T7 – -Xusejit:false path still works (no crash)
#   T8 – JIT filter/exclude env vars work
#   T9 – compile diagnostics are silent by default
#
# Usage: ./tools/verify/win64_phase4/run_jit_smoke.sh
#   WINEDEBUG=fixme-all ./run_jit_smoke.sh   (override wine debug)

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
TIMEOUT=180
PASS=0
FAIL=0

red()  { echo -e "\033[31m$*\033[0m"; }
green(){ echo -e "\033[32m$*\033[0m"; }
cyan() { echo -e "\033[36m$*\033[0m"; }

assert() {
  local label="$1"; shift
  if "$@"; then
    green "  PASS $label"
    PASS=$((PASS + 1))
    return 0
  else
    red "  FAIL $label"
    FAIL=$((FAIL + 1))
    return 1
  fi
}

run_dalvik() {
  local jar="$1"; shift
  local cls="$1"; shift
  cd "$BUILD"
  ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run \
  ANDROID_DATA=run/data ICU_DATA=run/icu \
  ART_WIN64_JIT_LOG_COMPILES="${ART_WIN64_JIT_LOG_COMPILES:-}" \
  WINEDEBUG="${WINEDEBUG:--all}" \
  timeout "$TIMEOUT" wine64 ./dalvikvm.exe \
    -Xbootclasspath:run/boot.jar \
    -Xbootclasspath-locations:run/boot.jar \
    -Ximage:/nonexistent-no-boot-image \
    -Xno-sig-chain \
    -XjdwpProvider:none \
    -Xms64m -Xmx512m \
    -cp "$jar" "$cls" \
    "$@" 2>&1 || true
}

# Count JIT compile lines — returns 0 when none found (grep -c exits 1 on 0 matches)
count_compiles() {
  local cnt
  cnt=$(grep -c "Win64 CompileMethod done success=1" <<< "$1" 2>/dev/null) || cnt=0
  echo "$cnt"
}

has_clean_hello() {
  local output="$1"
  grep -q "Hello from dalvikvm" <<< "$output" &&
    grep -q "main end exception=0" <<< "$output"
}

has_clean_native_hello() {
  local output="$1"
  grep -q "StringFactory.newStringFromBytes" <<< "$output" &&
    has_clean_hello "$output"
}

# --------------------------------------------------------------------
cyan "=== T1: JIT Code Cache creation ==="

OUT1=$(ART_WIN64_JIT_LOG_COMPILES=1 run_dalvik "$RUN/hello.jar" "Hello")
echo "$OUT1" | grep -vE '^dalvikvm\.exe|^wine:|^[[:space:]]*$' | head -5
echo "  ... (full log truncated)"

assert "JIT code cache created (JitCodeCache::Create OK)" \
  grep -q "JitCodeCache::Create OK" <<< "$OUT1"

# --------------------------------------------------------------------
cyan "=== T2: Managed methods JIT-compiled ==="

NCOMP=$(count_compiles "$OUT1")
echo "  Managed methods JIT-compiled: $NCOMP"
assert "At least one managed method JIT-compiled" [ "$NCOMP" -gt 0 ]

# --------------------------------------------------------------------
cyan "=== T3: Correct Hello output ==="

assert "Prints Hello and ends without exception" has_clean_hello "$OUT1"

# --------------------------------------------------------------------
cyan "=== T4: Native methods NOT JIT-compiled by default ==="

NATIVE_COMPILE=$(grep "Win64 CompileMethod done success=1" <<< "$OUT1" 2>/dev/null | grep -i "StringFactory" || true)
if [ -z "$NATIVE_COMPILE" ]; then
  green "  PASS No native methods JIT-compiled (gate active)"
  PASS=$((PASS + 1))
else
  echo "  Native compile detected:"
  echo "$NATIVE_COMPILE"
  red "  FAIL — native method JIT-compiled when it should be gated"
  FAIL=$((FAIL + 1))
fi

# --------------------------------------------------------------------
cyan "=== T5: ART_WIN64_JIT_NATIVE=1 gate override ==="

OUT5=$(ART_WIN64_JIT_NATIVE=1 ART_WIN64_JIT_LOG_COMPILES=1 \
  run_dalvik "$RUN/hello.jar" "Hello")
NCOMP5=$(count_compiles "$OUT5")
echo "  Native-gate-open mode ncomp: $NCOMP5"
assert "ART_WIN64_JIT_NATIVE=1 compiles and executes native ABI" has_clean_native_hello "$OUT5"

# --------------------------------------------------------------------
cyan "=== T6: ART_WIN64_JIT=0 disables all compile ==="

OUT6=$(ART_WIN64_JIT=0 ART_WIN64_JIT_LOG_COMPILES=1 \
  run_dalvik "$RUN/hello.jar" "Hello")
NCOMP6=$(count_compiles "$OUT6")
echo "  JIT_OFF mode ncomp: $NCOMP6"
assert "ART_WIN64_JIT=0 completes Hello cleanly" has_clean_hello "$OUT6"
assert "ART_WIN64_JIT=0 produces zero JIT compiles" [ "$NCOMP6" -eq 0 ]

# --------------------------------------------------------------------
cyan "=== T7: -Xusejit:false path ==="

OUT7=$(run_dalvik "$RUN/hello.jar" "Hello" -Xusejit:false)
assert "-Xusejit:false completes Hello cleanly" has_clean_hello "$OUT7"
# Note: -Xusejit:false may still create the JIT cache on Win64 b/c
# JitCodeCache::Create happens during Runtime::Init before flags are fully
# evaluated. This is a known subtlety; the key invariant is "no crash."

# --------------------------------------------------------------------
cyan "=== T8: JIT filter/exclude env vars ==="

OUT8_FILT=$(ART_WIN64_JIT_FILTER=StringBuilder ART_WIN64_JIT_LOG_COMPILES=1 \
  run_dalvik "$RUN/hello.jar" "Hello")
FCOMP=$(count_compiles "$OUT8_FILT")
echo "  Filter mode ncomp: $FCOMP"
assert "ART_WIN64_JIT_FILTER completes Hello cleanly" has_clean_hello "$OUT8_FILT"

OUT8_EXCL=$(ART_WIN64_JIT_EXCLUDE=StringBuilder ART_WIN64_JIT_LOG_COMPILES=1 \
  run_dalvik "$RUN/hello.jar" "Hello")
assert "ART_WIN64_JIT_EXCLUDE completes Hello cleanly" has_clean_hello "$OUT8_EXCL"

# --------------------------------------------------------------------
cyan "=== T9: Compile diagnostics are opt-in ==="

OUT9=$(run_dalvik "$RUN/hello.jar" "Hello")
NCOMP9=$(count_compiles "$OUT9")
assert "Default diagnostic-off mode completes Hello cleanly" has_clean_hello "$OUT9"
assert "Default diagnostic-off mode emits zero compile records" [ "$NCOMP9" -eq 0 ]

# --------------------------------------------------------------------
echo ""
echo "========================================="
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "========================================="

if [ "$FAIL" -gt 0 ]; then
  red "SOME TESTS FAILED"
  exit 1
else
  green "ALL TESTS PASSED"
  exit 0
fi
