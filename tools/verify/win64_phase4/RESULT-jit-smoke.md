# Win64 JIT smoke test — native-JIT gate verification

Date: 2026-07-21. VM: agent01, wine. Build: win64_phase1 RelWithDebInfo.

## Test: `run_jit_smoke.sh`

Automated script runs `dalvikvm.exe` under wine with Hello.jar and verifies the
native-JIT gate introduced in commit `da388124c1` (vendor/art) /
`23bc77e` (root).

## Results: ALL 10 TESTS PASSED

| Test | Assertion | Result |
|------|-----------|--------|
| T1 | JIT code cache created (`JitCodeCache::Create OK`) | **PASS** |
| T2 | ≥1 managed method JIT-compiled | **PASS** (24 compiles) |
| T3 | Prints `Hello from dalvikvm!` | **PASS** |
| T4 | No native methods JIT-compiled by default | **PASS** (gate active) |
| T5 | `ART_WIN64_JIT_NATIVE=1` runs Hello | **PASS** (22 compiles) |
| T6 | `ART_WIN64_JIT=0` disables all compile | **PASS** (0 compiles) |
| T7 | `-Xusejit:false` no crash | **PASS** |
| T8a | `ART_WIN64_JIT_FILTER=StringBuilder` runs | **PASS** (5 compiles) |
| T8b | `ART_WIN64_JIT_EXCLUDE=StringBuilder` runs | **PASS** |

## Key observations

- Default path: 64 KB initial / 64 MB max code cache created successfully.
- 24 managed methods compiled (Baseline): String.equals, String.length,
  StringBuilder.append, Math.min/max, Unsafe.getReferenceAcquire, etc.
- Zero native-method compiles in default mode — the new `method->IsNative()`
  gate correctly excludes all native methods.
- `ART_WIN64_JIT=0` cleanly disables all JIT while keeping nterp.
- `-Xusejit:false` may still create the JIT cache (ART init ordering on Win)
  but Hello passes without crash.
- 11,346 methods upgraded to nterp after `finished_starting_`.

## Code under test

- `vendor/art/runtime/jit/jit.cc` — `CompileMethodInternal`: native-gate check
  (`method->IsNative()` → skip unless `ART_WIN64_JIT_NATIVE=1`)
- `vendor/art/runtime/jit/jit_code_cache.cc` — J-1 RemapAtEnd via
  VirtualProtect; Create log line

## Related

- [win32_jit_memory.md](../../win32_jit_memory.md) §13 — implementation status
- [win32_open_items.md](../../win32_open_items.md) W-025 — JIT code cache + codegen TLS
