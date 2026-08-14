# STM32TK-0502 Monitor UI Release Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to execute this plan sequentially with a fresh Codex subagent for each task and a Codex review checkpoint after every commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved offline Preact Monitor UI, same-process aiohttp/static/auth/launcher integration, deterministic wheels, unified `0.5.0` Plugin release, and complete Windows/browser evidence without changing the accepted 0501 protocol.

**Architecture:** One lossless TypeScript wire adapter consumes the accepted-base REST and live serializers, one pure reducer owns authoritative browser state, prop-only Preact views render it, and one controller alone orchestrates REST/WebSocket commands. The existing random-port `MonitorService` also serves an exact package-resource allowlist; release gates run against one immutable Git `CODE_HEAD`, emit evidence only outside the repository, and are followed by one report-only commit.

**Tech Stack:** Preact, strict TypeScript, Vite, modular ECharts, Vitest/Testing Library/axe, Playwright Chromium, CPython 3.10/3.12, aiohttp, pytest/coverage, PowerShell 5.1, Windows CMD, setuptools wheels.

## Delivery Ledger and Authority

- Module/phase: `STM32TK-0502-MONITOR-UI-RELEASE`, replacement implementation plan and then local implementation/review/acceptance.
- Full accepted product base: `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`.
- Plan branch at rewrite: `codex/STM32TK-0502-MONITOR-UI-RELEASE`; reviewed plan HEAD for fix round 1: `ee81349`; upstream product base: `origin/master` at the accepted-base SHA.
- Specification owner and acceptance reviewer: Codex. Implementer and implementation-test owner: a fresh Codex subagent per task under the user's single objective-bounded exception. That exception applies only to this complete 0502 objective and expires immediately at `ACCEPTED`, `REWRITE_REQUIRED`, or explicit reassignment. OpenClaw has no role.
- Active PR: none known or required. Remote authorization: none. No fetch, push, PR mutation, approval, merge, close, or remote branch deletion occurs during Tasks 1-12 or report creation. A remote action may be proposed only after the final accepted-branch stage and still needs the user's explicit authorization.
- Bounded override: the objective-level Codex-subagent implementation exception above; it grants no authority for 0.6, another module, or a later correction.
- Packet schema: **none**. Delete no product state and create no custom packet, signature, handoff JSON, signed file, or producer/consumer packet field list. Git full SHAs plus the subagent-driven-development ledger are the only task/phase handoff.

## Global Command and Task-Entry Convention

The controller resolves Codex-bundled Node/npm and CPython 3.10/3.12 through the desktop workspace-dependency integration and records their absolute paths in `$node`, `$npm`, `$python310`, and `$python312`. It also records absolute `$git`, `$powerShell` (Windows PowerShell 5.1), and `$cmdExe`. No command depends on `PATH`, `py`, ambient `python`, ambient `node`, `uv`, or a guessed installation path. Scratch, venv, coverage, Playwright, log, screenshot, wheel, and evidence roots are repository-external.

Before Task 1 the release owner supplies a read-only repository-external `$supportRoot` containing `support-manifest.json`, `npm-cache/`, `wheelhouse/`, and the Chromium executable named by that manifest. The manifest records every relative file's byte count and lowercase SHA-256, exact Node/npm/Chromium identities, exact npm dependency/devDependency versions, and exact Python artifacts for `setuptools>=68`, `wheel`, `build`, pytest/coverage, aiohttp, jsonschema, mcp, pyelftools, Jinja2, and the probe extra. Task 1's pure-stdlib verifier resolves every member, rejects traversal/symlinks/junctions/case aliases, requires the support root and manifest to reject non-mutating fail-closed writable-open/create probes, checks exhaustive bytes, and returns the verified absolute cache/wheelhouse/browser paths, support-manifest SHA-256, support-tree SHA-256, and exact requirements before any dependency command. No task downloads, updates, changes attributes on, or otherwise writes this input; `npm.cmd` is never modified. Before its first npm command, each task verifies support, mechanically copies the verified cache to a new repository-external `$taskRoot\\npm-cache-working`, rejects a pre-existing/nonempty/reparse destination, and uses only that working copy. Before and after every npm install/ci/audit phase and at task-final verification, rerun the verifier and require both source hashes to equal the values recorded before copying; the source cache is never a writable npm cache. Every npm install/ci/audit uses `--offline --cache $npmWorkingCache`; every pip command uses `--no-index --find-links $verified.wheelhouse`. Offline audit runs only when `$verified.auditCache` is true; otherwise the Windows gate returns `BLOCKED`.

At the start of **every** task, the SDD ledger supplies only `$ExpectedParent`, the exact 40-character SHA committed by the preceding task (Task 1 receives the committed plan head). Run this PowerShell 5.1-compatible gate from the isolated implementation worktree; do not serialize its values to a file:

```powershell
$AcceptedBase = 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'
$ExpectedBranch = 'codex/STM32TK-0502-MONITOR-UI-RELEASE'
if ($ExpectedParent -notmatch '^[0-9a-f]{40}$') { throw 'SDD ledger parent must be one full SHA' }
$actualHead = (& $git rev-parse HEAD).Trim()
$actualBranch = (& $git branch --show-current).Trim()
$dirty = @(& $git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $actualHead -cne $ExpectedParent) { throw 'task parent mismatch' }
if ($actualBranch -cne $ExpectedBranch) { throw 'implementation branch mismatch' }
if ($dirty.Count -ne 0) { throw 'task worktree must be clean' }
& $git cat-file -e "$AcceptedBase^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'accepted base is unavailable' }
& $git merge-base --is-ancestor $AcceptedBase $actualHead
if ($LASTEXITCODE -ne 0) { throw 'task head does not descend from accepted base' }
& $git diff --check "$AcceptedBase..$actualHead"
if ($LASTEXITCODE -ne 0) { throw 'existing branch diff is malformed' }
$report = 'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'
if (Test-Path -LiteralPath $report) { throw 'implementation report exists before CODE_HEAD' }
```

Repository-root commands run from `$repoRoot`; UI commands from `$uiRoot = Join-Path $repoRoot 'tools/stm32-monitor/ui'`. RED must fail for the named missing behavior, never dependency resolution, syntax, collection, or fixture setup. Each Task 1-12 produces exactly one ordinary local commit. Do not amend, rebase, reset, or create an intermediate report commit.

Every RED/GREEN command sets its cache, basetemp, coverage, Playwright output, and Python bytecode roots below the task's repository-external `$taskRoot`. After each GREEN command, require `@(& $git status --porcelain=v1 --untracked-files=all)` to equal the task's declared product/test paths only; after each commit it must be empty. Step 5 in every task calls this exact helper with a literal allowlist (Task 8 mechanically adds manifest-derived hashed assets):

```powershell
function Commit-0502Task([string]$Message,[string[]]$Paths) {
  $changed=@(& $git status --porcelain=v1 --untracked-files=all | ForEach-Object { $_.Substring(3).Replace('\\','/') } | Sort-Object -Unique)
  $allowed=@($Paths | ForEach-Object { $_.Replace('\\','/') } | Sort-Object -Unique)
  if(@(Compare-Object $changed $allowed).Count-ne0){throw 'task changed-path set differs from its literal allowlist'}
  & $git add -- @Paths;if($LASTEXITCODE-ne0){throw 'git add failed'}
  $cached=@(& $git diff --cached --name-only | ForEach-Object { $_.Replace('\\','/') } | Sort-Object)
  if(@(Compare-Object $cached $allowed).Count-ne0){throw 'cached-name set differs from task allowlist'}
  & $git commit -m $Message;if($LASTEXITCODE-ne0){throw 'task commit failed'}
  if(@(& $git status --porcelain=v1 --untracked-files=all).Count-ne0){throw 'task commit did not leave a clean worktree'}
}
```

## Global Product Constraints

- Preserve `stm32-toolkit-monitor/1`, every accepted 0501 route/operation/body/query grammar, the full REST/live envelope, history/storage/sampling/export behavior, and runtime-record rules. The only accepted 0501 compatibility change is the Design §7.3 cookie transport matrix in `auth.py`, `service.py`, and their tests.
- Browser runtime is offline and same-origin: no CDN, remote font, analytics, telemetry, service worker, source map, remote request, browser persistence, project write, direct PyOCD, probe backend import, second server, fixed port, or hidden process.
- Token flow is fragment-only, scrub-before-bootstrap, exact Bearer bootstrap, then HttpOnly `SameSite=Strict; Path=/api/v1` cookie only. Token/access URL never enters state, props, DOM, URL after scrub, console, errors, storage, files, logs, screenshots, evidence, report, or runtime record.
- Fresh workspaces have zero user groups and no presets. Probe connect/reconnect/release, group mutation/import, sampling start/pause/resume/stop, and exports are explicit user actions; there is no auto-connect, auto-reacquire, auto-start, steal, or last-write-wins.
- All signed-int64 identity, state, revision, drop, sequence, timestamp-nanosecond, byte/count, and ordinal values are parsed losslessly and represented internally as `bigint` (or a canonical decimal string only at a URL/DOM boundary). They are never converted to JavaScript `Number` for equality, ordering, replay, CAS, or request serialization.
- Every command follows `request.started -> authoritative success or explicit authoritative refresh -> request.cleared`, or `request.started -> request.failed`. Sampling success always performs `GET /api/v1/status` before clearing. Components are prop-only and contain no `fetch`, `WebSocket`, envelope parsing, or authority logic.
- Sample `ERROR`, absent/non-numeric typed value, and explicit null preserve the previous table value but append a `null` chart gap for that series. Every selected series is capped at 600 points; selection is capped at eight, so realized points are capped at 4,800.
- Catalog query is NFC-normalized, <=128 characters, 300 ms debounced, limit 100, connected-only, and keyed by catalog kind + query + binding identity + requested cursor. A query/binding change discards old rows, pending cursor, and returned stale cursor.
- `ui_dist` is committed, manifest-exact, byte-reproducible, no-source-map output. Index/manifest <=256 KiB, one asset <=4 MiB, total <=8 MiB, gzip initial JS <=450 KiB, gzip CSS <=50 KiB. Python wheel build never invokes Node.
- Windows mandatory gates are `PASS/FAIL/BLOCKED`. Only `DEFERRED — Linux release owner` and `DEFERRED — user/hardware owner` are legal deferrals. No pure-code or Windows-reproducible failure is deferred.
- 0.6 exclusions are absolute: no host/target test implementation, AI snapshot/analyze/diagnostic session export, advanced cross-run/group/firmware history comparison, quality timeline/distribution/full dashboard, annotations/bookmarks/diagnostic markers, or diagnostic hypothesis/evidence/action/fix UI in code, tests, hidden flags/routes, assets, active Skills, or active README claims.

## Frozen Accepted-Base Wire Contract

`contract.ts` is the single field/type authority. `client.ts`, `live.ts`, reducer, fixture, and tests import it; none repeats a producer/consumer field-name array. The accepted envelope has the eight base members `protocol`, `toolkitVersion`, `monitorVersion`, `ok`, `operation`, `code`, `message`, and `data`, plus the required `details` member emitted by the accepted serializer; none may be omitted. Each WebSocket text message is that same complete envelope with operation `monitor.live`, whose `data` is exactly `{eventId,type,data}`; `details.subscriberDropped` is transport evidence.

```ts
export type I64=bigint;
export type JsonValue=null|boolean|number|bigint|string|readonly JsonValue[]|{readonly [k:string]:JsonValue};
export type ApiFailure={ok:false;code:string;message:string};
export type ApiResult<T>={ok:true;data:T}|ApiFailure;
export type ProjectStatus={logicalProjectId:string;name:string;targetDevice:string};
export type FirmwareStatus={buildId:string;elfSha256:string;inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;targetDevice:string};
export type SamplingStatus={state:"IDLE"|"STARTING"|"RUNNING"|"PAUSED"|"PAUSED_BLOCKED"|"STOPPING";active:boolean;blockedCode:string|null;groupId:string|null;groupRevision:I64|null;runId:string|null;lastSequence:I64|null;bindingEpoch:I64;subscriberDrops:I64;historyDrops:I64;deadlineDrops:I64;serviceDrops:I64};
export type MonitorStatus={workspaceId:string;sessionId:string;project:ProjectStatus;firmware:FirmwareStatus|null;probe:{connected:boolean;probeId:string|null};sampling:SamplingStatus;probeConnected:boolean;samplingActive:boolean};
export type ProbeInfo={probeId:string;vendor:string;product:string;boardName:string|null};
export type VariableDescriptor={selector:string;typeName:string;kind:string;byteSize:number;signed:boolean|null;encoding:string|null;qualifiers:readonly string[];aliases:readonly string[];enumValues:readonly {value:bigint;name:string}[];elementCount:I64|null;elementKind:string|null;memberNames:readonly string[]};
export type RegisterDescriptor={selector:string;sizeBits:number;access:string|null;readAction:string|null;resetValue:bigint|null;resetMask:bigint|null;fields:readonly {name:string;bitOffset:number;bitWidth:number}[];sampleable:boolean;requiresAccessAcknowledgement:boolean};
export type VariableWatch={kind:"variable";expression:string};
export type RegisterWatch={kind:"register";registerPath:string};
export type WatchItem=VariableWatch|RegisterWatch;
export type WatchGroup={groupId:string;name:string;description:string;intervalMs:number;items:readonly WatchItem[];revision:I64;createdAtUtc:string;updatedAtUtc:string};
export type GroupPage={groups:readonly WatchGroup[];nextCursor:string|null;revision:string};
export type GroupTransfer={name:string;description:string;intervalMs:number;items:readonly WatchItem[]};
export type GroupImportDocument={schemaVersion:1;groups:readonly GroupTransfer[]};
export type MemoryRegionBinding={name:string;origin:number;length:number;attributes:string};
export type DebugFirmwareBinding={logicalProjectId:string;workspaceId:string;observationSessionId:string;flashSessionId:string;leaseId:string;probeId:string;targetDevice:string;debugTarget:string;buildId:string;elfSha256:string;elfSize:number;elfPath:string;inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;confirmedAtUtc:string;memoryRegions:readonly MemoryRegionBinding[]};
export type ObservationBinding={workspaceId:string;logicalProjectId:string;sessionId:string;probeId:string;targetDevice:string;physicalTarget:string;buildId:string;elfSha256:string;inputSnapshotSha256:string;gitHead:string;gitDirty:boolean;flashSessionId:string;leaseId:string;dwarfSha256:string;svdSha256:string|null};
export type KnownTypedValue={expression:string;typeName:string;value:JsonValue;rawHex:string;bitWidth:number};
export type SampleValue={watch:WatchItem;status:"OK";typedValue:JsonValue;code:null;definition:Readonly<Record<string,JsonValue>>|null}|{watch:WatchItem;status:"ERROR";typedValue:null;code:string;definition:Readonly<Record<string,JsonValue>>|null};
export type SampleBatch={binding:ObservationBinding;groupId:string;groupRevision:I64;runId:string;sequence:I64;scheduledUnixNs:I64;scheduledAtUtc:string;capturedUnixNs:I64;capturedAtUtc:string;latencyNs:I64;actualRateHz:number;subscriberDrops:I64;historyDrops:I64;deadlineDrops:I64;values:readonly SampleValue[]};
export type LiveEvent={eventId:I64;type:"hello";data:{protocol:"stm32-toolkit-monitor/1";toolkitVersion:string;monitorVersion:string;stateRevision:I64}}|{eventId:I64;type:"state";data:{stateRevision:I64;gap:boolean;status:MonitorStatus}}|{eventId:I64;type:"sample";data:{batch:SampleBatch;serviceSubscriberDrops:I64}}|{eventId:I64;type:"heartbeat";data:{stateRevision:I64;capturedAtUtc:string}};
export type ParsedLiveEnvelope={event:LiveEvent;subscriberDropped:I64};
export type HistoryBatchSlice=SampleBatch&{startOrdinal:I64;batchValueCount:I64};
export type HistoryPage={batches:readonly HistoryBatchSlice[];valueCount:I64;nextCursor:string|null;serializedBytes:I64};
export type HistoryQuery={startNs:I64;endNs:I64;limit?:number;cursor?:string;runId?:string;groupId?:string;selectorKind?:"variable"|"register";selector?:string};
export type ExportArtifact={exportId:string;format:"csv"|"jsonl";sha256:string;bytes:I64;valueCount:I64};
export type GroupDraft={sourceGroupId:string|null;expectedRevision:I64|null;name:string;description:string;intervalMs:number;items:readonly WatchItem[]};
export type CreateGroupRequest=GroupTransfer&{authorized:true};
export type UpdateGroupRequest={expectedRevision:I64;authorized:true;name?:string;description?:string;intervalMs?:number;items?:readonly WatchItem[]};
export type DeleteGroupRequest={expectedRevision:I64;authorized:true};
export type SamplerStartResult={groupId:string;groupRevision:I64;runId:string;intervalMs:number};
export type DownloadResult=ApiFailure|{ok:true;blob:Blob;filename:string;contentType:string};
export interface MonitorApi{status():Promise<ApiResult<MonitorStatus>>;probes():Promise<ApiResult<{probes:readonly ProbeInfo[]}>>;
 variables(query:string,cursor?:string):Promise<ApiResult<{items:readonly VariableDescriptor[];nextCursor:string|null}>>;registers(query:string,cursor?:string):Promise<ApiResult<{items:readonly RegisterDescriptor[];nextCursor:string|null}>>;
 groups(cursor?:string):Promise<ApiResult<GroupPage>>;createGroup(request:CreateGroupRequest):Promise<ApiResult<WatchGroup>>;updateGroup(groupId:string,request:UpdateGroupRequest):Promise<ApiResult<WatchGroup>>;deleteGroup(groupId:string,request:DeleteGroupRequest):Promise<ApiResult<{groupId:string;deleted:true}>>;importGroups(document:GroupImportDocument):Promise<ApiResult<readonly WatchGroup[]>>;
 connect(probeId:string):Promise<ApiResult<DebugFirmwareBinding>>;reconnect():Promise<ApiResult<DebugFirmwareBinding>>;release():Promise<ApiResult<{released:boolean}>>;
 start(groupId:string,expectedRevision:I64):Promise<ApiResult<SamplerStartResult>>;pause():Promise<ApiResult<{paused:boolean}>>;resume():Promise<ApiResult<{resumed:boolean}>>;stop():Promise<ApiResult<{stopped:boolean}>>;
 history(query:HistoryQuery):Promise<ApiResult<HistoryPage>>;createExport(startNs:I64,endNs:I64,format:"csv"|"jsonl"):Promise<ApiResult<ExportArtifact>>;exportStatus(exportId:string):Promise<ApiResult<ExportArtifact>>;downloadExport(exportId:string):Promise<DownloadResult>}

export type LiveHandlers={onEnvelope(value:ParsedLiveEnvelope):void;onClosed():void};
export type OpenLive=(afterEventId:I64|null,handlers:LiveHandlers)=>(()=>void);
export function openLive(origin:string,afterEventId:I64|null,handlers:LiveHandlers,socketFactory?:(url:string)=>WebSocket):()=>void;
export function groupImportGuard(value:unknown):GroupImportDocument;
export function selectedGroup(state:MonitorState):WatchGroup|null;
export function liveRows(state:MonitorState):readonly LiveRow[];
export function chartSeries(state:MonitorState):readonly DisplaySeries[];
```

Exact routes remain those in Design §8: bodyless reconnect/release/pause/resume/stop send neither body nor `Content-Type`; history uses required canonical decimal `startNs/endNs`; export JSON emits raw canonical integer tokens; callers never send workspace/session/project/root/target/ELF/SVD/address/backend/filename/path identity.

## Complete File Ownership Map

| Task | Files owned or bounded modification |
|---|---|
| 1 | `.gitignore`, `ui/index.html`, `package*.json`, all TS/Vite/Vitest/Playwright/ESLint configs, `src/env.d.ts`, `src/api/{contract,wire,client,live}.ts`, pure-stdlib support verifier, serializer fixture generator, API/toolchain tests, `test_ui_config.py` |
| 2 | `src/state/{model,reducer,selectors,group-transfer}.ts`, `src/catalog/shallow-selectors.ts`, `src/chart/{series,zoom}.ts`, pure state tests |
| 3 | `src/app.tsx`, `src/styles.css`, `src/chart/echarts.ts`, the fifteen explicitly listed `src/components/*.tsx` files in Task 3, and its nine named prop-view/a11y tests |
| 4 | `src/controller.ts`, `tests/controller.test.ts` |
| 5 | `src/bootstrap.ts`, `src/main.tsx`, bootstrap/main tests |
| 6 | `tests/coverage-branches.test.ts`, `tests/check-coverage.mjs`; test-only additions needed to prove every product file branch >=90% |
| 7 | `ui_assets.py`, bounded `auth.py/service.py/cli.py`, `test_ui_assets.py`, `test_auth.py`, `test_service.py`, `test_cli.py`, `test_launcher.py` |
| 8 | `scripts/verify-dist.mjs`, committed `ui_dist/**`, Monitor package-data metadata, bounded `service.py` default package-resource wiring, dist/package-boundary/installed-resource tests |
| 9 | exact active 0.5 version/runtime/Plugin/launcher/setup/Skill/README/phase/roadmap surfaces and their active tests |
| 10 | `tools/release/run_0502_windows_gates.ps1`, `test_0502_release_gate_controller.py` |
| 11 | `ui/e2e/fake_runtime.py`, `fixture.ts`, `fixture-contract.spec.ts`; fixture-only RPC/evidence guards remain local to `fixture.ts`, and e2e typecheck uses the frozen Task 1 config/contract without modifying Task 1 files |
| 12 | browser acceptance/security/isolation/accessibility/performance specs and test helpers; report is created only after `CODE_HEAD` outside the task commits |

Later tasks import the frozen interfaces above and do not restate or replace whole earlier modules. A later bounded modification is allowed only where the ownership map explicitly names an accepted-base release/version surface.

---

### Task 1: Accepted-Base Lossless Wire Adapter and Frontend Toolchain

**Files:**
- Modify: `.gitignore`.
- Create: `tools/stm32-monitor/ui/index.html`, `package.json`, `package-lock.json`, `tsconfig.json`, `tsconfig.e2e.json`, `vite.config.ts`, `vitest.config.ts`, `playwright.config.ts`, `eslint.config.js`.
- Create: `tools/stm32-monitor/ui/src/env.d.ts`, `src/api/contract.ts`, `src/api/wire.ts`, `src/api/client.ts`, `src/api/live.ts`.
- Create: `tools/stm32-monitor/ui/tests/setup.ts`, `tests/fixtures.ts`, `tests/contract.test.ts`, `tests/client.test.ts`, `tests/live.test.ts`, `tests/a11y.test.tsx`, `tests/check-coverage.mjs`.
- Create: `tools/stm32-monitor/ui/tests/generate_wire_fixture.py` (writes only to its explicit external output path).
- Create: `tools/stm32-monitor/ui/tests/verify_support.py` (pure stdlib; reads support and writes nothing).
- Create: `tools/stm32-monitor/tests/test_ui_config.py`.

**Interfaces:**
- Produces the frozen types above, `parseEnvelope<T>(text,operation,guard):ApiResult<T>`, `encodeJson(value):string`, `MonitorApi`, `createMonitorApi(fetchImpl,origin):MonitorApi`, `parseLiveEnvelope(text):ApiResult<ParsedLiveEnvelope>`, `liveUrl(origin,afterEventId):string`, and exact `openLive(origin,afterEventId,handlers,socketFactory?):()=>void`.
- Integer tokenization occurs once in `wire.ts`; guards consume token objects and choose `bigint` for every frozen `I64`, safe `number` only for bounded presentation/config values, and `number|bigint` for arbitrary typed JSON. No consumer field array exists outside `contract.ts`.
- `tests/fixtures.ts` exports concrete `statusResult()`, `watchGroup()`, `heartbeatEnvelope(eventId)`, `fakeClock()`, `fakeScheduler()`, `recordingDownload(trace)`, and `recordingApi(trace,status)` fixtures typed against the accepted DTOs; later tests import these names instead of relying on implicit harness globals.

- [ ] **Step 1: Verify support with stdlib, create the controlled venv/toolchain, then write runnable failing contract tests.** Create `verify_support.py` first and run it with `$python312` before pip/npm. Parse its sole JSON line into `$verified`; create `$taskRoot/wire-venv`, install `$verified.pythonRequirements` with its verified wheelhouse, and set current-source `PYTHONPATH` exactly to Monitor and Toolkit `src`. Create package/config/lock/test setup and `.gitignore` entries before importing absent product modules; exact pins include Preact, modular ECharts, TypeScript/Vite/Vitest/V8, Testing Library, axe, ESLint, and Playwright. The verifier core and commands are copy-complete:

```python
# tools/stm32-monitor/ui/tests/verify_support.py
import argparse,hashlib,json,os,re,secrets,stat
from pathlib import Path,PurePosixPath
parser=argparse.ArgumentParser();parser.add_argument("--support",type=Path,required=True);parser.add_argument("--package",type=Path);parser.add_argument("--package-lock",type=Path);args=parser.parse_args();root=args.support.absolute()
doc=json.loads((root/"support-manifest.json").read_text("utf-8"));rows=doc.get("files")
if doc.get("schemaVersion")!=1 or not isinstance(rows,list): raise SystemExit("support manifest is invalid")
seen=set()
def relative_name(value: object,label: str) -> PurePosixPath:
 if not isinstance(value,str): raise SystemExit(f"{label} is not a string")
 pure=PurePosixPath(value)
 if pure.is_absolute() or not pure.parts or ".." in pure.parts or "." in pure.parts or pure.as_posix()!=value: raise SystemExit(f"{label} is not canonical relative POSIX")
 return pure
def canonical(path: Path,label: str,kind: str) -> Path:
 path=path.absolute();resolved=path.resolve(strict=True)
 try: resolved.relative_to(root.resolve(strict=True)) if path!=root else None
 except ValueError: raise SystemExit(f"{label} escapes support root")
 current=Path(path.anchor)
 for part in path.parts[1:]:
  names={entry.name for entry in os.scandir(current)}
  if part not in names: raise SystemExit(f"{label} is not case-exact")
  current/=part;metadata=os.lstat(current)
  if stat.S_ISLNK(metadata.st_mode) or getattr(metadata,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400): raise SystemExit(f"{label} contains a redirect")
 if resolved!=path or (kind=="file" and not path.is_file()) or (kind=="dir" and not path.is_dir()): raise SystemExit(f"{label} is not canonical {kind}")
 return path
root=canonical(root,"SupportRoot","dir")
manifest=canonical(root/"support-manifest.json","support-manifest.json","file")
try: fd=os.open(manifest,os.O_WRONLY|os.O_APPEND)
except PermissionError: pass
else:
 os.close(fd);raise SystemExit("support manifest is writable")
probe=root/(".stm32tk-readonly-probe-"+secrets.token_hex(32))
if os.path.lexists(probe): raise SystemExit("readonly probe path already exists")
temporary=getattr(os,"O_TEMPORARY",None)
if temporary is None: raise SystemExit("O_TEMPORARY is unavailable; cannot prove support root is readonly")
try: fd=os.open(probe,os.O_CREAT|os.O_EXCL|os.O_WRONLY|temporary,0o600)
except PermissionError: pass
else:
 os.close(fd)
 try: probe.unlink()
 except OSError: pass
 raise SystemExit("support root is writable")
if os.path.lexists(probe): raise SystemExit("readonly probe left residue")
def member(value: object,label: str,kind: str) -> Path:
 pure=relative_name(value,label);return canonical(root.joinpath(*pure.parts),label,kind)
for row in rows:
 name=row["path"];pure=relative_name(name,"files.path")
 if name in seen: raise SystemExit("support member is duplicate")
 seen.add(name);path=member(name,"files.path","file")
 digest=hashlib.sha256(path.read_bytes()).hexdigest()
 if path.stat().st_size!=row["bytes"] or digest!=row["sha256"]: raise SystemExit("support member hash differs")
actual={path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}-{"support-manifest.json"}
if actual!=seen: raise SystemExit("support inventory is not exhaustive")
artifacts_root=member(doc.get("artifacts"),"artifacts","dir")
artifacts=doc.get("pythonArtifacts",{});required={"setuptools","wheel","build","pytest","pytest-cov","coverage","aiohttp","jsonschema","mcp","pyelftools","jinja2","pyocd"}
if set(artifacts)!=required or int(artifacts["setuptools"]["version"].split(".")[0])<68: raise SystemExit("Python artifact set is invalid")
for name,artifact in artifacts.items():
 path=member(artifact.get("path"),f"pythonArtifacts.{name}.path","file")
 try:path.relative_to(artifacts_root)
 except ValueError:raise SystemExit(f"python artifact escapes artifacts: {name}")
 if artifact["path"] not in seen: raise SystemExit(f"python artifact is not hashed: {name}")
requirements=[name+"=="+artifacts[name]["version"] for name in sorted(artifacts)]
for table in ("dependencies","devDependencies"):
 if not doc.get("nodePackages",{}).get(table) or any(re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?",value) is None for value in doc["nodePackages"][table].values()): raise SystemExit("npm versions are not exact")
wheelhouse=member(doc["wheelhouse"],"wheelhouse","dir");cache=member(doc["npmCache"],"npmCache","dir");browser=member(doc["chromiumExecutable"],"chromiumExecutable","file");node=member(doc["nodeExecutable"],"nodeExecutable","file");npm=member(doc["npmExecutable"],"npmExecutable","file")
for label,path in (("wheelhouse",wheelhouse),("npmCache",cache),("artifacts",artifacts_root)):
 if any(path==other or path in other.parents or other in path.parents for other in (wheelhouse,cache,artifacts_root) if other!=path):raise SystemExit(f"{label} overlaps another support root")
for label,value in (("chromiumExecutable",doc["chromiumExecutable"]),("nodeExecutable",doc["nodeExecutable"]),("npmExecutable",doc["npmExecutable"])):
 if value not in seen: raise SystemExit(f"{label} is not hashed in files")
tables=doc["nodePackages"]
if (args.package is None)!=(args.package_lock is None):raise SystemExit("package and package-lock must be supplied together")
if args.package is not None:
 package=json.loads(args.package.resolve(strict=True).read_text("utf-8"));lock=json.loads(args.package_lock.resolve(strict=True).read_text("utf-8"));root_lock=lock.get("packages",{}).get("")
 if not isinstance(root_lock,dict) or lock.get("lockfileVersion")!=3:raise SystemExit("package lock root is invalid")
 for table in ("dependencies","devDependencies"):
  if package.get(table,{})!=tables[table] or root_lock.get(table,{})!=tables[table]:raise SystemExit(f"{table} differs from support manifest")
 for name,version in {**tables["dependencies"],**tables["devDependencies"]}.items():
  if lock["packages"].get("node_modules/"+name,{}).get("version")!=version:raise SystemExit(f"locked package version differs: {name}")
by_name={row["path"]:row for row in rows}
tree_hash=hashlib.sha256("".join(f"{row['path']}\\0{row['bytes']}\\0{row['sha256']}\\n" for row in sorted(rows,key=lambda row:row["path"])).encode("utf-8")).hexdigest()
print(json.dumps({"wheelhouse":str(wheelhouse),"npmCache":str(cache),"artifacts":str(artifacts_root),"browser":str(browser),"node":str(node),"npm":str(npm),"nodeSha256":by_name[doc["nodeExecutable"]]["sha256"],"npmSha256":by_name[doc["npmExecutable"]]["sha256"],"nodeVersion":doc["nodeVersion"],"npmVersion":doc["npmVersion"],"nodePackages":tables,"auditCache":bool(doc.get("npmAuditCache")),"pythonRequirements":requirements,"supportManifestSha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),"supportTreeSha256":tree_hash},separators=(",",":"),sort_keys=True))
```

```powershell
$supportVerifier=(Resolve-Path -LiteralPath (Join-Path $repoRoot 'tools\stm32-monitor\ui\tests\verify_support.py')).Path
function Assert-0502Support([string[]]$PackageArgs=@()) {
  $result=(& $python312 $supportVerifier --support $supportRoot @PackageArgs|Select-Object -Last 1|ConvertFrom-Json)
  if($LASTEXITCODE-ne0){throw 'support verification failed'}
  if($script:SupportManifestSha256){if([string]$result.supportManifestSha256-cne$script:SupportManifestSha256 -or [string]$result.supportTreeSha256-cne$script:SupportTreeSha256){throw 'support manifest or source tree changed'}}
  return $result
}
function New-0502NpmWorkingCache($SourceCache) {
  $taskRootPath=(Resolve-Path -LiteralPath $taskRoot -ErrorAction Stop).Path;$taskRootItem=Get-Item -LiteralPath $taskRootPath -Force
  if(-not[IO.Path]::IsPathRooted($taskRootPath) -or $taskRootPath-cne[IO.Path]::GetFullPath($taskRoot) -or ($taskRootItem.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw 'task root must be an existing canonical non-reparse external directory'}
  $destination=Join-Path $taskRootPath 'npm-cache-working'
  if(Test-Path -LiteralPath $destination){$existing=(Resolve-Path -LiteralPath $destination -ErrorAction Stop).Path;if($existing-cne$destination -or ((Get-Item -LiteralPath $existing -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw 'existing npm working cache escapes or redirects'};Remove-Item -LiteralPath $existing -Recurse -Force -ErrorAction Stop}
  New-Item -ItemType Directory -Path $destination -ErrorAction Stop|Out-Null
  $rootItem=Get-Item -LiteralPath $destination -Force
  if(($rootItem.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0 -or @((Get-ChildItem -LiteralPath $destination -Force)).Count-ne0){throw 'npm working cache is not a new empty ordinary directory'}
  Get-ChildItem -LiteralPath $SourceCache -Force|ForEach-Object{Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force -ErrorAction Stop}
  $members=@(Get-Item -LiteralPath $destination -Force);$members+=@(Get-ChildItem -LiteralPath $destination -Force -Recurse)
  if(@($members|Where-Object{(($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)}).Count-ne0){throw 'npm working cache contains a reparse point'}
  foreach($member in $members){$attributes=[IO.FileAttributes]$member.Attributes;[IO.File]::SetAttributes($member.FullName,[IO.FileAttributes](([int]$attributes) -band (-bnot [int][IO.FileAttributes]::ReadOnly)))}
  $members=@(Get-Item -LiteralPath $destination -Force);$members+=@(Get-ChildItem -LiteralPath $destination -Force -Recurse)
  if(@($members|Where-Object{(($_.Attributes -band ([IO.FileAttributes]::ReadOnly -bor [IO.FileAttributes]::ReparsePoint)) -ne 0)}).Count-ne0){throw 'npm working cache retains ReadOnly or reparse attributes'}
  return (Resolve-Path -LiteralPath $destination).Path
}
function Invoke-0502NpmPhase([scriptblock]$Command,[string]$Failure) {
  Assert-0502Support|Out-Null
  & $Command
  if($LASTEXITCODE-ne0){throw $Failure}
  Assert-0502Support|Out-Null
}
$verified=Assert-0502Support
$script:SupportManifestSha256=[string]$verified.supportManifestSha256;$script:SupportTreeSha256=[string]$verified.supportTreeSha256
$npmWorkingCache=New-0502NpmWorkingCache ([string]$verified.npmCache)
Assert-0502Support|Out-Null
if((Resolve-Path -LiteralPath $node).Path-cne[string]$verified.node -or (Resolve-Path -LiteralPath $npm).Path-cne[string]$verified.npm){throw 'selected Node/npm do not match verified support executables'}
$actualNodeVersion=(& $node --version).Trim();if($LASTEXITCODE-ne0 -or $actualNodeVersion-cne[string]$verified.nodeVersion){throw 'verified Node version differs'}
$actualNpmVersion=(& $npm --version).Trim();if($LASTEXITCODE-ne0 -or $actualNpmVersion-cne[string]$verified.npmVersion){throw 'verified npm version differs'}
$wireVenv=Join-Path $taskRoot 'wire-venv';& $python312 -m venv $wireVenv;if($LASTEXITCODE-ne0){throw 'wire venv failed'}
$fixturePython=(Resolve-Path -LiteralPath (Join-Path $wireVenv 'Scripts\python.exe')).Path
& $fixturePython -m pip install --no-index --find-links ([string]$verified.wheelhouse) @($verified.pythonRequirements);if($LASTEXITCODE-ne0){throw 'wire dependencies failed'}
$env:PYTHONPATH=(Join-Path $repoRoot 'tools\stm32-monitor\src')+[IO.Path]::PathSeparator+(Join-Path $repoRoot 'tools\stm32-toolkit\src')
Push-Location $uiRoot;try{Invoke-0502NpmPhase {& $npm install --offline --cache $npmWorkingCache --package-lock-only --ignore-scripts} 'offline lock creation failed';Invoke-0502NpmPhase {& $npm ci --offline --cache $npmWorkingCache} 'offline npm ci failed'}finally{Pop-Location}
$verified=Assert-0502Support @('--package',(Join-Path $uiRoot 'package.json'),'--package-lock',(Join-Path $uiRoot 'package-lock.json'))
```

```ts
// tests/contract.test.ts
import {describe,expect,it} from "vitest";
import {parseLiveEnvelope} from "../src/api/live";
import {encodeJson} from "../src/api/wire";
const envelope=(data:string)=>`{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","ok":true,"operation":"monitor.live","code":"OK","message":"","data":${data},"details":{"subscriberDropped":9223372036854775807}}`;
describe("accepted-base lossless live envelope",()=>{
  it("keeps every identity and counter outside Number",()=>{
    const result=parseLiveEnvelope(envelope(`{"eventId":9223372036854775807,"type":"hello","data":{"protocol":"stm32-toolkit-monitor/1","toolkitVersion":"0.4.0","monitorVersion":"0.4.0","stateRevision":9223372036854775807}}`));
    expect(result.ok).toBe(true);
    if(result.ok){expect(result.data.event.eventId).toBe(9223372036854775807n);expect(result.data.subscriberDropped).toBe(9223372036854775807n);}
    expect(encodeJson({startNs:9223372036854775806n,endNs:9223372036854775807n})).toBe('{"startNs":9223372036854775806,"endNs":9223372036854775807}');
  });
});
```

```python
# tools/stm32-monitor/tests/test_ui_config.py
import json
import re
from pathlib import Path

def test_ui_scaffold_is_private_and_exactly_pinned():
    root = Path(__file__).parents[1] / "ui"
    package = json.loads((root / "package.json").read_text("utf-8"))
    assert package["private"] is True and package["type"] == "module"
    assert all(re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", v)
               for table in (package["dependencies"], package["devDependencies"])
               for v in table.values())

def test_ui_green_source_names_real_live_envelope_and_lossless_ints():
    root = Path(__file__).parents[1] / "ui"
    contract = (root / "src/api/contract.ts").read_text("utf-8")
    assert "type I64=bigint" in contract and "eventId:I64" in contract
    live = (root / "src/api/live.ts").read_text("utf-8")
    assert 'parseEnvelope(text,"monitor.live",liveEventGuard)' in live.replace(" ", "")
```

```python
# tools/stm32-monitor/ui/tests/generate_wire_fixture.py
import argparse
import json
from pathlib import Path
from stm32_monitor.models import SampleValue,WatchItem
from stm32_monitor.protocol import success
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding

parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--project",type=Path,required=True);args=parser.parse_args()
binding=DebugFirmwareBinding(logical_project_id="project",workspace_id="workspace",observation_session_id="observe",flash_session_id="flash",lease_id="lease",probe_id="probe",target_device="STM32F407VG",debug_target="cortex_m",build_id="0"*64,elf_sha256="1"*64,elf_size=4096,elf_path="build/fw.elf",input_snapshot_sha256="2"*64,git_head="a"*40,git_dirty=False,confirmed_at_utc="2026-08-10T00:00:00.000000Z",memory_regions=(MemoryRegionBinding("FLASH",0x08000000,0x10000,"rx"),),project_root=args.project.resolve(strict=True))
sample=SampleValue(WatchItem.variable("x"),"OK",typed_value={"vendorShape":[1,{"nested":True}]})
connect_json=json.dumps(success("monitor.probe.connect",binding.to_dict()).to_dict(),ensure_ascii=False,separators=(",",":"))
sample_json=json.dumps(sample.to_dict(),ensure_ascii=False,separators=(",",":"))
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text('{"connect":'+connect_json+',"sample":'+sample_json+'}',"utf-8")
```

- [ ] **Step 2: Run RED.** With the exact Step 1 `PYTHONPATH`, run `& $fixturePython tools/stm32-monitor/ui/tests/generate_wire_fixture.py --output (Join-Path $taskRoot 'accepted-wire.json') --project $repoRoot`; set `STM32_MONITOR_WIRE_FIXTURE` to that absolute file; run only `& $fixturePython -m pytest tools/stm32-monitor/tests/test_ui_config.py::test_ui_scaffold_is_private_and_exactly_pinned -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'pytest-scaffold')`; from `$uiRoot` run `& $npm run test -- tests/contract.test.ts tests/client.test.ts tests/live.test.ts`. Expected: verifier/venv/generator/scaffold PASS and Vitest fails only on absent `src/api/contract.ts`, `wire.ts`, `client.ts`, and `live.ts`; the GREEN-only source assertion is deliberately not selected during RED.

- [ ] **Step 3: Implement the one wire authority after the runnable RED.** Retain the manifest-pinned scaffold from Step 1; configs enable `strict`, `noEmit`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, jsdom, V8 `perFile:true`, deterministic manifest/no sourcemap, and Chromium 1280x720/1024x768 plus named deferred Firefox/WebKit projects. `package.json` scripts are exactly `typecheck`, `typecheck:e2e`, `lint`, `test`, `test:coverage`, `coverage:check`, `test:a11y`, `build`, `verify:dist`, `test:e2e:windows`, and `test:e2e:performance`. Implement the compilable tokenizer/encoder core below and all direct-property guards in `contract.ts`:

```ts
// src/api/wire.ts
export class IntegerToken{constructor(readonly decimal:string){}}
const integer=/^-?(?:0|[1-9]\d*)$/;
export function parseLossless(text:string):unknown{
  let sentinel="__stm32_i64__";while(text.includes(sentinel))sentinel+="_";
  let out="",index=0,inString=false,escaped=false;
  while(index<text.length){const c=text[index]!;
    if(inString){out+=c;index++;if(escaped){escaped=false;}else if(c==="\\"){escaped=true;}else if(c==='"'){inString=false;}continue;}
    if(c==='"'){inString=true;out+=c;index++;continue;}
    if(c==='-'||(c>='0'&&c<='9')){let end=index+1;while(end<text.length&&/[0-9.eE+-]/.test(text[end]!))end++;
      const token=text.slice(index,end);out+=integer.test(token)?JSON.stringify(sentinel+token):token;index=end;continue;}
    out+=c;index++;
  }
  return JSON.parse(out,(_key,value)=>typeof value==="string"&&value.startsWith(sentinel)
    ?new IntegerToken(value.slice(sentinel.length)):value);
}
export const i64=(value:unknown):bigint=>{if(!(value instanceof IntegerToken)||!integer.test(value.decimal))throw new Error("expected integer");const result=BigInt(value.decimal);if(result<-(1n<<63n)||result>(1n<<63n)-1n)throw new Error("integer outside signed-int64");return result;};
export function encodeJson(value:unknown):string{
  if(value===null)return"null";if(typeof value==="bigint")return value.toString(10);
  if(typeof value==="string"||typeof value==="boolean")return JSON.stringify(value);
  if(typeof value==="number"){if(!Number.isFinite(value))throw new Error("non-finite JSON number");return JSON.stringify(value);}
  if(Array.isArray(value))return`[${value.map(encodeJson).join(",")}]`;
  if(typeof value==="object")return`{${Object.keys(value).filter(key=>Reflect.get(value,key)!==undefined).map(key=>`${JSON.stringify(key)}:${encodeJson(Reflect.get(value,key))}`).join(",")}}`;
  throw new Error("unsupported JSON value");
}
```

`contract.ts` implements one guard per frozen DTO by direct property access, validates exact object shape at that single boundary, validates the envelope's nine fields/operation/code, and exposes all route guards. Connect/reconnect use `debugFirmwareBindingGuard`, including `observationSessionId`, `debugTarget`, `elfSize`, `elfPath`, `confirmedAtUtc`, and `memoryRegions`; they never reuse `ObservationBinding`. `sampleValueGuard` leaves successful `typedValue` as `JsonValue` and `knownTypedValue(value):KnownTypedValue|null` is only an optional display refinement. `stop` accepts both `{"stopped":false}` and `{"stopped":true}`. `client.ts` uses `credentials:"same-origin"`, exact same-origin `Origin` only on mutations/bootstrap, absent body/Content-Type for bodyless POST, and `encodeJson` for bigint bodies. `live.ts` calls `parseEnvelope(text,"monitor.live",liveEventGuard)`, reads `details.subscriberDropped`, never sends a client message, and exports the exact `openLive` signature; replay is `afterEventId=${eventId.toString(10)}`.

- [ ] **Step 4: Run GREEN and determinism checks.** Execute this exact fail-fast PowerShell; every cache, source root, venv, nodeid, and output is explicit:

```powershell
$verified=Assert-0502Support @('--package',(Join-Path $uiRoot 'package.json'),'--package-lock',(Join-Path $uiRoot 'package-lock.json'))
if(-not(Test-Path -LiteralPath $npmWorkingCache)){throw 'Task 1 npm working cache is absent'}
if(((Get-Item -LiteralPath $npmWorkingCache -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw 'Task 1 npm working cache is a reparse point'}
if((Resolve-Path -LiteralPath $node).Path-cne[string]$verified.node -or (Resolve-Path -LiteralPath $npm).Path-cne[string]$verified.npm){throw 'Node/npm identity differs'}
if((& $node --version).Trim()-cne[string]$verified.nodeVersion -or (& $npm --version).Trim()-cne[string]$verified.npmVersion){throw 'Node/npm version differs'}
if((Get-FileHash -LiteralPath $node -Algorithm SHA256).Hash.ToLowerInvariant()-cne[string]$verified.nodeSha256 -or (Get-FileHash -LiteralPath $npm -Algorithm SHA256).Hash.ToLowerInvariant()-cne[string]$verified.npmSha256){throw 'Node/npm byte identity differs'}
$env:PYTHONPATH=(Join-Path $repoRoot 'tools\stm32-monitor\src')+[IO.Path]::PathSeparator+(Join-Path $repoRoot 'tools\stm32-toolkit\src');$env:PYTHONDONTWRITEBYTECODE='1';$env:PYTHONPYCACHEPREFIX=Join-Path $taskRoot 'wire-pycache'
$wire310=Join-Path $taskRoot 'wire-venv-310';& $python310 -m venv $wire310;if($LASTEXITCODE-ne0){throw '310 venv failed'}
$fixturePython310=(Resolve-Path -LiteralPath (Join-Path $wire310 'Scripts\python.exe')).Path;$fixturePython312=$fixturePython
& $fixturePython310 -m pip install --no-index --find-links ([string]$verified.wheelhouse) @($verified.pythonRequirements);if($LASTEXITCODE-ne0){throw '310 dependency install failed'}
Push-Location $uiRoot;try{Invoke-0502NpmPhase {& $npm ci --offline --cache $npmWorkingCache} 'npm ci failed';& $npm run typecheck;if($LASTEXITCODE-ne0){throw 'typecheck failed'};& $npm run typecheck:e2e;if($LASTEXITCODE-ne0){throw 'e2e typecheck failed'};& $npm run lint;if($LASTEXITCODE-ne0){throw 'lint failed'}}finally{Pop-Location}
$wire310Json=Join-Path $taskRoot 'accepted-wire-310.json';$wire312Json=Join-Path $taskRoot 'accepted-wire-312.json'
& $fixturePython310 tools/stm32-monitor/ui/tests/generate_wire_fixture.py --output $wire310Json --project $repoRoot;if($LASTEXITCODE-ne0){throw '310 fixture failed'}
& $fixturePython312 tools/stm32-monitor/ui/tests/generate_wire_fixture.py --output $wire312Json --project $repoRoot;if($LASTEXITCODE-ne0){throw '312 fixture failed'}
if((Get-FileHash $wire310Json -Algorithm SHA256).Hash -cne (Get-FileHash $wire312Json -Algorithm SHA256).Hash){throw 'serializer fixture differs by Python version'}
foreach($entry in @(@('310',$fixturePython310,$wire310Json),@('312',$fixturePython312,$wire312Json))){$minor=$entry[0];$py=$entry[1];$env:STM32_MONITOR_WIRE_FIXTURE=$entry[2];& $py -m pytest tools/stm32-monitor/tests/test_ui_config.py::test_ui_scaffold_is_private_and_exactly_pinned tools/stm32-monitor/tests/test_ui_config.py::test_ui_green_source_names_real_live_envelope_and_lossless_ints -q -p no:cacheprovider --basetemp (Join-Path $taskRoot ('ui-config-'+$minor));if($LASTEXITCODE-ne0){throw "Python $minor config tests failed"};Push-Location $uiRoot;try{& $npm run test -- tests/contract.test.ts tests/client.test.ts tests/live.test.ts;if($LASTEXITCODE-ne0){throw "Vitest $minor failed"}}finally{Pop-Location}}
Push-Location $uiRoot;try{Invoke-0502NpmPhase {& $npm ci --offline --cache $npmWorkingCache} 'second npm ci failed'}finally{Pop-Location}
& $git -C $repoRoot diff --exit-code -- tools/stm32-monitor/ui/package-lock.json;if($LASTEXITCODE-ne0){throw 'lockfile is nondeterministic'}
Assert-0502Support @('--package',(Join-Path $uiRoot 'package.json'),'--package-lock',(Join-Path $uiRoot 'package-lock.json'))|Out-Null
```

Expected: every command PASS with serializer parity, no unverified dependency source, and identical support-manifest/source-tree hashes before cache copy, around every npm phase, and at the final check; only `$taskRoot\npm-cache-working` is mutated by npm.

- [ ] **Step 5: Commit Task 1.** Call `Commit-0502Task 'feat(STM32TK-0502): add lossless monitor wire adapter' @('.gitignore','tools/stm32-monitor/ui/index.html','tools/stm32-monitor/ui/package.json','tools/stm32-monitor/ui/package-lock.json','tools/stm32-monitor/ui/tsconfig.json','tools/stm32-monitor/ui/tsconfig.e2e.json','tools/stm32-monitor/ui/vite.config.ts','tools/stm32-monitor/ui/vitest.config.ts','tools/stm32-monitor/ui/playwright.config.ts','tools/stm32-monitor/ui/eslint.config.js','tools/stm32-monitor/ui/src/env.d.ts','tools/stm32-monitor/ui/src/api/contract.ts','tools/stm32-monitor/ui/src/api/wire.ts','tools/stm32-monitor/ui/src/api/client.ts','tools/stm32-monitor/ui/src/api/live.ts','tools/stm32-monitor/ui/tests/setup.ts','tools/stm32-monitor/ui/tests/fixtures.ts','tools/stm32-monitor/ui/tests/contract.test.ts','tools/stm32-monitor/ui/tests/client.test.ts','tools/stm32-monitor/ui/tests/live.test.ts','tools/stm32-monitor/ui/tests/a11y.test.tsx','tools/stm32-monitor/ui/tests/check-coverage.mjs','tools/stm32-monitor/ui/tests/generate_wire_fixture.py','tools/stm32-monitor/ui/tests/verify_support.py','tools/stm32-monitor/tests/test_ui_config.py')`.

### Task 2: Pure Authoritative State, Series, Catalog, and Group Transfer

**Files:**
- Create: `tools/stm32-monitor/ui/src/state/model.ts`, `reducer.ts`, `selectors.ts`, `group-transfer.ts`.
- Create: `tools/stm32-monitor/ui/src/catalog/shallow-selectors.ts`, `src/chart/series.ts`, `src/chart/zoom.ts`.
- Create: `tools/stm32-monitor/ui/tests/reducer.test.ts`, `series.test.ts`, `catalog.test.ts`, `group-transfer.test.ts`, `zoom.test.ts`.

**Interfaces:**
- Produces `MonitorState`, the closed `MonitorAction` union, `initialState`, `reducer`, `reduceAcceptedLiveEnvelope`, `appendAuthoritativeSample`, `appendContinuityGap`, `addSampleDropDeltas`, `projectHistoryPage(page,groups,selected):HistoryProjection`, `watchKey`, `deriveMember`, `deriveElement`, `toGroupImportDocument`, `parseGroupImportDocument`, `previewGroupImport`, `ZoomRange`, `selectedGroup(state):WatchGroup|null`, `liveRows(state):readonly LiveRow[]`, and `chartSeries(state):readonly DisplaySeries[]`.
- `RequestScope` is the finite union `initial|status|probes|probe.connect|probe.reconnect|probe.release|catalog.variables|catalog.registers|groups.create|groups.update|groups.delete|groups.import|sampling.start|sampling.pause|sampling.resume|sampling.stop|history|export.create|export.status|export.download`; pending entries contain a local bigint request ID.
- State/live identity uses workspace/session + binding identity + bindingEpoch + runId. `lastAcceptedEventId` rejects replay/duplicate events before any drop mutation. For each newly accepted `sample` event, `batch.subscriberDrops`, `batch.historyDrops`, `batch.deadlineDrops`, and `serviceSubscriberDrops` are bigint **deltas** added once to `pendingDropDeltas`; zero adds nothing and never decreases a displayed total. `status.loaded` replaces authoritative totals and zeros pending deltas. Outer envelope `details.subscriberDropped>0` never changes a counter: it inserts one null continuity gap and requests status refresh. Old state revision, wrong identity samples, stale catalog responses, and old command results are ignored.

- [ ] **Step 1: Write failing pure tests for every state transition.** Cover initial authoritative load, lower `stateRevision`, identity mismatch stale, event replay ordering, gap/reset, request lifecycle traces, no stale catalog cursor, complete group draft order/CAS/import preview/export stripping, error/null gap behavior, trend reset, max 8x600, and zoom reset. Include these non-negotiable tests:

```ts
it("preserves prior row and appends a null chart gap for ERROR",()=>{
  const one=appendAuthoritativeSample(emptyLive(),sampleBatch(1n,"OK",12.5),group(),new Set(["variable:x"]));
  const two=appendAuthoritativeSample(one,sampleBatch(2n,"ERROR",null),group(),new Set(["variable:x"]));
  expect(two.rows.get("variable:x")?.displayValue).toBe("12.5");
  expect(two.series.get("variable:x")?.map(p=>p.value)).toEqual([12.5,null]);
});
it("never accepts a catalog page for an obsolete binding cursor",()=>{
  const requested=reducer(connectedState(4n),{type:"catalog.requested",catalog:"variables",query:"x",bindingKey:"w/s/p/4",cursor:null});
  const rebound={...requested,status:{...requested.status!,sampling:{...requested.status!.sampling,bindingEpoch:5n}}};
  expect(reducer(rebound,{type:"catalog.loaded",catalog:"variables",query:"x",bindingKey:"w/s/p/4",cursor:null,items:[],nextCursor:"old"})).toEqual(rebound);
});
it("adds sample deltas once, never decreases on zero, and rebases from status",()=>{
 const event=sampleEnvelope({eventId:9n,batchDrops:{subscriber:2n,history:3n,deadline:4n},service:5n,outer:7n});const once=reduceAcceptedLiveEnvelope(runningState(),event);const replay=reduceAcceptedLiveEnvelope(once,event);
 expect(once.live.pendingDropDeltas).toEqual({subscriber:2n,history:3n,deadline:4n,service:5n});expect(replay).toEqual(once);expect(lastPoints(once)).toEqual([null]);
 const zero=reduceAcceptedLiveEnvelope(once,sampleEnvelope({eventId:10n,batchDrops:{subscriber:0n,history:0n,deadline:0n},service:0n,outer:0n}));expect(displayDropTotals(zero.live)).toEqual(displayDropTotals(once.live));
 const rebased=reducer(zero,{type:"status.loaded",status:statusWithDrops(11n,12n,13n,14n)});
 expect(rebased.live.authoritativeDrops).toEqual({subscriber:11n,history:12n,deadline:13n,service:14n});expect(rebased.live.pendingDropDeltas).toEqual({subscriber:0n,history:0n,deadline:0n,service:0n});
});
it("projects a HistoryPage into the same bounded 8 by 600 model",()=>{
 const projection=projectHistoryPage(historyPage(601,8),new Map([[GROUP.groupId,GROUP]]),new Set(GROUP.items.slice(0,8).map(watchKey)));
 expect(projection.series.size).toBe(8);for(const points of projection.series.values())expect(points).toHaveLength(600);
 expect(projection.rows.map(row=>row.startOrdinal)[0]).toBe(1n);
});
```

- [ ] **Step 2: Run RED.** From `$uiRoot` run `& $npm run test -- tests/reducer.test.ts tests/series.test.ts tests/catalog.test.ts tests/group-transfer.test.ts tests/zoom.test.ts`. Expected: FAIL because the pure state modules do not exist.

- [ ] **Step 3: Implement the closed reducer and pure helpers.** Use bigint comparisons for every authoritative counter. `appendAuthoritativeSample` visits authoritative group order; selected series always receive one point per batch, with `null` for `ERROR`, null, bigint, non-number, or non-finite typed value. Keep the most recent 600 points. The exact core is:

```ts
// src/chart/series.ts
export type ChartPoint={capturedAtUtc:string;capturedUnixNs:bigint;value:number|null;segment:bigint};
export type LiveRow={watch:WatchItem;displayValue:string;rawHex:string|null;typeName:string|null;capturedAtUtc:string;trend:"up"|"down"|"flat"|"none";errorCode:string|null};
export function appendAuthoritativeSample(live:LiveState,batch:SampleBatch,group:WatchGroup,selected:ReadonlySet<string>):LiveState{
  const incoming=new Map(batch.values.map(value=>[watchKey(value.watch),value]));
  const rows=new Map(live.rows),series=new Map(live.series);
  for(const watch of group.items){const key=watchKey(watch),value=incoming.get(key),previous=rows.get(key);
    if(value?.status==="OK")rows.set(key,rowFromOk(value,batch.capturedAtUtc,previous));
    else if(value?.status==="ERROR")rows.set(key,{...(previous??emptyRow(watch)),capturedAtUtc:batch.capturedAtUtc,errorCode:value.code,trend:"none"});
    if(selected.has(key)){const known=value?.status==="OK"?knownTypedValue(value.typedValue):null;const numeric=known!==null&&typeof known.value==="number"&&Number.isFinite(known.value)?known.value:null;
      const points=[...(series.get(key)??[]),{capturedAtUtc:batch.capturedAtUtc,capturedUnixNs:batch.capturedUnixNs,value:numeric,segment:live.segment}];series.set(key,points.slice(-600));}
  }
  return {...live,rows,series,lastSequence:batch.sequence,actualRateHz:batch.actualRateHz,latencyNs:batch.latencyNs};
}
export function appendContinuityGap(live:LiveState):LiveState{
 const series=new Map(live.series);for(const key of live.selectedSeries){const points=series.get(key)??[];series.set(key,[...points,{capturedAtUtc:"",capturedUnixNs:0n,value:null,segment:live.segment}].slice(-600));}
 return {...live,series};
}
export const addSampleDropDeltas=(live:LiveState,batch:SampleBatch,service:bigint):LiveState=>({...live,pendingDropDeltas:{subscriber:live.pendingDropDeltas.subscriber+batch.subscriberDrops,history:live.pendingDropDeltas.history+batch.historyDrops,deadline:live.pendingDropDeltas.deadline+batch.deadlineDrops,service:live.pendingDropDeltas.service+service}});
export const displayDropTotals=(live:LiveState):DropTotals=>({subscriber:live.authoritativeDrops.subscriber+live.pendingDropDeltas.subscriber,history:live.authoritativeDrops.history+live.pendingDropDeltas.history,deadline:live.authoritativeDrops.deadline+live.pendingDropDeltas.deadline,service:live.authoritativeDrops.service+live.pendingDropDeltas.service});
export function projectHistoryPage(page:HistoryPage,groups:ReadonlyMap<string,WatchGroup>,selected:ReadonlySet<string>):HistoryProjection{
 const limited=new Set([...selected].slice(0,8)),series=new Map<string,ChartPoint[]>(),rows:HistoryRow[]=[];
 for(const batch of page.batches){const group=groups.get(batch.groupId);if(group===undefined)continue;rows.push({runId:batch.runId,sequence:batch.sequence,startOrdinal:batch.startOrdinal,batchValueCount:batch.batchValueCount,capturedAtUtc:batch.capturedAtUtc,values:batch.values});
  const incoming=new Map(batch.values.map(value=>[watchKey(value.watch),value]));for(const watch of group.items){const key=watchKey(watch);if(!limited.has(key))continue;const value=incoming.get(key),known=value?.status==="OK"?knownTypedValue(value.typedValue):null,numeric=known!==null&&typeof known.value==="number"&&Number.isFinite(known.value)?known.value:null;const points=series.get(key)??[];series.set(key,[...points,{capturedAtUtc:batch.capturedAtUtc,capturedUnixNs:batch.capturedUnixNs,value:numeric,segment:0n}].slice(-600));}}
 return {rows,series};
}
```

```ts
// src/state/selectors.ts
export const selectedGroup=(state:MonitorState):WatchGroup|null=>state.selectedGroupId===null?null:state.groups.find(group=>group.groupId===state.selectedGroupId)??null;
export const liveRows=(state:MonitorState):readonly LiveRow[]=>{const group=selectedGroup(state);return group===null?[]:group.items.map(watch=>state.live.rows.get(watchKey(watch))??emptyRow(watch));};
export const chartSeries=(state:MonitorState):readonly DisplaySeries[]=>[...state.selectedSeries].slice(0,8).map(key=>({key,label:key,points:state.live.series.get(key)??[]}));
```

```ts
// src/state/group-transfer.ts
export const toGroupImportDocument=(groups:readonly WatchGroup[]):GroupImportDocument=>({schemaVersion:1,groups:groups.map(({name,description,intervalMs,items})=>({name,description,intervalMs,items:[...items]}))});
export function parseGroupImportDocument(value:unknown):ApiResult<GroupImportDocument>{
  try{const document=groupImportGuard(value);return{ok:true,data:document};}
  catch{return{ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import document is invalid"};}
}
export const previewGroupImport=(document:GroupImportDocument,current:readonly WatchGroup[]):ImportPreview=>({groupCount:document.groups.length,itemCount:document.groups.reduce((n,g)=>n+g.items.length,0),conflictingNames:document.groups.map(g=>g.name.normalize("NFC").toLocaleLowerCase()).filter(name=>current.some(g=>g.name.normalize("NFC").toLocaleLowerCase()===name))});
```

`reduceAcceptedLiveEnvelope` first rejects `eventId <= lastAcceptedEventId`; only then records the ID. For `sample`, it calls `addSampleDropDeltas` once before appending values. Independently, positive outer `subscriberDropped` calls `appendContinuityGap` but touches no counter; `state.gap` also adds a gap. `status.loaded` atomically rebases `authoritativeDrops` from `status.sampling` and zeros all `pendingDropDeltas`. `history.loaded` calls `projectHistoryPage`; no view parses batches. Remaining reducer behavior stays closed as listed above.

- [ ] **Step 4: Run GREEN and mutation-proof checks.** From `$uiRoot` run `& $npm run test -- tests/reducer.test.ts tests/series.test.ts tests/catalog.test.ts tests/group-transfer.test.ts tests/zoom.test.ts`; run `& $npm run typecheck`; run `& $npm run lint`; then run `& $npm run test -- tests/zoom.test.ts tests/group-transfer.test.ts tests/catalog.test.ts tests/series.test.ts tests/reducer.test.ts`. Expected: every command PASS with max-int64 CAS, null gaps, 8×600 bounds, stripped exports, history projection, drop rebase/dedup, and stale-cursor behavior asserted.

- [ ] **Step 5: Commit Task 2.** Call `Commit-0502Task 'feat(STM32TK-0502): add authoritative monitor state' @('tools/stm32-monitor/ui/src/state/model.ts','tools/stm32-monitor/ui/src/state/reducer.ts','tools/stm32-monitor/ui/src/state/selectors.ts','tools/stm32-monitor/ui/src/state/group-transfer.ts','tools/stm32-monitor/ui/src/catalog/shallow-selectors.ts','tools/stm32-monitor/ui/src/chart/series.ts','tools/stm32-monitor/ui/src/chart/zoom.ts','tools/stm32-monitor/ui/tests/reducer.test.ts','tools/stm32-monitor/ui/tests/series.test.ts','tools/stm32-monitor/ui/tests/catalog.test.ts','tools/stm32-monitor/ui/tests/group-transfer.test.ts','tools/stm32-monitor/ui/tests/zoom.test.ts')`.

### Task 3: Prop-Only Views, Components, Chart, and Complete Group UX

**Files:**
- Create: `tools/stm32-monitor/ui/src/app.tsx`, `src/styles.css`, `src/chart/echarts.ts`.
- Create: `tools/stm32-monitor/ui/src/components/IdentityBar.tsx`, `ProbePanel.tsx`, `CatalogPanel.tsx`, `GroupPanel.tsx`, `GroupImportDialog.tsx`, `SamplingControls.tsx`, `LiveTable.tsx`, `LiveChart.tsx`, `ChartZoomControls.tsx`, `StatusStrip.tsx`, `NoticeRegion.tsx`, `HistoryPanel.tsx`, `ExportPanel.tsx`.
- Create: `tools/stm32-monitor/ui/tests/app.test.tsx`, `identity-probe.test.tsx`, `catalog-view.test.tsx`, `group-view.test.tsx`, `sampling-view.test.tsx`, `live-view.test.tsx`, `history-export-view.test.tsx`, `chart-view.test.tsx`; replace the Task 1 axe smoke body in `tests/a11y.test.tsx` with complete view states.

**Interfaces:**
- Produces `AppViewProps` and callback-only component prop types. `App` receives complete state plus callbacks; no view imports `client.ts`, `live.ts`, `controller.ts`, `bootstrap.ts`, or calls any transport/storage API.
- `GroupPanel` covers zero state, create/edit/rename/delete, ordered item add/remove, CAS save, user-click group JSON export, and explicit import preview/confirm. Create/import/delete/access-risk register add use per-action confirmation; ordinary edits do not add a second confirmation but still invoke an authorized controller callback.
- `LiveChart` registers only `LineChart`, `GridComponent`, `TooltipComponent`, `LegendComponent`, `DatasetComponent`, `DataZoomComponent`, and `CanvasRenderer`; option has `connectNulls:false`, inside+slider zoom, animation-frame coalescing with no more than one `setOption` per 100 ms, and visible resettable range. Around each real `chart.setOption`, it measures `performance.now()` and dispatches `CustomEvent("stm32-monitor:chart-update",{detail:{durationMs}})` after completion; Task 12 listens to this event, so no synthetic/configured duration can enter evidence. `LiveTable` remains the non-canvas equivalent.
- `HistoryPanel` consumes only the Task 2 `HistoryProjection`; it renders an accessible captioned table containing run, sequence, start ordinal, value count, capture time, watch, status/value, plus a `LiveChart` projection. Previous/Next buttons expose cursor availability and never parse `HistoryPage` themselves.

- [ ] **Step 1: Write failing prop-only workflow, dialog, accessibility, and chart tests.** Render every component with inert callbacks; assert zero groups, connect/reconnect/release states, catalog risk confirmation, group draft/import flow/focus restoration/Escape, explicit sampling buttons, error row plus retained value, 8-series selection, zoom keyboard `+/-/0`, history cursor buttons, verified export confirmation, labels/live regions, 1024 stacking hooks, and reduced-motion class. Add a source-boundary test:

```tsx
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {vi} from "vitest";
import type {GroupPanelProps} from "../src/components/GroupPanel";
import {GroupPanel} from "../src/components/GroupPanel";
const groupProps=(overrides:Partial<GroupPanelProps>={}):GroupPanelProps=>({groups:[],selectedId:null,draft:{sourceGroupId:null,expectedRevision:null,name:"",description:"",intervalMs:250,items:[]},pending:new Map(),onSelect:vi.fn(),onChange:vi.fn(),onCreate:vi.fn(),onSave:vi.fn(),onDelete:vi.fn(),onImport:vi.fn(),onExport:vi.fn(),...overrides});
const groupFile=()=>new File([JSON.stringify({schemaVersion:1,groups:[{name:"Core",description:"",intervalMs:250,items:[{kind:"variable",expression:"x"}]},{name:"IO",description:"",intervalMs:500,items:[{kind:"register",registerPath:"GPIOA.ODR"},{kind:"variable",expression:"y"}]}]})],"groups.json",{type:"application/json"});

it("all views are prop-only",()=>{
  for(const file of readdirSync(new URL("../src/components",import.meta.url))){
    if(!file.endsWith(".tsx"))continue;
    const text=readFileSync(new URL(`../src/components/${file}`,import.meta.url),"utf8");
    expect(text).not.toMatch(/\bfetch\s*\(|\bWebSocket\b|localStorage|sessionStorage|indexedDB|src\/api\/client|src\/api\/live/);
  }
});
it("requires confirmation before group import",async()=>{
  const user=userEvent.setup(),onImport=vi.fn();
  render(<GroupPanel {...groupProps({onImport})}/>);
  await user.upload(screen.getByLabelText("Import group JSON"),groupFile());
  expect(await screen.findByText("2 groups, 3 items")).toBeVisible();
  expect(onImport).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button",{name:"Confirm import"}));
  expect(onImport).toHaveBeenCalledTimes(1);
});
it("renders authoritative history as an accessible table and bounded chart",async()=>{
 const onLoad=vi.fn(async()=>{}),user=userEvent.setup();render(<HistoryPanel projection={historyProjection()} canPrevious={true} canNext={false} onLoad={onLoad} onPrevious={vi.fn()} onNext={vi.fn()}/>);
 expect(screen.getByRole("table",{name:"Monitor history"})).toBeVisible();expect(screen.getByText("Start ordinal")).toBeVisible();expect(screen.getByTestId("history-chart")).toHaveAttribute("data-chart-realized-points","4800");
 await user.type(screen.getByLabelText("History start nanoseconds"),"100");await user.type(screen.getByLabelText("History end nanoseconds"),"200");await user.selectOptions(screen.getByLabelText("History selector kind"),"variable");await user.type(screen.getByLabelText("History selector"),"counter");await user.click(screen.getByRole("button",{name:"Load history"}));expect(onLoad).toHaveBeenCalledWith({startNs:100n,endNs:200n,limit:100,selectorKind:"variable",selector:"counter"});
});
```

- [ ] **Step 2: Run RED.** From `$uiRoot` run `& $npm run test -- tests/app.test.tsx tests/identity-probe.test.tsx tests/catalog-view.test.tsx tests/group-view.test.tsx tests/sampling-view.test.tsx tests/live-view.test.tsx tests/history-export-view.test.tsx tests/chart-view.test.tsx tests/a11y.test.tsx`. Expected: FAIL because the views and ECharts adapter do not exist.

- [ ] **Step 3: Implement the callback-only view tree and exact accessible behavior.** Define the complete top-level interface once and make all child props projections of it:

```tsx
// src/app.tsx
export interface AppViewProps{
  readonly state:MonitorState;
  readonly actions:{refresh():void;connect(probeId:string):void;reconnect():void;release():void;
    searchCatalog(kind:"variables"|"registers",query:string,cursor?:string):void;selectGroup(groupId:string|null):void;
    changeDraft(draft:GroupDraft):void;addWatch(watch:WatchItem):void;removeWatch(key:string):void;
    createGroup(draft:GroupDraft):void;saveGroup(draft:GroupDraft):void;deleteGroup(group:WatchGroup):void;
    importGroups(document:GroupImportDocument):void;exportGroups():void;start(group:WatchGroup):void;
    pause():void;resume():void;stop():void;toggleSeries(key:string):void;zoom(action:ZoomAction):void;
    loadHistory(query:HistoryQuery):void;previousHistory():void;nextHistory():void;
    createExport(request:{startNs:bigint;endNs:bigint;format:"csv"|"jsonl"}):void;
    refreshExport(exportId:string):void;downloadExport(exportId:string):void;};
}
export function App({state,actions}:AppViewProps){return <main id="monitor-app">
  <h1>STM32 Monitor</h1><IdentityBar status={state.status}/><NoticeRegion notices={state.notices} error={state.blockingError}/>
  <ProbePanel status={state.status} probes={state.probes} pending={state.pending} onConnect={actions.connect} onReconnect={actions.reconnect} onRelease={actions.release}/>
  <GroupPanel groups={state.groups} selectedId={state.selectedGroupId} draft={state.groupDraft} pending={state.pending} onSelect={actions.selectGroup} onChange={actions.changeDraft} onCreate={actions.createGroup} onSave={actions.saveGroup} onDelete={actions.deleteGroup} onImport={actions.importGroups} onExport={actions.exportGroups}/>
  <CatalogPanel state={state.catalog} connected={state.status?.probe.connected===true} onSearch={actions.searchCatalog} onAdd={actions.addWatch}/>
  <SamplingControls status={state.status} group={selectedGroup(state)} pending={state.pending} onStart={actions.start} onPause={actions.pause} onResume={actions.resume} onStop={actions.stop}/>
  <StatusStrip live={state.live}/><LiveTable rows={liveRows(state)} selected={state.selectedSeries} onToggle={actions.toggleSeries}/>
  <LiveChart series={chartSeries(state)} zoom={state.zoom} onZoom={actions.zoom}/>
  <HistoryPanel projection={state.history.projection} canPrevious={state.history.cursorIndex>0} canNext={state.history.nextCursor!==null} onLoad={actions.loadHistory} onPrevious={actions.previousHistory} onNext={actions.nextHistory}/>
  <ExportPanel state={state.exports} onCreate={actions.createExport} onRefresh={actions.refreshExport} onDownload={actions.downloadExport}/>
 </main>}
```

```ts
// src/chart/echarts.ts
import * as echarts from "echarts/core";
import {LineChart} from "echarts/charts";
import {GridComponent,TooltipComponent,LegendComponent,DatasetComponent,DataZoomComponent} from "echarts/components";
import {CanvasRenderer} from "echarts/renderers";
echarts.use([LineChart,GridComponent,TooltipComponent,LegendComponent,DatasetComponent,DataZoomComponent,CanvasRenderer]);
export {echarts};
export const chartOption=(series:readonly DisplaySeries[],zoom:ZoomRange)=>({animation:false,tooltip:{trigger:"axis"},legend:{},grid:{containLabel:true},dataset:series.map(item=>({id:item.key,source:item.points.map(p=>[p.capturedAtUtc,p.value])})),dataZoom:[{type:"inside",start:zoom.start,end:zoom.end},{type:"slider",start:zoom.start,end:zoom.end}],series:series.map((item,index)=>({type:"line",datasetIndex:index,encode:{x:0,y:1},name:item.label,showSymbol:false,connectNulls:false}))});
```

```tsx
// src/components/HistoryPanel.tsx
import {useState} from "preact/hooks";
export interface HistoryPanelProps{projection:HistoryProjection;canPrevious:boolean;canNext:boolean;onLoad(query:HistoryQuery):void;onPrevious():void;onNext():void}
const historyDisplaySeries=(projection:HistoryProjection):readonly DisplaySeries[]=>[...projection.series].map(([key,points])=>({key,label:key,points}));
const formatJson=(value:JsonValue):string=>value===null?"null":typeof value==="bigint"?value.toString(10):typeof value==="string"?value:typeof value==="number"||typeof value==="boolean"?String(value):Array.isArray(value)?`[${value.map(formatJson).join(", ")}]`:`{${Object.entries(value).map(([key,item])=>`${key}: ${formatJson(item)}`).join(", ")}}`;
const historyValuesText=(values:readonly SampleValue[]):string=>values.map(value=>value.status==="ERROR"?`${watchKey(value.watch)}: ${value.code}`:`${watchKey(value.watch)}: ${formatJson(value.typedValue)}`).join("; ");
const signed=/^-?(?:0|[1-9]\d*)$/;const parseI64=(value:string,label:string)=>{if(!signed.test(value))throw new Error(`${label} must be a canonical integer`);const result=BigInt(value);if(result<-(1n<<63n)||result>(1n<<63n)-1n)throw new Error(`${label} is outside signed-int64`);return result;};
export function HistoryPanel({projection,canPrevious,canNext,onLoad,onPrevious,onNext}:HistoryPanelProps){const [start,setStart]=useState(""),[end,setEnd]=useState(""),[runId,setRunId]=useState(""),[groupId,setGroupId]=useState(""),[selectorKind,setSelectorKind]=useState<""|"variable"|"register">(""),[selector,setSelector]=useState(""),[error,setError]=useState<string|null>(null);const series=historyDisplaySeries(projection),realized=series.reduce((count,item)=>count+item.points.length,0);const submit=(event:Event)=>{event.preventDefault();try{const startNs=parseI64(start,"History start"),endNs=parseI64(end,"History end");if(startNs>endNs)throw new Error("History start must not exceed end");if((selectorKind==="")!== (selector===""))throw new Error("History selector kind and selector must be paired");setError(null);onLoad({startNs,endNs,limit:100,...(runId?{runId}:{}),...(groupId?{groupId}:{}),...(selectorKind?{selectorKind,selector}: {})});}catch(value){setError(value instanceof Error?value.message:"History query is invalid");}};return <section aria-labelledby="history-title"><h2 id="history-title">History</h2><form onSubmit={submit}><label>History start nanoseconds<input value={start} onInput={event=>setStart(event.currentTarget.value)}/></label><label>History end nanoseconds<input value={end} onInput={event=>setEnd(event.currentTarget.value)}/></label><label>History run ID<input value={runId} onInput={event=>setRunId(event.currentTarget.value)}/></label><label>History group ID<input value={groupId} onInput={event=>setGroupId(event.currentTarget.value)}/></label><label>History selector kind<select value={selectorKind} onChange={event=>setSelectorKind(event.currentTarget.value as ""|"variable"|"register")}><option value="">Any</option><option value="variable">Variable</option><option value="register">Register</option></select></label><label>History selector<input value={selector} onInput={event=>setSelector(event.currentTarget.value)}/></label><button type="submit">Load history</button>{error&&<p role="alert">{error}</p>}</form><div data-testid="history-chart" data-chart-realized-points={realized}><LiveChart series={series} zoom={{start:0,end:100}} onZoom={()=>{}}/></div><table aria-label="Monitor history"><caption>Authoritative sample history</caption><thead><tr><th>Run</th><th>Sequence</th><th>Start ordinal</th><th>Value count</th><th>Captured</th><th>Samples</th></tr></thead><tbody>{projection.rows.map(row=><tr key={`${row.runId}:${row.sequence.toString()}:${row.startOrdinal.toString()}`}><td>{row.runId}</td><td>{row.sequence.toString()}</td><td>{row.startOrdinal.toString()}</td><td>{row.batchValueCount.toString()}</td><td>{row.capturedAtUtc}</td><td>{historyValuesText(row.values)}</td></tr>)}</tbody></table><button type="button" disabled={!canPrevious} onClick={onPrevious}>Previous history page</button><button type="button" disabled={!canNext} onClick={onNext}>Next history page</button></section>}
```

Dialogs move focus inside on open, restore the trigger on close, and allow Escape only before submission. All controls have programmatic names; `NoticeRegion` uses `aria-live="polite"`, blocking errors use `role="alert"`; CSS supplies visible focus >=3:1, text >=4.5:1, 1024x768 stacking, 200% usable overflow, and `prefers-reduced-motion`. Typed values use text nodes and a bounded formatter, never `innerHTML`.

- [ ] **Step 4: Run GREEN, axe, typecheck, and source scans.** From `$uiRoot` run `& $npm run test -- tests/app.test.tsx tests/identity-probe.test.tsx tests/catalog-view.test.tsx tests/group-view.test.tsx tests/sampling-view.test.tsx tests/live-view.test.tsx tests/history-export-view.test.tsx tests/chart-view.test.tsx tests/a11y.test.tsx`; run `& $npm run typecheck`; run `& $npm run lint`; run `& $npm run test:a11y`. From `$repoRoot`, run the exact `rg` scan shown in Step 3 over `tools/stm32-monitor/ui/src/components` and `tools/stm32-monitor/ui/src/app.tsx`. Expected: test/typecheck/lint/axe PASS and scan exit 1 with no match.

- [ ] **Step 5: Commit Task 3.** Call `Commit-0502Task 'feat(STM32TK-0502): add prop-only monitor views' @('tools/stm32-monitor/ui/src/app.tsx','tools/stm32-monitor/ui/src/styles.css','tools/stm32-monitor/ui/src/chart/echarts.ts','tools/stm32-monitor/ui/src/components/IdentityBar.tsx','tools/stm32-monitor/ui/src/components/ProbePanel.tsx','tools/stm32-monitor/ui/src/components/CatalogPanel.tsx','tools/stm32-monitor/ui/src/components/GroupPanel.tsx','tools/stm32-monitor/ui/src/components/GroupImportDialog.tsx','tools/stm32-monitor/ui/src/components/SamplingControls.tsx','tools/stm32-monitor/ui/src/components/LiveTable.tsx','tools/stm32-monitor/ui/src/components/LiveChart.tsx','tools/stm32-monitor/ui/src/components/ChartZoomControls.tsx','tools/stm32-monitor/ui/src/components/StatusStrip.tsx','tools/stm32-monitor/ui/src/components/NoticeRegion.tsx','tools/stm32-monitor/ui/src/components/HistoryPanel.tsx','tools/stm32-monitor/ui/src/components/ExportPanel.tsx','tools/stm32-monitor/ui/tests/app.test.tsx','tools/stm32-monitor/ui/tests/identity-probe.test.tsx','tools/stm32-monitor/ui/tests/catalog-view.test.tsx','tools/stm32-monitor/ui/tests/group-view.test.tsx','tools/stm32-monitor/ui/tests/sampling-view.test.tsx','tools/stm32-monitor/ui/tests/live-view.test.tsx','tools/stm32-monitor/ui/tests/history-export-view.test.tsx','tools/stm32-monitor/ui/tests/chart-view.test.tsx','tools/stm32-monitor/ui/tests/a11y.test.tsx')`.

### Task 4: Controller-Only Orchestration and Complete Command Lifecycles

**Files:**
- Create: `tools/stm32-monitor/ui/src/controller.ts`.
- Create: `tools/stm32-monitor/ui/tests/controller.test.ts`.

**Interfaces:**
- Produces `MonitorController extends AppViewProps["actions"]` with distinct lifecycle methods `initialize():Promise<void>` and `dispose():void`, plus `createMonitorController({api,openLive,dispatch,clock,scheduler,download})`; `openLive` has the exact frozen `OpenLive` signature. Sampling action `start(group)` is never overloaded as lifecycle startup.
- Startup concurrently requests status, probes, and all `groups(cursor)` pages (the accepted service fixes page size at 16), then opens live. Catalog is connected-only and debounce keyed. Controller owns history cursor stack in memory, group Blob download, verified artifact binary download, heartbeat stale timer (35 s), and live capped reconnect delays `500,1000,2000,4000,8000` ms.
- No command clears pending from the command's acknowledgement alone. Probe/group commands apply returned authority or refresh the corresponding authority; sampling commands always refresh status. Errors dispatch exact public `code/message`, preserve form input, and clear only the matching request ID.

- [ ] **Step 1: Write failing orchestration tests with ordered recording fakes.** Assert startup concurrency/all group pages; started-authority-cleared traces for every command; failure traces; sampling acknowledgement followed by status; group conflict refresh; reconnect availability only after successful connect; no automatic probe reconnect/start; debounced catalog cancellation; history Previous cursor stack; verified download metadata; and 35-second stale plus capped live replay using exact bigint `afterEventId`. Core trace:

```ts
it.each(["start","pause","resume","stop"] as const)("%s refreshes authoritative status before clearing",async command=>{
  const trace:string[]=[],h=harness(trace);
  await h.controller[command](command==="start"?h.group:undefined as never);
  expect(trace).toEqual([`dispatch:request.started:sampling.${command}`,`api:${command}`,"api:status","dispatch:status.loaded",`dispatch:request.cleared:sampling.${command}`]);
});
it("uses exact replay bigint and never reacquires hardware",async()=>{
  const h=harness([]);await h.controller.initialize();h.live.emit(heartbeatEnvelope(9223372036854775807n));h.live.close();
  await h.scheduler.advanceBy(500);
  expect(h.live.openedAfter).toEqual([null,9223372036854775807n]);
  expect(h.api.calls.filter(x=>x==="reconnect"||x==="start")).toEqual([]);
});
```

```ts
import {heartbeatEnvelope,statusResult,watchGroup,fakeClock,fakeScheduler,recordingDownload,recordingApi} from "./fixtures";
const harness=(trace:string[])=>{const handlers:{current:LiveHandlers|null}={current:null};const status=statusResult(),group=watchGroup();const api:MonitorApi={...recordingApi(trace,status),start:async(id,revision)=>{trace.push("api:start");return{ok:true,data:{groupId:id,groupRevision:revision,runId:"run",intervalMs:250}};},pause:async()=>{trace.push("api:pause");return{ok:true,data:{paused:true}};},resume:async()=>{trace.push("api:resume");return{ok:true,data:{resumed:true}};},stop:async()=>{trace.push("api:stop");return{ok:true,data:{stopped:false}};},status:async()=>{trace.push("api:status");return{ok:true,data:status};}};
 const live={openedAfter:[] as (bigint|null)[],emit(value:ParsedLiveEnvelope){handlers.current?.onEnvelope(value);},close(){handlers.current?.onClosed();}};const openLive:OpenLive=(after,next)=>{live.openedAfter.push(after);handlers.current=next;return()=>{handlers.current=null;}};const scheduler=fakeScheduler();const dispatch=(action:MonitorAction)=>{trace.push(`dispatch:${action.type}${"scope" in action?":"+action.scope:"}`);};return{api,group,live,scheduler,controller:createMonitorController({api,openLive,dispatch,clock:fakeClock(),scheduler,download:recordingDownload(trace)})};};
```

- [ ] **Step 2: Run RED.** From `$uiRoot` run `& $npm run test -- tests/controller.test.ts`. Expected: FAIL because `controller.ts` is absent.

- [ ] **Step 3: Implement one orchestration layer and no transport elsewhere.** Use one request wrapper that cannot clear before its authoritative callback completes, and explicit sampling refresh:

```ts
// src/controller.ts
const scopes=["initial","status","probes","probe.connect","probe.reconnect","probe.release","catalog.variables","catalog.registers","groups.create","groups.update","groups.delete","groups.import","sampling.start","sampling.pause","sampling.resume","sampling.stop","history","export.create","export.status","export.download"] as const;
export function createMonitorController(deps:ControllerDeps):MonitorController{
 let nextRequest=0n,lastEventId:bigint|null=null,liveStop:(()=>void)|null=null,historyCursors:(string|undefined)[]=[];
 const run=async<T>(scope:RequestScope,request:()=>Promise<ApiResult<T>>,authoritative:(value:T)=>Promise<void>|void):Promise<void>=>{
   const requestId=++nextRequest;deps.dispatch({type:"request.started",scope,requestId});
   try{const result=await request();if(!result.ok){deps.dispatch({type:"request.failed",scope,requestId,code:result.code,message:result.message});return;}
     await authoritative(result.data);deps.dispatch({type:"request.cleared",scope,requestId});}
   catch{deps.dispatch({type:"request.failed",scope,requestId,code:"MONITOR_CLIENT_ERROR",message:"Monitor request failed"});}
 };
 const refreshStatus=async()=>{const result=await deps.api.status();if(!result.ok)throw new Error(result.code);deps.dispatch({type:"status.loaded",status:result.data});};
 const sampling=(name:"start"|"pause"|"resume"|"stop",group?:WatchGroup)=>run(`sampling.${name}`,()=>name==="start"?deps.api.start(group!.groupId,group!.revision):deps.api[name](),refreshStatus);
 const command={start:(group:WatchGroup)=>sampling("start",group),pause:()=>sampling("pause"),resume:()=>sampling("resume"),stop:()=>sampling("stop")};
 const open=()=>{liveStop?.();liveStop=deps.openLive(lastEventId,{onEnvelope:value=>{if(lastEventId!==null&&value.event.eventId<=lastEventId)return;lastEventId=value.event.eventId;deps.dispatch({type:"live.envelope",value});if(value.subscriberDropped>0n||(value.event.type==="state"&&value.event.data.gap))void refreshStatus();},onClosed:()=>scheduleReconnect()});};
 const reconnectDelays=[500,1000,2000,4000,8000] as const;let reconnectAttempt=0;
 const scheduleReconnect=()=>deps.scheduler.setTimeout(()=>{open();reconnectAttempt=Math.min(reconnectAttempt+1,reconnectDelays.length-1);},reconnectDelays[reconnectAttempt]!);
 const loadGroups=async()=>{const groups:WatchGroup[]=[];let cursor:string|undefined;do{const page=await deps.api.groups(cursor);if(!page.ok)throw new Error(page.code);groups.push(...page.data.groups);cursor=page.data.nextCursor??undefined;}while(cursor!==undefined);deps.dispatch({type:"groups.loaded",groups});};
 const groupMutation=(scope:"groups.create"|"groups.update"|"groups.delete"|"groups.import",request:()=>Promise<ApiResult<unknown>>)=>run(scope,request,loadGroups);
 const searchCatalog=debounceCatalog(deps.scheduler,300,async(kind,query,cursor,bindingKey)=>run(`catalog.${kind}`,()=>kind==="variables"?deps.api.variables(query,cursor):deps.api.registers(query,cursor),page=>deps.dispatch({type:"catalog.loaded",catalog:kind,query,bindingKey,cursor:cursor??null,items:page.items,nextCursor:page.nextCursor})));
 const controller:MonitorController={
  async initialize(){await Promise.all([refreshStatus(),run("probes",()=>deps.api.probes(),value=>deps.dispatch({type:"probes.loaded",probes:value.probes})),loadGroups()]);open();},
  dispose(){liveStop?.();liveStop=null;deps.scheduler.clearAll();},refresh:()=>run("status",()=>deps.api.status(),value=>deps.dispatch({type:"status.loaded",status:value})),
  connect:probeId=>run("probe.connect",()=>deps.api.connect(probeId),async()=>{await refreshStatus();const probes=await deps.api.probes();if(!probes.ok)throw new Error(probes.code);deps.dispatch({type:"probes.loaded",probes:probes.data.probes});}),
  reconnect:()=>run("probe.reconnect",()=>deps.api.reconnect(),refreshStatus),release:()=>run("probe.release",()=>deps.api.release(),refreshStatus),
  searchCatalog,selectGroup:groupId=>deps.dispatch({type:"group.selected",groupId}),changeDraft:draft=>deps.dispatch({type:"group.draft.changed",draft}),addWatch:watch=>deps.dispatch({type:"group.watch.added",watch}),removeWatch:key=>deps.dispatch({type:"group.watch.removed",key}),
  createGroup:draft=>groupMutation("groups.create",()=>deps.api.createGroup({...draftToTransfer(draft),authorized:true})),saveGroup:draft=>groupMutation("groups.update",()=>deps.api.updateGroup(requiredGroupId(draft),draftToUpdate(draft))),deleteGroup:group=>groupMutation("groups.delete",()=>deps.api.deleteGroup(group.groupId,{expectedRevision:group.revision,authorized:true})),importGroups:document=>groupMutation("groups.import",()=>deps.api.importGroups(document)),
  exportGroups:()=>deps.download.json("stm32-monitor-groups.json",toGroupImportDocument(deps.getState().groups)),start:command.start,pause:command.pause,resume:command.resume,stop:command.stop,toggleSeries:key=>deps.dispatch({type:"series.toggled",key}),zoom:action=>deps.dispatch({type:"zoom.changed",action}),
  loadHistory:query=>run("history",()=>deps.api.history(query),page=>{historyCursors=[query.cursor];deps.dispatch({type:"history.loaded",page,query});}),previousHistory:()=>loadVisitedHistory(-1),nextHistory:()=>loadVisitedHistory(1),
  createExport:request=>run("export.create",()=>deps.api.createExport(request.startNs,request.endNs,request.format),artifact=>deps.dispatch({type:"export.loaded",artifact})),refreshExport:exportId=>run("export.status",()=>deps.api.exportStatus(exportId),artifact=>deps.dispatch({type:"export.loaded",artifact})),downloadExport:exportId=>run("export.download",()=>deps.api.downloadExport(exportId),result=>{if(!result.ok)throw new Error(result.code);deps.download.blob(result.filename,result.contentType,result.blob);})};
 return controller;
}
```

The same file defines the referenced, typed local functions `debounceCatalog`, `draftToTransfer`, `draftToUpdate`, `requiredGroupId`, and `loadVisitedHistory`; none is imported or left to a later task. `debounceCatalog` NFC-normalizes/caps input and captures binding key+cursor. `loadVisitedHistory` owns a `{query,cursors,index}` value and never exposes cursors to state. Group conflict catches the accepted conflict code, awaits `loadGroups`, preserves the draft, then dispatches `request.failed`. Group import is invoked only by the view's confirmed callback. Live positive outer drops and `gap:true` refresh status but never fabricate samples; the event-ID check precedes dispatch and refresh, so replay cannot double-count or double-refresh.

- [ ] **Step 4: Run GREEN and controller boundary checks.** From `$uiRoot` run `& $npm run test -- tests/controller.test.ts`; run `& $npm run typecheck`; run `& $npm run lint`; run `& $npm run test -- tests/reducer.test.ts tests/controller.test.ts tests/client.test.ts tests/live.test.ts`. Expected: every command PASS; fake-timer traces prove lifecycle/action separation, every scope terminates, all sampling operations refresh status, outer drops refresh once, and reconnect touches no hardware command.

- [ ] **Step 5: Commit Task 4.** Call `Commit-0502Task 'feat(STM32TK-0502): orchestrate authoritative monitor commands' @('tools/stm32-monitor/ui/src/controller.ts','tools/stm32-monitor/ui/tests/controller.test.ts')`.

### Task 5: Secret-Safe Bootstrap and Separately Tested Main Composition

**Files:**
- Create: `tools/stm32-monitor/ui/src/bootstrap.ts`, `src/main.tsx`.
- Create: `tools/stm32-monitor/ui/tests/bootstrap.test.ts`, `tests/main.test.tsx`.

**Interfaces:**
- Produces `takeFragmentToken(location,history):string`, `bootstrapCookie(token,fetchImpl,origin):Promise<ApiResult<{authenticated:true}>>`, `renderStartupError(message)`, and `startMain(deps):Promise<void>`.
- Exactly one `token=<64 lowercase hex>` fragment is accepted. It is synchronously removed with `history.replaceState(null,"","/")` before Preact import/mount, state creation, controller creation, or any request. Bootstrap sends exact Origin + Bearer, empty body, no cookie acceptance; local token reference is set to `null` in `finally`, then and only then is the app/controller dynamically imported and mounted.

- [ ] **Step 1: Write failing bootstrap-order and main-composition tests.** Cases cover missing/duplicate/query/uppercase/nonhex token; replacement before fetch; bootstrap failure secret-free DOM/error/console; no state or transport before success; token nulled; main creates controller once, subscribes renderer once, and stops once. Include:

```ts
it("scrubs before bootstrap and mounts only after the local token is cleared",async()=>{
  const order:string[]=[],deps=mainDeps(order);
  await startMain(deps);
  expect(order).toEqual(["take","replace:/","bootstrap","token:null","import-app","create-controller","mount","controller:initialize"]);
  expect(document.documentElement.textContent).not.toContain(deps.secret);
});
it.each(["","#token=a","#token="+"A".repeat(64),"#token="+"a".repeat(64)+"&token="+"b".repeat(64)])("rejects fragment %s without guessing",fragment=>{
  expect(()=>takeFragmentToken(fakeLocation(fragment),fakeHistory())).toThrow("Monitor startup failed");
});
```

- [ ] **Step 2: Run RED.** From `$uiRoot` run `& $npm run test -- tests/bootstrap.test.ts tests/main.test.tsx`. Expected: FAIL because bootstrap/main modules are absent.

- [ ] **Step 3: Implement scrub-before-bootstrap and dynamic post-auth composition.** Use this exact ordering; the static imports in `main.tsx` are limited to `takeFragmentToken`, `bootstrapCookie`, and secret-free error rendering:

```ts
// src/main.tsx
import {bootstrapCookie,renderStartupError,takeFragmentToken} from "./bootstrap";
export async function startMain(deps:MainDeps=browserDeps):Promise<void>{
 let token:string|null=null;
 try{
   token=takeFragmentToken(deps.location,deps.history);
   const result=await bootstrapCookie(token,deps.fetch,deps.location.origin);
   if(!result.ok)throw new Error("Monitor startup failed");
 }catch{renderStartupError("Monitor startup failed",deps.document);return;}
 finally{token=null;deps.onTokenCleared?.();}
 const [{render},{App},{createMonitorApi},{createMonitorController},{openLive},{reducer,initialState}]=await Promise.all([
   import("preact"),import("./app"),import("./api/client"),import("./controller"),import("./api/live"),import("./state/reducer")]);
 const store=deps.createStore(reducer,initialState);const boundLive:OpenLive=(after,handlers)=>openLive(deps.location.origin,after,handlers,deps.socketFactory);const controller=createMonitorController({api:createMonitorApi(deps.fetch,deps.location.origin),openLive:boundLive,dispatch:store.dispatch,getState:store.getState,clock:deps.clock,scheduler:deps.scheduler,download:deps.download});
 const mount=()=>render(<App state={store.getState()} actions={controller}/>,deps.document.getElementById("app")!);
 const unsubscribe=store.subscribe(mount);mount();await controller.initialize();deps.onUnload(()=>{unsubscribe();controller.dispose();});
}
if(import.meta.env.PROD||!import.meta.env.VITEST)void startMain();
```

```ts
// src/bootstrap.ts
export function takeFragmentToken(location:Pick<Location,"hash">,history:Pick<History,"replaceState">):string{
 const match=/^#token=([0-9a-f]{64})$/.exec(location.hash);history.replaceState(null,"","/");
 if(match===null)throw new Error("Monitor startup failed");return match[1]!;
}
export async function bootstrapCookie(token:string,fetchImpl:typeof fetch,origin:string):Promise<ApiResult<{authenticated:true}>>{
 const response=await fetchImpl("/api/v1/auth/bootstrap",{method:"POST",credentials:"same-origin",headers:{Authorization:`Bearer ${token}`,Origin:origin}});
 return parseEnvelope(await response.text(),"monitor.auth.bootstrap",authenticatedGuard);
}
```

No query/storage fallback exists; `renderStartupError` writes fixed text with `textContent` and no caught value. `main.test.tsx` injects all dependencies and independently proves composition; it does not rely on bootstrap unit mocks to assert order.

- [ ] **Step 4: Run GREEN and secret scans.** From `$uiRoot` run `& $npm run test -- tests/bootstrap.test.ts tests/main.test.tsx`; run `& $npm run typecheck`; run `& $npm run lint`; run `& $npm run test -- tests/bootstrap.test.ts tests/main.test.tsx tests/controller.test.ts`; then run the exact `rg` token-fallback scan shown in Step 3 against `tools/stm32-monitor/ui/src`. Expected: test/typecheck/lint PASS and scan exit 1 with no hit.

- [ ] **Step 5: Commit Task 5.** Call `Commit-0502Task 'feat(STM32TK-0502): secure monitor bootstrap and main' @('tools/stm32-monitor/ui/src/bootstrap.ts','tools/stm32-monitor/ui/src/main.tsx','tools/stm32-monitor/ui/tests/bootstrap.test.ts','tools/stm32-monitor/ui/tests/main.test.tsx')`.

### Task 6: Close Per-File Frontend Branch Coverage with Real Tests

**Files:**
- Modify: `tools/stm32-monitor/ui/tests/check-coverage.mjs`.
- Create: `tools/stm32-monitor/ui/tests/coverage-branches.test.ts`.
- Modify only test files from Tasks 1-5 when an uncovered branch belongs to their corresponding product module; no product source changes.

**Interfaces:**
- `check-coverage.mjs` enumerates every `src/**/*.ts(x)` except `.d.ts`, requires one unambiguous `coverage-final.json` entry, and fails any product file below 90% branches. Files with zero branches pass at 100%; missing entries fail.
- Coverage closure comes from asserted behavior, not ignore comments, threshold reductions, source exclusion, generated files, or empty imports.

- [ ] **Step 1: Write the failing coverage-checker self-test and concrete branch cases.** Add tests for missing coverage record, duplicate normalized path, 89.99%, zero-branch, Windows separators, and real product error branches: malformed integer token/collision, envelope wrong key/operation, rejected descriptor, mutation/network failure, group conflict, stale revision, gap/error/null, catalog rebind, dialog Escape/submit, chart disposal, bootstrap failure, controller stop/retry. Core checker fixture:

```ts
it("fails a changed product file at 89.99 branches and a missing file",()=>{
  const result=runCoverageCheck({"src/api/wire.ts":coverageEntry(8999,10000)},["src/api/wire.ts","src/controller.ts"]);
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("api/wire.ts: branches 89.99%");
  expect(result.stderr).toContain("controller.ts: no coverage record");
});
```

- [ ] **Step 2: Run RED.** From `$uiRoot` run `& $npm run test:coverage`. Expected: FAIL with an explicit per-file list; the failure must include actual untested branches or checker self-test behavior, not a TypeScript/build/dependency error.

- [ ] **Step 3: Implement the exact mechanical checker and add behavior assertions until every row is covered.** Replace the checker with this complete algorithm and use the coverage JSON's branch map rather than line coverage:

```js
import {readFileSync,readdirSync,statSync} from "node:fs";import {resolve,relative,sep} from "node:path";
const root=resolve("src"),document=JSON.parse(readFileSync("coverage/coverage-final.json","utf8"));
const normalized=new Map();for(const [name,value] of Object.entries(document)){const key=resolve(name).toLowerCase();if(normalized.has(key)){console.error(`${name}: duplicate coverage record`);process.exitCode=1;}normalized.set(key,value);}
const files=[];const walk=dir=>{for(const name of readdirSync(dir)){const file=resolve(dir,name),info=statSync(file);if(info.isDirectory())walk(file);else if(/\.(ts|tsx)$/.test(name)&&!name.endsWith(".d.ts"))files.push(file);}};walk(root);
const failures=[];for(const file of files.sort()){const entry=normalized.get(file.toLowerCase());const label=relative(root,file).split(sep).join("/");if(entry===undefined){failures.push(`${label}: no coverage record`);continue;}const counters=Object.values(entry.b).flat();const hit=counters.filter(value=>value>0).length;const percent=counters.length===0?100:hit*100/counters.length;if(percent<90)failures.push(`${label}: branches ${percent.toFixed(2)}%`);}
if(failures.length){console.error(failures.join("\n"));process.exit(1);}
```

For each RED-listed branch, add an assertion to the owning existing test or `coverage-branches.test.ts`; each added test names the condition and expected public state. Do not add source pragmas matching `istanbul ignore`, `c8 ignore`, or `v8 ignore`.

- [ ] **Step 4: Run GREEN twice and prove no exclusions.** Initialize this task's new `$taskRoot\npm-cache-working` by the Global Command convention, then run `Assert-0502Support`, `Invoke-0502NpmPhase {& $npm ci --offline --cache $npmWorkingCache} 'npm ci failed'`, `& $npm run typecheck`, `& $npm run lint`, `& $npm run test:coverage`, `& $npm run test:a11y`, and `& $npm run test:coverage`; run `rg -n 'istanbul ignore|c8 ignore|v8 ignore|coveragePathIgnorePatterns' tools/stm32-monitor/ui`; finally run `Assert-0502Support`. Expected: verification and both coverage runs PASS with each product file branches >=90%, source/exclusion scan has no hit, the realized tests include state/controller/main separately, and source support hashes remain unchanged.

- [ ] **Step 5: Commit Task 6.** Step 3 adds an asserted boundary case to every named owner test, so call `Commit-0502Task 'test(STM32TK-0502): close per-file frontend coverage' @('tools/stm32-monitor/ui/tests/check-coverage.mjs','tools/stm32-monitor/ui/tests/coverage-branches.test.ts','tools/stm32-monitor/ui/tests/contract.test.ts','tools/stm32-monitor/ui/tests/client.test.ts','tools/stm32-monitor/ui/tests/live.test.ts','tools/stm32-monitor/ui/tests/reducer.test.ts','tools/stm32-monitor/ui/tests/series.test.ts','tools/stm32-monitor/ui/tests/catalog.test.ts','tools/stm32-monitor/ui/tests/group-transfer.test.ts','tools/stm32-monitor/ui/tests/zoom.test.ts','tools/stm32-monitor/ui/tests/app.test.tsx','tools/stm32-monitor/ui/tests/identity-probe.test.tsx','tools/stm32-monitor/ui/tests/catalog-view.test.tsx','tools/stm32-monitor/ui/tests/group-view.test.tsx','tools/stm32-monitor/ui/tests/sampling-view.test.tsx','tools/stm32-monitor/ui/tests/live-view.test.tsx','tools/stm32-monitor/ui/tests/history-export-view.test.tsx','tools/stm32-monitor/ui/tests/chart-view.test.tsx','tools/stm32-monitor/ui/tests/a11y.test.tsx','tools/stm32-monitor/ui/tests/bootstrap.test.ts','tools/stm32-monitor/ui/tests/main.test.tsx','tools/stm32-monitor/ui/tests/controller.test.ts')`. The cached set is exact and contains no product source.

### Task 7: Same-Process Static Runtime, Browser Auth Matrix, and Explicit CLI

**Files:**
- Create: `tools/stm32-monitor/src/stm32_monitor/ui_assets.py`.
- Modify: `tools/stm32-monitor/src/stm32_monitor/auth.py`, `service.py`, `cli.py`.
- Create: `tools/stm32-monitor/tests/test_ui_assets.py`, `test_launcher.py`.
- Modify: `tools/stm32-monitor/tests/test_auth.py`, `test_service.py`, `test_cli.py`.

**Interfaces:**
- Produces `UiAssets.from_traversable(root:Traversable):UiAssets`, `UiAssets.response(route,method,port)`, and `MonitorAuth.authorize(...,method,fetch_site,websocket,bootstrap)`. Task 7 real-service tests inject a complete synthetic `UiAssets`; they never depend on the not-yet-created package `ui_dist`.
- `MonitorService(...,ui_assets:UiAssets|None=None)` serves `/` plus exact `/assets/<manifest member>` from the same random IPv4-loopback aiohttp application when injected; `None` retains fixed static 404 until Task 8 wires the package default. No request path is joined to a filesystem path; no `add_static`, directory listing, reflection, `/api` fallback, or second process/server exists.
- When the runtime `live_subscribe` source ends normally, `MonitorService` closes that client WebSocket and awaits/cancels both owned live tasks; this is the authoritative disconnect seam used by Task 11 replay/gap tests. It must not leave `_live` blocked in the client-message loop after the producer has completed.
- Machine `serve --json` remains browser-side-effect free. Human `open --project --data-root [--session-id]` starts first, opens `endpoint.access_url` exactly once, prints no URL/token, waits foreground, owns cleanup, and generates `monitor-<32 lowercase hex>` only when session is omitted.

- [ ] **Step 1: Write failing auth/static/CLI tests over a real service.** Test the complete Design §7.3 matrix: all API/WS require peer `127.0.0.1`, exact Host, header budget, exact Origin when present, and same-origin Fetch Site when present; Bearer always requires exact Origin and bootstrap refuses cookie; cookie GET/HEAD/WS accepts exact Origin or absent Origin plus `Sec-Fetch-Site:same-origin`; cookie mutations require exact Origin and reject absent Origin even with same-origin metadata; `Origin:null`, cross/same-site/none, wrong peer/Host all fail. Static tests cover exact headers/CSP/cache/MIME/ETag/HEAD, 256 KiB index/manifest, 4 MiB asset, 8 MiB tree, traversal/unknown fixed 404, and API no fallback. CLI tests record exact order and opener counts:

```python
@pytest.mark.parametrize(
    "method,origin,fetch_site,websocket,allowed",
    [("GET",None,"same-origin",False,True),("HEAD",None,"same-origin",False,True),
     ("GET",None,"same-origin",True,True),("POST",None,"same-origin",False,False),
     ("POST","http://127.0.0.1:43210","same-origin",False,True),
     ("GET",None,None,False,False),("GET","null","same-origin",False,False),
     ("GET",None,"same-site",False,False),("GET",None,"cross-site",False,False),
     ("GET",None,"none",False,False)])
def test_cookie_browser_transport_matrix(method,origin,fetch_site,websocket,allowed):
    call=lambda: auth.authorize(peer="127.0.0.1",host="127.0.0.1:43210",origin=origin,
      authorization=None,cookie=auth.token,method=method,fetch_site=fetch_site,
      websocket=websocket,bootstrap=False)
    if allowed: assert call()=="cookie"
    else:
      with pytest.raises(MonitorAuthError): call()

def test_open_starts_then_opens_once_and_cleans_up():
    events=[];result=main(["open","--project",str(PROJECT),"--data-root",str(DATA)],
      runtime_factory=runtime_factory(events),browser_open=lambda url: events.append(("open",url)) or True)
    assert result==0 and [e[0] if isinstance(e,tuple) else e for e in events]==["start","open","wait","stop"]

async def test_real_service_uses_only_injected_assets(aiohttp_client):
    assets=UiAssets.from_traversable(MemoryTree({"index.html":b"<div id=app></div>",".vite/manifest.json":MANIFEST,"assets/app-a1b2c3.js":b"export{}"}))
    service=MonitorService(runtime(),workspace_id="workspace",session_id="session",token_factory=lambda count:b"x"*count,ui_assets=assets)
    endpoint=await service.start()
    try: assert (await fetch(endpoint,"/",token=service.token)).body==b"<div id=app></div>"
    finally: await service.stop()

async def test_live_source_completion_closes_websocket_and_cleans_tasks(aiohttp_client):
    source_finished=asyncio.Event();runtime=runtime_with_finite_live_source(source_finished)
    service=MonitorService(runtime,workspace_id="workspace",session_id="session",token_factory=lambda count:b"x"*count)
    endpoint=await service.start()
    try:
        socket=await authenticated_websocket(endpoint,service.token)
        await source_finished.wait()
        message=await asyncio.wait_for(socket.receive(),timeout=1.0)
        assert message.type in {WSMsgType.CLOSE,WSMsgType.CLOSED} and not service._live_tasks
    finally: await service.stop()
```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-monitor/tests/test_ui_assets.py tools/stm32-monitor/tests/test_auth.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_launcher.py tools/stm32-monitor/tests/test_cli.py -q -p no:cacheprovider --basetemp $taskTemp312`. Expected: FAIL on missing `ui_assets`, old cookie Origin rule, absent static routes, absent `open`, and the finite live-source test timing out because the existing `_live` handler does not close the WebSocket when its producer ends; accepted 0501 protocol tests still collect.

- [ ] **Step 3: Implement exact immutable resources, normalized transport evidence, and owned open.** The authorization decision is method/fetch-site/WS based, never caller-supplied “safe”:

```python
# auth.py replacement decision inside authorize
method = method.upper()
if method not in {"GET", "HEAD", "POST", "PATCH", "PUT", "DELETE"}:
    raise _error("MONITOR_AUTH_REQUIRED", "Monitor Service authentication failed", 401)
if fetch_site is not None and fetch_site != "same-origin":
    raise _error("MONITOR_ORIGIN_REJECTED", "Monitor Service Origin is invalid", 403)
exact_origin = origin == self.origin
bearer_ok = exact_origin and len(bearer) == 64 and secrets.compare_digest(bearer, self.token)
safe_cookie = method in {"GET", "HEAD"} and (exact_origin or (origin is None and fetch_site == "same-origin"))
mutation_cookie = method in {"POST", "PATCH", "PUT", "DELETE"} and exact_origin
cookie_ok = not bootstrap and (safe_cookie or mutation_cookie) and isinstance(cookie, str) and len(cookie) == 64 and secrets.compare_digest(cookie, self.token)
if bootstrap and cookie_ok: cookie_ok = False
if bearer_ok: return "bearer"
if cookie_ok: return "cookie"
raise _error("MONITOR_AUTH_REQUIRED", "Monitor Service authentication failed", 401)
```

```python
# ui_assets.py core
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Mapping

@dataclass(frozen=True)
class UiAsset:
    route: str; body: bytes; content_type: str; etag: str; cache_control: str
@dataclass(frozen=True)
class UiAssets:
    entries: Mapping[str, UiAsset]
    @classmethod
    def from_traversable(cls, root: Traversable) -> "UiAssets":
        blobs: dict[str, bytes]={}
        def visit(node: Traversable, prefix: PurePosixPath) -> None:
            for child in sorted(node.iterdir(),key=lambda value:value.name):
                if not child.name or child.name in {".",".."} or "/" in child.name or "\\" in child.name: raise ValueError("UI resource name is invalid")
                relative=prefix/child.name
                if child.is_dir(): visit(child,relative)
                elif child.is_file(): blobs[relative.as_posix()]=child.read_bytes()
                else: raise ValueError("UI resource type is invalid")
        visit(root,PurePosixPath())
        return cls(MappingProxyType(_validated_manifest_entries(blobs)))
    def find(self, route: str) -> UiAsset | None:
        return self.entries.get(route)
```

The recursion carries a `PurePosixPath` from the traversal root and never calls filesystem-only `relative_to`/`as_posix` methods on a `Traversable`. In `service.py`, accept injected assets before `runner.setup`, register exact GET/HEAD routes before API routes, validate static peer/Host/header budget/optional Origin, return fixed empty 404 for any unlisted route, and pass `request.method`, `request.headers.get("Sec-Fetch-Site")`, and WebSocket context into auth. Preserve the existing request envelope and live wrapper unchanged. Refactor `_live` so producer completion wins a bounded `asyncio.wait(..., return_when=FIRST_COMPLETED)` race against the client receive loop: normal source exhaustion closes the WebSocket, client close still cancels the producer, and the `finally` block cancels/awaits producer, sender, and receiver before removing every task from `_live_tasks`. The sender must also receive an explicit end sentinel or be cancelled; it may not wait forever on an empty queue. In `cli.py`, add an injected `_browser_open`, generate the optional session with `secrets.token_hex(16)`, await start before one opener call, stop on false/raise, foreground wait, Ctrl-C 130, and never add `--open-browser` to `serve`.

- [ ] **Step 4: Run GREEN on both Python versions and prove protocol containment.** Run `& $python310 -m pytest tools/stm32-monitor/tests/test_ui_assets.py tools/stm32-monitor/tests/test_auth.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_launcher.py tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_protocol.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_groups.py tools/stm32-monitor/tests/test_sampler.py tools/stm32-monitor/tests/test_exports.py -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'green-310')`, then the identical paths with `$python312` and `green-312`; set `PYTHONPYCACHEPREFIX=(Join-Path $taskRoot 'pycache')` and run `& $python312 -m compileall -q tools/stm32-monitor/src`. Expected: every command PASS with one process/port and exact opener behavior.

- [ ] **Step 5: Commit Task 7.** Call `Commit-0502Task 'feat(STM32TK-0502): integrate same-process monitor UI' @('tools/stm32-monitor/src/stm32_monitor/ui_assets.py','tools/stm32-monitor/src/stm32_monitor/auth.py','tools/stm32-monitor/src/stm32_monitor/service.py','tools/stm32-monitor/src/stm32_monitor/cli.py','tools/stm32-monitor/tests/test_ui_assets.py','tools/stm32-monitor/tests/test_launcher.py','tools/stm32-monitor/tests/test_auth.py','tools/stm32-monitor/tests/test_service.py','tools/stm32-monitor/tests/test_cli.py')`.

### Task 8: Deterministic Committed Dist and Node-Free Wheel

**Files:**
- Create: `tools/stm32-monitor/ui/scripts/verify-dist.mjs`.
- Create: generated `tools/stm32-monitor/src/stm32_monitor/ui_dist/index.html`, `.vite/manifest.json`, and exact manifest-referenced `assets/<content-hashed files>`.
- Modify: `tools/stm32-monitor/ui/vite.config.ts` only to freeze final `outDir` if Task 1 did not already set the same value; `tools/stm32-monitor/pyproject.toml` only for explicit package-data; `tools/stm32-monitor/src/stm32_monitor/service.py` only to make `UiAssets.load()` the production default when injection is absent.
- Create: `tools/stm32-monitor/tests/test_ui_dist.py`; modify `tools/stm32-monitor/tests/test_package_boundary.py` only for exact RECORD, no-Node build, zipimport, and installed-wheel resource tests.

**Interfaces:**
- `npm run build` writes the version-controlled `ui_dist`; `npm run verify:dist` builds to one fresh repository-external directory, recursively compares sorted relative names and bytes, and removes only its own verified temp directory.
- Wheel package data is exactly `ui_dist/index.html`, `ui_dist/.vite/manifest.json`, and `ui_dist/assets/*`. No build hook invokes Node; wheel RECORD contains every manifest-exact resource and no `.map`/extra file.
- Produces `UiAssets.load(package="stm32_monitor",root="ui_dist"):UiAssets` by calling `resources.files(package).joinpath(root)` then the Task 7 `from_traversable`; the same code works from source, a wheel placed directly on `sys.path`, and an installed wheel.

- [ ] **Step 1: Write failing dist, manifest, size, audit, reproducibility, and wheel tests.** Assert nonempty index/manifest/asset inventory equality, hash-like asset names, no source map, remote URL, inline script/style, `eval`, `new Function`, service worker, aggregate ECharts import/bundle, size budgets, byte-identical rebuild, and a fake `node.cmd`/`npm.cmd` marker untouched during Python wheel build. Include:

```python
import json
import subprocess
import zipfile

def test_wheel_record_is_exact_manifest_inventory_and_build_never_calls_node(tmp_path, monkeypatch):
    marker=tmp_path/"node-called";_prepend_fake_node(tmp_path,marker,monkeypatch)
    wheel=_build_monitor_wheel(tmp_path)
    assert not marker.exists()
    with zipfile.ZipFile(wheel) as archive:
        names=set(archive.namelist());manifest=json.loads(archive.read("stm32_monitor/ui_dist/.vite/manifest.json"))
        expected={"stm32_monitor/ui_dist/index.html","stm32_monitor/ui_dist/.vite/manifest.json"}|{
          "stm32_monitor/ui_dist/"+name for name in manifest_files(manifest)}
        assert {name for name in names if "/ui_dist/" in name}==expected

def test_ui_assets_load_from_zipped_and_installed_wheel(tmp_path):
    wheel=_build_monitor_wheel(tmp_path)
    zipped=_run_clean_python(tmp_path,[str(wheel)],"from stm32_monitor.ui_assets import UiAssets; a=UiAssets.load(); assert a.find('/') is not None")
    installed=_install_and_run_clean_venv(tmp_path,wheel,"from stm32_monitor.ui_assets import UiAssets; a=UiAssets.load(); assert a.find('/') is not None")
    assert zipped.returncode==installed.returncode==0

def test_dist_verifier_cli_has_only_verify_and_list(controlled_node, ui_root):
    verify=subprocess.run([controlled_node,ui_root/"scripts/verify-dist.mjs"],cwd=ui_root,text=True,capture_output=True)
    listed=subprocess.run([controlled_node,ui_root/"scripts/verify-dist.mjs","--list"],cwd=ui_root,text=True,capture_output=True)
    unknown=subprocess.run([controlled_node,ui_root/"scripts/verify-dist.mjs","--unknown"],cwd=ui_root,text=True,capture_output=True)
    assert verify.returncode==listed.returncode==0
    assert listed.stdout.splitlines()==sorted({"index.html",".vite/manifest.json",*manifest_files(json.loads((ui_root.parent/"src/stm32_monitor/ui_dist/.vite/manifest.json").read_text("utf-8")))})
    assert unknown.returncode!=0 and "usage: verify-dist.mjs [--list]" in unknown.stderr
```

- [ ] **Step 2: Run RED.** From `$repoRoot`, initialize this task's new `$taskRoot\npm-cache-working` by the Global Command convention and parse `$verified`; set `PYTHONPATH` exactly to Monitor/Toolkit current-source roots and `PYTHONPYCACHEPREFIX=(Join-Path $taskRoot 'pycache-red')`. Create `$taskRoot/dist-red-312` with `$python312 -m venv`, install `$verified.pythonRequirements` using `--no-index --find-links $verified.wheelhouse`, and bind `$distPython312` to its absolute interpreter. From `$uiRoot` run `Invoke-0502NpmPhase {& $npm ci --offline --cache $npmWorkingCache} 'npm ci failed'` then `& $npm run verify:dist`; from `$repoRoot` run `& $distPython312 -m pytest tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/tests/test_package_boundary.py -k 'ui or wheel or node' -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'red-pytest-312')`, then `Assert-0502Support`. Expected: support/dependency setup PASS, source support hashes remain unchanged, then verifier/tests fail only because committed dist/package data are absent.

- [ ] **Step 3: Implement the complete build/compare script and explicit package data.** Vite final build is `manifest:true`, `sourcemap:false`, `outDir:"../src/stm32_monitor/ui_dist"`, `emptyOutDir:true`, with deterministic hashed entry/chunk/asset names. Use this exact verifier algorithm:

```js
// scripts/verify-dist.mjs
import {build} from "vite";import {mkdtemp,readdir,readFile,rm,stat} from "node:fs/promises";import {tmpdir} from "node:os";import {join,posix,relative,resolve} from "node:path";import {fileURLToPath} from "node:url";
const args=process.argv.slice(2);if(args.length>1||(args.length===1&&args[0]!=="--list"))throw new Error("usage: verify-dist.mjs [--list]");
const ui=resolve(fileURLToPath(new URL("..",import.meta.url))),committed=resolve(ui,"../src/stm32_monitor/ui_dist");
async function files(root,dir=root,out=[]){for(const name of (await readdir(dir)).sort()){const full=join(dir,name),info=await stat(full);if(info.isDirectory())await files(root,full,out);else out.push(relative(root,full).replaceAll("\\","/"));}return out;}
const clean=name=>{if(typeof name!=="string"||name.startsWith("/")||name.includes("\\")||name!==posix.normalize(name)||name===".."||name.startsWith("../"))throw new Error(`invalid manifest path: ${name}`);return name;};
async function manifestFiles(){const manifest=JSON.parse(await readFile(join(committed,".vite/manifest.json"),"utf8")),wanted=new Set([".vite/manifest.json","index.html"]),visit=value=>{if(Array.isArray(value))for(const item of value)visit(item);else if(value&&typeof value==="object")for(const [key,item] of Object.entries(value)){if(["file","css","assets"].includes(key))visit(item);else if(item&&typeof item==="object")visit(item);}else if(typeof value==="string")wanted.add(clean(value));};visit(manifest);const listed=[...wanted].sort(),actual=await files(committed);if(JSON.stringify(listed)!==JSON.stringify(actual))throw new Error("manifest inventory differs");return listed;}
if(args[0]==="--list"){for(const name of await manifestFiles())process.stdout.write(name+"\n");}else{await manifestFiles();const temp=await mkdtemp(join(tmpdir(),"stm32-monitor-dist-"));try{await build({root:ui,configFile:resolve(ui,"vite.config.ts"),build:{outDir:temp,emptyOutDir:true}});const left=await files(committed),right=await files(temp);if(JSON.stringify(left)!==JSON.stringify(right))throw new Error("dist inventory differs");for(const name of left){if(!Buffer.from(await readFile(join(committed,name))).equals(Buffer.from(await readFile(join(temp,name))))throw new Error(`dist bytes differ: ${name}`);}}finally{await rm(temp,{recursive:true,force:true});}}
```

Add `[tool.setuptools.package-data]` with `stm32_monitor = ["ui_dist/index.html", "ui_dist/.vite/manifest.json", "ui_dist/assets/*"]`. Build once to populate committed dist, then run verifier twice. `test_ui_dist.py` independently parses the manifest and computes gzip/raw limits; it does not trust verifier output.
Add `UiAssets.load` as `return cls.from_traversable(resources.files(package).joinpath(root))`; change the production service constructor's `None` branch to call it before bind while preserving explicit injection for Task 7 tests. `verify-dist.mjs --list` parses the committed manifest and prints exactly `.vite/manifest.json`, `index.html`, and its recursively referenced `file`, `css`, and `assets` names after checking each is a normalized relative POSIX path; duplicate/missing/extra assets fail.

- [ ] **Step 4: Run GREEN without repository drift on 3.10 and 3.12.** Execute these literal commands; each line checks `$LASTEXITCODE` before continuing:

```powershell
$supportVerifier=(Resolve-Path -LiteralPath (Join-Path $repoRoot 'tools\stm32-monitor\ui\tests\verify_support.py')).Path;$verified=(& $python312 $supportVerifier --support $supportRoot|Select-Object -Last 1|ConvertFrom-Json);if($LASTEXITCODE-ne0){throw 'support verification failed'}
$env:PYTHONPATH=(Join-Path $repoRoot 'tools\stm32-monitor\src')+[IO.Path]::PathSeparator+(Join-Path $repoRoot 'tools\stm32-toolkit\src');$env:PYTHONDONTWRITEBYTECODE='1';$env:PYTHONPYCACHEPREFIX=Join-Path $taskRoot 'dist-pycache'
$venv310=Join-Path $taskRoot 'dist-green-310';& $python310 -m venv $venv310;if($LASTEXITCODE-ne0){throw '310 venv failed'};$distPython310=(Resolve-Path (Join-Path $venv310 'Scripts\python.exe')).Path
& $distPython310 -m pip install --no-index --find-links ([string]$verified.wheelhouse) @($verified.pythonRequirements);if($LASTEXITCODE-ne0){throw '310 install failed'}
$venv312=Join-Path $taskRoot 'dist-green-312';& $python312 -m venv $venv312;if($LASTEXITCODE-ne0){throw '312 venv failed'};$distPython312=(Resolve-Path (Join-Path $venv312 'Scripts\python.exe')).Path
& $distPython312 -m pip install --no-index --find-links ([string]$verified.wheelhouse) @($verified.pythonRequirements);if($LASTEXITCODE-ne0){throw '312 install failed'}
Push-Location $uiRoot;try{Invoke-0502NpmPhase {& $npm ci --offline --cache $npmWorkingCache} 'npm ci failed';& $npm run build;if($LASTEXITCODE-ne0){throw 'build failed'};& $npm run verify:dist;if($LASTEXITCODE-ne0){throw 'verify one failed'};& $npm run verify:dist;if($LASTEXITCODE-ne0){throw 'verify two failed'}}finally{Pop-Location};Assert-0502Support|Out-Null
& $distPython310 -m pytest tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/tests/test_package_boundary.py -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'dist-pytest-310');if($LASTEXITCODE-ne0){throw '310 dist tests failed'}
$env:PYTHONPYCACHEPREFIX=Join-Path $taskRoot 'dist-pycache-310';& $distPython310 -m compileall -q tools/stm32-monitor/src;if($LASTEXITCODE-ne0){throw '310 compileall failed'}
$env:PYTHONPYCACHEPREFIX=Join-Path $taskRoot 'dist-pycache-312';& $distPython312 -m pytest tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/tests/test_package_boundary.py -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'dist-pytest-312');if($LASTEXITCODE-ne0){throw '312 dist tests failed'}
& $distPython312 -m compileall -q tools/stm32-monitor/src;if($LASTEXITCODE-ne0){throw '312 compileall failed'}
$status=@(& $git -C $repoRoot status --porcelain=v1 --untracked-files=all);if($LASTEXITCODE-ne0 -or $status.Count){throw 'dist gate changed repository'}
```

Expected: all PASS, byte-identical output, 3.10/3.12 zip/installed resources, no Node marker, exact RECORD, and no repository pycache/basetemp.

- [ ] **Step 5: Commit Task 8.** Run `$generated=@(& $node (Join-Path $uiRoot 'scripts/verify-dist.mjs') --list | ForEach-Object { 'tools/stm32-monitor/src/stm32_monitor/ui_dist/'+$_ })`; reject empty, duplicate, non-manifest, or non-hash `assets/` names; then call `Commit-0502Task 'build(STM32TK-0502): package deterministic monitor UI' (@('tools/stm32-monitor/ui/scripts/verify-dist.mjs','tools/stm32-monitor/ui/vite.config.ts','tools/stm32-monitor/pyproject.toml','tools/stm32-monitor/src/stm32_monitor/service.py','tools/stm32-monitor/src/stm32_monitor/ui_assets.py','tools/stm32-monitor/tests/test_ui_dist.py','tools/stm32-monitor/tests/test_package_boundary.py')+$generated)`.

### Task 9: Unified `0.5.0` Python, Plugin, Setup, Skill, and Documentation Release

**Files:**
- Modify: `tools/stm32-toolkit/pyproject.toml`, `src/stm32_toolkit/__init__.py`, `src/stm32_toolkit/cli.py`; `tools/stm32-monitor/pyproject.toml`, `src/stm32_monitor/__init__.py`, `protocol.py`, `runtime.py`.
- Create: `bin/stm32-monitor.cmd`, `skills/stm32-monitor/SKILL.md`, `tools/stm32-toolkit/tests/test_0502_release_version.py`, `test_0502_release_docs.py`.
- Modify: `bin/stm32-toolkit-mcp.cmd`, `bin/setup-stm32-env.ps1`, `skills/setup-stm32-env/SKILL.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `README.md`, `README_zh-CN.md`, `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md`, `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`.
- Modify exact current-output tests: Monitor `test_cli.py`, `test_exports.py`, `test_models.py`, `test_package_boundary.py`, `test_runtime.py`, `test_service.py`; Toolkit `test_cli.py`, `test_build_runner.py`, `test_hardware_workflows.py`, `test_mcp_migration_build.py`, current-generated assertions in `test_migration_plan.py`, `test_plugin_layout.py`, `test_setup_runtime.py`. Preserve historical/invalid previous-version fixtures and `requirements/follow-on-skills/stm32-monitor/SKILL.md` byte-identically.

**Interfaces:**
- Both distributions/packages/CLI/protocol/runtime records, Plugin manifest, launchers, managed setup, active Skills, README, and active tests agree on `0.5.0`; Monitor dependencies remain exactly `stm32-toolkit==0.5.0` and `aiohttp>=3.9,<4`.
- Both CMD launchers select only `${CLAUDE_PLUGIN_DATA}\runtime\0.5.0\Scripts\python.exe`, preserve argv/exit, and have no fallback. Setup Check is read-only; Bootstrap/Repair stages both local distributions plus Toolkit probe extra, verifies exact versions/doctor/Monitor CLI/UI resources, then atomically promotes and quarantines healthy or broken 0.4.0 as existing policy requires.
- Plugin discovers exactly eight active release Skills. Monitor Skill gets project context, explains observation-only/zero-presets/no-auto behavior, requires explicit open request, then runs foreground managed `open`.

- [ ] **Step 1: Write failing centralized version, launcher, setup, Plugin, and active-doc tests.** Assert exact Python metadata/dependencies/protocol/runtime constants, wheel filenames, CMD interpreter/argv/fallback absence, 0.4->0.5 Check/Repair/rollback/UI manifest, eight Skills, historical Skill blob equality, explicit open, zero presets, project isolation, CSV/JSONL, and 0.6 deferrals. Use:

```python
import json
import tomllib
from pathlib import Path
import stm32_monitor
import stm32_toolkit
from stm32_monitor.protocol import MONITOR_VERSION

ROOT=Path(__file__).resolve().parents[3]
def discovered_skills() -> set[str]:
    return {path.parent.name for path in (ROOT/"skills").glob("*/SKILL.md") if path.is_file()}

def test_all_active_0502_surfaces_are_unified():
    toolkit=tomllib.loads((ROOT/"tools/stm32-toolkit/pyproject.toml").read_text("utf-8"))
    monitor=tomllib.loads((ROOT/"tools/stm32-monitor/pyproject.toml").read_text("utf-8"))
    assert toolkit["project"]["version"]==stm32_toolkit.__version__=="0.5.0"
    assert monitor["project"]["version"]==stm32_monitor.__version__==MONITOR_VERSION=="0.5.0"
    assert monitor["project"]["dependencies"]==["stm32-toolkit==0.5.0","aiohttp>=3.9,<4"]
    assert json.loads((ROOT/".claude-plugin/plugin.json").read_text("utf-8"))["version"]=="0.5.0"
    assert discovered_skills()=={"setup-stm32-env","migrate-keil","configure-stm32-project","build-firmware","flash-firmware","debug-firmware","read-var","stm32-monitor"}
```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-toolkit/tests/test_0502_release_version.py tools/stm32-toolkit/tests/test_0502_release_docs.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'red-312')`, then run `& $python310 -m pytest tools/stm32-toolkit/tests/test_0502_release_version.py tools/stm32-toolkit/tests/test_0502_release_docs.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'red-310')`. Expected: FAIL only on active 0.4.0 surfaces, absent Monitor CMD/Skill, seven-Skill count, and old setup contents.

- [ ] **Step 3: Apply exact active-surface edits and no historical mass replacement.** Set version authorities, replace runtime's literal with imported `MONITOR_VERSION`, update current-output assertions only, implement fixed CMD selectors, and update setup validation. Create the active Skill exactly:

````markdown
---
name: stm32-monitor
description: Use when a user explicitly asks to open the project-isolated STM32 Monitor UI.
---

# Open STM32 Monitor

1. Call `stm32_project_context`; stop on non-ok and never guess project, target, ELF, SVD, address, or probe.
2. Explain that the UI is observation-only, starts with zero presets, and never connects a probe or starts sampling automatically.
3. Continue only after the user's explicit request to open this project's UI.
4. Run in the foreground:

   ```powershell
   & '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
   ```

Never print, persist, copy, or log the fragment URL. Connect, group creation, and sampling remain explicit page actions.
````

Update both READMEs to name eight Skills, managed `runtime/0.5.0`, explicit `stm32-monitor open`, zero groups/presets, project isolation, explicit connect/start, verified CSV/JSONL and user group schema. Their `Deferred to 0.6.0` section names every global 0.6 exclusion. Split the phase plan/roadmap 0.5 and 0.6 rows, leave 0.5 unchecked pending acceptance, and state 0.6 implementation cannot begin before 0.5 acceptance. Do not edit historical specs/reports/requirement Skill.

- [ ] **Step 4: Run GREEN across release surfaces and both Pythons.** For `$python310` and `$python312`, run the four exact Step 2 paths plus Monitor `test_cli.py test_exports.py test_models.py test_package_boundary.py test_runtime.py test_service.py` and Toolkit `test_cli.py test_build_runner.py test_hardware_workflows.py test_mcp_migration_build.py test_migration_plan.py test_plugin_layout.py test_setup_runtime.py`, with `-q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'release-310')` or `release-312`. Run `& $python312 -m build --no-isolation --wheel --outdir (Join-Path $taskRoot 'wheels') tools/stm32-toolkit` and the same command for `tools/stm32-monitor`; assert exactly the two named 0.5.0 wheels. Run both absolute CMD launchers with `--help` against managed `runtime/0.5.0`, then `& $git diff --exit-code $AcceptedBase -- requirements/follow-on-skills/stm32-monitor/SKILL.md`. Expected: every command PASS.

- [ ] **Step 5: Commit Task 9.** Call `Commit-0502Task 'feat(STM32TK-0502): promote unified monitor release 0.5.0' @('tools/stm32-toolkit/pyproject.toml','tools/stm32-toolkit/src/stm32_toolkit/__init__.py','tools/stm32-toolkit/src/stm32_toolkit/cli.py','tools/stm32-monitor/pyproject.toml','tools/stm32-monitor/src/stm32_monitor/__init__.py','tools/stm32-monitor/src/stm32_monitor/protocol.py','tools/stm32-monitor/src/stm32_monitor/runtime.py','bin/stm32-monitor.cmd','skills/stm32-monitor/SKILL.md','tools/stm32-toolkit/tests/test_0502_release_version.py','tools/stm32-toolkit/tests/test_0502_release_docs.py','bin/stm32-toolkit-mcp.cmd','bin/setup-stm32-env.ps1','skills/setup-stm32-env/SKILL.md','.claude-plugin/plugin.json','.claude-plugin/marketplace.json','README.md','README_zh-CN.md','docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md','docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md','tools/stm32-monitor/tests/test_cli.py','tools/stm32-monitor/tests/test_exports.py','tools/stm32-monitor/tests/test_models.py','tools/stm32-monitor/tests/test_package_boundary.py','tools/stm32-monitor/tests/test_runtime.py','tools/stm32-monitor/tests/test_service.py','tools/stm32-toolkit/tests/test_cli.py','tools/stm32-toolkit/tests/test_build_runner.py','tools/stm32-toolkit/tests/test_hardware_workflows.py','tools/stm32-toolkit/tests/test_mcp_migration_build.py','tools/stm32-toolkit/tests/test_migration_plan.py','tools/stm32-toolkit/tests/test_plugin_layout.py','tools/stm32-toolkit/tests/test_setup_runtime.py')`.

### Task 10: Exact Windows Release-Gate Controller Without a Handoff Packet

**Files:**
- Create: `tools/release/run_0502_windows_gates.ps1`.
- Create: `tools/release/verify_0502_release.py`.
- Create: `tools/stm32-toolkit/tests/test_0502_release_gate_controller.py`.

**Interfaces:**
- Parameters are exactly rooted absolute `RepoRoot`, repository-external empty `EvidenceRoot`, read-only repository-external `SupportRoot`, full `CodeHead`, and absolute `Git`, `Node`, `Npm`, `Python310`, `Python312`, `CmdExe`. Chromium, npm cache, advisory-cache capability, wheelhouse, and exact dependency artifacts come only from the verified support manifest. There is no packet path, packet object, packet signature, hidden checkout, optional tool alias, or remote operation.
- The controller is PowerShell 5.1-compatible, fail-fast, invokes every executable by its resolved absolute variable, rejects duplicate resolved tool paths and Python version aliases, mechanically derives the exhaustive no-renames `acceptedBase..CodeHead` path/status inventory, hashes present changed files, and writes logs/inventory/measurements only below `EvidenceRoot`.
- Evidence JSON is terminal gate evidence, not a handoff and never an implementation input. The SDD ledger transports only the Git SHA.
- Test inventories are collected mechanically. Within each Python/version partition every nodeid must occur exactly once; all collected nodeids must equal all assigned nodeids. Node coverage/a11y and Playwright functional/performance specs are disjoint. A duplicate or omitted test aborts before execution.
- After verified support and before its first npm phase, the controller creates only the new ordinary `$EvidenceRoot\npm-cache-working`, mechanically copies the verified read-only source cache, and sets npm's cache environment only to that copy. Recording tests assert the copy is non-reparse and initially empty, every `ci`/`audit` argument and npm cache environment value names that copy rather than `supportInfo.npmCache`, source manifest/tree hashes are reverified before and after each npm phase and at controller exit, and a changed source/hash check aborts before the next gate.

- [ ] **Step 1: Write failing PowerShell AST, alias/duplicate, diff-inventory, and fail-fast tests.** Parse the helper with the PowerShell AST; require exact parameters; forbid bare `git/node/npm/npx/python/python3/py/uv/pip`, `Get-Command`, `where.exe`, `Invoke-Expression`, web commands, packet/signature text, and remote Git verbs. Execute recording tools from paths containing spaces. Create a small Git repository whose accepted-base..head includes add/modify/delete/case-sensitive names and assert the external inventory is exhaustive; pass duplicate tool paths and duplicate recorded nodeids and assert failure before the first product gate. Core:

```python
import json,os,subprocess,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]
CONTROLLER=ROOT/"tools/release/run_0502_windows_gates.ps1"
VERIFY=ROOT/"tools/release/verify_0502_release.py"

def test_controller_has_no_packet_remote_or_ambient_tool_path():
    ast=powershell_ast(CONTROLLER)
    assert ast["errors"]==[]
    assert ast["parameters"]==["RepoRoot","EvidenceRoot","SupportRoot","CodeHead","Git","Node","Npm","Python310","Python312","CmdExe"]
    forbidden={"git","node","npm","npx","python","python3","py","uv","pip","curl","wget"}
    assert forbidden.isdisjoint({str(x).casefold() for x in ast["commands"]})
    text=CONTROLLER.read_text("utf-8").casefold()
    assert all(word not in text for word in ("returnpacket","handoffsignature","git push","git fetch","gh pr","invoke-expression"))

def test_controller_rejects_duplicate_tool_identity_before_gates(tmp_path):
    result=run_controller(tmp_path,node=RECORDER,npm=RECORDER)
    assert result.returncode!=0
    assert "duplicate tool identity" in result.stderr
    assert not (tmp_path/"evidence"/"node-npm-ci.log").exists()

def test_raw_git_inventory_requires_and_consumes_the_trailing_nul(tmp_path):
    repo=git_repo_with_add_modify_delete_and_names(tmp_path,["Case.txt","space name.txt"])
    ok=run_controller(repo,stop_after="inventory")
    assert ok.returncode==0 and inventory(ok)==[("A","Case.txt"),("A","space name.txt"),("D","deleted.txt"),("M","modified.txt")]
    bad=run_controller(repo,git=git_without_final_nul_exe(tmp_path),stop_after="inventory")
    assert bad.returncode!=0 and "trailing NUL" in bad.stderr

def test_rejects_case_alias_junction_and_unverified_support_before_gates(tmp_path):
    for mutation in (wrong_case_repo_path,junction_tool_path,changed_support_byte):
        result=run_controller_with_mutation(tmp_path,mutation)
        assert result.returncode!=0 and not first_product_gate_log(result).exists()

def test_requires_empty_nonoverlapping_evidence_and_support_roots(tmp_path):
    for mutation in (nonempty_evidence,evidence_inside_repo,repo_inside_evidence,support_inside_repo,repo_inside_support,evidence_inside_support,support_inside_evidence,equal_roots):
        result=run_controller_with_mutation(tmp_path,mutation)
        assert result.returncode!=0 and not any((tmp_path/"evidence").glob("*.log"))

def test_controller_copies_only_verified_npm_cache_and_rechecks_source_before_after_phases(tmp_path):
    success=run_controller_with_recording_npm(tmp_path)
    assert success.returncode==0
    records=recorded_npm_phases(success)
    assert records[0].cache==tmp_path/"evidence"/"npm-cache-working"
    assert all(record.cache==records[0].cache and record.cache!=verified_support_cache(tmp_path) for record in records)
    assert source_hash_checks(success)==["before-copy","after-copy","before-node-npm-ci","after-node-npm-ci","before-node-production-audit","after-node-production-audit","final"]
    changed=run_controller_with_recording_npm(tmp_path,mutate_support_after="node-npm-ci")
    assert changed.returncode!=0 and "support manifest or source tree changed" in changed.stderr
    assert "node-typecheck" not in recorded_gate_names(changed)

def test_generic_nul_parser_allows_odd_ls_files_count_but_diff_requires_pairs(tmp_path):
    assert run_controller(git_repo_with_one_tracked_file(tmp_path),stop_after="tracked-manifest").returncode==0
    result=run_controller(tmp_path,git=git_with_odd_diff_fields_exe(tmp_path),stop_after="inventory")
    assert result.returncode!=0 and "diff inventory is malformed" in result.stderr

def test_changed_monitor_and_toolkit_files_use_integer_branch_counts(tmp_path):
    repo=tmp_path/"repo";monitor=repo/"tools/stm32-monitor/src/stm32_monitor/auth.py";toolkit=repo/"tools/stm32-toolkit/src/stm32_toolkit/cli.py"
    for path in (monitor,toolkit): path.parent.mkdir(parents=True,exist_ok=True);path.write_text("VALUE=1\n","utf-8")
    inventory=tmp_path/"inventory.json";inventory.write_text(json.dumps([{"status":"M","path":monitor.relative_to(repo).as_posix()},{"status":"M","path":toolkit.relative_to(repo).as_posix()}]),"utf-8")
    monitor_json=tmp_path/"monitor.json";monitor_json.write_text(json.dumps({"files":{str(monitor.resolve()):{"summary":{"num_statements":1,"covered_lines":1,"num_branches":10,"covered_branches":9,"percent_covered":0.0}}}}),"utf-8")
    toolkit_json=tmp_path/"toolkit.json";toolkit_json.write_text(json.dumps({"files":{str(toolkit.resolve()):{"summary":{"num_statements":1,"covered_lines":1,"num_branches":0,"covered_branches":0,"percent_covered":0.0}}}}),"utf-8")
    command=[sys.executable,str(VERIFY),"coverage","--repo",str(repo.resolve()),"--inventory",str(inventory),"--coverage",str(monitor_json),"--coverage",str(toolkit_json)]
    assert subprocess.run(command,text=True,capture_output=True).returncode==0
    monitor_json.write_text(json.dumps({"files":{str(monitor.resolve()):{"summary":{"num_statements":1,"covered_lines":1,"num_branches":100,"covered_branches":89,"percent_covered":100.0}}}}),"utf-8")
    failed=subprocess.run(command,text=True,capture_output=True);assert failed.returncode!=0 and "below 90" in failed.stderr
```

- [ ] **Step 2: Run RED.** Set `STM32_0502_TEST_POWERSHELL` and `STM32_0502_TEST_GIT` to controlled absolute paths, then run `& $python312 -m pytest tools/stm32-toolkit/tests/test_0502_release_gate_controller.py -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL because the controller is absent.

- [ ] **Step 3: Implement the complete PS5.1 controller and exact gate inventory.** Start the script with this exact validation/inventory/process core; all later gate calls use `Invoke-0502Gate` and never `&` a literal executable name:

```powershell
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$RepoRoot,[Parameter(Mandatory=$true)][string]$EvidenceRoot,
 [Parameter(Mandatory=$true)][string]$SupportRoot,[Parameter(Mandatory=$true)][string]$CodeHead,[Parameter(Mandatory=$true)][string]$Git,
 [Parameter(Mandatory=$true)][string]$Node,[Parameter(Mandatory=$true)][string]$Npm,
 [Parameter(Mandatory=$true)][string]$Python310,[Parameter(Mandatory=$true)][string]$Python312,[Parameter(Mandatory=$true)][string]$CmdExe)
Set-StrictMode -Version 2.0;$ErrorActionPreference='Stop'
$AcceptedBase='bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'
function Resolve-0502Path([string]$Value,[string]$Label,[bool]$Leaf){
 if([string]::IsNullOrWhiteSpace($Value)-or-not[IO.Path]::IsPathRooted($Value)){throw "$Label must be rooted"}
 $full=[IO.Path]::GetFullPath($Value);if($full-cne$Value){throw "$Label must be normalized"}
 $resolved=(Resolve-Path -LiteralPath $full -ErrorAction Stop).Path
 if($resolved-cne$full){throw "$Label resolves through a case or reparse alias"}
 if($Leaf-and-not[IO.File]::Exists($resolved)){throw "$Label must be a file"};return $resolved
}
$RepoRoot=Resolve-0502Path $RepoRoot 'RepoRoot' $false;$EvidenceRoot=Resolve-0502Path $EvidenceRoot 'EvidenceRoot' $false;$SupportRoot=Resolve-0502Path $SupportRoot 'SupportRoot' $false
$Git=Resolve-0502Path $Git 'Git' $true;$Node=Resolve-0502Path $Node 'Node' $true;$Npm=Resolve-0502Path $Npm 'Npm' $true
$Python310=Resolve-0502Path $Python310 'Python310' $true;$Python312=Resolve-0502Path $Python312 'Python312' $true;$CmdExe=Resolve-0502Path $CmdExe 'CmdExe' $true
if($CodeHead-notmatch'^[0-9a-f]{40}$'){throw 'CodeHead must be one full SHA'}
function Assert-0502Separate([string]$Left,[string]$Right,[string]$Label){$a=$Left.TrimEnd('\')+'\';$b=$Right.TrimEnd('\')+'\';if([string]::Equals($Left,$Right,[StringComparison]::OrdinalIgnoreCase) -or $a.StartsWith($b,[StringComparison]::OrdinalIgnoreCase) -or $b.StartsWith($a,[StringComparison]::OrdinalIgnoreCase)){throw "$Label roots overlap"}}
Assert-0502Separate $RepoRoot $EvidenceRoot 'RepoRoot/EvidenceRoot';Assert-0502Separate $RepoRoot $SupportRoot 'RepoRoot/SupportRoot';Assert-0502Separate $EvidenceRoot $SupportRoot 'EvidenceRoot/SupportRoot'
if(@(Get-ChildItem -LiteralPath $EvidenceRoot -Force -ErrorAction Stop).Count-ne0){throw 'EvidenceRoot must be empty before any log'}
$identities=@($Git,$Node,$Npm,$Python310,$Python312,$CmdExe)|ForEach-Object{$_.ToLowerInvariant()}
if(@($identities|Sort-Object -Unique).Count-ne$identities.Count){throw 'duplicate tool identity'}
function Invoke-0502Capture([string]$Name,[string]$WorkingDirectory,[string]$Executable,[string[]]$Arguments){
 $log=Join-Path $EvidenceRoot ($Name+'.log');Push-Location -LiteralPath $WorkingDirectory
 try{$lines=@(& $Executable @Arguments 2>&1);$exit=$LASTEXITCODE}finally{Pop-Location}
 $lines|Set-Content -Encoding UTF8 -LiteralPath $log;if($exit-ne0){throw "$Name failed with exit $exit"};return $lines
}
function Invoke-0502Gate([string]$Name,[string]$WorkingDirectory,[string]$Executable,[string[]]$Arguments){[void](Invoke-0502Capture $Name $WorkingDirectory $Executable $Arguments)}
$status=@(Invoke-0502Capture 'git-status-before' $RepoRoot $Git @('-C',$RepoRoot,'status','--porcelain=v1','--untracked-files=all'));if($status.Count){throw 'repository is dirty'}
$head=(@(Invoke-0502Capture 'git-head' $RepoRoot $Git @('-C',$RepoRoot,'rev-parse','HEAD'))[-1]).Trim();if($head-cne$CodeHead){throw 'worktree is not CodeHead'}
Invoke-0502Gate 'git-accepted-ancestor' $RepoRoot $Git @('-C',$RepoRoot,'merge-base','--is-ancestor',$AcceptedBase,$CodeHead)
Invoke-0502Gate 'git-diff-check' $RepoRoot $Git @('-C',$RepoRoot,'diff','--check',"$AcceptedBase..$CodeHead")
function Invoke-0502GitDiffRaw {
 $start=New-Object Diagnostics.ProcessStartInfo;$start.FileName=$Git;$start.WorkingDirectory=$RepoRoot;$start.UseShellExecute=$false;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true;$start.CreateNoWindow=$true;$start.Arguments='diff --name-status --no-renames -z '+$AcceptedBase+'..'+$CodeHead
 $process=New-Object Diagnostics.Process;$process.StartInfo=$start;if(-not$process.Start()){throw 'raw git process did not start'};$stderrTask=$process.StandardError.ReadToEndAsync();$memory=New-Object IO.MemoryStream;$process.StandardOutput.BaseStream.CopyTo($memory);$process.WaitForExit();$stderr=$stderrTask.Result
 if($process.ExitCode-ne0){throw ('raw git diff failed: '+$stderr)};return $memory.ToArray()
}
function Split-0502NulBytes([byte[]]$Bytes){
 if($Bytes.Length-eq0-or$Bytes[$Bytes.Length-1]-ne0){throw 'raw git inventory requires trailing NUL'};$utf8=New-Object Text.UTF8Encoding($false,$true);$parts=New-Object Collections.Generic.List[string];$start=0
 for($index=0;$index-lt$Bytes.Length;$index++){if($Bytes[$index]-eq0){if($index-eq$start){if($index-ne$Bytes.Length-1){throw 'raw git inventory contains an empty interior field'}}else{$parts.Add($utf8.GetString($Bytes,$start,$index-$start))};$start=$index+1}}
 if($start-ne$Bytes.Length){throw 'raw NUL stream did not terminate'};return $parts.ToArray()
}
$raw=Invoke-0502GitDiffRaw;[IO.File]::WriteAllBytes((Join-Path $EvidenceRoot 'git-diff-inventory.raw'),$raw);$parts=Split-0502NulBytes $raw;if(($parts.Count%2)-ne0){throw 'diff inventory is malformed'}
$seen=@{};$inventory=@();for($i=0;$i-lt$parts.Count;$i+=2){$change=$parts[$i];$path=$parts[$i+1];$key=$path.ToLowerInvariant();if($seen.ContainsKey($key)){throw 'duplicate diff path'};$seen[$key]=$true
 $full=Join-Path $RepoRoot $path;if($change-eq'D'){$inventory+=[ordered]@{status=$change;path=$path;bytes=$null;sha256=$null}}
 else{$item=Get-Item -LiteralPath $full;$inventory+=[ordered]@{status=$change;path=$path;bytes=$item.Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $full).Hash.ToLowerInvariant()}}}
$inventory|ConvertTo-Json -Depth 4|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json')
```

`verify_0502_release.py` is the complete deterministic data checker invoked by the controller. It has three subcommands and no network/process/checkout behavior: `scope` validates every inventory row against the exhaustive 0502 path policy and required active surfaces; `coverage` maps every changed product `.py` to exactly one coverage JSON row and enforces branch >=90 from integer counts; `static` validates manifest closure, eight active Skills, required active docs/marketplace, and forbidden 0.6 text/asset paths. Support verification is owned by Task 1 and invoked from its frozen path. Its core is:

```python
from __future__ import annotations
import argparse,json
from pathlib import Path

REQUIRED_ACTIVE={".claude-plugin/plugin.json",".claude-plugin/marketplace.json","README.md","README_zh-CN.md","bin/setup-stm32-env.ps1","bin/stm32-monitor.cmd","bin/stm32-toolkit-mcp.cmd","skills/setup-stm32-env/SKILL.md","skills/stm32-monitor/SKILL.md","docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md","docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md"}
EXACT_PLAN={"docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md","docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md","docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md","docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md","docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md","docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md"}
PREFIXES=("tools/stm32-monitor/ui/","tools/stm32-monitor/src/stm32_monitor/","tools/stm32-monitor/tests/","tools/stm32-toolkit/src/stm32_toolkit/","tools/stm32-toolkit/tests/","tools/release/")
SKILLS={"setup-stm32-env","migrate-keil","configure-stm32-project","build-firmware","flash-firmware","debug-firmware","read-var","stm32-monitor"}
FORBIDDEN=("host-target test","diagnostic hypothesis","quality dashboard","annotation bookmark","cross-run comparison")
def read(path:Path): return json.loads(path.read_text("utf-8"))
def scope(args):
 repo=Path(args.repo).resolve(strict=True);rows=read(Path(args.inventory));paths={row["path"] for row in rows}
 for row in rows:
  path=row["path"]
  if row["status"] not in {"A","M","D"} or not (path in REQUIRED_ACTIVE or path in EXACT_PLAN or path in {".gitignore","tools/stm32-monitor/pyproject.toml","tools/stm32-toolkit/pyproject.toml"} or path.startswith(PREFIXES)): raise SystemExit(f"out-of-scope changed path: {path}")
 if not REQUIRED_ACTIVE<=paths or not EXACT_PLAN<=paths: raise SystemExit("required active release/plan surface missing from inventory")
 for row in rows:
  name=row["path"]
  if row["status"]!="D" and (name.startswith("tools/stm32-monitor/src/") or name.startswith("tools/stm32-toolkit/src/") or name.startswith("tools/stm32-monitor/ui/src/") or name.startswith("skills/")):
   path=repo/name
   if path.is_file() and path.suffix.casefold() not in {".png",".ico",".woff",".woff2"}:
    text=path.read_text("utf-8",errors="strict").casefold()
    if any(term in text for term in FORBIDDEN): raise SystemExit(f"0.6 implementation term in active product: {name}")
def coverage(args):
 repo=Path(args.repo).resolve(strict=True);rows=read(Path(args.inventory));documents=[read(Path(name)) for name in args.coverage]
 records={}
 for document in documents:
  for name,value in document["files"].items(): records.setdefault(str(Path(name).resolve()).casefold(),[]).append(value)
 changed=[repo/row["path"] for row in rows if row["status"]!="D" and (row["path"].startswith("tools/stm32-monitor/src/stm32_monitor/") or row["path"].startswith("tools/stm32-toolkit/src/stm32_toolkit/")) and row["path"].endswith(".py")]
 for path in changed:
  found=records.get(str(path.resolve(strict=True)).casefold(),[])
  if len(found)!=1: raise SystemExit(f"changed product coverage row count is {len(found)}: {path}")
  summary=found[0]["summary"];total=int(summary["num_branches"]);covered=int(summary["covered_branches"])
  if total<0 or covered<0 or covered>total: raise SystemExit(f"invalid branch counts: {path}")
  percent=100.0 if total==0 else covered*100.0/total
  if percent<90.0: raise SystemExit(f"changed product branch coverage below 90: {path}")
def static(args):
 repo=Path(args.repo).resolve(strict=True);dist=repo/"tools/stm32-monitor/src/stm32_monitor/ui_dist";manifest=read(dist/".vite/manifest.json");wanted={"index.html",".vite/manifest.json"}
 def visit(value):
  if isinstance(value,dict):
   for key,item in value.items():
    if key in {"file","css","assets"}: visit(item)
    elif isinstance(item,(dict,list)): visit(item)
  elif isinstance(value,list):
   for item in value: visit(item)
  elif isinstance(value,str): wanted.add(value)
 visit(manifest);actual={path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()}
 if actual!=wanted: raise SystemExit("static manifest closure differs from tracked assets")
 active={path.parent.name for path in (repo/"skills").glob("*/SKILL.md")}
 if active!=SKILLS: raise SystemExit("active Skill set differs from release contract")
 inventory={row["path"] for row in read(Path(args.inventory))}
 if not REQUIRED_ACTIVE<=inventory: raise SystemExit("active docs/marketplace are absent from inventory")
def main():
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True)
 p=sub.add_parser("scope");p.add_argument("--repo",required=True);p.add_argument("--inventory",required=True);p.set_defaults(run=scope)
 p=sub.add_parser("coverage");p.add_argument("--repo",required=True);p.add_argument("--inventory",required=True);p.add_argument("--coverage",action="append",required=True);p.set_defaults(run=coverage)
 p=sub.add_parser("static");p.add_argument("--repo",required=True);p.add_argument("--inventory",required=True);p.set_defaults(run=static)
 args=parser.parse_args();args.run(args)
if __name__=="__main__": main()
```

The PowerShell file then executes one linear fail-fast list in this exact order: support verification; tool version/identity; changed-path scope/forbidden-0.6/historical-Skill blob; offline npm ci, typechecks, lint, disjoint unit coverage and axe, build, verify-dist twice, conditional offline audit; fresh external test venvs; mechanically collected/disjoint Monitor 3.10 complete and Monitor 3.12 coverage partitions; mechanically sharded Toolkit 3.12 coverage; per-changed-product Python branch gate; clean-source wheels; fresh 3.10/3.12 installed-wheel smoke with no repository `PYTHONPATH`; real CMD launchers; controlled Chromium functional/security/five-minute gates; final static/Skill closure, tracked-byte manifest, diff check, and clean status. Every invocation below is literal and fail-fast; no second generated driver exists.

The executable tail defines its partitions mechanically and invokes these commands; the implementation expands the shown arrays literally, not through a second script:

```powershell
function Get-0502NodeIds([string]$Name,[string]$Python,[string[]]$Paths,[string[]]$Extra){
 $lines=@(Invoke-0502Capture $Name $RepoRoot $Python (@('-m','pytest')+$Paths+@('--collect-only','-q','-p','no:cacheprovider')+$Extra))
 return @($lines|ForEach-Object{[string]$_}|Where-Object{$_-match'^[^=]+::'}|Sort-Object)
}
function Assert-0502ExactPartition([string]$Label,[string[]]$All,[string[]]$Assigned){
 if($All.Count-eq0){throw "$Label collection is empty"};if(@($Assigned|Sort-Object -Unique).Count-ne$Assigned.Count){throw "$Label duplicate nodeid"}
 if(@(Compare-Object ($All|Sort-Object) ($Assigned|Sort-Object)).Count-ne0){throw "$Label omitted or added nodeid"}
}
$uiRoot=(Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\ui')).Path;$supportVerifier=(Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\ui\tests\verify_support.py')).Path
function Assert-0502Support([string]$Phase){
 $info=(@(Invoke-0502Capture ('verify-support-'+$Phase) $RepoRoot $Python312 @($supportVerifier,'--support',$SupportRoot,'--package',(Join-Path $uiRoot 'package.json'),'--package-lock',(Join-Path $uiRoot 'package-lock.json')))[-1]|ConvertFrom-Json)
 if($script:SupportManifestSha256){if([string]$info.supportManifestSha256-cne$script:SupportManifestSha256-or[string]$info.supportTreeSha256-cne$script:SupportTreeSha256){throw 'support manifest or source tree changed'}}
 return $info
}
function New-0502NpmWorkingCache([string]$SourceCache){
 $evidenceItem=Get-Item -LiteralPath $EvidenceRoot -Force;if(-not[IO.Path]::IsPathRooted($EvidenceRoot) -or $EvidenceRoot-cne[IO.Path]::GetFullPath($EvidenceRoot) -or ($evidenceItem.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw 'EvidenceRoot must be an existing canonical non-reparse external directory'}
 $destination=Join-Path $EvidenceRoot 'npm-cache-working';if(Test-Path -LiteralPath $destination){$existing=(Resolve-Path -LiteralPath $destination -ErrorAction Stop).Path;if($existing-cne$destination -or ((Get-Item -LiteralPath $existing -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){throw 'existing npm working cache escapes or redirects'};Remove-Item -LiteralPath $existing -Recurse -Force -ErrorAction Stop}
 New-Item -ItemType Directory -Path $destination -ErrorAction Stop|Out-Null;$rootItem=Get-Item -LiteralPath $destination -Force
 if(($rootItem.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0-or@(Get-ChildItem -LiteralPath $destination -Force).Count-ne0){throw 'npm working cache is not a new empty ordinary directory'}
 Get-ChildItem -LiteralPath $SourceCache -Force|ForEach-Object{Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force -ErrorAction Stop}
 $members=@(Get-Item -LiteralPath $destination -Force);$members+=@(Get-ChildItem -LiteralPath $destination -Force -Recurse);if(@($members|Where-Object{(($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)}).Count-ne0){throw 'npm working cache contains a reparse point'}
 foreach($member in $members){$attributes=[IO.FileAttributes]$member.Attributes;[IO.File]::SetAttributes($member.FullName,[IO.FileAttributes](([int]$attributes) -band (-bnot [int][IO.FileAttributes]::ReadOnly)))}
 $members=@(Get-Item -LiteralPath $destination -Force);$members+=@(Get-ChildItem -LiteralPath $destination -Force -Recurse)
 if(@($members|Where-Object{(($_.Attributes -band ([IO.FileAttributes]::ReadOnly -bor [IO.FileAttributes]::ReparsePoint)) -ne 0)}).Count-ne0){throw 'npm working cache retains ReadOnly or reparse attributes'}
 return (Resolve-Path -LiteralPath $destination).Path
}
function Invoke-0502NpmPhase([string]$Name,[string[]]$Arguments){Assert-0502Support ('before-'+$Name)|Out-Null;Invoke-0502Gate $Name $uiRoot $Npm $Arguments;Assert-0502Support ('after-'+$Name)|Out-Null}
$supportInfo=Assert-0502Support 'before-copy';$script:SupportManifestSha256=[string]$supportInfo.supportManifestSha256;$script:SupportTreeSha256=[string]$supportInfo.supportTreeSha256
$npmWorkingCache=New-0502NpmWorkingCache ([string]$supportInfo.npmCache);Assert-0502Support 'after-copy'|Out-Null
if((Resolve-Path -LiteralPath $Node).Path -cne [string]$supportInfo.node -or (Resolve-Path -LiteralPath $Npm).Path -cne [string]$supportInfo.npm){throw 'Node/npm paths differ from verified support'}
$nodeHash=(Get-FileHash -LiteralPath $Node -Algorithm SHA256).Hash.ToLowerInvariant();$npmHash=(Get-FileHash -LiteralPath $Npm -Algorithm SHA256).Hash.ToLowerInvariant()
if($nodeHash -cne [string]$supportInfo.nodeSha256 -or $npmHash -cne [string]$supportInfo.npmSha256){throw 'Node/npm hashes differ from verified support'}
$nodeVersion=(@(Invoke-0502Capture 'version-node' $RepoRoot $Node @('--version'))[-1]).Trim();$npmVersion=(@(Invoke-0502Capture 'version-npm' $RepoRoot $Npm @('--version'))[-1]).Trim()
if($nodeVersion -cne [string]$supportInfo.nodeVersion -or $npmVersion -cne [string]$supportInfo.npmVersion){throw 'Node/npm versions differ from verified support'}
Invoke-0502Gate 'verify-changed-scope' $RepoRoot $Python312 @('tools/release/verify_0502_release.py','scope','--repo',$RepoRoot,'--inventory',(Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'))
$historical='requirements/follow-on-skills/stm32-monitor/SKILL.md';$baseBlob=(@(Invoke-0502Capture 'historical-skill-base' $RepoRoot $Git @('-C',$RepoRoot,'rev-parse',($AcceptedBase+':'+$historical)))[-1]).Trim();$headBlob=(@(Invoke-0502Capture 'historical-skill-head' $RepoRoot $Git @('-C',$RepoRoot,'rev-parse',($CodeHead+':'+$historical)))[-1]).Trim();if($baseBlob-cne$headBlob){throw 'historical monitor Skill changed'}
$py310=(@(Invoke-0502Capture 'version-python310' $RepoRoot $Python310 @('-c','import json,sys;print(json.dumps([sys.version_info[:2],sys.executable]))'))[-1]|ConvertFrom-Json)
$py312=(@(Invoke-0502Capture 'version-python312' $RepoRoot $Python312 @('-c','import json,sys;print(json.dumps([sys.version_info[:2],sys.executable]))'))[-1]|ConvertFrom-Json)
if($py310[0][0]-ne3-or$py310[0][1]-ne10-or$py312[0][0]-ne3-or$py312[0][1]-ne12){throw 'Python version alias detected'}
$env:npm_config_cache=$npmWorkingCache;$env:PLAYWRIGHT_BROWSERS_PATH='0';$env:STM32_MONITOR_CHROMIUM_EXECUTABLE=[string]$supportInfo.browser;$env:PYTHONDONTWRITEBYTECODE='1';$env:PYTHONPYCACHEPREFIX=Join-Path $EvidenceRoot 'pycache'
Invoke-0502NpmPhase 'node-npm-ci' @('ci','--offline','--cache',$npmWorkingCache);Invoke-0502Gate 'node-typecheck' $uiRoot $Npm @('run','typecheck')
Invoke-0502Gate 'node-e2e-typecheck' $uiRoot $Npm @('run','typecheck:e2e');Invoke-0502Gate 'node-lint' $uiRoot $Npm @('run','lint')
Invoke-0502Gate 'node-unit-coverage' $uiRoot $Npm @('run','test:coverage');Invoke-0502Gate 'node-a11y' $uiRoot $Npm @('run','test:a11y')
Invoke-0502Gate 'node-build' $uiRoot $Npm @('run','build');Invoke-0502Gate 'node-verify-dist-1' $uiRoot $Npm @('run','verify:dist')
Invoke-0502Gate 'node-verify-dist-2' $uiRoot $Npm @('run','verify:dist');if(-not[bool]$supportInfo.auditCache){throw 'BLOCKED: verified support has no compatible npm advisory cache'};Invoke-0502NpmPhase 'node-production-audit' @('audit','--offline','--cache',$npmWorkingCache,'--omit=dev','--audit-level=high')
$support=[string]$supportInfo.wheelhouse;$requirements=@($supportInfo.pythonRequirements|ForEach-Object{[string]$_});$sourcePath=(Join-Path $RepoRoot 'tools\stm32-monitor\src')+';'+(Join-Path $RepoRoot 'tools\stm32-toolkit\src')
$testPythons=@{};foreach($entry in @(@('310',$Python310),@('312',$Python312))){$minor=[string]$entry[0];$base=[string]$entry[1];$venv=Join-Path $EvidenceRoot ('test-'+$minor)
 Invoke-0502Gate ('venv-create-'+$minor) $EvidenceRoot $base @('-m','venv',$venv);$testPython=(Resolve-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe')).Path
 Invoke-0502Gate ('venv-install-'+$minor) $EvidenceRoot $testPython (@('-m','pip','install','--no-index','--find-links',$support)+$requirements);$testPythons[$minor]=$testPython}
$testPython310=[string]$testPythons['310'];$testPython312=[string]$testPythons['312'];$env:PYTHONPATH=$sourcePath
$monitorAll310=Get-0502NodeIds 'collect-monitor-310' $testPython310 @('tools/stm32-monitor/tests') @();$monitorAll312=Get-0502NodeIds 'collect-monitor-312' $testPython312 @('tools/stm32-monitor/tests') @()
if(@(Compare-Object $monitorAll310 $monitorAll312).Count-ne0){throw 'Monitor version inventories differ'}
$special=@('tools/stm32-monitor/tests/test_auth.py','tools/stm32-monitor/tests/test_service.py','tools/stm32-monitor/tests/test_ui_assets.py','tools/stm32-monitor/tests/test_ui_dist.py','tools/stm32-monitor/tests/test_package_boundary.py','tools/stm32-monitor/tests/test_performance.py')
$ignore=@($special|ForEach-Object{'--ignore='+$_});$monitorMain=Get-0502NodeIds 'collect-monitor-main-312' $testPython312 @('tools/stm32-monitor/tests') $ignore;$monitorSpecial=Get-0502NodeIds 'collect-monitor-special-312' $testPython312 $special @();Assert-0502ExactPartition 'Monitor 3.12' $monitorAll312 @($monitorMain+$monitorSpecial)
Invoke-0502Gate 'python310-monitor-complete' $RepoRoot $testPython310 @('-m','pytest','tools/stm32-monitor/tests','-q','-p','no:cacheprovider','--basetemp',(Join-Path $EvidenceRoot 'bt-monitor-310'))
$env:COVERAGE_FILE=Join-Path $EvidenceRoot '.coverage-monitor-312';Invoke-0502Gate 'python312-monitor-main' $RepoRoot $testPython312 (@('-m','pytest','tools/stm32-monitor/tests')+$ignore+@('-q','-p','no:cacheprovider','--cov=stm32_monitor','--cov-branch','--cov-report=','--basetemp',(Join-Path $EvidenceRoot 'bt-monitor-main-312')))
Invoke-0502Gate 'python312-monitor-special' $RepoRoot $testPython312 (@('-m','pytest')+$special+@('-q','-s','-p','no:cacheprovider','--cov=stm32_monitor','--cov-branch','--cov-append','--cov-report=','--basetemp',(Join-Path $EvidenceRoot 'bt-monitor-special-312')))
$toolkitFiles=@(Get-ChildItem -LiteralPath (Join-Path $RepoRoot 'tools\stm32-toolkit\tests') -Filter 'test_*.py' -File|ForEach-Object{$_.FullName.Substring($RepoRoot.Length+1).Replace('\','/')}|Sort-Object)
$env:COVERAGE_FILE=Join-Path $EvidenceRoot '.coverage-toolkit-312';$toolkitAll=Get-0502NodeIds 'collect-toolkit-312' $testPython312 @('tools/stm32-toolkit/tests') @();$assigned=@();for($shard=0;$shard-lt8;$shard++){$files=@();for($index=$shard;$index-lt$toolkitFiles.Count;$index+=8){$files+=$toolkitFiles[$index]};if($files.Count){$ids=Get-0502NodeIds ('collect-toolkit-shard-'+($shard+1)) $testPython312 $files @();$assigned+=$ids;Invoke-0502Gate ('python312-toolkit-shard-'+($shard+1)) $RepoRoot $testPython312 (@('-m','pytest')+$files+@('-q','-p','no:cacheprovider','--cov=stm32_toolkit','--cov-branch','--cov-append','--cov-report=','--basetemp',(Join-Path $EvidenceRoot ('bt-toolkit-'+($shard+1)))) )}}
Assert-0502ExactPartition 'Toolkit 3.12' $toolkitAll $assigned
$env:COVERAGE_FILE=Join-Path $EvidenceRoot '.coverage-monitor-312';Invoke-0502Gate 'python312-monitor-coverage-json' $RepoRoot $testPython312 @('-m','coverage','json','-o',(Join-Path $EvidenceRoot 'monitor-coverage.json'))
$env:COVERAGE_FILE=Join-Path $EvidenceRoot '.coverage-toolkit-312';Invoke-0502Gate 'python312-toolkit-coverage-json' $RepoRoot $testPython312 @('-m','coverage','json','-o',(Join-Path $EvidenceRoot 'toolkit-coverage.json'))
Invoke-0502Gate 'changed-product-branch-coverage' $RepoRoot $testPython312 @('tools/release/verify_0502_release.py','coverage','--repo',$RepoRoot,'--inventory',(Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'),'--coverage',(Join-Path $EvidenceRoot 'monitor-coverage.json'),'--coverage',(Join-Path $EvidenceRoot 'toolkit-coverage.json'))
$packageRoot=Join-Path $EvidenceRoot 'packages';$wheels=Join-Path $packageRoot 'wheels';New-Item -ItemType Directory -Force -Path $wheels|Out-Null
Invoke-0502Gate 'wheel-toolkit' $RepoRoot $testPython312 @('-m','pip','wheel','--no-index','--find-links',$support,'--no-deps','--no-build-isolation','--wheel-dir',$wheels,'tools/stm32-toolkit')
Invoke-0502Gate 'wheel-monitor' $RepoRoot $testPython312 @('-m','pip','wheel','--no-index','--find-links',$support,'--no-deps','--no-build-isolation','--wheel-dir',$wheels,'tools/stm32-monitor')
$wheelNames=@(Get-ChildItem -LiteralPath $wheels -Filter '*.whl' -File|ForEach-Object{$_.Name}|Sort-Object);if(@(Compare-Object $wheelNames @('stm32_monitor-0.5.0-py3-none-any.whl','stm32_toolkit-0.5.0-py3-none-any.whl')).Count-ne0){throw 'wheel inventory is not exact'}
$savedPythonPath=$env:PYTHONPATH;Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
try{foreach($minor in @('310','312')){$base=if($minor-eq'310'){$Python310}else{$Python312};$pluginData=Join-Path $EvidenceRoot ('installed-'+$minor);$runtime=Join-Path $pluginData 'runtime\0.5.0'
 Invoke-0502Gate ('installed-venv-'+$minor) $EvidenceRoot $base @('-m','venv',$runtime);$installedPython=(Resolve-Path -LiteralPath (Join-Path $runtime 'Scripts\python.exe')).Path
 Invoke-0502Gate ('installed-packages-'+$minor) $EvidenceRoot $installedPython @('-m','pip','install','--no-index','--find-links',$support,(Join-Path $wheels 'stm32_toolkit-0.5.0-py3-none-any.whl'),(Join-Path $wheels 'stm32_monitor-0.5.0-py3-none-any.whl'),'pyocd')
 $smoke='import importlib.metadata as m,pathlib,sys;import stm32_monitor,stm32_toolkit;from stm32_monitor.ui_assets import UiAssets;assert m.version("stm32-toolkit")==m.version("stm32-monitor")=="0.5.0";assert pathlib.Path(stm32_monitor.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve());assert UiAssets.load().find("/") is not None'
 Invoke-0502Gate ('installed-smoke-'+$minor) $EvidenceRoot $installedPython @('-I','-c',$smoke);$env:CLAUDE_PLUGIN_ROOT=$RepoRoot;$env:CLAUDE_PLUGIN_DATA=$pluginData
 Invoke-0502Gate ('launcher-monitor-'+$minor) $RepoRoot $CmdExe @('/d','/c',(Join-Path $RepoRoot 'bin\stm32-monitor.cmd'),'--help');Invoke-0502Gate ('launcher-toolkit-'+$minor) $RepoRoot $CmdExe @('/d','/c',(Join-Path $RepoRoot 'bin\stm32-toolkit-mcp.cmd'),'--help')}}
finally{if($null-ne$savedPythonPath){$env:PYTHONPATH=$savedPythonPath}else{Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue}}
$env:STM32_MONITOR_E2E_PYTHON=$testPython312;$env:STM32_MONITOR_E2E_REPO_ROOT=$RepoRoot;$env:STM32_MONITOR_E2E_EVIDENCE_ROOT=$EvidenceRoot
Invoke-0502Gate 'playwright-functional' $uiRoot $Npm @('exec','--','playwright','test','--project=chromium-1280','--project=chromium-1024','--grep-invert','five-minute')
Invoke-0502Gate 'playwright-five-minute' $uiRoot $Npm @('exec','--','playwright','test','e2e/performance.spec.ts','--project=chromium-1280','--grep','five-minute')
Invoke-0502Gate 'release-static-closure' $RepoRoot $testPython312 @('tools/release/verify_0502_release.py','static','--repo',$RepoRoot,'--inventory',(Join-Path $EvidenceRoot 'accepted-base-to-code-head-inventory.json'))
$trackedRawStart=New-Object Diagnostics.ProcessStartInfo;$trackedRawStart.FileName=$Git;$trackedRawStart.WorkingDirectory=$RepoRoot;$trackedRawStart.UseShellExecute=$false;$trackedRawStart.RedirectStandardOutput=$true;$trackedRawStart.RedirectStandardError=$true;$trackedRawStart.CreateNoWindow=$true;$trackedRawStart.Arguments='ls-files -z';$trackedProcess=New-Object Diagnostics.Process;$trackedProcess.StartInfo=$trackedRawStart;if(-not$trackedProcess.Start()){throw 'git ls-files process did not start'};$trackedError=$trackedProcess.StandardError.ReadToEndAsync();$trackedMemory=New-Object IO.MemoryStream;$trackedProcess.StandardOutput.BaseStream.CopyTo($trackedMemory);$trackedProcess.WaitForExit();if($trackedProcess.ExitCode-ne0){throw ('git ls-files failed: '+$trackedError.Result)};$tracked=Split-0502NulBytes $trackedMemory.ToArray();$trackedManifest=@();foreach($path in $tracked){$file=Join-Path $RepoRoot $path;$trackedManifest+=[ordered]@{path=$path;bytes=(Get-Item -LiteralPath $file).Length;sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()}};$trackedManifest|ConvertTo-Json -Depth 3|Set-Content -Encoding UTF8 -LiteralPath (Join-Path $EvidenceRoot 'tracked-byte-manifest.json')
Invoke-0502Gate 'git-diff-check-after' $RepoRoot $Git @('-C',$RepoRoot,'diff','--check',"$AcceptedBase..$CodeHead")
Assert-0502Support 'final'|Out-Null
$final=@(Invoke-0502Capture 'git-status-after' $RepoRoot $Git @('-C',$RepoRoot,'status','--porcelain=v1','--untracked-files=all'));if($final.Count){throw 'repository changed during gates'}
```

The recording-tool suite asserts this exact invocation order and each argument vector, including support hashes, conditional audit behavior, both coverage JSONs, changed-file mapping, two installed environments, absolute CMD use, controlled Chromium, static closure, and the final tracked-byte manifest. Any first nonzero exit prevents every later log.

- [ ] **Step 4: Run GREEN including path, alias, duplicate, inventory, and fail-fast fixtures.** With exact `STM32_0502_TEST_POWERSHELL` and `STM32_0502_TEST_GIT`, run `& $python310 -m pytest tools/stm32-toolkit/tests/test_0502_release_gate_controller.py -q -p no:cacheprovider --basetemp (Join-Path $taskRoot 'controller-310')` and the identical path under `$python312` with `controller-312`. Expected: both PASS; PS5.1 AST, trailing NUL, aliases, duplicate tools/nodeids, inventory, external logs, support hashes, and fail-fast order are asserted.

- [ ] **Step 5: Commit Task 10.** Call `Commit-0502Task 'test(STM32TK-0502): add exact Windows release gates' @('tools/release/run_0502_windows_gates.ps1','tools/release/verify_0502_release.py','tools/stm32-toolkit/tests/test_0502_release_gate_controller.py')`.

### Task 11: Stateful Real-aiohttp Browser Fixture and Strict E2E Typecheck

**Files:**
- Create: `tools/stm32-monitor/ui/e2e/fake_runtime.py`, `e2e/fixture.ts`, `e2e/fixture-contract.spec.ts`.

**Interfaces:**
- `fake_runtime.py` imports the current-source real `MonitorService`, `ProtocolResult`, `DebugFirmwareBinding`, `WatchGroup`, `WatchItem`, `ObservationBinding`, `SampleValue`, `HistoryBatchSlice`, and `HistoryPage`; browser HTTP/WS always traverses the real service/auth/static/envelope path. A JSON-line control channel may mutate producer/test evidence but never answers browser product requests.
- Service startup passes `token_factory(count)` and proves it was called once with `32`. Groups are real authoritative objects with bigint-capable revisions and ordered watches. Live subscription emits hello then state, retains a bounded journal, replays deltas after `afterEventId`, and emits `gap:true` when the cursor predates retention. History responses are `HistoryPage.create(...)` and therefore use the accepted serializer.
- Initial runtime state has zero groups, revision zero, no watches, and no producer. Group/revision/watch authority must first be created through the real rendered UI or authenticated REST route; only then can `startProducer` emit typed batches. There is no seed method or alternate producer name.
- Produces the exact interface below; `startMonitor(workspace)` returns it, safe `origin` contains scheme/host/port only, `navigate(page)` consumes/scrubs the private access URL once, and no method exposes token or fragment URL.

```ts
// e2e/fixture.ts — imports are authoritative for Task 12
import {expect,test as base,type BrowserContext,type Page} from "@playwright/test";
import type {ExportArtifact,GroupTransfer,I64,JsonValue,LiveEvent,WatchGroup} from "../src/api/contract";
export type DropTotals={subscriber:I64;history:I64;deadline:I64;service:I64};
export type ProducerOptions={hz:10;typedValues:readonly JsonValue[]};
export type ProducerStartEvidence={active:true;confirmedAtUnixNs:I64};
export type PerformanceSnapshot={heapBytes:number;queueDepth:number};
export type AssetSizes={rawBytes:I64;gzipJsBytes:I64;gzipCssBytes:I64};
export type EvidenceFile={relativePath:string;bytes:I64;sha256:string};
export type CatalogScenario="scalar"|"float"|"enum"|"array"|"member"|"register"|"unavailable"|"pagination";
export interface MonitorBrowserFixture{
 readonly origin:string;navigate(page:Page):Promise<void>;stop():Promise<void>;requestCount():Promise<number>;
 createGroupThroughRest(page:Page,transfer:GroupTransfer):Promise<WatchGroup>;startThroughRest(page:Page,groupId:string,revision:I64):Promise<void>;
 createGroupThroughUi(page:Page,input:{rows:number;intervalMs:100|250|5000}):Promise<WatchGroup>;startThroughUi(page:Page,group:WatchGroup):Promise<void>;selectSeriesThroughUi(page:Page,count:8):Promise<void>;
 setProbeMode(mode:"ready"|"busy"|"lease-lost"):Promise<void>;setCatalogScenario(value:CatalogScenario):Promise<void>;forceGroupConflict():Promise<void>;failNextItem(code:string):Promise<void>;forceStale():Promise<void>;forceReset():Promise<void>;
 emitOuterDrop(count:I64):Promise<void>;setDropDeltas(value:DropTotals):Promise<void>;
 startProducer(options:ProducerOptions):Promise<ProducerStartEvidence>;stopProducer():Promise<void>;producerActive():Promise<boolean>;sampleCount():Promise<I64>;
 dropTotals():Promise<DropTotals>;performanceSnapshot(page:Page):Promise<PerformanceSnapshot>;assetSizes():Promise<AssetSizes>;writeEvidence(name:"performance.json",value:JsonValue):Promise<EvidenceFile>;
  liveEvents(count:number):Promise<readonly LiveEvent[]>;disconnectLive(holdReconnect:boolean):Promise<I64>;subscriptionCursors():Promise<readonly (I64|null)[]>;expireBefore(eventId:I64):Promise<void>;
 containsSecret(text:string):Promise<boolean>;consoleContainsSecret():Promise<boolean>;securityHeaders(page:Page):Promise<Readonly<Record<string,string>>>;remoteInventory(page:Page):Promise<readonly string[]>;downloadedExports():Promise<readonly {format:"csv"|"jsonl";artifact:ExportArtifact;body:Uint8Array}[]>;
}
export function startMonitor(workspace:string):Promise<MonitorBrowserFixture>;
export const test=base.extend<{monitor:MonitorBrowserFixture}>({monitor:async({},use,testInfo)=>{const monitor=await startMonitor(testInfo.title.replace(/[^a-z0-9]+/gi,"-").toLowerCase());try{await use(monitor);}finally{await monitor.stop();}}});
export {expect};
```

- [ ] **Step 1: Write the failing real-service fixture and e2e type tests.** Start from a repository/evidence path with spaces; prove current-source module paths, exact loopback random port, one-shot navigate, `token_factory(32)`, real full envelopes, authoritative group revisions/watches, hello+state ordering, delta replay, expired gap, real HistoryPage batch/startOrdinal serialization, and clean teardown. Max-int64 event/revision/ordinal values must typecheck as bigint in fixture APIs. Include:

```ts
test("real service emits initial hello/state and uses its journal for replay and an expired gap",async({page})=>{
 const monitor=await startMonitor("fixture-replay");try{await monitor.navigate(page);
   expect(await page.getByText("No groups yet").isVisible()).toBe(true);await expect(page.getByText("Disconnected")).toBeVisible();
   await expect.poll(async()=>(await monitor.liveEvents(2)).map(x=>x.type)).toEqual(["hello","state"]);
   await page.getByRole("button",{name:"Connect probe"}).click();
   const group=await monitor.createGroupThroughRest(page,{name:"User group",description:"",intervalMs:250,items:[{kind:"variable",expression:"counter"}]});await monitor.startThroughRest(page,group.groupId,group.revision);
   await monitor.startProducer({hz:10,typedValues:[1]});await expect.poll(()=>monitor.sampleCount()).toBeGreaterThan(1n);
   const replayAnchor=await monitor.disconnectLive(false);const beforeReplay=await monitor.sampleCount();await expect.poll(()=>monitor.sampleCount()).toBeGreaterThan(beforeReplay);
   await expect.poll(async()=>await monitor.subscriptionCursors()).toContain(replayAnchor);await expect(page.getByRole("table",{name:"Live values"})).toContainText("counter");
   const gapAnchor=await monitor.disconnectLive(true);await monitor.expireBefore(gapAnchor+3n);
   await expect.poll(async()=>await monitor.subscriptionCursors()).toContain(gapAnchor);await expect(page.getByTestId("continuity-gap")).toBeVisible();
   await monitor.stopProducer();const dropsBefore=await monitor.dropTotals();await monitor.emitOuterDrop(2n);expect((await monitor.dropTotals()).service).toBe(dropsBefore.service+2n);
  }finally{await monitor.stop();}
});
```

- [ ] **Step 2: Run RED.** Set exact current-source `PYTHONPATH`, `STM32_MONITOR_E2E_PYTHON`, `STM32_MONITOR_E2E_REPO_ROOT`, and external `STM32_MONITOR_E2E_EVIDENCE_ROOT`; run `& $npm run typecheck:e2e` and `& $npm exec -- playwright test e2e/fixture-contract.spec.ts --project=chromium-1280`. Expected: FAIL because fixture files are absent; not because Playwright/browser/current-source dependencies are missing.

- [ ] **Step 3: Implement the stateful fake using accepted model serializers and correct token factory signature.** The core startup/history/live code is:

```python
import argparse,asyncio,gzip,hashlib,json,os,re,secrets,sys,time
from collections import deque
from pathlib import Path
from uuid import UUID,uuid4
from stm32_monitor.exports import ExportRequest,MonitorExporter
from stm32_monitor.groups import GroupStore
from stm32_monitor.history import HistoryQuery,HistoryStore
from stm32_monitor.models import LiveEvent,ObservationBinding,SampleBatch,SampleValue,WatchGroup,WatchItem
from stm32_monitor.protocol import MONITOR_PROTOCOL_VERSION,MONITOR_VERSION,failure,success
from stm32_monitor.service import MonitorService
from stm32_toolkit import __version__ as TOOLKIT_VERSION
from stm32_toolkit.debug.model import DebugFirmwareBinding,MemoryRegionBinding
from stm32_toolkit.debug.types import CatalogPage,RegisterDescriptor,VariableDescriptor
from stm32_toolkit.paths import WorkspacePaths

class TokenChecker:
    def __init__(self,token:bytes):self.__hex=token.hex()
    def contains(self,text:object)->bool:return self.__hex in str(text)
class ScenarioRuntime:
    def __init__(self, workspace: str, project: Path,evidence_root:Path,checker:TokenChecker):
        if re.fullmatch(r"[0-9a-f]{24}",workspace) is None:raise ValueError("workspace must be 24 lowercase hex")
        self.workspace_id=workspace;self.project=project.resolve(strict=True);self.revision=0;self.event_id=0;self.binding_epoch=0;self.connected=False;self.sampling_state="IDLE"
        self.active_group_id:UUID|None=None;self.active_group_revision:int|None=None;self.run_id:UUID|None=None
        self.journal:deque[LiveEvent]=deque(maxlen=32);self.changed=asyncio.Condition();self.closed=False;self.subscribers:dict[asyncio.Queue[object],int]={};self.subscription_cursors:list[int|None]=[];self.live_reconnect_gate=asyncio.Event();self.live_reconnect_gate.set();self.service_drop_changed=asyncio.Event();self.producer_task:asyncio.Task[None]|None=None;self.sequence=0;self.producer_confirmed=asyncio.Event()
        self.evidence_root=evidence_root.resolve(strict=True);self.checker=checker;self.set_service_send_delay=lambda _seconds:None;data=self.evidence_root/"runtime-data"/workspace;root=data/"projects"/workspace
        self.paths=WorkspacePaths(self.project,data,workspace,"e2e-session",root,root/"monitor",root/"diagnostics",root/"logs",root/"cache",root/"sessions"/"e2e-session");self.paths.ensure();self.group_store=GroupStore(self.paths);self.history_store=HistoryStore(self.paths);self.exporter=MonitorExporter(self.paths,self.history_store)
        logical="11111111-1111-4111-8111-111111111111";self.binding=ObservationBinding(workspace,logical,"e2e-session","probe-1","STM32F407VG","usb:probe-1","0"*64,"1"*64,"2"*64,"a"*40,False,"flash-session","lease-1","3"*64,None)
        self.debug_binding=DebugFirmwareBinding(logical,workspace,"e2e-session","flash-session","lease-1","probe-1","STM32F407VG","cortex_m","0"*64,"1"*64,4096,"build/fw.elf","2"*64,"a"*40,False,"2026-08-10T00:00:00.000000Z",(MemoryRegionBinding("FLASH",0x08000000,0x10000,"rx"),),self.project)
        self.probe_mode="ready";self.catalog_scenario="scalar";self.next_item_error:str|None=None;self.force_conflict=False;self.request_count=0;self.drop_totals={"subscriber":0,"history":0,"deadline":0,"service":0};self.next_drop_deltas={"subscriber":0,"history":0,"deadline":0};self.pause_heartbeats=False;self.exports={};self.downloaded_exports=[]
    def event(self, kind: str, data: dict[str, object]) -> dict[str, object]:
        self.event_id+=1;event=LiveEvent(self.event_id,kind,data);self.journal.append(event);return event.to_dict()
    def status(self)->dict[str,object]:
        sampling={"state":self.sampling_state,"active":self.sampling_state in {"RUNNING","PAUSED"},"blockedCode":None,"groupId":str(self.active_group_id) if self.active_group_id else None,"groupRevision":self.active_group_revision,"runId":str(self.run_id) if self.run_id else None,"lastSequence":self.sequence if self.run_id else None,"bindingEpoch":self.binding_epoch,"subscriberDrops":self.drop_totals["subscriber"],"historyDrops":self.drop_totals["history"],"deadlineDrops":self.drop_totals["deadline"],"serviceDrops":self.drop_totals["service"]}
        firmware={"buildId":"0"*64,"elfSha256":"1"*64,"inputSnapshotSha256":"2"*64,"gitHead":"a"*40,"gitDirty":False,"targetDevice":"STM32F407VG"}
        return {"workspaceId":self.workspace_id,"sessionId":"e2e-session","project":{"logicalProjectId":self.binding.logical_project_id,"name":"E2E project","targetDevice":self.binding.target_device},"firmware":firmware,"probe":{"connected":self.connected,"probeId":self.binding.probe_id if self.connected else None},"sampling":sampling,"probeConnected":self.connected,"samplingActive":sampling["active"]}
    async def publish(self,kind:str,data:dict[str,object])->dict[str,object]:
        if kind=="state":self.revision+=1;data={**data,"stateRevision":self.revision}
        event=self.event(kind,data)
        async with self.changed:self.changed.notify_all()
        for queue in tuple(self.subscribers):
            if queue.full():queue.get_nowait()
            queue.put_nowait(self.journal[-1])
        return event
    async def live_subscribe(self, *, after_event_id: int | None=None):
        if after_event_id is not None:await self.live_reconnect_gate.wait()
        self.subscription_cursors.append(after_event_id)
        if after_event_id is None:
            yield self.event("hello",{"protocol":MONITOR_PROTOCOL_VERSION,"toolkitVersion":TOOLKIT_VERSION,"monitorVersion":MONITOR_VERSION,"stateRevision":self.revision});yield self.event("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});cursor=self.event_id
        else:
            cursor=after_event_id;oldest=self.journal[0].event_id if self.journal else self.event_id+1
            if cursor<oldest-1:
                gap=self.event("state",{"stateRevision":self.revision,"gap":True,"status":self.status()});yield gap;cursor=int(gap["eventId"])
        queue:asyncio.Queue[object]=asyncio.Queue(maxsize=64);self.subscribers[queue]=cursor
        try:
            for event in tuple(self.journal):
                if event.event_id>cursor:cursor=event.event_id;self.subscribers[queue]=cursor;yield event.to_dict()
            while not self.closed:
                item=await queue.get()
                if item is None:return
                if isinstance(item,LiveEvent) and item.event_id>cursor:cursor=item.event_id;self.subscribers[queue]=cursor;yield item.to_dict()
        finally:self.subscribers.pop(queue,None)
    async def start_producer(self, *, hz: int, typed_values: list[object]) -> dict[str, object]:
        if self.active_group_id is None or self.run_id is None: raise RuntimeError("authoritative group and sampling are required")
        listed=self.group_store.list_groups();group=next((item for item in (listed.data or ()) if item.group_id==self.active_group_id and item.revision==self.active_group_revision),None)
        if group is None:raise RuntimeError("active group authority changed")
        if hz!=10 or len(typed_values)!=len(group.items): raise ValueError("typed producer is invalid")
        if self.producer_task is not None: raise RuntimeError("producer is already active")
        self.producer_confirmed.clear();self.producer_task=asyncio.create_task(self._produce(group,typed_values),name="e2e-10hz-producer");await asyncio.wait_for(self.producer_confirmed.wait(),5);return {"active":True,"confirmedAtUnixNs":time.time_ns()}
    async def _produce(self,group:WatchGroup,typed_values:list[object])->None:
        period_ns=100_000_000;wall_zero=time.time_ns();mono_zero=time.monotonic_ns();tick=0
        try:
            while True:
                current=self._group(group.group_id)
                if current is None or current.revision!=group.revision or current.items!=group.items or self.active_group_id!=group.group_id or self.active_group_revision!=group.revision:raise RuntimeError("active group authority changed during production")
                tick+=1;target=mono_zero+tick*period_ns;await asyncio.sleep(max(0,(target-time.monotonic_ns())/1_000_000_000));scheduled=wall_zero+tick*period_ns;captured=time.time_ns();self.sequence+=1
                values=[]
                for index,watch in enumerate(group.items):
                    if index==0 and self.next_item_error is not None:values.append(SampleValue(watch,"ERROR",code=self.next_item_error));self.next_item_error=None
                    else:values.append(SampleValue(watch,"OK",typed_value=typed_values[index]))
                delta=self.next_drop_deltas;self.next_drop_deltas={"subscriber":0,"history":0,"deadline":0}
                for name in delta:self.drop_totals[name]+=delta[name]
                batch=SampleBatch(self.binding,group.group_id,group.revision,self.run_id,self.sequence,scheduled,captured,max(0,captured-scheduled),10.0,delta["subscriber"],delta["history"],delta["deadline"],tuple(values))
                stored=self.history_store.append_batch(batch)
                if not stored.ok:raise RuntimeError(stored.code)
                await self.publish("sample",{"batch":batch.to_dict(),"serviceSubscriberDrops":0});self.producer_confirmed.set()
        except asyncio.CancelledError:
            raise
    async def stop_producer(self) -> None:
        task,self.producer_task=self.producer_task,None
        if task is not None: task.cancel();await asyncio.gather(task,return_exceptions=True)
    async def close(self)->None:
        await self.stop_producer();self.closed=True
        for queue in tuple(self.subscribers):queue.put_nowait(None)
        async with self.changed:self.changed.notify_all()
    def write_evidence(self,name:str,value:object)->dict[str,object]:
        if name!="performance.json":raise ValueError("evidence name is invalid")
        body=json.dumps(value,separators=(",",":"),sort_keys=True).encode();path=self.evidence_root/name;path.write_bytes(body);return {"relativePath":name,"bytes":len(body),"sha256":hashlib.sha256(body).hexdigest()}
    def record_service_drops(self,count:int)->None:self.drop_totals["service"]+=count;self.service_drop_changed.set()
    @staticmethod
    def _exact(value:dict[str,object],required:set[str],optional:set[str]=set())->None:
        if not required<=set(value) or set(value)-required-optional:raise ValueError("request keys are invalid")
    def _group(self,group_id:UUID)->WatchGroup|None:
        result=self.group_store.list_groups();return next((item for item in (result.data or ()) if item.group_id==group_id),None) if result.ok else None
    def _catalog(self,operation:str,query:dict[str,str]):
        self._exact({},set());limit=int(query.get("limit","100"));cursor=query.get("cursor")
        if set(query)-{"query","cursor","limit"} or not 1<=limit<=256:return failure(operation,"MONITOR_REQUEST_INVALID","Monitor request is invalid")
        if not self.connected:return failure(operation,"MONITOR_REQUEST_INVALID","A probe must be connected")
        if self.catalog_scenario=="unavailable":return failure(operation,"MONITOR_PROVENANCE_CHANGED","Catalog is unavailable")
        if operation.endswith("registers"):
            rows=(RegisterDescriptor("GPIOA.ODR",32,"read-write",None,0,0xffffffff,(("OD0",0,1),),True,False),)
        else:
            values={
             "scalar":VariableDescriptor("counter","uint32_t","base",4,False,"unsigned"),"float":VariableDescriptor("temperature","float","base",4,True,"float"),
             "enum":VariableDescriptor("mode","Mode","enum",4,False,"unsigned",enum_values=((0,"Idle"),(1,"Run"))),"array":VariableDescriptor("samples","uint16_t[300]","array",600,False,"unsigned",element_count=300,element_kind="base"),
             "member":VariableDescriptor("state","State","structure",8,member_names=("x","y")),"register":VariableDescriptor("counter","uint32_t","base",4,False,"unsigned"),"pagination":VariableDescriptor("counter","uint32_t","base",4,False,"unsigned")}
            rows=(values[self.catalog_scenario],)
        next_cursor="page-2" if self.catalog_scenario=="pagination" and cursor is None else None
        return success(operation,CatalogPage(rows,next_cursor).to_dict())
    async def dispatch(self,operation:str,payload:dict[str,object],*,resource_id:str|None=None,query:dict[str,str]|None=None):
        self.request_count+=1;q={} if query is None else query
        try:
            if operation=="monitor.status":self._exact(payload,set());return success(operation,self.status())
            if operation=="monitor.probes.list":self._exact(payload,set());return success(operation,{"probes":[{"probeId":"probe-1","vendor":"ST","product":"E2E","boardName":None}]})
            if operation in {"monitor.catalog.variables","monitor.catalog.registers"}:self._exact(payload,set());return self._catalog(operation,q)
            if operation=="monitor.groups.list":
                self._exact(payload,set());self._exact({key:object() for key in q},set(),{"cursor","limit"});return self.group_store.list_group_page(cursor=q.get("cursor"),limit=int(q.get("limit","16")))
            if operation=="monitor.groups.create":
                self._exact(payload,{"name","description","intervalMs","items","authorized"});return self.group_store.create_group(str(payload["name"]),str(payload["description"]),int(payload["intervalMs"]),tuple(WatchItem.from_dict(item) for item in payload["items"]),authorized=payload["authorized"])
            if operation=="monitor.groups.update":
                self._exact(payload,{"expectedRevision","authorized"},{"name","description","intervalMs","items"})
                if self.force_conflict:self.force_conflict=False;return failure(operation,"MONITOR_GROUP_CONFLICT","watch group revision changed")
                changes={};
                if "name" in payload:changes["name"]=payload["name"]
                if "description" in payload:changes["description"]=payload["description"]
                if "intervalMs" in payload:changes["interval_ms"]=int(payload["intervalMs"])
                if "items" in payload:changes["items"]=tuple(WatchItem.from_dict(item) for item in payload["items"])
                return self.group_store.update_group(UUID(resource_id),expected_revision=int(payload["expectedRevision"]),authorized=payload["authorized"],**changes)
            if operation=="monitor.groups.delete":self._exact(payload,{"expectedRevision","authorized"});return self.group_store.delete_group(UUID(resource_id),expected_revision=int(payload["expectedRevision"]),authorized=payload["authorized"])
            if operation=="monitor.groups.import":self._exact(payload,{"document","authorized"});return self.group_store.import_groups(json.dumps(payload["document"],separators=(",",":"),sort_keys=True).encode(),authorized=payload["authorized"])
            if operation=="monitor.probe.connect":
                self._exact(payload,{"probeId"})
                if self.probe_mode=="busy" or self.connected:return failure(operation,"MONITOR_PROBE_BUSY","A probe is already connected")
                if payload["probeId"]!="probe-1":return failure(operation,"MONITOR_REQUEST_INVALID","Probe is unavailable")
                self.connected=True;self.binding_epoch+=1;await self.publish("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});return success(operation,self.debug_binding.to_dict())
            if operation=="monitor.probe.reconnect":
                self._exact(payload,set())
                if self.probe_mode=="lease-lost":self.connected=False;return failure(operation,"MONITOR_LEASE_LOST","Probe lease was lost")
                if not self.connected:return failure(operation,"MONITOR_REQUEST_INVALID","No prior probe request exists")
                self.binding_epoch+=1;await self.publish("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});return success(operation,self.debug_binding.to_dict())
            if operation=="monitor.probe.release":
                self._exact(payload,set());await self.stop_producer();self.connected=False;self.sampling_state="IDLE";self.active_group_id=None;self.active_group_revision=None;self.run_id=None;await self.publish("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});return success(operation,{"released":True})
            if operation=="monitor.sampling.start":
                self._exact(payload,{"groupId","expectedRevision"});group=self._group(UUID(str(payload["groupId"])))
                if not self.connected or group is None:return failure(operation,"MONITOR_REQUEST_INVALID","Connected probe and group are required")
                if group.revision!=int(payload["expectedRevision"]):return failure(operation,"MONITOR_GROUP_CONFLICT","watch group revision changed")
                self.active_group_id=group.group_id;self.active_group_revision=group.revision;self.run_id=uuid4();self.sequence=0;self.sampling_state="RUNNING";await self.publish("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});return success(operation,{"groupId":str(group.group_id),"groupRevision":group.revision,"runId":str(self.run_id),"intervalMs":group.interval_ms})
            if operation in {"monitor.sampling.pause","monitor.sampling.resume","monitor.sampling.stop"}:
                self._exact(payload,set());action=operation.rsplit(".",1)[1]
                if action=="pause" and self.sampling_state=="RUNNING":self.sampling_state="PAUSED";data={"paused":True}
                elif action=="resume" and self.sampling_state=="PAUSED":self.sampling_state="RUNNING";data={"resumed":True}
                elif action=="stop":await self.stop_producer();self.sampling_state="IDLE";self.active_group_id=None;self.active_group_revision=None;self.run_id=None;data={"stopped":True}
                else:return failure(operation,"MONITOR_REQUEST_INVALID","Sampling transition is invalid")
                await self.publish("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});return success(operation,data)
            if operation=="monitor.history.query":
                self._exact(payload,set());self._exact({key:object() for key in q},{"startNs","endNs"},{"limit","cursor","runId","groupId","selectorKind","selector"})
                if ("selectorKind" in q)!=("selector" in q):raise ValueError("selector pair differs")
                request=HistoryQuery(self.paths.session_id,int(q["startNs"]),int(q["endNs"]),limit=int(q.get("limit","10000")),cursor=q.get("cursor"),run_id=UUID(q["runId"]) if "runId" in q else None,group_id=UUID(q["groupId"]) if "groupId" in q else None,selector_kind=q.get("selectorKind"),selector=q.get("selector"));return self.history_store.query_history(request)
            if operation=="monitor.exports.create":
                self._exact(payload,{"startNs","endNs","format","authorized"});result=self.exporter.create_export(ExportRequest(self.paths.session_id,int(payload["startNs"]),int(payload["endNs"]),str(payload["format"])),authorized=payload["authorized"])
                if result.ok and result.data is not None:self.exports[result.data.export_id]=result.data
                return result
            if operation=="monitor.exports.get":self._exact(payload,set());return self.exporter.get_export(UUID(resource_id))
            if operation=="monitor.exports.download":
                self._exact(payload,set());export_id=UUID(resource_id);artifact=self.exports.get(export_id)
                if artifact is not None:self.downloaded_exports.append({"format":artifact.data_path.suffix[1:],"artifact":artifact.to_dict(),"body":artifact.data_path.read_text("utf-8")})
                return self.exporter.open_download(export_id)
        except (AttributeError,KeyError,TypeError,ValueError):return failure(operation,"MONITOR_REQUEST_INVALID","Monitor request is invalid")
        return failure(operation,"MONITOR_REQUEST_INVALID","Monitor operation is unsupported")
    async def control_scenario(self,method:str,params:dict[str,object])->object:
        if method=="requestCount":return self.request_count
        if method=="selectedGroup":
            listed=self.group_store.list_groups();groups=tuple(listed.data or ());return (self._group(self.active_group_id) if self.active_group_id else groups[-1]).to_dict()
        if method=="setProbeMode":self.probe_mode=str(params["mode"]);return {"mode":self.probe_mode}
        if method=="setCatalogScenario":self.catalog_scenario=str(params["value"]);return {"value":self.catalog_scenario}
        if method=="forceGroupConflict":self.force_conflict=True;return {"armed":True}
        if method=="failNextItem":self.next_item_error=str(params["code"]);return {"armed":True}
        if method=="emitOuterDrop":
            count=int(params["count"]);before=self.drop_totals["service"]
            if count<1:raise ValueError("outer drop count must be positive")
            await asyncio.sleep(0.05);self.set_service_send_delay(0.25)
            try:
                await self.publish("heartbeat",{"stateRevision":self.revision,"capturedAtUtc":"2026-08-10T00:00:00.000000Z"});await asyncio.sleep(0.02)
                for _ in range(8+count):await self.publish("heartbeat",{"stateRevision":self.revision,"capturedAtUtc":"2026-08-10T00:00:00.000000Z"})
                deadline=time.monotonic()+1.0
                while self.drop_totals["service"]-before<count:
                    self.service_drop_changed.clear()
                    if self.drop_totals["service"]-before>=count:break
                    await asyncio.wait_for(self.service_drop_changed.wait(),max(0.001,deadline-time.monotonic()))
                if self.drop_totals["service"]-before!=count:raise RuntimeError("8-slot service queue did not overflow deterministically")
                return {"serviceDropsBefore":before,"serviceDropsAfter":self.drop_totals["service"]}
            finally:self.set_service_send_delay(0.0)
        if method=="setDropDeltas":self.next_drop_deltas={name:int(params[name]) for name in ("subscriber","history","deadline")};return dict(self.next_drop_deltas)
        if method=="expireBefore":
            cutoff=int(params["eventId"])
            while self.event_id<cutoff:await self.publish("heartbeat",{"stateRevision":self.revision,"capturedAtUtc":"2026-08-10T00:00:00.000000Z"})
            self.journal=deque((item for item in self.journal if item.event_id>=cutoff),maxlen=32);self.live_reconnect_gate.set();return {"oldestEventId":self.journal[0].event_id}
        if method=="liveEvents":return [event.to_dict() for event in list(self.journal)[-int(params["count"]):]]
        if method=="subscriptionCursors":return self.subscription_cursors
        if method=="queueDepth":return max((queue.qsize() for queue in self.subscribers),default=0)
        if method=="assetSizes":
            dist=self.project/"tools/stm32-monitor/src/stm32_monitor/ui_dist";files=[path for path in dist.rglob("*") if path.is_file()];return {"rawBytes":sum(path.stat().st_size for path in files),"gzipJsBytes":sum(len(gzip.compress(path.read_bytes(),mtime=0)) for path in files if path.suffix==".js"),"gzipCssBytes":sum(len(gzip.compress(path.read_bytes(),mtime=0)) for path in files if path.suffix==".css")}
        if method=="downloadedExports":return list(self.downloaded_exports)
        if method=="writeEvidence":return self.write_evidence(str(params["name"]),params["value"])
        if method=="containsSecret":return self.checker.contains(params["text"])
        if method=="forceStale":
            self.pause_heartbeats=True;await self.stop_producer()
            return {"armed":True}
        if method=="forceReset":self.binding_epoch+=1;await self.publish("state",{"stateRevision":self.revision,"gap":False,"status":self.status()});return {"bindingEpoch":self.binding_epoch}
        if method=="disconnectLive":
            anchors=list(self.subscribers.values())
            if not anchors:raise RuntimeError("no live subscriber is connected")
            anchor=max(anchors)
            if bool(params["holdReconnect"]):self.live_reconnect_gate.clear()
            else:self.live_reconnect_gate.set()
            for queue in tuple(self.subscribers):queue.put_nowait(None)
            return anchor
        raise ValueError(f"unknown control method: {method}")

async def control(runtime:ScenarioRuntime,message:dict[str,object])->dict[str,object]:
    request_id=message["id"];method=message["method"];params=message.get("params",{})
    try:
        if method=="startProducer":result=await runtime.start_producer(hz=int(params["hz"]),typed_values=list(params["typedValues"]))
        elif method=="stopProducer":await runtime.stop_producer();result={"stopped":True}
        elif method=="producerActive":result=runtime.producer_task is not None and not runtime.producer_task.done()
        elif method=="sampleCount":result=runtime.sequence
        elif method=="dropTotals":result=dict(runtime.drop_totals)
        elif method=="shutdown":await runtime.close();result={"stopped":True}
        else:result=await runtime.control_scenario(str(method),dict(params))
        return {"id":request_id,"ok":True,"result":result}
    except Exception as error:return {"id":request_id,"ok":False,"error":f"{type(error).__name__}: {error}"}

async def control_lines(runtime:ScenarioRuntime,reader:asyncio.StreamReader,writer:asyncio.StreamWriter)->None:
    while not reader.at_eof():
        line=await reader.readline()
        if not line:break
        reply=await control(runtime,json.loads(line));writer.write((json.dumps(reply,separators=(",",":"))+"\n").encode());await writer.drain()
    await runtime.close();writer.close();await writer.wait_closed()
```

```python
async def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--workspace",required=True);parser.add_argument("--repo",type=Path,required=True);parser.add_argument("--evidence",type=Path,required=True);cli=parser.parse_args()
    token_bytes=secrets.token_bytes(32);checker=TokenChecker(token_bytes);runtime=ScenarioRuntime(cli.workspace,cli.repo,cli.evidence,checker);token_calls=[]
    def token_factory(count:int)->bytes:
        token_calls.append(count)
        if count!=32:raise AssertionError("MonitorService requested a non-32-byte token")
        return token_bytes
    service=MonitorService(runtime,workspace_id=runtime.workspace_id,session_id="e2e-session",token_factory=token_factory,send_delay_seconds=0.0);runtime.set_service_send_delay=lambda seconds:setattr(service,"_send_delay_seconds",seconds);endpoint=await service.start()
    if token_calls!=[32]:raise AssertionError("token_factory call contract differs")
    print(json.dumps({"type":"ready","origin":endpoint.url,"accessUrl":endpoint.access_url},separators=(",",":")),flush=True)
    try:
        while True:
            line=await asyncio.to_thread(sys.stdin.buffer.readline)
            if not line:break
            reply=await control(runtime,json.loads(line));print(json.dumps(reply,separators=(",",":")),flush=True)
            if reply.get("result")=={"stopped":True} and json.loads(line).get("method")=="shutdown":break
    finally:
        await runtime.close();await service.stop()
if __name__=="__main__":asyncio.run(main())
```

The TypeScript process/RPC wrapper is complete and is the only caller of the JSON-line control channel:

```ts
import {spawn,type ChildProcessWithoutNullStreams} from "node:child_process";
import {createHash} from "node:crypto";
import {createInterface} from "node:readline";
import {resolve} from "node:path";
import {createMonitorApi} from "../src/api/client";
import {encodeJson,IntegerToken,i64,parseLossless} from "../src/api/wire";
import {exportArtifactGuard,liveEventGuard} from "../src/api/contract";
import type {MonitorApi} from "../src/api/contract";
class RuntimeProcess{
 private next=1;private pending=new Map<number,{resolve(value:unknown):void;reject(error:Error):void}>();
 private consoleLines:string[]=[];private constructor(private readonly child:ChildProcessWithoutNullStreams,readonly origin:string,private accessUrl:string){const lines=createInterface({input:child.stdout});lines.on("line",line=>{const reply=rpcReplyGuard(parseLossless(line)),p=this.pending.get(reply.id);if(!p)return;this.pending.delete(reply.id);reply.ok?p.resolve(reply.result):p.reject(new Error(reply.error));});child.once("exit",code=>{for(const p of this.pending.values())p.reject(new Error(`runtime exited ${code}`));this.pending.clear();});}
 static async start(label:string):Promise<RuntimeProcess>{const python=resolveRequired("STM32_MONITOR_E2E_PYTHON"),repo=resolveRequired("STM32_MONITOR_E2E_REPO_ROOT"),evidence=resolveRequired("STM32_MONITOR_E2E_EVIDENCE_ROOT"),script=resolve(repo,"tools/stm32-monitor/ui/e2e/fake_runtime.py"),workspace=createHash("sha256").update(label).digest("hex").slice(0,24),child=spawn(python,[script,"--workspace",workspace,"--repo",repo,"--evidence",evidence],{stdio:["pipe","pipe","pipe"],env:controlledPythonEnv(repo)});const first=readyGuard(await oneJsonLine(child.stdout));return new RuntimeProcess(child,first.origin,first.accessUrl);}
 async navigate(page:Page):Promise<void>{page.on("console",message=>this.consoleLines.push(message.text()));page.on("pageerror",error=>this.consoleLines.push(error.message));const url=this.accessUrl;if(!url)throw new Error("private access URL already consumed");this.accessUrl="";await page.goto(url);url.replace(/./g,"0");await page.waitForURL(this.origin+"/");}
 request(method:string,params:Record<string,unknown>={}):Promise<unknown>{const id=this.next++;return new Promise((resolve,reject)=>{this.pending.set(id,{resolve,reject});this.child.stdin.write(encodeJson({id,method,params})+"\n");});}
 consoleText():string{return this.consoleLines.join("\n");}
 async stop():Promise<void>{if(this.child.exitCode===null){await this.request("shutdown");this.child.stdin.end();await new Promise<void>(resolve=>this.child.once("exit",()=>resolve()));}}
}
export async function startMonitor(workspace:string):Promise<MonitorBrowserFixture>{const runtime=await RuntimeProcess.start(workspace);return buildMonitorBrowserFixture(runtime);}
function resolveRequired(name:string):string{const value=process.env[name];if(!value)throw new Error(`${name} is required`);return resolve(value);}
function controlledPythonEnv(repo:string):NodeJS.ProcessEnv{return{PYTHONPATH:[resolve(repo,"tools/stm32-monitor/src"),resolve(repo,"tools/stm32-toolkit/src")].join(";"),PYTHONDONTWRITEBYTECODE:"1",PYTHONPYCACHEPREFIX:resolve(resolveRequired("STM32_MONITOR_E2E_EVIDENCE_ROOT"),"pycache"),SystemRoot:process.env.SystemRoot};}
const record=(value:unknown):value is Record<string,unknown>=>typeof value==="object"&&value!==null&&!Array.isArray(value);
const bounded=(value:unknown):number=>{if(!(value instanceof IntegerToken))throw new Error("expected integer token");const n=Number(value.decimal);if(!Number.isSafeInteger(n))throw new Error("integer is not bounded");return n;};
const rpcReplyGuard=(value:unknown):{id:number;ok:true;result:unknown}|{id:number;ok:false;error:string}=>{if(!record(value))throw new Error("RPC reply is not an object");const id=bounded(value.id);if(value.ok===true)return{id,ok:true,result:value.result};if(value.ok===false&&typeof value.error==="string")return{id,ok:false,error:value.error};throw new Error("RPC reply is invalid");};
const readyGuard=(value:unknown):{origin:string;accessUrl:string}=>{if(!record(value)||value.type!=="ready"||typeof value.origin!=="string"||typeof value.accessUrl!=="string")throw new Error("runtime startup record invalid");return{origin:value.origin,accessUrl:value.accessUrl};};
async function oneJsonLine(stream:NodeJS.ReadableStream):Promise<unknown>{return new Promise((resolveLine,reject)=>{const lines=createInterface({input:stream});lines.once("line",line=>{lines.close();try{resolveLine(parseLossless(line));}catch(error){reject(error);}});});}
const producerEvidence=(value:unknown):ProducerStartEvidence=>{if(!record(value)||value.active!==true)return(()=>{throw new Error("producer did not start")})();return{active:true,confirmedAtUnixNs:i64(value.confirmedAtUnixNs)};};
const drops=(value:unknown):DropTotals=>{if(!record(value))throw new Error("drops are invalid");return{subscriber:i64(value.subscriber),history:i64(value.history),deadline:i64(value.deadline),service:i64(value.service)};};
const rpcUnknown=(runtime:RuntimeProcess,method:string,params:Record<string,unknown>={}):Promise<unknown>=>runtime.request(method,params);
const boolGuard=(value:unknown):boolean=>{if(typeof value!=="boolean")throw new Error("expected boolean");return value;};
const i64Guard=(value:unknown):bigint=>i64(value);
const liveEventArrayGuard=(value:unknown):readonly LiveEvent[]=>{if(!Array.isArray(value))throw new Error("live event list is invalid");return value.map(liveEventGuard);};
const subscriptionCursorGuard=(value:unknown):readonly (I64|null)[]=>{if(!Array.isArray(value))throw new Error("subscription cursor list is invalid");return value.map(item=>item===null?null:i64(item));};
const assetSizesGuard=(value:unknown):AssetSizes=>{if(!record(value))throw new Error("asset sizes are invalid");return{rawBytes:i64(value.rawBytes),gzipJsBytes:i64(value.gzipJsBytes),gzipCssBytes:i64(value.gzipCssBytes)};};
const evidenceFileGuard=(value:unknown):EvidenceFile=>{if(!record(value)||typeof value.relativePath!=="string"||typeof value.sha256!=="string")throw new Error("evidence file is invalid");return{relativePath:value.relativePath,bytes:i64(value.bytes),sha256:value.sha256};};
const exportDownloadEvidenceGuard=(value:unknown):readonly {format:"csv"|"jsonl";artifact:ExportArtifact;body:Uint8Array}[]=>{if(!Array.isArray(value))throw new Error("download evidence is invalid");return value.map(item=>{if(!record(item)||(item.format!=="csv"&&item.format!=="jsonl")||typeof item.body!=="string")throw new Error("download evidence row is invalid");return{format:item.format,artifact:exportArtifactGuard(item.artifact),body:new TextEncoder().encode(item.body)};});};
const normalizedBrowserHeaders=(value:HeadersInit|undefined):Record<string,string>=>{const result:Record<string,string>={};new Headers(value).forEach((item,name)=>{if(name!=="origin")result[name]=item;});return result;};
const browserApi=(page:Page,origin:string):MonitorApi=>createMonitorApi(async(input,init)=>{const headers=normalizedBrowserHeaders(init?.headers),payload={url:new URL(String(input),origin).href,...(init?.method===undefined?{}:{method:init.method}),...(Object.keys(headers).length===0?{}:{headers}),...(typeof init?.body==="string"?{body:init.body}:{})};const result=await page.evaluate(async request=>{const response=await fetch(request.url,{credentials:"same-origin",...("method" in request?{method:request.method}:{}),...("headers" in request?{headers:request.headers}:{}),...("body" in request?{body:request.body}:{})}),responseHeaders:Record<string,string>={};response.headers.forEach((value,name)=>{responseHeaders[name]=value;});return{status:response.status,headers:responseHeaders,body:Array.from(new Uint8Array(await response.arrayBuffer()))};},payload);return new Response(Uint8Array.from(result.body),{status:result.status,headers:result.headers});},origin);
function buildMonitorBrowserFixture(runtime:RuntimeProcess):MonitorBrowserFixture{return{
 origin:runtime.origin,navigate:page=>runtime.navigate(page),stop:()=>runtime.stop(),requestCount:()=>rpcUnknown(runtime,"requestCount").then(bounded),
 createGroupThroughRest:async(page,transfer)=>{const result=await browserApi(page,runtime.origin).createGroup({...transfer,authorized:true});if(!result.ok)throw new Error(result.code);return result.data;},startThroughRest:async(page,groupId,revision)=>{const result=await browserApi(page,runtime.origin).start(groupId,revision);if(!result.ok)throw new Error(result.code);},
 createGroupThroughUi:async(page,input)=>{await page.getByRole("button",{name:"Create group"}).click();await page.getByLabel("Group name").fill("E2E group");await page.getByLabel("Sampling interval").press("Control+A");await page.keyboard.type(String(input.intervalMs));for(let i=0;i<input.rows;i++){await page.getByRole("button",{name:"Add watch"}).click();await page.getByLabel(`Watch ${i+1} expression`).fill(`counter${i}`);}await page.getByRole("button",{name:"Save group"}).click();const result=await browserApi(page,runtime.origin).groups();if(!result.ok||result.data.groups.length===0)throw new Error("UI group was not authoritative");return result.data.groups.at(-1)!;},startThroughUi:async(page,group)=>{await page.getByRole("button",{name:"Start sampling"}).click();await expect(page.getByText("RUNNING")).toBeVisible();expect(group.revision).toBeGreaterThan(0n);},selectSeriesThroughUi:async(page,count)=>{for(let i=0;i<count;i++)await page.getByLabel(`Chart series ${i+1}`).check();},
 setProbeMode:mode=>rpcUnknown(runtime,"setProbeMode",{mode}).then(()=>undefined),setCatalogScenario:value=>rpcUnknown(runtime,"setCatalogScenario",{value}).then(()=>undefined),forceGroupConflict:()=>rpcUnknown(runtime,"forceGroupConflict").then(()=>undefined),failNextItem:code=>rpcUnknown(runtime,"failNextItem",{code}).then(()=>undefined),forceStale:()=>rpcUnknown(runtime,"forceStale").then(()=>undefined),forceReset:()=>rpcUnknown(runtime,"forceReset").then(()=>undefined),emitOuterDrop:count=>rpcUnknown(runtime,"emitOuterDrop",{count}).then(()=>undefined),setDropDeltas:value=>rpcUnknown(runtime,"setDropDeltas",value).then(()=>undefined),
 startProducer:options=>rpcUnknown(runtime,"startProducer",{hz:options.hz,typedValues:options.typedValues}).then(producerEvidence),stopProducer:()=>rpcUnknown(runtime,"stopProducer").then(()=>undefined),producerActive:()=>rpcUnknown(runtime,"producerActive").then(boolGuard),sampleCount:()=>rpcUnknown(runtime,"sampleCount").then(i64Guard),dropTotals:()=>rpcUnknown(runtime,"dropTotals").then(drops),performanceSnapshot:async page=>({heapBytes:await page.evaluate(()=>{const value=Reflect.get(performance,"memory");return typeof value==="object"&&value!==null&&typeof Reflect.get(value,"usedJSHeapSize")==="number"?Reflect.get(value,"usedJSHeapSize"):0;}),queueDepth:await rpcUnknown(runtime,"queueDepth").then(bounded)}),assetSizes:()=>rpcUnknown(runtime,"assetSizes").then(assetSizesGuard),writeEvidence:(name,value)=>rpcUnknown(runtime,"writeEvidence",{name,value}).then(evidenceFileGuard),
 liveEvents:count=>rpcUnknown(runtime,"liveEvents",{count}).then(liveEventArrayGuard),disconnectLive:holdReconnect=>rpcUnknown(runtime,"disconnectLive",{holdReconnect}).then(i64Guard),subscriptionCursors:()=>rpcUnknown(runtime,"subscriptionCursors").then(subscriptionCursorGuard),expireBefore:eventId=>rpcUnknown(runtime,"expireBefore",{eventId}).then(()=>undefined),
 containsSecret:text=>rpcUnknown(runtime,"containsSecret",{text}).then(boolGuard),consoleContainsSecret:()=>rpcUnknown(runtime,"containsSecret",{text:runtime.consoleText()}).then(boolGuard),securityHeaders:async page=>{const response=await page.request.get(runtime.origin+"/");const wanted=["cache-control","content-security-policy","referrer-policy","x-content-type-options","cross-origin-opener-policy","cross-origin-resource-policy","permissions-policy"];return Object.fromEntries(wanted.map(name=>[name,response.headers()[name]??""]));},remoteInventory:page=>page.evaluate(origin=>performance.getEntriesByType("resource").map(entry=>entry.name).filter(name=>new URL(name).origin!==origin),runtime.origin),downloadedExports:()=>rpcUnknown(runtime,"downloadedExports").then(exportDownloadEvidenceGuard)
};}
```

The fixture-only `producerEvidence`, `drops`, `assetSizesGuard`, `evidenceFileGuard`, `subscriptionCursorGuard`, and download-evidence guards stay in `fixture.ts`: each validates its exact local control/evidence shape and converts every integer token through `i64`; Task 11 never modifies frozen Task 1 `contract.ts`. Browser API calls run through real page-context `fetch`, so the BrowserContext supplies its HttpOnly cookie and browser-generated exact Origin/`Sec-Fetch-Site`; the adapter normalizes `HeadersInit` to `Record<string,string>`, omits forbidden caller-set Origin, and conditionally adds `method`, `headers`, and `body`, so `exactOptionalPropertyTypes` receives no explicit `undefined`. `page.request` is used only for unauthenticated static-header inspection. `disconnectLive(false)` returns the last cursor yielded by the real runtime subscription and permits normal reconnect; `disconnectLive(true)` closes the same subscription but holds the next generator at a fixture-only gate until `expireBefore` has advanced ordinary heartbeat events and trimmed the same journal. `subscriptionCursors` only observes arguments received by real subscriptions, `expireBefore` never constructs a gap, and only `live_subscribe` may emit `gap:true` after comparing the released reconnect cursor with retained journal state; both Task 11 and Task 12 assert the resulting UI continuity state. The existing constructor-exposed service send-delay seam stays `0.0` for all normal/ performance flows and is set to `0.25` only inside `emitOuterDrop`: after one sender-blocking heartbeat, exactly `8+count` ordinary events overflow the real eight-slot service queue by `count`, then the delay is restored in `finally`. The producer is stopped first, and a bounded event wait fails unless `record_service_drops` observes that exact delta. The JSON-line channel is only control/evidence and never returns a fabricated replay/gap. Playwright config has no global offline mode.

- [ ] **Step 4: Run GREEN, strict typecheck, and teardown checks.** With the exact Step 2 environment, run `& $npm run typecheck:e2e`; run `& $npm exec -- playwright test e2e/fixture-contract.spec.ts --project=chromium-1280 --project=chromium-1024`; set `PYTHONPYCACHEPREFIX=(Join-Path $taskRoot 'fixture-pycache')` and run `& $python312 -m compileall -q tools/stm32-monitor/ui/e2e/fake_runtime.py`. Expected: all PASS with strict bigint APIs, zero initial groups, real envelopes/HistoryPage, token count 32, and clean teardown.

- [ ] **Step 5: Commit Task 11.** Call `Commit-0502Task 'test(STM32TK-0502): add real aiohttp browser fixture' @('tools/stm32-monitor/ui/e2e/fake_runtime.py','tools/stm32-monitor/ui/e2e/fixture.ts','tools/stm32-monitor/ui/e2e/fixture-contract.spec.ts')`.

### Task 12: Browser Acceptance, Accessibility, Security, and Five-Minute Performance

**Files:**
- Create: `tools/stm32-monitor/ui/e2e/acceptance.ts`, `monitor.spec.ts`, `security.spec.ts`, `isolation.spec.ts`, `accessibility.spec.ts`, `performance.spec.ts`.

**Interfaces:**
- Functional projects are Chromium 1280x720 and 1024x768 on Windows; Firefox/WebKit remain configured for the named Linux release owner. Each test installs a context route guard allowing HTTP plus its exact HTTP→WS or HTTPS→WSS scheme pair at the fixture's exact host and port; there is no global offline mode. Normal workflows assert zero external-origin attempts; deliberate requests to a second real service are blocked and its request count remains zero.
- Product acceptance covers fresh zero state, identity, full probe lifecycle/busy/lease-lost, catalog scalar/float/enum/array/member/register/unavailable and pagination, group CRUD/order/export/import/conflict, 100/250/5000 ms sampling, command states, 256 rows, item-error isolation, 8x600 realized chart points, mouse/touch/keyboard zoom/reset, replay/gap/stale/reset, compact drops, history ordinals/cursors, verified CSV/JSONL, two-workspace isolation, secret absence, keyboard/focus/contrast/200%, and security headers/offline inventory.
- Performance is production dist at 10 Hz, 256 rows, exactly eight selected series with exactly 600 realized points each (4,800 total). The collector installs instrumentation and snapshots before it starts the explicit typed producer; it warms up for 120 seconds and measures for 180 seconds. It records before/after authoritative and transport drops, queue depth samples, update durations, Long Tasks, heap samples, realized points, sample count, and raw/gzip asset sizes to retained external JSON. Test timeout is 390 seconds, leaving at least 90 seconds of setup/teardown margin around the 300-second run.

- [ ] **Step 1: Write failing acceptance/a11y/security/performance specifications against an absent helper.** Specs import `installSameOriginGuard`, `completeUserWorkflow`, `assertNoSecret`, `realizedChartPointCount`, and `collectFiveMinuteMetrics` from `acceptance.ts`, then assert every interface row above. Add exact 4,800 realization and performance thresholds:

```ts
import {expect,test} from "./fixture";
import {collectFiveMinuteMetrics,installSameOriginGuard,typedValues} from "./acceptance";
test("five-minute production fixture stays bounded",async({page,monitor})=>{
 test.setTimeout(390_000);const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);
 await page.getByRole("button",{name:"Connect probe"}).click();const group=await monitor.createGroupThroughUi(page,{rows:256,intervalMs:100});await monitor.startThroughUi(page,group);await monitor.selectSeriesThroughUi(page,8);
 const metrics=await collectFiveMinuteMetrics(page,monitor,{warmupMs:120_000,measureMs:180_000,producer:{hz:10,typedValues:typedValues(256)}});
 expect(metrics.realizedPoints).toBe(4800);expect(metrics.updateP95Ms).toBeLessThanOrEqual(150);
 expect(metrics.longTasksAtLeast200Ms).toBe(0);expect(metrics.queueGrowth).toBeLessThanOrEqual(0);
 expect(metrics.heapSlopeMiBPerMinute).toBeLessThanOrEqual(2);expect(metrics.serverDropsAfter).toEqual(metrics.serverDropsBefore);
 expect(BigInt(metrics.sampleCount)).toBeGreaterThanOrEqual(1_790n);expect(BigInt(metrics.sampleCount)).toBeLessThanOrEqual(1_810n);expect(BigInt(metrics.assetSizes.rawBytes)).toBeGreaterThan(0n);expect(BigInt(metrics.assetSizes.gzipJsBytes)).toBeGreaterThan(0n);expect(BigInt(metrics.assetSizes.gzipCssBytes)).toBeGreaterThan(0n);expect(guard.attempts).toEqual([]);
});
```

- [ ] **Step 2: Run RED.** Set `PLAYWRIGHT_BROWSERS_PATH=0`, `STM32_MONITOR_CHROMIUM_EXECUTABLE` to the verified support executable, and `PLAYWRIGHT_OUTPUT_DIR` below `$taskRoot`; run `& $npm run typecheck:e2e`, then `& $npm exec -- playwright test e2e/monitor.spec.ts e2e/security.spec.ts e2e/isolation.spec.ts e2e/accessibility.spec.ts --project=chromium-1280 --project=chromium-1024`. Expected: FAIL only because `acceptance.ts` and its exports are absent; `e2e/fixture-contract.spec.ts` still passes independently.

- [ ] **Step 3: Implement the exact browser helper and all scenarios without product bypass.** The origin guard and metrics collector use real browser APIs and write retained JSON only below the external evidence root:

```ts
import {expect,type BrowserContext,type Page} from "@playwright/test";
import type {JsonValue} from "../src/api/contract";
import {type AssetSizes,type DropTotals,type MonitorBrowserFixture,type PerformanceSnapshot,type ProducerOptions} from "./fixture";
export type HeapSample={minute:number;bytes:number};
export type GuardEvidence={attempts:string[]};
const guards=new WeakMap<BrowserContext,GuardEvidence>();
export function guardFor(context:BrowserContext):GuardEvidence{const value=guards.get(context);if(value===undefined)throw new Error("same-origin guard was not installed");return value;}
export interface InstrumentedWindow extends Window{__monitorUpdates?:number[];__monitorLongTasks?:number[];__monitorLongTaskObserver?:PerformanceObserver}
export type PerformanceOptions={warmupMs:120000;measureMs:180000;producer:ProducerOptions};
export type DropEvidence={subscriber:string;history:string;deadline:string;service:string};export type AssetEvidence={rawBytes:string;gzipJsBytes:string;gzipCssBytes:string};
export type PerformanceEvidence={updateP50Ms:number;updateP95Ms:number;updateMaxMs:number;longTasksAtLeast200Ms:number;queueGrowth:number;queueSamples:readonly number[];heapSlopeMiBPerMinute:number;serverDropsBefore:DropEvidence;serverDropsAfter:DropEvidence;realizedPoints:number;sampleCount:string;assetSizes:AssetEvidence;warmupMs:120000;measureMs:180000;producerConfirmedAtUnixNs:string};
export type PerformanceInput={updates:readonly number[];heaps:readonly HeapSample[];queues:readonly number[];longTasks:readonly number[];dropsBefore:DropTotals;dropsAfter:DropTotals;realizedPoints:number;sampleCount:bigint;assetSizes:AssetSizes;warmupMs:120000;measureMs:180000;producerConfirmedAtUnixNs:bigint};
export const expectedSecurityHeaders=(origin:string)=>{const base=new URL(origin),ws=`${base.protocol==="https:"?"wss:":"ws:"}//${base.host}`;return{"cache-control":"no-store","content-security-policy":`default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' ${ws}; worker-src 'none'; child-src 'none'; media-src 'none'`,"referrer-policy":"no-referrer","x-content-type-options":"nosniff","cross-origin-opener-policy":"same-origin","cross-origin-resource-policy":"same-origin","permissions-policy":"camera=(), microphone=(), geolocation=(), usb=(), serial=(), payment=()"};};
export async function installSameOriginGuard(context:BrowserContext,allowed:string):Promise<GuardEvidence>{
 const base=new URL(allowed),attempts:string[]=[];if(!["http:","https:"].includes(base.protocol)||base.username||base.password||base.pathname!=="/"||base.search||base.hash)throw new Error("allowed origin is invalid");
 const permitted=(candidate:URL,websocket:boolean)=>candidate.hostname===base.hostname&&candidate.port===base.port&&candidate.protocol===(websocket?(base.protocol==="https:"?"wss:":"ws:"):base.protocol);
 await context.route("**/*",async route=>{const url=new URL(route.request().url());if(!permitted(url,false)){attempts.push(url.origin);await route.abort("blockedbyclient");}else await route.continue();});
 await context.routeWebSocket(/.*/,async socket=>{const url=new URL(socket.url());if(!permitted(url,true)){attempts.push(url.origin);await socket.close();}else socket.connectToServer();});
 const evidence={attempts};guards.set(context,evidence);return evidence;
}
export const typedValues=(count:number):readonly JsonValue[]=>Array.from({length:count},(_,index)=>({expression:`v${index}`,typeName:"uint32_t",value:index,rawHex:`0x${index.toString(16).padStart(8,"0")}`,bitWidth:32}));
export async function realizedChartPointCount(page:Page):Promise<number>{return page.locator("[data-chart-realized-points]").evaluate(node=>Number(node.getAttribute("data-chart-realized-points")));}
export async function collectFiveMinuteMetrics(page:Page,monitor:MonitorBrowserFixture,options:PerformanceOptions):Promise<PerformanceEvidence>{
 const updates:number[]=[],heaps:HeapSample[]=[],queues:number[]=[];
 await page.evaluate(()=>{const target=window as InstrumentedWindow;target.__monitorUpdates=[];target.__monitorLongTasks=[];addEventListener("stm32-monitor:chart-update",event=>{const value=(event as CustomEvent<{durationMs:number}>).detail.durationMs;if(Number.isFinite(value))target.__monitorUpdates!.push(value);});target.__monitorLongTaskObserver=new PerformanceObserver(list=>target.__monitorLongTasks!.push(...list.getEntries().map(entry=>entry.duration)));target.__monitorLongTaskObserver.observe({entryTypes:["longtask"]});});
 const producer=await monitor.startProducer(options.producer);if(!producer.active||!await monitor.producerActive())throw new Error("producer did not become active");const warmStarted=performance.now();let before:DropTotals,baseline:bigint,measureStarted=0;
 try{await page.waitForTimeout(options.warmupMs);if(performance.now()-warmStarted<options.warmupMs)throw new Error("warmup window ended early");await page.evaluate(()=>{const target=window as InstrumentedWindow;target.__monitorUpdates=[];target.__monitorLongTasks=[];});updates.length=0;heaps.length=0;queues.length=0;before=await monitor.dropTotals();baseline=await monitor.sampleCount();measureStarted=performance.now();while(performance.now()-measureStarted<options.measureMs){const remaining=options.measureMs-(performance.now()-measureStarted);await page.waitForTimeout(Math.min(5_000,remaining));const elapsed=performance.now()-measureStarted,snapshot:PerformanceSnapshot=await monitor.performanceSnapshot(page),measured=await page.evaluate(()=>{const target=window as InstrumentedWindow,values=[...(target.__monitorUpdates??[])];target.__monitorUpdates=[];return values;});updates.push(...measured);heaps.push({minute:elapsed/60_000,bytes:snapshot.heapBytes});queues.push(snapshot.queueDepth);}}
 finally{await monitor.stopProducer();}
 if(performance.now()-measureStarted<options.measureMs)throw new Error("measurement window ended early");const result:PerformanceEvidence=summarizePerformance({updates,heaps,queues,longTasks:await page.evaluate(()=>(window as InstrumentedWindow).__monitorLongTasks??[]),dropsBefore:before!,dropsAfter:await monitor.dropTotals(),realizedPoints:await realizedChartPointCount(page),sampleCount:(await monitor.sampleCount())-baseline!,assetSizes:await monitor.assetSizes(),warmupMs:options.warmupMs,measureMs:options.measureMs,producerConfirmedAtUnixNs:producer.confirmedAtUnixNs});await monitor.writeEvidence("performance.json",result);return result;
}
const percentile=(values:readonly number[],fraction:number)=>{if(values.length===0)throw new Error("performance sample is empty");const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*fraction)-1)]!;};
const heapSlope=(samples:readonly HeapSample[])=>{if(samples.length<2)return 0;const xm=samples.reduce((n,x)=>n+x.minute,0)/samples.length,ym=samples.reduce((n,x)=>n+x.bytes,0)/samples.length;const numerator=samples.reduce((n,x)=>n+(x.minute-xm)*(x.bytes-ym),0),denominator=samples.reduce((n,x)=>n+(x.minute-xm)**2,0);return denominator===0?0:numerator/denominator/1048576;};
const dropEvidence=(value:DropTotals):DropEvidence=>({subscriber:value.subscriber.toString(),history:value.history.toString(),deadline:value.deadline.toString(),service:value.service.toString()});const assetEvidence=(value:AssetSizes):AssetEvidence=>({rawBytes:value.rawBytes.toString(),gzipJsBytes:value.gzipJsBytes.toString(),gzipCssBytes:value.gzipCssBytes.toString()});
export function summarizePerformance(input:PerformanceInput):PerformanceEvidence{if(input.queues.length<2||input.heaps.length<2||input.assetSizes.rawBytes<=0n||input.assetSizes.gzipJsBytes<=0n||input.assetSizes.gzipCssBytes<=0n)throw new Error("real performance evidence is incomplete");return{updateP50Ms:percentile(input.updates,.5),updateP95Ms:percentile(input.updates,.95),updateMaxMs:Math.max(...input.updates),longTasksAtLeast200Ms:input.longTasks.filter(value=>value>=200).length,queueGrowth:input.queues.at(-1)!-input.queues[0]!,queueSamples:[...input.queues],heapSlopeMiBPerMinute:heapSlope(input.heaps),serverDropsBefore:dropEvidence(input.dropsBefore),serverDropsAfter:dropEvidence(input.dropsAfter),realizedPoints:input.realizedPoints,sampleCount:input.sampleCount.toString(),assetSizes:assetEvidence(input.assetSizes),warmupMs:input.warmupMs,measureMs:input.measureMs,producerConfirmedAtUnixNs:input.producerConfirmedAtUnixNs.toString()};}
export async function assertNoSecret(page:Page,monitor:MonitorBrowserFixture):Promise<void>{const browser=await page.evaluate(async()=>({url:location.href,text:document.documentElement.textContent??"",local:Object.entries(localStorage),session:Object.entries(sessionStorage),databases:(await indexedDB.databases()).map(item=>item.name??""),cookie:document.cookie}));expect(await monitor.containsSecret(JSON.stringify(browser))).toBe(false);expect(await monitor.consoleContainsSecret()).toBe(false);}
export async function completeUserWorkflow(page:Page,monitor:MonitorBrowserFixture):Promise<void>{await expect(page.getByText("No groups yet")).toBeVisible();await page.getByRole("button",{name:"Connect probe"}).click();await expect(page.getByText("Connected")).toBeVisible();const group=await monitor.createGroupThroughUi(page,{rows:2,intervalMs:250});await monitor.startThroughUi(page,group);await monitor.startProducer({hz:10,typedValues:typedValues(2)});await expect.poll(()=>monitor.sampleCount()).toBeGreaterThan(1n);await monitor.stopProducer();await expect(page.getByRole("table",{name:"Live values"})).toContainText("counter");await page.getByLabel("History start nanoseconds").fill("0");await page.getByLabel("History end nanoseconds").fill("9223372036854775807");await page.getByLabel("History group ID").fill(group.groupId);await page.getByRole("button",{name:"Load history"}).click();await expect(page.getByRole("table",{name:"Monitor history"})).toContainText("counter");await expect(page.getByTestId("history-chart")).toBeVisible();await page.getByRole("button",{name:"Stop sampling"}).click();await page.getByRole("button",{name:"Release probe"}).click();}
```

The five spec modules contain these executable scenario bodies (each imports Playwright `test,expect` and the shown helpers):

```ts
// monitor.spec.ts (complete imports)
import {Buffer} from "node:buffer";import {createHash} from "node:crypto";
import {expect,test} from "./fixture";
import {completeUserWorkflow,guardFor,installSameOriginGuard,typedValues} from "./acceptance";
test.afterEach(async({page})=>expect(guardFor(page.context()).attempts).toEqual([]));
test("complete real-service workflow and history table/chart",async({page,monitor})=>{const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await completeUserWorkflow(page,monitor);expect(guard.attempts).toEqual([]);});
test("identity and successful reconnect are authoritative",async({page,monitor})=>{const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await expect(page.getByRole("region",{name:"Workspace identity"})).toContainText("e2e-session");await page.getByRole("button",{name:"Connect probe"}).click();const before=await page.getByTestId("binding-epoch").getAttribute("data-value");await page.getByRole("button",{name:"Reconnect probe"}).click();await expect(page.getByText("Connected")).toBeVisible();expect(BigInt(await page.getByTestId("binding-epoch").getAttribute("data-value")??"0")).toBeGreaterThan(BigInt(before??"0"));expect(guard.attempts).toEqual([]);});
test("probe busy and lease-lost remain explicit",async({page,monitor})=>{const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await monitor.setProbeMode("busy");await page.getByRole("button",{name:"Connect probe"}).click();await expect(page.getByRole("alert")).toContainText("MONITOR_PROBE_BUSY");await monitor.setProbeMode("ready");await page.getByRole("button",{name:"Connect probe"}).click();await monitor.setProbeMode("lease-lost");await page.getByRole("button",{name:"Reconnect probe"}).click();await expect(page.getByRole("alert")).toContainText("MONITOR_LEASE_LOST");expect(guard.attempts).toEqual([]);});
for(const scenario of ["scalar","float","enum","array","member","register","unavailable","pagination"] as const)test(`catalog ${scenario} uses authoritative shallow rows`,async({page,monitor})=>{const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.setCatalogScenario(scenario);await monitor.navigate(page);await page.getByRole("button",{name:"Connect probe"}).click();if(scenario==="register")await page.getByLabel("Catalog kind").selectOption("registers");await page.getByLabel("Catalog search").fill("counter");if(scenario==="unavailable")await expect(page.getByRole("alert")).toContainText("MONITOR_PROVENANCE_CHANGED");else await expect(page.getByRole("region",{name:"Catalog results"})).toHaveAttribute("data-scenario",scenario);if(scenario==="pagination")await page.getByRole("button",{name:"Next catalog page"}).click();expect(guard.attempts).toEqual([]);});
test("group CRUD order import and conflict are authoritative",async({page,monitor})=>{await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);const group=await monitor.createGroupThroughUi(page,{rows:2,intervalMs:250});await page.getByLabel("Group name").fill("Renamed");await page.getByRole("button",{name:"Save group"}).click();await page.getByRole("button",{name:"Move watch down"}).first().click();await page.getByRole("button",{name:"Export groups"}).click();await page.getByLabel("Import group JSON").setInputFiles({name:"groups.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify({schemaVersion:1,groups:[{name:"Imported",description:"",intervalMs:5000,items:[]}]}))});await page.getByRole("button",{name:"Confirm import"}).click();await monitor.forceGroupConflict();await page.getByRole("button",{name:"Save group"}).click();await expect(page.getByRole("alert")).toContainText("MONITOR_GROUP_CONFLICT");await page.getByRole("button",{name:"Delete group"}).click();await page.getByRole("button",{name:"Confirm delete"}).click();expect(group.revision).toBeGreaterThan(0n);});
for(const intervalMs of [100,250,5000] as const)test(`sampling interval ${intervalMs} ms and command states`,async({page,monitor})=>{await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await page.getByRole("button",{name:"Connect probe"}).click();const group=await monitor.createGroupThroughUi(page,{rows:1,intervalMs});await monitor.startThroughUi(page,group);await page.getByRole("button",{name:"Pause sampling"}).click();await expect(page.getByText("PAUSED")).toBeVisible();await page.getByRole("button",{name:"Resume sampling"}).click();await expect(page.getByText("RUNNING")).toBeVisible();await page.getByRole("button",{name:"Stop sampling"}).click();await expect(page.getByText("IDLE")).toBeVisible();});
test.describe("touch-enabled chart",()=>{test.use({hasTouch:true});test("256 rows isolate item errors and a real two-contact gesture changes zoom",async({page,monitor,browserName})=>{test.skip(browserName!=="chromium");await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await page.getByRole("button",{name:"Connect probe"}).click();const group=await monitor.createGroupThroughUi(page,{rows:256,intervalMs:100});await monitor.startThroughUi(page,group);await monitor.failNextItem("MONITOR_SAMPLE_ITEM_FAILED");await monitor.startProducer({hz:10,typedValues:typedValues(256)});await expect(page.getByRole("table",{name:"Live values"}).locator("tbody tr")).toHaveCount(256);await expect(page.getByRole("table",{name:"Live values"})).toContainText("MONITOR_SAMPLE_ITEM_FAILED");const chart=page.getByRole("img",{name:"Live sample chart"}),box=await chart.boundingBox();if(box===null)throw new Error("chart has no box");const before=await chart.getAttribute("data-zoom"),cdp=await page.context().newCDPSession(page),point=(x:number)=>({x:box.x+x,y:box.y+box.height/2,radiusX:2,radiusY:2,force:1,id:x});await cdp.send("Input.dispatchTouchEvent",{type:"touchStart",touchPoints:[point(80),point(box.width-80)]});await cdp.send("Input.dispatchTouchEvent",{type:"touchMove",touchPoints:[point(180),point(box.width-180)]});await cdp.send("Input.dispatchTouchEvent",{type:"touchEnd",touchPoints:[]});await expect(chart).not.toHaveAttribute("data-zoom",before??"");await monitor.stopProducer();});});
test("mouse wheel and keyboard plus minus zero expose independent zoom state",async({page,monitor})=>{await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);const chart=page.getByRole("img",{name:"Live sample chart"});await chart.hover();const initial=await chart.getAttribute("data-zoom");await page.mouse.wheel(0,-400);await expect(chart).not.toHaveAttribute("data-zoom",initial??"");await chart.focus();await page.keyboard.press("+");const plus=await chart.getAttribute("data-zoom");await page.keyboard.press("-");await expect(chart).not.toHaveAttribute("data-zoom",plus??"");await page.keyboard.press("0");await expect(chart).toHaveAttribute("data-zoom","0:100");});
test("outer drops create a gap while accepted deltas stay compact",async({page,monitor})=>{await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await page.getByRole("button",{name:"Connect probe"}).click();const group=await monitor.createGroupThroughUi(page,{rows:1,intervalMs:250});await monitor.startThroughUi(page,group);await monitor.setDropDeltas({subscriber:2n,history:3n,deadline:4n,service:0n});await monitor.startProducer({hz:10,typedValues:typedValues(1)});await expect(page.getByRole("status")).toContainText("2 / 3 / 4");await monitor.stopProducer();const before=await monitor.dropTotals();await monitor.emitOuterDrop(7n);await expect(page.getByTestId("continuity-gap")).toBeVisible();const totals=await monitor.dropTotals();expect(totals.subscriber).toBe(2n);expect(totals.history).toBe(3n);expect(totals.deadline).toBe(4n);expect(totals.service).toBe(before.service+7n);});
test("replay gap stale heartbeat and reset preserve explicit semantics",async({page,monitor})=>{test.setTimeout(50_000);await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await page.getByRole("button",{name:"Connect probe"}).click();const group=await monitor.createGroupThroughUi(page,{rows:1,intervalMs:250});await monitor.startThroughUi(page,group);await monitor.startProducer({hz:10,typedValues:typedValues(1)});await expect.poll(()=>monitor.sampleCount()).toBeGreaterThan(1n);const replayAnchor=await monitor.disconnectLive(false),beforeReplay=await monitor.sampleCount();await expect.poll(()=>monitor.sampleCount()).toBeGreaterThan(beforeReplay);await expect.poll(()=>monitor.subscriptionCursors()).toContain(replayAnchor);await expect(page.getByRole("table",{name:"Live values"})).toContainText("counter");const gapAnchor=await monitor.disconnectLive(true);await monitor.expireBefore(gapAnchor+3n);await expect.poll(()=>monitor.subscriptionCursors()).toContain(gapAnchor);await expect(page.getByTestId("continuity-gap")).toBeVisible();await monitor.forceStale();await expect(page.getByText("Live updates stale")).toBeVisible({timeout:40_000});await monitor.forceReset();await expect(page.getByText("Continuity reset")).toBeVisible();await monitor.stopProducer();});
test("history producer ordinals Previous chart and verified CSV JSONL",async({page,monitor})=>{test.setTimeout(30_000);await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await page.getByRole("button",{name:"Connect probe"}).click();const group=await monitor.createGroupThroughUi(page,{rows:2,intervalMs:250});await monitor.startThroughUi(page,group);await monitor.startProducer({hz:10,typedValues:typedValues(2)});await expect.poll(()=>monitor.sampleCount(),{timeout:15_000}).toBeGreaterThan(105n);await monitor.stopProducer();await page.getByLabel("History start nanoseconds").fill("0");await page.getByLabel("History end nanoseconds").fill("9223372036854775807");await page.getByRole("button",{name:"Load history"}).click();await expect(page.getByRole("table",{name:"Monitor history"})).toContainText("0");await page.getByRole("button",{name:"Next history page"}).click();await expect(page.getByRole("button",{name:"Previous history page"})).toBeEnabled();await page.getByRole("button",{name:"Previous history page"}).click();await expect(page.getByRole("button",{name:"Previous history page"})).toBeDisabled();await expect(page.getByTestId("history-chart")).toBeVisible();for(const format of ["csv","jsonl"] as const){await page.getByLabel("Export format").selectOption(format);await page.getByRole("button",{name:"Create export"}).click();await page.getByRole("button",{name:"Download verified export"}).click();}const downloads=await monitor.downloadedExports();expect(downloads).toHaveLength(2);expect(new Set(downloads.map(item=>item.format))).toEqual(new Set(["csv","jsonl"]));for(const item of downloads){expect(createHash("sha256").update(item.body).digest("hex")).toBe(item.artifact.sha256);expect(BigInt(item.body.byteLength)).toBe(item.artifact.bytes);expect(item.body.byteLength).toBeGreaterThan(0);}});
```

```ts
// security.spec.ts (complete file)
import {expect,test} from "./fixture";import {assertNoSecret,expectedSecurityHeaders,installSameOriginGuard} from "./acceptance";
test("headers offline inventory secrets and normal-origin guard remain closed",async({page,monitor})=>{const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await assertNoSecret(page,monitor);expect(await monitor.securityHeaders(page)).toEqual(expectedSecurityHeaders(monitor.origin));expect(await monitor.remoteInventory(page)).toEqual([]);expect(guard.attempts).toEqual([]);});
```

```ts
// isolation.spec.ts (complete file)
import {expect,startMonitor,test} from "./fixture";import {installSameOriginGuard,typedValues} from "./acceptance";
test("two workspaces isolate groups history live storage and block an untouched service",async({browser,page,monitor})=>{const other=await startMonitor("other-workspace"),blocked=await startMonitor("blocked-workspace"),otherContext=await browser.newContext(),otherPage=await otherContext.newPage();try{const guard=await installSameOriginGuard(page.context(),monitor.origin),otherGuard=await installSameOriginGuard(otherContext,other.origin);await monitor.navigate(page);await other.navigate(otherPage);for(const target of [page,otherPage])await target.getByRole("button",{name:"Connect probe"}).click();const one=await monitor.createGroupThroughUi(page,{rows:1,intervalMs:250}),two=await other.createGroupThroughUi(otherPage,{rows:2,intervalMs:5000});expect(one.groupId).not.toBe(two.groupId);await monitor.startThroughUi(page,one);await other.startThroughUi(otherPage,two);await monitor.startProducer({hz:10,typedValues:typedValues(1)});await other.startProducer({hz:10,typedValues:typedValues(2)});await expect.poll(()=>monitor.sampleCount()).toBeGreaterThan(0n);await expect.poll(()=>other.sampleCount()).toBeGreaterThan(0n);expect((await monitor.liveEvents(2)).length).toBeGreaterThan(0);expect((await other.liveEvents(2)).length).toBeGreaterThan(0);for(const target of [page,otherPage]){await target.getByLabel("History start nanoseconds").fill("0");await target.getByLabel("History end nanoseconds").fill("9223372036854775807");await target.getByRole("button",{name:"Load history"}).click();await expect(target.getByRole("table",{name:"Monitor history"})).toBeVisible();expect(await target.evaluate(()=>Object.keys(localStorage))).toEqual([]);}expect(await blocked.requestCount()).toBe(0);const target=new URL("api/v1/status",blocked.origin+"/").href;await page.evaluate(url=>fetch(url),target).catch(()=>undefined);expect(guard.attempts).toContain(new URL(target).origin);expect(await blocked.requestCount()).toBe(0);expect(otherGuard.attempts).toEqual([]);}finally{await monitor.stopProducer();await other.stopProducer();await otherContext.close();await blocked.stop();await other.stop();}});
```

```ts
// accessibility.spec.ts (complete file)
import AxeBuilder from "@axe-core/playwright";import {expect,test} from "./fixture";import {installSameOriginGuard} from "./acceptance";
async function tabTo(page:import("@playwright/test").Page,name:string){const labelled=page.getByLabel(name,{exact:true}),button=page.getByRole("button",{name,exact:true}),focused=async(locator:import("@playwright/test").Locator)=>locator.evaluateAll(elements=>elements.some(element=>element===document.activeElement));for(let i=0;i<80;i++){await page.keyboard.press("Tab");if(await focused(labelled)||await focused(button))return;}throw new Error(`keyboard target not reached: ${name}`);}
test("real 200 percent then keyboard-only valid group watch and Start",async({page,monitor},testInfo)=>{const guard=await installSameOriginGuard(page.context(),monitor.origin);await monitor.navigate(page);await page.evaluate(()=>{document.documentElement.style.zoom="200%";});expect([[1280,720],[1024,768]]).toContainEqual([page.viewportSize()!.width,page.viewportSize()!.height]);await tabTo(page,"Connect probe");await expect(page.getByRole("button",{name:"Connect probe"})).toBeFocused();await page.keyboard.press("Enter");await expect(page.getByText("Connected")).toBeVisible();await tabTo(page,"Create group");await expect(page.getByRole("button",{name:"Create group"})).toBeFocused();await page.keyboard.press("Enter");await tabTo(page,"Group name");await page.keyboard.type("Keyboard group");await tabTo(page,"Sampling interval");await page.keyboard.press("Control+A");await page.keyboard.type("250");await tabTo(page,"Add watch");await page.keyboard.press("Enter");await tabTo(page,"Watch 1 expression");await page.keyboard.press("Control+A");await page.keyboard.type("counter");await tabTo(page,"Save group");await page.keyboard.press("Enter");await tabTo(page,"Start sampling");await expect(page.getByRole("button",{name:"Start sampling"})).toBeFocused();await page.keyboard.press("Enter");await expect(page.getByText("RUNNING")).toBeVisible();expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);await page.screenshot({path:testInfo.outputPath("zoom-200.png"),fullPage:true});expect(guard.attempts).toEqual([]);});
```

No spec mocks `fetch`, `WebSocket`, auth, service, or history serialization. Performance passes only after the adapter reports 4,800 stored points during the concurrent run; configuration counts cannot satisfy it.

- [ ] **Step 4: Run GREEN functional, a11y, security, isolation, and the full five-minute collector.** With the exact Step 2 environment, run `& $npm run typecheck:e2e`; run `& $npm exec -- playwright test e2e/monitor.spec.ts e2e/security.spec.ts e2e/isolation.spec.ts e2e/accessibility.spec.ts --project=chromium-1280 --project=chromium-1024`; then run `& $npm exec -- playwright test e2e/performance.spec.ts --project=chromium-1280 --grep 'five-minute production fixture stays bounded' --workers=1`. Assert `$taskRoot` contains one `performance.json` plus per-project screenshots and no repository path changed. Expected: all scenarios PASS with the stated 120+180-second thresholds and unchanged drops.

- [ ] **Step 5: Commit Task 12 browser evidence code.** Call `Commit-0502Task 'test(STM32TK-0502): add browser release acceptance' @('tools/stm32-monitor/ui/e2e/acceptance.ts','tools/stm32-monitor/ui/e2e/monitor.spec.ts','tools/stm32-monitor/ui/e2e/security.spec.ts','tools/stm32-monitor/ui/e2e/isolation.spec.ts','tools/stm32-monitor/ui/e2e/accessibility.spec.ts','tools/stm32-monitor/ui/e2e/performance.spec.ts')`. Do not create the report or name a moving head inside this commit.

## Unique `CODE_HEAD`, Full Verification, Fresh Review, and Report-Only Sequence

After Task 12's one commit, the implementation tasks are complete. This terminal evidence sequence is not Task 13 and creates no product commit beyond the required report-only commit.

1. In the implementation worktree, re-run the global task-entry checks with Task 12's full SHA, require a clean worktree, and bind the immutable value once:

```powershell
$CODE_HEAD = (& $git rev-parse HEAD).Trim()
if($CODE_HEAD-notmatch'^[0-9a-f]{40}$'){throw 'CODE_HEAD is not a full SHA'}
$status=@(& $git status --porcelain=v1 --untracked-files=all);if($status.Count){throw 'CODE_HEAD worktree is dirty'}
& $git merge-base --is-ancestor 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa' $CODE_HEAD
if($LASTEXITCODE-ne0){throw 'CODE_HEAD does not descend from accepted base'}
if(Test-Path -LiteralPath 'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'){throw 'report exists at CODE_HEAD'}
```

2. Create one repository-external fresh detached review worktree at exactly `$CODE_HEAD`, verify it is detached/clean, and invoke Task 10's controller there with absolute tools and a new external evidence root. The controller runs the complete Windows matrix exactly once against this SHA. It must return nonzero on any mandatory gate; no report is written after failure.

```powershell
& $git worktree add --detach $reviewRoot $CODE_HEAD
if($LASTEXITCODE-ne0){throw 'fresh review worktree creation failed'}
& $powerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $reviewRoot 'tools/release/run_0502_windows_gates.ps1') -RepoRoot $reviewRoot -EvidenceRoot $evidenceRoot -SupportRoot $supportRoot -CodeHead $CODE_HEAD -Git $git -Node $node -Npm $npm -Python310 $python310 -Python312 $python312 -CmdExe $cmdExe
if($LASTEXITCODE-ne0){throw 'Windows release matrix failed'}
```

3. Codex performs a fresh whole-branch review of `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa..$CODE_HEAD` in that clean review worktree: inspect mechanical `--name-status --no-renames`, every changed file, protocol/schema diff, historical Skill blob, 0.6 exclusion scan, test inventory equality, wheel/dist/evidence hashes, and gate logs. Any correctable issue is `REVISION_REQUIRED` on the same branch; architecture/safety/scope/coverage failure is `REWRITE_REQUIRED`. Either outcome invalidates `$CODE_HEAD`; return to the relevant task with a new local commit and repeat the terminal sequence from step 1. Do not amend.

4. Only after every mandatory gate and fresh review passes, create `docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md` in the implementation worktree. It records module, status, accepted-base full SHA, branch, exact **code head before report commit** `$CODE_HEAD`, scope/path summary, version/lockfile facts, each gate owner/status/OS/arch/absolute tool+version/cwd/full command/UTC/exit/bounded summary/measurement, wheel and `ui_dist`/browser/performance evidence relative paths+bytes+SHA-256, and only the two legal named deferrals when actually applicable. It contains no token/access URL, its own/final commit SHA, moving commit total, plaintext credential, fabricated hardware PASS, or custom packet/signature.

5. Commit exactly the report and nothing else:

```powershell
& $git add -- 'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'
& $git diff --cached --name-only
if((@(& $git diff --cached --name-only)-join"`n")-cne'docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md'){throw 'report commit contains another path'}
& $git commit -m 'docs(STM32TK-0502): record monitor UI release evidence'
if($LASTEXITCODE-ne0){throw 'report commit failed'}
$finalHead=(& $git rev-parse HEAD).Trim();$parent=(& $git rev-parse HEAD^).Trim()
if($parent-cne$CODE_HEAD){throw 'report commit parent is not CODE_HEAD'}
```

6. Verify final worktree clean, report diff is the sole `$CODE_HEAD..$finalHead` change, and the complete accepted-base diff remains in scope. Stop locally with a Codex verdict. Do not push or create/mutate a PR; the final accepted-branch remote stage requires a new explicit user authorization.

## Final Full Verification Commands

The Task 10 controller owns the authoritative run, but the report must list at least these logical commands with their absolute resolved executables and exact external roots:

```text
npm ci --offline --cache $npmWorkingCache
npm run typecheck
npm run typecheck:e2e
npm run lint
npm run test:coverage
npm run test:a11y
npm run build
npm run verify:dist (twice)
Python 3.10: complete tools/stm32-monitor/tests
Python 3.12: disjoint Monitor coverage partitions + disjoint Toolkit shards, exact-once inventories
Python 3.10/3.12: clean wheels + external installed-wheel smoke without repository PYTHONPATH
Windows CMD: both managed launchers, no ambient fallback
Playwright Chromium: 1280x720 and 1024x768 functional/a11y/security/isolation
Playwright Chromium 1280x720: full five-minute 10 Hz / 256 row / 8x600 performance
git diff --check acceptedBase..CODE_HEAD; exhaustive no-renames inventory; final clean byte manifest
```

## Plan Self-Review

- [x] Exactly 12 sequential tasks exist; each has `Files`, `Interfaces`, and exactly five checkbox steps. Each Step 1 and Step 3 contains actual test/code or an exact mechanical edit script; every Task Step 2 states a named RED failure and every Step 4 states GREEN evidence; every Task Step 5 creates exactly one local commit.
- [x] Packet schema is none. No custom packet/file/signature/handoff remains. Git full SHA plus SDD ledger is the only task handoff, and every task verifies branch, clean state, exact parent, and accepted-base ancestry.
- [x] The accepted serializer's complete envelope and actual `monitor.live -> data:{eventId,type,data}` nesting are frozen once. Client/live/fixture import the authority; no duplicated producer/consumer field arrays exist.
- [x] Every signed-int64 identity/state/revision/drop/sequence/nanosecond/byte/count/ordinal is bigint or canonical decimal at a boundary; none is `Number` identity. Controller, reducer, main, and bootstrap are separately tested.
- [x] Closed request lifecycle, sampling status refresh, ERROR/null chart gaps with prior row retention, 8x600 cap, catalog cursor invalidation, full group draft/import/export, prop-only views, and per-file >=90% branch coverage have executable tests.
- [x] Static/runtime/auth/CLI, deterministic dist/wheel, unified 0.5.0 setup/Plugin/Skill/docs, exact Windows controller, real aiohttp fake with `token_factory(32)`, real HistoryPage, replay/gap/delta, strict e2e typecheck, route-guarded browser acceptance, two viewports/200%, 4,800 realized points, and five-minute thresholds map to Tasks 7-12.
- [x] PowerShell snippets use Windows PowerShell 5.1 syntax: no ternary/null-coalescing operator, no `&&`, no PowerShell 7-only path API, and no ambient tool lookup. Tool alias and duplicate test inventories fail closed.
- [x] Whole-branch review uses a fresh clean worktree at one immutable `CODE_HEAD`; the following report-only commit records that pre-report SHA and no final SHA/moving totals. No remote action is authorized before a separately approved final accepted-branch stage.
- [x] Prohibited-instruction scan returns zero matches; no deferred filler or cross-task shorthand remains. All 0.6 exclusions are explicit and forbidden from product/test/asset/active-doc scope.
