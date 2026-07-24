#!/usr/bin/env bash
set -euo pipefail

# Verify real JVMTI thread-scoped forced-interpreter transitions around
# compiled normal, FastNative, and CriticalNative methods.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
AGENT_BUILD="${AGENT_BUILD:-$REPO/build/win64_jvmti_force_probe}"
WIN64_TOOLCHAIN="${WIN64_TOOLCHAIN:-/home/agent/Projects/win64-dev-env/cmake/Win64LLVM.cmake}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-90}"
REPEATS="${REPEATS:-3}"

cmake -S "$REPO/tools/verify/win64_phase4/jvmti_force" \
  -B "$AGENT_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WIN64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$AGENT_BUILD" -j"$(nproc)"
cmake --build "$BUILD" --target openjdkjvmti -j"$(nproc)"

for dll in "$BUILD/openjdkjvmti.dll" "$AGENT_BUILD/libjvmtiforceprobe.dll"; do
  if [[ ! -f "$dll" ]]; then
    echo "missing JVMTI DLL: $dll" >&2
    exit 1
  fi
done
cp -f "$AGENT_BUILD/libjvmtiforceprobe.dll" "$BUILD/"

JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/win64-jvmti-force-java.XXXXXX")"
trap 'rm -rf "$JAVA_TMP"' EXIT
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex"
"$JAVAC" -d "$JAVA_TMP/classes" \
  "$REPO/vendor/libcore/dalvik/src/main/java/dalvik/annotation/optimization/FastNative.java" \
  "$REPO/vendor/libcore/dalvik/src/main/java/dalvik/annotation/optimization/CriticalNative.java" \
  "$REPO/tools/verify/win64_phase4/src/JvmtiForceProbe.java"
mapfile -t CLASS_FILES < <(find "$JAVA_TMP/classes" -name '*.class' | sort)
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" "${CLASS_FILES[@]}"
"$JAR" --create --file "$RUN/jvmtiforceprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

TARGET_METHODS=(
  "double JvmtiForceProbe.normalRegistered("
  "double JvmtiForceProbe.fastRegistered("
)

run_one() {
  local mode="$1"
  local dual="$2"
  local iteration="$3"
  local log="${TMPDIR:-/tmp}/win64-jvmti-force-${mode}-${iteration}.log"

  if ! (
    cd "$BUILD"
    ART_WIN64_JIT_DUAL="$dual" \
    ART_WIN64_JIT_NATIVE=1 \
    ART_WIN64_JIT_FILTER=JvmtiForceProbe \
    ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run \
    ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}" \
    timeout -k 1 "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -Xno-sig-chain \
      -XjdwpProvider:none \
      -Xplugin:openjdkjvmti.dll \
      -agentpath:libjvmtiforceprobe.dll \
      -Xms64m -Xmx512m \
      -Xjitthreshold:0 \
      '-Djava.library.path=.' \
      -cp run/jvmtiforceprobe.jar JvmtiForceProbe
  ) >"$log" 2>&1; then
    echo "$mode run=$iteration failed: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  for phase in before during after; do
    if ! grep -qF "JvmtiForceProbe $phase normalRegistered=137.75 fastRegistered=237.75 criticalRegistered=337.75 normalDlsym=437.75 fastDlsym=537.75 criticalDlsym=637.75" "$log"; then
      echo "$mode run=$iteration missing $phase values: $log" >&2
      tail -120 "$log" >&2
      return 1
    fi
  done
  if ! grep -Eq 'JvmtiForceProbe steps before=0 during=[1-9][0-9]* disabled=[1-9][0-9]* final=[1-9][0-9]*' "$log" ||
     ! grep -qF 'JvmtiForceProbe OK' "$log" ||
     ! grep -qF 'main end exception=0' "$log"; then
    echo "$mode run=$iteration missing transition markers: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  local records=0
  local method
  for method in "${TARGET_METHODS[@]}"; do
    local matches
    matches="$(grep -cF "success=1 method=$method" "$log" || true)"
    if [[ "$matches" -ne 1 ]]; then
      echo "$mode run=$iteration target compilation count $matches for $method: $log" >&2
      tail -120 "$log" >&2
      return 1
    fi
    records=$((records + matches))
  done
  if grep -qF 'success=1 method=double JvmtiForceProbe.criticalRegistered(' "$log" ||
     grep -qF 'success=1 method=double JvmtiForceProbe.criticalDlsym(' "$log"; then
    echo "$mode run=$iteration unexpectedly compiled CriticalNative in a debuggable runtime: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  printf '%s run=%s PASS compiled_registered_targets=%s/%s compilation_records=%s critical_debuggable_compile=0\n' \
    "$mode" "$iteration" "${#TARGET_METHODS[@]}" "${#TARGET_METHODS[@]}" "$records"
}

for mode_and_dual in "dual:1" "j1:0"; do
  mode="${mode_and_dual%%:*}"
  dual="${mode_and_dual##*:}"
  for iteration in $(seq 1 "$REPEATS"); do
    run_one "$mode" "$dual" "$iteration"
  done
done

printf 'JVMTI forced-interpreter acceptance: dual=%s/%s j1=%s/%s\n' \
  "$REPEATS" "$REPEATS" "$REPEATS" "$REPEATS"
