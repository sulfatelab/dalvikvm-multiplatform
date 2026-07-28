#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" HandleLeakProbe handleleak.ok=true HandleLeakProbe.done=ok
