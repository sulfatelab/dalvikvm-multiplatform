#!/usr/bin/env bash
set -euo pipefail
CLS="${1:?class}"; shift || true
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
JAR="run/$(echo "$CLS" | tr '[:upper:]' '[:lower:]').jar"
python3 - <<PY
import subprocess, os, sys
cls=r'''$CLS'''
jar=r'''$JAR'''
needs='''$*'''.split()
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':env.get('WINEDEBUG','-all')})
cmd=['timeout','180','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m','-cp',jar,cls]
r=subprocess.run(cmd, cwd=os.getcwd(), env=env, capture_output=True, text=True)
for line in r.stdout.splitlines():
  if not line.startswith('dalvikvm.exe'): print(line)
print('exit', r.returncode)
fail = 0 if r.returncode==0 else 1
print('=== ASSERT ===')
print('PASS exit0' if r.returncode==0 else 'FAIL exit0')
for n in needs:
  if not n: continue
  ok = n in r.stdout
  print(('PASS' if ok else 'FAIL'), n)
  if not ok: fail=1
sys.exit(fail)
PY
