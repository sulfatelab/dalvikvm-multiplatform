# Historical W-003 native Windows acceptance checklist

This checklist applies only to the already issued package and its immutable
returned evidence. The repository package producer and packaged-runner source
were retired after the unified `stage:w003` product and frame-attribution
variant passed on Windows Server 2025 and repeated as Ninja no-ops. For a new
run, use `tools/build_art.py test --stage w003`; do not reconstruct this package.

Use this package on the authoritative Windows Server 2025 Datacenter
Evaluation x64 build-26100 host. The former Windows 10 host is unavailable for
future reruns. The Windows 10 build-17134 API level remains the product
compatibility baseline, and Wine results are development gates only. See
[HOST_GATE_POLICY.md](HOST_GATE_POLICY.md).

The package contains two ART variants:

- `art.product.dll` is the ordinary product runtime;
- `art.frame-probe.dll` is the opt-in frame-counter runtime; and
- `art.dll` is the active copy and is product-identical when the package is
  issued and after the runner exits, including after a test failure.

The probe deliberately does not test nterp implicit-null fault translation.
That independently reproduced product defect belongs to W-010. Class-cast,
array-store, and bounds exception paths remain covered; no product workaround
is present in this package.

## 1. Verify and unpack

Copy both `windows_x64_w003_host.zip` and `windows_x64_w003_host.zip.sha256` to the native
Windows host. Verify the archive hash against the `.sha256` file, then extract
the archive into a new, empty, local writable directory. Do not merge it into
an older run and do not run it from inside the ZIP.

PowerShell example:

```powershell
$expected = ((Get-Content -LiteralPath .\windows_x64_w003_host.zip.sha256) -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 .\windows_x64_w003_host.zip).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'W-003 package SHA-256 mismatch' }
$destination = Join-Path $PWD 'w003-native-run'
if (Test-Path -LiteralPath $destination) { throw "$destination already exists" }
New-Item -ItemType Directory -Path $destination | Out-Null
Expand-Archive -LiteralPath .\windows_x64_w003_host.zip -DestinationPath $destination
Set-Location (Join-Path $destination 'windows_x64_w003_host')
```

No LLVM tools, compiler, JDK, or network connection is required on the
Windows host. Keep the package directory writable because ART uses `run\data`
and the runner writes evidence under `logs`.

## 2. Run the acceptance matrix

Open 64-bit Windows PowerShell in the extracted package directory and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\scripts\RUN_W003_HOST.ps1
```

The runner performs:

- package SHA-256 and precomputed structural-report checks;
- 2 runs each of the frame probe in `-Xint`, switch, nterp, and
  threshold-zero JIT modes (8 processes);
- 2 runs each of the full-width XMM6-XMM15 sentinel in switch, nterp, and
  threshold-zero JIT modes (6 processes);
- fatal-marker scanning over every process log; and
- a recursive `.dmp` scan over the extracted package.

The expected final console line and process exit code are:

```text
OVERALL PASS
exit code 0
```

## 3. Verify the result contract

The result must contain exactly 19 `PASS` records followed by `OVERALL PASS`:

```powershell
$result = Get-Content -LiteralPath .\logs\RESULT_W003.txt
($result | Where-Object { $_ -match '^PASS ' }).Count
$result | Select-Object -Last 1
Get-Content -LiteralPath .\logs\DMP_SCAN.txt
```

Expected output:

```text
19
OVERALL PASS
NO_DMP_FILES
```

Acceptance additionally requires:

- all 8 `frame_*` records are `PASS`;
- all 6 `xmm_*` records are `PASS`;
- `PASS log_scan` and `PASS dump_scan NO_DMP_FILES` are present;
- no `FAIL` record is present;
- JIT frame logs contain positive refs-only, refs-and-args,
  all-callee-saves, and save-everything counters;
- nterp frame logs contain the same four positive families; and
- JIT XMM logs contain the compatibility marker
  `mask=0 selfTestMask=63 iterations=128`, the full-width marker
  `fullSelfTestMask=1023`, and a successful compile record for
  `W003XmmSentinelProbe.managedCallback`.

The runner checks these conditions automatically. The commands above are a
short operator cross-check, not a substitute for a zero runner exit code.

## 4. Preserve native evidence

Do not clean or rerun the package after a failure until its original logs and
any dumps have been copied. After a passing run, preserve all logs:

```powershell
Compress-Archive -Path .\logs\* -DestinationPath .\W003_NATIVE_LOGS.zip -Force
Get-FileHash -Algorithm SHA256 .\W003_NATIVE_LOGS.zip
```

Return `W003_NATIVE_LOGS.zip`, its SHA-256, the Windows caption/version/build,
and the console exit code. `logs\WINDOWS_VERSION.txt` records the detailed
host and PowerShell version. A failure remains actionable evidence and must
include every process log plus any `.dmp` file.
