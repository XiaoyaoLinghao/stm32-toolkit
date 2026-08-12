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

# Support manifest: controlled dependency wheelhouse and npm cache are read-only inputs.
$supportManifestPath = Join-Path $SupportRoot 'support-manifest.json'
if (-not [IO.File]::Exists($supportManifestPath)) { throw 'SupportRoot must contain support-manifest.json' }
$supportManifest = Get-Content -Raw -LiteralPath $supportManifestPath | ConvertFrom-Json
if ($supportManifest.schemaVersion -ne 1) { throw 'support-manifest.json schemaVersion must be 1' }
if (-not $supportManifest.wheelhouse -or -not [IO.Path]::IsPathRooted([string]$supportManifest.wheelhouse)) { throw 'support-manifest.json wheelhouse must be an absolute path' }
$Wheelhouse = (Resolve-0502Path ([string]$supportManifest.wheelhouse) 'wheelhouse' $false)
if (-not $supportManifest.npmCache -or -not [IO.Path]::IsPathRooted([string]$supportManifest.npmCache)) { throw 'support-manifest.json npmCache must be an absolute path' }
$NpmCache = (Resolve-0502Path ([string]$supportManifest.npmCache) 'npmCache' $false)

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
    param([string]$Name, [string]$Status, [string]$Detail)
    $script:GateResults.Add([ordered]@{ gate = $Name; status = $Status; detail = $Detail })
    if ($Status -ne 'PASS') { $script:Failed = $true }
}

# --- Identity binding: the worktree MUST be exactly CodeHead. ------------------
$actualHeadResult = Invoke-0502Capture 'git-rev-parse-head' $RepoRoot $Git @('rev-parse', 'HEAD')
if ($actualHeadResult.Exit -ne 0) { $script:Failed = $true; $script:GateResults.Add([ordered]@{ gate = 'git-head-identity'; status = 'FAIL'; exit = $actualHeadResult.Exit; log = $actualHeadResult.Log }); throw 'git rev-parse HEAD failed' }
$actualHead = ($actualHeadResult.Lines | Select-Object -Last 1).Trim()
if ($actualHead -cne $CodeHead) {
    $script:Failed = $true
    $script:GateResults.Add([ordered]@{ gate = 'git-head-identity'; status = 'FAIL'; detail = "HEAD $actualHead does not equal CodeHead $CodeHead" })
    throw "HEAD $actualHead does not equal CodeHead $CodeHead"
}
$script:GateResults.Add([ordered]@{ gate = 'git-head-identity'; status = 'PASS'; detail = "HEAD equals CodeHead $CodeHead" })

$baseCheck = Invoke-0502Capture 'git-verify-base' $RepoRoot $Git @('cat-file', '-e', "$AcceptedBase^{commit}")
if ($baseCheck.Exit -ne 0) { $script:Failed = $true; $script:GateResults.Add([ordered]@{ gate = 'git-verify-base'; status = 'FAIL'; exit = $baseCheck.Exit }); throw 'accepted base is unavailable' }
$descendCheck = Invoke-0502Capture 'git-verify-descend' $RepoRoot $Git @('merge-base', '--is-ancestor', $AcceptedBase, $CodeHead)
if ($descendCheck.Exit -ne 0) { $script:Failed = $true; $script:GateResults.Add([ordered]@{ gate = 'git-verify-descend'; status = 'FAIL'; exit = $descendCheck.Exit }); throw 'code head does not descend from accepted base' }

# --- CODE_HEAD archive ---------------------------------------------------------
$archiveRoot = Join-Path $EvidenceRoot 'code-head-archive'
[void][IO.Directory]::CreateDirectory($archiveRoot)
$archiveResult = Invoke-0502Capture 'git-archive-code-head' $RepoRoot $Git @('archive', '--format=tar', '--output', (Join-Path $archiveRoot 'code-head.tar'), $CodeHead)
if ($archiveResult.Exit -ne 0) { $script:Failed = $true; $script:GateResults.Add([ordered]@{ gate = 'git-archive-code-head'; status = 'FAIL'; exit = $archiveResult.Exit }); throw 'CODE_HEAD archive failed' }
if (-not [IO.File]::Exists((Join-Path $archiveRoot 'code-head.tar'))) { throw 'CODE_HEAD archive was not written' }

$inventory = Invoke-0502Capture 'git-diff-inventory' $RepoRoot $Git @('diff', '--name-status', '--no-renames', "$AcceptedBase..$CodeHead")
if ($inventory.Exit -ne 0 -or @($inventory.Lines).Count -eq 0) { throw 'accepted-base..code-head diff inventory is empty' }
Invoke-0502Gate 'git-diff-check' $RepoRoot $Git @('diff', '--check', "$AcceptedBase..$CodeHead")

$uiRoot = Join-Path $RepoRoot 'tools\stm32-monitor\ui'

# Node gates (offline against the verified npm cache).
Invoke-0502Gate 'node-npm-ci' $uiRoot $Npm @('ci', '--offline', '--cache', $NpmCache)
Invoke-0502Gate 'node-typecheck' $uiRoot $Npm @('run', 'typecheck')
Invoke-0502Gate 'node-typecheck-e2e' $uiRoot $Npm @('run', 'typecheck:e2e')
Invoke-0502Gate 'node-lint' $uiRoot $Npm @('run', 'lint')
Invoke-0502Gate 'node-test' $uiRoot $Npm @('run', 'test')
Invoke-0502Gate 'node-a11y' $uiRoot $Npm @('run', 'test:a11y')
Invoke-0502Gate 'node-coverage' $uiRoot $Npm @('exec', 'vitest', 'run', '--coverage')
Invoke-0502Gate 'node-coverage-gate' $uiRoot $Node @('tests/check-coverage.mjs')
Invoke-0502Gate 'node-build' $uiRoot $Npm @('run', 'build')
Invoke-0502Gate 'node-verify-dist' $uiRoot $Npm @('run', 'verify:dist')

# Playwright functional and five-minute performance. Clear the duration overrides
# so the gate always runs the authoritative 300 000 ms window.
Remove-Item Env:STM32_MONITOR_PERF_WARMUP_MS -ErrorAction SilentlyContinue
Remove-Item Env:STM32_MONITOR_PERF_MEASURE_MS -ErrorAction SilentlyContinue
Invoke-0502Gate 'playwright-functional' $uiRoot $Npm @('exec', '--', 'playwright', 'test', '--project=chromium-1280', '--project=chromium-1024', '--workers=1')
Invoke-0502Gate 'playwright-performance' $uiRoot $Npm @('exec', '--', 'playwright', 'test', 'e2e/performance.spec.ts', '--project=chromium-1280', '--workers=1')

# Python monitor suites: disjoint partitions so each run is stable on the host.
Invoke-0502Gate 'python310-monitor-core' $RepoRoot $Python310 @('-m', 'pytest', 'tools/stm32-monitor/tests', '--ignore=tools/stm32-monitor/tests/test_performance.py', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py310-monitor-core'))
Invoke-0502Gate 'python310-monitor-perf' $RepoRoot $Python310 @('-m', 'pytest', 'tools/stm32-monitor/tests/test_performance.py', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py310-monitor-perf'))
Invoke-0502Gate 'python312-monitor-core' $RepoRoot $Python312 @('-m', 'pytest', 'tools/stm32-monitor/tests', '--ignore=tools/stm32-monitor/tests/test_performance.py', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py312-monitor-core'))
Invoke-0502Gate 'python312-monitor-perf' $RepoRoot $Python312 @('-m', 'pytest', 'tools/stm32-monitor/tests/test_performance.py', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py312-monitor-perf'))
Invoke-0502Gate 'python312-toolkit' $RepoRoot $Python312 @('-m', 'pytest', 'tools/stm32-toolkit/tests', '-q', '-p', 'no:cacheprovider', '--basetemp', (Join-Path $EvidenceRoot 'py312-toolkit'))

Invoke-0502Gate 'compileall-310' $RepoRoot $Python310 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')
Invoke-0502Gate 'compileall-312' $RepoRoot $Python312 @('-m', 'compileall', '-q', 'tools/stm32-monitor/src/stm32_monitor', 'tools/stm32-toolkit/src/stm32_toolkit')

# Wheel build (offline from the controlled wheelhouse) for both distributions.
$wheelRoot = Join-Path $EvidenceRoot 'wheels'
[void][IO.Directory]::CreateDirectory($wheelRoot)
$env:PIP_NO_INDEX = '1'
$env:PIP_FIND_LINKS = $Wheelhouse
Invoke-0502Gate 'wheel-toolkit' $RepoRoot $Python312 @('-m', 'build', '--wheel', '--no-isolation', '--outdir', $wheelRoot, 'tools/stm32-toolkit')
Invoke-0502Gate 'wheel-monitor' $RepoRoot $Python312 @('-m', 'build', '--wheel', '--no-isolation', '--outdir', $wheelRoot, 'tools/stm32-monitor')
Remove-Item Env:PIP_NO_INDEX -ErrorAction SilentlyContinue
Remove-Item Env:PIP_FIND_LINKS -ErrorAction SilentlyContinue

$toolkitWheel = Join-Path $wheelRoot 'stm32_toolkit-0.5.0-py3-none-any.whl'
$monitorWheel = Join-Path $wheelRoot 'stm32_monitor-0.5.0-py3-none-any.whl'
if (-not [IO.File]::Exists($toolkitWheel) -or -not [IO.File]::Exists($monitorWheel)) { throw 'expected 0.5.0 wheels were not built' }
$wheelHashResult = Invoke-0502Capture 'wheel-hashes' $wheelRoot $CmdExe @('/d', '/c', 'for %f in (*.whl) do @certutil -hashfile "%f" SHA256 | findstr /v "hash"')

# Installed-copy smoke: offline install into fresh venvs, then verify the import
# comes from the installed directory, pip check passes, and the wheel UI assets,
# static index, CSP, and auth rejection are correct, and the managed launcher runs.
foreach ($pyLabel in @('python310', 'python312')) {
    $pyPath = if ($pyLabel -eq 'python310') { $Python310 } else { $Python312 }
    $smoke = Join-Path $EvidenceRoot ("smoke-" + $pyLabel)
    Invoke-0502Gate "smoke-$pyLabel-venv" $RepoRoot $pyPath @('-m', 'venv', $smoke)
    $smokePython = Join-Path $smoke 'Scripts\python.exe'
    Invoke-0502Gate "smoke-$pyLabel-install" $smoke $smokePython @('-m', 'pip', 'install', '--no-index', '--find-links', $Wheelhouse, '--disable-pip-version-check', $toolkitWheel, $monitorWheel)
    Invoke-0502Gate "smoke-$pyLabel-pip-check" $smoke $smokePython @('-m', 'pip', 'check')
    Invoke-0502Gate "smoke-$pyLabel-import-path" $smoke $smokePython @('-c', "import stm32_monitor, stm32_toolkit, pathlib, sys; assert str(pathlib.Path(stm32_monitor.__file__).resolve()).lower().startswith(str(pathlib.Path(sys.prefix).resolve()).lower()), 'import not from installed dir'; print(stm32_monitor.__version__, stm32_toolkit.__version__)")
    Invoke-0502Gate "smoke-$pyLabel-ui-assets" $smoke $smokePython @('-c', "from stm32_monitor.ui_assets import UiAssets; a = UiAssets.load(); r = a.response('/', 43210); assert r.status == 200; assert 'ws://127.0.0.1:43210' in r.headers.get('Content-Security-Policy', ''); assert a.response('/assets/nope.js', 43210).status == 404")
    Invoke-0502Gate "smoke-$pyLabel-auth-fail" $smoke $smokePython @('-c', "import asyncio, aiohttp, re; from stm32_monitor.service import MonitorService; from stm32_monitor.runtime import MonitorRuntime
class R:
    async def start(self, c): raise RuntimeError
async def main():
    s = MonitorService(R(), workspace_id='w', session_id='s', serve_ui=True)
    ep = await s.start()
    async with aiohttp.ClientSession() as cl:
        async with cl.get(ep.url + '/api/v1/status') as resp:
            assert resp.status in (401, 403), resp.status
        async with cl.get(ep.url + '/') as resp:
            assert resp.status == 200 and 'text/html' in resp.headers.get('Content-Type', '')
    await s.stop()
asyncio.run(main())")
}

# Managed launcher with the installed runtime: fail closed without CLAUDE_PLUGIN_DATA.
$launcherResult = Invoke-0502Capture 'launcher-fail-closed' $RepoRoot $CmdExe @('/d', '/c', 'bin\stm32-monitor.cmd', '--help')
if ($launcherResult.Exit -eq 0) {
    $script:Failed = $true
    $script:GateResults.Add([ordered]@{ gate = 'launcher-fail-closed'; status = 'FAIL'; exit = 0; detail = 'launcher did not fail closed without CLAUDE_PLUGIN_DATA' })
} else {
    $script:GateResults.Add([ordered]@{ gate = 'launcher-fail-closed'; status = 'PASS'; exit = $launcherResult.Exit; log = $launcherResult.Log })
}

# Final clean-tree verification.
$status = @(Invoke-0502Capture 'git-final-status' $RepoRoot $Git @('status', '--porcelain=v1', '--untracked-files=all'))
$dirty = @($status.Lines | Where-Object { $_ -and $_.Trim() })
if ($dirty.Count -ne 0) {
    $script:Failed = $true
    $script:GateResults.Add([ordered]@{ gate = 'clean-tree'; status = 'FAIL'; detail = 'gate run left the repository dirty' })
} else {
    $script:GateResults.Add([ordered]@{ gate = 'clean-tree'; status = 'PASS' })
}

$summary = @{
    acceptedBase = $AcceptedBase
    codeHead = $CodeHead
    headIdentity = $actualHead
    gates = @($script:GateResults)
    overall = if ($script:Failed) { 'FAIL' } else { 'PASS' }
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceRoot 'summary.json')
if ($script:Failed) { throw 'one or more 0502 gates FAILED; see EvidenceRoot' }
