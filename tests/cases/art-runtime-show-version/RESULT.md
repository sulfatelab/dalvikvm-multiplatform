# ART runtime show-version result

## Contract

The target's `dalvikvm` executable must load its build-tree DSO closure, exit
zero for `-showversion`, and report the exact runtime architecture marker.
This is a native loader/version smoke; it does not start a managed runtime.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | verified | verified | 2026-07-31 |
| `linux-aarch64-gnu` | yes | verified | verified under explicit QEMU user mode | 2026-08-02 18:37:13 CST |
| `windows-x86_64-msvc` | no | not applicable | not applicable | — |

## Latest accepted run

- Product commit: the Stage 2 commit containing this acceptance record
- Command: `python tools/build_art.py test --target-id linux-x86_64-gnu --stage w004 --parallel 32`
- Expected and observed marker: `ART version 2.1.0 x86_64`
- Runner: `tests/support/runtime_gate.py show-version`
- Generated artifacts and logs: ignored under the canonical Linux output tree

The exact target selector is intentional. Another architecture needs its own
reviewed marker before applicability is expanded.

## Latest Linux AArch64 acceptance

- Product commit: the experimental AArch64 runner-admission commit containing
  this record
- Command: `python tools/build_art.py test --target-id linux-aarch64-gnu --stage w004 --parallel 32`
- Expected and observed marker: `ART version 2.1.0 arm64`
- Runner: QEMU user mode 10.2.1 from the official Ubuntu `qemu-user` package,
  bound only in ignored local TOML
- Runner SHA-256:
  `6b8505bcdd48f1ff0214630a978214d8fe770049b2515d31b160bfa0c1804ebb`

This is an explicit local target-runner result. It does not claim a native
AArch64 build host or broaden any managed/JIT/boot-image test selector.
