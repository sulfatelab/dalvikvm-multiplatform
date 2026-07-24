#!/usr/bin/env bash
set -euo pipefail

# Verify the Win64 optimizing-compiler direct @CriticalNative ABI, including
# threshold-zero ()J and unresolved exported mixed-signature dlsym paths.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/win64_critical_native_probe}"
WIN64_TOOLCHAIN="${WIN64_TOOLCHAIN:-/home/agent/Projects/win64-dev-env/cmake/Win64LLVM.cmake}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
REPEATS="${REPEATS:-3}"
TIMEOUT="${TIMEOUT:-60}"

if [[ ! -x "$BUILD/dalvikvm.exe" || ! -f "$RUN/FloatProbe.jar" ]]; then
  echo "missing Win64 dalvikvm or FloatProbe.jar under $BUILD" >&2
  exit 1
fi

cmake -S "$REPO/tools/verify/win64_phase4/critical_native" \
  -B "$NATIVE_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WIN64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$NATIVE_BUILD" -j"$(nproc)"

EXPORTS="$(llvm-readobj --coff-exports "$NATIVE_BUILD/libcriticalnativeprobe.dll")"
for symbol in JNI_OnLoad \
    Java_CriticalNativeDlsymProbe_zero \
    Java_CriticalNativeDlsymProbe_sixLongs \
    Java_CriticalNativeDlsymProbe_sixDoubles \
    Java_CriticalNativeDlsymProbe_mixed \
    Java_CriticalNativeDlsymProbe_mixed32 \
    Java_CriticalNativeDlsymProbe_floatReturn \
    Java_CriticalNativeDlsymProbe_callMask; do
  if ! grep -qF "Name: $symbol" <<< "$EXPORTS"; then
    echo "critical native probe DLL does not export $symbol" >&2
    exit 1
  fi
done
cp -f "$NATIVE_BUILD/libcriticalnativeprobe.dll" "$BUILD/"
mkdir -p "$BUILD/empty-native-dir"

JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/win64-critical-java.XXXXXX")"
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex"
"$JAVAC" -d "$JAVA_TMP/classes" \
  "$REPO/vendor/libcore/dalvik/src/main/java/dalvik/annotation/optimization/CriticalNative.java" \
  "$REPO/tools/verify/win64_phase4/src/CriticalNativeProbe.java" \
  "$REPO/tools/verify/win64_phase4/src/CriticalNativeDlsymProbe.java"
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" \
  "$JAVA_TMP/classes/CriticalNativeProbe.class" \
  "$JAVA_TMP/classes/CriticalNativeDlsymProbe.class"
"$JAR" --create --file "$RUN/criticalnativeprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

run_vm() {
  local mode="$1"
  local dual="$2"
  local probe="$3"
  local jar="$4"
  local cls="$5"
  local marker="$6"
  local values_marker="$7"
  local iteration="$8"
  local load_mode="${9:-library}"
  local log="${TMPDIR:-/tmp}/win64-critical-${mode}-${probe}-${iteration}.log"

  local rc
  if (
    cd "$BUILD"
    ART_WIN64_JIT_DUAL="$dual" \
    ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run \
    ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}" \
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -Xno-sig-chain \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      -Xjitthreshold:0 \
      -Dcritical.load="$load_mode" \
      '-Djava.library.path=empty-native-dir;.' \
      -cp "$jar" "$cls"
  ) > "$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  if [[ $rc -eq 0 ]] &&
     grep -qF "$marker" "$log" &&
     grep -qF "main end exception=0" "$log" &&
     { [[ -z "$values_marker" ]] || grep -qF "$values_marker" "$log"; }; then
    printf '%s %s run=%s PASS\n' "$mode" "$probe" "$iteration"
    return 0
  fi

  printf '%s %s run=%s FAIL exit=%s log=%s\n' \
    "$mode" "$probe" "$iteration" "$rc" "$log" >&2
  tail -100 "$log" >&2
  return 1
}

FLOAT_VALUES=""
CRITICAL_VALUES="CriticalNativeProbe values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true"
DLSYM_VALUES="CriticalNativeDlsymProbe values longs=190 doubles=91.0 mixed=159.5 mixed32=87 floatReturn=15.25 calls=63 branchSeen=true"

for mode_and_dual in "dual:1" "j1:0"; do
  mode="${mode_and_dual%%:*}"
  dual="${mode_and_dual##*:}"
  for iteration in $(seq 1 "$REPEATS"); do
    run_vm "$mode" "$dual" float "$RUN/FloatProbe.jar" \
      FloatProbe "FloatProbe OK" "$FLOAT_VALUES" "$iteration"
    if (( iteration % 2 == 0 )); then
      load_mode="absolute"
    else
      load_mode="library"
    fi
    run_vm "$mode" "$dual" signatures "$RUN/criticalnativeprobe.jar" \
      CriticalNativeProbe "CriticalNativeProbe OK" "$CRITICAL_VALUES" "$iteration" "$load_mode"
    log="${TMPDIR:-/tmp}/win64-critical-${mode}-signatures-${iteration}.log"
    if ! grep -qF "CriticalNativeProbe load=$load_mode" "$log"; then
      echo "$mode signature load-mode verification failed: $log" >&2
      tail -100 "$log" >&2
      exit 1
    fi
    if ! grep -qF "CriticalNativeDlsymProbe OK" "$log" ||
       ! grep -qF "$DLSYM_VALUES" "$log"; then
      echo "$mode unresolved dlsym signature verification failed: $log" >&2
      tail -100 "$log" >&2
      exit 1
    fi
  done
done

printf 'CriticalNative acceptance: dual=%s/%s float+signature runs; j1=%s/%s\n' \
  "$((REPEATS * 2))" "$((REPEATS * 2))" \
  "$((REPEATS * 2))" "$((REPEATS * 2))"
