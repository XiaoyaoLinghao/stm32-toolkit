---
name: setup-stm32-env
description: Use when a Claude Code user asks to check, bootstrap, repair, or diagnose the STM32 Toolkit environment.
---

# Setup STM32 Environment

## Overview

Keep diagnosis separate from installation. Always start in CHECK; enter MUTATE only after the user explicitly authorizes creation of the exact versioned runtime and installation of the local Toolkit package.

## Non-negotiable boundaries

- CHECK is read-only and offline. Do not create, modify, or delete files; install anything; kill processes; enumerate USB devices, boards, or debug probes; or access hardware.
- Never register MCP manually. The plugin-bundled `.mcp.json` binds the project automatically.
- The only MCP runtime is `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0/Scripts/python.exe`. Never fall back to system `python`, `py`, `uv`, or another interpreter.
- Host Python 3.10+ is only a bootstrap prerequisite for installing `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit`.
- Report ARM GCC, ARM GDB, CMake, Ninja, PyOCD, CubeMX, VS Code extension, and CMSIS-Pack gaps; do not install hardware tools, extensions, drivers, or packs.
- Monitoring groups are user-created. Do not create presets or implement follow-on monitoring in this foundation.

## Shell and path contract

Claude substitutes `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, and `${CLAUDE_PROJECT_DIR}` inline in this Skill. Never read those paths from ambient shell environment variables. Run the exact single-line commands below from either PowerShell or Git Bash; both explicitly invoke `powershell.exe` and pass all three substituted paths as quoted arguments.

The helper rejects an empty, relative, or unresolved Claude path before any mutation. If it reports `unresolved Claude placeholder`, stop and report that plugin substitution is unavailable. Never repair the command by guessing a path.

## CHECK

Run CHECK first:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

The helper checks Host Python 3.10+ as a bootstrap candidate. If the managed runtime exists, it uses only that interpreter to run `-m stm32_toolkit.cli version` and `doctor --json`. It returns JSON with `mode: CHECK`, the resolved forward-slash runtime/project paths, runtime presence/version, bootstrap Python evidence, `mutated: false`, and whether authorization is required.

Then perform read-only gap discovery. A missing executable is a gap, not permission to install it:

```powershell
powershell.exe -NoProfile -Command '$names=@("arm-none-eabi-gcc","arm-none-eabi-gdb","cmake","ninja","pyocd","STM32CubeMX"); foreach($name in $names){$tool=Get-Command $name -CommandType Application -ErrorAction SilentlyContinue; if($tool){& $tool.Source --version}}; $code=Get-Command code -CommandType Application -ErrorAction SilentlyContinue; if($code){& $code.Source --list-extensions}; $pyocd=Get-Command pyocd -CommandType Application -ErrorAction SilentlyContinue; if($pyocd){& $pyocd.Source pack show}'
```

Do not run probe enumeration. CMSIS-Pack inventory is allowed only through the existing local PyOCD inventory command shown above.

If the runtime is absent or broken, report the evidence, identify whether a supported Host Python exists, ask for explicit authorization to run the exact MUTATE command, and stop. Do not mutate in the same response without an affirmative answer.

## MUTATE

After explicit authorization, restate these exact targets:

- runtime: `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0`
- package: `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit`
- project: `${CLAUDE_PROJECT_DIR}`

Then run only:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Bootstrap -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

The helper revalidates all paths before creation, discovers a supported Host Python, creates only the version `0.2.0` venv, installs the local package and declared dependencies, and runs `stm32-toolkit doctor --json` with the explicit project root. It creates no hardware-tool installation, CMSIS-Pack, extension, driver, project file, or second MCP.

After MUTATE, repeat CHECK and report remaining gaps. Toolchain gaps do not make the plugin runtime invalid.

## Quick reference

| Situation | Required action |
|---|---|
| Claude path empty/unresolved/relative | Fail closed; do not guess or create anything |
| Runtime missing or broken | Report, request explicit authorization, stop |
| Runtime healthy | Run managed version and `doctor --json` |
| Tool, extension, or pack missing | Report the gap only |
| MCP unavailable | Repair the versioned runtime; rely on bundled `.mcp.json` |
