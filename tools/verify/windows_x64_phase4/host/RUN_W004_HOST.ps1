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
    $report = Join-Path $Root 'W004_STRUCTURAL_REPORT.txt'
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'W004_STRUCTURAL_REPORT.txt is missing'
    }
    $required = @(
        '^status=PASS$'
        '^direct_total=[1-9][0-9]*$'
        '^retired_helper_references=0$'
        '^runtime_instance_exports=1$'
        '^openjdkjvmti_runtime_instance_imports=1$'
        '^art_sha256=[0-9a-f]{64}$'
        '^openjdkjvmti_sha256=[0-9a-f]{64}$'
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
    $jvmtiHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root 'openjdkjvmti.dll')).Hash.ToLowerInvariant()
    if ($values['art_sha256'] -ne $artHash) {
        throw 'Structural report art.dll hash does not match the packaged artifact'
    }
    if ($values['openjdkjvmti_sha256'] -ne $jvmtiHash) {
        throw 'Structural report openjdkjvmti.dll hash does not match the packaged artifact'
    }
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Executable,
        [string]$Arguments = '',
        [string[]]$Markers = @(),
        [string[]]$ForbiddenMarkers = @(),
        [int[]]$ExpectedExitCodes = @(0),
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
        "expected_exit=$($ExpectedExitCodes -join ',')"
        "timeout_seconds=$TimeoutSeconds"
        "timed_out=$timedOut"
        "elapsed_ms=$elapsedMs"
        if ($null -ne $launchError) { "launch_error=$launchError" }
        '--- stdout ---'
    ) | Set-Content -LiteralPath $combined
    if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout | Add-Content $combined }
    '--- stderr ---' | Add-Content $combined
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr | Add-Content $combined }

    $ok = ($null -eq $launchError) -and (-not $timedOut) -and ($ExpectedExitCodes -contains $exitCode)
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

Add-Result "W-004 native host acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $buildNumber = [int]$os.BuildNumber
    $os | Select-Object Caption, Version, BuildNumber, OSArchitecture |
        Format-List | Out-String | Set-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
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
    Copy-Item -LiteralPath (Join-Path $Root 'W004_STRUCTURAL_REPORT.txt') `
        -Destination (Join-Path $Logs 'W004_STRUCTURAL_REPORT.txt') -Force
    Add-Result 'PASS structural_report'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'W004_STRUCTURAL_REPORT_ERROR.txt')
    Add-Result 'FAIL structural_report'
    $script:Failed = $true
}

Clear-JitEnvironment
Invoke-CheckedProcess 'nterp_xint' 'dalvikvm.exe' "$Common -Xint -cp run\hello.jar Hello" @(
    'Hello from dalvikvm!'
    'main end exception=0'
)

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'jit_dual' 'dalvikvm.exe' "$Common -cp run\hello.jar Hello" @(
    'JitCodeCache::Create OK'
    'Windows x64 CompileMethod done success=1 method=java.lang.StringBuilder'
    'Hello from dalvikvm!'
    'main end exception=0'
)

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
Invoke-CheckedProcess 'float_threshold0_dual' 'dalvikvm.exe' "$Common -Xjitthreshold:0 -cp run\FloatProbe.jar FloatProbe" @(
    'FloatProbe OK'
    'main end exception=0'
)

foreach ($mode in @('dual', 'j1')) {
    Clear-JitEnvironment
    if ($mode -eq 'dual') { $env:ART_WINDOWS_X64_JIT_DUAL = '1' } else { $env:ART_WINDOWS_X64_JIT_DUAL = '0' }
    Invoke-CheckedProcess ("critical_$mode") 'dalvikvm.exe' `
        "$Common -Xjitthreshold:0 -Dcritical.load=library -Dcritical.instrumentation=1 -Djava.library.path=empty-native-dir;. -cp run\criticalnativeprobe.jar CriticalNativeProbe" @(
            'CriticalNativeProbe instrumentation OK'
            'CriticalNativeDlsymProbe postTracing OK'
            'CriticalNativeProbe tracingMode before=0'
            'main end exception=0'
        )
}

$nativeAbiMarkers = @(
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
)
foreach ($mode in @('dual', 'j1')) {
    Clear-JitEnvironment
    if ($mode -eq 'dual') { $env:ART_WINDOWS_X64_JIT_DUAL = '1' } else { $env:ART_WINDOWS_X64_JIT_DUAL = '0' }
    $env:ART_WINDOWS_X64_JIT_FILTER = 'FastNativeAbiProbe'
    $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
    Invoke-CheckedProcess ("native_abi_$mode") 'dalvikvm.exe' `
        "$Common -Xjitthreshold:0 -Dnative.abi.instrumentation=1 -Djava.library.path=empty-native-dir;. -cp run\fastnativeabiprobe.jar FastNativeAbiProbe" `
        $nativeAbiMarkers
}

$jvmtiMarkers = @(
    'JvmtiForceProbe OK'
    'JvmtiForceProbe after normalRegistered=137.75'
    'success=1 method=double JvmtiForceProbe.normalRegistered('
    'success=1 method=double JvmtiForceProbe.fastRegistered('
    'main end exception=0'
)
$jvmtiForbidden = @(
    'success=1 method=double JvmtiForceProbe.criticalRegistered('
    'success=1 method=double JvmtiForceProbe.criticalDlsym('
)
foreach ($mode in @('dual', 'j1')) {
    Clear-JitEnvironment
    if ($mode -eq 'dual') { $env:ART_WINDOWS_X64_JIT_DUAL = '1' } else { $env:ART_WINDOWS_X64_JIT_DUAL = '0' }
    $env:ART_WINDOWS_X64_JIT_FILTER = 'JvmtiForceProbe'
    $env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
    Invoke-CheckedProcess ("jvmti_$mode") 'dalvikvm.exe' `
        "$Common -Xplugin:openjdkjvmti.dll -agentpath:libjvmtiforceprobe.dll -Xjitthreshold:0 -Djava.library.path=. -cp run\jvmtiforceprobe.jar JvmtiForceProbe" `
        $jvmtiMarkers $jvmtiForbidden
}

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
Invoke-CheckedProcess 'gcstress' 'dalvikvm.exe' "$Common -cp run\gcstressprobe.jar GcStressProbe" @(
    'gcstress.ok=true'
    'GcStressProbe.done=ok'
)
Invoke-CheckedProcess 'threadheavy' 'dalvikvm.exe' "$Common -cp run\threadheavyprobe.jar ThreadHeavyProbe" @(
    'threadheavy.ok=true'
    'ThreadHeavyProbe.done=ok'
)
Invoke-CheckedProcess 'handleleak' 'dalvikvm.exe' "$Common -cp run\handleleakprobe.jar HandleLeakProbe" @(
    'handleleak.ok=true'
    'HandleLeakProbe.done=ok'
)

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
foreach ($index in 1..10) {
    Invoke-CheckedProcess ("repeat_hello_{0:D2}" -f $index) 'dalvikvm.exe' `
        "$Common -cp run\hello.jar Hello" @(
            'Hello from dalvikvm!'
            'main end exception=0'
        )
}
Clear-JitEnvironment

$traceFiles = @(
    'critical-native-instrumentation.trace'
    'native-abi-instrumentation.trace'
)
$traceCleanupFailed = $false
foreach ($trace in $traceFiles) {
    if (Test-Path -LiteralPath (Join-Path $Root $trace)) {
        Add-Result "FAIL trace_cleanup file=$trace"
        $traceCleanupFailed = $true
        $script:Failed = $true
    }
}
if (-not $traceCleanupFailed) {
    Add-Result 'PASS trace_cleanup'
}

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

$resultPath = Join-Path $Logs 'RESULT_W004.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
