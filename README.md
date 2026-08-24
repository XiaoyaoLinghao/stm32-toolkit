# STM32 Toolkit 0.9

[简体中文](README_zh-CN.md) | English

STM32 Toolkit is a local, Agent-neutral STM32 development control plane. The CLI and MCP server
share one product contract for project identity, Keil-to-GCC migration, builds, probe workflows,
Monitor, tests, and evidence-driven diagnosis. Claude Code is a thin adapter to that contract.

## VS09-A status and runtime boundary

This repository contains a local 0.9.0 VS09-A candidate. It has not been pushed, tagged, or
released. The release contract is CPython `>=3.12,<3.13`; the managed interpreter is selected only
from `DATA_ROOT/runtime/0.9.0/Scripts/python.exe`. A system interpreter is never an MCP fallback.
The setup helper's CHECK mode is read-only. Bootstrap and Repair require explicit authorization,
stage locally, validate the Toolkit and Monitor packages, and promote only after validation.

The current runtime is generic: an integration may choose any absolute `TOOLKIT_ROOT`,
`DATA_ROOT`, and `PROJECT_ROOT`. The launcher reads only `STM32_TOOLKIT_DATA_ROOT`; the CLI requires
an explicit `--project-root` for every project-bound command.

```powershell
stm32-toolkit --project-root C:\work\blinky doctor --json
stm32-toolkit --project-root C:\work\blinky build --preset Debug --json
```

## Generic MCP template

The generic configuration uses an **absolute launcher**, explicit project/data arguments, and only
`STM32_TOOLKIT_DATA_ROOT` in `env`:

```json
{
  "mcpServers": {
    "stm32-toolkit": {
      "command": "C:\\tools\\stm32-toolkit\\bin\\stm32-toolkit-mcp.cmd",
      "args": [
        "--project-root", "C:\\work\\blinky",
        "--data-root", "C:\\data\\stm32-toolkit"
      ],
      "env": {
        "STM32_TOOLKIT_DATA_ROOT": "C:\\data\\stm32-toolkit"
      }
    }
  }
}
```

The Claude `.mcp.json` is only a mapping to the same contract. Claude automatically substitutes
the inline paths while it keeps one server, substitutes
`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`, and `${CLAUDE_PLUGIN_DATA}` inline, passes the
explicit project/data arguments, and maps only `STM32_TOOLKIT_DATA_ROOT` to plugin data. It does
not add a second server or a host-Python fallback.

## CLI, setup, and isolation

Run `/stm32-toolkit:setup-stm32-env` first. CHECK reports `missing`, `healthy`, or `broken` and
does not mutate the project. The generic invocation is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File '${CLAUDE_PLUGIN_ROOT}/bin/setup-stm32-env.ps1' -Mode Check -ToolkitRoot '${CLAUDE_PLUGIN_ROOT}' -DataRoot '${CLAUDE_PLUGIN_DATA}' -ProjectRoot '${CLAUDE_PROJECT_DIR}'
```

`.stm32-project.json` is the version-controlled project configuration. Machine-owned state lives
under `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>` (or the equivalent generic `DATA_ROOT`), so
separate clones have distinct workspaces and sessions. Monitor groups remain user-created; the
product's user-created monitor groups are never replaced by presets.
Toolkit ships no invented presets. The Monitor Skill temporarily supplies the generic data-root
environment to its launcher and restores the previous process value.

## Skills (exactly eight)

The public Skills are:

- `/stm32-toolkit:setup-stm32-env`
- `/stm32-toolkit:migrate-keil`
- `/stm32-toolkit:configure-stm32-project`
- `/stm32-toolkit:build-firmware`
- `/stm32-toolkit:flash-firmware`
- `/stm32-toolkit:debug-firmware`
- `/stm32-toolkit:read-var`
- `/stm32-toolkit:stm32-monitor`

Each Skill is a thin handoff to the same CLI/MCP behavior. Hardware Skills first establish project
context and exact firmware/probe identity; fake, skipped, deferred, or failed hardware evidence is
never described as physical success. Keil-to-GCC migration is one-way and never writes back to a
Keil project.

## MCP inventory (all 48 names)

The closed public inventory is grouped by responsibility:

### Project

`stm32_doctor`, `stm32_project_detect`, `stm32_project_context`, `stm32_project_create_plan`,
`stm32_project_create_prepare`, `stm32_project_create_apply`, `stm32_project_regenerate_plan`,
`stm32_project_regenerate_prepare`, `stm32_project_regenerate_apply`, `stm32_keil_inspect`,
`stm32_keil_convert`, `stm32_project_configure`

### Build

`stm32_build`

### Probe

`stm32_probe_list`, `stm32_flash`, `stm32_debug_handoff_begin`, `stm32_debug_handoff_end`,
`stm32_variable_read`, `stm32_variable_sample`, `stm32_register_read`, `stm32_fault_analyze`

### Diagnostic

`stm32_diagnostic_start`, `stm32_diagnostic_show`, `stm32_diagnostic_begin`,
`stm32_diagnostic_hypothesis_add`, `stm32_diagnostic_hypothesis_assess`,
`stm32_diagnostic_plan_add`, `stm32_diagnostic_plan_run`, `stm32_test_target_replay`,
`stm32_diagnostic_source_change_declare`, `stm32_diagnostic_verification_plan_add`,
`stm32_diagnostic_verification_start`, `stm32_diagnostic_marker_attach`,
`stm32_diagnostic_verification_complete`, `stm32_diagnostic_verification_show`

### Test

`stm32_test_host_discover`, `stm32_test_host_run`, `stm32_test_show`,
`stm32_test_target_prepare`, `stm32_test_target_execute`

### Acceptance

`stm32_acceptance_scenario_describe`, `stm32_acceptance_scenario_record`,
`stm32_acceptance_scenario_show`, `stm32_acceptance_attempt_begin`,
`stm32_acceptance_attempt_checkpoint`, `stm32_acceptance_attempt_authorize_source_change`,
`stm32_acceptance_attempt_show`, `stm32_acceptance_attempt_resume`

The server exposes exactly these 48 names. Registration order and schemas are part of the
Agent-neutral contract; callers cannot smuggle an alternate project root, environment, target,
ELF, SVD, address, or service credential through a project-bound operation.

## Product tool boundary

STM32CubeMX generates new-project MCU, pin, clock, peripheral, startup, HAL/LL, and native CMake
bytes. STM32CubeCLT supplies ARM GCC, CMake, Ninja, ST tools, target facts, and SVD data. PyOCD is
the production probe backend, and Cortex-Debug is the human VS Code UI after an explicit handoff.
External tool, extension, driver, and CMSIS-Pack checks are bounded and read-only; missing tools
remain operator actions.

## VS09-B boundary

VS09-B owns pinned-source installation, secure upgrade and downgrade, malicious-name tests,
checksums, archives, SBOM, licenses, compatibility, and troubleshooting. Those controls are not
claimed as completed release evidence by this local VS09-A candidate. Hardware, remote, PR, merge,
tag, and release actions are likewise outside this candidate.

Historical 0.5 evidence remains in its labelled release-controller and replay fixtures. It is
preserved as history, not presented as the current runtime or inventory.
