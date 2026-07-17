#!/usr/bin/env bash
# Stage product runtime assets that must ship with every Win64 ART tree,
# same class as boot.jar (required, not optional).
#
# Usage:
#   tools/win64/stage_run_assets.sh <dest_root> [build_dir]
#
# Ensures:
#   <dest_root>/run/boot.jar                    (copied from build if missing in dest)
#   <dest_root>/run/icu/icudt72l.dat             (always present; preferred full data)
#   <dest_root>/run/etc/security/cacerts/*      (AndroidCAStore system roots)
#
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:?dest root required (e.g. build/win64_phase1 or dist/win64_phase3_host)}"
BUILD="${2:-$REPO/build/win64_phase1}"
ASSET_CACERTS="$REPO/tools/win64/assets/cacerts"

mkdir -p "$DEST/run/icu" "$DEST/run/data" "$DEST/run/framework" \
         "$DEST/run/etc/security/cacerts"

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

# --- System CA roots for AndroidCAStore (required product asset; L-002) ---
# Layout matches TrustedCertificateStore: $ANDROID_ROOT/etc/security/cacerts/<hash_old>.N
cacerts_count() {
  local d="$1"
  find "$d" -maxdepth 1 -type f ! -name 'MANIFEST.txt' ! -name 'README*' 2>/dev/null | wc -l | tr -d ' '
}

need_cacerts=0
if [[ "$(cacerts_count "$DEST/run/etc/security/cacerts")" -lt 1 ]]; then
  need_cacerts=1
fi

if [[ "$need_cacerts" -eq 1 ]]; then
  # Prefer already-staged build tree, then hermetic in-repo assets, then regenerate.
  if [[ -d "$BUILD/run/etc/security/cacerts" && \
        "$(cacerts_count "$BUILD/run/etc/security/cacerts")" -ge 1 && \
        "$(cd "$BUILD/run/etc/security/cacerts" && pwd -P)" != "$(cd "$DEST/run/etc/security/cacerts" && pwd -P)" ]]; then
    cp -a "$BUILD/run/etc/security/cacerts/." "$DEST/run/etc/security/cacerts/"
    echo "stage_run_assets: cacerts <- $BUILD/run/etc/security/cacerts"
  elif [[ -d "$ASSET_CACERTS" && "$(cacerts_count "$ASSET_CACERTS")" -ge 1 ]]; then
    cp -a "$ASSET_CACERTS/." "$DEST/run/etc/security/cacerts/"
    echo "stage_run_assets: cacerts <- $ASSET_CACERTS"
  elif [[ -x "$REPO/tools/win64/generate_cacerts.sh" ]]; then
    bash "$REPO/tools/win64/generate_cacerts.sh" "$DEST/run/etc/security/cacerts"
    echo "stage_run_assets: cacerts generated into dest"
  fi
fi

if [[ "$(cacerts_count "$DEST/run/etc/security/cacerts")" -lt 1 ]]; then
  echo "ERROR: cannot stage run/etc/security/cacerts (required product asset like icudt72l.dat)" >&2
  echo "  Generate with: bash tools/win64/generate_cacerts.sh tools/win64/assets/cacerts" >&2
  exit 1
fi

# Ensure ANDROID_DATA keychain dirs exist (user added/deleted CAs).
mkdir -p "$DEST/run/data/misc/keychain/cacerts-added" \
         "$DEST/run/data/misc/keychain/cacerts-removed"

# Optional: stamp size for logs
sz=$(wc -c < "$DEST/run/icu/icudt72l.dat" | tr -d ' ')
nca=$(cacerts_count "$DEST/run/etc/security/cacerts")
echo "stage_run_assets: OK boot.jar + icudt72l.dat (${sz} bytes) + cacerts (${nca}) under $DEST/run/"
