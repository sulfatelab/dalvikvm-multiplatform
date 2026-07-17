#!/usr/bin/env bash
# Regenerate the native build description from Android.bp.
#
# Emits generated/dalvikvm.cmake = the full transitive dependency closure of the
# `dalvikvm` root module (18 targets), converted from nested vendor/ Android.bp
# by bp2cmake. Run this after a submodule bump or an overlay change; the
# top-level CMakeLists.txt include()s the result. This replaces the old
# per-module verify harnesses and the hand-maintained --module list.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
SRC_ROOT="${MDVM_NATIVE_SRC_ROOT:-$REPO/vendor}"
VENDOR="$REPO/vendor"

# Pure multipath (L-006): SRC_ROOT defaults to nested vendor/. art + libcore
# live under vendor/ at a coherent AOSP snapshot (android-16.0.0_r4).
# --exclude-top art avoids double-loading if a layout still nests art oddly;
# vendor/art is loaded via --extra-root so module bp_dirs keep `art/...`
# prefixes against MDVM_ART_ROOT_DIR.
COMMON_ARGS=(
    --root "$SRC_ROOT"
    --exclude-top art
    --overlay "$REPO/overlay/port_policy.py"
    --extra-root "$VENDOR:MDVM_ART_ROOT_DIR"
    --extra-root "$VENDOR/libcore:MDVM_LIBCORE_DIR"
    --extra-root "$VENDOR/icu:MDVM_ICU_DIR"
    --extra-root "$VENDOR/java-external/fdlibm:MDVM_FDLIBM_DIR"
    --root-module dalvikvm
    --root-module dex2oat
    --root-module libjavacore
    --root-module libopenjdk
    --root-module libicu_jni
)

mkdir -p "$HERE/generated"
PYTHONPATH="$REPO/tools/bp2cmake" python3 -m bp2cmake \
    "${COMMON_ARGS[@]}" --out "$HERE/generated/dalvikvm.cmake"

echo "Generated targets:"
PYTHONPATH="$REPO/tools/bp2cmake" python3 -m bp2cmake \
    "${COMMON_ARGS[@]}" --list-only 2>/dev/null | sed 's/^/  /'
