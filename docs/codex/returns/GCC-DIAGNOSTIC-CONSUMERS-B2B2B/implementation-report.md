# Snapshot identity in diagnostics, continuation and MCP — accepted with fixes

Date: 2026-10-27. Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline software slice. This does not qualify a release, hardware operation or the unfinished cross-branch GCC delivery integration.

## Ownership and source ledger

- Accepted base: `59464807250cdb0cf58c7d7d19f8a9ba47cdde44` (B2b2A).
- CodeHead before this report: `798a5f5a32f54fb2ac6993c3c163c82704d35957`.
- Specification: `docs/superpowers/specs/2026-10-26-gcc-delivery-contract.md`; second bounded edit in `docs/superpowers/plans/2026-10-26-gcc-monitor-consumers.md`.
- Branch: `codex/gcc-monitor-consumers`. No PR or remote action authorized/performed.
- Primary Codex owns specification, dispatch, complete-diff review and acceptance. Local Claude Code CLI 2.1.308 with the user's unchanged `deepseek-v4.1-flash[1m]` route authored product code and tests. Primary authored this report and planning addendum.
- Implementation checkout: `C:/Users/zhy76/.codex/worktrees/v133-review/STM32-Toolkit`; independent clean exact-head checkout: `C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit`.
- Primary reviewed the entire accepted-base-to-CodeHead nine-file diff, including retained partial edits and both new regression files. Final `git diff --check` passed; both checkouts were clean at the code freeze. The final correction changes only two test fixtures; product bytes match `dc2b87457fb9a1a437089f68f9f321d64084859d`.
- Only disposable offline fixtures were used. Original firmware projects, installed Toolkit runtimes and hardware were not changed/accessed. No version, release, credential, provider or permission change occurred.

## Delivered behavior

Diagnostic replay and physical-shaped transcript/reference consumers and continuation Monitor comparisons now retain and compare the complete `source_baseline` / bounded `git_evidence` pair. Two records with equal hashes and null Git fields cannot substitute different recorded Git-unavailable evidence. Existing build, target, session, probe, lease, lineage, evidence-parent and authority checks remain.

MCP's Monitor reference model accepts the valid content-snapshot form with nullable Git fields, and preserves the exact legacy wire key set. Its serializer omits only pair members that were never supplied; explicit nulls remain visible to the shared validator. Required nullable `svd_sha256` remains on the wire. Raw input, existing models, copied/mutated instances and nested models are checked through the shared reference validator before effects. No parallel relaxed validator was introduced.

The two new regression files cover 24 cases: 20 actual registered MCP schema/roundtrip/refusal cases and four persisted diagnostic/continuation/verification workflows. They cover legacy compatibility, snapshot readback through fresh stores, physical-shaped synthetic data, replay origin/import identity, and self-consistent republished provenance substitutions with no-effect assertions. Synthetic physical-shaped fixtures are software evidence, never a claim of real hardware validation.

Three existing test fixtures carry optional snapshot provenance while preserving their legacy defaults. Two stale recovery tests now create real disposable projects through the existing fixture rather than incomplete model stubs; original stage/continuation assertions remain, with real nonzero input-snapshot assertions added.

## Review findings and retained failures

1. R1 from report commit `996e7b7904dfe9978ceb29dd2db5bf7ed3260aa5` is resolved. Explicit null in a copied legacy model previously disappeared on serialization. The corrected serializer retains fields-set intent and an after-validator checks the canonical alias dump, including existing-instance validation.
2. The first correction at `9c0ac4733ca36f0880c26208170e72ada475e274` forced Pydantic instance revalidation, which expanded internal/default fields before the wire validator. Author `dgm` and independent primary `dgn` each recorded 120 passes and four legitimate instance-roundtrip failures. Claude corrected this at `6fa9fdc4f2bc3112ddd7525031b580ee996e30db`; final raw/instance/nested cases pass. Original failures remain retained.
3. `dg2` found two recovery-test failures at `dc2b87457fb9a1a437089f68f9f321d64084859d`. Primary `dg3` reproduced exactly the same failures on accepted base `59464807250cdb0cf58c7d7d19f8a9ba47cdde44`: `_current_identity` could not enumerate the incomplete `SimpleNamespace` model. This was stale fixture setup, not a new MCP product regression. Claude corrected only those test setups at `798a5f5a32f54fb2ac6993c3c163c82704d35957`; full-file author and independent runs each pass all 35 tests. Product snapshot enumeration was not weakened or mocked.

## Execution evidence

Run root: `D:/codex-tmp/gcc26`. Every row has `execution.json`, fresh `junit.xml`, stdout and source hashes. Commands use the verified `D:/codex-tmp/kx23/venv/Scripts/python.exe -X utf8 D:/codex-tmp/gcc26/run_checks.py ROOT HEAD LABEL GROUP`. ROOT is the implementation checkout for Claude rows and the clean review checkout for primary rows; HEAD and labels are recorded below and exactly in each execution record. The runner isolates temporary data and checks source state before/after. All passing rows have subprocess exit 0 and `sourceUnchanged=true`.

| Label / owner | Source | Group | Result |
| --- | --- | --- | --- |
| dgr / Claude; dgs / primary | dc2b87457fb9a1a437089f68f9f321d64084859d | diagnostic-content-new | 24 passed each |
| dgt / Claude | dc2b87457fb9a1a437089f68f9f321d64084859d | diagnostic-content-mcp | 124 passed |
| dgu / Claude | same dc2b8745 source | diagnostic-content-core | 106 passed |
| dgv / Claude | same dc2b8745 source | diagnostic-content-risk | 6 passed |
| dgw / Claude-started process, completion reconciled by primary | same dc2b8745 source | diagnostic-content-continuation | 72 passed; see abnormal CLI audit below |
| dg1 / Claude | same dc2b8745 source | diagnostic-content-adapters-core | 11 passed, 2 archived-data checks skipped |
| dgy / Claude | same dc2b8745 source | monitor-analysis-new | 16 passed |
| dgz / Claude | same dc2b8745 source | monitor-analysis-risk | 15 passed |
| dg4 / Claude; dg6 / primary | 798a5f5a32f54fb2ac6993c3c163c82704d35957 | diagnostic-content-recovery | 35 passed each |
| dg5 / Claude | 798a5f5a32f54fb2ac6993c3c163c82704d35957 | diagnostic-content-new | 24 passed |

Distinct selected regression cases, deduplicated by JUnit classname/name: **389 passed, 2 skipped, 0 failed** in the applicable evidence set (`diagnostic-final-evidence-summary.json`). Repeated author/primary runs are not added to this count. Most affected regressions ran on dc2b8745; the final change affects only the two recovery fixtures, and that entire file plus new tests were rerun on the final CodeHead. This is explicit unchanged-byte evidence reuse, not a claim of a final-head full repository rerun. Monitor source/tests are unchanged from the accepted B2b2A slice; its larger analysis/source-catalog evidence remains attributed to its original report, not counted again here. One existing Pydantic settings forward-reference warning remains.

The two skipped checks are `test_archived_continuation_authenticate_and_prepare_public_context_variants` and `test_archived_continuation_public_root_refusal_restores_authentication_and_reference`. They require the external pinned VS10-A public-data archive via `STM32TK_VS10A_PUBLIC_DATA_ARCHIVE`; it is not configured or tracked here. They are not passed tests. Current legacy/snapshot authority and refusal regressions above passed with reproducible disposable fixtures. Qualification against that historical archive remains unverified and belongs to the primary coordinator at final GCC integration when the pinned fixture is available; this slice acceptance does not waive a release/integration requirement or transfer an old release exception.

## Claude invocation evidence and guidance

The global launcher remains `C:/Users/zhy76/.codex/tools/claude-dispatch/dispatch.py`. Each new launch checked actual native init inventory; verify also executed its real PowerShell smoke. Editing, command execution, test success and coordinator acceptance were kept separate. No absent numeric tool exit was fabricated; native numeric status remains null when omitted, while subprocess exit 0 above is from the bound runner record.

The initial Bash attempts in `diagnostic-core-20261027` and `diagnostic-mcp-r1` occurred despite correctly registered file tools and were unexecuted. They were completion/no-op shell attempts, so read/search one-shot recovery did not apply. Conflicting blanket smoke instructions, contradictory test-edit task text and stale global Toolkit guidance were corrected through Claude in a separate reviewed tooling slice. Fresh calls receive bounded appended guidance without replacing the default system prompt, model or permissions. Normal assistant text completes a task; shell smoke belongs only to verify startup.

Later `diagnostic-regression-b` exceeded the native 600000 ms foreground window. The authorized dgw process was started; native structured background metadata was not terminal execution. Tool output suggested an unavailable reader and the model attempted absent `DeferredToolPlaceholder`; the CLI invocation remains rejected. The already-started test process subsequently finished with 72 passes after 779.5 seconds. Primary reconciled only its existing bound execution/JUnit evidence, without rerun, recovery, worker polling, permission expansion or interference with other processes. The other commands were genuinely unexecuted and were later dispatched in smaller groups.

The installed dispatcher now records valid native background metadata as started/pending, never completed/passed. Worker guidance says report PENDING and finish; the primary may reconcile existing bound evidence. Actual canary worker behavior followed this rule, but a subsequent duplicate CLI init event still triggers the strict stop guard: full background-session reliability is not claimed. Ordinary subsequent editor/verify runs have clean native evidence. Tooling CodeHead `dd482a3afaa97383402f863fa2d6c9b615555437`, independent 132 passes/1 symlink-capability skip, complete diff review and hash-guarded global deployment are documented in `D:/codex-tmp/cli27/evidence/background-acceptance.md` and `background-installed-files.json`.

Retained scope-audit failures in `diagnostic-mcp-r2` (undeclared parent Glob) and `diagnostic-backend-r2` (three undeclared local dependency files) remain rejected as CLI invocations; their allowed edits were fully reviewed independently. Global task guidance now requires local model/schema/helper dependencies to be declared up front, without retroactively accepting violations. `diagnostic-mcp-fix`, `diagnostic-recovery-fixture`, `diagnostic-new-verify`, `diagnostic-regression-a`, `diagnostic-remaining-a` and `diagnostic-final-verify` have clean native audits. `diagnostic-remaining-b` correctly reported real failed tests, later corrected as described above. No fallback Codex implementation, provider switch or permissive retry was used.

## Remaining product work

This slice closes the diagnostic/continuation/MCP snapshot-consumer work and the explicit-null finding. The independent prepared-source guidance/fixture slice and cross-branch integration of Keil-to-GCC and new-GCC development journeys remain separate work. Final archive qualification, broader integration, user-facing installation/IDE validation and any release or hardware actions are not implied by this acceptance. No new release was published.
