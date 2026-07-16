#!/usr/bin/env bash
# Integrity-smoke the staged host package under wine64 (not a substitute for G12 host).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PKG="${1:-$REPO/dist/win64_phase3_host}"
if [[ ! -x "$PKG/dalvikvm.exe" ]]; then
  bash "$REPO/tools/win64/host_package/package_win64_phase3.sh" "$PKG"
fi
# Stage C: jar for abspath
STAGE="${WINEPREFIX:-$HOME/.wine}/drive_c/art_phase3/abs_dir"
mkdir -p "$STAGE"
cp -a "$PKG/run/hello.jar" "$STAGE/hello.jar"
cd "$PKG"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG=-all
python3 -u - <<'PY'
import os, subprocess, sys
pkg=os.getcwd()
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':'-all'})
base=['timeout','60','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m']
fail=0
def run(label, args, need=None, expect_fail=False):
  global fail
  r=subprocess.run(base+args, cwd=pkg, env=env, capture_output=True, text=True)
  text=r.stdout+'\n'+r.stderr
  ok=True
  if expect_fail:
    ok = r.returncode != 0 and (need is None or need in text)
  else:
    ok = r.returncode == 0 and (need is None or need in r.stdout)
  print(('PASS' if ok else 'FAIL'), label, 'exit', r.returncode)
  if not ok:
    fail=1
    for line in text.splitlines()[-12:]:
      if line.strip() and 'FinishArray' not in line:
        print(' ', line[:200])
  return r

run('hello', ['-cp','run/hello.jar','Hello'], 'Hello from dalvikvm!')
run('props', ['-cp','run/propsprobe.jar','PropsProbe'], 'props.ok=true')
run('rtmem', ['-cp','run/rtmem.jar','RtMem'], 'mem.ok=true')
run('golden', ['-cp','run/goldenapp.jar','GoldenApp'], 'golden.ok=true')
run('abspath', ['-cp', r'C:\art_phase3\abs_dir\hello.jar;run/abspathprobe.jar','AbsPathProbe'], 'AbsPathProbe.done=ok')
run('throw', ['-cp','run/throwprobe.jar','ThrowProbe'], 'phase3-throw-ok', expect_fail=True)
print('OVERALL', 'PASS' if fail==0 else 'FAIL')
sys.exit(fail)
PY
