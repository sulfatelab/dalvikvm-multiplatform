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

function Add-Result([string]$Text) {
    $script:Results.Add($Text)
    Write-Host $Text
}

function Clear-W002Environment {
    @(
        'ART_WINDOWS_X64_JIT'
        'ART_WINDOWS_X64_JIT_DUAL'
        'ART_WINDOWS_X64_JIT_EXCLUDE'
        'ART_WINDOWS_X64_JIT_FILTER'
        'ART_WINDOWS_X64_JIT_LOG_COMPILES'
        'ART_WINDOWS_X64_NTERP'
        'ART_WINDOWS_X64_QUICK_INVOKE'
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

function Test-StructuralReport {
    $report = Join-Path $Root 'W002_STRUCTURAL_REPORT.txt'
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'W002_STRUCTURAL_REPORT.txt is missing'
    }
    $required = @(
        '^status=PASS$'
        '^attach_exports=2$'
        '^art_sha256=[0-9a-f]{64}$'
        '^attach_dll_sha256=[0-9a-f]{64}$'
        '^host_llvm_tools_required=no$'
    )
    foreach ($pattern in $required) {
        if (-not (Select-String -LiteralPath $report -Pattern $pattern -Quiet)) {
            throw "Structural report is missing: $pattern"
        }
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $report) {
        if ($line -match '^([^=]+)=(.*)$') {
            $values[$Matches[1]] = $Matches[2]
        }
    }
    $artHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root 'art.dll')).Hash.ToLowerInvariant()
    $attachHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root 'libw002attachprobe.dll')).Hash.ToLowerInvariant()
    if ($values['art_sha256'] -ne $artHash) {
        throw 'Structural report art.dll hash does not match the packaged artifact'
    }
    if ($values['attach_dll_sha256'] -ne $attachHash) {
        throw 'Structural report attach DLL hash does not match the packaged artifact'
    }
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Arguments,
        [string[]]$Markers = @(),
        [string[]]$ForbiddenMarkers = @(),
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
    foreach ($marker in $ForbiddenMarkers) {
        if (Select-String -LiteralPath $combined -SimpleMatch $marker -Quiet) {
            $ok = $false
            Add-Content -LiteralPath $combined -Value "forbidden_marker=$marker"
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

Add-Result "W-002 native host acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
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
}

try {
    Test-PackageIntegrity
    Add-Result 'PASS package_integrity'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'PACKAGE_INTEGRITY.txt')
    Add-Result 'FAIL package_integrity'
    $script:Failed = $true
}

try {
    Test-StructuralReport
    Copy-Item -LiteralPath (Join-Path $Root 'W002_STRUCTURAL_REPORT.txt') -Destination (Join-Path $Logs 'W002_STRUCTURAL_REPORT.txt') -Force
    Add-Result 'PASS structural_report'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'W002_STRUCTURAL_REPORT_ERROR.txt')
    Add-Result 'FAIL structural_report'
    $script:Failed = $true
}

$OsrMarkers = @(
    'warmup_threshold=100, optimize_threshold=100'
    'W002OsrProbe OK checksum=65553463744'
    'kind=Baseline'
    'kind=Osr'
    'Jumping to long W002OsrProbe.osrLoop(int)'
    'main end exception=0'
)
$AttachMarkers = @(
    'W002AttachProbe OK completed=16'
    'Windows x64 CompileMethod done success=1 method=long W002AttachProbe.attachedCallback(boolean, int)'
    'main end exception=0'
)
$SwitchCompletion = 'Done running OSR code for long W002OsrProbe.osrLoop(int)'

foreach ($mode in @('dual', 'j1')) {
    foreach ($interpreter in @('default', 'switch')) {
        foreach ($repeat in 1..2) {
            Clear-W002Environment
            if ($mode -eq 'dual') {
                $env:ART_WINDOWS_X64_JIT_DUAL = '1'
            } else {
                $env:ART_WINDOWS_X64_JIT_DUAL = '0'
            }
            if ($interpreter -eq 'switch') {
                $env:ART_WINDOWS_X64_NTERP = '0'
            }
            $env:ART_WINDOWS_X64_JIT_FILTER = 'W002OsrProbe.osrLoop'
            $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
            $osrRequired = @($OsrMarkers)
            $osrForbidden = @()
            if ($interpreter -eq 'switch') {
                $osrRequired += $SwitchCompletion
            } else {
                $osrForbidden += $SwitchCompletion
            }
            $osrName = 'osr_{0}_{1}_run{2:D2}' -f $mode, $interpreter, $repeat
            Invoke-CheckedProcess $osrName "$Common -verbose:jit -Xjitwarmupthreshold:100 -Xjitthreshold:100 -cp run\w002osrprobe.jar W002OsrProbe" $osrRequired $osrForbidden

            Clear-W002Environment
            if ($mode -eq 'dual') {
                $env:ART_WINDOWS_X64_JIT_DUAL = '1'
            } else {
                $env:ART_WINDOWS_X64_JIT_DUAL = '0'
            }
            if ($interpreter -eq 'switch') {
                $env:ART_WINDOWS_X64_NTERP = '0'
            }
            $env:ART_WINDOWS_X64_JIT_FILTER = 'W002AttachProbe.attachedCallback'
            $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
            $attachName = 'attach_{0}_{1}_run{2:D2}' -f $mode, $interpreter, $repeat
            Invoke-CheckedProcess $attachName "$Common -Xjitthreshold:0 -Djava.library.path=. -cp run\w002attachprobe.jar W002AttachProbe" $AttachMarkers
        }
    }
}
Clear-W002Environment

$badLogPatterns = @(
    'Check failed:'
    'Fatal signal'
    'Unhandled page fault'
    'Unhandled exception'
    'Access violation'
    'STATUS_ACCESS_VIOLATION'
    '0xc0000005'
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

$resultPath = Join-Path $Logs 'RESULT_W002.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
