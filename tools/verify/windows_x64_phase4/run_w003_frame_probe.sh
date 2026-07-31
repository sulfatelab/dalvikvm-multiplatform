#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PRODUCT_BUILD="${PRODUCT_BUILD:-$REPO/build/windows_x64_phase1}"
BUILD="${BUILD:-$REPO/build/windows_x64_w003_frames}"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/windows_x64_w003_frame_probe}"
WINDOWS_X64_TOOLCHAIN="${WINDOWS_X64_TOOLCHAIN:-/home/agent/Projects/windows_x64-dev-env/cmake/WindowsX64LLVM.cmake}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-180}"
REPEATS="${REPEATS:-1}"

cmake -S "$REPO/tools/verify/windows_x64_phase1" \
  -B "$BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_TOOLCHAIN" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DMDVM_W003_FRAME_PROBE=ON
cmake --build "$BUILD" --target art dalvikvm -j32

PRODUCT_EXPORTS="$(llvm-readobj --coff-exports "$PRODUCT_BUILD/art.dll")"
PROBE_EXPORTS="$(llvm-readobj --coff-exports "$BUILD/art.dll")"
for symbol in art_w003_frame_probe_reset art_w003_frame_probe_snapshot; do
  if grep -qF "Name: $symbol" <<<"$PRODUCT_EXPORTS"; then
    echo "product art.dll unexpectedly exports $symbol" >&2
    exit 1
  fi
  if ! grep -qF "Name: $symbol" <<<"$PROBE_EXPORTS"; then
    echo "instrumented art.dll is missing $symbol" >&2
    exit 1
  fi
done

PROBE_OBJ="$(find "$BUILD/CMakeFiles/art.dir" \
  -name 'quick_entrypoints_x86_64.S.obj' -print -quit)"
PRODUCT_OBJ="$(find "$PRODUCT_BUILD/CMakeFiles/art.dir" \
  -name 'quick_entrypoints_x86_64.S.obj' -print -quit)"
PROBE_SYMBOLS="$(llvm-readobj --symbols "$PROBE_OBJ")"
PRODUCT_SYMBOLS="$(llvm-readobj --symbols "$PRODUCT_OBJ")"
for symbol in \
    art_w003_frame_probe_refs_only \
    art_w003_frame_probe_refs_and_args \
    art_w003_frame_probe_all_callee_saves \
    art_w003_frame_probe_everything; do
  if ! grep -qF "Name: $symbol" <<<"$PROBE_SYMBOLS"; then
    echo "instrumented quick object is missing $symbol" >&2
    exit 1
  fi
  if grep -qF "Name: $symbol" <<<"$PRODUCT_SYMBOLS"; then
    echo "product quick object unexpectedly contains $symbol" >&2
    exit 1
  fi
done

cmake -S "$REPO/tools/verify/windows_x64_phase4/w003_frame_probe" \
  -B "$NATIVE_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$NATIVE_BUILD" -j32

mkdir -p "$BUILD/run"
find "$PRODUCT_BUILD" -maxdepth 1 -type f -name '*.dll' ! -name 'art.dll' \
  -exec cp -f {} "$BUILD/" \;
bash "$REPO/tools/windows_x64/stage_run_assets.sh" "$BUILD" "$PRODUCT_BUILD"
bash "$REPO/tools/windows_x64/stage_native_modules.sh" \
  "$BUILD" "$REPO/build/windows_x64_libcore_icu" "$PRODUCT_BUILD"
cp -f "$NATIVE_BUILD/libw003frameprobe.dll" "$BUILD/"

JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/w003-frame-java.XXXXXX")"
trap 'rm -rf "$JAVA_TMP"' EXIT
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex"
"$JAVAC" -d "$JAVA_TMP/classes" \
  "$REPO/tests/cases/w003-frame-probe/W003FrameProbe.java"
java -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" \
  "$JAVA_TMP/classes/W003FrameProbe.class" \
  "$JAVA_TMP/classes/W003FrameProbe\$1.class"
"$JAR" --create --file "$BUILD/run/w003frameprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

run_one() {
  local mode="$1"
  local iteration="$2"
  local log="${TMPDIR:-/tmp}/w003-frame-${mode}-${iteration}.log"
  local -a mode_env=()
  local -a vm_args=()

  case "$mode" in
    int)
      mode_env+=(ART_WINDOWS_X64_JIT=0 ART_WINDOWS_X64_NTERP=0)
      vm_args+=(-Xint)
      ;;
    switch)
      mode_env+=(ART_WINDOWS_X64_JIT=0 ART_WINDOWS_X64_NTERP=0)
      ;;
    nterp)
      mode_env+=(ART_WINDOWS_X64_JIT=0 ART_WINDOWS_X64_NTERP=1)
      ;;
    jit)
      mode_env+=(ART_WINDOWS_X64_JIT=1 ART_WINDOWS_X64_NTERP=1)
      mode_env+=(ART_WINDOWS_X64_JIT_FILTER=W003FrameProbe)
      mode_env+=(ART_WINDOWS_X64_JIT_LOG_COMPILES=1)
      vm_args+=(-verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0)
      ;;
    *)
      echo "unknown W-003 frame mode: $mode" >&2
      return 2
      ;;
  esac

  if ! (
    cd "$BUILD"
    env \
      ANDROID_ROOT=run \
      ANDROID_ART_ROOT=run \
      ANDROID_I18N_ROOT=run \
      ANDROID_DATA=run/data \
      ICU_DATA=run/icu \
      WINEDEBUG="${WINEDEBUG:--all}" \
      ART_WINDOWS_X64_QUICK_INVOKE=1 \
      "${mode_env[@]}" \
      timeout -k 1 "$TIMEOUT" "$WINE" ./dalvikvm.exe \
        -Xbootclasspath:run/boot.jar \
        -Xbootclasspath-locations:run/boot.jar \
        -Ximage:/nonexistent-no-boot-image \
        -XjdwpProvider:none \
        -Xms64m -Xmx512m \
        "${vm_args[@]}" \
        "-Dw003.mode=$mode" \
        '-Djava.library.path=.' \
        -cp run/w003frameprobe.jar W003FrameProbe
  ) >"$log" 2>&1; then
    echo "W-003 frame probe $mode run=$iteration failed: $log" >&2
    tail -160 "$log" >&2
    return 1
  fi

  for phase in refs_only refs_and_args all_callee_saves everything; do
    if ! grep -Eq "W003FrameProbe mode=$mode phase=$phase counts=refs_only:[0-9]+,refs_and_args:[0-9]+,all_callee_saves:[0-9]+,everything:[0-9]+ checksum=-?[0-9]+" "$log"; then
      echo "W-003 frame probe $mode missing phase $phase: $log" >&2
      tail -160 "$log" >&2
      return 1
    fi
  done
  if ! grep -Eq "W003FrameProbe OK mode=$mode checksum=-?[0-9]+" "$log" ||
     ! grep -qF 'main end exception=0' "$log"; then
    echo "W-003 frame probe $mode completion markers failed: $log" >&2
    tail -160 "$log" >&2
    return 1
  fi

  phase_counter() {
    local phase="$1"
    local family="$2"
    local line
    line="$(grep -F "W003FrameProbe mode=$mode phase=$phase counts=" "$log" | tail -n 1)"
    sed -E "s/.*${family}:([0-9]+).*/\1/" <<<"$line"
  }

  require_positive_counter() {
    local phase="$1"
    local family="$2"
    local value
    value="$(phase_counter "$phase" "$family")"
    if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value == 0 )); then
      echo "W-003 frame probe $mode did not reach $family during $phase: $log" >&2
      tail -160 "$log" >&2
      return 1
    fi
  }

  require_positive_counter refs_and_args refs_and_args
  require_positive_counter everything everything
  if [[ "$mode" == nterp || "$mode" == jit ]]; then
    require_positive_counter refs_only refs_only
    require_positive_counter all_callee_saves all_callee_saves
  fi
  printf 'W-003 frame probe %s run=%s PASS log=%s\n' "$mode" "$iteration" "$log"
}

for mode in int switch nterp jit; do
  for iteration in $(seq 1 "$REPEATS"); do
    run_one "$mode" "$iteration"
  done
done

printf 'W-003 four-family functional matrix: int/switch/nterp/JIT, %s repeat(s): PASS\n' \
  "$REPEATS"
