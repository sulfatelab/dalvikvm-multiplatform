#!/usr/bin/env bash
# Build shared multipath boot.jar for Win64 ART (and Linux).
#
# Phase-1 shared boot: one jar contains UnixFileSystem + WinNTFileSystem;
# runtime selection uses dalvik.system.VMRuntime.isWindowsOs() and
# dalvik.vm.multiplatform.internal.os (injected by libart).
#
# Historical "WinNT overlay" that forced DefaultFileSystem → WinNT-only and
# Windows separator hardcodes is no longer applied.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "$REPO/tools/bootjar/build.sh" || true
OUT=/tmp/bootbuild
CLASSES=$OUT/classes
JAVAC=/usr/lib/jvm/java-21-openjdk-amd64/bin/javac

if [ ! -d "$CLASSES/java/io" ]; then
  echo "!! run tools/bootjar/build.sh first to populate classes" >&2
  exit 1
fi

# sun.misc.Version compile-time folds JAVA_VERSION; recompile so java.version
# is not stuck at "0" when libart's AndroidHardcodedSystemProperties wins the
# source list over ojluni (same as historical win overlay).
SOURCES=()
if [ -f "$REPO/vendor/libcore/ojluni/src/main/java/sun/misc/Version.java" ]; then
  SOURCES+=("$REPO/vendor/libcore/ojluni/src/main/java/sun/misc/Version.java")
fi
# Ensure multipath shared classes are compiled from sources (VMRuntime helpers + FS).
for f in \
  "$REPO/vendor/libcore/libart/src/main/java/dalvik/system/VMRuntime.java" \
  "$REPO/vendor/libcore/ojluni/src/main/java/java/io/DefaultFileSystem.java" \
  "$REPO/vendor/libcore/ojluni/src/main/java/java/io/WinNTFileSystem.java" \
  "$REPO/vendor/libcore/ojluni/src/main/java/java/lang/AndroidHardcodedSystemProperties.java" \
  "$REPO/vendor/libcore/ojluni/src/main/java/java/lang/System.java"
do
  if [ -f "$f" ]; then
    SOURCES+=("$f")
  fi
done

if [ "${#SOURCES[@]}" -gt 0 ]; then
  rm -rf "$OUT/shared_overlay"
  mkdir -p "$OUT/shared_overlay"
  "$JAVAC" -d "$OUT/shared_overlay" \
    -source 8 -target 8 \
    -bootclasspath "$CLASSES" -classpath "$CLASSES" \
    -encoding UTF-8 -proc:none -Xlint:none -XDstringConcat=inline \
    "${SOURCES[@]}" 2>"$OUT/shared_fs_javac.err"
  echo "shared_fs javac exit: $?"
  grep -E 'error:' "$OUT/shared_fs_javac.err" | head -20 || true
  # Install any produced classes
  if [ -d "$OUT/shared_overlay/java" ]; then
    cp -a "$OUT/shared_overlay/java/." "$CLASSES/java/" 2>/dev/null || true
  fi
  if [ -f "$OUT/shared_overlay/sun/misc/Version.class" ]; then
    mkdir -p "$CLASSES/sun/misc"
    cp -f "$OUT/shared_overlay/sun/misc/Version.class" "$CLASSES/sun/misc/"
  fi
fi

ls -la "$CLASSES/java/io/DefaultFileSystem.class" \
       "$CLASSES/java/io/WinNTFileSystem.class" \
       "$CLASSES/java/io/UnixFileSystem.class" \
       "$CLASSES/dalvik/system/VMRuntime.class" 2>&1 || true

if strings "$CLASSES/java/io/WinNTFileSystem.class" | grep -q 'isLetter'; then
  echo "WARN: WinNTFileSystem still references isLetter (ICU risk)" >&2
else
  echo "OK: no isLetter symbol in WinNTFileSystem.class"
fi

bash "$REPO/tools/bootjar/dex.sh"
mkdir -p "$REPO/build/win64_phase1/run"
cp -f /tmp/bootbuild/boot.jar "$REPO/build/win64_phase1/run/boot.jar"
# Also stage a Linux-shared copy for L-005 if desired
mkdir -p /tmp/vm/run
cp -f /tmp/bootbuild/boot.jar /tmp/vm/run/boot.jar
echo "staged build/win64_phase1/run/boot.jar ($(stat -c%s "$REPO/build/win64_phase1/run/boot.jar") bytes)"
echo "staged /tmp/vm/run/boot.jar (shared multipath)"
python3 - <<PY
import zipfile
d=zipfile.ZipFile("$REPO/build/win64_phase1/run/boot.jar").read('classes.dex')
for s in [b'WinNTFileSystem', b'UnixFileSystem', b'isWindowsOs',
          b'dalvik.vm.multiplatform.internal.os', b'DefaultFileSystem']:
    print(s.decode(errors='replace'), s in d)
print('boot.jar dex size', len(d))
PY
