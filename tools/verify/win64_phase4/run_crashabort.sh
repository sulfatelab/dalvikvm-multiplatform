#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
python3 - <<'PY'
import subprocess, os, sys
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':env.get('WINEDEBUG','-all')})
cmd=['timeout','60','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m','-cp','run/crashabortprobe.jar','CrashAbortProbe']
r=subprocess.run(cmd,env=env,capture_output=True,text=True)
text=r.stdout+'\n'+r.stderr
for line in r.stdout.splitlines():
  if not line.startswith('dalvikvm.exe'): print(line)
print('exit', r.returncode)
print('=== ASSERT ===')
ok = r.returncode != 0 and 'phase4-abort-ok' in text
print('PASS' if ok else 'FAIL', 'abort_nonzero_with_message')
ok2 = 'Exception' in text or 'RuntimeException' in text
print('PASS' if ok2 else 'FAIL', 'exception_printed')
sys.exit(0 if ok and ok2 else 1)
PY
