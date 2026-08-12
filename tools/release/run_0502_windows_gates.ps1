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

function Invoke-0502Capture {
    param([string]$Name, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments)
    $log = Join-Path $EvidenceRoot ($Name + '.log')
    Push-Location -LiteralPath $WorkingDirectory
    try {
        $lines = @(& $Executable @Arguments 2>&1)
        $exit = $LASTEXITCODE
    }
    finally { Pop-Location }
    $lines | Set-Content -Encoding UTF8 -LiteralPath $log
    return @{ Name = $Name; Exit = $exit; Log = $log; Lines = $lines }
}

function Invoke-0502Gate {
    param([string]$Name, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments)
    $result = Invoke-0502Capture $Name $WorkingDirectory $Executable $Arguments
    $ok = ($result.Exit -eq 0)
    if (-not $ok) { $script:Failed = $true }
    $script:GateResults.Add([ordered]@{ gate = $Name; status = if ($ok) { 'PASS' } else { 'FAIL' }; exit = $result.Exit; log = $result.Log })
    if (-not $ok) { throw "$Name failed with exit $($result.Exit) (see $($result.Log))" }
    return $result
}

function Invoke-0502Recorded {
    # Record a gate that could not be executed (explicit SKIP, never PASS).
    param([string]$Name, [string]$Reason)
    $script:GateResults.Add([ordered]@{ gate = $Name; status = 'SKIP'; exit = $null; reason = $Reason })
    $script:Failed = $true
}

# Fail fast if the accepted base or code head is not a descendant chain.
Invoke-0502Capture 'git-verify-base' $RepoRoot $Git @('cat-file', '-e', "$AcceptedBase^{commit}") | Out-Null
Invoke-0502Capture 'git-verify-head' $RepoRoot $Git @('merge-base', '--is-ancestor', $AcceptedBase, $CodeHead) | Out-Null
$inventory = Invoke-0502Capture 'git-diff-inventory' $RepoRoot $Git @('diff', '--name-status', '--no-renames', "$AcceptedBase..$CodeHead")
if (@($inventory.Lines).Count -eq 0) { throw 'accepted-base..code-head diff inventory is empty' }
Invoke-0502Gate 'git-diff-check' $RepoRoot $Git @('diff', '--check', "$AcceptedBase..$CodeHead")

$uiRoot = Join-Path $RepoRoot 'tools\stm32-monitor\ui'

# Node gates.
Invoke-0502Gate 'node-npm-ci' $uiRoot $Npm @('ci')
Invoke-0502Gate 'node-typecheck' $uiRoot $Npm @('run', 'typecheck')
Invoke-0502Gate 'node-typecheck-e2e' $uiRoot $Npm @('run', 'typecheck:e2e')
Invoke-0502Gate 'node-lint' $uiRoot $Npm @('run', 'lint')
Invoke-0502Gate 'node-test' $uiRoot $Npm @('run', 'test')
Invoke-0502Gate 'node-a11y' $uiRoot $Npm @('run', 'test:a11y')
Invoke-0502Gate 'node-coverage' $uiRoot $Npm @('exec', 'vitest', 'run', '--coverage')
Invoke-0502Gate 'node-coverage-gate' $uiRoot $Node @('tests/check-coverage.mjs')
Invoke-0502Gate 'node-build' $uiRoot $Npm @('run', 'build')
Invoke-0502Gate 'node-verify-dist' $uiRoot $Npm @('run', 'verify:dist')

# Playwright functional and performance gates (Chromium 1280 x 1024).
Invoke-0502Gate 'playwright-functional' $uiRoot $Npm @('exec', '--', 'playwright', 'test', '--project=chromium-1280', '--project=chromium-1024', '--workers=1')
Invoke-0502Gate 'playwright-performance' $uiRoot $Npm @('exec', '--', 'playwright', 'test', 'e2e/performance.spec.ts', '--project=chromium-1280', '--workers=1')

# Python monitor suites on 3.10 and 3.12.
Invoke-0502Gate 'python310-monitor' $RepoRoot $Python310 @('-m', 'pytest', 'tools/stm32-monitor/tests', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py310-monitor'))
Invoke-0502Gate 'python312-monitor' $RepoRoot $Python312 @('-m', 'pytest', 'tools/stm32-monitor/tests', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py312-monitor'))
Invoke-0502Gate 'python312-toolkit' $RepoRoot $Python312 @('-m', 'pytest', 'tools/stm32-toolkit/tests', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py312-toolkit'))

# Byte-compile both source trees on both interpreters.
Invoke-0502Gate 'compileall-310' $RepoRoot $Python310 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')
Invoke-0502Gate 'compileall-312' $RepoRoot $Python312 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')

# Wheel build for both distributions.
$wheelRoot = Join-Path $EvidenceRoot 'wheels'
[void][IO.Directory]::CreateDirectory($wheelRoot)
Invoke-0502Gate 'wheel-toolkit' $RepoRoot $Python312 @('-m', 'build', '--wheel', '--outdir', $wheelRoot, 'tools/stm32-toolkit')
Invoke-0502Gate 'wheel-monitor' $RepoRoot $Python312 @('-m', 'build', '--wheel', '--outdir', $wheelRoot, 'tools/stm32-monitor')
$wheelHashes = Invoke-0502Capture 'wheel-hashes' $wheelRoot $CmdExe @('/d', '/c', 'for %f in (*.whl) do @certutil -hashfile "%f" SHA256 | findstr /v "hash"')
if (@($wheelHashes.Lines | Where-Object { $_ }).Count -lt 2) { $script:Failed = $true; $script:GateResults.Add([ordered]@{ gate = 'wheel-hashes'; status = 'FAIL'; exit = $wheelHashes.Exit; log = $wheelHashes.Log }) }

# Managed-runtime launcher: fail closed without an ambient interpreter.
$launcherResult = Invoke-0502Capture 'launcher-fail-closed' $RepoRoot $CmdExe @('/d', '/c', 'bin\stm32-monitor.cmd', '--help')
if ($launcherResult.Exit -eq 0) {
    $script:Failed = $true
    $script:GateResults.Add([ordered]@{ gate = 'launcher-fail-closed'; status = 'FAIL'; exit = 0; reason = 'launcher did not fail closed without CLAUDE_PLUGIN_DATA' })
} else {
    $script:GateResults.Add([ordered]@{ gate = 'launcher-fail-closed'; status = 'PASS'; exit = $launcherResult.Exit; log = $launcherResult.Log })
}

# Exact CODE_HEAD installed-copy archive: the evidence bundle is keyed to the committed head.
Invoke-0502Capture 'git-code-head' $RepoRoot $Git @('rev-parse', 'HEAD') | Out-Null

# Final clean-tree verification.
$status = @(Invoke-0502Capture 'git-final-status' $RepoRoot $Git @('status', '--porcelain=v1', '--untracked-files=all'))
$dirty = @($status.Lines | Where-Object { $_ -and $_.Trim() })
if ($dirty.Count -ne 0) {
    $script:Failed = $true
    $script:GateResults.Add([ordered]@{ gate = 'clean-tree'; status = 'FAIL'; exit = $null; reason = 'gate run left the repository dirty' })
} else {
    $script:GateResults.Add([ordered]@{ gate = 'clean-tree'; status = 'PASS'; exit = 0 })
}

$summary = @{
    acceptedBase = $AcceptedBase
    codeHead = $CodeHead
    gates = @($script:GateResults)
    overall = if ($script:Failed) { 'FAIL' } else { 'PASS' }
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceRoot 'summary.json')
if ($script:Failed) { throw 'one or more 0502 gates FAILED or were SKIPPED; see EvidenceRoot' }
