---
name: setup-stm32-env
description: Use when a Claude Code user asks to check, bootstrap, repair, or diagnose the STM32 Toolkit environment.
---

# Setup STM32 Environment

## Overview

Keep diagnosis separate from installation. Always start in CHECK; enter MUTATE only after the user explicitly authorizes the exact versioned runtime creation and local package installation.

## Non-negotiable boundaries

- CHECK is read-only and offline. Do not create, modify, or delete files; install anything; kill processes; enumerate USB devices, boards, or debug probes; or access hardware.
- CHECK may inspect existing executable versions, the existing VS Code extension list, and the installed CMSIS-Pack inventory. Do not install or update hardware tools, extensions, drivers, or packs.
- Never run probe-enumeration commands (including `pyocd list`) during setup.
- Never register MCP manually. Do not run `claude mcp add` or edit Claude settings. The plugin-bundled `.mcp.json` is authoritative and binds the project automatically.
- The only MCP runtime is `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0/Scripts/python.exe`. Never fall back to system `python`, `py`, `uv`, or another interpreter.
- Host Python 3.10+ is only a bootstrap prerequisite for creating the managed runtime and installing `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit`.
- Monitoring groups are user-created. Preserve that requirement; do not create presets or rewrite monitoring in this foundation.

## CHECK

1. Check Host Python 3.10+ first, solely as a bootstrap prerequisite. Resolve the executable before running the version check; do not treat it as the MCP runtime:

```powershell
$hostPython = @("python", "python3", "py") | ForEach-Object { Get-Command $_ -CommandType Application -ErrorAction SilentlyContinue } | Select-Object -First 1
if ($hostPython) { & $hostPython.Source -c "import json, sys; print(json.dumps({'version': list(sys.version_info[:3]), 'supported': sys.version_info >= (3, 10)}))" }
```

2. Confirm `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, and `CLAUDE_PROJECT_DIR` are set. Use forward-slash paths in all feedback.
3. Set the expected runtime path and test whether it exists:

```powershell
$runtime = "$env:CLAUDE_PLUGIN_DATA/runtime/0.2.0"
$runtimePython = "$runtime/Scripts/python.exe"
Test-Path -LiteralPath $runtimePython -PathType Leaf
```

4. If the runtime exists, run only that interpreter:

```powershell
& $runtimePython -m stm32_toolkit.cli version
& $runtimePython -m stm32_toolkit.cli --project-root "$env:CLAUDE_PROJECT_DIR" doctor --json
```

5. Read-only gap checks must report:

   - ARM GCC (`arm-none-eabi-gcc`) and ARM GDB (`arm-none-eabi-gdb`)
   - CMake, Ninja, PyOCD, and CubeMX
   - existing VS Code extensions
   - installed CMSIS-Pack inventory, but only when an existing PyOCD executable provides a local inventory command

Use only these read-only discovery patterns. A missing executable is a gap, not permission to install it:

```powershell
$toolNames = @("arm-none-eabi-gcc", "arm-none-eabi-gdb", "cmake", "ninja", "pyocd", "STM32CubeMX")
foreach ($name in $toolNames) {
  $tool = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
  if ($tool) { & $tool.Source --version }
}
$code = Get-Command code -CommandType Application -ErrorAction SilentlyContinue
if ($code) { & $code.Source --list-extensions }
$pyocd = Get-Command pyocd -CommandType Application -ErrorAction SilentlyContinue
if ($pyocd) { & $pyocd.Source pack show }
```

6. Return a concise result with this shape (JSON when requested):

```json
{
  "mode": "CHECK",
  "runtime": {"path": ".../runtime/0.2.0", "present": false, "version": null},
  "bootstrapPython": {"available": true, "version": "3.10+"},
  "tools": {"armGcc": {}, "armGdb": {}, "cmake": {}, "ninja": {}, "pyocd": {}, "cubeMx": {}},
  "vscodeExtensions": {"installed": [], "gaps": []},
  "cmsisPacks": {"installed": [], "gaps": []},
  "mutated": false,
  "authorizationRequired": true
}
```

If the runtime is absent or broken, report that fact, identify a Host Python 3.10+ candidate without using it as the MCP runtime, ask for explicit authorization to create the exact runtime and install the local package, and stop. Do not begin MUTATE in the same response without an affirmative answer.

## MUTATE

Enter this section only after explicit authorization. Restate the exact runtime and package paths, then perform only this bootstrap:

```powershell
$runtime = "$env:CLAUDE_PLUGIN_DATA/runtime/0.2.0"
$package = "$env:CLAUDE_PLUGIN_ROOT/tools/stm32-toolkit"
& $hostPython -m venv $runtime
if ($LASTEXITCODE -ne 0) { throw "runtime creation failed" }
& "$runtime/Scripts/python.exe" -m pip install $package
if ($LASTEXITCODE -ne 0) { throw "toolkit installation failed" }
& "$runtime/Scripts/python.exe" -m stm32_toolkit.cli --project-root "$env:CLAUDE_PROJECT_DIR" doctor --json
if ($LASTEXITCODE -ne 0) { throw "toolkit doctor failed" }
```

`$hostPython` must be the already checked Python 3.10+ executable. The local package installation brings its declared dependencies into this venv. Create no other runtime and install no external hardware tool, CMSIS-Pack, VS Code extension, driver, or second MCP.

After MUTATE, repeat CHECK with the exact managed interpreter and report remaining gaps. Toolchain gaps do not make the plugin runtime invalid.

## Quick reference

| Situation | Required action |
|---|---|
| Runtime missing or broken | Report, ask explicit authorization, stop |
| Runtime healthy | Run its version and `doctor --json` |
| Tool, extension, or pack missing | Report the gap only |
| Board may be attached | Do not enumerate it during setup |
| MCP unavailable | Repair the versioned runtime; rely on bundled `.mcp.json` |

## Common mistakes

- Treating a check-only request as permission to remediate.
- Using an ambient Python command after the managed runtime is missing.
- Turning an optional tool gap into an automatic install.
- Mixing machine-owned runtime state into the project or registering another MCP.
