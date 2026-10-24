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
8. Return the complete operation result, including any stable failure code and flash-result evidence. A successful result carries `details.postFlash` with `targetState=unknown` and `runVerified=false`; some early failure results do not contain `postFlash`, so report the actual returned fields rather than assuming it. A successful flash proves only the existing programming and readback checks; target state is unknown and program execution is unverified.

## Imported external firmware (current source/candidate only)

Use this separate route only when the bound server actually exposes
`stm32_firmware_import`, `stm32_firmware_admit`, and `stm32_flash_imported`
and their input schema matches this workflow; the published v1.2.0 runtime
(48 tools) does not. Check the installed launcher version, `doctor --json`
`data.publicInventory`, and the real tool schema before promising the route.
It needs no managed `.stm32-project.json`, Git baseline, build receipt, or
SVD. `capabilities.flash` in project context describes the managed route only
and does not block this route.

1. Ask for the original project-relative firmware path, its exact lowercase
   SHA-256, the format (`elf`; AXF is parsed as ELF, `hex`, or `bin`), the exact
   supported pyOCD target, and the reviewed internal-Flash regions. BIN also
   requires an explicit uint32 base address and carries no debug symbols.
2. Call `stm32_firmware_import` with no `planId` to obtain the read-only PLAN.
   Show `data.planId`, `data.importId`, `data.source.sha256` (original file)
   and `data.image.sha256` (normalized programming image, with segments and
   entry). Admission and flash results report flat `sourceSha256` and
   `imageSha256` fields. Never conflate the two hashes.
3. Obtain explicit authorization for the offline import copy, then repeat the
   exact request with that `data.planId` and `authorized=true`. Import
   authorization covers only the immutable copy and never authorizes hardware.
4. Call `stm32_firmware_admit` with the exact `importId` and original source
   SHA-256. Report `offlineReady`, `hardwareVerified=false`, and the remaining
   requirements. Admission success is not a flash success, not a current build,
   and not a reusable token. Never fabricate a manifest, `buildId`, or Git state
   to replace it.
5. Only if the user then asks to flash: call `stm32_probe_list`, require one
   exact `probeId`, restate the exact import, probe, and target, and obtain a
   new explicit authorization for this exact hardware operation.
6. Call `stm32_flash_imported` with that `probeId`, `importId`, original source
   SHA-256, and `authorized=true`. Report the complete result. A successful
   result includes the external-flash receipt path and `details.postFlash`
   (`targetState=unknown`, `runVerified=false`); some early failure results do
   not contain `postFlash`. Report the actual returned fields.

An imported receipt proves only the programming/readback checks for that
immutable snapshot. It does not unlock debug, Monitor, Target tests, legacy
flash evidence, reset/recovery, or a managed build identity.

## Boundaries

- Never invoke PyOCD, a compiler, or a process directly. Call only the named MCP tools above.
- Never accept a caller-selected target, SVD, ELF path, workspace, endpoint, token, or memory location.
- Never weaken stale-build, dirty-project, lease, or authorization failures.
- Never treat unavailable Git (`gitHead=null`, `gitDirty=null`) as a clean repository, and never fabricate a commit to admit snapshot firmware to a hardware path.
- Never fabricate physical success. A skipped, simulated, deferred, or failed hardware gate is not a board PASS.
- Under-reset recovery is a separately selected, explicitly authorized policy for a target that cannot use ordinary attach. Do not select it automatically after a failure. Recovery flash may leave the target halted; do not claim that it reset or ran.
- Diagnose a failed attach from its returned stage and last verified state. Do not retry, reset, resume, or add a second hardware operation without fresh authorization.
- Probe enumeration is discovery only; it does not verify target identity, current firmware, or flash readiness. A full Fault analysis requires its own controlled halt authorization; running observation does not grant it.
