---
name: debug-firmware
description: Use when a Claude Code user asks to hand a selected STM32 probe to an external debugger, read typed registers, or analyze Fault state.
---

# Debug Firmware

## Workflow

1. Call `stm32_project_context` with no arguments. Require current managed firmware identity and retain the exact `buildId` and ELF SHA-256. Target and optional SVD always come from the project model. Read `data.firmwareRoutes` only to distinguish routes: the imported route is `not-evaluated` in context and is not a debug, Monitor, Target-test, or recovery path. If context fails, preserve the full error; a model or binding error does not prove another endpoint is absent and must not be bypassed. An imported external-firmware receipt is never a substitute for the current managed build identity or a remedy for a debug failure. A project delivered by `keil convert` must first be bound at its `outputRoot`, configured and built through the normal GCC route. Git is optional for that delivery and build, but this unpublished branch's managed firmware admission still requires Git-shaped provenance for debug handoff, so a snapshot build is reported as blocked instead of debugged.
2. Call `stm32_probe_list`; ask the user to select one exact probe. Probe discovery requires no manifest, build, target, or SVD and is read-only. Never choose a wildcard or the first device implicitly. If discovery is `unbound`, report that status and never invent a workspace ID; target identity and flash readiness remain not evaluated.
3. For external debugging, explain that `stm32_debug_handoff_begin` releases Toolkit ownership. Obtain explicit authorization for the exact probe and identity pins, call it with `authorized=true`, and protect the returned one-time ticket from logs or summaries. After the external debugger stops, call `stm32_debug_handoff_end` once with that ticket to reacquire, verify, consume, and release the transient Toolkit session.
   Preserve the returned canonical `cortexDebug` identity and `ticket`. To wrap the supported Cortex-Debug launch, require `cortexDebugLaunch.schemaVersion=1` and verify `cortexDebugLaunch.profile.cortexDebug=1.12.1` and `cortexDebugLaunch.profile.pyocd=0.45.1` against the actual installed versions; if the envelope is missing or any version differs, stop without an implicit fallback. Use `cortexDebugLaunch.configuration` as-is and add only `name`, `type`, and verified `serverpath`, `gdbPath`, and `cmsisPack`. Do not edit its raw-ID `serverArgs`, ready regex, or `cwd`, and do not generate tasks.
4. For named register paths, call `stm32_register_read`. For the controlled Fault snapshot, explicitly pass `haltForAnalysis=true` through MCP or `--halt-for-analysis` through the CLI; omitting it keeps the existing observe-only path. This selection performs one authorized halt, one analysis while halted, and one fresh authorized resume with a verified running postcondition. If identity, state, halt or resume is unknown or fails, report failure and stop without retrying, reconnecting, resetting, or flashing. Pass the exact probe, `buildId`, and ELF SHA-256; report partial item failures exactly.
5. Return the complete operation result and evidence.

## Boundaries

- Call only `stm32_project_context`, `stm32_probe_list`, `stm32_debug_handoff_begin`, `stm32_debug_handoff_end`, `stm32_register_read`, and `stm32_fault_analyze`.
- Debug, Monitor, Target tests, and recovery require the current managed build identity. Never offer an imported receipt, an imported flash result, or an `stm32_firmware_*` route as their remedy.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, memory location, or access size.
- Never expose the handoff ticket, service credential, or local runtime path.
- Never fabricate physical success. Simulated, skipped, deferred, or failed probe evidence remains exactly that.
- The shared OBSERVE attach may briefly halt and resume the core while connecting. That connection side effect is not state-preserving and is not halted-run analysis; only the explicitly authorized controlled Fault path claims a controlled halt.
