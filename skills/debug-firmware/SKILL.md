---
name: debug-firmware
description: Use when a Claude Code user asks to hand a selected STM32 probe to an external debugger, read typed registers, or analyze Fault state.
---

# Debug Firmware

## Workflow

1. Call `stm32_project_context` with no arguments. Require current firmware identity and retain the exact `buildId` and ELF SHA-256. Target and optional SVD always come from the project model.
2. Call `stm32_probe_list`; ask the user to select one exact probe. Never choose a wildcard or the first device implicitly.
3. For external debugging, explain that `stm32_debug_handoff_begin` releases Toolkit ownership. Obtain explicit authorization for the exact probe and identity pins, call it with `authorized=true`, and protect the returned one-time ticket from logs or summaries. After the external debugger stops, call `stm32_debug_handoff_end` once with that ticket to reacquire, verify, consume, and release the transient Toolkit session.
4. For named register paths, call `stm32_register_read`. For a Fault snapshot, call `stm32_fault_analyze`. Pass the exact probe, `buildId`, and ELF SHA-256; report partial item failures exactly.
5. Return the complete operation result and evidence.

## Boundaries

- Call only `stm32_project_context`, `stm32_probe_list`, `stm32_debug_handoff_begin`, `stm32_debug_handoff_end`, `stm32_register_read`, and `stm32_fault_analyze`.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, memory location, or access size.
- Never expose the handoff ticket, service credential, or local runtime path.
- Never fabricate physical success. Simulated, skipped, deferred, or failed probe evidence remains exactly that.
