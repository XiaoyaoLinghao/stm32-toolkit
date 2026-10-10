---
name: setup-stm32-env
description: Use when a Claude Code user asks to check, bootstrap, repair, or diagnose the STM32 Toolkit environment.
---

# Setup STM32 Environment

## Overview

`/stm32-toolkit:setup-stm32-env` is the Skill-only bootstrap path before the MCP runtime exists. Always start with CHECK. Run Bootstrap or Repair only after explicit authorization for that exact mutation. After the runtime is healthy, the MCP tools expose Keil migration, configuration, build, probe flash, handoff, and typed debug workflows; every workflow Skill starts with `stm32_project_context`.

## Non-negotiable boundaries

- CHECK is read-only and offline with respect to installation. It never creates files, probes hardware, kills unrelated or existing processes, or installs anything. It may terminate only a probe subprocess that CHECK itself started after that probe exceeds its timeout.
- Never register a second MCP. The plugin-bundled `.mcp.json` starts only after the managed runtime is healthy.
- The only MCP interpreter for this candidate is `${CLAUDE_PLUGIN_DATA}/runtime/1.0.1/Scripts/python.exe`; system `python`, `py`, or `uv` is never an MCP fallback. A healthy runtime includes the exact manifest-listed Toolkit/Monitor wheels with readable UI assets, the pinned `pyocd==0.45.1` distribution, and the existing doctor contract.
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
inline. Never read them from ambient shell variables. This host command invokes `powershell.exe`
with explicit quoted paths:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

### Standalone PowerShell sequence

Standalone users must pass three explicit absolute paths: the extracted `ToolkitRoot`, the
long-lived `DataRoot`, and the existing `ProjectRoot`. The examples below are complete ordinary
PowerShell and do not require host placeholders. Set the paths once and always run the read-only
check first.

```powershell
$ToolkitRoot = 'C:\tools\stm32-toolkit-1.0.1'
$DataRoot = 'C:\data\stm32-toolkit'
$ProjectRoot = 'C:\work\blinky'
$SetupScript = Join-Path $ToolkitRoot 'bin\setup-stm32-env.ps1'

# Always run the read-only check first.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Check `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports `missing`, review its evidence and explicitly authorize the absent-runtime
install before running this separate Bootstrap command:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Bootstrap `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

If `Check` reports `repairable` for an approved 1.0.0/0.9.0/0.5.0/0.3.0 legacy upgrade, or `broken` for
an existing runtime, review its source and downgrade guards and explicitly authorize Repair before
running this separate command:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -Mode Repair `
  -ToolkitRoot $ToolkitRoot -DataRoot $DataRoot -ProjectRoot $ProjectRoot
```

`Check` is read-only. Run at most one mutation command for the decision, then repeat `Check`.

## CHECK

CHECK always returns JSON. `bundle.status` is `missing` or verified, and `runtimeState.status` is
`missing`, `matching`, `repairable`, `downgrade-refused`, `source-conflict`, `unsupported`, or
`invalid`. `runtime.status` is `missing`, `healthy`, or `broken`; it includes version/error evidence
and `recommendedMode`. A healthy runtime has version `1.0.1` and a successful bounded
`-m stm32_toolkit.cli ... doctor --json`. An existing 1.0.0, 0.9.0, 0.5.0 or 0.3.0 runtime reports broken as legacy
evidence. Repair quarantines that runtime before atomically promoting 1.0.1 and publishing one
`runtime/runtime-state.json` generation. Tool version, extension, and pack inventory commands are
bounded; timeouts become evidence rather than hangs.

The existing isolated PEP 440 `pyocd` distribution check remains bounded to `>=0.45.1,<0.46`.

Final-path launcher checks additionally require the PyOCD console executable to be bound to the final runtime Python and to return the expected version with `pyocd.exe --version`. Bootstrap/Repair require the exact release pin; Check retains the supported module-version range above and requires the launcher to agree with that validated module version. Import/module checks alone are insufficient after staging promotion. Use the [Windows deployment and IDE preflight](../../docs/testing/windows-deployment-and-ide-preflight.md) when preparing deployment instructions; keep its version-specific IDE compatibility limits explicit.

## GUI tools and VS Code extensions (CHECK evidence only)

Neither CHECK nor doctor starts CubeMX or VS Code. CHECK locates the CubeMX executable and reads Windows file-version metadata without running it: `cubeMx.status` is `ok` with a static version, `unknown` when an executable has no readable static version, or `missing` when absent. `tools.vscodeExtensions` is `not-probed`, with a located command path or `null`, and `output=null`; it does not enumerate extensions. Other CLI tool probes remain bounded.

Doctor retains the three recommended extension names: `ms-vscode.cpptools`, `ms-vscode.cmake-tools`, and `marus25.cortex-debug`. Without an actual extension probe, each reports `installed=false`, `version=null`, `status="not-probed"`. This is unknown installation state, not proof that an extension is missing. CHECK never installs, removes, or modifies extensions, settings, or the extensions directory. For IDE use, verify the active VS Code profile and extension versions manually against the [Windows deployment and IDE preflight](../../docs/testing/windows-deployment-and-ide-preflight.md).

For `missing`, ask authorization for Bootstrap. For `repairable` legacy-upgrade state or `broken`
runtime, ask authorization for Repair. Stop until the user explicitly approves the exact mode and
paths.

## MUTATE

Both modes first verify `release/release-manifest.json`, every manifest hash, safe path, and the closed
wheel set. They copy the verified wheels into a unique
`${CLAUDE_PLUGIN_DATA}/runtime/.staging/1.0.1-<id>` directory before one offline
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

Once CHECK reports `healthy`, hand off to one of the eight release Skills: `/stm32-toolkit:migrate-keil`, `/stm32-toolkit:configure-stm32-project`, `/stm32-toolkit:build-firmware`, `/stm32-toolkit:flash-firmware`, `/stm32-toolkit:debug-firmware`, `/stm32-toolkit:read-var`, or `/stm32-toolkit:stm32-monitor`. Every workflow starts with `stm32_project_context`, keeps project-derived target/SVD selection authoritative, and requires explicit authorization at every modifying or ownership-release boundary. The Monitor UI is observation-only: it never connects a probe or starts sampling automatically, and opens only after the user explicitly asks.
