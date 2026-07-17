#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ICU="${1:-$REPO/build/win64_libcore_icu}"
P1="${2:-$REPO/build/win64_phase1}"
# Real PE only (W-005): never copy libcombined into product names.
bash "$REPO/tools/win64/stage_native_modules.sh" "$P1" "$ICU" "$P1"
bash "$REPO/tools/win64/stage_run_assets.sh" "$P1" "$P1"
echo "Installed real ICU+javacore+openjdk PE into $P1 (no libcombined aliases)"
ls -lh "$P1"/{icuuc,icui18n,icu_jni,libicu_jni,javacore,libjavacore,openjdk,libopenjdk,openjdkjvm}.dll 2>/dev/null || true
ls -lh "$P1"/run/boot.jar "$P1"/run/icu/icudt72l.dat 2>/dev/null || true
