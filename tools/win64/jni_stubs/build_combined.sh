#!/usr/bin/env bash
# Build Phase-3 PE JNI combined stub (libjavacore/libopenjdk/libicu_jni stand-in).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
source "${WIN64_DEV_ENV:-/home/agent/Projects/win64-dev-env}/env.sh"
cd "$ROOT"
CFLAGS=(
  --target=x86_64-pc-windows-msvc -O2 -fms-compatibility -fms-extensions
  -I/home/agent/Projects/MinDalvikVM-Archive/native/libnativehelper/include_jni
  -isystem"$WIN64_DEV_ENV/xwin/sdk/include/ucrt"
  -isystem"$WIN64_DEV_ENV/xwin/sdk/include/shared"
  -isystem"$WIN64_DEV_ENV/xwin/sdk/include/um"
  -isystem"$WIN64_DEV_ENV/xwin/crt/include"
  -D_CRT_SECURE_NO_WARNINGS
)
for src in libcore_hello3.c native_converter.c win_path.c win_fs_natives.c win_net_natives.c win_runtime_natives.c; do
  clang "${CFLAGS[@]}" -c "$src" -o "${src%.c}.obj"
done
clang++ --target=x86_64-pc-windows-msvc -shared -fuse-ld=lld \
  -L"$WIN64_DEV_ENV/xwin/sdk/lib/ucrt/x86_64" \
  -L"$WIN64_DEV_ENV/xwin/sdk/lib/um/x86_64" \
  -L"$WIN64_DEV_ENV/xwin/crt/lib/x86_64" \
  -Xlinker /OPT:NOREF \
  -o libcombined.dll libcore_hello3.obj native_converter.obj win_path.obj win_fs_natives.obj win_net_natives.obj win_runtime_natives.obj \
  -lkernel32 -lws2_32 -lucrt -lmsvcrt
echo "built $ROOT/libcombined.dll"
llvm-objdump -p libcombined.dll | rg "WinNTFileSystem_getBoolean|Linux_open|path.separator|writeBytes" | head
