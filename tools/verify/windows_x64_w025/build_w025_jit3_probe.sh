#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
RUN="$BUILD/run"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
SOURCE="$REPO/tests/cases/jit-lifecycle-stress/W025JitLifecycleStressProbe.java"

cmake --build "$BUILD" --target w025jitlifecyclestressprobe -j"${JOBS:-32}"

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/w025-jit3-build.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT
mkdir -p "$temp_dir/classes" "$temp_dir/dex" "$RUN"
"$JAVAC" -d "$temp_dir/classes" "$SOURCE"
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$temp_dir/dex" \
  "$temp_dir/classes/W025JitLifecycleStressProbe.class"
"$JAR" --create --file "$RUN/w025jitlifecyclestressprobe.jar" \
  -C "$temp_dir/dex" classes.dex

printf 'W025_JIT3_BUILD_PASS jar=%s dll=%s\n' \
  "$RUN/w025jitlifecyclestressprobe.jar" \
  "$BUILD/libw025jitlifecyclestressprobe.dll"
