[CmdletBinding()]
param(
  [string]$Matrix,
  [string]$Module,
  [string]$Shard,
  [string]$RunId,
  [string]$EvidenceRoot,
  [string]$ExpectedCodeHead,
  [string]$GateCatalog,
  [string]$PerformanceCatalog,
  [string]$SupportProfile,
  [switch]$ContractSelfTest
)

$ErrorActionPreference = 'Stop'
$python = (Get-Command py.exe -ErrorAction Stop).Source

function Assert-BootstrapCaller {
  param([string]$Repository,[string]$ExpectedHead)
  if ($ExpectedHead -cnotmatch '^[0-9a-f]{40}$') { throw 'bootstrap CodeHead is invalid' }
  $head = (& git.exe -C $Repository rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedHead) { throw 'bootstrap HEAD mismatch' }
  foreach ($relative in @('tools/release/path_contract_0600.ps1','tools/release/run_0600_gates.py','tools/release/verify_0600_feasibility.py','tools/release/verify_0600_release.py')) {
    $path = Join-Path $Repository ($relative.Replace('/','\'))
    $working = (& git.exe -C $Repository hash-object -- $path 2>$null)
    $committed = (& git.exe -C $Repository rev-parse ($ExpectedHead + ':' + $relative) 2>$null)
    if ($LASTEXITCODE -ne 0 -or $working -cnotmatch '^[0-9a-f]{40}$' -or $working -cne $committed) { throw "bootstrap blob mismatch: $relative" }
  }
}
$bootstrapRepository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$bootstrapHead = $ExpectedCodeHead
if ($ContractSelfTest) { $bootstrapHead = (& git.exe -C $bootstrapRepository rev-parse HEAD 2>$null) }
Assert-BootstrapCaller -Repository $bootstrapRepository -ExpectedHead $bootstrapHead
. (Join-Path $bootstrapRepository 'tools\release\path_contract_0600.ps1')

if ($ContractSelfTest) {
  if ($PSBoundParameters.Count -ne 1) { throw 'ContractSelfTest accepts no runner inputs' }
  $selfTestRepository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
  $selfTestHead = (& git.exe -C $selfTestRepository rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0 -or $selfTestHead -cnotmatch '^[0-9a-f]{40}$') { throw 'self-test caller HEAD is unavailable' }
  Assert-FrozenVerifierCaller -Repository $selfTestRepository -ExpectedCodeHead $selfTestHead
  $runner = Join-Path $selfTestRepository 'tools\release\run_0600_gates.py'
  & $python -3.12 $runner contract-self-test --kind quick
  exit $LASTEXITCODE
}

foreach ($name in @('Matrix','Module','Shard','RunId','EvidenceRoot','ExpectedCodeHead','GateCatalog','PerformanceCatalog','SupportProfile')) {
  if (-not $PSBoundParameters.ContainsKey($name)) { throw "$name is required" }
}
if ($Matrix -cne 'quick') { throw 'Matrix must be quick' }
$EvidenceRoot = ConvertTo-CanonicalAbsolutePath -Path $EvidenceRoot -Name 'EvidenceRoot'
$GateCatalog = ConvertTo-CanonicalAbsolutePath -Path $GateCatalog -Name 'GateCatalog'
$PerformanceCatalog = ConvertTo-CanonicalAbsolutePath -Path $PerformanceCatalog -Name 'PerformanceCatalog'
$SupportProfile = ConvertTo-CanonicalAbsolutePath -Path $SupportProfile -Name 'SupportProfile'
$repository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Assert-FrozenVerifierCaller -Repository $repository -ExpectedCodeHead $ExpectedCodeHead
$runner = Join-Path $repository 'tools\release\run_0600_gates.py'
& $python -3.12 $runner wrapper --kind quick --matrix $Matrix --module $Module --shard $Shard --run-id $RunId --evidence-root $EvidenceRoot --expected-code-head $ExpectedCodeHead --gate-catalog $GateCatalog --performance-catalog $PerformanceCatalog --support-profile $SupportProfile
exit $LASTEXITCODE
