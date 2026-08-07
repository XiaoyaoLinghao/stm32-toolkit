# STM32 Toolkit

[简体中文](README_zh-CN.md) | English

STM32 Toolkit 0.3.0 turns one Keil uVision project into a reproducible ARM GNU/GCC build: read-only Keil inspection, a guarded ARMCC-to-GCC conversion plan, managed GCC/CMake and VS Code configuration, and bounded builds with firmware identity. It is the foundation for future AI-assisted STM32 coding, debugging, testing, and monitoring. It keeps shared project intent in the repository while isolating machine-owned runtime and session state for every checkout.

## Install directly from GitHub

This project is distributed directly from GitHub and is not submitted to a public plugin directory. Register the repository as a Claude Code plugin source, then install the plugin once at user scope:

```powershell
claude plugin marketplace add https://github.com/XiaoyaoLinghao/stm32-toolkit.git --scope user
claude plugin install stm32-toolkit@stm32-toolkit --scope user
```

Run `/reload-plugins` in an active Claude Code session, or restart Claude Code. The `marketplace` word in the first command is Claude Code's fixed command name; this repository remains the installation source and is not listed in a public catalog.

To update an existing installation after a new Toolkit version is released:

```powershell
claude plugin marketplace update stm32-toolkit
claude plugin update stm32-toolkit@stm32-toolkit --scope user
```

Toolkit uses the version in `.claude-plugin/plugin.json` as Claude Code's update key, so each published release must bump that version. Upgrading from 0.2.0 to 0.3.0 updates the managed runtime path from `runtime/0.2.0` to `runtime/0.3.0`; CHECK reports an existing 0.2.0 runtime as `broken` with `recommendedMode` `Repair`, and Repair quarantines it before promoting the 0.3.0 runtime.

Do not copy Skills manually and do not register a second MCP server. Claude Code discovers the plugin's standard `skills/` directory and bundled `.mcp.json`. Version 0.3.0 exposes exactly four Skills: `/stm32-toolkit:setup-stm32-env`, `/stm32-toolkit:migrate-keil`, `/stm32-toolkit:configure-stm32-project`, and `/stm32-toolkit:build-firmware`. Unfinished skill sources are preserved under `requirements/follow-on-skills/`, outside Claude's automatic Skill discovery.

Run `/stm32-toolkit:setup-stm32-env` after installation. Its Skill-only CHECK works before MCP startup and always reports the managed runtime as `missing`, `healthy`, or `broken`. After explicit authorization, Bootstrap or Repair builds in a unique plugin-data staging directory, validates Toolkit 0.3.0 plus doctor, and only then promotes it. Repair quarantines the failed runtime for recovery. Host Python 3.10+ is only a bounded bootstrap prerequisite and never an MCP fallback.

## Automatic project binding and isolation

When the plugin is enabled, its bundled MCP configuration automatically starts the managed runtime and binds the server to `${CLAUDE_PROJECT_DIR}`. The launcher always uses `${CLAUDE_PLUGIN_DATA}/runtime/0.3.0/Scripts/python.exe`; it never selects a system interpreter.

Two kinds of data stay deliberately separate:

- `.stm32-project.json` is the shared, version-controlled project configuration. Its `logicalProjectId` identifies the logical firmware project.
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` contains isolated user state for one canonical checkout, including sessions, logs, diagnostics, caches, and future monitor state. Separate clones get different workspace IDs even when they share a logical project ID.

The MCP process is bound to one canonical project root and exposes exactly seven tools: `stm32_doctor`, `stm32_project_detect`, `stm32_project_context`, `stm32_keil_inspect`, `stm32_keil_convert`, `stm32_project_configure`, and `stm32_build`. No tool accepts a project root, command, or environment argument. Unconfigured Keil-only or unknown projects remain read-only and do not receive a workspace until a valid `.stm32-project.json` exists.

## Workflows and authorization

Every conversion and configuration workflow is two-phase. The read-only plan returns a deterministic `plan_id`; mutation requires the caller to return that exact ID with explicit authorization. The core then independently replans from current disk state and rechecks every digest, Git, and drift guard immediately before its first write. Applying with a missing, malformed, or stale plan ID fails closed (`AUTHORIZATION_REQUIRED` / `PLAN_CHANGED`) without writes.

- **Inspect**: `stm32-toolkit keil inspect --project <path> [--uvprojx <rel>] [--target-name <name>] [--no-baseline] --json` returns the read-only `inspection` and optional `baseline` evidence.
- **Conversion plan**: `stm32-toolkit keil convert --project <path> --dry-run --json` shows blockers, exact changed paths, diffs, and the plan ID.
- **Conversion apply**: `stm32-toolkit keil convert --project <path> --apply --plan-id <sha256> --authorized --json` applies only the exact plan.
- **Configuration plan**: `stm32-toolkit project configure --project <path> --dry-run --json` shows file statuses, diffs, blockers, and the plan ID.
- **Configuration apply**: `stm32-toolkit project configure --project <path> --apply --plan-id <sha256> --authorized --json` installs the managed files.
- **Build**: `stm32-toolkit build --project <path> --preset {arm-debug,arm-release} [--clean] [--timeout-seconds 300] [--json]` runs the guarded CMake/Ninja build and publishes build logs, a build result, and firmware identity. The CLI invocation is itself the explicit user action; the MCP `stm32_build` tool additionally requires `authorized=true`.

The same operations are available to Claude Code through the MCP tools and the three workflow Skills, which always start with `stm32_project_context`, show the read-only plan and evidence, and request authorization at the mutation boundary. A Skill never infers consent from a previous read-only call.

The VS Code tasks generated for a configured project call only the supported `stm32-toolkit build --preset ... --project ${workspaceFolder}` contract; flash and debug handoff commands are not exposed in this release.

## Troubleshooting

The first troubleshooting command is `stm32-toolkit doctor --json`. Run it through the managed runtime so diagnosis uses the same environment as MCP:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -PluginRoot '${CLAUDE_PLUGIN_ROOT}' -PluginData '${CLAUDE_PLUGIN_DATA}' -ProjectDir '${CLAUDE_PROJECT_DIR}'
```

Doctor reports offline evidence for ARM GCC/GDB, CMake, Ninja, PyOCD, CubeMX, and VS Code without probing hardware or changing the project. `/stm32-toolkit:setup-stm32-env` also reports existing VS Code extension and CMSIS-Pack inventory gaps. Missing hardware tools, extensions, drivers, or packs are reported for the user to resolve; setup does not install them.

If MCP startup says the runtime is missing, rerun `/stm32-toolkit:setup-stm32-env`. The plugin-bundled `.mcp.json` is authoritative, so manual `claude mcp add` registration is neither required nor supported. A failed setup never promotes a partial runtime; authorize `Repair` only when CHECK reports `broken`.

## Foundation and follow-on capabilities

### Delivered in version 0.3.0

- versioned Python package and stable JSON result envelopes (`stm32-toolkit/1`);
- STM32 project detection and validated Schema v1/v2 `.stm32-project.json` loading;
- deterministic per-checkout workspace IDs and isolated plugin-data paths;
- read-only Keil inspection and AXF/MAP baseline evidence;
- guarded ARMCC-to-GCC conversion plans with exact patches, blockers, and deterministic plan IDs;
- managed GCC/CMake, linker, and VS Code configuration with drift protection;
- bounded CMake/Ninja builds with MAP validation, ELF identity, and failure records;
- offline doctor, project context, CLI wrappers, and seven project-bound MCP tools;
- user-scope plugin layout, one-time managed runtime bootstrap guidance, and automatic MCP binding.

### Follow-on work

The toolkit does not yet claim hardware flashing, probe leases, live target inspection, breakpoint debugging, host/target test execution, or a monitoring UI. Those capabilities require later implementation and hardware-aware safety contracts.

Keil-to-GCC migration is one-way: migration inspects Keil input and generates GCC/CMake configuration, but it must not write back to or synchronize the Keil project. The existing monitor requirement is preserved but monitoring is not implemented in this release. The contract requires user-created monitor groups; the toolkit does not ship or invent named presets.
