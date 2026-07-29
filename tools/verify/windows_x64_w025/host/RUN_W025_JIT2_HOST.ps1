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
        [int]$TimeoutSeconds = 300
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

$Common = '-Xbootclasspath:run\boot.jar -Xbootclasspath-locations:run\boot.jar -Ximage:/nonexistent-no-boot-image -XjdwpProvider:none -Xms64m -Xmx512m'
$MappingPrefix = "$Common -Xjitwarmupthreshold:1 -Xjitthreshold:1"
$MappingMain = '-Djava.library.path=.;run -cp run\w025jitmappingprobe.jar W025JitMappingProbe'

Add-Result "W-025 JIT-2 native host acceptance $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $computer = Get-CimInstance -ClassName Win32_ComputerSystem
    $pageFiles = @(Get-CimInstance -ClassName Win32_PageFileUsage)
    @(
        "caption=$($os.Caption)"
        "version=$($os.Version)"
        "build=$($os.BuildNumber)"
        "architecture=$($os.OSArchitecture)"
        "total_physical_memory_bytes=$($computer.TotalPhysicalMemory)"
        "free_physical_memory_kib=$($os.FreePhysicalMemory)"
        "total_virtual_memory_kib=$($os.TotalVirtualMemorySize)"
        "free_virtual_memory_kib=$($os.FreeVirtualMemory)"
        "pagefile_count=$($pageFiles.Count)"
        foreach ($pageFile in $pageFiles) {
            "pagefile_name=$($pageFile.Name)"
            "pagefile_allocated_mib=$($pageFile.AllocatedBaseSize)"
            "pagefile_current_usage_mib=$($pageFile.CurrentUsage)"
            "pagefile_peak_usage_mib=$($pageFile.PeakUsage)"
        }
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
    Copy-Item -LiteralPath (Join-Path $Root 'W025_STRUCTURAL_REPORT.txt') `
        -Destination (Join-Path $Logs 'W025_STRUCTURAL_REPORT.txt')
    Add-Result 'PASS package_integrity'
} catch {
    $_.Exception.ToString() | Set-Content (Join-Path $Logs 'PACKAGE_INTEGRITY_ERROR.txt')
    Add-Result 'FAIL package_integrity'
    $script:Failed = $true
}

Clear-JitEnvironment
Invoke-CheckedProcess 'section_basic' 'W025SectionPolicyProbe.exe' '--basic' @(
    'roles=R_RX_RW type=MEM_MAPPED rwx=0 mapped_names=0'
    'W025_SECTION_POLICY_PASS mode=basic'
) -TimeoutSeconds 60

Invoke-CheckedProcess 'low_va_failure' 'W025SectionPolicyProbe.exe' '--low-va' @(
    'W025_LOW_VA_PASS'
    'no_high_fallback=1 recovery=1'
    'W025_SECTION_POLICY_PASS mode=low-va'
) -TimeoutSeconds 60

Invoke-CheckedProcess 'sec_commit_pressure' 'W025SectionPolicyProbe.exe' '--pressure' @(
    'W025_SEC_COMMIT_PASS capacity_bytes=1073741824'
    'primary_low=1 alias=1'
    'W025_SECTION_POLICY_PASS mode=pressure'
) -TimeoutSeconds 600

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
$env:ART_WINDOWS_X64_JIT_FILTER = 'W025JitMappingProbe'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'runtime_mapping_64m' 'dalvikvm.exe' `
    "$MappingPrefix -Xjitmaxsize:64M $MappingMain 64 false" @(
        'Windows x64 JIT dual-view (J-2) created: capacity=64MiB'
        'roles primary_data=R primary_code=RX alias_data=RW alias_code=RW type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes=67108864'
        'primary_name_length=0'
        'W025_JIT_MAPPING_PASS'
        'success=1 method=int W025JitMappingProbe.target(int)'
        'W025JitMappingProbe PASS capacity_bytes=67108864 require_cfg=false'
        'main end exception=0'
    )

Invoke-CheckedProcess 'runtime_mapping_1024m' 'dalvikvm.exe' `
    "$MappingPrefix -Xjitmaxsize:1024M $MappingMain 1024 false" @(
        'Windows x64 JIT dual-view (J-2) created: capacity=1024MiB'
        'roles primary_data=R primary_code=RX alias_data=RW alias_code=RW type=MEM_MAPPED rwx=0 contiguous_low=1 capacity_bytes=1073741824'
        'primary_name_length=0'
        'W025_JIT_MAPPING_PASS'
        'success=1 method=int W025JitMappingProbe.target(int)'
        'W025JitMappingProbe PASS capacity_bytes=1073741824 require_cfg=false'
        'main end exception=0'
    ) -TimeoutSeconds 600

Clear-JitEnvironment
Invoke-CheckedProcess 'cfg_section_call' 'W025PolicyLauncher.exe' `
    'cfg zero W025SectionPolicyProbe.exe --cfg-call' @(
        'W025_POLICY_CHILD policy=cfg'
        'cfg_enabled=1'
        'W025_SECTION_MAPPING label=default'
        'execute=1'
        'W025_SECTION_POLICY_PASS mode=cfg-call'
        'W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero'
    )

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
$env:ART_WINDOWS_X64_JIT_FILTER = 'W025JitMappingProbe'
$env:ART_WINDOWS_X64_JIT_LOG_COMPILES = '1'
Invoke-CheckedProcess 'cfg_runtime_mapping' 'W025PolicyLauncher.exe' `
    "cfg zero dalvikvm.exe $MappingPrefix -Xjitmaxsize:64M $MappingMain 64 true" @(
        'W025_POLICY_CHILD policy=cfg'
        'cfg_enabled=1'
        'W025_JIT_MAPPING_PASS'
        'success=1 method=int W025JitMappingProbe.target(int)'
        'W025JitMappingProbe PASS capacity_bytes=67108864 require_cfg=true'
        'W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero'
    )

Clear-JitEnvironment
$env:ART_WINDOWS_X64_JIT_DUAL = '1'
Invoke-CheckedProcess 'dynamic_code_jit_rejected' 'W025PolicyLauncher.exe' `
    "dynamic zero dalvikvm.exe $Common -cp run\hello.jar Hello" @(
        'W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1'
        'Windows x64 JIT dual-view construction failed:'
        'failed: 1655; falling back to single-view (J-1)'
        'Failed to create JIT Code Cache:'
        'VirtualProtect RemapAtEnd('
        'failed: 1655'
        'Hello from dalvikvm!'
        'main end exception=0'
        'W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero'
    ) @('JitCodeCache::Create OK')

Clear-JitEnvironment
Invoke-CheckedProcess 'dynamic_code_nojit' 'W025PolicyLauncher.exe' `
    "dynamic zero dalvikvm.exe $Common -Xusejit:false -cp run\hello.jar Hello" @(
        'W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1'
        'Hello from dalvikvm!'
        'main end exception=0'
        'W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero'
    ) @('JitCodeCache::Create OK')

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
    'Unhandled page fault'
    'Unhandled exception'
    'Access violation'
    'STATUS_ACCESS_VIOLATION'
    '0xc0000005'
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

$resultPath = Join-Path $Logs 'RESULT_W025_JIT2.txt'
$script:Results | Set-Content $resultPath
if ($script:Failed) {
    'OVERALL FAIL' | Add-Content $resultPath
    Write-Host 'OVERALL FAIL'
    exit 1
}
'OVERALL PASS' | Add-Content $resultPath
Write-Host 'OVERALL PASS'
exit 0
