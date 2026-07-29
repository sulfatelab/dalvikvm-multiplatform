$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root 'logs'
$Checker = Join-Path $PSScriptRoot 'check_fs1_stack_high_water.py'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
Get-ChildItem -Path $Logs -File -ErrorAction SilentlyContinue | Remove-Item -Force

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
        $relative = ($Matches[2] -replace '^\./', '') -replace '/', '\'
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

function Invoke-Fs1Mode {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('Release', 'Debug')][string]$BuildType,
        [Parameter(Mandatory = $true)][ValidateSet('switch', 'nterp', 'jit')][string]$Mode
    )

    Clear-ArtEnvironment
    $runtime = Join-Path $Root ($BuildType.ToLowerInvariant())
    $runRoot = (Resolve-Path -LiteralPath (Join-Path $runtime 'run')).Path
    $dataRoot = Join-Path $runRoot 'data'
    $crashRoot = Join-Path $runRoot 'crash'
    New-Item -ItemType Directory -Force -Path $dataRoot, $crashRoot | Out-Null

    $env:ANDROID_ROOT = $runRoot
    $env:ANDROID_ART_ROOT = $runRoot
    $env:ANDROID_I18N_ROOT = $runRoot
    $env:ANDROID_DATA = $dataRoot
    $env:ICU_DATA = Join-Path $runRoot 'icu'

    $arguments = @(
        ('-Xbootclasspath:"{0}"' -f (Join-Path $runRoot 'boot.jar'))
        ('-Xbootclasspath-locations:"{0}"' -f (Join-Path $runRoot 'boot.jar'))
        '-Ximage:/nonexistent-no-boot-image'
        '-XjdwpProvider:none'
        '-Xms64m'
        '-Xmx512m'
    )
    if ($BuildType -eq 'Debug') {
        # Debug recursion is intentionally slow. Do not let unrelated suspend-all
        # work turn this stack-overflow measurement into a two-second timeout.
        $arguments += '-XX:ThreadSuspendTimeout=30000'
    }

    if ($Mode -eq 'switch') {
        $env:ART_WINDOWS_X64_JIT = '0'
        $env:ART_WINDOWS_X64_NTERP = '0'
        $arguments += '-Xusejit:false'
    } elseif ($Mode -eq 'nterp') {
        $env:ART_WINDOWS_X64_JIT = '0'
        $env:ART_WINDOWS_X64_NTERP = '1'
        $arguments += '-Xusejit:false'
    } else {
        $env:ART_WINDOWS_X64_JIT = '1'
        $env:ART_WINDOWS_X64_NTERP = '1'
        $env:ART_WINDOWS_X64_JIT_FILTER = 'FS1StackHighWaterProbe'
        $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
        $arguments += @('-verbose:jit', '-Xjitwarmupthreshold:0', '-Xjitthreshold:0')
    }
    $arguments += @(
        '-Djava.library.path=.'
        '-cp'
        ('"{0}"' -f (Join-Path $runRoot 'fs1stackhighwaterprobe.jar'))
        'FS1StackHighWaterProbe'
        $Mode
    )

    $name = '{0}_{1}' -f $BuildType.ToLowerInvariant(), $Mode
    $stdout = Join-Path $Logs ($name + '.stdout.log')
    $stderr = Join-Path $Logs ($name + '.stderr.log')
    $combined = Join-Path $Logs ($name + '.log')
    $timeoutSeconds = if ($BuildType -eq 'Debug') { 300 } else { 180 }
    $started = Get-Date
    $process = $null
    $launchError = $null
    $timedOut = $false
    $exitCode = -1

    try {
        $startParameters = @{
            FilePath = Join-Path $runtime 'dalvikvm.exe'
            WorkingDirectory = $runtime
            ArgumentList = $arguments -join ' '
            RedirectStandardOutput = $stdout
            RedirectStandardError = $stderr
            NoNewWindow = $true
            PassThru = $true
        }
        $process = Start-Process @startParameters
        $null = $process.Handle
        if (-not $process.WaitForExit($timeoutSeconds * 1000)) {
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
        "build_type=$BuildType"
        "mode=$Mode"
        "exit=$exitCode"
        "timeout_seconds=$timeoutSeconds"
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

    $processOk = ($null -eq $launchError) -and (-not $timedOut) -and ($exitCode -eq 0)
    $validation = @()
    $validationExit = -1
    if ($processOk) {
        $expectedReserve = if ($BuildType -eq 'Debug') { 40960 } else { 8192 }
        $validation = @(& python.exe $Checker --log $combined --mode $Mode --art-reserve $expectedReserve 2>&1)
        $validationExit = $LASTEXITCODE
        $validation | Set-Content -LiteralPath (Join-Path $Logs ($name + '.validation.log'))
    }
    if ($processOk -and $validationExit -eq 0) {
        Add-Result "PASS $BuildType $Mode elapsed_ms=$elapsedMs $($validation -join ' ')"
    } else {
        Add-Result "FAIL $BuildType $Mode exit=$exitCode timed_out=$timedOut validation_exit=$validationExit"
        $script:Failed = $true
    }
}

Add-Result "FS-1 native stack high-water acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $os | Select-Object Caption, Version, BuildNumber, OSArchitecture |
        Format-List | Out-String | Set-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    if ([int]$os.BuildNumber -lt 26100) {
        throw "Windows build $($os.BuildNumber) is older than the Server 2025 acceptance host"
    }
    Add-Result "PASS host_os build=$($os.BuildNumber)"
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

foreach ($buildType in @('Release', 'Debug')) {
    $runtime = Join-Path $Root ($buildType.ToLowerInvariant())
    $crashRoot = Join-Path $runtime 'run\crash'
    New-Item -ItemType Directory -Force -Path $crashRoot | Out-Null
    Get-ChildItem -Path $crashRoot -File -Filter '*.dmp' -ErrorAction SilentlyContinue |
        Remove-Item -Force
    foreach ($mode in @('switch', 'nterp', 'jit')) {
        Invoke-Fs1Mode -BuildType $buildType -Mode $mode
    }
}
Clear-ArtEnvironment

$dumps = @(Get-ChildItem -Path $Root -Recurse -File -Filter '*.dmp' -ErrorAction SilentlyContinue)
if ($dumps.Count -eq 0) {
    'NO_DMP_FILES' | Set-Content (Join-Path $Logs 'DMP_SCAN.txt')
    Add-Result 'PASS dump_scan NO_DMP_FILES'
} else {
    $dumps.FullName | Set-Content (Join-Path $Logs 'DMP_SCAN.txt')
    Add-Result "FAIL dump_scan count=$($dumps.Count)"
    $script:Failed = $true
}

$resultPath = Join-Path $Logs 'RESULT_FS1.txt'
$script:Results | Set-Content -LiteralPath $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content -LiteralPath $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content -LiteralPath $resultPath
Write-Host 'OVERALL PASS'
