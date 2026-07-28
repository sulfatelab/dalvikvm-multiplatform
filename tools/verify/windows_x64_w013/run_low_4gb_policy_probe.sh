#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
RUNTIME="$REPO/vendor/art/runtime/runtime.cc"
CARD_TABLE_CC="$REPO/vendor/art/runtime/gc/accounting/card_table.cc"
CARD_TABLE_H="$REPO/vendor/art/runtime/gc/accounting/card_table.h"
HEAP_INL="$REPO/vendor/art/runtime/gc/heap-inl.h"

if rg -n 'windows_x64_low_4gb|MarkCard OOB|Windows x64 NonMoving WB|must match low-4g heap' \
    "$RUNTIME" "$CARD_TABLE_CC" "$CARD_TABLE_H" "$HEAP_INL"; then
  echo "W013_LOW_4GB_POLICY_FAIL: temporary Windows x64 forced-low or write-barrier workaround remains" >&2
  exit 1
fi

for required in \
    'MemMapArenaPool\(/\* low_4gb= \*/ false\)' \
    'MemMapArenaPool\(/\* low_4gb= \*/ false, "CompilerMetadata"\)' \
    'const bool low_4gb = IsAotCompiler\(\) && Is64BitInstructionSet\(kRuntimeISA\)'; do
  if ! rg -q "$required" "$RUNTIME"; then
    echo "W013_LOW_4GB_POLICY_FAIL: runtime metadata placement diverged: $required" >&2
    exit 1
  fi
done

if ! rg -Uq 'MapAnonymous\("card table",\n[[:space:]]+capacity \+ 256,\n[[:space:]]+PROT_READ \| PROT_WRITE,\n[[:space:]]+/\*low_4gb=\*/ false,' \
    "$CARD_TABLE_CC"; then
  echo "W013_LOW_4GB_POLICY_FAIL: card table is not an anywhere mapping" >&2
  exit 1
fi

if rg -n '#ifn?def _WIN32|defined\(_WIN32\)' "$CARD_TABLE_CC" "$CARD_TABLE_H"; then
  echo "W013_LOW_4GB_POLICY_FAIL: card-table behavior still differs on Windows" >&2
  exit 1
fi

if rg -n 'AddrIsInCardTable|#ifn?def _WIN32|defined\(_WIN32\)' "$HEAP_INL"; then
  echo "W013_LOW_4GB_POLICY_FAIL: non-moving allocation write barrier still differs on Windows" >&2
  exit 1
fi

mapfile -t observed_low_files < <(
  rg -l '/\*[[:space:]]*low_4gb[[:space:]]*=[[:space:]]*\*/[[:space:]]*true' \
    "$REPO/vendor/art/runtime" \
    --glob '*.cc' \
    --glob '!**/*test*' |
    sed "s|$REPO/vendor/art/||" |
    sort
)

expected_low_files=(
  runtime/gc/heap.cc
  runtime/gc/space/bump_pointer_space.cc
  runtime/gc/space/image_space.cc
  runtime/gc/space/large_object_space.cc
  runtime/gc/space/malloc_space.cc
  runtime/gc/space/region_space.cc
  runtime/jit/jit_memory_region.cc
  runtime/runtime.cc
)

if ! diff -u \
    <(printf '%s\n' "${expected_low_files[@]}") \
    <(printf '%s\n' "${observed_low_files[@]}"); then
  echo "W013_LOW_4GB_POLICY_FAIL: product low-address caller inventory changed" >&2
  exit 1
fi

echo "W013_LOW_4GB_POLICY_PASS required_files=${#observed_low_files[@]} metadata=anywhere card_mark=unconditional nonmoving_barrier=unconditional"
