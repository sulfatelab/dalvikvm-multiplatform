#!/usr/bin/env bash
# Sequential wine64 Phase 3 gate suite (agent01 cross-build oracle).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/../../.." && pwd)"
export BUILD="${BUILD:-$REPO/build/win64_phase1}"
cd "$ROOT"
fail=0
run() {
  local name="$1"; shift
  echo "==== GATE $name ===="
  if "$@"; then
    echo "PASS $name"
  else
    echo "FAIL $name"
    fail=1
  fi
}
# Build jars that may be missing
for cls in PathProbe IoProbe CoreProbe NetProbe GcProbe GcForced InterruptProbe GoldenApp RtMem AbsPathProbe DnsProbe PropsProbe OsErrnoProbe ThreadStressProbe ThrowProbe; do
  jar="$BUILD/run/$(echo "$cls" | tr '[:upper:]' '[:lower:]').jar"
  if [[ ! -f "$jar" ]]; then
    bash "$ROOT/build_one.sh" "$cls" || true
  fi
done
# Ensure Props/Os jars always fresh if sources newer? rebuild cheaply for new probes
bash "$ROOT/build_one.sh" PropsProbe
bash "$ROOT/build_one.sh" OsErrnoProbe
bash "$ROOT/build_one.sh" ThreadStressProbe
bash "$ROOT/build_one.sh" ThrowProbe

run G3_G4_G5 bash "$ROOT/run_probe.sh"
run G5b_G5c bash "$ROOT/run_abspathprobe.sh"
run G6 bash "$ROOT/run_ioprobe.sh"
run G7 bash "$ROOT/run_coreprobe.sh"
run G7b bash "$ROOT/run_rtmem.sh"
run G7c bash "$ROOT/run_one.sh" PropsProbe props.ok=true PropsProbe.done=ok
run G7d bash "$ROOT/run_one.sh" OsErrnoProbe OsErrnoProbe.done=ok
run G8 bash "$ROOT/run_netprobe.sh"
run G8b bash "$ROOT/run_dnsprobe.sh"
run G9 bash "$ROOT/run_gcprobe.sh"
run G9b bash "$ROOT/run_gcforced.sh"
run G10 bash "$ROOT/run_interruptprobe.sh"
run G10b bash "$ROOT/run_threadstress.sh"
run G11 bash "$ROOT/run_goldenapp.sh"
run G11b bash "$ROOT/run_throwprobe.sh"
echo "==== SUMMARY ===="
if [[ $fail -eq 0 ]]; then
  echo "PASS all wine Phase 3 gates"
else
  echo "FAIL some wine Phase 3 gates"
fi
exit $fail
