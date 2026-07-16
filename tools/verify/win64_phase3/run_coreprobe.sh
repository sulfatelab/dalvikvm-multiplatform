#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
python3 - <<'PY'
import subprocess, os, sys
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':env.get('WINEDEBUG','-all')})
cmd=['timeout','60','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m','-cp','run/coreprobe.jar','CoreProbe']
r=subprocess.run(cmd, cwd=os.getcwd(), env=env, capture_output=True, text=True)
for line in r.stdout.splitlines():
  if not line.startswith('dalvikvm.exe'): print(line)
print('exit', r.returncode)
text=r.stdout
checks=[
 ('exit0', r.returncode==0),
 ('arraycopy', 'arraycopy=true' in text),
 ('charset', 'charset=true' in text),
 ('reflect', 'reflect=reflect-ok' in text),
 ('threads', 'threads.ok=true' in text),
 ('done', 'CoreProbe.done=ok' in text),
]
fail=0
print('=== ASSERT ===')
for n,ok in checks:
  print(('PASS' if ok else 'FAIL'), n)
  if not ok: fail=1
sys.exit(fail)
PY
