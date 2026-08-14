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
  [switch]$ContractSelfTest,
  [switch]$ResumeFinalRun,
  [string]$FinalCheckpoint,
  [string]$RecoveryRecord
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
if ($ContractSelfTest) {
  $bootstrapHead = (& git.exe -C $bootstrapRepository rev-parse HEAD 2>$null)
} elseif ($ResumeFinalRun) {
  if (-not [System.IO.Path]::IsPathRooted($FinalCheckpoint) -or $FinalCheckpoint -cne [System.IO.Path]::GetFullPath($FinalCheckpoint)) { throw 'FinalCheckpoint is not canonical absolute' }
  $bootstrapCheckpoint = (Get-Content -LiteralPath $FinalCheckpoint -Raw -Encoding UTF8 | ConvertFrom-Json)
  $bootstrapRepository = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetDirectoryName($bootstrapCheckpoint.controller_path)) '..\..'))
  $bootstrapHead = $bootstrapCheckpoint.code_head
}
Assert-BootstrapCaller -Repository $bootstrapRepository -ExpectedHead $bootstrapHead
. (Join-Path $bootstrapRepository 'tools\release\path_contract_0600.ps1')

if ($ContractSelfTest) {
  if ($PSBoundParameters.Count -ne 1) { throw 'ContractSelfTest accepts no runner inputs' }
  $selfTestRepository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
  $selfTestHead = (& git.exe -C $selfTestRepository rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0 -or $selfTestHead -cnotmatch '^[0-9a-f]{40}$') { throw 'self-test caller HEAD is unavailable' }
  Assert-FrozenVerifierCaller -Repository $selfTestRepository -ExpectedCodeHead $selfTestHead
  $runner = Join-Path $selfTestRepository 'tools\release\run_0600_gates.py'
  & $python -3.12 $runner contract-self-test --kind final
  exit $LASTEXITCODE
}
if ($ResumeFinalRun) {
  if (-not $PSBoundParameters.ContainsKey('FinalCheckpoint') -or -not $PSBoundParameters.ContainsKey('RecoveryRecord')) { throw 'final resume requires FinalCheckpoint and RecoveryRecord' }
  if ($PSBoundParameters.Count -ne 3) { throw 'final resume accepts only its checkpoint and recovery record' }
  $FinalCheckpoint = ConvertTo-CanonicalAbsolutePath -Path $FinalCheckpoint -Name 'FinalCheckpoint'
  $RecoveryRecord = ConvertTo-CanonicalAbsolutePath -Path $RecoveryRecord -Name 'RecoveryRecord'
  $checkpointValue = (Get-Content -LiteralPath $FinalCheckpoint -Raw -Encoding UTF8 | ConvertFrom-Json)
  $resumeRepository = [System.IO.Path]::GetFullPath((Join-Path ([System.IO.Path]::GetDirectoryName($checkpointValue.controller_path)) '..\..'))
  Assert-FrozenVerifierCaller -Repository $resumeRepository -ExpectedCodeHead $checkpointValue.code_head
  $resumeRunner = Join-Path $resumeRepository 'tools\release\run_0600_gates.py'
  & $python -3.12 $resumeRunner wrapper-resume --kind final --final-checkpoint $FinalCheckpoint --recovery-record $RecoveryRecord
  exit $LASTEXITCODE
}
foreach ($name in @('Matrix','Module','Shard','RunId','EvidenceRoot','ExpectedCodeHead','GateCatalog','PerformanceCatalog','SupportProfile')) {
  if (-not $PSBoundParameters.ContainsKey($name)) { throw "$name is required" }
}
if ($FinalCheckpoint -or $RecoveryRecord) { throw 'final resume inputs require ResumeFinalRun' }
if ($Matrix -cne 'final') { throw 'Matrix must be final' }
$EvidenceRoot = ConvertTo-CanonicalAbsolutePath -Path $EvidenceRoot -Name 'EvidenceRoot'
$GateCatalog = ConvertTo-CanonicalAbsolutePath -Path $GateCatalog -Name 'GateCatalog'
$PerformanceCatalog = ConvertTo-CanonicalAbsolutePath -Path $PerformanceCatalog -Name 'PerformanceCatalog'
$SupportProfile = ConvertTo-CanonicalAbsolutePath -Path $SupportProfile -Name 'SupportProfile'
$repository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
Assert-FrozenVerifierCaller -Repository $repository -ExpectedCodeHead $ExpectedCodeHead
$runner = Join-Path $repository 'tools\release\run_0600_gates.py'
& $python -3.12 $runner wrapper --kind final --matrix $Matrix --module $Module --shard $Shard --run-id $RunId --evidence-root $EvidenceRoot --expected-code-head $ExpectedCodeHead --gate-catalog $GateCatalog --performance-catalog $PerformanceCatalog --support-profile $SupportProfile
exit $LASTEXITCODE
