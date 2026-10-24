# PY-OCD-DEBUG-CONFIG implementation report

## Identity and ownership

- Module/phase: PY-OCD-DEBUG-CONFIG, bounded offline source slice.
- Accepted base: `7b25b890f02892626c5ba6201bd3dec2712a95e4`.
- Branch: `codex/pyocd-debug-config`.
- Final pre-report CodeHead: `313743acfa609d6c29ca8bb9cbec3800f3577418` (clean author and independent review worktrees at this exact head; all work local, no remote action).
- Implementer: local Claude Code CLI using the existing configured `deepseek-v4.1-flash[1m]` provider/model configuration. No provider, model, authentication, or permission change; output is not labeled as an Anthropic model.
- Specification, plan, orchestration, independent complete-diff review and verdict owner: primary Codex. This author does not approve its own diff and records no acceptance verdict.
- Governance documents (primary-owned, unchanged by this report): `docs/superpowers/specs/2026-10-25-pyocd-debug-config-design.md` and `docs/superpowers/plans/2026-10-25-pyocd-debug-config-plan.md`.
- Authoritative machine ledger supplied by the coordinator: `D:\codex-tmp\pd25\evidence-draft.json` (read-only evidence; not copied into the repository). Exact long argv, JUnit/log paths, SHA-256 values and counts are taken from it.
- Boundary: offline/synthetic projects only. No original-project access, hardware, probe/backend connection, network, remote/Git mutation, installation, runtime/global Skill change, or release-asset change. Delivery is local only.

## Implemented behavior and boundaries

- The existing configure workflow gained one optional explicit pair: Python `debug_backend`/`debug_target`, CLI `--debug-backend`/`--debug-target`, MCP `debugBackend`/`debugTarget`. No new MCP tool and no migration parameter were added.
- Both options omitted preserve the historical configure route, plan shape, bytes and one-argument internal planning invocation. Any supplied value passes both raw fields to the shared validator unchanged: one value alone, a non-string, an empty/whitespace value or a backend other than exactly `pyocd` fails with `DEBUG_CONFIGURATION_INVALID`, a stable first `field`/`rule`, complete `diagnostics[]` and `missingFields[]`, before any write. Registered MCP parameters remain unconstrained raw values (`Any`), so wrong integers/booleans/lists are refused rather than coerced.
- A valid pair (`pyocd` plus the existing target identifier grammar `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`, no trimming/case-folding/coercion) edits only `debug.backend` and `debug.target` in an existing valid Schema 2/3 `.stm32-project.json`. All other keys and values are preserved, including `svd`, `svdDevice`, `readableRegions`, memory, generation/linkerFragment, identity and testing. The manifest remains user-owned and is never a managed record.
- PLAN is read-only. It reports optional `debug_configuration` and immutable `manifest_edit` evidence: path/status, before/after SHA-256 and sizes, and the complete unified diff (raw bytes remain private). `plan.inputs` records observed **source before** bytes, while `plan.model`/`model_sha256` and generated outputs describe the validated candidate **after** model. A same-value pair keeps exact source bytes (`status=unchanged`, empty diff) rather than reformatting.
- APPLY accepts only the same project and pair, the exact reviewed plan ID and JSON boolean `authorized=true` through the existing authorization boundary. It freshly replans and refuses stale/changed/omitted pairs, input drift, generated-file drift and tampered optional fields before writing. Manifest edit, generated outputs and managed manifest are applied in the existing single guarded staging/backup/replace/rollback transaction; rollback covers both the user-owned manifest and the managed manifest.
- Shared pure diagnostics describe missing/invalid pairs consistently for configure, context and hardware. Remediation text names the real paired entries and complete runnable commands:
  `stm32-toolkit project configure --project <project> --debug-backend pyocd --debug-target <pyocd-target> --dry-run --json` and MCP `stm32_project_configure` with `debugBackend`/`debugTarget`; APPLY adds `--apply --json --plan-id <data.plan_id> --authorized`. No invented `stm32-toolkit configure` or `stm32_configure_project` names remain.
- Configured project context exposes additive `data.debugConfiguration` with `backend`/`target` (null when absent), `status` (`configured`/`needs-user-input`), `missingFields`, `diagnostics` (`code`/`field`/`rule`/`message`/`remediation`), `targetSupport=not-checked`, `hardwareVerified=false` and `nextSteps`. Missing/invalid settings block `capabilityDetails.flash`/`targetTest`/`monitor`/`breakpointDebug` with every diagnostic reason while preserving existing snapshot/Git blockers; build and configure availability are unchanged, and a valid pair never turns hardware booleans true.
- Keil preflight adds non-blocking post-migration `data.debugConfiguration` for the planned `debug: {}` model (`phase=post-migration`, `blocking=false`). It adds no technical blocker, no `planReadiness`/`applyReadiness` prerequisite, no Git dependency and no plan ID; ordinary conversion retains its existing Git/plan/authorization requirements.
- Hardware `_prepare` uses the shared status while preserving `HARDWARE_INPUT_INVALID`, the historical first-field/rule (`debug.backend`/`pyocdRequired`, `debug.target`/`identifierRequired`), `projectKind`, and the separate SVD gate. Probe discovery remains independent of manifest/debug/SVD. No backend discovery, target support claim, device mapping or relaxed admission was introduced.
- A configured pair is metadata only: it does not install, discover or verify a PyOCD target, prove the physical device, create a live debug session or populate `.vscode/launch.json`. A real debug handoff remains separate and explicitly authorized.

## Scope and changed areas

Product:

- `tools/stm32-toolkit/src/stm32_toolkit/debug_configuration.py` (new shared validator/diagnostics)
- `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` (candidate model loading seam)
- `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` (paired planning, source/candidate identity, integrity and transaction integration)
- `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py` (`GenerationPlan` optional pair/`ManifestEdit` serialization)
- `tools/stm32-toolkit/src/stm32_toolkit/generation/__init__.py` (minimal exports)
- `tools/stm32-toolkit/src/stm32_toolkit/workflows.py` (optional pair threading; omitted-pair legacy one-argument call)
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py` (`--debug-backend`/`--debug-target`)
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` (three existing configure wrappers; raw optional arguments)
- `tools/stm32-toolkit/src/stm32_toolkit/context.py` (`data.debugConfiguration`, capability blocking)
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py` (shared diagnostics, preserved hardware gates)
- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py` (non-blocking post-migration description)

Tests:

- `tools/stm32-toolkit/tests/test_debug_configuration.py` (new core tests)
- `tools/stm32-toolkit/tests/test_debug_configuration_workflows.py` (new public workflow/CLI/MCP/context/preflight/hardware tests)
- `tools/stm32-toolkit/tests/test_mcp_migration_build.py` (configure schema expectations)
- `tools/stm32-toolkit/tests/test_workflows.py` (historical conversion test double accepts the existing `extra_regions` keyword)
- `tools/stm32-toolkit/tests/test_context.py` (complete-response debugConfiguration goldens)
- `tools/stm32-toolkit/tests/test_hardware_workflows.py` (complete backend/target diagnostics goldens)

Guidance:

- `docs/user-guide.md`
- `skills/configure-stm32-project/SKILL.md`
- `skills/migrate-keil/SKILL.md`

Governance documents present in the accepted-base-to-CodeHead diff but authored by the primary owner, not this implementation, are the spec and plan named above. No schema, dependency, version, CI/automation, template, launch/task, package or release asset was changed.

## Verification evidence

All Claude-owned checks below were actual registered native `PowerShell` tool events using the exact coordinator-supplied commands; shell inventory initialization and `Get-Location` were verified before execution. Native Claude tool returns do not expose the underlying pytest process exit code, so those exits are recorded as **unreported** rather than inferred from text. The primary's independent runs were executed by the primary's own recorded process; the final review run reported `exitCode: 0`.

### Author core run

At `138dfd17d52802fd989ba6e3ac4fc65ae691cfb6`:

```text
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_debug_configuration.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_regeneration.py -q --tb=short --basetemp=D:/codex-tmp/pd25/p-core -o cache_dir=D:/codex-tmp/pd25/c-core --junitxml=D:/codex-tmp/pd25/core.xml
```

Result: 409 tests, 408 passed, 0 failed, 0 errors, 1 platform skip; JUnit `D:\codex-tmp\pd25\core.xml`, SHA-256 `cd87ddf8c08e1c6e239772222e73944baabdcb9face4e6944967cc7df2f5e419`; process exit unreported. The skip is `tests.test_regeneration::test_destination_symlink_is_rejected_before_resolution` ("symlink creation is unavailable").

### Author public-route run and corrections

Initial public run at `f5148987e4ab03430ab4f353bd90736a21e186b4`:

```text
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_debug_configuration.py tools/stm32-toolkit/tests/test_debug_configuration_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py -q --tb=short --basetemp=D:/codex-tmp/pd25/p-new -o cache_dir=D:/codex-tmp/pd25/c-new --junitxml=D:/codex-tmp/pd25/new.xml
```

Result: 101 tests, 94 passed, 7 failed, 0 errors, 0 skipped; JUnit `D:\codex-tmp\pd25\new.xml`, SHA-256 `541299277ea9f75017a50390a22df44e7ebfe3663f9079c099fdf10bc61b3692`; log retained. All seven were new fixture/expectation errors, not product defects:

- the invalid-pair parameterization wrongly treated `(None, None)` as invalid although it is the preserved historical route;
- the documentation test demanded a literal installed `stm32-toolkit project configure` in the user guide instead of its intentional verified-patched-runtime binding;
- two assertions compared JSON lists against recursively frozen `OperationResult.data` tuples;
- one configured-context test asserted `configured` for the SVD-only fixture;
- context and hardware fixtures used numeric `debug.target`, which the retained broader schema contract rejects before the debug gate.

The author corrected only tests and skill field text; no product behavior or schema validation was loosened. New-test rerun at `f329ac653abc48ee142d88be74fdea6e42eaba26`:

```text
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_debug_configuration.py tools/stm32-toolkit/tests/test_debug_configuration_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py -q --tb=short --basetemp=D:/codex-tmp/pd25/p-new2 -o cache_dir=D:/codex-tmp/pd25/c-new2 --junitxml=D:/codex-tmp/pd25/new2.xml
```

Result: 101 tests, 101 passed, 0 failed, 0 errors, 0 skipped; JUnit `D:\codex-tmp\pd25\new2.xml`, SHA-256 `75863d154179f0a99ba85536a652a7922827b81468b993e0dafbf117a24495c8`; process exit unreported.

### Primary broad regression and baseline

Primary independent broad run at `f5148987e4ab03430ab4f353bd90736a21e186b4`, in `C:\Users\zhy76\.codex\worktrees\build-snapshot-final\STM32-Toolkit`: 1,168 tests, 1,158 passed, 6 failed, 0 errors, 4 platform skips; recorded process `exitCode: 1`; JUnit `D:\codex-tmp\pd25\regress.xml`, SHA-256 `334b413766e1511361ef700fa76f733f0a793b96ef2fa45b8a81def2a5ac2dfc`; log SHA-256 `4094faef544eab1620e0d17d1e3ec902386242d8d37560c6b31c1626198e0415`. The full 16-module argv is recorded in the machine ledger (`results[regress].argv`).

The six failures were classified and corrected:

- four complete-response goldens omitted the approved new diagnostics: `tests.test_context::test_configured_context_reports_evidence_sections_without_build[2]`, `[3]`, `tests.test_hardware_workflows::test_public_workflow_preflight_and_runtime_guard_matrix`, and `tests.test_hardware_workflows::test_non_discovery_workflows_still_require_a_model_and_explain_failures`;
- `tests.test_workflows::test_configure_workflow_translates_stable_generation_errors` exposed the omitted-pair workflow still calling the planning API with new keywords; the product correction now calls the historical one-argument shape when both options are omitted and the raw pair otherwise;
- `tests.test_workflows::test_convert_workflow_translates_stable_inspection_and_plan_errors` had an old test double missing the real API's existing `extra_regions` keyword. This failure is historical, not caused by this slice. Primary reproduced it at accepted base `7b25b890f02892626c5ba6201bd3dec2712a95e4` with the recorded one-test baseline: 1 test, 0 passed, 1 failed, process `exitCode: 1`; JUnit `D:\codex-tmp\pd25\baseline.xml`, SHA-256 `e031de81f639b0a7a8b7e06ef27fc52d4e95ef6e4b169008a29853bbccb82ee1`; log SHA-256 `a4448918369b323755956e9970f5bd96d9d1784dfee1f5ad2193fcc6d539de22`. The correct historical fix was the test double accepting explicit `extra_regions=()` with an empty-request assertion; conversion product code is unchanged.

After `f5148987`, the only product delta was the configure omitted-pair one-argument compatibility call. All other product bytes were unchanged, and all affected workflow/context/hardware/new tests were rerun.

### Final targeted verification at the pre-report CodeHead

Author final run at `313743acfa609d6c29ca8bb9cbec3800f3577418`:

```text
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_debug_configuration.py tools/stm32-toolkit/tests/test_debug_configuration_workflows.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py -q --tb=short --basetemp=D:/codex-tmp/pd25/p-final -o cache_dir=D:/codex-tmp/pd25/c-final --junitxml=D:/codex-tmp/pd25/final.xml
```

Result: 344 tests, 344 passed, 0 failed, 0 errors, 0 skipped; JUnit `D:\codex-tmp\pd25\final.xml`, SHA-256 `341f9d1563369a3ef110e473b9f192867306c0604f98c4ca9ff3b29d29998971`; process exit unreported by the native tool.

Primary independent final review at the same head, in the clean review tree:

```text
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_debug_configuration.py tools/stm32-toolkit/tests/test_debug_configuration_workflows.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py -q --tb=short --basetemp=D:\codex-tmp\pd25\p-final-review -o cache_dir=D:\codex-tmp\pd25\c-final-review --junitxml=D:\codex-tmp\pd25\final-review.xml
```

Result: 344 tests, 344 passed, 0 failed, 0 errors, 0 skipped; recorded process `exitCode: 0`; JUnit `D:\codex-tmp\pd25\final-review.xml`, SHA-256 `8691576aa254e381d02a303d0d6f83626516029f98151599d0f87140c077e8b5`; log SHA-256 `3458a763f4915f1b389c86172f616d6f105ba807467f310b411ab309ffea1062`.

Class distribution at the final head: `test_debug_configuration.py` 51, `test_debug_configuration_workflows.py` 31, `test_workflows.py` 79, `test_context.py` 48, `test_hardware_workflows.py` 116, `test_mcp_migration_build.py` 19.

### Skill validation

Native PowerShell `quick_validate` (skill-creator) was run against `skills/configure-stm32-project` and `skills/migrate-keil`; each returned the actual text `Skill is valid!`. Underlying process exit codes were not exposed by the native tool and are unreported; no separate native exit is invented.

### Aggregate and reuse basis

- 82 new and 1,164 historical unique passing cases = 1,246 unique passing cases in the recorded evidence.
- The final 344-case targeted suite was rerun by both owners at the pre-report CodeHead.
- The remaining 902 passing historical cases are reused from the broad run after reviewing affected paths, justified by the narrow product delta described above. This is **not** a final-head full-repository matrix and not release qualification.

### Reviewed corrections and coverage exercised

- Corrected wrong CLI/MCP entry names and missing `--dry-run --json`/APPLY flags in public remediation, and exercised the actual emitted remediation string through the real CLI as a read-only PLAN.
- Corrected inaccurate user-guide wording about Git, conforming the guide to the real verified-patched-runtime invocation rather than inventing an installed command.
- Verified same-value pair preserves exact manifest bytes; PLAN records source-before and candidate-after identity without pretending candidate bytes exist on disk.
- Verified single-transaction success and injected rollback after both managed-manifest and generated-target replacements, plus chmod failure rollback with mode/bookkeeping restoration.
- Verified stale/omitted/changed pair, tampered optional fields, changed diff/digest and generated drift refuse without writes; duplicate-key, oversize, non-regular and redirecting manifests fail closed.
- Verified complete field diagnostics, no coercion in registered MCP raw values, context absence vs configured metadata-only behavior, snapshot/Git blocker retention, non-blocking preflight guidance, hardware missing-both/malformed/SVD-separate gates, and independent fake-backend probe discovery.
- Valid pair remains metadata only; no SVD selection, target guessing/discovery, firmware admission change or hardware verification was added.

### Platform deferrals

Four real-symlink cases are deferred to **primary-owned release qualification** on capable Windows/Linux:

- `tests.test_project_model::test_file_symlink_cannot_escape_project_root`
- `tests.test_project_model::test_directory_symlink_parent_cannot_escape_project_root`
- `tests.test_regeneration::test_destination_symlink_is_rejected_before_resolution`
- `tests.test_linker_fragment::test_read_linker_fragment_rejects_a_real_symlinked_file`

Reasons recorded: symbolic links unavailable in this environment (mocked reparse coverage applies). Mocked reparse/symlink coverage and all pure-code checks passed; no pure-code failure was deferred.

A third-party `pydantic_settings` lifespan forward-reference warning remains nonfatal and is retained.

## Execution anomalies (orchestration, not test results)

- The initial broad file-only call requested an unregistered `Bash` grep against a repository test fixture. The tool was absent/disabled and rejected it (`No such tool available: Bash`); no shell command ran and no product edit occurred then. The primary stopped that exact Claude process, preserved logs/edits, and resumed smaller file-only tasks without widening permissions.
- A later integration editing call hit the 65-turn bound; it was resumed retaining prior edits.
- All actual verification used registered native `PowerShell` with the exact coordinator-supplied command; shell inventory smoke and `Get-Location` were confirmed first. A successful CLI exit or text-only tool claim was never counted as a test result.
- No permission bypass, alternate shell, alternate provider, authentication change, or global setting change was used.

## Limitations and boundaries

- Source-only patch: the frozen/installed 1.3.0 (and published 1.2.0) runtime lacks it. Installation, upgrade, packaging and runtime/global Skill changes were not performed and are separate authorization layers.
- The pair is syntax/metadata only. It does not prove PyOCD target installation/support, match the physical device, create a live debug session, or populate `.vscode/launch.json`; real debug handoff is separate and explicitly authorized.
- A manifest edit naturally invalidates earlier build/firmware identity; users must rebuild (with `clean` where required) and never hand-repair hashes or receipts.
- The 344-case final suite is targeted, not a full-head repository or release matrix; 902 historical passing cases are reused as described. Four real-symlink checks remain platform-deferred to primary release qualification.
- No original-project access, hardware operation, network/remote action, PR mutation, tag, package, installation, credential exposure or authentication change occurred.

Implementation/evidence submitted for primary review, not self-accepted.
