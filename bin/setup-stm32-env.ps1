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
$RuntimeVersion = "0.2.0"
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

function ConvertTo-ProcessArguments {
    param([string[]]$Values)
    return (($Values | ForEach-Object { '"' + $_.Replace('"', '\"') + '"' }) -join ' ')
}


function Invoke-BoundedProcess {
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 5)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = [Diagnostics.ProcessStartInfo]@{
        FileName = $FilePath
        Arguments = (ConvertTo-ProcessArguments $Arguments)
        UseShellExecute = $false
        CreateNoWindow = $true
        RedirectStandardOutput = $true
        RedirectStandardError = $true
    }
    try {
        try { [void]$process.Start() } catch { return [ordered]@{ status = "error"; exitCode = $null; stdout = ""; stderr = $_.Exception.Message } }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch {}
            [void]$process.WaitForExit(1000)
            [void]$stdoutTask.Wait(1000)
            [void]$stderrTask.Wait(1000)
            $out = if ($stdoutTask.IsCompleted) { $stdoutTask.Result.Substring(0, [Math]::Min($stdoutTask.Result.Length, $ProcessOutputLimit)).Trim() } else { "" }
            $err = if ($stderrTask.IsCompleted) { $stderrTask.Result.Substring(0, [Math]::Min($stderrTask.Result.Length, $ProcessOutputLimit)).Trim() } else { "" }
            return [ordered]@{ status = "timeout"; exitCode = $null; stdout = $out; stderr = $err }
        }
        [void]$stdoutTask.Wait(1000)
        [void]$stderrTask.Wait(1000)
        $status = if ($process.ExitCode -eq 0) { "ok" } else { "nonzero" }
        $out = if ($stdoutTask.IsCompleted) { $stdoutTask.Result.Substring(0, [Math]::Min($stdoutTask.Result.Length, $ProcessOutputLimit)).Trim() } else { "" }
        $err = if ($stderrTask.IsCompleted) { $stderrTask.Result.Substring(0, [Math]::Min($stderrTask.Result.Length, $ProcessOutputLimit)).Trim() } else { "" }
        return [ordered]@{ status = $status; exitCode = $process.ExitCode; stdout = $out; stderr = $err }
    } finally {
        $process.Dispose()
    }
}

function Find-BootstrapPython {
    $firstFailure = $null
    foreach ($name in @("python", "python3", "py")) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $probe = Invoke-BoundedProcess $command.Source @("-c", "import json,sys;print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),'supported':sys.version_info>=(3,10)}))") 3
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
    $evidence = [ordered]@{ path = $Runtime.Replace("\", "/"); present = (Test-Path -LiteralPath $RuntimePython -PathType Leaf); status = "missing"; version = $null; error = $null }
    if (-not $evidence.present) { return $evidence }
    try { Assert-NotRedirect "managed runtime" $Runtime; Assert-NotRedirect "managed runtime Scripts" (Join-Path $Runtime "Scripts"); Assert-NotRedirect "managed runtime interpreter" $RuntimePython } catch { $evidence.status = "broken"; $evidence.error = $_.Exception.Message; return $evidence }
    $version = Invoke-BoundedProcess $RuntimePython @("-m", "stm32_toolkit.cli", "version") 10
    if ($version.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "version check $($version.status): $($version.stderr)".Trim(); return $evidence }
    $evidence.version = ($version.stdout -split "`r?`n")[0].Trim()
    if ($evidence.version -ne $RuntimeVersion) { $evidence.status = "broken"; $evidence.error = "expected toolkit $RuntimeVersion, found $($evidence.version)"; return $evidence }
    $doctor = Invoke-BoundedProcess $RuntimePython @("-m", "stm32_toolkit.cli", "--project-root", $Project, "doctor", "--json") 15
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
    Assert-NotRedirect "PluginData" $resolvedPluginData
    $package = Join-Path $resolvedPluginRoot "tools/stm32-toolkit"
    if (-not (Test-Path -LiteralPath $package -PathType Container)) { throw "PluginRoot does not contain tools/stm32-toolkit" }
    $runtimeParent = Join-Path $resolvedPluginData "runtime"
    $runtime = Join-Path $runtimeParent $RuntimeVersion
    $runtimePython = Join-Path $runtime "Scripts/python.exe"
    $bootstrapPython = Find-BootstrapPython

    if ($Mode -eq "Check") {
        $runtimeEvidence = Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectDir
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
    if ($Mode -eq "Bootstrap" -and (Test-Path -LiteralPath $runtime)) { throw "managed runtime path already exists; run Check and authorize Repair if it is broken" }
    if ($Mode -eq "Repair" -and -not (Test-Path -LiteralPath $runtime)) { throw "managed runtime is missing; authorize Bootstrap instead" }
    Assert-NotRedirect "runtime parent" $runtimeParent
    Assert-NotRedirect "managed runtime" $runtime

    [void][IO.Directory]::CreateDirectory($runtimeParent)
    Assert-NotRedirect "runtime parent" $runtimeParent
    $stagingRoot = Join-Path $runtimeParent ".staging"
    [void][IO.Directory]::CreateDirectory($stagingRoot)
    Assert-NotRedirect "staging root" $stagingRoot
    $staging = Join-Path $stagingRoot ("$RuntimeVersion-" + [Guid]::NewGuid().ToString("N"))

    Assert-StepOk (Invoke-BoundedProcess $bootstrapPython.path @("-m", "venv", $staging) 120) "runtime creation"
    $stagingPython = Join-Path $staging "Scripts/python.exe"
    Assert-NotRedirect "staging runtime" $staging
    Assert-NotRedirect "staging Scripts" (Join-Path $staging "Scripts")
    Assert-NotRedirect "staging interpreter" $stagingPython
    Assert-StepOk (Invoke-BoundedProcess $stagingPython @("-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--no-build-isolation", $package) 300) "toolkit installation"
    $versionCheck = Invoke-BoundedProcess $stagingPython @("-m", "stm32_toolkit.cli", "version") 10
    Assert-StepOk $versionCheck "toolkit version validation"
    $installedVersion = ($versionCheck.stdout -split "`r?`n")[0].Trim()
    if ($installedVersion -ne $RuntimeVersion) { throw "expected toolkit $RuntimeVersion, found $installedVersion" }
    $doctorCheck = Invoke-BoundedProcess $stagingPython @("-m", "stm32_toolkit.cli", "--project-root", $resolvedProjectDir, "doctor", "--json") 15
    Assert-StepOk $doctorCheck "toolkit doctor validation"
    try { $doctorPayload = $doctorCheck.stdout | ConvertFrom-Json } catch { throw "toolkit doctor returned invalid JSON" }
    if ($doctorPayload.ok -ne $true) { throw "toolkit doctor reported failure" }

    $quarantined = $null
    if ($Mode -eq "Repair") {
        $quarantineRoot = Join-Path $runtimeParent ".quarantine"
        [void][IO.Directory]::CreateDirectory($quarantineRoot)
        Assert-NotRedirect "quarantine root" $quarantineRoot
        $quarantined = Join-Path $quarantineRoot ("$RuntimeVersion-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + [Guid]::NewGuid().ToString("N"))
        Move-Item -LiteralPath $runtime -Destination $quarantined
    }
    try {
        Move-Item -LiteralPath $staging -Destination $runtime
        $staging = $null
    } catch {
        if ($quarantined -and -not (Test-Path -LiteralPath $runtime) -and (Test-Path -LiteralPath $quarantined)) { Move-Item -LiteralPath $quarantined -Destination $runtime }
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
