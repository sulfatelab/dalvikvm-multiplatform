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
    $metricsSampled = $false
    $exitCode = -1
    $peakPaged = -1
    $peakWorkingSet = -1
    $peakVirtual = -1
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
        # Force System.Diagnostics.Process to retain a real process handle. Windows
        # PowerShell can otherwise return a Process wrapper whose post-exit
        # accounting properties are empty for very short-lived children.
        $null = $process.Handle
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while ($true) {
            try {
                $process.Refresh()
                $samplePaged = $process.PeakPagedMemorySize64
                $sampleWorkingSet = $process.PeakWorkingSet64
                $sampleVirtual = $process.PeakVirtualMemorySize64
                if ($null -ne $samplePaged -and
                    $null -ne $sampleWorkingSet -and
                    $null -ne $sampleVirtual) {
                    $peakPaged = [Math]::Max($peakPaged, [long]$samplePaged)
                    $peakWorkingSet = [Math]::Max($peakWorkingSet, [long]$sampleWorkingSet)
                    $peakVirtual = [Math]::Max($peakVirtual, [long]$sampleVirtual)
                    $metricsSampled = $true
                }
            } catch {
                # The child can exit between Refresh() and a property read. Exit
                # handling below still obtains its retained process exit code.
            }
            if ($process.WaitForExit(50)) {
                break
            }
            if ([DateTime]::UtcNow -ge $deadline) {
                $timedOut = $true
                $process.Kill()
                break
            }
        }
        $process.WaitForExit()
        $rawExitCode = $process.ExitCode
        if ($null -eq $rawExitCode) {
            throw 'Process exit code was unavailable after WaitForExit'
        }
        if (-not $metricsSampled) {
            throw 'Process memory metrics were unavailable while the child was running'
        }
        $exitCode = [int]$rawExitCode
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
        "metrics_sampled=$metricsSampled"
        "elapsed_ms=$elapsedMs"
        "peak_paged_bytes=$peakPaged"
        "peak_working_set_bytes=$peakWorkingSet"
        "peak_virtual_bytes=$peakVirtual"
        if ($null -ne $launchError) { "launch_error=$launchError" }
        '--- stdout ---'
    ) | Set-Content -Path $combined
    if (Test-Path $stdout) { Get-Content $stdout | Add-Content $combined }
    '--- stderr ---' | Add-Content $combined
    if (Test-Path $stderr) { Get-Content $stderr | Add-Content $combined }

    $ok = ($null -eq $launchError) -and (-not $timedOut) -and ($ExpectedExitCodes -contains $exitCode)
    foreach ($marker in $Markers) {
        if (-not (Select-String -Path $combined -SimpleMatch $marker -Quiet)) {
            $ok = $false
            Add-Content -Path $combined -Value "missing_marker=$marker"
        }
    }
    foreach ($marker in $ForbiddenMarkers) {
        if (Select-String -Path $combined -SimpleMatch $marker -Quiet) {
            $ok = $false
            Add-Content -Path $combined -Value "forbidden_marker=$marker"
        }
    }
    if ($ok) {
        Add-Result "PASS $Name exit=$exitCode elapsed_ms=$elapsedMs peak_paged_bytes=$peakPaged peak_working_set_bytes=$peakWorkingSet peak_virtual_bytes=$peakVirtual"
    } else {
        Add-Result "FAIL $Name exit=$exitCode timed_out=$timedOut"
        $script:Failed = $true
    }
}

function Clear-JitEnvironment {
    @(
        'ART_WIN64_JIT'
        'ART_WIN64_JIT_DUAL'
        'ART_WIN64_JIT_EXCLUDE'
        'ART_WIN64_JIT_FILTER'
        'ART_WIN64_JIT_LOG_COMPILES'
    ) | ForEach-Object {
        Remove-Item -Path ('Env:' + $_) -ErrorAction SilentlyContinue
    }
}

$Common = '-Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -XjdwpProvider:none'

Add-Result "W-013 native host acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture |
        Format-List | Out-String | Set-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    $PSVersionTable | Format-List | Out-String | Add-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    Add-Result 'PASS host_os_info'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'WINDOWS_VERSION.txt')
    Add-Result 'FAIL host_os_info'
    $script:Failed = $true
}
try {
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem
    $operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem
    $pageFiles = @(Get-CimInstance -ClassName Win32_PageFileUsage)
    $memoryLines = New-Object System.Collections.Generic.List[string]
    $memoryLines.Add("total_physical_memory_bytes=$($computer.TotalPhysicalMemory)")
    $memoryLines.Add("free_physical_memory_kib=$($operatingSystem.FreePhysicalMemory)")
    $memoryLines.Add("total_virtual_memory_kib=$($operatingSystem.TotalVirtualMemorySize)")
    $memoryLines.Add("free_virtual_memory_kib=$($operatingSystem.FreeVirtualMemory)")
    $memoryLines.Add("pagefile_count=$($pageFiles.Count)")
    foreach ($pageFile in $pageFiles) {
        $memoryLines.Add("pagefile_name=$($pageFile.Name)")
        $memoryLines.Add("pagefile_allocated_mib=$($pageFile.AllocatedBaseSize)")
        $memoryLines.Add("pagefile_current_usage_mib=$($pageFile.CurrentUsage)")
        $memoryLines.Add("pagefile_peak_usage_mib=$($pageFile.PeakUsage)")
    }
    $memoryLines | Set-Content (Join-Path $Logs 'HOST_MEMORY.txt')
    Add-Result 'PASS host_memory_info'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'HOST_MEMORY.txt')
    Add-Result 'FAIL host_memory_info'
    $script:Failed = $true
}

Invoke-CheckedProcess 'mem_map_policy' 'win64_w013_mem_map_probe.exe' '' @('W013_MEM_MAP_POLICY_PASS', 'boundary=tested', 'transitions=32', 'fragments=', 'exhaustion_reservations=', 'destruction_cycles=128')
Invoke-CheckedProcess 'dlmalloc_config' 'W013DlmallocConfigProbe.exe' '' @('W013_DLMALLOC_CONFIG_PASS')
Invoke-CheckedProcess 'mspace_owner' 'win64_w013_mspace_owner_probe.exe' 'success' @('W013_MSPACE_OWNER_PASS')
Invoke-CheckedProcess 'nonmoving_128m' 'dalvikvm.exe' "$Common -Xint -Xms2m -Xmx128m -cp run\w013nonmovingstressprobe.jar W013NonMovingStressProbe" @('nonmoving.ok=true', 'W013NonMovingStressProbe.done=ok')
Invoke-CheckedProcess 'nonmoving_1024m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx1024m -cp run\w013nonmovingstressprobe.jar W013NonMovingStressProbe" @('nonmoving.ok=true', 'W013NonMovingStressProbe.done=ok')
Invoke-CheckedProcess 'gcforced_512m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx512m -cp run\gcforced.jar GcForced" @('tiny.ok=true', 'los.ok=true', 'gc.forced.ok=true', 'GcForced.done=ok')
Invoke-CheckedProcess 'gcstress_512m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx512m -cp run\gcstressprobe.jar GcStressProbe" @('gcstress.ok=true', 'GcStressProbe.done=ok')
Invoke-CheckedProcess 'threadheavy_512m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx512m -cp run\threadheavyprobe.jar ThreadHeavyProbe" @('threadheavy.ok=true', 'ThreadHeavyProbe.done=ok')
Invoke-CheckedProcess 'handleleak_512m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx512m -cp run\handleleakprobe.jar HandleLeakProbe" @('handleleak.ok=true', 'HandleLeakProbe.done=ok')
Invoke-CheckedProcess 'hello_512m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx512m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0')
Invoke-CheckedProcess 'hello_1024m' 'dalvikvm.exe' "$Common -Xint -Xms64m -Xmx1024m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0')

Clear-JitEnvironment
$env:ART_WIN64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'jit_dual_compile' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\hello.jar Hello" @('JitCodeCache::Create OK', 'Win64 CompileMethod done success=1 method=java.lang.StringBuilder', 'Hello from dalvikvm!', 'main end exception=0')

$env:ART_WIN64_JIT = '0'
Invoke-CheckedProcess 'jit_disabled' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0') @('Win64 CompileMethod done success=1')
Remove-Item Env:ART_WIN64_JIT -ErrorAction SilentlyContinue

Remove-Item Env:ART_WIN64_JIT_LOG_COMPILES -ErrorAction SilentlyContinue
Invoke-CheckedProcess 'jit_usejit_false' 'dalvikvm.exe' "$Common -Xusejit:false -Xms64m -Xmx512m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0')

$env:ART_WIN64_JIT_LOG_COMPILES = '1'
$env:ART_WIN64_JIT_FILTER = 'StringBuilder'
Invoke-CheckedProcess 'jit_filter' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\hello.jar Hello" @('Win64 CompileMethod done success=1 method=java.lang.StringBuilder', 'Hello from dalvikvm!', 'main end exception=0')
Remove-Item Env:ART_WIN64_JIT_FILTER -ErrorAction SilentlyContinue

$env:ART_WIN64_JIT_EXCLUDE = 'StringBuilder'
Invoke-CheckedProcess 'jit_exclude' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0') @('Win64 CompileMethod done success=1 method=java.lang.StringBuilder')
Remove-Item Env:ART_WIN64_JIT_EXCLUDE -ErrorAction SilentlyContinue

Remove-Item Env:ART_WIN64_JIT_LOG_COMPILES -ErrorAction SilentlyContinue
Invoke-CheckedProcess 'jit_quiet' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0') @('Win64 CompileMethod done success=1')

$env:ART_WIN64_JIT_DUAL = '0'
$env:ART_WIN64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'jit_j1_compile' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\hello.jar Hello" @('JitCodeCache::Create OK', 'Win64 CompileMethod done success=1 method=java.lang.StringBuilder', 'Hello from dalvikvm!', 'main end exception=0')

Clear-JitEnvironment
$env:ART_WIN64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'jit_matrix_cenc' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\CEnc.jar CEnc" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_cenc2' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\CEnc2.jar CEnc2" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_celike' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\CELike.jar CELike" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_cfloat' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\CFloat.jar CFloat" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_floatprobe' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\FloatProbe.jar FloatProbe" @('FloatProbe OK')
Invoke-CheckedProcess 'jit_matrix_ifloat' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\IFloat.jar IFloat" @('IFloat OK')
Invoke-CheckedProcess 'jit_matrix_jlfloat' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\JLFloat.jar JLFloat" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_rfloat' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\RFloat.jar RFloat" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_sfloat' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\SFloat.jar SFloat" @('main end exception=0')
Invoke-CheckedProcess 'jit_matrix_math' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\MathProbe.jar MathProbe" @('MathProbe.done=ok')
Invoke-CheckedProcess 'jit_matrix_io' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\ioprobe.jar IoProbe" @('IoProbe.done=ok')
Invoke-CheckedProcess 'jit_matrix_net' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\netprobe.jar NetProbe" @('NetProbe.done=ok')
Invoke-CheckedProcess 'jit_matrix_gc' 'dalvikvm.exe' "$Common -Xms64m -Xmx512m -cp run\gcprobe.jar GcProbe" @('GcProbe.done=ok')
Invoke-CheckedProcess -Name 'jit_matrix_throw' -Executable 'dalvikvm.exe' -Arguments "$Common -Xms64m -Xmx512m -cp run\throwprobe.jar ThrowProbe" -Markers @('phase3-throw-ok') -ExpectedExitCodes @(1)
Clear-JitEnvironment

foreach ($index in 1..20) {
    Invoke-CheckedProcess ("repeat_hello_{0:D2}" -f $index) 'dalvikvm.exe' "$Common -Xms2m -Xmx128m -cp run\hello.jar Hello" @('Hello from dalvikvm!', 'main end exception=0')
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

$resultPath = Join-Path $Logs 'RESULT_W013.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
