# PY-OCD-DEBUG-CONFIG independent review

2026-10-25 verdict: **ACCEPTED_WITH_FIXES**, limited to the requested offline source slice.

Accepted base `7b25b890f02892626c5ba6201bd3dec2712a95e4`; final CodeHead `313743acfa609d6c29ca8bb9cbec3800f3577418`; author branch `codex/pyocd-debug-config`. Primary Codex owns specification, orchestration, complete-diff review and acceptance. Local Claude Code CLI using the retained `deepseek-v4.1-flash[1m]` configuration authored all product code, tests and product guidance. No ownership override or remote action was used. Primary planning/review still consumes Codex conversation usage.

Governing [design](../../../superpowers/specs/2026-10-25-pyocd-debug-config-design.md) and [plan](../../../superpowers/plans/2026-10-25-pyocd-debug-config-plan.md). Review covered the complete accepted-base-to-CodeHead diff and each correction in the clean `build-snapshot-final/STM32-Toolkit` tree. Retained binary diff SHA256: `23e4275f358eaa3b63b4bf3ee1f21d67560292de0bb8184dc9133a0153079dde`, at `D:/codex-tmp/pd25/reviewed.diff`. [Machine evidence](evidence.json) records exact commands, source identities, counts and hashes.

## Accepted behavior

Existing `project configure` accepts paired `--debug-backend`/`--debug-target`; existing MCP `stm32_project_configure` accepts `debugBackend`/`debugTarget`. Both omitted retain historical configure behavior and plan shape/hash. Backend is exactly `pyocd`; target uses the existing bounded hardware identifier grammar, without trimming, coercion, case folding, device mapping or catalog access. Registered MCP parameters preserve raw JSON values for structured validation. No new MCP tool or migration option was introduced.

For a valid Schema2/3 manifest, PLAN derives an in-memory candidate changing only `debug.backend` and `debug.target`. It exposes `debug_configuration` and `manifest_edit`, including complete diff, before/after SHA256 and sizes. Exact source bytes remain in plan.inputs; the candidate model and managed manifest describe the after state. An already-equal pair preserves the original manifest bytes. SVD, readableRegions, memory, linkerFragment and other fields remain intact; the user manifest never becomes a managed generated record.

APPLY binds the same request/project to the reviewed plan ID and existing authorization gate. Candidate/hash/diff/request forgery, changed inputs, generated drift and redirected manifest files are refused. Source manifest, generated files and managed manifest share one guarded staging/backup/replace/rollback transaction. Replacement bookkeeping occurs before fallible chmod, allowing complete restoration after that failure. Old build/firmware identities become stale naturally; the supported route is reconfiguration and clean rebuilding when required, never manual receipt/hash repair.

Context and Git-free Keil preflight expose `debugConfiguration`: backend/target, status, missingFields, full diagnostics, targetSupport=`not-checked`, hardwareVerified=false and nextSteps. Preflight's missing pair is explicitly nonblocking post-migration guidance. Ordinary migration still emits `debug: {}` and remains usable for building; conversion PLAN/APPLY retain existing Git and authorization requirements. Context appends debug reasons without losing snapshot/Git provenance restrictions or changing imported-route selection. A valid pair never enables hardware capability booleans. Probe discovery remains independent.

Hardware preflight retains `HARDWARE_INPUT_INVALID` and its existing first field/rule, adding all debug diagnostics and actionable configuration guidance. Earlier model/schema errors remain earlier errors; the SVD gate is separate. No firmware identity, admission, probe, lease, target or authorization boundary was relaxed. User guide and configure/migrate skills show complete real CLI/MCP calls; an actual emitted remediation command is exercised through the CLI parser and read-only workflow.

## Corrections and retained failures

| Area | Finding and correction | Evidence |
| --- | --- | --- |
| Shared remediation / guide | Draft invented CLI/MCP names and omitted required mode/JSON flags. Corrected to real `project configure` / `stm32_project_configure`, with `--dry-run --json` and complete APPLY. Clarified that Git-free debug preflight does not remove conversion Git requirements. | Emitted-command CLI test, registered MCP round trip/raw types, guide checks and complete diff review. |
| Configure compatibility | Always forwarding new None kwargs broke historical one-argument planner doubles. Omitted pair now calls the original one-argument planning shape; supplied values retain strict validation. | Original stable-generation-error test unchanged and passing; final new/no-option tests. |
| New public tests | Initial101 cases had7 failures: contradictory None/None expectation, executable-name assumption in guide, frozen-vs-JSON containers, missing-pair fixture mislabeled configured, and numeric targets stopped by schema before debug diagnostics. | Failure XML retained; corrected fixtures/assertions, added explicit earlier-schema rejection coverage;101 then344 passed. Product validation was not weakened. |
| Historical responses | Four broad-run failures were exact context/hardware dictionaries lacking the newly specified fields/message. Full new expectations were added while retaining prior fields and no-backend-call checks. | Final whole context and hardware test files pass. |
| Prior conversion fixture | A plan-error double lacked the already-existing `extra_regions` keyword. It also failed at accepted base, independently reproduced. The double now accepts the explicit empty option and preserves error assertions; conversion product code is unchanged. | `baseline.xml` records the old failure; final whole workflow file passes. |

No pure-code failure remains deferred. Raw failed runs and invocation logs remain under `D:/codex-tmp/pd25`.

## Verification and scope

Windows CPython3.12.14; same-worktree Toolkit/Monitor source with installed1.3.0 packages used only as read-only dependencies. Synthetic projects and all temporary/cache/log output were confined to the run directory. No original `mobile-robot-controller` project was read or modified.

| Owner / head | Result |
| --- | --- |
| Claude / `138dfd17d52802fd989ba6e3ac4fc65ae691cfb6` | Core/generation/regeneration:408 pass,1 platform skip. |
| Claude / `f5148987e4ab03430ab4f353bd90736a21e186b4` | Initial new/public:94 pass,7 fail, retained. |
| Claude / `f329ac653abc48ee142d88be74fdea6e42eaba26` | Corrected new/public:101 pass. |
| Primary / clean `f5148987e4ab03430ab4f353bd90736a21e186b4` | Broad related regression:1158 pass,6 fail,4 platform skips; actual process exit1. |
| Primary / clean accepted base | Historical conversion-double failure reproduced; actual exit1. |
| Claude / final CodeHead |344 pass,0 fail,0 skip, across both new files and complete workflows/context/hardware/MCP migration-build files. |
| Primary / clean final CodeHead | Same344 cases independently pass, actual process exit0. |
| Claude / final CodeHead | Both modified skills: actual native `Skill is valid!` outputs. |

There are **1246 unique passing cases:82 new and1164 historical**. Final344 were rerun by both owners;902 unaffected historical passing cases are reused explicitly from the broad run. After that broad-run head, the only product delta is the omitted-pair configure call compatibility branch. All other product files and the reused test files are unchanged; all affected workflow/context/hardware tests and both new files were rerun. This is not a final-head full repository or release qualification matrix. Native PowerShell events establish author execution and JUnit establishes counts; the native outputs did not report pytest process exits, so the ledger records them as unreported rather than inferring them from Claude CLI exits. The earlier native author's textual101-run summary incorrectly counted73; machine XML is authoritative. The existing third-party pydantic_settings lifespan warning is nonfatal.

Four real-symlink cases remain **PLATFORM DEFERRED to primary-owned release qualification on capable Windows/Linux**: model file escape, model directory-parent escape, regeneration destination redirect and linker-fragment file redirect. Deterministic mocked reparse coverage passed. No physical target/IDE session, compiler qualification, firmware equivalence, package installation or release qualification was performed or implied.

## Delegation and delivery boundaries

Claude2.1.308 native PowerShell registration was checked by no-action init metadata and an actual Get-Location call. Process-only tool-registration/execution-policy flags preserved existing permissions. File editing and exact single-command native verification were separate invocations with empty MCP configuration. The initial broad file-only call requested an absent Bash tool; it was rejected without execution, the coordinator stopped that process and retained logs, and a smaller file-only task continued without permission expansion. A later integration call reached its65-turn bound and resumed with edits retained. No Codex-hosted implementation subagent was used.

This accepts the local source change only. Frozen/installed1.3.0 does not include it; restarting VS Code does not install it. There was no original-project mutation, hardware access, runtime/global-skill change, packaging, push, PR, merge, tag or remote deletion. No additional hardware or publication authority is granted. Source fixtures and raw failure/verification material remain available for reproducibility.
