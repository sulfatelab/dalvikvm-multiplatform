# W-024 native Windows 10 acceptance checklist

**Latest result:** PASS on Windows 10 Enterprise LTSC 2021, build 19044, on
2026-07-24. Accepted evidence is stored under `evidence/w024_host/`.

This checklist records the native-host gate required before removing the
native-JIT diagnostic gate or the legacy `InterpreterJni` fallbacks. Run it on
a native x86-64 Windows installation, not Wine, WSL, or Windows 7.

## 1. Host requirement

- Windows 10 version 1803 or later, or Windows 11 x64.
- Run `winver` and record the reported version in the returned evidence.
- Do not substitute a Wine result for this gate.

## 2. Build and transfer

On `agent01`, from the repository root:

```bash
bash tools/win64/host_package/package_win64_w024_tripwire.sh
```

Transfer and unpack one of:

```text
dist/win64_w024_tripwire_host/
dist/win64_w024_tripwire_host.zip
```

The package is path-space safe. A short path is still convenient, for example
`C:\art_w024\win64_w024_tripwire_host`.

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

## 4. Run the acceptance matrix

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

## 7. What a pass authorizes

A native-host pass closes only the reachability gate. The next code stage must
still restore the upstream pre-start-only bridge invariant, reduce
`InterpreterJni` and `ResolveJniEntryPoint`, remove the native-JIT diagnostic
gate, rebuild Linux and Win64, and rerun the full regression matrix before
W-011, W-012, and W-024 can close.

The packaged tripwire `art.dll` is diagnostic-only and must not ship as a
product binary.
