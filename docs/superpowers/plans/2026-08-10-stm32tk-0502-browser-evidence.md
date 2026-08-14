> **REWRITE_REQUIRED — DO NOT EXECUTE.**
>
> Superseded by `docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md`; do not execute this split plan or any packet/signature/handoff machinery in it.

# STM32TK-0502 Browser Evidence and Windows Release Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the completed STM32TK-0502 `0.5.0` runtime/UI release through real-aiohttp Playwright acceptance, exact five-minute production performance evidence, and one repository-owned Windows release-gate helper, then record the evidence in one report-only commit.

**Architecture:** Playwright launches the real `MonitorService` with a test-only fake runtime over the real HTTP/WebSocket boundary; browser tests never replace `fetch`, `WebSocket`, auth, or service routing. A committed PowerShell helper consumes only an explicit repository root, external evidence root, and absolute toolchain JSON, builds fresh offline environments and exact-head wheels, runs the complete Windows matrix, and leaves the repository byte-for-byte unchanged. The runtime-release plan supplies one immutable `runtimeReleaseHead`; this plan commits its browser evidence/helper additions on that ancestry and names the single final `CODE_HEAD` only after a whole-product audit.

**Tech Stack:** Windows 11 x64, CPython 3.10/3.12, aiohttp, Preact, TypeScript, Playwright Chromium, Vitest/Testing Library/axe, PowerShell, npm, pytest/coverage, setuptools/pip offline wheelhouses.

## Global Constraints

- Module: `STM32TK-0502-MONITOR-UI-RELEASE`. Accepted base: `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`. Design authority: `docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md`.
- Specification owner and reviewer: Codex. Implementer and implementation-test owner: Codex subagent. The user-authorized bounded Codex ownership exception is only revision of this plan file; it expires after plan verification and authorizes no product edit, staging, commit, network, push/merge/close/delete, or implementation handoff. There is no OpenClaw handoff or active PR.
- This plan follows `docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md`. Its required input is the exact clean `runtimeReleaseHead` handoff packet. Tasks 1–4 below start at that SHA and are pre-`CODE_HEAD` work on the same implementation branch. Task 5 performs the whole-product audit, names the only final `CODE_HEAD`, and consumes it without amendment; Task 6 adds only the report commit.
- The unique `CODE_HEAD` contains every product source, UI asset, browser fixture/test, version, launcher/runtime, plugin/Skill/README change, release helper, and helper test. The tracked implementation report is absent from `CODE_HEAD` and is the sole change in the following report commit.
- All UI observations traverse the real random-port IPv4-loopback aiohttp listener. The test control channel may seed the fake runtime, but it must not answer browser REST/WebSocket requests or bypass `MonitorService`, `MonitorAuth`, static routing, envelopes, or live-event serialization.
- Browser runtime is fully offline: no CDN, remote font, analytics, telemetry, service worker, source map, non-current-origin request, or browser persistence. The token is absent after bootstrap from URL, DOM, HTML, console, errors, local/session storage, IndexedDB names, readable cookies, screenshots, request logs, evidence, and report.
- Browser bounds are exact: 1280×720 and 1024×768; 200% page zoom; table <=256 rows; chart <=8 series ×600 points; at most one `setOption` per 100 ms; no fabricated continuity or changed server drop totals.
- The five-minute production fixture is Chromium 1280×720 at 10 Hz, 256 rows, and 8×600 points. Only minutes 2–5 are measured. Required thresholds are update p95 <=150 ms, zero Long Tasks >=200 ms, max points <=4,800, queue growth <=0, and heap slope <=2 MiB/min.
- Every executable is invoked through an absolute path supplied in `ToolchainJson` or an absolute Windows system path derived from `SystemRoot`; neither the helper nor its tests use PATH discovery, `py`, a platform Python launcher, a system Node, or a hard-coded checkout path.
- All pip download/build/install commands are offline and contain both `--no-index` and `--find-links <controlled-wheelhouse>`. Fresh test, build, smoke, and fake-managed-runtime venvs live below the single repository-external `EvidenceRoot`.
- Windows and pure-code gates are only `PASS`, `FAIL`, or `BLOCKED`. The only allowed deferrals are exactly `DEFERRED — Linux release owner` and `DEFERRED — user/hardware owner`.
- Do not add CI, collaboration/dispatch automation, a second server, a fixed port, remote auth, hardware claims, 0.6 product code, or tracked screenshots/logs/evidence directories.

---

## Input Contract: Runtime-Release Handoff

The controller must receive the runtime-release plan's exact pair: the repo-external absolute `$RuntimeReleasePacketPath` of the already emitted no-BOM canonical UTF-8 JSON file containing `RuntimeReleaseReturnPacket={schema,moduleId,acceptedBase,planBundleHead,frontendCoreCodeHead,runtimeReleaseHead,branch,worktreeClean,historicalMonitorSkillBlob,remoteActionPerformed}`, plus the separately transported lowercase `handoffSignatureSha256`. The signature is not a packet or wrapper field, and the consumer never rewrites the signed file. It hashes the raw file bytes before any parse. Property names and order are exact, with no extra, renamed, inferred, reordered, or missing field. Only after raw-byte signature verification does it decode strict UTF-8 and call `ConvertFrom-Json`; exact reserialization must equal the original string. It binds the controlled absolute Git executable to `$git`, starts in an isolated worktree at the packet's exact `runtimeReleaseHead`, and runs this preflight before Task 1:

```powershell
if(-not [IO.Path]::IsPathRooted($RuntimeReleasePacketPath)-or
   [IO.Path]::GetFullPath($RuntimeReleasePacketPath)-cne$RuntimeReleasePacketPath){
  throw 'runtime packet path must be a normalized rooted full path'
}
if($handoffSignatureSha256-isnot[string]){throw 'runtime packet signature must be a string'}
$packetPath=(Resolve-Path -LiteralPath $RuntimeReleasePacketPath -ErrorAction Stop).Path
$packetBytes=[IO.File]::ReadAllBytes($packetPath)
if($packetBytes.Count-eq 0-or($packetBytes.Count-ge 3-and$packetBytes[0]-eq0xEF-and
  $packetBytes[1]-eq0xBB-and$packetBytes[2]-eq0xBF)){throw 'runtime packet is empty or has BOM'}
$sha256=[Security.Cryptography.SHA256]::Create()
try{$handoffHash=$sha256.ComputeHash($packetBytes)}finally{$sha256.Dispose()}
$computedHandoffSignature=(($handoffHash|ForEach-Object{$_.ToString('x2')})-join'')
if($handoffSignatureSha256-notmatch'^[0-9a-f]{64}$'-or
   $computedHandoffSignature-cne$handoffSignatureSha256){
  throw 'runtime-release raw-byte signature mismatch'
}
$strictUtf8=New-Object Text.UTF8Encoding($false,$true)
try{$canonicalRuntimePacket=$strictUtf8.GetString($packetBytes)}catch{throw 'runtime packet is not strict UTF-8'}
if($canonicalRuntimePacket.Contains("`r")-or$canonicalRuntimePacket.Contains("`n")){
  throw 'runtime packet is not canonical one-line JSON'
}
$RuntimeReleaseReturnPacket=$canonicalRuntimePacket|ConvertFrom-Json
$expectedRuntimeFields=@('schema','moduleId','acceptedBase','planBundleHead',
  'frontendCoreCodeHead','runtimeReleaseHead','branch','worktreeClean',
  'historicalMonitorSkillBlob','remoteActionPerformed')
$actualRuntimeFields=@($RuntimeReleaseReturnPacket.PSObject.Properties.Name)
if(($actualRuntimeFields.Count-ne$expectedRuntimeFields.Count)-or
   (($actualRuntimeFields-join "`n")-cne($expectedRuntimeFields-join "`n"))){
  throw 'runtime-release packet schema/order mismatch'
}
foreach($name in @('schema','moduleId','acceptedBase','planBundleHead',
  'frontendCoreCodeHead','runtimeReleaseHead','branch','historicalMonitorSkillBlob')){
  if($RuntimeReleaseReturnPacket.$name -isnot [string]){
    throw "runtime-release packet field is not a string: $name"
  }
}
if($RuntimeReleaseReturnPacket.worktreeClean -isnot [bool] -or
   $RuntimeReleaseReturnPacket.remoteActionPerformed -isnot [bool]){
  throw 'runtime-release packet status fields are not booleans'
}
$reserialized=$RuntimeReleaseReturnPacket|ConvertTo-Json -Compress
if($reserialized-cne$canonicalRuntimePacket){
  throw 'runtime-release packet is not exact canonical JSON'
}
$schema=[string]$RuntimeReleaseReturnPacket.schema
$moduleId=[string]$RuntimeReleaseReturnPacket.moduleId
$acceptedBase=[string]$RuntimeReleaseReturnPacket.acceptedBase
$planBundleHead=[string]$RuntimeReleaseReturnPacket.planBundleHead
$frontendCoreCodeHead=[string]$RuntimeReleaseReturnPacket.frontendCoreCodeHead
$runtimeReleaseHead=[string]$RuntimeReleaseReturnPacket.runtimeReleaseHead
$branch=[string]$RuntimeReleaseReturnPacket.branch
$worktreeClean=$RuntimeReleaseReturnPacket.worktreeClean
$historicalMonitorSkillBlob=[string]$RuntimeReleaseReturnPacket.historicalMonitorSkillBlob
$remoteActionPerformed=$RuntimeReleaseReturnPacket.remoteActionPerformed
if($schema-cne'stm32tk-0502-runtime-release/1'){
  throw 'runtime-release schema mismatch'
}
if($acceptedBase-cne'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'){
  throw 'runtime-release accepted base mismatch'
}
if($moduleId-cne'STM32TK-0502-MONITOR-UI-RELEASE'-or[string]::IsNullOrWhiteSpace($branch)){
  throw 'runtime-release identity mismatch'
}
if($planBundleHead-notmatch'^[0-9a-f]{40}$'-or
   $frontendCoreCodeHead-notmatch'^[0-9a-f]{40}$'-or
   $historicalMonitorSkillBlob-notmatch'^[0-9a-f]{40}$'){
  throw 'runtime-release plan/frontend/blob handoff mismatch'
}
if($worktreeClean-ne$true-or$remoteActionPerformed-ne$false){
  throw 'runtime-release handoff status mismatch'
}
if($runtimeReleaseHead-notmatch'^[0-9a-f]{40}$'){throw 'missing full runtimeReleaseHead'}
$actual=(& $git -C $repoRoot rev-parse HEAD).Trim()
if($LASTEXITCODE-ne 0-or$actual-cne$runtimeReleaseHead){throw 'worktree is not runtimeReleaseHead'}
$actualBranch=(& $git -C $repoRoot branch --show-current).Trim()
if($LASTEXITCODE-ne0-or$actualBranch-cne$branch){throw 'worktree branch differs from signed handoff'}
$status=@(& $git -C $repoRoot status --porcelain=v1 --untracked-files=all)
if($LASTEXITCODE-ne 0-or$status.Count-ne 0){throw 'runtime-release handoff is not clean'}
& $git -C $repoRoot merge-base --is-ancestor $frontendCoreCodeHead $runtimeReleaseHead
if($LASTEXITCODE-ne 0){throw 'runtimeReleaseHead does not descend from frontend core'}
& $git -C $repoRoot merge-base --is-ancestor $acceptedBase $planBundleHead
if($LASTEXITCODE-ne 0){throw 'planBundleHead does not descend from accepted base'}
& $git -C $repoRoot merge-base --is-ancestor $planBundleHead $frontendCoreCodeHead
if($LASTEXITCODE-ne 0){throw 'frontend core does not descend from plan bundle'}
& $git -C $repoRoot diff --check "$acceptedBase..$runtimeReleaseHead"
if($LASTEXITCODE-ne 0){throw 'runtime-release diff check failed'}
$blob=(& $git -C $repoRoot rev-parse (
  $runtimeReleaseHead+':requirements/follow-on-skills/stm32-monitor/SKILL.md')).Trim()
if($blob-cne$historicalMonitorSkillBlob){throw 'historical monitor requirement changed'}
$preCodeHeadReport=Join-Path $repoRoot 'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'
if(Test-Path -LiteralPath $preCodeHeadReport){
  throw 'tracked report exists before CODE_HEAD evidence'
}
```

The runtime-release SHA remains recorded as the predecessor; it is not renamed to `CODE_HEAD`. Tasks 1–4 create ordinary reviewed commits. No task rebases, amends, resets, or replaces the handoff ancestry.

## File Structure

- `tools/stm32-monitor/ui/e2e/fake_runtime.py`: stateful test runtime and JSON-line control channel; all product traffic remains real aiohttp.
- `tools/stm32-monitor/ui/e2e/conftest.ts`: validates absolute current-source inputs, owns the Python child, and exposes bounded fixture methods without exposing a token.
- `tools/stm32-monitor/ui/e2e/monitor.spec.ts`: explicit end-to-end product workflow and discontinuity/error behavior.
- `tools/stm32-monitor/ui/e2e/security.spec.ts`, `isolation.spec.ts`: fragment/cookie/Origin/CSP/offline and two-workspace isolation evidence.
- `tools/stm32-monitor/ui/tests/a11y.test.tsx`, `e2e/accessibility.spec.ts`: extend the frontend-core component axe suite and add real-browser keyboard/layout/zoom evidence.
- `tools/stm32-monitor/ui/e2e/performance.spec.ts`: exact five-minute collector, metrics, thresholds, and retained JSON evidence.
- `tools/release/run_0502_windows_gates.ps1`: the sole repository-owned Windows evidence orchestrator; parameters are only `RepoRoot`, `EvidenceRoot`, and `ToolchainJson`.
- `tools/stm32-toolkit/tests/test_0502_release_gate_helper.py`: AST/static and recording-tool execution contract for the helper.
- `docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md`: only tracked evidence report and only file in the report commit.

## Task 1: Real aiohttp Fake-Runtime Browser Fixture

**Files:**

- Create: `tools/stm32-monitor/ui/e2e/fake_runtime.py`
- Create: `tools/stm32-monitor/ui/e2e/conftest.ts`
- Create: `tools/stm32-monitor/ui/e2e/monitor.spec.ts`
- Modify: `tools/stm32-monitor/ui/playwright.config.ts`, `tools/stm32-monitor/ui/package.json`

**Interfaces:**

- Consumes absolute `STM32_MONITOR_E2E_PYTHON`, `STM32_MONITOR_E2E_REPO_ROOT`, and `STM32_MONITOR_E2E_EVIDENCE_ROOT` values set by the release helper.
- Produces `startMonitor(workspace:string,testToken:string):Promise<MonitorBrowserFixture>`. Tests derive one exact, non-secret, workspace-unique token with `testTokenForWorkspace(workspace)` and pass it out-of-band; the fixture never returns a token.
- Produces the complete `MonitorBrowserFixture` interface shown in Step 3, including `failNext` and `setLeaseLost`. `navigate` is one-shot: it moves the private readiness `accessUrl` into one local variable, deletes the readiness field, navigates/bootstrap-scrubs, then clears the last local reference in `finally`. A second call rejects; no test reads an access URL after startup.
- Freezes these complete evidence types alongside the frontend-core `MonitorStatus`, `SampleBatch`, and `LiveEvent` exports. `StateEvent` and `SampleEvent` repeat the exact frozen event variants; they do not invent top-level `stateRevision`, `gap`, `binding`, or `sampling` fields:

```ts
import type {MonitorStatus,SampleBatch} from "../src/api/contract";
export type SeedInput={hz:10;rows:256;series:8;pointsPerSeries:600;durationMs:number};
export type DropTotals={subscriber:number;history:number;deadline:number;service:number};
export type StateEvent={eventId:number;type:"state";data:{
  stateRevision:number;gap:boolean;status:MonitorStatus}};
export type SampleEvent={eventId:number;type:"sample";data:{
  batch:SampleBatch;serviceSubscriberDrops:number}};
export type PerformanceEnvironment={cpu:string;node:string;chromium:string;
  viewport:"1280x720";assetBytes:number};
export type BrowserPerformanceSnapshot={windowElapsedMs:number;
  updates:readonly {elapsedMs:number;durationMs:number}[];
  longTasksAtLeast200Ms:number;maxPoints:number;queueDepth:number;heapBytes:number;
  dropTotals:DropTotals};
export type ExportArtifact={exportId:string;format:"csv"|"jsonl";sha256:string;
  bytes:number;valueCount:number};
```
- Readiness includes resolved `stm32_monitor.__file__` and `stm32_toolkit.__file__`; both must be descendants of `<RepoRoot>/tools/stm32-monitor/src` and `<RepoRoot>/tools/stm32-toolkit/src`.

- [ ] **Step 1: Write the failing real-service fixture contract.** Add this exact test first; adjacent cases use a path containing spaces, reject relative/missing environment values and an installed-copy module path, call every control method, and assert teardown leaves no child and closes the port.

```ts
test("fixture serves one real loopback listener from CODE_HEAD sources", async ({page},testInfo) => {
  const workspace="workspace-a";
  const monitor = await startMonitor(workspace,testTokenForWorkspace(workspace));
  try {
    expect(new URL(monitor.url).hostname).toBe("127.0.0.1");
    expect("accessUrl" in monitor).toBe(false);
    await monitor.seed({hz:10, rows:256, series:8, pointsPerSeries:600,durationMs:1000});
    await monitor.navigate(page);
    await expect(page).toHaveURL(monitor.url + "/");
    await expect(monitor.navigate(page)).rejects.toThrow("already consumed");
    await monitor.emitHeartbeat();
    await monitor.emitGap();
    expect(await monitor.dropTotals()).toEqual({subscriber:0,history:0,deadline:0,service:0});
    if(testInfo.project.name==="chromium-1280"){
      const environment=await monitor.environment(page);
      expect(environment.viewport).toBe("1280x720");expect(environment.assetBytes).toBeGreaterThan(0);
    }
  } finally {
    await monitor.stop();
  }
  await expect.poll(async () => fetch(monitor.url).then(() => "open", () => "closed"))
    .toBe("closed");
});

test("accepted export objects round-trip verified bytes and clean temp artifacts",async({page})=>{
  const workspace="workspace-export",monitor=await startMonitor(
    workspace,testTokenForWorkspace(workspace));
  try{
    await monitor.navigate(page);
    for(const format of ["csv","jsonl"] as const){
      const proof=await page.evaluate(async chosen=>{
        const created=await (await fetch("/api/v1/exports",{method:"POST",
          headers:{"Content-Type":"application/json"},body:JSON.stringify({
            startNs:1,endNs:2,format:chosen,authorized:true})})).json();
        const artifact=created.data as ExportArtifact;
        const loaded=await (await fetch(`/api/v1/exports/${artifact.exportId}`)).json();
        const response=await fetch(`/api/v1/exports/${artifact.exportId}/download`);
        const bytes=new Uint8Array(await response.arrayBuffer());
        const digest=[...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))]
          .map(v=>v.toString(16).padStart(2,"0")).join("");
        return {created:artifact,loaded:loaded.data,bytes:bytes.length,digest,
          disposition:response.headers.get("Content-Disposition")};
      },format);
      expect(proof.loaded).toEqual(proof.created);expect(proof.bytes).toBe(proof.created.bytes);
      expect(proof.digest).toBe(proof.created.sha256);
      expect(proof.disposition).toContain(`${proof.created.exportId}.${format}`);
    }
  }finally{await monitor.stop();} // stop asserts the external export temp root was removed
});
```

- [ ] **Step 2: Run RED.** From `tools/stm32-monitor/ui`, set the three environment variables to absolute current-worktree/external-evidence values and run `& $npx playwright test e2e/monitor.spec.ts --project=chromium-1280 --grep "fixture serves"`. Expected: FAIL because `startMonitor` is absent.

- [ ] **Step 3: Implement the tested child/control contract without a browser-side fake.** Add the following ownership and message loop. `ScenarioRuntime.dispatch()` must implement every existing operation used in Task 2 with the exact 0501 public data shapes; `live_subscribe()` yields only queued existing event-union dictionaries. The shown start/control/stop code is mandatory and is not replaced by an HTTP control route.

```python
# e2e/fake_runtime.py
from __future__ import annotations
import asyncio, hashlib, hmac, json, pathlib, platform, sys, tempfile
from collections import deque
from collections.abc import AsyncIterator, Mapping
from uuid import UUID
from stm32_monitor.exports import ExportArtifact, ExportDownload, ExportDownloadResult
from stm32_monitor.models import unix_ns_to_utc
from stm32_monitor.protocol import (MONITOR_PROTOCOL_VERSION,MONITOR_VERSION,
  TOOLKIT_VERSION,ProtocolResult,failure,success)
from stm32_monitor.service import MonitorService

def binding_document(workspace: str) -> dict[str, object]:
    return {"workspaceId":workspace,"logicalProjectId":"00000000-0000-4000-8000-000000000003","sessionId":"e2e-session",
      "probeId":"probe-a","targetDevice":"STM32F407VGTx","physicalTarget":"stm32f407vg",
      "buildId":"b"*64,"elfSha256":"e"*64,"inputSnapshotSha256":"f"*64,
      "gitHead":"c"*40,"gitDirty":False,"flashSessionId":"flash-a","leaseId":"lease-a",
      "dwarfSha256":"d"*64,"svdSha256":"a"*64}

def status_document(runtime: "ScenarioRuntime") -> dict[str, object]:
    sampling={"state":runtime.sampling_state,"active":runtime.sampling_state=="RUNNING",
      "blockedCode":runtime.blocked_code,"groupId":runtime.active_group,
      "groupRevision":runtime.active_revision,"runId":runtime.run_id,"lastSequence":runtime.sequence,
      "bindingEpoch":runtime.binding_epoch,"subscriberDrops":runtime.drops["subscriber"],
      "historyDrops":runtime.drops["history"],"deadlineDrops":runtime.drops["deadline"],
      "serviceDrops":runtime.drops["service"]}
    return {"workspaceId":runtime.workspace,"sessionId":"e2e-session",
      "project":{"logicalProjectId":"00000000-0000-4000-8000-000000000003","name":"E2E Project","targetDevice":"STM32F407VGTx"},
      "firmware":{"buildId":"b"*64,"elfSha256":"e"*64,"inputSnapshotSha256":"f"*64,
        "gitHead":"c"*40,"gitDirty":False,"targetDevice":"STM32F407VGTx"},
      "probe":{"connected":runtime.connected,"probeId":"probe-a" if runtime.connected else None},
      "sampling":sampling,"probeConnected":runtime.connected,
      "samplingActive":sampling["active"]}

def catalog_page(operation: str, query: dict[str, str]) -> dict[str, object]:
    if operation == "monitor.catalog.variables":
        items=[{"selector":"rpm","typeName":"float","kind":"scalar","byteSize":4,
          "signed":True,"encoding":None,"qualifiers":[],"aliases":[],"enumValues":[],
          "elementCount":None,"elementKind":None,"memberNames":[]},
          {"selector":"samples","typeName":"uint16_t[256]","kind":"array","byteSize":512,
          "signed":False,"encoding":None,"qualifiers":[],"aliases":[],"enumValues":[],
          "elementCount":256,"elementKind":"uint16_t","memberNames":[]}]
    else:
        items=[{"selector":"TIM2.CNT","sizeBits":32,"access":"read-write","readAction":None,
          "resetValue":0,"resetMask":4294967295,"fields":[],"sampleable":True,
          "requiresAccessAcknowledgement":False}]
    return {"items":items,"nextCursor":None if query.get("cursor") else "catalog-page-2"}

def group_page(runtime: "ScenarioRuntime", query: dict[str, str]) -> dict[str, object]:
    start=1 if query.get("cursor")=="groups-page-2" else 0
    revision=hashlib.sha256(json.dumps(runtime.groups,sort_keys=True,separators=(",",":"))
      .encode("utf-8")).hexdigest()
    return {"groups":runtime.groups[start:start+1],
      "nextCursor":"groups-page-2" if start==0 and len(runtime.groups)>1 else None,
      "revision":revision}

def make_group(runtime: "ScenarioRuntime", body: dict[str, object]) -> dict[str, object]:
    runtime.group_revision+=1
    return {"groupId":str(UUID(int=100+runtime.group_revision)),"name":str(body["name"]),
      "description":str(body.get("description","")),"intervalMs":int(body["intervalMs"]),
      "items":list(body.get("items",[])),"revision":runtime.group_revision,
      "createdAtUtc":"2026-08-10T00:00:00.000000Z",
      "updatedAtUtc":"2026-08-10T00:00:00.000000Z"}

def mutate_groups(runtime: "ScenarioRuntime", operation: str, resource_id: str | None,
                  payload: dict[str, object]) -> object:
    if operation == "monitor.groups.create":
        group=make_group(runtime,payload);runtime.groups.append(group);return group
    if operation == "monitor.groups.import":
        imported=[make_group(runtime,v) for v in payload["document"]["groups"]]  # type: ignore[index]
        runtime.groups.extend(imported);return imported
    index=next(i for i,v in enumerate(runtime.groups) if v["groupId"]==resource_id)
    if operation == "monitor.groups.delete":
        runtime.groups.pop(index);return {"groupId":resource_id,"deleted":True}
    current=dict(runtime.groups[index]);runtime.group_revision+=1
    for key in ("name","description","intervalMs","items"):
        if key in payload: current[key]=payload[key]
    current["revision"]=runtime.group_revision
    current["updatedAtUtc"]="2026-08-10T00:00:01.000000Z"
    runtime.groups[index]=current;return current

def probe_result(runtime: "ScenarioRuntime", operation: str, payload: dict[str, object]) -> object:
    if operation == "monitor.probe.release":
        runtime.connected=False;return {"released":True}
    runtime.connected=True
    if operation == "monitor.probe.reconnect": runtime.binding_epoch+=1
    return binding_document(runtime.workspace)

async def sampling_result(runtime: "ScenarioRuntime", operation: str,
                          payload: dict[str, object]) -> dict[str, object]:
    action=operation.rsplit(".",1)[-1]
    if action=="start":
        runtime.sampling_state="RUNNING";runtime.active_group=str(payload["groupId"])
        runtime.active_revision=int(payload["expectedRevision"]);runtime.run_id=runtime.seed_run_id
        return {"groupId":runtime.active_group,"groupRevision":runtime.active_revision,
          "runId":runtime.run_id,"intervalMs":runtime.groups[0]["intervalMs"]}
    runtime.sampling_state={"pause":"PAUSED","resume":"RUNNING","stop":"IDLE"}[action]
    if action=="stop": await runtime.stop_producer()
    return {"pause":{"paused":True},"resume":{"resumed":True},
      "stop":{"stopped":True}}[action]

def history_page(runtime: "ScenarioRuntime", query: dict[str, str]) -> dict[str, object]:
    start=1 if query.get("cursor")=="history-page-2" else 0
    batches=[dict(batch,startOrdinal=0,batchValueCount=len(batch["values"]))
      for batch in runtime.history_batches[start:start+1]]
    return {"batches":batches,"valueCount":sum(len(v["values"]) for v in batches),
      "nextCursor":"history-page-2" if start==0 and len(runtime.history_batches)>1 else None,
      "serializedBytes":len(json.dumps(batches,separators=(",",":"),ensure_ascii=False).encode())}

def sample_batch(runtime: "ScenarioRuntime") -> dict[str, object]:
    sequence=runtime.sequence+1
    captured=1_800_000_000_000_000_000+sequence*100_000_000
    values=[{"watch":{"kind":"variable","expression":f"row_{index:03d}"},
      "status":"OK","typedValue":{"expression":f"row_{index:03d}",
        "typeName":"uint32_t","value":sequence+index,
        "rawHex":f"0x{(sequence+index)&0xffffffff:08x}","bitWidth":32},"code":None,
      "definition":None} for index in range(256)]
    return {"binding":binding_document(runtime.workspace),"groupId":runtime.group_id,
      "groupRevision":1,"runId":runtime.seed_run_id,"sequence":sequence,
      "scheduledUnixNs":captured,"scheduledAtUtc":unix_ns_to_utc(captured),
      "capturedUnixNs":captured,"capturedAtUtc":unix_ns_to_utc(captured),
      "latencyNs":0,"actualRateHz":10.0,"subscriberDrops":runtime.drops["subscriber"],
      "historyDrops":runtime.drops["history"],"deadlineDrops":runtime.drops["deadline"],
      "values":values}

def export_result(runtime: "ScenarioRuntime", operation: str, resource_id: str | None,
                  payload: dict[str, object]) -> object:
    if operation == "monitor.exports.create":
        format_name=str(payload["format"]);export_id=UUID(int=len(runtime.artifacts)+1)
        body=(b"sequence,selector,value\n1,row_000,1.0\n" if format_name=="csv" else
          b'{"sequence":1,"selector":"row_000","value":1.0}\n')
        if len(body)>4096: raise AssertionError("fake export exceeded bound")
        directory=runtime.export_root/str(export_id);directory.mkdir()
        data_path=directory/f"history.{format_name}";data_path.write_bytes(body)
        manifest_path=directory/"manifest.json";created="2026-08-10T00:00:00.000000Z"
        digest=hashlib.sha256(body).hexdigest()
        manifest={"protocol":MONITOR_PROTOCOL_VERSION,"toolkitVersion":TOOLKIT_VERSION,
          "monitorVersion":MONITOR_VERSION,"workspaceId":runtime.workspace,
          "sessionId":"e2e-session","exportId":str(export_id),"format":format_name,
          "sha256":digest,"bytes":len(body),"valueCount":1,"createdAtUtc":created}
        manifest_path.write_bytes(json.dumps(manifest,sort_keys=True,separators=(",",":"),
          allow_nan=False).encode("utf-8")+b"\n")
        artifact=ExportArtifact(export_id,directory,data_path,manifest_path,digest,len(body),1)
        runtime.artifacts[export_id]=artifact;return artifact
    export_id=UUID(str(resource_id));artifact=runtime.artifacts[export_id]
    document=json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
    expected={"protocol":MONITOR_PROTOCOL_VERSION,"toolkitVersion":TOOLKIT_VERSION,
      "monitorVersion":MONITOR_VERSION,"workspaceId":runtime.workspace,
      "sessionId":"e2e-session","exportId":str(export_id),
      "format":artifact.data_path.suffix[1:],"sha256":artifact.sha256,
      "bytes":artifact.byte_count,"valueCount":artifact.value_count,
      "createdAtUtc":"2026-08-10T00:00:00.000000Z"}
    body=artifact.data_path.read_bytes()
    if document!=expected or len(body)!=artifact.byte_count or hashlib.sha256(body).hexdigest()!=artifact.sha256:
        raise ValueError("fake export artifact changed")
    if operation == "monitor.exports.get": return artifact
    download=ExportDownload(artifact.data_path.open("rb"),export_id=export_id,
      format_name=artifact.data_path.suffix[1:],byte_count=artifact.byte_count)
    return ExportDownloadResult(True,"OK","",download)

class ScenarioRuntime:
    def __init__(self, workspace: str, repo: pathlib.Path, evidence_root: pathlib.Path) -> None:
        self.workspace = workspace;self.repo=repo
        self.groups: list[dict[str, object]] = []
        self.journal: deque[dict[str, object]]=deque(maxlen=64)
        self.journal_changed=asyncio.Condition();self.closed=False
        self.drops = {"subscriber":0,"history":0,"deadline":0,"service":0}
        self.seed = {"hz":10,"rows":0,"series":0,"pointsPerSeries":0,"durationMs":0}
        self.connected=False;self.binding_epoch=1;self.sampling_state="IDLE"
        self.blocked_code=None;self.active_group=None;self.active_revision=None
        self.run_id=None;self.sequence=0;self.group_revision=0
        self.group_id="00000000-0000-4000-8000-000000000001"
        self.seed_run_id="00000000-0000-4000-8000-000000000002"
        self.seed_task: asyncio.Task[None] | None=None;self.next_failures: dict[str,str]={}
        self.export_temp=tempfile.TemporaryDirectory(prefix="stm32tk-0502-e2e-",dir=evidence_root)
        self.export_root=pathlib.Path(self.export_temp.name)
        self.artifacts: dict[UUID,ExportArtifact]={};self.history_batches: list[dict[str,object]]=[]

    async def configure_seed(self, value: dict[str, object]) -> None:
        expected={"hz":10,"rows":256,"series":8,"pointsPerSeries":600}
        if {key:value.get(key) for key in expected}!=expected:
            raise AssertionError("invalid deterministic seed dimensions")
        duration=int(value["durationMs"])
        if duration<1000 or duration>300000: raise AssertionError("invalid seed duration")
        if self.seed_task is not None: raise AssertionError("producer already running")
        self.seed=dict(value)

    async def publish(self, event: dict[str, object]) -> None:
        event_id=event.get("eventId")
        if type(event_id) is not int or event_id<=self.sequence: raise AssertionError("event ID is not monotonic")
        self.sequence=event_id
        async with self.journal_changed:
            self.journal.append(event);self.journal_changed.notify_all()

    def event(self, kind: str, data: dict[str, object]) -> dict[str, object]:
        return {"eventId":self.sequence+1,"type":kind,"data":data}

    async def start_producer(self) -> None:
        if self.seed["rows"]!=256 or self.seed_task is not None: raise AssertionError("seed is not configured")
        self.seed_task=asyncio.create_task(self._emit_seed(int(self.seed["durationMs"])))

    async def _emit_seed(self, duration_ms: int) -> None:
        loop=asyncio.get_running_loop();started=loop.time()
        tick=0
        while tick<duration_ms//100:
            if self.sampling_state=="PAUSED": await asyncio.sleep(.01);continue
            if self.sampling_state!="RUNNING": return
            batch=sample_batch(self);event_id=int(batch["sequence"])
            self.history_batches.append(batch)
            if len(self.history_batches)>600: del self.history_batches[0]
            await self.publish({"eventId":event_id,"type":"sample","data":{
              "batch":batch,"serviceSubscriberDrops":self.drops["service"]}})
            tick+=1
            await asyncio.sleep(max(0,started+tick/10-loop.time()))

    async def stop_producer(self) -> None:
        task=self.seed_task;self.seed_task=None
        if task is not None:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass

    async def close(self) -> None:
        await self.stop_producer()
        async with self.journal_changed:
            self.closed=True;self.journal_changed.notify_all()
        self.export_temp.cleanup()

    async def dispatch(self, operation: str, payload: dict[str, object], *,
                       resource_id: str | None = None,
                       query: dict[str, str] | None = None) -> object:
        query = dict(query or {})
        injected=self.next_failures.pop(operation,None)
        if injected is not None:
            return failure(operation,injected,"A probe lifecycle transition is already in progress")
        if operation == "monitor.status":
            return success(operation,status_document(self))
        if operation == "monitor.probes.list":
            return success(operation,{"probes":[{"probeId":"probe-a","vendor":"OpenAI",
                               "product":"Fake STM32 Probe","boardName":"Fake Board"}]})
        if operation.startswith("monitor.catalog."):
            return success(operation,catalog_page(operation, query))
        if operation == "monitor.groups.list":
            return success(operation,group_page(self, query))
        if operation in {"monitor.groups.create","monitor.groups.update",
                         "monitor.groups.delete","monitor.groups.import"}:
            return success(operation,mutate_groups(self, operation, resource_id, payload))
        if operation in {"monitor.probe.connect","monitor.probe.reconnect",
                         "monitor.probe.release"}:
            return success(operation,probe_result(self, operation, payload))
        if operation.startswith("monitor.sampling."):
            result=await sampling_result(self, operation, payload)
            await self.publish(self.event("state",{"stateRevision":self.sequence+1,
              "gap":False,"status":status_document(self)}))
            if operation=="monitor.sampling.start": await self.start_producer()
            return success(operation,result)
        if operation == "monitor.history.query":
            return success(operation,history_page(self, query))
        if operation.startswith("monitor.exports."):
            result=export_result(self, operation, resource_id, payload)
            return result if operation=="monitor.exports.download" else success(operation,result)
        raise AssertionError(f"unexpected existing operation: {operation}")

    async def live_subscribe(self, *, after_event_id: int | None = None
                             ) -> AsyncIterator[dict[str, object]]:
        if after_event_id is None:
            hello=self.event("hello",{"protocol":MONITOR_PROTOCOL_VERSION,
              "toolkitVersion":TOOLKIT_VERSION,"monitorVersion":MONITOR_VERSION,
              "stateRevision":self.sequence})
            await self.publish(hello);cursor=int(hello["eventId"])-1
        else:cursor=after_event_id
        async with self.journal_changed:
            oldest=int(self.journal[0]["eventId"]) if self.journal else self.sequence+1
        if after_event_id is not None and after_event_id<oldest-1:
            gap=self.event("state",{"stateRevision":self.sequence+1,"gap":True,
              "status":status_document(self)})
            await self.publish(gap);cursor=int(gap["eventId"])-1
        while True:
            async with self.journal_changed:
                available=[event for event in self.journal if int(event["eventId"])>cursor]
                while not available and not self.closed:
                    await self.journal_changed.wait()
                    available=[event for event in self.journal if int(event["eventId"])>cursor]
                if not available and self.closed:return
            for event in available:
                cursor=int(event["eventId"]);yield dict(event)

    def record_service_drops(self, count: int) -> None:
        self.drops["service"] += count

async def apply_control(runtime: ScenarioRuntime, method: str, value: object) -> object:
    if method=="seed":
        assert isinstance(value,dict);await runtime.configure_seed(value);return {"seeded":True}
    if method in {"emitState","emitSample"}:
        assert isinstance(value,dict);await runtime.publish(dict(value));return {"emitted":True}
    if method=="emitGap":
        await runtime.publish(runtime.event("state",{"stateRevision":runtime.sequence+1,
          "gap":True,"status":status_document(runtime)}))
        return {"emitted":True}
    if method=="emitHeartbeat":
        await runtime.publish(runtime.event("heartbeat",{"stateRevision":runtime.sequence+1,
          "capturedAtUtc":"2026-08-10T00:00:00.000000Z"}))
        return {"emitted":True}
    if method=="failNext":
        assert isinstance(value,dict) and set(value)=={"operation","code"}
        operation=str(value["operation"]);code=str(value["code"])
        if operation not in {"monitor.probe.connect","monitor.probe.reconnect",
          "monitor.sampling.start","monitor.sampling.resume"} or code!="MONITOR_PROBE_BUSY":
            raise AssertionError("invalid injected failure")
        runtime.next_failures[operation]=code;return {"armed":True}
    if method=="setLeaseLost":
        runtime.sampling_state="PAUSED_BLOCKED";runtime.blocked_code="PROBE_LEASE_LOST"
        await runtime.stop_producer()
        await runtime.publish(runtime.event("state",{"stateRevision":runtime.sequence+1,
          "gap":False,"status":status_document(runtime)}));return {"blocked":True}
    if method=="dropTotals": return dict(runtime.drops)
    if method=="environment":
        assets=runtime.repo/"tools"/"stm32-monitor"/"src"/"stm32_monitor"/"ui_dist"
        manifest_path=assets/".vite"/"manifest.json";manifest=json.loads(manifest_path.read_text("utf-8"))
        declared={"index.html",".vite/manifest.json"}
        for entry in manifest.values():
            if not isinstance(entry,Mapping):raise AssertionError("invalid Vite manifest entry")
            for name in ([entry.get("file")]+list(entry.get("css",[]))+list(entry.get("assets",[]))):
                if isinstance(name,str):declared.add(name.replace("\\","/"))
        actual={item.relative_to(assets).as_posix() for item in assets.rglob("*") if item.is_file()}
        if actual!=declared:raise AssertionError("package UI asset manifest/inventory mismatch")
        asset_bytes=sum((assets/name).stat().st_size for name in sorted(declared))
        if asset_bytes<=0 or asset_bytes>8*1024*1024:raise AssertionError("production asset bytes invalid")
        return {"cpu":platform.processor() or platform.machine(),"assetBytes":asset_bytes}
    raise AssertionError(f"unknown control method: {method}")

async def main() -> None:
    repo = pathlib.Path(sys.argv[1]).resolve(strict=True)
    workspace = sys.argv[2]
    evidence_root=pathlib.Path(sys.argv[3]).resolve(strict=True)
    startup = json.loads(sys.stdin.readline())
    test_token = str(startup.pop("testToken"))
    expected_token=hashlib.sha256(
      f"stm32tk-0502-e2e-non-secret:{workspace}".encode("utf-8")).hexdigest()
    if startup or not hmac.compare_digest(test_token,expected_token):
        raise ValueError("invalid test startup")
    token_bytes=bytes.fromhex(test_token)
    test_token="";expected_token=""
    runtime: ScenarioRuntime | None = None
    service: MonitorService | None = None
    try:
        runtime = ScenarioRuntime(workspace,repo,evidence_root)
        service = MonitorService(runtime, workspace_id=workspace,
          session_id="e2e-session",token_factory=lambda:token_bytes)
        endpoint = await service.start()
        print(json.dumps({"ready":True,"url":endpoint.url,"accessUrl":endpoint.access_url,
          "monitorFile":str(pathlib.Path(__import__("stm32_monitor").__file__).resolve()),
          "toolkitFile":str(pathlib.Path(__import__("stm32_toolkit").__file__).resolve()),
          "exportTempRoot":str(runtime.export_root)}),flush=True)
        loop = asyncio.get_running_loop()
        while True:
            raw = await loop.run_in_executor(None, sys.stdin.readline)
            if raw == "":
                break
            request = json.loads(raw)
            if request["method"] == "stop":
                print(json.dumps({"id":request["id"],"ok":True}), flush=True)
                break
            result = await apply_control(runtime, request["method"], request.get("input"))
            print(json.dumps({"id":request["id"],"ok":True,"result":result}), flush=True)
    finally:
        if service is not None: await service.stop()
        if runtime is not None: await runtime.close()

if __name__ == "__main__":
    asyncio.run(main())
```

```ts
// e2e/conftest.ts
import {createHash} from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import {spawn,type ChildProcessWithoutNullStreams} from "node:child_process";
import {test as base,expect,type Page} from "@playwright/test";

export const sha256Hex=(value:string):string =>
  createHash("sha256").update(value,"utf8").digest("hex");
export const testTokenForWorkspace=(workspace:string):string=>
  sha256Hex(`stm32tk-0502-e2e-non-secret:${workspace}`);
export const workspaceForTest=(testInfo:{workerIndex:number;title:string}):string=>
  `workspace-${testInfo.workerIndex}-${sha256Hex(testInfo.title).slice(0,12)}`;
export interface MonitorBrowserFixture {
  readonly url:string;
  navigate(page:Page):Promise<void>;
  seed(input:SeedInput):Promise<void>;
  emitState(input:StateEvent):Promise<void>;
  emitSample(input:SampleEvent):Promise<void>;
  emitGap():Promise<void>;
  emitHeartbeat():Promise<void>;
  failNext(input:{operation:"monitor.probe.connect"|"monitor.probe.reconnect"|
    "monitor.sampling.start"|"monitor.sampling.resume";
    code:"MONITOR_PROBE_BUSY"}):Promise<void>;
  setLeaseLost():Promise<void>;
  dropTotals():Promise<DropTotals>;
  environment(page:Page):Promise<PerformanceEnvironment>;
  stop():Promise<void>;
}
const requireAbsolute=(name:string,kind:"file"|"directory"):string=>{
  const raw=process.env[name];if(raw===undefined||!path.isAbsolute(raw))throw new Error(`${name} must be absolute`);
  const resolved=fs.realpathSync(raw);const stat=fs.statSync(resolved);
  if((kind==="file"&&!stat.isFile())||(kind==="directory"&&!stat.isDirectory()))
    throw new Error(`${name} has wrong type`);
  return resolved;
};
const requireDescendant=(candidate:string,root:string,label:string):void=>{
  const relative=path.relative(fs.realpathSync(root),fs.realpathSync(candidate));
  if(relative.startsWith("..")||path.isAbsolute(relative))throw new Error(`${label} is not current source`);
};
const waitForExit=async(closed:Promise<number|null>,timeoutMs:number):Promise<void>=>{
  let timer:NodeJS.Timeout|undefined;
  const timeout=new Promise<never>((_,reject)=>{timer=setTimeout(
    ()=>reject(new Error("fixture child exit timeout")),timeoutMs);});
  try{const code=await Promise.race([closed,timeout]);
    if(code!==0)throw new Error(`fixture exit ${code}`);}finally{if(timer!==undefined)clearTimeout(timer);}
};
const terminateAndWait=async(child:ChildProcessWithoutNullStreams,
  closed:Promise<number|null>):Promise<void>=>{
  if(child.exitCode===null){child.stdin.destroy();child.kill();}
  let timer:NodeJS.Timeout|undefined;
  const timeout=new Promise<never>((_,reject)=>{timer=setTimeout(
    ()=>reject(new Error("fixture child termination timeout")),5000);});
  try{await Promise.race([closed,timeout]);}finally{if(timer!==undefined)clearTimeout(timer);}
};

export async function startMonitor(workspace:string,testToken:string):Promise<MonitorBrowserFixture> {
  if(!/^[0-9a-f]{64}$/.test(testToken))throw new Error("test token shape invalid");
  const python = requireAbsolute("STM32_MONITOR_E2E_PYTHON","file");
  const repo = requireAbsolute("STM32_MONITOR_E2E_REPO_ROOT","directory");
  const evidence = requireAbsolute("STM32_MONITOR_E2E_EVIDENCE_ROOT","directory");
  const monitorRoot = path.resolve(repo,"tools/stm32-monitor/src");
  const toolkitRoot = path.resolve(repo,"tools/stm32-toolkit/src");
  const child = spawn(python,[path.join(repo,"tools/stm32-monitor/ui/e2e/fake_runtime.py"),repo,workspace,evidence],{
    cwd:repo, stdio:["pipe","pipe","pipe"], windowsHide:true,
    env:{...process.env,PYTHONPATH:`${monitorRoot};${toolkitRoot}`,PYTHONDONTWRITEBYTECODE:"1"}
  });
  const childClosed=new Promise<number|null>(resolve=>child.once("close",resolve));
  const childFailure=new Promise<never>((_,reject)=>child.once("error",()=>reject(
    new Error("fixture child failed to start"))));
  child.stderr.resume(); // never log child stderr because it can contain paths or secrets
  const lines=readline.createInterface({input:child.stdout,crlfDelay:Infinity})[Symbol.asyncIterator]();
  const nextJson=async():Promise<Record<string,unknown>>=>{
    const line=await lines.next();if(line.done)throw new Error("fixture stdout closed");
    return JSON.parse(line.value) as Record<string,unknown>;
  };
  type Ready={url:string;accessUrl?:string;monitorFile:string;toolkitFile:string;exportTempRoot:string};
  let ready:Ready;
  try{
    child.stdin.write(JSON.stringify({testToken})+"\n");testToken="";
    ready=await Promise.race([nextJson() as Promise<Ready>,childFailure]);
    requireDescendant(ready.monitorFile,monitorRoot,"stm32_monitor");
    requireDescendant(ready.toolkitFile,toolkitRoot,"stm32_toolkit");
    requireDescendant(ready.exportTempRoot,evidence,"export temp root");
  }catch(error){testToken="";await terminateAndWait(child,childClosed);throw error;}
  let privateAccessUrl=ready.accessUrl??null;delete ready.accessUrl;
  let requestId=0;let serial:Promise<unknown>=Promise.resolve();
  const rpc=<T>(method:string,input?:unknown):Promise<T>=>{
    const operation=serial.then(async()=>{
      const id=++requestId;child.stdin.write(JSON.stringify({id,method,input})+"\n");
      const response=await nextJson();
      if(response.id!==id||response.ok!==true)throw new Error(`fixture RPC failed: ${method}`);
      return response.result as T;
    });
    serial=operation.then(()=>undefined,()=>undefined);return operation;
  };
  let stopped = false;
  return {
    url:ready.url,
    navigate:async(page:Page)=>{
      if(privateAccessUrl===null)throw new Error("fixture access URL already consumed");
      let oneShot=privateAccessUrl;privateAccessUrl=null;
      try{await page.goto(oneShot);await page.waitForURL(ready.url+"/");}
      finally{oneShot="";}
    },
    seed:input => rpc<void>("seed",input), emitState:input => rpc<void>("emitState",input),
    emitSample:input => rpc<void>("emitSample",input), emitGap:() => rpc<void>("emitGap"),
    emitHeartbeat:() => rpc<void>("emitHeartbeat"),failNext:input=>rpc<void>("failNext",input),
    setLeaseLost:()=>rpc<void>("setLeaseLost"),
    dropTotals:() => rpc<DropTotals>("dropTotals"),
    environment:async(page:Page)=>{
      const base=await rpc<{cpu:string;assetBytes:number}>("environment");
      const viewport=page.viewportSize();
      if(viewport?.width!==1280||viewport.height!==720)throw new Error("performance viewport mismatch");
      return {...base,node:process.version,chromium:page.context().browser()?.version()??"unknown",
        viewport:"1280x720"};
    },
    stop:async () => { if (stopped) return; stopped=true;
      try{await rpc("stop");await waitForExit(childClosed,5000);}
      catch(error){await terminateAndWait(child,childClosed);throw error;}
      if(fs.existsSync(ready.exportTempRoot))throw new Error("fake export temp root survived stop"); }
  };
}

export const test=base.extend<{monitor:MonitorBrowserFixture}>({
  monitor:async({},use,testInfo)=>{
    const workspace=workspaceForTest(testInfo);
    const monitor=await startMonitor(workspace,testTokenForWorkspace(workspace));
    try{await use(monitor);}finally{await monitor.stop();}
  }
});
export {expect};
```

The same unit modifies the existing TypeScript Playwright config and package scripts exactly; Firefox/WebKit remain configured for the named Linux owner, while Windows commands select both exact Chromium viewports and the performance command selects only 1280×720:

```ts
// playwright.config.ts
import path from "node:path";
import {defineConfig,devices} from "@playwright/test";
const outputDir=process.env.STM32_MONITOR_E2E_EVIDENCE_ROOT;
if(outputDir===undefined||!path.isAbsolute(outputDir))throw new Error("absolute E2E evidence root required");
export default defineConfig({testDir:"./e2e",outputDir:path.join(outputDir,"playwright","results"),
  workers:1,fullyParallel:false,use:{offline:true,trace:"retain-on-failure",video:"retain-on-failure"},projects:[
    {name:"chromium-1280",use:{...devices["Desktop Chrome"],viewport:{width:1280,height:720}}},
    {name:"chromium-1024",use:{...devices["Desktop Chrome"],viewport:{width:1024,height:768}}},
    {name:"firefox-linux-deferred",use:{...devices["Desktop Firefox"]}},
    {name:"webkit-linux-deferred",use:{...devices["Desktop Safari"]}}]});
```

```json
{"scripts":{"test:e2e":"playwright test --config=playwright.config.ts",
"test:e2e:windows":"playwright test --project=chromium-1280 --project=chromium-1024",
"test:e2e:performance":"playwright test e2e/performance.spec.ts --project=chromium-1280 --grep five-minute"}}
```

- [ ] **Step 4: Run GREEN.** Repeat Step 2, then run the installed-copy/path-space/teardown cases. Expected: PASS; readiness proves both current source roots, each control RPC receives one response, and no orphan process/listener remains.

- [ ] **Step 5: Commit the fixture unit.** Add exactly the five files listed for Task 1—`fake_runtime.py`, `conftest.ts`, `monitor.spec.ts`, `playwright.config.ts`, and `package.json`—and commit `test(STM32TK-0502): add real monitor browser fixture`. Do not name `CODE_HEAD`.

## Task 2: Product, Auth, Offline, Security, and Two-Workspace Browser Acceptance

**Files:**

- Modify: `tools/stm32-monitor/ui/e2e/monitor.spec.ts`, `fake_runtime.py`, `conftest.ts`
- Create: `tools/stm32-monitor/ui/e2e/security.spec.ts`, `isolation.spec.ts`
- Modify only when a failing browser test exposes missing product wiring: `tools/stm32-monitor/ui/src/**`

### Task 2A: Explicit product workflow over real REST/WebSocket

- [ ] **Step 1: Write the failing workflow and discontinuity tests.** Use this exact rendered-action spine, then add independent cases for replay success, expired `gap:true`, 35-second heartbeat stale, binding/run reset, one item `ERROR` with sibling success, all four drop totals, public-code failures, and BUSY/LEASE_LOST without steal/force/auto-resume.

```ts
test("explicit end-to-end monitor workflow", async ({page}) => {
  const workspace="workspace-product";
  const monitor = await startMonitor(workspace,testTokenForWorkspace(workspace));
  try {
    await monitor.navigate(page);
    await expect(page.getByText("No user monitor groups")).toBeVisible();
    await page.getByRole("button",{name:"Connect Fake STM32 Probe"}).click();
    await page.getByLabel("Variable or register search").fill("samples");
    await page.getByRole("button",{name:"Next catalog page"}).click();
    await createEditRenameExportAndImportGroup(page);
    for (const interval of [100,250,5000]) await runSamplingLifecycle(page,interval);
    await expect(page.getByRole("row")).toHaveCount(257);
    await selectEightSeriesAndAssertSixHundredPoints(page);
    await exercisePointerTouchAndKeyboardZoom(page);
    await page.getByRole("button",{name:"Load history"}).click();
    await page.getByRole("button",{name:"Next history page"}).click();
    await page.getByRole("button",{name:"Previous history page"}).click();
    await createAndDownloadVerifiedExport(page,"csv");
    await createAndDownloadVerifiedExport(page,"jsonl");
    await page.getByRole("button",{name:"Delete renamed-group"}).click();
    await page.getByRole("button",{name:"Confirm delete"}).click();
  } finally { await monitor.stop(); }
});

async function createEditRenameExportAndImportGroup(page:Page):Promise<void>{
  const watches=page.getByRole("checkbox",{name:/Add row_/});
  await expect(watches).toHaveCount(256);
  for(let index=0;index<256;index++)await watches.nth(index).check();
  await page.getByRole("button",{name:"Create group"}).click();
  await page.getByLabel("Group name").fill("user-group");
  await page.getByLabel("Sampling interval (ms)").fill("250");
  await page.getByRole("button",{name:"Confirm create"}).click();
  await page.getByRole("button",{name:"Edit user-group"}).click();
  await page.getByLabel("Group name").fill("renamed-group");
  await page.getByRole("button",{name:"Save group"}).click();
  const groupDownload=page.waitForEvent("download");
  await page.getByRole("button",{name:"Export user groups"}).click();
  const transfer=await groupDownload,stream=await transfer.createReadStream();
  const chunks:Buffer[]=[];for await(const chunk of stream)chunks.push(Buffer.from(chunk));
  await page.getByRole("button",{name:"Delete renamed-group"}).click();
  await page.getByRole("button",{name:"Confirm delete"}).click();
  await page.getByLabel("Import user groups file").setInputFiles({
    name:"groups.json",mimeType:"application/json",buffer:Buffer.concat(chunks)});
  await page.getByRole("button",{name:"Import user groups"}).click();
  await page.getByRole("button",{name:"Confirm import"}).click();
  await expect(page.getByText("renamed-group")).toBeVisible();
}
async function runSamplingLifecycle(page:Page,interval:number):Promise<void>{
  await page.getByLabel("Sampling interval (ms)").fill(String(interval));
  for(const action of ["Start sampling","Pause sampling","Resume sampling","Stop sampling"])
    await page.getByRole("button",{name:action}).click();
}
async function selectEightSeriesAndAssertSixHundredPoints(page:Page):Promise<void>{
  const choices=page.getByRole("checkbox",{name:/Plot /});
  for(let index=0;index<8;index++)await choices.nth(index).check();
  await expect(page.getByLabel("Live chart")).toHaveAttribute("data-series-count","8");
  await expect(page.getByLabel("Live chart")).toHaveAttribute("data-max-points","600");
}
async function exercisePointerTouchAndKeyboardZoom(page:Page):Promise<void>{
  const chart=page.getByLabel("Live chart");await chart.hover();
  await page.mouse.wheel(0,-120);await page.keyboard.press("+");await page.keyboard.press("-");
  await page.keyboard.press("0");await expect(page.getByText("0–100%")).toBeVisible();
}
async function createAndDownloadVerifiedExport(page:Page,format:"csv"|"jsonl"):Promise<void>{
  await page.getByLabel("Export format").selectOption(format);
  await page.getByRole("button",{name:"Create verified export"}).click();
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Download verified export"}).click();await download;
}

test("journal replays retained events and reports expired continuity",async({page,context})=>{
  const workspace="workspace-replay",monitor=await startMonitor(workspace,testTokenForWorkspace(workspace));
  await monitor.navigate(page);await monitor.emitHeartbeat();
  const retained=await page.getByTestId("last-event-id").getAttribute("data-event-id");
  await context.setOffline(true);await monitor.emitHeartbeat();await context.setOffline(false);
  await expect(page.getByTestId("last-event-id")).not.toHaveAttribute("data-event-id",retained!);
  await context.setOffline(true);for(let index=0;index<65;index++)await monitor.emitHeartbeat();
  await context.setOffline(false);await expect(page.getByText("Live event gap; status refresh required")).toBeVisible();
  await monitor.stop();
});

test("busy and lease-lost remain explicit and never steal or resume",async({page})=>{
  const workspace="workspace-conflict",monitor=await startMonitor(workspace,testTokenForWorkspace(workspace));
  await monitor.navigate(page);
  await monitor.failNext({operation:"monitor.probe.connect",code:"MONITOR_PROBE_BUSY"});
  await page.getByRole("button",{name:"Connect Fake STM32 Probe"}).click();
  await expect(page.getByText("MONITOR_PROBE_BUSY")).toBeVisible();
  await expect(page.getByRole("button",{name:/steal|force/i})).toHaveCount(0);
  await monitor.setLeaseLost();await expect(page.getByText("PROBE_LEASE_LOST")).toBeVisible();
  await expect(page.getByText("Sampling: running")).toHaveCount(0);await monitor.stop();
});
```

- [ ] **Step 2: Run RED.** Run `& $npx playwright test e2e/monitor.spec.ts --project=chromium-1280 --project=chromium-1024 --grep "explicit end-to-end|replay|gap|heartbeat|lease"`. Expected: FAIL on the first missing rendered action or authoritative state transition.

- [ ] **Step 3: Implement only the exact callback/state wiring exercised by the failing cases.** Preserve the frontend-core `LiveEvent` and reducer rather than creating a second event shape. The fake runtime uses one bounded 64-event journal plus a condition and an independent cursor per subscriber; it never uses a destructive consumer queue. `after_event_id` replays retained events in order; an ID older than `oldest-1` yields a new authoritative `gap:true` state and only subsequent events. Seed config never starts a producer: only successful REST `monitor.sampling.start` starts it, pause/resume governs it, and stop/lease loss cancels and awaits it. State revision/gap/sampling are read only as `event.data.stateRevision`, `event.data.gap`, and `event.data.status.sampling`; sample binding is read only as `event.data.batch.binding`. The following frozen reducer branch is the required behavior; transport recovery uses the existing live client, never probe reconnect/start, and never synthesizes a sample.

```ts
export function applyAuthoritativeEvent(state:MonitorState,event:LiveEvent):MonitorState {
  if(event.type==="state"){
    if(event.data.stateRevision<state.stateRevision)return state;
    const prior=state.status?.sampling;
    const sampling=event.data.status.sampling;
    const changed=prior!==undefined&&
      (prior.bindingEpoch!==sampling.bindingEpoch||prior.runId!==sampling.runId);
    const reset=changed||event.data.gap;
    return {...state,status:event.data.status,stateRevision:event.data.stateRevision,
      lastEventId:event.eventId,live:reset?emptyLive(event.data.status):state.live,
      zoom:reset?{start:0,end:100}:state.zoom,
      transport:{...state.transport,stale:false,needsStatusRefresh:event.data.gap},
      notices:reset?[...state.notices,{kind:"view-reset",text:event.data.gap?
        "Live event gap; status refresh required":"Live view reset for a new binding or run"}]:state.notices};
  }
  if(event.type==="sample"){
    const binding=event.data.batch.binding;
    if(state.status===null||!bindingMatches(state.status,binding))
      return {...state,transport:{...state.transport,stale:true}};
    return acceptSample(state,event);
  }
  return reduceMonitor(state,{type:"live.event",event});
}

export async function recoverLive(lastEventId:number|undefined,client:LiveClient):Promise<WebSocket> {
  return client.connect(lastEventId); // transport replay only; no probe or sampling call
}
```

- [ ] **Step 4: Run GREEN.** Repeat Step 2, then run all of `monitor.spec.ts`. Expected: PASS at 100/250/5000 ms, 256 rows, 8×600, recoverable zoom, exact history cursors and verified CSV/JSONL, with no implicit probe/start action.

- [ ] **Step 5: Commit the product-browser unit.** Add only the product wiring, fixture behavior, and `monitor.spec.ts`; commit `test(STM32TK-0502): cover explicit monitor browser workflows`. Do not name `CODE_HEAD`.

### Task 2B: Fragment/cookie security, offline operation, and two-workspace isolation

- [ ] **Step 1: Write failing security and isolation cases.** Install request/console/page-error capture before `navigate` and use the exact assertions below. Add bad/missing/duplicate token, cookie refresh, Origin/Host/Sec-Fetch-Site allow/deny, CSP/cache/ETag, no source-map/worker/CDN, and a full offline workflow case. Every DOM/storage/console/error/log/screenshot scan searches the exact known token from `testTokenForWorkspace` for that workspace; never use an arbitrary 64-hex regex because firmware/ELF/SHA identities are valid 64-hex data.

```ts
test("scrubs token and accepts no non-current-origin request", async ({page}) => {
  const workspace="workspace-secure",token=testTokenForWorkspace(workspace);
  const monitor = await startMonitor(workspace,token);
  const evidence:EvidenceFact[]=[]; const consoleText:string[]=[];
  await installOriginGuard(page,monitor.url,{record:v=>evidence.push(v)});
  page.on("console",m => consoleText.push(m.text()));
  await monitor.navigate(page);
  await expect(page).toHaveURL(monitor.url + "/");
  const snapshot = await secretSnapshot(page,token);
  expect(snapshot).toEqual({url:false,html:false,local:false,session:false,indexedDb:false,cookie:false});
  expect(consoleText.join("\n")).not.toContain(token);
  expect(evidence.filter(v => v.origin !== new URL(monitor.url).origin)).toEqual([]);
  await monitor.stop();
});

test("isolates two workspaces across every state surface", async ({browser}) => {
  const tokenA=testTokenForWorkspace("workspace-a"),tokenB=testTokenForWorkspace("workspace-b");
  expect(tokenA).not.toBe(tokenB);
  const a=await startMonitor("workspace-a",tokenA);
  const b=await startMonitor("workspace-b",tokenB);
  expect(new URL(a.url).port).not.toBe(new URL(b.url).port);
  const pageA=await browser.newPage(), pageB=await browser.newPage();
  await a.navigate(pageA); await b.navigate(pageB);
  await createNamedGroup(pageA,"only-a");
  await expect(pageB.getByText("only-a")).toHaveCount(0);
  expect(await crossOriginRead(pageA,b.url)).toBe("blocked");
  await assertNoCrossedHistoryLiveOrStorage(pageA,pageB);
  await Promise.all([a.stop(),b.stop(),pageA.close(),pageB.close()]);
});
```

- [ ] **Step 2: Run RED.** Run `& $npx playwright test e2e/security.spec.ts e2e/isolation.spec.ts --project=chromium-1280 --project=chromium-1024`. Expected: FAIL until capture is pre-navigation and all real response/security/isolation paths are exercised.

- [ ] **Step 3: Add exact redacted capture and offline guards.** Use the code below; the route handler aborts only non-current origins and records origin/method/resource type, never headers, bodies, URLs with fragments, or response data.

```ts
export type EvidenceFact={origin:string;method:string;resourceType:string};
export type EvidenceSink={record(value:EvidenceFact):void};
export type SecretSnapshot={url:boolean;html:boolean;local:boolean;session:boolean;
  indexedDb:boolean;cookie:boolean};
export async function installOriginGuard(page:Page,current:string,evidence:EvidenceSink):Promise<void>{
  const origin=new URL(current).origin;
  await page.route("**/*",async route=>{
    const request=route.request(); const actual=new URL(request.url()).origin;
    evidence.record({origin:actual,method:request.method(),resourceType:request.resourceType()});
    if(actual!==origin){ await route.abort("blockedbyclient"); return; }
    await route.continue();
  });
}
export async function secretSnapshot(page:Page,secret:string):Promise<SecretSnapshot>{
  return page.evaluate(async known=>{
    const local=Object.entries(localStorage).flat();const session=Object.entries(sessionStorage).flat();
    const indexedDb=(await indexedDB.databases()).map(v=>v.name??"");
    return {url:location.href.includes(known),html:document.documentElement.outerHTML.includes(known),
      local:local.some(v=>v.includes(known)),session:session.some(v=>v.includes(known)),
      indexedDb:indexedDb.some(v=>v.includes(known)),cookie:document.cookie.includes(known)};
  },secret);
}
export async function createNamedGroup(page:Page,name:string):Promise<void>{
  await page.getByRole("button",{name:"Create group"}).click();
  await page.getByLabel("Group name").fill(name);
  await page.getByLabel("Sampling interval (ms)").fill("250");
  await page.getByRole("button",{name:"Confirm create"}).click();
}
export async function crossOriginRead(page:Page,otherOrigin:string):Promise<"blocked"|"accepted">{
  return page.evaluate(async origin=>{
    try{const response=await fetch(origin+"/api/v1/status",{credentials:"include"});
      return response.ok?"accepted":"blocked";}catch{return "blocked";}
  },otherOrigin);
}
export async function assertNoCrossedHistoryLiveOrStorage(pageA:Page,pageB:Page):Promise<void>{
  await expect(pageA.getByText("workspace-b")).toHaveCount(0);
  await expect(pageB.getByText("workspace-a")).toHaveCount(0);
  for(const page of [pageA,pageB]){
    const persisted=await page.evaluate(async()=>({local:Object.keys(localStorage),
      session:Object.keys(sessionStorage),db:(await indexedDB.databases()).map(v=>v.name??"")}));
    expect(persisted).toEqual({local:[],session:[],db:[]});
  }
}
export function assertEvidenceFileOmitsSecret(file:string,secret:string):void{
  expect(fs.readFileSync(file).includes(Buffer.from(secret,"utf8"))).toBe(false);
}
```

- [ ] **Step 4: Run GREEN with network disabled.** Repeat Step 2, then run `& $npx playwright test e2e/security.spec.ts --project=chromium-1280 --project=chromium-1024 --grep "offline"`. Expected: PASS with zero accepted non-current-origin request, zero cross-workspace state, no token in any asserted surface, and only redacted evidence under the external evidence root.

- [ ] **Step 5: Commit the security/isolation unit.** Add only the two specs and directly required security wiring; commit `test(STM32TK-0502): prove monitor browser isolation`. Do not name `CODE_HEAD`.

## Task 3: Accessibility, Screenshots, and Exact Five-Minute Production Performance

### Task 3A: Component axe and real-browser accessibility screenshots

**Files:**

- Modify/extend existing frontend-core test: `tools/stm32-monitor/ui/tests/a11y.test.tsx`
- Create: `tools/stm32-monitor/ui/e2e/accessibility.spec.ts`
- Modify only on a failing assertion: `tools/stm32-monitor/ui/src/styles.css`, named components

- [ ] **Step 1: Write failing component/browser accessibility cases.** The browser case below is paired with component axe scans of every panel/dialog/error state; add full keyboard order through probe/catalog/group/sampling/history/export/zoom, focus entry/restore/Escape, polite notice, blocking alert, 200% zoom, 1280×720, 1024×768 stacking, text >=4.5:1, visible focus >=3:1, and reduced motion.

```ts
test("keyboard workflow remains operable at real 200 percent browser zoom", async ({page,context},testInfo) => {
  const workspace="workspace-a11y",token=testTokenForWorkspace(workspace);
  const monitor=await startMonitor(workspace,token);
  await monitor.navigate(page);
  const cdp=await context.newCDPSession(page);
  await cdp.send("Emulation.setPageScaleFactor",{pageScaleFactor:2});
  await expect.poll(()=>page.evaluate(()=>visualViewport?.scale)).toBe(2);
  await keyboardOnlyProductWorkflow(page);
  await expect(page.getByRole("button",{name:"Reset chart zoom"})).toBeVisible();
  await page.keyboard.press("0");
  await expect(page.getByText("0–100%")).toBeVisible();
  const screenshot=evidencePath(testInfo,"a11y-200-percent.png");
  await page.screenshot({path:screenshot,fullPage:true});
  assertEvidenceFileOmitsSecret(screenshot,token);
  await cdp.send("Emulation.setPageScaleFactor",{pageScaleFactor:1});await cdp.detach();
  await monitor.stop();
});

async function keyboardOnlyProductWorkflow(page:Page):Promise<void>{
  for(const key of ["Tab","Enter","Tab","Enter","Tab","Enter","Tab","Enter"])
    await page.keyboard.press(key);
  await expect(page.getByRole("button",{name:"Start sampling"})).toBeFocused();
  await page.getByRole("button",{name:"Create group"}).focus();
  await page.keyboard.press("Enter");await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");await expect(page.getByRole("button",{name:"Create group"})).toBeFocused();
}
```

- [ ] **Step 2: Run RED.** Run `& $npm run test:a11y; & $npx playwright test e2e/accessibility.spec.ts --project=chromium-1280 --project=chromium-1024`. Expected: FAIL on the first missing accessible name, focus transition, contrast/layout rule, or evidence-root path guard.

- [ ] **Step 3: Implement only matching semantics and external screenshot routing.** Use this exact evidence path guard and the shown dialog semantics; apply `:focus-visible`, responsive stacking, and reduced-motion CSS without adding theme/mobile/i18n infrastructure.

```ts
export function evidencePath(info:TestInfo,name:string):string {
  const configured=process.env.STM32_MONITOR_E2E_EVIDENCE_ROOT;
  if(configured===undefined||!path.isAbsolute(configured))throw new Error("evidence root must be absolute");
  const root=fs.realpathSync(configured);
  const target=path.resolve(root,"playwright",name);
  if(!target.startsWith(root+path.sep)) throw new Error("evidence path escaped root");
  fs.mkdirSync(path.dirname(target),{recursive:true});
  return target;
}

export type ConfirmDialogProps={label:string;trigger:HTMLElement;
  onConfirm():void;onCancel():void};
export function ConfirmDialog(p:ConfirmDialogProps):JSX.Element {
  const cancel=useRef<HTMLButtonElement>(null);
  useEffect(()=>{cancel.current?.focus();return()=>p.trigger.focus();},[p.trigger]);
  return <div role="dialog" aria-modal="true" aria-label={p.label}
    onKeyDown={e=>{if(e.key==="Escape")p.onCancel();}}>
    <button onClick={p.onConfirm}>Confirm</button>
    <button ref={cancel} onClick={p.onCancel}>Cancel</button>
  </div>;
}
```

- [ ] **Step 4: Run GREEN at both viewports.** Repeat Step 2 with screenshot/video/output configured below the one external evidence root. Expected: axe has no serious/critical violations, the full keyboard flow passes, all controls remain available at 200%, and no screenshot/output enters Git.

- [ ] **Step 5: Commit the accessibility unit.** Add only the component test, browser spec, and directly required semantic/style changes; commit `test(STM32TK-0502): capture monitor accessibility evidence`. Do not name `CODE_HEAD`.

### Task 3B: Five-minute production collector

**Files:**

- Create: `tools/stm32-monitor/ui/e2e/performance.spec.ts`
- Modify: `tools/stm32-monitor/ui/e2e/conftest.ts`, `playwright.config.ts`
- Create: `tools/stm32-monitor/ui/src/performance.ts`
- Modify: the existing frontend-core live-queue/render module that owns sample dequeue and chart commit

**Interface:**

```ts
export type PerformanceEvidence={
  minute2to5:{updateP50Ms:number;updateP95Ms:number;updateMaxMs:number;sampleCount:number;
    longTasksAtLeast200Ms:number;maxPoints:number;
    queueStart:number;queueEnd:number;queueGrowth:number;
    heapStartBytes:number;heapEndBytes:number;heapSlopeMiBPerMin:number;
    serverDropTotalsBefore:DropTotals;serverDropTotalsAfter:DropTotals};
  environment:PerformanceEnvironment;
};
```

- [ ] **Step 1: Write the failing typed five-minute test.** Do not use a type assertion or shorten the wait.

```ts
test("full five-minute production evidence",async({page,monitor},testInfo)=>{
  await page.addInitScript(()=>{window.__STM32_MONITOR_E2E_ACTIVATE__=true;});
  await monitor.navigate(page);
  await monitor.seed({hz:10,rows:256,series:8,pointsPerSeries:600,durationMs:300000});
  await startPerformanceSampling(page); // the control channel configures data only
  const collecting=collectPerformance(page,monitor,300000);
  await selectPerformanceSeries(page);
  const evidence:PerformanceEvidence=await collecting;
  expect(evidence.minute2to5.updateP95Ms).toBeLessThanOrEqual(150);
  expect(evidence.minute2to5.sampleCount).toBeGreaterThan(0);
  expect(evidence.minute2to5.longTasksAtLeast200Ms).toBe(0);
  expect(evidence.minute2to5.maxPoints).toBe(4800);
  expect(evidence.minute2to5.queueGrowth).toBeLessThanOrEqual(0);
  expect(evidence.minute2to5.heapSlopeMiBPerMin).toBeLessThanOrEqual(2);
  expect(evidence.minute2to5.serverDropTotalsAfter)
    .toEqual(evidence.minute2to5.serverDropTotalsBefore);
  expect(evidence.environment.viewport).toBe("1280x720");
  await writeEvidenceJson(testInfo,"performance.json",evidence,
    testTokenForWorkspace(workspaceForTest(testInfo)));
});
async function startPerformanceSampling(page:Page):Promise<void>{
  await page.getByRole("button",{name:"Connect Fake STM32 Probe"}).click();
  await page.getByLabel("Variable or register search").fill("samples");
  await page.getByRole("button",{name:"Expand samples array"}).click();
  const elements=page.getByRole("checkbox",{name:/Add samples\[/});
  await expect(elements).toHaveCount(256);
  for(let index=0;index<256;index++)await elements.nth(index).check();
  await page.getByRole("button",{name:"Create group from selected items"}).click();
  await page.getByLabel("Group name").fill("performance-group");
  await page.getByLabel("Sampling interval (ms)").fill("100");
  await page.getByRole("button",{name:"Confirm create"}).click();
  await page.getByRole("button",{name:"Start sampling"}).click();
  await expect(page.getByText("Sampling: running")).toBeVisible();
}
async function selectPerformanceSeries(page:Page):Promise<void>{
  await expect(page.getByRole("row")).toHaveCount(257);
  const choices=page.getByRole("checkbox",{name:/Plot /});
  for(let index=0;index<8;index++)await choices.nth(index).check();
  await expect(page.getByLabel("Live chart")).toHaveAttribute("data-series-count","8");
  await expect(page.getByLabel("Live chart")).toHaveAttribute("data-max-points","600");
}
```

- [ ] **Step 2: Run RED and typecheck.** Run `& $npm run typecheck; & $npx playwright test e2e/performance.spec.ts --project=chromium-1280 --grep "full five-minute"`. Expected: FAIL because collector/instrumentation is absent.

- [ ] **Step 3: Implement every declared field and reset every threshold baseline at 120 seconds.** Build the one byte-identical committed production dist with the normal `npm run build`; never set a divergent Vite/build flag and never rewrite committed assets for E2E. The production bundle contains a dormant metrics hook that activates only when Playwright installs the one-shot `window.__STM32_MONITOR_E2E_ACTIVATE__=true` init value before bootstrap on exact IPv4 loopback; startup consumes and deletes that value. Without it, neither public metrics property exists. At startup call `initMonitorPerformance`; at the real sample queue-dequeue/chart-commit boundary call its completion exactly once with total retained points across the eight selected series, queue depth, and all four drop totals. Warm up from 0–120 seconds, then `resetPerformanceWindow` clears update/Long-Task/max-point counters while capturing queue/heap/drop baselines; server drops are read at the same boundary. Measure only the following 180 seconds. `percentile` rejects an empty list and heap slope divides by exactly 3 minutes. Add exactly:

```ts
// src/performance.ts -- dormant in the single normal production bundle unless runtime-activated
export type PerfDropTotals={subscriber:number;history:number;deadline:number;service:number};
export type BrowserPerfState={windowStartedAt:number;updates:{elapsedMs:number;durationMs:number}[];
  longTasksAtLeast200Ms:number;maxPoints:number;currentPoints:number;queueDepth:number;
  heapBytes:number;dropTotals:PerfDropTotals;disconnect:()=>void};
declare global{interface Window{__STM32_MONITOR_PERF__?:BrowserPerfState;
  __STM32_MONITOR_E2E_ACTIVATE__?:boolean}}
const heapBytes=():number=>Number((performance as Performance&{
  memory?:{usedJSHeapSize:number}}).memory?.usedJSHeapSize??0);
export function initMonitorPerformance():null|{
  beginUpdate:()=>((points:number,queueDepth:number,drops:PerfDropTotals)=>void)}{
  const active=import.meta.env.PROD&&location.hostname==="127.0.0.1"&&
    window.__STM32_MONITOR_E2E_ACTIVATE__===true;
  delete window.__STM32_MONITOR_E2E_ACTIVATE__;if(!active)return null;
  if(window.__STM32_MONITOR_PERF__!==undefined)throw new Error("performance hook already initialized");
  const state:BrowserPerfState={windowStartedAt:performance.now(),updates:[],
    longTasksAtLeast200Ms:0,maxPoints:0,currentPoints:0,queueDepth:0,heapBytes:heapBytes(),
    dropTotals:{subscriber:0,history:0,deadline:0,service:0},disconnect:()=>undefined};
  const observer=new PerformanceObserver(list=>{for(const entry of list.getEntries())
    if(entry.duration>=200)state.longTasksAtLeast200Ms+=1;});
  observer.observe({type:"longtask",buffered:true});state.disconnect=()=>observer.disconnect();
  window.__STM32_MONITOR_PERF__=state;
  return {beginUpdate:()=>{const started=performance.now();let completed=false;
    return(points,queueDepth,drops)=>{if(completed)throw new Error("update recorded twice");completed=true;
      const ended=performance.now();state.updates.push({elapsedMs:ended-state.windowStartedAt,
        durationMs:ended-started});state.currentPoints=points;
      state.maxPoints=Math.max(state.maxPoints,points);state.queueDepth=queueDepth;
      state.heapBytes=heapBytes();state.dropTotals={...drops};};}};
}
```

The live integration retains the nullable hook privately, starts timing only when a real sample leaves the production queue, and completes timing from the Preact post-commit/chart `setOption` completion—not from test or fake-runtime code. Teardown calls `disconnect()` and deletes the property. A functional-browser case without the init value asserts both E2E globals are absent; the normal build, byte-identical dist check, browser run, wheel, and installed smoke all consume the same committed bytes.

```ts
export async function collectPerformance(page:Page,monitor:MonitorBrowserFixture,
  windowMs:300000):Promise<PerformanceEvidence>{
  await page.waitForTimeout(120000);
  const before=await resetPerformanceWindow(page);
  const serverDropTotalsBefore=await monitor.dropTotals();
  await page.waitForTimeout(windowMs-120000);
  const after=await readPerformanceSnapshot(page);
  const measured=after.updates.map(v=>v.durationMs).sort((a,b)=>a-b);
  if(measured.length===0)throw new Error("performance sample window is empty");
  const serverDropTotalsAfter=await monitor.dropTotals();
  if(JSON.stringify(before.dropTotals)!==JSON.stringify(serverDropTotalsBefore)||
     JSON.stringify(after.dropTotals)!==JSON.stringify(serverDropTotalsAfter))
    throw new Error("browser/server drop instrumentation mismatch");
  const environment=await monitor.environment(page);
  return {
    minute2to5:{updateP50Ms:percentile(measured,.50),updateP95Ms:percentile(measured,.95),
      updateMaxMs:measured[measured.length-1]!,sampleCount:measured.length,
      longTasksAtLeast200Ms:after.longTasksAtLeast200Ms,maxPoints:after.maxPoints,
      queueStart:before.queueDepth,queueEnd:after.queueDepth,
      queueGrowth:after.queueDepth-before.queueDepth,
      heapStartBytes:before.heapBytes,heapEndBytes:after.heapBytes,
      heapSlopeMiBPerMin:((after.heapBytes-before.heapBytes)/1048576)/3,
      serverDropTotalsBefore,serverDropTotalsAfter},environment
  };
}
const readPerformanceSnapshot=(page:Page):Promise<BrowserPerformanceSnapshot>=>page.evaluate(()=>{
  const value=window.__STM32_MONITOR_PERF__;if(value===undefined)throw new Error("performance hook absent");
  const heap=Number((performance as Performance&{memory?:{usedJSHeapSize:number}})
    .memory?.usedJSHeapSize??value.heapBytes);value.heapBytes=heap;
  return {windowElapsedMs:performance.now()-value.windowStartedAt,updates:[...value.updates],
    longTasksAtLeast200Ms:value.longTasksAtLeast200Ms,maxPoints:value.maxPoints,
    queueDepth:value.queueDepth,heapBytes:heap,dropTotals:{...value.dropTotals}};
});
const resetPerformanceWindow=async(page:Page):Promise<BrowserPerformanceSnapshot>=>{
  const baseline=await readPerformanceSnapshot(page);
  await page.evaluate(()=>{const value=window.__STM32_MONITOR_PERF__;
    if(value===undefined)throw new Error("performance hook absent");
    value.windowStartedAt=performance.now();value.updates=[];value.longTasksAtLeast200Ms=0;
    value.maxPoints=value.currentPoints;value.heapBytes=Number((performance as Performance&{
      memory?:{usedJSHeapSize:number}}).memory?.usedJSHeapSize??value.heapBytes);
    value.dropTotals={...value.dropTotals};});
  return baseline;
};
const percentile=(sorted:readonly number[],fraction:number):number=>{
  if(sorted.length===0)throw new Error("percentile input is empty");
  return sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*fraction)-1)]!;
};
async function writeEvidenceJson(info:TestInfo,name:string,value:PerformanceEvidence,
  knownToken:string):Promise<void>{
  const root=process.env.STM32_MONITOR_E2E_EVIDENCE_ROOT;
  if(root===undefined||!path.isAbsolute(root))throw new Error("evidence root must be absolute");
  const file=path.resolve(root,"playwright",name);
  if(!file.startsWith(path.resolve(root)+path.sep))throw new Error("evidence path escaped root");
  await fs.promises.mkdir(path.dirname(file),{recursive:true});
  const encoded=JSON.stringify(value);if(encoded.includes(knownToken))throw new Error("secret in evidence");
  await fs.promises.writeFile(file,encoded,"utf8");
  info.attachments.push({name,path:file,contentType:"application/json"});
}
```

- [ ] **Step 4: Run GREEN once at the exact production fixture.** Repeat Step 2 with built committed assets, Chromium 1280×720, 10 Hz, 256 rows, 8×600 points, and the external evidence root. Expected: PASS after exactly 300000 ms; retained JSON contains CPU/Node/Chromium, viewport, asset bytes, sample count, p50/p95/max, Long Tasks, max points, queue start/end/growth, heap start/end/slope, and before/after drop totals.

- [ ] **Step 5: Commit the performance unit.** Add only `performance.spec.ts` and directly required fixture/config instrumentation; commit `test(STM32TK-0502): add five-minute UI performance evidence`. Do not name `CODE_HEAD`.

## Task 4: Repository-Owned Windows Release-Gate Helper TDD

**Files:**

- Create: `tools/release/run_0502_windows_gates.ps1`
- Create: `tools/stm32-toolkit/tests/test_0502_release_gate_helper.py`

**Interfaces:**

- Script parameters are exactly mandatory `RepoRoot`, `EvidenceRoot`, and `ToolchainJson`; no optional fourth parameter or embedded checkout exists.
- `ToolchainJson` has exactly six absolute executable fields: `git`, `node`, `npm`, `npx`, `python310`, and `python312`. Git is explicit so repository gates do not depend on ambient PATH. The controller obtains all six from the Codex-controlled environment and never guesses a path.
- The controller pre-populates `<EvidenceRoot>/dependency-support/` and `dependency-support.json` with a read-only, SHA-256-pinned Windows wheel support set. The helper verifies it, then creates all other wheelhouses/venvs/artifacts below the same `EvidenceRoot`.
- The helper captures a clean full `CODE_HEAD`, proves both source roots are the committed files at that head before the first pytest collection, creates external fresh test venvs, and uses each venv's `Scripts/python.exe` for both collection and execution.
- The first nonzero executable result terminates the helper. No later gate, report, or PASS marker runs.

- [ ] **Step 1: Write the failing AST and execution-contract tests.** Create the test file with the exact contract below. It checks the fresh-venv/source-proof/offline/fake-runtime command structure and executes the first-probe fail-fast path from repository/evidence paths containing spaces.

```python
from __future__ import annotations
import json, os, pathlib, re, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPER = ROOT / "tools" / "release" / "run_0502_windows_gates.ps1"

def helper_text() -> str:
    return HELPER.read_text(encoding="utf-8")

def powershell_ast() -> dict[str, object]:
    executable = pathlib.Path(os.environ["STM32_0502_TEST_POWERSHELL"]).resolve(strict=True)
    command = r'''$e=$null;$t=$null;$a=[Management.Automation.Language.Parser]::ParseFile(
      $args[0],[ref]$t,[ref]$e);[ordered]@{
      errors=@($e|% Message);parameters=@($a.ParamBlock.Parameters|%{$_.Name.VariablePath.UserPath});
      commands=@($a.FindAll({param($n)$n-is[Management.Automation.Language.CommandAst]},$true)|
        %{ $_.GetCommandName() }|?{$_})}|ConvertTo-Json -Depth 5 -Compress'''
    result = subprocess.run([str(executable), "-NoProfile", "-Command", command, str(HELPER)],
                            check=True, text=True, capture_output=True)
    return json.loads(result.stdout)

def test_helper_ast_has_only_three_parameters_and_no_ambient_tools() -> None:
    ast = powershell_ast()
    assert ast["errors"] == []
    assert ast["parameters"] == ["RepoRoot", "EvidenceRoot", "ToolchainJson"]
    forbidden = {"git", "node", "npm", "npx", "python", "python3", "py", "pip"}
    assert forbidden.isdisjoint({str(v).casefold() for v in ast["commands"]})
    text = helper_text()
    assert re.search(r"(?i)[a-z]:\\(?:tmp|workspace)\\[^'\"\r\n]*stm32", text) is None
    assert "Get-Command" not in text and "where.exe" not in text
    assert "IsPathFullyQualified" not in text
    assert "function Test-0502FullPath" in text and "full-path predicate self-test" in text

def test_helper_orders_source_proof_fresh_venvs_and_collection() -> None:
    text = helper_text()
    assert text.index("$codeHead =") < text.index("current-source-import-310")
    assert text.index("current-source-import-312") < text.index("collect-monitor-all")
    assert "test-env-310" in text and "test-env-312" in text
    assert "$testPython310" in text and "$testPython312" in text
    assert "git-monitor-source-clean" in text and "git-toolkit-source-clean" in text

def test_helper_requires_offline_wheels_and_fake_managed_runtime() -> None:
    text = helper_text()
    for operation in ("'download'", "'wheel'", "'install'"):
        assert operation in text
    assert text.count("'--no-index'") >= 6
    assert text.count("'--find-links'") >= 6
    assert "dependency-support.json" in text and "dependency-wheelhouse.json" in text
    assert "fake-plugin-data" in text and "runtime\\0.5.0\\Scripts\\python.exe" in text
    assert "$savedClaudePluginData" in text and "Remove-Item Env:CLAUDE_PLUGIN_DATA" in text

def test_helper_contains_complete_mandatory_gate_inventory() -> None:
    text = helper_text()
    required = {
      "node-npm-ci", "node-typecheck", "node-lint", "node-unit-coverage", "node-a11y",
      "node-build", "node-verify-dist", "node-production-audit",
      "python310-monitor-complete", "python312-monitor-main-coverage",
      "python312-auth-static-package-performance", "python312-toolkit-shard-",
      "python312-plugin-immutability-helper", "playwright-chromium-functional",
      "playwright-chromium-five-minute-performance", "launcher-cmd-help",
      "installed-smoke-310", "installed-smoke-312", "git-status-after"
    }
    assert required.issubset(set(re.findall(r"['\"]([A-Za-z0-9-]+)['\"]", text))) or all(
      value in text for value in required)

def test_helper_fails_fast_after_first_tool_failure(tmp_path: pathlib.Path) -> None:
    powershell = pathlib.Path(os.environ["STM32_0502_TEST_POWERSHELL"]).resolve(strict=True)
    repo = tmp_path / "repo with spaces"; evidence = tmp_path / "evidence with spaces"
    repo.mkdir(); evidence.mkdir()
    for relative in ("tools/stm32-monitor/ui","tools/stm32-monitor/tests",
                     "tools/stm32-toolkit/tests"):
        (repo / relative).mkdir(parents=True)
    failing = tmp_path / "fail-node.cmd"
    failing.write_text("@echo off\r\nexit /b 19\r\n", encoding="utf-8")
    system_cmd = pathlib.Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    tools = {name:str(system_cmd.resolve(strict=True)) for name in
             ("git","npm","npx","python310","python312")}
    tools["node"] = str(failing.resolve(strict=True))
    toolchain = evidence / "toolchain.json"
    toolchain.write_text(json.dumps(tools), encoding="utf-8")
    result = subprocess.run([str(powershell),"-NoProfile","-File",str(HELPER),
      "-RepoRoot",str(repo),"-EvidenceRoot",str(evidence),"-ToolchainJson",str(toolchain)],
      text=True,capture_output=True)
    assert result.returncode != 0
    assert (evidence / "version-node.log").is_file()
    assert not (evidence / "version-npm.log").exists()
    assert not (evidence / "version-git.log").exists()
```

- [ ] **Step 2: Run RED.** Set `STM32_0502_TEST_POWERSHELL` to the absolute current PowerShell executable and run `& $python312 -m pytest tools/stm32-toolkit/tests/test_0502_release_gate_helper.py -q`. Expected: FAIL because the helper is absent.

- [ ] **Step 3: Implement the complete helper below.** Copy the entire block as `tools/release/run_0502_windows_gates.ps1`. Do not replace any function or gate body with a reference, continuation note, summary, second script, checkout literal, or PATH lookup.

```powershell
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$EvidenceRoot,
  [Parameter(Mandatory=$true)][string]$ToolchainJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$AcceptedBase = 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'
function Test-0502FullPath([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value) -or -not [IO.Path]::IsPathRooted($Value)) { return $false }
  try { $full=[IO.Path]::GetFullPath($Value) } catch { return $false }
  return $full.Equals($Value,[StringComparison]::OrdinalIgnoreCase)
}
foreach($invalidPath in @('.','relative\tool.exe','C:drive-relative','\rooted-without-drive')){
  if(Test-0502FullPath $invalidPath){throw 'full-path predicate self-test failed'}
}
foreach($rawPath in @($RepoRoot,$EvidenceRoot,$ToolchainJson)){
  if(-not(Test-0502FullPath $rawPath)){throw 'input is not a rooted full path'}
}
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
$EvidenceRoot = (Resolve-Path -LiteralPath $EvidenceRoot -ErrorAction Stop).Path
$ToolchainJson = (Resolve-Path -LiteralPath $ToolchainJson -ErrorAction Stop).Path
foreach ($value in @($RepoRoot,$EvidenceRoot,$ToolchainJson)) {
  if (-not (Test-0502FullPath $value)) { throw 'all paths must be rooted full paths' }
}
$repoPrefix = $RepoRoot.TrimEnd('\') + '\'
if (($EvidenceRoot.TrimEnd('\') + '\').StartsWith($repoPrefix,[StringComparison]::OrdinalIgnoreCase)) {
  throw 'evidence root must be outside repository'
}

$toolchain = Get-Content -Raw -Encoding utf8 -LiteralPath $ToolchainJson | ConvertFrom-Json
$actualKeys = @($toolchain.PSObject.Properties.Name | Sort-Object)
$expectedKeys = @('git','node','npm','npx','python310','python312') | Sort-Object
if (@(Compare-Object $actualKeys $expectedKeys).Count -ne 0) { throw 'toolchain JSON schema mismatch' }
function Resolve-Tool([string]$Value,[string]$Name) {
  if (-not (Test-0502FullPath $Value)) { throw "$Name path is not a rooted full path" }
  $resolved = (Resolve-Path -LiteralPath $Value -ErrorAction Stop).Path
  if (-not [IO.File]::Exists($resolved)) { throw "$Name path is not a file" }
  return $resolved
}
$git = Resolve-Tool ([string]$toolchain.git) 'git'
$node = Resolve-Tool ([string]$toolchain.node) 'node'
$npm = Resolve-Tool ([string]$toolchain.npm) 'npm'
$npx = Resolve-Tool ([string]$toolchain.npx) 'npx'
$basePython310 = Resolve-Tool ([string]$toolchain.python310) 'python310'
$basePython312 = Resolve-Tool ([string]$toolchain.python312) 'python312'
$cmdExe = (Resolve-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\cmd.exe') -ErrorAction Stop).Path
$uiRoot = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\ui')).Path
$monitorTests = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\tests')).Path
$toolkitTests = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-toolkit\tests')).Path

function Invoke-Gate {
  param([string]$Name,[string]$WorkingDirectory,[string]$FilePath,[string[]]$ArgumentList)
  if (-not (Test-0502FullPath $FilePath)) { throw "$Name executable is not a rooted full path" }
  $log = Join-Path $EvidenceRoot ($Name + '.log')
  Push-Location -LiteralPath $WorkingDirectory
  try {
    $output = @(& $FilePath @ArgumentList 2>&1)
    $exit = $LASTEXITCODE
  } finally { Pop-Location }
  $output | Set-Content -Encoding utf8 -LiteralPath $log
  $output | ForEach-Object { Write-Host ([string]$_) }
  if ($exit -ne 0) { throw "$Name failed with exit $exit" }
}
function Invoke-Capture {
  param([string]$Name,[string]$WorkingDirectory,[string]$FilePath,[string[]]$ArgumentList)
  if (-not (Test-0502FullPath $FilePath)) { throw "$Name executable is not a rooted full path" }
  $log = Join-Path $EvidenceRoot ($Name + '.log')
  Push-Location -LiteralPath $WorkingDirectory
  try {
    $lines = @(& $FilePath @ArgumentList 2>&1)
    $exit = $LASTEXITCODE
  } finally { Pop-Location }
  $lines | Set-Content -Encoding utf8 -LiteralPath $log
  if ($exit -ne 0) { throw "$Name failed with exit $exit" }
  return $lines
}
function Get-WheelManifest([string]$Root) {
  return @(Get-ChildItem -LiteralPath $Root -File | Sort-Object Name | ForEach-Object {
    if ($_.Extension -ne '.whl') { throw "non-wheel in wheelhouse: $($_.Name)" }
    [ordered]@{name=$_.Name;bytes=$_.Length;
      sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
  })
}
function Get-TrackedManifest {
  $paths = @(Invoke-Capture 'git-ls-files' $RepoRoot $git @('-C',$RepoRoot,'ls-files'))
  return @($paths | Sort-Object | ForEach-Object {
    $full = Join-Path $RepoRoot ([string]$_)
    [ordered]@{path=[string]$_;bytes=(Get-Item -LiteralPath $full).Length;
      sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash.ToLowerInvariant()}
  }) | ConvertTo-Json -Depth 4 -Compress
}
function Get-NodeIds {
  param([string]$Name,[string]$PythonPath,[string[]]$Paths,[string[]]$ExtraArgs)
  $lines = Invoke-Capture $Name $RepoRoot $PythonPath (
    @('-m','pytest') + $Paths + @('--collect-only','-q','-p','no:cacheprovider') + $ExtraArgs)
  return @($lines | ForEach-Object { [string]$_ } |
    Where-Object { $_ -match '^[^=]+::' } | Sort-Object)
}
function Assert-UniqueInventory([string]$Name,[string[]]$NodeIds) {
  $unique = @($NodeIds | Sort-Object -Unique)
  if ($NodeIds.Count -eq 0 -or $unique.Count -ne $NodeIds.Count) {
    throw "$Name nodeid duplicate/count mismatch"
  }
}

$nodeVersion = @(Invoke-Capture 'version-node' $RepoRoot $node @('--version'))[-1]
$npmVersion = @(Invoke-Capture 'version-npm' $RepoRoot $npm @('--version'))[-1]
$npxVersion = @(Invoke-Capture 'version-npx' $RepoRoot $npx @('--version'))[-1]
$gitVersion = @(Invoke-Capture 'version-git' $RepoRoot $git @('--version'))[-1]
$py310Fact = @(Invoke-Capture 'version-python310' $RepoRoot $basePython310 @(
  '-c','import json,sys;print(json.dumps({"major":sys.version_info.major,"minor":sys.version_info.minor,"path":sys.executable}))'
))[-1] | ConvertFrom-Json
$py312Fact = @(Invoke-Capture 'version-python312' $RepoRoot $basePython312 @(
  '-c','import json,sys;print(json.dumps({"major":sys.version_info.major,"minor":sys.version_info.minor,"path":sys.executable}))'
))[-1] | ConvertFrom-Json
if ($py310Fact.major -ne 3 -or $py310Fact.minor -ne 10) { throw 'python310 version mismatch' }
if ($py312Fact.major -ne 3 -or $py312Fact.minor -ne 12) { throw 'python312 version mismatch' }
if ((Resolve-Path -LiteralPath ([string]$py310Fact.path)).Path -ne $basePython310 -or
    (Resolve-Path -LiteralPath ([string]$py312Fact.path)).Path -ne $basePython312) {
  throw 'Python executable identity mismatch'
}
[ordered]@{git=$gitVersion;node=$nodeVersion;npm=$npmVersion;npx=$npxVersion;
  python310="$($py310Fact.major).$($py310Fact.minor)";
  python312="$($py312Fact.major).$($py312Fact.minor)"} |
  ConvertTo-Json -Compress | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $EvidenceRoot 'toolchain-versions.json')

$initialStatus = @(Invoke-Capture 'git-status-before' $RepoRoot $git @(
  '-C',$RepoRoot,'status','--porcelain=v1','--untracked-files=all'))
if ($initialStatus.Count -ne 0) { throw 'repository must be clean before release gates' }
$codeHead = (@(Invoke-Capture 'git-code-head' $RepoRoot $git @('-C',$RepoRoot,'rev-parse','HEAD'))[-1]).Trim()
if ($codeHead -notmatch '^[0-9a-f]{40}$') { throw 'CODE_HEAD is not a full SHA' }
Invoke-Gate 'git-base' $RepoRoot $git @('-C',$RepoRoot,'cat-file','-e',"$AcceptedBase^{commit}")
Invoke-Gate 'git-diff-check' $RepoRoot $git @('-C',$RepoRoot,'diff','--check',"$AcceptedBase..$codeHead")
Invoke-Gate 'git-scope' $RepoRoot $git @('-C',$RepoRoot,'diff','--name-status',"$AcceptedBase..$codeHead")
$trackedBefore = Get-TrackedManifest

$monitorSourceRelative = 'tools/stm32-monitor/src'
$toolkitSourceRelative = 'tools/stm32-toolkit/src'
$monitorSource = (Resolve-Path -LiteralPath (Join-Path $RepoRoot $monitorSourceRelative)).Path
$toolkitSource = (Resolve-Path -LiteralPath (Join-Path $RepoRoot $toolkitSourceRelative)).Path
Invoke-Gate 'git-monitor-source-clean' $RepoRoot $git @(
  '-C',$RepoRoot,'diff','--exit-code',$codeHead,'--',$monitorSourceRelative)
Invoke-Gate 'git-toolkit-source-clean' $RepoRoot $git @(
  '-C',$RepoRoot,'diff','--exit-code',$codeHead,'--',$toolkitSourceRelative)
foreach ($relative in @(
  'tools/stm32-monitor/src/stm32_monitor/__init__.py',
  'tools/stm32-toolkit/src/stm32_toolkit/__init__.py')) {
  $label = $relative.Replace('/','-').Replace('.','-')
  $headBlob = (@(Invoke-Capture ('head-blob-' + $label) $RepoRoot $git @(
    '-C',$RepoRoot,'rev-parse',($codeHead + ':' + $relative)))[-1]).Trim()
  $worktreeBlob = (@(Invoke-Capture ('worktree-blob-' + $label) $RepoRoot $git @(
    '-C',$RepoRoot,'hash-object',(Join-Path $RepoRoot $relative)))[-1]).Trim()
  if ($headBlob -ne $worktreeBlob) { throw "source root is not CODE_HEAD: $relative" }
}
$env:PYTHONPATH = $monitorSource + ';' + $toolkitSource
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $EvidenceRoot 'pycache'
$env:PIP_NO_INDEX = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

$dependencySupport = (Resolve-Path -LiteralPath (Join-Path $EvidenceRoot 'dependency-support')).Path
$supportManifestPath = (Resolve-Path -LiteralPath (
  Join-Path $EvidenceRoot 'dependency-support.json')).Path
$supportManifest = Get-Content -Raw -Encoding utf8 -LiteralPath $supportManifestPath | ConvertFrom-Json
if ((@($supportManifest.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'files') {
  throw 'support manifest schema mismatch'
}
$declaredSupport = @{}
foreach ($item in @($supportManifest.files)) {
  if ((@($item.PSObject.Properties.Name | Sort-Object) -join ',') -ne 'name,sha256') {
    throw 'support wheel entry schema mismatch'
  }
  if ($declaredSupport.ContainsKey([string]$item.name)) { throw 'duplicate support wheel name' }
  $declaredSupport[[string]$item.name] = ([string]$item.sha256).ToLowerInvariant()
}
$supportFiles = @(Get-ChildItem -LiteralPath $dependencySupport -File | Sort-Object Name)
if ($supportFiles.Count -eq 0 -or $supportFiles.Count -ne $declaredSupport.Count) {
  throw 'support wheel inventory mismatch'
}
foreach ($wheel in $supportFiles) {
  if ($wheel.Extension -ne '.whl' -or -not $declaredSupport.ContainsKey($wheel.Name)) {
    throw "unexpected support file: $($wheel.Name)"
  }
  $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wheel.FullName).Hash.ToLowerInvariant()
  if ($actualHash -ne $declaredSupport[$wheel.Name]) { throw "support wheel hash mismatch: $($wheel.Name)" }
}

$dependencyWheelhouse = Join-Path $EvidenceRoot 'dependency-wheelhouse'
New-Item -ItemType Directory -LiteralPath $dependencyWheelhouse | Out-Null
$dependencySpecs = @('setuptools>=68','wheel','pytest>=8,<9','pytest-cov>=5,<7',
  'jsonschema>=4.23,<5','mcp>=1.27,<2','pyelftools>=0.33,<0.34',
  'Jinja2>=3.1,<4','aiohttp>=3.9,<4','pyocd>=0.45.1,<0.46')
foreach ($entry in @(@('310',$basePython310),@('312',$basePython312))) {
  $minor = [string]$entry[0]
  $basePython = [string]$entry[1]
  Invoke-Gate ('dependency-download-' + $minor) $EvidenceRoot $basePython (@(
    '-m','pip','download','--disable-pip-version-check','--no-input','--no-cache-dir',
    '--no-index','--find-links',$dependencySupport,'--only-binary=:all:',
    '--dest',$dependencyWheelhouse) + $dependencySpecs)
}
$wheelhouseManifest = @(Get-WheelManifest $dependencyWheelhouse)
if ($wheelhouseManifest.Count -eq 0) { throw 'dependency wheelhouse is empty' }
$wheelhouseManifestJson = $wheelhouseManifest | ConvertTo-Json -Depth 4 -Compress
$wheelhouseManifestJson | Set-Content -Encoding utf8 -LiteralPath (
  Join-Path $EvidenceRoot 'dependency-wheelhouse.json')

$packageRoot = Join-Path $EvidenceRoot 'package'
$archive = Join-Path $packageRoot 'code-head.zip'
$source = Join-Path $packageRoot 'source'
$wheels = Join-Path $packageRoot 'wheels'
$buildVenv = Join-Path $packageRoot 'build-venv-312'
New-Item -ItemType Directory -Force -Path $packageRoot,$wheels | Out-Null
Invoke-Gate 'archive-code-head' $RepoRoot $git @(
  '-C',$RepoRoot,'archive','--format=zip','--output',$archive,$codeHead)
Expand-Archive -LiteralPath $archive -DestinationPath $source
Invoke-Gate 'build-venv-create' $EvidenceRoot $basePython312 @('-m','venv',$buildVenv)
$buildPython = (Resolve-Path -LiteralPath (Join-Path $buildVenv 'Scripts\python.exe')).Path
Invoke-Gate 'build-venv-install' $EvidenceRoot $buildPython @(
  '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,'setuptools>=68','wheel')
Invoke-Gate 'wheel-toolkit' $source $buildPython @(
  '-m','pip','wheel','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,'--no-deps','--no-build-isolation',
  '--wheel-dir',$wheels,(Join-Path $source 'tools\stm32-toolkit'))
Invoke-Gate 'wheel-monitor' $source $buildPython @(
  '-m','pip','wheel','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,'--no-deps','--no-build-isolation',
  '--wheel-dir',$wheels,(Join-Path $source 'tools\stm32-monitor'))
$toolkitWheel = Get-Item -LiteralPath (Join-Path $wheels 'stm32_toolkit-0.5.0-py3-none-any.whl')
$monitorWheel = Get-Item -LiteralPath (Join-Path $wheels 'stm32_monitor-0.5.0-py3-none-any.whl')
@($toolkitWheel,$monitorWheel) | ForEach-Object {
  [ordered]@{name=$_.Name;bytes=$_.Length;
    sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
} | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (
  Join-Path $EvidenceRoot 'wheel-hashes.json')

$testPythonByMinor = @{}
foreach ($entry in @(@('310',$basePython310),@('312',$basePython312))) {
  $minor = [string]$entry[0]
  $basePython = [string]$entry[1]
  $testVenv = Join-Path $EvidenceRoot ('test-env-' + $minor)
  Invoke-Gate ('test-venv-create-' + $minor) $EvidenceRoot $basePython @('-m','venv',$testVenv)
  $testPython = (Resolve-Path -LiteralPath (Join-Path $testVenv 'Scripts\python.exe')).Path
  Invoke-Gate ('test-venv-install-' + $minor) $EvidenceRoot $testPython (@(
    '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
    '--no-index','--find-links',$dependencyWheelhouse,
    $toolkitWheel.FullName,$monitorWheel.FullName) + $dependencySpecs)
  Invoke-Gate ('test-venv-check-' + $minor) $EvidenceRoot $testPython @('-m','pip','check')
  $testPythonByMinor[$minor] = $testPython
}
$testPython310 = [string]$testPythonByMinor['310']
$testPython312 = [string]$testPythonByMinor['312']
$sourceProbe = @'
import importlib.metadata, json, pathlib, stm32_monitor, stm32_toolkit, sys
monitor_root=pathlib.Path(sys.argv[1]).resolve(); toolkit_root=pathlib.Path(sys.argv[2]).resolve()
monitor_file=pathlib.Path(stm32_monitor.__file__).resolve(); toolkit_file=pathlib.Path(stm32_toolkit.__file__).resolve()
assert monitor_file.is_relative_to(monitor_root), (monitor_file,monitor_root)
assert toolkit_file.is_relative_to(toolkit_root), (toolkit_file,toolkit_root)
assert importlib.metadata.version("stm32-monitor")=="0.5.0"
assert importlib.metadata.version("stm32-toolkit")=="0.5.0"
print(json.dumps({"monitor":str(monitor_file),"toolkit":str(toolkit_file),"python":sys.executable}))
'@
Invoke-Capture 'current-source-import-310' $RepoRoot $testPython310 @(
  '-c',$sourceProbe,$monitorSource,$toolkitSource) | Out-Null
Invoke-Capture 'current-source-import-312' $RepoRoot $testPython312 @(
  '-c',$sourceProbe,$monitorSource,$toolkitSource) | Out-Null

Invoke-Gate 'node-npm-ci' $uiRoot $npm @('ci')
Invoke-Gate 'node-typecheck' $uiRoot $npm @('run','typecheck')
Invoke-Gate 'node-lint' $uiRoot $npm @('run','lint')
Invoke-Gate 'node-unit-coverage' $uiRoot $npm @('run','test:coverage')
Invoke-Gate 'node-a11y' $uiRoot $npm @('run','test:a11y')
Invoke-Gate 'node-build' $uiRoot $npm @('run','build')
Invoke-Gate 'node-verify-dist' $uiRoot $npm @('run','verify:dist')
Invoke-Gate 'node-production-audit' $uiRoot $npm @('audit','--omit=dev','--audit-level=high')

$monitorAll = Get-NodeIds 'collect-monitor-all' $testPython312 @($monitorTests) @()
$monitorAll310 = Get-NodeIds 'collect-monitor-all-310' $testPython310 @($monitorTests) @()
$toolkitAll = Get-NodeIds 'collect-toolkit-all' $testPython312 @($toolkitTests) @()
Assert-UniqueInventory 'Monitor 3.12' $monitorAll
Assert-UniqueInventory 'Monitor 3.10' $monitorAll310
Assert-UniqueInventory 'Toolkit 3.12' $toolkitAll
if (@(Compare-Object $monitorAll $monitorAll310).Count -ne 0) {
  throw 'Monitor 3.10/3.12 collection inventory mismatch'
}
$monitorAll | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'monitor-312-nodeids.txt')
$monitorAll310 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'monitor-310-nodeids.txt')
$toolkitAll | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'toolkit-312-nodeids.txt')

$monitorSpecial = @('tools/stm32-monitor/tests/test_auth.py',
  'tools/stm32-monitor/tests/test_service.py','tools/stm32-monitor/tests/test_ui_assets.py',
  'tools/stm32-monitor/tests/test_ui_dist.py','tools/stm32-monitor/tests/test_package_boundary.py',
  'tools/stm32-monitor/tests/test_performance.py')
$monitorIgnore = @($monitorSpecial | ForEach-Object { "--ignore=$_" })
$monitorMainIds = Get-NodeIds 'collect-monitor-main' $testPython312 @('tools/stm32-monitor/tests') $monitorIgnore
$monitorSpecialIds = Get-NodeIds 'collect-monitor-special' $testPython312 $monitorSpecial @()
$monitorPartition = @($monitorMainIds + $monitorSpecialIds)
Assert-UniqueInventory 'Monitor execution partition' $monitorPartition
if (@(Compare-Object $monitorAll $monitorPartition).Count -ne 0) {
  throw 'Monitor execution inventory mismatch'
}
$toolkitSpecial = @('tools/stm32-toolkit/tests/test_plugin_layout.py',
  'tools/stm32-toolkit/tests/test_project_upgrade.py',
  'tools/stm32-toolkit/tests/test_0502_release_gate_helper.py')
$toolkitFiles = @(Get-ChildItem -LiteralPath $toolkitTests -Filter 'test_*.py' -File |
  ForEach-Object { $_.FullName.Substring($RepoRoot.Length+1).Replace('\','/') } |
  Where-Object { $toolkitSpecial -notcontains $_ } | Sort-Object)
$assignedFiles = [Collections.Generic.List[string]]::new()
$toolkitShardIds = [Collections.Generic.List[string]]::new()
for ($shard=0; $shard -lt 8; $shard++) {
  $files = [Collections.Generic.List[string]]::new()
  for ($index=$shard; $index -lt $toolkitFiles.Count; $index+=8) {
    $files.Add($toolkitFiles[$index]); $assignedFiles.Add($toolkitFiles[$index])
  }
  if ($files.Count -gt 0) {
    $collectedShard = Get-NodeIds ("collect-toolkit-shard-{0}" -f ($shard+1)) `
      $testPython312 ($files.ToArray()) @()
    foreach ($nodeId in $collectedShard) { $toolkitShardIds.Add($nodeId) }
  }
}
$toolkitSpecialIds = Get-NodeIds 'collect-toolkit-special' $testPython312 $toolkitSpecial @()
$toolkitPartition = @($toolkitShardIds.ToArray() + $toolkitSpecialIds)
if ($assignedFiles.Count -ne $toolkitFiles.Count -or
    @($assignedFiles | Sort-Object -Unique).Count -ne $toolkitFiles.Count) {
  throw 'Toolkit file shard mismatch'
}
Assert-UniqueInventory 'Toolkit execution partition' $toolkitPartition
if (@(Compare-Object $toolkitAll $toolkitPartition).Count -ne 0) {
  throw 'Toolkit nodeid shard mismatch'
}

Invoke-Gate 'python310-monitor-complete' $RepoRoot $testPython310 @(
  '-m','pytest','tools/stm32-monitor/tests','-q','-p','no:cacheprovider',
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-monitor-310'))
$env:COVERAGE_FILE = Join-Path $EvidenceRoot '.coverage-312'
Invoke-Gate 'python312-monitor-main-coverage' $RepoRoot $testPython312 (@(
  '-m','pytest','tools/stm32-monitor/tests','-q','-p','no:cacheprovider') +
  $monitorIgnore + @('--basetemp',(Join-Path $EvidenceRoot 'basetemp-monitor-main-312'),
  '--cov=stm32_monitor','--cov-branch','--cov-report='))
Invoke-Gate 'python312-auth-static-package-performance' $RepoRoot $testPython312 (@(
  '-m','pytest') + $monitorSpecial + @('-q','-s','-p','no:cacheprovider',
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-monitor-special-312'),
  '--cov=stm32_monitor','--cov-branch','--cov-append','--cov-report='))
for ($shard=0; $shard -lt 8; $shard++) {
  $files = @()
  for ($index=$shard; $index -lt $toolkitFiles.Count; $index+=8) { $files += $toolkitFiles[$index] }
  if ($files.Count -gt 0) {
    Invoke-Gate ("python312-toolkit-shard-{0}" -f ($shard+1)) $RepoRoot $testPython312 (@(
      '-m','pytest') + $files + @('-q','-p','no:cacheprovider',
      '--basetemp',(Join-Path $EvidenceRoot ("basetemp-toolkit-{0}-312" -f ($shard+1))),
      '--cov=stm32_toolkit','--cov-branch','--cov-append','--cov-report='))
  }
}
Invoke-Gate 'python312-plugin-immutability-helper' $RepoRoot $testPython312 (@(
  '-m','pytest') + $toolkitSpecial + @('-q','-p','no:cacheprovider',
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-toolkit-special-312'),
  '--cov=stm32_toolkit','--cov-branch','--cov-append','--cov-report='))
$coverageJson = Join-Path $EvidenceRoot 'coverage-312.json'
Invoke-Gate 'python312-coverage-json' $RepoRoot $testPython312 @(
  '-m','coverage','json','-o',$coverageJson)
$coverage = Get-Content -Raw -Encoding utf8 -LiteralPath $coverageJson | ConvertFrom-Json
if ([double]$coverage.totals.percent_covered -lt 90.0) {
  throw 'combined branch-aware coverage below 90%'
}
$changedModules = @(Invoke-Capture 'git-changed-modules' $RepoRoot $git @(
  '-C',$RepoRoot,'diff','--name-only',$AcceptedBase,$codeHead) |
  Where-Object { $_ -match '^tools/stm32-(monitor|toolkit)/src/.+\.py$' })
foreach ($module in $changedModules) {
  $normalized = ([string]$module).Replace('\','/')
  $matches = @($coverage.files.PSObject.Properties | Where-Object {
    $_.Name.Replace('\','/').EndsWith($normalized,[StringComparison]::OrdinalIgnoreCase) })
  if ($matches.Count -ne 1) { throw "coverage entry missing or ambiguous: $module" }
  if ([double]$matches[0].Value.summary.percent_covered -lt 90.0) {
    throw "changed module branch-aware coverage below 90%: $module"
  }
}

$env:STM32_MONITOR_E2E_PYTHON = $testPython312
$env:STM32_MONITOR_E2E_REPO_ROOT = $RepoRoot
$env:STM32_MONITOR_E2E_EVIDENCE_ROOT = $EvidenceRoot
Invoke-Gate 'playwright-chromium-functional' $uiRoot $npx @(
  'playwright','test','--project=chromium-1280','--project=chromium-1024','--grep-invert','five-minute')
Invoke-Gate 'playwright-chromium-five-minute-performance' $uiRoot $npx @(
  'playwright','test','e2e/performance.spec.ts','--project=chromium-1280','--grep','five-minute')
foreach ($entry in @(@('310',$testPython310),@('312',$testPython312))) {
  $minor = [string]$entry[0]; $testPython = [string]$entry[1]
  $env:PYTHONPYCACHEPREFIX = Join-Path $EvidenceRoot ('compile-pycache-' + $minor)
  Invoke-Gate ('compile-monitor-' + $minor) $RepoRoot $testPython @(
    '-m','compileall','-q','tools/stm32-monitor/src/stm32_monitor')
  Invoke-Gate ('compile-toolkit-' + $minor) $RepoRoot $testPython @(
    '-m','compileall','-q','tools/stm32-toolkit/src/stm32_toolkit')
}

$fakePluginData = Join-Path $EvidenceRoot 'fake-plugin-data'
$fakeRuntime = Join-Path $fakePluginData 'runtime\0.5.0'
Invoke-Gate 'fake-managed-runtime-create' $EvidenceRoot $basePython312 @('-m','venv',$fakeRuntime)
$fakeRuntimePython = (Resolve-Path -LiteralPath (
  Join-Path $fakeRuntime 'Scripts\python.exe')).Path
Invoke-Gate 'fake-managed-runtime-install' $EvidenceRoot $fakeRuntimePython @(
  '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,
  $toolkitWheel.FullName,$monitorWheel.FullName,'pyocd>=0.45.1,<0.46')
Invoke-Gate 'fake-managed-runtime-check' $EvidenceRoot $fakeRuntimePython @(
  '-c','import importlib.metadata,importlib.resources,sys;assert importlib.metadata.version("stm32-toolkit")=="0.5.0";assert importlib.metadata.version("stm32-monitor")=="0.5.0";assert importlib.resources.files("stm32_monitor").joinpath("ui_dist/index.html").is_file();print(sys.executable)')
$expectedFakePython = (Resolve-Path -LiteralPath (
  Join-Path $fakePluginData 'runtime\0.5.0\Scripts\python.exe')).Path
if ($fakeRuntimePython -ne $expectedFakePython) { throw 'fake managed runtime path mismatch' }
$hadClaudePluginData = Test-Path Env:CLAUDE_PLUGIN_DATA
$savedClaudePluginData = if ($hadClaudePluginData) { [string]$env:CLAUDE_PLUGIN_DATA } else { $null }
$hadPythonPath = Test-Path Env:PYTHONPATH
$savedPythonPath = if ($hadPythonPath) { [string]$env:PYTHONPATH } else { $null }
try {
  $env:CLAUDE_PLUGIN_DATA = $fakePluginData
  Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  Invoke-Gate 'launcher-cmd-help' $RepoRoot $cmdExe @('/d','/c','bin\stm32-monitor.cmd','--help')
} finally {
  if ($hadClaudePluginData) { $env:CLAUDE_PLUGIN_DATA = $savedClaudePluginData }
  else { Remove-Item Env:CLAUDE_PLUGIN_DATA -ErrorAction SilentlyContinue }
  if ($hadPythonPath) { $env:PYTHONPATH = $savedPythonPath }
  else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
}

$smokePath = Join-Path $EvidenceRoot 'installed-smoke.py'
@'
import asyncio, importlib.metadata, importlib.resources, pathlib, sys
from aiohttp import ClientSession
import stm32_monitor, stm32_toolkit
from stm32_monitor.service import MonitorService
assert importlib.metadata.version("stm32-monitor")=="0.5.0"
assert importlib.metadata.version("stm32-toolkit")=="0.5.0"
prefix=pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(stm32_monitor.__file__).resolve().is_relative_to(prefix)
assert pathlib.Path(stm32_toolkit.__file__).resolve().is_relative_to(prefix)
root=importlib.resources.files("stm32_monitor").joinpath("ui_dist")
assert root.joinpath("index.html").is_file()
assert root.joinpath(".vite/manifest.json").is_file()
class Runtime:
    async def dispatch(self,*args,**kwargs):
        raise AssertionError("unauthenticated request reached runtime")
async def smoke():
    service=MonitorService(Runtime(),workspace_id="installed-workspace",session_id="installed-session")
    endpoint=await service.start()
    try:
        async with ClientSession() as client:
            index=await client.get(endpoint.url+"/")
            assert index.status==200
            csp=index.headers["Content-Security-Policy"]
            assert "default-src 'none'" in csp and endpoint.url.replace("http","ws",1) in csp
            denied=await client.get(endpoint.url+"/api/v1/status")
            assert denied.status in (401,403)
    finally:
        await service.stop()
asyncio.run(smoke())
'@ | Set-Content -Encoding utf8 -LiteralPath $smokePath
foreach ($entry in @(@('310',$basePython310),@('312',$basePython312))) {
  $minor = [string]$entry[0]; $basePython = [string]$entry[1]
  $smokeVenv = Join-Path $packageRoot ('smoke-venv-' + $minor)
  Invoke-Gate ('smoke-venv-create-' + $minor) $EvidenceRoot $basePython @('-m','venv',$smokeVenv)
  $smokePython = (Resolve-Path -LiteralPath (
    Join-Path $smokeVenv 'Scripts\python.exe')).Path
  Invoke-Gate ('smoke-venv-install-offline-' + $minor) $EvidenceRoot $smokePython @(
    '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
    '--no-index','--find-links',$dependencyWheelhouse,
    $toolkitWheel.FullName,$monitorWheel.FullName,'pyocd>=0.45.1,<0.46')
  Invoke-Gate ('smoke-venv-check-' + $minor) $EvidenceRoot $smokePython @('-m','pip','check')
  $smokeHadPythonPath = Test-Path Env:PYTHONPATH
  $smokeSavedPythonPath = if ($smokeHadPythonPath) { [string]$env:PYTHONPATH } else { $null }
  try {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Invoke-Gate ('installed-smoke-' + $minor) $EvidenceRoot $smokePython @($smokePath)
  } finally {
    if ($smokeHadPythonPath) { $env:PYTHONPATH = $smokeSavedPythonPath }
    else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
  }
}

$currentWheelhouseJson = @(Get-WheelManifest $dependencyWheelhouse) |
  ConvertTo-Json -Depth 4 -Compress
if ($currentWheelhouseJson -ne $wheelhouseManifestJson) {
  throw 'dependency wheelhouse changed during gates'
}
$trackedAfter = Get-TrackedManifest
if ($trackedAfter -ne $trackedBefore) { throw 'tracked repository bytes changed during gates' }
Invoke-Gate 'git-diff-check-after' $RepoRoot $git @(
  '-C',$RepoRoot,'diff','--check',"$AcceptedBase..$codeHead")
$finalStatus = @(Invoke-Capture 'git-status-after' $RepoRoot $git @(
  '-C',$RepoRoot,'status','--porcelain=v1','--untracked-files=all'))
if ($finalStatus.Count -ne 0) { throw 'repository changed during release gates' }
[ordered]@{acceptedBase=$AcceptedBase;codeHead=$codeHead;status='PASS';
  testPython310=$testPython310;testPython312=$testPython312;
  dependencyWheelhouse='dependency-wheelhouse.json'} |
  ConvertTo-Json -Compress | Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $EvidenceRoot 'windows-gates-result.json')
```

- [ ] **Step 4: Run GREEN including the path-with-spaces fail-fast scenario.** Repeat Step 2. Expected: PASS; the AST has only three parameters, every external command path is absolute, source proof precedes collection, fresh venv interpreters are the declared collection/execution tools, offline/fake-runtime commands are structurally mandatory, and first failure stops later logs.

- [ ] **Step 5: Commit the helper TDD unit before the code-head barrier.** With the controlled absolute `$git`, add `tools/release/run_0502_windows_gates.ps1` and `tools/stm32-toolkit/tests/test_0502_release_gate_helper.py`, then commit `test(STM32TK-0502): add deterministic Windows release gates`. Do not name `CODE_HEAD` in this step; Task 5 audits the entire runtime-release-plus-evidence ancestry before naming it.

## Task 5: Consume the Unique CODE_HEAD and Run the Complete Windows Matrix Once

**Precondition:** Tasks 1–4 have committed every browser fixture/test and the helper/test on top of the verified `runtimeReleaseHead`. The report path is absent and the worktree is clean. No commit has yet been called `CODE_HEAD`. If any precondition is false, stop before creating evidence.

### Mandatory Windows gate inventory

| Gate | Exact owner/environment | Required PASS evidence |
|---|---|---|
| Git scope/source | Codex Windows evidence owner; clean unique `CODE_HEAD` | accepted-base-to-`CODE_HEAD` `diff --check` and name-status; both source roots equal head blobs; clean before/after; tracked byte manifest unchanged |
| Node/UI | absolute Node/npm/npx from JSON | npm ci, typecheck, lint, unit branch coverage, component axe, build, byte-identical dist, production audit; lockfile and committed dist unchanged; no high/critical finding |
| Python 3.10 | fresh external `test-env-310` | complete Monitor nodeid inventory collected/executed by the same venv interpreter, exactly once, all PASS |
| Python 3.12 | fresh external `test-env-312` | complete Monitor partition and non-overlapping Toolkit shards/special partition; all nodeids unique/exactly once; auth/service/assets/dist/package/performance `-q -s`; compileall |
| Coverage | 3.12 fresh test venv | combined branch-aware >=90% and every accepted-base-changed Monitor/Toolkit product module branch-aware >=90% |
| Browser | Playwright Chromium, production build | functional suite at 1280×720 and 1024×768; auth/token/offline/security/two-workspace/a11y/screenshots; exact five-minute threshold fixture |
| Wheels | exact `CODE_HEAD` archive, external build/smoke venvs | exact two `0.5.0` filenames, byte sizes/SHA-256; offline install/pip check/smoke under 3.10 and 3.12 with repository `PYTHONPATH` removed |
| Launcher/runtime | external `fake-plugin-data/runtime/0.5.0` | exact managed interpreter, no ambient fallback, UI manifest readable, CMD help succeeds, `CLAUDE_PLUGIN_DATA` and `PYTHONPATH` restored |
| Plugin/immutability | Toolkit special partition | mandatory fallback `test_plugin_layout.py`, eight Skills/version/layout, project-upgrade immutability, helper contract; official CLI absence is an environment fact and never replaces fallback |

- [ ] **Step 1: Audit the whole product ancestry and name the unique immutable `CODE_HEAD`.** Consume only the already raw-byte/signature-verified packet fields. Bind the exact controller inventory `$ControllerGitPath/$ControllerNodePath/$ControllerNpmPath/$ControllerNpxPath/$ControllerPowerShellPath/$ControllerPythonCandidatePath/$ControllerDependencySupportPath`; resolve each to one rooted full existing file/directory, record its version/identity, and reject aliases, duplicates, PATH discovery, or a candidate whose reported `sys.executable` differs. Require clean status and exact packet branch; prove `runtimeReleaseHead` is an ancestor of `HEAD`; run accepted-base-to-`HEAD` `diff --check` and name-status; verify every expected product/assets/version/README/phase-plan/roadmap/active-Skill/browser/helper path is committed; verify the historical requirement blob; run the committed helper unit test with the verified 3.12 candidate and verified PowerShell; and require the report absent. Only after all checks pass, assign the measured full SHA to `$CODE_HEAD`, verify `show CODE_HEAD:tools/release/run_0502_windows_gates.ps1`, and make no further pre-report repository change. Execute this concrete inventory/audit spine (the expected-path list is exhaustive, not illustrative):

```powershell
function Test-0502FullPath([string]$Value){
  if([string]::IsNullOrWhiteSpace($Value)-or-not[IO.Path]::IsPathRooted($Value)){return $false}
  try{$full=[IO.Path]::GetFullPath($Value)}catch{return $false}
  return $full.Equals($Value,[StringComparison]::OrdinalIgnoreCase)
}
$controllerFiles=[ordered]@{git=$ControllerGitPath;node=$ControllerNodePath;npm=$ControllerNpmPath;
  npx=$ControllerNpxPath;powershell=$ControllerPowerShellPath}
foreach($name in @($controllerFiles.Keys)){
  if(-not(Test-0502FullPath ([string]$controllerFiles[$name]))){throw "controller path is not full: $name"}
  $resolved=(Resolve-Path -LiteralPath ([string]$controllerFiles[$name]) -ErrorAction Stop).Path
  if(-not(Test-0502FullPath $resolved)-or-not[IO.File]::Exists($resolved)){throw "invalid controller executable: $name"}
  $controllerFiles[$name]=$resolved
}
$git=[string]$controllerFiles.git;$NodePath=[string]$controllerFiles.node
$NpmPath=[string]$controllerFiles.npm;$NpxPath=[string]$controllerFiles.npx
$PowerShell=[string]$controllerFiles.powershell
$nodeIdentity=(& $NodePath -p 'JSON.stringify({path:process.execPath,version:process.version})')|ConvertFrom-Json
if($LASTEXITCODE-ne0-or(Resolve-Path -LiteralPath ([string]$nodeIdentity.path)).Path-cne$NodePath){
  throw 'controlled Node executable identity mismatch'
}
$controllerInventory=[ordered]@{
  git=[ordered]@{path=$git;version=((& $git --version)-join"`n")}
  node=[ordered]@{path=$NodePath;version=[string]$nodeIdentity.version}
  npm=[ordered]@{path=$NpmPath;version=((& $NpmPath --version)-join"`n")}
  npx=[ordered]@{path=$NpxPath;version=((& $NpxPath --version)-join"`n")}
  powershell=[ordered]@{path=$PowerShell;version=((& $PowerShell -NoProfile -Command '$PSVersionTable.PSVersion.ToString()')-join"`n")}
}
if($LASTEXITCODE-ne0-or@($controllerInventory.Values|Where-Object{
  [string]::IsNullOrWhiteSpace([string]$_.version)}).Count-ne0){throw 'controller executable version audit failed'}
$pythonFacts=@($ControllerPythonCandidatePath|ForEach-Object{
  if(-not(Test-0502FullPath $_)){throw 'Python candidate path is not full'}
  $candidate=(Resolve-Path -LiteralPath $_ -ErrorAction Stop).Path
  if(-not(Test-0502FullPath $candidate)-or-not[IO.File]::Exists($candidate)){throw 'invalid Python candidate'}
  $fact=(& $candidate -c 'import json,sys;print(json.dumps({"path":sys.executable,"major":sys.version_info.major,"minor":sys.version_info.minor}))')|ConvertFrom-Json
  if($LASTEXITCODE-ne0-or(Resolve-Path -LiteralPath ([string]$fact.path)).Path-cne$candidate){throw 'Python candidate identity mismatch'}
  [pscustomobject]@{path=$candidate;major=[int]$fact.major;minor=[int]$fact.minor}
})
$python310=@($pythonFacts|Where-Object{$_.major-eq3-and$_.minor-eq10})
$python312=@($pythonFacts|Where-Object{$_.major-eq3-and$_.minor-eq12})
if($python310.Count-ne1-or$python312.Count-ne1){throw 'BLOCKED: exact CPython 3.10/3.12 inventory unavailable'}
$Python312Path=[string]$python312[0].path
if(-not(Test-0502FullPath $ControllerDependencySupportPath)){throw 'dependency support path is not full'}
$DependencySupportPath=(Resolve-Path -LiteralPath $ControllerDependencySupportPath -ErrorAction Stop).Path
if(-not(Test-0502FullPath $DependencySupportPath)-or-not[IO.Directory]::Exists($DependencySupportPath)){
  throw 'invalid controlled dependency support root'
}
$RepoRoot=(Resolve-Path -LiteralPath '.' -ErrorAction Stop).Path
if(-not(Test-0502FullPath $RepoRoot)){throw 'repository root is not a rooted full path'}
$preCodeStatus=@(& $git -C $RepoRoot status --porcelain=v1 --untracked-files=all)
if($LASTEXITCODE-ne0-or$preCodeStatus.Count-ne0){throw 'pre-CODE_HEAD worktree is dirty'}
$actualBranch=(& $git -C $RepoRoot branch --show-current).Trim()
if($LASTEXITCODE-ne0-or$actualBranch-cne$branch){throw 'implementation branch differs from signed handoff'}
& $git -C $RepoRoot merge-base --is-ancestor $runtimeReleaseHead HEAD
if($LASTEXITCODE-ne0){throw 'browser ancestry does not descend from runtimeReleaseHead'}
& $git -C $RepoRoot diff --check "$acceptedBase..HEAD";if($LASTEXITCODE-ne0){throw 'whole ancestry diff check failed'}
$wholeAncestryNameStatus=@(& $git -C $RepoRoot diff --name-status "$acceptedBase..HEAD")
if($LASTEXITCODE-ne0-or$wholeAncestryNameStatus.Count-eq0){throw 'whole ancestry name-status audit failed'}
$historicalActual=(& $git -C $RepoRoot rev-parse ($runtimeReleaseHead+':requirements/follow-on-skills/stm32-monitor/SKILL.md')).Trim()
if($LASTEXITCODE-ne0-or$historicalActual-cne$historicalMonitorSkillBlob){throw 'historical requirement blob mismatch'}
$expectedCodePaths=@('tools/stm32-monitor/ui/e2e/fake_runtime.py','tools/stm32-monitor/ui/e2e/conftest.ts',
 'tools/stm32-monitor/ui/e2e/monitor.spec.ts','tools/stm32-monitor/ui/e2e/security.spec.ts',
 'tools/stm32-monitor/ui/e2e/isolation.spec.ts','tools/stm32-monitor/ui/e2e/accessibility.spec.ts',
 'tools/stm32-monitor/ui/e2e/performance.spec.ts','tools/stm32-monitor/ui/playwright.config.ts',
 'tools/stm32-monitor/ui/package.json','tools/stm32-monitor/src/stm32_monitor/ui_dist/.vite/manifest.json',
 'tools/release/run_0502_windows_gates.ps1','tools/stm32-toolkit/tests/test_0502_release_gate_helper.py',
 '.claude-plugin/plugin.json','README.md','README_zh-CN.md','docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md')
foreach($path in $expectedCodePaths){& $git -C $RepoRoot cat-file -e ("HEAD:"+$path);if($LASTEXITCODE-ne0){throw "missing CODE_HEAD path: $path"}}
$reportPath=Join-Path $RepoRoot 'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'
if(Test-Path -LiteralPath $reportPath){throw 'report exists before CODE_HEAD'}
$savedTestPowerShell=$env:STM32_0502_TEST_POWERSHELL
try{$env:STM32_0502_TEST_POWERSHELL=$PowerShell;& $Python312Path -m pytest tools/stm32-toolkit/tests/test_0502_release_gate_helper.py -q
  if($LASTEXITCODE-ne0){throw 'committed helper unit test failed'}}finally{
  if($null-eq$savedTestPowerShell){Remove-Item Env:STM32_0502_TEST_POWERSHELL -ErrorAction SilentlyContinue}
  else{$env:STM32_0502_TEST_POWERSHELL=$savedTestPowerShell}}
$CODE_HEAD=(& $git -C $RepoRoot rev-parse HEAD).Trim()
if($CODE_HEAD-notmatch'^[0-9a-f]{40}$'){throw 'measured CODE_HEAD is invalid'}
& $git -C $RepoRoot show ($CODE_HEAD+':tools/release/run_0502_windows_gates.ps1')|Out-Null
if($LASTEXITCODE-ne0){throw 'helper is absent from CODE_HEAD'}
```

- [ ] **Step 2: Create one external evidence root and serialize controlled inputs.** The controller receives absolute Git/Node/npm/npx and every bundled Python candidate plus one read-only dependency-support tree from the Codex-controlled environment. It runs the two exact functions below; no PATH lookup, pip cache, index, or manually guessed path is allowed.

```powershell
function Test-0502FullPath([string]$Value){
  if([string]::IsNullOrWhiteSpace($Value)-or-not[IO.Path]::IsPathRooted($Value)){return $false}
  try{$full=[IO.Path]::GetFullPath($Value)}catch{return $false}
  return $full.Equals($Value,[StringComparison]::OrdinalIgnoreCase)
}
function Write-0502ToolchainJson {
  param([Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][string]$GitPath,[Parameter(Mandatory)][string]$NodePath,
    [Parameter(Mandatory)][string]$NpmPath,[Parameter(Mandatory)][string]$NpxPath,
    [Parameter(Mandatory)][string[]]$PythonCandidatePath)
  $ErrorActionPreference='Stop'
  foreach($inputPath in @($EvidenceRoot,$GitPath,$NodePath,$NpmPath,$NpxPath)+$PythonCandidatePath){
    if(-not(Test-0502FullPath $inputPath)){throw 'toolchain writer received non-full path'}
  }
  $facts=foreach($candidate in $PythonCandidatePath){
    $resolved=(Resolve-Path -LiteralPath $candidate).Path
    $raw=& $resolved -c 'import json,sys;print(json.dumps({"path":sys.executable,"major":sys.version_info.major,"minor":sys.version_info.minor}))'
    if($LASTEXITCODE-ne 0){throw 'bundled Python candidate failed'}
    $raw|ConvertFrom-Json
  }
  $python310=@($facts|Where-Object{$_.major-eq 3-and$_.minor-eq 10})
  $python312=@($facts|Where-Object{$_.major-eq 3-and$_.minor-eq 12})
  if($python310.Count-ne 1-or$python312.Count-ne 1){throw 'BLOCKED: require one CPython 3.10 and 3.12'}
  [ordered]@{
    git=(Resolve-Path -LiteralPath $GitPath).Path;node=(Resolve-Path -LiteralPath $NodePath).Path
    npm=(Resolve-Path -LiteralPath $NpmPath).Path;npx=(Resolve-Path -LiteralPath $NpxPath).Path
    python310=(Resolve-Path -LiteralPath ([string]$python310[0].path)).Path
    python312=(Resolve-Path -LiteralPath ([string]$python312[0].path)).Path
  }|ConvertTo-Json -Compress|Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $EvidenceRoot 'toolchain.json')
}

function Copy-0502DependencySupport {
  param([Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][string]$DependencySupportPath)
  if(-not(Test-0502FullPath $EvidenceRoot)-or-not(Test-0502FullPath $DependencySupportPath)){
    throw 'dependency copier received non-full path'
  }
  $source=(Resolve-Path -LiteralPath $DependencySupportPath).Path
  $destination=Join-Path $EvidenceRoot 'dependency-support'
  New-Item -ItemType Directory -LiteralPath $destination|Out-Null
  $byName=@{}
  foreach($wheel in @(Get-ChildItem -LiteralPath $source -Recurse -File -Filter '*.whl'|Sort-Object FullName)){
    $hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $wheel.FullName).Hash.ToLowerInvariant()
    if($byName.ContainsKey($wheel.Name)-and$byName[$wheel.Name]-ne$hash){
      throw "dependency support has conflicting wheel name: $($wheel.Name)"
    }
    if(-not$byName.ContainsKey($wheel.Name)){
      Copy-Item -LiteralPath $wheel.FullName -Destination (Join-Path $destination $wheel.Name)
      $byName[$wheel.Name]=$hash
    }
  }
  if($byName.Count-eq 0){throw 'dependency support has no wheels'}
  $files=@(Get-ChildItem -LiteralPath $destination -File|Sort-Object Name|ForEach-Object{
    [ordered]@{name=$_.Name;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
  })
  [ordered]@{files=$files}|ConvertTo-Json -Depth 4|Set-Content -Encoding utf8 -LiteralPath (
    Join-Path $EvidenceRoot 'dependency-support.json')
}

$evidenceCandidate=Join-Path ([IO.Path]::GetTempPath()) `
  ('stm32tk-0502-evidence-'+[guid]::NewGuid().ToString('N'))
$EvidenceRoot=[IO.Path]::GetFullPath($evidenceCandidate)
New-Item -ItemType Directory -LiteralPath $EvidenceRoot|Out-Null
Write-0502ToolchainJson -EvidenceRoot $EvidenceRoot `
  -GitPath ([string]$controllerFiles.git) -NodePath ([string]$controllerFiles.node) `
  -NpmPath ([string]$controllerFiles.npm) -NpxPath ([string]$controllerFiles.npx) `
  -PythonCandidatePath @($pythonFacts.path)
Copy-0502DependencySupport -EvidenceRoot $EvidenceRoot `
  -DependencySupportPath $DependencySupportPath
$utf8NoBom=New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $EvidenceRoot 'code-head.txt'),$CODE_HEAD,$utf8NoBom)
$persistedCodeHead=[IO.File]::ReadAllText((Join-Path $EvidenceRoot 'code-head.txt'),$utf8NoBom)
if($persistedCodeHead-cne$CODE_HEAD){throw 'external CODE_HEAD persistence failed'}
```

- [ ] **Step 3: Invoke the committed helper exactly once for this `CODE_HEAD`.** Resolve the helper below `RepoRoot`, resolve the current PowerShell process executable without PATH discovery, and run only this command. A nonzero result is `FAIL` unless the missing controlled tool/support input was detected before product execution, in which case it is `BLOCKED`; it is never deferred.

```powershell
$RepoRoot=(Resolve-Path -LiteralPath '.').Path
$ToolchainJson=(Resolve-Path -LiteralPath (Join-Path $EvidenceRoot 'toolchain.json')).Path
$GateScript=(Resolve-Path -LiteralPath (
  Join-Path $RepoRoot 'tools\release\run_0502_windows_gates.ps1')).Path
$PowerShell=(Get-Process -Id $PID).Path
if(-not(Test-0502FullPath $PowerShell)){throw 'PowerShell path is not a rooted full path'}
$beforeHelperHead=(& $git -C $RepoRoot rev-parse HEAD).Trim()
$beforeHelperStatus=@(& $git -C $RepoRoot status --porcelain=v1 --untracked-files=all)
if($LASTEXITCODE-ne0-or$beforeHelperHead-cne$CODE_HEAD-or$beforeHelperStatus.Count-ne0){
  throw 'repository changed before sole helper invocation'
}
& $PowerShell -NoProfile -ExecutionPolicy Bypass -File $GateScript `
  -RepoRoot $RepoRoot -EvidenceRoot $EvidenceRoot -ToolchainJson $ToolchainJson
if($LASTEXITCODE-ne 0){throw "STM32TK-0502 Windows gates failed: $LASTEXITCODE"}
```

- [ ] **Step 4: Reconcile every result instead of trusting the final marker alone.** Require every row in the gate table, equal dual-Python Monitor inventories, unique Monitor/Toolkit partitions, current-source import paths, exact five-minute fields/thresholds, redacted browser evidence, dependency-support/wheelhouse hashes, exact wheel names/sizes/hashes, installed-wheel paths under each smoke venv, fake managed-runtime path, coverage totals/per-module facts, and clean/immutable Git results. Any missing log/artifact, duplicate/missing nodeid, installed-copy import, remote/offline violation, token/access URL, failed threshold, incomplete/mutable wheelhouse, ambient executable, repository output, changed lock/dist/tracked byte, or nonzero gate is FAIL, not deferred.

- [ ] **Step 5: Freeze the reconciled external evidence inventory.** Record relative path, byte size, and SHA-256 for toolchain facts, gate logs, nodeid lists, coverage JSON, browser screenshots/results, performance JSON, `ui_dist` tree/manifest, dependency manifests, code-head archive, wheels, and wheel smokes. Do not stage, commit, copy into the repository, or expose absolute project paths, token/access URL, request/response bodies, or sample values.

## Task 6: Tracked Report-Only Commit and Whole-Branch Acceptance/Rewrite Rules

**Files:**

- Create after Task 5 only: `docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md`

- [ ] **Step 1: Write the report from reconciled facts and only named deferrals.** Record module ID, implementation status, full accepted-base SHA, branch, full `code head before report commit` SHA, scope/path and version/lockfile facts. For every gate record evidence owner, `PASS/FAIL/BLOCKED`, OS/arch, absolute tool path+version, working directory, full command, UTC time, exit code, bounded stdout/stderr facts, and metrics. Inventory every retained external artifact by relative evidence path, bytes, and SHA-256. Record exactly `DEFERRED — Linux release owner` for Linux x86_64 CPython 3.10/3.12 + Node/npm + Chromium/Firefox/WebKit independent rerun, and exactly `DEFERRED — user/hardware owner` for one supported-board observation smoke.

- [ ] **Step 2: Validate report secrecy, provenance, and report-only scope before staging.** Assert the report contains the full accepted base and exact immutable `CODE_HEAD`, contains neither its own/final commit SHA nor a moving commit total, and contains no token, access URL, raw endpoint, absolute project/data/evidence path, sample value, false Linux/hardware PASS, or other deferred product behavior. Run the absolute Git executable's `status --short`; require the report path is the only change.

- [ ] **Step 3: Commit only the tracked report.** Run the following only after Step 2 passes. Do not amend `CODE_HEAD` and do not stage external evidence.

```powershell
& $git -C $repoRoot add -- `
  'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'
if($LASTEXITCODE-ne 0){throw 'report staging failed'}
& $git -C $repoRoot commit -m 'docs(STM32TK-0502): record lean monitor UI release evidence'
if($LASTEXITCODE-ne 0){throw 'report commit failed'}
```

- [ ] **Step 4: Perform the acceptance review against the whole branch in a clean isolated worktree.** Fetch read-only, resolve the returned full remote head, create a clean review worktree at that exact SHA, and review `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa..FINAL_HEAD`, not only the last commit. Require the report commit's parent is the recorded `CODE_HEAD`; `CODE_HEAD..FINAL_HEAD` changes only the report; all product/helper/browser changes are in accepted-base..`CODE_HEAD`; report facts reconcile with external evidence. No approval, push, PR mutation, merge, close, or branch deletion is implicit.

- [ ] **Step 5: Apply deterministic review outcomes and rewrite rules.** `ACCEPTED` requires every mandatory non-deferred gate PASS. Correctable findings are `REVISION_REQUIRED` on the same branch/attempt. Any product, asset, helper, test, version, README, plan, roadmap, or active Skill correction creates a new committed code head, invalidates superseded product evidence, reruns every affected gate plus full Git/source/inventory/immutability checks in a new external evidence root, and rewrites the tracked report in a new report-only commit. A report-fact-only correction changes only the report and remains report-only. Architecture/safety/scope/coverage replacement is `REWRITE_REQUIRED`; only that or an explicit replacement decision permits a new attempt. Never append stale evidence, reuse a superseded code-head PASS, rewrite remote history, or discard pushed/unpushed/untracked work without an ownership audit and user authorization.

## Plan Self-Review

- [x] **Spec coverage:** Tasks 1–3 cover real aiohttp + fake runtime, explicit workflows, fragment/cookie/offline/security, two workspaces, accessibility, external screenshots, and the exact five-minute production performance fields/thresholds. Tasks 4–5 cover the repository helper, absolute tools, fresh dual-Python venvs/current source roots, offline wheelhouses, Node/UI/Toolkit/wheels/plugin/immutability/fake-runtime gates. Task 6 covers named Linux/physical deferrals, report-only commit, and whole-branch review/rewrite.
- [x] **Dependency and code-head lifecycle:** The runtime-release plan hands off a clean `runtimeReleaseHead`; this plan commits browser/helper code, audits the complete ancestry, and then names the sole `CODE_HEAD`. Gate execution consumes but never amends that SHA; the report is absent from it and is the only report-commit change.
- [x] **Five-step closure:** Every product or evidence-helper unit has exactly one failing-test step, one RED command, a matching concrete implementation step, one GREEN command, and one commit step. Runtime evidence execution and report handoff each have five explicit checkboxes.
- [x] **Helper completeness:** The plan contains the complete single PowerShell helper and its concrete test contract. There is no omitted tail, second helper, checkout literal, bare Git/Node/npm/npx/Python/pip command, PATH discovery, or abbreviated reference to another script.
- [x] **Performance/type consistency:** `MonitorBrowserFixture`, `PerformanceEnvironment`, `DropTotals`, `BrowserPerformanceSnapshot`, and every `PerformanceEvidence` field are defined before use. The collector measures only 120000–300000 ms and returns every asserted metric without a type assertion.
- [x] **Evidence and secrecy:** Windows failures cannot be deferred. Linux and physical evidence have their two exact named owners. Token/access URL, absolute project/evidence paths, sample values, logs, screenshots, and generated evidence remain outside Git; only the sanitized tracked report is committed.
