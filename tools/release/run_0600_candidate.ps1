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
  [switch]$ResumeCandidateRun,
  [string]$CandidateLedger,
  [string]$RecoveryRecord
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'path_contract_0600.ps1')
$runner = Join-Path $PSScriptRoot 'run_0600_gates.py'
$python = (Get-Command py.exe -ErrorAction Stop).Source

if ($ContractSelfTest) {
  if ($PSBoundParameters.Count -ne 1) { throw 'ContractSelfTest accepts no runner inputs' }
  & $python -3.12 $runner contract-self-test --kind quick
  exit $LASTEXITCODE
}
if ($ResumeCandidateRun) {
  if (-not $PSBoundParameters.ContainsKey('CandidateLedger') -or -not $PSBoundParameters.ContainsKey('RecoveryRecord')) { throw 'candidate resume requires CandidateLedger and RecoveryRecord' }
  if ($PSBoundParameters.Count -ne 3) { throw 'candidate resume accepts only its ledger and recovery record' }
  $CandidateLedger = ConvertTo-CanonicalAbsolutePath -Path $CandidateLedger -Name 'CandidateLedger'
  $RecoveryRecord = ConvertTo-CanonicalAbsolutePath -Path $RecoveryRecord -Name 'RecoveryRecord'
  & $python -3.12 $runner wrapper-resume --kind candidate --candidate-ledger $CandidateLedger --recovery-record $RecoveryRecord
  exit $LASTEXITCODE
}
foreach ($name in @('Matrix','Module','Shard','RunId','EvidenceRoot','ExpectedCodeHead','GateCatalog','PerformanceCatalog','SupportProfile')) {
  if (-not $PSBoundParameters.ContainsKey($name)) { throw "$name is required" }
}
if ($CandidateLedger -or $RecoveryRecord) { throw 'candidate resume inputs require ResumeCandidateRun' }
if ($Matrix -cne 'candidate') { throw 'Matrix must be candidate' }
$EvidenceRoot = ConvertTo-CanonicalAbsolutePath -Path $EvidenceRoot -Name 'EvidenceRoot'
$GateCatalog = ConvertTo-CanonicalAbsolutePath -Path $GateCatalog -Name 'GateCatalog'
$PerformanceCatalog = ConvertTo-CanonicalAbsolutePath -Path $PerformanceCatalog -Name 'PerformanceCatalog'
$SupportProfile = ConvertTo-CanonicalAbsolutePath -Path $SupportProfile -Name 'SupportProfile'
& $python -3.12 $runner wrapper --kind candidate --matrix $Matrix --module $Module --shard $Shard --run-id $RunId --evidence-root $EvidenceRoot --expected-code-head $ExpectedCodeHead --gate-catalog $GateCatalog --performance-catalog $PerformanceCatalog --support-profile $SupportProfile
exit $LASTEXITCODE
