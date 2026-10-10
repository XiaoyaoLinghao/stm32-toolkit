---
name: migrate-keil
description: Use when a Claude Code user asks to inspect a Keil uVision project or migrate ARMCC sources to ARM GNU GCC with a guarded, explicitly authorized conversion.
---

# Migrate Keil Project

## Workflow

1. **Context first.** Call `stm32_project_context` (no arguments). `hardwareDiscovery=not-performed` means no probe was queried. `keilInspect` and `keilConvert` mean a candidate exists, not that conversion has no blockers. If either is `false`, report the context evidence and stop.
2. **Select and inspect.** Use `project.files` to identify the project-root-relative `.uvprojx`. For multiple candidates, ask the user to choose one. Call `stm32_keil_inspect(uvprojx="<selected relative path>", includeBaseline=true)`; if target selection is required, obtain the exact target name and inspect again with `targetName`. Keep the selected project path and target name for every later call. Show the selected device, warnings, and baseline availability. `baseline.available` only means a historical AXF or MAP was found and parsed; it does not prove a current build, toolchain, source identity, or authorized baseline.
3. **Read-only plan.** Call `stm32_keil_convert(uvprojx="<same path>", targetName="<same target>")` with no `planId` and no `authorized` — this returns the deterministic `keil-conversion-plan`. Show the plan's `plan_id`, every blocker with its portable path and category, and the exact changed paths and diffs from `patches`.
4. **Stop on blockers.** If `blockers` is non-empty, report them and stop; never apply a blocked plan.
5. **Authorize.** Ask the user for explicit authorization for the exact displayed `plan_id`. Never infer consent from the earlier read-only calls.
6. **Apply.** Only after the user authorizes, call `stm32_keil_convert(uvprojx="<same path>", targetName="<same target>", planId="<exact plan_id>", authorized=true)`. The core replans and rechecks the digest, Git, and drift guards before its first write.
7. **Return the result.** Report the `keil-conversion-apply` result: the conversion report path, the Schema v2 `.stm32-project.json` path, patched source paths, and any warnings. If the result is a failure (`AUTHORIZATION_REQUIRED`, `PLAN_CHANGED`, `MIGRATION_*`), report the exact code and details and stop.

## Rules

- `stm32_keil_inspect` and the plan call are read-only; verify the plan before any mutation.
- UTF-8 source, ARMCC startup assembly, Git index/tracked/untracked changes, and an existing conflicting manifest can block migration. Show the exact relative paths and safe next steps from the result. Toolkit does not silently transcode sources, replace startup code, remove untracked files, or overwrite a conflicting manifest.
- The apply call is the only mutation. Pass exactly the plan ID shown to the user.
- Do not parse `.uvprojx` XML, rewrite source files, render templates, or run compilers yourself.
- Never claim success; report the returned `OperationResult` exactly as received and finish immediately.
