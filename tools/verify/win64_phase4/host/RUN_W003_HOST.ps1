$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
Get-ChildItem -Path $Logs -File -ErrorAction SilentlyContinue | Remove-Item -Force

$env:ANDROID_ROOT = 'run'
$env:ANDROID_ART_ROOT = 'run'
$env:ANDROID_I18N_ROOT = 'run'
$env:ANDROID_DATA = 'run\data'
$env:ICU_DATA = 'run\icu'

$script:Results = New-Object System.Collections.Generic.List[string]
$script:Failed = $false
$script:PreflightPassed = $true

function Add-Result([string]$Text) {
    $script:Results.Add($Text)
    Write-Host $Text
}

function Clear-W003Environment {
    @(
        'ART_WIN64_JIT'
        'ART_WIN64_JIT_DUAL'
        'ART_WIN64_JIT_EXCLUDE'
        'ART_WIN64_JIT_FILTER'
        'ART_WIN64_JIT_LOG_COMPILES'
        'ART_WIN64_NTERP'
        'ART_WIN64_QUICK_INVOKE'
    ) | ForEach-Object {
        Remove-Item -Path ('Env:' + $_) -ErrorAction SilentlyContinue
    }
}

function Test-PackageIntegrity {
    $sumsPath = Join-Path $Root 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) {
        throw 'SHA256SUMS.txt is missing'
    }
    foreach ($line in Get-Content -LiteralPath $sumsPath) {
        if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
            throw "Invalid SHA256SUMS line: $line"
        }
        $expected = $Matches[1].ToLowerInvariant()
        $relative = $Matches[2] -replace '^\./', ''
        $relative = $relative -replace '/', '\'
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Manifest file is missing: $relative"
        }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "SHA-256 mismatch: $relative"
        }
    }
}

function Read-ReportValues {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath (Join-Path $Root 'W003_STRUCTURAL_REPORT.txt')) {
        if ($line -match '^([^=]+)=(.*)$') {
            $values[$Matches[1]] = $Matches[2]
        }
    }
    return $values
}

function Test-StructuralReport {
    $report = Join-Path $Root 'W003_STRUCTURAL_REPORT.txt'
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'W003_STRUCTURAL_REPORT.txt is missing'
    }
    $required = @(
        '^status=PASS$'
        '^product_probe_exports=0$'
        '^frame_probe_exports=2$'
        '^frame_counter_symbols=4$'
        '^frame_jni_exports=3$'
        '^xmm_jni_exports=1$'
        '^xmm_unwind_saves=6$'
        '^host_llvm_tools_required=no$'
    )
    foreach ($pattern in $required) {
        if (-not (Select-String -LiteralPath $report -Pattern $pattern -Quiet)) {
            throw "Structural report is missing: $pattern"
        }
    }
    $values = Read-ReportValues
    $hashes = @{
        'product_art_sha256' = 'art.product.dll'
        'frame_art_sha256' = 'art.frame-probe.dll'
        'frame_probe_dll_sha256' = 'libw003frameprobe.dll'
        'xmm_probe_dll_sha256' = 'libw003xmmsentinel.dll'
    }
    foreach ($entry in $hashes.GetEnumerator()) {
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root $entry.Value)).Hash.ToLowerInvariant()
        if ($values[$entry.Key] -ne $actual) {
            throw "Structural report hash mismatch: $($entry.Value)"
        }
    }
}

function Set-ArtVariant([string]$Name) {
    $source = Join-Path $Root $Name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "ART variant is missing: $Name"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $Root 'art.dll') -Force
}

function Get-FrameCounter {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Mode,
        [Parameter(Mandatory = $true)][string]$Phase,
        [Parameter(Mandatory = $true)][string]$Family
    )
    $prefix = "W003FrameProbe mode=$Mode phase=$Phase counts="
    $line = Get-Content -LiteralPath $Path | Where-Object { $_.StartsWith($prefix) } | Select-Object -Last 1
    if ($null -eq $line) {
        throw "Missing frame counter line: mode=$Mode phase=$Phase"
    }
    $pattern = [regex]::Escape($Family) + ':([0-9]+)'
    if ($line -notmatch $pattern) {
        throw "Missing frame counter: mode=$Mode phase=$Phase family=$Family"
    }
    return [long]$Matches[1]
}

function Test-FrameCounters {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Mode
    )
    if ((Get-FrameCounter -Path $Path -Mode $Mode -Phase 'refs_and_args' -Family 'refs_and_args') -le 0) {
        throw "$Mode refs-and-args counter is zero"
    }
    if ((Get-FrameCounter -Path $Path -Mode $Mode -Phase 'everything' -Family 'everything') -le 0) {
        throw "$Mode save-everything counter is zero"
    }
    if ($Mode -in @('nterp', 'jit')) {
        if ((Get-FrameCounter -Path $Path -Mode $Mode -Phase 'refs_only' -Family 'refs_only') -le 0) {
            throw "$Mode refs-only counter is zero"
        }
        if ((Get-FrameCounter -Path $Path -Mode $Mode -Phase 'all_callee_saves' -Family 'all_callee_saves') -le 0) {
            throw "$Mode all-callee-saves counter is zero"
        }
    }
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [string[]]$Markers = @(),
        [string]$FrameMode = '',
        [int]$TimeoutSeconds = 180
    )

    $stdout = Join-Path $Logs ($Name + '.stdout.log')
    $stderr = Join-Path $Logs ($Name + '.stderr.log')
    $combined = Join-Path $Logs ($Name + '.log')
    $started = Get-Date
    $process = $null
    $launchError = $null
    $timedOut = $false
    $exitCode = -1
    try {
        $process = Start-Process -FilePath (Join-Path $Root 'dalvikvm.exe') -WorkingDirectory $Root -ArgumentList $Arguments -RedirectStandardOutput $stdout -RedirectStandardError $stderr -NoNewWindow -PassThru
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
        if ($null -ne $process) {
            $process.Dispose()
        }
    }
    $elapsedMs = [long]((Get-Date) - $started).TotalMilliseconds

    @(
        "name=$Name"
        "exit=$exitCode"
        'expected_exit=0'
        "timeout_seconds=$TimeoutSeconds"
        "timed_out=$timedOut"
        "elapsed_ms=$elapsedMs"
        if ($null -ne $launchError) { "launch_error=$launchError" }
        '--- stdout ---'
    ) | Set-Content -LiteralPath $combined
    if (Test-Path -LiteralPath $stdout) {
        Get-Content -LiteralPath $stdout | Add-Content -LiteralPath $combined
    }
    '--- stderr ---' | Add-Content -LiteralPath $combined
    if (Test-Path -LiteralPath $stderr) {
        Get-Content -LiteralPath $stderr | Add-Content -LiteralPath $combined
    }

    $ok = ($null -eq $launchError) -and (-not $timedOut) -and ($exitCode -eq 0)
    foreach ($marker in $Markers) {
        if (-not (Select-String -LiteralPath $combined -SimpleMatch $marker -Quiet)) {
            $ok = $false
            Add-Content -LiteralPath $combined -Value "missing_marker=$marker"
        }
    }
    if ($ok -and $FrameMode -ne '') {
        try {
            Test-FrameCounters -Path $combined -Mode $FrameMode
        } catch {
            $ok = $false
            Add-Content -LiteralPath $combined -Value ('counter_error=' + $_.Exception.Message)
        }
    }
    if ($ok) {
        Add-Result "PASS $Name exit=$exitCode elapsed_ms=$elapsedMs"
    } else {
        Add-Result "FAIL $Name exit=$exitCode timed_out=$timedOut"
        $script:Failed = $true
    }
}

$Common = '-Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -XjdwpProvider:none -Xms64m -Xmx512m'

Add-Result "W-003 native host acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $buildNumber = [int]$os.BuildNumber
    $os | Select-Object Caption, Version, BuildNumber, OSArchitecture | Format-List | Out-String | Set-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    $PSVersionTable | Format-List | Out-String | Add-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    if ($buildNumber -lt 17134) {
        throw "Windows build $buildNumber is older than the Windows 10 RS4 baseline 17134"
    }
    Add-Result "PASS host_os build=$buildNumber"
} catch {
    $_.Exception.ToString() | Add-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    Add-Result 'FAIL host_os'
    $script:Failed = $true
    $script:PreflightPassed = $false
}

try {
    Test-PackageIntegrity
    Add-Result 'PASS package_integrity'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'PACKAGE_INTEGRITY.txt')
    Add-Result 'FAIL package_integrity'
    $script:Failed = $true
    $script:PreflightPassed = $false
}

try {
    Test-StructuralReport
    Copy-Item -LiteralPath (Join-Path $Root 'W003_STRUCTURAL_REPORT.txt') -Destination (Join-Path $Logs 'W003_STRUCTURAL_REPORT.txt') -Force
    Add-Result 'PASS structural_report'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'W003_STRUCTURAL_REPORT_ERROR.txt')
    Add-Result 'FAIL structural_report'
    $script:Failed = $true
    $script:PreflightPassed = $false
}

if ($script:PreflightPassed) {
    try {
        Set-ArtVariant 'art.frame-probe.dll'
        foreach ($mode in @('int', 'switch', 'nterp', 'jit')) {
            foreach ($repeat in 1..2) {
                Clear-W003Environment
                $env:ART_WIN64_QUICK_INVOKE = '1'
                $vmArgs = ''
                if ($mode -eq 'int') {
                    $env:ART_WIN64_JIT = '0'
                    $env:ART_WIN64_NTERP = '0'
                    $vmArgs = '-Xint'
                } elseif ($mode -eq 'switch') {
                    $env:ART_WIN64_JIT = '0'
                    $env:ART_WIN64_NTERP = '0'
                } elseif ($mode -eq 'nterp') {
                    $env:ART_WIN64_JIT = '0'
                    $env:ART_WIN64_NTERP = '1'
                } else {
                    $env:ART_WIN64_JIT = '1'
                    $env:ART_WIN64_NTERP = '1'
                    $env:ART_WIN64_JIT_FILTER = 'W003FrameProbe'
                    $env:ART_WIN64_JIT_LOG_COMPILES = '1'
                    $vmArgs = '-verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0'
                }
                $name = 'frame_{0}_run{1:D2}' -f $mode, $repeat
                $markers = @(
                    "W003FrameProbe mode=$mode phase=refs_only counts="
                    "W003FrameProbe mode=$mode phase=refs_and_args counts="
                    "W003FrameProbe mode=$mode phase=all_callee_saves counts="
                    "W003FrameProbe mode=$mode phase=everything counts="
                    "W003FrameProbe OK mode=$mode"
                    'main end exception=0'
                )
                Invoke-CheckedProcess -Name $name -Arguments "$Common $vmArgs -Dw003.mode=$mode -Djava.library.path=. -cp run\w003frameprobe.jar W003FrameProbe" -Markers $markers -FrameMode $mode
            }
        }

        Set-ArtVariant 'art.product.dll'
        foreach ($mode in @('nterp', 'switch', 'jit')) {
            foreach ($repeat in 1..2) {
                Clear-W003Environment
                $env:ART_WIN64_QUICK_INVOKE = '1'
                $vmArgs = ''
                if ($mode -eq 'nterp') {
                    $env:ART_WIN64_JIT = '0'
                    $env:ART_WIN64_NTERP = '1'
                } elseif ($mode -eq 'switch') {
                    $env:ART_WIN64_JIT = '0'
                    $env:ART_WIN64_NTERP = '0'
                } else {
                    $env:ART_WIN64_JIT = '1'
                    $env:ART_WIN64_NTERP = '1'
                    $env:ART_WIN64_JIT_FILTER = 'W003XmmSentinelProbe.managedCallback'
                    $env:ART_WIN64_JIT_LOG_COMPILES = '1'
                    $vmArgs = '-verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0'
                }
                $name = 'xmm_{0}_run{1:D2}' -f $mode, $repeat
                $markers = @(
                    "W003XmmSentinelProbe mode=$mode"
                    'mask=0 selfTestMask=63 iterations=128'
                    'W003XmmSentinelProbe OK'
                    'main end exception=0'
                )
                if ($mode -eq 'jit') {
                    $markers += 'success=1 method=int W003XmmSentinelProbe.managedCallback('
                }
                Invoke-CheckedProcess -Name $name -Arguments "$Common $vmArgs -Dw003.mode=$mode -Djava.library.path=. -cp run\w003xmmsentinelprobe.jar W003XmmSentinelProbe" -Markers $markers
            }
        }
    } finally {
        Set-ArtVariant 'art.product.dll'
        Clear-W003Environment
    }
} else {
    Add-Result 'FAIL test_matrix skipped_preflight'
    $script:Failed = $true
    Clear-W003Environment
}

$badLogPatterns = @(
    'Check failed:'
    'Fatal signal'
    'Unhandled page fault'
    'Unhandled exception'
    'Access violation'
    'STATUS_ACCESS_VIOLATION'
    '0xc0000005'
    'ART Win64 VEH'
    'ART Win64 UEF'
)
$logScanFailed = $false
foreach ($pattern in $badLogPatterns) {
    $matches = @(Get-ChildItem -Path $Logs -Filter '*.log' -File | Select-String -SimpleMatch $pattern)
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

$resultPath = Join-Path $Logs 'RESULT_W003.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
