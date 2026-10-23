---
name: flash-firmware
description: Use when a Claude Code user asks to discover a probe and flash an identity-pinned STM32 firmware image.
---

# Flash Firmware

## Workflow

1. Call `stm32_project_context` with no arguments. Read `capabilityDetails`, not only the legacy booleans. Normally `flash` is `not-evaluated` because context does not enumerate probes; that means hardware state is unprobed, not that flashing is unavailable. If a fresh build has `data.build.sourceBaseline="input-snapshot-v1"`, `capabilityDetails.flash` is `blocked` with `FIRMWARE_PROVENANCE_UNSUPPORTED`: report that limitation and stop before discovery for a flash request. A false legacy hardware boolean alone never establishes that flashing is unavailable.
2. **Discovery-only request.** If the user only asks which probes are connected, call `stm32_probe_list` and report its evidence. Probe discovery requires no manifest, build, target, or SVD, is read-only, and grants no board-modification permission. Snapshot firmware provenance does not block this discovery-only request. Do not require or discuss a build, and do not flash. If `workspaceId` is null and `discovery.status` is `unbound`, say so and never invent a workspace ID. Finish here.
3. **Flash request.** Require a current successful build identity. Read `data.build.buildId` and `data.build.elfSha256` (the ELF SHA-256) from the context; if the build evidence is blocked or stale, report that and stop. A schema-2 identity (null `gitHead`/`gitDirty`, `sourceBaseline="input-snapshot-v1"`) is build-only: the tool refuses it with `FIRMWARE_PROVENANCE_UNSUPPORTED` before probe, lease or attach. Do not fabricate a Git commit. The project model remains the authority for target and optional SVD selection.
4. Call `stm32_probe_list` and show its returned evidence. Require the user to choose one exact `probeId`; zero or multiple probes never imply a default.
5. Restate the exact probe, `expectedBuildId`, `expectedElfSha256`, project target, and that flash modifies the selected board.
6. Obtain explicit authorization for that exact operation. Without it, call nothing intrusive and stop.
7. Call `stm32_flash` with only the selected `probeId`, `expectedBuildId`, `expectedElfSha256`, and `authorized=true`.
8. Return the complete operation result, including stable failure code, flash-result evidence, and `details.postFlash`. A successful flash proves only the existing programming and readback checks; target state is unknown and program execution is unverified.

## Boundaries

- Never invoke PyOCD, a compiler, or a process directly. Call only the named MCP tools above.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, or memory location.
- Never weaken stale-build, dirty-project, lease, or authorization failures.
- Never treat unavailable Git (`gitHead=null`, `gitDirty=null`) as a clean repository, and never fabricate a commit to admit snapshot firmware to a hardware path.
- Never fabricate physical success. A skipped, simulated, deferred, or failed hardware gate is not a board PASS.
- Under-reset recovery is a separately selected, explicitly authorized policy for a target that cannot use ordinary attach. Do not select it automatically after a failure. Recovery flash may leave the target halted; do not claim that it reset or ran.
- Diagnose a failed attach from its returned stage and last verified state. Do not retry, reset, resume, or add a second hardware operation without fresh authorization.
- Probe enumeration is discovery only; it does not verify target identity, current firmware, or flash readiness. A full Fault analysis requires its own controlled halt authorization; running observation does not grant it.
