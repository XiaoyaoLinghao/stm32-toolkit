> **REWRITE_REQUIRED — DO NOT EXECUTE.**
>
> Superseded by `docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md`; do not execute this split plan or any packet/signature/handoff machinery in it.

# STM32TK-0502 Runtime and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Starting from the committed frontend-core result, serve its offline UI through the existing random-port aiohttp process, add the explicit human launcher, promote the managed Plugin runtime and all active release surfaces to `0.5.0`, and finish every release document that must precede the final evidence `CODE_HEAD`.

**Architecture:** The committed Vite output is read only through `importlib.resources`, validated once into an exact immutable allowlist, and served by the existing `MonitorService`; no request path is joined to a filesystem path and `/api/*` never receives an SPA fallback. `serve --json` remains the side-effect-free machine interface, while `open` is the sole browser-opening path and both Plugin launchers select only `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0/Scripts/python.exe`. The runtime consumes an exact signed `FrontendCoreReturnPacket` and ends by emitting an exact separately signed `RuntimeReleaseReturnPacket` containing one clean `runtimeReleaseHead`; the browser-evidence plan adds its pre-barrier fixtures/tests/helper, and its Task 5 alone audits the complete ancestry and names the sole final `CODE_HEAD` before Task 6 writes the report.

**Tech Stack:** CPython 3.10/3.12, aiohttp, `importlib.resources`, setuptools wheels, PowerShell, Windows CMD, committed Preact/Vite assets, pytest, npm.

## Delivery Ledger and Authority

- Module/phase: `STM32TK-0502-MONITOR-UI-RELEASE`, runtime/release implementation packet after frontend core and before evidence/acceptance.
- Full accepted base: `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`.
- Design authority and specification owner: Codex, `docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md` at `28c8a91b7f65392257c0ba517195fdd2365d55a7`.
- Objective-bounded ownership exception: the user explicitly authorized Codex subagents to implement the complete `STM32TK-0502-MONITOR-UI-RELEASE` objective across its frontend-core, runtime-release, and browser-evidence plans. The selected Codex subagent is implementer and Codex is reviewer/acceptance owner; this exception expires when this 0502 objective is concluded and grants no implementation ownership for any other module, later release, correction, or follow-on work.
- Active implementation branch/worktree: supplied by the frontend-core handoff and checked out at the exact input SHA. Do not infer it from a main checkout, another branch, or a remote tracking ref.
- Remote authorization: none. This plan authorizes local implementation commits only; it does not authorize push, PR mutation, merge, close, approval, or branch deletion.
- Bounded override: only the objective-level Codex ownership exception above. It does not imply a future-module override; any later correction outside the 0502 objective requires a new user-authorized file/behavior bound.

## Input Contract: Signed Canonical `FrontendCoreReturnPacket` File and `FRONTEND_CORE_CODE_HEAD`

The only cross-plan transport is a repository-external canonical UTF-8 JSON file plus a separate lowercase signature string. The controller binds its absolute file path to `$FrontendCorePacketPath` and the separately transmitted signature to `$handoffSignatureSha256`; the signature is never embedded in the JSON. The file contains exactly one `FrontendCoreReturnPacket` with no BOM, newline, extra whitespace, wrapper, renamed field, reordered field, or extra field.

```ts
type FrontendCoreReturnPacket={schema:"stm32tk-0502-frontend-core/1";
 moduleId:"STM32TK-0502-MONITOR-UI-RELEASE";
 acceptedBase:"bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa";planBundleHead:string;
 frontendCoreCodeHead:string;branch:string;worktreeClean:true;remoteActionPerformed:false};
```

`frontendCoreCodeHead` is not copied into this plan. The controller also passes that exact packet value as `$env:FRONTEND_CORE_CODE_HEAD`, checks out an isolated worktree at that exact commit, and runs this preflight from that worktree's repository root. The hash covers the file bytes before parsing. The decoded string must then be byte-for-byte equivalent to PowerShell `ConvertTo-Json -Compress` over the parsed packet in the declared property order.

```powershell
$repoRoot = (Resolve-Path -LiteralPath '.').Path
$expectedAcceptedBase = 'bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa'
if (-not [IO.Path]::IsPathRooted($FrontendCorePacketPath)) { throw 'frontend packet path is not absolute' }
$FrontendCorePacketPath = [IO.Path]::GetFullPath($FrontendCorePacketPath)
$repoPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($FrontendCorePacketPath.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'frontend packet file is inside the repository' }
if (-not (Test-Path -LiteralPath $FrontendCorePacketPath -PathType Leaf)) { throw 'frontend packet file is unavailable' }
if ($handoffSignatureSha256 -isnot [string] -or $handoffSignatureSha256 -notmatch '^[0-9a-f]{64}$') { throw 'frontend handoff signature is invalid' }
$frontendBytes = [IO.File]::ReadAllBytes($FrontendCorePacketPath)
if ($frontendBytes.Count -eq 0 -or ($frontendBytes.Count -ge 3 -and $frontendBytes[0] -eq 0xEF -and $frontendBytes[1] -eq 0xBB -and $frontendBytes[2] -eq 0xBF)) { throw 'frontend packet is empty or has BOM' }
$frontendHasher = [Security.Cryptography.SHA256]::Create()
try { $frontendHash = $frontendHasher.ComputeHash($frontendBytes) }
finally { $frontendHasher.Dispose() }
$computedFrontendSignature = (($frontendHash | ForEach-Object { $_.ToString('x2') }) -join '')
if ($computedFrontendSignature -cne $handoffSignatureSha256) { throw 'frontend handoff signature mismatch' }
$strictUtf8 = New-Object Text.UTF8Encoding($false, $true)
$frontendCanonical = $strictUtf8.GetString($frontendBytes)
if ($frontendCanonical.Contains("`r") -or $frontendCanonical.Contains("`n")) { throw 'frontend packet is not one-line canonical JSON' }
$FrontendCoreReturnPacket = $frontendCanonical | ConvertFrom-Json
$packetFields = @($FrontendCoreReturnPacket.PSObject.Properties.Name)
if (($packetFields -join ',') -cne 'schema,moduleId,acceptedBase,planBundleHead,frontendCoreCodeHead,branch,worktreeClean,remoteActionPerformed') { throw 'frontend packet field schema/order is invalid' }
foreach ($name in @('schema','moduleId','acceptedBase','planBundleHead','frontendCoreCodeHead','branch')) {
  if ($FrontendCoreReturnPacket.$name -isnot [string]) { throw "frontend packet field is not a string: $name" }
}
$reencodedFrontendCanonical = $FrontendCoreReturnPacket | ConvertTo-Json -Compress
if ($reencodedFrontendCanonical -cne $frontendCanonical) { throw 'frontend packet is not canonical JSON' }
$schema = [string]$FrontendCoreReturnPacket.schema
$moduleId = [string]$FrontendCoreReturnPacket.moduleId
$acceptedBase = [string]$FrontendCoreReturnPacket.acceptedBase
$planBundleHead = [string]$FrontendCoreReturnPacket.planBundleHead
$frontendCoreCodeHead = [string]$FrontendCoreReturnPacket.frontendCoreCodeHead
$branch = [string]$FrontendCoreReturnPacket.branch
$worktreeClean = $FrontendCoreReturnPacket.worktreeClean
$remoteActionPerformed = $FrontendCoreReturnPacket.remoteActionPerformed
if ($schema -cne 'stm32tk-0502-frontend-core/1') { throw 'frontend handoff schema is invalid' }
if ($moduleId -cne 'STM32TK-0502-MONITOR-UI-RELEASE') { throw 'frontend handoff moduleId is invalid' }
if ($acceptedBase -cne $expectedAcceptedBase) { throw 'frontend handoff acceptedBase is invalid' }
if ($planBundleHead -notmatch '^[0-9a-f]{40}$') { throw 'frontend handoff planBundleHead is invalid' }
if ($frontendCoreCodeHead -notmatch '^[0-9a-f]{40}$') { throw 'frontend handoff frontendCoreCodeHead is invalid' }
if ($branch -notmatch '\S' -or $worktreeClean -isnot [bool] -or $worktreeClean -cne $true -or $remoteActionPerformed -isnot [bool] -or $remoteActionPerformed -cne $false) { throw 'frontend handoff state is invalid' }
if ($env:FRONTEND_CORE_CODE_HEAD -notmatch '^[0-9a-f]{40}$') { throw 'missing full FRONTEND_CORE_CODE_HEAD' }
$resolvedFrontendCoreCodeHead = (& git rev-parse "$frontendCoreCodeHead^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $resolvedFrontendCoreCodeHead -cne $frontendCoreCodeHead -or $frontendCoreCodeHead -cne $env:FRONTEND_CORE_CODE_HEAD) { throw 'frontend-core packet/env SHA mismatch' }
$resolvedPlanBundleHead = (& git rev-parse "$planBundleHead^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $resolvedPlanBundleHead -cne $planBundleHead) { throw 'plan bundle SHA is not an exact commit' }
$actualHead = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actualHead -cne $frontendCoreCodeHead) { throw 'worktree is not at FRONTEND_CORE_CODE_HEAD' }
$actualBranch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $actualBranch -cne $branch) { throw 'frontend handoff branch does not match worktree' }
$status = @(& git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'frontend-core worktree is not clean' }
& git cat-file -e "$acceptedBase^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'accepted base is unavailable' }
& git merge-base --is-ancestor $acceptedBase $planBundleHead
if ($LASTEXITCODE -ne 0) { throw 'plan bundle does not descend from accepted base' }
& git merge-base --is-ancestor $planBundleHead $frontendCoreCodeHead
if ($LASTEXITCODE -ne 0) { throw 'frontend-core head does not descend from plan bundle' }
& git merge-base --is-ancestor $acceptedBase $frontendCoreCodeHead
if ($LASTEXITCODE -ne 0) { throw 'frontend-core head does not descend from accepted base' }
& git diff --check "$acceptedBase..$frontendCoreCodeHead"
if ($LASTEXITCODE -ne 0) { throw 'frontend-core diff check failed' }
```

The input commit must already contain the complete frontend source/config/lock/tests from the frontend-core plan and the bounded design §7.3 auth compatibility change. In particular, these interfaces must exist before Task 1:

- `tools/stm32-monitor/ui/package.json`, committed `package-lock.json`, strict TypeScript/Vite/Vitest configuration, frontend source and frontend unit tests;
- `tools/stm32-monitor/src/stm32_monitor/auth.py` with `authorize(..., method, fetch_site, websocket)` and the exact safe-cookie/Bearer/mutation matrix;
- `tools/stm32-monitor/src/stm32_monitor/service.py` passing normalized method, `Sec-Fetch-Site`, and WebSocket context into auth without changing the 0501 API grammar;
- passing frontend-core focused gates under the exact handoff commit.

This packet may extend `service.py`, but it must not reopen or broaden the §7.3 decision. If any input is absent or the preflight fails, stop as `BLOCKED`; do not reconstruct frontend work here.

The historical requirement source is immutable. Before Task 1 record and verify its accepted-base blob:

```powershell
$historicalSkill = 'requirements/follow-on-skills/stm32-monitor/SKILL.md'
$historicalBlob = (& git rev-parse "$acceptedBase`:$historicalSkill").Trim()
$inputHistoricalBlob = (& git rev-parse "$frontendCoreCodeHead`:$historicalSkill").Trim()
if ($LASTEXITCODE -ne 0 -or $historicalBlob -notmatch '^[0-9a-f]{40}$' -or $historicalBlob -cne $inputHistoricalBlob) { throw 'historical monitor requirement changed before runtime packet' }
```

## Tool and Working-Directory Contract

The implementation controller uses the Codex desktop workspace-dependency integration once and binds its returned absolute paths to `$node`, `$npm`, `$npx`, `$python310`, and `$python312`. It validates each path and version before Task 1. Do not use `PATH` Python/Node, `py`, the Windows Python launcher, `uv`, a hard-coded checkout, or the main checkout. `$cmdExe` is the resolved `Join-Path $env:SystemRoot 'System32/cmd.exe'`; `$powerShell` is the resolved `Join-Path $PSHOME 'powershell.exe'`.

| Tool/action | Working directory | Exact command form |
|---|---|---|
| Python focused RED/GREEN | `$repoRoot` | use the exact pytest paths/nodeids in the applicable task with `& $python312 -m pytest`, `-q -p no:cacheprovider`, and that task's external `$taskTemp`; repeat the named compatibility command with `$python310` |
| UI build/dist | `$uiRoot = Resolve-Path "$repoRoot/tools/stm32-monitor/ui"` | `& $npm ci`, `& $npm run build`, `& $npm run verify:dist` |
| CMD launcher smoke | `$repoRoot` | `& $cmdExe /d /c bin\stm32-monitor.cmd --help` or the pytest fixture command named below |
| Setup helper tests | `$repoRoot` | use the exact focused nodes stated in Task 8, then the exact full-file command `& $python312 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py -q -p no:cacheprovider --basetemp $taskTemp` |
| Git checks/commits | `$repoRoot` | exact `git add` paths listed in each Step 5, followed by the listed `git commit -m ...` |

Every pytest `--basetemp`, wheel directory, rebuilt dist comparison directory, CMD fixture runtime, and build scratch path is repository-external. Product output is only the explicitly committed `ui_dist`; no `.pytest_cache`, coverage file, `node_modules`, wheel, venv, screenshot, or log enters Git.

## Global Constraints

- Preserve every 0501 REST/WS route, operation, envelope, request/body/query grammar, history, sampling, store, exporter, and runtime-record rule. This packet adds only static UI service behavior and release/runtime surfaces.
- `UiAssets` consumes package resources only. It never concatenates request input with a filesystem path, calls `web.add_static`, lists a directory, reflects a rejected route, or falls back from `/api/*` to `index.html`.
- Static access is unauthenticated only after exact IPv4 loopback peer, exact bound Host, header budget, and optional exact Origin checks. Static access never relaxes API authentication.
- `serve --json` stays byte-compatible, waits in the foreground, and calls no browser API. It does not accept `--open-browser` and writes no token/access URL/raw endpoint to files or logs.
- `open` starts first, opens `endpoint.access_url` exactly once, prints no fragment URL, uses a random `monitor-<32 lowercase hex>` session only when omitted, remains foreground, and owns cleanup on opener failure and Ctrl-C.
- Both CMD launchers select only `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0/Scripts/python.exe`; there is no fallback to system `python`, `python3`, `py`, or `uv`.
- The managed runtime contains exact `stm32-toolkit==0.5.0`, exact `stm32-monitor==0.5.0`, Toolkit's `probe` extra, and readable UI manifest/assets. Node and `node_modules` never enter it.
- Runtime Python dependencies remain exactly `stm32-toolkit==0.5.0` and `aiohttp>=3.9,<4`. Python wheel construction never invokes Node.
- Active Plugin, Toolkit, Monitor, CLI, protocol, launchers, setup, Skills, README, and active tests are `0.5.0`. Previous-version fixtures remain previous-version fixtures and are not mass-rewritten.
- The active Monitor Skill is `skills/stm32-monitor/SKILL.md`. `requirements/follow-on-skills/stm32-monitor/SKILL.md` stays byte-identical to the accepted base and is never executed as release behavior.
- No fixed port, direct PyOCD, automatic install from the Monitor Skill, named preset, auto-connect, auto-sampling, AI snapshot/analyze, diagnostics, host/target test, remote request, CI, collaboration manifest, or dispatch automation is added.
- README, the 0.5–0.6 phase plan, roadmap, active Skills, assets, versions, and product code all precede the final evidence `CODE_HEAD`; the tracked implementation report is outside this packet.

## Static Security Matrix

Task 4 tests every row through a real `MonitorService` using the committed Task 3 resources; a peer seam is allowed only in tests. All rejection bodies are fixed and contain no request value.

| Request | Peer / Host / Origin / budget | Expected result |
|---|---|---|
| `GET /` | `127.0.0.1`; exact `127.0.0.1:<bound-port>`; Origin absent; within budget | `200`, index, `Cache-Control: no-store`, full security headers |
| `HEAD /` | same | `200`, empty body, GET-equivalent headers and content length |
| `GET` or `HEAD /assets/<exact manifest route>` | same, or exact Origin `http://127.0.0.1:<bound-port>` | `200`, exact MIME/ETag, immutable cache, full security headers |
| exact index/asset | peer not exact IPv4 loopback | fixed `403` |
| exact index/asset | Host is `localhost`, IPv6, lacks port, or has another port | fixed `403` |
| exact index/asset | Origin is `null`, `http://localhost:<port>`, remote, or another loopback port | fixed `403` |
| exact index/asset | encoded header total exceeds `1_048_576` bytes | fixed `431` |
| `/assets/../auth.py`, encoded traversal, slash/backslash variants, unlisted or malformed asset | otherwise valid boundary | fixed empty `404`; no reflected route |
| `GET /api/v1/status` without API credentials | valid static boundary | API `401/403`; never index/assets |
| unknown `/api/v1/*` or non-GET static method | any | existing bounded API/method error; never SPA fallback |

Every successful HTML/asset response has this exact dynamic CSP, with `<bound-port>` replaced only by the actual listener port:

```text
default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' ws://127.0.0.1:<bound-port>; worker-src 'none'; child-src 'none'; media-src 'none'
```

It also has `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`, and `Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=(), serial=(), payment=()`. CSP must contain no `*`, `unsafe-inline`, `unsafe-eval`, remote origin, `data:` script, or `blob:` worker.

## Packaging Contract

| Layer | Exact contents and limits |
|---|---|
| committed package resources | `ui_dist/index.html`, `ui_dist/.vite/manifest.json`, and only manifest-referenced `ui_dist/assets/<content-hashed filename>` files |
| byte limits | index <=256 KiB; manifest <=256 KiB; each asset <=4 MiB; entire raw tree <=8 MiB; gzip initial JS <=450 KiB; gzip CSS <=50 KiB |
| forbidden output | source maps, remote URLs, inline script/style, `eval`, `new Function`, service worker, unlisted file, aggregate ECharts bundle |
| Python metadata | explicit `stm32_monitor = ["ui_dist/index.html", "ui_dist/.vite/manifest.json", "ui_dist/assets/*"]`; no dynamic Node build hook |
| wheel output | `stm32_monitor-0.5.0-py3-none-any.whl` contains every exact resource in RECORD; Toolkit wheel remains `stm32_toolkit-0.5.0-py3-none-any.whl` |
| reproducibility | Node script builds to one fresh repository-external directory and byte-compares relative names and contents with committed `ui_dist`; two verify runs leave Git unchanged |

## Unified Version Path Matrix

The version unit changes these active sources and their current-output assertions, and no other historical artifact:

| Surface | Exact path/value |
|---|---|
| Toolkit distribution/package/CLI | `tools/stm32-toolkit/pyproject.toml`, `src/stm32_toolkit/__init__.py`, `src/stm32_toolkit/cli.py` = `0.5.0` |
| Monitor distribution/dependency/package/protocol | `tools/stm32-monitor/pyproject.toml`, `src/stm32_monitor/__init__.py`, `src/stm32_monitor/protocol.py` = `0.5.0`; dependency `stm32-toolkit==0.5.0` |
| Monitor runtime records/events | `tools/stm32-monitor/src/stm32_monitor/runtime.py` consumes `MONITOR_VERSION`; no current-version literal remains there |
| managed runtime | `bin/stm32-toolkit-mcp.cmd`, new `bin/stm32-monitor.cmd`, `bin/setup-stm32-env.ps1`, `skills/setup-stm32-env/SKILL.md` select `runtime/0.5.0` |
| Plugin/active workflow | `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` release descriptions, new `skills/stm32-monitor/SKILL.md`; exactly eight active Skills |
| documentation | `README.md`, `README_zh-CN.md`, 0.5–0.6 phase plan, complete roadmap |

Current-output assertions are updated in Monitor `test_cli.py`, `test_exports.py`, `test_models.py`, `test_package_boundary.py`, `test_runtime.py`, and `test_service.py`, plus Toolkit `test_cli.py`, `test_build_runner.py`, `test_hardware_workflows.py`, `test_mcp_migration_build.py`, and only the current-generated assertions in `test_migration_plan.py`. Setup and Plugin assertions are updated in their own units. Deliberately malformed/previous-version values in `test_generation.py`, `test_probe_protocol.py`, `test_result.py`, and the invalid-input fixture in `test_migration_plan.py` remain unchanged.

---

### Task 1: Exact Package-Resource Allowlist and Security Headers

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/ui_assets.py`
- Create: `tools/stm32-monitor/tests/test_ui_assets.py`

**Interfaces:**

- `UiAssets.load(root: Traversable | None = None) -> UiAssets` reads `ui_dist` package resources; the optional root is a test seam, not a runtime path parameter.
- `UiAssets.response(route: str, port: int, *, head: bool = False) -> web.Response` performs a dictionary lookup only.
- `UiAssetEntry` stores route, package-relative name, immutable bytes, exact MIME, quoted SHA-256 ETag, and cache policy.

- [ ] **Step 1: Write the failing allowlist/header tests.** Add fixture `_write_dist(tmp_path)` with one `index.html`, one Vite manifest entry, `assets/index-A1b2C3d4.js`, and `assets/index-E5f6G7h8.css`. Add the following base case and parameterize traversal with `../`, `%2e%2e`, `%2f`, `%5c`, doubled separators, an unknown hash, and `/api/v1/status`; also assert exact MIME, quoted SHA-256 ETag, cache headers, full CSP/security headers, and HEAD parity. Keep size-limit cases out of this unit.

  ```python
  def test_allowlist_never_resolves_or_reflects_request_paths(tmp_path: Path) -> None:
      from stm32_monitor.ui_assets import UiAssets
      assets = UiAssets.load(_write_dist(tmp_path))
      ok = assets.response("/assets/index-A1b2C3d4.js", 43125)
      assert ok.status == 200
      assert ok.headers["Content-Type"] == "text/javascript; charset=utf-8"
      assert ok.headers["Cache-Control"] == "public, max-age=31536000, immutable"
      assert ok.headers["ETag"] == '"' + hashlib.sha256(ok.body).hexdigest() + '"'
      denied = assets.response("/assets/../auth.py", 43125)
      assert denied.status == 404 and denied.body == b""
      assert "auth.py" not in str(denied.headers)
  ```

- [ ] **Step 2: Run RED.** From `$repoRoot`, run `& $python312 -m pytest tools/stm32-monitor/tests/test_ui_assets.py -k "allowlist or header or head" -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL because `stm32_monitor.ui_assets` does not exist.

- [ ] **Step 3: Implement only the exact immutable lookup.** Define exact MIME entries for `.js`, `.css`, `.svg`, `.png`, `.jpg`/`.jpeg`, `.webp`, and `.woff2`; reject `.map` and any manifest filename not matching `assets/<name>-<at-least-8-alphanumeric-or-_ hash>.<allowed extension>`. Parse the Vite records' `file`, `css`, and `assets` members, load bytes into immutable entries, map only `/` and `/assets/...`, and use this response core:

  ```python
  _CSP = ("default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
          "form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
          "font-src 'self'; connect-src 'self' ws://127.0.0.1:{port}; worker-src 'none'; "
          "child-src 'none'; media-src 'none'")
  _COMMON = {
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Resource-Policy": "same-origin",
      "Permissions-Policy": "camera=(), microphone=(), geolocation=(), usb=(), serial=(), payment=()",
  }

  def response(self, route: str, port: int, *, head: bool = False) -> web.Response:
      entry = self._entries.get(route)
      if entry is None:
          return web.Response(status=404, body=b"")
      headers = dict(_COMMON)
      headers.update({"Content-Security-Policy": _CSP.format(port=port),
                      "Content-Type": entry.mime, "ETag": entry.etag,
                      "Cache-Control": entry.cache_control,
                      "Content-Length": str(len(entry.body))})
      return web.Response(status=200, body=b"" if head else entry.body, headers=headers)
  ```

  Index uses `no-store`; every allowlisted content-hashed asset uses `public, max-age=31536000, immutable`. Do not expose a method that accepts a filesystem path from a request.

- [ ] **Step 4: Run GREEN.** Repeat Step 2, then run `& $python310 -m pytest tools/stm32-monitor/tests/test_ui_assets.py -k "allowlist or header or head" -q -p no:cacheprovider --basetemp $taskTemp310`. Expected: both PASS.

- [ ] **Step 5: Commit the allowlist unit.** Run `git add tools/stm32-monitor/src/stm32_monitor/ui_assets.py tools/stm32-monitor/tests/test_ui_assets.py` and `git commit -m "feat(STM32TK-0502): allowlist bundled UI resources"`.

### Task 2: Manifest Integrity and Static Size Ceilings

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/ui_assets.py`
- Modify: `tools/stm32-monitor/tests/test_ui_assets.py`

**Interfaces:**

- Produces `UiAssetInventory(index_bytes: int, manifest_bytes: int, total_bytes: int, routes: tuple[str, ...])`.
- `UiAssets.verify_tree() -> UiAssetInventory` validates the already-read in-memory resource tree; it does not read resources a second time.
- `UiAssets.load()` calls `verify_tree()` before returning, so invalid resources fail service construction before routing.

- [ ] **Step 1: Write the independent failing integrity/limit tests.** Build fixtures exactly at and one byte over 256 KiB index, 256 KiB manifest, 4 MiB single asset, and 8 MiB total. Add missing manifest, invalid JSON/object shape, duplicate route, duplicate manifest filename, unlisted resource, absent listed resource, path outside `assets/`, and non-regular nested resource rows. Assert `UiAssets.load()` raises only `UiAssetError("Monitor UI assets are invalid")`; do not route a traversal request in this unit.

  ```python
  @pytest.mark.parametrize("field,limit", [
      ("index", 256 * 1024), ("manifest", 256 * 1024),
      ("asset", 4 * 1024 * 1024), ("total", 8 * 1024 * 1024),
  ])
  def test_static_limits_accept_boundary_and_reject_one_more(tmp_path, field, limit):
      exact = _write_sized_dist(tmp_path / "exact", field, limit)
      assert UiAssets.load(exact).verify_tree().total_bytes <= 8 * 1024 * 1024
      over = _write_sized_dist(tmp_path / "over", field, limit + 1)
      with pytest.raises(UiAssetError, match="^Monitor UI assets are invalid$"):
          UiAssets.load(over)
  ```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-monitor/tests/test_ui_assets.py -k "tree or manifest or limit or unlisted" -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL because `verify_tree` and `UiAssetInventory` are absent.

- [ ] **Step 3: Implement the in-memory inventory check.** Make `load()` recursively read each package resource exactly once into `Mapping[str, bytes]`, parse the manifest from that mapping, create the allowlist, then call this bounded check before returning:

  ```python
  def verify_tree(self) -> UiAssetInventory:
      index = self._files.get("index.html")
      manifest = self._files.get(".vite/manifest.json")
      if index is None or manifest is None or len(index) > 256*1024 or len(manifest) > 256*1024:
          raise UiAssetError("Monitor UI assets are invalid")
      total = 0
      expected = {"index.html", ".vite/manifest.json", *(e.resource for e in self._entries.values() if e.route != "/")}
      if set(self._files) != expected:
          raise UiAssetError("Monitor UI assets are invalid")
      for name, body in self._files.items():
          if name.startswith("assets/") and len(body) > 4*1024*1024:
              raise UiAssetError("Monitor UI assets are invalid")
          total += len(body)
          if total > 8*1024*1024:
              raise UiAssetError("Monitor UI assets are invalid")
      return UiAssetInventory(len(index), len(manifest), total, tuple(sorted(self._entries)))
  ```

  Reject duplicate manifest output before converting to a set. Catch JSON/Unicode/type/resource errors and raise the one public `UiAssetError` without a path or parser detail.

- [ ] **Step 4: Run GREEN.** Repeat Step 2 and then all `test_ui_assets.py` under both `$python312` and `$python310`. Expected: PASS, including the independent Task 1 traversal selectors.

- [ ] **Step 5: Commit the inventory unit.** Add the two listed files and commit `feat(STM32TK-0502): bound bundled UI inventory`.

### Task 3: Reproducible Committed Dist and Explicit Wheel Package Data

**Files:**

- Create: `tools/stm32-monitor/ui/scripts/verify-dist.mjs`
- Create: `tools/stm32-monitor/tests/test_ui_dist.py`
- Create/update from production build: `tools/stm32-monitor/src/stm32_monitor/ui_dist/index.html`, `.vite/manifest.json`, `assets/*`
- Modify: `tools/stm32-monitor/ui/package.json`, `vite.config.ts`
- Modify: `tools/stm32-monitor/pyproject.toml`
- Modify: `tools/stm32-monitor/tests/test_package_boundary.py`

**Interfaces:**

- `npm run build` emits the only committed dist at `../src/stm32_monitor/ui_dist` with manifest and no sourcemap.
- `npm run verify:dist` invokes `node scripts/verify-dist.mjs`; it rebuilds to an OS temp directory and byte-compares names and contents.
- setuptools includes only the three explicit package-data patterns in the Packaging Contract.

- [ ] **Step 1: Write failing dist/wheel tests.** In `test_ui_dist.py`, walk committed files, parse the manifest, assert exact inventory, no `.map`, no remote URL/inline script/style/service-worker/eval/new-Function token, gzip budgets, raw size budgets, and no aggregate `echarts` source import. Extend `test_package_boundary.py` to build a wheel with a fake `node`/`npm` marker prepended to PATH, assert the marker is untouched, and assert wheel RECORD contains index, manifest, and every exact asset. Base assertions:

  ```python
  def test_wheel_contains_only_verified_ui_resources(built_monitor_wheel: Path) -> None:
      with zipfile.ZipFile(built_monitor_wheel) as wheel:
          names = set(wheel.namelist())
          resources = {n for n in names if n.startswith("stm32_monitor/ui_dist/")}
          assert "stm32_monitor/ui_dist/index.html" in resources
          assert "stm32_monitor/ui_dist/.vite/manifest.json" in resources
          assets = {n for n in resources if n.startswith("stm32_monitor/ui_dist/assets/")}
          assert assets, "release wheel must contain at least one manifest-referenced asset"
          expected = {"stm32_monitor/ui_dist/" + p.relative_to(UI_DIST).as_posix()
                      for p in UI_DIST.rglob("*") if p.is_file()}
          assert resources == expected
          record_name = next(n for n in names if n.endswith(".dist-info/RECORD"))
          record = wheel.read(record_name).decode("utf-8")
          assert all(name in record for name in expected)
  ```

- [ ] **Step 2: Run RED.** From `$uiRoot`, run `& $npm run verify:dist`; from `$repoRoot`, run `& $python312 -m pytest tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/tests/test_package_boundary.py::test_wheel_contains_only_verified_ui_resources -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL because verify script and committed dist are absent; the wheel node must independently fail unless index, manifest, and at least one exact asset are present, so an empty resource set cannot pass vacuously.

- [ ] **Step 3: Implement deterministic build/compare and explicit data.** Set Vite `build.manifest=true`, `sourcemap=false`, deterministic hashed `entryFileNames/chunkFileNames/assetFileNames`, and output only to `../src/stm32_monitor/ui_dist`. Add package scripts `"build":"vite build"` and `"verify:dist":"node scripts/verify-dist.mjs"`. The verifier uses `mkdtemp(join(tmpdir(), "stm32-monitor-dist-"))`, calls Vite's programmatic `build({root:uiRoot,build:{outDir:temp,emptyOutDir:true}})`, recursively sorts relative names, compares `Buffer.equals`, and removes only that verified temp directory in `finally`; it never derives a checkout outside `import.meta.url`. Add:

  ```toml
  [tool.setuptools.package-data]
  stm32_monitor = ["ui_dist/index.html", "ui_dist/.vite/manifest.json", "ui_dist/assets/*"]
  ```

  Run the absolute `$npm` build once to create the committed tree. Python metadata has no build command or Node hook.

- [ ] **Step 4: Run GREEN twice without drift.** From `$uiRoot`, run `& $npm ci; & $npm run build; & $npm run verify:dist; & $npm run verify:dist`. From `$repoRoot`, run the full Step 2 Python command. Capture `git status --short` before and after the two verify runs and require equality. Expected: PASS, byte-identical rebuild, no Node marker, no scratch output in Git.

- [ ] **Step 5: Commit the dist/package unit.** Add the verifier, `package.json`, lockfile only if the script entry changes it, Vite config, exact `ui_dist`, Monitor `pyproject.toml`, and the two named Python tests. Commit `feat(STM32TK-0502): package reproducible monitor UI assets`.

### Task 4: Real aiohttp Static Routes and Request Boundary

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/service.py`
- Modify: `tools/stm32-monitor/tests/test_service.py`

**Interfaces:**

- Consumes frontend-core `MonitorAuth` only for its existing header-budget primitive and API authorization; it does not change `auth.py`.
- Consumes the real committed `ui_dist` produced by Task 3; `MonitorService.start()` requires no asset monkeypatch or ambient build output.
- `MonitorService._static(request: web.Request) -> web.Response` serves `/` or the exact `/assets/{tail}` lookup.
- `MonitorService` loads and validates one `UiAssets` instance during startup and clears it during owned cleanup.

- [ ] **Step 1: Write the failing real-service matrix.** Start a default real random-port service against Task 3's committed `ui_dist` and execute every row in the Static Security Matrix; do not monkeypatch `UiAssets.load`. For peer rejection only, invoke the handler with the existing request seam rather than binding a non-loopback socket. Assert `GET/HEAD`, fixed 403/431, fixed empty traversal 404, no route reflection, API unauthenticated denial, no `/api` fallback, and this exact CSP equality:

  ```python
  expected_csp = (
      "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
      "form-action 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
      "font-src 'self'; connect-src 'self' "
      f"ws://127.0.0.1:{endpoint.port}; worker-src 'none'; child-src 'none'; media-src 'none'"
  )
  assert index.headers["Content-Security-Policy"] == expected_csp
  assert (await client.get(endpoint.url + "/api/v1/status")).status in {401, 403}
  assert (await client.get(endpoint.url + "/assets/../auth.py")).status == 404
  ```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-monitor/tests/test_service.py -k "static or api_never_falls_back" -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL because no static routes exist; default startup succeeds because Task 3 already committed the package resources.

- [ ] **Step 3: Add only the exact routes and fail-closed boundary.** In `_start_locked`, load `UiAssets` before runner setup, register `application.router.add_get("/", self._static)` and `application.router.add_get("/assets/{asset:.*}", self._static)` before API routes, and never call `add_static`. The handler performs these checks in order and returns fixed bodies:

  ```python
  async def _static(self, request: web.Request) -> web.Response:
      endpoint, auth, assets = self._endpoint, self._auth, self._ui_assets
      if endpoint is None or auth is None or assets is None:
          return web.Response(status=503, body=b"")
      try:
          auth.require_header_budget(tuple(request.headers.items()))
      except MonitorAuthError as error:
          return web.Response(status=error.status, body=b"")
      origin = request.headers.get("Origin")
      if request.remote != "127.0.0.1" or request.host != f"127.0.0.1:{endpoint.port}":
          return web.Response(status=403, body=b"")
      if origin is not None and origin != endpoint.url:
          return web.Response(status=403, body=b"")
      route = "/" if request.path == "/" else "/assets/" + request.match_info["asset"]
      return assets.response(route, endpoint.port, head=request.method == "HEAD")
  ```

  Assign `self._ui_assets` before accepting traffic and reset it in `_cleanup_runner`. Do not catch API routes, alter `_protocol_errors`, or accept a caller-supplied safe flag.

- [ ] **Step 4: Run GREEN with regression checks.** Run `& $python312 -m pytest tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_auth.py tools/stm32-monitor/tests/test_ui_assets.py -q -p no:cacheprovider --basetemp $taskTemp`, then the same suites with `$python310`. Set `PYTHONPYCACHEPREFIX` to an external directory and run `& $python312 -m compileall -q tools/stm32-monitor/src/stm32_monitor`. Expected: PASS against the committed Task 3 resources and no repository write.

- [ ] **Step 5: Commit the service unit.** Add only `service.py` and `test_service.py`; commit `feat(STM32TK-0502): serve UI through the monitor listener`.

### Task 5: Side-Effect-Free `serve` and Explicit Human `open`

**Files:**

- Create: `tools/stm32-monitor/tests/test_launcher.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/cli.py`
- Modify: `tools/stm32-monitor/tests/test_cli.py`

**Interfaces:**

- Existing `serve --project ... --data-root ... --session-id ... --json` retains its parser, one-line JSON stdout, foreground wait, cleanup, and opener count zero.
- New `open --project ... --data-root ... [--session-id ...]` is the only human/browser command.
- `main(..., _browser_open: Callable[[str], bool] = webbrowser.open) -> int` is the test seam.

- [ ] **Step 1: Write failing launcher tests with an ordered fake runtime.** Record `start`, `open`, `wait`, and `stop`; assert exact order, exactly one access URL passed only after successful start, empty success stdout/stderr, no token/access URL in output, and `serve --json` opener count zero. Add omitted-session regex `monitor-[0-9a-f]{32}`, explicit-session preservation, opener false/raise cleanup with fixed `MONITOR_BROWSER_OPEN_FAILED`, wait cancellation cleanup, Ctrl-C 130, no `--open-browser`, and no persisted session/token/access URL. Base case:

  ```python
  def test_open_starts_then_opens_once_and_never_writes_url(tmp_path: Path) -> None:
      events, output, errors = [], io.StringIO(), io.StringIO()
      runtime = OrderedRuntime(events)
      code = main(["open", "--project", str(_project(tmp_path)),
                   "--data-root", str(tmp_path / "data")],
                  _runtime_factory=lambda: runtime,
                  _browser_open=lambda url: events.append(("open", url)) or True,
                  _stdout=output, _stderr=errors)
      assert code == 0
      assert [event[0] if isinstance(event, tuple) else event for event in events] == ["start", "open", "wait", "stop"]
      assert events[1] == ("open", runtime.endpoint.access_url)
      assert output.getvalue() == errors.getvalue() == ""
      assert runtime.endpoint.token not in output.getvalue() + errors.getvalue()
  ```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-monitor/tests/test_launcher.py::test_open_starts_then_opens_once_and_never_writes_url tools/stm32-monitor/tests/test_cli.py -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL because `open` and `_browser_open` are absent.

- [ ] **Step 3: Implement only the matching parser and owned coroutine.** Import `secrets` and `webbrowser`; add the `open` parser with optional session. Generate `"monitor-" + secrets.token_hex(16)` only when absent. Keep `_serve` unchanged and add:

  ```python
  async def _open(config: MonitorConfig, runtime: object,
                  browser_open: Callable[[str], bool]) -> int:
      endpoint = await runtime.start(config)
      try:
          try:
              opened = browser_open(endpoint.access_url)
          except Exception:
              opened = False
          if opened is not True:
              raise MonitorRuntimeError("MONITOR_BROWSER_OPEN_FAILED", "Monitor browser failed to open")
          await runtime.wait_closed()
          return 0
      finally:
          await runtime.stop()
  ```

  Dispatch `serve` to `_serve` and `open` to `_open`. Existing bounded exception mapping remains; `open` success writes nothing, and no detached process, clipboard, shell history, or token file is introduced.

- [ ] **Step 4: Run GREEN on both Python versions.** Run all `test_launcher.py` and `test_cli.py` first with `$python312`, then `$python310`, with separate external basetemps. Expected: PASS; serve JSON snapshots remain byte-compatible except the version change deliberately deferred to Task 6.

- [ ] **Step 5: Commit the CLI unit.** Add the three listed files and commit `feat(STM32TK-0502): add explicit monitor open command`.

### Task 6: Unified Python/Protocol Version `0.5.0`

**Files:**

- Create: `tools/stm32-toolkit/tests/test_0502_release_version.py`
- Modify: the Toolkit and Monitor product/version paths in the Unified Version Path Matrix
- Modify: the exact current-output test files listed below that matrix; do not mass-replace fixtures

**Interfaces:**

- Toolkit package `__version__`, Toolkit CLI version, Monitor package `__version__`, `MONITOR_VERSION`, both project metadata versions, runtime record/event version, and Monitor's exact Toolkit dependency all agree on `0.5.0`.
- Protocol identifiers remain `stm32-toolkit/1`, `stm32-toolkit-probe/1`, and `stm32-toolkit-monitor/1`; only SemVer fields change.

- [ ] **Step 1: Write the failing centralized version test.** Parse TOML, import both packages and protocol/runtime modules from current sources, call Toolkit `version`, and inspect current dependency/runtime literals. Do not inspect Plugin/CMD/setup/docs in this unit. Use:

  ```python
  def test_python_protocol_release_surfaces_are_exact_0_5_0() -> None:
      toolkit = tomllib.loads((ROOT/"tools/stm32-toolkit/pyproject.toml").read_text("utf-8"))
      monitor = tomllib.loads((ROOT/"tools/stm32-monitor/pyproject.toml").read_text("utf-8"))
      assert toolkit["project"]["version"] == stm32_toolkit.__version__ == "0.5.0"
      assert monitor["project"]["version"] == stm32_monitor.__version__ == MONITOR_VERSION == "0.5.0"
      assert monitor["project"]["dependencies"] == ["stm32-toolkit==0.5.0", "aiohttp>=3.9,<4"]
      assert toolkit_cli.main(["version"]) == 0
      assert '"0.4.0"' not in (ROOT/"tools/stm32-monitor/src/stm32_monitor/runtime.py").read_text("utf-8")
  ```

  Also add `test_release_wheel_filename_is_0_5_0` beside the Task 3 wheel fixture: build without Node and assert the exact name `stm32_monitor-0.5.0-py3-none-any.whl` and exact `Version: 0.5.0` metadata.

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-toolkit/tests/test_0502_release_version.py tools/stm32-monitor/tests/test_package_boundary.py::test_release_wheel_filename_is_0_5_0 -q -p no:cacheprovider --basetemp $taskTemp`. Expected: both the centralized surface assertion and the exact wheel filename/metadata node FAIL on `0.4.0`.

- [ ] **Step 3: Change only current version authorities and current-output assertions.** Set both pyprojects and package versions to `0.5.0`, Monitor dependency to `stm32-toolkit==0.5.0`, Monitor protocol constant to `0.5.0`, Toolkit CLI `_VERSION` to imported package `__version__`, and runtime comparisons/records/events to imported `MONITOR_VERSION`. Update current-output assertions in Monitor `test_cli.py`, `test_exports.py`, `test_models.py`, `test_package_boundary.py`, `test_runtime.py`, `test_service.py`; update Toolkit `test_cli.py`, `test_build_runner.py`, `test_hardware_workflows.py`, `test_mcp_migration_build.py`, and the current-generated assertions at `test_migration_plan.py` while retaining its invalid-input `0.4.0` fixture. Leave `test_generation.py`, `test_probe_protocol.py`, and `test_result.py` unchanged.

- [ ] **Step 4: Run GREEN and focused current-output regressions.** Repeat the exact Step 2 command; run the six named Monitor files and Toolkit `test_cli.py`, `test_build_runner.py`, `test_hardware_workflows.py`, `test_mcp_migration_build.py`, `test_migration_plan.py` under `$python312`. Repeat `test_0502_release_version.py`, Monitor `test_cli.py/test_runtime.py/test_service.py`, and Toolkit `test_cli.py` under `$python310`. Finally run Task 3's wheel RECORD node. Expected: all PASS with exact `0.5.0` filenames.

- [ ] **Step 5: Commit the version unit.** Add only the product authorities and named active tests; commit `feat(STM32TK-0502): align Python and protocol release versions`.

### Task 7: Fixed Managed-Runtime CMD Launchers

**Files:**

- Create: `bin/stm32-monitor.cmd`
- Modify: `bin/stm32-toolkit-mcp.cmd`
- Modify: `tools/stm32-monitor/tests/test_launcher.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`

**Interfaces:**

- Monitor CMD executes exact managed Python as `-m stm32_monitor` and forwards unchanged arguments.
- Toolkit CMD executes the same exact managed Python as `-m stm32_toolkit.mcp_server`.
- Both fail with exit 2 when `CLAUDE_PLUGIN_DATA` or the versioned interpreter is absent and preserve the child exit code otherwise.

- [ ] **Step 1: Write failing real-CMD tests and isolate the launcher layout node.** Build a fake external `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0` venv and write tiny `stm32_monitor.__main__`/`stm32_toolkit.mcp_server` modules into that venv's site-packages; each records `sys.executable` and `sys.argv[1:]` then exits a chosen code. Invoke the real CMD with arguments containing spaces and metacharacters as quoted individual argv, and assert only the managed interpreter ran, argv is unchanged, and the child code is preserved. Run missing-env/missing-runtime cases with marker executables named `python`, `python3`, `py`, and `uv` earlier on PATH and assert no marker exists. In `test_plugin_layout.py`, update the three existing `test_launcher_*` fixtures and expected missing-runtime text from `runtime/0.4.0` to `runtime/0.5.0`; remove `test_unified_0_4_0_runtime_version_across_launcher_setup_and_skill` and move only its two launcher assertions into `test_release_launchers_select_only_managed_runtime_0_5_0`. Setup-Skill assertions belong to Task 8 and manifest/version assertions belong to Task 9.

  ```python
  assert recorded["executable"] == str(runtime / "Scripts" / "python.exe")
  assert recorded["argv"] == ["open", "--project", str(project_with_spaces),
                               "--data-root", str(data_with_spaces)]
  assert result.returncode == 37
  assert not any((markers / name).exists() for name in ("python", "python3", "py", "uv"))

  def test_release_launchers_select_only_managed_runtime_0_5_0() -> None:
      monitor = (REPO_ROOT / "bin/stm32-monitor.cmd").read_text("utf-8")
      toolkit = LAUNCHER.read_text("utf-8")
      assert r"runtime\0.5.0\Scripts\python.exe" in monitor
      assert r"runtime\0.5.0\Scripts\python.exe" in toolkit
  ```

- [ ] **Step 2: Run RED.** On Windows run `& $python312 -m pytest tools/stm32-monitor/tests/test_launcher.py -k "managed_cmd" -q -p no:cacheprovider --basetemp $taskTempMonitor`, then run `& $python312 -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py::test_launcher_reports_missing_environment_without_interpreter_fallback tools/stm32-toolkit/tests/test_plugin_layout.py::test_launcher_reports_missing_versioned_runtime_without_interpreter_fallback tools/stm32-toolkit/tests/test_plugin_layout.py::test_launcher_forwards_arguments_and_preserves_runtime_exit_code tools/stm32-toolkit/tests/test_plugin_layout.py::test_release_launchers_select_only_managed_runtime_0_5_0 -q -p no:cacheprovider --basetemp $taskTempToolkit`. Expected: launcher-only nodes FAIL because Monitor CMD is absent and Toolkit CMD still names 0.4.0; no setup-Skill or manifest node runs in this unit.

- [ ] **Step 3: Implement the two fixed selectors.** Both scripts first check `CLAUDE_PLUGIN_DATA`, set `...\runtime\0.5.0\Scripts\python.exe`, check that exact leaf, emit a fixed setup-Skill instruction on failure, invoke the declared `-m` module with `%*`, store `%ERRORLEVEL%`, and `exit /b` with it. The Monitor body is exactly this shape:

  ```bat
  @echo off
  setlocal
  if not defined CLAUDE_PLUGIN_DATA (
    >&2 echo stm32-monitor: CLAUDE_PLUGIN_DATA is not set. Run /stm32-toolkit:setup-stm32-env, then retry.
    exit /b 2
  )
  set "STM32_MONITOR_RUNTIME=%CLAUDE_PLUGIN_DATA%\runtime\0.5.0\Scripts\python.exe"
  if not exist "%STM32_MONITOR_RUNTIME%" (
    >&2 echo stm32-monitor: runtime/0.5.0/Scripts/python.exe is missing under CLAUDE_PLUGIN_DATA. Run /stm32-toolkit:setup-stm32-env, then retry.
    exit /b 2
  )
  "%STM32_MONITOR_RUNTIME%" -m stm32_monitor %*
  set "STM32_MONITOR_EXIT_CODE=%ERRORLEVEL%"
  exit /b %STM32_MONITOR_EXIT_CODE%
  ```

  Apply the same version-only selection to Toolkit CMD; add no fallback or command-string evaluation.

- [ ] **Step 4: Run GREEN plus real help smoke.** Repeat both Step 2 commands under `$python312`, then under `$python310` with distinct external basetemps. In the prepared fake managed-runtime environment run `& $cmdExe /d /c bin\stm32-monitor.cmd --help` and `& $cmdExe /d /c bin\stm32-toolkit-mcp.cmd --help`. Expected: launcher-only nodes PASS, with exact interpreter evidence and no ambient marker; Task 8/9 nodes remain outside this gate.

- [ ] **Step 5: Commit the CMD unit.** Add the four listed files and commit `feat(STM32TK-0502): bind launchers to managed runtime 0.5.0`.

### Task 8: Atomic Setup/Repair Installs Toolkit, Probe, Monitor, and UI

**Files:**

- Modify: `bin/setup-stm32-env.ps1`
- Modify: `skills/setup-stm32-env/SKILL.md`
- Modify: `tools/stm32-toolkit/tests/test_setup_runtime.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Modify: `tools/stm32-monitor/tests/test_runtime.py`

**Interfaces:**

- Current runtime is `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0`; immediately previous runtime is `0.4.0`.
- CHECK is read-only. A present healthy or broken 0.4.0 runtime reports `broken` and recommends `Repair` without mutation.
- Bootstrap/Repair stage both local packages, Toolkit probe extra, validate exact distributions/doctor/Monitor CLI/UI resources, then atomically promote; failure restores/quarantines according to existing path-safety rules.

- [ ] **Step 1: Write failing promotion/validation tests and the setup-only layout node.** Update current-runtime fixtures to 0.5.0 and add a fake local Monitor wheel containing `stm32_monitor/__init__.py`, `__main__.py`, `ui_dist/index.html`, and `.vite/manifest.json`. Add two parameter rows for healthy and broken 0.4.0; CHECK must recommend Repair and not mutate, Repair must quarantine a path beginning `0.4.0-`, promote one 0.5.0 runtime, and validate both distributions. Add Monitor missing/wrong version/missing manifest/unreadable asset failures, staging cleanup/rollback, no Node/node_modules, hostile Python env removal, and project/repository snapshot immutability. In `test_plugin_layout.py`, add `test_release_setup_skill_and_helper_select_runtime_0_5_0`, containing the setup-Skill/helper assertions removed from the accepted-base unified test; it asserts the helper's exact current assignment and the Skill's exact managed-runtime path without inspecting either launcher or the Plugin manifest.

  ```python
  @pytest.mark.parametrize("previous_state", ["healthy", "broken"])
  def test_repair_promotes_0_4_to_exact_0_5_with_monitor_assets(tmp_path, previous_state):
      plugin_root, plugin_data, project = _release_fixture(tmp_path, previous_state)
      checked = _run_helper("Check", plugin_root, plugin_data, project)
      assert json.loads(checked.stdout)["recommendedMode"] == "Repair"
      repaired = _run_helper("Repair", plugin_root, plugin_data, project)
      assert repaired.returncode == 0, repaired.stderr
      runtime = plugin_data / "runtime" / "0.5.0"
      assert _installed_version(runtime, "stm32-toolkit") == "0.5.0"
      assert _installed_version(runtime, "stm32-monitor") == "0.5.0"
      assert _resource(runtime, "stm32_monitor/ui_dist/.vite/manifest.json").is_file()
      assert any(p.name.startswith("0.4.0-") for p in (plugin_data/"runtime/.quarantine").iterdir())

  def test_release_setup_skill_and_helper_select_runtime_0_5_0() -> None:
      helper = SETUP_HELPER.read_text("utf-8")
      skill = SETUP_SKILL.read_text("utf-8")
      assert '$RuntimeVersion = "0.5.0"' in helper
      assert "runtime/0.5.0" in skill.replace("\\", "/")
  ```

- [ ] **Step 2: Run the complete declared RED matrix.** From `$repoRoot`, run the complete setup file with `& $python312 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py -q -p no:cacheprovider --basetemp $taskTemp312`, then the complete same file with `$python310` and `$taskTemp310`. Run `& $python312 -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py::test_setup_skill_has_an_explicit_read_only_check_and_authorized_mutation_contract tools/stm32-toolkit/tests/test_plugin_layout.py::test_setup_skill_passes_inline_claude_paths_explicitly_without_ambient_variables tools/stm32-toolkit/tests/test_plugin_layout.py::test_release_setup_skill_and_helper_select_runtime_0_5_0 -q -p no:cacheprovider --basetemp $layoutTemp312`, and repeat those exact three nodes with `$python310`/`$layoutTemp310`. Expected: the new 0.5 promotion/asset rows and setup-only layout node FAIL because setup selects 0.4.0 and installs only Toolkit; every pre-existing row still runs.

- [ ] **Step 3: Implement exact 0.5 staging and validation.** Set `$RuntimeVersion = "0.5.0"` and `$PreviousRuntimeVersion = "0.4.0"`; resolve both `tools/stm32-toolkit` and `tools/stm32-monitor` below the explicit `PluginRoot`. CHECK chooses current if present, otherwise previous; previous always becomes a bounded broken/Repair result. Stage with one bounded pip invocation of `"${toolkitPackage}[probe]"` and `$monitorPackage`. Add an isolated Python validation script that requires `metadata.version("stm32-toolkit") == metadata.version("stm32-monitor") == "0.5.0"`, validates PyOCD range, and reads both `ui_dist/index.html` and `.vite/manifest.json` through `importlib.resources`. Run Toolkit `doctor --json` and Monitor `-m stm32_monitor --help`; only then quarantine previous/current broken runtime and atomically move staging. Preserve the existing redirect checks, bounded output, rollback, and project-read-only behavior.

- [ ] **Step 4: Run GREEN across both Python versions and all setup tests.** Repeat all four exact Step 2 commands. Then run `& $python312 -m pytest tools/stm32-monitor/tests/test_runtime.py -q -p no:cacheprovider --basetemp $runtimeTemp312` and the same with `$python310`/`$runtimeTemp310`. Expected: all complete setup files and setup-only layout nodes PASS; Plugin data contains no `node`/`node_modules`; repository and project snapshots are unchanged.

- [ ] **Step 5: Commit the setup unit.** Add the five listed files and commit `feat(STM32TK-0502): promote complete managed runtime atomically`.

### Task 9: Plugin Manifest, Eighth Active Skill, and Historical-Skill Separation

**Files:**

- Create: `skills/stm32-monitor/SKILL.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Read only: `requirements/follow-on-skills/stm32-monitor/SKILL.md`

**Interfaces:**

- Plugin standard discovery exposes exactly eight active Skills: the existing seven plus `stm32-monitor`.
- Active Monitor Skill obtains `stm32_project_context`, explains observation-only/no-auto-connect/no-auto-sampling behavior, waits for the user's explicit open request, then invokes the human `open` CMD with inline Claude paths.
- Historical requirement source remains a non-executable preserved input.

- [ ] **Step 1: Write failing manifest/active-Skill nodes without reopening launcher/setup tests.** Update `test_plugin_manifest_uses_standard_skill_discovery_and_version` to the exact 0.5.0 manifest/description and keep `test_marketplace_manifest_uses_a_supported_plugin_source` focused on the single marketplace entry. Rename `test_exactly_seven_release_skills_are_discovered_and_follow_on_sources_are_preserved` to `test_exactly_eight_release_skills_are_discovered_and_follow_on_sources_are_preserved`, change only its active discovered set to eight, and retain its accepted historical set. Add `test_active_monitor_skill_requires_explicit_managed_open` to read active and historical Monitor Skills separately; assert active contains context, explicit request, managed CMD `open`, inline project/plugin-data paths, and no `localhost:8888`, direct `pyocd`, `pip install`, named preset, auto-connect/start, AI snapshot/analyze, token printing, or historical file invocation. The Task 7 launcher node and Task 8 setup-only node are not modified. Also assert `git` preflight/final blob identity outside pytest.

  ```python
  assert discovered == {"setup-stm32-env", "migrate-keil", "configure-stm32-project",
                        "build-firmware", "flash-firmware", "debug-firmware", "read-var",
                        "stm32-monitor"}
  assert plugin["version"] == __version__ == "0.5.0"
  for phrase in ("stm32_project_context", "explicit request", "bin/stm32-monitor.cmd",
                 " open ", "${CLAUDE_PROJECT_DIR}", "${CLAUDE_PLUGIN_DATA}"):
      assert phrase in active
  for forbidden in ("localhost:8888", "pyocd list", "pip install", "motor_status",
                    "AI Analyze", "diagnostic session export"):
      assert forbidden.casefold() not in active.casefold()
  ```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py::test_plugin_manifest_uses_standard_skill_discovery_and_version tools/stm32-toolkit/tests/test_plugin_layout.py::test_marketplace_manifest_uses_a_supported_plugin_source tools/stm32-toolkit/tests/test_plugin_layout.py::test_exactly_eight_release_skills_are_discovered_and_follow_on_sources_are_preserved tools/stm32-toolkit/tests/test_plugin_layout.py::test_active_monitor_skill_requires_explicit_managed_open -q -p no:cacheprovider --basetemp $taskTemp312`, then repeat those exact four nodes with `$python310`/`$taskTemp310`. Expected: only manifest/marketplace/active-Skill nodes FAIL because the active Skill is absent and manifest is 0.4.0; launcher and setup nodes are not selected.

- [ ] **Step 3: Add the thin active Skill and update release descriptions.** Set Plugin manifest version to `0.5.0` and mention the offline project-isolated Monitor; update marketplace descriptions without adding a new plugin entry. Create the active Skill with this exact behavioral order:

  ````markdown
  ---
  name: stm32-monitor
  description: Use when a user explicitly asks to open the project-isolated STM32 Monitor UI.
  ---

  # Open STM32 Monitor

  1. Call `stm32_project_context` and show the current project and firmware identity. Stop on a non-ok result; never guess a project, target, ELF, SVD, address, or probe.
  2. Explain that the UI is observation-only, starts with zero presets, and will not connect a probe or start sampling automatically.
  3. Continue only for the user's explicit request to open this project's UI. Read-only context or a request to inspect facts is not launch authorization.
  4. Run the foreground human launcher:

     ```powershell
     & '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
     ```

  Keep the command in the foreground. Report only bounded launcher success/failure; never print, copy, persist, or log its fragment URL. Probe connect, group creation, and sampling remain explicit user actions in the page.
  ````

  Do not copy any historical requirement prose into active behavior.

- [ ] **Step 4: Run GREEN and prove historical immutability.** Repeat both exact Step 2 commands. Then run `git diff --exit-code $frontendCoreCodeHead -- requirements/follow-on-skills/stm32-monitor/SKILL.md` and compare `git rev-parse "HEAD:requirements/follow-on-skills/stm32-monitor/SKILL.md"` with `$historicalBlob` using case-sensitive equality. Expected: all four Plugin/Skill nodes PASS and exact blob equality; Task 7/8 nodes remain independently attributable to their earlier commits.

- [ ] **Step 5: Commit the Plugin/Skill unit.** Add only `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/stm32-monitor/SKILL.md`, and `test_plugin_layout.py`; commit `feat(STM32TK-0502): expose explicit monitor release skill`.

### Task 10: README, 0.5–0.6 Phase Plan, and Roadmap Before Evidence

**Files:**

- Create: `tools/stm32-toolkit/tests/test_0502_release_docs.py`
- Modify: `README.md`, `README_zh-CN.md`
- Modify: `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md`
- Modify: `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`

**Interfaces:**

- README describes the active 0.5.0 product, exactly eight Skills, explicit Monitor launch, zero presets, per-project isolation, verified CSV/JSONL, and 0.6 deferrals.
- Phase plan separates lean 0.5 Monitor from 0.6 host/target tests and diagnostics and removes AI snapshot/advanced dashboard/history/annotation work from 0.5.
- Roadmap splits the combined release row and keeps the 0.5 checkbox unchecked until the evidence plan records acceptance.

- [ ] **Step 1: Write failing exact documentation assertions.** Parse both README files, phase plan, roadmap, and active Skill. Assert `0.5.0`, eight named Skills, `stm32-monitor open`, managed runtime 0.5.0, zero presets, project isolation, explicit connect/start, CSV/JSONL, and a named `0.6.0` deferred section. Assert active 0.5 text contains none of `AI Analyze`, `diagnostic session export`, multi-run comparison, annotations, or full quality dashboard. Assert the phase plan says 0.6 cannot start before 0.5 acceptance, and roadmap has distinct 0.5/0.6 rows with 0.5 still unchecked.

  ```python
  def test_active_docs_describe_lean_0_5_and_defer_diagnostics() -> None:
      active = README.read_text("utf-8") + README_ZH.read_text("utf-8")
      for phrase in ("0.5.0", "stm32-monitor open", "runtime/0.5.0",
                     "zero presets", "CSV", "JSONL", "0.6.0"):
          assert phrase.casefold() in active.casefold()
      for forbidden in ("AI Analyze", "diagnostic session export"):
          assert forbidden.casefold() not in active.casefold()
      assert "0.5.0 |" in ROADMAP.read_text("utf-8")
      assert "0.6.0 |" in ROADMAP.read_text("utf-8")
      assert "before 0.5.0 acceptance" in PHASE.read_text("utf-8")
  ```

- [ ] **Step 2: Run RED.** Run `& $python312 -m pytest tools/stm32-toolkit/tests/test_0502_release_docs.py -q -p no:cacheprovider --basetemp $taskTemp`. Expected: FAIL on current 0.4/combined-plan text.

- [ ] **Step 3: Make the exact four-document release edits.** In both READMEs: promote the opening/current release and managed runtime to 0.5.0; list all eight Skills including `/stm32-toolkit:stm32-monitor`; document that the Skill calls foreground `stm32-monitor open`, the page starts with zero groups/presets and never auto-connects/samples, data remains below the per-workspace Plugin data tree, and only verified CSV/JSONL plus user group-schema export exist. Add a `Deferred to 0.6.0` section naming host/target tests, AI diagnostics/snapshot/analyze, advanced cross-run history, annotations/markers, and full quality dashboards. In the phase plan: replace stale FastAPI/Pydantic/static/AI-export 0.5 claims with the final aiohttp/Preact 0502 boundary, move those five advanced areas exclusively to 0.6, split 0.5 and 0.6 exit criteria, and state `0.6 implementation must not start before 0.5.0 acceptance`. In the roadmap: split the combined release row, mark accepted 0.4 progress accurately, leave 0.5 unchecked pending evidence, keep 0.6 unchecked, and update traceability so lean Monitor maps to 0.5 and tests/diagnostics map to 0.6. Do not claim Windows/Linux/hardware PASS and do not edit historical specs/reports/requirements.

- [ ] **Step 4: Run GREEN and active-surface scans.** Repeat Step 2 under both Python versions; run the full Plugin layout test. Run `rg -n 'AI Analyze|diagnostic session export|localhost:8888|motor_status|can_bus' README.md README_zh-CN.md skills docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md` and require no active 0.5 hit (0.6-only explanatory hits are reviewed and explicitly scoped). Re-run the historical blob comparison. Expected: PASS.

- [ ] **Step 5: Commit all pre-`CODE_HEAD` documentation.** Add only the two READMEs, phase plan, roadmap, and documentation test; commit `docs(STM32TK-0502): align runtime release and defer 0.6 work`.

## First Handoff: Runtime/Release Head to the Evidence Plan's Pre-Barrier Tasks

After Task 10, do not name `CODE_HEAD`. Prove the product packet is committed and clean:

```powershell
$runtimeStatus = @(& git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $runtimeStatus.Count -ne 0) { throw 'runtime/release handoff is not clean' }
$runtimeReleaseHead = (& git rev-parse HEAD).Trim()
if ($runtimeReleaseHead -notmatch '^[0-9a-f]{40}$') { throw 'runtime release head is not a full SHA' }
& git merge-base --is-ancestor $frontendCoreCodeHead $runtimeReleaseHead
if ($LASTEXITCODE -ne 0) { throw 'runtime release head does not descend from frontend core' }
& git diff --check "$acceptedBase..$runtimeReleaseHead"
if ($LASTEXITCODE -ne 0) { throw 'runtime release head diff check failed' }
$runtimeHistoricalBlob = (& git rev-parse "$runtimeReleaseHead`:requirements/follow-on-skills/stm32-monitor/SKILL.md").Trim()
if ($runtimeHistoricalBlob -cne $historicalBlob) { throw 'historical monitor requirement changed' }
```

Return exactly one `RuntimeReleaseReturnPacket` plus its separate `handoffSignatureSha256` to `2026-08-10-stm32tk-0502-browser-evidence.md` Tasks 1–4. The signature is excluded from the packet it signs; browser evidence consumes this exact schema without aliases or extra fields:

```ts
type RuntimeReleaseReturnPacket={schema:"stm32tk-0502-runtime-release/1";
 moduleId:"STM32TK-0502-MONITOR-UI-RELEASE";
 acceptedBase:"bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa";planBundleHead:string;
 frontendCoreCodeHead:string;runtimeReleaseHead:string;branch:string;worktreeClean:true;
 historicalMonitorSkillBlob:string;remoteActionPerformed:false};
```

Evaluate this after the checks. The controller pre-allocates a repository-external absolute file path in `$RuntimeReleasePacketPath`. The producer writes exactly the canonical UTF-8 JSON bytes without BOM or newline to that file and transmits `{RuntimeReleasePacketPath,handoffSignatureSha256}` as two separate transport values; it does not embed the signature into the packet or invent a JSON wrapper. The browser consumer must read and hash the original file bytes before parsing, require the exact declared field order/types, require re-encoding with `ConvertTo-Json -Compress` to be case-sensitively identical, and only then trust the packet. Browser Step 5 must invoke its audit function with values parsed from this verified file; that invocation remains owned by the browser-plan fixer.

```powershell
$runtimeBranch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $runtimeBranch -cne $branch) { throw 'runtime handoff branch changed' }
if (-not [IO.Path]::IsPathRooted($RuntimeReleasePacketPath)) { throw 'runtime packet path is not absolute' }
$RuntimeReleasePacketPath = [IO.Path]::GetFullPath($RuntimeReleasePacketPath)
if ($RuntimeReleasePacketPath.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'runtime packet file is inside the repository' }
$runtimePacketParent = Split-Path -Parent $RuntimeReleasePacketPath
if (-not (Test-Path -LiteralPath $runtimePacketParent -PathType Container)) { throw 'runtime packet parent is unavailable' }
$RuntimeReleaseReturnPacket = [ordered]@{
  schema='stm32tk-0502-runtime-release/1'
  moduleId='STM32TK-0502-MONITOR-UI-RELEASE'
  acceptedBase=$acceptedBase
  planBundleHead=$planBundleHead
  frontendCoreCodeHead=$frontendCoreCodeHead
  runtimeReleaseHead=$runtimeReleaseHead
  branch=$runtimeBranch
  worktreeClean=$true
  historicalMonitorSkillBlob=$historicalBlob
  remoteActionPerformed=$false
}
$runtimeCanonical = $RuntimeReleaseReturnPacket | ConvertTo-Json -Compress
$runtimeBytes = [Text.Encoding]::UTF8.GetBytes($runtimeCanonical)
$runtimeHasher = [Security.Cryptography.SHA256]::Create()
try { $runtimeHash = $runtimeHasher.ComputeHash($runtimeBytes) }
finally { $runtimeHasher.Dispose() }
$handoffSignatureSha256 = (($runtimeHash | ForEach-Object { $_.ToString('x2') }) -join '')
if ($handoffSignatureSha256 -notmatch '^[0-9a-f]{64}$') { throw 'runtime handoff signature format is invalid' }
[IO.File]::WriteAllText($RuntimeReleasePacketPath, $runtimeCanonical, (New-Object Text.UTF8Encoding($false)))
$writtenRuntimeBytes = [IO.File]::ReadAllBytes($RuntimeReleasePacketPath)
if ([Convert]::ToBase64String($writtenRuntimeBytes) -cne [Convert]::ToBase64String($runtimeBytes)) { throw 'runtime packet bytes changed while writing' }
$RuntimeReleasePacketPath
$handoffSignatureSha256
```

This runtime/release plan ends at that handoff. Browser-evidence Tasks 1–4 start from exactly `runtimeReleaseHead` and commit all pre-barrier browser fixtures/tests and the release helper/test on the same ancestry. Browser-evidence Task 5 alone performs the whole-product audit, names the sole immutable `CODE_HEAD`, and executes the Windows matrix without amending it; Task 6 alone creates the tracked report-only commit. This plan never receives an evidence-ready head, never audits or names `CODE_HEAD`, and never writes the report.

## Plan Self-Review

- [x] **Spec coverage:** Tasks 1–4 cover manifest allowlisting, fixed non-reflecting failures, exact CSP/security/cache headers, byte ceilings, deterministic committed assets, explicit wheel data, and Python-build-without-Node. Tasks 5–8 cover side-effect-free machine serve, exactly-once human open, random session, cleanup, fixed CMD runtime, exact 0.5.0 packages/protocol, and atomic setup/Repair. Tasks 9–10 cover Plugin, eighth active Skill, historical-Skill immutability, README, phase plan, roadmap, and 0.6 exclusion before evidence.
- [x] **Five-step product units:** All ten independently reviewable product units contain exactly one adjacent failing-test step, exact RED command, matching minimum implementation, exact GREEN command, and commit step. The terminal handoff adds no implementation, audit, or competing barrier.
- [x] **Dependency/order audit:** Task 3 creates, verifies, packages, and commits deterministic `ui_dist` before Task 4 starts default `MonitorService`; its wheel test requires index, manifest, and at least one asset before comparing exact inventory. Task 4's RED therefore fails only on absent routes, not absent resources. Task 6 RED includes the exact new wheel filename node. Tasks 7, 8, and 9 split the accepted-base unified Plugin layout assertion into launcher-only, setup-only, and manifest/Skill nodeids; each RED/GREEN selects only its owned nodes, while Task 8 runs the complete setup file under both Python versions.
- [x] **Static/security precision:** The plan names every allowed route, peer/Host/Origin/header condition, failure status/body, complete dynamic CSP, cache rule, MIME/ETag behavior, traversal case, and API no-fallback condition.
- [x] **Packaging/version precision:** Committed tree, all byte/gzip ceilings, package-data paths, wheel names, current version authorities, active assertion files, and intentionally preserved previous-version fixtures are explicit.
- [x] **Tool/path precision:** Every tool variable comes from the workspace dependency integration or a resolved OS path; commands name their working directory; scratch/evidence paths are external; no main-checkout literal or ambient Python/Node exists.
- [x] **Interface consistency:** accepted/product base remains `bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa`; the only transport is a repository-external no-BOM canonical UTF-8 JSON file plus a separate lowercase SHA-256 signature. Signed `FrontendCoreReturnPacket` schema `stm32tk-0502-frontend-core/1` and matching actual `FRONTEND_CORE_CODE_HEAD` are immutable inputs; clean `runtimeReleaseHead` is this plan's sole product-head output. The exact `RuntimeReleaseReturnPacket` schema `stm32tk-0502-runtime-release/1` preserves `moduleId`, `acceptedBase`, `planBundleHead`, and `frontendCoreCodeHead`. Both ends hash original file bytes, verify exact order/types and case-sensitive canonical re-encoding, and use case-sensitive identity/branch/signature comparisons. Browser-evidence Tasks 1–4 extend that ancestry, Task 5 alone audits/names `CODE_HEAD`, and Task 6 alone records the report. Historical requirement content is blob-checked at input and runtime handoff.
- [x] **Ownership boundary:** the user-authorized Codex implementation exception is bounded to the complete 0502 objective, expires with that objective, and grants no implementation or correction authority for another module or future release.
- [x] **Placeholder scan:** Cross-plan packets are emitted from checked runtime variables rather than placeholder strings; no implementation instruction, command, test, signature, path, or expected behavior is left unspecified.
