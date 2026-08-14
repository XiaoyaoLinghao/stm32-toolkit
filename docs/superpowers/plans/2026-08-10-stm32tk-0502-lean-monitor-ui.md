# STM32TK-0502 Lean Monitor UI Implementation Plan

> **REWRITE_REQUIRED — DO NOT EXECUTE.** This monolithic recovery record points
> directly to the sole executable replacement:
> `docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md`.
> The three former split plans are also non-executable. Git full SHA plus the SDD
> ledger are the only task/phase handoff; there is no plan bundle or packet.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Ship an offline, loopback-only Monitor UI and its explicit human launcher as a fully evidenced \`0.5.0\` release, without implementing any 0.6 diagnostic product feature.

**Architecture:** Strict Preact/TypeScript turns the unchanged \`stm32-toolkit-monitor/1\` REST and live-event contracts into typed actions consumed by one pure reducer. The existing aiohttp listener serves committed Vite output from an importlib-resource allowlist; the only 0501 behavior change is the §7.3 cookie request-auth compatibility matrix.

**Tech Stack:** Python 3.10/3.12, aiohttp, Preact, strict TypeScript, Vite, modular ECharts, Vitest, Testing Library, axe, Playwright, npm, setuptools.

## Global Constraints

- Accepted base: \`bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa\`. Design authority: \`docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md\` at \`28c8a91b7f65392257c0ba517195fdd2365d55a7\`.
- Preserve all 0501 routes, envelope, REST bodies/queries, WebSocket union, history, sampling, storage, export, and public operation semantics. Only Task 1 changes bounded auth transport policy.
- Active Toolkit, Monitor, plugin, runtime, Skills, README, CLI, protocol-envelope, and active-test version surfaces are exactly \`0.5.0\`.
- Task 1 uses the configured bundled Node/npm to resolve exact direct versions, writes the observed Node floor/next-major ceiling and full npm package-manager version, then commits its generated \`package-lock.json\`; the plan never guesses those values.
- UI and API are one random-port \`127.0.0.1\` aiohttp process. There is no CDN, remote font, telemetry, analytics, service worker, source map, remote request, localStorage, sessionStorage, IndexedDB, Cache, inline script/style, \`eval\`, or \`new Function\`.
- The 32-byte token is only in the initial fragment. Before mount, the client validates a single lower-case 64-hex token, calls \`history.replaceState(null, "", "/")\`, posts it once as Bearer bootstrap evidence, clears local reference in \`finally\`, and subsequently uses only HttpOnly Strict cookie.
- UI never opens PyOCD, imports a probe backend, manages a process, auto-connects/reconnects a probe, auto-starts sampling, guesses project/target/ELF/SVD/address/type, creates a preset/example/named group, or writes browser storage.
- UI persistence remains only in 0501 stores keyed by \`workspaceId\`/\`sessionId\`; no UI request sends those identifiers or project/data-root/download path fields.
- Bounds: catalog query <=128 NFC chars/debounce 300 ms/limit <=256; table <=256 rows; chart <=8 numeric series x600; render <=1 setOption/100 ms; history <=10,000 values/page; index/manifest <=256 KiB; asset <=4 MiB; total <=8 MiB; gzip initial JS <=450 KiB/CSS <=50 KiB.
- Controls have programmatic labels. Notice is \`aria-live="polite"\`; blocking failure is \`role="alert"\`; dialogs move focus/restore trigger/Escape cancels; focus >=3:1; text >=4.5:1; controls survive 200% zoom; reduced-motion disables non-essential animation.
- The only permitted deferrals are \`DEFERRED — Linux release owner\` and \`DEFERRED — user/hardware owner\`. Windows and pure-code results are PASS, FAIL, or BLOCKED.
- Do not create OpenClaw artifacts, CI, dispatch automation, collaboration manifests, or a second runtime.
- 0.6-only: AI snapshot/analyze/diagnostic export, multi-run/group/firmware comparison, diff/brush/cross-session history, quality dashboards/timelines/distributions, annotations/bookmarks/markers, and diagnostic hypothesis/evidence/action/fix UI.
- **Command convention:** before Task 1 RED runs, use the Codex desktop \`load_workspace_dependencies\` result to resolve absolute Node, npm, npx, CPython 3.10, and CPython 3.12 paths. In task prose, \`$npm\`, \`$npx\`, \`$python310\`, and \`$python312\` mean those resolved absolute paths and are invoked with PowerShell's call operator (for example, \`& $python312 -m pytest ...\`). Never use \`py\`, PATH discovery, a system Node, or a hard-coded checkout path. Task 8 recreates the exact five-field toolchain record and validates every executable inside the release-helper process.

---

## File Structure

- \`tools/stm32-monitor/ui/src/api/contract.ts\`: validates the exact envelope and public data shapes.
- \`tools/stm32-monitor/ui/src/api/client.ts\`: the only REST request constructor.
- \`tools/stm32-monitor/ui/src/api/live.ts\`: the only WebSocket constructor; it only dispatches typed actions.
- \`tools/stm32-monitor/ui/src/state/model.ts\`, \`reducer.ts\`, \`selectors.ts\`: state definitions, pure state transitions, and bounded view selectors.
- \`tools/stm32-monitor/ui/src/catalog/shallow-selectors.ts\`: one-hop descriptor derivation only.
- \`tools/stm32-monitor/ui/src/chart/echarts.ts\`, \`series.ts\`, \`zoom.ts\`: exact ECharts module registration, bounded series, and zoom reducer.
- \`tools/stm32-monitor/ui/src/components/\`: panels render props and dispatch callbacks; none parses envelopes or owns authentication.
- \`tools/stm32-monitor/src/stm32_monitor/ui_assets.py\`: static allowlist/MIME/ETag/CSP; \`service.py\` adds routes and normalized request evidence.
- \`tools/stm32-monitor/src/stm32_monitor/ui_dist/\`: committed Vite artifact and never Node tooling.
- \`tools/release/run_0502_windows_gates.ps1\`: repository-owned, parameterized release-evidence helper; it is committed and tested before \`CODE_HEAD\`, accepts only \`-RepoRoot\`, \`-EvidenceRoot\`, and \`-ToolchainJson\`, and never assumes the main checkout path.
- \`docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md\`: the only tracked implementation report; subagent-driven-development retained reports are not tracked product evidence.

### Task 1: Client Contract, Fragment Bootstrap, Reducer, and Exact Auth Compatibility

**Files:**

- Create: \`tools/stm32-monitor/ui/package.json\`, \`package-lock.json\`, \`tsconfig.json\`, \`vite.config.ts\`, \`vitest.config.ts\`
- Create: \`tools/stm32-monitor/ui/src/main.tsx\`, \`app.tsx\`, \`styles.css\`
- Create: \`tools/stm32-monitor/ui/src/api/contract.ts\`, \`client.ts\`, \`live.ts\`
- Create: \`tools/stm32-monitor/ui/src/state/model.ts\`, \`reducer.ts\`, \`selectors.ts\`
- Create: \`tools/stm32-monitor/ui/tests/contract.test.ts\`, \`auth.test.ts\`, \`reducer.test.ts\`
- Create: \`tools/stm32-monitor/tests/test_ui_config.py\`
- Modify: \`tools/stm32-monitor/src/stm32_monitor/auth.py\`, \`service.py\`
- Modify: \`tools/stm32-monitor/tests/test_auth.py\`, \`test_service.py\`

**Interfaces:**

- \`type ApiOk<T> = {ok:true; data:T}\`; \`type ApiFailure = {ok:false; code:string; message:string}\`; \`type ApiResult<T> = ApiOk<T> | ApiFailure\`.
- \`parseEnvelope<T>(value: unknown, operation: string): ApiResult<T>\` rejects duplicate/unknown fields, protocol/toolkit/monitor version mismatch, and non-object data shape before reducer input.
- \`type MonitorAction = {type:"bootstrap.ready";status:Status}|{type:"api.failure";code:string;message:string}|{type:"live.hello";eventId:number;stateRevision:number;data:LiveHello}|{type:"live.state";eventId:number;stateRevision:number;gap:boolean;data:StateEvent}|{type:"live.sample";eventId:number;data:SampleEvent}|{type:"live.heartbeat";eventId:number;data:Heartbeat}|{type:"transport.closed"}|{type:"zoom.reset"}\`.
- \`reduce(state: MonitorState, action: MonitorAction): MonitorState\` ignores old stateRevision, rejects samples outside current workspace/session/binding, clears live continuity on bindingEpoch/runId change, inserts a gap, and resets zoom.
- \`bootstrapFromFragment(windowLike:Window, fetchLike:typeof fetch):Promise<ApiResult<{authenticated:true}>>\` is invoked before Preact mount, reducer creation, or other request.
- \`MonitorClient.status():Promise<ApiResult<Status>>\` calls \`GET /api/v1/status\` with no query/body.
- \`MonitorClient.probes():Promise<ApiResult<ProbePage>>\` calls \`GET /api/v1/probes\` with no query/body.
- \`MonitorClient.variables(query:string,cursor?:string):Promise<ApiResult<CatalogPage>>\` calls \`GET /api/v1/catalog/variables?query=&cursor=&limit=\`.
- \`MonitorClient.registers(query:string,cursor?:string):Promise<ApiResult<CatalogPage>>\` calls \`GET /api/v1/catalog/registers?query=&cursor=&limit=\`.
- \`MonitorClient.groups(cursor?:string):Promise<ApiResult<GroupPage>>\` calls \`GET /api/v1/groups?cursor=&limit=16\`.
- \`MonitorClient.createGroup(body:CreateGroup):Promise<ApiResult<WatchGroup>>\` posts \`{name,description,intervalMs,items,authorized:true}\` to \`/api/v1/groups\`.
- \`MonitorClient.updateGroup(id:string,body:UpdateGroup):Promise<ApiResult<WatchGroup>>\` patches \`/api/v1/groups/{id}\` with expectedRevision, changed fields, authorized:true.
- \`MonitorClient.deleteGroup(id:string,body:{expectedRevision:number;authorized:true}):Promise<ApiResult<DeletedGroup>>\` deletes exact route.
- \`MonitorClient.importGroups(body:{document:GroupImportDocument;authorized:true}):Promise<ApiResult<GroupImportResult>>\` posts \`/api/v1/groups/import\`.
- \`MonitorClient.connect(body:{probeId:string}):Promise<ApiResult<ObservationBinding>>\`, \`reconnect():Promise<ApiResult<ObservationBinding>>\`, and \`release():Promise<ApiResult<ReleasedProbe>>\` use exact existing probe routes; latter two send absent body.
- \`MonitorClient.start(body:{groupId:string;expectedRevision:number}):Promise<ApiResult<SamplerResult>>\`, \`pause()\`, \`resume()\`, \`stop()\` use exact sampling routes; latter three send absent body.
- \`MonitorClient.history(query:HistoryQuery):Promise<ApiResult<HistoryPage>>\` calls \`GET /api/v1/history\` with required startNs/endNs and only optional limit/cursor/runId/groupId/selectorKind/selector.
- \`MonitorClient.createExport(body:{startNs:number;endNs:number;format:"csv"|"jsonl";authorized:true}):Promise<ApiResult<ExportArtifact>>\`, \`exportStatus(id:string)\`, and \`downloadExport(id:string)\` use exact existing export routes; download sends no Range/query.
- \`LiveClient.connect(afterEventId?:number):WebSocket\` opens only \`GET /api/v1/live?afterEventId=N\`, sends no client message, and dispatches only MonitorAction.
- Python \`MonitorAuth.authorize(peer,host,origin,authorization,cookie,bootstrap,method,fetch_site,websocket)->str\` accepts only normalized method/fetch/WS evidence from \`service.py\`, never a caller “safe” flag.

\`\`\`ts
export type ProjectIdentity = {name:string; gitHead:string; dirty:boolean};
export type FirmwareIdentity = {targetDevice:string; buildId:string; elfDigest:string};
export type Probe = {probeId:string; vendor:string; product:string; boardName:string|null};
export type ProbeState = {connected:boolean; probeId:string|null; bindingEpoch:number|null; leaseState:"NONE"|"HELD"|"BUSY"|"LOST"};
export type DropTotals = {subscriber:number;history:number;deadline:number;service:number};
export type ObservationBinding = {workspaceId:string;sessionId:string;bindingEpoch:number;probeId:string};
export type WatchItem = {selector:string;kind:"variable"|"register";typeName:string};
export type WatchGroup = {groupId:string;revision:number;name:string;description:string;intervalMs:number;items:readonly WatchItem[]};
export type CatalogDescriptor = {selector:string;kind:"variable"|"register";typeName?:string;byteSize?:number;signed?:boolean;encoding?:string;qualifiers?:readonly string[];aliases?:readonly string[];enumValues?:Readonly<Record<string,number>>;elementCount?:number;elementKind?:string;memberNames?:readonly string[];sampleable?:boolean;readAction?:string;access?:string};
export type SampleValue = {selector:string;status:"OK"|"ERROR";value:unknown;rawHex:string|null;capturedNs:number;code?:string};
export type HistoryBatchSlice = {binding:ObservationBinding;startOrdinal:number;values:readonly SampleValue[]};
export type Status = {project:ProjectIdentity; firmware:FirmwareIdentity|null; probe:ProbeState; sampling:SamplingState};
export type ProbePage = {probes:readonly Probe[]};
export type CatalogPage = {items:readonly CatalogDescriptor[]; nextCursor:string|null};
export type GroupPage = {groups:readonly WatchGroup[]; nextCursor:string|null; revision:number};
export type SamplingState = {state:"STOPPED"|"RUNNING"|"PAUSED"|"PAUSED_BLOCKED"; runId:string|null; actualRateHz:number; latencyNs:number; drops:DropTotals};
export type HistoryPage = {slices:readonly HistoryBatchSlice[]; nextCursor:string|null};
export type ExportArtifact = {exportId:string; format:"csv"|"jsonl"; verified:boolean};
export type LiveHello = {workspaceId:string; sessionId:string; bindingEpoch:number; stateRevision:number};
export type StateEvent = {binding:ObservationBinding|null; sampling:SamplingState};
export type SampleEvent = {workspaceId:string; sessionId:string; bindingEpoch:number; runId:string|null; values:readonly SampleValue[]};
export type MonitorAction =
 | {type:"bootstrap.ready";status:Status}
 | {type:"probes.loaded";page:ProbePage}|{type:"catalog.loaded";kind:"variables"|"registers";page:CatalogPage}
 | {type:"groups.loaded";page:GroupPage}|{type:"groups.conflict";code:"MONITOR_GROUP_REVISION_CONFLICT"}
 | {type:"sampling.changed";data:SamplingState}|{type:"history.loaded";page:HistoryPage}
 | {type:"export.created";artifact:ExportArtifact}|{type:"export.ready";artifact:ExportArtifact}
 | {type:"live.hello";eventId:number;stateRevision:number;data:LiveHello}
 | {type:"live.state";eventId:number;stateRevision:number;gap:boolean;data:StateEvent}
 | {type:"live.sample";eventId:number;data:SampleEvent}|{type:"live.heartbeat";eventId:number}
 | {type:"zoom.in"}|{type:"zoom.out"}|{type:"zoom.reset"}|{type:"zoom.set";start:number;end:number}
 | {type:"api.failure";code:string;message:string}|{type:"transport.closed"};
\`\`\`

#### Task 1A: exact UI tool configuration

- [ ] **1A.1 (2–5 min): Write the failing configuration contract test.** Create \`tools/stm32-monitor/tests/test_ui_config.py\`; have it read all five Task 1 config files and assert exact direct dependency strings (no range, tag, or URL), a concrete Node floor with next-major-exclusive ceiling, a full npm \`packageManager\`, strict/noEmit/noUncheckedIndexedAccess TypeScript, deterministic manifest/no sourcemap, jsdom plus v8 branch coverage, no aggregate ECharts entry, and Chromium/Firefox/WebKit projects.
- [ ] **1A.2 (2–5 min): Run RED.** From repository root run \`& $python312 -m pytest tools/stm32-monitor/tests/test_ui_config.py -q\`. Expected: FAIL at the first missing config file.
- [ ] **1A.3 (2–5 min): Implement exactly the tested configuration.** Create \`package.json\` with direct versions resolved from bundled Node/npm, set \`engines.node\` to the observed version through next-major-exclusive and \`packageManager\` to the full observed npm version, create the strict TypeScript/Vite/Vitest/Playwright configs, and generate \`package-lock.json\` only with \`& $npm install --package-lock-only\`.
- [ ] **1A.4 (2–5 min): Run GREEN config gates.** Run \`& $python312 -m pytest tools/stm32-monitor/tests/test_ui_config.py -q; & $npm ci; & $npm run typecheck; & $npm run lint; & $npm ci\`. Expected: PASS and \`git diff -- package-lock.json\` is empty after the second \`npm ci\`.
- [ ] **1A.5 (2–5 min): Commit the configuration unit.** Run \`git add tools/stm32-monitor/ui/package.json tools/stm32-monitor/ui/package-lock.json tools/stm32-monitor/ui/tsconfig.json tools/stm32-monitor/ui/vite.config.ts tools/stm32-monitor/ui/vitest.config.ts tools/stm32-monitor/tests/test_ui_config.py\` and commit \`test(STM32TK-0502): lock UI tool configuration\`.

#### Task 1B: Python \`auth.py\` and \`service.py\` §7.3 matrix

- [ ] **1B.1 (2–5 min): Write concrete failing auth/service parameter rows.** Each row calls \`_auth().authorize(peer="127.0.0.1",host="127.0.0.1:43125",origin=origin,authorization="",cookie=TOKEN,bootstrap=False,method=method,fetch_site=fetch_site,websocket=websocket)\`; allowed rows assert \`"cookie"\`, denied rows assert \`MonitorAuthError\`. Include no-Origin same-origin GET/HEAD/WS, mutation without Origin, Bearer without exact Origin, missing metadata, Origin:null, cross/same-site/none, wrong Host/peer, header overflow, unsupported method, bootstrap-cookie rejection, and WS client close 1008.
- [ ] **1B.2 (2–5 min): Run RED.** From \`tools/stm32-monitor\`, run \`& $python312 -m pytest tests/test_auth.py::test_cookie_safe_matrix tests/test_service.py::test_cookie_transport_matrix -q\`. Expected: FAIL because method/fetch-site/WS evidence is not accepted.
- [ ] **1B.3 (2–5 min): Implement only normalized method/fetch-site/websocket parameters and the design matrix.** Preserve peer/Host/budget/constant-time token/cookie attributes/public codes; never accept a caller-supplied safe flag.
- [ ] **1B.4 (2–5 min): Run GREEN under both interpreters.** Run \`& $python312 -m pytest tests/test_auth.py tests/test_service.py -q; & $python310 -m pytest tests/test_auth.py tests/test_service.py -q\`. Expected: both PASS with no operation/body/query changes.
- [ ] **1B.5 (2–5 min): Commit the bounded auth unit.** Run \`git add tools/stm32-monitor/src/stm32_monitor/auth.py tools/stm32-monitor/src/stm32_monitor/service.py tools/stm32-monitor/tests/test_auth.py tools/stm32-monitor/tests/test_service.py\` and commit \`fix(STM32TK-0502): allow bounded browser cookie requests\`.

#### Task 1C: \`contract.ts\`

- [ ] **1C.1 (2–5 min): Write the full failing parser/type tests.** Assert exact success parsing and fixed \`MONITOR_PROTOCOL_INVALID\` failures for duplicate keys, unknown envelope fields, non-object, wrong protocol/toolkit/monitor version, wrong operation, malformed success data, and non-ok public code/message; add one valid and one invalid fixture for every public data/action union member declared in Task 1.
- [ ] **1C.2 (2–5 min): Run RED.** Run \`& $npm run test -- contract\`. Expected: FAIL because \`parseEnvelope\` is absent.
- [ ] **1C.3 (2–5 min): Implement exactly the tested types and parser.** Define every declared public Task 1 type, then add record/key/version/operation/data-shape guards and the typed success/failure return; components never receive raw envelopes or details.
- [ ] **1C.4 (2–5 min): Run GREEN and typecheck.** Run \`& $npm run test -- contract; & $npm run typecheck\`. Expected: PASS.
- [ ] **1C.5 (2–5 min): Commit the contract unit.** Run \`git add tools/stm32-monitor/ui/src/api/contract.ts tools/stm32-monitor/ui/tests/contract.test.ts\` and commit \`feat(STM32TK-0502): define exact monitor client contracts\`.

#### Task 1D: \`main.tsx\` fragment bootstrap

- [ ] **1D.1 (2–5 min): Write the full failing bootstrap/security tests.** Assert one lowercase 64-hex fragment is read, \`history.replaceState(null,"","/")\` occurs before the one bootstrap fetch, fetch is POST with Bearer/exact Origin/\`body:null\`, local token reference is cleared in \`finally\`, and App mount follows success only. Also assert invalid/missing/duplicate/query/storage token attempts issue no normal request and that the token is absent from DOM, props, state, URL, errors, console, local/session storage, and IndexedDB names.
- [ ] **1D.2 (2–5 min): Run RED.** Run \`& $npm run test -- auth -t "scrubs fragment before"\`. Expected: FAIL.
- [ ] **1D.3 (2–5 min): Implement exactly the tested bootstrap and no-secret behavior.** Implement \`readSingleToken\` and \`bootstrapFromFragment\` in the asserted order; invalid/missing/duplicate/query/storage token attempts scrub then render only a fixed secret-free startup error, create no MonitorState, make no normal request, and retain no token reference after \`finally\`.
- [ ] **1D.4 (2–5 min): Run GREEN and typecheck.** Repeat 1D.2 and run typecheck.
- [ ] **1D.5 (2–5 min): Commit the fragment-bootstrap unit.** Run \`git add tools/stm32-monitor/ui/src/main.tsx tools/stm32-monitor/ui/tests/auth.test.ts\` and commit \`feat(STM32TK-0502): bootstrap monitor auth from a scrubbed fragment\`.

#### Task 1E: \`client.ts\` and \`live.ts\`

- [ ] **1E.1 (2–5 min): Write the full failing transport tests for every method listed in Interfaces.** Assert exact route/query/body, \`authorized:true\`, absent bodies for reconnect/release/pause/resume/stop, no Range for download, no workspace/session/project/path override, cookie credentials, \`afterEventId\` as the sole optional live query, one-for-one mapping of messages to declared \`MonitorAction\`, reconnect/event ordering, and no client WS messages.
- [ ] **1E.2 (2–5 min): Run RED.** Run \`& $npm run test -- contract -t "request construction"\`. Expected: FAIL because clients are absent.
- [ ] **1E.3 (2–5 min): Implement exactly the tested two transport classes and central \`request<T>\` helper.** Only \`client.ts\` calls fetch; only \`live.ts\` constructs WebSocket; both parse before dispatch, preserve event order, expose no extra live query, and never send a client message.
- [ ] **1E.4 (2–5 min): Run GREEN and typecheck.** Repeat 1E.2 and run typecheck.
- [ ] **1E.5 (2–5 min): Commit the transport unit.** Run \`git add tools/stm32-monitor/ui/src/api/client.ts tools/stm32-monitor/ui/src/api/live.ts tools/stm32-monitor/ui/tests/contract.test.ts\` and commit \`feat(STM32TK-0502): add exact monitor transports\`.

#### Task 1F: \`model.ts\`, \`reducer.ts\`, \`selectors.ts\`, \`app.tsx\`, and base \`styles.css\`

- [ ] **1F.1 (2–5 min): Write failing pure reducer tests.** Assert old stateRevision identity return, sample binding rejection/stale, bindingEpoch/runId change clears rings and resets zoom, gap inserts null/reset/status-refresh intent, and api.failure preserves panel input.
- [ ] **1F.2 (2–5 min): Run RED.** Run \`& $npm run test -- reducer\`. Expected: FAIL because state modules are absent.
- [ ] **1F.3 (2–5 min): Implement immutable initial state and every declared action branch, then prop-only App composition.** \`app.tsx\` owns no fetch/envelope parsing; selectors enforce the global bounds; base CSS supplies focus/contrast/reduced-motion tokens without theme infrastructure.
- [ ] **1F.4 (2–5 min): Run GREEN aggregate gates.** Run \`& $npm ci; & $npm run typecheck; & $npm run lint; & $npm run test:coverage\`. Expected: PASS and each Task 1 product module branch-aware coverage >=90%.
- [ ] **1F.5 (2–5 min): Commit Task 1.** Add only the listed UI/auth/service/tests and commit \`feat(STM32TK-0502): add secure monitor UI foundation\`.

### Task 2: Probe, Catalog, Shallow Selection, and User Groups

**Files:**

- Create: \`tools/stm32-monitor/ui/src/catalog/shallow-selectors.ts\`
- Create: \`tools/stm32-monitor/ui/src/components/IdentityBar.tsx\`, \`ProbePanel.tsx\`, \`CatalogPanel.tsx\`, \`GroupPanel.tsx\`
- Create: \`tools/stm32-monitor/ui/tests/probe-catalog.test.tsx\`, \`group-panel.test.tsx\`
- Modify: \`tools/stm32-monitor/ui/src/api/client.ts\`, \`src/state/model.ts\`, \`reducer.ts\`, \`selectors.ts\`, \`app.tsx\`, \`styles.css\`

**Interfaces:**

- Consumes Task 1 \`MonitorClient\`, \`MonitorAction\`, and state selectors.
- Produces \`deriveShallowSelectors(d:CatalogDescriptor,choice:{kind:"member";name:string}|{kind:"index";index:number}):readonly WatchItem[]\`. A derived selector retains only descriptor metadata already present; because the public descriptor has no child type field, every derived child uses \`typeName:"unknown"\` and is validated by the backend.
- Produces \`toGroupImportDocument(groups:readonly WatchGroup[]):{schemaVersion:1;groups:readonly GroupTransfer[]}\`.
- Produces panel callback signatures \`onConnect(probeId:string):Promise<void>\`, \`onGroupSave(change:GroupChange):Promise<void>\`, and \`onCatalogAdd(item:WatchItem):void\`.

Every Task 2 unit below is a complete five-step TDD loop. Run all commands from
\`tools/stm32-monitor/ui\` with the resolved absolute \`$npm\`.

#### Task 2A: \`shallow-selectors.ts\`

- [ ] **2A.1 (2–5 min): Write the full failing one-hop selector tests.** Add this exact base case to \`tests/probe-catalog.test.tsx\`, then add member-not-declared, negative/fractional/out-of-range index, \`N<=256\` materialization, \`N>256\` bounded-input, and no pointer/address/recursive-selector cases. Assert every derived child has \`typeName:"unknown"\`; the selector may preserve existing descriptor fields but may not construct or copy a parent type as a child type.

\`\`\`ts
it("derives one declared member and rejects an out-of-range index", () => {
  const member: CatalogDescriptor = {
    selector: "state", kind: "variable", typeName: "State", memberNames: ["rpm"]
  };
  const array: CatalogDescriptor = {
    selector: "samples", kind: "variable", typeName: "uint16_t[257]", elementCount: 257
  };
  expect(deriveShallowSelectors(member, {kind: "member", name: "rpm"}))
    .toEqual([{selector: "state.rpm", kind: "variable", typeName: "unknown"}]);
  expect(deriveShallowSelectors(array, {kind: "index", index: 257})).toEqual([]);
});
\`\`\`

- [ ] **2A.2 (2–5 min): Run RED.** Run \`& $npm run test -- probe-catalog -t "derives one declared"\`. Expected: FAIL because \`deriveShallowSelectors\` is absent.
- [ ] **2A.3 (2–5 min): Implement exactly the tested shallow derivation.** Create \`src/catalog/shallow-selectors.ts\` with the guards shown here plus bounded \`N<=256\` enumeration/\`N>256\` index-input helpers; do not recurse, parse pointers, infer offsets, copy the parent type, or synthesize a member type:

\`\`\`ts
export function deriveShallowSelectors(
  descriptor: CatalogDescriptor,
  choice: {kind:"member";name:string}|{kind:"index";index:number}
): readonly WatchItem[] {
  if (choice.kind === "member") {
    if (!descriptor.memberNames?.includes(choice.name)) return [];
    return [{selector:`${descriptor.selector}.${choice.name}`,kind:descriptor.kind,
      typeName:"unknown"}];
  }
  if (!Number.isInteger(choice.index) || choice.index < 0 ||
      descriptor.elementCount === undefined || choice.index >= descriptor.elementCount) return [];
  return [{selector:`${descriptor.selector}[${choice.index}]`,kind:descriptor.kind,
    typeName:"unknown"}];
}
\`\`\`

- [ ] **2A.4 (2–5 min): Run GREEN and typecheck.** Run \`& $npm run test -- probe-catalog -t "shallow|declared|bounded"; & $npm run typecheck\`. Expected: all selector cases PASS and no asserted child type differs from \`"unknown"\`.
- [ ] **2A.5 (2–5 min): Commit the shallow-selector unit.** Run \`git add tools/stm32-monitor/ui/src/catalog/shallow-selectors.ts tools/stm32-monitor/ui/tests/probe-catalog.test.tsx\` and commit \`feat(STM32TK-0502): derive backend-validated shallow selectors\`.

#### Task 2B: \`IdentityBar.tsx\`

- [ ] **2B.1 (2–5 min): Write the failing identity-only tests.** Render \`IdentityBar\` independently and assert project name, target device, dirty/clean state, short and full Git HEAD/build ID/ELF digest, copy actions carrying the full values, and explicit stale/unavailable copy when firmware is null.

\`\`\`tsx
it("shows and copies only authoritative identity", async () => {
  render(<IdentityBar project={project} firmware={firmware} onCopy={copy}/>);
  expect(screen.getByText(project.name)).toBeVisible();
  expect(screen.getByText(project.gitHead)).toBeVisible();
  await user.click(screen.getByRole("button", {name:"Copy full Git HEAD"}));
  expect(copy).toHaveBeenCalledWith(project.gitHead);
});
\`\`\`

- [ ] **2B.2 (2–5 min): Run RED.** Run \`& $npm run test -- probe-catalog -t "authoritative identity"\`. Expected: FAIL because \`IdentityBar\` is absent.
- [ ] **2B.3 (2–5 min): Implement exactly the tested identity rendering and copy callbacks.** Use authoritative props only; expose the full values through labeled output/copy buttons, render fixed unavailable/stale text when firmware is null, and never infer a target, build, or digest.
- [ ] **2B.4 (2–5 min): Run GREEN and accessibility checks.** Run \`& $npm run test -- probe-catalog -t "authoritative identity"; & $npm run typecheck; & $npm run test:a11y\`. Expected: PASS.
- [ ] **2B.5 (2–5 min): Commit the identity unit.** Run \`git add tools/stm32-monitor/ui/src/components/IdentityBar.tsx tools/stm32-monitor/ui/tests/probe-catalog.test.tsx\` and commit \`feat(STM32TK-0502): render authoritative monitor identity\`.

#### Task 2C: \`ProbePanel.tsx\`

- [ ] **2C.1 (2–5 min): Write the failing probe-only action tests.** Render \`ProbePanel\` without \`IdentityBar\`; assert list refresh, explicit Connect/Reconnect/Release callbacks, reconnect disabled before prior success, release disabled while disconnected, BUSY/LOST exact-reason copy, no steal/force control, and zero callbacks before a user click.
- [ ] **2C.2 (2–5 min): Run RED.** Run \`& $npm run test -- probe-catalog -t "explicit probe actions"\`. Expected: FAIL because \`ProbePanel\` is absent.
- [ ] **2C.3 (2–5 min): Implement exactly the independently tested probe controls.** The minimum action surface is:

\`\`\`tsx
export function ProbePanel(p: ProbePanelProps): JSX.Element {
  return <section aria-label="Probes">
    <button onClick={() => void p.onRefresh()}>Refresh probes</button>
    {p.probes.map(probe => <button key={probe.probeId}
      onClick={() => void p.onConnect(probe.probeId)}>Connect {probe.product}</button>)}
    <button disabled={!p.canReconnect} onClick={() => void p.onReconnect()}>Reconnect probe</button>
    <button disabled={p.connectedProbeId === null} onClick={() => void p.onRelease()}>Release probe</button>
    {p.leaseReason !== null && <p role="status">{p.leaseReason}</p>}
  </section>;
}
\`\`\`

- [ ] **2C.4 (2–5 min): Run GREEN and accessibility checks.** Run \`& $npm run test -- probe-catalog -t "explicit probe actions"; & $npm run typecheck; & $npm run test:a11y\`. Expected: PASS with zero pre-click callback.
- [ ] **2C.5 (2–5 min): Commit the probe unit.** Run \`git add tools/stm32-monitor/ui/src/components/ProbePanel.tsx tools/stm32-monitor/ui/tests/probe-catalog.test.tsx\` and commit \`feat(STM32TK-0502): add explicit probe controls\`.

#### Task 2D: \`CatalogPanel.tsx\`

- [ ] **2D.1 (2–5 min): Write the full failing catalog tests.** Use fake timers for the exact transport case below, then add rows for scalar/float/enum/member/array, a sampleable register, an unavailable-register explanation, and a per-click access-risk confirmation that calls \`onAdd(item)\` only after Confirm and is never persisted.

\`\`\`tsx
it("normalizes and debounces catalog search while preserving the opaque cursor", async () => {
  vi.useFakeTimers();
  render(<CatalogPanel connected descriptors={[]} nextCursor="opaque-2"
    onSearch={search} onNext={next} onAdd={add}/>);
  await user.type(screen.getByLabelText("Variable or register search"), "e\u0301");
  await vi.advanceTimersByTimeAsync(299);
  expect(search).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  expect(search).toHaveBeenCalledWith("é", undefined, 100);
  await user.click(screen.getByRole("button", {name:"Next catalog page"}));
  expect(next).toHaveBeenCalledWith("opaque-2");
});
\`\`\`

- [ ] **2D.2 (2–5 min): Run RED.** Run \`& $npm run test -- probe-catalog -t "normalizes and debounces|catalog rows|access risk"\`. Expected: FAIL because \`CatalogPanel\` is absent.
- [ ] **2D.3 (2–5 min): Implement exactly the tested query, rendering, and current-click confirmation.** Store NFC text capped at 128 code units, clear the prior timeout on change/unmount, invoke \`onSearch(normalized,undefined,100)\` at 300 ms, pass only the supplied cursor to \`onNext\`, keep search disabled while disconnected, render only descriptor facts, and discard risk confirmation state after the current add decision.
- [ ] **2D.4 (2–5 min): Run GREEN, typecheck, and axe.** Run \`& $npm run test -- probe-catalog; & $npm run typecheck; & $npm run test:a11y\`. Expected: PASS.
- [ ] **2D.5 (2–5 min): Commit the catalog unit.** Run \`git add tools/stm32-monitor/ui/src/components/CatalogPanel.tsx tools/stm32-monitor/ui/tests/probe-catalog.test.tsx\` and commit \`feat(STM32TK-0502): add bounded catalog workflows\`.

#### Task 2E: \`GroupPanel.tsx\` delete confirmation and editor

- [ ] **2E.1 (2–5 min): Write the full failing group-panel tests.** Add the rendered Delete→pending dialog→Confirm case below, plus zero-group copy, create/import confirmations, ordinary save without a second confirmation but with \`authorized:true\`, interval 100–5000, CAS-conflict refresh/re-decision, dialog focus/trigger restoration/Escape, and input retention on public API failure.

\`\`\`tsx
it("deletes only after Delete then pending dialog then Confirm", async () => {
  render(<GroupPanel groups={[group]} onDelete={remove} onSave={save}
    onImport={importGroups} onExport={exportGroups}/>);
  await user.click(screen.getByRole("button", {name:`Delete ${group.name}`}));
  expect(remove).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog", {name:"Confirm group deletion"})).toBeVisible();
  await user.click(screen.getByRole("button", {name:"Confirm delete"}));
  expect(remove).toHaveBeenCalledWith(group.groupId,
    {expectedRevision:group.revision,authorized:true});
});
\`\`\`

- [ ] **2E.2 (2–5 min): Run RED.** Run \`& $npm run test -- group-panel -t "Delete then pending|group editor|conflict"\`. Expected: FAIL because \`GroupPanel\` is absent.
- [ ] **2E.3 (2–5 min): Implement exactly the tested editor and confirmation state.** Use the deletion shape below, add the tested create/import/save/CAS paths, keep 100–5000 validation and panel input local, and perform focus entry/restoration/Escape without creating any default group:

\`\`\`tsx
export function GroupPanel(props: GroupPanelProps): JSX.Element {
  const [pendingDelete,setPendingDelete]=useState<WatchGroup|null>(null);
  return <section aria-label="User monitor groups">
    {props.groups.length === 0 && <p>No user monitor groups</p>}
    {props.groups.map(group => <button key={group.groupId}
      onClick={() => setPendingDelete(group)}>Delete {group.name}</button>)}
    {pendingDelete !== null && <div role="dialog" aria-label="Confirm group deletion">
      <button onClick={() => { const group=pendingDelete; setPendingDelete(null);
        void props.onDelete(group.groupId,{expectedRevision:group.revision,authorized:true}); }}>
        Confirm delete
      </button>
      <button onClick={() => setPendingDelete(null)}>Cancel</button>
    </div>}
  </section>;
}
\`\`\`

- [ ] **2E.4 (2–5 min): Run GREEN, typecheck, and axe.** Run \`& $npm run test -- group-panel; & $npm run typecheck; & $npm run test:a11y\`. Expected: PASS.
- [ ] **2E.5 (2–5 min): Commit the group-panel unit.** Run \`git add tools/stm32-monitor/ui/src/components/GroupPanel.tsx tools/stm32-monitor/ui/tests/group-panel.test.tsx\` and commit \`feat(STM32TK-0502): add user-owned monitor groups\`.

#### Task 2F: group transfer and \`app.tsx\` wiring

- [ ] **2F.1 (2–5 min): Write the full failing schema and callback tests.** Assert \`toGroupImportDocument([group])\` equals only \`{schemaVersion:1,groups:[{name,description,intervalMs,items}]}\`, a user-clicked Blob export strips IDs/revisions/timestamps, import preview reports exact group/item/conflict counts before confirmation, and Probe/Group/Catalog callbacks each call the corresponding \`MonitorClient\` method once and dispatch its typed action.
- [ ] **2F.2 (2–5 min): Run RED.** Run \`& $npm run test -- group-panel probe-catalog -t "schema|callback|preview"\`. Expected: FAIL because transfer and app wiring are absent.
- [ ] **2F.3 (2–5 min): Implement exactly the tested pure transfer and callback composition.** Strip \`groupId\`, revision, and timestamps; create a Blob only from the clicked export; show the tested preview before \`authorized:true\`; keep \`client.ts\` the only transport constructor.
- [ ] **2F.4 (2–5 min): Run GREEN, typecheck, and accessibility gates.** Run \`& $npm run test -- group-panel probe-catalog; & $npm run typecheck; & $npm run test:a11y\`. Expected: PASS.
- [ ] **2F.5 (2–5 min): Commit the wiring unit.** Run \`git add tools/stm32-monitor/ui/src/app.tsx tools/stm32-monitor/ui/src/state tools/stm32-monitor/ui/src/api/client.ts tools/stm32-monitor/ui/tests\` and commit \`feat(STM32TK-0502): wire probe catalog and group workflows\`.

### Task 3: Sampling, Typed Table, Compact Quality, Chart, and DataZoom

**Files:**

- Create: \`tools/stm32-monitor/ui/src/chart/echarts.ts\`, \`series.ts\`, \`zoom.ts\`
- Create: \`tools/stm32-monitor/ui/src/components/LiveTable.tsx\`, \`LiveChart.tsx\`, \`ChartZoomControls.tsx\`, \`StatusStrip.tsx\`, \`NoticeRegion.tsx\`
- Create: \`tools/stm32-monitor/ui/tests/live-monitor.test.tsx\`, \`chart.test.ts\`, \`zoom.test.tsx\`
- Modify: \`tools/stm32-monitor/ui/src/api/client.ts\`, \`live.ts\`, \`src/state/model.ts\`, \`reducer.ts\`, \`selectors.ts\`, \`app.tsx\`, \`styles.css\`

**Interfaces:**

- Consumes Task 1 sampling methods/live actions and Task 2 selected group.
- Produces \`appendSample(state:LiveState,sample:SampleEvent):LiveState\`.
- Produces \`chartSeries(state:LiveState,selected:readonly string[]):readonly SeriesOption[]\`.
- Produces \`type ZoomRange={start:number;end:number}\`, \`type ZoomAction={type:"zoom.in"}|{type:"zoom.out"}|{type:"zoom.reset"}|{type:"zoom.set";start:number;end:number}\`, and \`zoomReducer(range:ZoomRange,action:ZoomAction):ZoomRange\`.
- Produces \`register([LineChart,GridComponent,TooltipComponent,LegendComponent,DatasetComponent,DataZoomComponent,CanvasRenderer])\` and no aggregate ECharts import.
- Produces \`ChartZoomControls({range,onAction}:{range:ZoomRange;onAction:(a:ZoomAction)=>void})\`.

Every Task 3 unit is a five-step TDD loop from \`tools/stm32-monitor/ui\`.

#### Task 3A: \`series.ts\` and \`LiveTable.tsx\`

- [ ] **3A.1 (2–5 min): Write the full failing table/series tests.** Feed one ERROR value and one finite numeric OK value through \`appendSample\`; assert sibling isolation and numeric projection. Also cover enum/string/object/array/unknown shape, NaN/infinity exclusion, one-level expansion, gap/error/reset trend clearing, 256-row/group-order bounds, and DOM without \`innerHTML\`.
- [ ] **3A.2 (2–5 min): Run RED.** Run \`& $npm run test -- live-monitor chart -t "isolates one item error"\`. Expected: FAIL because the modules are absent.
- [ ] **3A.3 (2–5 min): Implement exactly the tested immutable row update and finite-number projection.** Key rows by group order, cap at 256, preserve rawHex/capturedNs/code, render other JSON as bounded escaped one-level text, exclude non-finite numbers, and reset trend unless the adjacent value has the same binding/run and no discontinuity.
- [ ] **3A.4 (2–5 min): Run GREEN and typecheck.** Repeat 3A.2, then run \`& $npm run typecheck\`. Expected: PASS.
- [ ] **3A.5 (2–5 min): Commit the table/series unit.** Run \`git add tools/stm32-monitor/ui/src/chart/series.ts tools/stm32-monitor/ui/src/components/LiveTable.tsx tools/stm32-monitor/ui/tests/live-monitor.test.tsx tools/stm32-monitor/ui/tests/chart.test.ts\` and commit \`feat(STM32TK-0502): add bounded typed live rows\`.

#### Task 3B: \`echarts.ts\`, bounded series, and \`LiveChart.tsx\`

- [ ] **3B.1 (2–5 min): Write the full failing chart tests.** Assert the registered module list is exactly Line/Grid/Tooltip/Legend/Dataset/DataZoom/Canvas, \`connectNulls:false\`, inside+slider DataZoom, an 8-series/600-point cap, and null gap point. With fake timers also prove at most one \`setOption\` per 100 ms, bounded queue depth, and unchanged server drop totals.
- [ ] **3B.2 (2–5 min): Run RED.** Run \`& $npm run test -- chart -t "registered module list"\`. Expected: FAIL because chart modules are absent.
- [ ] **3B.3 (2–5 min): Implement exactly the tested ECharts imports, option builder, and coalescer.** Never import the \`echarts\` aggregate entry; schedule one animation-frame flush, refuse a second \`setOption\` within 100 ms, cap queued state, and never mutate server drop totals.
- [ ] **3B.4 (2–5 min): Run GREEN and typecheck.** Repeat 3B.2 and run \`& $npm run typecheck\`. Expected: PASS.
- [ ] **3B.5 (2–5 min): Commit the chart unit.** Run \`git add tools/stm32-monitor/ui/src/chart/echarts.ts tools/stm32-monitor/ui/src/components/LiveChart.tsx tools/stm32-monitor/ui/tests/chart.test.ts\` and commit \`feat(STM32TK-0502): render bounded modular charts\`.

#### Task 3C: \`zoom.ts\` and \`ChartZoomControls.tsx\`

- [ ] **3C.1 (2–5 min): Write the full failing zoom tests.** Render range 25–75, click \`Reset chart zoom\`, press \`+\`, \`-\`, and \`0\`, and assert typed actions plus visible \`25–75%\` text; also assert pointer/touch options, reset at 200% page zoom, clamping, and \`zoom.reset\` on gap/binding epoch/run ID/authoritative binding changes.
- [ ] **3C.2 (2–5 min): Run RED.** Run \`& $npm run test -- zoom -t "reset/control"\`. Expected: FAIL because controls are absent.
- [ ] **3C.3 (2–5 min): Implement exactly the tested zoom reducer, controls, and continuity resets.** Add focusable Zoom In/Out/Reset buttons and keyboard handler; clamp 0–100, preserve an ordered nonzero range, keep Reset reachable, configure pointer/touch dataZoom, and dispatch reset for every tested discontinuity.
- [ ] **3C.4 (2–5 min): Run GREEN, typecheck, and axe.** Run \`& $npm run test -- zoom; & $npm run typecheck; & $npm run test:a11y\`. Expected: PASS.
- [ ] **3C.5 (2–5 min): Commit the zoom unit.** Run \`git add tools/stm32-monitor/ui/src/chart/zoom.ts tools/stm32-monitor/ui/src/components/ChartZoomControls.tsx tools/stm32-monitor/ui/tests/zoom.test.tsx tools/stm32-monitor/ui/tests/chart.test.ts\` and commit \`feat(STM32TK-0502): add recoverable chart zoom\`.

#### Task 3D: \`StatusStrip.tsx\` and \`NoticeRegion.tsx\`

- [ ] **3D.1 (2–5 min): Write the full failing status/notice tests.** Render actualRateHz, latencyNs, and exact subscriber/history/deadline/service totals; increase one total and assert one deduplicated polite notice. Add authoritative stale/reset/gap/lease-code copy cases and assert no physical-reset claim, steal/auto-resume action, timeline, distribution, or per-stage dashboard.
- [ ] **3D.2 (2–5 min): Run RED.** Run \`& $npm run test -- live-monitor -t "compact-status"\`. Expected: FAIL because status components are absent.
- [ ] **3D.3 (2–5 min): Implement exactly the tested prop-only status and notice components.** Render current compact values; use \`aria-live="polite"\`, deduplicate each increment, expose blocking public-code failures with \`role="alert"\`, and map only the tested authoritative discontinuity/lease codes to bounded copy.
- [ ] **3D.4 (2–5 min): Run GREEN and axe.** Repeat 3D.2 and run \`& $npm run test:a11y\`. Expected: PASS.
- [ ] **3D.5 (2–5 min): Commit the compact-status unit.** Run \`git add tools/stm32-monitor/ui/src/components/StatusStrip.tsx tools/stm32-monitor/ui/src/components/NoticeRegion.tsx tools/stm32-monitor/ui/tests/live-monitor.test.tsx\` and commit \`feat(STM32TK-0502): expose compact monitor status\`.

#### Task 3E: sampling controls, live reconnect, reducer, and \`app.tsx\`

- [ ] **3E.1 (2–5 min): Write the failing exact-action test.** Assert Start is enabled only for connected/current-revision/nonempty group/100..5000, sends \`{groupId,expectedRevision}\`; Pause/Resume/Stop send no body; a 35-second heartbeat timeout marks transport stale; reconnect delays are 0.5/1/2/4/8 seconds and never call probe reconnect/start.
- [ ] **3E.2 (2–5 min): Run RED.** Run \`& $npm run test -- live-monitor -t "exact-action"\`. Expected: FAIL at missing controls/reconnect policy.
- [ ] **3E.3 (2–5 min): Implement the matching buttons, Task 1 client calls, live timer/backoff, and reducer dispatches.** Reset continuity on gap/binding/run, retain last values as stale, refresh status after gap, and never synthesize samples.
- [ ] **3E.4 (2–5 min): Run GREEN and aggregate gates.** Run \`& $npm run typecheck; & $npm run test -- live-monitor chart zoom; & $npm run test:a11y; & $npm run build\`. Expected: PASS.
- [ ] **3E.5 (2–5 min): Commit Task 3.** Add only Task 3 source/tests and commit \`feat(STM32TK-0502): add live monitor chart and controls\`.

### Task 4: Paged History and Verified CSV/JSONL

**Files:**

- Create: \`tools/stm32-monitor/ui/src/components/HistoryPanel.tsx\`, \`ExportPanel.tsx\`
- Create: \`tools/stm32-monitor/ui/tests/history-export.test.tsx\`
- Modify: \`tools/stm32-monitor/ui/src/api/client.ts\`, \`src/state/model.ts\`, \`reducer.ts\`, \`selectors.ts\`, \`app.tsx\`, \`styles.css\`

**Interfaces:**

- Consumes Task 1 history/export methods and Task 3 selected chart series.
- Produces \`flattenHistory(page:HistoryPage):readonly HistoryRow[]\` retaining binding/startOrdinal/valueOrdinal.
- Produces \`HistoryPanel({query,onLoad,onPage}:{query:HistoryQuery;onLoad:(q:HistoryQuery)=>Promise<void>;onPage:(cursor?:string)=>Promise<void>})\`.
- Produces \`ExportPanel({onCreate,onDownload}:{onCreate:(r:ExportRequest)=>Promise<void>;onDownload:(id:string)=>Promise<void>})\`.

Every Task 4 unit is a complete five-step loop run from \`tools/stm32-monitor/ui\`.

#### Task 4A: history flattening and query construction

- [ ] **4A.1 (2–5 min): Write the full failing flatten/query tests.** Build one \`HistoryPage\` with \`startOrdinal:4\` and two values and assert exact rows/binding. Also require startNs/endNs, clamp limit to 10,000, include only current group/run/selector filters, preserve an opaque cursor, and reject fetch-all/cross-session/comparison fields.
- [ ] **4A.2 (2–5 min): Run RED.** Run \`& $npm run test -- history-export -t "ordinal"\`. Expected: FAIL because \`flattenHistory\` is absent.
- [ ] **4A.3 (2–5 min): Implement exactly the tested pure flattener and query builder.** Map each slice/value to \`{binding,startOrdinal,valueOrdinal:startOrdinal+index,value}\`; validate the bounded allowlisted query fields and do not merge slices, synthesize gaps, mutate input, or add a session/comparison field.
- [ ] **4A.4 (2–5 min): Run GREEN and typecheck.** Run \`& $npm run test -- history-export -t "ordinal"; & $npm run typecheck\`. Expected: PASS.
- [ ] **4A.5 (2–5 min): Commit the history-data unit.** Run \`git add tools/stm32-monitor/ui/src/state/selectors.ts tools/stm32-monitor/ui/src/api/client.ts tools/stm32-monitor/ui/tests/history-export.test.tsx\` and commit \`feat(STM32TK-0502): flatten bounded monitor history\`.

#### Task 4B: \`HistoryPanel.tsx\` cursor actions

- [ ] **4B.1 (2–5 min): Write the full failing history-panel tests.** The base case below exercises the rendered current \`nextCursor\`; also assert first-page Previous disabled, a two-page in-memory back stack, refresh clearing memory, retained input/public code on failure, raw paged table, chart <=8×600, and no automatic next/fetch-all.

\`\`\`tsx
it("Next passes the server cursor to onPage and Previous uses visited memory only", async () => {
  render(<HistoryPanel query={query} page={{slices:[],nextCursor:"cursor-2"}}
    onLoad={load} onPage={page}/>);
  expect(screen.getByRole("button", {name:"Previous history page"})).toBeDisabled();
  await user.click(screen.getByRole("button", {name:"Next history page"}));
  expect(page).toHaveBeenCalledWith("cursor-2");
});
\`\`\`

- [ ] **4B.2 (2–5 min): Run RED.** Run \`& $npm run test -- history-export -t "Next passes"\`. Expected: FAIL because \`HistoryPanel\` has no Next/cursor action.
- [ ] **4B.3 (2–5 min): Implement exactly the tested page controls, table/chart bounds, and in-memory cursor stack.** Use this component shape, clear visited cursors on refresh/query identity change, retain form input on public failure, and never schedule an automatic page:

\`\`\`tsx
export function HistoryPanel({query,page,onLoad,onPage}:HistoryPanelProps):JSX.Element {
  const [visited,setVisited]=useState<readonly (string|undefined)[]>([]);
  const next=page?.nextCursor ?? null;
  const goNext=():void => { if (next===null) return; setVisited(v=>[...v,query.cursor]); void onPage(next); };
  const goPrevious=():void => { const prior=visited.at(-1); if (visited.length===0) return;
    setVisited(v=>v.slice(0,-1)); void onPage(prior); };
  return <section aria-label="History">
    <button onClick={() => void onLoad({...query,limit:Math.min(query.limit ?? 10000,10000)})}>Load history</button>
    <button disabled={visited.length===0} onClick={goPrevious}>Previous history page</button>
    <button disabled={next===null} onClick={goNext}>Next history page</button>
  </section>;
}
\`\`\`

- [ ] **4B.4 (2–5 min): Run GREEN and typecheck.** Run \`& $npm run test -- history-export -t "Next passes"; & $npm run typecheck\`. Expected: PASS.
- [ ] **4B.5 (2–5 min): Commit the history-panel unit.** Run \`git add tools/stm32-monitor/ui/src/components/HistoryPanel.tsx tools/stm32-monitor/ui/tests/history-export.test.tsx\` and commit \`feat(STM32TK-0502): page basic monitor history\`.

#### Task 4C: \`ExportPanel.tsx\` and export client calls

- [ ] **4C.1 (2–5 min): Write the full failing export-panel tests.** Click Create CSV and assert confirmation precedes \`onCreate({startNs,endNs,format:"csv",authorized:true})\`; provide a verified artifact and assert Download calls \`onDownload("export-1")\`. Add JSONL, quota/oversize/public-error input retention, no path/filename/Range controls, and no AI snapshot/session label cases.
- [ ] **4C.2 (2–5 min): Run RED.** Run \`& $npm run test -- history-export -t "verified-download"\`. Expected: FAIL because \`ExportPanel\` is absent.
- [ ] **4C.3 (2–5 min): Implement exactly the tested CSV/JSONL confirmation, public-error retention, and verified enablement.** Do not expose filename/path/Range inputs or AI labels; call exact create/status/download routes, keep Download disabled until \`verified===true\`, and mount both panels through \`app.tsx\`.
- [ ] **4C.4 (2–5 min): Run GREEN and typecheck.** Run \`& $npm run test -- history-export -t "verified-download"; & $npm run typecheck\`. Expected: PASS.
- [ ] **4C.5 (2–5 min): Commit the verified-export unit.** Run \`git add tools/stm32-monitor/ui/src/components/ExportPanel.tsx tools/stm32-monitor/ui/src/app.tsx tools/stm32-monitor/ui/tests/history-export.test.tsx\` and commit \`feat(STM32TK-0502): add verified monitor exports\`.

### Task 5: Static Allowlist, CSP, and Reproducible Wheel Assets

**Files:**

- Create: \`tools/stm32-monitor/src/stm32_monitor/ui_assets.py\`, \`tests/test_ui_assets.py\`, \`tests/test_ui_dist.py\`
- Create/update from build: \`tools/stm32-monitor/src/stm32_monitor/ui_dist/index.html\`, \`.vite/manifest.json\`, \`assets/*\`
- Modify: \`tools/stm32-monitor/src/stm32_monitor/service.py\`, \`pyproject.toml\`, \`tests/test_service.py\`, \`tests/test_package_boundary.py\`, \`ui/package.json\`

**Interfaces:**

- Produces \`UiAssets.load()->UiAssets\`, \`UiAssets.response(route:str,port:int)->web.Response\`, and \`UiAssets.verify_tree()->UiAssetInventory\`.
- Consumes only package resources and manifest-listed exact routes. \`/\` maps index; \`/assets/<manifest filename>\` maps one exact file; no other SPA fallback exists.
- Service static authorization consumes peer/exact Host/header budget/optional Origin, independent of API token authentication.

#### Task 5A: \`ui_assets.py\` exact allowlist

- [ ] **5A.1 (2–5 min): Write the full failing allowlist/traversal tests.** Assert \`UiAssets.load().response("/assets/../auth.py",43125)\` is a fixed 404 with empty text; add encoded traversal, unknown route, no listing/SPA/API fallback, exact MIME/ETag, index no-store, hashed immutable cache, exact-port CSP with no unsafe/remote/data/blob, and HEAD-parity cases. Do not include size-limit assertions in this unit.
- [ ] **5A.2 (2–5 min): Run RED.** From \`tools/stm32-monitor\`, run \`& $python312 -m pytest tests/test_ui_assets.py::test_traversal_is_fixed_non_reflecting_404 tests/test_ui_assets.py -k "allowlist or headers or head" -q\`. Expected: FAIL because \`UiAssets.response\` is absent.
- [ ] **5A.3 (2–5 min): Implement exactly the tested package-resource allowlist and response lookup.** Load manifest-listed routes into an immutable dictionary; use \`self.entries.get(route)\`; unknown/decoded traversal never becomes a filesystem path and returns \`web.Response(status=404,text="")\`; add only the tested MIME/ETag/cache/CSP/HEAD behavior.
- [ ] **5A.4 (2–5 min): Run GREEN.** Repeat 5A.2. Expected: PASS with no size-limit test selected.
- [ ] **5A.5 (2–5 min): Commit the allowlist/traversal unit.** Run \`git add tools/stm32-monitor/src/stm32_monitor/ui_assets.py tools/stm32-monitor/tests/test_ui_assets.py\` and commit \`feat(STM32TK-0502): allowlist bundled UI routes\`.

#### Task 5B: \`UiAssets.verify_tree()\` size limits

- [ ] **5B.1 (2–5 min): Write the independent failing tree-limit tests.** Build package-resource fixtures at each boundary and one byte over; assert index and manifest <=256 KiB, each asset <=4 MiB, total UI bytes <=8 MiB, and missing/invalid manifest, unlisted file, duplicate route, or oversize tree rejects service startup. Do not exercise traversal routes in this unit.
- [ ] **5B.2 (2–5 min): Run RED.** From \`tools/stm32-monitor\`, run \`& $python312 -m pytest tests/test_ui_assets.py::test_static_limits tests/test_ui_assets.py -k "tree or manifest or oversize" -q\`. Expected: FAIL because \`verify_tree()\` is absent.
- [ ] **5B.3 (2–5 min): Implement exactly the tested inventory verification.** Read each package resource once, count raw bytes with checked addition, reject before response routing, and return \`UiAssetInventory\` only when manifest membership and all three size ceilings pass.
- [ ] **5B.4 (2–5 min): Run GREEN.** Repeat 5B.2. Expected: PASS while the independent traversal selector remains excluded.
- [ ] **5B.5 (2–5 min): Commit the tree-limit unit.** Run \`git add tools/stm32-monitor/src/stm32_monitor/ui_assets.py tools/stm32-monitor/tests/test_ui_assets.py\` and commit \`feat(STM32TK-0502): bound bundled UI inventory\`.

#### Task 5C: \`service.py\` static routes and request boundary

- [ ] **5C.1 (2–5 min): Write the failing real-service matrix.** Assert unauthenticated static GET/HEAD succeeds only for IPv4 peer, exact bound Host, header budget, and absent/exact Origin; wrong peer/Host/Origin fail; every API remains authenticated.
- [ ] **5C.2 (2–5 min): Run RED.** Run \`& $python312 -m pytest tests/test_service.py -k "static" -q\`. Expected: FAIL because routes are absent.
- [ ] **5C.3 (2–5 min): Implement exactly the tested static boundary.** Add only \`/\` and exact manifest asset handlers before the API wildcard, pass normalized request evidence to \`UiAssets\`, and never use \`add_static\` or concatenate a path.
- [ ] **5C.4 (2–5 min): Run GREEN with auth and compile gates.** Run \`& $python312 -m pytest tests/test_service.py tests/test_auth.py -q; & $python312 -m compileall -q src/stm32_monitor\` with external \`PYTHONPYCACHEPREFIX\`. Expected: PASS and no repository writes.
- [ ] **5C.5 (2–5 min): Commit the service-route unit.** Run \`git add tools/stm32-monitor/src/stm32_monitor/service.py tools/stm32-monitor/tests/test_service.py\` and commit \`feat(STM32TK-0502): serve UI through the monitor listener\`.

#### Task 5D: reproducible \`ui_dist\` and wheel package data

- [ ] **5D.1 (2–5 min): Write failing dist/package tests.** Assert production output has no source map/remote URL/worker/inline/eval/\`new Function\`/aggregate ECharts, satisfies gzip/total limits, is in wheel RECORD, and Python wheel build has no Node invocation.
- [ ] **5D.2 (2–5 min): Run RED.** From UI run \`& $npm run verify:dist\`; from repository root run \`& $python312 -m pytest tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/tests/test_package_boundary.py -q\`. Expected: FAIL before dist/package-data integration.
- [ ] **5D.3 (2–5 min): Implement exactly the tested deterministic Vite output and package data.** \`verify:dist\` builds into a fresh external temp directory and byte-compares every relative file against committed \`ui_dist\`; setuptools names every required package resource.
- [ ] **5D.4 (2–5 min): Run GREEN twice.** Run \`& $npm run build; & $npm run verify:dist; & $npm run verify:dist\`, then the exact Python tests from 5D.2. Expected: PASS and unchanged Git status.
- [ ] **5D.5 (2–5 min): Commit the reproducible-dist unit.** Add only UI dist/config, package metadata, and named tests; commit \`feat(STM32TK-0502): package reproducible monitor UI assets\`.

### Task 6: Explicit Launcher, Managed Runtime, Plugin, Active Skill, and 0.5.0

**Files:**

- Create: \`bin/stm32-monitor.cmd\`, \`skills/stm32-monitor/SKILL.md\`, \`tools/stm32-monitor/tests/test_launcher.py\`
- Modify: \`tools/stm32-monitor/src/stm32_monitor/cli.py\`, \`tests/test_cli.py\`, \`bin/setup-stm32-env.ps1\`
- Modify: \`bin/stm32-toolkit-mcp.cmd\`, \`tools/stm32-monitor/src/stm32_monitor/runtime.py\`, \`tools/stm32-monitor/tests/test_runtime.py\`, both \`pyproject.toml\`, both package \`__init__.py\`, Toolkit CLI, Monitor protocol, plugin manifest/marketplace, README files, \`skills/setup-stm32-env/SKILL.md\`, \`tools/stm32-toolkit/tests/test_plugin_layout.py\`
- Read only: \`requirements/follow-on-skills/stm32-monitor/SKILL.md\`; do not replace, delete, or modify it.

**Interfaces:**

- Existing \`serve --project ... --data-root ... --session-id ... --json\` is byte-compatible and opener count zero.
- Produces \`open --project ... --data-root ... [--session-id ...]\`.
- Produces \`main(argv:Sequence[str]|None=None, *, _runtime_factory:Callable[[],object]=MonitorRuntime, _stdout:TextIO=sys.stdout, _stderr:TextIO=sys.stderr, _browser_open:Callable[[str],bool]=webbrowser.open)->int\`.
- CMD invokes only \`CLAUDE_PLUGIN_DATA/runtime/0.5.0/Scripts/python.exe\`; no ambient python/py/uv fallback.

#### Task 6A: human \`open\` and machine \`serve --json\`

- [ ] **6A.1 (2–5 min): Write the full failing CLI launcher tests.** Inject \`FakeRuntime\` and \`Mock(return_value=True)\`; assert \`open\` starts first, calls opener exactly once with the runtime access URL, prints no URL/token, waits foreground, and \`serve --json\` calls opener zero times. Assert omitted session creates exactly \`monitor-\` plus 32 lowercase hex digits, passes it to one owned runtime, never persists it, and leaves only the token digest in the runtime record.
- [ ] **6A.2 (2–5 min): Run RED.** Run \`& $python312 -m pytest tools/stm32-monitor/tests/test_launcher.py::test_open_starts_then_opens_once_and_never_writes_url -q\`. Expected: FAIL because \`open\` is absent.
- [ ] **6A.3 (2–5 min): Implement exactly the tested \`_open\`, session generation, and unchanged machine path.** On opener failure stop owned runtime and emit one sanitized failure; on KeyboardInterrupt stop it and return 130; preserve existing serve parser/stdout bytes, generate only the tested ephemeral session form, persist no session/token, and never add \`--open-browser\`.
- [ ] **6A.4 (2–5 min): Run GREEN on 3.10 and 3.12.** Run the same node with both \`$python310\` and \`$python312\`; expected PASS.
- [ ] **6A.5 (2–5 min): Commit the CLI launcher unit.** Run \`git add tools/stm32-monitor/src/stm32_monitor/cli.py tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_launcher.py\` and commit \`feat(STM32TK-0502): add explicit monitor open command\`.

#### Task 6B: \`stm32-monitor.cmd\` and runtime cleanup

- [ ] **6B.1 (2–5 min): Write the full failing CMD/runtime tests.** With a fake \`CLAUDE_PLUGIN_DATA\`, assert only \`runtime/0.5.0/Scripts/python.exe\` receives unchanged argv; absent executable returns nonzero and never searches python/py/uv. Also assert cancellation cleanup, opener failure cleanup, Ctrl-C return 130, sanitized error text, no detached process, and no token/access-URL shell interpolation.
- [ ] **6B.2 (2–5 min): Run RED.** Run \`& $python312 -m pytest tools/stm32-monitor/tests/test_launcher.py tools/stm32-monitor/tests/test_runtime.py -k "cmd or cleanup" -q\`. Expected: FAIL.
- [ ] **6B.3 (2–5 min): Implement exactly the tested fixed managed-runtime selection and cleanup paths.** Use only the declared executable, forward argv without interpolation, await the owned process/runtime, sanitize failures, and handle opener failure/Ctrl-C without detaching or retaining a token/access URL.
- [ ] **6B.4 (2–5 min): Run GREEN under both interpreters plus the real CMD help smoke.** Run the complete launcher/CLI/runtime suites with \`$python310\` and \`$python312\`, then run \`& "$env:SystemRoot\System32\cmd.exe" /d /c bin\stm32-monitor.cmd --help\` in the prepared fixture environment. Expected: PASS.
- [ ] **6B.5 (2–5 min): Commit the CMD/runtime unit.** Run \`git add bin/stm32-monitor.cmd tools/stm32-monitor/src/stm32_monitor/runtime.py tools/stm32-monitor/tests/test_launcher.py tools/stm32-monitor/tests/test_runtime.py\` and commit \`feat(STM32TK-0502): bind monitor launcher to managed runtime\`.

#### Task 6C: setup Repair and exact 0.5.0 runtime

- [ ] **6C.1 (2–5 min): Write the full failing setup/promotion tests.** Assert healthy/broken 0.4.0 is classified and quarantined, both exact 0.5.0 wheels plus Toolkit probe extra install atomically, doctor/Monitor CLI/UI manifest/static resource validate, Node/node_modules are absent, rollback restores prior state, and a repository bytes/names/mtime/modes/Git-porcelain snapshot is unchanged outside documented managed-runtime data.
- [ ] **6C.2 (2–5 min): Run RED.** Run \`& $python312 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py -q\`. Expected: FAIL before promotion changes.
- [ ] **6C.3 (2–5 min): Implement exactly the tested atomic 0.5.0 promotion.** Update \`setup-stm32-env.ps1\`, setup Skill, launcher path, and runtime metadata; preserve rollback/quarantine, avoid ambient interpreters, validate both distributions/probe/doctor/Monitor/UI, and write only documented managed-runtime data.
- [ ] **6C.4 (2–5 min): Run GREEN.** Repeat 6C.2 and the Monitor runtime tests; expected PASS.
- [ ] **6C.5 (2–5 min): Commit the managed-runtime promotion unit.** Run \`git add bin/setup-stm32-env.ps1 skills/setup-stm32-env/SKILL.md bin/stm32-toolkit-mcp.cmd tools/stm32-monitor/src/stm32_monitor/runtime.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-monitor/tests/test_runtime.py\` and commit \`feat(STM32TK-0502): promote managed runtime atomically\`.

#### Task 6D: plugin, active Skill, README, and version surfaces

- [ ] **6D.1 (2–5 min): Write failing layout/version tests.** Assert exactly eight release Skills, Monitor Skill requires current project context plus explicit user request, all active surfaces are 0.5.0, README states zero presets/project isolation/0.6 deferrals, and legacy fixed port/direct PyOCD/auto install/AI snapshot text is absent from active surfaces.
- [ ] **6D.2 (2–5 min): Run RED.** Run \`& $python312 -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py -q\`. Expected: FAIL before plugin/version edits.
- [ ] **6D.3 (2–5 min): Update only the listed plugin/marketplace, Skill, README, Python versions/dependency, CLI/protocol, and active version tests.** Keep historical specs/reports and previous-version fixtures unchanged.
- [ ] **6D.4 (2–5 min): Run GREEN and forbidden-surface scan.** Run plugin test and \`rg -n '"version": "0\.4\.0"|__version__ = "0\.4\.0"|version = "0\.4\.0"|runtime/0\.4\.0' bin .claude-plugin skills README.md README_zh-CN.md tools\`; any active hit is FAIL, test-fixture hits are reviewed exceptions.
- [ ] **6D.5 (2–5 min): Commit Task 6.** Add only listed active release surfaces/tests and commit \`feat(STM32TK-0502): promote monitor UI release surfaces\`.

### Task 7: Real aiohttp Fixture, Playwright, axe, Offline, Isolation, Security, and Performance

**Files:**

- Create: \`tools/stm32-monitor/ui/playwright.config.ts\`
- Create: \`tools/stm32-monitor/ui/e2e/fake_runtime.py\`, \`conftest.ts\`, \`monitor.spec.ts\`, \`security.spec.ts\`, \`isolation.spec.ts\`, \`accessibility.spec.ts\`, \`performance.spec.ts\`
- Create: \`tools/stm32-monitor/ui/tests/a11y.test.tsx\`
- Modify: \`tools/stm32-monitor/ui/package.json\`, \`tools/stm32-monitor/tests/test_service.py\`

**Interfaces:**

- \`startMonitor(workspace:string,clock:FakeClock):Promise<MonitorBrowserFixture>\` requires absolute \`STM32_MONITOR_E2E_PYTHON\` and \`STM32_MONITOR_E2E_REPO_ROOT\`, starts real \`MonitorService\` with test-only fake runtime and real HTTP/WS, and rejects readiness unless \`stm32_monitor.__file__\` and \`stm32_toolkit.__file__\` resolve below that repository's two current source roots; fake runtime cannot bypass auth/service.
- \`MonitorBrowserFixture={url:string;accessUrl:string;seed(input:{hz:10;rows:256;series:8;pointsPerSeries:600}):Promise<void>;emitState(input:StateEvent):Promise<void>;emitSample(input:SampleEvent):Promise<void>;emitGap():Promise<void>;emitHeartbeat():Promise<void>;dropTotals():Promise<DropTotals>;environment():Promise<PerformanceEnvironment>;stop():Promise<void>}\`. It deliberately exposes no token field to tests after navigation.
- \`collectPerformance(page:Page,monitor:MonitorBrowserFixture,windowMs:300000):Promise<PerformanceEvidence>\`.
- \`PerformanceEvidence={minute2to5:{updateP50Ms:number;updateP95Ms:number;updateMaxMs:number;sampleCount:number};longTasksAtLeast200Ms:number;maxPoints:number;queueStart:number;queueEnd:number;queueGrowth:number;heapStartBytes:number;heapEndBytes:number;heapSlopeMiBPerMin:number;serverDropTotalsBefore:DropTotals;serverDropTotalsAfter:DropTotals;environment:{cpu:string;node:string;chromium:string;viewport:"1280x720";assetBytes:number}}\`.

Every Task 7 unit is a complete five-step loop from \`tools/stm32-monitor/ui\`.

#### Task 7A: real aiohttp fake-runtime fixture

- [ ] **7A.1 (2–5 min): Write the full failing fixture tests.** Start one fixture; assert its URL pair shares one random IPv4-loopback port, \`/\` traverses the listener, teardown closes it, and readiness reports Monitor/Toolkit module files below the supplied current source roots. Exercise \`seed\`, \`emitState\`, \`emitSample\`, \`emitGap\`, \`emitHeartbeat\`, \`dropTotals\`, and \`environment\`; reject an installed-copy module path, missing absolute E2E Python/repo root, a second HTTP/WS route, or orphan process.
- [ ] **7A.2 (2–5 min): Run RED.** From UI set \`$env:STM32_MONITOR_E2E_PYTHON=$python312\` and \`$env:STM32_MONITOR_E2E_REPO_ROOT=(Resolve-Path '..\\..\\..').Path\`, then run \`& $npx playwright test e2e/monitor.spec.ts --project=chromium --grep "fixture"\`. Expected: FAIL because \`startMonitor\` is absent.
- [ ] **7A.3 (2–5 min): Implement exactly the tested fake-runtime fixture and API.** Resolve/validate both environment paths, spawn that exact CPython with repo/workspace arguments, prepend only the two supplied source roots, instantiate real \`MonitorService\`, report bounded readiness including resolved module files, implement every declared control method, and terminate/await in teardown; UI observations still use real Monitor HTTP/WS.
- [ ] **7A.4 (2–5 min): Run GREEN.** Repeat the exact 7A.2 environment assignments and command. Expected: PASS with current-source import proof and no orphan Python process.
- [ ] **7A.5 (2–5 min): Commit the fake-runtime fixture unit.** Run \`git add tools/stm32-monitor/ui/e2e/fake_runtime.py tools/stm32-monitor/ui/e2e/conftest.ts tools/stm32-monitor/ui/e2e/monitor.spec.ts\` and commit \`test(STM32TK-0502): add real monitor browser fixture\`.

#### Task 7B: \`monitor.spec.ts\` product workflow

- [ ] **7B.1 (2–5 min): Write the full failing product workflows.** The main workflow bootstraps, verifies zero groups, explicitly connects, pages catalog, performs group CRUD/export/import, runs 100/250/5000 ms start-pause-resume-stop, asserts 256 rows and 8×600 chart, exercises pointer/touch/+/-/0 zoom, loads rendered Next/Previous history, and downloads verified CSV/JSONL. Independent cases cover replay, expired \`gap:true\`, heartbeat stale, binding/run reset, one item error with sibling success, four drop totals, busy/lease-lost without steal, and public-code failures.
- [ ] **7B.2 (2–5 min): Run RED.** Run \`& $npx playwright test e2e/monitor.spec.ts --project=chromium --grep "explicit end-to-end"\`. Expected: FAIL at the first unwired product behavior.
- [ ] **7B.3 (2–5 min): Implement exactly the callbacks/selectors needed by the tested workflows.** Wire each explicit action and each authoritative discontinuity/public-code path; do not add automatic probe acquisition/start, a fake browser API, cross-session history, synthetic continuity, or an alternate export path.
- [ ] **7B.4 (2–5 min): Run GREEN.** Repeat 7B.2; expected PASS.
- [ ] **7B.5 (2–5 min): Commit the product-workflow unit.** Run \`git add tools/stm32-monitor/ui/src tools/stm32-monitor/ui/e2e/monitor.spec.ts\` and commit \`test(STM32TK-0502): cover explicit monitor workflows\`.

#### Task 7C: \`security.spec.ts\` and \`isolation.spec.ts\`

- [ ] **7C.1 (2–5 min): Write the full failing token/no-remote/isolation/offline cases.** After \`page.goto(monitor.accessUrl)\`, assert the scrubbed URL and absence of token from DOM/HTML/console/errors/storage/IndexedDB/readable cookies/screenshots/logs. Start two workspaces and assert different ports plus zero successful cross-origin state reads; disable external network and assert the production page still completes the workflow with zero non-current-origin requests.
- [ ] **7C.2 (2–5 min): Run RED.** Run \`& $npx playwright test e2e/security.spec.ts e2e/isolation.spec.ts --project=chromium\`. Expected: FAIL until instrumentation and all guards are wired.
- [ ] **7C.3 (2–5 min): Implement exactly the tested request/console/storage capture and offline guards.** Register request interception before navigation, fail any non-current origin including other loopback ports, record only redacted facts, and exercise bad token, cookie refresh, Host/Origin/fetch-site matrices, CSP, no source maps/CDN/worker, readable-cookie absence, and blocked-network operation through real responses.
- [ ] **7C.4 (2–5 min): Run GREEN including offline.** Run \`& $npx playwright test e2e/security.spec.ts e2e/isolation.spec.ts --project=chromium\` and \`& $npx playwright test e2e/security.spec.ts --project=chromium --grep offline\`. Expected: PASS with zero accepted cross-origin requests; retain redacted evidence only under the supplied external evidence root.
- [ ] **7C.5 (2–5 min): Commit the security/isolation unit.** Run \`git add tools/stm32-monitor/ui/e2e/security.spec.ts tools/stm32-monitor/ui/e2e/isolation.spec.ts\` and commit \`test(STM32TK-0502): prove monitor browser isolation\`.

#### Task 7D: \`a11y.test.tsx\` and \`accessibility.spec.ts\`

- [ ] **7D.1 (2–5 min): Write failing component and browser accessibility cases.** Assert axe zero serious/critical violations, full keyboard order through probe/catalog/group/sampling/history/export/zoom, dialog focus/restore/Escape, polite notice, alert failure, visible controls at 200%, 1280×720 and 1024×768, and reduced-motion style.
- [ ] **7D.2 (2–5 min): Run RED.** Run \`& $npm run test:a11y; & $npx playwright test e2e/accessibility.spec.ts --project=chromium\`. Expected: FAIL on missing names/focus/layout.
- [ ] **7D.3 (2–5 min): Add the minimum semantic labels, focus transitions, responsive stacking, contrast tokens, and reduced-motion rule required by the failures.** Do not add a mobile-specific layout/theme/i18n system.
- [ ] **7D.4 (2–5 min): Run GREEN and capture exact viewport/zoom evidence.** Repeat 7D.2 with screenshot output directed only to the Task 8 external \`-EvidenceRoot\`. Expected: PASS; no screenshot enters Git.
- [ ] **7D.5 (2–5 min): Commit the accessibility unit.** Run \`git add tools/stm32-monitor/ui/tests/a11y.test.tsx tools/stm32-monitor/ui/e2e/accessibility.spec.ts tools/stm32-monitor/ui/src/styles.css\` and commit \`test(STM32TK-0502): cover monitor accessibility\`.

#### Task 7E: full five-minute performance collector

- [ ] **7E.1 (2–5 min): Write the failing typed collector test.** The test consumes every required field, so a partial object cannot typecheck:

\`\`\`ts
test("collector returns full five-minute evidence", async ({page,monitor}) => {
  await monitor.seed({hz:10,rows:256,series:8,pointsPerSeries:600});
  const evidence: PerformanceEvidence = await collectPerformance(page,monitor,300000);
  expect(evidence.minute2to5.updateP95Ms).toBeLessThanOrEqual(150);
  expect(evidence.minute2to5.sampleCount).toBeGreaterThan(0);
  expect(evidence.longTasksAtLeast200Ms).toBe(0);
  expect(evidence.maxPoints).toBeLessThanOrEqual(4800);
  expect(evidence.queueGrowth).toBeLessThanOrEqual(0);
  expect(evidence.heapSlopeMiBPerMin).toBeLessThanOrEqual(2);
  expect(evidence.serverDropTotalsAfter).toEqual(evidence.serverDropTotalsBefore);
  expect(evidence.environment.viewport).toBe("1280x720");
});
\`\`\`

- [ ] **7E.2 (2–5 min): Run RED and typecheck.** Run \`& $npm run typecheck; & $npx playwright test e2e/performance.spec.ts --project=chromium --grep "full five-minute"\`. Expected: FAIL because the collector/instrumentation is absent; a type assertion is forbidden.
- [ ] **7E.3 (2–5 min): Implement the full return object with the declared fixture methods.** Define \`BrowserPerformanceSnapshot\` with \`updates:{elapsedMs:number;durationMs:number}[]\`, \`longTasksAtLeast200Ms\`, \`maxPoints\`, \`queueDepth\`, and \`heapBytes\`; define \`percentile\` to reject an empty list. Then implement exactly:

\`\`\`ts
export async function collectPerformance(
  page:Page, monitor:MonitorBrowserFixture, windowMs:300000
):Promise<PerformanceEvidence> {
  const before = await readPerformanceSnapshot(page);
  const serverDropTotalsBefore = await monitor.dropTotals();
  await page.waitForTimeout(windowMs);
  const after = await readPerformanceSnapshot(page);
  const measured = after.updates.filter(v => v.elapsedMs >= 120000 && v.elapsedMs <= windowMs)
    .map(v => v.durationMs).sort((a,b) => a-b);
  if (measured.length === 0) throw new Error("performance sample window is empty");
  const serverDropTotalsAfter = await monitor.dropTotals();
  const environment = await monitor.environment();
  return {
    minute2to5:{updateP50Ms:percentile(measured,0.50),updateP95Ms:percentile(measured,0.95),
      updateMaxMs:measured[measured.length-1]!,sampleCount:measured.length},
    longTasksAtLeast200Ms:after.longTasksAtLeast200Ms-before.longTasksAtLeast200Ms,
    maxPoints:after.maxPoints,
    queueStart:before.queueDepth, queueEnd:after.queueDepth,
    queueGrowth:after.queueDepth-before.queueDepth,
    heapStartBytes:before.heapBytes, heapEndBytes:after.heapBytes,
    heapSlopeMiBPerMin:((after.heapBytes-before.heapBytes)/1048576)/(windowMs/60000),
    serverDropTotalsBefore, serverDropTotalsAfter, environment
  };
}
\`\`\`

- [ ] **7E.4 (2–5 min): Run GREEN, typecheck, and Task 7 aggregate gates.** Repeat 7E.2, then run \`& $npm run test:a11y; & $npx playwright test --project=chromium; & $npm audit --omit=dev --audit-level=high\`. Expected: the collector passes after exactly 300000 ms at 10 Hz/256 rows/8×600 on built assets in Chromium 1280×720 and no high/critical audit item exists.
- [ ] **7E.5 (2–5 min): Commit the performance/acceptance unit.** Add only \`tools/stm32-monitor/ui\` and \`tools/stm32-monitor/tests/test_service.py\`, then commit \`test(STM32TK-0502): add monitor UI browser acceptance\`.

### Task 8: Final Windows Gates, Unique Code Head, Report Commit, and 0.6 Documentation Deferral

**Files:**

- Modify before code head: \`docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md\`, \`docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md\`, \`README.md\`, \`README_zh-CN.md\`, and \`skills/stm32-monitor/SKILL.md\` only as necessary to document 0.6 deferral.
- Create before code head: \`tools/release/run_0502_windows_gates.ps1\` and \`tools/stm32-toolkit/tests/test_0502_release_gate_helper.py\`.
- Create after code head: \`docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md\`.
- Modify test if necessary: \`tools/stm32-toolkit/tests/test_plugin_layout.py\`.

**Interfaces:**

- Input is one clean, committed \`CODE_HEAD\` that includes every product, asset, version, README, active Skill, phase-plan, and roadmap change.
- Report records full accepted base \`bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa\`, full code-head SHA before report commit, branch, scope/path summary, exact evidence owner/status/OS-arch/tool absolute path+version/working directory/command/UTC/exit/bounded output/metrics, artifact inventory/byte-size/SHA-256, and only named deferrals.
- Retained subagent-driven-development reports remain untracked task-process evidence. The tracked report is the release evidence authority.

| TDD phase | Working directory | Exact command | Tests | Expected |
|---|---|---|---|---|
| RED docs | repository root | \`& $python312 -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py -q\` | 0.6 scope assertion | FAIL before docs changed |
| GREEN Windows | repository root | invoke committed \`tools/release/run_0502_windows_gates.ps1\` once with the three absolute parameters in Step 6 | full release inventory | PASS or concrete BLOCKED |
| report | repository root | \`git status --short; git log -1 --format=%H\` | report-only change | clean then report commit |

- [ ] **Step 1: Write and run RED docs assertion.**

\`\`\`python
def test_active_docs_defer_without_exposing_point_six_ui() -> None:
 text=Path("README.md").read_text(encoding="utf-8")+Path("README_zh-CN.md").read_text(encoding="utf-8")
 assert "0.6.0" in text
 assert "AI Analyze" not in text
 assert "diagnostic session export" not in text
\`\`\`

- [ ] **Step 2: Update documentation, phase plan, roadmap, and active Skill before code head.**

Move only deferred description: AI snapshot/analyze/diagnostic export, advanced history comparison, annotations, diagnostic timeline, full quality dashboard. Add no route, flag, implementation, or invoked test. Stage these changes with final product/assets/version content, but do not name \`CODE_HEAD\` until the release helper from Step 5 is implemented, tested, and included in the same committed head.

- [ ] **Step 3: Write and run the release-helper RED tests before code head.**

In \`tools/stm32-toolkit/tests/test_0502_release_gate_helper.py\`, add these exact tests:

1. \`test_helper_ast_has_only_three_parameters_and_no_discovery\` parses the PowerShell AST, requires only mandatory \`RepoRoot\`, \`EvidenceRoot\`, and \`ToolchainJson\`, and rejects an embedded checkout/platform-launcher literal, bare npm/npx/python, a fourth parameter, or an evidence path below RepoRoot.
2. \`test_helper_proves_code_head_sources_before_first_collection\` locates the first \`Get-NodeIds\` invocation and requires earlier CODE_HEAD capture, clean/source-tree Git checks, \`PYTHONPATH\` assignment to both resolved Monitor/Toolkit source roots, and successful current-source import checks under both fresh test interpreters.
3. \`test_helper_uses_fresh_test_venvs_for_collection_and_execution\` runs the helper with paths containing spaces and recording fake tools; base 3.10/3.12 may only create venvs/download wheels, while every pytest collect and execute command must use the corresponding \`EvidenceRoot\\test-env-*\\Scripts\\python.exe\`; 3.12 collection and execution must use the same executable.
4. \`test_helper_rejects_installed_copy_and_incomplete_wheelhouse_offline\` makes the fake import proof report one module outside the CODE_HEAD roots, then omits one dependency wheel on the next run. Both runs fail before collection/smoke. Every recorded pip \`download\`, \`wheel\`, and \`install\` command must contain \`--no-index\` and \`--find-links\` followed by the recorded resolved support or dependency-wheelhouse path; an HTTP(S) index/link or missing wheel is forbidden.
5. \`test_helper_builds_fake_managed_runtime_without_ambient_plugin_data\` starts with a sentinel \`CLAUDE_PLUGIN_DATA\`, records that CMD receives only the external \`fake-plugin-data\\runtime\\0.5.0\\Scripts\\python.exe\`, and proves the helper saves, explicitly sets, and restores the sentinel; a second run with the variable absent proves it remains absent afterward.
6. \`test_helper_fails_fast_after_first_tool_failure\` makes the first version probe fail and proves no later gate is invoked.

Run: \`& $python312 -m pytest tools/stm32-toolkit/tests/test_0502_release_gate_helper.py -q\`. Expected: FAIL because the helper is absent.

- [ ] **Step 4: Create exactly one external evidence root, then serialize the five-field toolchain record from the dependency integration.**

The controller first creates a unique repository-external absolute directory; no other evidence directory is permitted:

\`\`\`powershell
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetTempPath()) ("stm32tk-0502-evidence-" + [guid]::NewGuid().ToString("N"))))
New-Item -ItemType Directory -LiteralPath $EvidenceRoot | Out-Null
\`\`\`

The controller then calls the Codex desktop \`load_workspace_dependencies\` integration. It copies the returned absolute Node/npm/npx paths and **every** returned bundled Python candidate into the parameters of the following PowerShell function; it does not use PATH, \`Get-Command\`, the Windows launcher, or a manually guessed path. If multiple Python paths are returned, the function executes every candidate, parses \`sys.version_info\` and \`sys.executable\`, and requires exactly one 3.10 and one 3.12 result. The controller must execute the call with the actual literals returned by the integration; those runtime-dependent literals are evidence, not plan constants.

\`\`\`powershell
function Write-0502ToolchainJson {
  param(
    [Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][string]$NodePath,
    [Parameter(Mandatory)][string]$NpmPath,
    [Parameter(Mandatory)][string]$NpxPath,
    [Parameter(Mandatory)][string[]]$PythonCandidatePath
  )
  $ErrorActionPreference = 'Stop'
  $node = (Resolve-Path -LiteralPath $NodePath).Path
  $npm = (Resolve-Path -LiteralPath $NpmPath).Path
  $npx = (Resolve-Path -LiteralPath $NpxPath).Path
  $facts = foreach ($candidate in $PythonCandidatePath) {
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    $raw = & $resolved -c 'import json,sys;print(json.dumps({"path":sys.executable,"major":sys.version_info.major,"minor":sys.version_info.minor}))'
    if ($LASTEXITCODE -ne 0) { throw "bundled Python candidate failed" }
    $raw | ConvertFrom-Json
  }
  $python310 = @($facts | Where-Object { $_.major -eq 3 -and $_.minor -eq 10 })
  $python312 = @($facts | Where-Object { $_.major -eq 3 -and $_.minor -eq 12 })
  if ($python310.Count -ne 1 -or $python312.Count -ne 1) { throw "BLOCKED: require exactly one bundled CPython 3.10 and 3.12" }
  $record = [ordered]@{
    node = $node
    npm = $npm
    npx = $npx
    python310 = (Resolve-Path -LiteralPath ([string]$python310[0].path)).Path
    python312 = (Resolve-Path -LiteralPath ([string]$python312[0].path)).Path
  }
  $record | ConvertTo-Json -Compress | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'toolchain.json')
}
\`\`\`

The resulting JSON has exactly \`{node,npm,npx,python310,python312}\`; no version, launcher, repo, or evidence fields are added. From the same dependency integration, the controller must also receive one repository-external, read-only wheel support tree containing the Windows CPython 3.10/3.12 build/runtime/test wheels. It calls the function below with that returned absolute literal. The function copies only wheels into the unique EvidenceRoot and records an exact SHA-256 manifest; it never resolves a package from the network.

\`\`\`powershell
function Copy-0502DependencySupport {
  param(
    [Parameter(Mandatory)][string]$EvidenceRoot,
    [Parameter(Mandatory)][string]$DependencySupportPath
  )
  $source = (Resolve-Path -LiteralPath $DependencySupportPath -ErrorAction Stop).Path
  $destination = Join-Path $EvidenceRoot 'dependency-support'
  New-Item -ItemType Directory -LiteralPath $destination | Out-Null
  $byName = @{}
  foreach ($wheel in @(Get-ChildItem -LiteralPath $source -Recurse -File -Filter '*.whl' | Sort-Object FullName)) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wheel.FullName).Hash.ToLowerInvariant()
    if ($byName.ContainsKey($wheel.Name) -and $byName[$wheel.Name] -ne $hash) {
      throw "dependency support has conflicting wheel name: $($wheel.Name)"
    }
    if (-not $byName.ContainsKey($wheel.Name)) {
      Copy-Item -LiteralPath $wheel.FullName -Destination (Join-Path $destination $wheel.Name)
      $byName[$wheel.Name] = $hash
    }
  }
  if ($byName.Count -eq 0) { throw 'dependency support has no wheels' }
  $files = @(Get-ChildItem -LiteralPath $destination -File | Sort-Object Name | ForEach-Object {
    [ordered]@{name=$_.Name;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
  })
  [ordered]@{files=$files} | ConvertTo-Json -Depth 4 |
    Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'dependency-support.json')
}
\`\`\`

If the integration omits any tool class or a complete controlled support tree, record \`BLOCKED\` outside Git and stop; do not use pip cache, PATH, an index, or a manually guessed directory.

- [ ] **Step 5: Implement the repository-owned helper through its explicit failing test, passing test, and pre-code-head commit.**

Create \`tools/release/run_0502_windows_gates.ps1\` with the complete content below. This is the implementation contract; no omitted tail, second gate script, or checkout constant is allowed.

\`\`\`powershell
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$RepoRoot,
  [Parameter(Mandatory=$true)][string]$EvidenceRoot,
  [Parameter(Mandatory=$true)][string]$ToolchainJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$AcceptedBase = 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'
$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot -ErrorAction Stop).Path
$EvidenceRoot = (Resolve-Path -LiteralPath $EvidenceRoot -ErrorAction Stop).Path
$ToolchainJson = (Resolve-Path -LiteralPath $ToolchainJson -ErrorAction Stop).Path
if (-not [IO.Path]::IsPathFullyQualified($RepoRoot) -or
    -not [IO.Path]::IsPathFullyQualified($EvidenceRoot) -or
    -not [IO.Path]::IsPathFullyQualified($ToolchainJson)) { throw 'all paths must be absolute' }
$repoPrefix = $RepoRoot.TrimEnd('\') + '\'
if (($EvidenceRoot.TrimEnd('\') + '\').StartsWith($repoPrefix,[StringComparison]::OrdinalIgnoreCase)) {
  throw 'evidence root must be outside repository'
}

$toolchain = Get-Content -Raw -Encoding utf8 -LiteralPath $ToolchainJson | ConvertFrom-Json
$actualKeys = @($toolchain.PSObject.Properties.Name | Sort-Object)
$expectedKeys = @('node','npm','npx','python310','python312') | Sort-Object
if (@(Compare-Object $actualKeys $expectedKeys).Count -ne 0) { throw 'toolchain JSON schema mismatch' }
function Resolve-Tool([string]$value,[string]$name) {
  if (-not [IO.Path]::IsPathFullyQualified($value)) { throw "$name path is not absolute" }
  $resolved = (Resolve-Path -LiteralPath $value -ErrorAction Stop).Path
  if (-not [IO.File]::Exists($resolved)) { throw "$name path is not a file" }
  return $resolved
}
$node = Resolve-Tool ([string]$toolchain.node) 'node'
$npm = Resolve-Tool ([string]$toolchain.npm) 'npm'
$npx = Resolve-Tool ([string]$toolchain.npx) 'npx'
$basePython310 = Resolve-Tool ([string]$toolchain.python310) 'python310'
$basePython312 = Resolve-Tool ([string]$toolchain.python312) 'python312'
$uiRoot = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\ui')).Path
$monitorTests = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-monitor\tests')).Path
$toolkitTests = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\stm32-toolkit\tests')).Path
$cmdExe = (Resolve-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\cmd.exe')).Path

function Invoke-Gate {
  param([string]$Name,[string]$WorkingDirectory,[string]$FilePath,[string[]]$ArgumentList)
  $log = Join-Path $EvidenceRoot ($Name + '.log')
  $exit = -1
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
  $log = Join-Path $EvidenceRoot ($Name + '.log')
  $exit = -1
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
    if ($_.Extension -ne '.whl') { throw "non-wheel in controlled wheelhouse: $($_.Name)" }
    [ordered]@{name=$_.Name;bytes=$_.Length;
      sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
  })
}

$nodeVersion = @(Invoke-Capture 'version-node' $RepoRoot $node @('--version'))[-1]
$npmVersion = @(Invoke-Capture 'version-npm' $RepoRoot $npm @('--version'))[-1]
$npxVersion = @(Invoke-Capture 'version-npx' $RepoRoot $npx @('--version'))[-1]
$py310Fact = @(Invoke-Capture 'version-python310' $RepoRoot $basePython310 @(
  '-c','import json,sys;print(json.dumps({"major":sys.version_info.major,"minor":sys.version_info.minor,"path":sys.executable}))'
))[-1] | ConvertFrom-Json
$py312Fact = @(Invoke-Capture 'version-python312' $RepoRoot $basePython312 @(
  '-c','import json,sys;print(json.dumps({"major":sys.version_info.major,"minor":sys.version_info.minor,"path":sys.executable}))'
))[-1] | ConvertFrom-Json
if ($py310Fact.major -ne 3 -or $py310Fact.minor -ne 10) { throw 'python310 version mismatch' }
if ($py312Fact.major -ne 3 -or $py312Fact.minor -ne 12) { throw 'python312 version mismatch' }
if ((Resolve-Path -LiteralPath $py310Fact.path).Path -ne $basePython310 -or
    (Resolve-Path -LiteralPath $py312Fact.path).Path -ne $basePython312) {
  throw 'Python executable identity mismatch'
}
[ordered]@{node=$nodeVersion;npm=$npmVersion;npx=$npxVersion;
  python310="$($py310Fact.major).$($py310Fact.minor)";
  python312="$($py312Fact.major).$($py312Fact.minor)"} |
  ConvertTo-Json -Compress |
  Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'toolchain-versions.json')

$initialStatus = @(Invoke-Capture 'git-status-before' $RepoRoot 'git' @(
  'status','--porcelain=v1','--untracked-files=all'
))
if ($initialStatus.Count -ne 0) { throw 'repository must be clean before release gates' }
$codeHead = (@(Invoke-Capture 'git-code-head' $RepoRoot 'git' @('rev-parse','HEAD'))[-1]).Trim()
if ($codeHead -notmatch '^[0-9a-f]{40}$') { throw 'CODE_HEAD is not a full SHA' }
Invoke-Gate 'git-base' $RepoRoot 'git' @('cat-file','-e',"$AcceptedBase^{commit}")
Invoke-Gate 'git-diff-check' $RepoRoot 'git' @('diff','--check',"$AcceptedBase..$codeHead")
Invoke-Gate 'git-scope' $RepoRoot 'git' @('diff','--name-status',"$AcceptedBase..$codeHead")

# Bind and prove both CODE_HEAD source roots before any node collection.
$monitorSourceRelative = 'tools/stm32-monitor/src'
$toolkitSourceRelative = 'tools/stm32-toolkit/src'
$monitorSource = (Resolve-Path -LiteralPath (Join-Path $RepoRoot $monitorSourceRelative)).Path
$toolkitSource = (Resolve-Path -LiteralPath (Join-Path $RepoRoot $toolkitSourceRelative)).Path
Invoke-Gate 'git-monitor-source-clean' $RepoRoot 'git' @(
  'diff','--exit-code',$codeHead,'--',$monitorSourceRelative
)
Invoke-Gate 'git-toolkit-source-clean' $RepoRoot 'git' @(
  'diff','--exit-code',$codeHead,'--',$toolkitSourceRelative
)
foreach ($relative in @(
  'tools/stm32-monitor/src/stm32_monitor/__init__.py',
  'tools/stm32-toolkit/src/stm32_toolkit/__init__.py'
)) {
  $label = $relative.Replace('/','-').Replace('.','-')
  $headBlob = (@(Invoke-Capture ('head-blob-' + $label) $RepoRoot 'git' @(
    'rev-parse',($codeHead + ':' + $relative)
  ))[-1]).Trim()
  $worktreeBlob = (@(Invoke-Capture ('worktree-blob-' + $label) $RepoRoot 'git' @(
    'hash-object',(Join-Path $RepoRoot $relative)
  ))[-1]).Trim()
  if ($headBlob -ne $worktreeBlob) { throw "source root is not CODE_HEAD: $relative" }
}
$env:PYTHONPATH = $monitorSource + ';' + $toolkitSource
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPYCACHEPREFIX = Join-Path $EvidenceRoot 'pycache'
$env:PIP_NO_INDEX = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

# Verify the hash-pinned support tree supplied by the controller.
$dependencySupport = (Resolve-Path -LiteralPath (Join-Path $EvidenceRoot 'dependency-support')).Path
$supportManifestPath = (Resolve-Path -LiteralPath (Join-Path $EvidenceRoot 'dependency-support.json')).Path
$supportManifest = Get-Content -Raw -Encoding utf8 -LiteralPath $supportManifestPath | ConvertFrom-Json
if (@($supportManifest.PSObject.Properties.Name).Count -ne 1 -or
    $supportManifest.PSObject.Properties.Name -ne 'files') { throw 'support manifest schema mismatch' }
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

# Materialize one complete dual-Python dependency wheelhouse without an index.
$dependencyWheelhouse = Join-Path $EvidenceRoot 'dependency-wheelhouse'
New-Item -ItemType Directory -LiteralPath $dependencyWheelhouse | Out-Null
$dependencySpecs = @(
  'setuptools>=68','wheel','pytest>=8,<9','pytest-cov>=5,<7',
  'jsonschema>=4.23,<5','mcp>=1.27,<2','pyelftools>=0.33,<0.34',
  'Jinja2>=3.1,<4','aiohttp>=3.9,<4','pyocd>=0.45.1,<0.46'
)
foreach ($entry in @(@('310',$basePython310),@('312',$basePython312))) {
  $minor = [string]$entry[0]
  $basePython = [string]$entry[1]
  Invoke-Gate ('dependency-download-' + $minor) $EvidenceRoot $basePython (@(
    '-m','pip','download','--disable-pip-version-check','--no-input','--no-cache-dir',
    '--no-index','--find-links',$dependencySupport,'--only-binary=:all:',
    '--dest',$dependencyWheelhouse
  ) + $dependencySpecs)
}
$wheelhouseManifest = @(Get-WheelManifest $dependencyWheelhouse)
if ($wheelhouseManifest.Count -eq 0) { throw 'dependency wheelhouse is empty' }
$wheelhouseManifestJson = $wheelhouseManifest | ConvertTo-Json -Depth 4 -Compress
$wheelhouseManifestJson | Set-Content -Encoding utf8 -LiteralPath (
  Join-Path $EvidenceRoot 'dependency-wheelhouse.json'
)

# Build release wheels from an exact CODE_HEAD archive in an external build venv.
$packageRoot = Join-Path $EvidenceRoot 'package'
$archive = Join-Path $packageRoot 'code-head.zip'
$source = Join-Path $packageRoot 'source'
$wheels = Join-Path $packageRoot 'wheels'
$buildVenv = Join-Path $packageRoot 'build-venv-312'
New-Item -ItemType Directory -Force -Path $packageRoot,$wheels | Out-Null
Invoke-Gate 'archive-code-head' $RepoRoot 'git' @('archive','--format=zip','--output',$archive,$codeHead)
Expand-Archive -LiteralPath $archive -DestinationPath $source
Invoke-Gate 'build-venv-create' $EvidenceRoot $basePython312 @('-m','venv',$buildVenv)
$buildPython = (Resolve-Path -LiteralPath (Join-Path $buildVenv 'Scripts\python.exe')).Path
Invoke-Gate 'build-venv-install' $EvidenceRoot $buildPython @(
  '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,'setuptools>=68','wheel'
)
Invoke-Gate 'wheel-toolkit' $source $buildPython @(
  '-m','pip','wheel','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,'--no-deps','--no-build-isolation',
  '--wheel-dir',$wheels,(Join-Path $source 'tools\stm32-toolkit')
)
Invoke-Gate 'wheel-monitor' $source $buildPython @(
  '-m','pip','wheel','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,'--no-deps','--no-build-isolation',
  '--wheel-dir',$wheels,(Join-Path $source 'tools\stm32-monitor')
)
$toolkitWheel = Get-Item -LiteralPath (Join-Path $wheels 'stm32_toolkit-0.5.0-py3-none-any.whl')
$monitorWheel = Get-Item -LiteralPath (Join-Path $wheels 'stm32_monitor-0.5.0-py3-none-any.whl')
@($toolkitWheel,$monitorWheel) | ForEach-Object {
  [ordered]@{name=$_.Name;bytes=$_.Length;
    sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
} | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'wheel-hashes.json')

# Create fresh external test venvs and install all dependencies offline.
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
    $toolkitWheel.FullName,$monitorWheel.FullName
  ) + $dependencySpecs)
  Invoke-Gate ('test-venv-check-' + $minor) $EvidenceRoot $testPython @('-m','pip','check')
  $testPythonByMinor[$minor] = $testPython
}
$testPython310 = [string]$testPythonByMinor['310']
$testPython312 = [string]$testPythonByMinor['312']

$sourceProbe = @'
import importlib.metadata, json, pathlib, stm32_monitor, stm32_toolkit, sys
monitor_root = pathlib.Path(sys.argv[1]).resolve()
toolkit_root = pathlib.Path(sys.argv[2]).resolve()
monitor_file = pathlib.Path(stm32_monitor.__file__).resolve()
toolkit_file = pathlib.Path(stm32_toolkit.__file__).resolve()
assert monitor_file.is_relative_to(monitor_root), (monitor_file, monitor_root)
assert toolkit_file.is_relative_to(toolkit_root), (toolkit_file, toolkit_root)
assert importlib.metadata.version("stm32-monitor") == "0.5.0"
assert importlib.metadata.version("stm32-toolkit") == "0.5.0"
print(json.dumps({"monitor":str(monitor_file),"toolkit":str(toolkit_file),"python":sys.executable}))
'@
foreach ($entry in @(@('310',$testPython310),@('312',$testPython312))) {
  $minor = [string]$entry[0]
  $testPython = [string]$entry[1]
  Invoke-Capture ('current-source-import-' + $minor) $RepoRoot $testPython @(
    '-c',$sourceProbe,$monitorSource,$toolkitSource
  ) | Out-Null
}

Invoke-Gate 'node-npm-ci' $uiRoot $npm @('ci')
Invoke-Gate 'node-typecheck' $uiRoot $npm @('run','typecheck')
Invoke-Gate 'node-lint' $uiRoot $npm @('run','lint')
Invoke-Gate 'node-unit-coverage' $uiRoot $npm @('run','test:coverage')
Invoke-Gate 'node-a11y' $uiRoot $npm @('run','test:a11y')
Invoke-Gate 'node-build' $uiRoot $npm @('run','build')
Invoke-Gate 'node-verify-dist' $uiRoot $npm @('run','verify:dist')
Invoke-Gate 'node-production-audit' $uiRoot $npm @('audit','--omit=dev','--audit-level=high')

function Get-NodeIds {
  param([string]$Name,[string]$PythonPath,[string[]]$Paths,[string[]]$ExtraArgs)
  $args = @('-m','pytest') + $Paths + @('--collect-only','-q','-p','no:cacheprovider') + $ExtraArgs
  $lines = Invoke-Capture $Name $RepoRoot $PythonPath $args
  return @($lines | ForEach-Object { [string]$_ } | Where-Object { $_ -match '^[^=]+::' } | Sort-Object)
}
function Assert-UniqueInventory([string]$Name,[string[]]$NodeIds) {
  $unique = @($NodeIds | Sort-Object -Unique)
  if ($NodeIds.Count -eq 0 -or $unique.Count -ne $NodeIds.Count) {
    throw "$Name nodeid duplicate/count mismatch"
  }
}

# First collection occurs only after both current-source proofs.
$monitorAll = Get-NodeIds 'collect-monitor-all' $testPython312 @($monitorTests) @()
$toolkitAll = Get-NodeIds 'collect-toolkit-all' $testPython312 @($toolkitTests) @()
$monitorAll310 = Get-NodeIds 'collect-monitor-all-310' $testPython310 @($monitorTests) @()
Assert-UniqueInventory 'Monitor' $monitorAll
Assert-UniqueInventory 'Toolkit' $toolkitAll
Assert-UniqueInventory 'Monitor 3.10' $monitorAll310
if (@(Compare-Object $monitorAll $monitorAll310).Count -ne 0) {
  throw 'Monitor 3.10/3.12 collection inventory mismatch'
}
$allNodeIds = @($monitorAll + $toolkitAll)
Assert-UniqueInventory 'combined' $allNodeIds
$monitorAll | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'monitor-312-nodeids.txt')
$monitorAll310 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'monitor-310-nodeids.txt')
$toolkitAll | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'toolkit-312-nodeids.txt')
$allNodeIds | Sort-Object | Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'all-312-nodeids.txt')

$monitorSpecial = @(
  'tools/stm32-monitor/tests/test_auth.py',
  'tools/stm32-monitor/tests/test_service.py',
  'tools/stm32-monitor/tests/test_ui_assets.py',
  'tools/stm32-monitor/tests/test_ui_dist.py',
  'tools/stm32-monitor/tests/test_package_boundary.py',
  'tools/stm32-monitor/tests/test_performance.py'
)
$monitorIgnore = @($monitorSpecial | ForEach-Object { "--ignore=$_" })
$monitorMainIds = Get-NodeIds 'collect-monitor-main' $testPython312 @('tools/stm32-monitor/tests') $monitorIgnore
$monitorSpecialIds = Get-NodeIds 'collect-monitor-special' $testPython312 $monitorSpecial @()
$monitorPartition = @($monitorMainIds + $monitorSpecialIds)
Assert-UniqueInventory 'Monitor execution partition' $monitorPartition
if (@(Compare-Object $monitorAll $monitorPartition).Count -ne 0) {
  throw 'Monitor execution inventory mismatch'
}

$toolkitSpecial = @(
  'tools/stm32-toolkit/tests/test_plugin_layout.py',
  'tools/stm32-toolkit/tests/test_project_upgrade.py',
  'tools/stm32-toolkit/tests/test_0502_release_gate_helper.py'
)
$toolkitFiles = @(Get-ChildItem -LiteralPath $toolkitTests -Filter 'test_*.py' -File |
  ForEach-Object { $_.FullName.Substring($RepoRoot.Length + 1).Replace('\','/') } |
  Where-Object { $toolkitSpecial -notcontains $_ } | Sort-Object)
$assignedFiles = [Collections.Generic.List[string]]::new()
$toolkitShardIds = [Collections.Generic.List[string]]::new()
for ($shard=0; $shard -lt 8; $shard++) {
  $files = [Collections.Generic.List[string]]::new()
  for ($index=$shard; $index -lt $toolkitFiles.Count; $index+=8) {
    $files.Add($toolkitFiles[$index])
    $assignedFiles.Add($toolkitFiles[$index])
  }
  if ($files.Count -gt 0) {
    foreach ($nodeId in (Get-NodeIds ("collect-toolkit-shard-{0}" -f ($shard+1)) $testPython312 $files.ToArray() @())) {
      $toolkitShardIds.Add($nodeId)
    }
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
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-monitor-310')
)
$env:COVERAGE_FILE = Join-Path $EvidenceRoot '.coverage-312'
Invoke-Gate 'python312-monitor-main-coverage' $RepoRoot $testPython312 (@(
  '-m','pytest','tools/stm32-monitor/tests','-q','-p','no:cacheprovider'
) + $monitorIgnore + @(
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-monitor-main-312'),
  '--cov=stm32_monitor','--cov-branch','--cov-report='
))
Invoke-Gate 'python312-auth-static-package-performance' $RepoRoot $testPython312 (@(
  '-m','pytest'
) + $monitorSpecial + @(
  '-q','-s','-p','no:cacheprovider',
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-monitor-special-312'),
  '--cov=stm32_monitor','--cov-branch','--cov-append','--cov-report='
))
for ($shard=0; $shard -lt 8; $shard++) {
  $files = @()
  for ($index=$shard; $index -lt $toolkitFiles.Count; $index+=8) { $files += $toolkitFiles[$index] }
  if ($files.Count -gt 0) {
    Invoke-Gate ("python312-toolkit-shard-{0}" -f ($shard+1)) $RepoRoot $testPython312 (@(
      '-m','pytest'
    ) + $files + @(
      '-q','-p','no:cacheprovider',
      '--basetemp',(Join-Path $EvidenceRoot ("basetemp-toolkit-{0}-312" -f ($shard+1))),
      '--cov=stm32_toolkit','--cov-branch','--cov-append','--cov-report='
    ))
  }
}
Invoke-Gate 'python312-plugin-immutability-helper' $RepoRoot $testPython312 (@(
  '-m','pytest'
) + $toolkitSpecial + @(
  '-q','-p','no:cacheprovider',
  '--basetemp',(Join-Path $EvidenceRoot 'basetemp-toolkit-special-312'),
  '--cov=stm32_toolkit','--cov-branch','--cov-append','--cov-report='
))
$coverageJson = Join-Path $EvidenceRoot 'coverage-312.json'
Invoke-Gate 'python312-coverage-json' $RepoRoot $testPython312 @(
  '-m','coverage','json','-o',$coverageJson
)
$coverage = Get-Content -Raw -Encoding utf8 -LiteralPath $coverageJson | ConvertFrom-Json
if ([double]$coverage.totals.percent_covered -lt 90.0) {
  throw 'combined branch-aware coverage below 90%'
}
$changedModules = @(& git -C $RepoRoot diff --name-only $AcceptedBase $codeHead |
  Where-Object { $_ -match '^tools/stm32-(monitor|toolkit)/src/.+\.py$' })
if ($LASTEXITCODE -ne 0) { throw 'changed-module inventory failed' }
foreach ($module in $changedModules) {
  $normalized = $module.Replace('\','/')
  $matches = @($coverage.files.PSObject.Properties | Where-Object {
    $_.Name.Replace('\','/').EndsWith($normalized,[StringComparison]::OrdinalIgnoreCase)
  })
  if ($matches.Count -ne 1) { throw "coverage entry missing or ambiguous: $module" }
  if ([double]$matches[0].Value.summary.percent_covered -lt 90.0) {
    throw "changed module branch-aware coverage below 90%: $module"
  }
}

$env:STM32_MONITOR_E2E_PYTHON = $testPython312
$env:STM32_MONITOR_E2E_REPO_ROOT = $RepoRoot
Invoke-Gate 'playwright-chromium-functional' $uiRoot $npx @(
  'playwright','test','--project=chromium','--grep-invert','five-minute'
)
Invoke-Gate 'playwright-chromium-five-minute-performance' $uiRoot $npx @(
  'playwright','test','e2e/performance.spec.ts','--project=chromium','--grep','five-minute'
)
foreach ($entry in @(@('310',$testPython310),@('312',$testPython312))) {
  $minor = [string]$entry[0]
  $testPython = [string]$entry[1]
  $env:PYTHONPYCACHEPREFIX = Join-Path $EvidenceRoot ('compile-pycache-' + $minor)
  Invoke-Gate ('compile-monitor-' + $minor) $RepoRoot $testPython @(
    '-m','compileall','-q','tools/stm32-monitor/src/stm32_monitor'
  )
  Invoke-Gate ('compile-toolkit-' + $minor) $RepoRoot $testPython @(
    '-m','compileall','-q','tools/stm32-toolkit/src/stm32_toolkit'
  )
}

# Create an external fake managed runtime and remove ambient state from CMD.
$fakePluginData = Join-Path $EvidenceRoot 'fake-plugin-data'
$fakeRuntime = Join-Path $fakePluginData 'runtime\0.5.0'
Invoke-Gate 'fake-managed-runtime-create' $EvidenceRoot $basePython312 @('-m','venv',$fakeRuntime)
$fakeRuntimePython = (Resolve-Path -LiteralPath (Join-Path $fakeRuntime 'Scripts\python.exe')).Path
Invoke-Gate 'fake-managed-runtime-install' $EvidenceRoot $fakeRuntimePython @(
  '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
  '--no-index','--find-links',$dependencyWheelhouse,
  $toolkitWheel.FullName,$monitorWheel.FullName,'pyocd>=0.45.1,<0.46'
)
Invoke-Gate 'fake-managed-runtime-check' $EvidenceRoot $fakeRuntimePython @(
  '-c','import importlib.metadata,importlib.resources,sys;assert importlib.metadata.version("stm32-toolkit")=="0.5.0";assert importlib.metadata.version("stm32-monitor")=="0.5.0";assert importlib.resources.files("stm32_monitor").joinpath("ui_dist/index.html").is_file();print(sys.executable)'
)
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

# Install exact release wheels into separate fresh smoke venvs, offline.
$smokePath = Join-Path $EvidenceRoot 'installed-smoke.py'
@'
import asyncio, importlib.metadata, importlib.resources, pathlib, sys
from aiohttp import ClientSession
import stm32_monitor, stm32_toolkit
from stm32_monitor.service import MonitorService
assert importlib.metadata.version("stm32-monitor") == "0.5.0"
assert importlib.metadata.version("stm32-toolkit") == "0.5.0"
prefix = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(stm32_monitor.__file__).resolve().is_relative_to(prefix)
assert pathlib.Path(stm32_toolkit.__file__).resolve().is_relative_to(prefix)
root = importlib.resources.files("stm32_monitor").joinpath("ui_dist")
assert root.joinpath("index.html").is_file()
assert root.joinpath(".vite/manifest.json").is_file()
class Runtime:
    async def dispatch(self, *args, **kwargs):
        raise AssertionError("unauthenticated request reached runtime")
async def smoke():
    service = MonitorService(Runtime(), workspace_id="installed-workspace", session_id="installed-session")
    endpoint = await service.start()
    try:
        async with ClientSession() as client:
            index = await client.get(endpoint.url + "/")
            assert index.status == 200
            csp = index.headers["Content-Security-Policy"]
            assert "default-src 'none'" in csp and endpoint.url.replace("http","ws",1) in csp
            denied = await client.get(endpoint.url + "/api/v1/status")
            assert denied.status in (401, 403)
    finally:
        await service.stop()
asyncio.run(smoke())
'@ | Set-Content -Encoding utf8 -LiteralPath $smokePath

foreach ($entry in @(@('310',$basePython310),@('312',$basePython312))) {
  $minor = [string]$entry[0]
  $basePython = [string]$entry[1]
  $smokeVenv = Join-Path $packageRoot ('smoke-venv-' + $minor)
  Invoke-Gate ('smoke-venv-create-' + $minor) $EvidenceRoot $basePython @('-m','venv',$smokeVenv)
  $smokePython = (Resolve-Path -LiteralPath (Join-Path $smokeVenv 'Scripts\python.exe')).Path
  Invoke-Gate ('smoke-venv-install-offline-' + $minor) $EvidenceRoot $smokePython @(
    '-m','pip','install','--disable-pip-version-check','--no-input','--no-cache-dir',
    '--no-index','--find-links',$dependencyWheelhouse,
    $toolkitWheel.FullName,$monitorWheel.FullName,'pyocd>=0.45.1,<0.46'
  )
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
Invoke-Gate 'git-diff-check-after' $RepoRoot 'git' @('diff','--check',"$AcceptedBase..$codeHead")
$finalStatus = @(Invoke-Capture 'git-status-after' $RepoRoot 'git' @(
  'status','--porcelain=v1','--untracked-files=all'
))
if ($finalStatus.Count -ne 0) { throw 'repository changed during release gates' }
[ordered]@{acceptedBase=$AcceptedBase;codeHead=$codeHead;status='PASS';
  testPython310=$testPython310;testPython312=$testPython312;
  dependencyWheelhouse='dependency-wheelhouse.json'} |
  ConvertTo-Json -Compress |
  Set-Content -Encoding utf8 -LiteralPath (Join-Path $EvidenceRoot 'windows-gates-summary.json')
\`\`\`

Run the RED helper test from Step 3 again; then run the PowerShell parser over the helper and execute the test with a fake RepoRoot/EvidenceRoot/toolchain containing spaces. Expected: PASS and fail-fast ordering proven. Stage the helper/test plus all product/assets/version/docs changes and create the final product commit. Only now run \`git status --short; git rev-parse HEAD; git diff --name-status bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa..HEAD; git diff --check bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa..HEAD\`; require clean worktree, record the full SHA as the unique \`CODE_HEAD\`, and verify the helper is present in that commit.

- [ ] **Step 6: Execute the committed helper once from the current isolated worktree.**

\`\`\`powershell
$RepoRoot = (Resolve-Path -LiteralPath '.').Path
$ToolchainJson = (Resolve-Path -LiteralPath (Join-Path $EvidenceRoot 'toolchain.json')).Path
$GateScript = (Resolve-Path -LiteralPath (Join-Path $RepoRoot 'tools\release\run_0502_windows_gates.ps1')).Path
$PowerShell = (Resolve-Path -LiteralPath (Join-Path $PSHOME 'powershell.exe')).Path
& $PowerShell -NoProfile -ExecutionPolicy Bypass -File $GateScript -RepoRoot $RepoRoot -EvidenceRoot $EvidenceRoot -ToolchainJson $ToolchainJson
if ($LASTEXITCODE -ne 0) { throw "STM32TK-0502 Windows gates failed: $LASTEXITCODE" }
\`\`\`

The one invocation reloads JSON inside its process, resolves and version-checks all five tools, verifies the controller's hash-pinned support tree, creates a complete dependency wheelhouse, and then creates fresh external 3.10/3.12 test venvs. Both Monitor collections use the same respective venv interpreter as execution and must enumerate equal nodeids; every 3.12 Monitor/Toolkit nodeid is unique and assigned once. The helper proves both imports resolve below CODE_HEAD source roots before the first collection, points Playwright's fake runtime at the 3.12 test venv/current repo, partitions 3.12 Monitor and Toolkit coverage without overlap, and fails on the first nonzero process. The performance invocation is exactly \`& $npx playwright test e2e/performance.spec.ts --project=chromium --grep five-minute\`; every log/artifact stays below the one external EvidenceRoot.

- [ ] **Step 7: Reconcile the helper outputs before reporting.**

Require PASS logs for npm ci/typecheck/lint/unit branch coverage/a11y/build/dist/audit; current-source import proof; equal 3.10/3.12 Monitor inventories; unique 3.12 Monitor/Toolkit assignment; same-venv collection/execution; functional Chromium/fake-runtime import proof plus the five-minute collector; 3.12 Toolkit shards; combined and every changed product module branch-aware coverage >=90%; auth/static/package/performance; dual compileall; plugin/helper/project immutability; external fake managed runtime CMD launcher; verified dependency-support and dependency-wheelhouse manifests; CODE_HEAD archive; exact wheel filenames/hashes; offline fresh 3.10/3.12 wheel install/smoke; and clean Git status. Any missing log, duplicate/missing nodeid, installed-copy import, ambient launcher dependency, mutable/incomplete wheelhouse, pip command without \`--no-index --find-links\`, failed threshold, untracked repo output, or changed lock/dist is FAIL, not deferred.

- [ ] **Step 8: Record only allowed platform deferrals.**

Record exactly \`DEFERRED — Linux release owner\` for Linux x86_64 CPython 3.10/3.12 Node/npm Chromium/Firefox/WebKit independent rerun, and \`DEFERRED — user/hardware owner\` for supported-board observation smoke. Never infer either PASS from Windows.

- [ ] **Step 9: Write report after all gates and commit report only.**

The report is created after CODE_HEAD and gate completion. It must not contain own final SHA, moving commit total, token/access URL/raw endpoint/absolute project path/sample values, or false hardware evidence.

\`\`\`bash
git add docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md
git commit -m "docs(STM32TK-0502): record lean monitor UI release evidence"
\`\`\`

- [ ] **Step 10: Handle a post-gate review correction deterministically.**

If review changes any product, asset, version, README, phase plan, roadmap, or active Skill, create a new committed CODE_HEAD; rerun every affected gate plus full scope/integrity checks against \`bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa..new-code-head\`; replace report contents with new code head/evidence; commit the rewritten report separately. Do not append a stale report or reuse results from superseded code.

## Plan Self-Review

- [x] **Spec coverage:** Task 1 is exact Node/Preact/contract/fragment/auth/state. Task 2 covers identity/probe/catalog/groups/shallow selection. Task 3 covers typed live table/basic chart/DataZoom/sampling/quality. Task 4 covers history/verified CSV JSONL. Task 5 covers aiohttp allowlist/CSP/wheel. Task 6 covers explicit launcher/runtime/plugin/active Skill/0.5. Task 7 covers real aiohttp fake-runtime Playwright/axe/offline/two-workspace/security and five-minute production performance. Task 8 covers code-head gates/report and documentation-only 0.6 deferral.
- [x] **Finding closure:** Every one of the 31 original product units was rechecked for adjacent failing test, exact RED command, matching minimum implementation, exact GREEN command, and commit. The two reviewer-identified merged boundaries were split, so the final plan has 33 independently numbered five-checkbox loops: \`IdentityBar\`/ \`ProbePanel\`, and traversal allowlist/\`verify_tree\` limits. No later checkbox introduces another test-and-implementation pair. Group deletion exercises Delete→pending dialog→Confirm→\`onDelete\`; history pagination exercises the rendered Next button, server cursor, and \`onPage\`; the collector fills every \`PerformanceEvidence\` field through declared fixture methods without a type assertion.
- [x] **Gate closure:** Task 8 commits/tests the three-parameter helper before naming \`CODE_HEAD\`. Before first collection it binds and proves both current source roots, creates external fresh 3.10/3.12 test venvs from a hash-verified offline wheelhouse, and uses those same interpreters for collection/execution. The same invocation covers Node, inventory uniqueness, coverage, explicit fake-runtime imports, Playwright five-minute, auth/static/performance, compile/plugin/immutability, external fake managed runtime with saved/set/restored \`CLAUDE_PLUGIN_DATA\`, exact-head wheels, offline dual smoke, hashes, and clean-worktree gates.
- [x] **Placeholder/hard-code scan:** No unresolved instruction, platform Python-launcher literal, checkout-root literal, bare runtime discovery, or external gate-script path remains. Runtime-dependent tool paths come only from \`load_workspace_dependencies\` and the exact five-field JSON.
- [x] **Type consistency:** Task 1 defines MonitorClient, action union, auth method and reducer before every consumer. Derived selectors preserve only descriptor facts and give unknown child type to backend validation; no member/element type is guessed. Task 3 defines zoom state/control before E2E/performance. Task 4 props include page/cursor/\`onPage\`. Task 7 fixture and collector signatures match. Task 8 uses report/code-head names only after defining their lifecycle.
