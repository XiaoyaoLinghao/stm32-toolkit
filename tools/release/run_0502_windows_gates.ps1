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
    if ($exit -ne 0) { throw "$Name failed with exit $exit (see $log)" }
    return $lines
}

function Invoke-0502Gate {
    param([string]$Name, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments)
    [void](Invoke-0502Capture $Name $WorkingDirectory $Executable $Arguments)
}

# Fail fast if the accepted base or code head is not a descendant chain in this repo.
Invoke-0502Capture 'git-verify-base' $RepoRoot $Git @('cat-file', '-e', "$AcceptedBase^{commit}")
Invoke-0502Capture 'git-verify-head' $RepoRoot $Git @('merge-base', '--is-ancestor', $AcceptedBase, $CodeHead)

# Mechanical no-renames diff inventory from the accepted base to the code head.
$inventory = Invoke-0502Capture 'git-diff-inventory' $RepoRoot $Git @('diff', '--name-status', '--no-renames', "$AcceptedBase..$CodeHead")
if (@($inventory).Count -eq 0) { throw 'accepted-base..code-head diff inventory is empty' }

# Whitespace gate across the complete accepted-base..code-head diff.
Invoke-0502Capture 'git-diff-check' $RepoRoot $Git @('diff', '--check', "$AcceptedBase..$CodeHead")

$uiRoot = Join-Path $RepoRoot 'tools\stm32-monitor\ui'

# Node gates from the committed ui package.
Invoke-0502Gate 'node-typecheck' $uiRoot $Npm @('run', 'typecheck')
Invoke-0502Gate 'node-typecheck-e2e' $uiRoot $Npm @('run', 'typecheck:e2e')
Invoke-0502Gate 'node-lint' $uiRoot $Npm @('run', 'lint')
Invoke-0502Gate 'node-test' $uiRoot $Npm @('run', 'test')
Invoke-0502Gate 'node-a11y' $uiRoot $Npm @('run', 'test:a11y')
Invoke-0502Gate 'node-build' $uiRoot $Npm @('run', 'build')
Invoke-0502Gate 'node-verify-dist' $uiRoot $Npm @('run', 'verify:dist')

# Python 3.10 and 3.12 Monitor suites.
$monitor310 = Invoke-0502Capture 'python310-monitor-tests' $RepoRoot $Python310 @('-m', 'pytest', 'tools/stm32-monitor/tests', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py310-basetemp'))
$monitor312 = Invoke-0502Capture 'python312-monitor-tests' $RepoRoot $Python312 @('-m', 'pytest', 'tools/stm32-monitor/tests', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py312-basetemp'))

# Python byte-compilation for both interpreters.
Invoke-0502Capture 'compileall-310' $RepoRoot $Python310 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')
Invoke-0502Capture 'compileall-312' $RepoRoot $Python312 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')

# Final clean-tree verification after all gates.
$status = @(Invoke-0502Capture 'git-final-status' $RepoRoot $Git @('status', '--porcelain=v1', '--untracked-files=all'))
if (@($status | Where-Object { $_ -and $_.Trim() }).Count -ne 0) { throw 'gate run left the repository dirty' }

[ordered]@{
    acceptedBase = $AcceptedBase
    codeHead = $CodeHead
    inventoryCount = @($inventory).Count
    monitor310Passed = @($monitor310).Count -gt 0
    monitor312Passed = @($monitor312).Count -gt 0
    gates = 'all PASS'
} | ConvertTo-Json -Depth 5
