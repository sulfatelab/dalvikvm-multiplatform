#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-120}"

cmake --build "$BUILD" --target jitunwindlifecycleprobe -j"${JOBS:-32}"

if [[ ! -f "$BUILD/art.dll" || ! -f "$RUN/art.dll" ]] ||
   ! cmp -s "$BUILD/art.dll" "$RUN/art.dll"; then
  printf 'built and staged art.dll must exist and match after the JIT lifecycle build\n' >&2
  exit 1
fi

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/jit-unwind-lifecycle.XXXXXX")"
trap 'rm -rf "$temp_dir"' EXIT
mkdir -p "$temp_dir/classes" "$temp_dir/dex"
"$JAVAC" -d "$temp_dir/classes" \
  "$REPO/tests/cases/jit-unwind-lifecycle/JitUnwindLifecycleProbe.java"
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$temp_dir/dex" \
  "$temp_dir/classes/JitUnwindLifecycleProbe.class"
"$JAR" --create --file "$RUN/jitunwindlifecycleprobe.jar" \
  -C "$temp_dir/dex" classes.dex

run_one() {
  local mode="$1"
  local log="${TMPDIR:-/tmp}/win32-jit-unwind-lifecycle-${mode}.log"
  local rc
  local collection_count

  if (
    cd "$BUILD"
    export ART_WINDOWS_X64_JIT_FILTER=JitUnwindLifecycleProbe
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -Xjitwarmupthreshold:1 -Xjitthreshold:1 \
      -Xjitinitialsize:4M -Xjitmaxsize:16M \
      -XX:DumpJITInfoOnShutdown \
      -Xms64m -Xmx512m \
      '-Djava.library.path=.' \
      -cp "$RUN/jitunwindlifecycleprobe.jar" JitUnwindLifecycleProbe
  ) >"$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  collection_count="$(sed -n \
    's/.*Total number of JIT code cache collections: \([0-9][0-9]*\).*/\1/p' \
    "$log" | tail -1)"
  if [[ $rc -ne 0 ]] ||
     ! grep -qF 'invalidated=present collected=absent reused=yes recompiled=present' "$log" ||
     ! grep -qF 'JitUnwindLifecycleProbe OK result=' "$log" ||
     [[ -z "$collection_count" || "$collection_count" -lt 1 ]] ||
     grep -qE 'ART Win32 (VEH|UEF)|minidump written|Check failed|Fatal signal' "$log"; then
    printf 'Windows x64 JIT unwind lifecycle %s FAIL exit=%s collections=%s log=%s\n' \
      "$mode" "$rc" "${collection_count:-missing}" "$log" >&2
    tail -240 "$log" >&2
    return 1
  fi

  grep -qF 'Windows x64 JIT dual-view (J-2) created' "$log"

  printf 'Windows x64 JIT unwind lifecycle %s PASS collections=%s\n' \
    "$mode" "$collection_count"
}

run_one default
printf 'Windows x64 JIT unwind lifecycle acceptance: default J-2 PASS\n'
