# STM32 Toolkit

[简体中文](README_zh-CN.md) | English

STM32 Toolkit 0.4.0 turns one Keil uVision project into a reproducible ARM GNU/GCC build and an identity-pinned probe/debug workflow. It provides read-only Keil inspection, guarded ARMCC-to-GCC conversion, managed GCC/CMake and VS Code configuration, bounded builds, explicit probe flashing, one-time debugger handoff, typed DWARF/SVD reads, finite sampling, and Fault analysis. It remains the foundation for future AI-assisted STM32 coding, debugging, testing, and monitoring.

## Install directly from GitHub

The plugin is distributed directly from GitHub, not a public catalog. Install it once at user scope:

```powershell
claude plugin marketplace add https://github.com/XiaoyaoLinghao/stm32-toolkit.git --scope user
claude plugin install stm32-toolkit@stm32-toolkit --scope user
```

Run `/reload-plugins` or restart Claude Code. To update:

```powershell
claude plugin marketplace update stm32-toolkit
claude plugin update stm32-toolkit@stm32-toolkit --scope user
```

Claude Code discovers the plugin's standard `skills/` directory and bundled `.mcp.json` automatically. Do not copy Skills or register a second MCP server. Version 0.4.0 exposes exactly seven Skills:

- `/stm32-toolkit:setup-stm32-env`
- `/stm32-toolkit:migrate-keil`
- `/stm32-toolkit:configure-stm32-project`
- `/stm32-toolkit:build-firmware`
- `/stm32-toolkit:flash-firmware`
- `/stm32-toolkit:debug-firmware`
- `/stm32-toolkit:read-var`

Run `/stm32-toolkit:setup-stm32-env` after installation. CHECK reports the managed runtime as `missing`, `healthy`, or `broken`. An existing 0.3.0 runtime is `broken` with `recommendedMode` `Repair`; after explicit authorization Repair quarantines it before atomically promoting 0.4.0. Host Python 3.10+ is only a bounded bootstrap prerequisite and never an MCP fallback.

## Automatic project binding and isolation

The bundled MCP configuration binds one server automatically to `${CLAUDE_PROJECT_DIR}`. The launcher uses only `${CLAUDE_PLUGIN_DATA}/runtime/0.4.0/Scripts/python.exe` and never a system interpreter.

- `.stm32-project.json` is the shared, version-controlled project configuration.
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` contains machine-owned state for one canonical checkout. Separate clones have distinct workspaces and sessions.

The server exposes exactly 15 project-bound tools: `stm32_doctor`, `stm32_project_detect`, `stm32_project_context`, `stm32_keil_inspect`, `stm32_keil_convert`, `stm32_project_configure`, `stm32_build`, `stm32_probe_list`, `stm32_flash`, `stm32_debug_handoff_begin`, `stm32_debug_handoff_end`, `stm32_variable_read`, `stm32_variable_sample`, `stm32_register_read`, and `stm32_fault_analyze`. They do not accept a project root, data root, command, environment, service credential, target override, SVD override, ELF path, or memory address.

## Workflows and authorization

Conversion and configuration remain two-phase: read-only planning returns a deterministic `plan_id`, and mutation requires that exact ID plus explicit authorization. Build, flash, and debugger handoff are identity-pinned. Target and optional SVD selection come only from the Schema-v2 project model.

- **Inspect:** `stm32-toolkit keil inspect ...`
- **Convert:** `stm32-toolkit keil convert ... --dry-run|--apply`
- **Configure:** `stm32-toolkit project configure ... --dry-run|--apply`
- **Build:** `stm32-toolkit build ...`
- **Probe:** list one or more devices without opening a target session.
- **Flash:** requires an exact probe, build ID, ELF SHA-256, and explicit authorization.
- **Handoff:** begin requires explicit authorization and returns a one-time secret ticket; end reacquires, verifies, consumes, and releases ownership.
- **Typed debug:** variable/register reads, finite sampling, and Fault analysis are observation-only and identity-pinned.

Every hardware Skill starts with `stm32_project_context`, shows the exact probe and firmware identity, and never infers consent. Fake, skipped, deferred, or failed hardware evidence is never reported as physical success.

## Troubleshooting

Run the same bounded CHECK used by the setup Skill:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

The first package command is `stm32-toolkit doctor --json`. Doctor reports offline evidence for ARM GCC/GDB, CMake, Ninja, PyOCD, CubeMX, VS Code, and CMSIS-Pack without probing hardware or modifying the project. Missing external tools, extensions, drivers, or packs remain operator actions.

## Foundation and follow-on capabilities

### Delivered in version 0.4.0

- validated Schema-v2 projects, per-checkout workspace isolation, Keil inspection, conversion, generation, builds, and firmware identity;
- cross-process probe leases, identity-pinned flash, one-time external debugger handoff, typed DWARF/SVD reads, finite sampling, and Fault analysis;
- strict JSON CLI workflows, exactly 15 MCP tools, seven thin Skills, and one managed 0.4.0 runtime.

### Follow-on work

The 0.4 software surface is complete, but physical probe/board claims require the named real-hardware gates. Linux and physical gates that were not actually run remain deferred rather than fabricated.

Monitor groups, history, retention, storage, HTTP/WebSocket service, and UI are 0.5 scope. They remain user-created monitor groups; Toolkit 0.4.0 ships no invented presets. Keil-to-GCC migration remains one-way and never writes back to a Keil project.
