#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${BUILD:-$REPO/build/windows_x64_phase1}"
WINE="${WINE:-wine64}"
WINEDEBUG="${WINEDEBUG:--all}"

"$REPO/tools/verify/windows_x64_w025/build_w025_jit2_probe.sh"

section_stdout="$(mktemp "${TMPDIR:-/tmp}/w025-section-basic.stdout.XXXXXX.log")"
section_stderr="$(mktemp "${TMPDIR:-/tmp}/w025-section-basic.stderr.XXXXXX.log")"
runtime_stdout="$(mktemp "${TMPDIR:-/tmp}/w025-runtime-mapping.stdout.XXXXXX.log")"
runtime_stderr="$(mktemp "${TMPDIR:-/tmp}/w025-runtime-mapping.stderr.XXXXXX.log")"
trap 'rm -f "$section_stdout" "$section_stderr" "$runtime_stdout" "$runtime_stderr"' EXIT

(
  cd "$BUILD"
  WINEDEBUG="$WINEDEBUG" timeout 180 "$WINE" ./W025SectionPolicyProbe.exe --basic
) >"$section_stdout" 2>"$section_stderr"
grep -Fq 'roles=R_RX_RW type=MEM_MAPPED rwx=0 mapped_names=0' "$section_stdout"
grep -Fq 'W025_SECTION_POLICY_PASS mode=basic' "$section_stdout"

(
  cd "$BUILD"
  env \
    ANDROID_ROOT=run \
    ANDROID_ART_ROOT=run \
    ANDROID_I18N_ROOT=run \
    ANDROID_DATA=run/data \
    ICU_DATA=run/icu \
    WINEDEBUG="$WINEDEBUG" \
    ART_WINDOWS_X64_JIT_DUAL=1 \
    ART_WINDOWS_X64_JIT_FILTER=W025JitMappingProbe \
    ART_WINDOWS_X64_JIT_LOG_COMPILES=1 \
    timeout 180 "$WINE" ./dalvikvm.exe \
      -Xbootclasspath:run/boot.jar \
      -Xbootclasspath-locations:run/boot.jar \
      -Ximage:/nonexistent-no-boot-image \
      -XjdwpProvider:none \
      -Xjitwarmupthreshold:1 \
      -Xjitthreshold:1 \
      -Xjitmaxsize:64M \
      -Xms64m \
      -Xmx512m \
      '-Djava.library.path=.;run' \
      -cp run/w025jitmappingprobe.jar \
      W025JitMappingProbe 64 false
) >"$runtime_stdout" 2>"$runtime_stderr"
grep -Fq 'Windows x64 JIT dual-view (J-2) created: capacity=64MiB' "$runtime_stderr"
grep -Fq 'roles primary_data=R primary_code=RX alias_data=RW alias_code=RW type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes=67108864' "$runtime_stdout"
grep -Fq 'W025_JIT_MAPPING_PASS' "$runtime_stdout"
grep -Fq 'W025JitMappingProbe PASS capacity_bytes=67108864 require_cfg=false' "$runtime_stdout"

printf 'W025_JIT2_WINE_PREFLIGHT_PASS section=basic runtime_mapping=64MiB '\
'native_only=SEC_COMMIT,low-VA,CFG,dynamic-code-policy\n'
