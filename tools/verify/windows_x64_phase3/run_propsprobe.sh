#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" PropsProbe props.ok=true PropsProbe.done=ok
