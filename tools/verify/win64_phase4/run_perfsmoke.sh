#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" PerfSmokeProbe perf.ok=true PerfSmokeProbe.done=ok
