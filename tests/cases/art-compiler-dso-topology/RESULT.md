# ART compiler DSO topology result

## Contract

Both the runtime and compiler shared objects must load from the target build
closure. `libart-compiler.so` must contain a direct `DT_NEEDED` entry for
`libart.so`, while `libart.so` must not contain a reverse dependency on
`libart-compiler.so`. The gate parses ELF program and dynamic tables in Python
and does not require `readelf` or another POSIX utility.

## Target status

| Target ID | Applicable | Build | Runtime | Last accepted |
|---|---:|---:|---:|---|
| `linux-x86_64-gnu` | yes | verified | verified | 2026-07-31 |
| `windows-x86_64-msvc` | no | not applicable | not applicable | — |

## Latest accepted run

- Product commit: the Stage 2 commit containing this acceptance record
- Command: `python tools/build_art.py test --target-id linux-x86_64-gnu --stage w004 --parallel 32`
- Observed edge: `libart-compiler.so -> libart.so`
- Observed reverse edge: absent
- Load result: `libart.so` and `libart-compiler.so` both loaded with immediate
  symbol resolution
- Runner: `tests/support/runtime_gate.py dso-topology`

Windows PE load, import, export, and no-cycle acceptance remains separately
recorded by the native Windows baseline; this ELF gate does not claim Windows
applicability.
