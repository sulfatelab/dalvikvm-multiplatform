# ART runtime show-version result

## Contract

The target's `dalvikvm` executable must load its build-tree DSO closure, exit
zero for `-showversion`, and report the exact runtime architecture marker.
This is a native loader/version smoke; it does not start a managed runtime.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | verified | verified | 2026-07-31 |
| `windows-x86_64-msvc` | no | not applicable | not applicable | — |

## Latest accepted run

- Product commit: the Stage 2 commit containing this acceptance record
- Command: `python tools/build_art.py test --target-id linux-x86_64-gnu --stage w004 --parallel 32`
- Expected and observed marker: `ART version 2.1.0 x86_64`
- Runner: `tests/support/runtime_gate.py show-version`
- Generated artifacts and logs: ignored under the canonical Linux output tree

The exact target selector is intentional. Another architecture needs its own
reviewed marker before applicability is expanded.
