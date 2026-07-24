# Win64 JIT smoke test — default dual-view and native-JIT gate verification

Date: 2026-07-24. VM: agent01, Wine. Build: win64_phase1 RelWithDebInfo.

## Test: `run_jit_smoke.sh`

The automated script runs `dalvikvm.exe` under Wine with Hello.jar through the
default pagefile-backed contiguous dual-view code cache. It also verifies the
native-JIT gate and the managed-JIT control environment variables.

## Results: ALL 12 TESTS PASSED

| Test | Assertion | Result |
|------|-----------|--------|
| T1 | JIT code cache created (`JitCodeCache::Create OK`) | **PASS** |
| T2 | ≥1 managed method JIT-compiled | **PASS** (20 compiles in the recorded run) |
| T3 | Prints Hello and reports `main end exception=0` | **PASS** |
| T4 | No native methods JIT-compiled by default | **PASS** (gate active) |
| T5 | `ART_WIN64_JIT_NATIVE=1` compiles and executes the native stub | **PASS** |
| T6 | `ART_WIN64_JIT=0` disables all compile and completes Hello cleanly | **PASS** (0 compiles) |
| T7 | `-Xusejit:false` completes Hello cleanly | **PASS** |
| T8a | `ART_WIN64_JIT_FILTER=StringBuilder` completes Hello cleanly | **PASS** (6 compiles) |
| T8b | `ART_WIN64_JIT_EXCLUDE=StringBuilder` completes Hello cleanly | **PASS** |
| T9a | Product diagnostic-off mode completes Hello cleanly | **PASS** |
| T9b | Product diagnostic-off mode emits zero per-method compile records | **PASS** |

## Key observations

- Default path: 64 KiB initial / 64 MiB maximum code cache created successfully
  with the corrected contiguous dual view.
- 20 managed methods compiled in the recorded primary Hello run (Baseline):
  String.equals, String.length, StringBuilder.append, Math.min/max,
  Unsafe.getReferenceAcquire, etc.
- Zero native-method compiles in default mode — the new `method->IsNative()`
  gate correctly excludes all native methods.
- T5 now requires both a compiled `StringFactory.newStringFromBytes` stub and
  `main end exception=0`. The previous check searched only for
  `Hello from dalvikvm!` and was a false-positive because that text can be
  printed before `main end exception=1`.
- `run_native_abi_probe.sh` provides the focused acceptance control: the
  mixed/high-FP normal/FastNative matrix passes with 0/7 targets compiled when
  the gate is closed and 7/7 when it is open, across initial,
  unregister/dlsym, re-register, and method-tracing phases without extra
  target compilation or a leftover trace file.
- `run_critical_native_probe.sh` separately verifies registered and unresolved
  CriticalNative calls during and after method tracing in both J-1 and the
  corrected dual-view mode.
- `ART_WIN64_JIT=0` cleanly disables all JIT while keeping nterp.
- `-Xusejit:false` may still create the JIT cache (ART init ordering on Win)
  but Hello passes without crash.
- Per-method `Win64 CompileMethod done` records are now opt-in through
  `ART_WIN64_JIT_LOG_COMPILES=1`. Acceptance harnesses that count compilation
  records set it explicitly; normal product runs are quiet.
- 11,346 methods upgraded to nterp after `finished_starting_`.

## Code under test

- `vendor/art/runtime/jit/jit.cc` — `CompileMethodInternal`: native-gate check
  (`method->IsNative()` → skip unless `ART_WIN64_JIT_NATIVE=1`) and opt-in
  compile diagnostics (`ART_WIN64_JIT_LOG_COMPILES=1`)
- `vendor/art/runtime/jit/jit_memory_region.cc` — default contiguous dual-view
  construction and common post-mapping initialization
- `vendor/art/libartbase/base/mem_map_windows.cc` — unnamed pagefile-section
  views
- `vendor/art/libartbase/base/utils.cc` — Windows `FlushInstructionCache`

## Related

- [win32_jit_memory.md](../../win32_jit_memory.md) §13 — implementation status
- [win32_open_items.md](../../win32_open_items.md) W-025 — JIT code cache + codegen TLS
- [RESULT-native-abi.md](RESULT-native-abi.md) — focused W-024 native ABI evidence
