[CmdletBinding()]
param(
  [ValidateSet('0400','0600')][string]$Contract,
  [string]$Repo,
  [string]$ExpectedCodeHead,
  [string]$FinalRunId,
  [string]$EvidenceRoot,
  [switch]$PrepareAction,
  [switch]$ExecuteAction,
  [string]$Nonce,
  [string]$ActionDigest,
  [switch]$Authorized,
  [switch]$ResumeContract,
  [string]$Checkpoint,
  [string]$RecoveryRecord,
  [switch]$ContractSelfTest
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'path_contract_0600.ps1')
$runner = Join-Path $PSScriptRoot 'run_0600_gates.py'
$python = (Get-Command py.exe -ErrorAction Stop).Source

if ($ContractSelfTest) {
  if ($PSBoundParameters.Count -ne 1) { throw 'ContractSelfTest accepts no hardware inputs' }
  & $python -3.12 $runner contract-self-test --kind hardware
  exit $LASTEXITCODE
}
foreach ($name in @('Contract','Repo','ExpectedCodeHead','FinalRunId','EvidenceRoot')) {
  if (-not $PSBoundParameters.ContainsKey($name)) { throw "$name is required" }
}
$modeCount = [int]$PrepareAction + [int]$ExecuteAction + [int]$ResumeContract
if ($modeCount -ne 1) { throw 'exactly one hardware mode is required' }
$Repo = ConvertTo-CanonicalAbsolutePath -Path $Repo -Name 'Repo'
$EvidenceRoot = ConvertTo-CanonicalAbsolutePath -Path $EvidenceRoot -Name 'EvidenceRoot'
if ($ExecuteAction) {
  if (-not $Authorized -or $Nonce -notmatch '^[0-9a-f]{64}$' -or $ActionDigest -notmatch '^[0-9a-f]{64}$') { throw 'execute requires exact nonce/digest and Authorized' }
} elseif ($Nonce -or $ActionDigest -or $Authorized) {
  throw 'authorization inputs are execute-only'
}
if ($ResumeContract) {
  if (-not $Checkpoint -or -not $RecoveryRecord) { throw 'resume requires checkpoint and recovery record' }
  $Checkpoint = ConvertTo-CanonicalAbsolutePath -Path $Checkpoint -Name 'Checkpoint'
  $RecoveryRecord = ConvertTo-CanonicalAbsolutePath -Path $RecoveryRecord -Name 'RecoveryRecord'
} elseif ($Checkpoint -or $RecoveryRecord) {
  throw 'checkpoint/recovery inputs are resume-only'
}

# Deferred catalog entries are intentionally non-executable during the 0601
# software candidate.  The Python state machine is exercised only by the fake
# contract self-test until the post-0603 hardware campaign supplies commands.
Write-Error 'hardware catalog actions are deferred and non-executable in the 0601 software candidate'
exit 2
