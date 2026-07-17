#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ICU="${1:-$REPO/build/win64_libcore_icu}"
P1="${2:-$REPO/build/win64_phase1}"
cp -f "$ICU/icuuc.dll" "$ICU/icui18n.dll" "$ICU/icu_jni.dll" "$P1/"
cp -f "$ICU/icu_jni.dll" "$P1/libicu_jni.dll"
if [[ -f "$ICU/javacore.dll" ]]; then
  cp -f "$ICU/javacore.dll" "$P1/javacore.dll"
  cp -f "$ICU/javacore.dll" "$P1/libjavacore.dll"
fi
if [[ -f "$ICU/openjdk.dll" ]]; then
  cp -f "$ICU/openjdk.dll" "$P1/openjdk.dll"
  cp -f "$ICU/openjdk.dll" "$P1/libopenjdk.dll"
fi
if [[ -f "$ICU/openjdkjvm.dll" ]]; then
  cp -f "$ICU/openjdkjvm.dll" "$P1/openjdkjvm.dll" 2>/dev/null || true
fi
# Always ship ICU data with the product tree (same class as boot.jar).
bash "$REPO/tools/win64/stage_run_assets.sh" "$P1" "$P1"
echo "Installed real ICU(+javacore/openjdk if built) PE into $P1"
ls -lh "$P1"/icuuc.dll "$P1"/icui18n.dll "$P1"/icu_jni.dll "$P1"/libicu_jni.dll "$P1"/libjavacore.dll 2>/dev/null || true
ls -lh "$P1"/run/boot.jar "$P1"/run/icu/icudt72l.dat 2>/dev/null || true
