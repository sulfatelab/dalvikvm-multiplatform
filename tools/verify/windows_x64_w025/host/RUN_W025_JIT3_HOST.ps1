$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root 'logs'
$JitTemp = Join-Path $Root 'jit-temp'
New-Item -ItemType Directory -Force -Path $Logs, $JitTemp | Out-Null
Get-ChildItem -Path $Logs -File -ErrorAction SilentlyContinue | Remove-Item -Force
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

function Clear-JitEnvironment {
    @(
        'ART_WINDOWS_X64_JIT'
        'ART_WINDOWS_X64_JIT_DUAL'
        'ART_WINDOWS_X64_JIT_EXCLUDE'
        'ART_WINDOWS_X64_JIT_FILTER'
        'ART_WINDOWS_X64_JIT_LOG_COMPILES'
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
        [Parameter(Mandatory = $true)][string]$Executable,
        [string]$Arguments = '',
        [string[]]$Markers = @(),
        [string[]]$ForbiddenMarkers = @(),
        [int]$TimeoutSeconds = 600
    )

    $stdout = Join-Path $Logs ($Name + '.stdout.log')
    $stderr = Join-Path $Logs ($Name + '.stderr.log')
    $combined = Join-Path $Logs ($Name + '.log')
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $process = $null
    $launchError = $null
    $timedOut = $false
    $exitCode = -1
    $metricsSampled = $false
    $peakPaged = -1L
    $peakWorkingSet = -1L
    $peakVirtual = -1L
    $parameters = @{
        FilePath = Join-Path $Root $Executable
        WorkingDirectory = $Root
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        NoNewWindow = $true
        PassThru = $true
    }
    if ($Arguments.Length -ne 0) {
        $parameters.ArgumentList = $Arguments
    }
    try {
        $process = Start-Process @parameters
        $null = $process.Handle
        $timeoutMilliseconds = [long]$TimeoutSeconds * 1000L
        while ($true) {
            try {
                $process.Refresh()
                $peakPaged = [Math]::Max($peakPaged, [long]$process.PeakPagedMemorySize64)
                $peakWorkingSet = [Math]::Max($peakWorkingSet, [long]$process.PeakWorkingSet64)
                $peakVirtual = [Math]::Max($peakVirtual, [long]$process.PeakVirtualMemorySize64)
                $metricsSampled = $true
            } catch {
                # A child can exit between refresh and property reads.
            }
            if ($process.WaitForExit(50)) {
                break
            }
            if ($timer.ElapsedMilliseconds -ge $timeoutMilliseconds) {
                $timedOut = $true
                $process.Kill()
                break
            }
        }
        $process.WaitForExit()
        $exitCode = [int]$process.ExitCode
    } catch {
        $launchError = $_.Exception.ToString()
    } finally {
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
    $timer.Stop()
    $elapsedMs = [long]$timer.ElapsedMilliseconds

    @(
        "name=$Name"
        "exit=$exitCode"
        'expected_exit=0'
        "timeout_seconds=$TimeoutSeconds"
        "timed_out=$timedOut"
        "metrics_sampled=$metricsSampled"
        "elapsed_ms=$elapsedMs"
        "peak_paged_bytes=$peakPaged"
        "peak_working_set_bytes=$peakWorkingSet"
        "peak_virtual_bytes=$peakVirtual"
        if ($null -ne $launchError) { "launch_error=$launchError" }
        '--- stdout ---'
    ) | Set-Content -LiteralPath $combined
    if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout | Add-Content $combined }
    '--- stderr ---' | Add-Content $combined
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr | Add-Content $combined }

    $ok = ($null -eq $launchError) -and (-not $timedOut) -and $metricsSampled -and
        ($exitCode -eq 0)
    foreach ($marker in $Markers) {
        if (-not (Select-String -LiteralPath $combined -SimpleMatch $marker -Quiet)) {
            Add-Content -LiteralPath $combined -Value "missing_marker=$marker"
            $ok = $false
        }
    }
    foreach ($marker in $ForbiddenMarkers) {
        if (Select-String -LiteralPath $combined -SimpleMatch $marker -Quiet) {
            Add-Content -LiteralPath $combined -Value "forbidden_marker=$marker"
            $ok = $false
        }
    }

    if ($ok) {
        Add-Result "PASS $Name exit=$exitCode elapsed_ms=$elapsedMs peak_paged_bytes=$peakPaged peak_working_set_bytes=$peakWorkingSet peak_virtual_bytes=$peakVirtual"
    } else {
        Add-Result "FAIL $Name exit=$exitCode timed_out=$timedOut"
        $script:Failed = $true
    }
}

function Invoke-Jit3Case {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$Dual,
        [Parameter(Mandatory = $true)][int]$Cycles
    )
    # The native probe performs concurrent RtlLookupFunctionEntry and
    # RtlVirtualUnwind sampling while ART invalidates, collects, and republishes.
    Clear-JitEnvironment
    $env:ART_WINDOWS_X64_JIT_DUAL = [string]$Dual
    $env:ART_WINDOWS_X64_JIT_FILTER = 'W025JitLifecycleStressProbe'
    $compilations = 24 * ($Cycles + 1)
    $reuse = 24 * $Cycles
    $markers = @(
        "W025_JIT3_PASS methods=24 managed=16 jni=8 unique_allocations=24 cycles=$Cycles collections=$Cycles compilations=$compilations exact_reuse=$reuse"
        'missing_live=0 stale_dead=0 unwind_failures=0'
        'callback_tables=0'
        "W025JitLifecycleStressProbe PASS cycles=$Cycles"
        'jni_values=pass'
        'main end exception=0'
    )
    $forbidden = @(
        'W025_JIT3_FAIL'
        'Unhandled page fault'
        'Access violation'
        'AssertionError'
    )
    if ($Dual -eq 1) {
        $markers += 'Windows x64 JIT dual-view (J-2) created: capacity=16MiB'
    } else {
        $forbidden += 'Windows x64 JIT dual-view (J-2) created'
    }
    Invoke-CheckedProcess $Name 'dalvikvm.exe' "$script:Jit3Arguments $Cycles" `
        $markers $forbidden -TimeoutSeconds 600
}

$Common = '-Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -XjdwpProvider:none -Xms64m -Xmx512m'
$script:Jit3Arguments = "$Common -Xjitwarmupthreshold:65535 -Xjitthreshold:65535 -Xjitinitialsize:4M -Xjitmaxsize:16M -XX:DumpJITInfoOnShutdown -Djava.library.path=.;run -cp run\w025jitlifecyclestressprobe.jar W025JitLifecycleStressProbe"

Add-Result "W-025 JIT-3 native host acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
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
    if ([int]$os.BuildNumber -lt 17134) {
        throw "Windows build $($os.BuildNumber) is below 17134"
    }
    Add-Result "PASS host_os build=$($os.BuildNumber)"
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'HOST_INFO.txt')
    Add-Result 'FAIL host_os'
    $script:Failed = $true
}

try {
    Test-PackageIntegrity
    Copy-Item -LiteralPath (Join-Path $Root 'W025_JIT3_SOURCE_REPORT.txt') `
        -Destination (Join-Path $Logs 'W025_JIT3_SOURCE_REPORT.txt')
    Add-Result 'PASS package_integrity'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'PACKAGE_INTEGRITY_ERROR.txt')
    Add-Result 'FAIL package_integrity'
    $script:Failed = $true
}

Invoke-Jit3Case 'jit3_j2_stress' 1 24
Invoke-Jit3Case 'jit3_j1_compare' 0 12
Invoke-Jit3Case 'jit3_j2_repeat_a' 1 8
Invoke-Jit3Case 'jit3_j2_repeat_b' 1 8

Clear-JitEnvironment
$tempFiles = @(Get-ChildItem -Path $JitTemp -Recurse -File -ErrorAction SilentlyContinue)
if ($tempFiles.Count -eq 0) {
    Add-Result 'PASS no_jit_temp_files count=0'
} else {
    $tempFiles.FullName | Set-Content (Join-Path $Logs 'JIT_TEMP_FILES.txt')
    Add-Result "FAIL no_jit_temp_files count=$($tempFiles.Count)"
    $script:Failed = $true
}

$badLogPatterns = @(
    'W025_JIT3_FAIL'
    'Unhandled page fault'
    'Unhandled exception'
    'Access violation'
    'STATUS_ACCESS_VIOLATION'
    '0xc0000005'
    'AssertionError'
    'missing_marker='
    'forbidden_marker='
    'launch_error='
)
$logScanFailed = $false
foreach ($pattern in $badLogPatterns) {
    $matches = @(Get-ChildItem -Path $Logs -Filter '*.log' -File |
        Select-String -SimpleMatch $pattern)
    if ($matches.Count -ne 0) {
        Add-Result "FAIL log_scan pattern=$pattern count=$($matches.Count)"
        $logScanFailed = $true
        $script:Failed = $true
    }
}
if (-not $logScanFailed) {
    Add-Result 'PASS log_scan'
}

$dumps = @(Get-ChildItem -Path $Root -Recurse -File -Filter '*.dmp' -ErrorAction SilentlyContinue)
if ($dumps.Count -eq 0) {
    'NO_DMP_FILES' | Set-Content (Join-Path $Logs 'DMP_SCAN.txt')
    Add-Result 'PASS dump_scan NO_DMP_FILES'
} else {
    $dumps.FullName | Set-Content (Join-Path $Logs 'DMP_SCAN.txt')
    Add-Result "FAIL dump_scan count=$($dumps.Count)"
    $script:Failed = $true
}

$resultPath = Join-Path $Logs 'RESULT_W025_JIT3.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
