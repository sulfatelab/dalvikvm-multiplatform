#!/usr/bin/env bash
# Build, verify, and package the W-024 InterpreterJni tripwire for Windows 10.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
OUT="${1:-$REPO/dist/win64_w024_tripwire_host}"
WIN64_TOOLCHAIN="${WIN64_TOOLCHAIN:-/home/agent/Projects/win64-dev-env/cmake/Win64LLVM.cmake}"
JOBS="${JOBS:-$(nproc)}"
WINEDEBUG="${WINEDEBUG:--all}"

configure_tripwire() {
  local enabled="$1"
  cmake -S "$REPO/tools/verify/win64_phase1" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$WIN64_TOOLCHAIN" \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DMDVM_WIN64_INTERPRETER_JNI_TRIPWIRE="$enabled"
}

restore_needed=1
restore_product_build() {
  configure_tripwire OFF
  cmake --build "$BUILD" --target art dalvikvm openjdkjvmti -j"$JOBS"
}
cleanup() {
  if [[ "$restore_needed" == 1 ]]; then
    echo "restoring product build after interrupted tripwire packaging" >&2
    restore_product_build || true
  fi
}
trap cleanup EXIT

configure_tripwire ON
cmake --build "$BUILD" --target art dalvikvm openjdkjvmti -j"$JOBS"

# Generate all probe artifacts and prove the tripwire build under Wine before
# asking a Windows host to run it.
REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_math_critical_probe.sh"
REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_critical_native_probe.sh"
WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_native_abi_probe.sh"
REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_jvmti_force_probe.sh"

required=(
  "$BUILD/dalvikvm.exe"
  "$BUILD/art.dll"
  "$BUILD/openjdkjvmti.dll"
  "$BUILD/libcriticalnativeprobe.dll"
  "$BUILD/libnativeabiprobe.dll"
  "$BUILD/libjvmtiforceprobe.dll"
  "$BUILD/run/boot.jar"
  "$BUILD/run/mathcriticalprobe.jar"
  "$BUILD/run/criticalnativeprobe.jar"
  "$BUILD/run/fastnativeabiprobe.jar"
  "$BUILD/run/jvmtiforceprobe.jar"
)
for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing W-024 package artifact: $path" >&2
    exit 1
  fi
done

rm -rf "$OUT"
mkdir -p "$OUT/run/data" "$OUT/run/icu" "$OUT/scripts" "$OUT/logs"

cp -a "$BUILD/dalvikvm.exe" "$OUT/"
for name in art.dll artpalette.dll base.dll c++.dll log.dll lzma.dll \
    nativebridge.dll nativehelper.dll nativeloader.dll procinfo.dll \
    sigchain.dll ziparchive.dll openjdkjvmti.dll; do
  if [[ -f "$BUILD/$name" ]]; then
    cp -a "$BUILD/$name" "$OUT/"
  else
    echo "missing runtime DLL: $BUILD/$name" >&2
    exit 1
  fi
done

bash "$REPO/tools/win64/stage_native_modules.sh" "$OUT" \
  "${MDVM_HYBRID_BUILD:-$REPO/build/win64_libcore_icu}" "$BUILD"
bash "$REPO/tools/win64/stage_run_assets.sh" "$OUT" "$BUILD"

for jar in mathcriticalprobe.jar criticalnativeprobe.jar \
    fastnativeabiprobe.jar jvmtiforceprobe.jar; do
  cp -a "$BUILD/run/$jar" "$OUT/run/"
done
for dll in criticalnativeprobe.dll libcriticalnativeprobe.dll \
    libnativeabiprobe.dll jvmtiforceprobe.dll libjvmtiforceprobe.dll; do
  if [[ -f "$BUILD/$dll" ]]; then
    cp -a "$BUILD/$dll" "$OUT/"
  fi
done

write_case() {
  local name="$1"
  local dual="$2"
  local extra="$3"
  local jar="$4"
  local main="$5"
  local marker1="$6"
  local marker2="${7:-}"
  local native_gate="${8:-0}"
  local jit_filter="${9:-}"
  local script="$OUT/scripts/${name}.cmd"
  cat > "$script" <<CMD
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
set ANDROID_ROOT=run
set ANDROID_ART_ROOT=run
set ANDROID_I18N_ROOT=run
set ANDROID_DATA=run\data
set ICU_DATA=run\icu
set ART_WIN64_JIT_DUAL=${dual}
set ART_WIN64_JIT_NATIVE=${native_gate}
set ART_WIN64_JIT_FILTER=${jit_filter}
if not exist logs mkdir logs
del /q critical-native-instrumentation.trace native-abi-instrumentation.trace 2>nul
echo === ${name} ===> logs\\${name}.log
dalvikvm.exe -Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -Xno-sig-chain -XjdwpProvider:none -Xms64m -Xmx512m ${extra} -cp run\\${jar} ${main} >> logs\\${name}.log 2>&1
set RC=!ERRORLEVEL!
echo exit=!RC!>> logs\\${name}.log
type logs\\${name}.log
if not !RC!==0 exit /b !RC!
findstr /C:"${marker1}" logs\\${name}.log >nul
if errorlevel 1 exit /b 1
CMD
  if [[ -n "$marker2" ]]; then
    cat >> "$script" <<CMD
findstr /C:"${marker2}" logs\\${name}.log >nul
if errorlevel 1 exit /b 1
CMD
  fi
  cat >> "$script" <<'CMD'
findstr /C:"Win64 InterpreterJni tripwire" logs\%~n0.log >nul
if not errorlevel 1 exit /b 1
findstr /C:"main end exception=0" logs\%~n0.log >nul
if errorlevel 1 exit /b 1
echo PASS %~n0
exit /b 0
CMD

  if grep -Fq '${' "$script" ||
      ! grep -Fq 'cd /d "%~dp0\.."' "$script" ||
      ! grep -Fq "logs\\${name}.log" "$script" ||
      ! grep -Fq "run\\${jar}" "$script"; then
    echo "invalid generated Windows case script: $script" >&2
    sed -n '1,80p' "$script" >&2
    exit 1
  fi
}

write_case math_dual 1 \
  "-Xjitthreshold:0" \
  mathcriticalprobe.jar MathCriticalProbe \
  "MathCriticalProbe OK" "" 1 MathCriticalProbe
write_case math_j1 0 \
  "-Xjitthreshold:0" \
  mathcriticalprobe.jar MathCriticalProbe \
  "MathCriticalProbe OK" "" 1 MathCriticalProbe
write_case math_xint 1 \
  "-Xint" \
  mathcriticalprobe.jar MathCriticalProbe \
  "MathCriticalProbe OK" "" 1 MathCriticalProbe
write_case critical_dual 1 \
  "-Xjitthreshold:0 -Dcritical.load=library -Dcritical.instrumentation=1 -Djava.library.path=." \
  criticalnativeprobe.jar CriticalNativeProbe \
  "CriticalNativeProbe instrumentation OK" \
  "CriticalNativeDlsymProbe postTracing OK" 0
write_case critical_j1 0 \
  "-Xjitthreshold:0 -Dcritical.load=library -Dcritical.instrumentation=1 -Djava.library.path=." \
  criticalnativeprobe.jar CriticalNativeProbe \
  "CriticalNativeProbe instrumentation OK" \
  "CriticalNativeDlsymProbe postTracing OK" 0
write_case native_abi_dual 1 \
  "-Xjitthreshold:0 -Dnative.abi.instrumentation=1 -Djava.library.path=." \
  fastnativeabiprobe.jar FastNativeAbiProbe \
  "FastNativeAbiProbe OK" \
  "FastNativeAbiProbe tracingMode before=0" 1 FastNativeAbiProbe
write_case native_abi_j1 0 \
  "-Xjitthreshold:0 -Dnative.abi.instrumentation=1 -Djava.library.path=." \
  fastnativeabiprobe.jar FastNativeAbiProbe \
  "FastNativeAbiProbe OK" \
  "FastNativeAbiProbe tracingMode before=0" 1 FastNativeAbiProbe
write_case jvmti_dual 1 \
  "-Xplugin:openjdkjvmti.dll -agentpath:libjvmtiforceprobe.dll -Xjitthreshold:0 -Djava.library.path=." \
  jvmtiforceprobe.jar JvmtiForceProbe \
  "JvmtiForceProbe OK" \
  "JvmtiForceProbe after normalRegistered=137.75" 1 JvmtiForceProbe
write_case jvmti_j1 0 \
  "-Xplugin:openjdkjvmti.dll -agentpath:libjvmtiforceprobe.dll -Xjitthreshold:0 -Djava.library.path=." \
  jvmtiforceprobe.jar JvmtiForceProbe \
  "JvmtiForceProbe OK" \
  "JvmtiForceProbe after normalRegistered=137.75" 1 JvmtiForceProbe

cat > "$OUT/scripts/run_all_w024.cmd" <<'CMD'
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
if not exist logs mkdir logs
echo Win64 W-024 InterpreterJni tripwire %DATE% %TIME%> logs\RESULT_W024.txt
set FAIL=0
for %%S in (
  math_dual math_j1 math_xint
  critical_dual critical_j1
  native_abi_dual native_abi_j1
  jvmti_dual jvmti_j1
) do (
  echo ==== %%S ====
  call scripts\%%S.cmd
  set RC=!ERRORLEVEL!
  echo %%S exit=!RC!>> logs\RESULT_W024.txt
  if not !RC!==0 set FAIL=1
)
if !FAIL!==0 (
  echo OVERALL PASS>> logs\RESULT_W024.txt
  echo OVERALL PASS
  exit /b 0
)
echo OVERALL FAIL>> logs\RESULT_W024.txt
echo OVERALL FAIL
exit /b 1
CMD

if grep -R -Fq '${' "$OUT/scripts" ||
    ! grep -Fq 'cd /d "%~dp0\.."' "$OUT/scripts/run_all_w024.cmd"; then
  echo "invalid generated Windows driver scripts" >&2
  exit 1
fi

cat > "$OUT/README_W024.md" <<'MD'
# Win64 W-024 InterpreterJni tripwire package

This package contains an `art.dll` built with
`MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE=ON`. It aborts if a runtime-started native
method reaches either legacy `InterpreterJni` fallback call site.

Run on native Windows 10 version 1803 or later, not Wine or WSL:

```bat
cd <package-directory>
scripts\run_all_w024.cmd
```

Pass criteria:

- every case exits zero;
- `logs\RESULT_W024.txt` ends with `OVERALL PASS`;
- no log contains `Win64 InterpreterJni tripwire`;
- Math passes dual-view, J-1, and `-Xint`;
- direct/unresolved CriticalNative, method tracing, compiled normal/FastNative,
  and JVMTI forced interpretation pass in both memory modes.

Return the complete `logs` directory for review. Do not use this tripwire
`art.dll` as a product binary. The complete native-host procedure is included
as `W024_HOST_CHECKLIST.md`.
MD

cp -a "$REPO/tools/verify/win64_phase4/W024_HOST_CHECKLIST.md" "$OUT/"

{
  echo "created=$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "parent_commit=$(git -C "$REPO" rev-parse HEAD)"
  echo "art_commit=$(git -C "$REPO/vendor/art" rev-parse HEAD)"
  echo "boot_sha256=$(sha256sum "$BUILD/run/boot.jar" | awk '{print $1}')"
  echo "boot_size=$(stat -c %s "$BUILD/run/boot.jar")"
  echo "tripwire=MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE=ON"
} > "$OUT/BUILD_INFO.txt"

OUT_FOR_MANIFEST="$OUT" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OUT_FOR_MANIFEST"])
files = []
for path in sorted(root.rglob("*")):
    if path.is_file() and "logs" not in path.parts:
        files.append({
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
(root / "MANIFEST.json").write_text(
    json.dumps({"count": len(files), "files": files}, indent=2) + "\n")
PY

OUT_FOR_ZIP="$OUT" python3 - <<'PY'
import os
import zipfile
from pathlib import Path

root = Path(os.environ["OUT_FOR_ZIP"])
archive = root.parent / (root.name + ".zip")
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in root.rglob("*"):
        if path.is_file() and "logs" not in path.parts:
            output.write(path, path.relative_to(root.parent))
print(f"package={root}")
print(f"zip={archive}")
PY

# Leave the shared build directory in product-default mode.
restore_product_build
restore_needed=0
REPEATS=1 WINEDEBUG="$WINEDEBUG" \
  "$REPO/tools/verify/win64_phase4/run_math_critical_probe.sh"

trap - EXIT
echo "W-024 tripwire package ready: $OUT"
