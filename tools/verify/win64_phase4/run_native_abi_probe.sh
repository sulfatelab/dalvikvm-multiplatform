#!/usr/bin/env bash
set -euo pipefail

# Verify default mixed/high-FP Win64 compiled-JNI normal/FastNative
# conventions, rebinding, and tracing.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/win64_native_abi_probe}"
WIN64_TOOLCHAIN="${WIN64_TOOLCHAIN:-/home/agent/Projects/win64-dev-env/cmake/Win64LLVM.cmake}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-60}"
DEFAULT_LOG="${TMPDIR:-/tmp}/win64-fastnative-default.log"
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
      ART_WIN64_JIT_LOG_COMPILES=1 \
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
run_probe "$DEFAULT_LOG"
default_rc=$?
NATIVE_ABI_INSTRUMENTATION_PROPERTY=1 run_probe "$TRACE_LOG"
trace_rc=$?
set -e

default_compiled="$(count_compiled_targets "$DEFAULT_LOG")"
trace_compiled="$(count_compiled_targets "$TRACE_LOG")"
default_records="$(count_compilation_records "$DEFAULT_LOG")"
trace_records="$(count_compilation_records "$TRACE_LOG")"

default_values=false
if has_value_markers "$DEFAULT_LOG"; then
  default_values=true
fi
trace_values=false
if has_value_markers "$TRACE_LOG" && has_trace_value_markers "$TRACE_LOG"; then
  trace_values=true
fi

default_ok=false
if [[ $default_rc -eq 0 ]] &&
   [[ $default_values == true ]] &&
   grep -qF "FastNativeAbiProbe OK" "$DEFAULT_LOG" &&
   grep -qF "main end exception=0" "$DEFAULT_LOG" &&
   [[ $default_compiled -eq ${#TARGET_METHODS[@]} ]] &&
   [[ $default_records -eq ${#TARGET_METHODS[@]} ]]; then
  default_ok=true
fi

trace_ok=false
if [[ $trace_rc -eq 0 ]] &&
   [[ $trace_values == true ]] &&
   grep -Eq "FastNativeAbiProbe tracingMode before=0 during=[1-9][0-9]* after=0 traceFileDeleted=true" \
     "$TRACE_LOG" &&
   grep -qF "FastNativeAbiProbe OK" "$TRACE_LOG" &&
   grep -qF "main end exception=0" "$TRACE_LOG" &&
   [[ $trace_compiled -eq ${#TARGET_METHODS[@]} ]] &&
   [[ $trace_records -eq ${#TARGET_METHODS[@]} ]]; then
  trace_ok=true
fi

printf 'default_exit=%s default_ok=%s compiled_targets=%s/%s compilation_records=%s\n' \
  "$default_rc" "$default_ok" "$default_compiled" "${#TARGET_METHODS[@]}" "$default_records"
printf 'instrumentation_exit=%s instrumentation_ok=%s compiled_targets=%s/%s compilation_records=%s\n' \
  "$trace_rc" "$trace_ok" "$trace_compiled" "${#TARGET_METHODS[@]}" "$trace_records"
printf 'default_log=%s\n' "$DEFAULT_LOG"
printf 'instrumentation_log=%s\n' "$TRACE_LOG"

if [[ $default_ok != true ]]; then
  tail -100 "$DEFAULT_LOG" >&2
  exit 1
fi
if [[ $trace_ok != true ]]; then
  tail -100 "$TRACE_LOG" >&2
  exit 1
fi
