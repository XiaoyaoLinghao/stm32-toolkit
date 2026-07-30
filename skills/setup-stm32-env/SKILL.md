---
name: setup-stm32-env
description: Use when a Claude Code user asks to check, bootstrap, repair, or diagnose the STM32 Toolkit foundation environment.
---

# Setup STM32 Environment

## Overview

`/stm32-toolkit:setup-stm32-env` is the Skill-only bootstrap path before the MCP runtime exists. Always start with CHECK. Run Bootstrap or Repair only after explicit authorization for that exact mutation.

## Non-negotiable boundaries

- CHECK is read-only and offline with respect to installation. It never creates files, probes hardware, kills processes, or installs anything.
- Never register a second MCP. The plugin-bundled `.mcp.json` starts only after the managed runtime is healthy.
- The only MCP interpreter is `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0/Scripts/python.exe`; system `python`, `py`, or `uv` is never an MCP fallback.
- Host Python 3.10+ is only a bounded bootstrap prerequisite for installing `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit`.
- ARM GCC, ARM GDB, CMake, Ninja, PyOCD, CubeMX, VS Code extension, and CMSIS-Pack checks are bounded and read-only. Missing tools are reported, never installed.
- Monitor groups remain user-created; do not probe boards or create presets.

## Shell and path contract

Claude substitutes `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, and `${CLAUDE_PROJECT_DIR}` inline. Never read them from ambient shell variables. These single-line commands work from PowerShell or Git Bash because they invoke `powershell.exe` and pass explicit quoted paths.

The helper fails closed before mutation on empty, relative, unresolved, redirected, or reparse-point paths. Never guess a replacement path.

## CHECK

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

CHECK always returns JSON. `runtime.status` is `missing`, `healthy`, or `broken`; it includes exact version/error evidence and `recommendedMode`. A healthy runtime has version `0.2.0` and a successful bounded `-m stm32_toolkit.cli ... doctor --json`. Tool version, extension, and pack inventory commands are bounded; timeouts become evidence rather than hangs.

For `missing`, ask authorization for Bootstrap. For `broken`, ask authorization for Repair. Stop until the user explicitly approves the exact mode and paths.

## MUTATE

Both modes build in a unique `${CLAUDE_PLUGIN_DATA}/runtime/.staging/0.2.0-<id>` directory, install without using the user pip cache, validate exact Toolkit version `0.2.0`, and validate doctor before promotion. Failed safe staging is removed; a staging tree containing redirects is preserved for manual recovery rather than followed.

For an absent runtime, after explicit authorization run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Bootstrap -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

For a broken runtime, after separate explicit authorization run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Repair -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

Repair moves the failed runtime to `${CLAUDE_PLUGIN_DATA}/runtime/.quarantine/` before promotion and rolls it back if promotion fails. Neither mode writes project files, installs external hardware tools, packs, extensions, drivers, or registers MCP.

After mutation, repeat CHECK. Toolchain gaps do not invalidate a healthy plugin runtime.