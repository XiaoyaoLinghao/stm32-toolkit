---
name: flash-firmware
description: Use when a Claude Code user asks to discover a probe and flash an identity-pinned STM32 firmware image.
---

# Flash Firmware

## Workflow

1. Call `stm32_project_context` with no arguments. Require a current successful build identity and record its exact `buildId` and ELF SHA-256. The project model remains the authority for target and optional SVD selection.
2. Call `stm32_probe_list` and show its returned evidence. Require the user to choose one exact probe; zero or multiple probes never imply a default.
3. Restate the exact probe, `buildId`, ELF SHA-256, project target, and that flash modifies the selected board.
4. Obtain explicit authorization for that exact operation. Without it, call nothing intrusive and stop.
5. Call `stm32_flash` with only the selected probe, the exact identity pins, and `authorized=true`.
6. Return the complete operation result, including stable failure code, flash-result evidence, and `details.postFlash`. A successful flash proves only the existing programming and readback checks; target state is unknown and program execution is unverified.

## Boundaries

- Never invoke PyOCD, a compiler, or a process directly. Call only the named MCP tools above.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, or memory location.
- Never weaken stale-build, dirty-project, lease, or authorization failures.
- Never fabricate physical success. A skipped, simulated, deferred, or failed hardware gate is not a board PASS.
- Under-reset recovery is a separately selected, explicitly authorized policy for a target that cannot use ordinary attach. Do not select it automatically after a failure. Recovery flash may leave the target halted; do not claim that it reset or ran.
- Diagnose a failed attach from its returned stage and last verified state. Do not retry, reset, resume, or add a second hardware operation without fresh authorization. A full Fault analysis requires its own controlled halt authorization; running observation does not grant it.
