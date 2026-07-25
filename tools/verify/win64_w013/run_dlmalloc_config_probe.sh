#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
WIN64_DEV_ENV="${WIN64_DEV_ENV:-/home/agent/Projects/win64-dev-env}"
OUT_DIR="$REPO/build/win64_phase1/probes"
OUT="$OUT_DIR/W013DlmallocConfigProbe.exe"
ART_DLMALLOC="$REPO/vendor/art/runtime/gc/allocator/art-dlmalloc.cc"

if rg -n '^#\s*undef\s+(_WIN32|WIN32)\b' "$ART_DLMALLOC"; then
  echo "W013_DLMALLOC_CONFIG_FAIL: art-dlmalloc.cc masks Windows platform macros" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

clang --target=x86_64-pc-windows-msvc -std=c11 -O2 \
  -D_WIN32_WINNT=0x0A00 -DNTDDI_VERSION=0x0A000005 \
  -isystem /usr/lib/llvm-21/lib/clang/21/include \
  -isystem "$WIN64_DEV_ENV/xwin/sdk/include/ucrt" \
  -isystem "$WIN64_DEV_ENV/xwin/sdk/include/shared" \
  -isystem "$WIN64_DEV_ENV/xwin/sdk/include/um" \
  -isystem "$WIN64_DEV_ENV/xwin/crt/include" \
  -I"$REPO/vendor/external/dlmalloc" \
  -nostdlib -fuse-ld=lld-link \
  -Xlinker /entry:mainCRTStartup -Xlinker /subsystem:console \
  -L"$WIN64_DEV_ENV/xwin/sdk/lib/um/x86_64" \
  -L"$WIN64_DEV_ENV/xwin/sdk/lib/ucrt/x86_64" \
  -L"$WIN64_DEV_ENV/xwin/crt/lib/x86_64" \
  -lonecore -lmsvcrt -lvcruntime -lucrt \
  "$REPO/tools/verify/win64_w013/W013DlmallocConfigProbe.c" \
  -o "$OUT"

WINEDEBUG="${WINEDEBUG:--all}" wine "$OUT"
