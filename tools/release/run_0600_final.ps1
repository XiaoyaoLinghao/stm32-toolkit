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
. (Join-Path $PSScriptRoot 'path_contract_0600.ps1')
$runner = Join-Path $PSScriptRoot 'run_0600_gates.py'
$python = (Get-Command py.exe -ErrorAction Stop).Source

if ($ContractSelfTest) {
  if ($PSBoundParameters.Count -ne 1) { throw 'ContractSelfTest accepts no runner inputs' }
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
  & $python -3.12 $runner wrapper-resume --kind final --final-checkpoint $FinalCheckpoint --recovery-record $RecoveryRecord
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
& $python -3.12 $runner wrapper --kind final --matrix $Matrix --module $Module --shard $Shard --run-id $RunId --evidence-root $EvidenceRoot --expected-code-head $ExpectedCodeHead --gate-catalog $GateCatalog --performance-catalog $PerformanceCatalog --support-profile $SupportProfile
exit $LASTEXITCODE
