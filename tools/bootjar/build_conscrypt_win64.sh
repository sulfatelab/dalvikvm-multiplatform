#!/usr/bin/env bash
# L-002 C2: compile platform conscrypt (jarjar com.android.org.conscrypt) into
# boot classes, package security.properties, re-dex boot.jar for Win64 ART.
#
# Prerequisites:
#   - /tmp/bootbuild/classes from tools/bootjar/build.sh (+ optional build_win64 overlay)
#   - JDK 21 javac
#   - vendor/r8/r8.jar for dex
#   - host g++ + boringssl headers for NativeConstants
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CS="$REPO/vendor/java-external/conscrypt"
BOOT_CLASSES="${MDVM_BOOT_CLASSES:-/tmp/bootbuild/classes}"
OUT="${MDVM_CONSCRYPT_OUT:-/tmp/conscrypt_build}"
JAVAC="${MDVM_JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
STAGE_BOOT="${MDVM_STAGE_BOOT:-$REPO/build/win64_phase1/run/boot.jar}"

if [[ ! -d "$BOOT_CLASSES/java/lang" ]]; then
  echo "ERROR: missing boot classes at $BOOT_CLASSES (run tools/bootjar/build.sh first)" >&2
  exit 1
fi

mkdir -p "$OUT/gen/com/android/org/conscrypt" "$OUT/classes"

# --- NativeConstants via boringssl headers (host tool, no PE link needed) ---
if [[ ! -x "$OUT/generate_constants" ]]; then
  g++ -std=c++17 -O0 \
    -I"$REPO/vendor/external/boringssl/src/include" \
    "$CS/constants/src/gen/cpp/generate_constants.cc" \
    -o "$OUT/generate_constants"
fi
"$OUT/generate_constants" com.android.org.conscrypt \
  > "$OUT/gen/com/android/org/conscrypt/NativeConstants.java"

# --- source list: repackaged platform conscrypt + public API ---
: > "$OUT/srclist.txt"
find "$CS/repackaged/common/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
find "$CS/repackaged/platform/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
find "$CS/publicapi/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
echo "$OUT/gen/com/android/org/conscrypt/NativeConstants.java" >> "$OUT/srclist.txt"
echo "conscrypt sources: $(wc -l < "$OUT/srclist.txt")"

# Compile into a dedicated tree, then merge into boot classes.
if [[ -d "$OUT/classes" ]]; then
  find "$OUT/classes" -mindepth 1 -delete
fi
"$JAVAC" -d "$OUT/classes" \
  -source 8 -target 8 \
  -bootclasspath "$BOOT_CLASSES" \
  -classpath "$BOOT_CLASSES" \
  -encoding UTF-8 -proc:none -Xlint:none -nowarn -g:none \
  @"$OUT/srclist.txt"
echo "conscrypt classes: $(find "$OUT/classes" -name '*.class' | wc -l)"

# Merge into boot class tree
cp -a "$OUT/classes/." "$BOOT_CLASSES/"

# --- security.properties (resource next to java.security.Security) ---
# C2: conscrypt + CertPath only. BC (provider.3 in AOSP) deferred until
# bouncycastle is packaged; Providers.removeInvalid asserts all entries load.
mkdir -p "$BOOT_CLASSES/java/security"
cat > "$BOOT_CLASSES/java/security/security.properties" <<'PROPS'
# Win64 ART multipath boot security.properties (L-002 C2)
# AndroidOpenSSL = conscrypt OpenSSLProvider
security.provider.1=com.android.org.conscrypt.OpenSSLProvider
security.provider.2=sun.security.provider.CertPathProvider
security.provider.3=com.android.org.conscrypt.JSSEProvider

ssl.SocketFactory.provider=com.android.org.conscrypt.OpenSSLSocketFactoryImpl
ssl.ServerSocketFactory.provider=com.android.org.conscrypt.OpenSSLSocketFactoryImpl
keystore.type=AndroidCAStore
ssl.KeyManagerFactory.algorithm=PKIX
ssl.TrustManagerFactory.algorithm=PKIX
ssl.disablePeerCertificateChainVerification=false
jdk.certpath.disabledAlgorithms=MD2, MD4, RSA keySize < 1024, DSA keySize < 1024, EC keySize < 160
securerandom.strongAlgorithms=SHA1PRNG:AndroidOpenSSL
PROPS

# Re-dex full boot tree
bash "$REPO/tools/bootjar/dex.sh"

# D8 only packages .class → classes.dex. Re-add security.properties resource.
python3 - <<PY
import zipfile
from pathlib import Path
boot = Path("/tmp/bootbuild/boot.jar")
props = Path("$BOOT_CLASSES/java/security/security.properties")
# rewrite jar with resource
data = boot.read_bytes()
# use temp then replace
out = Path("/tmp/bootbuild/boot_with_props.jar")
with zipfile.ZipFile(boot, "r") as zin, zipfile.ZipFile(out, "w") as zout:
    for item in zin.infolist():
        zout.writestr(item, zin.read(item.filename))
    # Android Security looks up resource relative to java.security package
    zout.writestr("java/security/security.properties", props.read_bytes())
out.replace(boot)
print("boot.jar entries:", zipfile.ZipFile(boot).namelist())
d = zipfile.ZipFile(boot).read("classes.dex")
print("NativeCrypto", b"NativeCrypto" in d)
print("OpenSSLProvider", b"OpenSSLProvider" in d)
print("Lcom/android/org/conscrypt/", b"Lcom/android/org/conscrypt/" in d)
print("javacrypto", b"javacrypto" in d)
print("dex size", len(d))
PY

mkdir -p "$(dirname "$STAGE_BOOT")"
cp -f /tmp/bootbuild/boot.jar "$STAGE_BOOT"
echo "staged $STAGE_BOOT ($(stat -c%s "$STAGE_BOOT") bytes)"
