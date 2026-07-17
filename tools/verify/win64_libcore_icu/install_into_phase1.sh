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
echo "Installed real ICU(+javacore if built) PE into $P1"
ls -lh "$P1"/icuuc.dll "$P1"/icui18n.dll "$P1"/icu_jni.dll "$P1"/libicu_jni.dll "$P1"/libjavacore.dll 2>/dev/null || true

# Ensure ICU data for smoke (do not delete existing full dat)
ICU_DIR="$P1/run/icu"
mkdir -p "$ICU_DIR"
if [[ ! -f "$ICU_DIR/icudt72l.dat" ]]; then
  for cand in       "$REPO/vendor/icu/icu4c/source/stubdata/icudt72l.dat"       "$REPO/dist/win64_phase3_host/run/icu/icudt72l.dat"; do
    if [[ -f "$cand" ]]; then
      cp -a "$cand" "$ICU_DIR/icudt72l.dat"
      echo "Installed ICU data from $cand"
      break
    fi
  done
fi
echo "Smoke: export ICU_DATA=run/icu (or absolute path to $ICU_DIR) before wine/host runs."
