# STM32 Toolkit

STM32 Toolkit is a Claude Code plugin for AI-assisted STM32 coding, debugging, testing, and monitoring. It keeps shared project intent in the repository while isolating machine-owned runtime and session state for every checkout.

## Install once for the user

Install the plugin from your configured Claude Code plugin source at user scope. For a marketplace installation, replace the placeholder with that source name:

```powershell
claude plugin install stm32-toolkit@<marketplace-name> --scope user
```

Do not copy Skills manually and do not register a second MCP server. Claude Code discovers the plugin's standard `skills/` directory and bundled `.mcp.json`. Version 0.2.0 exposes only `/setup-stm32-env`; unfinished skill sources are preserved under `requirements/follow-on-skills/`, outside Claude's automatic Skill discovery.

Run `/setup-stm32-env` once after installation. It first performs an offline, read-only check. If `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0` is absent, it asks for explicit authorization before using Host Python 3.10+ to create that venv and install the local `${CLAUDE_PLUGIN_ROOT}/tools/stm32-toolkit` package and dependencies. Host Python is never an MCP fallback.

## Automatic project binding and isolation

When the plugin is enabled, its bundled MCP configuration automatically starts the managed runtime and binds the server to `${CLAUDE_PROJECT_DIR}`. The launcher always uses `${CLAUDE_PLUGIN_DATA}/runtime/0.2.0/Scripts/python.exe`; it never selects a system interpreter.

Two kinds of data stay deliberately separate:

- `.stm32-project.json` is the shared, version-controlled project configuration. Its `logicalProjectId` identifies the logical firmware project.
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` contains isolated user state for one canonical checkout, including sessions, logs, diagnostics, caches, and future monitor state. Separate clones get different workspace IDs even when they share a logical project ID.

The MCP process is bound to one canonical project root. Unconfigured Keil-only or unknown projects remain read-only and do not receive a workspace until a valid `.stm32-project.json` exists.

## Troubleshooting

The first troubleshooting command is `stm32-toolkit doctor --json`. Run it through the managed runtime so diagnosis uses the same environment as MCP:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

Doctor reports offline evidence for ARM GCC/GDB, CMake, Ninja, PyOCD, CubeMX, and VS Code without probing hardware or changing the project. `/setup-stm32-env` also reports existing VS Code extension and CMSIS-Pack inventory gaps. Missing hardware tools, extensions, drivers, or packs are reported for the user to resolve; setup does not install them.

If MCP startup says the runtime is missing, rerun `/setup-stm32-env`. The plugin-bundled `.mcp.json` is authoritative, so manual `claude mcp add` registration is neither required nor supported.

## Foundation and follow-on capabilities

### Foundation delivered in version 0.2.0

- versioned Python package and stable JSON result envelopes;
- STM32 project detection and validated `.stm32-project.json` loading;
- deterministic per-checkout workspace IDs and isolated plugin-data paths;
- offline doctor, project context, CLI wrappers, and project-bound MCP tools;
- user-scope plugin layout, one-time managed runtime bootstrap guidance, and automatic MCP binding.

### Follow-on work

The foundation does not yet claim hardware flashing, probe leases, live target inspection, breakpoint debugging, host/target test execution, project generation, or a monitoring UI. Those capabilities require later implementation and hardware-aware safety contracts.

Keil-to-GCC migration is one-way: future migration work may inspect Keil input and generate GCC/CMake configuration, but it must not write back to or synchronize the Keil project. The existing monitor requirement is preserved but monitoring is not implemented in this foundation. The contract requires user-created monitor groups; the toolkit does not ship or invent named presets.
