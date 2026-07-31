#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="$REPO/build/windows_x64_phase1"
RUN="$BUILD/run"
NATIVE_BUILD="$REPO/build/native"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
SRC="$REPO/tests/cases/non-moving-heap/W013NonMovingStressProbe.java"
OUT="$REPO/tools/verify/windows_x64_w013/bin"
CLASSES="$OUT/W013NonMovingStressProbe_classes"
DEX="$OUT/W013NonMovingStressProbe_dex"
JAR="$RUN/w013nonmovingstressprobe.jar"
LINUX_DATA="/tmp/mdvm_linux_w013_data"
WIN_LOG="$(mktemp /tmp/mdvm_w013_nonmoving_win.XXXXXX.log)"
LINUX_LOG="$(mktemp /tmp/mdvm_w013_nonmoving_linux.XXXXXX.log)"
trap 'rm -f "$WIN_LOG" "$LINUX_LOG"' EXIT

for required in "$JAVAC" "$R8JAR" "$SRC" "$BUILD/dalvikvm.exe" "$NATIVE_BUILD/dalvikvm" \
    "$RUN/boot.jar"; do
  if [[ ! -f "$required" ]]; then
    echo "W013_NON_MOVING_STRESS_FAIL: missing $required" >&2
    exit 1
  fi
done

rm -rf "$CLASSES" "$DEX"
mkdir -p "$CLASSES" "$DEX" "$LINUX_DATA"
"$JAVAC" -d "$CLASSES" "$SRC"
mapfile -t class_files < <(find "$CLASSES" -name '*.class' | sort)
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$DEX" "${class_files[@]}"
python3 - "$DEX/classes.dex" "$JAR" <<'PY'
import os
import sys
import zipfile

dex, output = sys.argv[1:]
with zipfile.ZipFile(output, "w") as archive:
    archive.write(dex, "classes.dex")
print(f"wrote {output} {os.path.getsize(output)}")
PY

if ! (
  cd "$BUILD"
  env \
      ANDROID_ROOT=run \
      ANDROID_ART_ROOT=run \
      ANDROID_I18N_ROOT=run \
      ANDROID_DATA=run/data \
      ICU_DATA=run/icu \
      WINEDEBUG="${WINEDEBUG:--all}" \
      timeout 180 wine64 ./dalvikvm.exe \
        -Xbootclasspath:run/boot.jar \
        -Xbootclasspath-locations:run/boot.jar \
        -Ximage:/nonexistent-no-boot-image \
        -XjdwpProvider:none \
        -Xint \
        -Xms2m \
        -Xmx128m \
        -cp run/w013nonmovingstressprobe.jar \
        W013NonMovingStressProbe >"$WIN_LOG" 2>&1
); then
  tail -n 200 "$WIN_LOG" >&2
  exit 1
fi

if ! env \
    LD_LIBRARY_PATH="$NATIVE_BUILD" \
    ANDROID_ROOT="$RUN" \
    ANDROID_ART_ROOT="$RUN" \
    ANDROID_I18N_ROOT="$RUN" \
    ANDROID_DATA="$LINUX_DATA" \
    ICU_DATA="$RUN/icu" \
    timeout 180 "$NATIVE_BUILD/dalvikvm" \
      -Xbootclasspath:"$RUN/boot.jar" \
      -Xbootclasspath-locations:"$RUN/boot.jar" \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -Xint \
      -Xms2m \
      -Xmx128m \
      -cp "$JAR" \
      W013NonMovingStressProbe >"$LINUX_LOG" 2>&1; then
  tail -n 200 "$LINUX_LOG" >&2
  exit 1
fi

for log in "$WIN_LOG" "$LINUX_LOG"; do
  grep -Fq 'nonmoving.total_bytes=75497472' "$log"
  grep -Fq 'nonmoving.stable=true' "$log"
  grep -Fq 'nonmoving.low=true' "$log"
  grep -Fq 'nonmoving.ok=true' "$log"
  grep -Fq 'W013NonMovingStressProbe.done=ok' "$log"
done

echo '=== Windows x64 non-moving stress ==='
grep -E '^(round=(0|11) |nonmoving\.|W013NonMovingStressProbe)' "$WIN_LOG"
echo '=== Linux non-moving stress ==='
grep -E '^(round=(0|11) |nonmoving\.|W013NonMovingStressProbe)' "$LINUX_LOG"
echo 'W013_NON_MOVING_STRESS_PASS windows_x64=ok linux=ok total_bytes=75497472'
