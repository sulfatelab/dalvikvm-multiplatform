#!/usr/bin/env bash
# Absolute path / P2–P9c / Runtime memory acceptance under wine64.
# Requires hello.jar staged at wine C:\art_phase3\abs_dir\hello.jar
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
STAGE_DIR="${WINEPREFIX:-$HOME/.wine}/drive_c/art_phase3/abs_dir"
mkdir -p "$STAGE_DIR"
cp -a "$BUILD/run/hello.jar" "$STAGE_DIR/hello.jar"
# Ensure AbsPathProbe jar built
if [[ ! -f "$BUILD/run/abspathprobe.jar" ]]; then
  bash "$REPO/tools/verify/win64_phase3/build_one.sh" AbsPathProbe
fi
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
python3 -u - <<'PY'
import subprocess, os, sys
build=os.getcwd()
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':env.get('WINEDEBUG','-all')})
base=['timeout','45','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m']
fail=0
for label,cp in [
  ('P2_fwd', r'C:/art_phase3/abs_dir/hello.jar'),
  ('P3_back', r'C:\art_phase3\abs_dir\hello.jar'),
  ('P4_mixed', r'C:\art_phase3\abs_dir/hello.jar'),
]:
  r=subprocess.run(base+['-cp',cp,'Hello'], cwd=build, env=env, capture_output=True, text=True)
  ok=r.returncode==0 and 'Hello from dalvikvm!' in r.stdout
  print(('PASS' if ok else 'FAIL'), label)
  if not ok: fail=1
r=subprocess.run(base+['-cp', r'C:\art_phase3\abs_dir\hello.jar;run/abspathprobe.jar','AbsPathProbe'], cwd=build, env=env, capture_output=True, text=True)
for line in r.stdout.splitlines():
  if not line.startswith('dalvikvm.exe'): print(line)
print('abs_exit', r.returncode)
if r.returncode!=0: fail=1
# P9c: ':' must not act as multi-jar separator on Win64
r=subprocess.run(base+['-cp', r'run/probe.jar:run/hello.jar','PathProbe'], cwd=build, env=env, capture_output=True, text=True)
p9c_ok = r.returncode!=0 and ('ClassNotFoundException' in (r.stderr+r.stdout) or 'Unable to locate class' in (r.stderr+r.stdout))
print(('PASS' if p9c_ok else 'FAIL'), 'P9c_colon_not_multi')
if not p9c_ok: fail=1
r=subprocess.run(base+['-cp', r'C:\art_phase3\abs_dir\hello.jar:C:\art_phase3\abs_dir\hello.jar','Hello'], cwd=build, env=env, capture_output=True, text=True)
colon_abs_ok = not (r.returncode==0 and 'Hello from dalvikvm!' in r.stdout)
print(('PASS' if colon_abs_ok else 'FAIL'), 'P9c_abs_colon_not_two_jars')
if not colon_abs_ok: fail=1
print('=== ASSERT ===')
print('PASS overall' if fail==0 else 'FAIL overall')
sys.exit(fail)
PY
