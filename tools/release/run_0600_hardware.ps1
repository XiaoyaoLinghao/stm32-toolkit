[CmdletBinding()]
param(
  [ValidateSet('0400','0600')][string]$Contract,
  [string]$Repo,
  [string]$ExpectedCodeHead,
  [string]$FinalRunId,
  [string]$EvidenceRoot,
  [string]$HardwareInput,
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
$bootstrapRepository = if ($ContractSelfTest) { [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')) } else { [System.IO.Path]::GetFullPath($Repo) }
$bootstrapHead = (& git.exe -C $bootstrapRepository rev-parse HEAD 2>$null)
Assert-BootstrapCaller -Repository $bootstrapRepository -ExpectedHead $bootstrapHead
. (Join-Path $bootstrapRepository 'tools\release\path_contract_0600.ps1')

if ($ContractSelfTest) {
  if ($PSBoundParameters.Count -ne 1) { throw 'ContractSelfTest accepts no hardware inputs' }
  $selfTestRepository = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
  $selfTestHead = (& git.exe -C $selfTestRepository rev-parse HEAD 2>$null)
  if ($LASTEXITCODE -ne 0 -or $selfTestHead -cnotmatch '^[0-9a-f]{40}$') { throw 'self-test caller HEAD is unavailable' }
  Assert-FrozenVerifierCaller -Repository $selfTestRepository -ExpectedCodeHead $selfTestHead
  $runner = Join-Path $selfTestRepository 'tools\release\run_0600_gates.py'
  & $python -3.12 $runner contract-self-test --kind hardware
  exit $LASTEXITCODE
}
foreach ($name in @('Contract','Repo','ExpectedCodeHead','FinalRunId','EvidenceRoot','HardwareInput')) {
  if (-not $PSBoundParameters.ContainsKey($name)) { throw "$name is required" }
}
$modeCount = [int]$PrepareAction + [int]$ExecuteAction + [int]$ResumeContract
if ($modeCount -ne 1) { throw 'exactly one hardware mode is required' }
$Repo = ConvertTo-CanonicalAbsolutePath -Path $Repo -Name 'Repo'
$EvidenceRoot = ConvertTo-CanonicalAbsolutePath -Path $EvidenceRoot -Name 'EvidenceRoot'
$HardwareInput = ConvertTo-CanonicalAbsolutePath -Path $HardwareInput -Name 'HardwareInput'
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

$controllerHead = (& git.exe -C $Repo rev-parse HEAD 2>$null)
if ($LASTEXITCODE -ne 0 -or $controllerHead -cnotmatch '^[0-9a-f]{40}$') { throw 'hardware controller HEAD is unavailable' }
Assert-FrozenVerifierCaller -Repository $Repo -ExpectedCodeHead $controllerHead
$runner = Join-Path $Repo 'tools\release\run_0600_gates.py'
$base = @('-3.12',$runner,'hardware','--contract',$Contract,'--repo',$Repo,'--expected-code-head',$ExpectedCodeHead,'--final-run-id',$FinalRunId,'--evidence-root',$EvidenceRoot,'--hardware-input',$HardwareInput)
if ($PrepareAction) {
  & $python @base --mode prepare
} elseif ($ExecuteAction) {
  & $python @base --mode execute --nonce $Nonce --action-digest $ActionDigest --authorized
} else {
  & $python @base --mode resume --checkpoint $Checkpoint --recovery-record $RecoveryRecord
}
exit $LASTEXITCODE
