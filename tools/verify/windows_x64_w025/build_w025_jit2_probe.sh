#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
SOURCE="$REPO/tests/cases/jit-mapping/W025JitMappingProbe.java"

cmake --build "$BUILD" --target \
  w025jitmappingprobe \
  windows_x64_w025_section_policy_probe \
  windows_x64_w025_policy_launcher \
  -j"${JOBS:-16}"

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/w025-jit2-build.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT
mkdir -p "$temp_dir/classes" "$temp_dir/dex"
"$JAVAC" -d "$temp_dir/classes" "$SOURCE"
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$temp_dir/dex" \
  "$temp_dir/classes/W025JitMappingProbe.class"
"$JAR" --create --file "$BUILD/run/w025jitmappingprobe.jar" \
  -C "$temp_dir/dex" classes.dex

cp -a "$BUILD/libw025jitmappingprobe.dll" "$BUILD/run/"
printf 'W025_JIT2_BUILD_PASS jar=%s dll=%s\n' \
  "$BUILD/run/w025jitmappingprobe.jar" "$BUILD/libw025jitmappingprobe.dll"
