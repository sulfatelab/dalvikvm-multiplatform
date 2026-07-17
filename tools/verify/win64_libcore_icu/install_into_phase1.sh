#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ICU="${1:-$REPO/build/win64_libcore_icu}"
P1="${2:-$REPO/build/win64_phase1}"
cp -f "$ICU/icuuc.dll" "$ICU/icui18n.dll" "$ICU/icu_jni.dll" "$P1/"
cp -f "$ICU/icu_jni.dll" "$P1/libicu_jni.dll"
echo "Installed real ICU PE into $P1"
ls -lh "$P1"/icuuc.dll "$P1"/icui18n.dll "$P1"/icu_jni.dll "$P1"/libicu_jni.dll
