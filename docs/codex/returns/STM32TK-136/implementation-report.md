# v1.3.6 tool evidence repair — implementation and independent acceptance

Software slice: **ACCEPTED_WITH_FIXES**. Release qualification: **COVERAGE_DECISION_PENDING**.
This report does not claim publication, a new physical flash, or final recipient installation.

Accepted base: `37f69ca4acc2b879d4227a099384241ec39080f4`. Reviewed product/package CodeHead: `b00cbc4edee191712dd6da7e1beb073ff4a74f28`.
Report preparation started at `b00cbc4edee191712dd6da7e1beb073ff4a74f28`; this report does not contain its own commit SHA.
Primary owns requirements, architecture, plan, complete-diff review and acceptance.
Local Claude Code CLI implements and verifies through the unchanged configured
`deepseek-v4.1-flash[1m]` route. Branch: `codex/v136-tool-evidence`; no PR.
The user explicitly authorized v1.3.6 builds, master integration and Release publication;
that does not transfer a historical coverage exception or authorize hardware/installation.

## Result and scope

These are tool evidence/presentation/documentation defects, not evidence that the
user's Keil or migrated firmware source is wrong. Option A retains the existing
ARMCC Cortex-M4/FPU2 hard inference with explicit origin, raw decision evidence,
rule, warning and baselineVerified=false. PLAN/APPLY and conversion reports expose
the decision. Firmware identity and build receipts capture its fixed report path/hash;
explicit softfp remains softfp. Invalid optional reports are bounded warnings, and
unchanged incremental outputs retain the previously admitted provenance.

Every new success/failure receipt carries actual toolkitVersion=1.3.6. Optional
fields are strictly validated when present; old records missing them remain readable.
Existing buildId calculation, freshness/authorization/lease/failure-stop contracts
remain. Debug keeps the documented historical `artifacts/migration/build-result.json`;
release uses `artifacts/migration/arm-release/build-result.json`. Both switching
directions work without --clean. Context returns matching buildId/elfSha256.

Backend flash counters remain real backend values or null; 0 is preserved and
verifiedBytes remains independent readback evidence. pyOCD 0.46.0 high-level program
does not supply structured counters; no count is invented. No frequency, retry,
reset, hardware behavior or cross-version identity/generatedBy accommodation was added.
Empty debug/launch design is preserved. Current version authorities are 1.3.6;
CHANGELOG accurately links published v1.3.5 without changing older release claims.

The complete accepted-base-to-CodeHead diff (54 files) was independently
reviewed; SHA-256 `997bb96af71d91f89b64988037861225fdce6ede2469a8bcc10d9f848b40bc76`. No unresolved functional finding remains.
The retained extra blank EOF in the new ABI test file is nonfunctional; diff-check
returned 1 and is not described as PASS. Changed files and exact bindings are in
[integration-evidence.json](integration-evidence.json).

## Verification

The source-bound Python matrix completed all 265 test files:
**9720 distinct passed, 20 skipped, no unresolved failure/error**.
Tests span explicitly recorded commits with final product source and selected
passing test bindings; this is not a single final-head full rerun. All product
bytes match except abi_evidence.py in the two scenario-only runs: its executed
raw LF blob and final CRLF export differ only in newlines, with AST and line
locations identical. Its mismatching raw-byte coverage is excluded; p01 supplies
the final export-byte ABI module evidence. No source is silently normalized.
Later test corrections are the ABI programmable-ELF fixture, independently
executed in p01 (321 passed), and two legacy scenario snapshot test doubles,
executed in q163short (7 passed). Their shared helper imports were independently
reviewed and unchanged; original failed test bytes remain bound to their old head.
Every delegated command has matched native PowerShell evidence, actual test
exit/fresh JUnit and unchanged source. Missing native numeric exits stay null.

[Targeted acceptance](acceptance.md) records actual public CLI commands, full
debug/release build IDs/ELF hashes, inferred/declared ABI JSON and null/value/zero
telemetry cases. The real GNU creation journey also passes after a bounded shorter
temporary-base comparison; CubeMX generation and the backend remain labelled
synthetic. No original project, existing runtime or hardware was changed.

UI reuses explicitly bound unchanged source/tests/configuration/assets/dependencies:
534 pass/1 platform skip, native 2938/3147 branches, per-file90 met. Only package
version metadata changes; no fresh browser/IDE/UI execution is claimed. Quiet
Monitor performance tests and the Windows source-adapter timing comparison use
unchanged assertions/thresholds and no coverage timing overhead.

## Retained original results

- t01 accessor failures; i01 receipt-order/schema failures; i32 three generic-ELF
  positive admission failures remain. Corrections were implemented by Claude and
  verified; p01 completes the final relevant 321-node file group.
- i03/i18 interruption has no terminal exit/JUnit and is never PASS. Their original
  logs remain; only incomplete files were scheduled in bounded resumed attempts.
- Native pending i05/i17/q005/q022/q070/q140 invocation audits remain unaccepted.
  Primary reconciles the same original executions' fresh exit0/JUnit/source evidence;
  completed tests were not rerun. The earlier interruption note called i17's seven
  archive-input skips platform skips; the exact reasons below correct that label.
- q139 retains 15 failed/27 passed from the Windows venv-redirector PID mismatch.
  One direct-base Python3.12.14 comparison passes the same 42 assertions unchanged.
- q023 retains its configuration-stage failure. The same complete journey passes
  once with only a 16-character shorter pytest base. The original deterministic
  staging path is 262 characters; path-limit causation is inferred because the
  original swallowed OSError was not retained, not claimed as directly observed.
- q141 retains 1 failed/26 passed: its one-second intermediate liveness assertion
  saw both processes already gone. One quiet, non-instrumented comparison passes
  all 27 unchanged checks; no assertion, timeout or cleanup contract is weakened.
- q163 retains 6 failed/1 passed from two test doubles requiring a policy argument
  that the existing production default-policy caller legitimately omits. Claude
  corrected only those signatures and kept explicit legacy-policy assertions.
  q163fixed resolves those six but retains a seventh WinError3 overlong temporary
  destination. One short-base q163short completes all 7 tests, unchanged product.
- The matrix-resume-30 smoke invocation remains NOT_ACCEPTED: 23 native calls
  (19 successful reads including smoke, 3 blocked discovery commands, one Git read
  failure), no original test execution. It improperly continued after denials.
  Primary retained logs, verified a clean worktree and did not reissue denied
  discovery. A separately bounded invocation executes only the six original,
  genuinely unexecuted test commands. No policy, provider or tools were widened.
- Earlier edit read-scope violations and malformed-write/unauthorized continuation
  audits remain NOT_ACCEPTED; candidate diffs were retained and independently
  reviewed. CLI/dispatcher0 alone never establishes editing or test passing.
- The first context acceptance script used --project instead of --project-root;
  only one corrected read-only context call followed, with no repeat build. Its
  unrecorded native exit stays unknown. Preliminary export/raw-LF and incomplete
  native-audit assumptions are retained as coordinator errors, not product failures.
- The first final helper audit handled from-imports only and stopped on its count
  assertion; a corrected read-only audit includes module alias attribute use.
  No product file changed. A commit attempt lacking local author metadata failed;
  the existing Codex author was supplied per command, without global/auth changes.
- Final package cleanliness initially found the previous official builds' ignored
  build/egg-info intermediates. Only those eight known directories were moved to
  a run-local archive after containment checks; no tracked source changed. Both
  clean export-byte audits then passed. Two calls to the matrix-only lane helper
  rejected package task names before any dispatch/build; first actual final
  builds use the documented dispatcher entry, with original wrapper errors retained.

## Coverage and package qualification

Complete native Python branch denominators include all 150 source files and the
whole new build/abi_evidence.py risk member selected before measurement. Native
union retains only exact unchanged-source v1.3.5 arcs; old arcs for changed files
and failed/interrupted aggregates are excluded. No membership or floor is lowered.

| Scope | Native branches | Permanent floor | Result | v1.3.5 comparison only |
| --- | --- | --- | --- | --- |
| toolkit-overall | 16414/18836 (87.1416%) | 90% | UNMET | NOT_LOWER |
| toolkit-risk-core-v2 | 15281/17496 (87.3400%) | 90% | UNMET | NOT_LOWER |
| monitor-overall | 3293/3564 (92.3962%) | 90% | PASS | NOT_LOWER |
| monitor-risk-core-v2 | 3293/3564 (92.3962%) | 95% | UNMET | NOT_LOWER |

Prior one-version exceptions do not transfer. NOT_LOWER is a comparison, not
release authorization or permanent-gate PASS. Current release state is
**COVERAGE_DECISION_PENDING**; any exception must identify this frozen source and package.

[Earlier independent builds](candidate-build.md) remain historical and are superseded
by two final builds at `b00cbc4edee191712dd6da7e1beb073ff4a74f28` after the scenario fixture correction. These final
builds produced exactly matching 13 names/lengths/SHA-256, then official
verify-bundle returned exit0/ok. The source
ZIP matches Git archive export bytes under existing line-ending attributes, not
a claim that Windows CRLF equals raw LF blobs. The Windows ZIP is 119432768 bytes,
SHA-256 `61170df3c700e1fceb0fc9e9c3f3845d92f7e6a17bca54614f707630d14bdbc1`.
pyOCD remains 0.46.0, public inventory52/9. No installed runtime was replaced.

## Deferred checks and exact skips

Primary owns later capable-host real symlink/rename checks. The selected historical
archive must be supplied by its owner before Primary runs those reader checks.
The user owns final recipient installation/VS Code/MCP/interactive validation.
Actual vendor generation and a new physical flash have no new PASS; this tool-only
repair does not introduce a physical acceptance requirement or reuse old authority.

- `tools/stm32-toolkit/tests/test_project.py::tests.test_project::test_source_symlink_cannot_escape_canonical_project_root` — symbolic links are unavailable in this test environment
- `tools/stm32-toolkit/tests/test_project_model.py::tests.test_project_model::test_file_symlink_cannot_escape_project_root` — symbolic links are unavailable in this test environment
- `tools/stm32-toolkit/tests/test_project_model.py::tests.test_project_model::test_directory_symlink_parent_cannot_escape_project_root` — symbolic links are unavailable in this test environment
- `tools/stm32-toolkit/tests/test_regeneration.py::tests.test_regeneration::test_destination_symlink_is_rejected_before_resolution` — symlink creation is unavailable
- `tools/stm32-toolkit/tests/test_risk_acceptance_archive_lifecycle.py::tests.test_risk_acceptance_archive_lifecycle::test_archived_acceptance_begin_checkpoint_retry_and_completed_reader` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_risk_acceptance_archive_lifecycle.py::tests.test_risk_acceptance_archive_lifecycle::test_archived_acceptance_refusals_preserve_data_then_complete_and_reject_completed_retry` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_risk_acceptance_archive_readers.py::tests.test_risk_acceptance_archive_readers::test_archived_completed_acceptance_show_and_resume_are_read_only` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_risk_acceptance_archive_readers.py::tests.test_risk_acceptance_archive_readers::test_archived_in_progress_acceptance_show_and_resume_report_current_timeout` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_risk_acceptance_archive_readers.py::tests.test_risk_acceptance_archive_readers::test_archived_acceptance_root_corruption_refuses_without_write_then_restores` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_risk_continuation_archive_reader.py::tests.test_risk_continuation_archive_reader::test_archived_continuation_authenticate_and_prepare_public_context_variants` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_risk_continuation_archive_reader.py::tests.test_risk_continuation_archive_reader::test_archived_continuation_public_root_refusal_restores_authentication_and_reference` — set STM32TK_VS10A_PUBLIC_DATA_ARCHIVE for the selected archived public-data batch
- `tools/stm32-toolkit/tests/test_creation_apply.py::tests.test_creation_apply::test_creation_apply_refuses_linked_cache_entry_before_activation` — directory symlinks are unavailable on this host
- `tools/stm32-toolkit/tests/test_detection.py::tests.test_detection::test_keil_discovery_does_not_follow_directory_symlink` — directory symlink creation is unavailable
- `tools/stm32-toolkit/tests/test_diagnostic_cli.py::tests.test_diagnostic_cli::test_unsafe_steps_symlink_is_generic_error_without_dispatch` — symlink capability unavailable
- `tools/stm32-toolkit/tests/test_diagnostic_store.py::tests.test_diagnostic_store::test_event_redirect_is_rejected_without_root_mutation` — Windows symlink creation unavailable: [WinError 1314] 客户端没有所需的特权。: 'D:\\codex-tmp\\v136-evidence\\q046\\t\\dstore0\\redirect-target.json' -> 'D:\\codex-tmp\\v136-evidence\\q046\\t\\dstore0\\diagnostics\\sessions\\ffffffffffffffffffffffffffffffff\\events\\00000000.json'
- `tools/stm32-toolkit/tests/test_doctor_readiness.py::tests.test_doctor_readiness::test_redirected_explicit_parent_is_invalid` — directory symlink unavailable
- `tools/stm32-toolkit/tests/test_evidence_store.py::tests.test_evidence_store::test_read_artifact_rejects_redirected_object_path` — this host does not permit file symlink creation
- `tools/stm32-toolkit/tests/test_linker_fragment.py::tests.test_linker_fragment::test_read_linker_fragment_rejects_a_real_symlinked_file` — unprivileged Windows file symlinks are unavailable; mocked coverage applies
- `tools/stm32-toolkit/tests/test_monitor_observation.py::tests.test_monitor_observation::test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state` — Windows directory handles deny rename
- `tools/stm32-toolkit/tests/test_vscode_configuration.py::tests.test_vscode_configuration::test_redirect_targets_are_refused` — host cannot create a file symlink for this check

Raw commands, native events, source hashes, JUnit and coverage live under
`D:/codex-tmp/v136-evidence`; their SHA bindings are recorded in the integration JSON.
The final remote identity and publication/download verification must be recorded
only after their authorized actions; neither is fabricated in this report.
