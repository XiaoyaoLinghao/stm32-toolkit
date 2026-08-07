---
name: migrate-keil
description: Use when a Claude Code user asks to inspect a Keil uVision project or migrate ARMCC sources to ARM GNU GCC with a guarded, explicitly authorized conversion.
---

# Migrate Keil Project

## Workflow

1. **Context first.** Call `stm32_project_context` (no arguments). If `capabilities.keilInspect` or `capabilities.keilConvert` is `false`, report the context evidence and stop.
2. **Inspect.** Call `stm32_keil_inspect(uvprojx?, targetName?, includeBaseline=true)`. Show the selected target, device, warnings, and baseline availability from the returned `inspection` and `baseline`.
3. **Read-only plan.** Call `stm32_keil_convert(uvprojx?, targetName?)` with no `planId` and no `authorized` — this returns the deterministic `keil-conversion-plan`. Show the plan's `plan_id`, every blocker with its portable path, and the exact changed paths and diffs from `patches`.
4. **Stop on blockers.** If `blockers` is non-empty, report them and stop; never apply a blocked plan.
5. **Authorize.** Ask the user for explicit authorization for the exact displayed `plan_id`. Never infer consent from the earlier read-only calls.
6. **Apply.** Only after the user authorizes, call `stm32_keil_convert(planId="<exact plan_id>", authorized=true)`. The core replans and rechecks all digest, Git, and drift guards before its first write.
7. **Return the result.** Report the `keil-conversion-apply` result: the conversion report path, the Schema v2 `.stm32-project.json` path, patched source paths, and any warnings. If the result is a failure (`AUTHORIZATION_REQUIRED`, `PLAN_CHANGED`, `MIGRATION_*`), report the exact code and details and stop.

## Rules

- `stm32_keil_inspect` and the plan call are read-only; verify the plan before any mutation.
- The apply call is the only mutation. Pass exactly the plan ID shown to the user.
- Do not parse `.uvprojx` XML, rewrite source files, render templates, or run compilers yourself.
- Never claim success; report the returned `OperationResult` exactly as received and finish immediately.
