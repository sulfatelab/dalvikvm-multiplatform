#!/usr/bin/env bash
# Stage real Win64 PE native modules for product trees (L-004: one name each).
#
# ART InitNativeMethods loads (Windows):
#   libicu_jni.dll, libjavacore.dll, libopenjdk.dll
# Supporting PE (dependency / optional):
#   icuuc.dll, icui18n.dll, libopenjdkjvm.dll, libcrypto.dll
#
# Build artifacts may use the same OUTPUT_NAME. Product trees do NOT ship
# short-name duplicates (icu_jni.dll / javacore.dll / openjdk.dll / crypto.dll).
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

# Resolve a product soname from either product name or legacy short build name.
pick_module() {
  local product="$1"
  shift
  local alt
  if src=$(pick "$product"); then
    echo "$src"
    return 0
  fi
  for alt in "$@"; do
    if src=$(pick "$alt"); then
      echo "$src"
      return 0
    fi
  done
  return 1
}

require_copy_as() {
  local product_name="$1"
  shift
  local src
  if ! src=$(pick_module "$product_name" "$@"); then
    echo "ERROR: missing required real PE module: $product_name (also tried: $*)" >&2
    echo "  Build hybrid: cmake --build build/win64_libcore_icu --target icuuc icui18n icu_jni javacore openjdk openjdkjvm" >&2
    echo "  Then: bash tools/verify/win64_libcore_icu/install_into_phase1.sh" >&2
    echo "  libcombined multi-name stubs are NOT accepted for product (W-005)." >&2
    exit 1
  fi
  if [[ "$src" == *"/jni_stubs/libcombined.dll" ]]; then
    echo "ERROR: refusing libcombined.dll for $product_name (W-005)" >&2
    exit 1
  fi
  cp -a "$src" "$DEST/$product_name"
  # Drop legacy short-name twin if present so packages do not keep dual copies.
  local base="${product_name#lib}"
  if [[ "$base" != "$product_name" && -f "$DEST/$base" ]]; then
    rm -f "$DEST/$base"
  fi
  echo "stage_native_modules: $product_name <- $src"
}

# Supporting ICU (short names are the real DLL basenames used by imports)
require_copy_as icuuc.dll
require_copy_as icui18n.dll
require_copy_as libopenjdkjvm.dll openjdkjvm.dll

# ART-loaded modules (single product name each)
require_copy_as libicu_jni.dll icu_jni.dll
require_copy_as libjavacore.dll javacore.dll
require_copy_as libopenjdk.dll openjdk.dll

# Remove any residual short duplicates explicitly
rm -f "$DEST/icu_jni.dll" "$DEST/javacore.dll" "$DEST/openjdk.dll" \
      "$DEST/openjdkjvm.dll" "$DEST/crypto.dll" 2>/dev/null || true

# Sanity vs legacy combined
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

# Optional crypto PE (L-002): single product name libcrypto.dll
if src=$(pick_module libcrypto.dll crypto.dll); then
  cp -a "$src" "$DEST/libcrypto.dll"
  rm -f "$DEST/crypto.dll" 2>/dev/null || true
  echo "stage_native_modules: libcrypto.dll <- $src"
else
  echo "stage_native_modules: libcrypto.dll not built (optional L-002); skip"
fi

# Distinctness check (three ART load modules must differ)
h1=$(md5sum "$DEST/libicu_jni.dll" | awk '{print $1}')
h2=$(md5sum "$DEST/libjavacore.dll" | awk '{print $1}')
h3=$(md5sum "$DEST/libopenjdk.dll" | awk '{print $1}')
if [[ "$h1" == "$h2" || "$h2" == "$h3" || "$h1" == "$h3" ]]; then
  echo "ERROR: ART load modules are not distinct PE images" >&2
  exit 1
fi

echo "stage_native_modules: OK single-name product PE under $DEST"
echo "  (libicu_jni, libjavacore, libopenjdk + icuuc/icui18n/libopenjdkjvm [+libcrypto])"
