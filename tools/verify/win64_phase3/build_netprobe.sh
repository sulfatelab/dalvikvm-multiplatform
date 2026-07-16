#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
JAVAC="${JAVAC:-/usr/lib/jvm/java-21-openjdk-amd64/bin/javac}"
R8JAR="${R8JAR:-$REPO/vendor/r8/r8.jar}"
D8=(java -Dcom.android.tools.r8.emitRecordAnnotationsInDex=1 -cp "$R8JAR" com.android.tools.r8.D8)
OUT="$REPO/tools/verify/win64_phase3/bin"
SRC="$REPO/tools/verify/win64_phase3/src/NetProbe.java"
rm -rf "$OUT/netclasses" "$OUT/netdex"
mkdir -p "$OUT/netclasses" "$OUT/netdex"
"$JAVAC" -d "$OUT/netclasses" "$SRC"
"${D8[@]}" --release --min-api 31 --output "$OUT/netdex" "$OUT/netclasses/NetProbe.class"
python3 - <<PY
import zipfile, os
repo=r'''$REPO'''
dex=os.path.join(repo,'tools/verify/win64_phase3/bin/netdex/classes.dex')
out=os.path.join(repo,'build/win64_phase1/run/netprobe.jar')
with zipfile.ZipFile(out,'w') as z: z.write(dex,'classes.dex')
print('wrote', out, os.path.getsize(out))
PY
