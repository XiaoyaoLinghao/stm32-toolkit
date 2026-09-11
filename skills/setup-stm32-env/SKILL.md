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
- The only MCP interpreter is `${CLAUDE_PLUGIN_DATA}/runtime/0.9.0/Scripts/python.exe`; system `python`, `py`, or `uv` is never an MCP fallback. A healthy runtime includes the exact manifest-listed Toolkit/Monitor wheels with readable UI assets, the pinned `pyocd==0.45.1` distribution, and the existing doctor contract.
- CPython >=3.12,<3.13 is the only bounded bootstrap prerequisite for consuming an extracted offline bundle from the official pinned source candidate. Bootstrap never installs from a package index or from the source tree.
- `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit` remains source provenance only; the historical
  `tools/stm32-toolkit[probe]` source expression is not installed directly.
- ARM GCC, ARM GDB, CMake, Ninja, PyOCD, CubeMX, VS Code extension, and CMSIS-Pack checks are bounded and read-only. Missing tools are reported, never installed.
- Monitor groups remain user-created; do not probe boards or create presets.

## Shell and path contract

Claude substitutes `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, and `${CLAUDE_PROJECT_DIR}` inline. Never read them from ambient shell variables. These single-line commands work from PowerShell or Git Bash because they invoke `powershell.exe` and pass explicit quoted paths.

The helper fails closed before mutation on empty, relative, unresolved, redirected, or reparse-point paths. Never guess a replacement path.

## CHECK

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

CHECK always returns JSON. `bundle.status` is `missing` or verified, and `runtimeState.status` is
`missing`, `matching`, `repairable`, `downgrade-refused`, `source-conflict`, `unsupported`, or
`invalid`. `runtime.status` is `missing`, `healthy`, or `broken`; it includes version/error evidence
and `recommendedMode`. A healthy runtime has version `0.9.0` and a successful bounded
`-m stm32_toolkit.cli ... doctor --json`. An existing 0.5.0 runtime reports broken as legacy
evidence; an existing 0.3.0 runtime reports broken with `recommendedMode` `Repair`. Repair
quarantines that runtime before atomically promoting 0.9.0 and publishing one
`runtime/runtime-state.json` generation. Tool version, extension, and pack inventory commands are
bounded; timeouts become evidence rather than hangs.

The existing isolated PEP 440 `pyocd` distribution check remains bounded to `>=0.45.1,<0.46`.

Final-path launcher checks additionally require the PyOCD console executable to be bound to the final runtime Python and to return the expected version with `pyocd.exe --version`. Bootstrap/Repair require the exact release pin; Check retains the supported module-version range above and requires the launcher to agree with that validated module version. Import/module checks alone are insufficient after staging promotion. Use the [Windows deployment and IDE preflight](../../docs/testing/windows-deployment-and-ide-preflight.md) when preparing deployment instructions; keep its version-specific IDE compatibility limits explicit.

## VS Code extensions (CHECK evidence only)

The doctor `vscodeExtensions` evidence checks exactly three recommended extensions by invoking the bounded read-only `code --list-extensions --show-versions` probe: `ms-vscode.cpptools`, `ms-vscode.cmake-tools`, and `marus25.cortex-debug`. Each reports `installed`, `version`, and a status of `ok`, `missing`, `unavailable` (no `code` executable), or `nonzero`/`timeout`/`error` (probe failed).

CHECK never installs, removes, or modifies extensions, settings, or the extensions directory. When an extension is `missing` or the probe is unavailable, tell the operator to install or remove the recommended extensions manually in VS Code and re-run CHECK afterwards. Do not run any other VS Code command.

For `missing`, ask authorization for Bootstrap. For `broken`, ask authorization for Repair. Stop until the user explicitly approves the exact mode and paths.

## MUTATE

Both modes first verify `release/release-manifest.json`, every manifest hash, safe path, and the closed
wheel set. They copy the verified wheels into a unique
`${CLAUDE_PLUGIN_DATA}/runtime/.staging/0.9.0-<id>` directory before one offline
`pip install --no-index --no-deps` invocation, run `pip check`, validate exact Toolkit/Monitor
versions and assets, validate isolated `pyocd`, and validate doctor before promotion. Failed safe
staging is removed; a staging tree containing redirects is preserved for manual recovery rather
than followed. The state file is written atomically only after runtime promotion; failures restore
the old runtime and state bytes. After promotion, the verified Toolkit, Monitor and PyOCD wheels regenerate their console launchers using the final runtime interpreter; launcher binding/version checks must pass before healthy state is published.

For an absent runtime, after explicit authorization run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Bootstrap -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

For a broken runtime, after separate explicit authorization run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Repair -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

Repair moves the failed runtime to `${CLAUDE_PLUGIN_DATA}/runtime/.quarantine/` before promotion and rolls it back if promotion fails. Neither mode writes project files, installs external hardware tools, packs, extensions, drivers, or registers MCP.

After mutation, repeat CHECK. Toolchain gaps do not invalidate a healthy plugin runtime.

## Available workflow handoff

Once CHECK reports `healthy`, hand off to one of the eight release Skills: `/stm32-toolkit:migrate-keil`, `/stm32-toolkit:configure-stm32-project`, `/stm32-toolkit:build-firmware`, `/stm32-toolkit:flash-firmware`, `/stm32-toolkit:debug-firmware`, `/stm32-toolkit:read-var`, or `/stm32-toolkit:stm32-monitor`. Every workflow starts with `stm32_project_context`, keeps project-derived target/SVD selection authoritative, and requires explicit authorization at every modifying or ownership-release boundary. The Monitor UI is observation-only: it never connects a probe or starts sampling automatically, and opens only after the user explicitly asks.
