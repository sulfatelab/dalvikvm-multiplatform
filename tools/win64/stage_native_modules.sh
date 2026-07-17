#!/usr/bin/env bash
# Stage real Win64 PE native modules for product trees.
# ART InitNativeMethods loads (Windows):
#   libicu_jni.dll, libjavacore.dll, libopenjdk.dll
# Supporting PE (not multi-name libcombined stubs):
#   icuuc.dll, icui18n.dll, openjdkjvm.dll
#
# Usage:
#   tools/win64/stage_native_modules.sh <dest_root> [hybrid_build_dir] [phase1_dir]
#
# Rejects product use of tools/win64/jni_stubs/libcombined.dll (W-005).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:?dest root required}"
HYBRID="${2:-$REPO/build/win64_libcore_icu}"
PHASE1="${3:-$REPO/build/win64_phase1}"

mkdir -p "$DEST"

# Prefer freshly built hybrid PE, then existing dest/phase1.
pick() {
  local name="$1"
  for dir in "$HYBRID" "$PHASE1" "$DEST"; do
    if [[ -f "$dir/$name" ]]; then
      echo "$dir/$name"
      return 0
    fi
  done
  return 1
}

require_copy() {
  local name="$1"
  local src
  if ! src=$(pick "$name"); then
    echo "ERROR: missing required real PE module: $name" >&2
    echo "  Build hybrid: cmake --build build/win64_libcore_icu --target icuuc icui18n icu_jni javacore openjdk openjdkjvm" >&2
    echo "  Then: bash tools/verify/win64_libcore_icu/install_into_phase1.sh" >&2
    echo "  libcombined multi-name stubs are NOT accepted for product (W-005)." >&2
    exit 1
  fi
  # Refuse known stub alias path
  if [[ "$src" == *"/jni_stubs/libcombined.dll" ]]; then
    echo "ERROR: refusing libcombined.dll for $name (W-005)" >&2
    exit 1
  fi
  cp -a "$src" "$DEST/$name"
  echo "stage_native_modules: $name <- $src"
}

# Supporting ICU / openjdkjvm first
require_copy icuuc.dll
require_copy icui18n.dll
require_copy openjdkjvm.dll

# Module bodies (short names as build artifacts)
require_copy icu_jni.dll
require_copy javacore.dll
require_copy openjdk.dll

# ART sonames (must be real modules, not one stub thrice)
cp -a "$DEST/icu_jni.dll" "$DEST/libicu_jni.dll"
cp -a "$DEST/javacore.dll" "$DEST/libjavacore.dll"
cp -a "$DEST/openjdk.dll" "$DEST/libopenjdk.dll"
echo "stage_native_modules: libicu_jni/libjavacore/libopenjdk <- real PE (not libcombined)"

# Sanity: the three ART load names must not all be identical-to-libcombined if present
if [[ -f "$REPO/tools/win64/jni_stubs/libcombined.dll" ]]; then
  comb=$(md5sum "$REPO/tools/win64/jni_stubs/libcombined.dll" | awk '{print $1}')
  for n in libicu_jni.dll libjavacore.dll libopenjdk.dll; do
    h=$(md5sum "$DEST/$n" | awk '{print $1}')
    if [[ "$h" == "$comb" ]]; then
      echo "ERROR: $DEST/$n matches jni_stubs/libcombined.dll — product must use real PE (W-005)" >&2
      exit 1
    fi
  done
fi

# Optional crypto PE (L-002): present when hybrid build enabled MDVM_WIN64_BUILD_CRYPTO
if src=$(pick crypto.dll); then
  cp -a "$src" "$DEST/crypto.dll"
  # ART/conscrypt often look for libcrypto.so naming; provide libcrypto.dll alias
  cp -a "$src" "$DEST/libcrypto.dll"
  echo "stage_native_modules: crypto/libcrypto.dll <- $src"
else
  echo "stage_native_modules: crypto.dll not built (optional L-002); skip"
fi

echo "stage_native_modules: OK real ICU + javacore + openjdk PE under $DEST"
