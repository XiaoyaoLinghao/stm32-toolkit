---
name: read-var
description: Use when a Claude Code user asks to read or finitely sample typed firmware variables from one exact STM32 probe.
---

# Read Variables

## Workflow

1. Call `stm32_project_context` with no arguments. Require a current identity and retain the exact `buildId` and ELF SHA-256. The Toolkit derives typed locations from that ELF and target/SVD selection from the project model.
2. Call `stm32_probe_list`; require the user to select one exact probe.
3. Ask for DWARF variable expressions. Do not translate them into locations or accept caller-provided locations.
4. For one snapshot call `stm32_variable_read`. For a finite series call `stm32_variable_sample` with bounded interval, count, and duration. Pass the exact probe and identity pins.
5. Return every item result and its evidence. Preserve stable per-item failures instead of replacing them with guessed values.

## Boundaries

- Call only `stm32_project_context`, `stm32_probe_list`, `stm32_variable_read`, and `stm32_variable_sample`.
- This Skill is observation-only. It never writes memory, resumes execution, controls the core, or releases probe ownership.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, memory location, size, or type layout.
- Never fabricate physical success. A fake, skipped, deferred, or failed gate cannot prove a live-board read.
