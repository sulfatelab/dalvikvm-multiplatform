#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ART="$REPO/vendor/art"
INTERPRETER="$ART/runtime/interpreter/interpreter.cc"
JIT="$ART/runtime/jit/jit.cc"

if rg -q 'ResolveJniEntryPoint|InterpreterJniGeneric|ART_WIN64_INTERPRETER_JNI_TRIPWIRE' \
    "$INTERPRETER"; then
  echo "legacy Win64 InterpreterJni fallback code remains" >&2
  exit 1
fi

if ! rg -qF 'CHECK(!Runtime::Current()->IsStarted());' "$INTERPRETER"; then
  echo "upstream pre-start-only interpreter bridge invariant is missing" >&2
  exit 1
fi

if rg -q 'ART_WIN64_JIT_NATIVE' "$JIT" \
    "$REPO/tools/verify/win64_phase1/CMakeLists.txt" \
    "$REPO/tools/verify/win64_phase4/run_jit_smoke.sh" \
    "$REPO/tools/verify/win64_phase4/run_jvmti_force_probe.sh" \
    "$REPO/tools/verify/win64_phase4/run_math_critical_probe.sh" \
    "$REPO/tools/verify/win64_phase4/run_native_abi_probe.sh"; then
  echo "legacy Win64 native-JIT gate remains" >&2
  exit 1
fi

if rg -q 'MDVM_WIN64_INTERPRETER_JNI_TRIPWIRE' \
    "$REPO/tools/verify/win64_phase1/CMakeLists.txt"; then
  echo "retired InterpreterJni tripwire build option remains" >&2
  exit 1
fi

if [[ -e "$REPO/tools/win64/host_package/package_win64_w024_tripwire.sh" ]]; then
  echo "retired W-024 tripwire package generator remains" >&2
  exit 1
fi

if git -C "$ART" cat-file -e android-16.0.0_r4:runtime/interpreter/interpreter.cc \
    2>/dev/null; then
  if ! cmp -s <(git -C "$ART" show \
      android-16.0.0_r4:runtime/interpreter/interpreter.cc) "$INTERPRETER"; then
    echo "interpreter.cc differs from android-16.0.0_r4" >&2
    exit 1
  fi
fi

echo "W-024 cleanup source check: PASS"
