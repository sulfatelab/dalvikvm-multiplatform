# Memory-map policy result

The W-013 probe checks ART-owned Windows virtual-memory policy. Its current
selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | native safe gate passed | 2026-08-01 |

The canonical source passed the unified Windows cross catalog build. Windows
AArch64 and ARM64EC require separate validation before selector expansion.

The historical closure probe exhausts the process's complete low address
range. Native Windows 10 R2 accepted that contract, but two Server 2025 runs
left the VM unable to enumerate processes or start simple commands. Reducing
the fragmented reservation count from roughly 3,800 to 64 did not prevent the
failure: the fresh Stage-8 CTest run timed out after 300.01 seconds and the VM
again required a reboot. The other five W-013 gates passed in the same run.

Routine unified CTest execution therefore omits process-wide fragmentation
and exhaustion. The executable retains those operations only behind the
explicit `--exhaustive-low-va` argument for historical reproduction on an
isolated disposable host. Its default path continues to validate normal,
exact, low, boundary, aligned, protection-transition, reservation-transfer,
reuse, logical-shrink, and repeated-destruction behavior. The maintained
source-policy audit separately rejects a manual low-address scan or
unrestricted fallback.

Secondary Linux-hosted Wine execution of the freshly cross-built PE passed in
0.76 seconds:

```text
W013_MEM_MAP_POLICY_PASS anywhere=00007FFFFE7C0000 low=0000000000010000 boundary=tested transitions=32 fragments=64 exhaustion_reservations=2 destruction_cycles=128
```

Wine execution is not a substitute for the authoritative Server 2025 gate.
The output predates the explicit stress-mode marker and exercised the
exhaustive path.

## Authoritative safe-gate acceptance

After recovery, the Stage-8 Server 2025 host rebuilt the revised probe and ran
its exact CTest in 1.14 seconds. The canonical full W-013 command then reported
`ninja: no work to do.` and passed all six gates; the memory-map probe took
0.08 seconds. Process enumeration remained responsive after both runs, and
the source and output trees contained zero reparse points.

```text
W013_MEM_MAP_POLICY_PASS anywhere=00000240809A0000 low=0000000000410000 boundary=tested transitions=32 low_va_stress=skipped fragments=0 exhaustion_reservations=0 destruction_cycles=128
```
