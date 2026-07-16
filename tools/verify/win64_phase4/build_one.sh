#!/usr/bin/env bash
set -euo pipefail
# Build a Phase-4 probe jar into build/win64_phase1/run using the same pipeline as phase3.
CLS="${1:?class name}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
D8=(java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 -cp "$R8JAR" com.android.tools.r8.D8)
OUT="$REPO/tools/verify/win64_phase4/bin"
SRC="$REPO/tools/verify/win64_phase4/src/${CLS}.java"
rm -rf "$OUT/${CLS}_classes" "$OUT/${CLS}_dex"
mkdir -p "$OUT/${CLS}_classes" "$OUT/${CLS}_dex"
"$JAVAC" -d "$OUT/${CLS}_classes" "$SRC"
"${D8[@]}" --release --min-api 31 --output "$OUT/${CLS}_dex" "$OUT/${CLS}_classes/${CLS}.class"
python3 - <<PY
import zipfile, os
repo=r'''$REPO'''
cls=r'''$CLS'''
dex=os.path.join(repo,f'tools/verify/win64_phase4/bin/{cls}_dex/classes.dex')
out=os.path.join(repo,f'build/win64_phase1/run/{cls.lower()}.jar')
with zipfile.ZipFile(out,'w') as z: z.write(dex,'classes.dex')
print('wrote', out, os.path.getsize(out))
PY
