#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" GcStressProbe gcstress.ok=true GcStressProbe.done=ok
