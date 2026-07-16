#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ARCHIVE="${MDVM_NATIVE_SRC_ROOT_DIR:-/home/agent/Projects/MinDalvikVM-Archive/native}"
cd "$REPO"
export PYTHONPATH="$REPO/tools/bp2cmake${PYTHONPATH:+:$PYTHONPATH}"
python3 -m bp2cmake \
  --root "$ARCHIVE" \
  --overlay overlay/port_policy_windows.py \
  --os windows --arch x86_64 \
  --extra-root "$REPO/vendor:MDVM_ART_ROOT_DIR" \
  --exclude-top art \
  --module liblog --module libbase --module libnativehelper \
  --module libziparchive --module libartpalette --module libartbase \
  --out tools/verify/win64_phase0/phase0.cmake
echo "wrote tools/verify/win64_phase0/phase0.cmake"
