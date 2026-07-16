#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" ThreadStressProbe threadstress.ok=true ThreadStressProbe.done=ok
