#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/win64_phase1}"
RUN="$BUILD/run"
WINE="${WINE:-wine64}"
TIMEOUT="${TIMEOUT:-120}"

bash "$REPO/tools/verify/win64_phase4/build_one.sh" W010ManagedFaultProbe
mkdir -p "$RUN/crash"

snapshot_dumps() {
  find "$RUN/crash" -maxdepth 1 -type f -name '*.dmp' \
    -printf '%f %s %T@\n' | sort
}

before_dumps="$(snapshot_dumps)"

run_no_sig_chain_rejection() {
  local log="${TMPDIR:-/tmp}/w010-no-sig-chain-rejection.log"
  local rc

  if (
    cd "$BUILD"
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -Xno-sig-chain \
      -XjdwpProvider:none \
      -Xint \
      -Xms64m -Xmx512m \
      -cp "$RUN/w010managedfaultprobe.jar" W010ManagedFaultProbe npe
  ) >"$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  if [[ $rc -eq 0 ]] ||
     ! grep -qF "A started runtime should have sig chain enabled" "$log"; then
    printf 'W-010 -Xno-sig-chain started-runtime rejection FAIL exit=%s log=%s\n' \
      "$rc" "$log" >&2
    tail -120 "$log" >&2
    return 1
  fi
  printf 'W-010 -Xno-sig-chain started-runtime rejection PASS\n'
}

run_one() {
  local execution_mode="$1"
  local fault_mode="$2"
  local log="${TMPDIR:-/tmp}/w010-managed-${execution_mode}-${fault_mode}.log"
  local -a vm_args
  local rc

  if [[ "$execution_mode" == "nterp" ]]; then
    vm_args=(-Xusejit:false)
  else
    vm_args=(-verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0)
  fi

  if (
    cd "$BUILD"
    unset ART_WIN64_NTERP
    export ART_WIN64_JIT_FILTER="W010ManagedFaultProbe"
    export ART_WIN64_JIT_LOG_COMPILES=1
    export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
    export ANDROID_DATA=run/data ICU_DATA=run/icu WINEDEBUG="${WINEDEBUG:--all}"
    timeout "$TIMEOUT" "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -Xms64m -Xmx512m \
      "${vm_args[@]}" \
      -cp "$RUN/w010managedfaultprobe.jar" W010ManagedFaultProbe "$fault_mode"
  ) >"$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  if [[ $rc -ne 0 ]] ||
     ! grep -qF "W010ManagedFaultProbe OK mode=$fault_mode" "$log" ||
     grep -qE 'ART Win64 (VEH|UEF)|minidump written' "$log"; then
    printf 'W-010 managed fault %s/%s FAIL exit=%s log=%s\n' \
      "$execution_mode" "$fault_mode" "$rc" "$log" >&2
    tail -160 "$log" >&2
    return 1
  fi

  if [[ "$fault_mode" == "npe" ]] &&
     ! grep -qF "W010ManagedFaultProbe NPE OK read=64 write=64" "$log"; then
    printf 'W-010 managed NPE marker missing: %s\n' "$log" >&2
    tail -160 "$log" >&2
    return 1
  fi

  if [[ "$fault_mode" == "so" ]] &&
     ! grep -qF "W010ManagedFaultProbe SO OK main=2 child=2" "$log"; then
    printf 'W-010 managed SO marker missing: %s\n' "$log" >&2
    tail -160 "$log" >&2
    return 1
  fi

  if [[ "$execution_mode" == "jit" ]]; then
    local -a required_methods
    local required_method
    if [[ "$fault_mode" == "npe" ]]; then
      # readCell() and writeCell() are intentionally small enough to inline;
      # the faulting field loads/stores then live in this compiled caller.
      required_methods=(runNullChecks)
    else
      required_methods=(recurse runStackOverflowRounds)
    fi
    for required_method in "${required_methods[@]}"; do
      if ! grep -qE "Win64 CompileMethod done success=1 method=.*W010ManagedFaultProbe\\.${required_method}\\(" \
          "$log"; then
        printf 'W-010 JIT method %s was not compiled: %s\n' "$required_method" "$log" >&2
        tail -160 "$log" >&2
        return 1
      fi
    done
  elif grep -qF "Win64 CompileMethod done success=1 method=" "$log"; then
    printf 'W-010 nterp run unexpectedly compiled managed code: %s\n' "$log" >&2
    tail -160 "$log" >&2
    return 1
  fi

  printf 'W-010 managed fault %s/%s PASS\n' "$execution_mode" "$fault_mode"
}

run_no_sig_chain_rejection
for execution_mode in nterp jit; do
  run_one "$execution_mode" npe
  run_one "$execution_mode" so
done

after_dumps="$(snapshot_dumps)"
if [[ "$after_dumps" != "$before_dumps" ]]; then
  printf 'W-010 handled managed faults changed run/crash dump state\n' >&2
  diff -u <(printf '%s\n' "$before_dumps") <(printf '%s\n' "$after_dumps") >&2 || true
  exit 1
fi

printf 'W-010 managed fault acceptance: nterp and threshold-zero JIT NPE/SO: PASS\n'
