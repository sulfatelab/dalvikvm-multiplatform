#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" GcForced tiny.ok=true los.ok=true gc.forced.ok=true GcForced.done=ok
