#!/usr/bin/env bash
# Build an Android TrustedCertificateStore system CA directory
# (OpenSSL subject_hash_old PEM files: <8hex>.<n>) from a PEM bundle.
#
# Usage:
#   tools/win64/generate_cacerts.sh <out_dir> [pem_bundle]
#
# Defaults:
#   pem_bundle = /etc/ssl/certs/ca-certificates.crt (host Mozilla/system bundle)
#
# Output is suitable for:
#   $ANDROID_ROOT/etc/security/cacerts
#
set -euo pipefail
OUT="${1:?out dir required}"
BUNDLE="${2:-/etc/ssl/certs/ca-certificates.crt}"

if [[ ! -f "$BUNDLE" ]]; then
  echo "ERROR: PEM bundle not found: $BUNDLE" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl required" >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Split bundle into individual PEMs
awk -v d="$tmp" '
  /BEGIN CERTIFICATE/ { n++; f=sprintf("%s/c%04d.pem", d, n); writing=1 }
  writing { print > f }
  /END CERTIFICATE/ { writing=0; close(f) }
' "$BUNDLE"

count=0
for pem in "$tmp"/c*.pem; do
  [[ -f "$pem" ]] || continue
  # Skip unreadable/invalid
  if ! openssl x509 -in "$pem" -noout >/dev/null 2>&1; then
    continue
  fi
  hash=$(openssl x509 -in "$pem" -noout -subject_hash_old 2>/dev/null | tr -d '\r')
  if [[ -z "$hash" || ! "$hash" =~ ^[0-9a-fA-F]+$ ]]; then
    continue
  fi
  idx=0
  while [[ -e "$OUT/${hash}.${idx}" ]]; do
    idx=$((idx + 1))
  done
  # Android stores PEM (CertificateFactory accepts PEM). Keep text form.
  cp -a "$pem" "$OUT/${hash}.${idx}"
  # Readable for all (product layout)
  chmod 644 "$OUT/${hash}.${idx}"
  count=$((count + 1))
done

if [[ "$count" -lt 1 ]]; then
  echo "ERROR: no certificates generated from $BUNDLE" >&2
  exit 1
fi

# Manifest for packaging checks
{
  echo "# AndroidCAStore system cacerts"
  echo "# source=$BUNDLE"
  echo "# count=$count"
  echo "# generated=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$OUT/MANIFEST.txt"

echo "generate_cacerts: wrote $count certs -> $OUT"
