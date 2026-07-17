#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ICU="${1:-$REPO/build/win64_libcore_icu}"
P1="${2:-$REPO/build/win64_phase1}"
# Real PE only, single product soname each (W-005 / L-004).
bash "$REPO/tools/win64/stage_native_modules.sh" "$P1" "$ICU" "$P1"
bash "$REPO/tools/win64/stage_run_assets.sh" "$P1" "$P1"
echo "Installed real product PE into $P1 (ART sonames only; no short-name twins)"
ls -lh "$P1"/{icuuc,icui18n,libicu_jni,libjavacore,libopenjdk,libopenjdkjvm}.dll 2>/dev/null || true
ls -lh "$P1"/libcrypto.dll 2>/dev/null || true
ls -lh "$P1"/run/boot.jar "$P1"/run/icu/icudt72l.dat 2>/dev/null || true
# Fail if short twins reappear
for bad in icu_jni.dll javacore.dll openjdk.dll openjdkjvm.dll crypto.dll; do
  if [[ -f "$P1/$bad" ]]; then
    echo "ERROR: unexpected short-name twin $bad (L-004)" >&2
    exit 1
  fi
done
