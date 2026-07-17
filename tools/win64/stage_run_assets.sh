#!/usr/bin/env bash
# Stage product runtime assets that must ship with every Win64 ART tree,
# same class as boot.jar (required, not optional).
#
# Usage:
#   tools/win64/stage_run_assets.sh <dest_root> [build_dir]
#
# Ensures:
#   <dest_root>/run/boot.jar          (copied from build if missing in dest)
#   <dest_root>/run/icu/icudt72l.dat  (always present; preferred full data)
#
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:?dest root required (e.g. build/win64_phase1 or dist/win64_phase3_host)}"
BUILD="${2:-$REPO/build/win64_phase1}"

mkdir -p "$DEST/run/icu" "$DEST/run/data" "$DEST/run/framework"

# --- boot.jar (required) ---
if [[ -f "$DEST/run/boot.jar" ]]; then
  : # already present
elif [[ -f "$BUILD/run/boot.jar" ]]; then
  cp -a "$BUILD/run/boot.jar" "$DEST/run/boot.jar"
else
  echo "ERROR: missing boot.jar (looked in $BUILD/run/boot.jar and $DEST/run/boot.jar)" >&2
  exit 1
fi

# --- ICU data (required product asset; W-016) ---
# Prefer an already-staged full tree under BUILD, then other known full copies.
# vendor/.../stubdata/icudt72l.dat is the AOSP-checked-in data package used by this tree.
if [[ -d "$BUILD/run/icu" && "$(cd "$BUILD/run/icu" && pwd -P)" != "$(cd "$DEST/run/icu" && pwd -P)" ]]; then
  # Copy any extra files from build staging when dest differs.
  cp -a "$BUILD/run/icu/." "$DEST/run/icu/" 2>/dev/null || true
fi

if [[ ! -f "$DEST/run/icu/icudt72l.dat" ]]; then
  for cand in \
      "$BUILD/run/icu/icudt72l.dat" \
      "$REPO/vendor/icu/icu4c/source/stubdata/icudt72l.dat" \
      "$REPO/dist/win64_phase3_host/run/icu/icudt72l.dat"; do
    if [[ -f "$cand" ]]; then
      cp -a "$cand" "$DEST/run/icu/icudt72l.dat"
      echo "stage_run_assets: icudt72l.dat <- $cand"
      break
    fi
  done
fi

if [[ ! -f "$DEST/run/icu/icudt72l.dat" ]]; then
  echo "ERROR: cannot stage run/icu/icudt72l.dat (required product asset like boot.jar)" >&2
  exit 1
fi

# Optional: stamp size for logs
sz=$(wc -c < "$DEST/run/icu/icudt72l.dat" | tr -d ' ')
echo "stage_run_assets: OK boot.jar + icudt72l.dat (${sz} bytes) under $DEST/run/"
