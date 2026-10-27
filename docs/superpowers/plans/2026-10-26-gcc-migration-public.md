Accepted M1 base: 277cb556ad1302079463da2e07989bbfa14e8c7b. Branch: codex/gcc-migration-public. Core managed-firmware identity slice A integrates separately; this slice must not reimplement it.

# M2 public independent migration and AI guidance

Implement after M1 acceptance on its exact accepted head; the coordinator will fill head/branch at dispatch. Primary owns this design and acceptance; local Claude Code CLI owns implementation/tests. No original-project edits, hardware, installation, release/version or remote actions. M3 WFI/source preparation follows separately.

## Public behavior

keil convert CLI gains --destination <absolute-new-output>; stm32_keil_convert gains destination. Omission yields DELIVERY_DESTINATION_REQUIRED with a concrete example and rationale that the source is read-only and the deliverable is an independent GCC project. No silent legacy in-place fallback. The workflow validates the source, target/startup/layout/extraRegions as today, then calls plan_keil_delivery; apply requires authorized=true and the exact freshly recomputed planId with the identical destination/options. Return M1's complete plan preview and outputRoot/result without claiming a build/flash. Preserve existing authorization checks and structured diagnostics. Legacy low-level decoder remains available internally for old evidence, not public default behavior.

Use the delivery engine's public camelCase planId/output schema consistently across CLI, MCP descriptions, guidance and tests. Point to actual fields: data.planId, data.sourceSnapshotSha256, data.outputs (kind/path/beforeSha256/sha256/unifiedDiff/collision), data.sourcePatches and exact result outputRoot. No aliases whose meaning differs, no planId/contentId confusion. CLI --json remains safe UTF-8 JSON in a default Windows environment.

Preflight stays read-only. Git evidence may remain as optional information but can never cause an unmet plan prerequisite or an instruction to init/commit/stash/clean Git. Technical blockers alone determine technical readiness; new independent output directory is a required next input, with destination state explicitly not yet evaluated by preflight. A completed preflight never authorizes apply. Preserve complete blockers, remediation categories, source/dependency encoding hints, source/startup/layout/ABI evidence and debug configuration diagnostics. Update context's migrate-keil reasons/blockedBy and recommended steps accordingly. No live probe enumeration in context/preflight.

After apply, give exact next actions: open/bind outputRoot as the VS Code workspace/MCP project root; run context there; configure explicit debug backend/target and verified Toolkit/GCC paths there if missing; configure plan/apply then normal GCC build -> authorized managed flash. Git is optional for both new and migrated projects. External firmware import remains for externally supplied images, never the no-Git workaround. Do not mutate server project-root binding behind the user's back, fabricate paths or select a probe automatically. Reuse current configure endpoint for debug/editor configuration instead of duplicating its options in convert.

## Guidance and scope

Allowed public implementation: workflows.py, cli.py, mcp_server.py, migration/preflight.py, context.py and directly relevant tests. M1 delivery only for a necessary public integration correction backed by a regression. No new task automation or runtime registration mechanism.

Update skills/migrate-keil, build-firmware, configure-stm32-project, flash-firmware and debug-firmware plus docs/user-guide.md and docs/architecture.md to this actual implemented contract. Remove Git-only statements from current AI instructions/skills; historical release reports remain historical. Keep README.md and README_zh-CN.md short and aligned: two product paths, installation/use entry points and real current release status. Detailed engineering evidence belongs in the report, not README. Do not claim a new published version. Document same-input options for preflight/plan/apply and rebinding the output root explicitly.

## Evidence

Claude tests direct workflow + CLI subprocess + registered MCP parameter/call paths on disposable no-Git sources. Exercise missing destination, new destination plan/apply, source hashes unchanged, output configured/buildable, not falsely built/flashed, option/destination drift, nonempty destination, authorization denial, complete blocker classification and missing debug/editor guidance. Verify no repository or committed-HEAD prerequisite for no-Git, unborn, dirty and nested Git roots. Verify old public calls cannot edit the original tree. Preserve M1 real GCC relocation evidence and rerun only affected integration checks. Primary full clean-head review and representative CLI/MCP acceptance follow; real hardware/user IDE are not claimed.
