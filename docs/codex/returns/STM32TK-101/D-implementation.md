# STM32TK-101 D implementation return

## Identity and scope

- Accepted base: `24826f1723aac3c6f4e7a1dd9961e14aab1c5153`.
- D code head before this revised report: `c75adb430fa1f03cc0dc5a4a9e7f519838978664` on `codex/v1.0.1-d-release`.
- Worktree: `D:\codex-tmp\tk101\d`. No remote action, publication, host/user package installation, user runtime mutation, or physical-device run was performed.
- The diff from base to this code head is 42 paths, 464 insertions and 1277 deletions including the previous version of this report; excluding that report, the implementation delta is 41 paths, 422 insertions and 1277 deletions. Four approved non-release follow-on Skill drafts account for 1025 deleted lines. `schemas/stm32-release.schema.json` changes only the `productVersion` constant from 1.0.0 to 1.0.1; schema structure and compatibility rules do not change. The root is the only tracked copy of that release schema.

## Resulting candidate behavior

The plugin, Toolkit and Monitor distributions, exact Monitor-to-Toolkit dependency, UI package root, launcher paths, release policy/schema, and generated producer identity agree on 1.0.1. The two launchers continue to explain a missing managed runtime. The setup helper recognizes an existing 1.0.0 runtime as legacy and permits only its controlled, authorized Repair transaction; the 0.9.0/0.5.0/0.3.0 paths remain. Multiple legacy directories, unexplained future directories, source conflicts, downgrades, locked promotion, and rollback guards remain in force. Check's GUI evidence uses command location and static CubeMX file-version metadata; neither CubeMX nor Code is executed, and VS Code extensions are `not-probed` rather than asserted missing.

Existing project `generatedBy` values remain their real 1.0.0/0.9.0 identity. Those projects can still plan and apply; managed drift remains a blocker. New generated manifests and build identities carry 1.0.1. Old flash receipts and evidence are not rewritten or promoted into current observation authorization. README, changelog, user guide, Windows preflight, and the setup/build Skills describe candidate behavior and point to the release-status/execution records for review and qualification. The released v1.0.0 assets remain unchanged. Four obsolete follow-on Skill drafts were deleted while the eight current Skills and 48 MCP entry points remain.

The release builder's product `pip wheel` subprocess now passes `--no-cache-dir`; its deliberately narrow child environment still excludes the caller's `PIP_CACHE_DIR`. The offline backend install step remains otherwise unchanged. The builder and policy trusted Git-blob SHA-256 anchors in setup are respectively `641f58a01c1dad4b17d4a4d4df720e82544faf2a2ee8480bcf6f997155bc155b` and `980b6f34baca0d025768eba349612f85b8053763cbeb2e267433697afc639bf4`.

The active `_spdx` generator now uses one declared document ID for the SPDX document and each `DESCRIBES` source. The existing SBOM fixture checks that every relationship endpoint resolves to a declared document or package ID, that IDs are unique, and that each `DESCRIBES` source is the document. The pre-fix fixture failed on the actual mixed-case dangling ID; no schema or public API was changed.

## Slice evidence

All Python commands used `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe` (CPython 3.12.10), repository root as cwd, `PYTHONPATH` set to the D Toolkit and Monitor `src` directories, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and `TEMP`, `TMP`, `TMPDIR`, and each `--basetemp` under `D:\codex-tmp\tk101\d-run`. The pinned wheelhouse at `D:\codex-tmp\v10b-0918\r10\wheelhouse` was read-only. The setup tests created only their own offline fixture runtimes under the run root.

| Check (each `pytest -q`, unless stated otherwise) | Collected / passed | Exit | Log and attribution |
| --- | ---: | ---: | --- |
| Toolkit `test_plugin_layout.py`, `test_generation.py`, `release/test_0900_artifacts.py`, `test_public_inventory.py`, `test_cli.py` | 418 / 418 | 0 | `D:\codex-tmp\tk101\d-run\core.log`; source bytes before the later single release troubleshooting case, subsequently covered by the final release group. |
| Monitor `test_package_boundary.py`, `test_cli.py`, `test_service.py`, `test_exports.py`, `test_runtime.py` | 184 / 184 | 0 | `D:\codex-tmp\tk101\d-run\monitor.log`. |
| Toolkit `test_setup_runtime.py` | 40 / 40 | 0 | `D:\codex-tmp\tk101\d-run\setup.log`; 1.0.0 Repair fixture, GUI zero-execution marker, legacy/multiple/rollback behavior. |
| Toolkit `test_doctor.py`, `test_build_runner.py`, `test_mcp_migration_build.py`, `test_migration_plan.py`, `test_0900_security.py`; Monitor `test_models.py` | 336 / 336 | 0 | `D:\codex-tmp\tk101\d-run\current.log`; current-version output contracts. |
| README/layout and setup guidance assertions (`test_readme_links_current_user_guidance_and_release_boundaries`, `test_setup_contract_uses_namespaced_skill_and_ignores_coverage_data`) after the documentation follow-up | 2 / 2 | 0 | `D:\codex-tmp\tk101\d-run\docs.log`. |
| Release artifact test module at pre-SBOM code head, including `git archive` trusted-anchor and product wheel cache boundary | 45 / 45 | 0 | `D:\codex-tmp\tk101\d-run\release-nocache-head.log`, run after commit `94a17b53...`; this did not detect the subsequently identified SBOM reference defect. |
| SBOM reference-closure fixture before the builder fix | 1 / 0 | 1 | `D:\codex-tmp\tk101\d-run\sbom-red.log`; expected red test exposed `SPDXRef-Document` outside the declared ID set, not a passing qualification run. |
| The same SBOM fixture after the builder fix | 1 / 1 | 0 | `D:\codex-tmp\tk101\d-run\sbom-green.log`. |
| Entire release artifact module at new code head, including actual `git archive` trusted anchor and SBOM closure | 45 / 45 | 0 | `D:\codex-tmp\tk101\d-run\release-sbom-head.log`, run after commit `c75adb43...`. |
| Focused `-k build_wheel` fixture during cache fix | 3 / 3 | 0 | `D:\codex-tmp\tk101\d-run\nocache.log`; final full release group supersedes it. |

The passing groups above contain no skip or xfail markers; the pre-fix SBOM red case is recorded separately as a failure, not a PASS. Collection output is retained in `collect-setup.log`, `collect-current.log`, `collect-monitor.log`, `collect-release.log`, and `collect-docs.log`. The core group was run before one added release test, so its own 418 PASS dots are the count for that run; the final release module collected and passed all 45 cases after the SBOM fix.

For the UI, `npm run typecheck`, `npm run build`, and `npm run verify:dist` each exited 0. Their logs are `ui-typecheck.log`, `ui-build.log`, and `ui-dist.log`; `verify:dist` reported seven byte-identical files. Existing dependencies were copied as a regular directory from the C worktree to D's ignored `tools/stm32-monitor/ui/node_modules`; no install or shared cache write occurred. `git diff --check` exited 0. `git ls-files --eol` showed LF index/worktree bytes for builder and policy. A read-only `git show HEAD:<path>` SHA-256 check of both actual committed blobs matched setup's trusted values; the command is in `D:\codex-tmp\tk101\d-run\verify_blob.py`.

An early smoke run (`smoke.log`) exited 1 with 20 passing and one failing README layout assertion that still required the old “in development” phrase. This was a test-expectation/report mismatch after candidate wording changed, not a product failure. The assertion was updated within D ownership; the affected layout suite and later documentation assertions passed. It is not counted as a passing run.

## Remaining boundary and artifacts

There is no known unresolved D code blocker. The earlier built artifact pair was invalid as a fully qualified release candidate because its SBOM had dangling `DESCRIBES` references despite reproducible builds and `verify-bundle` success. The new code head requires independently rebuilt artifacts and renewed SBOM closure review; independent acceptance, final artifact qualification, native Windows installation, upgrade and rollback breadth, and physical hardware evidence belong to the integration/release owner. The v1.0.0 release-status record explicitly limits rollback evidence to the tested recoverable transaction branch; documentation makes no universal state-write rollback claim.

The primary owner cleaned the earlier pytest basetemps, temporary directories, npm cache, and D's copied, ignored UI `node_modules` after preserving logs. `D:\codex-tmp\tk101\d-run` retains the listed logs, `collect-*.log`, small run-local helper scripts, and three new SBOM-run basetemps: `D:\codex-tmp\tk101\d-run\pytest-sbom-red`, `D:\codex-tmp\tk101\d-run\pytest-sbom-green`, and `D:\codex-tmp\tk101\d-run\pytest-release-sbom-head`. I prepared a PowerShell removal limited to those verified absolute paths under the approved run root with a reparse-point guard, but automatic approval review rejected the recursive command before execution. None of the three directories was touched; I did not retry or bypass the rejection. The primary owner remains the sole cleanup owner for any later disposition. No unrelated tracked changes were made.
