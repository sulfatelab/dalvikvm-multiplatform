# W-024 native Windows 10 acceptance checklist (completed)

**Latest result:** PASS on Windows 10 Enterprise LTSC 2021, build 19044, on
2026-07-24. Accepted evidence is stored under `evidence/w024_host/`.

This checklist records the completed native-host gate that authorized removal
of the native-JIT diagnostic gate and legacy `InterpreterJni` fallbacks. The
tripwire generator was retired after cleanup; retained evidence is the
authoritative record.

## 1. Host requirement

- Windows 10 version 1803 or later, or Windows 11 x64.
- Run `winver` and record the reported version in the returned evidence.
- Do not substitute a Wine result for this gate.

## 2. Accepted package identity

The accepted package was built before cleanup from parent commit
`e7f90935c7b1909fe528a8441fa5014bcd666b95` and ART commit
`1a75ad10a3ee28910a7b46184a0a7628f96da72a`, with the tripwire enabled. Its
complete 169-entry manifest and build information are retained under
`evidence/w024_host/`.

## 3. Confirm the shared boot artifact

From PowerShell in the unpacked package:

```powershell
Get-FileHash .\run\boot.jar -Algorithm SHA256
(Get-Item .\run\boot.jar).Length
Get-Content .\BUILD_INFO.txt
```

The values must match `BUILD_INFO.txt`. The expected shared Linux/Win64
artifact for this stage is:

```text
sha256 3cbe9a7f0e4596229c0c5e229e6655463373b1445922b9557286313a28a35a2a
size   3436578 bytes
```

There is no Windows-specific `boot.jar` in this test.

## 4. Accepted matrix invocation

From Command Prompt in the unpacked package:

```bat
scripts\run_all_w024.cmd
```

The command must exit zero and print `OVERALL PASS`.

## 5. Pass criteria

`logs\RESULT_W024.txt` must end with:

```text
OVERALL PASS
```

Every case must report `exit=0`:

| Case | Coverage |
|------|----------|
| `math_dual` | threshold-zero Math CriticalNative, corrected dual-view JIT memory |
| `math_j1` | threshold-zero Math CriticalNative, J-1 diagnostic memory path |
| `math_xint` | Math CriticalNative with Win64 `-Xint` |
| `critical_dual` | registered/unresolved CriticalNative plus method tracing, dual view |
| `critical_j1` | registered/unresolved CriticalNative plus method tracing, J-1 |
| `native_abi_dual` | compiled normal/FastNative mixed ABI plus tracing, dual view |
| `native_abi_j1` | compiled normal/FastNative mixed ABI plus tracing, J-1 |
| `jvmti_dual` | JVMTI single-step forced interpretation, dual view |
| `jvmti_j1` | JVMTI single-step forced interpretation, J-1 |

No log may contain the fatal marker:

```bat
findstr /S /C:"Win64 InterpreterJni tripwire" logs\*.log && echo FAIL || echo PASS
```

Also confirm that no crash dump was produced:

```bat
dir /S /B *.dmp
```

`File Not Found` is the expected result.

## 6. Return evidence

Return all of the following without editing the logs:

```text
logs\
BUILD_INFO.txt
MANIFEST.json
Windows version from winver
```

Store accepted evidence under:

```text
tools/verify/win64_phase4/evidence/w024_host/
```

## 7. Authorized cleanup result

ART commit `42a03f2ea0` restored `runtime/interpreter/interpreter.cc`
byte-for-byte to `android-16.0.0_r4`, including the pre-start-only bridge
invariant, and removed the native-method JIT exclusion. The parent project
retired the tripwire build option and package generator and changed the focused
probes to require native compilation by default.

Post-change verification passed the Win64 build, JIT smoke 12/12, JIT matrix
14/14, all Phase 4 Wine gates, default normal/FastNative 7/7, CriticalNative,
JVMTI, Math, full Linux rebuild, L-005 shared-boot Hello, and Linux Math
controls. W-011, W-012, and W-024 are closed. The packaged tripwire `art.dll`
remains diagnostic-only historical evidence and is not a product binary.
