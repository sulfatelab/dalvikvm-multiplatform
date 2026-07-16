#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
[[ -f "$REPO/build/win64_phase1/run/rtmem.jar" ]] || bash "$REPO/tools/verify/win64_phase3/build_one.sh" RtMem
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" RtMem mem.ok=true RtMem.done=ok
