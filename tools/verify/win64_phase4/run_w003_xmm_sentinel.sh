#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
NATIVE_BUILD="${NATIVE_BUILD:-$REPO/build/win64_w003_xmm_sentinel}"
WIN64_TOOLCHAIN="${WIN64_TOOLCHAIN:-/home/agent/Projects/win64-dev-env/cmake/Win64LLVM.cmake}"
WINE="${WINE:-wine64}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
JAR="${JAR:-/usr/lib/jvm/java-21-openjdk-amd64/bin/jar}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
TIMEOUT="${TIMEOUT:-120}"
REPEATS="${REPEATS:-2}"

cmake -S "$REPO/tools/verify/win64_phase4/w003_xmm_sentinel" \
  -B "$NATIVE_BUILD" \
  -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$WIN64_TOOLCHAIN" \
  -DMDVM_REPO_ROOT="$REPO" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$NATIVE_BUILD" -j32

DLL="$NATIVE_BUILD/libw003xmmsentinel.dll"
EXPORTS="$(llvm-readobj --coff-exports "$DLL")"
if ! grep -qF "Name: Java_W003XmmSentinelProbe_runXmmSentinel" <<<"$EXPORTS"; then
  echo "W-003 sentinel DLL is missing the JNI export" >&2
  exit 1
fi

OBJ="$(find "$NATIVE_BUILD/CMakeFiles/w003xmmsentinel.dir" \
  -name 'w003_xmm_sentinel_x86_64.S.obj' -print -quit)"
DIS="$(llvm-objdump -dr --no-show-raw-insn "$OBJ")"
for token in \
    $'subq\t$0x88, %rsp' \
    $'movdqu\t%xmm6, 0x20(%rsp)' \
    $'movdqu\t%xmm11, 0x70(%rsp)' \
    $'IMAGE_REL_AMD64_REL32\tW003InvokeManagedCallback' \
    $'movdqu\t0x20(%rsp), %xmm6' \
    $'movdqu\t0x70(%rsp), %xmm11' \
    $'addq\t$0x88, %rsp'; do
  if ! grep -qF "$token" <<<"$DIS"; then
    echo "W-003 sentinel object is missing: $token" >&2
    exit 1
  fi
done
if ! llvm-readobj --unwind "$OBJ" | grep -qF 'W003XmmSentinelAssembly'; then
  echo "W-003 sentinel assembly is missing unwind metadata" >&2
  exit 1
fi
C_OBJ="$(find "$NATIVE_BUILD/CMakeFiles/w003xmmsentinel.dir" \
  -name 'w003_xmm_sentinel.c.obj' -print -quit)"
HELPER_DIS="$(llvm-objdump -dr --no-show-raw-insn "$C_OBJ" | \
  sed -n '/<W003InvokeManagedCallback>:/,/^$/p')"
if grep -Eq '%xmm(6|7|8|9|10|11)' <<<"$HELPER_DIS"; then
  echo "W-003 C callback unexpectedly masks the boundary with local XMM saves" >&2
  exit 1
fi
if ! grep -qF $'callq\t*0x408(%rax)' <<<"$HELPER_DIS"; then
  echo "W-003 C callback does not call the JNI CallStaticIntMethod slot" >&2
  exit 1
fi

cp -f "$DLL" "$BUILD/"
mkdir -p "$RUN"
JAVA_TMP="$(mktemp -d "${TMPDIR:-/tmp}/w003-xmm-java.XXXXXX")"
trap 'rm -rf "$JAVA_TMP"' EXIT
mkdir -p "$JAVA_TMP/classes" "$JAVA_TMP/dex"
"$JAVAC" -d "$JAVA_TMP/classes" \
  "$REPO/tools/verify/win64_phase4/src/W003XmmSentinelProbe.java"
java -cp "$R8JAR" com.android.tools.r8.D8 \
  --release --min-api 31 --output "$JAVA_TMP/dex" \
  "$JAVA_TMP/classes/W003XmmSentinelProbe.class"
"$JAR" --create --file "$RUN/w003xmmsentinelprobe.jar" \
  -C "$JAVA_TMP/dex" classes.dex

run_one() {
  local mode="$1"
  local iteration="$2"
  local log="${TMPDIR:-/tmp}/w003-xmm-${mode}-${iteration}.log"
  local -a mode_env=()
  local -a vm_args=()
  local require_compile=0

  case "$mode" in
    nterp)
      mode_env+=(ART_WIN64_JIT=0 ART_WIN64_NTERP=1)
      ;;
    switch)
      mode_env+=(ART_WIN64_JIT=0 ART_WIN64_NTERP=0)
      ;;
    jit)
      mode_env+=(ART_WIN64_JIT=1 ART_WIN64_NTERP=1)
      mode_env+=(ART_WIN64_JIT_FILTER=W003XmmSentinelProbe.managedCallback)
      mode_env+=(ART_WIN64_JIT_LOG_COMPILES=1)
      vm_args+=(-verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0)
      require_compile=1
      ;;
    *)
      echo "unknown W-003 sentinel mode: $mode" >&2
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
      ART_WIN64_QUICK_INVOKE=1 \
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
        -cp run/w003xmmsentinelprobe.jar W003XmmSentinelProbe
  ) >"$log" 2>&1; then
    echo "W-003 XMM sentinel $mode run=$iteration failed: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi

  if ! grep -Eq "W003XmmSentinelProbe mode=$mode expected=-?[0-9]+ warmChecksum=-?[0-9]+ mask=0 selfTestMask=63 iterations=128" "$log" ||
     ! grep -qF 'W003XmmSentinelProbe OK' "$log" ||
     ! grep -qF 'main end exception=0' "$log"; then
    echo "W-003 XMM sentinel $mode run=$iteration markers failed: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi
  if [[ $require_compile -eq 1 ]] &&
     ! grep -qF 'success=1 method=int W003XmmSentinelProbe.managedCallback(' "$log"; then
    echo "W-003 XMM sentinel JIT compilation marker missing: $log" >&2
    tail -120 "$log" >&2
    return 1
  fi
  printf 'W-003 XMM sentinel %s run=%s PASS\n' "$mode" "$iteration"
}

for mode in nterp switch jit; do
  for iteration in $(seq 1 "$REPEATS"); do
    run_one "$mode" "$iteration"
  done
done

printf 'W-003 XMM sentinel acceptance: nterp/switch/JIT, %s repeat(s): PASS\n' "$REPEATS"
