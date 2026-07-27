$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root 'logs'
$Crash = Join-Path $Root 'run\crash'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
New-Item -ItemType Directory -Force -Path $Crash | Out-Null
Get-ChildItem -Path $Logs -File -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue | Remove-Item -Force

$env:ANDROID_ROOT = 'run'
$env:ANDROID_ART_ROOT = 'run'
$env:ANDROID_I18N_ROOT = 'run'
$env:ANDROID_DATA = 'run\data'
$env:ICU_DATA = 'run\icu'

$script:Results = New-Object System.Collections.Generic.List[string]
$script:Failed = $false
$script:WindowsBuild = 0

function Add-Result([string]$Text) {
    $script:Results.Add($Text)
    Write-Host $Text
}

function Clear-ArtEnvironment {
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

function Test-StructuralReport {
    $report = Join-Path $Root 'W010_W014_STRUCTURAL_REPORT.txt'
    if (-not (Test-Path -LiteralPath $report -PathType Leaf)) {
        throw 'W010_W014_STRUCTURAL_REPORT.txt is missing'
    }
    $required = @(
        '^status=PASS$'
        '^cet_contract=WIN32_CET_CONTRACT PASS '
        '^boundary_unwind=win32_boundary_unwind OK '
        '^windows_minimum_build=17134$'
        '^requested_stack_sizes=0,65536,262144,1048576,2097152,9437184$'
        '^sigchain_action_calls=3$'
        '^sigchain_foreign_before_calls=2$'
        '^sigchain_foreign_after_calls=2$'
        '^sigchain_sequence=1,2,1,2$'
        '^managed_npe_read_rounds=64$'
        '^managed_npe_write_rounds=64$'
        '^managed_so_main_rounds=2$'
        '^managed_so_child_rounds=2$'
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
    $hashEntries = @{
        'dalvikvm.exe' = 'dalvikvm_sha256'
        'art.dll' = 'art_sha256'
        'sigchain.dll' = 'sigchain_sha256'
        'run\w010managedfaultprobe.jar' = 'managed_jar_sha256'
    }
    foreach ($relative in $hashEntries.Keys) {
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Root $relative)).Hash.ToLowerInvariant()
        if ($values[$hashEntries[$relative]] -ne $actual) {
            throw "Structural report hash does not match $relative"
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
        [int[]]$ExpectedExitCodes = @(0),
        [switch]$RequireNonZero,
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
    $startParameters = @{
        FilePath = Join-Path $Root $Executable
        WorkingDirectory = $Root
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        NoNewWindow = $true
        PassThru = $true
    }
    if ($Arguments.Length -ne 0) {
        $startParameters.ArgumentList = $Arguments
    }
    try {
        $process = Start-Process @startParameters
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
        "require_nonzero=$RequireNonZero"
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

    $exitOk = if ($RequireNonZero) { $exitCode -ne 0 } else { $ExpectedExitCodes -contains $exitCode }
    $ok = ($null -eq $launchError) -and (-not $timedOut) -and $exitOk
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
$HandledForbidden = @('ART Win64 VEH', 'ART Win64 UEF', 'minidump written', 'unexpected_continue')

Add-Result "W-010/W-014 native Stage E acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $script:WindowsBuild = [int]$os.BuildNumber
    $os | Select-Object Caption, Version, BuildNumber, OSArchitecture |
        Format-List | Out-String | Set-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    $PSVersionTable | Format-List | Out-String | Add-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    if ($script:WindowsBuild -lt 17134) {
        throw "Windows build $($script:WindowsBuild) is older than the Windows 10 RS4 baseline 17134"
    }
    Add-Result "PASS host_os build=$($script:WindowsBuild)"
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
    Copy-Item -LiteralPath (Join-Path $Root 'W010_W014_STRUCTURAL_REPORT.txt') -Destination (Join-Path $Logs 'W010_W014_STRUCTURAL_REPORT.txt') -Force
    Add-Result 'PASS structural_report'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'W010_W014_STRUCTURAL_REPORT_ERROR.txt')
    Add-Result 'FAIL structural_report'
    $script:Failed = $true
}

Invoke-CheckedProcess -Name 'cet_policy' -Executable 'win32_cet_policy_probe.exe' -Markers @('WIN32_CET_POLICY_PROBE PASS')
try {
    $cetLog = Join-Path $Logs 'cet_policy.log'
    if ($script:WindowsBuild -ge 19041) {
        if (-not (Select-String -LiteralPath $cetLog -SimpleMatch 'actual=disabled' -Quiet)) {
            throw 'Windows 10 build 19041+ did not report a disabled user shadow-stack policy'
        }
    } elseif (-not (
        (Select-String -LiteralPath $cetLog -SimpleMatch 'actual=disabled' -Quiet) -or
        (Select-String -LiteralPath $cetLog -SimpleMatch 'actual=unavailable-on-older-windows' -Quiet)
    )) {
        throw 'Older Windows did not report a disabled or unavailable user shadow-stack policy'
    }
    Add-Result 'PASS hsp_policy'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'HSP_POLICY_ERROR.txt')
    Add-Result 'FAIL hsp_policy'
    $script:Failed = $true
}

Invoke-CheckedProcess -Name 'thread_stack' -Executable 'win32_thread_stack_probe.exe' -Markers @(
    'requested=65536'
    'requested=262144'
    'requested=1048576'
    'requested=2097152'
    'requested=9437184'
    'join_stress count=512'
    'detach_stress count=128'
    'win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128'
    'win32_thread_stack_probe OK'
)
Invoke-CheckedProcess -Name 'stack_page' -Executable 'win32_stack_page_probe.exe' -Markers @(
    'selection_cases count=8'
    'reserved_case size=1048576 iterations=64'
    'win32_stack_page_probe failures=0 committed_restore_iterations=64 reserved_restore_iterations=64 faults=258'
    'win32_stack_page_probe OK'
)
Invoke-CheckedProcess -Name 'fault_record' -Executable 'win32_fault_record_probe.exe' -Markers @(
    'win32_fault_record_probe failures=0 cases=8'
    'win32_fault_record_probe OK'
)
Invoke-CheckedProcess -Name 'sigchain' -Executable 'win32_sigchain_probe.exe' -Markers @(
    'win32_sigchain_probe calls=2 first=0 second=0'
    'action_calls=3 foreign_before=2 foreign_after=2'
    'frame_with_action=1 frame_after_remove=1 sequence=1,2,1,2'
    'win32_sigchain_probe OK'
)

Clear-ArtEnvironment
Invoke-CheckedProcess -Name 'no_sig_chain_rejection' -Executable 'dalvikvm.exe' -Arguments "$Common -Xno-sig-chain -Xint -cp run\w010managedfaultprobe.jar W010ManagedFaultProbe npe" -Markers @('A started runtime should have sig chain enabled') -ForbiddenMarkers @('W010ManagedFaultProbe OK') -RequireNonZero

Clear-ArtEnvironment
$env:ART_WIN64_NTERP = '0'
Invoke-CheckedProcess -Name 'switch_so' -Executable 'dalvikvm.exe' -Arguments "$Common -Xusejit:false -cp run\w010managedfaultprobe.jar W010ManagedFaultProbe so" -Markers @('W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4', 'W010ManagedFaultProbe OK mode=so', 'main end exception=0') -ForbiddenMarkers @($HandledForbidden + 'Win64 CompileMethod done success=1 method=')

Clear-ArtEnvironment
Invoke-CheckedProcess -Name 'nterp_npe' -Executable 'dalvikvm.exe' -Arguments "$Common -Xusejit:false -cp run\w010managedfaultprobe.jar W010ManagedFaultProbe npe" -Markers @('W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16', 'W010ManagedFaultProbe OK mode=npe', 'main end exception=0') -ForbiddenMarkers @($HandledForbidden + 'Win64 CompileMethod done success=1 method=')
Invoke-CheckedProcess -Name 'nterp_so' -Executable 'dalvikvm.exe' -Arguments "$Common -Xusejit:false -cp run\w010managedfaultprobe.jar W010ManagedFaultProbe so" -Markers @('W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4', 'W010ManagedFaultProbe OK mode=so', 'main end exception=0') -ForbiddenMarkers @($HandledForbidden + 'Win64 CompileMethod done success=1 method=')

Clear-ArtEnvironment
$env:ART_WIN64_JIT_FILTER = 'W010ManagedFaultProbe'
$env:ART_WIN64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess -Name 'jit_npe' -Executable 'dalvikvm.exe' -Arguments "$Common -verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0 -cp run\w010managedfaultprobe.jar W010ManagedFaultProbe npe" -Markers @('W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16', 'Win64 CompileMethod done success=1 method=void W010ManagedFaultProbe.runNullChecks()', 'W010ManagedFaultProbe OK mode=npe', 'main end exception=0') -ForbiddenMarkers $HandledForbidden
Invoke-CheckedProcess -Name 'jit_so' -Executable 'dalvikvm.exe' -Arguments "$Common -verbose:jit -Xjitwarmupthreshold:0 -Xjitthreshold:0 -cp run\w010managedfaultprobe.jar W010ManagedFaultProbe so" -Markers @('W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4', 'Win64 CompileMethod done success=1 method=int W010ManagedFaultProbe.recurse(int)', 'Win64 CompileMethod done success=1 method=int W010ManagedFaultProbe.runStackOverflowRounds()', 'W010ManagedFaultProbe OK mode=so', 'main end exception=0') -ForbiddenMarkers $HandledForbidden
Clear-ArtEnvironment

$handledLogNames = @('thread_stack', 'stack_page', 'fault_record', 'sigchain', 'switch_so', 'nterp_npe', 'nterp_so', 'jit_npe', 'jit_so')
$handledScanFailed = $false
foreach ($name in $handledLogNames) {
    $path = Join-Path $Logs ($name + '.log')
    foreach ($pattern in $HandledForbidden) {
        if (Select-String -LiteralPath $path -SimpleMatch $pattern -Quiet) {
            Add-Result "FAIL handled_log_scan name=$name pattern=$pattern"
            $handledScanFailed = $true
            $script:Failed = $true
        }
    }
}
if (-not $handledScanFailed) {
    Add-Result 'PASS handled_log_scan'
}

$handledDumps = @(Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue)
if ($handledDumps.Count -eq 0) {
    'NO_HANDLED_DMP_FILES' | Set-Content (Join-Path $Logs 'HANDLED_DMP_SCAN.txt')
    Add-Result 'PASS handled_dump_scan NO_HANDLED_DMP_FILES'
} else {
    $handledDumps.FullName | Set-Content (Join-Path $Logs 'HANDLED_DMP_SCAN.txt')
    Add-Result "FAIL handled_dump_scan count=$($handledDumps.Count)"
    $script:Failed = $true
}

Clear-ArtEnvironment
Invoke-CheckedProcess -Name 'crashnative' -Executable 'dalvikvm.exe' -Arguments "$Common -Xint -cp run\crashnativeprobe.jar CrashNativeProbe" -Markers @('CrashNativeProbe.start', 'ART Win64 VEH: exception 0xc0000005', 'ART Win64 UEF: exception 0xc0000005', 'minidump written') -ForbiddenMarkers @('CrashNativeProbe.unexpected_continue') -RequireNonZero -TimeoutSeconds 120

$fatalDumps = @(Get-ChildItem -Path $Crash -File -Filter '*.dmp' -ErrorAction SilentlyContinue)
if ($fatalDumps.Count -ge 1) {
    $fatalDumps | ForEach-Object {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "path=$($_.FullName) bytes=$($_.Length) sha256=$hash"
    } | Set-Content (Join-Path $Logs 'FATAL_DMP_SCAN.txt')
    Add-Result "PASS fatal_dump_scan count=$($fatalDumps.Count)"
} else {
    'NO_FATAL_DMP_FILES' | Set-Content (Join-Path $Logs 'FATAL_DMP_SCAN.txt')
    Add-Result 'FAIL fatal_dump_scan count=0'
    $script:Failed = $true
}

$resultPath = Join-Path $Logs 'RESULT_W010_W014.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
