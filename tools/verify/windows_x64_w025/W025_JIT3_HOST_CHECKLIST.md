# W-025 JIT-3 / FS-3 native Windows acceptance

**Authoritative lab gate:** Windows Server 2025 Datacenter Evaluation, x64,
build 26100. The former Windows 10 host is unavailable for future reruns. See
`../windows_x64_phase4/HOST_GATE_POLICY.md`.

## Purpose

This package validates JIT allocation lifecycle and dynamic PE unwind-table
ownership on native Windows. It repeatedly compiles 16 optimizing methods and
8 distinct JNI stubs, invalidates and collects them, requires exact code-address
reuse, and republishes their unwind tables while a separate Windows thread runs
`RtlLookupFunctionEntry()` and synthetic `RtlVirtualUnwind()` calls.

The primary stress arm uses the default J-2 pagefile-section dual mapping. J-1
is retained only as a comparison arm for this gate. The package also verifies
the Windows nterp hard-float return regression through the JNI float and double
results after every lifecycle run.

No LLVM, compiler, SDK, Python, or network access is required on the Windows
host.

## Run

Unpack the ZIP, open Windows PowerShell in the package root, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W025_JIT3_HOST.ps1
```

The expected final line is `OVERALL PASS`. Results and child logs are written
under `logs\`. A successful run records `NO_DMP_FILES` and leaves `jit-temp\`
empty.

## Acceptance invariants

- Every live published PC has an unwind record.
- Every collected dead PC loses its unwind record.
- Every method reuses its exact prior code address before republishing.
- Synthetic virtual unwind succeeds for optimizing and JNI allocations.
- Lookup and unwind sampling remain active during repeated churn.
- `missing_live`, `stale_dead`, and `unwind_failures` are all zero.
- `callback_tables=0`; the one-entry immutable table design remains sufficient.
- JNI integer, reference, mixed, float, and double values remain exact after
  the compiled normal-JNI transition back through nterp.

Do not enable CET user shadow stacks for this package. The project-wide
`/CETCOMPAT:NO` and startup policy contract remains documented under W-010.
