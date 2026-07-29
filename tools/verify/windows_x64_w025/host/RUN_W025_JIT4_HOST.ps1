$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root 'logs'
$Crash = Join-Path $Root 'run\crash'
$JitTemp = Join-Path $Root 'jit-temp'
New-Item -ItemType Directory -Force -Path $Logs, $Crash, $JitTemp | Out-Null
Get-ChildItem -Path $Logs -File -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path $JitTemp -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

$env:ANDROID_ROOT = 'run'
$env:ANDROID_ART_ROOT = 'run'
$env:ANDROID_I18N_ROOT = 'run'
$env:ANDROID_DATA = 'run\data'
$env:ICU_DATA = 'run\icu'
$env:TEMP = $JitTemp
$env:TMP = $JitTemp

$script:Results = New-Object System.Collections.Generic.List[string]
$script:Failed = $false

function Add-Result([string]$Text) {
    $script:Results.Add($Text)
    Write-Host $Text
}

function Clear-ArtEnvironment {
    @(
        'ART_WINDOWS_X64_JIT'
        'ART_WINDOWS_X64_JIT_DUAL'
        'ART_WINDOWS_X64_JIT_EXCLUDE'
        'ART_WINDOWS_X64_JIT_FILTER'
        'ART_WINDOWS_X64_JIT_LOG_COMPILES'
        'ART_WINDOWS_X64_NTERP'
        'ART_WINDOWS_X64_QUICK_INVOKE'
        'ART_WINDOWS_X64_CRASH_NATIVE_WARMUP'
    ) | ForEach-Object {
        Remove-Item -Path ('Env:' + $_) -ErrorAction SilentlyContinue
    }
}

function Test-PackageIntegrity {
    $manifestPath = Join-Path $Root 'MANIFEST.json'
    $sumsPath = Join-Path $Root 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) {
        throw 'package manifest files are missing'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.count -ne @($manifest.files).Count) {
        throw 'MANIFEST.json count does not match its file list'
    }
    foreach ($entry in @($manifest.files)) {
        $path = Join-Path $Root ([string]$entry.path).Replace('/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "manifest payload is missing: $($entry.path)"
        }
        $item = Get-Item -LiteralPath $path
        if ($item.Length -ne [long]$entry.bytes) {
            throw "manifest size mismatch: $($entry.path)"
        }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) {
            throw "manifest hash mismatch: $($entry.path)"
        }
    }
    foreach ($line in Get-Content -LiteralPath $sumsPath) {
        if ($line -notmatch '^([0-9a-f]{64})  \./(.+)$') {
            throw "invalid SHA256SUMS line: $line"
        }
        $path = Join-Path $Root $Matches[2].Replace('/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "SHA256SUMS payload is missing: $($Matches[2])"
        }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($actual -ne $Matches[1]) {
            throw "SHA256SUMS mismatch: $($Matches[2])"
        }
    }
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Arguments = '',
        [string[]]$Markers = @(),
        [string[]]$ForbiddenMarkers = @(),
        [switch]$RequireNonZero,
        [switch]$RequireNewMinidump,
        [int]$TimeoutSeconds = 300
    )

    $stdout = Join-Path $Logs ($Name + '.stdout.log')
    $stderr = Join-Path $Logs ($Name + '.stderr.log')
    $combined = Join-Path $Logs ($Name + '.log')
    $started = Get-Date
    $process = $null
    $launchError = $null
    $timedOut = $false
    $exitCode = -1
    $beforeDumps = @{}
    if ($RequireNewMinidump) {
        Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue |
            ForEach-Object {
                $beforeDumps[$_.FullName] = "$($_.Length):$($_.LastWriteTimeUtc.Ticks)"
            }
    }
    try {
        $process = Start-Process -FilePath (Join-Path $Root 'dalvikvm.exe') `
            -WorkingDirectory $Root -ArgumentList $Arguments `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
            -NoNewWindow -PassThru
        $null = $process.Handle
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            $process.Kill()
        }
        $process.WaitForExit()
        $exitCode = [int]$process.ExitCode
    } catch {
        $launchError = $_.Exception.ToString()
    } finally {
        if ($null -ne $process) { $process.Dispose() }
    }
    $elapsedMs = [long]((Get-Date) - $started).TotalMilliseconds

    @(
        "name=$Name"
        "exit=$exitCode"
        "require_nonzero=$RequireNonZero"
        "timeout_seconds=$TimeoutSeconds"
        "timed_out=$timedOut"
        "elapsed_ms=$elapsedMs"
        if ($null -ne $launchError) { "launch_error=$launchError" }
        '--- stdout ---'
    ) | Set-Content -LiteralPath $combined
    if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout | Add-Content $combined }
    '--- stderr ---' | Add-Content -LiteralPath $combined
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr | Add-Content $combined }

    $dumpOk = $true
    if ($RequireNewMinidump) {
        $newDumps = @(
            Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue |
                Where-Object {
                    $signature = "$($_.Length):$($_.LastWriteTimeUtc.Ticks)"
                    (-not $beforeDumps.ContainsKey($_.FullName)) -or
                        $beforeDumps[$_.FullName] -ne $signature
                }
        )
        $valid = @()
        foreach ($dump in $newDumps) {
            $header = New-Object byte[] 4
            $stream = $null
            try {
                $stream = [System.IO.File]::OpenRead($dump.FullName)
                $read = $stream.Read($header, 0, 4)
            } finally {
                if ($null -ne $stream) { $stream.Dispose() }
            }
            $magic = if ($read -eq 4) { [System.Text.Encoding]::ASCII.GetString($header) } else { '' }
            if ($dump.Length -gt 4096 -and $magic -eq 'MDMP') {
                $destination = Join-Path $Crash ($Name + '-' + $dump.Name)
                Move-Item -LiteralPath $dump.FullName -Destination $destination
                $valid += Get-Item -LiteralPath $destination
                "new_minidump=$destination bytes=$($dump.Length)" | Add-Content $combined
            }
        }
        if ($valid.Count -ne 1) {
            "minidump_error=valid_new_count=$($valid.Count) expected=1" | Add-Content $combined
            $dumpOk = $false
        }
    }

    $exitOk = if ($RequireNonZero) { $exitCode -ne 0 } else { $exitCode -eq 0 }
    $ok = ($null -eq $launchError) -and (-not $timedOut) -and $exitOk -and $dumpOk
    foreach ($marker in $Markers) {
        if (-not (Select-String -LiteralPath $combined -SimpleMatch $marker -Quiet)) {
            "missing_marker=$marker" | Add-Content $combined
            $ok = $false
        }
    }
    foreach ($marker in $ForbiddenMarkers) {
        if (Select-String -LiteralPath $combined -SimpleMatch $marker -Quiet) {
            "forbidden_marker=$marker" | Add-Content $combined
            $ok = $false
        }
    }
    if ($ok) {
        Add-Result "PASS $Name exit=$exitCode elapsed_ms=$elapsedMs"
    } else {
        Add-Result "FAIL $Name exit=$exitCode timed_out=$timedOut"
        $script:Failed = $true
    }
}

function Invoke-MatrixCase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Jar,
        [Parameter(Mandatory = $true)][string]$Class,
        [Parameter(Mandatory = $true)][string]$Marker
    )
    Clear-ArtEnvironment
    $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
    Invoke-CheckedProcess $Name "$script:Common -cp run\$Jar $Class" @(
        $Marker
        'main end exception=0'
        'Windows x64 JIT dual-view (J-2) created'
    ) @('missing_marker=', 'forbidden_marker=')
}

$script:Common = '-Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -XjdwpProvider:none -Xms64m -Xmx512m'
$HelloMarkers = @('Hello from dalvikvm!', 'main end exception=0')

Add-Result "W-025 JIT-4 final native regression $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem
    @(
        "caption=$($os.Caption)"
        "version=$($os.Version)"
        "build=$($os.BuildNumber)"
        "architecture=$($os.OSArchitecture)"
        "total_physical_memory_bytes=$($computer.TotalPhysicalMemory)"
        "free_physical_memory_kib=$($os.FreePhysicalMemory)"
        $PSVersionTable | Format-List | Out-String
    ) | Set-Content (Join-Path $Logs 'HOST_INFO.txt')
    if ([int]$os.BuildNumber -lt 17134) { throw "Windows build $($os.BuildNumber) is below 17134" }
    Add-Result "PASS host_os build=$($os.BuildNumber)"
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'HOST_INFO.txt')
    Add-Result 'FAIL host_os'
    $script:Failed = $true
}

try {
    Test-PackageIntegrity
    Copy-Item -LiteralPath (Join-Path $Root 'W025_JIT4_SOURCE_REPORT.txt') `
        -Destination (Join-Path $Logs 'W025_JIT4_SOURCE_REPORT.txt')
    Add-Result 'PASS package_integrity'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'PACKAGE_INTEGRITY_ERROR.txt')
    Add-Result 'FAIL package_integrity'
    $script:Failed = $true
}

# Exact native equivalents of the 12-record JIT smoke gate.
Clear-ArtEnvironment
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'smoke_default_verbose' "$script:Common -cp run\hello.jar Hello" @(
    $HelloMarkers
    'JitCodeCache::Create OK'
    'Windows x64 JIT dual-view (J-2) created'
    'Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder'
    'Windows x64 CompileMethod done success=1 method=java.lang.StringFactory.newStringFromBytes'
)

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_JIT = '0'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'smoke_env_disabled' "$script:Common -cp run\hello.jar Hello" $HelloMarkers @(
    'Windows x64 CompileMethod done success=1'
)

Clear-ArtEnvironment
Invoke-CheckedProcess 'smoke_xusejit_false' "$script:Common -Xusejit:false -cp run\hello.jar Hello" $HelloMarkers

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_JIT_FILTER = 'StringBuilder'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'smoke_filter' "$script:Common -cp run\hello.jar Hello" @(
    $HelloMarkers
    'Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder'
)

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_JIT_EXCLUDE = 'StringBuilder'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'smoke_exclude' "$script:Common -cp run\hello.jar Hello" $HelloMarkers @(
    'Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder'
)

Clear-ArtEnvironment
Invoke-CheckedProcess 'smoke_quiet' "$script:Common -cp run\hello.jar Hello" $HelloMarkers @(
    'Windows x64 CompileMethod done success=1'
)

# Exact workload set from the 14-record JIT matrix.
Invoke-MatrixCase 'matrix_cenc' 'CEnc.jar' 'CEnc' 'main end exception=0'
Invoke-MatrixCase 'matrix_cenc2' 'CEnc2.jar' 'CEnc2' 'main end exception=0'
Invoke-MatrixCase 'matrix_celike' 'CELike.jar' 'CELike' 'main end exception=0'
Invoke-MatrixCase 'matrix_cfloat' 'CFloat.jar' 'CFloat' 'main end exception=0'
Invoke-MatrixCase 'matrix_floatprobe' 'FloatProbe.jar' 'FloatProbe' 'FloatProbe OK'
Invoke-MatrixCase 'matrix_ifloat' 'IFloat.jar' 'IFloat' 'IFloat OK'
Invoke-MatrixCase 'matrix_jlfloat' 'JLFloat.jar' 'JLFloat' 'main end exception=0'
Invoke-MatrixCase 'matrix_rfloat' 'RFloat.jar' 'RFloat' 'main end exception=0'
Invoke-MatrixCase 'matrix_sfloat' 'SFloat.jar' 'SFloat' 'main end exception=0'
Invoke-MatrixCase 'matrix_math' 'MathProbe.jar' 'MathProbe' 'MathProbe.done=ok'
Invoke-MatrixCase 'matrix_io' 'ioprobe.jar' 'IoProbe' 'IoProbe.done=ok'
Invoke-MatrixCase 'matrix_net' 'netprobe.jar' 'NetProbe' 'NetProbe.done=ok'
Invoke-MatrixCase 'matrix_gc' 'gcprobe.jar' 'GcProbe' 'GcProbe.done=ok'
Invoke-MatrixCase 'matrix_throw' 'throwprobe.jar' 'ThrowProbe' 'phase3-throw-ok'

Clear-ArtEnvironment
Invoke-CheckedProcess 'critical_default' "$script:Common -Xjitthreshold:0 -Dcritical.load=library -Dcritical.instrumentation=1 -Djava.library.path=empty-native-dir;. -cp run\criticalnativeprobe.jar CriticalNativeProbe" @(
    'CriticalNativeProbe instrumentation OK'
    'CriticalNativeDlsymProbe postTracing OK'
    'CriticalNativeProbe tracingMode before=0'
    'main end exception=0'
    'Windows x64 JIT dual-view (J-2) created'
)

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_JIT_FILTER = 'FastNativeAbiProbe'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'native_abi_default' "$script:Common -Xjitthreshold:0 -Dnative.abi.instrumentation=1 -Djava.library.path=empty-native-dir;. -cp run\fastnativeabiprobe.jar FastNativeAbiProbe" @(
    'FastNativeAbiProbe OK'
    'FastNativeAbiProbe tracingMode before=0'
    'success=1 method=double FastNativeAbiProbe.normalRegistered('
    'success=1 method=double FastNativeAbiProbe.fastRegistered('
    'success=1 method=double FastNativeAbiProbe.normalDlsym('
    'success=1 method=double FastNativeAbiProbe.fastDlsym('
    'success=1 method=double FastNativeAbiProbe.normalInstance('
    'success=1 method=double FastNativeAbiProbe.fastInstance('
    'success=1 method=int FastNativeAbiProbe.callMask('
    'main end exception=0'
    'Windows x64 JIT dual-view (J-2) created'
)

$OsrMarkers = @(
    'warmup_threshold=100, optimize_threshold=100'
    'W002OsrProbe OK checksum=65553463744'
    'kind=Baseline'
    'kind=Osr'
    'Jumping to long W002OsrProbe.osrLoop(int)'
    'main end exception=0'
    'Windows x64 JIT dual-view (J-2) created'
)
foreach ($interpreter in @('nterp', 'switch')) {
    Clear-ArtEnvironment
    if ($interpreter -eq 'switch') { $env:ART_WINDOWS_X64_NTERP = '0' }
    $env:ART_WINDOWS_X64_JIT_FILTER = 'W002OsrProbe.osrLoop'
    $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
    $markers = @($OsrMarkers)
    $forbidden = @()
    if ($interpreter -eq 'switch') {
        $markers += 'Done running OSR code for long W002OsrProbe.osrLoop(int)'
    } else {
        $forbidden += 'Done running OSR code for long W002OsrProbe.osrLoop(int)'
    }
    Invoke-CheckedProcess "osr_$interpreter" "$script:Common -verbose:jit -Xjitwarmupthreshold:100 -Xjitthreshold:100 -cp run\w002osrprobe.jar W002OsrProbe" $markers $forbidden
}

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_JIT_FILTER = 'W025JitLifecycleStressProbe'
Invoke-CheckedProcess 'lifecycle_default' "$script:Common -Xjitwarmupthreshold:65535 -Xjitthreshold:65535 -Xjitinitialsize:4M -Xjitmaxsize:16M -XX:DumpJITInfoOnShutdown -Djava.library.path=.;run -cp run\w025jitlifecyclestressprobe.jar W025JitLifecycleStressProbe 8" @(
    'W025_JIT3_PASS methods=24 managed=16 jni=8 unique_allocations=24 cycles=8 collections=8 compilations=216 exact_reuse=192'
    'missing_live=0 stale_dead=0 unwind_failures=0'
    'callback_tables=0'
    'W025JitLifecycleStressProbe PASS cycles=8'
    'jni_values=pass'
    'main end exception=0'
    'Windows x64 JIT dual-view (J-2) created: capacity=16MiB'
) @('W025_JIT3_FAIL', 'AssertionError') -TimeoutSeconds 600

$FatalMarkers = @(
    'ART Win32 VEH: exception 0xc0000005'
    'ART Win32 UEF: exception 0xc0000005'
    'minidump written'
)
Clear-ArtEnvironment
Invoke-CheckedProcess 'fatal_static' "$script:Common -Xint -cp run\crashnativeprobe.jar CrashNativeProbe" @(
    'CrashNativeProbe.start'
    $FatalMarkers
) @('CrashNativeProbe.unexpected_continue') -RequireNonZero -RequireNewMinidump -TimeoutSeconds 120

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_CRASH_NATIVE_WARMUP = '20000'
$env:ART_WINDOWS_X64_JIT_FILTER = 'CrashNativeProbe'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'fatal_jit_default' "$script:Common -verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0 -cp run\crashnativeprobe.jar CrashNativeProbe jit" @(
    'CrashNativeProbe.jit_ready calls=20000'
    'Windows x64 CompileMethod done success=1 method=void CrashNativeProbe.jitCrashCaller(int)'
    'Windows x64 CompileMethod done success=1 method=void CrashNativeProbe.nativeSegfault()'
    'Windows x64 JIT dual-view (J-2) created'
    $FatalMarkers
) @('CrashNativeProbe.unexpected_continue') -RequireNonZero -RequireNewMinidump -TimeoutSeconds 120

Clear-ArtEnvironment
$env:ART_WINDOWS_X64_NTERP = '0'
$env:ART_WINDOWS_X64_JIT_FILTER = 'CrashNativeProbe.osrCrashLoop'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'fatal_osr_default' "$script:Common -verbose:jit -Xjitwarmupthreshold:100 -Xjitthreshold:100 -cp run\crashnativeprobe.jar CrashNativeProbe osr" @(
    'CrashNativeProbe.osr_armed count=2000000'
    'warmup_threshold=100, optimize_threshold=100'
    'kind=Baseline'
    'kind=Osr'
    'Windows x64 CompileMethod done success=1 method=long CrashNativeProbe.osrCrashLoop(int)'
    'Jumping to long CrashNativeProbe.osrCrashLoop(int)'
    'Windows x64 JIT dual-view (J-2) created'
    $FatalMarkers
) @(
    'Done running OSR code for long CrashNativeProbe.osrCrashLoop(int)'
    'CrashNativeProbe.osr_unexpected_return'
    'CrashNativeProbe.unexpected_continue'
) -RequireNonZero -RequireNewMinidump -TimeoutSeconds 180

Clear-ArtEnvironment

$tempFiles = @(Get-ChildItem -Path $JitTemp -Recurse -File -ErrorAction SilentlyContinue)
if ($tempFiles.Count -eq 0) {
    Add-Result 'PASS no_jit_temp_files count=0'
} else {
    $tempFiles.FullName | Set-Content (Join-Path $Logs 'JIT_TEMP_FILES.txt')
    Add-Result "FAIL no_jit_temp_files count=$($tempFiles.Count)"
    $script:Failed = $true
}

$badPatterns = @('Check failed:', 'Fatal signal', 'Unhandled page fault', 'Unhandled exception', 'Access violation', 'STATUS_ACCESS_VIOLATION', '0xc0000005', 'missing_marker=', 'forbidden_marker=', 'launch_error=')
$scanFailed = $false
$nonfatalLogs = @(Get-ChildItem -Path $Logs -Filter '*.log' -File | Where-Object { $_.Name -notlike 'fatal_*' })
foreach ($pattern in $badPatterns) {
    $matches = @($nonfatalLogs | Select-String -SimpleMatch $pattern)
    if ($matches.Count -ne 0) {
        Add-Result "FAIL nonfatal_log_scan pattern=$pattern count=$($matches.Count)"
        $scanFailed = $true
        $script:Failed = $true
    }
}
if (-not $scanFailed) { Add-Result 'PASS nonfatal_log_scan' }

$dumps = @(Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue)
if ($dumps.Count -eq 3) {
    $records = @()
    foreach ($dump in $dumps) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dump.FullName).Hash.ToLowerInvariant()
        $records += "path=$($dump.FullName) bytes=$($dump.Length) sha256=$hash"
    }
    $records | Set-Content (Join-Path $Logs 'FATAL_DMP_SCAN.txt')
    Add-Result 'PASS fatal_dump_scan count=3'
} else {
    $dumps.FullName | Set-Content (Join-Path $Logs 'FATAL_DMP_SCAN.txt')
    Add-Result "FAIL fatal_dump_scan count=$($dumps.Count) expected=3"
    $script:Failed = $true
}

$traceFiles = @(Get-ChildItem -Path $Root -Recurse -File -Filter '*.trace' -ErrorAction SilentlyContinue)
if ($traceFiles.Count -eq 0) {
    Add-Result 'PASS trace_cleanup count=0'
} else {
    $traceFiles.FullName | Set-Content (Join-Path $Logs 'TRACE_FILES.txt')
    Add-Result "FAIL trace_cleanup count=$($traceFiles.Count)"
    $script:Failed = $true
}

$resultPath = Join-Path $Logs 'RESULT_W025_JIT4.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
