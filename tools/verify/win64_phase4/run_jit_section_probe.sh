#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
WIN64_DEV_ENV="${WIN64_DEV_ENV:-/home/agent/Projects/win64-dev-env}"
SRC="$REPO/tools/verify/win64_phase4/src/JitSectionProbe.c"
OUT_DIR="$REPO/build/win64_phase1/probes"
OUT="$OUT_DIR/JitSectionProbe.exe"

mkdir -p "$OUT_DIR"

clang --target=x86_64-pc-windows-msvc -O2 \
  -D_WIN32_WINNT=0x0A00 -DNTDDI_VERSION=0x0A000005 \
  -DWIN32_LEAN_AND_MEAN -DNOMINMAX \
  -isystem /usr/lib/llvm-21/lib/clang/21/include \
  -isystem "$WIN64_DEV_ENV/xwin/sdk/include/ucrt" \
  -isystem "$WIN64_DEV_ENV/xwin/sdk/include/shared" \
  -isystem "$WIN64_DEV_ENV/xwin/sdk/include/um" \
  -isystem "$WIN64_DEV_ENV/xwin/crt/include" \
  -nostdlib -fuse-ld=lld-link \
  -Xlinker /entry:mainCRTStartup -Xlinker /subsystem:console \
  -L"$WIN64_DEV_ENV/xwin/sdk/lib/um/x86_64" \
  -L"$WIN64_DEV_ENV/xwin/crt/lib/x86_64" \
  -lonecore -lmsvcrt \
  "$SRC" -o "$OUT"

WINEDEBUG="${WINEDEBUG:--all}" wine "$OUT"
