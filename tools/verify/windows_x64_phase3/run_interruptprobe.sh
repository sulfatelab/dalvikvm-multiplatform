#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" InterruptProbe interrupt.ok=true InterruptProbe.done=ok
