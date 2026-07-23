# Win64 JIT smoke test — default dual-view and native-JIT gate verification

Date: 2026-07-23. VM: agent01, Wine. Build: win64_phase1 RelWithDebInfo.

## Test: `run_jit_smoke.sh`

The automated script runs `dalvikvm.exe` under Wine with Hello.jar through the
default pagefile-backed contiguous dual-view code cache. It also verifies the
native-JIT gate and the managed-JIT control environment variables.

## Results: ALL 10 TESTS PASSED

| Test | Assertion | Result |
|------|-----------|--------|
| T1 | JIT code cache created (`JitCodeCache::Create OK`) | **PASS** |
| T2 | ≥1 managed method JIT-compiled | **PASS** (24 compiles) |
| T3 | Prints `Hello from dalvikvm!` | **PASS** |
| T4 | No native methods JIT-compiled by default | **PASS** (gate active) |
| T5 | `ART_WIN64_JIT_NATIVE=1` runs Hello | **PASS** (23 compiles) |
| T6 | `ART_WIN64_JIT=0` disables all compile | **PASS** (0 compiles) |
| T7 | `-Xusejit:false` no crash | **PASS** |
| T8a | `ART_WIN64_JIT_FILTER=StringBuilder` runs | **PASS** (5 compiles) |
| T8b | `ART_WIN64_JIT_EXCLUDE=StringBuilder` runs | **PASS** |

## Key observations

- Default path: 64 KiB initial / 64 MiB maximum code cache created successfully
  with the corrected contiguous dual view.
- 24 managed methods compiled in the primary Hello run (Baseline):
  String.equals, String.length, StringBuilder.append, Math.min/max,
  Unsafe.getReferenceAcquire, etc.
- Zero native-method compiles in default mode — the new `method->IsNative()`
  gate correctly excludes all native methods.
- `ART_WIN64_JIT=0` cleanly disables all JIT while keeping nterp.
- `-Xusejit:false` may still create the JIT cache (ART init ordering on Win)
  but Hello passes without crash.
- 11,346 methods upgraded to nterp after `finished_starting_`.

## Code under test

- `vendor/art/runtime/jit/jit.cc` — `CompileMethodInternal`: native-gate check
  (`method->IsNative()` → skip unless `ART_WIN64_JIT_NATIVE=1`)
- `vendor/art/runtime/jit/jit_memory_region.cc` — default contiguous dual-view
  construction and common post-mapping initialization
- `vendor/art/libartbase/base/mem_map_windows.cc` — unnamed pagefile-section
  views
- `vendor/art/libartbase/base/utils.cc` — Windows `FlushInstructionCache`

## Related

- [win32_jit_memory.md](../../win32_jit_memory.md) §13 — implementation status
- [win32_open_items.md](../../win32_open_items.md) W-025 — JIT code cache + codegen TLS
