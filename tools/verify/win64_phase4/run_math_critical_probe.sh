#!/usr/bin/env bash
set -euo pipefail

# Verify the restored AOSP-like Math.ceil/floor @CriticalNative surface with
# the same shared boot.jar on Win64 and Linux.

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
NATIVE="${MDVM_NATIVE:-$REPO/build/native}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-90}"
REPEATS="${REPEATS:-3}"

for required in "$BUILD/dalvikvm.exe" "$RUN/boot.jar" "$NATIVE/dalvikvm"; do
  if [[ ! -e "$required" ]]; then
    echo "missing required runtime artifact: $required" >&2
    exit 2
  fi
done

MATH_JAVA="$REPO/vendor/libcore/ojluni/src/main/java/java/lang/Math.java"
MATH_C="$REPO/vendor/libcore/ojluni/src/main/native/Math.c"
if rg -q 'gMethodsWin|defined\(_WIN32\)' "$MATH_C" ||
   ! rg -q 'public static native double ceil\(double a\);' "$MATH_JAVA" ||
   ! rg -q 'public static native double floor\(double a\);' "$MATH_JAVA" ||
   ! rg -q '(FAST|CRITICAL)_NATIVE_METHOD\(Math, ceil, "\(D\)D"\)' "$MATH_C" ||
   ! rg -q '(FAST|CRITICAL)_NATIVE_METHOD\(Math, floor, "\(D\)D"\)' "$MATH_C"; then
  echo "Math CriticalNative source surface or shared registration table is not restored" >&2
  exit 2
fi

JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/math-critical-java.XXXXXX")"
LINUX_RUN="$(mktemp -d "${TMPDIR:-/tmp}/math-critical-linux.XXXXXX")"
trap 'rm -rf "$JAVA_TMP" "$LINUX_RUN"' EXIT
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex" "$LINUX_RUN/data" "$LINUX_RUN/icu"

"$JAVAC" --release 8 -Xlint:-options -d "$JAVA_TMP/classes" \
  "$REPO/tools/verify/win64_phase4/src/MathCriticalProbe.java"
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" \
  "$JAVA_TMP/classes/MathCriticalProbe.class"
"$JAR" --create --file "$RUN/mathcriticalprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

check_log() {
  local label="$1"
  local log="$2"
  if ! grep -qF 'MathCriticalProbe native ceil=true floor=true cases=23 rounds=2000' "$log" ||
     ! grep -qF 'MathCriticalProbe OK' "$log" ||
     ! grep -qF 'main end exception=0' "$log"; then
    echo "$label missing acceptance markers: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi
}

run_wine() {
  local label="$1"
  local dual="$2"
  local iteration="$3"
  shift 3
  local log="${TMPDIR:-/tmp}/math-critical-${label}-${iteration}.log"
  if ! (
    cd "$BUILD"
    ART_WIN64_JIT_DUAL="$dual" \
    ART_WIN64_JIT_FILTER=MathCriticalProbe \
    ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run \
    ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}" \
    timeout -k 1 "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -Xno-sig-chain \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      "$@" \
      -cp run/mathcriticalprobe.jar MathCriticalProbe
  ) >"$log" 2>&1; then
    echo "$label run=$iteration failed: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi
  check_log "$label run=$iteration" "$log"
  printf '%s run=%s PASS\n' "$label" "$iteration"
}

for iteration in $(seq 1 "$REPEATS"); do
  run_wine dual 1 "$iteration" -Xjitthreshold:0
  run_wine j1 0 "$iteration" -Xjitthreshold:0
  run_wine xint 1 "$iteration" -Xint
done

cp -f "$RUN/boot.jar" "$LINUX_RUN/boot.jar"
cp -f "$RUN/mathcriticalprobe.jar" "$LINUX_RUN/mathcriticalprobe.jar"
for candidate in \
    "$RUN/icu/icudt72l.dat" \
    "$REPO/vendor/icu/icu4c/source/stubdata/icudt72l.dat"; do
  if [[ -f "$candidate" ]]; then
    cp -f "$candidate" "$LINUX_RUN/icu/icudt72l.dat"
    break
  fi
done

run_linux() {
  local label="$1"
  shift
  local log="${TMPDIR:-/tmp}/math-critical-${label}.log"
  if ! (
    ANDROID_ROOT="$LINUX_RUN" ANDROID_ART_ROOT="$LINUX_RUN" \
    ANDROID_I18N_ROOT="$LINUX_RUN" ANDROID_DATA="$LINUX_RUN/data" \
    ICU_DATA="$LINUX_RUN/icu" \
    LD_LIBRARY_PATH="$NATIVE${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    timeout -k 1 "$TIMEOUT" "$NATIVE/dalvikvm" \
      -Xbootclasspath:"$LINUX_RUN/boot.jar" \
      -Xbootclasspath-locations:"$LINUX_RUN/boot.jar" \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      "$@" \
      -cp "$LINUX_RUN/mathcriticalprobe.jar" MathCriticalProbe
  ) >"$log" 2>&1; then
    echo "$label failed: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi
  check_log "$label" "$log"
  printf '%s PASS\n' "$label"
}

run_linux linux-xint -Xint
run_linux linux-jit -Xjitthreshold:0

if ! cmp -s "$RUN/boot.jar" "$LINUX_RUN/boot.jar"; then
  echo "Linux did not consume the exact Win64-staged boot.jar bytes" >&2
  exit 1
fi

printf 'Math CriticalNative acceptance: dual=%s/%s j1=%s/%s xint=%s/%s linux-xint=1/1 linux-jit=1/1\n' \
  "$REPEATS" "$REPEATS" "$REPEATS" "$REPEATS" "$REPEATS" "$REPEATS"
