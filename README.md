# STM32 Toolkit

[简体中文](README_zh-CN.md) | English

STM32 Toolkit is a local, Agent-driven STM32 development control plane for VS Code. Its generic CLI/MCP core coordinates one-way Keil-to-GCC migration, reproducible CubeCLT builds, identity-pinned PyOCD probe workflows, Cortex-Debug handoff, project-isolated Monitor data, tests, and evidence-driven diagnosis. Claude Code is the currently released thin client adapter, not a separate product runtime.

The published 0.5.0 packaging below remains the current installable baseline. Local 0.6 product code has completed its software scenarios with named physical evidence deferred; it has not been pushed, merged, tagged, or released. The approved 0.7–1.0 direction adds CubeMX-backed new-project creation, one resumable vertical acceptance path, Windows/Python 3.12 release convergence, and a final unified real-project hardware campaign.

## Product tool boundary

- **STM32CubeMX 6.18:** generates MCU pin/clock/peripheral, startup, HAL/LL, and native CMake project bytes for new projects.
- **STM32CubeCLT 1.22.0:** supplies ARM GCC, CMake, Ninja, CubeProgrammer/ST tools, target facts, and SVD data. Toolkit uses GCC/CMake/Ninja; bundled ST flash/debug tools are not parallel product backends.
- **PyOCD:** remains the sole production Probe backend for flash, observation, target transports, and debug handoff.
- **Cortex-Debug:** provides the human VS Code debug UI after an explicit one-time PyOCD handoff.
- **STM32 Toolkit:** owns project identity, authorization, orchestration, Monitor/Test/Diagnostic contracts, and Agent-neutral CLI/MCP behavior.

The ST STM32 VS Code extension is not required. The recommended editor extensions remain C/C++, CMake Tools, and Cortex-Debug.

## VS07-A read-only creation planning

On supported Windows hosts running CPython `>=3.12,<3.13`, inspect a new project request with:

```powershell
stm32-toolkit project create-plan --project-root . --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --json
```

The command returns a deterministic plan, tool/profile and destination digests, or closed remediation blockers. CubeMX 6.18 is the generator; CubeCLT 1.22.0 supplies GCC/CMake/Ninja and is not a replacement for CubeMX. `CUBEMX_MISSING` means CubeMX must be installed or exposed through a trusted support profile before planning can proceed. VS07-A never runs CubeMX, creates staging, writes the destination, or applies a plan. The equivalent Agent-neutral MCP operation is `stm32_project_create_plan`.

## VS07-B authorized creation and build

After reviewing an unchanged plan, issue one expiring capability and then consume it exactly once:

```powershell
stm32-toolkit project create-prepare --project-root . --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --plan-id PLAN_ID --action-digest ACTION_DIGEST --json
stm32-toolkit project create-apply --project-root . --authorization-digest AUTHORIZATION_DIGEST --authorized --json
```

Preparation is destination-read-only. Apply generates in sibling staging, validates native CMake/IOC facts, reuses Toolkit configure plus Debug and Release builds, and activates only after both builds succeed. Replays, drift, missing Cube firmware repositories, protocol/build failures, or activation failures close with typed errors and no half-created destination. The MCP equivalents are `stm32_project_create_prepare` and `stm32_project_create_apply`. The verified host has CubeMX 6.18.1-RC2, CubeCLT 1.22.0, and the `STM32Cube_FW_F4_V1.28.3` offline package. This local candidate completed the MCU and captured-IOC native software scenarios, including configure, Debug/Release builds, activation, and residue checks, and passed Sol's independent complete-diff review. No hardware, installation, remote, or release action was performed.

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

Claude Code discovers the plugin's standard `skills/` directory and bundled `.mcp.json` automatically. Do not copy Skills or register a second MCP server. Version 0.5.0 exposes exactly eight Skills:

- `/stm32-toolkit:setup-stm32-env`
- `/stm32-toolkit:migrate-keil`
- `/stm32-toolkit:configure-stm32-project`
- `/stm32-toolkit:build-firmware`
- `/stm32-toolkit:flash-firmware`
- `/stm32-toolkit:debug-firmware`
- `/stm32-toolkit:read-var`
- `/stm32-toolkit:stm32-monitor`

Run `/stm32-toolkit:setup-stm32-env` after installation. CHECK reports the managed runtime as `missing`, `healthy`, or `broken`. An existing 0.3.0 runtime is `broken` with `recommendedMode` `Repair`; after explicit authorization Repair quarantines it before atomically promoting 0.5.0. Host Python 3.10+ is only a bounded bootstrap prerequisite and never an MCP fallback.

## Automatic project binding and isolation

The bundled MCP configuration binds one server automatically to `${CLAUDE_PROJECT_DIR}`. The launcher uses only `${CLAUDE_PLUGIN_DATA}/runtime/0.5.0/Scripts/python.exe` and never a system interpreter.

- `.stm32-project.json` is the shared, version-controlled project configuration.
- `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` contains machine-owned state for one canonical checkout. Separate clones have distinct workspaces and sessions.

The server exposes exactly 15 project-bound tools: `stm32_doctor`, `stm32_project_detect`, `stm32_project_context`, `stm32_keil_inspect`, `stm32_keil_convert`, `stm32_project_configure`, `stm32_build`, `stm32_probe_list`, `stm32_flash`, `stm32_debug_handoff_begin`, `stm32_debug_handoff_end`, `stm32_variable_read`, `stm32_variable_sample`, `stm32_register_read`, and `stm32_fault_analyze`. They do not accept a project root, data root, command, environment, service credential, target override, SVD override, ELF path, or memory address.

## Monitor UI

`/stm32-toolkit:stm32-monitor` is the explicit human path to the project-isolated Monitor UI. It first reads project context, explains that the UI is observation-only with zero presets, and only after the user explicitly asks to open this project's UI does it run the human launcher:

```powershell
& '${CLAUDE_PLUGIN_ROOT}/bin/stm32-monitor.cmd' open --project '${CLAUDE_PROJECT_DIR}' --data-root '${CLAUDE_PLUGIN_DATA}'
```

The launcher starts one loopback `127.0.0.1` Monitor service in the foreground and opens its fragment-token URL in the default browser exactly once. It never prints, persists, copies, or logs the access URL. The page starts with zero monitor groups and never connects a probe or starts sampling automatically; connect, group creation, import/export, and sampling start/pause/resume/stop remain explicit page actions. `serve --json` is the machine command and never opens a browser.

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

### Delivered in version 0.5.0

- validated Schema-v2 projects, per-checkout workspace isolation, Keil inspection, conversion, generation, builds, and firmware identity;
- cross-process probe leases, identity-pinned flash, one-time external debugger handoff, typed DWARF/SVD reads, finite sampling, and Fault analysis;
- strict JSON CLI workflows, exactly 15 MCP tools, eight thin Skills, and one managed 0.5.0 runtime;
- an offline Monitor UI served by the same loopback process, explicit human `stm32-monitor open`, verified CSV/JSONL history export, and user group schema JSON import/export.

### Repository development status

The local 0.6 candidate adds immutable Host/Target test evidence, four Target transports, diagnostic and fix-verification lifecycles, Monitor comparison/markers/bundles, and public CLI/MCP adapters. Its software scenarios are accepted locally; historical 0.4 hardware checks and the 0.6 physical scenario are deliberately retained for the unified 1.0 campaign. This is not a published 0.6 release claim.

The approved 0.7–1.0 design and progress baseline are:

- 0.7: read-only creation planning, authorized CubeMX generation/build, and safe regeneration;
- 0.8: one resumable, isolated vertical scenario adapter for Keil and CubeMX inputs;
- 0.9: Python 3.12 Windows runtime, Agent adapters, installation, upgrade, security, and release artifacts;
- 1.0: one real legacy-Keil scenario and one new-CubeMX scenario on named physical hardware.

Monitor groups and UI state remain user-created and project-isolated; the Toolkit ships no invented presets. Keil-to-GCC migration remains one-way and never writes back to a Keil project.
