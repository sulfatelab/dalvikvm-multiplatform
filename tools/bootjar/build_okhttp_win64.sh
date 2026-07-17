#!/usr/bin/env bash
# L-002: compile Android-repackaged OkHttp (com.android.okhttp + okio) into
# boot classes and re-dex boot.jar so URL.openConnection() can resolve
# HttpHandler / HttpsHandler.
#
# Prerequisites:
#   - /tmp/bootbuild/classes from tools/bootjar/build.sh (+ conscrypt already merged)
#   - JDK javac
#   - vendor/r8/r8.jar for dex
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OKHTTP="$REPO/vendor/java-external/okhttp"
BOOT_CLASSES="${MDVM_BOOT_CLASSES:-/tmp/bootbuild/classes}"
OUT="${MDVM_OKHTTP_OUT:-/tmp/okhttp_build}"
JAVAC="${MDVM_JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
STAGE_BOOT="${MDVM_STAGE_BOOT:-$REPO/build/win64_phase1/run/boot.jar}"

if [[ ! -d "$BOOT_CLASSES/java/lang" ]]; then
  echo "ERROR: missing boot classes at $BOOT_CLASSES (run tools/bootjar/build.sh first)" >&2
  exit 1
fi
if [[ ! -d "$OKHTTP/repackaged" ]]; then
  echo "ERROR: missing $OKHTTP/repackaged" >&2
  exit 1
fi

mkdir -p "$OUT/classes"
: > "$OUT/srclist.txt"

# Same set as okhttp_impl_files in Android.bp
find "$OKHTTP/repackaged/android/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
find "$OKHTTP/repackaged/okhttp/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
find "$OKHTTP/repackaged/okhttp-urlconnection/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
find "$OKHTTP/repackaged/okhttp-android-support/src/main/java" -name '*.java' >> "$OUT/srclist.txt"
find "$OKHTTP/repackaged/okio/okio/src/main/java" -name '*.java' >> "$OUT/srclist.txt"

# Exclude nothing by default; Platform.java is the Android one under repackaged/android.
echo "okhttp sources: $(wc -l < "$OUT/srclist.txt")"

# Clean OUT/classes
find "$OUT/classes" -mindepth 1 -delete 2>/dev/null || true

set +e
"$JAVAC" -d "$OUT/classes" \
  -source 8 -target 8 \
  -bootclasspath "$BOOT_CLASSES" \
  -classpath "$BOOT_CLASSES" \
  -encoding UTF-8 -proc:none -Xlint:none -nowarn -g:none \
  @"$OUT/srclist.txt" 2>"$OUT/javac.err"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "javac failed (exit $rc); first errors:" >&2
  rg -n 'error:|error ' "$OUT/javac.err" | head -40 >&2 || head -40 "$OUT/javac.err" >&2
  exit $rc
fi

nclass=$(find "$OUT/classes" -name '*.class' | wc -l | tr -d ' ')
echo "okhttp classes: $nclass"
if [[ "$nclass" -lt 50 ]]; then
  echo "ERROR: unexpectedly few okhttp classes" >&2
  exit 1
fi

# Merge into boot class tree
cp -a "$OUT/classes/." "$BOOT_CLASSES/"
echo "merged okhttp into $BOOT_CLASSES"

# Re-dex full boot tree
bash "$REPO/tools/bootjar/dex.sh"

# Re-add security.properties resource (D8 only packages .class)
python3 - <<'PY'
import zipfile
from pathlib import Path
import os
boot = Path(os.environ.get("OUT_BOOT", "/tmp/bootbuild/boot.jar"))
props = Path(os.environ.get("BOOT_CLASSES", "/tmp/bootbuild/classes")) / "java/security/security.properties"
if not props.exists():
    raise SystemExit(f"missing {props}")
src = zipfile.ZipFile(boot, "r")
out = boot.with_suffix(".withprops.jar")
with zipfile.ZipFile(out, "w") as dst:
    for info in src.infolist():
        if info.filename == "java/security/security.properties":
            continue
        dst.writestr(info, src.read(info.filename))
    dst.writestr("java/security/security.properties", props.read_bytes())
src.close()
out.replace(boot)
print("reinserted security.properties into", boot)
# sanity: handlers in dex
d = zipfile.ZipFile(boot).read("classes.dex")
for s in [b"Lcom/android/okhttp/HttpsHandler;", b"Lcom/android/okhttp/HttpHandler;", b"Lcom/android/okhttp/okio/Buffer;"]:
    print(s.decode(), s in d)
PY

if [[ -n "${STAGE_BOOT}" ]]; then
  mkdir -p "$(dirname "$STAGE_BOOT")"
  cp -f /tmp/bootbuild/boot.jar "$STAGE_BOOT"
  echo "staged $STAGE_BOOT ($(wc -c < "$STAGE_BOOT" | tr -d ' ') bytes)"
fi

echo "build_okhttp_win64: OK"
