#!/usr/bin/env bash
# AST-assisted LLP64 cast scan using compile_commands.json + clang-query.
#
# Prerequisites:
#   cmake ... -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
#   clang-query (LLVM 18+)
#
# Usage:
#   tools/verify/llp64_ptr_cast_audit/scan_ast.sh build/win64_libcore_icu [file ...]
set -euo pipefail
DB="${1:?compile_commands directory (e.g. build/win64_libcore_icu)}"
shift || true
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
if [[ ! -f "$DB/compile_commands.json" ]]; then
  echo "missing $DB/compile_commands.json" >&2
  exit 2
fi
QUERY=$(command -v clang-query-21 || command -v clang-query)
# Default critical product files
if [[ $# -eq 0 ]]; then
  set -- \
    vendor/libcore/ojluni/src/main/native/FileChannelImpl.c \
    vendor/libcore/ojluni/src/main/native/FileDispatcherImpl.c \
    vendor/libcore/ojluni/src/main/native/MappedByteBuffer.c \
    vendor/libcore/ojluni/src/main/native/IOUtil.c \
    vendor/libcore/luni/src/main/native/libcore_io_Memory.cpp \
    tools/win64/jni_stubs/win_fs_natives.c \
    tools/verify/win64_libcore_icu/openjdkjvm_memory_standalone.c
fi

echo "clang-query via -p $DB"
echo "Note: SDK headers (basetsd.h HANDLE_TO_LONG etc.) will match; filter to repo paths."
echo

for f in "$@"; do
  [[ -f "$f" ]] || { echo "skip missing $f"; continue; }
  echo "==== $f ===="
  # C-style casts whose type is long / unsigned long (may include non-pointer)
  "$QUERY" -p "$DB" "$f" \
    -c 'set bind-root false' \
    -c 'm cStyleCastExpr(hasType(asString("long"))).bind("to_long")' \
    -c 'm cStyleCastExpr(hasType(asString("unsigned long"))).bind("to_ulong")' \
    2>/dev/null | rg -n "note:|Match #|$ROOT/vendor|$ROOT/tools|$ROOT/compat" || true
  echo
done

echo "Done. Cross-check HIGH hits with scan_text.py; prefer ptr_to_jlong/jlong_to_ptr/uintptr_t."
