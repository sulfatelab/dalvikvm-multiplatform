#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" GoldenApp golden.ok=true net.ok=true GoldenApp.done=ok
