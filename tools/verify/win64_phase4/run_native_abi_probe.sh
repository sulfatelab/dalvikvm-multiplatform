#!/usr/bin/env bash
set -euo pipefail

# Verify mixed/high-FP Win64 compiled-JNI normal/FastNative conventions, rebinding, and tracing.
# Set EXPECT_FIXED=0 to reproduce the historical pre-split failure contract.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/win64_native_abi_probe}"
WIN64_TOOLCHAIN="${WIN64_TOOLCHAIN:-/home/agent/Projects/win64-dev-env/cmake/Win64LLVM.cmake}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
EXPECT_FIXED="${EXPECT_FIXED:-1}"
TIMEOUT="${TIMEOUT:-60}"
CLOSED_LOG="${TMPDIR:-/tmp}/win64-fastnative-gate-closed.log"
OPEN_LOG="${TMPDIR:-/tmp}/win64-fastnative-gate-open.log"
TRACE_LOG="${TMPDIR:-/tmp}/win64-fastnative-instrumentation.log"

cmake -S "$REPO/tools/verify/win64_phase4/native_abi" \
  -B "$NATIVE_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WIN64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$NATIVE_BUILD" -j"$(nproc)"

EXPORTS="$(llvm-readobj --coff-exports "$NATIVE_BUILD/libnativeabiprobe.dll")"
for symbol in JNI_OnLoad \
    Java_FastNativeAbiProbe_normalRegistered \
    Java_FastNativeAbiProbe_fastRegistered \
    Java_FastNativeAbiProbe_normalDlsym \
    Java_FastNativeAbiProbe_fastDlsym \
    Java_FastNativeAbiProbe_normalInstance \
    Java_FastNativeAbiProbe_fastInstance \
    Java_FastNativeAbiProbe_callMask \
    Java_FastNativeAbiProbe_unregisterNatives \
    Java_FastNativeAbiProbe_registerAlternateNatives; do
  if ! grep -qF "Name: $symbol" <<< "$EXPORTS"; then
    echo "native ABI probe DLL does not export $symbol" >&2
    exit 1
  fi
done
cp -f "$NATIVE_BUILD/libnativeabiprobe.dll" "$BUILD/"
mkdir -p "$BUILD/empty-native-dir"

JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/win64-native-abi-java.XXXXXX")"
trap 'rm -rf "$JAVA_TMP"' EXIT
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex"
"$JAVAC" -d "$JAVA_TMP/classes" \
  "$REPO/vendor/libcore/dalvik/src/main/java/dalvik/annotation/optimization/FastNative.java" \
  "$REPO/tools/verify/win64_phase4/src/FastNativeAbiProbe.java"
mapfile -t CLASS_FILES < <(find "$JAVA_TMP/classes" -name '*.class' | sort)
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" "${CLASS_FILES[@]}"
"$JAR" --create --file "$RUN/fastnativeabiprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

run_probe() {
  local log="$1"
  shift
  (
    cd "$BUILD"
    rm -f native-abi-instrumentation.trace
    env \
      ANDROID_ROOT=run \
      ANDROID_ART_ROOT=run \
      ANDROID_I18N_ROOT=run \
      ANDROID_DATA=run/data \
      ICU_DATA=run/icu \
      WINEDEBUG="${WINEDEBUG:--all}" \
      ART_WIN64_JIT_FILTER=FastNativeAbiProbe \
      "$@" \
      timeout -k 1 "$TIMEOUT" "$WINE" ./dalvikvm.exe \
        -Xbootclasspath:run/boot.jar \
        -Xbootclasspath-locations:run/boot.jar \
        -Ximage:/nonexistent-no-boot-image \
        -Xno-sig-chain \
        -XjdwpProvider:none \
        -Xms64m -Xmx512m \
        -Xjitthreshold:0 \
        "-Dnative.abi.instrumentation=${NATIVE_ABI_INSTRUMENTATION_PROPERTY:-0}" \
        '-Djava.library.path=empty-native-dir;.' \
        -cp "$RUN/fastnativeabiprobe.jar" FastNativeAbiProbe
    rc=$?
    rm -f native-abi-instrumentation.trace
    exit "$rc"
  ) >"$log" 2>&1
}

TARGET_METHODS=(
  "double FastNativeAbiProbe.normalRegistered("
  "double FastNativeAbiProbe.fastRegistered("
  "double FastNativeAbiProbe.normalDlsym("
  "double FastNativeAbiProbe.fastDlsym("
  "double FastNativeAbiProbe.normalInstance("
  "double FastNativeAbiProbe.fastInstance("
  "int FastNativeAbiProbe.callMask("
)
VALUE_MARKERS=(
  "FastNativeAbiProbe initial normalRegistered=743.75 fastRegistered=1743.75 normalDlsym=2755.75 fastDlsym=3755.75 normalInstance=4743.75 fastInstance=5743.75 calls=63"
  "FastNativeAbiProbe unregistered normalRegistered=10743.75 fastRegistered=11743.75 normalDlsym=12755.75 fastDlsym=13755.75 normalInstance=14743.75 fastInstance=15743.75 calls=63"
  "FastNativeAbiProbe reregistered normalRegistered=20743.75 fastRegistered=21743.75 normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 fastInstance=25743.75 calls=63"
)
TRACE_VALUE_MARKERS=(
  "FastNativeAbiProbe tracing normalRegistered=20743.75 fastRegistered=21743.75 normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 fastInstance=25743.75 calls=63"
  "FastNativeAbiProbe postTracing normalRegistered=20743.75 fastRegistered=21743.75 normalDlsym=22755.75 fastDlsym=23755.75 normalInstance=24743.75 fastInstance=25743.75 calls=63"
)

count_compiled_targets() {
  local log="$1"
  local count=0
  local method
  for method in "${TARGET_METHODS[@]}"; do
    if grep -qF "success=1 method=$method" "$log"; then
      count=$((count + 1))
    fi
  done
  printf '%s' "$count"
}

count_compilation_records() {
  local log="$1"
  local count=0
  local matches
  local method
  for method in "${TARGET_METHODS[@]}"; do
    matches="$(grep -cF "success=1 method=$method" "$log" || true)"
    count=$((count + matches))
  done
  printf '%s' "$count"
}

has_value_markers() {
  local log="$1"
  local marker
  for marker in "${VALUE_MARKERS[@]}"; do
    if ! grep -qF "$marker" "$log"; then
      return 1
    fi
  done
}

has_trace_value_markers() {
  local log="$1"
  local marker
  for marker in "${TRACE_VALUE_MARKERS[@]}"; do
    if ! grep -qF "$marker" "$log"; then
      return 1
    fi
  done
}

set +e
run_probe "$CLOSED_LOG"
closed_rc=$?
run_probe "$OPEN_LOG" ART_WIN64_JIT_NATIVE=1
open_rc=$?
NATIVE_ABI_INSTRUMENTATION_PROPERTY=1 run_probe "$TRACE_LOG" ART_WIN64_JIT_NATIVE=1
trace_rc=$?
set -e

closed_compiled="$(count_compiled_targets "$CLOSED_LOG")"
open_compiled="$(count_compiled_targets "$OPEN_LOG")"
trace_compiled="$(count_compiled_targets "$TRACE_LOG")"
closed_records="$(count_compilation_records "$CLOSED_LOG")"
open_records="$(count_compilation_records "$OPEN_LOG")"
trace_records="$(count_compilation_records "$TRACE_LOG")"

closed_values=false
if has_value_markers "$CLOSED_LOG"; then
  closed_values=true
fi
open_values=false
if has_value_markers "$OPEN_LOG"; then
  open_values=true
fi
trace_values=false
if has_value_markers "$TRACE_LOG" && has_trace_value_markers "$TRACE_LOG"; then
  trace_values=true
fi

closed_ok=false
if [[ $closed_rc -eq 0 ]] &&
   [[ $closed_values == true ]] &&
   grep -qF "FastNativeAbiProbe OK" "$CLOSED_LOG" &&
   grep -qF "main end exception=0" "$CLOSED_LOG" &&
   [[ $closed_compiled -eq 0 ]] &&
   [[ $closed_records -eq 0 ]]; then
  closed_ok=true
fi

open_ok=false
if [[ $open_rc -eq 0 ]] &&
   [[ $open_values == true ]] &&
   grep -qF "FastNativeAbiProbe OK" "$OPEN_LOG" &&
   grep -qF "main end exception=0" "$OPEN_LOG" &&
   [[ $open_compiled -eq ${#TARGET_METHODS[@]} ]] &&
   [[ $open_records -eq ${#TARGET_METHODS[@]} ]]; then
  open_ok=true
fi

trace_ok=false
if [[ $trace_rc -eq 0 ]] &&
   [[ $trace_values == true ]] &&
   grep -Eq "FastNativeAbiProbe tracingMode before=0 during=[1-9][0-9]* after=0 traceFileDeleted=true" \
     "$TRACE_LOG" &&
   grep -qF "FastNativeAbiProbe OK" "$TRACE_LOG" &&
   grep -qF "main end exception=0" "$TRACE_LOG" &&
   [[ $trace_compiled -eq ${#TARGET_METHODS[@]} ]] &&
   [[ $trace_records -ge ${#TARGET_METHODS[@]} ]]; then
  trace_ok=true
fi

historical_failure=false
if [[ $open_rc -ne 0 ]] &&
   [[ $open_compiled -gt 0 ]] &&
   ! grep -qF "FastNativeAbiProbe OK" "$OPEN_LOG"; then
  historical_failure=true
fi

printf 'gate_closed_exit=%s gate_closed_ok=%s compiled_targets=%s/%s compilation_records=%s\n' \
  "$closed_rc" "$closed_ok" "$closed_compiled" "${#TARGET_METHODS[@]}" "$closed_records"
printf 'gate_open_exit=%s gate_open_ok=%s compiled_targets=%s/%s compilation_records=%s historical_failure=%s\n' \
  "$open_rc" "$open_ok" "$open_compiled" "${#TARGET_METHODS[@]}" "$open_records" \
  "$historical_failure"
printf 'instrumentation_exit=%s instrumentation_ok=%s compiled_targets=%s/%s compilation_records=%s\n' \
  "$trace_rc" "$trace_ok" "$trace_compiled" "${#TARGET_METHODS[@]}" "$trace_records"
printf 'expected_mode=%s\n' "$([[ $EXPECT_FIXED == 1 ]] && echo fixed || echo historical-failure)"
printf 'gate_closed_log=%s\n' "$CLOSED_LOG"
printf 'gate_open_log=%s\n' "$OPEN_LOG"
printf 'instrumentation_log=%s\n' "$TRACE_LOG"

if [[ $closed_ok != true ]]; then
  tail -100 "$CLOSED_LOG" >&2
  exit 1
fi
if [[ $EXPECT_FIXED == 1 && $open_ok != true ]]; then
  tail -100 "$OPEN_LOG" >&2
  exit 1
fi
if [[ $EXPECT_FIXED == 1 && $trace_ok != true ]]; then
  tail -100 "$TRACE_LOG" >&2
  exit 1
fi
if [[ $EXPECT_FIXED != 1 && $historical_failure != true ]]; then
  tail -100 "$OPEN_LOG" >&2
  exit 1
fi
