#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
if [[ ! -f "$BUILD/art.dll" || ! -f "$BUILD/run/art.dll" ]]; then
  echo "missing built or staged art.dll under $BUILD" >&2
  exit 1
fi
if ! cmp -s "$BUILD/art.dll" "$BUILD/run/art.dll"; then
  echo "staged run/art.dll is stale; copy the current build artifact before testing" >&2
  exit 1
fi
python3 "$REPO/tools/verify/windows_x64_phase1/check_win32_boundary_unwind.py" \
  --art-dll "$BUILD/run/art.dll"
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
mkdir -p run/crash
python3 - <<'PY'
import subprocess, os, sys, glob
env=os.environ.copy()
env.update({'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run','ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':env.get('WINEDEBUG','-all')})
before=set(glob.glob('run/crash/*.dmp'))
cmd=['timeout','30','wine64','./dalvikvm.exe','-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar','-Ximage:/nonexistent-no-boot-image','-XjdwpProvider:none','-Xint','-Xms64m','-Xmx512m','-cp','run/crashnativeprobe.jar','CrashNativeProbe']
r=subprocess.run(cmd,env=env,capture_output=True,text=True)
text=r.stdout+'\n'+r.stderr
for line in (r.stdout+r.stderr).splitlines():
  if 'CrashNative' in line or 'VEH' in line or 'UEF' in line or 'minidump' in line or 'exception' in line.lower():
    if not line.startswith('dalvikvm.exe I'):
      print(line[:240])
print('exit', r.returncode)
after=set(glob.glob('run/crash/*.dmp'))
new=sorted(after-before)
print('new_dumps', new)
print('=== ASSERT ===')
checks = {
    'native_crash_aborts': 'unexpected_continue' not in text and r.returncode != 0,
    'initial_veh': 'ART Win32 VEH: exception 0xc0000005' in text,
    'unhandled_exception_filter': 'ART Win32 UEF: exception 0xc0000005' in text,
    'minidump_marker': 'ART Win32 crash: minidump written to ' in text,
}
valid_dumps=[]
for path in new:
    try:
        with open(path, 'rb') as dump:
            valid = dump.read(4) == b'MDMP'
        if valid and os.path.getsize(path) > 32:
            valid_dumps.append(path)
    except OSError:
        pass
checks['new_valid_minidump'] = bool(valid_dumps)
print('valid_dumps', valid_dumps)
for name, passed in checks.items():
    print('PASS' if passed else 'FAIL', name)
sys.exit(0 if all(checks.values()) else 1)
PY
