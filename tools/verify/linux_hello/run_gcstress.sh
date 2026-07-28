#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
DALVIKVM="$REPO/build/native/dalvikvm"
RUN="$REPO/build/windows_x64_phase1/run"
JAR="$RUN/gcstressprobe.jar"
DATA="/tmp/mdvm_linux_w013_data"
LOG="$(mktemp /tmp/mdvm_linux_w013_gcstress.XXXXXX.log)"
trap 'rm -f "$LOG"' EXIT

for required in "$DALVIKVM" "$RUN/boot.jar" "$JAR"; do
  if [[ ! -f "$required" ]]; then
    echo "L-005 GCStress FAIL: missing $required" >&2
    exit 1
  fi
done

mkdir -p "$DATA"
env \
  LD_LIBRARY_PATH="$REPO/build/native" \
  ANDROID_ROOT="$RUN" \
  ANDROID_ART_ROOT="$RUN" \
  ANDROID_I18N_ROOT="$RUN" \
  ANDROID_DATA="$DATA" \
  ICU_DATA="$RUN/icu" \
  timeout 180 "$DALVIKVM" \
    -Xbootclasspath:"$RUN/boot.jar" \
    -Xbootclasspath-locations:"$RUN/boot.jar" \
    -Ximage:/nonexistent-no-boot-image \
    -XjdwpProvider:none \
    -Xint \
    -Xms64m \
    -Xmx512m \
    -cp "$JAR" \
    GcStressProbe 2>&1 | tee "$LOG"

grep -Fq 'gcstress.ok=true' "$LOG"
grep -Fq 'GcStressProbe.done=ok' "$LOG"
echo 'L-005 GCStress PASS'
