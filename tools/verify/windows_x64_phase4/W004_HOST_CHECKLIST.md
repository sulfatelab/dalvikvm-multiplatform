# W-004 native Windows host acceptance

**Target:** Windows 10 version 1803 (RS4, build 17134) or later, x64

**State:** ACCEPTED on Windows 10 build 19044; W-004 closed

The accepted 2026-07-25 run produced 28 PASS records, zero failures,
`OVERALL PASS`, and `NO_DMP_FILES`. Package metadata and the structural report
match the issued package byte for byte. See
[`evidence/w004_host/ACCEPTANCE.md`](evidence/w004_host/ACCEPTANCE.md).

Linux-side review command:

```bash
python3 tools/verify/windows_x64_phase4/review_w004_host_result.py \
  /path/to/returned.zip --issued dist/windows_x64_w004_host
```

## Purpose

This package closes the final W-004 acceptance gap for the direct Windows x64
`Runtime::instance_` assembly load. Linux packaging performs the LLVM object and
PE inspection; the Windows host does not need LLVM tools.

The embedded `W004_STRUCTURAL_REPORT.txt` records:

- direct quick, JNI, and generated-nterp relocations;
- zero references to the retired helper;
- one `Runtime::instance_` export from `art.dll`;
- one `Runtime::instance_` import in `openjdkjvmti.dll`;
- unchanged Linux macro status; and
- SHA-256 identities for the inspected `art.dll` and `openjdkjvmti.dll`.

## Run

Unpack the generated archive on a native Windows 10/11 x64 host. Do not run it
from WSL. From PowerShell in the package root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\RUN_W004_HOST.ps1
```

The script resolves the package root from its own location, so the unpack path
may contain spaces.

## Required result

`logs\RESULT_W004.txt` must end with:

```text
OVERALL PASS
```

The runner first verifies every packaged SHA-256 and the embedded structural
contract. It then covers:

- an `-Xint` nterp/imageless Hello path;
- default dual-view JIT startup and compilation;
- threshold-zero `FloatProbe`;
- registered and unresolved CriticalNative calls with tracing in dual and J-1
  modes;
- seven compiled normal/FastNative JNI shapes with tracing in both modes;
- JVMTI forced-interpreter transitions in both modes;
- GC stress, thread-heavy, and handle-leak probes;
- ten independent default-JIT process starts;
- trace-file cleanup and fatal/access-violation log scanning; and
- a recursive `*.dmp` scan implemented with PowerShell `Get-ChildItem`.

The package intentionally contains no host-side LLVM dependency. The structural
report is accepted only when its recorded DLL hashes match the packaged files.

## Return evidence

Return the complete `logs` directory plus:

- `BUILD_INFO.txt`;
- `MANIFEST.json`;
- `SHA256SUMS.txt`; and
- `W004_STRUCTURAL_REPORT.txt`.

Do not return only screenshots. Preserve all stdout/stderr logs so marker,
exit-code, OS-build, and dump-scan results can be reviewed.

The procedure remains available for regression runs. The first returned run
was reviewed and accepted, closing W-004.
