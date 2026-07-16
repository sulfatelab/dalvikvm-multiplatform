#!/usr/bin/env bash
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT=/tmp/bootbuild
CLASSES=$OUT/classes
# Run r8/D8 with the platform record property.
R8JAR="${MDVM_R8JAR:-$REPO/vendor/r8/r8.jar}"
if [ ! -f "$R8JAR" ]; then
  # Fallback to sibling dalvikvm-linux tree during migration.
  R8JAR=/home/agent/Projects/dalvikvm-linux/vendor/r8/r8.jar
fi
D8="java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 -cp $R8JAR com.android.tools.r8.D8"
rm -rf "$OUT/dex"; mkdir -p "$OUT/dex"

find "$CLASSES" -name '*.class' > "$OUT/classlist.txt"
echo "classes to dex: $(wc -l < "$OUT/classlist.txt")"

# Dex with AOSP r8/D8 in --android-platform-build mode.
# emitRecordAnnotationsInDex=1 keeps java.lang.Record in boot dex.
timeout 600 $D8 --release --min-api 31 --android-platform-build \
    --output "$OUT/boot.jar" \
    @"$OUT/classlist.txt" 2>"$OUT/d8.err"
rc=$?
echo "d8 exit: $rc"
[ $rc -ne 0 ] && { echo "=== d8 errors ==="; grep -iE 'error|exception' "$OUT/d8.err" | head -10; }
echo "boot.jar: $(ls -la "$OUT/boot.jar" 2>/dev/null | awk '{print $5}') bytes"
python3 -c "import zipfile;z=zipfile.ZipFile('$OUT/boot.jar');print('dex entries:',[n for n in z.namelist() if n.endswith('.dex')])" 2>/dev/null
python3 -c "import zipfile; d=zipfile.ZipFile('$OUT/boot.jar').read('classes.dex'); print('java.lang.Record present:', b'Ljava/lang/Record;' in d)" 2>/dev/null
