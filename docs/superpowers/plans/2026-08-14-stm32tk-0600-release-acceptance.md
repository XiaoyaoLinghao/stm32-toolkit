# STM32TK-0600 Release Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the three accepted 0.6 modules, close the deferred 0.4 and new 0.6 real-board gates in one truthfully separated hardware campaign, prove one frozen final CodeHead with one logical Windows release matrix, create a report-only acceptance commit, and stop before any unauthorized remote release action.

**Architecture:** 0601 and 0602 enter through accepted report commits and immutable evidence inventories; the 0603 product commit is the only final product CodeHead. A non-executing readiness phase proves Windows software and hardware inventory without duplicating product tests. The final campaign runs the deferred 0.4 gates at the exact 0.4 accepted CodeHead and the 0.6 gates at the exact 0.6 CodeHead with separate firmware, action, and result identities. Windows software and hardware shards bind one `finalRunId`; each shard is fail-fast, and only one pre-enumerated external infrastructure interruption may resume its affected shard. Reporting is a separate child commit and cannot repair product or evidence.

**Tech Stack:** Git/worktrees, PowerShell 5.1, Python 3.10/3.12, Node/npm, Playwright browsers, pytest/coverage, wheel/pip offline install, real STM32 board/probe/transports, SHA-256 artifact inventories.

## Global Constraints

- Program base is exactly `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`).
- The deferred 0.4 hardware gates test product CodeHead
  `96966c461e7e11bff965027d8d498dd40ea5fd55`; its original report commit is
  `0ee0a5037b3bd158eea5bd312fce7feaadecbfc6`. Neither SHA may be replaced by a
  later 0.5/0.6 descendant when claiming 0.4 evidence.
- Follow all four 2026-08-14 STM32TK-0600/0601/0602/0603 design specifications.
- This plan starts only after Windows software feasibility PASS, 0601 and 0602 accepted report commits,
  and 0603 candidate reconciliation PASS with final catalog/node/performance digests at one product
  CodeHead.
- No product, test, helper, dependency, version, generated dist, documentation, Skill, gate, or
  threshold edit is allowed after final freeze. Any such edit invalidates the CodeHead and sends
  work back to the owning module plan.
- Test logs/results/screenshots/traces/wheels/coverage/manifests live in an external evidence root.
- Every required Windows software/hardware result is PASS or the release is BLOCKED/FAIL; no fake, skip,
  deferred, or another owner's stale evidence is promoted to PASS.
- All product-framework retries are disabled (`pytest` reruns absent and Playwright `retries: 0`).
  Scheduling targets only warn; they are never acceptance thresholds or child-process timeouts.
- `RECOVERABLE_INFRA_ERROR` is limited to the exact tokens `HOST_POWER_OR_REBOOT`,
  `RUNNER_LOSS_BEFORE_CHILD_RESULT`, `PHYSICAL_USB_OR_PROBE_REMOVAL`, and
  `TARGET_POWER_LOSS`. After reviewer classification, only the
  affected shard may resume once with identical frozen inputs and evidence root; both attempts are
  retained. A repeat is BLOCKED. Product/test/security/coverage/performance/timeout/corruption/
  dependency failures are not recoverable and any repository edit creates a new CodeHead.
- Remote push/PR/merge/tag/branch deletion requires a new explicit user authorization.

## Execution Order and Requirement Coverage

| Phase | Plan tasks | Required result before the next phase |
|---|---|---|
| feasibility | 0601 Task 1 | Windows owner/profile, tools, support manifest, and fake/replay proof before product code; hardware remains explicitly pending |
| 0601 contract foundation | 0601 Tasks 2--12 | frozen schema/families and 0601 nodes, evidence/test schemas, Project v3, Host/Target tests, four real-transport adapters/contracts with fake/replay coverage; real execution pending |
| 0601 acceptance | 0601 Task 13 | candidate PASS and report-only accepted-base commit |
| 0602 diagnostic product | 0602 Tasks 1--11 | hash chain, hypotheses, observations, controls, fix verification, bundle, and deferred real-board fixture/controller coverage; real execution pending to 0600 |
| 0602 acceptance | 0602 Task 12 | candidate PASS and report-only accepted-base commit |
| 0603 analytics product | 0603 Tasks 1--12 | history v2, comparison/quality, annotations, UI, bundles, version 0.6.0 |
| 0603 handoff | 0603 Task 13 | Windows software candidate PASS plus final catalog/node/performance digests at one product CodeHead; outcome may be `SOFTWARE_COMPLETE_HARDWARE_PENDING` |
| release closure | this plan Tasks 1--8 | unified exact-CodeHead 0.4/0.6 hardware campaign, one Windows final matrix, reconciliation, report-only commit, remote-action stop |

No task from a later row begins before the preceding row's required result. Software fakes own
unit/integration evidence; Codex owns the Windows evidence and the user remains the physical-
hardware evidence owner. Missing hardware blocks final release, not software implementation.
Linux support is outside 0.6 and no Linux result is required or claimed.

The release state machine is exact:

| Current state | Required evidence | Next state |
|---|---|---|
| `0603_CANDIDATE` | Windows software candidate PASS and frozen catalogs/nodes | `READINESS` |
| `READINESS` | non-executing Windows, 0.4-hardware, and 0.6-hardware readiness PASS | `SOFTWARE_COMPLETE_HARDWARE_PENDING` |
| `SOFTWARE_COMPLETE_HARDWARE_PENDING` | Windows final plus separate exact-CodeHead 0.4 and 0.6 hardware PASS | `RECONCILIATION` |
| `RECONCILIATION` | complete immutable evidence verification PASS | `ACCEPTED` |

Hardware product bodies cannot run before readiness. Readiness verifies availability and the
ability to request action-specific authorization; it never requires or creates hardware PASS.

---

## Task 1: Reconstruct and freeze the release ledger

**Files:** none; write the ledger into external evidence metadata, not a product file.

- [ ] Consume the closed `final-release-inputs.json` emitted by 0603 Task 13. It contains the
  repository URL, fixed program/0.4 identities, full 0601 product/report, 0602 product/report, and
  0603 product SHAs, plus sorted path/bytes/SHA-256 entries for every frozen spec, plan, catalog,
  controller, verifier, lock, and Windows software-support profile/manifest. It is an input, not a
  release ledger. Verify each parent/ancestry relationship and that every 0.6 module report commit
  changes only its declared report path.

- [ ] Verify the frozen 0.4 product/report pair above: the report parent is the product CodeHead,
  the historical report commit's exact four-path inventory is the 0405 report plus the three
  contemporaneous 0.4/0405 plan updates, and the deferred hardware claims match that report. Do
  not retroactively describe this pre-0.6 historical commit as report-only.

```powershell
# Run this block only after completing every remaining Task 1 inventory/profile/hash check below.
$inputPath = 'C:\tmp\stm32tk-0600-support\final-release-inputs.json'
$ledgerPath = 'C:\tmp\stm32tk-0600-support\release-ledger.json'
$ledgerDigestPath = "$ledgerPath.sha256"
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) { throw 'missing 0603 final release inputs' }
if ((Test-Path -LiteralPath $ledgerPath) -or (Test-Path -LiteralPath $ledgerDigestPath)) { throw 'release ledger output already exists' }
$inputBytes = [IO.File]::ReadAllBytes($inputPath)
$inputDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($inputBytes) | ForEach-Object ToString x2) -join ''
if ($inputDigest -cne (Get-Content -LiteralPath "$inputPath.sha256" -Raw).Trim()) { throw '0603 final release input digest mismatch' }
$inputs = [Text.Encoding]::UTF8.GetString($inputBytes) | ConvertFrom-Json
$inputFields = 'repositoryUrl','programBase','0400Product','0400Report','0601Product','0601Report','0602Product','0602Report','0603Product','governance','artifacts'
if ((@($inputs.psobject.Properties.Name) -join "`n") -cne ($inputFields -join "`n") -or $inputs.repositoryUrl -cne 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git' -or $inputs.programBase -cne 'bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f' -or $inputs.'0400Product' -cne '96966c461e7e11bff965027d8d498dd40ea5fd55' -or $inputs.'0400Report' -cne '0ee0a5037b3bd158eea5bd312fce7feaadecbfc6') { throw '0603 final release input schema or fixed identity mismatch' }
$sourceRepo = [IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim())
if ((git -C $sourceRepo rev-parse HEAD).Trim() -cne [string]$inputs.'0603Product') { throw 'Task 1 must run at the frozen 0603 CodeHead' }
if ((git -C $sourceRepo status --porcelain=v1 --untracked-files=all)) { throw 'dirty Task 1 source worktree' }
$ledgerBuilder = Join-Path $sourceRepo 'tools\release\verify_0600_release.py'
$pathContract = Join-Path $sourceRepo 'tools\release\path_contract_0600.ps1'
$trustedTask1Files = [ordered]@{ verifier=@('tools/release/verify_0600_release.py',$ledgerBuilder); path_contract=@('tools/release/path_contract_0600.ps1',$pathContract) }
$trustedTask1Blobs = @{}
foreach ($name in $trustedTask1Files.Keys) {
  $relative,$absolute = $trustedTask1Files[$name]
  $committed = (git -C $sourceRepo rev-parse "$($inputs.'0603Product')`:$relative").Trim()
  $working = (git -C $sourceRepo hash-object -- $absolute).Trim()
  if ($committed -notmatch '\A[0-9a-f]{40}\z' -or $working -cne $committed) { throw "$name differs from frozen CodeHead" }
  $trustedTask1Blobs[$name] = $committed
}
function Assert-Task1VerifierUnchanged {
  $working = (git -C $sourceRepo hash-object -- $ledgerBuilder).Trim()
  if ($LASTEXITCODE -ne 0 -or $working -cne $trustedTask1Blobs.verifier) { throw 'release verifier changed before execution' }
}
. $pathContract
$hardwareInputPath = [string]$env:STM32TK_0600_HARDWARE_INPUT
$expectedHardwareCampaignId = [string]$env:STM32TK_0600_HARDWARE_CAMPAIGN_ID
$expectedHardwareDigest = [string]$env:STM32TK_0600_HARDWARE_INPUT_SHA256
if ([string]::IsNullOrWhiteSpace($hardwareInputPath)) {
  if (-not [string]::IsNullOrWhiteSpace($expectedHardwareCampaignId) -or -not [string]::IsNullOrWhiteSpace($expectedHardwareDigest)) { throw 'partial hardware campaign resume identity' }
  $campaignId = [guid]::NewGuid().ToString('D')
  $hardwareRoot = "C:\tmp\stm32tk-0600-hardware-input-$campaignId"
  if (Test-Path -LiteralPath $hardwareRoot) { throw 'new hardware input root already exists' }
  [void](New-Item -ItemType Directory -Path $hardwareRoot)
  $hardwareInputPath = Join-Path $hardwareRoot 'hardware-campaign-inputs.json'
  Assert-Task1VerifierUnchanged
  py -3.12 $ledgerBuilder hardware-campaign-inputs --campaign-id $campaignId --generator-code-head ([string]$inputs.'0603Product') --support-profile C:\tmp\stm32tk-0600-support\hardware\profile.json --support-manifest C:\tmp\stm32tk-0600-support\hardware\manifest.json --firmware-0400 C:\tmp\stm32tk-0600-support\hardware\firmware-0400.bin --firmware-0600 C:\tmp\stm32tk-0600-support\hardware\firmware-0600.bin --output $hardwareInputPath --digest-output "$hardwareInputPath.sha256"
  if ($LASTEXITCODE -ne 0) { throw 'hardware campaign input construction failed' }
  $env:STM32TK_0600_HARDWARE_INPUT = $hardwareInputPath
  $env:STM32TK_0600_HARDWARE_CAMPAIGN_ID = $campaignId
  $env:STM32TK_0600_HARDWARE_INPUT_SHA256 = (Get-Content -LiteralPath "$hardwareInputPath.sha256" -Raw).Trim()
  Write-Host "STM32TK_0600_HARDWARE_INPUT=$hardwareInputPath"
  Write-Host "STM32TK_0600_HARDWARE_CAMPAIGN_ID=$campaignId"
  Write-Host "STM32TK_0600_HARDWARE_INPUT_SHA256=$($env:STM32TK_0600_HARDWARE_INPUT_SHA256)"
  $expectedHardwareCampaignId = $campaignId
  $expectedHardwareDigest = [string]$env:STM32TK_0600_HARDWARE_INPUT_SHA256
} elseif ($expectedHardwareCampaignId -notmatch '\A[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\z' -or $expectedHardwareDigest -notmatch '\A[0-9a-f]{64}\z') {
  throw 'hardware campaign resume requires its exact recorded campaign ID and digest'
}
$hardwareInputPath = ConvertTo-CanonicalAbsolutePath -Path $hardwareInputPath -Name 'hardware campaign input path'
$hardwareBytes = [IO.File]::ReadAllBytes($hardwareInputPath)
$hardwareDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($hardwareBytes) | ForEach-Object ToString x2) -join ''
if ($hardwareDigest -cne (Get-Content -LiteralPath "$hardwareInputPath.sha256" -Raw).Trim() -or $hardwareDigest -cne $expectedHardwareDigest) { throw 'hardware campaign input digest mismatch' }
$hardwareInput = [Text.Encoding]::UTF8.GetString($hardwareBytes) | ConvertFrom-Json
$hardwareFields = 'schema','campaign_id','created_at_utc','generator_code_head','evidence_owner','board_id','board_revision','mcu_part','mcu_uid_hash','probe_model','probe_serial_hash','uart_adapter_model','uart_serial_hash','power_identity','transports','support_profile','support_manifest','firmware_0400','firmware_0600'
if ((@($hardwareInput.psobject.Properties.Name) -join "`n") -cne ($hardwareFields -join "`n") -or $hardwareInput.schema -cne 'stm32-hardware-campaign-inputs/1' -or $hardwareInput.campaign_id -cne $expectedHardwareCampaignId -or $hardwareInput.generator_code_head -cne [string]$inputs.'0603Product') { throw 'hardware campaign binding mismatch' }
Assert-Task1VerifierUnchanged
py -3.12 $ledgerBuilder release-ledger --inputs $inputPath --hardware-inputs $hardwareInputPath --output $ledgerPath --digest-output $ledgerDigestPath
if ($LASTEXITCODE -ne 0) { throw 'release ledger construction failed' }
$ledgerBytes = [IO.File]::ReadAllBytes($ledgerPath)
$actualLedgerDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($ledgerBytes) | ForEach-Object ToString x2) -join ''
$expectedLedgerDigest = (Get-Content -LiteralPath $ledgerDigestPath -Raw).Trim()
if ($actualLedgerDigest -cne $expectedLedgerDigest -or $actualLedgerDigest -notmatch '\A[0-9a-f]{64}\z') { throw 'release ledger digest mismatch' }
Assert-Task1VerifierUnchanged
py -3.12 $ledgerBuilder verify-release-ledger --ledger $ledgerPath --digest $ledgerDigestPath --software-input $inputPath --hardware-input $hardwareInputPath
if ($LASTEXITCODE -ne 0) { throw 'recursive release ledger verification failed' }
$ledgerBytes = [IO.File]::ReadAllBytes($ledgerPath)
$postVerifyLedgerDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($ledgerBytes) | ForEach-Object ToString x2) -join ''
if ($postVerifyLedgerDigest -cne $actualLedgerDigest) { throw 'release ledger changed after recursive verification' }
$ledger = [Text.Encoding]::UTF8.GetString($ledgerBytes) | ConvertFrom-Json
$ledgerFields = 'schema','repositoryUrl','programBase','0400Product','0400Report','0601Product','0601Report','0602Product','0602Report','0603Product','governance','softwareInput','hardwareInput','hardware','artifacts'
if ((@($ledger.psobject.Properties.Name) -join "`n") -cne ($ledgerFields -join "`n") -or $ledger.schema -cne 'stm32-release-ledger/1') { throw 'release ledger schema mismatch' }
if ($ledger.softwareInput.path -cne [IO.Path]::GetFullPath($inputPath) -or $ledger.softwareInput.bytes -ne $inputBytes.Length -or $ledger.softwareInput.sha256 -cne $inputDigest) { throw 'release ledger software input binding mismatch' }
if ($ledger.hardwareInput.path -cne $hardwareInputPath -or $ledger.hardwareInput.bytes -ne $hardwareBytes.Length -or $ledger.hardwareInput.sha256 -cne $hardwareDigest) { throw 'release ledger hardware input binding mismatch' }
$shaNames = '0601Product','0601Report','0602Product','0602Report','0603Product'
foreach ($name in $shaNames) {
    $value = [string]$ledger.$name
    if ($value -notmatch '\A[0-9a-f]{40}\z' -or (git -C $sourceRepo rev-parse $value).Trim() -cne $value) { throw "invalid $name" }
}
git -C $sourceRepo merge-base --is-ancestor bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f $ledger.'0601Product'
git -C $sourceRepo diff-tree --no-commit-id --name-only -r $ledger.'0601Report'
git -C $sourceRepo diff-tree --no-commit-id --name-only -r $ledger.'0602Report'
git -C $sourceRepo merge-base --is-ancestor $ledger.'0602Report' $ledger.'0603Product'
```

On first entry all three `STM32TK_0600_HARDWARE_INPUT*` variables are unset and the builder refuses
an existing campaign root/output. After an interruption the exact printed path, campaign ID, and
digest must all be explicitly restored; the sidecar, schema, campaign ID, creation record,
generator CodeHead, and every artifact digest are
revalidated before reuse; no newest-file search or arbitrary pre-existing file is accepted. The
`hardware-campaign-inputs` mode extracts the named evidence owner, board/revision, MCU/hashed
UID, probe model/hashed serial, UART adapter/hashed serial, power identity, exact four-transport
inventory, support profile/manifest, and distinct 0400/0600 firmware path/bytes/SHA-256/build IDs;
it writes a closed create-new canonical object and refuses absent or placeholder identity. The
`release-ledger` mode accepts no unknown field in either input, verifies every declared artifact against the
input path/bytes/digest and repository identity, validates every fixed SHA, sorts all artifact
entries by POSIX-relative path, and writes canonical UTF-8 JSON plus its lowercase SHA-256 sidecar
with create-new semantics. Expected: each ancestry check exits zero; each 0.6 report tree lists
exactly one implementation report, and the ledger can be created from a clean environment where no
ledger previously existed.

- [ ] Record specification owner, implementer, reviewer, module branches/PRs if any, exact remote
  state, remote actions (none unless separately authorized), current-task hardware action
  authorizations, and bounded overrides (none unless explicitly restated by the user). Load the
  feasibility report and record the Codex Windows evidence-owner ID, the user physical-hardware
  evidence-owner ID, the exact Windows host/browser profile, and the pending board/MCU/probe/UART/
  RTT/semihosting/power/firmware profile fields. Those hardware fields must be closed before Task 3.

- [ ] Audit tracked/untracked, committed/uncommitted, pushed/unpushed state for the source workspace
  before creating an acceptance worktree. Preserve unrelated state and never clean/delete it.

- [ ] Require the offline advisory snapshot to record source/database version/generated UTC/digest
  and be no older than seven calendar days. If stale, the named support owner may refresh only that
  external support-manifest segment before the ledger freezes. Record old/new segment digests and
  prove every other support entry unchanged; do not change dependencies/locks or use a network
  audit as release evidence.

- [ ] Hash the feasibility profile/report, four design specs, four implementation plans, gate and
  performance catalogs, controllers, verifier, dependency locks, source inventory, platform
  support manifests, and firmware fixture into `release-ledger.json` in the external evidence root.

## Task 2: Create a clean isolated final worktree

**Files:** none in the repository.

- [ ] In one guarded PowerShell process, load and validate the ledger, generate a GUID `finalRunId`,
  derive all paths from the exact SHAs/run ID, and write an immutable execution context. Tasks 2--5
  reuse the in-memory `$ctx`; after an interruption, set `$env:STM32TK_0600_CONTEXT` to the exact
  context path printed here and reload it. Never reconstruct a context by selecting the newest file.

```powershell
$ledgerPath = 'C:\tmp\stm32tk-0600-support\release-ledger.json'
$ledgerDigestPath = "$ledgerPath.sha256"
$ledgerBytes = [IO.File]::ReadAllBytes($ledgerPath)
$ledgerDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($ledgerBytes) | ForEach-Object ToString x2) -join ''
if ($ledgerDigest -cne (Get-Content -LiteralPath $ledgerDigestPath -Raw).Trim()) { throw 'release ledger digest mismatch' }
$inputPath = 'C:\tmp\stm32tk-0600-support\final-release-inputs.json'
$inputBytes = [IO.File]::ReadAllBytes($inputPath)
$inputDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($inputBytes) | ForEach-Object ToString x2) -join ''
if ($inputDigest -cne (Get-Content -LiteralPath "$inputPath.sha256" -Raw).Trim()) { throw 'software input digest mismatch' }
$inputs = [Text.Encoding]::UTF8.GetString($inputBytes) | ConvertFrom-Json
$sourceRepo = [IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim())
$bootstrapCodeHead = [string]$inputs.'0603Product'
if ($bootstrapCodeHead -notmatch '\A[0-9a-f]{40}\z' -or (git -C $sourceRepo rev-parse HEAD).Trim() -cne $bootstrapCodeHead -or (git -C $sourceRepo remote get-url origin).Trim() -cne 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git' -or (git -C $sourceRepo status --porcelain=v1 --untracked-files=all)) { throw 'Task 2 bootstrap worktree mismatch' }
$verifier = Join-Path $sourceRepo 'tools\release\verify_0600_release.py'
$pathContract = Join-Path $sourceRepo 'tools\release\path_contract_0600.ps1'
$bootstrapBlobs = @{}
foreach ($pair in @(@('tools/release/verify_0600_release.py',$verifier),@('tools/release/path_contract_0600.ps1',$pathContract))) {
  $committed = (git -C $sourceRepo rev-parse "$bootstrapCodeHead`:$($pair[0])").Trim()
  $working = (git -C $sourceRepo hash-object -- $pair[1]).Trim()
  if ($committed -notmatch '\A[0-9a-f]{40}\z' -or $working -cne $committed) { throw "bootstrap file differs from CodeHead: $($pair[0])" }
  $bootstrapBlobs[$pair[0]] = $committed
}
. $pathContract
$hardwareInputPath = ConvertTo-CanonicalAbsolutePath -Path ([string]$env:STM32TK_0600_HARDWARE_INPUT) -Name 'hardware campaign input path'
$workingVerifier = (git -C $sourceRepo hash-object -- $verifier).Trim()
if ($LASTEXITCODE -ne 0 -or $workingVerifier -cne $bootstrapBlobs['tools/release/verify_0600_release.py']) { throw 'release verifier changed before context-creation verification' }
py -3.12 $verifier verify-release-ledger --ledger $ledgerPath --digest $ledgerDigestPath --software-input $inputPath --hardware-input $hardwareInputPath
if ($LASTEXITCODE -ne 0) { throw 'recursive release ledger verification failed before context creation' }
$ledgerBytes = [IO.File]::ReadAllBytes($ledgerPath)
if ((([Security.Cryptography.SHA256]::Create().ComputeHash($ledgerBytes) | ForEach-Object ToString x2) -join '') -cne $ledgerDigest) { throw 'release ledger changed after recursive verification' }
$ledger = [Text.Encoding]::UTF8.GetString($ledgerBytes) | ConvertFrom-Json
$ledgerFields = 'schema','repositoryUrl','programBase','0400Product','0400Report','0601Product','0601Report','0602Product','0602Report','0603Product','governance','softwareInput','hardwareInput','hardware','artifacts'
if ((@($ledger.psobject.Properties.Name) -join "`n") -cne ($ledgerFields -join "`n") -or $ledger.schema -cne 'stm32-release-ledger/1') { throw 'release ledger schema mismatch' }
foreach ($inputRef in $ledger.softwareInput,$ledger.hardwareInput) {
  $refBytes = [IO.File]::ReadAllBytes([string]$inputRef.path)
  $refDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash($refBytes) | ForEach-Object ToString x2) -join ''
  if ($refBytes.Length -ne $inputRef.bytes -or $refDigest -cne $inputRef.sha256 -or $refDigest -cne (Get-Content -LiteralPath "$($inputRef.path).sha256" -Raw).Trim()) { throw 'release ledger source input mismatch' }
}
if ((git -C $sourceRepo remote get-url origin).Trim() -cne [string]$ledger.repositoryUrl) { throw 'source repository identity mismatch' }
$codeHead = [string]$ledger.'0603Product'
if ($codeHead -notmatch '\A[0-9a-f]{40}\z' -or (git -C $sourceRepo rev-parse $codeHead).Trim() -cne $codeHead) { throw 'invalid 0603 CodeHead' }
$finalRunId = [guid]::NewGuid().ToString('D')
$shortCodeHead = $codeHead.Substring(0, 7)
$worktree0600 = "C:\tmp\stm32tk-0600-final-$shortCodeHead"
$worktree0400 = 'C:\tmp\stm32tk-0400-hardware-96966c4'
$runRoot = "C:\tmp\stm32tk-0600-final-$finalRunId"
foreach ($path in $worktree0600,$worktree0400,$runRoot) { if (Test-Path -LiteralPath $path) { throw "path already exists: $path" } }
git -C $sourceRepo worktree add --detach $worktree0600 $codeHead
git -C $sourceRepo worktree add --detach $worktree0400 96966c461e7e11bff965027d8d498dd40ea5fd55
New-Item -ItemType Directory -Path $runRoot | Out-Null
$softwareInputPath = [string]$ledger.softwareInput.path
$softwareInputDigest = [string]$ledger.softwareInput.sha256
$hardwareInputPath = [string]$ledger.hardwareInput.path
$hardwareInputDigest = [string]$ledger.hardwareInput.sha256
$hardwareCampaignId = [string]$ledger.hardware.campaign_id
$ctx = [pscustomobject]@{ schemaVersion=1; repositoryUrl=[string]$ledger.repositoryUrl; ledgerPath=$ledgerPath; ledgerDigest=$ledgerDigest; softwareInputPath=$softwareInputPath; softwareInputDigest=$softwareInputDigest; hardwareInputPath=$hardwareInputPath; hardwareInputDigest=$hardwareInputDigest; hardwareCampaignId=$hardwareCampaignId; finalRunId=$finalRunId; codeHead0600=$codeHead; codeHead0400='96966c461e7e11bff965027d8d498dd40ea5fd55'; worktree0600=$worktree0600; worktree0400=$worktree0400; runRoot=$runRoot }
$contextPath = Join-Path $runRoot 'execution-context.json'
[IO.File]::WriteAllText($contextPath, ($ctx | ConvertTo-Json -Depth 4 -Compress), (New-Object Text.UTF8Encoding($false)))
$contextDigestPath = "$contextPath.sha256"
$contextDigest = ([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($contextPath)) | ForEach-Object ToString x2) -join ''
[IO.File]::WriteAllText($contextDigestPath, "$contextDigest`n", (New-Object Text.UTF8Encoding($false)))
(Get-Item -LiteralPath $contextPath).IsReadOnly = $true
(Get-Item -LiteralPath $contextDigestPath).IsReadOnly = $true
$env:STM32TK_0600_CONTEXT = $contextPath
$ctx
git -C $ctx.worktree0600 rev-parse HEAD
git -C $ctx.worktree0600 status --porcelain=v1 --untracked-files=all
git -C $ctx.worktree0400 rev-parse HEAD
git -C $ctx.worktree0400 status --porcelain=v1 --untracked-files=all
```

Expected in both worktrees: the respective exact full SHA and no status output.

Every new PowerShell process in Tasks 2--6 first defines and calls this exact loader. No command
may trust `$env:STM32TK_0600_CONTEXT` or a field parsed from it before the byte digest passes:

```powershell
function Import-0600ExecutionContext {
  param([Parameter(Mandatory=$true)][string]$Path)
  $absolute = [IO.Path]::GetFullPath($Path)
  if ($absolute -cne $Path) { throw 'execution context path is not canonical absolute' }
  $digestPath = "$absolute.sha256"
  $bytes = [IO.File]::ReadAllBytes($absolute)
  $actual = ([Security.Cryptography.SHA256]::Create().ComputeHash($bytes) | ForEach-Object ToString x2) -join ''
  if ($actual -cne (Get-Content -LiteralPath $digestPath -Raw).Trim()) { throw 'execution context digest mismatch' }
  $value = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
  $expectedNames = 'schemaVersion','repositoryUrl','ledgerPath','ledgerDigest','softwareInputPath','softwareInputDigest','hardwareInputPath','hardwareInputDigest','hardwareCampaignId','finalRunId','codeHead0600','codeHead0400','worktree0600','worktree0400','runRoot'
  if ((@($value.psobject.Properties.Name) -join "`n") -cne ($expectedNames -join "`n")) { throw 'execution context schema mismatch' }
  if ($value.schemaVersion -ne 1 -or [string]$value.finalRunId -notmatch '\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\z') { throw 'execution context identity mismatch' }
  foreach ($sha in [string]$value.codeHead0600,[string]$value.codeHead0400) { if ($sha -notmatch '\A[0-9a-f]{40}\z') { throw 'execution context SHA mismatch' } }
  if ([IO.Path]::GetFullPath([string]$value.ledgerPath) -cne [string]$value.ledgerPath) { throw 'ledger path is not canonical absolute' }
  foreach ($inputName in 'softwareInput','hardwareInput') {
    $inputPath = [string]$value."$($inputName)Path"
    $expectedDigest = [string]$value."$($inputName)Digest"
    if ([IO.Path]::GetFullPath($inputPath) -cne $inputPath -or $expectedDigest -notmatch '\A[0-9a-f]{64}\z') { throw "$inputName context binding is invalid" }
    $inputActual = ([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($inputPath)) | ForEach-Object ToString x2) -join ''
    if ($inputActual -cne $expectedDigest -or $inputActual -cne (Get-Content -LiteralPath "$inputPath.sha256" -Raw).Trim()) { throw "$inputName context digest mismatch" }
  }
  if ([string]$value.hardwareCampaignId -notmatch '\A[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\z') { throw 'hardware campaign context identity mismatch' }
  $ledgerActual = ([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes([string]$value.ledgerPath)) | ForEach-Object ToString x2) -join ''
  if ($ledgerActual -cne [string]$value.ledgerDigest -or $ledgerActual -cne (Get-Content -LiteralPath "$($value.ledgerPath).sha256" -Raw).Trim()) { throw 'bound ledger mismatch' }
  if ([IO.Path]::GetFullPath([string]$value.worktree0600) -cne "C:\tmp\stm32tk-0600-final-$(([string]$value.codeHead0600).Substring(0,7))" -or
      [IO.Path]::GetFullPath([string]$value.worktree0400) -cne 'C:\tmp\stm32tk-0400-hardware-96966c4' -or
      [IO.Path]::GetFullPath([string]$value.runRoot) -cne "C:\tmp\stm32tk-0600-final-$($value.finalRunId)") { throw 'execution context path derivation mismatch' }
  foreach ($pair in @(@([string]$value.worktree0600,[string]$value.codeHead0600),@([string]$value.worktree0400,[string]$value.codeHead0400))) {
    if ((git -C $pair[0] rev-parse HEAD).Trim() -cne $pair[1] -or (git -C $pair[0] status --porcelain=v1 --untracked-files=all)) { throw 'bound worktree identity/cleanliness mismatch' }
    if ((git -C $pair[0] remote get-url origin).Trim() -cne [string]$value.repositoryUrl) { throw 'bound repository URL mismatch' }
  }
  $verifier = Join-Path ([string]$value.worktree0600) 'tools\release\verify_0600_release.py'
  $committedVerifier = (git -C ([string]$value.worktree0600) rev-parse "$($value.codeHead0600)`:tools/release/verify_0600_release.py").Trim()
  $workingVerifier = (git -C ([string]$value.worktree0600) hash-object -- $verifier).Trim()
  if ($committedVerifier -notmatch '\A[0-9a-f]{40}\z' -or $workingVerifier -cne $committedVerifier) { throw 'release verifier differs from frozen CodeHead' }
  $null = & py -3.12 $verifier verify-release-ledger --ledger ([string]$value.ledgerPath) --digest "$($value.ledgerPath).sha256" --software-input ([string]$value.softwareInputPath) --hardware-input ([string]$value.hardwareInputPath)
  if ($LASTEXITCODE -ne 0) { throw 'recursive release ledger verification failed during context load' }
  $verifiedLedgerBytes = [IO.File]::ReadAllBytes([string]$value.ledgerPath)
  $ledgerAfterVerify = ([Security.Cryptography.SHA256]::Create().ComputeHash($verifiedLedgerBytes) | ForEach-Object ToString x2) -join ''
  if ($ledgerAfterVerify -cne $ledgerActual) { throw 'release ledger changed during context load' }
  $ledgerValue = [Text.Encoding]::UTF8.GetString($verifiedLedgerBytes) | ConvertFrom-Json
  if ($ledgerValue.softwareInput.path -cne [string]$value.softwareInputPath -or $ledgerValue.softwareInput.sha256 -cne [string]$value.softwareInputDigest -or $ledgerValue.hardwareInput.path -cne [string]$value.hardwareInputPath -or $ledgerValue.hardwareInput.sha256 -cne [string]$value.hardwareInputDigest -or $ledgerValue.hardware.campaign_id -cne [string]$value.hardwareCampaignId) { throw 'release ledger nested bindings differ from execution context' }
  return $value
}
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
```

The loader is repeated after every interruption and before every readiness, final, recovery,
reconciliation, or report action. Tests mutate each context SHA, path, run root, run ID, ledger
digest, software/hardware input path or digest, hardware campaign ID, nested ledger reference, and
sidecar; swap valid inputs across contexts; mutate the verifier after Task 2's first check but before
process creation; mutate the ledger after verifier PASS but before digest/parse; and prove rejection
before any gate or hardware access. The nested comparison parses the exact byte array whose digest
was checked, never a second disk read.

- [ ] Verify the worktree's Git common directory/repository identity, no symlink/junction/reparse
  point within the tracked tree, accepted-base ancestry, `git diff --check`, expected path list,
  exact source inventory, package/dist manifest closure, dependency lock digests, and no extra
  tracked release artifacts.

- [ ] Under the context's new run root, create separate `readiness/windows`,
  `readiness/hardware-0400`, `readiness/hardware-0600`, `results/windows`,
  `results/hardware-0400`, and `results/hardware-0600` shard roots; refuse any existing file.
  Record absolute tools and versions for Git, shells, Python 3.10/3.12, Node, npm, pip/build,
  browsers, probe tools, and hardware identifiers. Every shard metadata file must bind the same
  `finalRunId`, CodeHead, final gate/performance catalog digests, dependency locks, and the correct
  platform support-manifest digest.

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$relativeRoots = 'readiness\windows','readiness\hardware-0400','readiness\hardware-0600','results\windows','results\hardware-0400','results\hardware-0600'
foreach ($relative in $relativeRoots) {
    $path = Join-Path $ctx.runRoot $relative
    if (Test-Path -LiteralPath $path) { throw "shard root already exists: $path" }
    New-Item -ItemType Directory -Path $path | Out-Null
}
```

- [ ] Verify the performance owner matches the frozen Ryzen 7 5800U/16 GB/WDC PC SN530 NVMe/
  Windows 11 x64 High performance reference profile. Record the exact OS build, AC/battery,
  antivirus state, free disk, and background-load preflight. If a calibrated component differs,
  require the pre-implementation prior-CodeHead calibration evidence; do not calibrate now.

## Task 3: Run non-executing final readiness

**Files:** none.

- [ ] From the frozen catalog, verify that final gate IDs cover all of these partitions without
  executing their test bodies:

  1. whole-ancestry Git/source/scope/inventory/immutability/clean-tree;
  2. Windows CPython 3.10/3.12 complete Toolkit and Monitor suites;
  3. changed product file branch coverage >=90%, with controller tests excluded;
  4. all unchanged 0.5 performance thresholds plus 0601/0602/0603 absolute and <=15% regressions;
  5. Node typecheck/E2E typecheck/lint/unit/a11y/coverage/build/dist/audit;
  6. Chromium both viewports/security/a11y/isolation/five-minute performance;
  7. managed Chromium core flows and both required Windows viewports;
  8. four real Target transports and real failed-before/fixed-after diagnostic/Monitor scenario;
  9. deterministic evidence/diagnostic/analysis bundles and corruption/security mutations;
  10. two-workspace isolation across Toolkit, Probe, Monitor, browser, evidence, and exports;
  11. reproducible wheels, offline dual-Python install/smoke, managed launchers, plugin/Skills;
  12. version/schema/docs/non-goal/release artifact inventories.

- [ ] Run readiness independently for the clean Windows and hardware shards. It may run Git/source/
  inventory checks, controller/verifier self-tests, `pytest --collect-only`, Vitest/Playwright test
  listing, support-manifest verification, owner/profile availability, evidence-root emptiness/
  writability, hardware identity/connectivity, and offline dependency availability. It must not run
  a product test body, browser flow, performance workload, build, flash, or diagnostic action.

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$controllerRoot = [IO.Path]::GetFullPath([string]$ctx.worktree0600)
$verifier = Join-Path $controllerRoot 'tools\release\verify_0600_release.py'
$catalog = Join-Path $controllerRoot 'tools\release\gates_0600.json'
$performance = Join-Path $controllerRoot 'tools\release\performance_0600.json'
$supportProfile = 'C:\tmp\stm32tk-0600-support\feasibility\profile.json'
foreach ($path in $verifier,$catalog,$performance,$supportProfile) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "missing frozen readiness input: $path" } }
py -3.12 $verifier final-readiness --shard windows --repo $ctx.worktree0600 --expected-code-head $ctx.codeHead0600 --catalog $catalog --performance $performance --support-profile $supportProfile --final-run-id $ctx.finalRunId --evidence-root (Join-Path $ctx.runRoot 'readiness\windows') --result-root (Join-Path $ctx.runRoot 'results\windows')
py -3.12 $verifier final-readiness --shard hardware-0400 --repo $ctx.worktree0400 --expected-code-head $ctx.codeHead0400 --controller-code-head $ctx.codeHead0600 --catalog $catalog --performance $performance --support-profile $supportProfile --final-run-id $ctx.finalRunId --evidence-root (Join-Path $ctx.runRoot 'readiness\hardware-0400') --result-root (Join-Path $ctx.runRoot 'results\hardware-0400')
py -3.12 $verifier final-readiness --shard hardware-0600 --repo $ctx.worktree0600 --expected-code-head $ctx.codeHead0600 --controller-code-head $ctx.codeHead0600 --catalog $catalog --performance $performance --support-profile $supportProfile --final-run-id $ctx.finalRunId --evidence-root (Join-Path $ctx.runRoot 'readiness\hardware-0600') --result-root (Join-Path $ctx.runRoot 'results\hardware-0600')
```

- [ ] Require exact CodeHead/catalog/performance/dependency/support/tool/profile equality, exact
  collect-only node inventory with no missing/extra/duplicate/deselected/skip/xfail required node,
  clean trees, empty shard result directories, available named owners, connected matching hardware,
  and the ability to prepare and consume an action-specific authorization. Readiness must not create
  action digests or authorizations: those bind live target state/revision and are prepared one at a time.
  Record readiness metadata separately from final gate results; it cannot satisfy a final product gate.

- [ ] If readiness fails, stop before final. An environment-only mismatch may be corrected outside
  the repository and readiness repeated. Any repository correction returns to the owning module,
  creates a new CodeHead, and requires candidate plus readiness again.

- [ ] Only after all three readiness shards PASS, freeze the recorded product SHA as the sole final
  `0.6.0` CodeHead. From this point no repository file may change before final reconciliation.

## Task 4: Run one logical complete final matrix

**Files:** none; controller outputs only to the external evidence root.

- [ ] Confirm immediately before launch: both isolated worktrees clean, product SHA exact, shard
  result directories empty except immutable ledger/readiness inputs, no coverage environment
  leakage, local package/browser/probe support present, named real hardware connected, and no
  remote Git/network action in controller commands.

- [ ] Run the deferred 0.4 real-probe gates first in the exact 0.4 worktree through the frozen
  0.6 hardware controller: bounded discovery,
  attach/non-halting reads, flash/readback, external-debug handoff/reacquire, typed sample/register/
  Fault, and CLI/MCP hardware workflows. Bind every result to the 0.4 SHA and its own firmware and
  single-use authorization; never claim that this run tested 0.6.

For each contract, invoke `-PrepareAction` to materialize only the next action and exit. Read the
returned nonce/digest/expiry/checkpoint, stop for the user's explicit authorization of that exact
action, then invoke `-ExecuteAction`. Success, failure, refusal, or expiry consumes the prepared
action. Repeat only after the previous result is retained. The following block shows one action;
execute the same pair for each subsequent action and then repeat with contract `0600` and its own
worktree/result root:

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$controllerRoot = [IO.Path]::GetFullPath([string]$ctx.worktree0600)
$hardwareRunner = Join-Path $controllerRoot 'tools\release\run_0600_hardware.ps1'
if (-not (Test-Path -LiteralPath $hardwareRunner -PathType Leaf)) { throw 'missing frozen hardware runner' }
$contract = '0400'
$testedRepo = $ctx.worktree0400
$testedCodeHead = $ctx.codeHead0400
$resultRoot = Join-Path $ctx.runRoot 'results\hardware-0400'
$prepared = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hardwareRunner -Contract $contract -Repo $testedRepo -ExpectedCodeHead $testedCodeHead -FinalRunId $ctx.finalRunId -EvidenceRoot $resultRoot -PrepareAction | ConvertFrom-Json)
if ($prepared.nonce -notmatch '\A[0-9a-f]{64}\z' -or $prepared.action_digest -notmatch '\A[0-9a-f]{64}\z') { throw 'invalid prepared action' }
# STOP HERE. Obtain explicit user authorization for exactly $prepared.action_digest before continuing.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hardwareRunner -Contract $contract -Repo $testedRepo -ExpectedCodeHead $testedCodeHead -FinalRunId $ctx.finalRunId -EvidenceRoot $resultRoot -ExecuteAction -Nonce $prepared.nonce -ActionDigest $prepared.action_digest -Authorized
```

- [ ] Run the 0.6 hardware gates in the exact 0.6 worktree: mailbox, RTT, UART, semihosting,
  Target runner, and failed-before/fixed-after diagnostic plus Monitor assertion. Bind every result
  to the 0.6 SHA and a fresh firmware/action chain. The two campaigns may share the selected board,
  probe, and test window but never share a PASS record.

For contract `0600`, set `$contract='0600'`, `$testedRepo=$ctx.worktree0600`,
`$testedCodeHead=$ctx.codeHead0600`, and `$resultRoot=Join-Path $ctx.runRoot
'results\hardware-0600'`, then use the same prepare/authorize/execute dialogue. An authorization
from `0400`, another action, or an earlier target revision is invalid.

- [ ] Start the Windows software shard only when resource-disjoint from the hardware work. Serialize
  hardware against absolute Windows performance when it shares the host/probe/board/UART/port. All
  commands use the same `finalRunId`, CodeHead, gate/performance catalog digests, dependency locks,
  support profile, and immutable run root:

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$controllerRoot = [IO.Path]::GetFullPath([string]$ctx.worktree0600)
$finalRunner = Join-Path $controllerRoot 'tools\release\run_0600_final.ps1'
$catalog = Join-Path $controllerRoot 'tools\release\gates_0600.json'
$performance = Join-Path $controllerRoot 'tools\release\performance_0600.json'
$supportProfile = 'C:\tmp\stm32tk-0600-support\feasibility\profile.json'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $finalRunner -Shard windows -Repo $ctx.worktree0600 -FinalRunId $ctx.finalRunId -EvidenceRoot (Join-Path $ctx.runRoot 'results\windows') -ExpectedCodeHead $ctx.codeHead0600 -Catalog $catalog -Performance $performance -SupportProfile $supportProfile
```

Expected: each fail-fast shard exits zero and says PASS; their union contains every final gate and
exact node once. The 120-minute wall-clock target assumes platform parallelism and only emits a
warning if exceeded.

- [ ] On a nonzero shard exit, preserve every file and classify from primary evidence. For an
  eligible external event only, a reviewer records `RECOVERABLE_INFRA_ERROR` and may resume that
  affected shard once; do not restart completed gates or any other shard:

Windows recovery uses `run_0600_final.ps1 -ResumeFinalRun` with every original input, the unchanged
`$ctx`, the wrapper-owned final checkpoint, and the retained recovery record. Hardware recovery
uses the matching hardware controller and the same closed recovery schema:

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$controllerRoot = [IO.Path]::GetFullPath([string]$ctx.worktree0600)
$finalRunner = Join-Path $controllerRoot 'tools\release\run_0600_final.ps1'
$hardwareRunner = Join-Path $controllerRoot 'tools\release\run_0600_hardware.ps1'
$catalog = Join-Path $controllerRoot 'tools\release\gates_0600.json'
$performance = Join-Path $controllerRoot 'tools\release\performance_0600.json'
$supportProfile = 'C:\tmp\stm32tk-0600-support\feasibility\profile.json'
$windowsRoot = Join-Path $ctx.runRoot 'results\windows'
$windowsCheckpoint = Join-Path $windowsRoot 'final-run-checkpoint.json'
$windowsRecovery = Join-Path $windowsRoot 'recovery-classification.json'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $finalRunner -ResumeFinalRun -Shard windows -Repo $ctx.worktree0600 -FinalRunId $ctx.finalRunId -EvidenceRoot $windowsRoot -ExpectedCodeHead $ctx.codeHead0600 -Catalog $catalog -Performance $performance -SupportProfile $supportProfile -Checkpoint $windowsCheckpoint -RecoveryRecord $windowsRecovery
$contract = '0400'
$testedRepo = $ctx.worktree0400
$testedCodeHead = $ctx.codeHead0400
$resultRoot = Join-Path $ctx.runRoot 'results\hardware-0400'
$recoveryPath = Join-Path $resultRoot 'recovery-classification.json'
$recovery = Get-Content -LiteralPath $recoveryPath -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace([string]$recovery.checkpoint)) { throw 'missing recovery checkpoint' }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $hardwareRunner -Contract $contract -Repo $testedRepo -ExpectedCodeHead $testedCodeHead -FinalRunId $ctx.finalRunId -EvidenceRoot $resultRoot -ResumeContract -Checkpoint $recovery.checkpoint -RecoveryRecord $recoveryPath
```

Use the corresponding `0600` variables for its shard. The hardware runner first validates the
reviewer-authored recovery record, retains the interrupted attempt, and then prepares a fresh next
action; it never reuses an expired/consumed authorization. For `0400`, the resume command carries
`$ctx.codeHead0400`, never the 0.6 CodeHead.

Every recovery record is canonical JSON with exactly `classification`, `event`, `reviewer`,
`recorded_at_utc`, `run_kind`, `run_id`, `code_head`, `checkpoint`, and
`interrupted_attempt_digest`; its values follow the common 0601 schema and its `checkpoint` equals
the command argument. Expected: resumed metadata proves identical inputs, names one enumerated event, records reviewer/UTC,
and retains both attempts. A repeated infrastructure event is BLOCKED. Any deterministic gate
failure is FAIL: do not resume, change thresholds, patch the final worktree, or write a report;
return to the owning module, create a new CodeHead, and repeat candidate/readiness before a new
logical final run.

- [ ] On PASS, verify both worktree statuses are clean and HEADs unchanged. Hash every shard
  summary and retained result/log/screenshot/trace/coverage/performance/wheel/manifest, including
  both attempts and recovery classification when recovery occurred.

## Task 5: Reconcile final evidence and release truth

**Files:** none yet.

- [ ] Independently run the read-only verifier over the final evidence root and frozen catalog:

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$controllerRoot = [IO.Path]::GetFullPath([string]$ctx.worktree0600)
$verifier = Join-Path $controllerRoot 'tools\release\verify_0600_release.py'
$catalog = Join-Path $controllerRoot 'tools\release\gates_0600.json'
$performance = Join-Path $controllerRoot 'tools\release\performance_0600.json'
py -3.12 $verifier final-evidence --repo $ctx.worktree0600 --evidence $ctx.runRoot --final-run-id $ctx.finalRunId --expected-code-head $ctx.codeHead0600 --expected-0400-code-head $ctx.codeHead0400 --catalog $catalog --performance $performance
```

Expected: PASS with zero missing/extra/duplicate gates, nodes, artifacts, hashes, or platforms; all
shards bind one logical run and any recovery has exactly two retained, policy-valid attempts.

- [ ] Recompute SHA-256/bytes for every retained artifact, compare source/package/dist inventories,
  confirm wheel repeatability and offline installed smoke results, and verify before/after clean
  status evidence.

- [ ] Inspect hardware evidence identities: each transport has a real independent run; diagnostic
  before/after identities differ as expected; authorized actions form a single-use chain; final
  Target test and Monitor assertion bind the new firmware.

- [ ] Inspect browser evidence: both required viewports, keyboard workflow, exact security headers,
  DOM/storage/URL/console checks, real second-origin zero requests, axe results, isolation, and
  complete five-minute performance samples are present.

- [ ] Produce external `final-reconciliation.json` and `artifact-inventory.json` with stable sorted
  entries, bytes/SHA-256, ownership, and no credentials/absolute user-private data in shareable
  fields. Include elapsed duration as scheduling evidence only, plus recovery classification and
  both attempt inventories when applicable. A verifier discrepancy changes overall result to FAIL.

## Task 6: Create the report-only acceptance commit

**Files:**

- Create: `docs/codex/returns/STM32TK-0600-EVIDENCE-DIAGNOSTICS/implementation-report.md`

- [ ] Only after final reconciliation PASS, reload and validate the immutable context, verify the
  exact frozen worktree again, and create local branch `codex/STM32TK-0600-RELEASE` at that detached
  product CodeHead. Refuse an existing branch or any HEAD/clean/repository-identity mismatch before
  creating the report. Record accepted base, 0601/0602
  report SHAs, final product CodeHead, scope, per-gate owner/platform/tools/versions/cwd/UTC/command/
  result, performance/coverage values, `finalRunId`, scheduling duration/warnings, recovery attempts
  if any, external evidence relative paths/bytes/SHA-256, and verdict.

- [ ] Do not put the report commit's own SHA, moving commit counts, unverifiable claims, another
  actor's evidence, skipped hardware PASS, or credentials in the report.

- [ ] Validate sole-change and report facts before committing:

```powershell
$ctx = Import-0600ExecutionContext -Path $env:STM32TK_0600_CONTEXT
$reportRepo = [IO.Path]::GetFullPath([string]$ctx.worktree0600)
if ((git -C $reportRepo branch --list codex/STM32TK-0600-RELEASE).Trim()) { throw 'report branch already exists' }
git -C $reportRepo switch -c codex/STM32TK-0600-RELEASE $ctx.codeHead0600
if ((git -C $reportRepo rev-parse HEAD).Trim() -cne $ctx.codeHead0600 -or (git -C $reportRepo remote get-url origin).Trim() -cne [string]$ctx.repositoryUrl) { throw 'report worktree identity mismatch' }
git -C $reportRepo diff --check
git -C $reportRepo status --short
git -C $reportRepo diff --name-only $ctx.codeHead0600
git -C $reportRepo add docs/codex/returns/STM32TK-0600-EVIDENCE-DIAGNOSTICS/implementation-report.md
git -C $reportRepo diff --cached --name-only
git -C $reportRepo diff --cached --check
```

Expected: exactly the one report path and no formatting error.

- [ ] Commit locally:

```powershell
git -C $reportRepo commit -m "docs(STM32TK-0600): record accepted version 0.6.0"
```

- [ ] Verify the new commit's parent is exactly the final product CodeHead, its tree diff is only
  the report, the report still names the parent CodeHead, and the external evidence hashes verify.

## Task 7: Prepare, but do not execute, remote release actions

**Files:** none.

- [ ] Determine current remote default branch and fetch status read-only only if a later user turn
  explicitly authorizes network access. Until then, use the already-recorded remote ledger and do
  not contact GitHub.

- [ ] Prepare a concise proposed action list containing exact source/ref/full SHAs for push,
  PR/merge if needed, `v0.6.0` annotated tag target, and obsolete branch deletions. Treat each as
  pending user authorization, not as implied by acceptance.

- [ ] Confirm the intended tag semantic before execution: the program spec says `v0.6.0` points to
  the accepted head; recommend the report-only acceptance commit so the released tree includes
  the verified report while its parent remains the tested product CodeHead.

- [ ] Stop and ask the user in the new development/release conversation for the exact remote
  action authorization. Do not push, merge, tag, close, or delete anything in this plan.

## Task 8: Handoff package for the new conversation

**Files:** none beyond the already committed design, plans, reports, and product.

- [ ] Provide the repository URL, module/program IDs, program base, full design-plan commit,
  accepted module/report SHAs, final product/report SHAs, branch/worktree state, evidence root
  inventory digest, verdict, and pending remote decisions.

- [ ] State the invariant for resumed work: commits are the cross-machine truth; reconstruct the
  ledger first; never reuse evidence across CodeHeads; preserve unrelated state; no implementation
  correction is authorized unless the user names exact files/behavior.

- [ ] Ensure the handoff does not depend on collapsed commentary or local-only prose. Every product
  requirement and test instruction must be reachable from committed specs/plans/reports and full
  SHAs.

- [ ] End with one of the exact outcomes: `ACCEPTED` and awaiting remote authorization, `FAIL` with
  owning failed gate, or `BLOCKED` with the unavailable required external platform/hardware. Do not
  call the release complete merely because the matrix budget elapsed.
