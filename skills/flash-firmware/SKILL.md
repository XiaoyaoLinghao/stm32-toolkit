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
6. Return the complete operation result, including stable failure code and flash-result evidence.

## Boundaries

- Never invoke PyOCD, a compiler, or a process directly. Call only the named MCP tools above.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, or memory location.
- Never weaken stale-build, dirty-project, lease, or authorization failures.
- Never fabricate physical success. A skipped, simulated, deferred, or failed hardware gate is not a board PASS.
