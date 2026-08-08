[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Check", "Bootstrap", "Repair")]
    [string]$Mode,
    [Parameter(Mandatory = $true)][string]$PluginRoot,
    [Parameter(Mandatory = $true)][string]$PluginData,
    [Parameter(Mandatory = $true)][string]$ProjectDir
)

$ErrorActionPreference = "Stop"
$RuntimeVersion = "0.4.0"
$LegacyRuntimeVersion = "0.3.0"
$ProcessOutputLimit = 65536

function Resolve-ClaudePath {
    param([string]$Name, [AllowEmptyString()][string]$Value, [switch]$MustExist)
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "$Name is empty; Claude inline path substitution is required" }
    if ($Value -match '\$\{CLAUDE_(PLUGIN_ROOT|PLUGIN_DATA|PROJECT_DIR)\}') { throw "$Name contains an unresolved Claude placeholder" }
    if ($Value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$)|//[^/]+/[^/]+(?:/|$))') { throw "$Name must be an absolute path" }
    $resolved = [IO.Path]::GetFullPath($Value)
    if ($MustExist -and -not (Test-Path -LiteralPath $resolved -PathType Container)) { throw "$Name does not identify an existing directory" }
    return $resolved
}

function Assert-NotRedirect {
    param([string]$Name, [string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "$Name must not be a path redirect or reparse point" }
    }
}

function Assert-NoRedirectAncestors {
    param([string]$Name, [string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($full)
    $current = $root
    $relative = $full.Substring($root.Length)
    foreach ($part in $relative.Split([char[]]"\/", [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $part
        Assert-NotRedirect $Name $current
    }
}
function ConvertTo-WindowsArgument {
    param([AllowEmptyString()][string]$Value)
    $builder = [Text.StringBuilder]::new()
    [void]$builder.Append([char]34)
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq [char]92) { $backslashes++; continue }
        if ($character -eq [char]34) {
            [void]$builder.Append([char]92, ($backslashes * 2) + 1)
            [void]$builder.Append([char]34)
        } else {
            if ($backslashes -gt 0) { [void]$builder.Append([char]92, $backslashes) }
            [void]$builder.Append($character)
        }
        $backslashes = 0
    }
    if ($backslashes -gt 0) { [void]$builder.Append([char]92, $backslashes * 2) }
    [void]$builder.Append([char]34)
    return $builder.ToString()
}

function ConvertTo-ProcessArguments {
    param([string[]]$Values)
    return (($Values | ForEach-Object { ConvertTo-WindowsArgument $_ }) -join ' ')
}

function Add-RetainedBytes {
    param([IO.MemoryStream]$Destination, [byte[]]$Buffer, [int]$Count)
    $remaining = $ProcessOutputLimit - [int]$Destination.Length
    if ($remaining -le 0 -or $Count -le 0) { return }
    $Destination.Write($Buffer, 0, [Math]::Min($remaining, $Count))
}

function Invoke-BoundedProcess {
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 5)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = [Diagnostics.ProcessStartInfo]@{ FileName=$FilePath; Arguments=(ConvertTo-ProcessArguments $Arguments); UseShellExecute=$false; CreateNoWindow=$true; RedirectStandardOutput=$true; RedirectStandardError=$true }
    foreach ($name in @("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP", "PYTHONINSPECT")) {
        [void]$process.StartInfo.EnvironmentVariables.Remove($name)
    }
    $process.StartInfo.EnvironmentVariables["PYTHONNOUSERSITE"] = "1"
    $process.StartInfo.EnvironmentVariables["PYTHONSAFEPATH"] = "1"
    $stdoutRetained = [IO.MemoryStream]::new()
    $stderrRetained = [IO.MemoryStream]::new()
    try {
        try { [void]$process.Start() } catch { return [ordered]@{ status="error"; exitCode=$null; stdout=""; stderr=$_.Exception.Message } }
        $stdoutBuffer = [byte[]]::new(4096); $stderrBuffer = [byte[]]::new(4096)
        $stdoutStream = $process.StandardOutput.BaseStream; $stderrStream = $process.StandardError.BaseStream
        $stdoutTask = $stdoutStream.ReadAsync($stdoutBuffer, 0, $stdoutBuffer.Length)
        $stderrTask = $stderrStream.ReadAsync($stderrBuffer, 0, $stderrBuffer.Length)
        $clock = [Diagnostics.Stopwatch]::StartNew(); $exited=$false; $timedOut=$false; $drainDeadline=[long]::MaxValue
        while ($true) {
            if ($null -ne $stdoutTask -and $stdoutTask.IsCompleted) {
                try { $count=$stdoutTask.Result } catch { $count=0 }
                if ($count -gt 0) { Add-RetainedBytes $stdoutRetained $stdoutBuffer $count; $stdoutTask=$stdoutStream.ReadAsync($stdoutBuffer,0,$stdoutBuffer.Length) } else { $stdoutTask=$null }
            }
            if ($null -ne $stderrTask -and $stderrTask.IsCompleted) {
                try { $count=$stderrTask.Result } catch { $count=0 }
                if ($count -gt 0) { Add-RetainedBytes $stderrRetained $stderrBuffer $count; $stderrTask=$stderrStream.ReadAsync($stderrBuffer,0,$stderrBuffer.Length) } else { $stderrTask=$null }
            }
            if (-not $exited) {
                if ($process.HasExited) { $exited=$true; $drainDeadline=$clock.ElapsedMilliseconds+1000 }
                elseif ($clock.ElapsedMilliseconds -ge ($TimeoutSeconds*1000)) { $timedOut=$true; try{$process.Kill()}catch{}; [void]$process.WaitForExit(1000); $exited=$true; $drainDeadline=$clock.ElapsedMilliseconds+1000 }
            }
            if ($exited -and $null -eq $stdoutTask -and $null -eq $stderrTask) { break }
            if ($exited -and $clock.ElapsedMilliseconds -ge $drainDeadline) { try{$stdoutStream.Close()}catch{}; try{$stderrStream.Close()}catch{}; break }
            Start-Sleep -Milliseconds 5
        }
        $out=[Text.Encoding]::UTF8.GetString($stdoutRetained.ToArray()).Trim(); $err=[Text.Encoding]::UTF8.GetString($stderrRetained.ToArray()).Trim()
        if ($timedOut) { return [ordered]@{ status="timeout"; exitCode=$null; stdout=$out; stderr=$err } }
        $status=if($process.ExitCode -eq 0){"ok"}else{"nonzero"}
        return [ordered]@{ status=$status; exitCode=$process.ExitCode; stdout=$out; stderr=$err }
    } finally { $stdoutRetained.Dispose(); $stderrRetained.Dispose(); $process.Dispose() }
}

function Find-BootstrapPython {
    $firstFailure = $null
    foreach ($name in @("python", "python3", "py")) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $probe = Invoke-BoundedProcess $command.Source @("-I", "-c", "import json,sys;print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),'supported':sys.version_info>=(3,10)}))") 3
        if ($probe.status -ne "ok") {
            if (-not $firstFailure) { $firstFailure = [ordered]@{ available = $true; path = $command.Source; version = $null; supported = $false; status = $probe.status } }
            continue
        }
        try { $metadata = $probe.stdout | ConvertFrom-Json } catch { continue }
        if ($metadata.supported -eq $true) { return [ordered]@{ available = $true; path = $command.Source; version = $metadata.version; supported = $true; status = "ok" } }
    }
    if ($firstFailure) { return $firstFailure }
    return [ordered]@{ available = $false; path = $null; version = $null; supported = $false; status = "missing" }
}

function Get-RuntimeEvidence {
    param([string]$Runtime, [string]$RuntimePython, [string]$Project)
    $runtimePathExists = Test-Path -LiteralPath $Runtime
    $runtimeDirectoryPresent = Test-Path -LiteralPath $Runtime -PathType Container
    $interpreterPresent = Test-Path -LiteralPath $RuntimePython -PathType Leaf
    $evidence = [ordered]@{ path = $Runtime.Replace("\", "/"); present = $runtimePathExists; directoryPresent = $runtimeDirectoryPresent; interpreterPresent = $interpreterPresent; status = "missing"; version = $null; error = $null }
    if (-not $runtimePathExists) { return $evidence }
    if (-not $runtimeDirectoryPresent) { $evidence.status = "broken"; $evidence.error = "managed runtime path is not a directory"; return $evidence }
    if (-not $interpreterPresent) { $evidence.status = "broken"; $evidence.error = "managed runtime interpreter is missing"; return $evidence }
    try { Assert-NotRedirect "managed runtime" $Runtime; Assert-NotRedirect "managed runtime Scripts" (Join-Path $Runtime "Scripts"); Assert-NotRedirect "managed runtime interpreter" $RuntimePython } catch { $evidence.status = "broken"; $evidence.error = $_.Exception.Message; return $evidence }
    $version = Invoke-BoundedProcess $RuntimePython @("-I", "-m", "stm32_toolkit.cli", "version") 10
    if ($version.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "version check $($version.status): $($version.stderr)".Trim(); return $evidence }
    $evidence.version = ($version.stdout -split "`r?`n")[0].Trim()
    if ($evidence.version -ne $RuntimeVersion) { $evidence.status = "broken"; $evidence.error = "expected toolkit $RuntimeVersion, found $($evidence.version)"; return $evidence }
    $doctor = Invoke-BoundedProcess $RuntimePython @("-I", "-m", "stm32_toolkit.cli", "--project-root", $Project, "doctor", "--json") 15
    if ($doctor.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "doctor $($doctor.status): $($doctor.stderr)".Trim(); return $evidence }
    try { $doctorPayload = $doctor.stdout | ConvertFrom-Json } catch { $evidence.status = "broken"; $evidence.error = "doctor returned invalid JSON"; return $evidence }
    if ($doctorPayload.ok -ne $true) { $evidence.status = "broken"; $evidence.error = "doctor reported failure"; return $evidence }
    $evidence.status = "healthy"
    $evidence.doctor = $doctorPayload
    return $evidence
}

function Get-GapEvidence {
    $commands = [ordered]@{
        "armGcc" = @("arm-none-eabi-gcc", "--version")
        "armGdb" = @("arm-none-eabi-gdb", "--version")
        "cmake" = @("cmake", "--version")
        "ninja" = @("ninja", "--version")
        "pyocd" = @("pyocd", "--version")
        "cubeMx" = @("STM32CubeMX", "--version")
        "vscodeExtensions" = @("code", "--list-extensions")
        "cmsisPacks" = @("pyocd", "pack", "show")
    }
    $result = [ordered]@{}
    foreach ($entry in $commands.GetEnumerator()) {
        $tool = Get-Command $entry.Value[0] -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $tool) { $result[$entry.Key] = [ordered]@{ status = "missing"; path = $null; output = $null }; continue }
        $probe = Invoke-BoundedProcess $tool.Source $entry.Value[1..($entry.Value.Count - 1)] 5
        $result[$entry.Key] = [ordered]@{ status = $probe.status; path = $tool.Source; output = if ($probe.stdout) { ($probe.stdout -split "`r?`n")[0] } else { $null } }
    }
    return $result
}

function Remove-SafeStaging {
    param([string]$Staging, [string]$StagingRoot)
    if (-not (Test-Path -LiteralPath $Staging)) { return }
    $fullStaging = [IO.Path]::GetFullPath($Staging)
    $fullRoot = [IO.Path]::GetFullPath($StagingRoot).TrimEnd("\", "/") + [IO.Path]::DirectorySeparatorChar
    if (-not $fullStaging.StartsWith($fullRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "refusing cleanup outside staging root" }
    $redirect = Get-ChildItem -LiteralPath $fullStaging -Force -Recurse -ErrorAction SilentlyContinue | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } | Select-Object -First 1
    if ($redirect) { throw "staging contains a path redirect; preserving it for manual recovery" }
    Remove-Item -LiteralPath $fullStaging -Force -Recurse
}

function Assert-StepOk {
    param($Evidence, [string]$Step)
    if ($Evidence.status -ne "ok") { throw "$Step failed ($($Evidence.status)): $($Evidence.stderr)" }
}

$staging = $null
$stagingRoot = $null
try {
    $resolvedPluginRoot = Resolve-ClaudePath "PluginRoot" $PluginRoot -MustExist
    $resolvedPluginData = Resolve-ClaudePath "PluginData" $PluginData
    $resolvedProjectDir = Resolve-ClaudePath "ProjectDir" $ProjectDir -MustExist
    Assert-NoRedirectAncestors "PluginData" $resolvedPluginData
    $package = Join-Path $resolvedPluginRoot "tools/stm32-toolkit"
    if (-not (Test-Path -LiteralPath $package -PathType Container)) { throw "PluginRoot does not contain tools/stm32-toolkit" }
    $runtimeParent = Join-Path $resolvedPluginData "runtime"
    $runtime = Join-Path $runtimeParent $RuntimeVersion
    $runtimePython = Join-Path $runtime "Scripts/python.exe"
    $legacyRuntime = Join-Path $runtimeParent $LegacyRuntimeVersion
    $legacyRuntimePython = Join-Path $legacyRuntime "Scripts/python.exe"
    $bootstrapPython = Find-BootstrapPython

    if ($Mode -eq "Check") {
        if (Test-Path -LiteralPath $runtime) {
            $runtimeEvidence = Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectDir
        } elseif (Test-Path -LiteralPath $legacyRuntime) {
            $runtimeEvidence = Get-RuntimeEvidence $legacyRuntime $legacyRuntimePython $resolvedProjectDir
        } else {
            $runtimeEvidence = Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectDir
        }
        $result = [ordered]@{
            mode = "CHECK"
            runtime = $runtimeEvidence
            bootstrapPython = $bootstrapPython
            tools = Get-GapEvidence
            project = $resolvedProjectDir.Replace("\", "/")
            mutated = $false
            authorizationRequired = ($runtimeEvidence.status -ne "healthy")
            recommendedMode = if ($runtimeEvidence.status -eq "missing") { "Bootstrap" } elseif ($runtimeEvidence.status -eq "broken") { "Repair" } else { $null }
        }
        $result | ConvertTo-Json -Depth 30
        exit 0
    }

    if (-not $bootstrapPython.supported) { throw "Host Python 3.10+ is required to create the managed runtime" }
    $currentExists = Test-Path -LiteralPath $runtime
    $legacyExists = Test-Path -LiteralPath $legacyRuntime
    if ($Mode -eq "Bootstrap" -and ($currentExists -or $legacyExists)) { throw "managed runtime path already exists; run Check and authorize Repair if it is broken" }
    if ($Mode -eq "Repair" -and -not ($currentExists -or $legacyExists)) { throw "managed runtime is missing; authorize Bootstrap instead" }
    Assert-NoRedirectAncestors "runtime parent" $runtimeParent
    Assert-NotRedirect "managed runtime" $runtime

    [void][IO.Directory]::CreateDirectory($runtimeParent)
    Assert-NoRedirectAncestors "runtime parent" $runtimeParent
    $stagingRoot = Join-Path $runtimeParent ".staging"
    [void][IO.Directory]::CreateDirectory($stagingRoot)
    Assert-NoRedirectAncestors "staging root" $stagingRoot
    $staging = Join-Path $stagingRoot ("$RuntimeVersion-" + [Guid]::NewGuid().ToString("N"))

    Assert-StepOk (Invoke-BoundedProcess $bootstrapPython.path @("-I", "-m", "venv", $staging) 120) "runtime creation"
    $stagingPython = Join-Path $staging "Scripts/python.exe"
    Assert-NotRedirect "staging runtime" $staging
    Assert-NotRedirect "staging Scripts" (Join-Path $staging "Scripts")
    Assert-NotRedirect "staging interpreter" $stagingPython
    Assert-StepOk (Invoke-BoundedProcess $stagingPython @("-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", $package) 300) "toolkit installation"
    $versionCheck = Invoke-BoundedProcess $stagingPython @("-I", "-m", "stm32_toolkit.cli", "version") 10
    Assert-StepOk $versionCheck "toolkit version validation"
    $installedVersion = ($versionCheck.stdout -split "`r?`n")[0].Trim()
    if ($installedVersion -ne $RuntimeVersion) { throw "expected toolkit $RuntimeVersion, found $installedVersion" }
    $doctorCheck = Invoke-BoundedProcess $stagingPython @("-I", "-m", "stm32_toolkit.cli", "--project-root", $resolvedProjectDir, "doctor", "--json") 15
    Assert-StepOk $doctorCheck "toolkit doctor validation"
    try { $doctorPayload = $doctorCheck.stdout | ConvertFrom-Json } catch { throw "toolkit doctor returned invalid JSON" }
    if ($doctorPayload.ok -ne $true) { throw "toolkit doctor reported failure" }

    $quarantined = $null
    $quarantineSource = $null
    if ($Mode -eq "Repair") {
        $quarantineRoot = Join-Path $runtimeParent ".quarantine"
        [void][IO.Directory]::CreateDirectory($quarantineRoot)
        Assert-NoRedirectAncestors "quarantine root" $quarantineRoot
        $quarantineSource = if ($currentExists) { $runtime } else { $legacyRuntime }
        $quarantineVersion = if ($currentExists) { $RuntimeVersion } else { $LegacyRuntimeVersion }
        $quarantined = Join-Path $quarantineRoot ("$quarantineVersion-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + [Guid]::NewGuid().ToString("N"))
        Move-Item -LiteralPath $quarantineSource -Destination $quarantined
    }
    try {
        Move-Item -LiteralPath $staging -Destination $runtime
        $staging = $null
    } catch {
        if ($quarantined -and $quarantineSource -and -not (Test-Path -LiteralPath $quarantineSource) -and (Test-Path -LiteralPath $quarantined)) { Move-Item -LiteralPath $quarantined -Destination $quarantineSource }
        throw
    }
    if ((Test-Path -LiteralPath $stagingRoot) -and -not (Get-ChildItem -LiteralPath $stagingRoot -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $stagingRoot -Force }
    [ordered]@{ mode = $Mode.ToUpperInvariant(); runtime = (Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectDir); quarantinedRuntime = if ($quarantined) { $quarantined.Replace("\", "/") } else { $null }; mutated = $true } | ConvertTo-Json -Depth 30
    exit 0
} catch {
    $primaryError = $_.Exception.Message
    if ($staging) { try { Remove-SafeStaging $staging $stagingRoot } catch { $primaryError += "; cleanup: " + $_.Exception.Message } }
    if ($stagingRoot -and (Test-Path -LiteralPath $stagingRoot) -and -not (Get-ChildItem -LiteralPath $stagingRoot -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $stagingRoot -Force }
    [Console]::Error.WriteLine("setup-stm32-env: " + $primaryError)
    exit 2
}
