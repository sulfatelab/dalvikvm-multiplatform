# Windows boot-OAT CFG result

The Windows x86-64 W-032 case validates `.oat_cfg.windows` transport and
observation-mode execution.

| Build | Runtime | Last checked |
|---|---|---|
| verified | PASS on Windows Server 2025 build 26100 | 2026-08-07 |

The accepted native gate rejects 18 semantic corruptions through 38 real
opens, accepts all eight metadata/relro layouts, and uses a verified guarded PE
caller to enter quick and JNI boot-OAT bodies under forced CFG without target
state API calls. Full evidence is in
[`docs/history/windows_x64_w032_result.md`](../../../docs/history/windows_x64_w032_result.md).
