#!/usr/bin/env bash
# Build boot.jar with WinNT FileSystem (Option H) for Win64 ART.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Reuse main build then overlay WinNT classes from nested libcore artmp fold
bash "$REPO/tools/bootjar/build.sh" || true
OUT=/tmp/bootbuild
CLASSES=$OUT/classes
JAVAC=/usr/lib/jvm/java-21-openjdk-amd64/bin/javac
# Prefer multipath mirrors; fall back to ojluni sources (same content after fold).
WINJAVA=$REPO/vendor/libcore/multiplatform/windows/java/io
WINLANG=$REPO/vendor/libcore/multiplatform/windows/java/lang
if [ ! -f "$WINJAVA/WinNTFileSystem.java" ]; then
  WINJAVA=$REPO/vendor/libcore/ojluni/src/main/java/java/io
  WINLANG=$REPO/vendor/libcore/ojluni/src/main/java/java/lang
fi
if [ ! -d "$CLASSES/java/io" ]; then
  echo "!! run tools/bootjar/build.sh first to populate classes" >&2
  exit 1
fi
# JDK21 --system=none fails to see package java.lang from a plain class tree.
# Use classic -bootclasspath + -source 8 for platform overlays.
SOURCES=(
  "$WINJAVA/WinNTFileSystem.java"
  "$WINJAVA/DefaultFileSystem.java"
)
if [ -f "$WINLANG/AndroidHardcodedSystemProperties.java" ]; then
  SOURCES+=("$WINLANG/AndroidHardcodedSystemProperties.java")
fi
# sun.misc.Version compile-time folds JAVA_VERSION; recompile so java.version is not stuck at "0".
if [ -f "$REPO/vendor/libcore/ojluni/src/main/java/sun/misc/Version.java" ]; then
  SOURCES+=("$REPO/vendor/libcore/ojluni/src/main/java/sun/misc/Version.java")
fi
rm -rf "$OUT/win_overlay"
mkdir -p "$OUT/win_overlay"
"$JAVAC" -d "$OUT/win_overlay" \
  -source 8 -target 8 \
  -bootclasspath "$CLASSES" -classpath "$CLASSES" \
  -encoding UTF-8 -proc:none -Xlint:none -XDstringConcat=inline \
  "${SOURCES[@]}" 2>"$OUT/winfs_javac.err"
echo "winfs javac exit: $?"
grep -E 'error:' "$OUT/winfs_javac.err" | head -20 || true
cp -f "$OUT/win_overlay/java/io/DefaultFileSystem.class" "$CLASSES/java/io/"
cp -f "$OUT/win_overlay/java/io/WinNTFileSystem.class" "$CLASSES/java/io/"
if [ -f "$OUT/win_overlay/java/lang/AndroidHardcodedSystemProperties.class" ]; then
  cp -f "$OUT/win_overlay/java/lang/AndroidHardcodedSystemProperties.class" "$CLASSES/java/lang/"
fi
if [ -f "$OUT/win_overlay/sun/misc/Version.class" ]; then
  mkdir -p "$CLASSES/sun/misc"
  cp -f "$OUT/win_overlay/sun/misc/Version.class" "$CLASSES/sun/misc/"
fi
ls -la "$CLASSES/java/io/DefaultFileSystem.class" "$CLASSES/java/io/WinNTFileSystem.class"
if strings "$CLASSES/java/io/WinNTFileSystem.class" | grep -q 'isLetter'; then
  echo "WARN: WinNTFileSystem still references isLetter (ICU risk)" >&2
else
  echo "OK: no isLetter symbol in WinNTFileSystem.class"
fi
bash "$REPO/tools/bootjar/dex.sh"
mkdir -p "$REPO/build/win64_phase1/run"
cp -f /tmp/bootbuild/boot.jar "$REPO/build/win64_phase1/run/boot.jar"
echo "staged build/win64_phase1/run/boot.jar ($(stat -c%s "$REPO/build/win64_phase1/run/boot.jar") bytes)"
python3 - <<PY
import zipfile
d=zipfile.ZipFile("$REPO/build/win64_phase1/run/boot.jar").read('classes.dex')
print('WinNTFileSystem', b'WinNTFileSystem' in d)
print('DefaultFileSystem', b'DefaultFileSystem' in d)
print('boot.jar dex size', len(d))
PY
