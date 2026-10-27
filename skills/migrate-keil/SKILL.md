---
name: migrate-keil
description: Use when a Claude Code user asks to inspect a Keil uVision project, check migration readiness, prepare a complete reviewed source copy, or deliver it as a separate, independently buildable ARM GNU GCC/CMake project with a read-only plan and an explicitly authorized apply.
---

# Migrate Keil Project

Migrate a Keil uVision project into a separate, independently buildable GCC/CMake project. The Keil
source is read-only. Encoding preparation produces a complete separate prepared tree; migration
then publishes a distinct complete output directory. Git is optional traceability.

Conditional detail lives in [source-preparation.md](references/source-preparation.md) (complete
tree, explicit charsets, strict/lossy review, root rebinding) and [migration-options.md](references/migration-options.md) (exact startup, memory,
external-RAM, WFI and common-syntax options and diagnostics).

## Workflow

1. **Context and binding.** Call `stm32_project_context` (no arguments) and read `capabilityDetails`, not only legacy booleans: `available` means the entry applies,
   `blocked` names a missing prerequisite, `not-evaluated` means context did not check it, and `hardwareDiscovery=not-performed` means no probe was queried.
   Context never scans all sources and does not establish migration readiness. Keep `data.project.root` authoritative and verify the client's actual tools/schemas
   before relying on a newer field. Missing tools/fields or a different root: preserve the full result and stop.
2. **Select and inspect.** Identify the project-root-relative `.uvprojx` from `data.project.files` (context does not list target names); ask the user to choose
   among candidates. If the exact target is unknown, call `stm32_keil_inspect(uvprojx="<path>")` and omit `targetName`; on
   `KEIL_TARGET_SELECTION_REQUIRED`, present `details.targets`, let the user choose, then inspect again with that exact `targetName`. Preserve
   `data.inspection.target_name` and the same `uvprojx` for every later call. Never guess a target; an optional historical AXF/MAP baseline is evidence only.
3. **Preflight without Git.** Call `stm32_keil_preflight` with the same `uvprojx` and `targetName`. It is read-only and requires no Git. Read typed
   `analysis.blockers` separately from `planReadiness` (technical readiness for a plan) and `applyReadiness` (always false pending a reviewed,
   authorized plan). `data.git` may truthfully report a missing repository, unborn HEAD, non-toplevel root or dirty worktree, but never as a prerequisite.
   Never run `git init`, commit, stash, clean or ignore files. `planReadiness.requiredInputs` names the absolute new output directory outside the source,
   absent or verified empty. Success means analysis completed; it does **not** mean the project is ready to apply and never returns an applicable plan ID.
   Each blocker carries complete `remediation` (`category` `needs-user-input`/`unsupported`, `summary`, optional real `tool` or `skill`, `requiredInputs`);
   report all of it. Any technical blocker fails the PLAN with `DELIVERY_BLOCKED` and complete details/codes.
4. **Prepare source when required.** Non-UTF-8 sources or needed quoted headers are `needs-user-input`. Reuse the `normalize-source-comments` helper
   with one explicit charset per selected file, then build a complete separate prepared tree with all unselected sources, headers, startup files,
   resources and licenses, overlaying only reviewed hash-matched converted copies. The helper output is a partial file set, never the project; follow
   [source-preparation.md](references/source-preparation.md).
5. **Choose options.** Pass only accepted inputs, identical for preflight, PLAN and APPLY: `startupStrategy`/`startupSource`, `memoryLayout`,
   `extraRegions`, and `wfiReturns` MCP objects or repeatable CLI `--wfi-return PATH:FUNCTION`. A plain file-scope zero-argument ARMCC
   `__asm void name(void)`/`name()` whose body is one WFI with no explicit return can become ordinary non-naked C executing
   `__asm volatile ("wfi" ::: "memory");` and returning normally only when exactly selected; that is requested source behaviour, not binary
   equivalence, and needs no Keil disassembly/AXF baseline. Explicit `BX LR`/`BX R14` wrappers keep their naked translation; unknown assembly stays a
   project-owned source port. See [migration-options.md](references/migration-options.md).
6. **Resolve blockers, not rules.** Report encoding, assembly, scoped option, scatter/memory and manifest conflicts with portable paths and remediation.
   `needs-user-input` means a real supported selection or reviewed preparation exists; `unsupported` needs a project-owned change. Toolkit
   never silently transcodes non-UTF-8 input, blindly replaces ARMCC startup code, edits a conflicting manifest, deletes untracked files or weakens a rule.
   Never edit digests or evidence to clear a blocker.
7. **Choose a destination and plan.** The Keil source is read-only. Ask the owner for one absolute path outside it, absent or verified empty; never invent
   a path, reuse the source or fall back to an in-place conversion. Omitting it returns `DELIVERY_DESTINATION_REQUIRED` with an example. With
   `planReadiness.ready=true` and no blockers, call `stm32_keil_convert(destination="<abs new>", uvprojx="<same>", targetName="<same>",
   ...same options...)` with no `planId` and no `authorized`. Review `data.planId`, `data.sourceSnapshotSha256`, `data.destinationState`,
   `data.options`, `data.outputs[]` (`kind`/`path`/`beforeSha256`/`sha256`/`unifiedDiff`/`collision`) and `data.sourcePatches[]`;
   `configured=false`, `built=false` and `flashed=false` mean neither build nor flash evidence.
8. **Authorize.** An explicit instruction covering this mutation and scope remains reusable after you review the actual plan while every change stays
   inside it; the user need not have quoted the not-yet-existing plan ID. Re-review a changed plan, destination, input, option or scope. Never infer
   mutation authority from inspection, preflight or a plan-only request. The PLAN response field is `data.planId`; the APPLY request argument is `planId`.
9. **Apply.** Call `stm32_keil_convert` with the same destination, project, target and options, `planId="<exact data.planId>"` and `authorized=true`.
   The core replans, verifies the source snapshot, destination state, options and exact plan ID, stages in an owned sibling and publishes one complete
   output directory. A changed destination/option/source snapshot returns `PLAN_CHANGED` or `DELIVERY_*` and writes nothing; a nonempty destination is
   never overwritten.
10. **Return and rebind.** Report `data.outputRoot`, `data.contentId`, `data.reportPath`, the delivered `.stm32-project.json`, changed/generated paths
    and warnings; confirm `configured=true`, `built=false`, `flashed=false`. Bind `data.outputRoot` as the VS Code workspace and MCP project root,
    rerun context there, configure explicit debug/paths when missing, then use the normal authorized GCC build and managed flash route. Never mutate the
    server binding behind the user's back, fabricate paths or select a probe automatically.

## Post-migration configure

After apply, use the ordinary two-step configure route. For a PyOCD pair, PLAN with
`stm32_project_configure(debugBackend="pyocd", debugTarget="<pyocd-target>")` or CLI `stm32-toolkit project configure --project <abs>
--debug-backend pyocd --debug-target <pyocd-target> --dry-run --json`; review `data.debug_configuration`, `data.manifest_edit`,
`data.diagnostics` and `data.inputs[]`, preserving `svd`, `readableRegions`, `memory`, `generation` and other fields. `targetSupport` stays
`not-checked` and `hardwareVerified` false. Then APPLY with the same pair, `planId=<data.plan_id>` and `authorized=true`, or CLI `--apply --json
--plan-id <data.plan_id> --authorized`. A pair is metadata only; a user-owned writable `NOLOAD` fragment is a separate reviewed configure input
(see `configure-stm32-project`). Always rebuild after a manifest edit.

## Boundaries

- Destination delivery is current local unpublished source behavior, not part of the published v1.3.2 package: an installed v1.3.2/v1.3.1 runtime
  still exposes the historical in-place `keil convert` without `--destination`. Verify the bound server's actual input schema before promising
  `destination`, `data.planId`, `data.outputs[]`, `data.sourcePatches[]` or `outputRoot`; never install or upgrade without separate authorization.
- Capability availability does not establish migration readiness; only current preflight/PLAN evidence does. Read complete diagnostics; unknown codes
  stay unsupported and no blocker is auto-fixable.
- `stm32_keil_inspect`, `stm32_keil_preflight` and the plan call are read-only. APPLY is the only migration write and writes only into the explicit new
  destination; the Keil source is never edited. The `normalize-source-comments` helper writes reviewed copies outside the project; it is not a migration
  apply.
- Current-branch limitation: content-based managed hardware admission is not integrated here yet, so a delivered project without Git-shaped provenance can
  build, but its managed flash, debug handoff, Monitor and Target tests stay blocked until integration. Do not route the final product definition through
  the external firmware import workaround.
- Successful syntax conversion is not behavioral equivalence; offline compiler/ELF checks are not hardware qualification. Do not parse `.uvprojx` XML,
  rewrite project sources, render templates or run compilers yourself. Never claim success; report the returned `OperationResult` exactly as received.
