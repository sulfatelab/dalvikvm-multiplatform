#!/usr/bin/env bash
# Stage a portable Win64 ART Phase-3 smoke tree for a real Windows host.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
OUT="${1:-$REPO/dist/win64_phase3_host}"
rm -rf "$OUT"
mkdir -p "$OUT/run/data" "$OUT/run/icu" "$OUT/run/framework" "$OUT/scripts" "$OUT/logs"
cp -a "$BUILD/dalvikvm.exe" "$OUT/"
for f in art.dll artpalette.dll base.dll c++.dll log.dll lzma.dll \
         nativebridge.dll nativehelper.dll nativeloader.dll procinfo.dll \
         sigchain.dll ziparchive.dll \
         libjavacore.dll libopenjdk.dll libicu_jni.dll \
         javacore.dll openjdk.dll icu_jni.dll; do
  if [[ -f "$BUILD/$f" ]]; then cp -a "$BUILD/$f" "$OUT/"; else echo "WARN missing $f" >&2; fi
done
cp -a "$BUILD/run/boot.jar" "$OUT/run/"
for j in hello.jar goldenapp.jar probe.jar ioprobe.jar coreprobe.jar netprobe.jar \
         gcprobe.jar gcforced.jar interruptprobe.jar rtmem.jar abspathprobe.jar \
         dnsprobe.jar propsprobe.jar oserrnoprobe.jar threadstressprobe.jar throwprobe.jar gcstressprobe.jar threadheavyprobe.jar handleleakprobe.jar perfsmokeprobe.jar crashabortprobe.jar crashnativeprobe.jar; do
  [[ -f "$BUILD/run/$j" ]] && cp -a "$BUILD/run/$j" "$OUT/run/" || true
done
if [[ -d "$BUILD/run/icu" ]]; then cp -a "$BUILD/run/icu/." "$OUT/run/icu/" 2>/dev/null || true; fi

# Shared env fragment for cmd scripts
write_runner() {
  local name="$1" cp="$2" main="$3"
  cat > "$OUT/scripts/${name}.cmd" <<CMD
@echo off
setlocal
cd /d %~dp0\\..
set ANDROID_ROOT=run
set ANDROID_ART_ROOT=run
set ANDROID_I18N_ROOT=run
set ANDROID_DATA=run\\data
set ICU_DATA=run\\icu
if not exist logs mkdir logs
echo === ${name} ===> logs\\${name}.log
dalvikvm.exe -Xbootclasspath:run\\boot.jar -Xbootclasspath-locations:run\\boot.jar -Ximage:/nonexistent-no-boot-image -Xno-sig-chain -XjdwpProvider:none -Xint -Xms64m -Xmx512m -cp ${cp} ${main} >> logs\\${name}.log 2>&1
set RC=%ERRORLEVEL%
echo exit=%RC%>> logs\\${name}.log
type logs\\${name}.log
echo exit=%RC%
exit /b %RC%
CMD
}

write_runner run_hello 'run\hello.jar' Hello
write_runner run_goldenapp 'run\goldenapp.jar' GoldenApp
write_runner run_props 'run\propsprobe.jar' PropsProbe
write_runner run_rtmem 'run\rtmem.jar' RtMem
write_runner run_core 'run\coreprobe.jar' CoreProbe
write_runner run_io 'run\ioprobe.jar' IoProbe
write_runner run_net 'run\netprobe.jar' NetProbe
write_runner run_dns 'run\dnsprobe.jar' DnsProbe
write_runner run_gc 'run\gcprobe.jar' GcProbe
write_runner run_gcforced 'run\gcforced.jar' GcForced
write_runner run_interrupt 'run\interruptprobe.jar' InterruptProbe
write_runner run_oserrno 'run\oserrnoprobe.jar' OsErrnoProbe
write_runner run_threadstress 'run\threadstressprobe.jar' ThreadStressProbe
write_runner run_gcstress 'run\gcstressprobe.jar' GcStressProbe
write_runner run_threadheavy 'run\threadheavyprobe.jar' ThreadHeavyProbe
write_runner run_handleleak 'run\handleleakprobe.jar' HandleLeakProbe
write_runner run_perfsmoke 'run\perfsmokeprobe.jar' PerfSmokeProbe

# Absolute path special-case (stages C:\art_phase3)
cat > "$OUT/scripts/run_abspath.cmd" <<'CMD'
@echo off
setlocal
cd /d %~dp0\..
set ANDROID_ROOT=run
set ANDROID_ART_ROOT=run
set ANDROID_I18N_ROOT=run
set ANDROID_DATA=run\data
set ICU_DATA=run\icu
if not exist logs mkdir logs
if not exist C:\art_phase3\abs_dir mkdir C:\art_phase3\abs_dir
copy /Y run\hello.jar C:\art_phase3\abs_dir\hello.jar >nul
echo === abspath ===> logs\abspath.log
dalvikvm.exe -Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -Xno-sig-chain -XjdwpProvider:none -Xint -Xms64m -Xmx512m -cp "C:\art_phase3\abs_dir\hello.jar;run\abspathprobe.jar" AbsPathProbe >> logs\abspath.log 2>&1
set RC=%ERRORLEVEL%
echo exit=%RC%>> logs\abspath.log
type logs\abspath.log
echo exit=%RC%
exit /b %RC%
CMD

# Throw probe expects non-zero
cat > "$OUT/scripts/run_throw.cmd" <<'CMD'
@echo off
setlocal
cd /d %~dp0\..
set ANDROID_ROOT=run
set ANDROID_ART_ROOT=run
set ANDROID_I18N_ROOT=run
set ANDROID_DATA=run\data
set ICU_DATA=run\icu
if not exist logs mkdir logs
echo === throw ===> logs\throw.log
dalvikvm.exe -Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -Xno-sig-chain -XjdwpProvider:none -Xint -Xms64m -Xmx512m -cp run\throwprobe.jar ThrowProbe >> logs\throw.log 2>&1
set RC=%ERRORLEVEL%
echo exit=%RC%>> logs\throw.log
type logs\throw.log
if %RC%==0 (
  echo FAIL throw expected non-zero
  exit /b 1
)
findstr /C:"phase3-throw-ok" logs\throw.log >nul
if errorlevel 1 (
  echo FAIL throw message missing
  exit /b 1
)
echo PASS throw
exit /b 0
CMD

cat > "$OUT/scripts/run_all_host.cmd" <<'CMD'
@echo off
setlocal enabledelayedexpansion
cd /d %~dp0\..
if not exist logs mkdir logs
echo Win64 Phase3 host goldens %DATE% %TIME%> logs\RESULT_HOST.txt
set FAIL=0
for %%S in (
  run_hello run_props run_rtmem run_core run_io run_oserrno run_net run_dns
  run_gc run_gcforced run_interrupt run_threadstress run_goldenapp run_abspath run_throw run_gcstress run_threadheavy run_handleleak run_perfsmoke
) do (
  echo ==== %%S ====
  call scripts\%%S.cmd
  set RC=!ERRORLEVEL!
  echo %%S exit=!RC!>> logs\RESULT_HOST.txt
  if not !RC!==0 set FAIL=1
)
if !FAIL!==0 (
  echo OVERALL PASS>> logs\RESULT_HOST.txt
  echo OVERALL PASS
  exit /b 0
) else (
  echo OVERALL FAIL>> logs\RESULT_HOST.txt
  echo OVERALL FAIL
  exit /b 1
)
CMD

cat > "$OUT/README_HOST.md" <<'MD'
# Win64 Phase 3 host smoke package

Cross-built on Linux (`x86_64-pc-windows-msvc` Clang/lld). Unpack on a **real Windows 10/11 x64** host (not WSL).

## Quick start

```bat
cd <this directory>
scripts\run_all_host.cmd
```

Or individual:

```bat
scripts\run_hello.cmd
scripts\run_goldenapp.cmd
scripts\run_abspath.cmd
scripts\run_throw.cmd
```

Working directory must be the package root so DLLs resolve next to `dalvikvm.exe`.

Logs land in `logs\*.log` and summary in `logs\RESULT_HOST.txt`.

## Environment

Scripts set `ANDROID_ROOT`, `ANDROID_ART_ROOT`, `ANDROID_I18N_ROOT`, `ANDROID_DATA`, `ICU_DATA` under `run\`.

## Expected PASS markers

| Script | Marker |
|--------|--------|
| run_hello | `Hello from dalvikvm!` and `java.version=1.8.0` |
| run_props | `props.ok=true` |
| run_rtmem | `mem.ok=true` |
| run_goldenapp | `golden.ok=true` |
| run_abspath | `AbsPathProbe.done=ok` / `fails=0` |
| run_throw | non-zero exit + `phase3-throw-ok` |
| run_all_host | `OVERALL PASS` |

Wine64 on Linux is the agent CI oracle (`tools/verify/win64_phase3/run_all_wine_gates.sh`). This package is **G12** for real host goldens.

## Package integrity (Linux agent)

```bash
bash tools/win64/host_package/smoke_package_wine64.sh
```
MD

python3 - <<PY
import os, hashlib, json
from pathlib import Path
root=Path(r'''$OUT''')
files=[]
for p in sorted(root.rglob('*')):
  if p.is_file():
    h=hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    files.append({'path': str(p.relative_to(root)).replace('\\\\','/'), 'bytes': p.stat().st_size, 'sha256_16': h})
(root/'MANIFEST.json').write_text(json.dumps({'files': files, 'count': len(files)}, indent=2))
print('packaged', root, 'files', len(files), 'bytes', sum(f['bytes'] for f in files))
PY
echo "OUT=$OUT"

# Portable zip for transfer to a Windows host (G12)
OUT_FOR_ZIP="$OUT" python3 - <<'PYZIP'
import zipfile
from pathlib import Path
import os
root = Path(os.environ["OUT_FOR_ZIP"])
out = root.parent / (root.name + ".zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob("*"):
        if p.is_file() and "logs" not in p.parts:
            z.write(p, p.relative_to(root.parent))
print("zip", out, out.stat().st_size)
PYZIP


# Phase 4 native crash (expect abort). Optional; may be skipped on locked-down hosts.
cat > "$OUT/scripts/run_crashabort.cmd" <<'CMD'
@echo off
setlocal
cd /d %~dp0\..
set ANDROID_ROOT=run
set ANDROID_ART_ROOT=run
set ANDROID_I18N_ROOT=run
set ANDROID_DATA=run\data
set ICU_DATA=run\icu
if not exist logs mkdir logs
echo === crashabort ===> logs\crashabort.log
dalvikvm.exe -Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -Xno-sig-chain -XjdwpProvider:none -Xint -Xms64m -Xmx512m -cp run\crashabortprobe.jar CrashAbortProbe >> logs\crashabort.log 2>&1
set RC=%ERRORLEVEL%
echo exit=%RC%>> logs\crashabort.log
type logs\crashabort.log
if %RC%==0 (
  echo FAIL crashabort expected nonzero
  exit /b 1
)
findstr /C:"phase4-abort-ok" logs\crashabort.log >nul
if errorlevel 1 (
  echo FAIL message missing
  exit /b 1
)
echo PASS crashabort
exit /b 0
CMD
