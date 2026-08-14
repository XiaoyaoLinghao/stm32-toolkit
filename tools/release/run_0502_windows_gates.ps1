[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$SupportRoot,
    [Parameter(Mandatory = $true)][string]$CodeHead,
    [Parameter(Mandatory = $true)][string]$Git,
    [Parameter(Mandatory = $true)][string]$Node,
    [Parameter(Mandatory = $true)][string]$Npm,
    [Parameter(Mandatory = $true)][string]$Python310,
    [Parameter(Mandatory = $true)][string]$Python312,
    [Parameter(Mandatory = $true)][string]$CmdExe
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$AcceptedBase = 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'

$script:GateResults = [System.Collections.Generic.List[object]]::new()
$script:Failed = $false
$script:FirstError = $null
$script:ActualHead = $null
$script:SupportManifestSha256 = $null
$script:SupportTreeSha256 = $null

# ---------------------------------------------------------------------------
# Entry validation. These failures happen before EvidenceRoot has been proven
# legal and therefore never claim a summary.json; the gate sequence below is
# the only place a summary is promised.
# ---------------------------------------------------------------------------
function Resolve-0502Path {
    param([string]$Value, [string]$Label, [bool]$Leaf)
    if ([string]::IsNullOrWhiteSpace($Value) -or -not [IO.Path]::IsPathRooted($Value)) { throw "$Label must be rooted" }
    $full = [IO.Path]::GetFullPath($Value)
    if ($full -cne $Value) { throw "$Label must be normalized" }
    $resolved = (Resolve-Path -LiteralPath $full -ErrorAction Stop).Path
    if ($resolved -cne $full) { throw "$Label resolves through a case or reparse alias" }
    if ($Leaf -and -not [IO.File]::Exists($resolved)) { throw "$Label must be a file" }
    return $resolved
}

$RepoRoot = Resolve-0502Path $RepoRoot 'RepoRoot' $false
$EvidenceRoot = Resolve-0502Path $EvidenceRoot 'EvidenceRoot' $false
$SupportRoot = Resolve-0502Path $SupportRoot 'SupportRoot' $false
$Git = Resolve-0502Path $Git 'Git' $true
$Node = Resolve-0502Path $Node 'Node' $true
$Npm = Resolve-0502Path $Npm 'Npm' $true
$Python310 = Resolve-0502Path $Python310 'Python310' $true
$Python312 = Resolve-0502Path $Python312 'Python312' $true
$CmdExe = Resolve-0502Path $CmdExe 'CmdExe' $true
if ($CodeHead -notmatch '^[0-9a-f]{40}$') { throw 'CodeHead must be one full SHA' }

function Assert-0502Separate {
    param([string]$Left, [string]$Right, [string]$Label)
    $a = $Left.TrimEnd('\') + '\'
    $b = $Right.TrimEnd('\') + '\'
    if ([string]::Equals($Left, $Right, [StringComparison]::OrdinalIgnoreCase) -or $a.StartsWith($b, [StringComparison]::OrdinalIgnoreCase) -or $b.StartsWith($a, [StringComparison]::OrdinalIgnoreCase)) { throw "$Label roots overlap" }
}
Assert-0502Separate $RepoRoot $EvidenceRoot 'RepoRoot/EvidenceRoot'
Assert-0502Separate $RepoRoot $SupportRoot 'RepoRoot/SupportRoot'
Assert-0502Separate $EvidenceRoot $SupportRoot 'EvidenceRoot/SupportRoot'
if (@(Get-ChildItem -LiteralPath $EvidenceRoot -Force -ErrorAction Stop).Count -ne 0) { throw 'EvidenceRoot must be empty before any log' }

$identities = @($Git, $Node, $Npm, $Python310, $Python312, $CmdExe) | ForEach-Object { $_.ToLowerInvariant() }
if (@($identities | Sort-Object -Unique).Count -ne $identities.Count) { throw 'duplicate tool identity' }

# ---------------------------------------------------------------------------
# Gate machinery. Invoke-0502Gate records PASS/FAIL and throws on the first
# nonzero exit so no later product gate ever runs.
# ---------------------------------------------------------------------------
function Invoke-0502Capture {
    param([string]$Name, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments)
    $log = Join-Path $EvidenceRoot ($Name + '.log')
    $oldGate = $env:STM32_MONITOR_GATE
    $env:STM32_MONITOR_GATE = $Name
    $oldEap = $ErrorActionPreference
    # Native stderr under Stop would raise a terminating error (e.g. the
    # fail-closed launcher tests legitimately emit to stderr and exit 2).
    $ErrorActionPreference = 'Continue'
    Push-Location -LiteralPath $WorkingDirectory
    try {
        $lines = @(& $Executable @Arguments 2>&1)
        $exit = $LASTEXITCODE
    }
    finally {
        Pop-Location
        $ErrorActionPreference = $oldEap
        if ($null -eq $oldGate) { Remove-Item Env:STM32_MONITOR_GATE -ErrorAction SilentlyContinue }
        else { $env:STM32_MONITOR_GATE = $oldGate }
    }
    $lines | Set-Content -Encoding UTF8 -LiteralPath $log
    return @{ Name = $Name; Exit = $exit; Log = $log; Lines = $lines }
}

function Invoke-0502Gate {
    param([string]$Name, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments)
    $result = Invoke-0502Capture $Name $WorkingDirectory $Executable $Arguments
    $ok = ($result.Exit -eq 0)
    $script:GateResults.Add([ordered]@{ gate = $Name; status = if ($ok) { 'PASS' } else { 'FAIL' }; exit = $result.Exit; log = $result.Log })
    if (-not $ok) {
        $script:Failed = $true
        throw "gate $Name failed with exit $($result.Exit)"
    }
    return $result
}

function Add-0502Result {
    param([string]$Name, [bool]$Ok, [string]$Detail)
    $script:GateResults.Add([ordered]@{ gate = $Name; status = if ($Ok) { 'PASS' } else { 'FAIL' }; detail = $Detail })
    if (-not $Ok) { throw "gate $Name failed: $Detail" }
}

# Get-FileHash is not reliably available under Windows PowerShell -File on this
# machine, so hashing uses the .NET API directly (lowercase hex SHA-256).
function Get-0502Sha256 {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        $bytes = $sha.ComputeHash($stream)
        return ([BitConverter]::ToString($bytes).Replace('-', '')).ToLowerInvariant()
    }
    finally { $stream.Dispose() }
}

function Write-0502Summary {
    $summary = [ordered]@{
        acceptedBase = $AcceptedBase
        codeHead = $CodeHead
        headIdentity = $script:ActualHead
        gates = @($script:GateResults)
        overall = if ($script:Failed) { 'FAIL' } else { 'PASS' }
    }
    $json = $summary | ConvertTo-Json -Depth 6
    $target = Join-Path $EvidenceRoot 'summary.json'
    $temp = Join-Path $EvidenceRoot 'summary.json.tmp'
    [IO.File]::WriteAllText($temp, $json, [Text.UTF8Encoding]::new($false))
    if ([IO.File]::Exists($target)) { [IO.File]::Replace($temp, $target, $null) | Out-Null }
    else { [IO.File]::Move($temp, $target) }
}

# ---------------------------------------------------------------------------
# Raw, trailing-NUL git inventory plumbing.
# ---------------------------------------------------------------------------
function Invoke-0502GitRaw {
    param([string[]]$Arguments)
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $Git
    $start.WorkingDirectory = $RepoRoot
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    $start.Arguments = ($Arguments | ForEach-Object { if ($_ -match '\s' -or $_ -eq '') { '"' + $_ + '"' } else { $_ } }) -join ' '
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'raw git process did not start' }
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $memory = New-Object IO.MemoryStream
    $process.StandardOutput.BaseStream.CopyTo($memory)
    $process.WaitForExit()
    $stderr = $stderrTask.Result
    if ($process.ExitCode -ne 0) { throw ('raw git diff failed: ' + $stderr) }
    return $memory.ToArray()
}

function Split-0502NulBytes {
    param([byte[]]$Bytes)
    if ($Bytes.Length -eq 0 -or $Bytes[$Bytes.Length - 1] -ne 0) { throw 'raw git inventory requires trailing NUL' }
    $utf8 = New-Object Text.UTF8Encoding($false, $true)
    $parts = New-Object Collections.Generic.List[string]
    $start = 0
    for ($index = 0; $index -lt $Bytes.Length; $index++) {
        if ($Bytes[$index] -eq 0) {
            if ($index -eq $start) { if ($index -ne $Bytes.Length - 1) { throw 'raw git inventory contains an empty interior field' } }
            else { $parts.Add($utf8.GetString($Bytes, $start, $index - $start)) }
            $start = $index + 1
        }
    }
    if ($start -ne $Bytes.Length) { throw 'raw NUL stream did not terminate' }
    return $parts.ToArray()
}

# ---------------------------------------------------------------------------
# Controlled support verification. verify_support.py (Task 1) is authoritative;
# verify_0502_release.py is only the deterministic scope/coverage/static checker.
# uiRoot/supportVerifier are resolved inside the gate sequence so a HEAD
# identity failure is reported before any repository-content dependency.
# ---------------------------------------------------------------------------
function Assert-0502Support {
    param([string]$Phase)
    $lines = Invoke-0502Gate ('verify-support-' + $Phase) $RepoRoot $Python312 @($supportVerifier, '--support', $SupportRoot, '--package', (Join-Path $uiRoot 'package.json'), '--package-lock', (Join-Path $uiRoot 'package-lock.json'))
    $info = ($lines.Lines | Select-Object -Last 1 | ConvertFrom-Json)
    if ($script:SupportManifestSha256) {
        if ([string]$info.supportManifestSha256 -cne $script:SupportManifestSha256 -or [string]$info.supportTreeSha256 -cne $script:SupportTreeSha256) { throw 'support manifest or source tree changed' }
    }
    return $info
}

function New-0502NpmWorkingCache {
    param([string]$SourceCache)
    $evidenceItem = Get-Item -LiteralPath $EvidenceRoot -Force
    if (-not [IO.Path]::IsPathRooted($EvidenceRoot) -or $EvidenceRoot -cne [IO.Path]::GetFullPath($EvidenceRoot) -or ($evidenceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'EvidenceRoot must be an existing canonical non-reparse external directory' }
    $destination = Join-Path $EvidenceRoot 'npm-cache-working'
    if (Test-Path -LiteralPath $destination) {
        $existing = (Resolve-Path -LiteralPath $destination -ErrorAction Stop).Path
        if ($existing -cne $destination -or ((Get-Item -LiteralPath $existing -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'existing npm working cache escapes or redirects' }
        Remove-Item -LiteralPath $existing -Recurse -Force -ErrorAction Stop
    }
    New-Item -ItemType Directory -Path $destination -ErrorAction Stop | Out-Null
    $rootItem = Get-Item -LiteralPath $destination -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or @(Get-ChildItem -LiteralPath $destination -Force).Count -ne 0) { throw 'npm working cache is not a new empty ordinary directory' }
    Get-ChildItem -LiteralPath $SourceCache -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force -ErrorAction Stop }
    $members = @(Get-Item -LiteralPath $destination -Force)
    $members += @(Get-ChildItem -LiteralPath $destination -Force -Recurse)
    if (@($members | Where-Object { (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) }).Count -ne 0) { throw 'npm working cache contains a reparse point' }
    foreach ($member in $members) {
        $attributes = [IO.FileAttributes]$member.Attributes
        [IO.File]::SetAttributes($member.FullName, [IO.FileAttributes](([int]$attributes) -band (-bnot [int][IO.FileAttributes]::ReadOnly)))
    }
    $members = @(Get-Item -LiteralPath $destination -Force)
    $members += @(Get-ChildItem -LiteralPath $destination -Force -Recurse)
    if (@($members | Where-Object { (($_.Attributes -band ([IO.FileAttributes]::ReadOnly -bor [IO.FileAttributes]::ReparsePoint)) -ne 0) }).Count -ne 0) { throw 'npm working cache retains ReadOnly or reparse attributes' }
    return (Resolve-Path -LiteralPath $destination).Path
}

function Get-0502OrdinaryTreeManifest {
    param([string]$Root, [string]$Label)
    $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
    if (-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "$Label root is not an ordinary directory" }
    $prefix = $rootItem.FullName.TrimEnd('\') + '\'
    $entries = [System.Collections.Generic.List[string]]::new()
    foreach ($item in @(Get-ChildItem -LiteralPath $rootItem.FullName -Force -Recurse -ErrorAction Stop)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "$Label contains a reparse point" }
        $relative = $item.FullName.Substring($prefix.Length)
        if ($item.PSIsContainer) { $entries.Add("D`t$relative") }
        else { $entries.Add("F`t$relative`t$($item.Length)`t$(Get-0502Sha256 $item.FullName)") }
    }
    return @($entries.ToArray() | Sort-Object -CaseSensitive)
}

function New-0502ChromiumWorkingCopy {
    param([string]$SourceExecutable)
    $sourceExecutable = (Resolve-Path -LiteralPath $SourceExecutable -ErrorAction Stop).Path
    $sourceRoot = (Resolve-Path -LiteralPath ([IO.Path]::GetDirectoryName($sourceExecutable)) -ErrorAction Stop).Path
    $supportPrefix = $SupportRoot.TrimEnd('\') + '\'
    $sourcePrefix = $sourceRoot.TrimEnd('\') + '\'
    if (-not $sourcePrefix.StartsWith($supportPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'verified Chromium executable is outside SupportRoot' }

    $destination = Join-Path $EvidenceRoot 'chromium-working'
    if (Test-Path -LiteralPath $destination) { throw 'Chromium working copy destination already exists' }
    New-Item -ItemType Directory -Path $destination -ErrorAction Stop | Out-Null
    $destinationItem = Get-Item -LiteralPath $destination -Force
    if (($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or @(Get-ChildItem -LiteralPath $destination -Force).Count -ne 0) { throw 'Chromium working copy is not a new empty ordinary directory' }

    foreach ($child in @(Get-ChildItem -LiteralPath $sourceRoot -Force -ErrorAction Stop)) {
        Copy-Item -LiteralPath $child.FullName -Destination $destination -Recurse -Force -ErrorAction Stop
    }
    $members = @(Get-Item -LiteralPath $destination -Force)
    $members += @(Get-ChildItem -LiteralPath $destination -Force -Recurse -ErrorAction Stop)
    foreach ($member in $members) {
        if (($member.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Chromium working copy contains a reparse point' }
        $attributes = [IO.FileAttributes]$member.Attributes
        [IO.File]::SetAttributes($member.FullName, [IO.FileAttributes](([int]$attributes) -band (-bnot [int][IO.FileAttributes]::ReadOnly)))
    }

    $sourceManifest = @(Get-0502OrdinaryTreeManifest $sourceRoot 'verified Chromium source')
    $copyManifest = @(Get-0502OrdinaryTreeManifest $destination 'Chromium working copy')
    if (@(Compare-Object $sourceManifest $copyManifest -CaseSensitive).Count -ne 0) { throw 'Chromium working copy differs from verified source' }
    $relativeExecutable = $sourceExecutable.Substring($sourcePrefix.Length)
    $workingExecutable = Join-Path $destination $relativeExecutable
    if (-not [IO.File]::Exists($workingExecutable)) { throw 'Chromium executable missing from working copy' }
    Add-0502Result 'chromium-working-copy' $true "exact byte copy at $workingExecutable"
    return (Resolve-Path -LiteralPath $workingExecutable).Path
}

function Invoke-0502NpmPhase {
    param([string]$Name, [string[]]$Arguments)
    Assert-0502Support ('before-' + $Name) | Out-Null
    Invoke-0502Gate $Name $uiRoot $Npm $Arguments
    Assert-0502Support ('after-' + $Name) | Out-Null
}

# ---------------------------------------------------------------------------
# Mechanical nodeid inventory and partition checks.
# ---------------------------------------------------------------------------
function Get-0502NodeIds {
    param([string]$Name, [string]$Python, [string[]]$Paths, [string[]]$Extra)
    # --collect-only -q with addopts cleared emits one "path::nodeid" line per
    # test for every package: the toolkit pyproject forces -q (which double -q
    # turns into per-file counts) and the monitor defaults to a structured tree.
    # Sort is case-sensitive because nodeids are case-sensitive logical ids.
    # A nonzero pytest exit (e.g. collection error) must fail the run closed;
    # partial stdout from a failed collection is never used as inventory.
    $result = Invoke-0502Capture $Name $RepoRoot $Python (@('-m', 'pytest') + $Paths + @('--collect-only', '-q', '-o', 'addopts=', '-p', 'no:cacheprovider') + $Extra)
    if ($result.Exit -ne 0) {
        $script:Failed = $true
        $script:GateResults.Add([ordered]@{ gate = $Name; status = 'FAIL'; exit = $result.Exit; log = $result.Log })
        throw "gate $Name failed with exit $($result.Exit)"
    }
    $lines = $result.Lines
    return @($lines | ForEach-Object { [string]$_ } | Where-Object { $_ -match '^[^=]+::' } | Sort-Object -CaseSensitive)
}

function Assert-0502ExactPartition {
    param([string]$Label, [string[]]$All, [string[]]$Assigned)
    if ($All.Count -eq 0) { throw "$Label collection is empty" }
    if (@($Assigned | Sort-Object -Unique -CaseSensitive).Count -ne $Assigned.Count) { throw "$Label duplicate nodeid" }
    if (@(Compare-Object ($All | Sort-Object -CaseSensitive) ($Assigned | Sort-Object -CaseSensitive) -CaseSensitive).Count -ne 0) { throw "$Label omitted or added nodeid" }
}

# ---------------------------------------------------------------------------
# Complete gate sequence. EvidenceRoot is legal here, so every failure writes
# a summary via the finally block.
# ---------------------------------------------------------------------------
try {
    # --- Git identity binding ------------------------------------------------
    $statusResult = Invoke-0502Capture 'git-status-before' $RepoRoot $Git @('-C', $RepoRoot, 'status', '--porcelain=v1', '--untracked-files=all')
    $statusLines = $statusResult.Lines
    if (@($statusLines | Where-Object { $_ -and $_.Trim() }).Count -ne 0) { Add-0502Result 'git-status-before' $false 'repository is dirty at start' }
    else { Add-0502Result 'git-status-before' $true 'clean' }
    $headResult = Invoke-0502Capture 'git-head' $RepoRoot $Git @('-C', $RepoRoot, 'rev-parse', 'HEAD')
    $headLine = ($headResult.Lines | Select-Object -Last 1)
    $script:ActualHead = [string]$headLine.Trim()
    if ($script:ActualHead -cne $CodeHead) {
        Add-0502Result 'git-head-identity' $false "HEAD $script:ActualHead does not equal CodeHead $CodeHead"
    }
    else { Add-0502Result 'git-head-identity' $true 'HEAD equals CodeHead' }
    Invoke-0502Gate 'git-accepted-ancestor' $RepoRoot $Git @('-C', $RepoRoot, 'merge-base', '--is-ancestor', $AcceptedBase, $CodeHead)
    Invoke-0502Gate 'git-diff-check' $RepoRoot $Git @('-C', $RepoRoot, 'diff', '--check', "$AcceptedBase..$CodeHead")

    $uiRoot = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\ui')).Path
    $monitorRoot = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor')).Path
    $supportVerifier = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\ui\tests\verify_support.py')).Path

    $raw = Invoke-0502GitRaw @('diff', '--name-status', '--no-renames', '-z', "$AcceptedBase..$CodeHead")
    [IO.File]::WriteAllBytes((Join-Path $EvidenceRoot 'git-diff-inventory.raw'), $raw)
    $parts = Split-0502NulBytes $raw
    if (($parts.Count % 2) -ne 0) { throw 'diff inventory is malformed' }
    $seen = @{}
    $inventory = @()
    for ($i = 0; $i -lt $parts.Count; $i += 2) {
        $change = $parts[$i]
        $path = $parts[$i + 1]
        $key = $path.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { throw 'duplicate diff path' }
        $seen[$key] = $true
        $full = Join-Path $RepoRoot $path
        if ($change -eq 'D') { $inventory += [ordered]@{ status = $change; path = $path; bytes = $null; sha256 = $null } }
        else {
            $item = Get-Item -LiteralPath $full
            $inventory += [ordered]@{ status = $change; path = $path; bytes = $item.Length; sha256 = (Get-0502Sha256 $full) }
        }
    }
    $inventory | ConvertTo-Json -Depth 4 | ForEach-Object { [IO.File]::WriteAllText((Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'), $_, [Text.UTF8Encoding]::new($false)) }
    Add-0502Result 'git-diff-inventory' $true "inventory of $($inventory.Count) changed paths written"

    $archiveRoot = Join-Path $EvidenceRoot 'code-head-archive'
    [void][IO.Directory]::CreateDirectory($archiveRoot)
    $archiveGate = Invoke-0502Gate 'git-archive-code-head' $RepoRoot $Git @('-C', $RepoRoot, 'archive', '--format=tar', '--output', (Join-Path $archiveRoot 'code-head.tar'), $CodeHead)
    if (-not [IO.File]::Exists((Join-Path $archiveRoot 'code-head.tar'))) { Add-0502Result 'git-archive-code-head' $false 'archive file missing after git archive' }

    # --- Verified support + npm working cache --------------------------------
    $supportInfo = Assert-0502Support 'before-copy'
    $script:SupportManifestSha256 = [string]$supportInfo.supportManifestSha256
    $script:SupportTreeSha256 = [string]$supportInfo.supportTreeSha256
    $Wheelhouse = [string]$supportInfo.wheelhouse
    $Chromium = [string]$supportInfo.browser
    $auditCache = [bool]$supportInfo.auditCache

    # Node/npm identity: resolved path and SHA-256 must equal the verified
    # support output before any version gate is attempted.
    if ((Resolve-Path -LiteralPath $Node).Path -cne [string]$supportInfo.node -or (Resolve-Path -LiteralPath $Npm).Path -cne [string]$supportInfo.npm) { throw 'Node/npm paths differ from verified support' }
    $nodeHash = Get-0502Sha256 $Node
    $npmHash = Get-0502Sha256 $Npm
    if ($nodeHash -cne [string]$supportInfo.nodeSha256 -or $npmHash -cne [string]$supportInfo.npmSha256) { throw 'Node/npm hashes differ from verified support' }
    $nodeVersionLines = Invoke-0502Gate 'version-node' $RepoRoot $Node @('--version')
    $nodeVersion = ($nodeVersionLines.Lines | Select-Object -Last 1).Trim()
    $npmVersionLines = Invoke-0502Gate 'version-npm' $RepoRoot $Npm @('--version')
    $npmVersion = ($npmVersionLines.Lines | Select-Object -Last 1).Trim()
    if ($nodeVersion -cne [string]$supportInfo.nodeVersion -or $npmVersion -cne [string]$supportInfo.npmVersion) { throw 'Node/npm versions differ from verified support' }

    $npmWorkingCache = New-0502NpmWorkingCache ([string]$supportInfo.npmCache)
    Assert-0502Support 'after-copy' | Out-Null

    Invoke-0502Gate 'verify-changed-scope' $RepoRoot $Python312 @('tools/release/verify_0502_release.py', 'scope', '--repo', $RepoRoot, '--inventory', (Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'))

    $historical = 'requirements/follow-on-skills/stm32-monitor/SKILL.md'
    $baseBlobResult = Invoke-0502Capture 'historical-skill-base' $RepoRoot $Git @('-C', $RepoRoot, 'rev-parse', ($AcceptedBase + ':' + $historical))
    $headBlobResult = Invoke-0502Capture 'historical-skill-head' $RepoRoot $Git @('-C', $RepoRoot, 'rev-parse', ($CodeHead + ':' + $historical))
    $baseBlob = ($baseBlobResult.Lines | Select-Object -Last 1).Trim()
    $headBlob = ($headBlobResult.Lines | Select-Object -Last 1).Trim()
    if ($baseBlob -cne $headBlob) { Add-0502Result 'historical-skill-blob' $false 'historical monitor Skill changed' }
    else { Add-0502Result 'historical-skill-blob' $true $baseBlob }

    $py310Lines = Invoke-0502Gate 'version-python310' $RepoRoot $Python310 @('-c', 'import json,sys;print(json.dumps([sys.version_info[0],sys.version_info[1],sys.executable]))')
    $py310 = ($py310Lines.Lines | Select-Object -Last 1 | ConvertFrom-Json)
    $py312Lines = Invoke-0502Gate 'version-python312' $RepoRoot $Python312 @('-c', 'import json,sys;print(json.dumps([sys.version_info[0],sys.version_info[1],sys.executable]))')
    $py312 = ($py312Lines.Lines | Select-Object -Last 1 | ConvertFrom-Json)
    if ([int]$py310[0] -ne 3 -or [int]$py310[1] -ne 10 -or [int]$py312[0] -ne 3 -or [int]$py312[1] -ne 12) { throw 'Python version alias detected' }
    if ([string]$py310[2] -ceq [string]$py312[2]) { throw 'Python 3.10 and 3.12 alias to the same interpreter' }

    # --- Node gates, offline against the working cache only -------------------
    $env:npm_config_cache = $npmWorkingCache
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONPYCACHEPREFIX = Join-Path $EvidenceRoot 'pycache'

    Invoke-0502NpmPhase 'node-npm-ci' @('ci', '--offline', '--cache', $npmWorkingCache)
    Invoke-0502Gate 'node-typecheck' $uiRoot $Npm @('run', 'typecheck')
    Invoke-0502Gate 'node-typecheck-e2e' $uiRoot $Npm @('run', 'typecheck:e2e')
    Invoke-0502Gate 'node-lint' $uiRoot $Npm @('run', 'lint')
    Invoke-0502Gate 'node-unit-coverage' $uiRoot $Npm @('run', 'test:coverage')
    Invoke-0502Gate 'node-coverage-gate' $uiRoot $Npm @('run', 'coverage:check')
    Invoke-0502Gate 'node-a11y' $uiRoot $Npm @('run', 'test:a11y')
    Invoke-0502Gate 'node-build' $uiRoot $Npm @('run', 'build')
    Invoke-0502Gate 'node-verify-dist-1' $uiRoot $Npm @('run', 'verify:dist')
    Invoke-0502Gate 'node-verify-dist-2' $uiRoot $Npm @('run', 'verify:dist')
    if (-not $auditCache) { throw 'BLOCKED: verified support has no compatible npm advisory cache' }
    Invoke-0502NpmPhase 'node-production-audit' @('audit', '--offline', '--cache', $npmWorkingCache, '--omit=dev', '--audit-level=high')

    # --- Fresh test venvs and exact offline dependency install ---------------
    $supportWheelhouse = [string]$supportInfo.wheelhouse
    $requirements = @($supportInfo.pythonRequirements | ForEach-Object { [string]$_ })
    $sourcePath = (Join-Path $RepoRoot 'tools\stm32-monitor\src') + ';' + (Join-Path $RepoRoot 'tools\stm32-toolkit\src')
    $testPythons = @{}
    foreach ($entry in @(@('310', $Python310), @('312', $Python312))) {
        $minor = [string]$entry[0]
        $base = [string]$entry[1]
        $venv = Join-Path $EvidenceRoot ('test-' + $minor)
        Invoke-0502Gate ('venv-create-' + $minor) $EvidenceRoot $base @('-m', 'venv', $venv)
        $testPython = (Resolve-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe')).Path
        Invoke-0502Gate ('venv-install-' + $minor) $EvidenceRoot $testPython (@('-m', 'pip', 'install', '--no-index', '--find-links', $supportWheelhouse) + $requirements)
        # The package_boundary tests spawn isolated (-I) python that cannot see
        # PYTHONPATH, so the project's own stm32_toolkit package must be present
        # in the venv site-packages. Build it from source, offline, without
        # dependency resolution (all deps were installed by the requirements).
        Invoke-0502Gate ('venv-install-toolkit-' + $minor) $EvidenceRoot $testPython @('-m', 'pip', 'install', '--no-index', '--find-links', $supportWheelhouse, '--no-deps', (Join-Path $RepoRoot 'tools\stm32-toolkit'))
        $testPythons[$minor] = $testPython
    }
    $testPython310 = [string]$testPythons['310']
    $testPython312 = [string]$testPythons['312']
    $env:PYTHONPATH = $sourcePath

    # --- Monitor inventories, partitions, and coverage ------------------------
    # The accepted 0501 performance acceptance runs without coverage
    # instrumentation (its ACCEPTANCE_COMMAND is a plain pytest invocation).
    # Coverage adds ~2-3x overhead that breaks the timing thresholds, so the
    # performance tests run in their own no-coverage gate on CPython 3.12.
    $special = @(
        'tools/stm32-monitor/tests/test_auth.py',
        'tools/stm32-monitor/tests/test_service.py',
        'tools/stm32-monitor/tests/test_ui_assets.py',
        'tools/stm32-monitor/tests/test_ui_dist.py',
        'tools/stm32-monitor/tests/test_package_boundary.py',
        'tools/stm32-monitor/tests/test_performance.py'
    )
    $specialCore = @(
        'tools/stm32-monitor/tests/test_auth.py',
        'tools/stm32-monitor/tests/test_service.py',
        'tools/stm32-monitor/tests/test_ui_assets.py',
        'tools/stm32-monitor/tests/test_ui_dist.py',
        'tools/stm32-monitor/tests/test_package_boundary.py'
    )
    $perfOnly = @('tools/stm32-monitor/tests/test_performance.py')
    $ignore = @($special | ForEach-Object { '--ignore=' + $_ })
    $monitorAll310 = Get-0502NodeIds 'collect-monitor-310' $testPython310 @('tools/stm32-monitor/tests') @()
    $monitorAll312 = Get-0502NodeIds 'collect-monitor-312' $testPython312 @('tools/stm32-monitor/tests') @()
    if (@(Compare-Object -CaseSensitive $monitorAll310 $monitorAll312).Count -ne 0) { throw 'Monitor version inventories differ' }
    $monitorMain = Get-0502NodeIds 'collect-monitor-main-312' $testPython312 @('tools/stm32-monitor/tests') $ignore
    $monitorSpecial = Get-0502NodeIds 'collect-monitor-special-312' $testPython312 $specialCore @()
    $monitorPerf = Get-0502NodeIds 'collect-monitor-perf-312' $testPython312 $perfOnly @()
    $perfMonitorMatches = @($monitorPerf | Where-Object { $_ -cmatch '(^|[\\/])test_performance\.py::test_named_monitor_performance_acceptance$' })
    $perfExportMatches = @($monitorPerf | Where-Object { $_ -cmatch '(^|[\\/])test_performance\.py::test_named_export_performance_acceptance$' })
    if ($monitorPerf.Count -ne 2 -or $perfMonitorMatches.Count -ne 1 -or $perfExportMatches.Count -ne 1) { throw 'Monitor performance inventory does not match the two named acceptance tests' }
    $perfMonitorNode = [string]$perfMonitorMatches[0]
    $perfExportNode = [string]$perfExportMatches[0]
    Assert-0502ExactPartition 'Monitor 3.12' $monitorAll312 @($monitorMain + $monitorSpecial + $monitorPerf)

    # CPython 3.10 runs the complete correctness suite but excludes
    # test_performance.py: the accepted 0501 performance thresholds were
    # calibrated on CPython 3.12 (see the test's ACCEPTANCE_COMMAND). The 3.12
    # performance gate runs FIRST, before the heavy correctness partitions, so
    # the acceptance measurement is taken on an unloaded machine exactly as the
    # original 0501 gate was calibrated.
    Invoke-0502Gate 'python312-monitor-perf-monitor' $monitorRoot $testPython312 @('-m', 'pytest', $perfMonitorNode, '-q', '-s', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'bt-monitor-perf-monitor-312'))
    Invoke-0502Gate 'python312-monitor-perf-export' $monitorRoot $testPython312 @('-m', 'pytest', $perfExportNode, '-q', '-s', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'bt-monitor-perf-export-312'))
    Invoke-0502Gate 'python310-monitor-complete' $RepoRoot $testPython310 @('-m', 'pytest', 'tools/stm32-monitor/tests', '--ignore=tools/stm32-monitor/tests/test_performance.py', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'bt-monitor-310'))
    $env:COVERAGE_FILE = Join-Path $EvidenceRoot '.coverage-monitor-312'
    Invoke-0502Gate 'python312-monitor-main' $RepoRoot $testPython312 (@('-m', 'pytest', 'tools/stm32-monitor/tests') + $ignore + @('-q', '-p', 'no:cacheprovider', '--cov=stm32_monitor', '--cov-branch', '--cov-report=', '--basetemp', (Join-Path $EvidenceRoot 'bt-monitor-main-312')))
    Invoke-0502Gate 'python312-monitor-special' $RepoRoot $testPython312 (@('-m', 'pytest') + $specialCore + @('-q', '-s', '-p', 'no:cacheprovider', '--cov=stm32_monitor', '--cov-branch', '--cov-append', '--cov-report=', '--basetemp', (Join-Path $EvidenceRoot 'bt-monitor-special-312')))

    # --- Toolkit sharded coverage ---------------------------------------------
    $toolkitContractFiles = @('tools/stm32-toolkit/tests/test_0502_release_gate_controller.py')
    $allToolkitFiles = @(Get-ChildItem -LiteralPath (Join-Path $RepoRoot 'tools\stm32-toolkit\tests') -Filter 'test_*.py' -File | ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1).Replace('\', '/') } | Sort-Object)
    if (@(Compare-Object $toolkitContractFiles @($allToolkitFiles | Where-Object { $toolkitContractFiles -contains $_ })).Count -ne 0) { throw 'Toolkit controller contract inventory is missing' }
    $toolkitFiles = @($allToolkitFiles | Where-Object { $toolkitContractFiles -notcontains $_ })
    $env:COVERAGE_FILE = Join-Path $EvidenceRoot '.coverage-toolkit-312'
    $toolkitAll = Get-0502NodeIds 'collect-toolkit-312' $testPython312 @('tools/stm32-toolkit/tests') @()
    # The controller contract launches thousands of recording subprocesses.
    # Run it as a mandatory correctness gate outside pytest-cov so those
    # non-product recorder processes cannot inherit subprocess coverage. The
    # Toolkit product suite below remains fully branch-instrumented.
    $contractIds = Get-0502NodeIds 'collect-toolkit-controller-contract' $testPython312 $toolkitContractFiles @()
    Invoke-0502Gate 'python312-toolkit-controller-contract' $RepoRoot $testPython312 (@('-m', 'pytest') + $toolkitContractFiles + @('-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'bt-toolkit-controller-contract')))
    $assigned = @($contractIds)
    for ($shard = 0; $shard -lt 8; $shard++) {
        $files = @()
        for ($index = $shard; $index -lt $toolkitFiles.Count; $index += 8) { $files += $toolkitFiles[$index] }
        if ($files.Count) {
            $ids = Get-0502NodeIds ('collect-toolkit-shard-' + ($shard + 1)) $testPython312 $files @()
            $assigned += $ids
            Invoke-0502Gate ('python312-toolkit-shard-' + ($shard + 1)) $RepoRoot $testPython312 (@('-m', 'pytest') + $files + @('-q', '-p', 'no:cacheprovider', '--cov=stm32_toolkit', '--cov-branch', '--cov-append', '--cov-report=', '--basetemp', (Join-Path $EvidenceRoot ('bt-toolkit-' + ($shard + 1)))))
        }
    }
    Assert-0502ExactPartition 'Toolkit 3.12' $toolkitAll $assigned

    $env:COVERAGE_FILE = Join-Path $EvidenceRoot '.coverage-monitor-312'
    Invoke-0502Gate 'python312-monitor-coverage-json' $RepoRoot $testPython312 @('-m', 'coverage', 'json', '-o', (Join-Path $EvidenceRoot 'monitor-coverage.json'))
    $env:COVERAGE_FILE = Join-Path $EvidenceRoot '.coverage-toolkit-312'
    Invoke-0502Gate 'python312-toolkit-coverage-json' $RepoRoot $testPython312 @('-m', 'coverage', 'json', '-o', (Join-Path $EvidenceRoot 'toolkit-coverage.json'))
    Invoke-0502Gate 'changed-product-branch-coverage' $RepoRoot $testPython312 @('tools/release/verify_0502_release.py', 'coverage', '--repo', $RepoRoot, '--inventory', (Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'), '--coverage', (Join-Path $EvidenceRoot 'monitor-coverage.json'), '--coverage', (Join-Path $EvidenceRoot 'toolkit-coverage.json'))

    Invoke-0502Gate 'compileall-310' $RepoRoot $testPython310 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')
    Invoke-0502Gate 'compileall-312' $RepoRoot $testPython312 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')

    # --- Clean-source offline wheels -------------------------------------------
    $packageRoot = Join-Path $EvidenceRoot 'packages'
    $wheels = Join-Path $packageRoot 'wheels'
    New-Item -ItemType Directory -Force -Path $wheels | Out-Null
    Invoke-0502Gate 'wheel-toolkit' $RepoRoot $testPython312 @('-m', 'pip', 'wheel', '--no-index', '--find-links', $supportWheelhouse, '--no-deps', '--no-build-isolation', '--wheel-dir', $wheels, 'tools/stm32-toolkit')
    Invoke-0502Gate 'wheel-monitor' $RepoRoot $testPython312 @('-m', 'pip', 'wheel', '--no-index', '--find-links', $supportWheelhouse, '--no-deps', '--no-build-isolation', '--wheel-dir', $wheels, 'tools/stm32-monitor')
    $wheelNames = @(Get-ChildItem -LiteralPath $wheels -Filter '*.whl' -File | ForEach-Object { $_.Name } | Sort-Object)
    if (@(Compare-Object $wheelNames @('stm32_monitor-0.5.0-py3-none-any.whl', 'stm32_toolkit-0.5.0-py3-none-any.whl')).Count -ne 0) { throw 'wheel inventory is not exact' }
    # Inline -c code is unreliable through Windows PowerShell native argument
    # passing, so the wheel hash script is written to a file and executed.
    $hashScriptPath = Join-Path $EvidenceRoot 'wheel-hashes.py'
    $hashScriptBody = @"
import hashlib,glob,json,os
print(json.dumps({os.path.basename(p):{'bytes':os.path.getsize(p),'sha256':hashlib.sha256(open(p,'rb').read()).hexdigest()} for p in glob.glob('*.whl')},sort_keys=True))
"@
    [IO.File]::WriteAllText($hashScriptPath, $hashScriptBody, [Text.UTF8Encoding]::new($false))
    $hashLines = Invoke-0502Gate 'wheel-hashes' $wheels $testPython312 @($hashScriptPath)
    $wheelHashes = ($hashLines.Lines | Select-Object -Last 1 | ConvertFrom-Json)
    $wheelHashes | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceRoot 'wheel-hashes.json')

    # --- Installed copies and managed CMD launchers -----------------------------
    $savedPythonPath = $env:PYTHONPATH
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    try {
        foreach ($minor in @('310', '312')) {
            $base = if ($minor -eq '310') { $Python310 } else { $Python312 }
            $pluginData = Join-Path $EvidenceRoot ('installed-' + $minor)
            $runtime = Join-Path $pluginData 'runtime\0.5.0'
            Invoke-0502Gate ('installed-venv-' + $minor) $EvidenceRoot $base @('-m', 'venv', $runtime)
            $installedPython = (Resolve-Path -LiteralPath (Join-Path $runtime 'Scripts\python.exe')).Path
            Invoke-0502Gate ('installed-packages-' + $minor) $EvidenceRoot $installedPython @('-m', 'pip', 'install', '--no-index', '--find-links', $supportWheelhouse, (Join-Path $wheels 'stm32_toolkit-0.5.0-py3-none-any.whl'), (Join-Path $wheels 'stm32_monitor-0.5.0-py3-none-any.whl'), 'pyocd')
            Invoke-0502Gate ('installed-pip-check-' + $minor) $EvidenceRoot $installedPython @('-m', 'pip', 'check')
            # Version + import-path + ui_dist verification. Single-quoted inline
            # code only (Windows PowerShell 5.1 mangles embedded double quotes).
            $smoke = "import importlib.metadata as m,pathlib,sys;import stm32_monitor,stm32_toolkit;from stm32_monitor.ui_assets import UiAssets;assert m.version('stm32-toolkit')==m.version('stm32-monitor')=='0.5.0';assert pathlib.Path(stm32_monitor.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve());assert UiAssets.load() is not None"
            Invoke-0502Gate ('installed-smoke-' + $minor) $EvidenceRoot $installedPython @('-I', '-c', $smoke)
            # Real HTTP smoke against the installed monitor service: public
            # homepage 200 + bound-port CSP, unknown asset 404, unauth API reject.
            $httpScript = Join-Path $EvidenceRoot ('installed-http-' + $minor + '.py')
            $httpBody = @"
import asyncio
import aiohttp
from urllib.parse import urlsplit
from stm32_monitor.service import MonitorService

class _Runtime:
    async def dispatch(self, operation, payload, *, resource_id=None, query=None):
        return {'operation': operation, 'workspaceId': 'workspace-a'}
    def record_service_drops(self, count):
        return None
    async def live_subscribe(self, *, after_event_id=None):
        if False:
            yield {}

def require_exact_connect_src(csp, port):
    expected = 'ws://127.0.0.1:' + str(port)
    found = False
    for directive in csp.split(';'):
        directive = directive.strip()
        if not directive:
            continue
        parts = directive.split(None, 1)
        name = parts[0].lower()
        if name != 'connect-src':
            continue
        tokens = parts[1].split() if len(parts) > 1 else []
        if expected in tokens:
            found = True
        for token in tokens:
            if (
                token == '*'
                or token in ('ws:', 'wss:', 'ws://*', 'wss://*')
                or token.endswith(':*')
            ):
                raise AssertionError('loose connect-src token: ' + token)
    if not found:
        raise AssertionError('exact ws origin missing from connect-src: ' + expected)

async def main():
    service = MonitorService(_Runtime(), workspace_id='w', session_id='s', serve_ui=True)
    endpoint = await service.start()
    try:
        async with aiohttp.ClientSession() as client:
            async with client.get(endpoint.url + '/') as resp:
                assert resp.status == 200, resp.status
                body = await resp.text()
                assert '<!doctype' in body.lower() or '<html' in body.lower(), 'homepage is not html'
                csp = resp.headers.get('Content-Security-Policy', '')
                port = urlsplit(endpoint.url).port
                assert port is not None, 'endpoint has no bound port'
                require_exact_connect_src(csp, port)
            async with client.get(endpoint.url + '/assets/nope.js') as resp:
                assert resp.status == 404, resp.status
            async with client.get(endpoint.url + '/api/v1/status') as resp:
                assert resp.status in (401, 403), resp.status
    finally:
        await service.stop()

asyncio.run(main())
"@
            [IO.File]::WriteAllText($httpScript, $httpBody, [Text.UTF8Encoding]::new($false))
            Invoke-0502Gate ('installed-http-' + $minor) $EvidenceRoot $installedPython @('-I', $httpScript)
            $env:CLAUDE_PLUGIN_ROOT = $RepoRoot
            $env:CLAUDE_PLUGIN_DATA = $pluginData
            Invoke-0502Gate ('launcher-monitor-' + $minor) $RepoRoot $CmdExe @('/d', '/c', (Join-Path $RepoRoot 'bin\stm32-monitor.cmd'), '--help')
            Invoke-0502Gate ('launcher-toolkit-' + $minor) $RepoRoot $CmdExe @('/d', '/c', (Join-Path $RepoRoot 'bin\stm32-toolkit-mcp.cmd'), '--help')
        }
    }
    finally {
        Remove-Item Env:CLAUDE_PLUGIN_ROOT -ErrorAction SilentlyContinue
        Remove-Item Env:CLAUDE_PLUGIN_DATA -ErrorAction SilentlyContinue
        if ($null -ne $savedPythonPath) { $env:PYTHONPATH = $savedPythonPath } else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    }

    # Fail-closed launcher behavior (missing env / missing runtime -> exit 2).
    $missingEnvMon = Invoke-0502Capture 'launcher-missing-env-monitor' $RepoRoot $CmdExe @('/d', '/c', (Join-Path $RepoRoot 'bin\stm32-monitor.cmd'), '--help')
    $missingEnvTk = Invoke-0502Capture 'launcher-missing-env-toolkit' $RepoRoot $CmdExe @('/d', '/c', (Join-Path $RepoRoot 'bin\stm32-toolkit-mcp.cmd'), '--help')
    if ($missingEnvMon.Exit -eq 2 -and $missingEnvTk.Exit -eq 2) { Add-0502Result 'launcher-fail-closed-missing-env' $true 'both launchers exit 2 without CLAUDE_PLUGIN_DATA' }
    else { Add-0502Result 'launcher-fail-closed-missing-env' $false "expected exit 2, got $($missingEnvMon.Exit)/$($missingEnvTk.Exit)" }
    $emptyPluginData = Join-Path $EvidenceRoot 'empty-plugin-data'
    New-Item -ItemType Directory -Force -Path $emptyPluginData | Out-Null
    $env:CLAUDE_PLUGIN_DATA = $emptyPluginData
    $missingRuntimeMon = Invoke-0502Capture 'launcher-missing-runtime-monitor' $RepoRoot $CmdExe @('/d', '/c', (Join-Path $RepoRoot 'bin\stm32-monitor.cmd'), '--help')
    $missingRuntimeTk = Invoke-0502Capture 'launcher-missing-runtime-toolkit' $RepoRoot $CmdExe @('/d', '/c', (Join-Path $RepoRoot 'bin\stm32-toolkit-mcp.cmd'), '--help')
    Remove-Item Env:CLAUDE_PLUGIN_DATA -ErrorAction SilentlyContinue
    if ($missingRuntimeMon.Exit -eq 2 -and $missingRuntimeTk.Exit -eq 2) { Add-0502Result 'launcher-fail-closed-missing-runtime' $true 'both launchers exit 2 without the versioned runtime' }
    else { Add-0502Result 'launcher-fail-closed-missing-runtime' $false "expected exit 2, got $($missingRuntimeMon.Exit)/$($missingRuntimeTk.Exit)" }

    # --- Controlled Playwright --------------------------------------------------
    Assert-0502Support 'before-chromium-copy' | Out-Null
    $ChromiumWorking = New-0502ChromiumWorkingCopy $Chromium
    # Re-verify the authoritative source after copying and before executing the
    # working copy.  This closes the interval in which SupportRoot could change
    # after the pre-copy verification while still producing a self-consistent
    # (but no longer verified) copy.
    Assert-0502Support 'after-chromium-copy' | Out-Null
    $env:STM32_MONITOR_PYTHON = $testPython312
    $env:STM32_MONITOR_EVIDENCE = $EvidenceRoot
    $env:PLAYWRIGHT_BROWSERS_PATH = '0'
    $env:STM32_MONITOR_CHROMIUM_EXECUTABLE = $ChromiumWorking
    Remove-Item Env:STM32_MONITOR_PERF_WARMUP_MS -ErrorAction SilentlyContinue
    Remove-Item Env:STM32_MONITOR_PERF_MEASURE_MS -ErrorAction SilentlyContinue
    $functionalSpecs = @(Get-ChildItem -LiteralPath (Join-Path $uiRoot 'e2e') -Filter '*.spec.ts' -File | ForEach-Object { $_.Name } | Where-Object { $_ -cne 'performance.spec.ts' } | Sort-Object)
    Invoke-0502Gate 'playwright-functional' $uiRoot $Npm (@('exec', '--', 'playwright', 'test') + $functionalSpecs + @('--project=chromium-1280', '--project=chromium-1024', '--workers=1'))
    Invoke-0502Gate 'playwright-performance' $uiRoot $Npm @('exec', '--', 'playwright', 'test', 'performance.spec.ts', '--project=chromium-1280', '--workers=1')
    Remove-Item Env:STM32_MONITOR_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:STM32_MONITOR_EVIDENCE -ErrorAction SilentlyContinue
    Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:STM32_MONITOR_CHROMIUM_EXECUTABLE -ErrorAction SilentlyContinue

    $perfJson = Join-Path $EvidenceRoot '.performance-evidence\performance.json'
    if (-not [IO.File]::Exists($perfJson)) { Add-0502Result 'playwright-performance-evidence' $false 'performance.json missing from EvidenceRoot' }
    else {
        $perf = Get-Content -Raw -LiteralPath $perfJson | ConvertFrom-Json
        $need = @('updateP95Ms', 'realizedPoints', 'longTasksAtLeast200Ms', 'queueGrowth', 'heapSlopeMiBPerMinute')
        $missing = @($need | Where-Object { $null -eq $perf.$_ })
        if ($missing.Count -ne 0) { Add-0502Result 'playwright-performance-evidence' $false "performance.json missing fields: $($missing -join ',')" }
        elseif ([int]$perf.realizedPoints -ne 4800 -or [double]$perf.updateP95Ms -gt 150 -or [int]$perf.longTasksAtLeast200Ms -ne 0 -or [double]$perf.queueGrowth -gt 0 -or [double]$perf.heapSlopeMiBPerMinute -gt 2) { Add-0502Result 'playwright-performance-evidence' $false 'performance thresholds not met' }
        else { Add-0502Result 'playwright-performance-evidence' $true 'performance.json validated' }
    }

    # --- Final closure -----------------------------------------------------------
    Invoke-0502Gate 'release-static-closure' $RepoRoot $testPython312 @('tools/release/verify_0502_release.py', 'static', '--repo', $RepoRoot, '--inventory', (Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'))

    $trackedRaw = Invoke-0502GitRaw @('ls-files', '-z')
    $tracked = Split-0502NulBytes $trackedRaw
    $trackedManifest = @()
    foreach ($path in $tracked) {
        $file = Join-Path $RepoRoot $path
        $trackedManifest += [ordered]@{ path = $path; bytes = (Get-Item -LiteralPath $file).Length; sha256 = (Get-0502Sha256 $file) }
    }
    $trackedManifest | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceRoot 'tracked-byte-manifest.json')
    Add-0502Result 'tracked-byte-manifest' $true "$($trackedManifest.Count) tracked files hashed"

    Invoke-0502Gate 'git-diff-check-after' $RepoRoot $Git @('-C', $RepoRoot, 'diff', '--check', "$AcceptedBase..$CodeHead")
    Assert-0502Support 'final' | Out-Null
    $finalResult = Invoke-0502Capture 'git-status-after' $RepoRoot $Git @('-C', $RepoRoot, 'status', '--porcelain=v1', '--untracked-files=all')
    $finalLines = $finalResult.Lines
    if (@($finalLines | Where-Object { $_ -and $_.Trim() }).Count -ne 0) { Add-0502Result 'clean-tree' $false 'repository changed during gates' }
    else { Add-0502Result 'clean-tree' $true 'clean' }
}
catch {
    if (-not $script:Failed) {
        $script:GateResults.Add([ordered]@{ gate = 'controller'; status = 'FAIL'; detail = $_.Exception.Message })
    }
    $script:Failed = $true
    $script:FirstError = $_.Exception.Message
}
finally {
    Write-0502Summary
}

if ($script:Failed) { throw "one or more 0502 gates FAILED: $script:FirstError" }
