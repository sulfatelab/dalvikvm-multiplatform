# W-025 JIT-2 native Windows acceptance

**Target:** Windows 10 version 1803 (build 17134) or later, x64

## Purpose

This package validates the default pagefile-backed JIT dual view on a native
Windows host. It covers the real ART mappings at 64 MiB and the supported
1 GiB maximum, a CFG-instrumented generated-code call, complete low-VA
fragmentation and clean recovery, `SEC_COMMIT` charge, and prohibited dynamic
code with a JIT-disabled control.

No LLVM, compiler, SDK, Python, or network access is required to run the gate.

## Run

Unpack the ZIP, open Windows PowerShell in the package root, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W025_JIT2_HOST.ps1
```

The expected final line is `OVERALL PASS`. Results and child logs are written
under `logs\`. A successful run records `NO_DMP_FILES` and leaves `jit-temp\`
empty.

## Expected policy behavior

- Default and CFG-enabled JIT processes must create the low R/RX primary and
  unrestricted RW alias, compile the target method, and report no RWX or named
  file mapping.
- A process created with `ProhibitDynamicCode` must reject both the J-2 and
  J-1 executable mappings with `ERROR_DYNAMIC_CODE_BLOCKED` (1655), continue
  without a JIT cache, and run Hello successfully.
- The same policy with `-Xusejit:false` must run Hello successfully. This
  separates the expected OS-policy rejection path from a general runtime
  defect and confirms that no JIT-cache creation was attempted.

Do not enable CET user shadow stacks for this package. The project-wide
`/CETCOMPAT:NO` and startup policy contract remains documented under W-010.
