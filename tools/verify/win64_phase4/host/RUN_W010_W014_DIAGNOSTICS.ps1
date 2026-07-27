$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root 'diagnostic_logs'
$Crash = Join-Path $Root 'run\crash'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
New-Item -ItemType Directory -Force -Path $Crash | Out-Null
Get-ChildItem -Path $Logs -File -ErrorAction SilentlyContinue | Remove-Item -Force

$env:ANDROID_ROOT = 'run'
$env:ANDROID_ART_ROOT = 'run'
$env:ANDROID_I18N_ROOT = 'run'
$env:ANDROID_DATA = 'run\data'
$env:ICU_DATA = 'run\icu'

@(
    'ART_WIN64_JIT'
    'ART_WIN64_JIT_DUAL'
    'ART_WIN64_JIT_EXCLUDE'
    'ART_WIN64_JIT_FILTER'
    'ART_WIN64_JIT_LOG_COMPILES'
    'ART_WIN64_NTERP'
    'ART_WIN64_QUICK_INVOKE'
    'ART_WIN64_CRASH_NATIVE_WARMUP'
) | ForEach-Object {
    Remove-Item -Path ('Env:' + $_) -ErrorAction SilentlyContinue
}

$script:Results = New-Object System.Collections.Generic.List[string]
$script:InfrastructureFailed = $false

function Add-Result([string]$Text) {
    $script:Results.Add($Text)
    Write-Host $Text
}

function Invoke-DiagnosticProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Executable,
        [string]$Arguments = '',
        [int]$TimeoutSeconds = 60
    )

    $stdout = Join-Path $Logs ($Name + '.stdout.log')
    $stderr = Join-Path $Logs ($Name + '.stderr.log')
    $combined = Join-Path $Logs ($Name + '.log')
    $process = $null
    $launchError = $null
    $timedOut = $false
    $exitCode = -1
    $started = Get-Date
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

    if ($null -ne $launchError -or $timedOut) {
        $script:InfrastructureFailed = $true
    }
    $text = Get-Content -LiteralPath $combined -Raw
    return [PSCustomObject]@{
        Name = $Name
        ExitCode = $exitCode
        TimedOut = $timedOut
        LaunchError = $launchError
        Text = $text
    }
}

function Has-Marker($Result, [string]$Marker) {
    return $Result.Text.Contains($Marker)
}

foreach ($mode in @('baseline', 'protected', 'writable', 'direct')) {
    $result = Invoke-DiagnosticProcess -Name ('stack_growth_' + $mode) -Executable 'win32_stack_growth_probe.exe' -Arguments $mode
    $ok = $result.ExitCode -eq 0 -and (Has-Marker $result 'win32_stack_growth_probe OK')
    $stackOverflow = Has-Marker $result 'caught=0xc00000fd'
    $accessViolation = Has-Marker $result 'caught=0xc0000005'
    $protectBefore = Has-Marker $result 'protect_before_reset_ok=1'
    $protectAfter = Has-Marker $result 'protect_after_reset_ok=1'
    Add-Result "STACK mode=$mode probe_ok=$([int]$ok) exit=$($result.ExitCode) stack_overflow=$([int]$stackOverflow) access_violation=$([int]$accessViolation) protect_before_reset=$([int]$protectBefore) protect_after_reset=$([int]$protectAfter)"
}

foreach ($mode in @('seh', 'unhandled', 'chain', 'thread')) {
    $result = Invoke-DiagnosticProcess -Name ('uef_' + $mode) -Executable 'win32_uef_probe.exe' -Arguments $mode
    $exitShape = if ($mode -eq 'seh') { $result.ExitCode -eq 0 } else { $result.ExitCode -ne 0 }
    $veh = Has-Marker $result 'WIN32_UEF_PROBE VEH enter'
    $first = Has-Marker $result 'WIN32_UEF_PROBE UEF first'
    $second = Has-Marker $result 'WIN32_UEF_PROBE UEF second'
    Add-Result "UEF mode=$mode exit_shape=$([int]$exitShape) exit=$($result.ExitCode) veh=$([int]$veh) first=$([int]$first) second=$([int]$second)"
}

$beforeDumps = @{}
Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue | ForEach-Object {
    $beforeDumps[$_.FullName] = "$($_.Length):$($_.LastWriteTimeUtc.Ticks)"
}

$Common = '-Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -XjdwpProvider:none -Xms64m -Xmx512m'
$late = Invoke-DiagnosticProcess -Name 'art_late_uef' -Executable 'dalvikvm.exe' -Arguments "$Common -Xint -cp run\crashnativeprobe.jar CrashNativeProbe uef" -TimeoutSeconds 120
$lateInstall = Has-Marker $late 'WIN32_LATE_UEF_INSTALL'
$lateEnter = Has-Marker $late 'WIN32_LATE_UEF enter'
$predecessorArt = Has-Marker $late 'is_art=1'
$artUef = Has-Marker $late 'ART Win64 UEF: exception 0xc0000005'
$artDump = Has-Marker $late 'minidump written'
$newDumps = @(
    Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue | Where-Object {
        $signature = "$($_.Length):$($_.LastWriteTimeUtc.Ticks)"
        (-not $beforeDumps.ContainsKey($_.FullName)) -or $beforeDumps[$_.FullName] -ne $signature
    }
)
$newDumpLines = @($newDumps | ForEach-Object { "new_dump=$($_.FullName) bytes=$($_.Length)" })
if ($newDumpLines.Count -eq 0) {
    'NO_NEW_DUMP' | Set-Content -LiteralPath (Join-Path $Logs 'ART_LATE_UEF_DUMPS.txt')
} else {
    $newDumpLines | Set-Content -LiteralPath (Join-Path $Logs 'ART_LATE_UEF_DUMPS.txt')
}
Add-Result "ART_LATE_UEF exit=$($late.ExitCode) install=$([int]$lateInstall) enter=$([int]$lateEnter) predecessor_art=$([int]$predecessorArt) art_uef=$([int]$artUef) minidump_marker=$([int]$artDump) new_dumps=$($newDumps.Count)"

if (-not $lateInstall -or $late.ExitCode -eq 0) {
    $script:InfrastructureFailed = $true
}

$script:Results | Set-Content -LiteralPath (Join-Path $Logs 'RESULT_W010_W014_DIAGNOSTICS.txt')
if ($script:InfrastructureFailed) {
    'DIAGNOSTICS INCOMPLETE' | Add-Content -LiteralPath (Join-Path $Logs 'RESULT_W010_W014_DIAGNOSTICS.txt')
    Write-Host 'DIAGNOSTICS INCOMPLETE'
    exit 1
}
'DIAGNOSTICS COMPLETE' | Add-Content -LiteralPath (Join-Path $Logs 'RESULT_W010_W014_DIAGNOSTICS.txt')
Write-Host 'DIAGNOSTICS COMPLETE'
