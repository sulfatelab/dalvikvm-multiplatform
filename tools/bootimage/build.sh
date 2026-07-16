#!/usr/bin/env bash
# Build a boot image (boot.art/boot.oat) from boot.jar using the converted
# dex2oat. This is the AOSP-true ART startup path: dex2oat resolves and lays
# out every boot-classpath class ahead of time, so the imageless
# InitWithoutImage + CheckSystemClass path (the String 779/771 wall) is never
# exercised and core java.* classes (java.lang.Record) need no d8
# --core-library dance. It also makes startup fast.
#
# Mirrors AOSP's bootimage build (art/build/art.go / dex2oat boot invocation):
# --image + --oat-file (multi-image default for boot), a fixed --base, the
# host instruction set. To compile a PRIMARY boot image, --boot-image is
# OMITTED entirely: dex2oat keys off an empty boot_image_filename_ to set
# image_type_=kBootImage (dex2oat.cc:661). Passing --boot-image=none does NOT
# work -- "none" is taken as a literal filename, flips the type to
# kBootImageExtension, and then --base is rejected (dex2oat.cc:776).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
LIBS="$REPO/build/native"
RUN="${MDVM_RUN_DIR:-/tmp/vm/run}"
ISA="${MDVM_ISA:-x86_64}"
# dalvikvm resolves -Ximage:DIR/boot.art to DIR/<isa>/boot.art, so emit the
# artifacts into the <isa> subdir directly (run.sh points -Ximage at the parent).
OUT="${MDVM_BOOTIMG_DIR:-$RUN/boot-image}/$ISA"

BOOTJAR="$RUN/boot.jar"
DEX2OAT="$LIBS/dex2oat"

[ -x "$DEX2OAT" ] || { echo "!! dex2oat not built at $DEX2OAT" >&2; exit 1; }
[ -f "$BOOTJAR" ] || { echo "!! boot.jar not found at $BOOTJAR" >&2; exit 1; }

mkdir -p "$OUT"
rm -f "$OUT"/boot*.art "$OUT"/boot*.oat "$OUT"/boot*.vdex

export LD_LIBRARY_PATH="$LIBS"
export ANDROID_ROOT="$RUN" ANDROID_ART_ROOT="$RUN" ANDROID_I18N_ROOT="$RUN"
export ANDROID_DATA="$RUN/data" ICU_DATA="$RUN/icu"

set -x
timeout 1800 "$DEX2OAT" \
    --dex-file="$BOOTJAR" \
    --dex-location="$BOOTJAR" \
    --image="$OUT/boot.art" \
    --oat-file="$OUT/boot.oat" \
    --base=0x70000000 \
    --instruction-set="$ISA" \
    --image-format=uncompressed \
    --compiler-filter=speed \
    --no-watch-dog \
    --runtime-arg -Xbootclasspath:"$BOOTJAR" \
    --runtime-arg -Xbootclasspath-locations:"$BOOTJAR" \
    --avoid-storing-invocation \
    --generate-debug-info \
    "$@" 2>&1
rc=$?
set +x
echo "=== dex2oat exit=$rc ==="
ls -la "$OUT"
