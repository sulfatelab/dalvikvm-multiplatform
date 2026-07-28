#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
RUN="$BUILD/run"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/windows_x64_w002_attach_probe}"
WINDOWS_X64_TOOLCHAIN="${WINDOWS_X64_TOOLCHAIN:-/home/agent/Projects/windows_x64-dev-env/cmake/WindowsX64LLVM.cmake}"
WINE="${WINE:-wine64}"
REPEATS="${REPEATS:-2}"
TIMEOUT="${TIMEOUT:-120}"

bash "$REPO/tools/verify/windows_x64_phase4/build_one.sh" W002AttachProbe
cmake -S "$REPO/tools/verify/windows_x64_phase4/w002_attach" \
  -B "$NATIVE_BUILD" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WINDOWS_X64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$NATIVE_BUILD" -j32
cp -f "$NATIVE_BUILD/libw002attachprobe.dll" "$BUILD/"

EXPORTS="$(llvm-readobj --coff-exports "$BUILD/libw002attachprobe.dll")"
for symbol in JNI_OnLoad Java_W002AttachProbe_runAttachMatrix; do
  if ! grep -qF "Name: $symbol" <<< "$EXPORTS"; then
    printf 'W-002 attach DLL does not export %s\n' "$symbol" >&2
    exit 1
  fi
done

run_one() {
  local memory_mode="$1"
  local dual="$2"
  local interpreter_mode="$3"
  local iteration="$4"
  local log="${TMPDIR:-/tmp}/w002-attach-${memory_mode}-${interpreter_mode}-${iteration}.log"
  local rc

  if (
    cd "$BUILD"
    if [[ "$interpreter_mode" == "switch" ]]; then
      export ART_WINDOWS_X64_NTERP=0
    else
      unset ART_WINDOWS_X64_NTERP
    fi
    export ART_WINDOWS_X64_JIT_DUAL="$dual"
    export ART_WINDOWS_X64_JIT_FILTER="W002AttachProbe.attachedCallback"
    export ART_WINDOWS_X64_JIT_LOG_COMPILES=1
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      -Xjitthreshold:0 \
      '-Djava.library.path=.' \
      -cp "$RUN/w002attachprobe.jar" W002AttachProbe
  ) > "$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  if [[ $rc -ne 0 ]] ||
     ! grep -qF "W002AttachProbe OK completed=16" "$log" ||
     ! grep -qF "Windows x64 CompileMethod done success=1 method=long W002AttachProbe.attachedCallback(boolean, int)" "$log" ||
     ! grep -qF "main end exception=0" "$log"; then
    printf 'W-002 attach %s/%s run=%s FAIL exit=%s log=%s\n' \
      "$memory_mode" "$interpreter_mode" "$iteration" "$rc" "$log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  printf 'W-002 attach %s/%s run=%s PASS\n' \
    "$memory_mode" "$interpreter_mode" "$iteration"
}

for memory_and_dual in "dual:1" "j1:0"; do
  memory_mode="${memory_and_dual%%:*}"
  dual="${memory_and_dual##*:}"
  for interpreter_mode in default switch; do
    for iteration in $(seq 1 "$REPEATS"); do
      run_one "$memory_mode" "$dual" "$interpreter_mode" "$iteration"
    done
  done
done

printf 'W-002 attach acceptance: regular and daemon attach, dual and J-1, default nterp and switch, %s repeat(s): PASS\n' \
  "$REPEATS"
