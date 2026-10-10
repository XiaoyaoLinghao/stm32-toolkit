# STM32TK-101 D implementation return

## Identity and scope

- Accepted base: `24826f1723aac3c6f4e7a1dd9961e14aab1c5153`.
- D code head before this report: `94a17b53c2f85cdcf08afde403d48d29ef141b61` on `codex/v1.0.1-d-release`.
- Worktree: `D:\codex-tmp\tk101\d`. No remote action, publication, host/user package installation, user runtime mutation, or physical-device run was performed.
- The diff from base to code head is 41 paths, 410 insertions and 1275 deletions. Four approved non-release follow-on Skill drafts account for 1025 deleted lines. `schemas/stm32-release.schema.json` changes only the `productVersion` constant from 1.0.0 to 1.0.1; schema structure and compatibility rules do not change. The root is the only tracked copy of that release schema.

## Resulting candidate behavior

The plugin, Toolkit and Monitor distributions, exact Monitor-to-Toolkit dependency, UI package root, launcher paths, release policy/schema, and generated producer identity agree on 1.0.1. The two launchers continue to explain a missing managed runtime. The setup helper recognizes an existing 1.0.0 runtime as legacy and permits only its controlled, authorized Repair transaction; the 0.9.0/0.5.0/0.3.0 paths remain. Multiple legacy directories, unexplained future directories, source conflicts, downgrades, locked promotion, and rollback guards remain in force. Check's GUI evidence uses command location and static CubeMX file-version metadata; neither CubeMX nor Code is executed, and VS Code extensions are `not-probed` rather than asserted missing.

Existing project `generatedBy` values remain their real 1.0.0/0.9.0 identity. Those projects can still plan and apply; managed drift remains a blocker. New generated manifests and build identities carry 1.0.1. Old flash receipts and evidence are not rewritten or promoted into current observation authorization. README, changelog, user guide, Windows preflight, and the setup/build Skills describe candidate behavior and point to the release-status/execution records for review and qualification. The released v1.0.0 assets remain unchanged. Four obsolete follow-on Skill drafts were deleted while the eight current Skills and 48 MCP entry points remain.

The release builder's product `pip wheel` subprocess now passes `--no-cache-dir`; its deliberately narrow child environment still excludes the caller's `PIP_CACHE_DIR`. The offline backend install step remains otherwise unchanged. The builder and policy trusted Git-blob SHA-256 anchors in setup are respectively `01e80ca978ecf5b4414f1b3bf00c9b67403b82407a44a0d959b8582c20bd4bdb` and `980b6f34baca0d025768eba349612f85b8053763cbeb2e267433697afc639bf4`.

## Slice evidence

All Python commands used `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe` (CPython 3.12.10), repository root as cwd, `PYTHONPATH` set to the D Toolkit and Monitor `src` directories, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and `TEMP`, `TMP`, `TMPDIR`, and each `--basetemp` under `D:\codex-tmp\tk101\d-run`. The pinned wheelhouse at `D:\codex-tmp\v10b-0918\r10\wheelhouse` was read-only. The setup tests created only their own offline fixture runtimes under the run root.

| Check (each `pytest -q`, unless stated otherwise) | Collected / passed | Exit | Log and attribution |
| --- | ---: | ---: | --- |
| Toolkit `test_plugin_layout.py`, `test_generation.py`, `release/test_0900_artifacts.py`, `test_public_inventory.py`, `test_cli.py` | 418 / 418 | 0 | `D:\codex-tmp\tk101\d-run\core.log`; source bytes before the later single release troubleshooting case, subsequently covered by the final release group. |
| Monitor `test_package_boundary.py`, `test_cli.py`, `test_service.py`, `test_exports.py`, `test_runtime.py` | 184 / 184 | 0 | `D:\codex-tmp\tk101\d-run\monitor.log`. |
| Toolkit `test_setup_runtime.py` | 40 / 40 | 0 | `D:\codex-tmp\tk101\d-run\setup.log`; 1.0.0 Repair fixture, GUI zero-execution marker, legacy/multiple/rollback behavior. |
| Toolkit `test_doctor.py`, `test_build_runner.py`, `test_mcp_migration_build.py`, `test_migration_plan.py`, `test_0900_security.py`; Monitor `test_models.py` | 336 / 336 | 0 | `D:\codex-tmp\tk101\d-run\current.log`; current-version output contracts. |
| README/layout and setup guidance assertions (`test_readme_links_current_user_guidance_and_release_boundaries`, `test_setup_contract_uses_namespaced_skill_and_ignores_coverage_data`) after the documentation follow-up | 2 / 2 | 0 | `D:\codex-tmp\tk101\d-run\docs.log`. |
| Release artifact test module at final D code head, including `git archive` trusted-anchor and product wheel cache boundary | 45 / 45 | 0 | `D:\codex-tmp\tk101\d-run\release-nocache-head.log`, run after commit `94a17b53...`. |
| Focused `-k build_wheel` fixture during cache fix | 3 / 3 | 0 | `D:\codex-tmp\tk101\d-run\nocache.log`; final full release group supersedes it. |

The pytest dot counts above contain no skip or xfail markers; collection output is retained in `collect-setup.log`, `collect-current.log`, `collect-monitor.log`, `collect-release.log`, and `collect-docs.log`. The core group was run before one added release test, so its own 418 PASS dots are the count for that run; the final release module collected and passed all 45 cases.

For the UI, `npm run typecheck`, `npm run build`, and `npm run verify:dist` each exited 0. Their logs are `ui-typecheck.log`, `ui-build.log`, and `ui-dist.log`; `verify:dist` reported seven byte-identical files. Existing dependencies were copied as a regular directory from the C worktree to D's ignored `tools/stm32-monitor/ui/node_modules`; no install or shared cache write occurred. `git diff --check` exited 0. `git ls-files --eol` showed LF index/worktree bytes for builder and policy. A read-only `git show HEAD:<path>` SHA-256 check of both actual committed blobs matched setup's trusted values; the command is in `D:\codex-tmp\tk101\d-run\verify_blob.py`.

An early smoke run (`smoke.log`) exited 1 with 20 passing and one failing README layout assertion that still required the old “in development” phrase. This was a test-expectation/report mismatch after candidate wording changed, not a product failure. The assertion was updated within D ownership; the affected layout suite and later documentation assertions passed. It is not counted as a passing run.

## Remaining boundary and artifacts

There is no known unresolved D product blocker. Independent acceptance, final artifact qualification, native Windows installation, upgrade and rollback breadth, and physical hardware evidence belong to the integration/release owner. The v1.0.0 release-status record explicitly limits rollback evidence to the tested recoverable transaction branch; documentation makes no universal state-write rollback claim.

Per primary-owner instruction, `D:\codex-tmp\tk101\d-run` remains intact for integration evidence and later attributable cleanup. It contains the listed logs, `collect-*.log`, approved-root pytest basetemps (`pytest-core`, `pytest-current`, `pytest-monitor`, `pytest-setup`, `pytest-release-*`, `pytest-docs`, `pytest-nocache`, `pytest-smoke` where present), `temp`, `npm-cache`, and small run-local helper scripts. D's copied, ignored `tools/stm32-monitor/ui/node_modules` also remains for the primary cleanup owner. The tracked D worktree is clean before the report is added.
