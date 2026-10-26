---
name: setup-stm32-env
description: Use when a Claude Code user asks to check, bootstrap, repair, or diagnose the STM32 Toolkit environment.
---

# Setup STM32 Environment

## Overview

`/stm32-toolkit:setup-stm32-env` is the Skill-only bootstrap path before the MCP runtime exists. Always start with CHECK. Run Bootstrap or Repair only after explicit authorization for that exact mutation. After the runtime is healthy, the MCP tools expose Keil migration, configuration, build, probe flash, handoff, and typed debug workflows; every managed-project workflow Skill starts with `stm32_project_context`. The discovery-only probe request does not, and an explicitly selected external/snapshot import validates its own declared inputs rather than requiring a managed model.

## Non-negotiable boundaries

- CHECK is read-only and offline with respect to installation. It never creates files, probes hardware, kills unrelated or existing processes, or installs anything. It may terminate only a probe subprocess that CHECK itself started after that probe exceeds its timeout.
- Never register a second MCP. The plugin-bundled `.mcp.json` starts only after the managed runtime is healthy.
- The only MCP interpreter for this candidate is `${CLAUDE_PLUGIN_DATA}/runtime/1.3.2/Scripts/python.exe`; system `python`, `py`, or `uv` is never an MCP fallback. A healthy runtime includes the exact manifest-listed Toolkit/Monitor wheels with readable UI assets, the pinned `pyocd==0.45.1` distribution, and the existing doctor contract.
- CPython >=3.12,<3.13 is the only bounded bootstrap prerequisite for consuming an extracted offline bundle from the official pinned source candidate. Bootstrap never installs from a package index or from the source tree.
- `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit` remains source provenance only; the historical
  `tools/stm32-toolkit[probe]` source expression is not installed directly.
- ARM GCC, ARM GDB, CMake, Ninja, PyOCD, CubeMX, VS Code extension, and CMSIS-Pack checks are bounded and read-only. Missing tools are reported, never installed.
- Monitor groups remain user-created; do not probe boards or create presets.

## Shell and path contract

The helper fails closed before mutation on empty, relative, unresolved, redirected, or reparse-point
paths. Never guess a replacement path.

### Agent-host adapter

Claude substitutes `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, and `${CLAUDE_PROJECT_DIR}`
inline. Never read them from ambient shell variables. This host command invokes native
PowerShell 7 (`pwsh`) with explicit quoted paths. Before the step, confirm the selected
interpreter is available and starts, for example with
`pwsh -NoProfile -Command '$PSVersionTable.PSVersion'`:

```powershell
pwsh -NoProfile -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

Do not add an `-ExecutionPolicy` override. If the machine execution policy denies the
script, stop and resolve that policy prerequisite with the machine owner; never switch
shells, widen policy, or automatically retry after a denial.

### Standalone PowerShell sequence

Standalone users must pass three explicit absolute paths: the extracted `ToolkitRoot`, the
long-lived `DataRoot`, and the existing `ProjectRoot`. The examples below are complete ordinary
PowerShell 7 commands and do not require host placeholders. Verify that `pwsh` starts
(`pwsh -NoProfile -Command '$PSVersionTable.PSVersion'`), set the paths once, and always run
the read-only check first.

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit-1.3.2'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

# Always run the read-only check first.
& pwsh -NoProfile -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports `missing`, review its evidence and explicitly authorize the absent-runtime
install before running this separate Bootstrap command:

```powershell
& pwsh -NoProfile -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports `repairable` for an approved 1.3.1/1.3.0/1.2.0/1.1.2/1.0.1/1.0.0/0.9.0/0.5.0/0.3.0 legacy upgrade, or `broken` for
an existing runtime, review its source and downgrade guards and explicitly authorize Repair before
running this separate command:

```powershell
& pwsh -NoProfile -File $SetupScript -Mode Repair `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

`Check` is read-only. Run at most one mutation command for the decision, then repeat `Check`.

## Verify version and binding

Use existing evidence only. Repeat `stm32_doctor` and `stm32_project_context` through the actual MCP client: the PowerShell commands below start a separate CLI process and do not prove what that live MCP process registered. `stm32_doctor` `data.runtime.toolkitVersion` and `data.publicInventory` describe the server; compare them with the actual tool list and input schemas the client exposes, and keep `stm32_project_context` `data.project.root` authoritative. An inventory count is not proof that the client registered those tools, and a launcher/CLI version alone does not prove the bound MCP version. After an upgrade restart VS Code once, then verify again. If expected tools or fields are missing, or the root differs, preserve the full JSON and stop the dependent operation.

`data.firmwareRoutes`, per-blocker preflight `remediation`/`blockerSummary.byRemediation`, and the `extraRegions` option (with `analysis.extraRegions`) are additions in the current v1.3.2 source. The published v1.3.1 package already contains them, but it may legitimately omit the new v1.3.2 `probeCore.pyocdResolution`, the pyOCD diagnostics entries, and `data.vscodeGuidance`; treat that absence as an older implementation, not proof of a stale MCP server. The frozen `1e6ea849` v1.3.0 ZIP/runtime contains only the earlier preflight basics (`stm32_keil_preflight` with `analysis.blockers`, the blocker summary, `planReadiness`/`applyReadiness`, and the `startupStrategy`/`startupSource`/`memoryLayout` options), so do not describe the whole preflight tool as absent there either. The newer fields become checkable only after a matching v1.3.2 build is installed; do not infer them from a version string or inventory count.

The following reads and prints the unfiltered JSON before checking `ok`; do not pipe it through `Select-Object`, `head`, or `grep`:

```powershell
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$CandidateCli = Join-Path $DataRoot 'runtime\1.3.2\Scripts\stm32-toolkit.exe'

& $CandidateCli version
$DoctorText = & $CandidateCli --project-root $ProjectRoot doctor --json | Out-String
$DoctorText
$Doctor = $DoctorText | ConvertFrom-Json
if (-not $Doctor.ok) { throw "doctor failed: $($Doctor.code): $($Doctor.message)" }
$Doctor.data.runtime.toolkitVersion
$Doctor.data.publicInventory

$ContextText = & $CandidateCli --project-root $ProjectRoot project context --data-root $DataRoot --session-id verify-1 --json | Out-String
$ContextText
$Context = $ContextText | ConvertFrom-Json
if (-not $Context.ok) { throw "context failed: $($Context.code): $($Context.message)" }
$Context.data.project.root
$Context.data.capabilityDetails
$Context.data.firmwareRoutes
```

Keep every `details.*` field when a result is `ok=false`; read the complete result before summarizing. The context `firmwareRoutes.managed` entry mirrors `capabilityDetails.flash`; `firmwareRoutes.imported` is always `not-evaluated` in context and does not require Git or a managed model. Tool availability is not image readiness, and a managed blocker never selects the imported route automatically.

## CHECK

CHECK always returns JSON. `bundle.status` is `missing` or verified, and `runtimeState.status` is
`missing`, `matching`, `repairable`, `downgrade-refused`, `source-conflict`, `unsupported`, or
`invalid`. `runtime.status` is `missing`, `healthy`, or `broken`; it includes version/error evidence
and `recommendedMode`. A healthy runtime has version `1.3.2` and a successful bounded
`-m stm32_toolkit.cli ... doctor --json`. An existing 1.3.1, 1.3.0, 1.2.0, 1.1.2, 1.0.1, 1.0.0, 0.9.0, 0.5.0 or 0.3.0 runtime reports broken as legacy
evidence. Repair quarantines that runtime before atomically promoting 1.3.2 and publishing one
`runtime/runtime-state.json` generation. Tool version, extension, and pack inventory commands are
bounded; timeouts become evidence rather than hangs.

The existing isolated PEP 440 `pyocd` distribution check remains bounded to `>=0.45.1,<0.46`.

When reading `doctor` output, keep the two pyOCD evidence forms separate: `data.tools.pyocd` is PATH command evidence (`available`/`path`/`status`/`returnCode`/`version`) and `data.probeCore.dependencies.pyocd` is installed-distribution metadata in the Toolkit interpreter. `data.probeCore.pyocdResolution` combines them once per call with `status` (`runtime-package-present` or `runtime-package-unconfirmed`), `runtimeAvailable`, `runtimeVersion`, `pathCommandAvailable`, `pathCommandStatus`, `evidenceBasis="distribution-metadata"`, `hardwareVerified=false`, `message`, and `remediation`. It is distribution metadata only: importability, a working Probe backend, and hardware are not checked. The internal Probe backend imports pyOCD from its runtime, so present metadata with a missing PATH command adds `PYOCD_CLI_NOT_ON_PATH_RUNTIME_PRESENT` (`info`) and does not establish a missing runtime dependency; do not edit PATH merely to silence it. Metadata that cannot be confirmed (including a lookup exception) adds `PYOCD_RUNTIME_PACKAGE_UNCONFIRMED` (`warning`) even when a separate PATH command works, and is not proof of uninstall. Preserve CLI `nonzero`/`timeout`/`error` evidence unchanged in `pathCommandStatus`, direct the user to the matching setup Check (`-Mode Check`), and never treat a global pip install or PATH edit as the default remedy. Doctor never imports pyOCD, starts a worker, enumerates probes, or performs extra process/network discovery.

Final-path launcher checks additionally require the PyOCD console executable to be bound to the final runtime Python and to return the expected version with `pyocd.exe --version`. Bootstrap/Repair require the exact release pin; Check retains the supported module-version range above and requires the launcher to agree with that validated module version. Import/module checks alone are insufficient after staging promotion. Use the [Windows deployment and IDE preflight](../../docs/testing/windows-deployment-and-ide-preflight.md) when preparing deployment instructions; keep its version-specific IDE compatibility limits explicit.

## GUI tools and VS Code extensions (read-only evidence)

Neither CHECK nor doctor opens a CubeMX or VS Code editor window, and neither installs, updates, or removes software. CHECK locates the CubeMX executable and reads Windows file-version metadata without running it: `cubeMx.status` is `ok` with a static version, `unknown` when an executable has no readable static version, or `missing` when absent. CHECK's `tools.vscodeExtensions` is static `not-probed` evidence, with a located command path or `null`, and `output=null`; CHECK itself does not enumerate extensions. Other CLI tool probes remain bounded.

That CHECK-only static evidence is not the current doctor contract. By default doctor performs a bounded, read-only `--list-extensions --show-versions` observation of the selected local VS Code CLI (never an editor window, installation or update) and reports the three recommended extensions `ms-vscode.cpptools`, `ms-vscode.cmake-tools`, and `marus25.cortex-debug` in `data.vscodeExtensions` with live `installed`/`version` evidence, plus `data.vscodeExtensionObservation` (`scope="local-default-profile"`, probe/selection status, executable and CLI script, `completeInventory`). A complete inventory distinguishes `installed=true` from an absent extension (`installed=false`). Explicit opt-out (`--skip-vscode-extensions`/MCP `probeVscodeExtensions=false`), a selection failure, timeout, nonzero exit, truncation, malformed or conflicting output, or any other incomplete observation reports `installed=null`, `version=null`, and its stable `status`/`code`/remediation; that is unknown state, not proof that an extension is missing. Do not treat `not-probed`, `skipped` or `null` as `installed=false`, and do not report extension observation as IDE or debug acceptance. For IDE use, verify the active VS Code profile and extension versions manually against the [Windows deployment and IDE preflight](../../docs/testing/windows-deployment-and-ide-preflight.md).

For `missing`, ask authorization for Bootstrap. For `repairable` legacy-upgrade state or `broken`
runtime, ask authorization for Repair. Stop until the user explicitly approves the exact mode and
paths.

## MUTATE

Both modes first verify `release/release-manifest.json`, every manifest hash, safe path, and the closed
wheel set. They copy the verified wheels into a unique
`${CLAUDE_PLUGIN_DATA}/runtime/.staging/1.3.2-<id>` directory before one offline
`pip install --no-index --no-deps` invocation, run `pip check`, validate exact Toolkit/Monitor
versions and assets, validate isolated `pyocd`, and validate doctor before promotion. Failed safe
staging is removed; a staging tree containing redirects is preserved for manual recovery rather
than followed. The state file is written atomically only after runtime promotion; failures restore
the old runtime and state bytes. After promotion, the verified Toolkit, Monitor and PyOCD wheels regenerate their console launchers using the final runtime interpreter; launcher binding/version checks must pass before healthy state is published.

For an absent runtime, after explicit authorization, select the separate `Bootstrap` command above.
For a `repairable` legacy-upgrade state or a broken runtime, after separate explicit authorization,
select the separate `Repair` command instead.

Repair moves the failed runtime to `${CLAUDE_PLUGIN_DATA}/runtime/.quarantine/` before promotion and rolls it back if promotion fails. Neither mode writes project files, installs external hardware tools, packs, extensions, drivers, or registers MCP.

After mutation, repeat CHECK. Toolchain gaps do not invalidate a healthy plugin runtime.

## Available workflow handoff

Once CHECK reports `healthy`, hand off to one of the eight release workflow Skills: `/stm32-toolkit:migrate-keil`, `/stm32-toolkit:configure-stm32-project`, `/stm32-toolkit:build-firmware`, `/stm32-toolkit:flash-firmware`, `/stm32-toolkit:debug-firmware`, `/stm32-toolkit:read-var`, or `/stm32-toolkit:stm32-monitor`. Every managed-project workflow starts with `stm32_project_context`, keeps project-derived target/SVD selection authoritative, and requires explicit authorization at every modifying or ownership-release boundary. Discovery-only probe interrogation needs no context or managed model. An explicitly selected external/snapshot import is separate: it validates its own declared path/hash/format/target/Flash-region inputs and does not require a managed model, though invalid roots or binding errors still stop it; no route switches automatically. The ninth bundled Skill, `normalize-source-comments`, is a separate explicit encoding-copy helper: it previews comment-only UTF-8 copies with per-file charsets into a new external directory, never edits the original project, and cannot remove migration blockers. The Monitor UI is observation-only: it never connects a probe or starts sampling automatically, and opens only after the user explicitly asks.
