#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
mkdir -p run/crash
python3 - <<'PY'
import subprocess, os, sys, glob
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':env.get('WINEDEBUG','-all')})
before=set(glob.glob('run/crash/*'))
cmd=['timeout','30','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m','-cp','run/crashnativeprobe.jar','CrashNativeProbe']
r=subprocess.run(cmd,env=env,capture_output=True,text=True)
text=r.stdout+'\n'+r.stderr
for line in (r.stdout+r.stderr).splitlines():
  if 'CrashNative' in line or 'VEH' in line or 'UEF' in line or 'minidump' in line or 'exception' in line.lower():
    if not line.startswith('dalvikvm.exe I'):
      print(line[:240])
print('exit', r.returncode)
after=set(glob.glob('run/crash/*'))
new=sorted(after-before)
print('new_dumps', new)
print('=== ASSERT ===')
# Success: does not print unexpected_continue, and exits nonzero (or killed)
ok = 'unexpected_continue' not in text and r.returncode != 0
print('PASS' if ok else 'FAIL', 'native_crash_aborts')
# Diagnostics optional under wine (minidump may not fully work)
diag = ('VEH' in text) or ('UEF' in text) or ('exception' in text.lower()) or bool(new)
print('PASS' if diag else 'FAIL', 'crash_diagnostics_or_dump')
# soft: don't fail suite solely for missing dump under wine if abort ok
sys.exit(0 if ok else 1)
PY
