[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Check", "Bootstrap", "Repair")]
    [string]$Mode,
    [Parameter(Mandatory = $true)][string]$ToolkitRoot,
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$RuntimeVersion = "0.9.0"
$LegacyRuntimeVersions = @("0.5.0", "0.3.0")
$ProcessOutputLimit = 65536
$ReleaseUtilityRelative = "tools/release/build_0900_artifacts.py"
$ReleasePolicyRelative = "tools/release/release_0900_policy.json"
$ReleaseUtilitySha256 = "6c6c457bff2606157a78c9b2215f77d4ecbd18e5d74d9ee97194754fe780aec8"
$ReleasePolicySha256 = "8bb1db7ed69941ced78ac0dac8c4aa600fc2dcb0300365a197cd8e85bade0ee7"
$ReleaseManifestRelative = "release/release-manifest.json"
$RuntimeStateFileName = "runtime-state.json"
$InMemoryReleaseLauncher = @'
import struct
import sys

try:
    utility_path = sys.argv[1]
    utility_arguments = sys.argv[2:]
    frame = sys.stdin.buffer.read()
    if frame.startswith(b"\xef\xbb\xbf"):
        frame = frame[3:]
    if len(frame) < 16:
        raise ValueError("trusted release input is truncated")
    utility_length, policy_length = struct.unpack("<QQ", frame[:16])
    expected = 16 + utility_length + policy_length
    if len(frame) != expected:
        raise ValueError("trusted release input length is invalid")
    utility_start = 16
    policy_start = utility_start + utility_length
    utility_bytes = frame[utility_start:policy_start]
    policy_bytes = frame[policy_start:]
    sys.argv = [utility_path] + utility_arguments
    namespace = {
        "__name__": "__main__",
        "__file__": utility_path,
        "__package__": None,
        "_TRUSTED_POLICY_BYTES": policy_bytes,
    }
    exec(compile(utility_bytes, utility_path, "exec"), namespace, namespace)
except SystemExit:
    raise
except Exception:
    raise SystemExit(2)
'@
$ProbeValidationScript = @'
import importlib.metadata as metadata
import sys

try:
    try:
        from packaging.version import Version
    except ImportError:
        from pip._vendor.packaging.version import Version
    import pyocd
    probe_version = metadata.version("pyocd")
    parsed_version = Version(probe_version)
    lower_bound = Version("0.45.1")
    upper_bound = Version("0.46")
except Exception:
    raise SystemExit(2)

if not lower_bound <= parsed_version < upper_bound:
    raise SystemExit(3)

print(probe_version)
'@

$MonitorValidationScript = @'
import importlib.metadata as metadata
import json
from importlib import resources


def _file(root, relative):
    node = root
    for part in relative.split("/"):
        if not part:
            continue
        node = node.joinpath(part)
    return node.is_file()


try:
    version = metadata.version("stm32-monitor")
except Exception:
    raise SystemExit(2)
ui = resources.files("stm32_monitor") / "ui_dist"
if version != "0.9.0":
    raise SystemExit(3)
if not _file(ui, "index.html") or not _file(ui, ".vite/manifest.json"):
    raise SystemExit(4)
try:
    manifest = json.loads((ui / ".vite" / "manifest.json").read_text("utf-8"))
except Exception:
    raise SystemExit(5)
assets = []
for record in manifest.values():
    if not isinstance(record, dict):
        continue
    for field in ("file", "css", "assets"):
        value = record.get(field)
        if isinstance(value, str):
            assets.append(value)
        elif isinstance(value, list):
            assets.extend(item for item in value if isinstance(item, str))
if not assets or not all(_file(ui, name) for name in assets):
    raise SystemExit(6)
print(version)
'@

$ExpectedMcpTools = @(
    "stm32_doctor",
    "stm32_project_detect",
    "stm32_project_context",
    "stm32_project_create_plan",
    "stm32_project_create_prepare",
    "stm32_project_create_apply",
    "stm32_project_regenerate_plan",
    "stm32_project_regenerate_prepare",
    "stm32_project_regenerate_apply",
    "stm32_keil_inspect",
    "stm32_keil_convert",
    "stm32_project_configure",
    "stm32_build",
    "stm32_probe_list",
    "stm32_flash",
    "stm32_debug_handoff_begin",
    "stm32_debug_handoff_end",
    "stm32_variable_read",
    "stm32_variable_sample",
    "stm32_register_read",
    "stm32_fault_analyze",
    "stm32_diagnostic_start",
    "stm32_diagnostic_show",
    "stm32_diagnostic_begin",
    "stm32_diagnostic_hypothesis_add",
    "stm32_diagnostic_hypothesis_assess",
    "stm32_diagnostic_plan_add",
    "stm32_diagnostic_plan_run",
    "stm32_test_target_replay",
    "stm32_diagnostic_source_change_declare",
    "stm32_diagnostic_verification_plan_add",
    "stm32_diagnostic_verification_start",
    "stm32_diagnostic_marker_attach",
    "stm32_diagnostic_verification_complete",
    "stm32_diagnostic_verification_show",
    "stm32_test_host_discover",
    "stm32_test_host_run",
    "stm32_test_show",
    "stm32_test_target_prepare",
    "stm32_test_target_execute",
    "stm32_acceptance_scenario_describe",
    "stm32_acceptance_scenario_record",
    "stm32_acceptance_scenario_show",
    "stm32_acceptance_attempt_begin",
    "stm32_acceptance_attempt_checkpoint",
    "stm32_acceptance_attempt_authorize_source_change",
    "stm32_acceptance_attempt_show",
    "stm32_acceptance_attempt_resume"
)
$ExpectedSkills = @(
    "setup-stm32-env",
    "migrate-keil",
    "configure-stm32-project",
    "build-firmware",
    "flash-firmware",
    "debug-firmware",
    "read-var",
    "stm32-monitor"
)

function Resolve-ExplicitPath {
    param([string]$Name, [AllowEmptyString()][string]$Value, [switch]$MustExist)
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "$Name is empty; an explicit path is required" }
    if ($Value -match '\$\{[^}]+\}') { throw "$Name contains an unresolved path placeholder" }
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
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 5, [byte[]]$StandardInput = $null)
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = [Diagnostics.ProcessStartInfo]@{ FileName=$FilePath; Arguments=(ConvertTo-ProcessArguments $Arguments); UseShellExecute=$false; CreateNoWindow=$true; RedirectStandardInput=($null -ne $StandardInput); RedirectStandardOutput=$true; RedirectStandardError=$true }
    foreach ($name in @("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTHONSTARTUP", "PYTHONINSPECT")) {
        [void]$process.StartInfo.EnvironmentVariables.Remove($name)
    }
    $process.StartInfo.EnvironmentVariables["PYTHONNOUSERSITE"] = "1"
    $process.StartInfo.EnvironmentVariables["PYTHONSAFEPATH"] = "1"
    $stdoutRetained = [IO.MemoryStream]::new()
    $stderrRetained = [IO.MemoryStream]::new()
    try {
        try { [void]$process.Start() } catch { return [ordered]@{ status="error"; exitCode=$null; stdout=""; stderr=$_.Exception.Message } }
        if ($null -ne $StandardInput) {
            try {
                $inputStream = $process.StandardInput.BaseStream
                $inputStream.Write($StandardInput, 0, $StandardInput.Length)
                $inputStream.Flush()
                $inputStream.Close()
            } catch { try { $process.Kill() } catch { }; return [ordered]@{ status="error"; exitCode=$null; stdout=""; stderr="trusted release input failed" } }
        }
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
    $candidates = @(
        [ordered]@{ name = "py"; prefix = @("-3.12") },
        [ordered]@{ name = "python"; prefix = @() },
        [ordered]@{ name = "python3"; prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $name = $candidate.name
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $command) { continue }
        $probeArguments = @($candidate.prefix) + @("-I", "-c", "import json,sys;print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),'supported':sys.version_info[:2] == (3,12)}))")
        $probe = Invoke-BoundedProcess $command.Source $probeArguments 3
        if ($probe.status -ne "ok") {
            if (-not $firstFailure) { $firstFailure = [ordered]@{ available = $true; path = $command.Source; prefix = @($candidate.prefix); version = $null; supported = $false; status = $probe.status } }
            continue
        }
        try { $metadata = $probe.stdout | ConvertFrom-Json } catch { continue }
        if ($metadata.supported -eq $true) { return [ordered]@{ available = $true; path = $command.Source; prefix = @($candidate.prefix); version = $metadata.version; supported = $true; status = "ok" } }
    }
    if ($firstFailure) { return $firstFailure }
    return [ordered]@{ available = $false; path = $null; prefix = @(); version = $null; supported = $false; status = "missing" }
}

function New-TrustedReleaseInputFrame {
    param([byte[]]$UtilityBytes, [byte[]]$PolicyBytes)
    $frame = [byte[]]::new(16 + $UtilityBytes.Length + $PolicyBytes.Length)
    [Buffer]::BlockCopy([BitConverter]::GetBytes([Int64]$UtilityBytes.Length), 0, $frame, 0, 8)
    [Buffer]::BlockCopy([BitConverter]::GetBytes([Int64]$PolicyBytes.Length), 0, $frame, 8, 8)
    [Buffer]::BlockCopy($UtilityBytes, 0, $frame, 16, $UtilityBytes.Length)
    [Buffer]::BlockCopy($PolicyBytes, 0, $frame, 16 + $UtilityBytes.Length, $PolicyBytes.Length)
    return $frame
}

function Invoke-ReleaseUtility {
    param([object]$BootstrapPython, [object]$TrustedInputs, [string[]]$Arguments)
    if ($null -eq $BootstrapPython -or $BootstrapPython.supported -ne $true -or -not $BootstrapPython.path -or $null -eq $TrustedInputs -or $TrustedInputs.status -ne "ok") {
        return [ordered]@{ status = "unavailable"; exitCode = $null; payload = $null }
    }
    $launcherArguments = @($BootstrapPython.prefix) + @("-I", "-c", $InMemoryReleaseLauncher, [string]$TrustedInputs.utilityPath) + @($Arguments)
    $inputFrame = New-TrustedReleaseInputFrame $TrustedInputs.utilityBytes $TrustedInputs.policyBytes
    $result = Invoke-BoundedProcess $BootstrapPython.path $launcherArguments 30 -StandardInput $inputFrame
    $payload = $null
    if ($result.stdout) {
        try { $payload = $result.stdout | ConvertFrom-Json } catch { $payload = $null }
    }
    return [ordered]@{ status = $result.status; exitCode = $result.exitCode; payload = $payload; stderr = $result.stderr }
}

function Get-BytesSha256 {
    param([byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (([BitConverter]::ToString($sha.ComputeHash($Bytes)) -replace "-", "").ToLowerInvariant()) }
    finally { $sha.Dispose() }
}

function Get-TrustedBundleInputs {
    param([string]$ToolkitRoot)
    $manifest = Join-Path $ToolkitRoot $ReleaseManifestRelative
    $utility = Join-Path $ToolkitRoot $ReleaseUtilityRelative
    $policy = Join-Path $ToolkitRoot $ReleasePolicyRelative
    $base = [ordered]@{ status = "missing"; manifestPath = $manifest; utilityPath = $utility; policyPath = $policy; manifestSha256 = $null; utilitySha256 = $null; policySha256 = $null; utilityBytes = $null; policyBytes = $null; error = $null }
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { return $base }
    if (-not (Test-Path -LiteralPath $utility -PathType Leaf) -or -not (Test-Path -LiteralPath $policy -PathType Leaf)) {
        $base.status = "invalid"; $base.error = "release trust inputs are unavailable"; return $base
    }
    try {
        Assert-NotRedirect "release utility" $utility
        Assert-NotRedirect "release policy" $policy
        $utilityBytes = [IO.File]::ReadAllBytes($utility)
        $policyBytes = [IO.File]::ReadAllBytes($policy)
        $utilityHash = Get-BytesSha256 $utilityBytes
        $policyHash = Get-BytesSha256 $policyBytes
        if ($utilityHash -cne $ReleaseUtilitySha256 -or $policyHash -cne $ReleasePolicySha256) {
            $base.status = "invalid"; $base.error = "release bootstrap trust anchor mismatch"; return $base
        }
        $base.status = "ok"
        $base.manifestSha256 = Get-FileSha256 $manifest
        $base.utilitySha256 = $utilityHash
        $base.policySha256 = $policyHash
        $base.utilityBytes = $utilityBytes
        $base.policyBytes = $policyBytes
        return $base
    } catch {
        $base.status = "invalid"; $base.error = "release bootstrap trust inputs are invalid"; return $base
    }
}

function Get-BundleEvidence {
    param([string]$ToolkitRoot, [object]$BootstrapPython, [object]$TrustedInputs)
    $manifest = Join-Path $ToolkitRoot $ReleaseManifestRelative
    $base = [ordered]@{ status = "missing"; productVersion = $null; wheels = @(); wheelEntries = @(); manifestSha256 = $null; utilitySha256 = $null; sourceCommit = $null; error = $null }
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { return $base }
    if ($null -eq $TrustedInputs -or $TrustedInputs.status -ne "ok") { $base.status = "invalid"; $base.error = if ($TrustedInputs.error) { $TrustedInputs.error } else { "release bootstrap trust inputs are unavailable" }; return $base }
    $checked = Invoke-ReleaseUtility $BootstrapPython $TrustedInputs @("verify-bundle", "--toolkit-root", $ToolkitRoot, "--json")
    if ($checked.status -ne "ok" -or $null -eq $checked.payload -or $checked.payload.status -ne "ok") {
        $base.status = "invalid"; $base.error = "release bundle verification failed"; return $base
    }
    if ([string]$checked.payload.manifestSha256 -cne [string]$TrustedInputs.manifestSha256 -or [string]$checked.payload.utilitySha256 -cne [string]$TrustedInputs.utilitySha256) {
        $base.status = "invalid"; $base.error = "release bundle facts changed after trust read"; return $base
    }
    $base.status = "ok"
    $base.productVersion = $checked.payload.productVersion
    $base.wheels = @($checked.payload.wheels)
    $base.wheelEntries = @($checked.payload.wheelEntries)
    $base.manifestSha256 = [string]$TrustedInputs.manifestSha256
    $base.utilitySha256 = [string]$TrustedInputs.utilitySha256
    $base.sourceCommit = [string]$checked.payload.sourceCommit
    if (-not $base.manifestSha256 -or -not $base.utilitySha256 -or -not $base.sourceCommit -or $base.wheelEntries.Count -eq 0) {
        $base.status = "invalid"; $base.error = "release bundle verification omitted bound facts"; return $base
    }
    return $base
}

function Assert-BundleFacts {
    param([string]$ToolkitRoot, [object]$BundleEvidence, [object]$TrustedInputs)
    if ($null -eq $BundleEvidence -or $BundleEvidence.status -ne "ok" -or $null -eq $TrustedInputs -or $TrustedInputs.status -ne "ok") { throw "release bundle verification is unavailable" }
    $manifest = Join-Path $ToolkitRoot $ReleaseManifestRelative
    $utility = Join-Path $ToolkitRoot $ReleaseUtilityRelative
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf) -or -not (Test-Path -LiteralPath $utility -PathType Leaf)) { throw "verified release facts are no longer present" }
    if ((Get-FileSha256 $manifest) -cne ([string]$TrustedInputs.manifestSha256)) { throw "release manifest changed after verification" }
    if ((Get-FileSha256 $utility) -cne ([string]$TrustedInputs.utilitySha256)) { throw "release utility changed after verification" }
    if ((Get-FileSha256 (Join-Path $ToolkitRoot $ReleasePolicyRelative)) -cne ([string]$TrustedInputs.policySha256)) { throw "release policy changed after verification" }
}

function Get-RuntimeStateEvidence {
    param([string]$StatePath, [string]$ManifestPath, [object]$BootstrapPython, [object]$BundleEvidence, [object]$TrustedInputs)
    $missing = [ordered]@{ status = "missing"; activeVersion = $null; installGeneration = $null }
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $missing }
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { return [ordered]@{ status = "invalid"; error = "release manifest is unavailable" } }
    try { Assert-BundleFacts (Split-Path (Split-Path $ManifestPath -Parent) -Parent) $BundleEvidence $TrustedInputs } catch { return [ordered]@{ status = "invalid"; error = $_.Exception.Message } }
    $toolkitRoot = Split-Path (Split-Path $ManifestPath -Parent) -Parent
    $checked = Invoke-ReleaseUtility $BootstrapPython $TrustedInputs @("verify-runtime-state", "--state", $StatePath, "--candidate-manifest", $ManifestPath, "--json")
    if ($null -eq $checked.payload -or -not ($checked.payload.status)) {
        return [ordered]@{ status = "invalid"; error = "runtime state verification failed" }
    }
    $result = [ordered]@{ status = [string]$checked.payload.status; activeVersion = $null; installGeneration = $null }
    if ($checked.payload.PSObject.Properties.Name -contains "activeVersion") { $result.activeVersion = $checked.payload.activeVersion }
    if ($checked.payload.PSObject.Properties.Name -contains "installGeneration") { $result.installGeneration = $checked.payload.installGeneration }
    return $result
}

function Write-RuntimeStateAtomic {
    param([string]$StatePath, [string]$ManifestHash, [string]$SourceCommit, [int]$Generation)
    $parent = Split-Path $StatePath -Parent
    [void][IO.Directory]::CreateDirectory($parent)
    $payload = [ordered]@{
        schema = "stm32-toolkit-runtime-state/1"
        activeVersion = $RuntimeVersion
        highestInstalledVersion = $RuntimeVersion
        releaseManifestSha256 = $ManifestHash
        sourceCommit = $SourceCommit
        installGeneration = $Generation
    }
    $json = ($payload | ConvertTo-Json -Compress) + "`n"
    $temp = "$StatePath.$([Guid]::NewGuid().ToString('N')).tmp"
    $encoding = [Text.UTF8Encoding]::new($false)
    $stream = $null
    try {
        $stream = [IO.FileStream]::new($temp, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $bytes = $encoding.GetBytes($json)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose(); $stream = $null
        if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
            $backup = "$StatePath.$([Guid]::NewGuid().ToString('N')).bak"
            [IO.File]::Replace($temp, $StatePath, $backup, $true)
            if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
        } else {
            [IO.File]::Move($temp, $StatePath)
        }
    } finally {
        if ($stream) { $stream.Dispose() }
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
    }
}

function Get-ManifestFacts {
    param([string]$ManifestPath)
    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw -ErrorAction Stop | ConvertFrom-Json
        $bytes = [IO.File]::ReadAllBytes($ManifestPath)
        $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
        $hex = ([BitConverter]::ToString($hash) -replace "-", "").ToLowerInvariant()
        return [ordered]@{ manifest = $manifest; hash = $hex; sourceCommit = [string]$manifest.source.commit }
    } catch { throw "release manifest facts are unavailable" }
}

function Get-FileSha256 {
    param([string]$Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return (([BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($Path))) -replace "-", "").ToLowerInvariant())
    } finally { $sha.Dispose() }
}

function Get-ProductWheelPaths {
    param([string]$Runtime, [object]$BundleEvidence)
    if ($null -eq $BundleEvidence -or $BundleEvidence.status -ne "ok") { throw "verified release bundle is unavailable" }
    $wheelStage = Join-Path $Runtime "release-wheels"
    if (-not (Test-Path -LiteralPath $wheelStage -PathType Container)) { throw "final runtime release wheels are missing" }
    Assert-NoRedirectAncestors "final runtime release wheels" $wheelStage
    $paths = @()
    foreach ($distribution in @("stm32-toolkit", "stm32-monitor")) {
        $matches = @($BundleEvidence.wheelEntries | Where-Object {
            $null -ne $_ -and
            $_.PSObject.Properties.Name -contains "name" -and
            $_.PSObject.Properties.Name -contains "version" -and
            ([string]$_.name -ceq $distribution) -and
            ([string]$_.version -ceq $RuntimeVersion)
        })
        if ($matches.Count -ne 1) { throw "release bundle must contain exactly one verified $distribution wheel" }
        $entry = $matches[0]
        if ($entry.PSObject.Properties.Name -notcontains "file" -or $entry.PSObject.Properties.Name -notcontains "size" -or $entry.PSObject.Properties.Name -notcontains "sha256") {
            throw "verified $distribution wheel facts are incomplete"
        }
        $relativeWheel = [string]$entry.file
        if ($relativeWheel -cnotmatch '^release/wheels/[^/]+\.whl$') { throw "verified $distribution wheel path is invalid" }
        $wheelName = [IO.Path]::GetFileName($relativeWheel.Replace("/", "\"))
        if ([string]::IsNullOrWhiteSpace($wheelName)) { throw "verified $distribution wheel name is invalid" }
        $path = Join-Path $wheelStage $wheelName
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "final runtime $distribution wheel is missing" }
        Assert-NotRedirect "final runtime $distribution wheel" $path
        $item = Get-Item -LiteralPath $path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "final runtime $distribution wheel must be a regular file" }
        if ($item.Length -ne [int64]$entry.size) { throw "final runtime $distribution wheel size changed" }
        if ((Get-FileSha256 $path) -cne ([string]$entry.sha256)) { throw "final runtime $distribution wheel integrity changed" }
        $paths += $path
    }
    return $paths
}

function Test-LauncherBytesContainText {
    param([byte[]]$Bytes, [string]$Value)
    if ($null -eq $Bytes -or [string]::IsNullOrEmpty($Value)) { return $false }
    foreach ($encoding in @([Text.Encoding]::ASCII, [Text.Encoding]::UTF8, [Text.Encoding]::Unicode)) {
        $decoded = $encoding.GetString($Bytes)
        if ($decoded.IndexOf($Value, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Get-PublicLauncherRecords {
    param([string]$Runtime)
    $scripts = Join-Path $Runtime "Scripts"
    if (-not (Test-Path -LiteralPath $scripts -PathType Container)) { throw "final runtime Scripts directory is missing" }
    Assert-NotRedirect "final runtime Scripts" $scripts
    return @(
        [ordered]@{ name = "stm32-toolkit"; path = Join-Path $scripts "stm32-toolkit.exe" }
        [ordered]@{ name = "stm32-toolkit-mcp"; path = Join-Path $scripts "stm32-toolkit-mcp.exe" }
        [ordered]@{ name = "stm32-monitor"; path = Join-Path $scripts "stm32-monitor.exe" }
    )
}

function Assert-PublicLauncherBindings {
    param([string]$Runtime, [string]$RuntimePython)
    if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) { throw "final runtime interpreter is missing" }
    Assert-NotRedirect "final runtime interpreter" $RuntimePython
    $records = @(Get-PublicLauncherRecords $Runtime)
    foreach ($record in $records) {
        if (-not (Test-Path -LiteralPath $record.path -PathType Leaf)) { throw "$($record.name) launcher is missing" }
        Assert-NotRedirect "$($record.name) launcher" $record.path
        $item = Get-Item -LiteralPath $record.path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "$($record.name) launcher must be a regular file" }
        $bytes = [IO.File]::ReadAllBytes($record.path)
        if (-not (Test-LauncherBytesContainText $bytes $RuntimePython)) { throw "$($record.name) launcher is not bound to the final runtime interpreter" }
        if (Test-LauncherBytesContainText $bytes ".staging") { throw "$($record.name) launcher contains a staging interpreter binding" }
    }
    return $records
}

function Assert-PublicLauncherVersions {
    param([string]$Runtime, [string]$RuntimePython)
    $records = @(Assert-PublicLauncherBindings $Runtime $RuntimePython)
    foreach ($record in $records | Where-Object { $_.name -in @("stm32-toolkit", "stm32-monitor") }) {
        $version = Invoke-BoundedProcess $record.path @("version") 10
        if ($version.status -ne "ok") { throw "$($record.name) launcher version check failed ($($version.status))" }
        $reported = ($version.stdout -split "`r?`n")[0].Trim()
        if ($reported -cne $RuntimeVersion) { throw "$($record.name) launcher reported an unexpected version" }
    }
    return $records
}

function Finalize-PublicLaunchers {
    param([string]$Runtime, [string]$RuntimePython, [object]$BundleEvidence)
    $wheelPaths = @(Get-ProductWheelPaths $Runtime $BundleEvidence)
    $pipArguments = @("-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--no-index", "--no-deps", "--only-binary=:all:", "--force-reinstall") + $wheelPaths
    Assert-StepOk (Invoke-BoundedProcess $RuntimePython $pipArguments 300) "final runtime console launcher regeneration"
    Assert-PublicLauncherVersions $Runtime $RuntimePython | Out-Null
}

function Get-DoctorContractError {
    param($Payload)
    if ($null -eq $Payload -or $Payload.ok -isnot [bool] -or $Payload.ok -ne $true) {
        return "doctor runtime evidence is missing or not ok"
    }
    $data = $Payload.data
    if ($null -eq $data) { return "doctor runtime evidence is missing data" }
    $runtime = $data.runtime
    if ($null -eq $runtime) { return "doctor runtime evidence is missing runtime" }
    foreach ($field in @("requiredPython", "pythonVersion", "pythonSupported", "toolkitVersion", "monitorVersion", "versionsCompatible")) {
        if (-not ($runtime.PSObject.Properties.Name -contains $field)) {
            return "doctor runtime evidence is missing $field"
        }
    }
    if ($runtime.requiredPython -isnot [string] -or $runtime.requiredPython -cne ">=3.12,<3.13") {
        return "doctor runtime evidence has an unexpected Python requirement"
    }
    if ($runtime.pythonVersion -isnot [string] -or $runtime.pythonVersion -notmatch '^3\.12\.\d+$') {
        return "doctor runtime evidence has an unsupported Python version"
    }
    if ($runtime.pythonSupported -isnot [bool] -or $runtime.pythonSupported -ne $true) {
        return "doctor runtime evidence reports an unsupported Python"
    }
    if ($runtime.toolkitVersion -isnot [string] -or $runtime.toolkitVersion -cne $RuntimeVersion) {
        return "doctor runtime evidence has an unexpected Toolkit version"
    }
    if ($runtime.monitorVersion -isnot [string] -or $runtime.monitorVersion -cne $RuntimeVersion) {
        return "doctor runtime evidence has an unexpected Monitor version"
    }
    if ($runtime.versionsCompatible -isnot [bool] -or $runtime.versionsCompatible -ne $true) {
        return "doctor runtime evidence reports incompatible package versions"
    }
    $inventory = $data.publicInventory
    if ($null -eq $inventory) { return "doctor runtime evidence is missing public inventory" }
    $mcpTools = @($inventory.mcpTools)
    if ($mcpTools.Count -ne $ExpectedMcpTools.Count) {
        return "doctor runtime evidence has an unexpected MCP inventory"
    }
    for ($index = 0; $index -lt $ExpectedMcpTools.Count; $index++) {
        if ($mcpTools[$index] -isnot [string] -or $mcpTools[$index] -cne $ExpectedMcpTools[$index]) {
            return "doctor runtime evidence has an unexpected MCP inventory"
        }
    }
    $skills = @($inventory.skills)
    if ($skills.Count -ne $ExpectedSkills.Count) {
        return "doctor runtime evidence has an unexpected Skill inventory"
    }
    for ($index = 0; $index -lt $ExpectedSkills.Count; $index++) {
        if ($skills[$index] -isnot [string] -or $skills[$index] -cne $ExpectedSkills[$index]) {
            return "doctor runtime evidence has an unexpected Skill inventory"
        }
    }
    return $null
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
    $probeRuntime = Invoke-BoundedProcess $RuntimePython @("-I", "-c", $ProbeValidationScript) 10
    if ($probeRuntime.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "pyocd runtime validation failed ($($probeRuntime.status))"; return $evidence }
    $monitorRuntime = Invoke-BoundedProcess $RuntimePython @("-I", "-c", $MonitorValidationScript) 10
    if ($monitorRuntime.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "stm32-monitor runtime validation failed ($($monitorRuntime.status))"; return $evidence }
    $doctor = Invoke-BoundedProcess $RuntimePython @("-I", "-m", "stm32_toolkit.cli", "--project-root", $Project, "doctor", "--json") 15
    if ($doctor.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "doctor $($doctor.status): $($doctor.stderr)".Trim(); return $evidence }
    try { $doctorPayload = $doctor.stdout | ConvertFrom-Json } catch { $evidence.status = "broken"; $evidence.error = "doctor returned invalid JSON"; return $evidence }
    $doctorError = Get-DoctorContractError $doctorPayload
    if ($doctorError) { $evidence.status = "broken"; $evidence.error = $doctorError; return $evidence }
    $pipCheck = Invoke-BoundedProcess $RuntimePython @("-I", "-m", "pip", "check") 120
    if ($pipCheck.status -ne "ok") { $evidence.status = "broken"; $evidence.error = "pip check $($pipCheck.status): $($pipCheck.stderr)".Trim(); return $evidence }
    try { Assert-PublicLauncherVersions $Runtime $RuntimePython | Out-Null } catch { $evidence.status = "broken"; $evidence.error = $_.Exception.Message; return $evidence }
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
    $resolvedToolkitRoot = Resolve-ExplicitPath "ToolkitRoot" $ToolkitRoot -MustExist
    $resolvedDataRoot = Resolve-ExplicitPath "DataRoot" $DataRoot
    $resolvedProjectRoot = Resolve-ExplicitPath "ProjectRoot" $ProjectRoot -MustExist
    Assert-NoRedirectAncestors "ToolkitRoot" $resolvedToolkitRoot
    Assert-NoRedirectAncestors "DataRoot" $resolvedDataRoot
    Assert-NoRedirectAncestors "ProjectRoot" $resolvedProjectRoot
    $package = Join-Path $resolvedToolkitRoot "tools/stm32-toolkit"
    if (-not (Test-Path -LiteralPath $package -PathType Container)) { throw "ToolkitRoot does not contain tools/stm32-toolkit" }
    $monitorPackage = Join-Path $resolvedToolkitRoot "tools/stm32-monitor"
    if (-not (Test-Path -LiteralPath $monitorPackage -PathType Container)) { throw "ToolkitRoot does not contain tools/stm32-monitor" }
    $runtimeParent = Join-Path $resolvedDataRoot "runtime"
    $runtime = Join-Path $runtimeParent $RuntimeVersion
    $runtimePython = Join-Path $runtime "Scripts/python.exe"
    $legacyRuntimes = @(
        foreach ($legacyVersion in $LegacyRuntimeVersions) {
            [ordered]@{
                version = $legacyVersion
                path = Join-Path $runtimeParent $legacyVersion
                python = Join-Path (Join-Path $runtimeParent $legacyVersion) "Scripts/python.exe"
            }
        }
    )
    $bootstrapPython = Find-BootstrapPython
    $releaseManifest = Join-Path $resolvedToolkitRoot $ReleaseManifestRelative
    $trustedInputs = Get-TrustedBundleInputs $resolvedToolkitRoot
    $bundleEvidence = Get-BundleEvidence $resolvedToolkitRoot $bootstrapPython $trustedInputs
    $runtimeStatePath = Join-Path $runtimeParent $RuntimeStateFileName
    $runtimeStateEvidence = Get-RuntimeStateEvidence $runtimeStatePath $releaseManifest $bootstrapPython $bundleEvidence $trustedInputs

    if ($Mode -eq "Check") {
        if (Test-Path -LiteralPath $runtime) {
            $runtimeEvidence = Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectRoot
        } else {
            $legacy = $legacyRuntimes | Where-Object { Test-Path -LiteralPath $_.path } | Select-Object -First 1
            if ($legacy) {
                $runtimeEvidence = Get-RuntimeEvidence $legacy.path $legacy.python $resolvedProjectRoot
            } else {
                $runtimeEvidence = Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectRoot
            }
        }
        $result = [ordered]@{
            mode = "CHECK"
            runtime = $runtimeEvidence
            bootstrapPython = $bootstrapPython
            tools = Get-GapEvidence
            bundle = $bundleEvidence
            runtimeState = $runtimeStateEvidence
            project = $resolvedProjectRoot.Replace("\", "/")
            mutated = $false
            authorizationRequired = ($runtimeEvidence.status -ne "healthy")
            recommendedMode = if ($runtimeEvidence.status -eq "missing") { "Bootstrap" } elseif ($runtimeEvidence.status -eq "broken") { "Repair" } else { $null }
        }
        $result | ConvertTo-Json -Depth 30
        exit 0
    }

    if (-not $bootstrapPython.supported) { throw "CPython >=3.12,<3.13 is required to create the managed runtime" }
    $currentExists = Test-Path -LiteralPath $runtime
    $presentLegacyRuntimes = @($legacyRuntimes | Where-Object { Test-Path -LiteralPath $_.path })
    $unknownRuntimeDirectories = @()
    if (Test-Path -LiteralPath $runtimeParent -PathType Container) {
        $knownRuntimeNames = @($RuntimeVersion) + @($LegacyRuntimeVersions) + @(".staging", ".quarantine")
        $unknownRuntimeDirectories = @(Get-ChildItem -LiteralPath $runtimeParent -Directory -Force | Where-Object { $knownRuntimeNames -notcontains $_.Name })
    }
    if ($unknownRuntimeDirectories.Count -gt 0) { throw "unexplained managed runtime directory is present" }
    if ($Mode -eq "Bootstrap" -and ($currentExists -or $presentLegacyRuntimes.Count -gt 0)) { throw "managed runtime path already exists; run Check and authorize Repair if it is broken" }
    if ($Mode -eq "Repair" -and ($presentLegacyRuntimes.Count -gt 1)) { throw "multiple legacy runtimes are present; repair is ambiguous" }
    if ($Mode -eq "Repair" -and -not ($currentExists -or $presentLegacyRuntimes.Count -gt 0)) { throw "managed runtime is missing; authorize Bootstrap instead" }
    if ($bundleEvidence.status -ne "ok") { throw "release bundle is missing or invalid" }
    Assert-BundleFacts $resolvedToolkitRoot $bundleEvidence $trustedInputs
    if ($runtimeStateEvidence.status -in @("downgrade-refused", "source-conflict", "unsupported", "invalid")) {
        throw "runtime state refuses this release candidate"
    }
    Assert-NoRedirectAncestors "runtime parent" $runtimeParent
    Assert-NotRedirect "managed runtime" $runtime

    [void][IO.Directory]::CreateDirectory($runtimeParent)
    Assert-NoRedirectAncestors "runtime parent" $runtimeParent
    $stagingRoot = Join-Path $runtimeParent ".staging"
    [void][IO.Directory]::CreateDirectory($stagingRoot)
    Assert-NoRedirectAncestors "staging root" $stagingRoot
    $staging = Join-Path $stagingRoot ("$RuntimeVersion-" + [Guid]::NewGuid().ToString("N"))

    Assert-StepOk (Invoke-BoundedProcess $bootstrapPython.path (@($bootstrapPython.prefix) + @("-I", "-m", "venv", $staging)) 120) "runtime creation"
    $stagingPython = Join-Path $staging "Scripts/python.exe"
    Assert-NotRedirect "staging runtime" $staging
    Assert-NotRedirect "staging Scripts" (Join-Path $staging "Scripts")
    Assert-NotRedirect "staging interpreter" $stagingPython
    $wheelArguments = @()
    $wheelStage = Join-Path $staging "release-wheels"
    [void][IO.Directory]::CreateDirectory($wheelStage)
    foreach ($manifestWheel in @($bundleEvidence.wheelEntries)) {
        if ($null -eq $manifestWheel) { throw "release bundle wheel facts are invalid" }
        $relativeWheel = [string]$manifestWheel.file
        if ($relativeWheel -isnot [string] -or $relativeWheel -notmatch '^release/wheels/[^/]+\.whl$') { throw "release bundle wheel path is invalid" }
        $sourceWheel = Join-Path $resolvedToolkitRoot ($relativeWheel.Replace("/", "\"))
        if (-not (Test-Path -LiteralPath $sourceWheel -PathType Leaf)) { throw "release bundle wheel is missing" }
        $sourceHash = Get-FileSha256 $sourceWheel
        if ((Get-Item -LiteralPath $sourceWheel).Length -ne [int64]$manifestWheel.size) { throw "release bundle wheel size changed" }
        if ($sourceHash -cne ([string]$manifestWheel.sha256)) { throw "release bundle wheel integrity changed" }
        $destinationWheel = Join-Path $wheelStage ([IO.Path]::GetFileName($sourceWheel))
        Copy-Item -LiteralPath $sourceWheel -Destination $destinationWheel -Force
        Assert-NotRedirect "staged release wheel" $destinationWheel
        $stagedHash = Get-FileSha256 $destinationWheel
        if ($stagedHash -cne ([string]$manifestWheel.sha256)) { throw "staged release wheel integrity changed" }
        $wheelArguments += $destinationWheel
    }
    if ($wheelArguments.Count -eq 0) { throw "release bundle has no runtime wheels" }
    # The historical source expressions "${package}[probe]" and $monitorPackage are
    # intentionally not installed; only verified release-manifest wheels are accepted.
    $pipInstallArguments = @("-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--no-index", "--no-deps", "--only-binary=:all:") + $wheelArguments
    Assert-StepOk (Invoke-BoundedProcess $stagingPython $pipInstallArguments 300) "offline runtime installation"
    Assert-StepOk (Invoke-BoundedProcess $stagingPython @("-I", "-m", "pip", "check") 120) "pip check"
    $versionCheck = Invoke-BoundedProcess $stagingPython @("-I", "-m", "stm32_toolkit.cli", "version") 10
    Assert-StepOk $versionCheck "toolkit version validation"
    $installedVersion = ($versionCheck.stdout -split "`r?`n")[0].Trim()
    if ($installedVersion -ne $RuntimeVersion) { throw "expected toolkit $RuntimeVersion, found $installedVersion" }
    Assert-StepOk (Invoke-BoundedProcess $stagingPython @("-I", "-c", $ProbeValidationScript) 10) "pyocd runtime validation"
    Assert-StepOk (Invoke-BoundedProcess $stagingPython @("-I", "-c", $MonitorValidationScript) 10) "monitor UI validation"
    $doctorCheck = Invoke-BoundedProcess $stagingPython @("-I", "-m", "stm32_toolkit.cli", "--project-root", $resolvedProjectRoot, "doctor", "--json") 15
    Assert-StepOk $doctorCheck "toolkit doctor validation"
    try { $doctorPayload = $doctorCheck.stdout | ConvertFrom-Json } catch { throw "toolkit doctor returned invalid JSON" }
    $doctorError = Get-DoctorContractError $doctorPayload
    if ($doctorError) { throw $doctorError }
    Assert-BundleFacts $resolvedToolkitRoot $bundleEvidence $trustedInputs

    $quarantined = $null
    $quarantineSource = $null
    $priorStateExists = Test-Path -LiteralPath $runtimeStatePath -PathType Leaf
    $priorStateBytes = $null
    if ($priorStateExists) { $priorStateBytes = [IO.File]::ReadAllBytes($runtimeStatePath) }
    $stateGeneration = 1
    if ($runtimeStateEvidence.installGeneration -is [int] -or $runtimeStateEvidence.installGeneration -is [long]) {
        $stateGeneration = ([int]$runtimeStateEvidence.installGeneration) + 1
    }
    if ($Mode -eq "Repair") {
        $quarantineRoot = Join-Path $runtimeParent ".quarantine"
        [void][IO.Directory]::CreateDirectory($quarantineRoot)
        Assert-NoRedirectAncestors "quarantine root" $quarantineRoot
        $legacyToQuarantine = if ($presentLegacyRuntimes.Count -eq 1) { $presentLegacyRuntimes[0] } else { $null }
        $quarantineSource = if ($currentExists) { $runtime } else { $legacyToQuarantine.path }
        $quarantineVersion = if ($currentExists) { $RuntimeVersion } else { $legacyToQuarantine.version }
        $quarantined = Join-Path $quarantineRoot ("$quarantineVersion-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + [Guid]::NewGuid().ToString("N"))
        Move-Item -LiteralPath $quarantineSource -Destination $quarantined
    }
    try {
        Move-Item -LiteralPath $staging -Destination $runtime
        $staging = $null
        Finalize-PublicLaunchers $runtime $runtimePython $bundleEvidence
        $finalRuntimeEvidence = Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectRoot
        if ($finalRuntimeEvidence.status -ne "healthy") { throw "final runtime validation failed: $($finalRuntimeEvidence.error)" }
        Write-RuntimeStateAtomic $runtimeStatePath $bundleEvidence.manifestSha256 $bundleEvidence.sourceCommit $stateGeneration
    } catch {
        if (Test-Path -LiteralPath $runtime -PathType Container) {
            try { Remove-Item -LiteralPath $runtime -Force -Recurse -ErrorAction Stop } catch { }
        }
        if ($quarantined -and $quarantineSource -and -not (Test-Path -LiteralPath $quarantineSource) -and (Test-Path -LiteralPath $quarantined)) {
            try { Move-Item -LiteralPath $quarantined -Destination $quarantineSource -ErrorAction Stop } catch { }
        }
        if ($priorStateExists -and $priorStateBytes) {
            try { [IO.File]::WriteAllBytes($runtimeStatePath, $priorStateBytes) } catch { }
        } elseif (-not $priorStateExists -and (Test-Path -LiteralPath $runtimeStatePath)) {
            try { Remove-Item -LiteralPath $runtimeStatePath -Force } catch { }
        }
        throw
    }
    if ((Test-Path -LiteralPath $stagingRoot) -and -not (Get-ChildItem -LiteralPath $stagingRoot -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $stagingRoot -Force }
    [ordered]@{ mode = $Mode.ToUpperInvariant(); runtime = (Get-RuntimeEvidence $runtime $runtimePython $resolvedProjectRoot); bundle = $bundleEvidence; runtimeState = (Get-RuntimeStateEvidence $runtimeStatePath $releaseManifest $bootstrapPython $bundleEvidence $trustedInputs); quarantinedRuntime = if ($quarantined) { $quarantined.Replace("\", "/") } else { $null }; mutated = $true } | ConvertTo-Json -Depth 30
    exit 0
} catch {
    $primaryError = $_.Exception.Message
    if ($staging) { try { Remove-SafeStaging $staging $stagingRoot } catch { $primaryError += "; cleanup: " + $_.Exception.Message } }
    if ($stagingRoot -and (Test-Path -LiteralPath $stagingRoot) -and -not (Get-ChildItem -LiteralPath $stagingRoot -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $stagingRoot -Force }
    [Console]::Error.WriteLine("setup-stm32-env: " + $primaryError)
    exit 2
}
