#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PRODUCT_BUILD="${PRODUCT_BUILD:-$REPO/build/windows_x64_phase1}"
BUILD="${BUILD:-$REPO/build/windows_x64_fs1_release}"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/windows_x64_fs1_stack_high_water_probe}"
WINDOWS_X64_TOOLCHAIN="${WINDOWS_X64_TOOLCHAIN:-/home/agent/Projects/windows_x64-dev-env/cmake/WindowsX64LLVM.cmake}"
LIBCORE_BUILD="${LIBCORE_BUILD:-$REPO/build/windows_x64_libcore_icu}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-180}"
JOBS="${JOBS:-32}"
LOG_DIR="${LOG_DIR:-$BUILD/fs1_logs}"
ART_RESERVE=8192
if [[ "$BUILD_TYPE" == "Debug" ]]; then
  ART_RESERVE=40960
fi

cmake -S "$REPO/tools/verify/windows_x64_phase1" \
  -B "$PRODUCT_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_TOOLCHAIN" \
  -DCMAKE_BUILD_TYPE=Release \
  -DMDVM_FS1_STACK_HIGH_WATER=OFF
cmake --build "$PRODUCT_BUILD" --target art dalvikvm -j"$JOBS"

cmake -S "$REPO/tools/verify/windows_x64_phase1" \
  -B "$BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_TOOLCHAIN" \
  -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
  -DMDVM_FS1_STACK_HIGH_WATER=ON
cmake --build "$BUILD" --target art dalvikvm -j"$JOBS"

python3 "$REPO/tests/support/windows/check_win32_explicit_stack_checks.py" \
  --repo "$REPO" --win-build "$PRODUCT_BUILD"
python3 "$REPO/tests/support/windows/fs1_stack_high_water_structure.py" \
  --repo "$REPO" --product-build "$PRODUCT_BUILD" --probe-build "$BUILD"

cmake -S "$REPO/tools/verify/windows_x64_phase4/fs1_stack_high_water" \
  -B "$NATIVE_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
cmake --build "$NATIVE_BUILD" -j"$JOBS"

mkdir -p "$BUILD/run" "$BUILD/run/crash" "$LOG_DIR"
find "$PRODUCT_BUILD" -maxdepth 1 -type f -name '*.dll' ! -name 'art.dll' \
  -exec cp -f {} "$BUILD/" \;
bash "$REPO/tools/windows_x64/stage_run_assets.sh" "$BUILD" "$PRODUCT_BUILD"
bash "$REPO/tools/windows_x64/stage_native_modules.sh" \
  "$BUILD" "$LIBCORE_BUILD" "$PRODUCT_BUILD"
if [[ "$BUILD_TYPE" == "Debug" ]]; then
  # ART follows its standard debug runtime naming convention for this one
  # core-native module; the staged module is ABI-identical and product-named.
  cp -f "$BUILD/libopenjdk.dll" "$BUILD/libopenjdkd.dll"
fi
cp -f "$NATIVE_BUILD/libfs1stackhighwater.dll" "$BUILD/"

JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/fs1-stack-high-water-java.XXXXXX")"
trap 'rm -rf "$JAVA_TMP"' EXIT
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex"
"$JAVAC" -d "$JAVA_TMP/classes" \
  "$REPO/tests/cases/stack-high-water/FS1StackHighWaterProbe.java"
java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 \
  -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" \
  "$JAVA_TMP/classes/FS1StackHighWaterProbe.class"
"$JAR" --create --file "$BUILD/run/fs1stackhighwaterprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

snapshot_dumps() {
  find "$BUILD/run/crash" -maxdepth 1 -type f -name '*.dmp' \
    -printf '%f %s %T@\n' | sort
}

before_dumps="$(snapshot_dumps)"
RUN_ROOT="$BUILD/run"

run_one() {
  local mode="$1"
  local log="$LOG_DIR/${mode}.log"
  local -a mode_env=()
  local -a vm_args=(-Xusejit:false)
  local -a build_vm_args=()

  if [[ "$BUILD_TYPE" == "Debug" ]]; then
    # A Debug compiled recursion can stay outside a safepoint for longer than
    # ART's two-second default under Wine. Keep unrelated suspend-all work from
    # turning the stack-overflow probe into a timing failure.
    build_vm_args+=(-XX:ThreadSuspendTimeout=30000)
  fi

  case "$mode" in
    switch)
      mode_env+=(ART_WINDOWS_X64_JIT=0 ART_WINDOWS_X64_NTERP=0)
      ;;
    nterp)
      mode_env+=(ART_WINDOWS_X64_JIT=0 ART_WINDOWS_X64_NTERP=1)
      ;;
    jit)
      mode_env+=(ART_WINDOWS_X64_JIT=1 ART_WINDOWS_X64_NTERP=1)
      mode_env+=(ART_WINDOWS_X64_JIT_FILTER=FS1StackHighWaterProbe)
      mode_env+=(ART_WINDOWS_X64_JIT_LOG_COMPILES=1)
      vm_args=(-verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0)
      ;;
    *)
      echo "unknown FS-1 mode: $mode" >&2
      return 2
      ;;
  esac

  if ! (
    cd "$BUILD"
    env \
      ANDROID_ROOT="$RUN_ROOT" \
      ANDROID_ART_ROOT="$RUN_ROOT" \
      ANDROID_I18N_ROOT="$RUN_ROOT" \
      ANDROID_DATA="$RUN_ROOT/data" \
      ICU_DATA="$RUN_ROOT/icu" \
      WINEDEBUG="${WINEDEBUG:--all}" \
      "${mode_env[@]}" \
      timeout -k 1 "$TIMEOUT" "$WINE" ./dalvikvm.exe \
        "-Xbootclasspath:$RUN_ROOT/boot.jar" \
        "-Xbootclasspath-locations:$RUN_ROOT/boot.jar" \
        -Ximage:/nonexistent-no-boot-image \
        -XjdwpProvider:none \
        -Xms64m -Xmx512m \
        "${build_vm_args[@]}" \
        "${vm_args[@]}" \
        '-Djava.library.path=.' \
        -cp "$RUN_ROOT/fs1stackhighwaterprobe.jar" FS1StackHighWaterProbe "$mode"
  ) >"$log" 2>&1; then
    echo "FS-1 $BUILD_TYPE $mode execution failed: $log" >&2
    tail -180 "$log" >&2
    return 1
  fi

  python3 "$REPO/tests/support/windows/fs1_stack_high_water_check.py" \
    --log "$log" --mode "$mode" \
    --art-reserve "$ART_RESERVE"
}

for mode in switch nterp jit; do
  run_one "$mode"
done

after_dumps="$(snapshot_dumps)"
if [[ "$after_dumps" != "$before_dumps" ]]; then
  echo "FS-1 handled overflows changed crash-dump state" >&2
  diff -u <(printf '%s\n' "$before_dumps") <(printf '%s\n' "$after_dumps") >&2 || true
  exit 1
fi

printf 'FS-1 %s stack high-water gate: switch/nterp/JIT, four records each, no dumps: PASS\n' \
  "$BUILD_TYPE"
