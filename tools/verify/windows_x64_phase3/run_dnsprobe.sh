#!/usr/bin/env bash
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_one.sh" DnsProbe dns.ok=true DnsProbe.done=ok
