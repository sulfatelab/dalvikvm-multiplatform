#!/usr/bin/env bash
# L-003 wine matrix: Process/exec, locale, zip edges, UDP IPv4, IPv6 dual-stack bind.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
P1="${MDVM_WIN64_PHASE1:-$ROOT/build/win64_phase1}"
cd "$P1"
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG=-all

build_one() {
  bash "$ROOT/tools/verify/win64_phase3/build_one.sh" "$1"
}

# Ipv6Probe needs android/libcore on javac bootclasspath
export MDVM_PROBE_BOOTCP="${MDVM_PROBE_BOOTCP:-/tmp/bootbuild/classes}"
if [[ ! -d "$MDVM_PROBE_BOOTCP/libcore/io" ]]; then
  echo "WARN: $MDVM_PROBE_BOOTCP missing; building boot classes may be required for Ipv6Probe" >&2
fi
for cls in ExecProbe LocaleProbe ZipProbe UdpProbe Ipv6Probe; do
  build_one "$cls"
done

python3 -u - <<'PY'
import os, subprocess, sys
p1=os.getcwd()
env=os.environ.copy()
env.update({
  'ANDROID_ROOT':'run','ANDROID_ART_ROOT':'run','ANDROID_I18N_ROOT':'run',
  'ANDROID_DATA':'run/data','ICU_DATA':'run/icu','WINEDEBUG':'-all',
})
base=['timeout','60','wine64','./dalvikvm.exe',
  '-Xbootclasspath:run/boot.jar','-Xbootclasspath-locations:run/boot.jar',
  '-Ximage:/nonexistent-no-boot-image','-Xno-sig-chain','-XjdwpProvider:none',
  '-Xint','-Xms64m','-Xmx512m']
cases=[
  ('exec','run/execprobe.jar','ExecProbe','ExecProbe.done=ok'),
  ('locale','run/localeprobe.jar','LocaleProbe','LocaleProbe.done=ok'),
  ('zip','run/zipprobe.jar','ZipProbe','ZipProbe.done=ok'),
  ('udp','run/udpprobe.jar','UdpProbe','UdpProbe.done=ok'),
  ('ipv6','run/ipv6probe.jar','Ipv6Probe','Ipv6Probe.done=ok'),
]
fail=0
for label,jar,cls,need in cases:
  r=subprocess.run(base+['-cp',jar,cls], cwd=p1, env=env, capture_output=True, text=True)
  text=r.stdout+'\n'+r.stderr
  ok = (r.returncode==0 and need in r.stdout)
  print(('PASS' if ok else 'FAIL'), label, 'exit', r.returncode)
  for line in text.splitlines():
    if any(k in line for k in (need.split('.')[0], 'done=', 'Exception', 'error=', 'fail=', 'skip=', 'note=')) \
       and 'class_linker' not in line and 'FinishArray' not in line and 'image_space' not in line:
      if line.strip():
        print(' ', line[:220])
  if not ok:
    fail=1
    kept=[ln for ln in text.splitlines() if ln.strip() and 'class_linker' not in ln and 'FinishArray' not in ln]
    for ln in kept[-15:]:
      print(' T', ln[:220])
print('L-003 OVERALL', 'PASS' if fail==0 else 'FAIL')
sys.exit(fail)
PY
