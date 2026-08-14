> **REWRITE_REQUIRED — DO NOT EXECUTE.**
>
> Superseded by `docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md`; do not execute this split plan or any packet/signature/handoff machinery in it.

# STM32TK-0502 Frontend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the authenticated, strictly typed Preact Monitor frontend core through probe/catalog/group/live/history/export workflows, plus only the bounded browser-cookie compatibility correction required for those workflows.

**Architecture:** A pre-mount fragment bootstrap exchanges the one-time token for the existing HttpOnly cookie, then exact REST and WebSocket adapters validate `stm32-toolkit-monitor/1` payloads and dispatch typed actions into one pure reducer. Prop-only Preact panels consume selectors; modular ECharts receives only bounded finite numeric projections. Python changes are limited to normalized request evidence passed from `service.py` into the §7.3 auth matrix.

**Tech Stack:** bundled Node/npm resolved by Codex workspace dependencies, Preact, strict TypeScript, Vite, modular ECharts, Vitest, Testing Library, axe, Playwright configuration, Python 3.10/3.12, aiohttp, pytest.

## Delivery Ledger

- Module / phase: `STM32TK-0502-MONITOR-UI-RELEASE` / frontend-core implementation slice (the former monolithic Tasks 1–4).
- Product accepted base: `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`.
- Plan integration base / superseded monolithic-plan head: `f124cc233f144303beb6cf52f471c6424518afee`.
- Design authority and specification owner: Codex; `docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md`.
- Implementer and implementation-test owner: Codex subagents under the user's explicit objective-level ownership exception for all `STM32TK-0502` product code and implementation tests; OpenClaw is not an implementer for this objective.
- Reviewer / acceptor: a fresh Codex reviewer in a clean worktree at the returned full frontend-core head.
- Planning branch at authoring time: `codex/STM32TK-0502-MONITOR-UI-RELEASE`; no active PR.
- Remote authority: none. This plan authorizes no push, PR mutation, merge, close, or remote deletion.
- Bounded objective-level ownership exception: Codex subagents own all 0502 product implementation and implementation tests through the final 0502 acceptance verdict; it expires when this objective is accepted, rewritten, or explicitly reassigned. It does not authorize any remote action. The only backend product change in this slice remains the exact auth compatibility unit in Task 7.

## Global Constraints

- The controller first records a clean `PLAN_BUNDLE_HEAD` commit containing all three split plans and the superseded notice in the former monolithic plan. `PLAN_BUNDLE_HEAD` must descend from `f124cc233f144303beb6cf52f471c6424518afee`; it is intentionally supplied at dispatch time and is never hardcoded into a plan that it contains.
- Run Task 1 implementation from a clean isolated worktree whose `HEAD` is exactly the input packet's `PLAN_BUNDLE_HEAD`; preserve unrelated changes and stop if the head, packet signature, ancestry, or bundle inventory differs.
- Preserve every existing route, operation, envelope, request/response field, WebSocket event, history, sampling, storage, and export semantic. Do not change backend DTOs to fit the UI.
- The UI never sends `workspaceId`, `sessionId`, project/data root, target, ELF, SVD, address, backend, operation level, build pin, download path, or filename.
- The UI does not open PyOCD, import a probe backend, manage processes, connect/reconnect a probe automatically, start/resume sampling automatically, create a default/preset/example group, or infer a probe, firmware, target, selector type, member type, element type, offset, pointer, or address.
- Browser persistence is forbidden: no `localStorage`, `sessionStorage`, IndexedDB, Cache API, service worker, telemetry, analytics, remote font, CDN, or non-same-origin request.
- Catalog input is NFC-normalized, at most 128 JavaScript code units, debounced 300 ms, requested with limit 100, and never above the server maximum 256. Query or binding identity changes discard prior results and opaque cursors.
- Bounds: 256 table rows in group order; 8 numeric series; 600 points per series; no more than one chart `setOption` per 100 ms; 35-second heartbeat stale threshold; reconnect backoff `0.5/1/2/4/8` seconds; history page limit at most 10,000 values.
- Interval input and client validation are exactly 100–5000 ms. Start requires connected probe, current group revision, and at least one item.
- Gaps, binding-epoch changes, authoritative binding changes, and run changes clear continuity, reset trend and zoom, and say “view reset”; they never claim a physical MCU reset.
- One item `ERROR` affects only its row. Only a finite JavaScript `number` at `typedValue.value` enters the chart.
- Components never parse envelopes, clients never render, charts never own identity/group state, and `app.tsx` never constructs `fetch` or `WebSocket` directly.
- No 0.6-only AI snapshot/analyze/diagnostic export, comparison/overlay/brush, full quality dashboard/timeline/distribution, annotation/bookmark/marker, or diagnostic hypothesis UI may appear in source, tests, copy, route names, or flags.
- Do not create static-resource serving, committed `ui_dist`, launcher/runtime/plugin/Skill/version-promotion, Playwright fake runtime, release helper, release report, CI, collaboration manifest, OpenClaw artifact, or dispatch automation in this plan. Those belong to later plans.

## Plan Bundle Input Packet and Signature

After all three split plans and the monolithic superseded notice are committed together, the controller creates the dispatch packet from the clean commit with this exact schema. `planBundleHead` is obtained from Git after that commit exists; no split plan contains or predicts it.

```ts
export type PlanBundleInput = {
  schema:"stm32tk-0502-plan-bundle/1";
  repository:"https://github.com/XiaoyaoLinghao/stm32-toolkit.git";
  moduleId:"STM32TK-0502-MONITOR-UI-RELEASE";
  acceptedBase:"bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa";
  planIntegrationBase:"f124cc233f144303beb6cf52f471c6424518afee";
  planBundleHead:string; // exactly 40 lowercase hexadecimal characters, recorded after commit
  frontendPlanPath:"docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md";
  browserEvidencePlanPath:"docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md";
  runtimeReleasePlanPath:"docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md";
  supersededPlanPath:"docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md";
  blobs:readonly [
    {path:"docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md";oid:string},
    {path:"docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md";oid:string},
    {path:"docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md";oid:string},
    {path:"docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md";oid:string}
  ];
};
```

The controller uses the following exact PowerShell from repository root. The packet JSON is written outside the repository; `planBundleSignatureSha256` is the lowercase SHA-256 of the UTF-8 bytes of `packet.json`, not a Git commit field and not a signature embedded back into any plan.

```powershell
$AcceptedBase = 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'
$PlanIntegrationBase = 'f124cc233f144303beb6cf52f471c6424518afee'
$ControllerEvidenceRoot = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) (
  'stm32tk-0502-plan-bundle-' + [guid]::NewGuid().ToString('N')
)))
New-Item -ItemType Directory -LiteralPath $ControllerEvidenceRoot | Out-Null
$PlanBundleHead = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $PlanBundleHead -notmatch '^[0-9a-f]{40}$') { throw 'PLAN_BUNDLE_HEAD is invalid' }
$Dirty = @(& git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $Dirty.Count -ne 0) { throw 'plan bundle worktree must be clean' }
& git merge-base --is-ancestor $PlanIntegrationBase $PlanBundleHead
if ($LASTEXITCODE -ne 0) { throw 'PLAN_BUNDLE_HEAD does not descend from the plan integration base' }
& git merge-base --is-ancestor $AcceptedBase $PlanIntegrationBase
if ($LASTEXITCODE -ne 0) { throw 'plan integration base does not descend from the accepted base' }
$BundlePaths = @(
  'docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md',
  'docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md',
  'docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md',
  'docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md'
)
foreach ($Path in $BundlePaths) {
  & git cat-file -e "${PlanBundleHead}:$Path"
  if ($LASTEXITCODE -ne 0) { throw "plan bundle path is absent: $Path" }
}
$BundleBlobs = @()
foreach ($Path in $BundlePaths) {
  $Oid = (& git rev-parse "${PlanBundleHead}:$Path").Trim()
  if ($LASTEXITCODE -ne 0 -or $Oid -notmatch '^[0-9a-f]{40}$') { throw "plan bundle blob is invalid: $Path" }
  $BundleBlobs += [ordered]@{path=$Path;oid=$Oid}
}
$SupersededText = @(& git show "${PlanBundleHead}:docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md") -join "`n"
if ($LASTEXITCODE -ne 0 -or $SupersededText -notmatch 'SUPERSEDED BY SPLIT PLANS') {
  throw 'monolithic plan lacks the exact superseded notice'
}
$Packet = [ordered]@{
  schema = 'stm32tk-0502-plan-bundle/1'
  repository = 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git'
  moduleId = 'STM32TK-0502-MONITOR-UI-RELEASE'
  acceptedBase = $AcceptedBase
  planIntegrationBase = $PlanIntegrationBase
  planBundleHead = $PlanBundleHead
  frontendPlanPath = $BundlePaths[0]
  browserEvidencePlanPath = $BundlePaths[1]
  runtimeReleasePlanPath = $BundlePaths[2]
  supersededPlanPath = $BundlePaths[3]
  blobs = $BundleBlobs
}
$PacketPath = Join-Path $ControllerEvidenceRoot 'packet.json'
$PacketJson = $Packet | ConvertTo-Json -Compress -Depth 8
[IO.File]::WriteAllText($PacketPath, $PacketJson, [Text.UTF8Encoding]::new($false))
$PacketBytes = [IO.File]::ReadAllBytes($PacketPath)
$Sha256 = [Security.Cryptography.SHA256]::Create()
try { $PacketHash = $Sha256.ComputeHash($PacketBytes) } finally { $Sha256.Dispose() }
$PlanBundleSignatureSha256 = (($PacketHash | ForEach-Object { $_.ToString('x2') }) -join '')
$SignaturePath = $PacketPath + '.sha256'
[IO.File]::WriteAllText($SignaturePath, $PlanBundleSignatureSha256 + "`n", [Text.UTF8Encoding]::new($false))
```

The dispatch input is the repository-external pair `packet.json` and `packet.json.sha256`. The implementer sets `$PlanBundlePacketPath` to the absolute JSON path and runs this PowerShell 5.1-compatible consumer verbatim before Task 1 Step 1:

```powershell
$PlanBundlePacketPath = [IO.Path]::GetFullPath($PlanBundlePacketPath)
$PlanBundleSignaturePath = $PlanBundlePacketPath + '.sha256'
if (-not [IO.File]::Exists($PlanBundlePacketPath) -or -not [IO.File]::Exists($PlanBundleSignaturePath)) {
  throw 'plan bundle packet pair is missing'
}
$Utf8 = New-Object Text.UTF8Encoding($false, $true)
$PacketBytes = [IO.File]::ReadAllBytes($PlanBundlePacketPath)
if ($PacketBytes.Length -ge 3 -and $PacketBytes[0] -eq 0xef -and $PacketBytes[1] -eq 0xbb -and $PacketBytes[2] -eq 0xbf) {
  throw 'plan bundle packet must be UTF-8 without BOM'
}
$PacketText = $Utf8.GetString($PacketBytes)
$SignatureBytes = [IO.File]::ReadAllBytes($PlanBundleSignaturePath)
if ($SignatureBytes.Length -ge 3 -and $SignatureBytes[0] -eq 0xef -and $SignatureBytes[1] -eq 0xbb -and $SignatureBytes[2] -eq 0xbf) {
  throw 'plan bundle signature must be UTF-8 without BOM'
}
$ExpectedSignature = $Utf8.GetString($SignatureBytes).Trim()
if ($ExpectedSignature -notmatch '^[0-9a-f]{64}$') { throw 'plan bundle signature is invalid' }
$Sha256 = [Security.Cryptography.SHA256]::Create()
try { $ActualSignature = (($Sha256.ComputeHash($PacketBytes) | ForEach-Object { $_.ToString('x2') }) -join '') }
finally { $Sha256.Dispose() }
if ($ActualSignature -cne $ExpectedSignature) { throw 'plan bundle signature mismatch' }
try { $PlanPacket = $PacketText | ConvertFrom-Json } catch { throw 'plan bundle JSON is invalid' }
$ExpectedProperties = @('schema','repository','moduleId','acceptedBase','planIntegrationBase','planBundleHead',
 'frontendPlanPath','browserEvidencePlanPath','runtimeReleasePlanPath','supersededPlanPath','blobs')
$ActualProperties = @($PlanPacket.PSObject.Properties.Name)
if (($ActualProperties -join "`n") -cne ($ExpectedProperties -join "`n")) { throw 'plan bundle schema keys or order differ' }
$ExpectedLiterals = [ordered]@{schema='stm32tk-0502-plan-bundle/1';repository='https://github.com/XiaoyaoLinghao/stm32-toolkit.git';
 moduleId='STM32TK-0502-MONITOR-UI-RELEASE';acceptedBase='bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa';
 planIntegrationBase='f124cc233f144303beb6cf52f471c6424518afee';
 frontendPlanPath='docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md';
 browserEvidencePlanPath='docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md';
 runtimeReleasePlanPath='docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md';
 supersededPlanPath='docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md'}
foreach ($Name in $ExpectedLiterals.Keys) {
 if ([string]$PlanPacket.$Name -cne [string]$ExpectedLiterals[$Name]) { throw "plan bundle literal differs: $Name" }
}
if ([string]$PlanPacket.planBundleHead -notmatch '^[0-9a-f]{40}$') { throw 'plan bundle head is invalid' }
$ExpectedBlobPaths = @($PlanPacket.frontendPlanPath,$PlanPacket.browserEvidencePlanPath,
 $PlanPacket.runtimeReleasePlanPath,$PlanPacket.supersededPlanPath)
if (@($PlanPacket.blobs).Count -ne 4) { throw 'plan bundle blob inventory count differs' }
for ($Index=0; $Index -lt 4; $Index++) {
 $Blob = @($PlanPacket.blobs)[$Index]
 if ((@($Blob.PSObject.Properties.Name) -join "`n") -cne "path`noid") { throw 'plan bundle blob schema differs' }
 if ([string]$Blob.path -cne $ExpectedBlobPaths[$Index] -or [string]$Blob.oid -notmatch '^[0-9a-f]{40}$') {
  throw 'plan bundle blob inventory differs'
 }
 $ActualOid = (& git rev-parse "$($PlanPacket.planBundleHead):$($Blob.path)").Trim()
 if ($LASTEXITCODE -ne 0 -or $ActualOid -cne [string]$Blob.oid) { throw 'plan bundle blob identity mismatch' }
}
& git merge-base --is-ancestor $PlanPacket.planIntegrationBase $PlanPacket.planBundleHead
if ($LASTEXITCODE -ne 0) { throw 'plan bundle ancestry mismatch' }
& git merge-base --is-ancestor $PlanPacket.acceptedBase $PlanPacket.planIntegrationBase
if ($LASTEXITCODE -ne 0) { throw 'accepted-base ancestry mismatch' }
$Head = (& git rev-parse HEAD).Trim();if ($LASTEXITCODE -ne 0 -or $Head -cne $PlanPacket.planBundleHead) {
 throw 'implementation worktree is not at planBundleHead'
}
$Dirty = @(& git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $Dirty.Count -ne 0) { throw 'implementation worktree is not clean' }
$Superseded = @(& git show "$($PlanPacket.planBundleHead):$($PlanPacket.supersededPlanPath)") -join "`n"
if ($LASTEXITCODE -ne 0 -or $Superseded -notmatch 'SUPERSEDED BY SPLIT PLANS') {
 throw 'superseded marker is missing'
}
$Canonical = [ordered]@{}
foreach ($Name in $ExpectedProperties) { $Canonical[$Name] = $PlanPacket.$Name }
$CanonicalBytes = $Utf8.GetBytes(($Canonical | ConvertTo-Json -Compress -Depth 8))
if ($CanonicalBytes.Length -ne $PacketBytes.Length) { throw 'plan bundle JSON is not canonical' }
for ($Index=0; $Index -lt $PacketBytes.Length; $Index++) {
 if ($CanonicalBytes[$Index] -ne $PacketBytes[$Index]) { throw 'plan bundle JSON is not canonical' }
}
```

A consumer mismatch is `BLOCKED`; the implementer never substitutes `f124…` as the implementation worktree head and never edits the packet, signature, or plans to make validation pass.

## Command Convention

Before Task 1, use the Codex desktop workspace-dependency integration and record absolute paths in PowerShell variables named `$node`, `$npm`, `$npx`, `$python310`, and `$python312`. Verify each with `& $tool --version`. Do not use `PATH`, `py`, ambient `python`, ambient `node`, or guessed installation paths.

- Repository-root commands run with `Set-Location -LiteralPath <isolated-worktree-root>`.
- UI commands run with `Set-Location -LiteralPath <isolated-worktree-root>\tools\stm32-monitor\ui`.
- Python Monitor commands run with `Set-Location -LiteralPath <isolated-worktree-root>\tools\stm32-monitor`.
- Every nodeid below is invoked exactly as written. A RED step must fail for the named missing behavior, not for dependency resolution, syntax, fixture, or import errors.

## Exact Existing Wire Authority

The implementation copies field names from the accepted-base Python serializers, not from memory:

- Envelope and operations: `tools/stm32-monitor/src/stm32_monitor/service.py` and `protocol.py`.
- Status, binding, groups, sample/live/history DTOs: `runtime.py`, `models.py`, `groups.py`, and `history.py`.
- Catalog descriptors: `tools/stm32-toolkit/src/stm32_toolkit/debug/types.py`.
- Typed values: `tools/stm32-toolkit/src/stm32_toolkit/debug/model.py::TypedValue.to_dict`.
- Export artifact and binary download: `tools/stm32-monitor/src/stm32_monitor/exports.py` and `service.py::_download`.

The public TypeScript shapes are therefore exact:

```ts
export type JsonValue = null | boolean | number | string |
  readonly JsonValue[] | {readonly [key:string]:JsonValue};
export type ApiFailure = {ok:false;code:string;message:string};
export type PublicFailure = Pick<ApiFailure,"code"|"message">;
export type ApiSuccess<T> = {ok:true;data:T};
export type ApiResult<T> = ApiSuccess<T>|ApiFailure;
export type EventId = string; // canonical unsigned decimal spelling in 1..signed-int64 max

export type ProjectStatus = {logicalProjectId:string;name:string;targetDevice:string};
export type FirmwareStatus = {buildId:string;elfSha256:string;inputSnapshotSha256:string;
  gitHead:string;gitDirty:boolean;targetDevice:string};
export type ProbeStatus = {connected:boolean;probeId:string|null};
export type SamplingStatus = {state:"IDLE"|"STARTING"|"RUNNING"|"PAUSED"|
  "PAUSED_BLOCKED"|"STOPPING";active:boolean;blockedCode:string|null;
  groupId:string|null;groupRevision:number|null;runId:string|null;lastSequence:number|null;
  bindingEpoch:number;subscriberDrops:number;historyDrops:number;deadlineDrops:number;
  serviceDrops:number};
export type MonitorStatus = {workspaceId:string;sessionId:string;project:ProjectStatus;
  firmware:FirmwareStatus|null;probe:ProbeStatus;sampling:SamplingStatus;
  probeConnected:boolean;samplingActive:boolean};

export type ProbeInfo = {probeId:string;vendor:string;product:string;boardName:string|null};
export type VariableDescriptor = {selector:string;typeName:string;kind:string;byteSize:number;
  signed:boolean|null;encoding:string|null;qualifiers:readonly string[];aliases:readonly string[];
  enumValues:readonly {value:number;name:string}[];elementCount:number|null;
  elementKind:string|null;memberNames:readonly string[]};
export type RegisterDescriptor = {selector:string;sizeBits:number;access:string|null;
  readAction:string|null;resetValue:number|null;resetMask:number|null;
  fields:readonly {name:string;bitOffset:number;bitWidth:number}[];sampleable:boolean;
  requiresAccessAcknowledgement:boolean};
export type VariableCatalogPage = {items:readonly VariableDescriptor[];nextCursor:string|null};
export type RegisterCatalogPage = {items:readonly RegisterDescriptor[];nextCursor:string|null};

export type VariableWatch = {kind:"variable";expression:string};
export type RegisterWatch = {kind:"register";registerPath:string};
export type WatchItem = VariableWatch|RegisterWatch;
export type WatchGroup = {groupId:string;name:string;description:string;intervalMs:number;
  items:readonly WatchItem[];revision:number;createdAtUtc:string;updatedAtUtc:string};
export type GroupPage = {groups:readonly WatchGroup[];nextCursor:string|null;revision:string};
export type GroupTransfer = {name:string;description:string;intervalMs:number;
  items:readonly WatchItem[]};
export type GroupImportDocument = {schemaVersion:1;groups:readonly GroupTransfer[]};
export type CreateGroupRequest = GroupTransfer & {authorized:true};
export type UpdateGroupRequest = {expectedRevision:number;authorized:true;name?:string;
  description?:string;intervalMs?:number;items?:readonly WatchItem[]};
export type DeleteGroupRequest = {expectedRevision:number;authorized:true};

export type ObservationBinding = {workspaceId:string;logicalProjectId:string;sessionId:string;
  probeId:string;targetDevice:string;physicalTarget:string;buildId:string;elfSha256:string;
  inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;flashSessionId:string;
  leaseId:string;dwarfSha256:string;svdSha256:string|null};
export type TypedValue = {expression:string;typeName:string;value:JsonValue;
  rawHex:string;bitWidth:number};
export type SampleValue =
  | {watch:WatchItem;status:"OK";typedValue:TypedValue;code:null;
      definition:Readonly<Record<string,JsonValue>>|null}
  | {watch:WatchItem;status:"ERROR";typedValue:null;code:string;
      definition:Readonly<Record<string,JsonValue>>|null};
export type SampleBatch = {binding:ObservationBinding;groupId:string;groupRevision:number;
  runId:string;sequence:number;scheduledUnixNs:number;scheduledAtUtc:string;
  capturedUnixNs:number;capturedAtUtc:string;latencyNs:number;actualRateHz:number;
  subscriberDrops:number;historyDrops:number;deadlineDrops:number;
  values:readonly SampleValue[]};

export type LiveEvent =
  | {eventId:EventId;type:"hello";data:{protocol:"stm32-toolkit-monitor/1";
      toolkitVersion:string;monitorVersion:string;stateRevision:number}}
  | {eventId:EventId;type:"state";data:{stateRevision:number;gap:boolean;status:MonitorStatus}}
  | {eventId:EventId;type:"sample";data:{batch:SampleBatch;serviceSubscriberDrops:number}}
  | {eventId:EventId;type:"heartbeat";data:{stateRevision:number;capturedAtUtc:string}};
export type ParsedLiveEnvelope = {event:LiveEvent;subscriberDropped:number};

export type HistoryBatchSlice = SampleBatch & {startOrdinal:number;batchValueCount:number};
export type HistoryPage = {batches:readonly HistoryBatchSlice[];valueCount:number;
  nextCursor:string|null;serializedBytes:number};
export type HistoryQuery = {startNs:bigint;endNs:bigint;limit?:number;cursor?:string;
  runId?:string;groupId?:string;selector?:{kind:"variable"|"register";value:string}};
export type ExportArtifact = {exportId:string;format:"csv"|"jsonl";sha256:string;
  bytes:number;valueCount:number};
export type ExportRequest = {startNs:bigint;endNs:bigint;format:"csv"|"jsonl";authorized:true};
export type SamplerStartResult = {groupId:string;groupRevision:number;runId:string;intervalMs:number};
export type DownloadResult = ApiFailure|{ok:true;blob:Blob;filename:string;contentType:string};
export type GroupDraft = {sourceGroupId:string|null;expectedRevision:number|null;name:string;
  description:string;intervalMs:number;items:readonly WatchItem[]};
```

`scheduledUnixNs`/`capturedUnixNs` remain display/chart `number` evidence received through `JSON.parse`; they are never reducer identity and UTC display uses the paired server `scheduledAtUtc`/`capturedAtUtc` strings. In contrast, `eventId` is extracted and range-checked from its raw JSON integer token before `JSON.parse` can round it, then stored as its canonical decimal `EventId`; replay serializes that exact decimal as `afterEventId`. User-entered range inputs remain `bigint` in UI state so history query strings and export JSON integer tokens are emitted without IEEE-754 rounding. Derived watches contain only the wire fields enumerated in this contract—there is no child `typeName` to guess.

## Exact Routes, Operations, and Actions

| Client method | HTTP request | Expected operation / success data |
|---|---|---|
| `status()` | `GET /api/v1/status`, no query/body | `monitor.status` / `MonitorStatus` |
| `probes()` | `GET /api/v1/probes`, no query/body | `monitor.probes.list` / `{probes:ProbeInfo[]}` |
| `variables(q,c)` | `GET /api/v1/catalog/variables?query=...&[cursor=...]&limit=100` | `monitor.catalog.variables` / `VariableCatalogPage` |
| `registers(q,c)` | corresponding register route | `monitor.catalog.registers` / `RegisterCatalogPage` |
| `groups(c)` | `GET /api/v1/groups?[cursor=...]&limit=16` | `monitor.groups.list` / `GroupPage` |
| `createGroup` | `POST /api/v1/groups` exact create body + `authorized:true` | `monitor.groups.create` / `WatchGroup` |
| `updateGroup` | `PATCH /api/v1/groups/{groupId}` expectedRevision, changed fields, `authorized:true` | `monitor.groups.update` / `WatchGroup` |
| `deleteGroup` | `DELETE /api/v1/groups/{groupId}` exact revision body | `monitor.groups.delete` / `{groupId:string;deleted:true}` |
| `importGroups` | `POST /api/v1/groups/import` exact document + `authorized:true` | `monitor.groups.import` / `WatchGroup[]` |
| `connect` | `POST /api/v1/probe/connect` `{probeId}` | `monitor.probe.connect` / `ObservationBinding` |
| `reconnect`, `release` | exact POST routes, absent body and absent `Content-Type` | corresponding operation / binding or `{released:true}` |
| `start` | `POST /api/v1/sampling/start` `{groupId,expectedRevision}` | `monitor.sampling.start` / `{groupId,groupRevision,runId,intervalMs}` |
| `pause`, `resume`, `stop` | exact POST routes, absent body and absent `Content-Type` | exact boolean result object |
| `history` | GET with required decimal `startNs/endNs`, allowlisted optional filters only | `monitor.history.query` / `HistoryPage` |
| `createExport` | exact JSON numeric tokens for `startNs/endNs`, format, `authorized:true` | `monitor.exports.create` / `ExportArtifact` |
| `exportStatus` | exact GET resource route | `monitor.exports.get` / `ExportArtifact` |
| `downloadExport` | exact GET download route, no query/body/Range | binary stream; envelope only on failure |
| `live` | `ws(s)://same-origin/api/v1/live[?afterEventId=N]` | exact `LiveEvent`; client sends no messages |

Reducer actions are exact and closed:

```ts
export type MonitorAction =
 | {type:"initial.loaded";status:MonitorStatus;probes:readonly ProbeInfo[];
    groups:readonly WatchGroup[];groupRevision:string}
 | {type:"status.loaded";status:MonitorStatus}
 | {type:"probes.loaded";probes:readonly ProbeInfo[]}
 | {type:"probe.reconnectAvailable";available:boolean}
 | {type:"catalog.requested";catalog:"variables"|"registers";query:string;bindingEpoch:number;
    cursor:string|undefined}
 | {type:"catalog.loaded";catalog:"variables";query:string;bindingEpoch:number;
    cursor:string|undefined;items:readonly VariableDescriptor[];nextCursor:string|null}
 | {type:"catalog.loaded";catalog:"registers";query:string;bindingEpoch:number;
    cursor:string|undefined;items:readonly RegisterDescriptor[];nextCursor:string|null}
 | {type:"groups.loaded";groups:readonly WatchGroup[];revision:string}
 | {type:"group.selected";groupId:string|null}
 | {type:"group.draft.changed";draft:GroupDraft}
 | {type:"group.item.added";watch:WatchItem}
 | {type:"group.item.removed";key:string}
 | {type:"series.toggled";key:string}
 | {type:"live.event";event:LiveEvent;subscriberDropped:number}
 | {type:"history.loaded";query:HistoryQuery;page:HistoryPage}
 | {type:"export.verified";artifact:ExportArtifact}
 | {type:"zoom.in"}|{type:"zoom.out"}|{type:"zoom.reset"}
 | {type:"zoom.set";start:number;end:number}
 | {type:"request.failed";scope:string;code:string;message:string}
 | {type:"transport.stale"}|{type:"transport.open"};
```

## File Structure

- Create `tools/stm32-monitor/ui/index.html`, `package.json`, committed `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `vitest.config.ts`, `playwright.config.ts`, and `eslint.config.js`.
- Create `tools/stm32-monitor/ui/src/main.tsx`, `bootstrap.ts`, `app.tsx`, `styles.css`.
- Create `tools/stm32-monitor/ui/src/api/contract.ts`, `client.ts`, `live.ts`.
- Create `tools/stm32-monitor/ui/src/state/model.ts`, `reducer.ts`, `selectors.ts`.
- Create `tools/stm32-monitor/ui/src/catalog/shallow-selectors.ts`.
- Create `tools/stm32-monitor/ui/src/chart/echarts.ts`, `series.ts`, `zoom.ts`.
- Create focused components `IdentityBar`, `ProbePanel`, `CatalogPanel`, `GroupPanel`, `LiveTable`, `LiveChart`, `ChartZoomControls`, `StatusStrip`, `NoticeRegion`, `HistoryPanel`, and `ExportPanel` under `src/components/`.
- Create Vitest/Testing Library tests under `tools/stm32-monitor/ui/tests/`, including shared exact fixtures in `tests/fixtures.ts` and axe coverage in `tests/a11y.test.tsx`.
- Create `tools/stm32-monitor/tests/test_ui_config.py`; modify only `auth.py`, `service.py`, `tests/test_auth.py`, and `tests/test_service.py` on the Python side.

---

### Task 1: Resolve and Lock the Frontend Toolchain

**Files:** create `tools/stm32-monitor/ui/index.html`, all seven UI config files, and `tools/stm32-monitor/tests/test_ui_config.py`.

**Interfaces:** produces reproducible `$npm ci`, `typecheck`, `lint`, `test`, `test:coverage`, `test:a11y`, and `build` scripts for every later task. Direct dependency versions and Node/npm facts are observed values, never plan literals.

**Task entry gate:** before Step 1, validate the dispatched packet/signature exactly as specified above and require the clean isolated implementation worktree `HEAD` to equal its `planBundleHead`. The RED test is not started from `f124…` directly.

- [ ] **Step 1: Write the failing configuration contract.** From the repository root create this test verbatim:

```python
# tools/stm32-monitor/tests/test_ui_config.py
import json, re
from pathlib import Path

UI = Path(__file__).parents[1] / "ui"
PIN = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\Z")

def test_frontend_config_is_strict_pinned_and_offline_production_safe() -> None:
    package = json.loads((UI / "package.json").read_text(encoding="utf-8"))
    assert package["private"] is True and package["type"] == "module"
    assert set(package["dependencies"]) == {"echarts", "preact"}
    assert {"typescript", "vite", "vitest", "@vitest/coverage-v8", "jsdom",
            "@preact/preset-vite", "@testing-library/preact",
            "@testing-library/user-event", "@testing-library/jest-dom",
            "axe-core", "vitest-axe", "eslint", "@eslint/js",
            "typescript-eslint", "@playwright/test"} <= set(package["devDependencies"])
    for table in (package["dependencies"], package["devDependencies"]):
        assert all(PIN.fullmatch(version) for version in table.values())
    node = package["engines"]["node"]
    assert re.fullmatch(r">=\d+\.\d+\.\d+ <\d+\.0\.0", node)
    assert re.fullmatch(r"npm@\d+\.\d+\.\d+", package["packageManager"])
    assert package["scripts"] == {
        "typecheck":"tsc --noEmit", "lint":"eslint src tests",
        "test":"vitest run", "test:coverage":"vitest run --coverage && npm run coverage:check",
        "coverage:check":"node tests/check-coverage.mjs",
        "test:a11y":"vitest run tests/a11y.test.tsx", "build":"vite build"
    }
    ts = json.loads((UI / "tsconfig.json").read_text(encoding="utf-8"))
    options = ts["compilerOptions"]
    assert options["strict"] is True and options["noEmit"] is True
    assert options["noUncheckedIndexedAccess"] is True
    assert "sourcemap: false" in (UI / "vite.config.ts").read_text(encoding="utf-8")
    vitest = (UI / "vitest.config.ts").read_text(encoding="utf-8")
    assert "environment: \"jsdom\"" in vitest and "provider: \"v8\"" in vitest
    assert "perFile: true" in vitest
    coverage_check = (UI / "tests/check-coverage.mjs").read_text(encoding="utf-8")
    assert "branches" in coverage_check and "90" in coverage_check
    playwright = (UI / "playwright.config.ts").read_text(encoding="utf-8")
    assert all(name in playwright for name in ('name: "chromium"','name: "firefox"','name: "webkit"'))
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert html == ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"UTF-8\">"
                    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                    "<title>STM32 Monitor</title></head><body><div id=\"app\"></div>"
                    "<script type=\"module\" src=\"/src/main.tsx\"></script></body></html>\n")
    assert "http://" not in html and "https://" not in html
    assert html.count("<script") == 1 and "></script>" in html
    assert not (UI / "package-lock.json").read_text(encoding="utf-8").strip() == ""
```

- [ ] **Step 2: Run RED.** From repository root run `& $python312 -m pytest tools/stm32-monitor/tests/test_ui_config.py::test_frontend_config_is_strict_pinned_and_offline_production_safe -q`. Expected: FAIL because `ui/package.json` is absent.

- [ ] **Step 3: Generate exact pins and write the minimum strict configs.** From `tools/stm32-monitor/ui`, run this block; the observed tool versions become the only version literals:

```powershell
$nodeVersion = ((& $node --version).Trim()).TrimStart('v')
$npmVersion = (& $npm --version).Trim()
$nodeMajor = [int]($nodeVersion.Split('.')[0])
& $npm init --yes
& $npm pkg set private=true --json
& $npm pkg set type=module
& $npm pkg set "engines.node=>=$nodeVersion <$($nodeMajor + 1).0.0" "packageManager=npm@$npmVersion"
& $npm pkg set "scripts.typecheck=tsc --noEmit" "scripts.lint=eslint src tests"
& $npm pkg set "scripts.test=vitest run" "scripts.test:coverage=vitest run --coverage && npm run coverage:check"
& $npm pkg set "scripts.coverage:check=node tests/check-coverage.mjs"
& $npm pkg set "scripts.test:a11y=vitest run tests/a11y.test.tsx" "scripts.build=vite build"
& $npm install --save-exact preact echarts
& $npm install --save-dev --save-exact typescript vite vitest '@vitest/coverage-v8' jsdom `
  '@preact/preset-vite' '@testing-library/preact' '@testing-library/user-event' `
  '@testing-library/jest-dom' axe-core vitest-axe eslint '@eslint/js' typescript-eslint `
  '@playwright/test'
```

```ts
// tests/setup.ts
import "@testing-library/jest-dom/vitest";
// tests/a11y.test.tsx -- Task 16 replaces this harness smoke with App state coverage.
import {expect,it} from "vitest";
it("loads the accessibility harness",()=>expect(document.body).toBeDefined());
// src/env.d.ts
/// <reference types="vite/client" />
```

```js
// tests/check-coverage.mjs
import {readFileSync,readdirSync,statSync} from "node:fs";
import {resolve,relative,sep} from "node:path";
const root=resolve("src"),coverage=JSON.parse(readFileSync("coverage/coverage-final.json","utf8"));
const normalized=new Map(Object.entries(coverage).map(([path,value])=>[resolve(path),value]));
const files=[];
const walk=dir=>{for(const name of readdirSync(dir)){const path=resolve(dir,name),info=statSync(path);
 if(info.isDirectory())walk(path);else if(/\.(?:ts|tsx)$/.test(name)&&!name.endsWith(".d.ts"))files.push(path);}};
walk(root);const failures=[];
for(const file of files.sort()){const entry=normalized.get(file);if(entry===undefined){
 failures.push(`${relative(root,file).split(sep).join("/")}: no coverage record`);continue;}
 const counters=Object.values(entry.b).flat();const covered=counters.filter(value=>value>0).length;
 const percent=counters.length===0?100:covered*100/counters.length;
 if(percent<90)failures.push(`${relative(root,file).split(sep).join("/")}: branches ${percent.toFixed(2)}%`);
}
if(failures.length!==0){console.error(failures.join("\n"));process.exit(1);}
```

```js
// eslint.config.js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
export default tseslint.config(js.configs.recommended,...tseslint.configs.recommended,
 {files:["src/**/*.{ts,tsx}","tests/**/*.{ts,tsx}"],rules:{"@typescript-eslint/no-explicit-any":"error"}});
```

```html
<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>STM32 Monitor</title></head><body><div id="app"></div><script type="module" src="/src/main.tsx"></script></body></html>
```

```json
// tsconfig.json
{"compilerOptions":{"target":"ES2022","module":"ESNext","moduleResolution":"Bundler",
"jsx":"react-jsx","jsxImportSource":"preact","strict":true,"noEmit":true,
"noUncheckedIndexedAccess":true,"exactOptionalPropertyTypes":true,
"useUnknownInCatchVariables":true,"skipLibCheck":true,"types":["vitest/globals"]},
"include":["src","tests","*.config.ts","eslint.config.js"]}
```

```ts
// vite.config.ts
import preact from "@preact/preset-vite";
import {defineConfig} from "vite";
export default defineConfig({plugins:[preact()],build:{manifest:true,sourcemap: false,
  rollupOptions:{output:{entryFileNames:"assets/[name]-[hash].js",
    chunkFileNames:"assets/[name]-[hash].js",assetFileNames:"assets/[name]-[hash][extname]"}}}});
```

```ts
// vitest.config.ts
import preact from "@preact/preset-vite";
import {defineConfig} from "vitest/config";
export default defineConfig({plugins:[preact()],test:{environment: "jsdom",setupFiles:["./tests/setup.ts"],
  coverage:{provider: "v8",reporter:["text","json"],include:["src/**/*.{ts,tsx}"],
    thresholds:{perFile: true,branches:90,functions:90,lines:90,statements:90}}}});
```

```ts
// playwright.config.ts
import {defineConfig,devices} from "@playwright/test";
export default defineConfig({projects:[
  {name: "chromium",use:{...devices["Desktop Chrome"]}},
  {name: "firefox",use:{...devices["Desktop Firefox"]}},
  {name: "webkit",use:{...devices["Desktop Safari"]}}
]});
```

- [ ] **Step 4: Run GREEN and lockfile determinism.** From repository root run `& $python312 -m pytest tools/stm32-monitor/tests/test_ui_config.py::test_frontend_config_is_strict_pinned_and_offline_production_safe -q`; from UI root run `& $npm ci; & $npm run typecheck; & $npm run lint; & $npm ci`; then run `git diff --exit-code -- tools/stm32-monitor/ui/package-lock.json`. Expected: every command PASS and the second install changes no lockfile byte.

- [ ] **Step 5: Commit the unit.** From repository root stage only `ui/index.html`, the seven configs, `src/env.d.ts`, `tests/setup.ts`, `tests/check-coverage.mjs`, the harness `tests/a11y.test.tsx`, and `test_ui_config.py`; commit `test(STM32TK-0502): lock frontend core toolchain`.

### Task 2: Define Exact DTO Guards and Envelope Parsing

**Files:** create `src/api/contract.ts`, `tests/fixtures.ts`, and `tests/contract.test.ts`.

**Interfaces:** produces every type in “Exact Existing Wire Authority”, `DataGuard<T>`, `parseEnvelopeText<T>(text,operation,guard):ApiResult<T>`, `parseLiveEnvelopeText(text):ParsedLiveEnvelope|null`, and `parseGroupImportDocumentText(text):ApiResult<GroupImportDocument>`. All object guards reject missing and unknown keys; discriminated unions reject inconsistent null/value combinations. The live parser validates the actual outer `monitor.live` envelope and extracts the inner `eventId` from its raw integer token before JSON number rounding.

- [ ] **Step 1: Write the failing strict-parser tests.** Create the exact fixtures and test below; `VALID_STATUS` contains exactly the status fields listed in this plan and no test casts an invalid value to the desired result type:

```ts
// tests/fixtures.ts
import {vi} from "vitest";
import type {ExportArtifact,GroupImportDocument,HistoryPage,HistoryQuery,JsonValue,MonitorStatus,
  RegisterDescriptor,SampleBatch,VariableDescriptor,WatchGroup,WatchItem} from "../src/api/contract";

export const GROUP_ID="12345678-1234-5678-9234-567812345678";
export const RUN_ID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const VALID_BINDING={workspaceId:"a".repeat(24),logicalProjectId:"12345678-1234-5678-9234-567812345678",
 sessionId:"session-a",probeId:"probe-a",targetDevice:"STM32F407VGTx",physicalTarget:"stm32f407vg",
 buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"d".repeat(64),
 gitHead:"c".repeat(40),gitDirty:false,flashSessionId:"flash-1",leaseId:"lease-1",
 dwarfSha256:"f".repeat(64),svdSha256:null} as const;
export const VALID_STATUS:MonitorStatus={workspaceId:"a".repeat(24),sessionId:"session-a",
 project:{logicalProjectId:VALID_BINDING.logicalProjectId,name:"Motor Control",targetDevice:"STM32F407VGTx"},
 firmware:{buildId:VALID_BINDING.buildId,elfSha256:VALID_BINDING.elfSha256,
  inputSnapshotSha256:VALID_BINDING.inputSnapshotSha256,gitHead:VALID_BINDING.gitHead,
  gitDirty:false,targetDevice:"STM32F407VGTx"},probe:{connected:true,probeId:"probe-a"},
 sampling:{state:"RUNNING",active:true,blockedCode:null,groupId:GROUP_ID,groupRevision:2,runId:RUN_ID,
  lastSequence:0,bindingEpoch:1,subscriberDrops:0,historyDrops:0,deadlineDrops:0,serviceDrops:0},
 probeConnected:true,samplingActive:true};
export const VALID_GROUP:WatchGroup={groupId:GROUP_ID,name:"Mine",description:"",
 intervalMs:250,items:[{kind:"variable",expression:"counter"}],revision:2,
 createdAtUtc:"2026-08-10T00:00:00.000000Z",updatedAtUtc:"2026-08-10T00:00:00.000000Z"};
export const VALID_SAMPLE_BATCH:SampleBatch={binding:VALID_BINDING,groupId:GROUP_ID,groupRevision:2,
 runId:RUN_ID,sequence:0,scheduledUnixNs:1_000,capturedUnixNs:1_250,
 scheduledAtUtc:"1970-01-01T00:00:00.000001Z",capturedAtUtc:"1970-01-01T00:00:00.000001Z",
 latencyNs:250,actualRateHz:4,subscriberDrops:0,historyDrops:0,deadlineDrops:0,
 values:[{watch:{kind:"variable",expression:"counter"},status:"OK",code:null,
  typedValue:{expression:"counter",typeName:"uint32_t",value:7,rawHex:"0x00000007",bitWidth:32},
  definition:{kind:"variable",selector:"counter"}}]};
export const VALID_HISTORY_BATCH={...VALID_SAMPLE_BATCH,startOrdinal:0,batchValueCount:1} as const;
export const HISTORY_PAGE:HistoryPage={batches:[VALID_HISTORY_BATCH],valueCount:1,nextCursor:null,serializedBytes:512};
export const HISTORY_QUERY:HistoryQuery={startNs:1_700_000_000_000_000_000n,
 endNs:1_700_000_001_000_000_000n,limit:10_000};
export const HISTORY_START_INPUT="2023-11-14T22:13:20.000";
export const HISTORY_END_INPUT="2023-11-14T22:13:21.000";
export const EXPORT_RANGE={startNs:HISTORY_QUERY.startNs,endNs:HISTORY_QUERY.endNs} as const;
export const EXPORT_START_INPUT=HISTORY_START_INPUT;
export const EXPORT_END_INPUT=HISTORY_END_INPUT;
export const VALID_EXPORT:ExportArtifact={exportId:"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
 format:"csv",sha256:"9".repeat(64),bytes:123,valueCount:4};
export const VALID_PROBES={probes:[{probeId:"probe-a",vendor:"ST",product:"ST-Link",boardName:null}]};
export const VARIABLE_CATALOG={items:[{selector:"counter",typeName:"uint32_t",kind:"integer",
 byteSize:4,signed:false,encoding:null,qualifiers:[],aliases:[],enumValues:[],elementCount:null,
 elementKind:null,memberNames:[]} satisfies VariableDescriptor],nextCursor:null};
export const LIVE_ROW={key:"variable:counter",selector:"counter",
 watch:{kind:"variable",expression:"counter"},typeName:"uint32_t",displayValue:"7",rawHex:"0x00000007",
 capturedAtUtc:VALID_SAMPLE_BATCH.capturedAtUtc,numericValue:7,trend:"none",errorCode:null} as const;

export const VARIABLE_ARRAY_257:VariableDescriptor={selector:"samples",typeName:"uint16_t[257]",
 kind:"array",byteSize:514,signed:null,encoding:null,qualifiers:[],aliases:[],enumValues:[],
 elementCount:257,elementKind:"integer",memberNames:[]};
export const UNAVAILABLE_REGISTER:RegisterDescriptor={selector:"RCC.DANGEROUS",sizeBits:32,
 access:"write-only",readAction:"undefined",resetValue:null,resetMask:null,fields:[],sampleable:false,
 requiresAccessAcknowledgement:false};
export const RISKY_REGISTER:RegisterDescriptor={selector:"RCC.CSR",sizeBits:32,access:"read-write",
 readAction:"read-clear",resetValue:0,resetMask:0xffffffff,fields:[],sampleable:true,
 requiresAccessAcknowledgement:true};
export const IMPORT_DOCUMENT:GroupImportDocument={schemaVersion:1,groups:[
 {name:"Mine",description:"conflict",intervalMs:250,items:[{kind:"variable",expression:"counter"}]},
 {name:"Other",description:"",intervalMs:500,items:[{kind:"register",registerPath:"RCC.CSR"},
  {kind:"variable",expression:"rpm"}]}]};

export const sampleBatchWithTypedValue=(value:JsonValue):SampleBatch=>({...VALID_SAMPLE_BATCH,
 values:[{watch:{kind:"variable",expression:"counter"},status:"OK",code:null,
  typedValue:{expression:"counter",typeName:"uint32_t",value,rawHex:"0x00000007",bitWidth:32},definition:null}]});
export function groupWithItems(count:number):WatchGroup{return {...VALID_GROUP,items:Array.from({length:count},
 (_,i):WatchItem=>({kind:"variable",expression:`v${i}`}))};}
export function batchForItems(items:readonly WatchItem[],value:number):SampleBatch{return {...VALID_SAMPLE_BATCH,
 sequence:value,values:items.slice(0,256).map(watch=>({watch,status:"OK" as const,code:null,
  typedValue:{expression:watch.kind==="variable"?watch.expression:watch.registerPath,typeName:"uint32_t",
   value,rawHex:`0x${value.toString(16).padStart(8,"0")}`,bitWidth:32},definition:null}))};}
export const seriesFixture=(series:number,points:number,gap:boolean)=>Array.from({length:series},(_,s)=>({
 name:`v${s}`,points:Array.from({length:points},(_,p)=>({x:p,y:gap&&p===10?null:p+s}))}));
export const optionFixture=(value:number)=>({series:[{type:"line",data:[[value,value]]}]});
export const validEnvelope=(operation:string,data:unknown):string=>JSON.stringify({
 protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",monitorVersion:"0.5.0",
 ok:true,operation,code:"OK",message:"",data,details:{}});

export class FakeSocket extends EventTarget{
 readonly send=vi.fn();readonly close=vi.fn();constructor(readonly url:string){super();}
 emit(type:string,init:Record<string,unknown>):void{this.dispatchEvent(Object.assign(new Event(type),init));}
}
```

```ts
// tests/contract.test.ts
import {describe,expect,it} from "vitest";
import {monitorStatusGuard,parseEnvelopeText,parseLiveEnvelopeText,watchGroupGuard} from "../src/api/contract";
import {HISTORY_PAGE,VALID_BINDING,VALID_EXPORT,VALID_GROUP,VALID_STATUS,VALID_SAMPLE_BATCH} from "./fixtures";

const ok = (operation:string,data:unknown) => JSON.stringify({
  protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",monitorVersion:"0.5.0",
  ok:true,operation,code:"OK",message:"",data,details:{}
});

describe("exact monitor DTO parser", () => {
  it("parses the exact status envelope", () => {
    expect(parseEnvelopeText(ok("monitor.status",VALID_STATUS),"monitor.status",monitorStatusGuard))
      .toEqual({ok:true,data:VALID_STATUS});
  });

  it.each([
    ["duplicate key",'{"protocol":"stm32-toolkit-monitor/1","protocol":"x"}'],
    ["unknown envelope key",JSON.stringify({...JSON.parse(ok("monitor.status",VALID_STATUS)),extra:1})],
    ["wrong protocol",ok("monitor.status",{...VALID_STATUS,probeConnected:"yes"})],
    ["wrong operation",ok("monitor.probes.list",VALID_STATUS)],
    ["unknown data key",ok("monitor.status",{...VALID_STATUS,extra:true})],
  ])("rejects %s", (_name,text) => {
    expect(parseEnvelopeText(text,"monitor.status",monitorStatusGuard))
      .toEqual({ok:false,code:"MONITOR_PROTOCOL_INVALID",message:"Monitor response is invalid"});
  });

  it("keeps public non-ok code/message and discards details", () => {
    const text=JSON.stringify({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",
      monitorVersion:"0.5.0",ok:false,operation:"monitor.status",code:"MONITOR_PROBE_BUSY",
      message:"A probe is busy",data:null,details:{internal:"not a UI fact"}});
    expect(parseEnvelopeText(text,"monitor.status",monitorStatusGuard))
      .toEqual({ok:false,code:"MONITOR_PROBE_BUSY",message:"A probe is busy"});
  });

  it("enforces watch wire discrimination and complete group timestamps", () => {
    expect(watchGroupGuard(VALID_GROUP)).toBe(true);
    expect(watchGroupGuard({...VALID_GROUP,items:[{kind:"variable",selector:"counter"}]})).toBe(false);
    const missing={...VALID_GROUP} as Record<string,unknown>; delete missing.updatedAtUtc;
    expect(watchGroupGuard(missing)).toBe(false);
  });

  const liveText=(eventId:string,type:string,data:unknown,subscriberDropped=0)=>
   `{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.5.0","monitorVersion":"0.5.0",`+
   `"ok":true,"operation":"monitor.live","code":"OK","message":"","data":{"eventId":${eventId},`+
   `"type":${JSON.stringify(type)},"data":${JSON.stringify(data)}},"details":{"subscriberDropped":${subscriberDropped}}}`;

  it.each([
    ["1","hello",{protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",monitorVersion:"0.5.0",stateRevision:0}],
    ["2","state",{stateRevision:1,gap:false,status:VALID_STATUS}],
    ["3","sample",{batch:VALID_SAMPLE_BATCH,serviceSubscriberDrops:0}],
    ["4","heartbeat",{stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"}],
  ] as const)("parses the accepted monitor.live envelope for %s",(eventId,type,data)=>{
    expect(parseLiveEnvelopeText(liveText(eventId,type,data,2))).toEqual({
      event:{eventId,type,data},subscriberDropped:2});
  });

  it.each([
    ["wrong operation",liveText("5","heartbeat",{stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"}).replace("monitor.live","monitor.status")],
    ["missing detail",liveText("5","heartbeat",{stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"}).replace(',"subscriberDropped":0',"")],
    ["fractional event id",liveText("5.5","heartbeat",{stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"})],
    ["zero event id",liveText("0","heartbeat",{stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"})],
    ["overflow event id",liveText("9223372036854775808","heartbeat",{stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"})],
  ])("rejects live envelope %s",(_name,text)=>expect(parseLiveEnvelopeText(text)).toBeNull());

  it("preserves signed-int64 event identity beyond Number.MAX_SAFE_INTEGER",()=>{
    const text=liveText("9223372036854775807","heartbeat",
      {stateRevision:1,capturedAtUtc:"2026-08-10T00:00:00.000000Z"});
    expect(parseLiveEnvelopeText(text)?.event.eventId).toBe("9223372036854775807");
  });

  it("accepts realistic 19-digit server nanosecond evidence", () => {
    const batch={...VALID_SAMPLE_BATCH,scheduledUnixNs:1_700_000_000_000_000_000,
      capturedUnixNs:1_700_000_000_001_000_000,
      scheduledAtUtc:"2023-11-14T22:13:20.000000Z",capturedAtUtc:"2023-11-14T22:13:20.001000Z"};
    const text=liveText("5","sample",{batch,serviceSubscriberDrops:0});
    expect(Number.isSafeInteger(batch.scheduledUnixNs)).toBe(false);
    expect(parseLiveEnvelopeText(text)?.event.data).toEqual({batch,serviceSubscriberDrops:0});
  });
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/contract.test.ts -t "exact monitor DTO parser"`. Expected: FAIL because `src/api/contract.ts` is absent.

- [ ] **Step 3: Implement the strict guard boundary matching the tests.** Use exact-key guards for every DTO in this plan; the minimal parser core is:

```ts
// src/api/contract.ts
export type DataGuard<T>=(value:unknown)=>value is T;
const ENVELOPE_KEYS=["protocol","toolkitVersion","monitorVersion","ok","operation","code","message","data","details"] as const;
const exactKeys=(v:unknown,keys:readonly string[]):v is Record<string,unknown> =>
  typeof v==="object"&&v!==null&&!Array.isArray(v)&&
  Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const invalid=():ApiFailure=>({ok:false,code:"MONITOR_PROTOCOL_INVALID",message:"Monitor response is invalid"});

export function parseEnvelopeText<T>(text:string,operation:string,guard:DataGuard<T>):ApiResult<T>{
  try {
    rejectDuplicateObjectKeys(text);
    const value:unknown=JSON.parse(text);
    if(!exactKeys(value,ENVELOPE_KEYS)||value.protocol!=="stm32-toolkit-monitor/1"||
       value.toolkitVersion!=="0.5.0"||value.monitorVersion!=="0.5.0"||
       value.operation!==operation||typeof value.ok!=="boolean"||typeof value.code!=="string"||
       typeof value.message!=="string"||typeof value.details!=="object"||value.details===null||
       Array.isArray(value.details)) return invalid();
    if(value.ok===false){
      if(value.data!==null||value.code==="OK"||value.message.length===0) return invalid();
      return {ok:false,code:value.code,message:value.message};
    }
    if(value.code!=="OK"||value.message!==""||Object.keys(value.details).length!==0||!guard(value.data)) return invalid();
    return {ok:true,data:value.data};
  } catch { return invalid(); }
}

export const watchItemGuard:DataGuard<WatchItem>=(v):v is WatchItem =>
  exactKeys(v,["kind","expression"])&&v.kind==="variable"&&typeof v.expression==="string" ||
  exactKeys(v,["kind","registerPath"])&&v.kind==="register"&&typeof v.registerPath==="string";

export const watchGroupGuard:DataGuard<WatchGroup>=(v):v is WatchGroup =>
  exactKeys(v,["groupId","name","description","intervalMs","items","revision","createdAtUtc","updatedAtUtc"])&&
  typeof v.groupId==="string"&&typeof v.name==="string"&&typeof v.description==="string"&&
  Number.isInteger(v.intervalMs)&&Array.isArray(v.items)&&v.items.every(watchItemGuard)&&
  Number.isInteger(v.revision)&&typeof v.createdAtUtc==="string"&&typeof v.updatedAtUtc==="string";
```

Append this complete duplicate-key pre-parser; it validates one bounded JSON value while retaining every object key set:

```ts
export function rejectDuplicateObjectKeys(text:string):void{
 if(text.length>1_048_576)throw new Error("JSON is too large");let i=0;
 const ws=()=>{while(i<text.length&&/[\t\n\r ]/.test(text[i]!))i++;};
 const str=():string=>{const start=i;if(text[i++]!=="\"")throw new Error("string expected");
  while(i<text.length){const c=text[i++]!;if(c==="\"")return JSON.parse(text.slice(start,i)) as string;
   if(c==="\\"){const e=text[i++]!;if(e==="u"){if(!/^[0-9a-fA-F]{4}$/.test(text.slice(i,i+4)))throw new Error("escape");i+=4;}
    else if(!'\"\\/bfnrt'.includes(e))throw new Error("escape");}
   else if(c.charCodeAt(0)<0x20)throw new Error("control");}throw new Error("unterminated string");};
 const value=(depth:number):void=>{if(depth>32)throw new Error("JSON nesting is too deep");ws();const c=text[i];
  if(c==="{"){i++;ws();const keys=new Set<string>();if(text[i]!=="}")for(;;){ws();const key=str();
    if(keys.has(key))throw new Error("duplicate key");keys.add(key);ws();if(text[i++]!==":")throw new Error("colon");
    value(depth+1);ws();if(text[i]===","){i++;continue;}break;}if(text[i++]!=="}")throw new Error("object close");return;}
  if(c==="["){i++;ws();if(text[i]!=="]")for(;;){value(depth+1);ws();if(text[i]===","){i++;continue;}break;}
    if(text[i++]!=="]")throw new Error("array close");return;}
  if(c==='\"'){str();return;}const token=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/
    .exec(text.slice(i))?.[0];if(token===undefined)throw new Error("value");i+=token.length;};
 value(0);ws();if(i!==text.length)throw new Error("trailing JSON");
}
```

Append the exact guards and live parser below; this defines every guard name consumed by `client.ts`:

```ts
const text=(v:unknown):v is string=>typeof v==="string";
const bool=(v:unknown):v is boolean=>typeof v==="boolean";
const integer=(v:unknown):v is number=>typeof v==="number"&&Number.isInteger(v);
const MAX_JSON_SIGNED_INT64=Number(9_223_372_036_854_775_807n);
const nonnegative=(v:unknown):v is number=>integer(v)&&v>=0&&v<=MAX_JSON_SIGNED_INT64;
const EVENT_ID_MAX=9_223_372_036_854_775_807n;
export const eventIdGuard=(v:unknown):v is EventId=>typeof v==="string"&&/^[1-9]\d{0,18}$/.test(v)&&BigInt(v)<=EVENT_ID_MAX;
const nullable=<T>(g:DataGuard<T>):DataGuard<T|null>=>(v):v is T|null=>v===null||g(v);
const arrayOf=<T>(g:DataGuard<T>):DataGuard<readonly T[]>=>(v):v is readonly T[]=>Array.isArray(v)&&v.every(g);
const jsonValueGuard:DataGuard<JsonValue>=(v):v is JsonValue=>v===null||text(v)||bool(v)||
 (typeof v==="number"&&Number.isFinite(v))||Array.isArray(v)&&v.every(jsonValueGuard)||
 (typeof v==="object"&&v!==null&&!Array.isArray(v)&&Object.values(v).every(jsonValueGuard));
const jsonObjectGuard:DataGuard<Readonly<Record<string,JsonValue>>>=(v):v is Readonly<Record<string,JsonValue>>=>
 typeof v==="object"&&v!==null&&!Array.isArray(v)&&Object.values(v).every(jsonValueGuard);
const projectGuard:DataGuard<ProjectStatus>=(v):v is ProjectStatus=>exactKeys(v,["logicalProjectId","name","targetDevice"])&&
 text(v.logicalProjectId)&&text(v.name)&&text(v.targetDevice);
const firmwareGuard:DataGuard<FirmwareStatus>=(v):v is FirmwareStatus=>exactKeys(v,
 ["buildId","elfSha256","inputSnapshotSha256","gitHead","gitDirty","targetDevice"])&&
 text(v.buildId)&&text(v.elfSha256)&&text(v.inputSnapshotSha256)&&text(v.gitHead)&&bool(v.gitDirty)&&text(v.targetDevice);
const probeStatusGuard:DataGuard<ProbeStatus>=(v):v is ProbeStatus=>exactKeys(v,["connected","probeId"])&&
 bool(v.connected)&&nullable(text)(v.probeId)&&v.connected===(v.probeId!==null);
const samplingStatusGuard:DataGuard<SamplingStatus>=(v):v is SamplingStatus=>exactKeys(v,
 ["state","active","blockedCode","groupId","groupRevision","runId","lastSequence","bindingEpoch",
  "subscriberDrops","historyDrops","deadlineDrops","serviceDrops"])&&
 ["IDLE","STARTING","RUNNING","PAUSED","PAUSED_BLOCKED","STOPPING"].includes(String(v.state))&&
 bool(v.active)&&nullable(text)(v.blockedCode)&&nullable(text)(v.groupId)&&nullable(integer)(v.groupRevision)&&
 nullable(text)(v.runId)&&nullable(nonnegative)(v.lastSequence)&&nonnegative(v.bindingEpoch)&&
 nonnegative(v.subscriberDrops)&&nonnegative(v.historyDrops)&&nonnegative(v.deadlineDrops)&&nonnegative(v.serviceDrops);
export const monitorStatusGuard:DataGuard<MonitorStatus>=(v):v is MonitorStatus=>exactKeys(v,
 ["workspaceId","sessionId","project","firmware","probe","sampling","probeConnected","samplingActive"])&&
 text(v.workspaceId)&&text(v.sessionId)&&projectGuard(v.project)&&nullable(firmwareGuard)(v.firmware)&&
 probeStatusGuard(v.probe)&&samplingStatusGuard(v.sampling)&&bool(v.probeConnected)&&bool(v.samplingActive)&&
 v.probeConnected===v.probe.connected&&v.samplingActive===v.sampling.active;
export const probeInfoGuard:DataGuard<ProbeInfo>=(v):v is ProbeInfo=>exactKeys(v,["probeId","vendor","product","boardName"])&&
 text(v.probeId)&&text(v.vendor)&&text(v.product)&&nullable(text)(v.boardName);
export const probePageGuard:DataGuard<{probes:readonly ProbeInfo[]}>=(v):v is {probes:readonly ProbeInfo[]}=>
 exactKeys(v,["probes"])&&arrayOf(probeInfoGuard)(v.probes);
const enumGuard:DataGuard<{value:number;name:string}>=(v):v is {value:number;name:string}=>
 exactKeys(v,["value","name"])&&integer(v.value)&&text(v.name);
export const variableDescriptorGuard:DataGuard<VariableDescriptor>=(v):v is VariableDescriptor=>exactKeys(v,
 ["selector","typeName","kind","byteSize","signed","encoding","qualifiers","aliases","enumValues",
  "elementCount","elementKind","memberNames"])&&text(v.selector)&&text(v.typeName)&&text(v.kind)&&
 integer(v.byteSize)&&nullable(bool)(v.signed)&&nullable(text)(v.encoding)&&arrayOf(text)(v.qualifiers)&&
 arrayOf(text)(v.aliases)&&arrayOf(enumGuard)(v.enumValues)&&nullable(integer)(v.elementCount)&&
 nullable(text)(v.elementKind)&&arrayOf(text)(v.memberNames);
const fieldGuard:DataGuard<{name:string;bitOffset:number;bitWidth:number}>=(v):v is {name:string;bitOffset:number;bitWidth:number}=>
 exactKeys(v,["name","bitOffset","bitWidth"])&&text(v.name)&&nonnegative(v.bitOffset)&&integer(v.bitWidth)&&v.bitWidth>0;
export const registerDescriptorGuard:DataGuard<RegisterDescriptor>=(v):v is RegisterDescriptor=>exactKeys(v,
 ["selector","sizeBits","access","readAction","resetValue","resetMask","fields","sampleable","requiresAccessAcknowledgement"])&&
 text(v.selector)&&integer(v.sizeBits)&&nullable(text)(v.access)&&nullable(text)(v.readAction)&&
 nullable(nonnegative)(v.resetValue)&&nullable(nonnegative)(v.resetMask)&&arrayOf(fieldGuard)(v.fields)&&
 bool(v.sampleable)&&bool(v.requiresAccessAcknowledgement);
export const variablePageGuard:DataGuard<VariableCatalogPage>=(v):v is VariableCatalogPage=>
 exactKeys(v,["items","nextCursor"])&&arrayOf(variableDescriptorGuard)(v.items)&&nullable(text)(v.nextCursor);
export const registerPageGuard:DataGuard<RegisterCatalogPage>=(v):v is RegisterCatalogPage=>
 exactKeys(v,["items","nextCursor"])&&arrayOf(registerDescriptorGuard)(v.items)&&nullable(text)(v.nextCursor);
export const groupPageGuard:DataGuard<GroupPage>=(v):v is GroupPage=>exactKeys(v,["groups","nextCursor","revision"])&&
 arrayOf(watchGroupGuard)(v.groups)&&nullable(text)(v.nextCursor)&&text(v.revision);
```

```ts
export const observationBindingGuard:DataGuard<ObservationBinding>=(v):v is ObservationBinding=>exactKeys(v,
 ["workspaceId","logicalProjectId","sessionId","probeId","targetDevice","physicalTarget","buildId","elfSha256",
  "inputSnapshotSha256","gitHead","gitDirty","flashSessionId","leaseId","dwarfSha256","svdSha256"])&&
 [v.workspaceId,v.logicalProjectId,v.sessionId,v.probeId,v.targetDevice,v.physicalTarget,v.buildId,v.elfSha256,
  v.inputSnapshotSha256,v.gitHead,v.flashSessionId,v.leaseId,v.dwarfSha256].every(text)&&bool(v.gitDirty)&&nullable(text)(v.svdSha256);
const typedValueGuard:DataGuard<TypedValue>=(v):v is TypedValue=>exactKeys(v,["expression","typeName","value","rawHex","bitWidth"])&&
 text(v.expression)&&text(v.typeName)&&jsonValueGuard(v.value)&&text(v.rawHex)&&integer(v.bitWidth);
const sampleValueGuard:DataGuard<SampleValue>=(v):v is SampleValue=>exactKeys(v,["watch","status","typedValue","code","definition"])&&
 watchItemGuard(v.watch)&&nullable(jsonObjectGuard)(v.definition)&&
 (v.status==="OK"&&typedValueGuard(v.typedValue)&&v.code===null||v.status==="ERROR"&&v.typedValue===null&&text(v.code));
export const sampleBatchGuard:DataGuard<SampleBatch>=(v):v is SampleBatch=>exactKeys(v,
 ["binding","groupId","groupRevision","runId","sequence","scheduledUnixNs","scheduledAtUtc","capturedUnixNs",
  "capturedAtUtc","latencyNs","actualRateHz","subscriberDrops","historyDrops","deadlineDrops","values"])&&
 observationBindingGuard(v.binding)&&text(v.groupId)&&integer(v.groupRevision)&&text(v.runId)&&nonnegative(v.sequence)&&
 nonnegative(v.scheduledUnixNs)&&text(v.scheduledAtUtc)&&nonnegative(v.capturedUnixNs)&&text(v.capturedAtUtc)&&
 nonnegative(v.latencyNs)&&typeof v.actualRateHz==="number"&&Number.isFinite(v.actualRateHz)&&v.actualRateHz>=0&&
 nonnegative(v.subscriberDrops)&&nonnegative(v.historyDrops)&&nonnegative(v.deadlineDrops)&&arrayOf(sampleValueGuard)(v.values);
const historyBatchGuard:DataGuard<HistoryBatchSlice>=(v):v is HistoryBatchSlice=>
 exactKeys(v,["binding","groupId","groupRevision","runId","sequence","scheduledUnixNs","scheduledAtUtc","capturedUnixNs",
  "capturedAtUtc","latencyNs","actualRateHz","subscriberDrops","historyDrops","deadlineDrops","startOrdinal","batchValueCount","values"])&&
 sampleBatchGuard(Object.fromEntries(Object.entries(v).filter(([k])=>k!=="startOrdinal"&&k!=="batchValueCount")))&&
 nonnegative(v.startOrdinal)&&integer(v.batchValueCount);
export const historyPageGuard:DataGuard<HistoryPage>=(v):v is HistoryPage=>exactKeys(v,
 ["batches","valueCount","nextCursor","serializedBytes"])&&arrayOf(historyBatchGuard)(v.batches)&&
 nonnegative(v.valueCount)&&nullable(text)(v.nextCursor)&&nonnegative(v.serializedBytes);
export const exportArtifactGuard:DataGuard<ExportArtifact>=(v):v is ExportArtifact=>exactKeys(v,
 ["exportId","format","sha256","bytes","valueCount"])&&text(v.exportId)&&(v.format==="csv"||v.format==="jsonl")&&
 text(v.sha256)&&nonnegative(v.bytes)&&nonnegative(v.valueCount);
export const authenticatedGuard:DataGuard<{authenticated:true}>=(v):v is {authenticated:true}=>
 exactKeys(v,["authenticated"])&&v.authenticated===true;
export const deletedGroupGuard:DataGuard<{groupId:string;deleted:true}>=(v):v is {groupId:string;deleted:true}=>
 exactKeys(v,["groupId","deleted"])&&text(v.groupId)&&v.deleted===true;
export const releasedGuard:DataGuard<{released:true}>=(v):v is {released:true}=>exactKeys(v,["released"])&&v.released===true;
export const importedGroupsGuard:DataGuard<readonly WatchGroup[]>=arrayOf(watchGroupGuard);
export const groupImportDocumentGuard:DataGuard<GroupImportDocument>=(v):v is GroupImportDocument=>
 exactKeys(v,["schemaVersion","groups"])&&v.schemaVersion===1&&arrayOf((g:unknown):g is GroupTransfer=>
  exactKeys(g,["name","description","intervalMs","items"])&&text(g.name)&&typeof g.description==="string"&&
  integer(g.intervalMs)&&g.intervalMs>=100&&g.intervalMs<=5000&&arrayOf(watchItemGuard)(g.items))(v.groups);
export const samplerStartGuard:DataGuard<SamplerStartResult>=(v):v is SamplerStartResult=>exactKeys(v,
 ["groupId","groupRevision","runId","intervalMs"])&&text(v.groupId)&&integer(v.groupRevision)&&text(v.runId)&&integer(v.intervalMs);
const literalResult=<K extends string>(key:K):DataGuard<Record<K,boolean>>=>(v):v is Record<K,boolean>=>
 exactKeys(v,[key])&&bool(v[key]);
export const pausedResultGuard=literalResult("paused"),resumedResultGuard=literalResult("resumed"),
 stoppedResultGuard=literalResult("stopped");
export const neverSuccessGuard:DataGuard<never>=(_value:unknown):_value is never=>false;
const LIVE_EVENT_TOKEN=/"data"\s*:\s*\{\s*"eventId"\s*:\s*([0-9]+)(?=\s*,\s*"type"\s*:)/;
export function parseLiveEnvelopeText(raw:string):ParsedLiveEnvelope|null{try{
 rejectDuplicateObjectKeys(raw);const token=LIVE_EVENT_TOKEN.exec(raw)?.[1];if(token===undefined||!eventIdGuard(token))return null;
 const v:unknown=JSON.parse(raw);if(!exactKeys(v,ENVELOPE_KEYS)||v.protocol!=="stm32-toolkit-monitor/1"||
  v.toolkitVersion!=="0.5.0"||v.monitorVersion!=="0.5.0"||v.ok!==true||v.operation!=="monitor.live"||
  v.code!=="OK"||v.message!==""||!exactKeys(v.details,["subscriberDropped"])||
  !nonnegative(v.details.subscriberDropped)||!exactKeys(v.data,["eventId","type","data"])||
  !nonnegative(v.data.eventId))return null;
 const eventId:EventId=token,data=v.data.data;let event:LiveEvent;
 if(v.data.type==="hello"&&exactKeys(data,["protocol","toolkitVersion","monitorVersion","stateRevision"])&&
  data.protocol==="stm32-toolkit-monitor/1"&&text(data.toolkitVersion)&&text(data.monitorVersion)&&nonnegative(data.stateRevision))
   event={eventId,type:"hello",data};
 else if(v.data.type==="state"&&exactKeys(data,["stateRevision","gap","status"])&&
  nonnegative(data.stateRevision)&&bool(data.gap)&&monitorStatusGuard(data.status))event={eventId,type:"state",data};
 else if(v.data.type==="sample"&&exactKeys(data,["batch","serviceSubscriberDrops"])&&
  sampleBatchGuard(data.batch)&&nonnegative(data.serviceSubscriberDrops))event={eventId,type:"sample",data};
 else if(v.data.type==="heartbeat"&&exactKeys(data,["stateRevision","capturedAtUtc"])&&
  nonnegative(data.stateRevision)&&text(data.capturedAtUtc))event={eventId,type:"heartbeat",data};
 else return null;
 return {event,subscriberDropped:v.details.subscriberDropped};
 }catch{return null;}}
export function parseGroupImportDocumentText(raw:string):ApiResult<GroupImportDocument>{
 try{rejectDuplicateObjectKeys(raw);const value:unknown=JSON.parse(raw);return groupImportDocumentGuard(value)?
  {ok:true,data:value}:{ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"};}
 catch{return {ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"};}
}
```

- [ ] **Step 4: Run GREEN and typecheck.** From UI root run `& $npm run test -- tests/contract.test.ts -t "exact monitor DTO parser"; & $npm run typecheck`. Expected: PASS with all four live discriminants and strict status/group fixtures accepted.

- [ ] **Step 5: Commit the unit.** Stage only `src/api/contract.ts`, `tests/fixtures.ts`, and `tests/contract.test.ts`; commit `feat(STM32TK-0502): define exact frontend wire contracts`.

### Task 3: Build the Only REST Client

**Files:** create `src/api/client.ts`; modify `tests/contract.test.ts`.

**Interfaces:** produces `MonitorClient` methods in the route table, `HistoryQuery` with `bigint` bounds, `ExportRequest` with `bigint` bounds, and `DownloadResult`. Only this file calls `fetch` after bootstrap.

- [ ] **Step 1: Write the failing request-construction matrix.** Append this exact table-driven test:

```ts
// tests/contract.test.ts
const validResponseFor=(url:string,method:string):string=>{
 const path=new URL(url,"http://127.0.0.1").pathname;
 if(path==="/api/v1/status")return ok("monitor.status",VALID_STATUS);
 if(path==="/api/v1/probes")return ok("monitor.probes.list",{probes:[]});
 if(path.endsWith("/catalog/variables"))return ok("monitor.catalog.variables",{items:[],nextCursor:null});
 if(path.endsWith("/catalog/registers"))return ok("monitor.catalog.registers",{items:[],nextCursor:null});
 if(path==="/api/v1/groups/import")return ok("monitor.groups.import",[VALID_GROUP]);
 if(path==="/api/v1/groups"&&method==="GET")return ok("monitor.groups.list",{groups:[VALID_GROUP],nextCursor:null,revision:"a".repeat(64)});
 if(path==="/api/v1/groups")return ok("monitor.groups.create",VALID_GROUP);
 if(path.startsWith("/api/v1/groups/")&&method==="PATCH")return ok("monitor.groups.update",VALID_GROUP);
 if(path.startsWith("/api/v1/groups/")&&method==="DELETE")return ok("monitor.groups.delete",{groupId:VALID_GROUP.groupId,deleted:true});
 if(path.endsWith("/probe/connect"))return ok("monitor.probe.connect",VALID_BINDING);
 if(path.endsWith("/probe/reconnect"))return ok("monitor.probe.reconnect",VALID_BINDING);
 if(path.endsWith("/probe/release"))return ok("monitor.probe.release",{released:true});
 if(path.endsWith("/sampling/start"))return ok("monitor.sampling.start",{groupId:VALID_GROUP.groupId,groupRevision:2,runId:VALID_SAMPLE_BATCH.runId,intervalMs:250});
 if(path.endsWith("/sampling/pause"))return ok("monitor.sampling.pause",{paused:true});
 if(path.endsWith("/sampling/resume"))return ok("monitor.sampling.resume",{resumed:true});
 if(path.endsWith("/sampling/stop"))return ok("monitor.sampling.stop",{stopped:true});
 if(path==="/api/v1/history")return ok("monitor.history.query",HISTORY_PAGE);
 if(path==="/api/v1/exports")return ok("monitor.exports.create",VALID_EXPORT);
 if(path.startsWith("/api/v1/exports/"))return ok("monitor.exports.get",VALID_EXPORT);
 throw new Error(`unmapped test URL ${method} ${url}`);
};
it.each([
 ["status",(c:MonitorClient)=>c.status(),"/api/v1/status","GET",undefined],
 ["probes",(c:MonitorClient)=>c.probes(),"/api/v1/probes","GET",undefined],
 ["variables",(c:MonitorClient)=>c.variables("é","opaque"),"/api/v1/catalog/variables?query=%C3%A9&cursor=opaque&limit=100","GET",undefined],
 ["registers",(c:MonitorClient)=>c.registers("RCC",undefined),"/api/v1/catalog/registers?query=RCC&limit=100","GET",undefined],
 ["groups",(c:MonitorClient)=>c.groups("g2"),"/api/v1/groups?cursor=g2&limit=16","GET",undefined],
 ["create",(c:MonitorClient)=>c.createGroup({name:"Mine",description:"",intervalMs:250,items:[],authorized:true}),
  "/api/v1/groups","POST",'{"name":"Mine","description":"","intervalMs":250,"items":[],"authorized":true}'],
 ["update",(c:MonitorClient)=>c.updateGroup(VALID_GROUP.groupId,{expectedRevision:2,name:"Renamed",authorized:true}),
  `/api/v1/groups/${VALID_GROUP.groupId}`,"PATCH",'{"expectedRevision":2,"name":"Renamed","authorized":true}'],
 ["delete",(c:MonitorClient)=>c.deleteGroup(VALID_GROUP.groupId,{expectedRevision:2,authorized:true}),
  `/api/v1/groups/${VALID_GROUP.groupId}`,"DELETE",'{"expectedRevision":2,"authorized":true}'],
 ["import",(c:MonitorClient)=>c.importGroups({document:{schemaVersion:1,groups:[]},authorized:true}),
  "/api/v1/groups/import","POST",'{"document":{"schemaVersion":1,"groups":[]},"authorized":true}'],
 ["connect",(c:MonitorClient)=>c.connect({probeId:"probe-1"}),"/api/v1/probe/connect","POST",'{"probeId":"probe-1"}'],
 ["reconnect",(c:MonitorClient)=>c.reconnect(),"/api/v1/probe/reconnect","POST",undefined],
 ["release",(c:MonitorClient)=>c.release(),"/api/v1/probe/release","POST",undefined],
 ["start",(c:MonitorClient)=>c.start({groupId:"12345678-1234-5678-1234-567812345678",expectedRevision:2}),
  "/api/v1/sampling/start","POST",'{"groupId":"12345678-1234-5678-1234-567812345678","expectedRevision":2}'],
 ["pause",(c:MonitorClient)=>c.pause(),"/api/v1/sampling/pause","POST",undefined],
 ["resume",(c:MonitorClient)=>c.resume(),"/api/v1/sampling/resume","POST",undefined],
 ["stop",(c:MonitorClient)=>c.stop(),"/api/v1/sampling/stop","POST",undefined],
 ["history",(c:MonitorClient)=>c.history({startNs:9007199254740993n,endNs:9007199254741993n,limit:10000}),
  "/api/v1/history?startNs=9007199254740993&endNs=9007199254741993&limit=10000","GET",undefined],
 ["create export",(c:MonitorClient)=>c.createExport({startNs:9007199254740993n,endNs:9007199254741993n,format:"jsonl",authorized:true}),
  "/api/v1/exports","POST",'{"startNs":9007199254740993,"endNs":9007199254741993,"format":"jsonl","authorized":true}'],
 ["export status",(c:MonitorClient)=>c.exportStatus("e1"),"/api/v1/exports/e1","GET",undefined],
] as const)("constructs exact %s request",async(_name,invoke,url,method,body)=>{
  const fetchLike=vi.fn().mockResolvedValue(new Response(validResponseFor(url,method)));
  await invoke(new MonitorClient(fetchLike));
  expect(fetchLike).toHaveBeenCalledWith(url,expect.objectContaining({method,credentials:"same-origin",body:body??null}));
  const headers=new Headers(fetchLike.mock.calls[0]![1].headers);
  expect(headers.has("Origin")).toBe(false);
  expect(headers.has("Content-Type")).toBe(body!==undefined);
});

it("downloads without query Range or caller filename",async()=>{
  const fetchLike=vi.fn().mockResolvedValue(new Response("x",{headers:{
    "Content-Type":"text/csv","Content-Disposition":'attachment; filename="history-e1.csv"'}}));
  const result=await new MonitorClient(fetchLike).downloadExport("e1");
  expect(fetchLike).toHaveBeenCalledWith("/api/v1/exports/e1/download",
    {method:"GET",credentials:"same-origin",headers:new Headers(),body:null});
  expect(result.ok&&result.filename).toBe("history-e1.csv");
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/contract.test.ts -t "constructs exact|downloads without"`. Expected: FAIL because `MonitorClient` is absent.

- [ ] **Step 3: Implement every tested REST method and lossless nanosecond encoding.** Create the complete client below:

```ts
// src/api/client.ts
import {deletedGroupGuard,exportArtifactGuard,groupPageGuard,historyPageGuard,importedGroupsGuard,
 monitorStatusGuard,neverSuccessGuard,observationBindingGuard,parseEnvelopeText,pausedResultGuard,
 probePageGuard,registerPageGuard,releasedGuard,resumedResultGuard,samplerStartGuard,stoppedResultGuard,
 variablePageGuard,watchGroupGuard,type ApiResult,type CreateGroupRequest,type DataGuard,
 type DeleteGroupRequest,type DownloadResult,type ExportArtifact,type ExportRequest,
 type GroupImportDocument,type HistoryQuery,type UpdateGroupRequest} from "./contract";
type FetchLike=(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>;
const jsonHeaders=():Headers=>new Headers({"Content-Type":"application/json"});
const encode=(value:string):string=>encodeURIComponent(value);

export class MonitorClient {
  constructor(private readonly fetchLike:FetchLike=fetch){}
  private async envelope<T>(path:string,method:string,operation:string,guard:DataGuard<T>,body:string|null=null):Promise<ApiResult<T>>{
    const response=await this.fetchLike(path,{method,credentials:"same-origin",
      headers:body===null?new Headers():jsonHeaders(),body});
    return parseEnvelopeText(await response.text(),operation,guard);
  }
  status(){return this.envelope("/api/v1/status","GET","monitor.status",monitorStatusGuard);}
  probes(){return this.envelope("/api/v1/probes","GET","monitor.probes.list",probePageGuard);}
  variables(query:string,cursor?:string){const p=new URLSearchParams({query,limit:"100"});
    if(cursor!==undefined)p.set("cursor",cursor);return this.envelope(`/api/v1/catalog/variables?${p}`,
      "GET","monitor.catalog.variables",variablePageGuard);}
  registers(query:string,cursor?:string){const p=new URLSearchParams({query,limit:"100"});
    if(cursor!==undefined)p.set("cursor",cursor);return this.envelope(`/api/v1/catalog/registers?${p}`,
      "GET","monitor.catalog.registers",registerPageGuard);}
  groups(cursor?:string){const p=new URLSearchParams();if(cursor!==undefined)p.set("cursor",cursor);p.set("limit","16");
    return this.envelope(`/api/v1/groups?${p}`,"GET","monitor.groups.list",groupPageGuard);}
  createGroup(body:CreateGroupRequest){return this.envelope("/api/v1/groups","POST","monitor.groups.create",
    watchGroupGuard,JSON.stringify(body));}
  updateGroup(id:string,body:UpdateGroupRequest){return this.envelope(`/api/v1/groups/${encode(id)}`,
    "PATCH","monitor.groups.update",watchGroupGuard,JSON.stringify(body));}
  deleteGroup(id:string,body:DeleteGroupRequest){return this.envelope(`/api/v1/groups/${encode(id)}`,
    "DELETE","monitor.groups.delete",deletedGroupGuard,JSON.stringify(body));}
  importGroups(body:{document:GroupImportDocument;authorized:true}){return this.envelope("/api/v1/groups/import",
    "POST","monitor.groups.import",importedGroupsGuard,JSON.stringify(body));}
  connect(body:{probeId:string}){return this.envelope("/api/v1/probe/connect","POST","monitor.probe.connect",
    observationBindingGuard,JSON.stringify(body));}
  reconnect(){return this.envelope("/api/v1/probe/reconnect","POST","monitor.probe.reconnect",observationBindingGuard);}
  release(){return this.envelope("/api/v1/probe/release","POST","monitor.probe.release",releasedGuard);}
  start(body:{groupId:string;expectedRevision:number}){return this.envelope("/api/v1/sampling/start","POST",
    "monitor.sampling.start",samplerStartGuard,JSON.stringify(body));}
  pause(){return this.envelope("/api/v1/sampling/pause","POST","monitor.sampling.pause",pausedResultGuard);}
  resume(){return this.envelope("/api/v1/sampling/resume","POST","monitor.sampling.resume",resumedResultGuard);}
  stop(){return this.envelope("/api/v1/sampling/stop","POST","monitor.sampling.stop",stoppedResultGuard);}
  history(q:HistoryQuery){
    const p=new URLSearchParams({startNs:q.startNs.toString(),endNs:q.endNs.toString(),limit:String(Math.min(q.limit??10000,10000))});
    if(q.cursor!==undefined)p.set("cursor",q.cursor); if(q.runId!==undefined)p.set("runId",q.runId);
    if(q.groupId!==undefined)p.set("groupId",q.groupId);
    if(q.selector!==undefined){p.set("selectorKind",q.selector.kind);p.set("selector",q.selector.value);}
    return this.envelope(`/api/v1/history?${p}`,"GET","monitor.history.query",historyPageGuard);
  }
  createExport(r:ExportRequest){
    if(r.endNs<=r.startNs) return Promise.resolve<ApiResult<ExportArtifact>>({ok:false,code:"MONITOR_REQUEST_INVALID",message:"Export range is invalid"});
    const body=`{"startNs":${r.startNs},"endNs":${r.endNs},"format":${JSON.stringify(r.format)},"authorized":true}`;
    return this.envelope("/api/v1/exports","POST","monitor.exports.create",exportArtifactGuard,body);
  }
  exportStatus(id:string){return this.envelope(`/api/v1/exports/${encode(id)}`,"GET","monitor.exports.get",exportArtifactGuard);}
  async downloadExport(id:string):Promise<DownloadResult>{
    const response=await this.fetchLike(`/api/v1/exports/${encode(id)}/download`,
      {method:"GET",credentials:"same-origin",headers:new Headers(),body:null});
    if(!response.ok)return parseEnvelopeText(await response.text(),"monitor.exports.download",neverSuccessGuard);
    const disposition=response.headers.get("Content-Disposition")??"";
    const filename=/^attachment; filename="([A-Za-z0-9.-]+)"$/.exec(disposition)?.[1];
    const contentType=response.headers.get("Content-Type");
    if(filename===undefined||contentType===null)return {ok:false,code:"MONITOR_PROTOCOL_INVALID",message:"Monitor download is invalid"};
    return {ok:true,blob:await response.blob(),filename,contentType};
  }
}
```

`UpdateGroupRequest` is the closed compile-time allowlist shown in the wire-authority block; the request matrix proves its serialized keys.

- [ ] **Step 4: Run GREEN and typecheck.** From UI root run `& $npm run test -- tests/contract.test.ts -t "constructs exact|downloads without"; & $npm run typecheck`. Expected: PASS; the `9007199254740993` decimal survives in query and JSON token form.

- [ ] **Step 5: Commit the unit.** Stage only `src/api/client.ts` and `tests/contract.test.ts`; commit `feat(STM32TK-0502): construct exact monitor REST requests`.

### Task 4: Scrub the Fragment and Render a Secret-Free Bootstrap Error

**Files:** create `src/bootstrap.ts`, `src/main.tsx`, `src/app.tsx`, `src/styles.css`, and `tests/bootstrap.test.ts`.

**Interfaces:** produces `takeFragmentToken(windowLike):string|null`, `bootstrapFromFragment(windowLike,fetchLike):Promise<ApiResult<{authenticated:true}>>`, and `renderStartupError(documentLike):void`. Preact is dynamically imported only after successful bootstrap.

- [ ] **Step 1: Write the failing ordering and no-secret tests.** Create:

```ts
// tests/bootstrap.test.ts
import {expect,it,vi} from "vitest";
import {bootstrapFromFragment,renderStartupError,takeFragmentToken} from "../src/bootstrap";

const TOKEN="a".repeat(64);
it("scrubs the only valid fragment before bearer bootstrap",async()=>{
  const order:string[]=[];
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const replace=vi.spyOn(window.history,"replaceState").mockImplementation((...args)=>{
    order.push("scrub");History.prototype.replaceState.apply(window.history,args);});
  const fetchLike=vi.fn(async(_url,init)=>{order.push("fetch");
    expect(window.location.hash).toBe("");
    expect(new Headers(init?.headers).get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(new Headers(init?.headers).has("Origin")).toBe(false);
    expect(init).toMatchObject({method:"POST",credentials:"same-origin",body:null});
    return new Response(JSON.stringify({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",
      monitorVersion:"0.5.0",ok:true,operation:"monitor.auth.bootstrap",code:"OK",message:"",
      data:{authenticated:true},details:{}}));});
  const result=await bootstrapFromFragment(window,fetchLike);
  expect(order).toEqual(["scrub","fetch"]); expect(result).toEqual({ok:true,data:{authenticated:true}});
  expect(window.location.href).not.toContain(TOKEN);replace.mockRestore();
});

it.each(["","#token=A"+"a".repeat(63),`#token=${TOKEN}&token=${TOKEN}`,
  "#access_token="+TOKEN,"#token="+TOKEN+"&extra=1"])("rejects fragment %s without fetch",async hash=>{
  window.history.replaceState(null,"",`/${hash}`);const fetchLike=vi.fn();
  const result=await bootstrapFromFragment(window,fetchLike);
  expect(result).toEqual({ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"});
  expect(window.location.hash).toBe("");expect(fetchLike).not.toHaveBeenCalled();
});

it("ignores a query token and creates no normal state or request",async()=>{
 window.history.replaceState(null,"",`/?token=${TOKEN}`);const fetchLike=vi.fn(),mount=vi.fn();
 const result=await bootstrapFromFragment(window,fetchLike);if(result.ok)mount(result.data);
 expect(result.ok).toBe(false);expect(fetchLike).not.toHaveBeenCalled();expect(mount).not.toHaveBeenCalled();
});

it("returns only fixed startup copy on bootstrap failure",async()=>{
  window.history.replaceState(null,"",`/#token=${TOKEN}`);
  const result=await bootstrapFromFragment(window,vi.fn().mockRejectedValue(new Error(TOKEN)));
  expect(result).toEqual({ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"});
  expect(JSON.stringify(result)).not.toContain(TOKEN);
  renderStartupError(document);expect(document.querySelector('[role="alert"]')?.textContent).toBe("Monitor could not start");
  expect(document.body.textContent).not.toContain(TOKEN);
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/bootstrap.test.ts`. Expected: FAIL because `src/bootstrap.ts` is absent.

- [ ] **Step 3: Implement the matching synchronous scrub and delayed Preact import.** Create:

```ts
// src/bootstrap.ts
import {authenticatedGuard,parseEnvelopeText,type ApiResult} from "./api/contract";
export function takeFragmentToken(windowLike:Pick<Window,"location"|"history">):string|null{
  const raw=windowLike.location.hash.startsWith("#")?windowLike.location.hash.slice(1):"";
  windowLike.history.replaceState(null,"","/");
  const params=new URLSearchParams(raw);
  const values=params.getAll("token");
  return windowLike.location.search===""&&[...params.keys()].every(k=>k==="token")&&values.length===1&&
    /^[0-9a-f]{64}$/.test(values[0]!)?values[0]!:null;
}
export async function bootstrapFromFragment(windowLike:Window,fetchLike:typeof fetch):Promise<ApiResult<{authenticated:true}>>{
  let token:string|null=takeFragmentToken(windowLike);
  if(token===null)return {ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"};
  try{
    const response=await fetchLike("/api/v1/auth/bootstrap",{method:"POST",credentials:"same-origin",
      headers:new Headers({Authorization:`Bearer ${token}`}),body:null});
    return parseEnvelopeText(await response.text(),"monitor.auth.bootstrap",authenticatedGuard);
  }catch{return {ok:false,code:"MONITOR_BOOTSTRAP_FAILED",message:"Monitor could not start"};
  }finally{token=null;}
}
export function renderStartupError(documentLike:Document):void{
 const host=documentLike.getElementById("app")??documentLike.body;const alert=documentLike.createElement("p");
 alert.setAttribute("role","alert");alert.textContent="Monitor could not start";host.replaceChildren(alert);
}
```

```tsx
// src/main.tsx
import {bootstrapFromFragment,renderStartupError} from "./bootstrap";
import "./styles.css";
const result=await bootstrapFromFragment(window,fetch);
if(!result.ok){renderStartupError(document);}
else {const [{render,h},{App}]=await Promise.all([import("preact"),import("./app")]);
  render(h(App,{}),document.getElementById("app")!);}
```

```tsx
// src/app.tsx -- compile-safe shell expanded by later component units.
export function App():JSX.Element{return <main aria-label="STM32 Monitor">Monitor loading</main>}
```

The module contains no console logging and never reads query parameters or browser storage. `credentials:"same-origin"` is mandatory so the browser accepts the bootstrap `Set-Cookie`; the request remains Bearer-authenticated and JavaScript does not attempt to set the forbidden `Origin` header. The later real-aiohttp Playwright gate must assert that the bootstrap request carries Bearer, the response cookie is HttpOnly, and subsequent status GET and live WebSocket requests are bearerless and succeed with that cookie.

- [ ] **Step 4: Run GREEN, typecheck, and secret scan.** From UI root run `& $npm run test -- tests/bootstrap.test.ts; & $npm run typecheck`; from repository root run `rg -n "localStorage|sessionStorage|indexedDB|caches\.|serviceWorker|console\." tools/stm32-monitor/ui/src`. Expected: tests/typecheck PASS and the scan has no match.

- [ ] **Step 5: Commit the unit.** Stage only `src/bootstrap.ts`, `src/main.tsx`, `src/app.tsx`, `src/styles.css`, and `tests/bootstrap.test.ts`; commit `feat(STM32TK-0502): bootstrap from a scrubbed fragment`.

### Task 5: Parse the Live Stream Without Client Messages

**Files:** create `src/api/live.ts`; modify `tests/contract.test.ts`.

**Interfaces:** produces `LiveClient.connect(afterEventId?:EventId):WebSocket`, `LiveClient.close():void`, and callback delivery of only the validated envelope's `data` event as `MonitorAction={type:"live.event";event,subscriberDropped}`. Cookie authentication is browser-managed same-origin WebSocket state.

- [ ] **Step 1: Write the failing WebSocket construction and dispatch test.** Append:

```ts
// tests/contract.test.ts
it("opens only the same-origin live route and never sends a client message",()=>{
  const sockets:FakeSocket[]=[];
  const factory=vi.fn((url:string)=>{const socket=new FakeSocket(url);sockets.push(socket);return socket as never;});
  const actions:MonitorAction[]=[];
  const client=new LiveClient("http://127.0.0.1:43125",factory,a=>actions.push(a));
  client.connect("9223372036854775807");
  expect(factory).toHaveBeenCalledWith("ws://127.0.0.1:43125/api/v1/live?afterEventId=9223372036854775807");
  sockets[0]!.emit("message",{data:'{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.5.0",'+
   '"monitorVersion":"0.5.0","ok":true,"operation":"monitor.live","code":"OK","message":"",'+
   '"data":{"eventId":42,"type":"heartbeat","data":{"stateRevision":3,'+
   '"capturedAtUtc":"2026-08-10T00:00:00.000000Z"}},"details":{"subscriberDropped":2}}'});
  expect(actions).toEqual([{type:"live.event",event:{eventId:"42",type:"heartbeat",
    data:{stateRevision:3,capturedAtUtc:"2026-08-10T00:00:00.000000Z"}},subscriberDropped:2}]);
  expect(sockets[0]!.send).not.toHaveBeenCalled();
});

it.each([undefined,"0","01","-1","9223372036854775808","1.5"])("omits or rejects invalid afterEventId %s",value=>{
  const factory=vi.fn((url:string)=>new FakeSocket(url) as never);
  const client=new LiveClient("http://127.0.0.1:43125",factory,vi.fn());
  if(value===undefined)expect(()=>client.connect(value)).not.toThrow();
  else expect(()=>client.connect(value)).toThrow("afterEventId");
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/contract.test.ts -t "live route|afterEventId"`. Expected: FAIL because `LiveClient` is absent.

- [ ] **Step 3: Implement the matching constructor and one-way event adapter.** Create:

```ts
// src/api/live.ts
import {eventIdGuard,parseLiveEnvelopeText,type EventId,type MonitorAction} from "./contract";
type SocketFactory=(url:string)=>WebSocket;
export class LiveClient{
  private socket:WebSocket|null=null;
  constructor(private readonly origin:string,private readonly factory:SocketFactory,
    private readonly dispatch:(action:MonitorAction)=>void){}
  connect(afterEventId?:EventId):WebSocket{
    if(afterEventId!==undefined&&!eventIdGuard(afterEventId))
      throw new Error("afterEventId is invalid");
    const url=new URL("/api/v1/live",this.origin); url.protocol=url.protocol==="https:"?"wss:":"ws:";
    if(afterEventId!==undefined)url.searchParams.set("afterEventId",String(afterEventId));
    const socket=this.factory(url.toString()); this.socket=socket;
    socket.addEventListener("message",event=>{
      if(typeof event.data!=="string")return;
      const parsed=parseLiveEnvelopeText(event.data);
      if(parsed===null)this.dispatch({type:"request.failed",scope:"live",code:"MONITOR_PROTOCOL_INVALID",
        message:"Monitor live event is invalid"});
      else this.dispatch({type:"live.event",event:parsed.event,subscriberDropped:parsed.subscriberDropped});
    });
    return socket;
  }
  close():void{this.socket?.close(1000,"view closed");this.socket=null;}
}
```

No production method calls `socket.send`, no alternate query is accepted, and malformed events are converted into a fixed `request.failed` protocol action without including raw payload text.

- [ ] **Step 4: Run GREEN and source scan.** From UI root run `& $npm run test -- tests/contract.test.ts -t "live route|afterEventId"; & $npm run typecheck`; from repository root run `rg -n "\.send\(|new WebSocket" tools/stm32-monitor/ui/src`. Expected: PASS; the only constructor is `src/api/live.ts` and `.send(` has no match.

- [ ] **Step 5: Commit the unit.** Stage only `src/api/live.ts` and `tests/contract.test.ts`; commit `feat(STM32TK-0502): adapt exact one-way live events`.

### Task 6: Load Initial State and Enforce Authoritative Reducer Identity

**Files:** create `src/state/model.ts`, `reducer.ts`, `selectors.ts`, and `tests/reducer.test.ts`; modify `src/api/client.ts` only to expose `loadInitial(client)`.

**Interfaces:** produces `initialMonitorState`, `reduceMonitor(state,action):MonitorState`, `loadInitial(client):Promise<ApiResult<InitialSnapshot>>`, `currentAfterEventId(state):EventId|undefined`, and `needsStatusRefresh(state):boolean`. Initial loading starts status, probes, and first group page together, then follows group cursors until null. Catalog identity includes kind, query, binding epoch, and requested cursor; selected group and its ordered draft are reducer state shared by GroupPanel and Catalog.

- [ ] **Step 1: Write the failing loader and identity-transition tests.** Create:

```ts
// tests/reducer.test.ts
import {expect,it,vi} from "vitest";
import {loadInitial} from "../src/api/client";
import type {ApiResult,GroupPage,LiveEvent,MonitorAction} from "../src/api/contract";
import type {MonitorClient} from "../src/api/client";
import {initialMonitorState,reduceMonitor} from "../src/state/reducer";
import {VALID_BINDING,VALID_GROUP,VALID_SAMPLE_BATCH,VALID_STATUS} from "./fixtures";

it("starts status probes and first group page before following opaque group cursors",async()=>{
  const started:string[]=[]; const release:Record<string,()=>void>={};
  const gate=<T,>(name:string,data:T)=>new Promise<ApiResult<T>>(resolve=>{
    started.push(name);release[name]=()=>resolve({ok:true,data});});
  const client={status:()=>gate("status",VALID_STATUS),probes:()=>gate("probes",{probes:[]}),
    groups:(cursor?:string):Promise<ApiResult<GroupPage>>=>gate(cursor??"groups-1",cursor?
      {groups:[],nextCursor:null,revision:"b".repeat(64)}:
      {groups:[VALID_GROUP],nextCursor:"opaque-2",revision:"a".repeat(64)})} satisfies Pick<MonitorClient,"status"|"probes"|"groups">;
  const pending=loadInitial(client);
  expect(started).toEqual(["status","probes","groups-1"]);
  release.status!();release.probes!();release["groups-1"]!();await Promise.resolve();
  expect(started).toContain("opaque-2");release["opaque-2"]!();
  expect(await pending).toMatchObject({ok:true,data:{groups:[VALID_GROUP]}});
});

it("ignores old state revision and rejects a mismatched sample as stale",()=>{
  const loaded=reduceMonitor(initialMonitorState,{type:"initial.loaded",status:VALID_STATUS,
    probes:[],groups:[VALID_GROUP],groupRevision:"a".repeat(64)});
  const current=reduceMonitor(loaded,{type:"live.event",event:{eventId:"2",type:"state",
    data:{stateRevision:5,gap:false,status:VALID_STATUS}},subscriberDropped:0});
  const older=reduceMonitor(current,{type:"live.event",event:{eventId:"3",type:"state",
    data:{stateRevision:4,gap:false,status:{...VALID_STATUS,probeConnected:false}}},subscriberDropped:0});
  expect(older.status).toBe(current.status);expect(older.lastEventId).toBe("3");
  const wrong={...VALID_SAMPLE_BATCH,binding:{...VALID_SAMPLE_BATCH.binding,workspaceId:"f".repeat(24)}};
  const stale=reduceMonitor(older,{type:"live.event",event:{eventId:"4",type:"sample",
    data:{batch:wrong,serviceSubscriberDrops:0}},subscriberDropped:0});
  expect(stale.transport.stale).toBe(true); expect(stale.live.rows.size).toBe(0);
});

it.each([
  ["gap",{type:"live.event",event:{eventId:"5",type:"state",data:{stateRevision:6,gap:true,status:VALID_STATUS}},subscriberDropped:0}],
  ["binding epoch",{type:"status.loaded",status:{...VALID_STATUS,sampling:{...VALID_STATUS.sampling,bindingEpoch:2}}}],
  ["run",{type:"live.event",event:{eventId:"6",type:"sample",data:{batch:{...VALID_SAMPLE_BATCH,runId:"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},serviceSubscriberDrops:0}}}],
] satisfies readonly (readonly [string,MonitorAction])[])("resets continuity on %s",(_name,action)=>{
  const seeded={...initialMonitorState,status:VALID_STATUS,stateRevision:5,
    live:{...initialMonitorState.live,runId:VALID_SAMPLE_BATCH.runId,points:new Map([["variable:counter",[{x:1,y:1}]]])},
    zoom:{start:20,end:80}};
  const next=reduceMonitor(seeded,action);
  expect(next.live.points.size).toBe(0);expect(next.zoom).toEqual({start:0,end:100});
  expect(next.notices.at(-1)?.kind).toBe("view-reset");
});

it.each(["leaseId","dwarfSha256"] as const)("rejects a %s-only binding change",field=>{
 const accepted={...initialMonitorState,status:VALID_STATUS,lastEventId:"10",
  live:{...initialMonitorState.live,binding:VALID_BINDING,runId:VALID_SAMPLE_BATCH.runId}};
 const binding={...VALID_BINDING,[field]:field==="leaseId"?"other-lease":"f".repeat(64)};
 const next=reduceMonitor(accepted,{type:"live.event",event:{eventId:"11",type:"sample",
  data:{batch:{...VALID_SAMPLE_BATCH,binding},serviceSubscriberDrops:0}},subscriberDropped:0});
 expect(next.transport.stale).toBe(true);expect(next.live.rows.size).toBe(0);
});

it.each([
 {eventId:"21",type:"hello",data:{protocol:"stm32-toolkit-monitor/1",toolkitVersion:"0.5.0",monitorVersion:"0.5.0",stateRevision:5}},
 {eventId:"21",type:"state",data:{stateRevision:6,gap:false,status:VALID_STATUS}},
 {eventId:"21",type:"sample",data:{batch:VALID_SAMPLE_BATCH,serviceSubscriberDrops:0}},
 {eventId:"21",type:"heartbeat",data:{stateRevision:5,capturedAtUtc:"2026-08-10T00:00:00.000000Z"}},
 ] satisfies readonly LiveEvent[])("rejects duplicate and out-of-order $type events",event=>{
 const seeded={...initialMonitorState,lastEventId:"21"};
 for(const eventId of ["21","20"])expect(reduceMonitor(seeded,
  {type:"live.event",event:{...event,eventId} as LiveEvent,subscriberDropped:0})).toBe(seeded);
});

it("accepts SampleBatch.values and stores compact metrics without inventing status fields",()=>{
 const loaded=reduceMonitor(initialMonitorState,{type:"initial.loaded",status:VALID_STATUS,
  probes:[],groups:[VALID_GROUP],groupRevision:"a".repeat(64)});
 const next=reduceMonitor(loaded,{type:"live.event",event:{eventId:"1",type:"sample",
  data:{batch:VALID_SAMPLE_BATCH,serviceSubscriberDrops:2}},subscriberDropped:0});
 expect(next.live.latestBatch?.values).toEqual(VALID_SAMPLE_BATCH.values);
 expect(next.live.drops).toEqual({subscriber:0,history:0,deadline:0,service:2});
});

it("rejects a catalog page whose kind query epoch or requested cursor is stale",()=>{
 const loaded=reduceMonitor(initialMonitorState,{type:"initial.loaded",status:VALID_STATUS,
  probes:[],groups:[VALID_GROUP],groupRevision:"a".repeat(64)});
 const pending=reduceMonitor(loaded,{type:"catalog.requested",catalog:"variables",query:"new",
  bindingEpoch:1,cursor:undefined});
 const stale=reduceMonitor(pending,{type:"catalog.loaded",catalog:"variables",query:"old",
  bindingEpoch:1,cursor:undefined,items:[],nextCursor:"stale"});
 expect(stale).toBe(pending);
 const first=reduceMonitor(pending,{type:"catalog.loaded",catalog:"variables",query:"new",
  bindingEpoch:1,cursor:undefined,items:[],nextCursor:"cursor-2"});
 const nextPending=reduceMonitor(first,{type:"catalog.requested",catalog:"variables",query:"new",
  bindingEpoch:1,cursor:"cursor-2"});
 expect(reduceMonitor(nextPending,{type:"catalog.loaded",catalog:"variables",query:"new",
  bindingEpoch:1,cursor:"different",items:[],nextCursor:null})).toBe(nextPending);
});

it("shares one selected group draft and preserves unique add/remove order",()=>{
 const loaded=reduceMonitor(initialMonitorState,{type:"initial.loaded",status:VALID_STATUS,
  probes:[],groups:[VALID_GROUP],groupRevision:"a".repeat(64)});
 const added=reduceMonitor(loaded,{type:"group.item.added",watch:{kind:"register",registerPath:"RCC.CSR"}});
 const duplicate=reduceMonitor(added,{type:"group.item.added",watch:{kind:"variable",expression:"counter"}});
 expect(duplicate.groupDraft.items).toEqual([VALID_GROUP.items[0],{kind:"register",registerPath:"RCC.CSR"}]);
 const removed=reduceMonitor(duplicate,{type:"group.item.removed",key:"variable:counter"});
 expect(removed.groupDraft.items).toEqual([{kind:"register",registerPath:"RCC.CSR"}]);
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/reducer.test.ts`. Expected: FAIL because the state modules are absent.

- [ ] **Step 3: Implement immutable state, initial loading, and exact identity checks.** The reducer core must use this matching structure:

```ts
// src/state/model.ts
import type {EventId,ExportArtifact,GroupDraft,HistoryPage,HistoryQuery,MonitorStatus,ObservationBinding,
 ProbeInfo,PublicFailure,SampleBatch,SampleValue,VariableDescriptor,RegisterDescriptor,WatchGroup,WatchItem} from "../api/contract";
export type DropTotals={subscriber:number;history:number;deadline:number;service:number};
export type LivePoint={x:number;y:number|null};
export type NumericSeries={name:string;points:readonly LivePoint[]};
export type LiveRow={key:string;selector:string;watch:WatchItem;typeName:string|null;
 displayValue:string;rawHex:string|null;capturedAtUtc:string;numericValue:number|null;
 trend:"none"|"up"|"down"|"flat";errorCode:string|null};
export type LiveState={rows:ReadonlyMap<string,LiveRow>;points:ReadonlyMap<string,readonly LivePoint[]>;
 latestBatch:SampleBatch|null;runId:string|null;bindingEpoch:number|null;
 binding:ObservationBinding|null;gap:boolean;actualRateHz:number;latencyNs:number;drops:DropTotals};
export type CatalogSlot<T,K extends "variables"|"registers">={kind:K;query:string;bindingEpoch:number;
 cursor:string|undefined;items:readonly T[];nextCursor:string|null};
export type MonitorNotice={id:string;kind:"view-reset"|"drop";text:string};
export type MonitorState={status:MonitorStatus|null;probes:readonly ProbeInfo[];groups:readonly WatchGroup[];
 groupRevision:string|null;selectedGroupId:string|null;groupDraft:GroupDraft;stateRevision:number;
 lastEventId:EventId|undefined;
 catalog:{variables:CatalogSlot<VariableDescriptor,"variables">|null;
  registers:CatalogSlot<RegisterDescriptor,"registers">|null};
 canReconnect:boolean;live:LiveState;selectedSeries:readonly string[];zoom:{start:number;end:number};
 transport:{open:boolean;stale:boolean;needsStatusRefresh:boolean};
 history:{query:HistoryQuery;page:HistoryPage}|null;verifiedExport:ExportArtifact|null;
 notices:readonly MonitorNotice[];
 failures:Readonly<Record<string,PublicFailure|undefined>>};
export type InitialSnapshot={status:MonitorStatus;probes:readonly ProbeInfo[];groups:readonly WatchGroup[];
 groupRevision:string};
export type HistoryRow={binding:ObservationBinding;groupId:string;runId:string;sequence:number;
 capturedAtUtc:string;startOrdinal:number;valueOrdinal:number;value:SampleValue};
export const emptyGroupDraft:GroupDraft={sourceGroupId:null,expectedRevision:null,name:"",description:"",
 intervalMs:250,items:[]};
export const draftFromGroup=(group:WatchGroup):GroupDraft=>({sourceGroupId:group.groupId,
 expectedRevision:group.revision,name:group.name,description:group.description,
 intervalMs:group.intervalMs,items:group.items});

// src/state/reducer.ts
import type {LiveEvent,MonitorAction,MonitorStatus,ObservationBinding,WatchItem} from "../api/contract";
import {draftFromGroup,emptyGroupDraft,type LiveState,type MonitorNotice,type MonitorState} from "./model";
export const initialMonitorState:MonitorState={status:null,probes:[],groups:[],groupRevision:null,
  selectedGroupId:null,groupDraft:emptyGroupDraft,stateRevision:-1,lastEventId:undefined,canReconnect:false,
  catalog:{variables:null,registers:null},
  live:{rows:new Map(),points:new Map(),latestBatch:null,runId:null,bindingEpoch:null,binding:null,gap:false,
   actualRateHz:0,latencyNs:0,drops:{subscriber:0,history:0,deadline:0,service:0}},
  selectedSeries:[],zoom:{start:0,end:100},transport:{open:false,stale:false,needsStatusRefresh:false},
  history:null,verifiedExport:null,notices:[],failures:{}};

const statusMatchesBinding=(status:MonitorStatus,b:ObservationBinding):boolean =>
 status.workspaceId===b.workspaceId&&status.sessionId===b.sessionId&&
 status.probe.connected&&status.probe.probeId===b.probeId&&
 status.project.logicalProjectId===b.logicalProjectId&&status.project.targetDevice===b.targetDevice&&
 status.firmware!==null&&status.firmware.buildId===b.buildId&&
 status.firmware.elfSha256===b.elfSha256&&status.firmware.inputSnapshotSha256===b.inputSnapshotSha256&&
 status.firmware.gitHead===b.gitHead&&status.firmware.gitDirty===b.gitDirty&&
 status.firmware.targetDevice===b.targetDevice;
const sameBinding=(a:ObservationBinding,b:ObservationBinding):boolean =>
 a.workspaceId===b.workspaceId&&a.sessionId===b.sessionId&&a.probeId===b.probeId&&
 a.physicalTarget===b.physicalTarget&&a.flashSessionId===b.flashSessionId&&a.leaseId===b.leaseId&&
 a.logicalProjectId===b.logicalProjectId&&a.targetDevice===b.targetDevice&&a.buildId===b.buildId&&
 a.elfSha256===b.elfSha256&&a.inputSnapshotSha256===b.inputSnapshotSha256&&
 a.gitHead===b.gitHead&&a.gitDirty===b.gitDirty&&a.dwarfSha256===b.dwarfSha256&&a.svdSha256===b.svdSha256;

export const emptyLive=(status:MonitorStatus):LiveState=>({rows:new Map(),points:new Map(),latestBatch:null,
 runId:status.sampling.runId,bindingEpoch:status.sampling.bindingEpoch,binding:null,gap:false,
 actualRateHz:0,latencyNs:0,drops:{subscriber:status.sampling.subscriberDrops,
  history:status.sampling.historyDrops,deadline:status.sampling.deadlineDrops,
  service:status.sampling.serviceDrops}});
const acceptSample=(state:MonitorState,event:Extract<LiveEvent,{type:"sample"}>):MonitorState=>{
  const {batch,serviceSubscriberDrops}=event.data;
  return {...state,lastEventId:event.eventId,live:{...state.live,latestBatch:batch,runId:batch.runId,
    bindingEpoch:state.status!.sampling.bindingEpoch,binding:batch.binding,gap:false,
    actualRateHz:batch.actualRateHz,latencyNs:batch.latencyNs,
    drops:{subscriber:batch.subscriberDrops,history:batch.historyDrops,deadline:batch.deadlineDrops,
      service:state.status!.sampling.serviceDrops+serviceSubscriberDrops}}};
};
const reduceNonSampleAction=(state:MonitorState,action:Exclude<MonitorAction,{type:"live.event"}>):MonitorState=>{
  if(action.type==="initial.loaded"){const selected=action.groups[0]??null;return {...state,status:action.status,
   probes:action.probes,groups:action.groups,groupRevision:action.groupRevision,
   selectedGroupId:selected?.groupId??null,groupDraft:selected===null?emptyGroupDraft:draftFromGroup(selected),
   canReconnect:action.status.probe.connected,live:emptyLive(action.status)};}
  if(action.type==="status.loaded"){
   const reset=state.status!==null&&(state.status.sampling.bindingEpoch!==action.status.sampling.bindingEpoch||
     state.status.sampling.runId!==action.status.sampling.runId);
   return {...state,status:action.status,live:reset?emptyLive(action.status):state.live,
     zoom:reset?{start:0,end:100}:state.zoom,
     catalog:reset?{variables:null,registers:null}:state.catalog,
     transport:{...state.transport,needsStatusRefresh:false},
     notices:reset?[...state.notices,{id:`view-reset-status-${action.status.sampling.bindingEpoch}-${action.status.sampling.runId??"none"}`,
      kind:"view-reset",text:"Live view reset for a new binding or run"}]:state.notices};
  }
  if(action.type==="probes.loaded")return {...state,probes:action.probes};
  if(action.type==="probe.reconnectAvailable")return {...state,canReconnect:action.available};
  if(action.type==="catalog.requested"){
   if(action.catalog==="variables"){const prior=state.catalog.variables,append=action.cursor!==undefined&&
     prior!==null&&prior.query===action.query&&prior.bindingEpoch===action.bindingEpoch&&prior.nextCursor===action.cursor;
    return {...state,catalog:{...state.catalog,variables:{kind:"variables",query:action.query,
     bindingEpoch:action.bindingEpoch,cursor:action.cursor,items:append?prior.items:[],nextCursor:null}}};}
   const prior=state.catalog.registers,append=action.cursor!==undefined&&prior!==null&&
    prior.query===action.query&&prior.bindingEpoch===action.bindingEpoch&&prior.nextCursor===action.cursor;
   return {...state,catalog:{...state.catalog,registers:{kind:"registers",query:action.query,
    bindingEpoch:action.bindingEpoch,cursor:action.cursor,items:append?prior.items:[],nextCursor:null}}};
  }
  if(action.type==="catalog.loaded"){
   if(state.status?.sampling.bindingEpoch!==action.bindingEpoch)return state;
   if(action.catalog==="variables"){const pending=state.catalog.variables;
    if(pending===null||pending.query!==action.query||pending.bindingEpoch!==action.bindingEpoch||
       pending.cursor!==action.cursor)return state;const items=action.cursor===undefined?action.items:
     [...pending.items,...action.items];return {...state,catalog:{...state.catalog,variables:{kind:"variables",
      query:action.query,bindingEpoch:action.bindingEpoch,cursor:action.cursor,items,nextCursor:action.nextCursor}}};}
   const pending=state.catalog.registers;if(pending===null||pending.query!==action.query||
    pending.bindingEpoch!==action.bindingEpoch||pending.cursor!==action.cursor)return state;
   const items=action.cursor===undefined?action.items:[...pending.items,...action.items];
   return {...state,catalog:{...state.catalog,registers:{kind:"registers",query:action.query,
    bindingEpoch:action.bindingEpoch,cursor:action.cursor,items,nextCursor:action.nextCursor}}};
  }
  if(action.type==="groups.loaded"){const selected=action.groups.find(g=>g.groupId===state.selectedGroupId)??
    action.groups[0]??null;return {...state,groups:action.groups,groupRevision:action.revision,
    selectedGroupId:selected?.groupId??null,groupDraft:selected===null?emptyGroupDraft:draftFromGroup(selected)};}
  if(action.type==="group.selected"){const selected=action.groupId===null?null:
    state.groups.find(group=>group.groupId===action.groupId)??null;return {...state,
    selectedGroupId:selected?.groupId??null,groupDraft:selected===null?emptyGroupDraft:draftFromGroup(selected)};}
  if(action.type==="group.draft.changed")return {...state,groupDraft:action.draft};
  if(action.type==="group.item.added"){const key=(w:WatchItem)=>w.kind==="variable"?`variable:${w.expression}`:`register:${w.registerPath}`;
    return state.groupDraft.items.some(item=>key(item)===key(action.watch))?state:{...state,
     groupDraft:{...state.groupDraft,items:[...state.groupDraft.items,action.watch]}};}
  if(action.type==="group.item.removed"){const items=state.groupDraft.items.filter(w=>
    (w.kind==="variable"?`variable:${w.expression}`:`register:${w.registerPath}`)!==action.key);
    return items.length===state.groupDraft.items.length?state:{...state,groupDraft:{...state.groupDraft,items}};}
  if(action.type==="series.toggled"){const selected=state.selectedSeries.includes(action.key);
    if(selected)return {...state,selectedSeries:state.selectedSeries.filter(key=>key!==action.key)};
    const row=state.live.rows.get(action.key);return row?.numericValue!==null&&row!==undefined&&state.selectedSeries.length<8?
     {...state,selectedSeries:[...state.selectedSeries,action.key]}:state;}
  if(action.type==="history.loaded")return {...state,history:{query:action.query,page:action.page}};
  if(action.type==="export.verified")return {...state,verifiedExport:action.artifact};
  if(action.type==="request.failed")return {...state,failures:{...state.failures,
   [action.scope]:{code:action.code,message:action.message}}};
  if(action.type==="transport.stale")return {...state,transport:{...state.transport,stale:true,open:false}};
  if(action.type==="transport.open")return {...state,transport:{...state.transport,stale:false,open:true}};
  if(action.type==="zoom.reset")return {...state,zoom:{start:0,end:100}};
  if(action.type==="zoom.in")return {...state,zoom:{start:Math.min(100,state.zoom.start+10),end:Math.max(0,state.zoom.end-10)}};
  if(action.type==="zoom.out")return {...state,zoom:{start:Math.max(0,state.zoom.start-10),end:Math.min(100,state.zoom.end+10)}};
  const start=Math.min(100,Math.max(0,action.start)),end=Math.min(100,Math.max(0,action.end));
  return {...state,zoom:end>start?{start,end}:{start:0,end:100}};
};

export function reduceMonitor(state:MonitorState,action:MonitorAction):MonitorState{
  if(action.type==="live.event"&&state.lastEventId!==undefined&&
    BigInt(action.event.eventId)<=BigInt(state.lastEventId))return state;
  if(action.type==="live.event"&&action.subscriberDropped>0){state={...state,
    live:state.status===null?state.live:emptyLive(state.status),zoom:{start:0,end:100},
    transport:{...state.transport,needsStatusRefresh:true},notices:[...state.notices,
     {id:`view-reset-subscriber-${action.event.eventId}`,kind:"view-reset",
      text:`Live subscriber dropped ${action.subscriberDropped} event(s); status refresh required`}]};}
  if(action.type==="live.event"&&action.event.type==="hello")return {...state,
   stateRevision:Math.max(state.stateRevision,action.event.data.stateRevision),lastEventId:action.event.eventId,
   transport:{...state.transport,stale:false}};
  if(action.type==="live.event"&&action.event.type==="heartbeat")return {...state,
   lastEventId:action.event.eventId,transport:{...state.transport,stale:false}};
  if(action.type==="live.event"&&action.event.type==="state"){
    if(action.event.data.stateRevision<state.stateRevision)return {...state,lastEventId:action.event.eventId};
    const changed=state.status!==null&&(
      state.status.sampling.bindingEpoch!==action.event.data.status.sampling.bindingEpoch||
      state.status.sampling.runId!==action.event.data.status.sampling.runId);
   const reset=changed||action.event.data.gap;
   return {...state,status:action.event.data.status,stateRevision:action.event.data.stateRevision,
     lastEventId:action.event.eventId,live:reset?emptyLive(action.event.data.status):state.live,
     zoom:reset?{start:0,end:100}:state.zoom,
     transport:{...state.transport,stale:false,needsStatusRefresh:action.event.data.gap},
      notices:reset?[...state.notices,{id:`view-reset-event-${action.event.eventId}`,kind:"view-reset",
       text:action.event.data.gap?"Live event gap; status refresh required":
        "Live view reset for a new binding or run"}]:state.notices};
  }
  if(action.type==="live.event"&&action.event.type==="sample"){
    const prior=state.live.binding;
    if(state.status===null||!statusMatchesBinding(state.status,action.event.data.batch.binding)||
       (prior!==null&&!sameBinding(prior,action.event.data.batch.binding)))
      return {...state,lastEventId:action.event.eventId,transport:{...state.transport,stale:true}};
    const reset=state.live.runId!==null&&state.live.runId!==action.event.data.batch.runId;
    const base=reset?{...state,live:emptyLive(state.status),zoom:{start:0,end:100},
     notices:[...state.notices,{id:`view-reset-run-${action.event.eventId}`,kind:"view-reset" as const,
      text:"Live view reset for a new binding or run"}]}:state;
    return acceptSample(base,action.event);
  }
  return reduceNonSampleAction(state,action);
}
```

```ts
// src/state/selectors.ts
import type {EventId} from "../api/contract";
import type {MonitorState} from "./model";
export const currentAfterEventId=(state:MonitorState):EventId|undefined=>state.lastEventId;
export const needsStatusRefresh=(state:MonitorState):boolean=>state.transport.needsStatusRefresh;
```

```ts
// src/api/client.ts
import type {InitialSnapshot} from "../state/model";
export async function loadGroups(client:Pick<MonitorClient,"groups">):Promise<ApiResult<
 {groups:readonly WatchGroup[];revision:string}>>{const first=await client.groups();if(!first.ok)return first;
 const groups=[...first.data.groups];let cursor=first.data.nextCursor,revision=first.data.revision;
 while(cursor!==null){const page=await client.groups(cursor);if(!page.ok)return page;
  groups.push(...page.data.groups);cursor=page.data.nextCursor;revision=page.data.revision;}
 return {ok:true,data:{groups,revision}};
}
export async function loadInitial(client:Pick<MonitorClient,"status"|"probes"|"groups">):Promise<ApiResult<InitialSnapshot>>{
 const [status,probes,first]=await Promise.all([client.status(),client.probes(),client.groups()]);
 if(!status.ok)return status;if(!probes.ok)return probes;if(!first.ok)return first;
 const groups=[...first.data.groups];let cursor=first.data.nextCursor;let revision=first.data.revision;
 while(cursor!==null){const page=await client.groups(cursor);if(!page.ok)return page;
   groups.push(...page.data.groups);cursor=page.data.nextCursor;revision=page.data.revision;}
 return {ok:true,data:{status:status.data,probes:probes.data.probes,groups,groupRevision:revision}};
}
```

The typed code above is the complete reducer core. Catalog responses are accepted only when normalized query, pending request kind, and `bindingEpoch` all still match. Every branch consumes one of the closed `MonitorAction` variants; no string event, undeclared action, alias DTO field, or unlisted live discriminant is accepted.

- [ ] **Step 4: Run GREEN and branch coverage.** From UI root run `& $npm run test -- tests/reducer.test.ts; & $npm run typecheck; & $npm run test:coverage -- tests/reducer.test.ts`. Expected: PASS and each of `model.ts`, `reducer.ts`, and `selectors.ts` has branch coverage at least 90%.

- [ ] **Step 5: Commit the unit.** Stage only `src/state`, `src/api/client.ts`, and `tests/reducer.test.ts`; commit `feat(STM32TK-0502): enforce authoritative monitor state`.

### Task 7: Apply the Complete Bounded Browser-Cookie Auth Matrix

**Files:** modify `src/stm32_monitor/auth.py`, `service.py`, `tests/test_auth.py`, and `tests/test_service.py` only.

**Interfaces:** changes `MonitorAuth.authorize(...,method:str,fetch_site:str|None,websocket:bool)->str`. `service.py` supplies normalized request method, normalized `Sec-Fetch-Site`, and route-owned WS context; there is no caller-owned “safe” boolean.

- [ ] **Step 1: Write the full failing allow/deny matrix before production edits.** Replace the obsolete origin-only cookie test with this complete parameterization and update existing bearer service helpers to send exact `Origin`:

```python
# tests/test_auth.py
ORIGIN = "http://127.0.0.1:43125"

@pytest.mark.parametrize(
    ("method", "origin", "fetch_site", "websocket"),
    [
        ("GET", ORIGIN, None, False), ("GET", None, "same-origin", False),
        ("HEAD", ORIGIN, None, False), ("HEAD", None, "same-origin", False),
        ("GET", ORIGIN, None, True), ("GET", None, "same-origin", True),
        ("POST", ORIGIN, None, False), ("POST", ORIGIN, "same-origin", False),
        ("PATCH", ORIGIN, None, False), ("PUT", ORIGIN, None, False),
        ("DELETE", ORIGIN, None, False),
    ],
)
def test_cookie_safe_matrix_allows_only_proved_same_origin(
    method: str, origin: str | None, fetch_site: str | None, websocket: bool
) -> None:
    assert _auth().authorize(
        peer="127.0.0.1", host="127.0.0.1:43125", origin=origin,
        authorization="", cookie=TOKEN, bootstrap=False, method=method,
        fetch_site=fetch_site, websocket=websocket,
    ) == "cookie"

def _authorize_cookie(overrides: dict[str, object]) -> str:
    request = dict(peer="127.0.0.1", host="127.0.0.1:43125", origin=ORIGIN,
        authorization="", cookie=TOKEN, bootstrap=False, method="GET",
        fetch_site=None, websocket=False)
    request.update(overrides)
    return _auth().authorize(
        peer=request["peer"], host=request["host"], origin=request["origin"],
        authorization=request["authorization"], cookie=request["cookie"],
        bootstrap=request["bootstrap"], method=request["method"],
        fetch_site=request["fetch_site"], websocket=request["websocket"],
    )

@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"peer":"192.0.2.1"}, "MONITOR_PEER_REJECTED"),
        ({"host":"localhost:43125"}, "MONITOR_HOST_REJECTED"),
        ({"origin":"http://localhost:43125"}, "MONITOR_ORIGIN_REJECTED"),
        ({"origin":"null"}, "MONITOR_ORIGIN_REJECTED"),
        ({"fetch_site":"cross-site"}, "MONITOR_ORIGIN_REJECTED"),
        ({"fetch_site":"same-site"}, "MONITOR_ORIGIN_REJECTED"),
        ({"fetch_site":"none"}, "MONITOR_ORIGIN_REJECTED"),
        ({"origin":None,"fetch_site":None}, "MONITOR_AUTH_REQUIRED"),
        ({"method":"POST","origin":None,"fetch_site":"same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method":"PATCH","origin":None,"fetch_site":"same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method":"PUT","origin":None,"fetch_site":"same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method":"DELETE","origin":None,"fetch_site":"same-origin"}, "MONITOR_AUTH_REQUIRED"),
        ({"method":"OPTIONS"}, "MONITOR_AUTH_REQUIRED"),
        ({"method":"POST","websocket":True}, "MONITOR_AUTH_REQUIRED"),
        ({"bootstrap":True}, "MONITOR_AUTH_REQUIRED"),
    ],
)
def test_cookie_safe_matrix_denies_every_unproved_request(overrides: dict[str, object], code: str) -> None:
    from stm32_monitor.auth import MonitorAuthError
    with pytest.raises(MonitorAuthError) as caught:
        _authorize_cookie(overrides)
    assert caught.value.code == code

@pytest.mark.parametrize("origin", [None, "null", "http://localhost:43125"])
def test_bearer_requires_exact_origin_even_with_exact_token(origin: str | None) -> None:
    from stm32_monitor.auth import MonitorAuthError
    with pytest.raises(MonitorAuthError):
        _auth().authorize(peer="127.0.0.1",host="127.0.0.1:43125",origin=origin,
          authorization=f"Bearer {TOKEN}",cookie=None,bootstrap=True,method="POST",
          fetch_site="same-origin",websocket=False)

def test_exact_origin_bearer_and_bootstrap_still_work() -> None:
    assert _auth().authorize(peer="127.0.0.1",host="127.0.0.1:43125",origin=ORIGIN,
      authorization=f"Bearer {TOKEN}",cookie=None,bootstrap=True,method="POST",
      fetch_site="same-origin",websocket=False) == "bearer"
```

```python
# tests/test_service.py
def test_cookie_transport_matrix() -> None:
    async def scenario(_runtime, _service, endpoint) -> None:
        origin = endpoint.url
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as client:
            boot = await client.post(endpoint.url + "/api/v1/auth/bootstrap", headers={
                "Authorization": f"Bearer {TOKEN_BYTES.hex()}", "Origin": origin,
                "Sec-Fetch-Site": "same-origin"})
            assert boot.status == 200
            safe = await client.get(endpoint.url + "/api/v1/status",
                headers={"Sec-Fetch-Site":"same-origin"})
            assert safe.status == 200
            head = await client.head(endpoint.url + "/api/v1/status",
                headers={"Sec-Fetch-Site":"same-origin"})
            assert head.status == 200
            denied = await client.post(endpoint.url + "/api/v1/probe/release",
                headers={"Sec-Fetch-Site":"same-origin"})
            assert denied.status == 401
            ws = await client.ws_connect(endpoint.url + "/api/v1/live",
                headers={"Sec-Fetch-Site":"same-origin"})
            await ws.close()
    asyncio.run(_with_service(scenario))
```

The existing header-budget test remains active and all existing service bearer request dictionaries become `{"Authorization":...,"Origin":endpoint.url}`; mutation/body/query semantics remain otherwise byte-for-byte unchanged.

Before RED, mechanically update every accepted-base direct `authorize` call (production and tests) to pass the new evidence explicitly; this script fails if an old direct call remains instead of silently relying on defaults:

```powershell
$AuthorizeAstAudit = @'
import ast
from pathlib import Path

required = {"peer", "host", "origin", "authorization", "cookie", "bootstrap",
            "method", "fetch_site", "websocket"}
failures = []
for root in (Path("src"), Path("tests")):
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "authorize":
                continue
            keywords = {item.arg for item in node.keywords if item.arg is not None}
            if any(item.arg is None for item in node.keywords) or keywords != required:
                failures.append(f"{path}:{node.lineno}: authorize keywords={sorted(keywords)}")
if failures:
    raise SystemExit("\n".join(failures))
'@
$AuthorizeAstAudit | & $python312 -
if ($LASTEXITCODE -ne 0) { throw 'direct authorize AST migration audit failed' }
```

For each direct call, add `method=<the existing request method>`, `fetch_site=<the existing Sec-Fetch-Site value or None>`, and `websocket=<True only for the existing live-upgrade case>`; do not change its peer, Host, Origin, token, bootstrap flag, expected result, or request payload. The AST audit checks every multiline call and rejects `**kwargs`, positional evidence, missing keywords, or extra compatibility defaults; migration is complete only when both the audit and named suites pass.

- [ ] **Step 2: Run RED.** From `tools/stm32-monitor`, run `& $python312 -m pytest tests/test_auth.py::test_cookie_safe_matrix_allows_only_proved_same_origin tests/test_auth.py::test_cookie_safe_matrix_denies_every_unproved_request tests/test_auth.py::test_bearer_requires_exact_origin_even_with_exact_token tests/test_auth.py::test_exact_origin_bearer_and_bootstrap_still_work tests/test_service.py::test_cookie_transport_matrix -q`. Expected: FAIL because `authorize` lacks method/fetch-site/WS evidence and no-Origin safe cookie requests are rejected.

- [ ] **Step 3: Implement exactly the tested transport decision and service evidence flow.** Preserve token comparison, peer, Host, header budget, cookie attributes, public codes, and body/query gates:

```python
# auth.py, inside MonitorAuth.authorize after peer/Host checks
method = method.upper() if isinstance(method, str) else ""
if origin is not None and origin != self.origin:
    raise _error("MONITOR_ORIGIN_REJECTED", "Monitor Service Origin is invalid", 403)
if fetch_site is not None and fetch_site != "same-origin":
    raise _error("MONITOR_ORIGIN_REJECTED", "Monitor Service fetch site is invalid", 403)
bearer_ok = len(bearer) == 64 and secrets.compare_digest(bearer, self.token)
if bearer_ok:
    if origin != self.origin:
        raise _error("MONITOR_AUTH_REQUIRED", "Monitor Service authentication failed", 401)
    return "bearer"
cookie_matches = isinstance(cookie, str) and len(cookie) == 64 and secrets.compare_digest(cookie, self.token)
if bootstrap or not cookie_matches:
    raise _error("MONITOR_AUTH_REQUIRED", "Monitor Service authentication failed", 401)
safe_http = not websocket and method in {"GET", "HEAD"} and (
    origin == self.origin or (origin is None and fetch_site == "same-origin"))
safe_ws = websocket and method == "GET" and (
    origin == self.origin or (origin is None and fetch_site == "same-origin"))
mutation = not websocket and method in {"POST", "PATCH", "PUT", "DELETE"} and origin == self.origin
if safe_http or safe_ws or mutation:
    return "cookie"
raise _error("MONITOR_AUTH_REQUIRED", "Monitor Service authentication failed", 401)
```

```python
# service.py
def _authorize(self, request: web.Request, *, bootstrap: bool = False, websocket: bool = False) -> str:
    auth = self._auth
    if auth is None:
        raise _ServiceFailure(
            "MONITOR_SERVICE_UNAVAILABLE", "Monitor Service is unavailable", 503
        )
    raw_fetch_site = request.headers.get("Sec-Fetch-Site")
    fetch_site = raw_fetch_site.lower() if raw_fetch_site is not None else None
    try:
        auth.require_header_budget(tuple(request.headers.items()))
        return auth.authorize(peer=request.remote,host=request.host,origin=request.headers.get("Origin"),
          authorization=request.headers.get("Authorization"),cookie=request.cookies.get(MONITOR_COOKIE_NAME),
          bootstrap=bootstrap,method=request.method.upper(),fetch_site=fetch_site,websocket=websocket)
    except MonitorAuthError as error:
        raise _ServiceFailure(error.code, error.message, error.status) from None

# _live invokes only:
self._authorize(request, websocket=True)
```

The signature has no defaults: `def authorize(..., bootstrap: bool, method: str, fetch_site: str | None, websocket: bool) -> str`. This makes any unconverted accepted-base caller a type/runtime failure rather than an implicit authorization decision.

- [ ] **Step 4: Run the full auth/service suites on both interpreters.** From `tools/stm32-monitor`, run `& $python312 -m pytest tests/test_auth.py tests/test_service.py -q; & $python310 -m pytest tests/test_auth.py tests/test_service.py -q`. Expected: both PASS; route-operation mapping, bodyless POST rejection of `{}`, cookie attributes, wrong peer/Host, header budget, and WS client-message close policy remain green.

- [ ] **Step 5: Commit the bounded correction.** Stage only the four named Python files; commit `fix(STM32TK-0502): allow bounded same-origin cookie requests`.

### Task 8: Render Authoritative Identity and Explicit Probe Controls

**Files:** create `src/components/IdentityBar.tsx`, `ProbePanel.tsx`, and `tests/probe.test.tsx`.

**Interfaces:** produces prop-only `IdentityBar` and `ProbePanel`; callbacks are `onRefresh():Promise<void>`, `onConnect(probeId):Promise<void>`, `onReconnect():Promise<void>`, and `onRelease():Promise<void>`.

- [ ] **Step 1: Write the failing rendered behavior.** Create:

```tsx
// tests/probe.test.tsx
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {IdentityBar} from "../src/components/IdentityBar";
import {ProbePanel} from "../src/components/ProbePanel";
import {VALID_STATUS} from "./fixtures";
it("shows and copies only authoritative identity",async()=>{
 const user=userEvent.setup();const copy=vi.fn();
 render(<IdentityBar project={VALID_STATUS.project} firmware={VALID_STATUS.firmware} onCopy={copy}/>);
 expect(screen.getByText(VALID_STATUS.project.name)).toBeVisible();
 expect(screen.getByText(VALID_STATUS.project.targetDevice)).toBeVisible();
 expect(screen.getByText(VALID_STATUS.firmware!.gitHead.slice(0,12))).toBeVisible();
 expect(screen.getByText(/dirty/i)).toBeVisible();
 await user.click(screen.getByRole("button",{name:"Copy full Git HEAD"}));
 expect(copy).toHaveBeenCalledWith(VALID_STATUS.firmware!.gitHead);
});

it("marks missing firmware stale and never infers values",()=>{
 render(<IdentityBar project={VALID_STATUS.project} firmware={null} onCopy={vi.fn()}/>);
 expect(screen.getByRole("alert")).toHaveTextContent("Firmware identity unavailable; refresh and reconnect explicitly");
 expect(screen.queryByRole("button",{name:/Copy full (Git HEAD|build ID|ELF digest)/})).toBeNull();
});

it("does nothing before explicit probe actions and exposes no steal",async()=>{
 const user=userEvent.setup();const refresh=vi.fn(),connect=vi.fn(),reconnect=vi.fn(),release=vi.fn();
 const {rerender}=render(<ProbePanel probes={[{probeId:"p1",vendor:"ST",product:"ST-Link",boardName:null}]}
  connectedProbeId={null} canReconnect={false} leaseReason="MONITOR_PROBE_BUSY"
  onRefresh={refresh} onConnect={connect} onReconnect={reconnect} onRelease={release}/>);
 expect(refresh).not.toHaveBeenCalled();expect(connect).not.toHaveBeenCalled();
 expect(screen.getByRole("button",{name:"Reconnect probe"})).toBeDisabled();
 expect(screen.queryByRole("button",{name:/steal|force/i})).toBeNull();
 await user.click(screen.getByRole("button",{name:"Connect ST-Link"}));expect(connect).toHaveBeenCalledWith("p1");
 rerender(<ProbePanel probes={[]} connectedProbeId="p1" canReconnect leaseReason={null}
  onRefresh={refresh} onConnect={connect} onReconnect={reconnect} onRelease={release}/>);
 await user.click(screen.getByRole("button",{name:"Reconnect probe"}));
 await user.click(screen.getByRole("button",{name:"Release probe"}));
 expect(reconnect).toHaveBeenCalledOnce();expect(release).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/probe.test.tsx`. Expected: FAIL because both components are absent.

- [ ] **Step 3: Implement the minimum authoritative render and buttons.** Use:

```tsx
// src/components/ProbePanel.tsx
import type {ProbeInfo} from "../api/contract";
export type ProbePanelProps={probes:readonly ProbeInfo[];connectedProbeId:string|null;
 canReconnect:boolean;leaseReason:string|null;onRefresh:()=>void|Promise<void>;
 onConnect:(probeId:string)=>void|Promise<void>;onReconnect:()=>void|Promise<void>;
 onRelease:()=>void|Promise<void>};
export function ProbePanel(p:ProbePanelProps):JSX.Element{return <div>
 <button type="button" onClick={()=>void p.onRefresh()}>Refresh probes</button>
 {p.probes.map(probe=><button type="button" key={probe.probeId}
   onClick={()=>void p.onConnect(probe.probeId)}>Connect {probe.product}</button>)}
 <button type="button" disabled={!p.canReconnect} onClick={()=>void p.onReconnect()}>Reconnect probe</button>
 <button type="button" disabled={p.connectedProbeId===null} onClick={()=>void p.onRelease()}>Release probe</button>
 {p.leaseReason!==null&&<p role="status">{p.leaseReason}</p>}
 </div>}
```

```tsx
// src/components/IdentityBar.tsx
import type {FirmwareStatus,ProjectStatus} from "../api/contract";
export type IdentityBarProps={project:ProjectStatus;firmware:FirmwareStatus|null;
 onCopy:(value:string)=>void|Promise<void>};
export function IdentityBar({project,firmware,onCopy}:IdentityBarProps):JSX.Element{return <header>
 <h1>{project.name}</h1><p>Target: {project.targetDevice}</p>
 {firmware===null?<p role="alert">Firmware identity unavailable; refresh and reconnect explicitly</p>:
  <dl><dt>Git</dt><dd>{firmware.gitHead.slice(0,12)} ({firmware.gitDirty?"dirty":"clean"})
    <button type="button" onClick={()=>void onCopy(firmware.gitHead)}>Copy full Git HEAD</button></dd>
    <dt>Build ID</dt><dd>{firmware.buildId.slice(0,12)}<button type="button" onClick={()=>void onCopy(firmware.buildId)}>Copy full build ID</button></dd>
    <dt>ELF digest</dt><dd>{firmware.elfSha256.slice(0,12)}<button type="button" onClick={()=>void onCopy(firmware.elfSha256)}>Copy full ELF digest</button></dd></dl>}
 </header>}
```

- [ ] **Step 4: Run GREEN, typecheck, and axe.** From UI root run `& $npm run test -- tests/probe.test.tsx; & $npm run typecheck; & $npm run test:a11y`. Expected: PASS with zero callback before a click.

- [ ] **Step 5: Commit the unit.** Stage only the two components and `tests/probe.test.tsx`; commit `feat(STM32TK-0502): add explicit probe identity controls`.

### Task 9: Search Catalogs and Derive Only Shallow Wire Selectors

**Files:** create `src/catalog/shallow-selectors.ts`, `src/components/dialog-focus.ts`, `src/components/CatalogPanel.tsx`, and `tests/catalog.test.tsx`; modify reducer/selectors only for catalog request identity.

**Interfaces:** produces `deriveVariableWatch(descriptor,choice):VariableWatch|null`, `registerWatch(descriptor):RegisterWatch|null`, shared `useDialogFocus`, and `CatalogResult<T>={kind,query,bindingEpoch,items,nextCursor}`. `CatalogPanel` exposes Next only when the rendered kind, normalized query, binding epoch, and result identity all match; an old cursor is never paired with a new query.

- [ ] **Step 1: Write the failing no-guessing and UI timing tests.** Create:

```tsx
// tests/catalog.test.tsx
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {deriveVariableWatch} from "../src/catalog/shallow-selectors";
import {CatalogPanel} from "../src/components/CatalogPanel";
import {RISKY_REGISTER,UNAVAILABLE_REGISTER,VARIABLE_ARRAY_257} from "./fixtures";
it.each([
 [{selector:"state",typeName:"State",kind:"structure",byteSize:8,signed:null,encoding:null,
   qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:["rpm"]},
  {kind:"member",name:"rpm"},{kind:"variable",expression:"state.rpm"}],
 [{selector:"samples",typeName:"uint16_t[257]",kind:"array",byteSize:514,signed:null,encoding:null,
   qualifiers:[],aliases:[],enumValues:[],elementCount:257,elementKind:"integer",memberNames:[]},
  {kind:"index",index:256},{kind:"variable",expression:"samples[256]"}],
] as const)("derives one backend-validated selector without a child type",(descriptor,choice,expected)=>{
 expect(deriveVariableWatch(descriptor,choice)).toEqual(expected);
 expect(Object.keys(deriveVariableWatch(descriptor,choice)!)).toEqual(["kind","expression"]);
});

it.each([{kind:"member",name:"missing"},{kind:"index",index:-1},{kind:"index",index:1.5},
 {kind:"index",index:257}] as const)("rejects invalid shallow choice %j",choice=>{
 expect(deriveVariableWatch(VARIABLE_ARRAY_257,choice)).toBeNull();
});

it("normalizes, caps, debounces, and exposes only a matching result cursor",async()=>{
 vi.useFakeTimers();const user=userEvent.setup({advanceTimers:vi.advanceTimersByTime});
 const search=vi.fn(),next=vi.fn();const {rerender}=render(<CatalogPanel connected bindingEpoch={3}
  variables={{kind:"variables",query:"old",bindingEpoch:3,items:[],nextCursor:"stale"}}
  registers={null} onSearch={search} onNext={next} onAdd={vi.fn()}/>);
 await user.type(screen.getByLabelText("Variable or register search"),"e\u0301");
 expect(screen.queryByRole("button",{name:"Next variable catalog page"})).toBeNull();
 await vi.advanceTimersByTimeAsync(299);expect(search).not.toHaveBeenCalled();
 await vi.advanceTimersByTimeAsync(1);expect(search).toHaveBeenCalledWith("variables","é",undefined,100,3);
 rerender(<CatalogPanel connected bindingEpoch={3}
  variables={{kind:"variables",query:"é",bindingEpoch:3,items:[],nextCursor:"opaque-2"}}
  registers={null} onSearch={search} onNext={next} onAdd={vi.fn()}/>);
 await user.click(screen.getByRole("button",{name:"Next variable catalog page"}));
 expect(next).toHaveBeenCalledWith("variables","é","opaque-2",100,3);
});

it("blocks unavailable registers and confirms each risky add",async()=>{
 const user=userEvent.setup(),add=vi.fn();render(<CatalogPanel connected bindingEpoch={3}
  variables={null} registers={{kind:"registers",query:"",bindingEpoch:3,
   items:[UNAVAILABLE_REGISTER,RISKY_REGISTER],nextCursor:null}}
  onSearch={vi.fn()} onNext={vi.fn()} onAdd={add}/>);
  expect(screen.getByRole("button",{name:`Add ${UNAVAILABLE_REGISTER.selector}`})).toBeDisabled();
  expect(screen.getByText(`${UNAVAILABLE_REGISTER.access} / ${UNAVAILABLE_REGISTER.readAction}`)).toBeVisible();
  const trigger=screen.getByRole("button",{name:`Add ${RISKY_REGISTER.selector}`});await user.click(trigger);
  expect(add).not.toHaveBeenCalled();expect(screen.getByRole("dialog",{name:"Confirm register read"})).toHaveFocus();
  await user.keyboard("{Escape}");expect(trigger).toHaveFocus();await user.click(trigger);
  await user.click(screen.getByRole("button",{name:"Confirm this register read"}));
 expect(add).toHaveBeenCalledWith({kind:"register",registerPath:RISKY_REGISTER.selector});
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/catalog.test.tsx`. Expected: FAIL because selector and panel modules are absent.

- [ ] **Step 3: Implement exact one-hop derivation and current-click risk state.** Create:

```ts
// src/catalog/shallow-selectors.ts
import type {RegisterDescriptor,RegisterWatch,VariableDescriptor,VariableWatch} from "../api/contract";
export type ShallowChoice={kind:"self"}|{kind:"member";name:string}|{kind:"index";index:number};
export function deriveVariableWatch(d:VariableDescriptor,c:ShallowChoice):VariableWatch|null{
 if(c.kind==="self")return {kind:"variable",expression:d.selector};
 if(c.kind==="member")return d.memberNames.includes(c.name)?{kind:"variable",expression:`${d.selector}.${c.name}`}:null;
 return Number.isInteger(c.index)&&c.index>=0&&d.elementCount!==null&&c.index<d.elementCount?
   {kind:"variable",expression:`${d.selector}[${c.index}]`}:null;
}
export const registerWatch=(d:RegisterDescriptor):RegisterWatch|null=>
 d.sampleable?{kind:"register",registerPath:d.selector}:null;
export const listedIndexes=(d:VariableDescriptor):readonly number[]=>
 d.elementCount!==null&&d.elementCount<=256?Array.from({length:d.elementCount},(_,i)=>i):[];
```

```tsx
// src/components/dialog-focus.ts
import type {JSX} from "preact";
import {useEffect,useRef} from "preact/hooks";
export function useDialogFocus(open:boolean,onCancel:()=>void){
 const dialogRef=useRef<HTMLDivElement>(null),triggerRef=useRef<HTMLButtonElement|null>(null);
 const wasOpen=useRef(false);
 useEffect(()=>{if(open){wasOpen.current=true;dialogRef.current?.focus();}
  else if(wasOpen.current){wasOpen.current=false;triggerRef.current?.focus();}},[open]);
 return {dialogRef,rememberTrigger:(trigger:HTMLButtonElement)=>{triggerRef.current=trigger;},
  onDialogKeyDown:(event:JSX.TargetedKeyboardEvent<HTMLDivElement>)=>{
   if(event.key==="Escape"){event.preventDefault();onCancel();}}
 };
}
```

```tsx
// src/components/CatalogPanel.tsx
import {useEffect,useState} from "preact/hooks";
import type {RegisterDescriptor,RegisterWatch,VariableDescriptor,WatchItem} from "../api/contract";
import {deriveVariableWatch,listedIndexes,registerWatch} from "../catalog/shallow-selectors";
import {useDialogFocus} from "./dialog-focus";
export type CatalogKind="variables"|"registers";
export type CatalogResult<T>={kind:CatalogKind;query:string;bindingEpoch:number;
 items:readonly T[];nextCursor:string|null};
export type CatalogPanelProps={connected:boolean;bindingEpoch:number;
 variables:CatalogResult<VariableDescriptor>|null;registers:CatalogResult<RegisterDescriptor>|null;
 onSearch:(kind:CatalogKind,query:string,cursor:undefined,limit:100,bindingEpoch:number)=>void|Promise<void>;
 onNext:(kind:CatalogKind,query:string,cursor:string,limit:100,bindingEpoch:number)=>void|Promise<void>;
 onAdd:(watch:WatchItem)=>void|Promise<void>};
function VariableResult({descriptor,onAdd}:{descriptor:VariableDescriptor;onAdd:(watch:WatchItem)=>void|Promise<void>}):JSX.Element{
 const [index,setIndex]=useState("0"),indexes=listedIndexes(descriptor);
 const add=(choice:{kind:"self"}|{kind:"member";name:string}|{kind:"index";index:number})=>{
  const watch=deriveVariableWatch(descriptor,choice);if(watch!==null)void onAdd(watch);};
 return <li>{descriptor.selector} · {descriptor.kind} · {descriptor.typeName}
  <button type="button" onClick={()=>add({kind:"self"})}>Add {descriptor.selector}</button>
  {descriptor.memberNames.map(name=><button type="button" key={name}
   onClick={()=>add({kind:"member",name})}>Add {descriptor.selector}.{name}</button>)}
  {indexes.map(value=><button type="button" key={value}
   onClick={()=>add({kind:"index",index:value})}>Add {descriptor.selector}[{value}]</button>)}
  {descriptor.elementCount!==null&&descriptor.elementCount>256&&<><label>Index for {descriptor.selector}
   <input type="number" min="0" max={descriptor.elementCount-1} value={index}
    onInput={event=>setIndex(event.currentTarget.value)}/></label>
   <button type="button" onClick={()=>add({kind:"index",index:Number(index)})}>Add selected index</button></>}
 </li>;
}
export function CatalogPanel(p:CatalogPanelProps):JSX.Element{
 const [query,setQuery]=useState(""),[kind,setKind]=useState<CatalogKind>("variables");
 const [risk,setRisk]=useState<RegisterDescriptor|null>(null),normalized=query.normalize("NFC").slice(0,128);
 const dialog=useDialogFocus(risk!==null,()=>setRisk(null));
 useEffect(()=>{setRisk(null);if(!p.connected)return;const timer=window.setTimeout(
  ()=>void p.onSearch(kind,normalized,undefined,100,p.bindingEpoch),300);
  return()=>window.clearTimeout(timer);},[p.connected,p.bindingEpoch,p.onSearch,normalized,kind]);
 const addRegister=(descriptor:RegisterDescriptor,trigger:HTMLButtonElement):void=>{
  const watch:RegisterWatch|null=registerWatch(descriptor);if(watch===null)return;
  if(descriptor.requiresAccessAcknowledgement){dialog.rememberTrigger(trigger);setRisk(descriptor);return;}
  void p.onAdd(watch);
 };
 const variables=p.variables!==null&&p.variables.kind==="variables"&&p.variables.query===normalized&&
  p.variables.bindingEpoch===p.bindingEpoch?p.variables:null;
 const registers=p.registers!==null&&p.registers.kind==="registers"&&p.registers.query===normalized&&
  p.registers.bindingEpoch===p.bindingEpoch?p.registers:null;
 const current=kind==="variables"?variables:registers;
 const cursor=current?.nextCursor??null;
 return <div><label>Catalog kind <select value={kind}
   onChange={event=>setKind(event.currentTarget.value as CatalogKind)}>
   <option value="variables">Variables</option><option value="registers">Registers</option></select></label>
  <label>Variable or register search <input value={query} onInput={event=>setQuery(event.currentTarget.value)}/></label>
   <ul>{kind==="variables"?(variables?.items??[]).map(descriptor=><VariableResult key={descriptor.selector}
     descriptor={descriptor} onAdd={p.onAdd}/>):(registers?.items??[]).map(descriptor=><li key={descriptor.selector}>
    {descriptor.selector} · {descriptor.access??"unknown"} / {descriptor.readAction??"none"}
    <button type="button" disabled={!descriptor.sampleable}
     onClick={event=>addRegister(descriptor,event.currentTarget)}>Add {descriptor.selector}</button></li>)}</ul>
  {cursor!==null&&<button type="button" onClick={()=>void p.onNext(kind,normalized,cursor,100,p.bindingEpoch)}>
   Next {kind==="variables"?"variable":"register"} catalog page</button>}
  {risk!==null&&<div role="dialog" aria-label="Confirm register read" tabIndex={-1}
   ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
   <p>{risk.access??"unknown"} / {risk.readAction??"none"}</p>
   <button type="button" onClick={()=>{const current=risk;setRisk(null);const watch=registerWatch(current);
    if(watch!==null)void p.onAdd(watch);}}>Confirm this register read</button>
   <button type="button" onClick={()=>setRisk(null)}>Cancel</button></div>}
 </div>;
}
```

For `elementCount>256`, render a bounded integer input with `min=0` and `max=elementCount-1`; never materialize all indexes. A query or `bindingEpoch` change dispatches a fresh request identity and clears both the page and cursor before the response. The register confirmation state holds only the current descriptor and is cleared on confirm, cancel, Escape, query change, and unmount.

- [ ] **Step 4: Run GREEN, typecheck, and axe.** From UI root run `& $npm run test -- tests/catalog.test.tsx; & $npm run typecheck; & $npm run test:a11y`. Expected: PASS; no derived object contains type/address/offset fields.

- [ ] **Step 5: Commit the unit.** Stage only the catalog helper/component/tests and exact reducer/selectors catalog changes; commit `feat(STM32TK-0502): add bounded shallow catalog selection`.

### Task 10: Manage Pure User Groups and Transfer the Existing Schema

**Files:** create `src/components/GroupPanel.tsx`, `src/components/GroupImportDialog.tsx`, `src/state/group-transfer.ts`, and `tests/groups.test.tsx`; modify client/reducer only for exact group callback results.

**Interfaces:** produces `toGroupImportDocument(groups):GroupImportDocument`, `readGroupImportFile(file):Promise<ApiResult<GroupImportDocument>>`, `previewGroupImport(document,currentGroups):ImportPreview`, click-driven Blob export, and one selected-group `GroupDraft` shared with Catalog add. The draft preserves authoritative member order; add appends only a unique watch, remove deletes only the chosen key, and Save sends that exact order with CAS revision.

- [ ] **Step 1: Write the failing zero-state, CAS, confirmation, and transfer tests.** Create:

```tsx
// tests/groups.test.tsx
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import type {GroupDraft} from "../src/api/contract";
import {GroupPanel} from "../src/components/GroupPanel";
import {previewGroupImport,readGroupImportFile,toGroupImportDocument} from "../src/state/group-transfer";
import {IMPORT_DOCUMENT,VALID_GROUP} from "./fixtures";
const DRAFT:GroupDraft={sourceGroupId:VALID_GROUP.groupId,expectedRevision:VALID_GROUP.revision,
 name:VALID_GROUP.name,description:VALID_GROUP.description,intervalMs:VALID_GROUP.intervalMs,
 items:VALID_GROUP.items};
const props=(overrides:Record<string,unknown>={})=>({groups:[VALID_GROUP],selectedGroupId:VALID_GROUP.groupId,
 draft:DRAFT,failure:null,onSelect:vi.fn(),onDraftChange:vi.fn(),onRemove:vi.fn(),onCreate:vi.fn(),
 onSave:vi.fn(),onDelete:vi.fn(),onReadImport:readGroupImportFile,onImport:vi.fn(),onExport:vi.fn(),
 onRefresh:vi.fn(),...overrides});
it("renders zero user groups without seed copy",()=>{
 render(<GroupPanel {...props({groups:[],selectedGroupId:null,draft:{...DRAFT,sourceGroupId:null,
  expectedRevision:null,name:"",description:"",items:[]}})}/>);
 expect(screen.getByText("No user monitor groups")).toBeVisible();
 expect(screen.queryByText(/preset|example|default/i)).toBeNull();
});

it("selects authoritative groups and edits one shared ordered draft",async()=>{
 const user=userEvent.setup(),select=vi.fn(),change=vi.fn(),remove=vi.fn(),save=vi.fn();
 render(<GroupPanel {...props({onSelect:select,onDraftChange:change,onRemove:remove,onSave:save,
  draft:{...DRAFT,items:[{kind:"variable",expression:"counter"},{kind:"register",registerPath:"RCC.CSR"}]}})}/>);
 await user.selectOptions(screen.getByLabelText("Monitor group"),VALID_GROUP.groupId);
 expect(select).toHaveBeenCalledWith(VALID_GROUP.groupId);
 await user.clear(screen.getByLabelText("Group name"));await user.type(screen.getByLabelText("Group name"),"Renamed");
 expect(change).toHaveBeenLastCalledWith(expect.objectContaining({name:"Renamed"}));
 await user.click(screen.getByRole("button",{name:"Remove RCC.CSR"}));
 expect(remove).toHaveBeenCalledWith("register:RCC.CSR");
 await user.click(screen.getByRole("button",{name:"Save group"}));
 expect(save).toHaveBeenCalledWith(VALID_GROUP.groupId,{expectedRevision:VALID_GROUP.revision,
  name:VALID_GROUP.name,description:"",intervalMs:250,items:[
   {kind:"variable",expression:"counter"},{kind:"register",registerPath:"RCC.CSR"}],authorized:true});
});

it("deletes only after the current confirmation and sends CAS evidence",async()=>{
 const user=userEvent.setup(),remove=vi.fn();render(<GroupPanel {...props({onDelete:remove})}/>);
 const trigger=screen.getByRole("button",{name:`Delete ${VALID_GROUP.name}`});await user.click(trigger);
 expect(remove).not.toHaveBeenCalled();expect(screen.getByRole("dialog",{name:"Confirm group deletion"})).toHaveFocus();
 await user.keyboard("{Escape}");expect(trigger).toHaveFocus();await user.click(trigger);
 await user.click(screen.getByRole("button",{name:"Confirm delete"}));
 expect(remove).toHaveBeenCalledWith(VALID_GROUP.groupId,{expectedRevision:VALID_GROUP.revision,authorized:true});
});

it("saves ordinary edits directly with authorized true and exact interval bounds",async()=>{
 const user=userEvent.setup(),save=vi.fn();render(<GroupPanel {...props({onSave:save})}/>);
 const interval=screen.getByLabelText("Sampling interval milliseconds");
 expect(interval).toHaveAttribute("min","100");expect(interval).toHaveAttribute("max","5000");
 await user.clear(interval);await user.type(interval,"250");await user.click(screen.getByRole("button",{name:"Save group"}));
 expect(save).toHaveBeenCalledWith(VALID_GROUP.groupId,
  expect.objectContaining({expectedRevision:VALID_GROUP.revision,intervalMs:250,authorized:true}));
 expect(screen.queryByRole("dialog",{name:/save/i})).toBeNull();
});

it("exports only schemaVersion 1 transfer fields",()=>{
 expect(toGroupImportDocument([VALID_GROUP])).toEqual({schemaVersion:1,groups:[{
  name:VALID_GROUP.name,description:VALID_GROUP.description,intervalMs:VALID_GROUP.intervalMs,
  items:VALID_GROUP.items}]});
 expect(JSON.stringify(toGroupImportDocument([VALID_GROUP]))).not.toMatch(/groupId|revision|createdAtUtc|updatedAtUtc/);
});

it("guards the file then previews counts and restores focus before authorized import",async()=>{
 const user=userEvent.setup(),send=vi.fn(),read=vi.fn(readGroupImportFile);
 render(<GroupPanel {...props({onReadImport:read,onImport:send})}/>);
 const input=screen.getByLabelText("Import group JSON");
 await user.upload(input,new File([JSON.stringify(IMPORT_DOCUMENT)],"groups.json",{type:"application/json"}));
 expect(read).toHaveBeenCalledOnce();
 expect(screen.getByText("2 groups, 3 items; server validates name conflicts")).toBeVisible();
 expect(screen.getByRole("dialog",{name:"Confirm group import"})).toHaveFocus();
 await user.keyboard("{Escape}");expect(input).toHaveFocus();
 await user.upload(input,new File([JSON.stringify(IMPORT_DOCUMENT)],"groups.json",{type:"application/json"}));
 expect(send).not.toHaveBeenCalled();await user.click(screen.getByRole("button",{name:"Confirm group import"}));
 expect(send).toHaveBeenCalledWith({document:IMPORT_DOCUMENT,authorized:true});
});

it("rejects oversized or non-JSON import files without parsing",async()=>{
 expect(await readGroupImportFile(new File([new Uint8Array(1_048_577)],"large.json",{type:"application/json"})))
  .toEqual({ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"});
 expect(await readGroupImportFile(new File(["{}"],"groups.txt",{type:"text/plain"})))
  .toEqual({ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"});
});

it("does not guess the server's Unicode name equivalence",()=>{
 const document={schemaVersion:1,groups:[{...IMPORT_DOCUMENT.groups[0],name:"STRASSE"}]} as const;
 const existing=[{...VALID_GROUP,name:"Straße"}];
 expect(previewGroupImport(document,existing)).toEqual({groups:1,items:document.groups[0].items.length});
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/groups.test.tsx`. Expected: FAIL because group component/transfer modules are absent.

- [ ] **Step 3: Implement matching pure transfer and explicit dialog state.** Create:

```ts
// src/state/group-transfer.ts
import {parseGroupImportDocumentText,type ApiResult,type GroupImportDocument,
 type WatchGroup} from "../api/contract";
export type ImportPreview={groups:number;items:number};
export const toGroupImportDocument=(groups:readonly WatchGroup[]):GroupImportDocument=>({schemaVersion:1,
 groups:groups.map(({name,description,intervalMs,items})=>({name,description,intervalMs,items}))});
export function previewGroupImport(document:GroupImportDocument,current:readonly WatchGroup[]):ImportPreview{
 void current; // the server is authoritative for Unicode normalization/casefold conflicts
 return {groups:document.groups.length,items:document.groups.reduce((n,g)=>n+g.items.length,0)};
}
const IMPORT_MAX_BYTES=1_048_576;
export async function readGroupImportFile(file:File):Promise<ApiResult<GroupImportDocument>>{
 if(file.size===0||file.size>IMPORT_MAX_BYTES||file.type!=="application/json")
  return {ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"};
 try{return parseGroupImportDocumentText(await file.text());}
 catch{return {ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"};}
}
export function downloadGroupDocument(transfer:GroupImportDocument):void{
 const url=URL.createObjectURL(new Blob([JSON.stringify(transfer)],{type:"application/json"}));
 const anchor=globalThis.document.createElement("a");anchor.href=url;anchor.download="monitor-groups.json";anchor.click();
 URL.revokeObjectURL(url);
}
```

```tsx
// src/components/GroupImportDialog.tsx
import type {RefObject} from "preact";
import type {GroupImportDocument,WatchGroup} from "../api/contract";
import {previewGroupImport} from "../state/group-transfer";
export type GroupImportDialogProps={document:GroupImportDocument;existing:readonly WatchGroup[];
 onConfirm:(request:{document:GroupImportDocument;authorized:true})=>void|Promise<void>;
 onCancel:()=>void;dialogRef:RefObject<HTMLDivElement>;onKeyDown:(event:JSX.TargetedKeyboardEvent<HTMLDivElement>)=>void};
export function GroupImportDialog(p:GroupImportDialogProps):JSX.Element{
 const preview=previewGroupImport(p.document,p.existing);
 return <div role="dialog" aria-label="Confirm group import" tabIndex={-1} ref={p.dialogRef}
  onKeyDown={p.onKeyDown}>
  <p>{preview.groups} groups, {preview.items} items; server validates name conflicts</p>
  <button type="button" onClick={()=>void p.onConfirm({document:p.document,authorized:true})}>Confirm group import</button>
  <button type="button" onClick={p.onCancel}>Cancel</button>
 </div>;
}
```

```tsx
// src/components/GroupPanel.tsx
import {useRef,useState} from "preact/hooks";
import type {ApiResult,CreateGroupRequest,DeleteGroupRequest,GroupDraft,GroupImportDocument,
 PublicFailure,UpdateGroupRequest,WatchGroup} from "../api/contract";
import {watchKey} from "../chart/series";
import {toGroupImportDocument} from "../state/group-transfer";
import {useDialogFocus} from "./dialog-focus";
import {GroupImportDialog} from "./GroupImportDialog";
export type GroupPanelProps={groups:readonly WatchGroup[];failure:PublicFailure|null;
 selectedGroupId:string|null;draft:GroupDraft;onSelect:(groupId:string|null)=>void;
 onDraftChange:(draft:GroupDraft)=>void;onRemove:(key:string)=>void;
 onCreate:(request:CreateGroupRequest)=>void|Promise<void>;
 onSave:(groupId:string,request:UpdateGroupRequest)=>void|Promise<void>;
 onDelete:(groupId:string,request:DeleteGroupRequest)=>void|Promise<void>;
 onReadImport:(file:File)=>Promise<ApiResult<GroupImportDocument>>;
 onImport:(request:{document:GroupImportDocument;authorized:true})=>void|Promise<void>;
 onExport:(document:GroupImportDocument)=>void|Promise<void>;
 onRefresh:()=>void|Promise<void>};
export function GroupPanel(p:GroupPanelProps):JSX.Element{
 const selected=p.groups.find(group=>group.groupId===p.selectedGroupId)??null;
 const [pendingDelete,setPendingDelete]=useState<WatchGroup|null>(null),[confirmCreate,setConfirmCreate]=useState(false);
 const [importDocument,setImportDocument]=useState<GroupImportDocument|null>(null);
 const [importFailure,setImportFailure]=useState<PublicFailure|null>(null),importInput=useRef<HTMLInputElement>(null);
 const deleteDialog=useDialogFocus(pendingDelete!==null,()=>setPendingDelete(null));
 const createDialog=useDialogFocus(confirmCreate,()=>setConfirmCreate(false));
 const importDialog=useDialogFocus(importDocument!==null,()=>setImportDocument(null));
 const change=(patch:Partial<GroupDraft>)=>p.onDraftChange({...p.draft,...patch});
 const valid=Number.isInteger(p.draft.intervalMs)&&p.draft.intervalMs>=100&&p.draft.intervalMs<=5000&&p.draft.name.length>0;
 const save=():void=>{if(!valid||p.draft.sourceGroupId===null||p.draft.expectedRevision===null)return;
  void p.onSave(p.draft.sourceGroupId,{expectedRevision:p.draft.expectedRevision,name:p.draft.name,
   description:p.draft.description,intervalMs:p.draft.intervalMs,items:p.draft.items,authorized:true});};
 const create=():void=>{if(!valid)return;setConfirmCreate(false);void p.onCreate({name:p.draft.name,
  description:p.draft.description,intervalMs:p.draft.intervalMs,items:p.draft.items,authorized:true});};
 const readImport=async(file:File|undefined):Promise<void>=>{if(file===undefined)return;const result=await p.onReadImport(file);
  if(!result.ok){setImportFailure(result);return;}setImportFailure(null);importDialog.rememberTrigger(importInput.current!);
  setImportDocument(result.data);};
 return <div>{p.groups.length===0?<p>No user monitor groups</p>:<><label>Monitor group <select
   value={p.selectedGroupId??""} onChange={event=>p.onSelect(event.currentTarget.value||null)}>
    {p.groups.map(group=><option key={group.groupId} value={group.groupId}>{group.name}</option>)}</select></label>
   </>}
   <label>Group name <input value={p.draft.name} onInput={event=>change({name:event.currentTarget.value})}/></label>
   <label>Group description <input value={p.draft.description} onInput={event=>change({description:event.currentTarget.value})}/></label>
   <label>Sampling interval milliseconds <input type="number" min="100" max="5000" value={p.draft.intervalMs}
    onInput={event=>change({intervalMs:Number(event.currentTarget.value)})}/></label>
   <ol>{p.draft.items.map(item=>{const key=watchKey(item),label=item.kind==="variable"?item.expression:item.registerPath;
    return <li key={key}>{label}<button type="button" onClick={()=>p.onRemove(key)}>Remove {label}</button></li>;})}</ol>
   <button type="button" disabled={!valid||p.draft.sourceGroupId===null} onClick={save}>Save group</button>
   {selected!==null&&
    <button type="button" onClick={event=>{if(selected!==null){deleteDialog.rememberTrigger(event.currentTarget);
     setPendingDelete(selected);}}}>Delete {selected.name}</button>}
   <button type="button" onClick={event=>{createDialog.rememberTrigger(event.currentTarget);setConfirmCreate(true);}}>Create group</button>
   <label>Import group JSON <input ref={importInput} type="file" accept="application/json,.json"
    onChange={event=>{const input=event.currentTarget;void readImport(input.files?.[0]).finally(()=>{input.value="";});}}/></label>
   <button type="button" onClick={()=>void p.onExport(toGroupImportDocument(p.groups))}>Export groups</button>
   <button type="button" onClick={()=>void p.onRefresh()}>Refresh groups</button>
   {p.failure!==null&&<p role="alert">{p.failure.code}: {p.failure.message}</p>}
   {importFailure!==null&&<p role="alert">{importFailure.code}: {importFailure.message}</p>}
   {confirmCreate&&<div role="dialog" aria-label="Confirm group creation" tabIndex={-1}
    ref={createDialog.dialogRef} onKeyDown={createDialog.onDialogKeyDown}>
    <button type="button" disabled={!valid} onClick={create}>Confirm create</button>
   <button type="button" onClick={()=>setConfirmCreate(false)}>Cancel</button></div>}
  {pendingDelete!==null&&<div role="dialog" aria-label="Confirm group deletion" tabIndex={-1}
   ref={deleteDialog.dialogRef} onKeyDown={deleteDialog.onDialogKeyDown}>
   <button type="button" onClick={()=>{const group=pendingDelete;setPendingDelete(null);void p.onDelete(group.groupId,
    {expectedRevision:group.revision,authorized:true});}}>Confirm delete</button>
    <button type="button" onClick={()=>setPendingDelete(null)}>Cancel</button></div>}
   {importDocument!==null&&<GroupImportDialog document={importDocument} existing={p.groups}
    dialogRef={importDialog.dialogRef} onKeyDown={importDialog.onDialogKeyDown}
    onCancel={()=>setImportDocument(null)} onConfirm={request=>{setImportDocument(null);void p.onImport(request);}}/>}
  </div>;
}
```

Create and import require their own current-click confirmations. `MONITOR_GROUP_CONFLICT` causes an exact group-page refetch and forces a new user decision; it never resubmits automatically. Panel input remains local and survives public request failures. No generated group name, group seed, or default group exists.

- [ ] **Step 4: Run GREEN, typecheck, and axe.** From UI root run `& $npm run test -- tests/groups.test.tsx; & $npm run typecheck; & $npm run test:a11y`. Expected: PASS including Escape/focus restoration and no identifiers in group export.

- [ ] **Step 5: Commit the unit.** Stage only group component/transfer/tests and exact client/reducer callbacks; commit `feat(STM32TK-0502): add user-owned monitor groups`.

### Task 11: Project Accepted Samples into a Typed Table and Compact Status

**Files:** create `src/chart/series.ts`, `src/components/LiveTable.tsx`, `StatusStrip.tsx`, `NoticeRegion.tsx`, and `tests/live-table.test.tsx`; modify state model/reducer/selectors only for accepted sample projection.

**Interfaces:** produces `appendSample(live,batch,serviceSubscriberDrops,group):LiveState`, `liveRows(state):readonly LiveRow[]`, and `numericSeriesCandidates(state):readonly string[]`. `LiveRow` retains watch, type name, bounded display value, raw hex, captured time, trend, and exact error code.

- [ ] **Step 1: Write the failing error-isolation, typed-value, trend, and compact-status tests.** Create:

```tsx
// tests/live-table.test.tsx
import {render,screen} from "@testing-library/preact";
import {expect,it,vi} from "vitest";
import {appendSample,boundedDisplay,clearContinuity,liveRows,numericSeriesCandidates,selectedNumericSeries,watchKey} from "../src/chart/series";
import {LiveTable} from "../src/components/LiveTable";
import {NoticeRegion} from "../src/components/NoticeRegion";
import {StatusStrip} from "../src/components/StatusStrip";
import {emptyLive,initialMonitorState,reduceMonitor} from "../src/state/reducer";
import {batchForItems,groupWithItems,sampleBatchWithTypedValue,VALID_GROUP,VALID_SAMPLE_BATCH,VALID_STATUS} from "./fixtures";
it("isolates one item error while preserving the finite numeric sibling",()=>{
 const batch={...VALID_SAMPLE_BATCH,values:[
  {watch:{kind:"variable",expression:"bad"},status:"ERROR",typedValue:null,
   code:"DWARF_LOCATION_UNAVAILABLE",definition:{kind:"variable",selector:"bad"}},
  {watch:{kind:"variable",expression:"counter"},status:"OK",code:null,
   typedValue:{expression:"counter",typeName:"uint32_t",value:7,rawHex:"0x00000007",bitWidth:32},
   definition:{kind:"variable",selector:"counter"}}] as const};
 const group={...VALID_GROUP,items:[{kind:"variable",expression:"bad"},{kind:"variable",expression:"counter"}] as const};
 const live=appendSample(emptyLive(VALID_STATUS),batch,0,group);
 expect(live.rows.get("variable:bad")?.errorCode).toBe("DWARF_LOCATION_UNAVAILABLE");
 expect(live.rows.get("variable:counter")?.displayValue).toBe("7");
 expect(numericSeriesCandidates(live)).toEqual(["variable:counter"]);
});

it.each(["nan","positiveInfinity","negativeInfinity",true,"text",{a:1},[1,2]] as const)
 ("keeps %j in the table but not the chart",value=>{
  const batch=sampleBatchWithTypedValue(value);const live=appendSample(emptyLive(VALID_STATUS),batch,0,VALID_GROUP);
  render(<LiveTable rows={liveRows(live)} selectedSeries={[]} onSeriesToggle={vi.fn()}/>);
  expect(screen.getByRole("cell",{name:boundedDisplay(value)})).toBeVisible();
  expect(numericSeriesCandidates(live)).toEqual([]);
 });

it("uses group order, caps 256 rows, and resets trend after discontinuity",()=>{
 const group=groupWithItems(300);let live=appendSample(emptyLive(VALID_STATUS),batchForItems(group.items,1),0,group);
 live=appendSample(live,batchForItems(group.items,2),0,group);
 expect(liveRows(live)).toHaveLength(256);expect(liveRows(live)[0]?.trend).toBe("up");
 expect(clearContinuity(live).rows.get(watchKey(group.items[0]!))?.trend).toBe("none");
});

it("shows exact compact quality and emits one polite drop notice per increase",()=>{
 const {rerender}=render(<><StatusStrip actualRateHz={10} latencyNs={2500}
  drops={{subscriber:1,history:2,deadline:3,service:4}}/><NoticeRegion notices={[]}/></>);
 expect(screen.getByText("10 Hz")).toBeVisible();expect(screen.getByText("2500 ns")).toBeVisible();
 expect(screen.getByText("subscriber 1 · history 2 · deadline 3 · service 4")).toBeVisible();
 rerender(<NoticeRegion notices={[{id:"drop-service-5",kind:"drop",text:"service drops increased to 5"}]}/>);
 expect(screen.getByText("service drops increased to 5")).toHaveAttribute("aria-live","polite");
});

it("wires appendSample through the reducer, caps finite selections at eight, and deduplicates all drop notices",()=>{
 const group=groupWithItems(9),status={...VALID_STATUS,sampling:{...VALID_STATUS.sampling,groupId:group.groupId,
  groupRevision:group.revision}};let state=reduceMonitor(initialMonitorState,{type:"initial.loaded",status,
  probes:[],groups:[group],groupRevision:"a".repeat(64)});
 const batch={...batchForItems(group.items,1),groupId:group.groupId,groupRevision:group.revision,
  subscriberDrops:1,historyDrops:2,deadlineDrops:3};
 state=reduceMonitor(state,{type:"live.event",event:{eventId:"1",type:"sample",
  data:{batch,serviceSubscriberDrops:4}},subscriberDropped:0});
 expect([...state.live.rows.keys()]).toEqual(group.items.map(watchKey));
 for(const key of group.items.map(watchKey))state=reduceMonitor(state,{type:"series.toggled",key});
 expect(state.selectedSeries).toHaveLength(8);
 expect(selectedNumericSeries(state)).toHaveLength(8);
 expect(state.notices.filter(n=>n.kind==="drop").map(n=>n.id)).toEqual([
  "drop-subscriber-1","drop-history-2","drop-deadline-3","drop-service-4"]);
 const repeated=reduceMonitor(state,{type:"live.event",event:{eventId:"2",type:"sample",
  data:{batch:{...batch,sequence:2},serviceSubscriberDrops:0}},subscriberDropped:0});
 expect(repeated.notices.filter(n=>n.kind==="drop")).toHaveLength(4);
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/live-table.test.tsx`. Expected: FAIL because series/table/status modules are absent.

- [ ] **Step 3: Implement immutable row updates and exact typed projection.** The core implementation is:

```ts
// src/chart/series.ts
import type {JsonValue,SampleBatch,SampleValue,WatchGroup,WatchItem} from "../api/contract";
import type {LiveRow,LiveState,MonitorState,NumericSeries} from "../state/model";
export const watchKey=(w:WatchItem):string=>w.kind==="variable"?`variable:${w.expression}`:`register:${w.registerPath}`;
export const selectorOfWatch=(w:WatchItem):string=>w.kind==="variable"?w.expression:w.registerPath;
export const finiteNumeric=(v:SampleValue):number|null=>
 v.status==="OK"&&typeof v.typedValue.value==="number"&&Number.isFinite(v.typedValue.value)?v.typedValue.value:null;
export const boundedDisplay=(value:JsonValue,max=160):string=>{
 const raw=typeof value==="string"?value:JSON.stringify(value);
 return raw.length<=max?raw:`${raw.slice(0,max-1)}…`;
};
const rowFrom=(value:SampleValue,capturedAtUtc:string,numeric:number|null,prior:LiveRow|undefined,continuous:boolean):LiveRow=>{
 const success=value.status==="OK",previous=prior?.numericValue??null;
 return {key:watchKey(value.watch),selector:selectorOfWatch(value.watch),watch:value.watch,
  typeName:success?value.typedValue.typeName:null,displayValue:success?boundedDisplay(value.typedValue.value):value.code,
  rawHex:success?value.typedValue.rawHex:null,capturedAtUtc,numericValue:numeric,
  trend:!continuous||numeric===null||previous===null?"none":numeric>previous?"up":numeric<previous?"down":"flat",
  errorCode:success?null:value.code};
};
export const liveRows=(live:LiveState):readonly LiveRow[]=>[...live.rows.values()].slice(0,256);
export const numericSeriesCandidates=(live:LiveState):readonly string[]=>liveRows(live).filter(r=>r.numericValue!==null).map(r=>r.key);
export const selectedNumericSeries=(state:MonitorState):readonly NumericSeries[]=>state.selectedSeries.slice(0,8)
 .flatMap(key=>{const row=state.live.rows.get(key),points=state.live.points.get(key);
  return row?.numericValue!==null&&row!==undefined&&points!==undefined?[{name:row.selector,points}]:[];});
export const clearContinuity=(live:LiveState):LiveState=>({...live,gap:true,
 rows:new Map([...live.rows].map(([key,row])=>[key,{...row,trend:"none" as const}]))});
export function appendSample(live:LiveState,batch:SampleBatch,serviceDrops:number,group:WatchGroup):LiveState{
  const allowed=group.items.slice(0,256);const byKey=new Map(batch.values.map(v=>[watchKey(v.watch),v]));
  const rows=new Map<string,LiveRow>(),points=new Map<string,readonly {x:number;y:number|null}[]>();
  for(const watch of allowed){const key=watchKey(watch),value=byKey.get(key);if(value===undefined)continue;
    const numeric=finiteNumeric(value),priorRow=live.rows.get(key);
    rows.set(key,rowFrom(value,batch.capturedAtUtc,numeric,priorRow,live.runId===batch.runId&&!live.gap));
    if(numeric!==null){const next=[...(live.points.get(key)??[]),{x:batch.capturedUnixNs,y:numeric}].slice(-600);points.set(key,next);}
  }
 return {...live,rows,points,latestBatch:batch,runId:batch.runId,binding:batch.binding,
   bindingEpoch:live.bindingEpoch,gap:false,
   actualRateHz:batch.actualRateHz,latencyNs:batch.latencyNs,
   drops:{subscriber:batch.subscriberDrops,history:batch.historyDrops,
    deadline:batch.deadlineDrops,service:live.drops.service+serviceDrops}};
}
```

```tsx
// src/components/LiveTable.tsx
import type {LiveRow} from "../state/model";
export type LiveTableProps={rows:readonly LiveRow[];selectedSeries:readonly string[];
 onSeriesToggle:(key:string)=>void};
export function LiveTable({rows,selectedSeries,onSeriesToggle}:LiveTableProps):JSX.Element{return <table>
 <caption>Live monitor values</caption><thead><tr><th>Chart</th><th>Selector</th><th>Kind</th><th>Type</th>
 <th>Value</th><th>Raw</th><th>Captured</th><th>Trend</th><th>Error</th></tr></thead>
 <tbody>{rows.map(row=><tr key={row.key}><td><input type="checkbox" aria-label={`Chart ${row.selector}`}
  checked={selectedSeries.includes(row.key)} disabled={row.numericValue===null&&!selectedSeries.includes(row.key)}
  onChange={()=>onSeriesToggle(row.key)}/></td><td>{row.selector}</td><td>{row.watch.kind}</td><td>{row.typeName??"—"}</td>
  <td>{row.displayValue}</td><td>{row.rawHex??"—"}</td><td>{row.capturedAtUtc}</td>
  <td>{row.trend}</td><td>{row.errorCode??"—"}</td></tr>)}</tbody></table>}
```

```tsx
// src/components/StatusStrip.tsx
import type {DropTotals} from "../state/model";
export type StatusStripProps={actualRateHz:number;latencyNs:number;drops:DropTotals};
export function StatusStrip(p:StatusStripProps):JSX.Element{return <div>
  <span>{p.actualRateHz} Hz</span><span>{p.latencyNs} ns</span>
  <span>subscriber {p.drops.subscriber} · history {p.drops.history} · deadline {p.drops.deadline} · service {p.drops.service}</span>
 </div>}
```

```tsx
// src/components/NoticeRegion.tsx
import type {MonitorNotice} from "../state/model";
export type NoticeRegionProps={notices:readonly MonitorNotice[]};
export function NoticeRegion({notices}:NoticeRegionProps):JSX.Element{return <div>
  {notices.map(n=><p key={n.id} aria-live="polite">{n.text}</p>)}
 </div>}
```

In `src/state/reducer.ts`, add `import {appendSample} from "../chart/series";` (the Task 6 model import already includes `MonitorNotice`) and replace the Task 6 `acceptSample` function with this complete implementation:

```ts
const withDropNotices=(state:MonitorState,next:LiveState):readonly MonitorNotice[]=>{
 const totals=["subscriber","history","deadline","service"] as const;let notices=[...state.notices];
 for(const kind of totals){const total=next.drops[kind];if(total>state.live.drops[kind]){
  const id=`drop-${kind}-${total}`;if(!notices.some(notice=>notice.id===id))
   notices.push({id,kind:"drop",text:`${kind} drops increased to ${total}`});}}
 return notices;
};
const acceptSample=(state:MonitorState,event:Extract<LiveEvent,{type:"sample"}>):MonitorState=>{
 const {batch,serviceSubscriberDrops}=event.data;
 const group=state.groups.find(item=>item.groupId===batch.groupId&&item.revision===batch.groupRevision);
 if(state.status===null||group===undefined)return {...state,lastEventId:event.eventId,
  transport:{...state.transport,stale:true}};
 const live=appendSample(state.live,batch,serviceSubscriberDrops,group);
 return {...state,lastEventId:event.eventId,live,notices:withDropNotices(state,live)};
};
```

`boundedDisplay` uses text nodes only, stringifies unknown JSON with a fixed character cap, and never uses `innerHTML`. `rowFrom` reads `typeName/rawHex` only from successful `typedValue`; error rows never invent them. The reducer calls `appendSample` with the authoritative group matching both group ID and revision, so Map insertion order is group order. Drop notices are emitted and deduplicated in executable reducer code for subscriber, history, deadline, and service totals.

- [ ] **Step 4: Run GREEN, typecheck, and DOM safety scan.** From UI root run `& $npm run test -- tests/live-table.test.tsx; & $npm run typecheck; & $npm run test:a11y`; from repository root run `rg -n "innerHTML|dangerouslySetInnerHTML" tools/stm32-monitor/ui/src`. Expected: tests/typecheck/axe PASS and the scan has no match.

- [ ] **Step 5: Commit the unit.** Stage only the named table/status/series/state files and test; commit `feat(STM32TK-0502): render bounded typed live values`.

### Task 12: Register Modular ECharts, Bound Series, Coalesce Updates, and Recover Zoom

**Files:** create `src/chart/echarts.ts`, `src/chart/zoom.ts`, `src/components/LiveChart.tsx`, `ChartZoomControls.tsx`, `tests/chart.test.ts`, and `tests/zoom.test.tsx`.

**Interfaces:** produces `buildChartOption(points,range):EChartsCoreOption`, `ChartUpdateCoalescer`, `ZoomRange`, `ZoomAction`, `zoomReducer`, and `ChartZoomControls`. Only seven approved ECharts modules are registered.

- [ ] **Step 1: Write the failing module/limit/coalescing/zoom tests.** Create:

```ts
// tests/chart.test.ts
import {expect,it,vi} from "vitest";
import {buildChartOption,REGISTERED_ECHARTS_MODULES} from "../src/chart/echarts";
import {ChartUpdateCoalescer} from "../src/components/LiveChart";
import {optionFixture,seriesFixture} from "./fixtures";
it("builds only 8 by 600 line series with explicit gaps and two dataZoom modes",()=>{
 const input=seriesFixture(9,601,true);const option=buildChartOption(input,{start:25,end:75});
 expect(option.series).toHaveLength(8);
 expect(option.series!.every(s=>s.type==="line"&&s.connectNulls===false&&s.data!.length<=600)).toBe(true);
 expect(option.series![0]!.data).toContainEqual([expect.any(Number),null]);
 expect(option.dataZoom).toEqual([
  expect.objectContaining({type:"inside",start:25,end:75,zoomOnMouseWheel:true,moveOnMouseMove:true}),
  expect.objectContaining({type:"slider",start:25,end:75})]);
});

it("registers exactly Line Grid Tooltip Legend Dataset DataZoom and Canvas",()=>{
 expect(REGISTERED_ECHARTS_MODULES).toEqual(["LineChart","GridComponent","TooltipComponent",
  "LegendComponent","DatasetComponent","DataZoomComponent","CanvasRenderer"]);
});

it("coalesces ingress to at most one setOption per 100 ms with one pending snapshot",()=>{
 vi.useFakeTimers();const setOption=vi.fn();const raf=(f:FrameRequestCallback)=>{f(0);return 1;};
 const c=new ChartUpdateCoalescer(setOption,raf,()=>performance.now());
 c.push(optionFixture(1));c.push(optionFixture(2));c.push(optionFixture(3));
 vi.advanceTimersByTime(99);expect(setOption).not.toHaveBeenCalled();
 vi.advanceTimersByTime(1);expect(setOption).toHaveBeenCalledTimes(1);
 expect(setOption).toHaveBeenLastCalledWith(optionFixture(3),{notMerge:true,lazyUpdate:true});
 expect(c.pendingCount).toBe(0);
});
```

```tsx
// tests/zoom.test.tsx
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {zoomReducer} from "../src/chart/zoom";
import {ChartZoomControls} from "../src/components/ChartZoomControls";
it("maps buttons and keyboard to recoverable zoom actions",async()=>{
 const user=userEvent.setup(),onAction=vi.fn();render(<ChartZoomControls range={{start:25,end:75}} onAction={onAction}/>);
 expect(screen.getByText("Visible range 25–75%")).toBeVisible();
 await user.click(screen.getByRole("button",{name:"Reset chart zoom"}));
 await user.keyboard("{+}{-}0");
 expect(onAction.mock.calls.map(v=>v[0])).toEqual([
  {type:"zoom.reset"},{type:"zoom.in"},{type:"zoom.out"},{type:"zoom.reset"}]);
});

it.each([
 [{start:25,end:75},{type:"zoom.reset"},{start:0,end:100}],
 [{start:0,end:100},{type:"zoom.in"},{start:10,end:90}],
 [{start:25,end:75},{type:"zoom.out"},{start:15,end:85}],
 [{start:25,end:75},{type:"zoom.set",start:-5,end:120},{start:0,end:100}],
] as const)("reduces zoom %j",(range,action,expected)=>expect(zoomReducer(range,action)).toEqual(expected));
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/chart.test.ts tests/zoom.test.tsx`. Expected: FAIL because chart/zoom modules are absent.

- [ ] **Step 3: Implement only modular imports, bounded option, one pending snapshot, and clamped zoom.** Create:

```ts
// src/chart/echarts.ts
import {use,init,type EChartsCoreOption} from "echarts/core";
import {LineChart} from "echarts/charts";
import {GridComponent,TooltipComponent,LegendComponent,DatasetComponent,DataZoomComponent} from "echarts/components";
import {CanvasRenderer} from "echarts/renderers";
import type {NumericSeries} from "../state/model";
import type {ZoomRange} from "./zoom";
export const REGISTERED_ECHARTS_MODULES=["LineChart","GridComponent","TooltipComponent",
 "LegendComponent","DatasetComponent","DataZoomComponent","CanvasRenderer"] as const;
use([LineChart,GridComponent,TooltipComponent,LegendComponent,DatasetComponent,DataZoomComponent,CanvasRenderer]);
export {init};
export function buildChartOption(input:readonly NumericSeries[],range:ZoomRange):EChartsCoreOption{
 return {animation:false,tooltip:{trigger:"axis"},legend:{},dataset:[],
  dataZoom:[{type:"inside",start:range.start,end:range.end,zoomOnMouseWheel:true,moveOnMouseMove:true,
    moveOnMouseWheel:false,preventDefaultMouseMove:true},{type:"slider",start:range.start,end:range.end}],
  series:input.slice(0,8).map(s=>({name:s.name,type:"line",showSymbol:false,connectNulls:false,
    data:s.points.slice(-600).map(p=>[p.x,p.y])}))};
}
```

```ts
// src/chart/zoom.ts
export type ZoomRange={start:number;end:number};
export type ZoomAction={type:"zoom.in"}|{type:"zoom.out"}|{type:"zoom.reset"}|
 {type:"zoom.set";start:number;end:number};
const clamp=(v:number)=>Math.min(100,Math.max(0,v));
export function zoomReducer(r:ZoomRange,a:ZoomAction):ZoomRange{
 if(a.type==="zoom.reset")return {start:0,end:100};
 if(a.type==="zoom.in")return {start:clamp(r.start+10),end:clamp(r.end-10)};
 if(a.type==="zoom.out")return {start:clamp(r.start-10),end:clamp(r.end+10)};
 const start=clamp(a.start),end=clamp(a.end);return end>start?{start,end}:{start:0,end:100};
}
```
```tsx
// src/components/LiveChart.tsx
import {useEffect,useRef} from "preact/hooks";
import type {EChartsCoreOption} from "echarts/core";
import {buildChartOption,init} from "../chart/echarts";
import type {ZoomRange} from "../chart/zoom";
import type {NumericSeries} from "../state/model";
export type LiveChartProps={series:readonly NumericSeries[];range:ZoomRange;
 onZoom:(action:{type:"zoom.set";start:number;end:number})=>void};
export class ChartUpdateCoalescer{
 private pending:EChartsCoreOption|null=null;private timer:number|null=null;private last:number;private disposed=false;
 constructor(private readonly setOption:(o:EChartsCoreOption,flags:{notMerge:true;lazyUpdate:true})=>void,
  private readonly raf:(f:FrameRequestCallback)=>number,private readonly now:()=>number){this.last=now();}
 get pendingCount():number{return this.pending===null?0:1;}
 push(option:EChartsCoreOption):void{if(this.disposed)return;this.pending=option;if(this.timer!==null)return;
  const delay=Math.max(0,100-(this.now()-this.last));this.timer=window.setTimeout(()=>this.raf(()=>{
   this.timer=null;if(this.disposed)return;const newest=this.pending;this.pending=null;
   if(newest!==null){this.last=this.now();this.setOption(newest,{notMerge:true,lazyUpdate:true});}}),delay);}
 dispose():void{this.disposed=true;this.pending=null;if(this.timer!==null)window.clearTimeout(this.timer);this.timer=null;}
}
export function LiveChart({series,range,onZoom}:LiveChartProps):JSX.Element{
 const host=useRef<HTMLDivElement>(null),coalescerRef=useRef<ChartUpdateCoalescer|null>(null);
 const onZoomRef=useRef(onZoom);
 useEffect(()=>{onZoomRef.current=onZoom;},[onZoom]);
 useEffect(()=>{if(host.current===null)return;const chart=init(host.current);
  const coalescer=new ChartUpdateCoalescer((option,flags)=>chart.setOption(option,flags),
   requestAnimationFrame,()=>performance.now());
  const listener=(event:{start?:number;end?:number})=>onZoomRef.current({type:"zoom.set",
   start:event.start??0,end:event.end??100});
  coalescerRef.current=coalescer;chart.on("datazoom",listener);
  return()=>{coalescer.dispose();chart.off("datazoom",listener);chart.dispose();
   coalescerRef.current=null;};},[]);
 useEffect(()=>{coalescerRef.current?.push(buildChartOption(series,range));},[series,range]);
 return <div ref={host} role="img" aria-label="Live numeric chart"/>;
}
```

```tsx
// src/components/ChartZoomControls.tsx
import type {ZoomAction,ZoomRange} from "../chart/zoom";
export type ChartZoomControlsProps={range:ZoomRange;onAction:(action:ZoomAction)=>void};
export function ChartZoomControls({range,onAction}:ChartZoomControlsProps):JSX.Element{return <div
 onKeyDown={e=>{if(e.key==="+")onAction({type:"zoom.in"});if(e.key==="-")onAction({type:"zoom.out"});if(e.key==="0")onAction({type:"zoom.reset"});}}>
 <span>Visible range {range.start}–{range.end}%</span>
 <button type="button" onClick={()=>onAction({type:"zoom.in"})}>Zoom in</button>
 <button type="button" onClick={()=>onAction({type:"zoom.out"})}>Zoom out</button>
 <button type="button" onClick={()=>onAction({type:"zoom.reset"})}>Reset chart zoom</button>
</div>}
```

- [ ] **Step 4: Run GREEN, typecheck, source-import scan, and axe.** From UI root run `& $npm run test -- tests/chart.test.ts tests/zoom.test.tsx; & $npm run typecheck; & $npm run test:a11y`; from repository root run `rg -n 'from "echarts"|from ''echarts''' tools/stm32-monitor/ui/src`. Expected: PASS and the aggregate ECharts import scan has no match.

- [ ] **Step 5: Commit the unit.** Stage only the chart/zoom components/modules/tests; commit `feat(STM32TK-0502): add bounded recoverable monitor chart`.

### Task 13: Wire Explicit Sampling and Bounded Live Reconnection

**Files:** create `src/components/SamplingControls.tsx`, `src/live-reconnect.ts`, and `tests/sampling.test.tsx`; modify `src/api/live.ts` only for the lossless replay type already specified in Task 5.

**Interfaces:** produces `canStart(status,group,loadedRevision):boolean`, a callback-only `SamplingControls`, and `LiveReconnectController` that uses lossless `EventId`, 35 seconds, and exact capped backoff. Task 16 composes these into the complete controller after history and export exist.

- [ ] **Step 1: Write the failing action and reconnect timing tests.** Create:

```tsx
// tests/sampling.test.tsx
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {expect,it,vi} from "vitest";
import {SamplingControls,canStart} from "../src/components/SamplingControls";
import {LiveReconnectController} from "../src/live-reconnect";
import {VALID_GROUP,VALID_STATUS} from "./fixtures";
it.each([
 [VALID_STATUS,VALID_GROUP,VALID_GROUP.revision,true],
 [{...VALID_STATUS,probe:{connected:false,probeId:null},probeConnected:false},VALID_GROUP,VALID_GROUP.revision,false],
 [VALID_STATUS,{...VALID_GROUP,items:[]},VALID_GROUP.revision,false],
 [VALID_STATUS,{...VALID_GROUP,intervalMs:99},VALID_GROUP.revision,false],
 [VALID_STATUS,VALID_GROUP,VALID_GROUP.revision+1,false],
] as const)("computes exact Start eligibility",(status,group,loadedRevision,enabled)=>
 expect(canStart(status,group,loadedRevision)).toBe(enabled));

it("sends exact explicit sampling actions only after clicks",async()=>{
 const user=userEvent.setup(),start=vi.fn(),pause=vi.fn(),resume=vi.fn(),stop=vi.fn();
 render(<SamplingControls status={VALID_STATUS} group={VALID_GROUP} loadedRevision={VALID_GROUP.revision}
  onStart={start} onPause={pause} onResume={resume} onStop={stop}/>);
 expect(start).not.toHaveBeenCalled();await user.click(screen.getByRole("button",{name:"Start sampling"}));
 expect(start).toHaveBeenCalledWith({groupId:VALID_GROUP.groupId,expectedRevision:VALID_GROUP.revision});
 await user.click(screen.getByRole("button",{name:"Pause sampling"}));
 await user.click(screen.getByRole("button",{name:"Resume sampling"}));
 await user.click(screen.getByRole("button",{name:"Stop sampling"}));
 expect(pause).toHaveBeenCalledWith();expect(resume).toHaveBeenCalledWith();expect(stop).toHaveBeenCalledWith();
});

it("rerenders authoritative RUNNING to PAUSED to RUNNING controls",()=>{
 const callbacks={onStart:vi.fn(),onPause:vi.fn(),onResume:vi.fn(),onStop:vi.fn()};
 const {rerender}=render(<SamplingControls status={VALID_STATUS} group={VALID_GROUP}
  loadedRevision={VALID_GROUP.revision} {...callbacks}/>);
 expect(screen.getByRole("button",{name:"Pause sampling"})).toBeEnabled();
 rerender(<SamplingControls status={{...VALID_STATUS,sampling:{...VALID_STATUS.sampling,state:"PAUSED",active:true}}}
  group={VALID_GROUP} loadedRevision={VALID_GROUP.revision} {...callbacks}/>);
 expect(screen.getByRole("button",{name:"Resume sampling"})).toBeEnabled();
 rerender(<SamplingControls status={VALID_STATUS} group={VALID_GROUP}
  loadedRevision={VALID_GROUP.revision} {...callbacks}/>);
 expect(screen.getByRole("button",{name:"Pause sampling"})).toBeEnabled();
});

it("marks stale at 35 seconds and reconnects WS at 0.5 1 2 4 8 second caps",()=>{
 vi.useFakeTimers();const connect=vi.fn(),dispatch=vi.fn();
 const controller=new LiveReconnectController({connect,dispatch,latestEventId:()=>"41"});
 controller.open("41");controller.opened();expect(connect).toHaveBeenLastCalledWith("41");
 vi.advanceTimersByTime(35000);expect(dispatch).toHaveBeenCalledWith({type:"transport.stale"});
 for(const delay of [500,1000,2000,4000,8000,8000]){
  const before=connect.mock.calls.length;controller.closed();vi.advanceTimersByTime(delay-1);
  expect(connect).toHaveBeenCalledTimes(before);vi.advanceTimersByTime(1);
  expect(connect).toHaveBeenCalledTimes(before+1);
 }
 expect(connect).toHaveBeenLastCalledWith("41");
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/sampling.test.tsx`. Expected: FAIL because controls/controller/reconnect policy are absent.

- [ ] **Step 3: Implement matching eligibility, button callbacks, and timers.** Use:

```ts
// src/live-reconnect.ts
import type {EventId,MonitorAction} from "./api/contract";
export class LiveReconnectController{
 private attempt=0;private heartbeat:number|null=null;private retry:number|null=null;private disposed=false;
 constructor(private readonly deps:{connect:(after?:EventId)=>void;dispatch:(a:MonitorAction)=>void;
  latestEventId:()=>EventId|undefined}){}
 open(after=this.deps.latestEventId()):void{if(!this.disposed)this.deps.connect(after);}
 heartbeatReceived():void{this.armHeartbeat();}
 private armHeartbeat():void{if(this.heartbeat!==null)clearTimeout(this.heartbeat);
  this.heartbeat=window.setTimeout(()=>this.deps.dispatch({type:"transport.stale"}),35000);}
 closed():void{if(this.disposed||this.retry!==null)return;if(this.heartbeat!==null)clearTimeout(this.heartbeat);
  this.heartbeat=null;this.deps.dispatch({type:"transport.stale"});
  const seconds=[.5,1,2,4,8][Math.min(this.attempt,4)]!;this.attempt+=1;
  this.retry=window.setTimeout(()=>{this.retry=null;this.deps.connect(this.deps.latestEventId());},seconds*1000);}
 opened():void{if(this.disposed)return;this.attempt=0;this.deps.dispatch({type:"transport.open"});this.armHeartbeat();}
 dispose():void{this.disposed=true;if(this.heartbeat!==null)clearTimeout(this.heartbeat);
  if(this.retry!==null)clearTimeout(this.retry);this.heartbeat=null;this.retry=null;}
}
```

```tsx
// src/components/SamplingControls.tsx
import type {MonitorStatus,WatchGroup} from "../api/contract";
export const canStart=(status:MonitorStatus,group:WatchGroup|null,loadedRevision:number|null):boolean=>
 status.probe.connected&&status.firmware!==null&&group!==null&&group.items.length>0&&
 group.intervalMs>=100&&group.intervalMs<=5000&&loadedRevision===group.revision;

export type SamplingControlsProps={status:MonitorStatus;group:WatchGroup|null;loadedRevision:number|null;
 onStart:(request:{groupId:string;expectedRevision:number})=>void|Promise<void>;
 onPause:()=>void|Promise<void>;onResume:()=>void|Promise<void>;onStop:()=>void|Promise<void>};
export function SamplingControls(p:SamplingControlsProps):JSX.Element{return <div>
 <button disabled={!canStart(p.status,p.group,p.loadedRevision)} onClick={()=>p.group&&void p.onStart({
  groupId:p.group.groupId,expectedRevision:p.group.revision})}>Start sampling</button>
 <button disabled={p.status.sampling.state!=="RUNNING"} onClick={()=>void p.onPause()}>Pause sampling</button>
 <button disabled={p.status.sampling.state!=="PAUSED"} onClick={()=>void p.onResume()}>Resume sampling</button>
 <button disabled={p.status.sampling.state==="IDLE"} onClick={()=>void p.onStop()}>Stop sampling</button>
 </div>}
```

- [ ] **Step 4: Run GREEN and aggregate frontend-core live gates.** From UI root run `& $npm run test -- tests/sampling.test.tsx tests/reducer.test.ts tests/live-table.test.tsx tests/chart.test.ts tests/zoom.test.tsx; & $npm run typecheck; & $npm run test:a11y; & $npm run build`. Expected: PASS; no reconnect timer invokes probe reconnect/start.

- [ ] **Step 5: Commit the unit.** Stage only `src/components/SamplingControls.tsx`, `src/live-reconnect.ts`, the Task 5 replay-type adjustment in `src/api/live.ts`, and `tests/sampling.test.tsx`; commit `feat(STM32TK-0502): add explicit live sampling controls`.

### Task 14: Page Basic Current-Session History Without Precision Loss

**Files:** create `src/components/HistoryPanel.tsx` and `tests/history.test.tsx`; modify selectors/client/reducer/app only for history state.

**Interfaces:** produces `flattenHistory(page):readonly HistoryRow[]`, `historyQueryKey(query):string`, and `HistoryPanel`. Previous navigation uses only an in-memory visited cursor stack; refresh/query identity clears it.

- [ ] **Step 1: Write the failing ordinal/query/cursor tests.** Create:

```tsx
// tests/history.test.tsx
import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import type {HistoryQuery} from "../src/api/contract";
import {HistoryPanel} from "../src/components/HistoryPanel";
import {flattenHistory,historyQueryKey,historyRowKey} from "../src/state/selectors";
import {HISTORY_END_INPUT,HISTORY_PAGE,HISTORY_QUERY,HISTORY_START_INPUT,VALID_GROUP,
 VALID_HISTORY_BATCH,VALID_SAMPLE_BATCH} from "./fixtures";
it("flattens exact batch binding and ordinals without merging batches",()=>{
 const page={batches:[{...VALID_HISTORY_BATCH,startOrdinal:4,batchValueCount:6,
  values:[VALID_SAMPLE_BATCH.values[0]!,VALID_SAMPLE_BATCH.values[0]!]}],
  valueCount:2,nextCursor:"opaque-next",serializedBytes:512};
 const rows=flattenHistory(page);expect(rows).toEqual([
  expect.objectContaining({binding:VALID_HISTORY_BATCH.binding,startOrdinal:4,valueOrdinal:4,value:page.batches[0]!.values[0]}),
  expect.objectContaining({binding:VALID_HISTORY_BATCH.binding,startOrdinal:4,valueOrdinal:5,value:page.batches[0]!.values[1]})]);
 expect(historyRowKey(rows[0]!)).not.toBe(historyRowKey({...rows[0]!,runId:"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}));
 expect(historyRowKey(rows[0]!)).not.toBe(historyRowKey({...rows[0]!,binding:{...rows[0]!.binding,leaseId:"lease-2"}}));
});

it("uses required lossless bounds and only current allowlisted filters",()=>{
 const q:HistoryQuery={startNs:9007199254740993n,endNs:9007199254741993n,limit:10000,
  runId:VALID_SAMPLE_BATCH.runId,groupId:VALID_GROUP.groupId,
  selector:{kind:"variable",value:"counter"},cursor:"opaque"};
 expect(historyQueryKey(q)).toBe("9007199254740993|9007199254741993|"+VALID_SAMPLE_BATCH.runId+"|"+
  VALID_GROUP.groupId+"|variable|counter");
 expect(Object.keys(q).sort()).toEqual(["cursor","endNs","groupId","limit","runId","selector","startNs"]);
});

it("passes server Next cursor and uses only visited memory for Previous",async()=>{
 const user=userEvent.setup(),load=vi.fn(),page=vi.fn();
 const {rerender}=render(<HistoryPanel query={HISTORY_QUERY} page={{...HISTORY_PAGE,nextCursor:"cursor-2"}}
  failure={null} onLoad={load} onPage={page}/>);
 expect(screen.getByRole("button",{name:"Previous history page"})).toBeDisabled();
 await user.click(screen.getByRole("button",{name:"Next history page"}));expect(page).toHaveBeenCalledWith("cursor-2");
 rerender(<HistoryPanel query={{...HISTORY_QUERY,cursor:"cursor-2"}} page={{...HISTORY_PAGE,nextCursor:null}}
  failure={null} onLoad={load} onPage={page}/>);
 await user.click(screen.getByRole("button",{name:"Previous history page"}));expect(page).toHaveBeenLastCalledWith(undefined);
});

it("never auto-fetches another page and retains input on public failure",()=>{
 const load=vi.fn(),page=vi.fn();render(<HistoryPanel query={HISTORY_QUERY} page={HISTORY_PAGE}
  failure={{code:"MONITOR_HISTORY_QUERY_INVALID",message:"history query is invalid"}} onLoad={load} onPage={page}/>);
 expect(load).not.toHaveBeenCalled();expect(page).not.toHaveBeenCalled();
 expect(screen.getByLabelText("History start")).toHaveValue(HISTORY_START_INPUT);
 expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_HISTORY_QUERY_INVALID");
});

it("loads edited lossless bounds once and renders every flattened row",async()=>{
 const user=userEvent.setup(),load=vi.fn();render(<HistoryPanel query={HISTORY_QUERY} page={HISTORY_PAGE}
  failure={null} onLoad={load} onPage={vi.fn()}/>);
 const start=screen.getByLabelText("History start"),end=screen.getByLabelText("History end");
 expect(start).toHaveValue(HISTORY_START_INPUT);expect(end).toHaveValue(HISTORY_END_INPUT);
 await user.clear(start);await user.type(start,"2023-11-14T22:13:20.000");
  await user.clear(end);await user.type(end,"2023-11-14T22:13:21.000");
  await user.click(screen.getByRole("button",{name:"Load history"}));
  expect(load).toHaveBeenCalledOnce();const submitted=load.mock.calls[0]![0];
  expect(Object.hasOwn(submitted,"cursor")).toBe(false);expect(submitted).toEqual(HISTORY_QUERY);
 expect(screen.getAllByRole("row")).toHaveLength(flattenHistory(HISTORY_PAGE).length+1);
 expect(screen.getByRole("cell",{name:"counter"})).toBeVisible();
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/history.test.tsx`. Expected: FAIL because history selector/panel behavior is absent.

- [ ] **Step 3: Implement exact flattening and in-memory page navigation.** Create:

```ts
// src/state/selectors.ts
import type {HistoryPage,HistoryQuery} from "../api/contract";
import type {HistoryRow} from "./model";
export function flattenHistory(page:HistoryPage):readonly HistoryRow[]{return page.batches.flatMap(batch=>
 batch.values.map((value,index)=>({binding:batch.binding,groupId:batch.groupId,runId:batch.runId,
  sequence:batch.sequence,capturedAtUtc:batch.capturedAtUtc,startOrdinal:batch.startOrdinal,
  valueOrdinal:batch.startOrdinal+index,value})));}
export const historyQueryKey=(q:HistoryQuery):string=>[q.startNs,q.endNs,q.runId??"",q.groupId??"",
 q.selector?.kind??"",q.selector?.value??""].join("|");
export const historyRowKey=(row:HistoryRow):string=>JSON.stringify([
 row.binding.workspaceId,row.binding.logicalProjectId,row.binding.sessionId,row.binding.probeId,
 row.binding.targetDevice,row.binding.physicalTarget,row.binding.buildId,row.binding.elfSha256,
 row.binding.inputSnapshotSha256,row.binding.gitHead,row.binding.gitDirty,row.binding.flashSessionId,
 row.binding.leaseId,row.binding.dwarfSha256,row.binding.svdSha256,row.runId,row.sequence,row.valueOrdinal]);
export function withoutHistoryCursor(q:HistoryQuery):HistoryQuery{const result:HistoryQuery={startNs:q.startNs,endNs:q.endNs};
 if(q.limit!==undefined)result.limit=q.limit;if(q.runId!==undefined)result.runId=q.runId;
 if(q.groupId!==undefined)result.groupId=q.groupId;if(q.selector!==undefined)result.selector=q.selector;return result;}
```

```tsx
// src/components/HistoryPanel.tsx
import {useEffect,useState} from "preact/hooks";
import type {HistoryPage,HistoryQuery,PublicFailure} from "../api/contract";
import {boundedDisplay} from "../chart/series";
import {flattenHistory,historyQueryKey,historyRowKey,withoutHistoryCursor} from "../state/selectors";
export type HistoryPanelProps={query:HistoryQuery;page:HistoryPage|null;failure:PublicFailure|null;
 onLoad:(query:HistoryQuery)=>void|Promise<void>;onPage:(cursor:string|undefined)=>void|Promise<void>};
export const historyInput=(ns:bigint):string=>new Date(Number(ns/1_000_000n)).toISOString().slice(0,23);
export const inputNs=(value:string):bigint|null=>{const ms=Date.parse(`${value}Z`);
 return Number.isFinite(ms)?BigInt(ms)*1_000_000n:null;};
export function HistoryPanel({query,page,failure,onLoad,onPage}:HistoryPanelProps):JSX.Element{
 const [start,setStart]=useState(()=>historyInput(query.startNs));
 const [end,setEnd]=useState(()=>historyInput(query.endNs));
 const [visited,setVisited]=useState<readonly (string|undefined)[]>([]);
 const key=historyQueryKey(query),rows=page===null?[]:flattenHistory(page),next=page?.nextCursor??null;
 useEffect(()=>{setVisited([]);setStart(historyInput(query.startNs));setEnd(historyInput(query.endNs));},[key]);
 const load=():void=>{const startNs=inputNs(start),endNs=inputNs(end);
  if(startNs===null||endNs===null||endNs<=startNs)return;
   void onLoad({...withoutHistoryCursor(query),startNs,endNs,limit:Math.min(query.limit??10_000,10_000)});};
 const goNext=():void=>{if(next===null)return;setVisited(v=>[...v,query.cursor]);void onPage(next);};
 const goPrevious=():void=>{if(visited.length===0)return;const prior=visited[visited.length-1];
  setVisited(v=>v.slice(0,-1));void onPage(prior);};
 return <div>
  <label>History start <input type="datetime-local" step="0.001" value={start} onInput={e=>setStart(e.currentTarget.value)}/></label>
  <label>History end <input type="datetime-local" step="0.001" value={end} onInput={e=>setEnd(e.currentTarget.value)}/></label>
  <button type="button" onClick={load}>Load history</button>
  <button type="button" disabled={visited.length===0} onClick={goPrevious}>Previous history page</button>
  <button type="button" disabled={next===null} onClick={goNext}>Next history page</button>
  {failure!==null&&<p role="alert">{failure.code}: {failure.message}</p>}
  <table><caption>History values</caption><thead><tr><th>Captured</th><th>Selector</th><th>Value</th></tr></thead>
   <tbody>{rows.map(row=><tr key={historyRowKey(row)}><td>{row.capturedAtUtc}</td>
    <td>{row.value.watch.kind==="variable"?row.value.watch.expression:row.value.watch.registerPath}</td>
    <td>{row.value.status==="OK"?boundedDisplay(row.value.typedValue.value):row.value.code}</td></tr>)}</tbody>
  </table>
 </div>;
}
```

- [ ] **Step 4: Run GREEN, typecheck, and axe.** From UI root run `& $npm run test -- tests/history.test.tsx; & $npm run typecheck; & $npm run test:a11y`. Expected: PASS with no request until Load/Next/Previous click.

- [ ] **Step 5: Commit the unit.** Stage only history component/test and exact selectors/client/reducer/app changes; commit `feat(STM32TK-0502): page basic monitor history`.

### Task 15: Create and Download Verified CSV/JSONL Exports

**Files:** create `src/components/ExportPanel.tsx` and `tests/export.test.tsx`; modify controller/reducer/app only for verified export state.

**Interfaces:** produces click-confirmed export creation for `csv|jsonl`, optional status refresh through `exportStatus`, and binary `downloadExport` using only server metadata. A successful `ExportArtifact` is the existing verified artifact; no `verified` field is added to the wire DTO.

- [ ] **Step 1: Write the failing confirmation, artifact, and download tests.** Create:

```tsx
// tests/export.test.tsx
import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {ExportPanel} from "../src/components/ExportPanel";
import {EXPORT_END_INPUT,EXPORT_RANGE,EXPORT_START_INPUT} from "./fixtures";
it.each(["csv","jsonl"] as const)("confirms and creates exact %s evidence export",async format=>{
 const user=userEvent.setup(),create=vi.fn();render(<ExportPanel range={EXPORT_RANGE} artifact={null}
  failure={null} onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
 const trigger=screen.getByRole("button",{name:`Create ${format.toUpperCase()} export`});await user.click(trigger);
 expect(create).not.toHaveBeenCalled();expect(screen.getByRole("dialog",{name:"Confirm history export"})).toHaveFocus();
 await user.keyboard("{Escape}");expect(screen.queryByRole("dialog",{name:"Confirm history export"})).toBeNull();
 expect(trigger).toHaveFocus();await user.click(trigger);
 await user.click(screen.getByRole("button",{name:"Confirm export"}));
 expect(create).toHaveBeenCalledWith({...EXPORT_RANGE,format,authorized:true});
});

it("renders exact verified artifact evidence and downloads by server exportId",async()=>{
 const user=userEvent.setup(),refresh=vi.fn(),download=vi.fn();render(<ExportPanel range={EXPORT_RANGE}
  artifact={{exportId:"e1",format:"csv",sha256:"a".repeat(64),bytes:123,valueCount:4}}
  failure={null} onCreate={vi.fn()} onRefresh={refresh} onDownload={download}/>);
 expect(screen.getByText("123 bytes · 4 values")).toBeVisible();
 expect(screen.getByText("a".repeat(64))).toBeVisible();
 await user.click(screen.getByRole("button",{name:"Refresh export status"}));expect(refresh).toHaveBeenCalledWith("e1");
 await user.click(screen.getByRole("button",{name:"Download verified CSV"}));expect(download).toHaveBeenCalledWith("e1");
});

it("retains range on public failure and exposes no path filename Range or AI export controls",()=>{
 render(<ExportPanel range={EXPORT_RANGE} artifact={null}
  failure={{code:"MONITOR_EXPORT_FAILED",message:"history export failed"}}
  onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
 expect(screen.getByLabelText("Export start")).toHaveValue(EXPORT_START_INPUT);
 expect(screen.getByLabelText("Export end")).toHaveValue(EXPORT_END_INPUT);
 expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_EXPORT_FAILED");
 expect(screen.queryByLabelText(/path|filename|range header/i)).toBeNull();
 expect(screen.queryByText(/AI|snapshot|diagnostic session/i)).toBeNull();
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/export.test.tsx`. Expected: FAIL because `ExportPanel` is absent.

- [ ] **Step 3: Implement current-click confirmation and server-controlled download.** Create:

```tsx
import {useState} from "preact/hooks";
import type {ExportArtifact,ExportRequest,PublicFailure} from "../api/contract";
import {historyInput,inputNs} from "./HistoryPanel";
import {useDialogFocus} from "./dialog-focus";
export type ExportPanelProps={range:{startNs:bigint;endNs:bigint};artifact:ExportArtifact|null;
 failure:PublicFailure|null;onCreate:(request:ExportRequest)=>void|Promise<void>;
 onRefresh:(exportId:string)=>void|Promise<void>;onDownload:(exportId:string)=>void|Promise<void>};
export function ExportPanel(p:ExportPanelProps):JSX.Element{
 const [pending,setPending]=useState<"csv"|"jsonl"|null>(null);
 const [start,setStart]=useState(()=>historyInput(p.range.startNs));
 const [end,setEnd]=useState(()=>historyInput(p.range.endNs));
 const dialog=useDialogFocus(pending!==null,()=>setPending(null));
 const confirm=():void=>{if(pending===null)return;const startNs=inputNs(start),endNs=inputNs(end);
  if(startNs===null||endNs===null||endNs<=startNs)return;const format=pending;setPending(null);
  void p.onCreate({startNs,endNs,format,authorized:true});};
 return <div>
  <label>Export start <input type="datetime-local" step="0.001" value={start}
   onInput={e=>setStart(e.currentTarget.value)}/></label>
  <label>Export end <input type="datetime-local" step="0.001" value={end}
   onInput={e=>setEnd(e.currentTarget.value)}/></label>
  <button type="button" onClick={event=>{dialog.rememberTrigger(event.currentTarget);setPending("csv");}}>Create CSV export</button>
  <button type="button" onClick={event=>{dialog.rememberTrigger(event.currentTarget);setPending("jsonl");}}>Create JSONL export</button>
  {pending!==null&&<div role="dialog" aria-label="Confirm history export" tabIndex={-1}
   ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
   <p>Export the selected current-session time range as {pending.toUpperCase()}?</p>
   <button type="button" onClick={confirm}>Confirm export</button>
   <button type="button" onClick={()=>setPending(null)}>Cancel</button></div>}
  {p.artifact!==null&&<><p>{p.artifact.bytes} bytes · {p.artifact.valueCount} values</p>
   <output>{p.artifact.sha256}</output><button onClick={()=>void p.onRefresh(p.artifact!.exportId)}>Refresh export status</button>
   <button onClick={()=>void p.onDownload(p.artifact!.exportId)}>Download verified {p.artifact.format.toUpperCase()}</button></>}
  {p.failure!==null&&<p role="alert">{p.failure.code}: {p.failure.message}</p>}
 </div>}
```

The download callback creates an object URL from the `DownloadResult.blob`, assigns only `DownloadResult.filename` parsed from server `Content-Disposition`, clicks once, and immediately revokes the URL. Failure never falls back to a filesystem path. Dialog focus/return/Escape uses the same tested helper as group confirmations.

- [ ] **Step 4: Run GREEN, typecheck, axe, and exact route tests.** From UI root run `& $npm run test -- tests/export.test.tsx tests/contract.test.ts -t "export|downloads without"; & $npm run typecheck; & $npm run test:a11y`. Expected: PASS; no wire artifact contains a `verified` property.

- [ ] **Step 5: Commit the unit.** Stage only export component/test and exact controller/reducer/app changes; commit `feat(STM32TK-0502): add verified CSV JSONL exports`.

### Task 16: Close the Frontend Shell, Accessibility, and Bootstrap Failure Paths

**Files:** create or finalize `src/app.tsx`, `src/styles.css`, `tests/app-props.ts`, `tests/a11y.test.tsx`, and `tests/app.test.tsx`; modify `main.tsx` and controller only for final composition.

**Interfaces:** produces the complete frontend-core `AppViewProps`, labeled desktop shell, fixed blocking startup/request errors, keyboard-reachable workflows, responsive 1024×768 stacking, and reduced-motion behavior. It produces no static serving or E2E fixture.

- [ ] **Step 1: Write the failing complete-shell and axe tests.** Create:

```tsx
// tests/app-props.ts
import {vi} from "vitest";
import type {AppViewProps} from "../src/app";
import {EXPORT_RANGE,HISTORY_PAGE,HISTORY_QUERY,LIVE_ROW,VALID_GROUP,VALID_PROBES,
 VALID_STATUS,VARIABLE_CATALOG} from "./fixtures";
const resolved=async():Promise<void>=>{};
export const APP_PROPS:AppViewProps={blockingFailure:null,
 identity:{project:VALID_STATUS.project,firmware:VALID_STATUS.firmware,onCopy:vi.fn()},
 probes:{probes:VALID_PROBES.probes,connectedProbeId:VALID_STATUS.probe.probeId,canReconnect:true,
  leaseReason:null,onRefresh:resolved,onConnect:async()=>{},onReconnect:resolved,onRelease:resolved},
 groups:{groups:[VALID_GROUP],selectedGroupId:VALID_GROUP.groupId,draft:{sourceGroupId:VALID_GROUP.groupId,
  expectedRevision:VALID_GROUP.revision,name:VALID_GROUP.name,description:VALID_GROUP.description,
  intervalMs:VALID_GROUP.intervalMs,items:VALID_GROUP.items},failure:null,onSelect:vi.fn(),
  onDraftChange:vi.fn(),onRemove:vi.fn(),onCreate:vi.fn(),onSave:vi.fn(),onDelete:vi.fn(),
  onReadImport:async()=>({ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import file is invalid"}),
  onImport:vi.fn(),onExport:vi.fn(),onRefresh:vi.fn()},
 catalog:{connected:true,bindingEpoch:VALID_STATUS.sampling.bindingEpoch,
  variables:{kind:"variables",query:"",bindingEpoch:VALID_STATUS.sampling.bindingEpoch,
   items:VARIABLE_CATALOG.items,nextCursor:null},registers:null,onSearch:vi.fn(),onNext:vi.fn(),onAdd:vi.fn()},
 sampling:{status:VALID_STATUS,group:VALID_GROUP,loadedRevision:VALID_GROUP.revision,
  onStart:vi.fn(),onPause:vi.fn(),onResume:vi.fn(),onStop:vi.fn()},
 liveTable:{rows:[],selectedSeries:[],onSeriesToggle:vi.fn()},liveChart:{series:[],range:{start:0,end:100},onZoom:vi.fn()},
 zoom:{range:{start:0,end:100},onAction:vi.fn()},status:{actualRateHz:0,latencyNs:0,
  drops:{subscriber:0,history:0,deadline:0,service:0}},notices:[],
 history:{query:HISTORY_QUERY,page:null,failure:null,onLoad:vi.fn(),onPage:vi.fn()},
 export:{range:EXPORT_RANGE,artifact:null,failure:null,
  onCreate:vi.fn(),onRefresh:vi.fn(),onDownload:vi.fn()}};
export const EMPTY_APP_PROPS:AppViewProps={...APP_PROPS,groups:{...APP_PROPS.groups,groups:[],selectedGroupId:null,
 draft:{sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]}}};
export const CONNECTED_APP_PROPS:AppViewProps=APP_PROPS;
export const LIVE_APP_PROPS:AppViewProps={...APP_PROPS,liveTable:{...APP_PROPS.liveTable,rows:[LIVE_ROW]}};
export const HISTORY_APP_PROPS:AppViewProps={...APP_PROPS,history:{...APP_PROPS.history,page:HISTORY_PAGE}};
export const ERROR_APP_PROPS:AppViewProps={...APP_PROPS,
 blockingFailure:{code:"MONITOR_REQUEST_FAILED",message:"Request failed"}};

// tests/app.test.tsx
import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import {App} from "../src/app";
import {buildAppViewProps,type ControllerCommands} from "../src/controller";
import {initialMonitorState,reduceMonitor} from "../src/state/reducer";
import {APP_PROPS} from "./app-props";
import {VALID_GROUP,VALID_STATUS} from "./fixtures";
it("renders every frontend-core region from props without issuing transport",()=>{
 const fetchSpy=vi.fn(),websocket=vi.fn();vi.stubGlobal("fetch",fetchSpy);vi.stubGlobal("WebSocket",websocket);
 render(<App {...APP_PROPS}/>);
 for(const name of ["Monitor identity","Probes","User monitor groups","Catalog","Sampling controls",
  "Live monitor values","Live chart","Monitor status","History","History export"])
  expect(screen.getByRole("region",{name})).toBeVisible();
 expect(screen.getAllByRole("region")).toHaveLength(10);
 expect(fetchSpy).not.toHaveBeenCalled();expect(websocket).not.toHaveBeenCalled();vi.unstubAllGlobals();
});

it("keeps a blocking public failure explicit and never renders details as fact",()=>{
 render(<App {...APP_PROPS} blockingFailure={{code:"MONITOR_PROVENANCE_CHANGED",
  message:"Monitor identity changed"}}/>);
 expect(screen.getByRole("alert")).toHaveTextContent("MONITOR_PROVENANCE_CHANGED: Monitor identity changed");
 expect(screen.queryByText(/internal|traceback|absolute path/i)).toBeNull();
});

it("builds every App callback from the complete controller command surface",()=>{
 const fn=vi.fn(),commands={copyIdentity:fn,refreshStatus:fn,refreshProbes:fn,connectProbe:fn,
  reconnectProbe:fn,releaseProbe:fn,selectGroup:fn,changeGroupDraft:fn,removeDraftItem:fn,
  addDraftItem:fn,createGroup:fn,saveGroup:fn,deleteGroup:fn,readImport:fn,importGroups:fn,
  exportGroups:fn,refreshGroups:fn,catalog:fn,startSampling:fn,pauseSampling:fn,
  resumeSampling:fn,stopSampling:fn,toggleSeries:fn,zoom:fn,loadHistory:fn,pageHistory:fn,
  createExport:fn,refreshExport:fn,downloadExport:fn} satisfies ControllerCommands;
 const state=reduceMonitor(initialMonitorState,{type:"initial.loaded",status:VALID_STATUS,
  probes:[],groups:[VALID_GROUP],groupRevision:"a".repeat(64)}),view=buildAppViewProps(state,commands);
 expect(view.probes.onRefresh).toBe(commands.refreshProbes);expect(view.probes.onConnect).toBe(commands.connectProbe);
 expect(view.groups.onDraftChange).toBe(commands.changeGroupDraft);expect(view.groups.onRemove).toBe(commands.removeDraftItem);
 expect(view.groups.onReadImport).toBe(commands.readImport);expect(view.catalog.onAdd).toBe(commands.addDraftItem);
 expect(view.catalog.onSearch).toBe(commands.catalog);expect(view.catalog.onNext).toBe(commands.catalog);
 expect(view.sampling.onStart).toBe(commands.startSampling);expect(view.liveTable.onSeriesToggle).toBe(commands.toggleSeries);
 expect(view.zoom.onAction).toBe(commands.zoom);expect(view.history.onLoad).toBe(commands.loadHistory);
 expect(view.export.onDownload).toBe(commands.downloadExport);
});
```

```tsx
// tests/a11y.test.tsx
import {expect,it} from "vitest";import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";import {axe} from "vitest-axe";
import {App} from "../src/app";
import {CONNECTED_APP_PROPS,EMPTY_APP_PROPS,ERROR_APP_PROPS,HISTORY_APP_PROPS,LIVE_APP_PROPS} from "./app-props";
it("has no serious or critical axe violations in empty connected live history and error states",async()=>{
 for(const props of [EMPTY_APP_PROPS,CONNECTED_APP_PROPS,LIVE_APP_PROPS,HISTORY_APP_PROPS,ERROR_APP_PROPS]){
  const {container,unmount}=render(<App {...props}/>);const result=await axe(container);
  expect(result.violations.filter(v=>v.impact==="serious"||v.impact==="critical")).toEqual([]);unmount();
 }
});

it("keeps the complete keyboard path and dialog restoration",async()=>{
 const user=userEvent.setup();render(<App {...CONNECTED_APP_PROPS}/>);
 await user.tab();expect(screen.getByRole("button",{name:"Copy full Git HEAD"})).toHaveFocus();
 for(const name of ["Refresh probes","Create group","Start sampling","Reset chart zoom","Load history","Create CSV export"]){
  const control=screen.getByRole("button",{name});control.focus();expect(control).toHaveFocus();}
 for(const name of ["Variable or register search","History start","Export start"]){
  const control=screen.getByLabelText(name);control.focus();expect(control).toHaveFocus();}
});
```

- [ ] **Step 2: Run RED.** From UI root run `& $npm run test -- tests/app.test.tsx tests/a11y.test.tsx`. Expected: FAIL on missing shell labels/styles or transport-free composition.

- [ ] **Step 3: Implement the prop-only shell and minimum accessibility CSS.** Use:

```tsx
// src/app.tsx
import type {ComponentProps} from "preact";
import type {PublicFailure} from "./api/contract";
import {CatalogPanel} from "./components/CatalogPanel";import {ChartZoomControls} from "./components/ChartZoomControls";
import {ExportPanel} from "./components/ExportPanel";import {GroupPanel} from "./components/GroupPanel";
import {HistoryPanel} from "./components/HistoryPanel";import {IdentityBar} from "./components/IdentityBar";
import {LiveChart} from "./components/LiveChart";import {LiveTable} from "./components/LiveTable";
import {NoticeRegion} from "./components/NoticeRegion";import {ProbePanel} from "./components/ProbePanel";
import {SamplingControls} from "./components/SamplingControls";import {StatusStrip} from "./components/StatusStrip";
export type AppViewProps={blockingFailure:PublicFailure|null;
 identity:ComponentProps<typeof IdentityBar>;probes:ComponentProps<typeof ProbePanel>;
 groups:ComponentProps<typeof GroupPanel>;catalog:ComponentProps<typeof CatalogPanel>;
 sampling:ComponentProps<typeof SamplingControls>;liveTable:ComponentProps<typeof LiveTable>;
 liveChart:ComponentProps<typeof LiveChart>;zoom:ComponentProps<typeof ChartZoomControls>;
 status:ComponentProps<typeof StatusStrip>;notices:ComponentProps<typeof NoticeRegion>["notices"];
 history:ComponentProps<typeof HistoryPanel>;export:ComponentProps<typeof ExportPanel>};
export function App(p:AppViewProps):JSX.Element{return <main>
 {p.blockingFailure!==null&&<p role="alert">{p.blockingFailure.code}: {p.blockingFailure.message}</p>}
 <section aria-label="Monitor identity"><IdentityBar {...p.identity}/></section>
 <section aria-label="Probes"><ProbePanel {...p.probes}/></section>
 <section aria-label="User monitor groups"><GroupPanel {...p.groups}/></section>
 <section aria-label="Catalog"><CatalogPanel {...p.catalog}/></section>
 <section aria-label="Sampling controls"><SamplingControls {...p.sampling}/></section>
 <section aria-label="Live monitor values"><LiveTable {...p.liveTable}/></section>
 <section aria-label="Live chart"><LiveChart {...p.liveChart}/><ChartZoomControls {...p.zoom}/></section>
 <section aria-label="Monitor status"><StatusStrip {...p.status}/><NoticeRegion notices={p.notices}/></section>
 <section aria-label="History"><HistoryPanel {...p.history}/></section>
 <section aria-label="History export"><ExportPanel {...p.export}/></section>
 </main>}
```

```ts
// src/controller.ts
import type {AppViewProps} from "./app";
import {loadGroups,loadInitial,MonitorClient} from "./api/client";
import {LiveClient} from "./api/live";
import type {ApiFailure,ApiResult,CreateGroupRequest,DeleteGroupRequest,DownloadResult,EventId,
 ExportRequest,GroupDraft,GroupImportDocument,HistoryQuery,MonitorAction,UpdateGroupRequest,
 WatchItem} from "./api/contract";
import type {ZoomAction} from "./chart/zoom";
import {liveRows,selectedNumericSeries} from "./chart/series";
import {downloadGroupDocument,readGroupImportFile} from "./state/group-transfer";
import type {MonitorState} from "./state/model";
import {initialMonitorState,reduceMonitor} from "./state/reducer";
import {withoutHistoryCursor} from "./state/selectors";
import {LiveReconnectController} from "./live-reconnect";

type CatalogKind="variables"|"registers";
export type ControllerCommands={
 copyIdentity:(value:string)=>Promise<void>;refreshStatus:()=>Promise<void>;refreshProbes:()=>Promise<void>;
 connectProbe:(probeId:string)=>Promise<void>;reconnectProbe:()=>Promise<void>;releaseProbe:()=>Promise<void>;
 selectGroup:(groupId:string|null)=>void;changeGroupDraft:(draft:GroupDraft)=>void;
 removeDraftItem:(key:string)=>void;addDraftItem:(watch:WatchItem)=>void;
 createGroup:(request:CreateGroupRequest)=>Promise<void>;
 saveGroup:(groupId:string,request:UpdateGroupRequest)=>Promise<void>;
 deleteGroup:(groupId:string,request:DeleteGroupRequest)=>Promise<void>;
 readImport:(file:File)=>Promise<ApiResult<GroupImportDocument>>;
 importGroups:(request:{document:GroupImportDocument;authorized:true})=>Promise<void>;
 exportGroups:(document:GroupImportDocument)=>Promise<void>;refreshGroups:()=>Promise<void>;
 catalog:(kind:CatalogKind,query:string,cursor:string|undefined,limit:100,bindingEpoch:number)=>Promise<void>;
 startSampling:(request:{groupId:string;expectedRevision:number})=>Promise<void>;
 pauseSampling:()=>Promise<void>;resumeSampling:()=>Promise<void>;stopSampling:()=>Promise<void>;
 toggleSeries:(key:string)=>void;zoom:(action:ZoomAction)=>void;loadHistory:(query:HistoryQuery)=>Promise<void>;
 pageHistory:(cursor:string|undefined)=>Promise<void>;createExport:(request:ExportRequest)=>Promise<void>;
 refreshExport:(exportId:string)=>Promise<void>;downloadExport:(exportId:string)=>Promise<void>;
};
const DEFAULT_HISTORY_QUERY:HistoryQuery={startNs:0n,endNs:1n,limit:10_000};
const failureAt=(state:MonitorState,scope:string):ApiFailure|null=>state.failures[scope]??null;
export function buildAppViewProps(state:MonitorState,commands:ControllerCommands):AppViewProps{
 const status=state.status;if(status===null)throw new Error("monitor state is not initialized");
 const selected=state.groups.find(group=>group.groupId===state.selectedGroupId)??null;
 const historyQuery=state.history?.query??DEFAULT_HISTORY_QUERY;
 return {blockingFailure:failureAt(state,"initial"),
  identity:{project:status.project,firmware:status.firmware,onCopy:commands.copyIdentity},
  probes:{probes:state.probes,connectedProbeId:status.probe.probeId,canReconnect:state.canReconnect,
   leaseReason:status.sampling.blockedCode??failureAt(state,"probe")?.code??null,
   onRefresh:commands.refreshProbes,onConnect:commands.connectProbe,
   onReconnect:commands.reconnectProbe,onRelease:commands.releaseProbe},
  groups:{groups:state.groups,selectedGroupId:state.selectedGroupId,draft:state.groupDraft,
   failure:failureAt(state,"groups"),onSelect:commands.selectGroup,onDraftChange:commands.changeGroupDraft,
   onRemove:commands.removeDraftItem,onCreate:commands.createGroup,onSave:commands.saveGroup,
   onDelete:commands.deleteGroup,onReadImport:commands.readImport,onImport:commands.importGroups,
   onExport:commands.exportGroups,onRefresh:commands.refreshGroups},
  catalog:{connected:status.probe.connected,bindingEpoch:status.sampling.bindingEpoch,
   variables:state.catalog.variables,registers:state.catalog.registers,
   onSearch:commands.catalog,onNext:commands.catalog,onAdd:commands.addDraftItem},
  sampling:{status,group:selected,loadedRevision:selected?.revision??null,onStart:commands.startSampling,
   onPause:commands.pauseSampling,onResume:commands.resumeSampling,onStop:commands.stopSampling},
  liveTable:{rows:liveRows(state.live),selectedSeries:state.selectedSeries,onSeriesToggle:commands.toggleSeries},
  liveChart:{series:selectedNumericSeries(state),range:state.zoom,onZoom:commands.zoom},
  zoom:{range:state.zoom,onAction:commands.zoom},status:{actualRateHz:state.live.actualRateHz,
   latencyNs:state.live.latencyNs,drops:state.live.drops},notices:state.notices,
  history:{query:historyQuery,page:state.history?.page??null,failure:failureAt(state,"history"),
   onLoad:commands.loadHistory,onPage:commands.pageHistory},
  export:{range:{startNs:historyQuery.startNs,endNs:historyQuery.endNs},artifact:state.verifiedExport,
   failure:failureAt(state,"export"),onCreate:commands.createExport,onRefresh:commands.refreshExport,
   onDownload:commands.downloadExport}};
}
const downloadBlob=(result:Extract<DownloadResult,{ok:true}>):void=>{const url=URL.createObjectURL(result.blob);
 try{const anchor=document.createElement("a");anchor.href=url;anchor.download=result.filename;anchor.click();}
 finally{URL.revokeObjectURL(url);}};

export class MonitorController{
 private state:MonitorState=initialMonitorState;private readonly live:LiveClient;
 private readonly reconnect:LiveReconnectController;private statusRefresh:Promise<void>|null=null;private disposed=false;
 constructor(private readonly client:MonitorClient,origin:string,factory:(url:string)=>WebSocket,
  private readonly renderView:(props:AppViewProps)=>void){
  this.live=new LiveClient(origin,factory,action=>this.dispatch(action));
  this.reconnect=new LiveReconnectController({dispatch:action=>this.dispatch(action),
   latestEventId:():EventId|undefined=>this.state.lastEventId,connect:after=>{const socket=this.live.connect(after);
    socket.addEventListener("open",()=>this.reconnect.opened());
    socket.addEventListener("close",()=>this.reconnect.closed());}});
 }
 private dispatch(action:MonitorAction):void{if(this.disposed)return;
  if(action.type==="live.event"&&action.event.type==="heartbeat")this.reconnect.heartbeatReceived();
  const needed=this.state.transport.needsStatusRefresh;this.state=reduceMonitor(this.state,action);
  if(this.state.status!==null)this.renderView(buildAppViewProps(this.state,this.commands));
  if(!needed&&this.state.transport.needsStatusRefresh)void this.refreshStatusImpl();
 }
 private fail(scope:string,result:ApiFailure):void{this.dispatch({type:"request.failed",scope,
  code:result.code,message:result.message});}
 private async request<T>(scope:string,run:()=>Promise<ApiResult<T>>):Promise<T|null>{try{
  const result=await run();if(!result.ok){this.fail(scope,result);return null;}return result.data;
 }catch{this.fail(scope,{ok:false,code:"MONITOR_REQUEST_FAILED",message:"Monitor request failed"});return null;}}
 private refreshStatusImpl():Promise<void>{if(this.statusRefresh!==null)return this.statusRefresh;
  this.statusRefresh=(async()=>{const status=await this.request("status",()=>this.client.status());
   if(status!==null)this.dispatch({type:"status.loaded",status});})().finally(()=>{this.statusRefresh=null;});
  return this.statusRefresh;
 }
 private async refreshGroupsImpl():Promise<void>{const loaded=await this.request("groups",()=>loadGroups(this.client));
  if(loaded!==null)this.dispatch({type:"groups.loaded",groups:loaded.groups,revision:loaded.revision});}
 private async groupMutation(run:()=>Promise<ApiResult<unknown>>):Promise<boolean>{try{const result=await run();
  if(!result.ok){if(result.code==="MONITOR_GROUP_CONFLICT")await this.refreshGroupsImpl();this.fail("groups",result);return false;}
  await this.refreshGroupsImpl();return true;
 }catch{this.fail("groups",{ok:false,code:"MONITOR_REQUEST_FAILED",message:"Monitor request failed"});return false;}}
 private async sampling(run:()=>Promise<ApiResult<unknown>>):Promise<void>{await this.request("sampling",run);}
 readonly commands:ControllerCommands={
  copyIdentity:async value=>{try{await navigator.clipboard.writeText(value);}catch{
   this.fail("identity",{ok:false,code:"MONITOR_CLIPBOARD_FAILED",message:"Identity copy failed"});}},
  refreshStatus:()=>this.refreshStatusImpl(),
  refreshProbes:async()=>{const data=await this.request("probes",()=>this.client.probes());
   if(data!==null)this.dispatch({type:"probes.loaded",probes:data.probes});},
  connectProbe:async probeId=>{const binding=await this.request("probe",()=>this.client.connect({probeId}));
   if(binding!==null){this.dispatch({type:"probe.reconnectAvailable",available:true});await this.refreshStatusImpl();}},
  reconnectProbe:async()=>{const binding=await this.request("probe",()=>this.client.reconnect());
   if(binding!==null){this.dispatch({type:"probe.reconnectAvailable",available:true});await this.refreshStatusImpl();}},
  releaseProbe:async()=>{const released=await this.request("probe",()=>this.client.release());
   if(released!==null)await this.refreshStatusImpl();},
  selectGroup:groupId=>this.dispatch({type:"group.selected",groupId}),
  changeGroupDraft:draft=>this.dispatch({type:"group.draft.changed",draft}),
  removeDraftItem:key=>this.dispatch({type:"group.item.removed",key}),
  addDraftItem:watch=>this.dispatch({type:"group.item.added",watch}),
  createGroup:async request=>{try{const result=await this.client.createGroup(request);if(!result.ok){
    if(result.code==="MONITOR_GROUP_CONFLICT")await this.refreshGroupsImpl();this.fail("groups",result);return;}
   await this.refreshGroupsImpl();this.dispatch({type:"group.selected",groupId:result.data.groupId});}
   catch{this.fail("groups",{ok:false,code:"MONITOR_REQUEST_FAILED",message:"Monitor request failed"});}},
  saveGroup:async(groupId,request)=>{await this.groupMutation(()=>this.client.updateGroup(groupId,request));},
  deleteGroup:async(groupId,request)=>{await this.groupMutation(()=>this.client.deleteGroup(groupId,request));},
  readImport:async file=>{const result=await readGroupImportFile(file);if(!result.ok)this.fail("groups",result);return result;},
  importGroups:async request=>{await this.groupMutation(()=>this.client.importGroups(request));},
  exportGroups:async document=>{try{downloadGroupDocument(document);}catch{
   this.fail("groups",{ok:false,code:"MONITOR_DOWNLOAD_FAILED",message:"Group export download failed"});}},
  refreshGroups:()=>this.refreshGroupsImpl(),
  catalog:async(kind,query,cursor,limit,bindingEpoch)=>{const normalized=query.normalize("NFC").slice(0,128);
   if(limit!==100||this.state.status?.sampling.bindingEpoch!==bindingEpoch)return;
   this.dispatch({type:"catalog.requested",catalog:kind,query:normalized,bindingEpoch,cursor});
   if(kind==="variables"){const page=await this.request("catalog",()=>this.client.variables(normalized,cursor));
    if(page!==null)this.dispatch({type:"catalog.loaded",catalog:"variables",query:normalized,bindingEpoch,
     cursor,items:page.items,nextCursor:page.nextCursor});}
   else{const page=await this.request("catalog",()=>this.client.registers(normalized,cursor));
    if(page!==null)this.dispatch({type:"catalog.loaded",catalog:"registers",query:normalized,bindingEpoch,
     cursor,items:page.items,nextCursor:page.nextCursor});}},
  startSampling:request=>this.sampling(()=>this.client.start(request)),
  pauseSampling:()=>this.sampling(()=>this.client.pause()),resumeSampling:()=>this.sampling(()=>this.client.resume()),
  stopSampling:()=>this.sampling(()=>this.client.stop()),
  toggleSeries:key=>this.dispatch({type:"series.toggled",key}),zoom:action=>this.dispatch(action),
  loadHistory:async query=>{const page=await this.request("history",()=>this.client.history(query));
   if(page!==null)this.dispatch({type:"history.loaded",query,page});},
  pageHistory:async cursor=>{const current=this.state.history?.query??DEFAULT_HISTORY_QUERY;
   const query=withoutHistoryCursor(current);if(cursor!==undefined)query.cursor=cursor;
   const page=await this.request("history",()=>this.client.history(query));
   if(page!==null)this.dispatch({type:"history.loaded",query,page});},
  createExport:async request=>{const artifact=await this.request("export",()=>this.client.createExport(request));
   if(artifact!==null)this.dispatch({type:"export.verified",artifact});},
  refreshExport:async exportId=>{const artifact=await this.request("export",()=>this.client.exportStatus(exportId));
   if(artifact!==null)this.dispatch({type:"export.verified",artifact});},
  downloadExport:async exportId=>{try{const result=await this.client.downloadExport(exportId);
   if(!result.ok){this.fail("export",result);return;}downloadBlob(result);}catch{
    this.fail("export",{ok:false,code:"MONITOR_DOWNLOAD_FAILED",message:"Monitor download failed"});}}
 };
 async start():Promise<boolean>{const initial=await this.request("initial",()=>loadInitial(this.client));
  if(initial===null)return false;this.dispatch({type:"initial.loaded",status:initial.status,
   probes:initial.probes,groups:initial.groups,groupRevision:initial.groupRevision});
  this.reconnect.open(this.state.lastEventId);return true;}
 dispose():void{this.disposed=true;this.reconnect.dispose();this.live.close();}
}
```

```tsx
// src/main.tsx -- complete final module; no App state/command mismatch remains.
import {bootstrapFromFragment,renderStartupError} from "./bootstrap";
import "./styles.css";
const bootstrap=await bootstrapFromFragment(window,window.fetch.bind(window));
if(!bootstrap.ok)renderStartupError(document);
else{const [{h,render},{App},{MonitorController},{MonitorClient}]=await Promise.all([
 import("preact"),import("./app"),import("./controller"),import("./api/client")]);
 const host=document.getElementById("app")!;
 const controller=new MonitorController(new MonitorClient(window.fetch.bind(window)),window.location.origin,
  url=>new WebSocket(url),props=>render(h(App,props),host));
 if(!await controller.start())renderStartupError(document);
}
```

```css
/* src/styles.css */
:root{font-family:system-ui,sans-serif;color:#111;background:#fff}body{margin:0}main{display:grid;
 grid-template-columns:minmax(20rem,1fr) minmax(30rem,2fr);gap:1rem;padding:1rem}
section{min-width:0;border:1px solid #5b6470;padding:.75rem}button,input,select{font:inherit}
:focus-visible{outline:3px solid #005fcc;outline-offset:2px} [role="alert"]{border-left:.35rem solid #a40000;padding:.5rem}
@media(max-width:1100px){main{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;
 animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
```

Every dialog focuses its container on open, returns focus to its trigger on close, and handles Escape only before submission. Status/error meaning always has text, not color alone. Table remains the canvas-independent accessible equivalent of live/history chart data.

- [ ] **Step 4: Run GREEN and the full local frontend-core suite.** From UI root run `& $npm ci; & $npm run typecheck; & $npm run lint; & $npm run test:coverage; & $npm run test:a11y; & $npm run build; & $npm ci`; then from repository root run `git diff --exit-code -- tools/stm32-monitor/ui/package-lock.json`. Expected: PASS, each new/modified frontend product module branch coverage ≥90%, and no lockfile change.

- [ ] **Step 5: Commit the shell unit.** Stage only app/main/styles/controller and shell/a11y tests; commit `feat(STM32TK-0502): close accessible frontend core`.

## Interface Handoff to Later Plans

The returned frontend-core implementation head is an input, not an accepted release head. The controller writes one canonical repository-external UTF-8/no-BOM packet and its adjacent `.sha256` file. The runtime plan receives only the absolute JSON path through `FrontendCorePacketPath`; it derives the signature path as `FrontendCorePacketPath + '.sha256'`.

```ts
type FrontendCoreReturnPacket={schema:"stm32tk-0502-frontend-core/1";
 moduleId:"STM32TK-0502-MONITOR-UI-RELEASE";
 acceptedBase:"bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa";planBundleHead:string;
 frontendCoreCodeHead:string;branch:string;worktreeClean:true;remoteActionPerformed:false;
 blobs:readonly {path:string;oid:string}[]};
```

```powershell
$FrontendCoreCodeHead = (& git rev-parse HEAD).Trim()
$Branch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $FrontendCoreCodeHead -notmatch '^[0-9a-f]{40}$' -or [string]::IsNullOrWhiteSpace($Branch)) {
 throw 'frontend-core identity is invalid'
}
& git merge-base --is-ancestor $PlanPacket.planBundleHead $FrontendCoreCodeHead
if ($LASTEXITCODE -ne 0) { throw 'frontend-core head does not descend from planBundleHead' }
$Dirty = @(& git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $Dirty.Count -ne 0) { throw 'frontend-core worktree must be clean' }
$ChangedPaths = @(& git diff --name-only --diff-filter=ACMRT $PlanPacket.planBundleHead $FrontendCoreCodeHead | Sort-Object)
if ($LASTEXITCODE -ne 0 -or $ChangedPaths.Count -eq 0) { throw 'frontend-core path inventory is empty' }
$DeletedPaths = @(& git diff --name-only --diff-filter=D $PlanPacket.planBundleHead $FrontendCoreCodeHead)
if ($LASTEXITCODE -ne 0 -or $DeletedPaths.Count -ne 0) { throw 'frontend-core must not delete paths' }
$Blobs = @()
foreach ($Path in $ChangedPaths) {
 $Allowed = $Path -like 'tools/stm32-monitor/ui/*' -or
  $Path -in @('tools/stm32-monitor/src/stm32_monitor/auth.py','tools/stm32-monitor/src/stm32_monitor/service.py',
   'tools/stm32-monitor/tests/test_auth.py','tools/stm32-monitor/tests/test_service.py','tools/stm32-monitor/tests/test_ui_config.py')
 if (-not $Allowed) { throw "frontend-core path is out of scope: $Path" }
 $Oid = (& git rev-parse "${FrontendCoreCodeHead}:$Path").Trim()
 if ($LASTEXITCODE -ne 0 -or $Oid -notmatch '^[0-9a-f]{40}$') { throw "frontend-core blob is invalid: $Path" }
 $Blobs += [ordered]@{path=$Path;oid=$Oid}
}
$FrontendCoreReturnPacket = [ordered]@{schema='stm32tk-0502-frontend-core/1';
 moduleId='STM32TK-0502-MONITOR-UI-RELEASE';acceptedBase=$PlanPacket.acceptedBase;
 planBundleHead=$PlanPacket.planBundleHead;frontendCoreCodeHead=$FrontendCoreCodeHead;branch=$Branch;
 worktreeClean=$true;remoteActionPerformed=$false;blobs=$Blobs}
$FrontendEvidenceRoot = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) (
 'stm32tk-0502-frontend-return-' + [guid]::NewGuid().ToString('N'))))
New-Item -ItemType Directory -LiteralPath $FrontendEvidenceRoot | Out-Null
$FrontendCorePacketPath = Join-Path $FrontendEvidenceRoot 'frontend-core-return.json'
$Utf8 = New-Object Text.UTF8Encoding($false, $true)
$ReturnBytes = $Utf8.GetBytes(($FrontendCoreReturnPacket | ConvertTo-Json -Compress -Depth 8))
[IO.File]::WriteAllBytes($FrontendCorePacketPath, $ReturnBytes)
$ReturnSha256 = [Security.Cryptography.SHA256]::Create()
try { $ReturnHash = $ReturnSha256.ComputeHash($ReturnBytes) } finally { $ReturnSha256.Dispose() }
$ReturnSignature = (($ReturnHash | ForEach-Object { $_.ToString('x2') }) -join '')
[IO.File]::WriteAllText($FrontendCorePacketPath + '.sha256', $ReturnSignature + "`n", [Text.UTF8Encoding]::new($false))
$env:FrontendCorePacketPath = $FrontendCorePacketPath
```

The runtime-plan consumer runs this PowerShell 5.1-compatible validation before using the packet:

```powershell
$FrontendCorePacketPath = [IO.Path]::GetFullPath($env:FrontendCorePacketPath)
$SignaturePath = $FrontendCorePacketPath + '.sha256'
if (-not [IO.File]::Exists($FrontendCorePacketPath) -or -not [IO.File]::Exists($SignaturePath)) { throw 'frontend-core packet pair is missing' }
$Utf8 = New-Object Text.UTF8Encoding($false, $true)
$Bytes = [IO.File]::ReadAllBytes($FrontendCorePacketPath)
if ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xef -and $Bytes[1] -eq 0xbb -and $Bytes[2] -eq 0xbf) { throw 'frontend-core packet has a BOM' }
$SignatureBytes = [IO.File]::ReadAllBytes($SignaturePath)
if ($SignatureBytes.Length -ge 3 -and $SignatureBytes[0] -eq 0xef -and $SignatureBytes[1] -eq 0xbb -and $SignatureBytes[2] -eq 0xbf) { throw 'frontend-core signature has a BOM' }
$ExpectedSignature = $Utf8.GetString($SignatureBytes).Trim()
if ($ExpectedSignature -notmatch '^[0-9a-f]{64}$') { throw 'frontend-core signature is invalid' }
$Hash = [Security.Cryptography.SHA256]::Create()
try { $ActualSignature = (($Hash.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') }) -join '') } finally { $Hash.Dispose() }
if ($ActualSignature -cne $ExpectedSignature) { throw 'frontend-core signature mismatch' }
$Text = $Utf8.GetString($Bytes);try { $FrontendCorePacket = $Text | ConvertFrom-Json } catch { throw 'frontend-core JSON is invalid' }
$Names = @('schema','moduleId','acceptedBase','planBundleHead','frontendCoreCodeHead','branch','worktreeClean','remoteActionPerformed','blobs')
if ((@($FrontendCorePacket.PSObject.Properties.Name) -join "`n") -cne ($Names -join "`n")) { throw 'frontend-core schema keys or order differ' }
if ($FrontendCorePacket.schema -cne 'stm32tk-0502-frontend-core/1' -or
 $FrontendCorePacket.moduleId -cne 'STM32TK-0502-MONITOR-UI-RELEASE' -or
 $FrontendCorePacket.acceptedBase -cne 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa' -or
 $FrontendCorePacket.worktreeClean -ne $true -or $FrontendCorePacket.remoteActionPerformed -ne $false) {
 throw 'frontend-core literals differ'
}
foreach ($Name in @('planBundleHead','frontendCoreCodeHead')) {
 if ([string]$FrontendCorePacket.$Name -notmatch '^[0-9a-f]{40}$') { throw "frontend-core SHA is invalid: $Name" }
}
& git merge-base --is-ancestor $FrontendCorePacket.acceptedBase $FrontendCorePacket.planBundleHead
if ($LASTEXITCODE -ne 0) { throw 'frontend-core accepted-base ancestry mismatch' }
& git merge-base --is-ancestor $FrontendCorePacket.planBundleHead $FrontendCorePacket.frontendCoreCodeHead
if ($LASTEXITCODE -ne 0) { throw 'frontend-core head ancestry mismatch' }
$ExpectedPaths = @(& git diff --name-only --diff-filter=ACMRT $FrontendCorePacket.planBundleHead $FrontendCorePacket.frontendCoreCodeHead | Sort-Object)
if ($LASTEXITCODE -ne 0 -or @($FrontendCorePacket.blobs).Count -ne $ExpectedPaths.Count) { throw 'frontend-core blob inventory count differs' }
for ($Index=0; $Index -lt $ExpectedPaths.Count; $Index++) {
 $Blob = @($FrontendCorePacket.blobs)[$Index]
 if ((@($Blob.PSObject.Properties.Name) -join "`n") -cne "path`noid" -or $Blob.path -cne $ExpectedPaths[$Index] -or
  [string]$Blob.oid -notmatch '^[0-9a-f]{40}$') { throw 'frontend-core blob inventory differs' }
 $Oid = (& git rev-parse "$($FrontendCorePacket.frontendCoreCodeHead):$($Blob.path)").Trim()
 if ($LASTEXITCODE -ne 0 -or $Oid -cne [string]$Blob.oid) { throw 'frontend-core blob identity mismatch' }
}
$Canonical = [ordered]@{}
foreach ($Name in $Names) { $Canonical[$Name]=$FrontendCorePacket.$Name }
$CanonicalBytes = $Utf8.GetBytes(($Canonical | ConvertTo-Json -Compress -Depth 8))
if ($CanonicalBytes.Length -ne $Bytes.Length) { throw 'frontend-core JSON is not canonical' }
for ($Index=0; $Index -lt $Bytes.Length; $Index++) { if ($CanonicalBytes[$Index] -ne $Bytes[$Index]) { throw 'frontend-core JSON is not canonical' } }
```

The frontend-core head guarantees these stable handoffs:

| Consumer plan | Consumes from this plan | Must not reinterpret |
|---|---|---|
| Static assets / CSP / wheel | `npm ci`, `npm run build`, hashed Vite output, dynamic pre-mount bootstrap, same-origin REST/WS | no contract field, route, auth decision, storage, or bootstrap reorder |
| Launcher / Plugin / 0.5.0 promotion | startup fragment grammar and fixed startup error; no auto action | no query token, printed token, ambient runtime, default group, or hidden start |
| Real aiohttp Playwright / security | labeled roles/buttons, exact callbacks, `afterEventId`, stale/gap/reset behavior | inspect bootstrap as same-origin credentials plus Bearer, prove the HttpOnly cookie is set, then prove a bearerless GET and bearerless WS succeed through real HTTP/WS; no browser-side fake transport |
| Performance / release evidence | 256 rows, 8×600, one pending option, ≤1 `setOption`/100 ms | client coalescing must not alter server drop totals |

Exact exported TypeScript interfaces to freeze at handoff are `MonitorClient`, `LiveClient`, `MonitorAction`, `MonitorState`, `reduceMonitor`, `AppViewProps`, `HistoryQuery`, `ExportRequest`, `ExportArtifact`, `buildChartOption`, `ZoomRange`, and `ZoomAction`. If implementation discovers a mismatch with the accepted-base Python serializer, the implementer must stop, cite the exact serializer/test, and revise this plan before changing either side; guessing a compensating field is forbidden.

The bounded Python handoff is the new `MonitorAuth.authorize` signature plus the complete matrix tests. Later static routing may call separate static authorization, but it must not weaken or bypass API/WS authorization.

## Full Plan Verification

After Task 16, from the repository root:

1. Revalidate `$PlanPacket` and its signature, require `git status --short` to be empty, run `git merge-base --is-ancestor $PlanPacket.planBundleHead HEAD`, and set `$FrontendCoreCodeHead = git rev-parse HEAD` only on success.
2. Run `git diff --check "$($PlanPacket.planIntegrationBase)..$FrontendCoreCodeHead"`.
3. Run `git diff --name-status "$($PlanPacket.planIntegrationBase)..$FrontendCoreCodeHead"`; implementation paths must be under `tools/stm32-monitor/ui`, the four bounded auth/service Python files, or `tools/stm32-monitor/tests/test_ui_config.py`. The only additional paths allowed by the integration base are the three exact split-plan paths and the superseded-notice edit to `docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md`; any other path is FAIL.
4. From UI root run `& $npm ci; & $npm run typecheck; & $npm run lint; & $npm run test:coverage; & $npm run test:a11y; & $npm run build; & $npm audit --omit=dev --audit-level=high`. Require all PASS, branch coverage ≥90% for every new/modified product module, and no high/critical production audit item.
5. From `tools/stm32-monitor` run `& $python310 -m pytest tests/test_auth.py tests/test_service.py -q; & $python312 -m pytest tests/test_auth.py tests/test_service.py -q`. Require both PASS.
6. From repository root run `rg -n "localStorage|sessionStorage|indexedDB|serviceWorker|innerHTML|dangerouslySetInnerHTML|from [\"'']echarts[\"'']|AI Analyze|diagnostic session export|preset|localhost:8888" tools/stm32-monitor/ui/src`. Review every match; forbidden behavior is FAIL.
7. Run `git status --short` again. Node build/test output must be ignored or external; the committed lockfile must remain byte-identical.

This slice does not claim static serving, wheel inclusion, launcher behavior, real-browser E2E, five-minute performance, release version promotion, Linux, or hardware PASS. Those gates remain owned by later plans.

## Independent Review Gate

A fresh reviewer receives the absolute repository-external JSON path in `$env:FrontendCorePacketPath` plus its adjacent `.sha256` file and runs the PowerShell 5.1 consumer verbatim. Only after that consumer has populated `$FrontendCorePacket` does the reviewer set `$FrontendCoreCodeHead = [string]$FrontendCorePacket.frontendCoreCodeHead` and `$PlanBundleHead = [string]$FrontendCorePacket.planBundleHead`, require both to be 40 lowercase hex characters, and create a clean worktree at exactly `$FrontendCoreCodeHead`. The reviewer verifies `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`, `$PlanBundleHead`, and `$FrontendCoreCodeHead` exist, requires `git merge-base --is-ancestor $PlanBundleHead $FrontendCoreCodeHead`, and reviews the complete diff `f124cc233f144303beb6cf52f471c6424518afee..$FrontendCoreCodeHead`. The reviewer reruns every command in “Full Plan Verification” with independently resolved bundled tools and checks:

- every wire key against the accepted-base Python serializer;
- every request against the exact service route and body/query grammar;
- the full auth allow/deny matrix, including no-Origin same-origin GET/HEAD/WS and fail-closed mutation/Bearer/metadata/peer/Host cases;
- token scrub before dynamic Preact import and absence from state/DOM/error/storage/console;
- no inferred type/member/element/address field;
- pure reducer revision/binding/run/gap behavior;
- zero-group fresh state and explicit probe/sampling/import/delete/risk actions;
- 256-row, 8×600, 100 ms, 35-second, backoff, history, and export bounds;
- scope contains no later-plan product or release artifacts.

The reviewer returns one evidence-backed verdict for this slice: `ACCEPTED`, `REVISION_REQUIRED` on the same branch/head lineage, or `REWRITE_REQUIRED`. Acceptance of this frontend-core slice does not authorize push, PR mutation, merge, or 0.6 implementation.

## Plan Self-Review

- [x] **Spec coverage:** former Tasks 1–4 are fully represented: toolchain/Preact, strict DTO/envelope/client/live/bootstrap/state, complete bounded auth, identity/probe/catalog/shallow selection, pure user groups/transfer, sampling/table/status/chart/DataZoom, paged history, and verified CSV/JSONL.
- [x] **Five-step product units:** all 16 independently reviewable units have exactly five checkbox steps; every Step 1 contains copyable failing test code and every Step 3 contains the matching minimum implementation code.
- [x] **Type consistency:** `WatchItem`, `HistoryPage`, sample typed values, status sampling fields, binding, group timestamps/revision, and export artifact match accepted-base serializers. Derived watches carry no guessed child type. Nanosecond inputs remain `bigint` through query and JSON numeric-token encoding.
- [x] **Auth closure:** the allow/deny table covers safe GET/HEAD/WS, mutations, Bearer/bootstrap, missing metadata, `Origin:null`, all non-same-origin fetch metadata, wrong peer/Host, unsupported method, bootstrap-cookie denial, and retained header-budget/WS-message gates.
- [x] **Scope closure:** no static assets/service, `ui_dist`, launcher, plugin, Skill, version promotion, E2E fixture, release helper/report, CI, or 0.6 feature is assigned here.
- [x] **Integration-base closure:** `f124cc233f144303beb6cf52f471c6424518afee` remains the immutable full diff/review base, while the non-self-referential dispatch packet records a clean descendant `PLAN_BUNDLE_HEAD`; Task 1 requires that exact implementation head and the full review range remains `f124cc233f144303beb6cf52f471c6424518afee..FRONTEND_CORE_HEAD`.
- [x] **Copy-completeness scan:** every test and implementation instruction names its final file, contract, literal, and verification command; no deferred code body, guessed tool version, or guessed checkout path remains.
