#!/usr/bin/env bash
# Run Hello.main() against the dex2oat-built boot image (boot.art/boot.oat).
# Contrast with /tmp/vm/run_beta4.sh, which used -Ximage:/nonexistent to force
# the slow imageless InitWithoutImage path. Here -Ximage points at the
# precompiled boot image, so class layouts (String) and core classes
# (java.lang.Record) come from the image -- the two imageless walls are gone.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LIBS="$REPO/build/native"
RUN="${MDVM_RUN_DIR:-/tmp/vm/run}"
IMG="${MDVM_BOOTIMG_DIR:-$RUN/boot-image}/boot.art"
OUT="${1:-/tmp/vm/hello-image.txt}"

pkill -9 -f dalvikvm 2>/dev/null; sleep 1
export ANDROID_ROOT="$RUN" ANDROID_ART_ROOT="$RUN" ANDROID_I18N_ROOT="$RUN"
export ANDROID_DATA="$RUN/data" ICU_DATA="$RUN/icu" LD_LIBRARY_PATH="$LIBS"

timeout 120 "$LIBS/dalvikvm" \
    -Xbootclasspath:"$RUN/boot.jar" -Xbootclasspath-locations:"$RUN/boot.jar" \
    -Ximage:"$IMG" \
    -cp "$RUN/hello.jar" Hello >"$OUT" 2>&1
echo "EXIT=$? at $(date +%T)" >>"$OUT"
pkill -9 -f dalvikvm 2>/dev/null
echo "done: $(wc -l <"$OUT") lines -> $OUT"
tail -20 "$OUT"
