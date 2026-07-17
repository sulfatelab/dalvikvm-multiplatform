#!/usr/bin/env bash
# Build a boot.jar from nested vendor/libcore (+ vendor/icu) to match libart.
# Pure-vendor: no MinDalvikVM-Archive sibling required.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LC=$REPO/vendor/libcore
ICU=$REPO/vendor/icu/android_icu4j
JSTUBS=$REPO/compat/java-stubs

if [ ! -d "$LC" ]; then
  echo "!! missing $LC (nested vendor/libcore required)" >&2
  exit 1
fi
if [ ! -d "$ICU" ]; then
  echo "!! missing $ICU (nested vendor/icu/android_icu4j required)" >&2
  exit 1
fi
if [ ! -d "$JSTUBS" ]; then
  echo "!! missing $JSTUBS (project annotation stubs for boot javac)" >&2
  exit 1
fi

# Optional escape hatch only: MDVM_ARCHIVE may point at a legacy archive for
# experimental extra sources. Product default is pure multipath vendor/.
ARCHIVE="${MDVM_ARCHIVE:-}"
STUB=""
if [ -n "$ARCHIVE" ] && [ -d "$ARCHIVE/javalib/android-annotation-stub/java" ]; then
  STUB="$ARCHIVE/javalib/android-annotation-stub/java"
  echo "note: also scanning optional archive annotation stub: $STUB" >&2
fi

D8=~/Android/Sdk/cmdline-tools/latest/bin/d8
# JDK 21 javac: android-16.0.0_r4 libcore uses Java 21 language features.
JAVAC=/usr/lib/jvm/java-21-openjdk-amd64/bin/javac
BP2CMAKE=$REPO/tools/bp2cmake
OUT=/tmp/bootbuild
CLASSES=$OUT/classes
GENFLAGS=$OUT/genflags
rm -rf "$CLASSES" "$OUT/srclist.txt" "$GENFLAGS"; mkdir -p "$CLASSES" "$GENFLAGS"

# Generate aconfig Flags classes from .aconfig declarations (all flags default disabled).
PYTHONPATH=$BP2CMAKE python3 - "$GENFLAGS" "$REPO" <<'PY'
import sys
from bp2cmake import aconfig
out = sys.argv[1]
repo = sys.argv[2]
files = [
    f"{repo}/vendor/libcore/libcore.aconfig",
    f"{repo}/vendor/art/build/flags/art-flags.aconfig",
    f"{repo}/vendor/art/build/flags/art-rw-flags.aconfig",
]
written = aconfig.generate_java(files, out)
print("generated Flags classes:", len(written))
PY

for d in \
  "$LC/ojluni/src/main/java" \
  "$LC/libart/src/main/java" \
  "$LC/dalvik/src/main/java" \
  "$LC/luni/src/main/java" \
  "$LC/xml/src/main/java" \
  "$LC/json/src/main/java" \
  "$ICU/src/main/java" \
  "$ICU/libcore_bridge/src/java" \
  "$JSTUBS" \
  "$GENFLAGS" \
  ${STUB:+"$STUB"} ; do
    if [ -z "$d" ]; then
      continue
    fi
    if [ -d "$d" ]; then
      find "$d" -name '*.java' >> "$OUT/srclist.txt"
    else
      echo "WARN: missing source dir $d" >&2
    fi
done
grep -vE 'luni/src/main/java/libcore/net/http/(Dns|HttpURLConnectionFactory)\.java' \
    "$OUT/srclist.txt" > "$OUT/srclist2.txt" && mv "$OUT/srclist2.txt" "$OUT/srclist.txt"
# Prefer ojluni multipath AndroidHardcodedSystemProperties (JAVA_VERSION 1.8.0,
# OS-neutral separators) over the libart copy (JAVA_VERSION "0").
grep -vE 'libart/src/main/java/java/lang/AndroidHardcodedSystemProperties\.java' \
    "$OUT/srclist.txt" > "$OUT/srclist2.txt" && mv "$OUT/srclist2.txt" "$OUT/srclist.txt"
echo "sources: $(wc -l < "$OUT/srclist.txt")"

"$JAVAC" -d "$CLASSES" \
  --system=none \
  --patch-module java.base="$LC/ojluni/src/main/java" \
  -g:none \
  -encoding UTF-8 -XDstringConcat=inline \
  -nowarn -proc:none \
  @"$OUT/srclist.txt" 2>"$OUT/javac.err"
echo "javac exit: $?"
echo "=== first javac errors ==="
grep -E 'error:' "$OUT/javac.err" | head -15
echo "error count: $(grep -c 'error:' "$OUT/javac.err" || true)"
echo "classes compiled: $(find "$CLASSES" -name '*.class' | wc -l)"
