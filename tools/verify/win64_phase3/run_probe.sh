#!/usr/bin/env bash
# Run PathProbe + Hello multi-jar under wine64 using Python argv (bash eats ';').
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
cd "$BUILD"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
export ANDROID_DATA=run/data ICU_DATA=run/icu
export WINEDEBUG="${WINEDEBUG:--all}"
python3 - <<'PY'
import subprocess, os, sys, re
build=os.environ.get('BUILD') or os.getcwd()
env=os.environ.copy()
env.update({
  'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run',
  'ANDROID_DATA':'run/data','ICU_DATA':'run/icu',
  'WINEDEBUG': env.get('WINEDEBUG','-all'),
})
base=['timeout','45','wine64','./dalvikvm.exe',
  '-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar',
  '-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none','-Xint',
  '-Xms64m','-Xmx512m']
# Hello regression
r=subprocess.run(base+['-cp','run/hello.jar','Hello'], cwd=build, env=env, capture_output=True, text=True)
print('=== Hello ===')
for line in r.stdout.splitlines():
    if not line.startswith('dalvikvm.exe'): print(line)
print('hello_exit', r.returncode)
# Multi-jar PathProbe — MUST pass -cp via argv list, not shell string
r2=subprocess.run(base+['-cp','run/probe.jar;run/hello.jar','PathProbe'], cwd=build, env=env, capture_output=True, text=True)
print('=== PathProbe ===')
for line in r2.stdout.splitlines():
    if line.startswith('dalvikvm.exe') or 'FinishArray' in line or 'oat_file' in line or 'SetCloseOnExec' in line:
        continue
    print(line)
print('probe_exit', r2.returncode)
text=r2.stdout
checks=[
  ('hello_exit0', r.returncode==0 and 'Hello from dalvikvm!' in r.stdout),
  ('probe_exit0', r2.returncode==0),
  ('path.separator=;', 'path.separator=;' in text),
  ('file.separator=\\', 'file.separator=\\' in text),
  ('multi-cp-semi', 'java.class.path=run/probe.jar;run/hello.jar' in text),
  ('WinNTFileSystem', 'File.fs=java.io.WinNTFileSystem' in text),
  ('abs_drive', re.search(r'in=C:\\\\x\npath=C:\\\\x\nprefixLength=3\nisAbsolute=true', text) is not None
               or ('in=C:\\x' in text and 'prefixLength=3' in text and 'isAbsolute=true' in text)),
  ('mixed_norm', 'path=C:\\User\\admin\\.ssh\\x' in text),
  ('unc_keep', 'path=\\\\server\\share\\a' in text or 'path=\\server\\share\\a' in text),
  ('Hello.load=ok', 'Hello.load=ok' in text),
]
# Stricter abs_drive check
blocks=text.split('---')
abs_ok=False
mixed_ok=False
unc_ok=False
for b in blocks:
    if 'in=C:\\x' in b and 'isAbsolute=true' in b and 'prefixLength=3' in b: abs_ok=True
    if 'in=C:\\User/admin/.ssh/x' in b and 'isAbsolute=true' in b and 'path=C:\\User\\admin\\.ssh\\x' in b: mixed_ok=True
    if 'in=\\\\server\\share\\a' in b and 'isAbsolute=true' in b and 'path=\\\\server\\share\\a' in b: unc_ok=True
checks=[
  ('hello_exit0', r.returncode==0 and 'Hello from dalvikvm!' in r.stdout),
  ('probe_exit0', r2.returncode==0),
  ('path.separator=;', 'path.separator=;' in text),
  ('file.separator=\\', 'file.separator=\\' in text),
  ('multi-cp-semi', 'java.class.path=run/probe.jar;run/hello.jar' in text),
  ('WinNTFileSystem', 'File.fs=java.io.WinNTFileSystem' in text),
  ('abs_drive_C', abs_ok),
  ('mixed_abs', mixed_ok),
  ('unc_abs', unc_ok),
  ('Hello.load=ok', 'Hello.load=ok' in text),
]
fail=0
print('=== ASSERT ===')
for name,ok in checks:
    print(('PASS' if ok else 'FAIL'), name)
    if not ok: fail+=1
# Note ICU pitfall visibility
if 'isLetterC=false' in text:
    print('NOTE Character.isLetter(C)=false (expected on imageless ART; WinNT uses ASCII isDriveLetter)')
sys.exit(1 if fail else 0)
PY
