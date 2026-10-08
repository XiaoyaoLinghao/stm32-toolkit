# STM32TK 1.0 local release: regeneration public contract qualification

## Scope

This bounded, test-only slice qualifies four public regeneration transaction boundaries against frozen product source revision `15b1a70e9bd684285da5557104deff529f537e49`:

1. IOC state drift after prepare returns `REGENERATION_STATE_CHANGED`, consumes the authorization, and does not call the CubeMX adapter.
2. A structurally valid candidate whose existing IOC `Mcu.Name` changes to `STM32F407VGTx` returns `REGENERATION_PREVIEW_FAILED` during public prepare before authorization publication.
3. A public configuration failure returns `REGENERATION_CONFIGURATION_FAILED`, skips both builds, and preserves the destination tree.
4. A public forward activation replacement failure returns `REGENERATION_ACTIVATION_FAILED`, executes the real rollback, and restores the original destination tree.

The tests use the existing `_project`, `_Adapter`, `_validator`, native-f429 fixture, and public prepare/apply entry points. They assert exact public codes, adapter/configure/build call boundaries, authorization consumption or non-publication, byte-identical destination state, and cleanup of generation, activation, and backup roots. No product source, CubeMX installation, hardware, build, package, deployment, or remote state was changed.

The accepted base is `ce687819617fec1cfb8ab7a25628056e0abfac7d`. The implementation code head before this report commit is `ab3e3fef43af7146a743319e477e7a4d352384e5` (`test: qualify regeneration public contracts`). This report intentionally records no report-commit SHA.

## Verification

The first invocation is retained at `D:\codex-tmp\v10b-0918\r10\e\regeneration-public-contracts\r1`. It stopped at the first new node before the scenario body because the internal CreationAuthorizationStore consume path was 261 characters under the initial basetemp and the product returned `REGENERATION_AUTHORIZATION_INVALID`. The native inner exception was not captured in that run. The retained authorization probe at `D:\codex-tmp\v10b-0918\r10\e\authorization-probe` captured the same prepare-success/consume-write boundary at a 278-character path with `FileNotFoundError`/errno 2. The first invocation is classified as environment/path-boundary infrastructure evidence; its 1 failure is not a behavior result.

The corrected run used the shorter, preflight-verified basetemp `D:\codex-tmp\v10b-0918\r10\t\rg\b`. The computed internal consume replacement path was 251 characters for all four node prefixes, within the known Windows path bound. The pinned interpreter and frozen Toolkit imports were:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe
D:\codex-tmp\v10b-0918\r10\verify\tools\stm32-toolkit\src
```

The exact argv is retained at `D:\codex-tmp\v10b-0918\r10\e\regeneration-public-contracts\r2\command.txt`:

```text
D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe -m pytest -q -x -o addopts= -o cache_dir=D:\codex-tmp\v10b-0918\r10\t\rg\r2\pytest-cache --basetemp D:\codex-tmp\v10b-0918\r10\t\rg\b --junitxml D:\codex-tmp\v10b-0918\r10\e\regeneration-public-contracts\r2\junit.xml --cov=stm32_toolkit --cov-branch --cov-fail-under=0 --cov-report=term-missing --cov-report=json:D:\codex-tmp\v10b-0918\r10\e\regeneration-public-contracts\r2\coverage.json tools/stm32-toolkit/tests/test_regeneration_workflows.py::test_apply_rejects_ioc_drift_after_prepare_without_cube_mx_call tools/stm32-toolkit/tests/test_regeneration_workflows.py::test_prepare_rejects_candidate_target_drift_before_authorization tools/stm32-toolkit/tests/test_regeneration_workflows.py::test_apply_configuration_failure_preserves_destination tools/stm32-toolkit/tests/test_regeneration_workflows.py::test_apply_activation_failure_restores_old_tree
```

Actual result: `4 passed in 16.12s`, pytest exit code `0`; JUnit reports 4 tests, 0 failures, 0 errors, and 0 skips. Toolkit-only branch coverage was enabled. The focused run measured 13,564 branches with 483 covered and 3.56% branch coverage; `--cov-fail-under=0` was used because the release threshold is an aggregate gate, not a focused four-node threshold. The raw coverage database is `D:\codex-tmp\v10b-0918\r10\e\regeneration-public-contracts\r2\coverage\.coverage`; JSON coverage, JUnit, stdout, stderr, command, environment, exit, and child tempfile evidence are retained beside it.

`TEMP`, `TMP`, and `TMPDIR` were bound to `D:\codex-tmp\v10b-0918\r10\t\rg\r2\tmpdir`. The effective `tempfile.gettempdir()` matched that path, and the child containment check exited 0 with its file under `D:\codex-tmp\v10b-0918\r10\t\rg\r2\childtempcheck`. All run-scoped temporary roots remain under `D:\codex-tmp\v10b-0918\r10\t\rg`; no cleanup was performed by the implementation agent.

This report records implementation evidence only. Independent review of the complete accepted-base-to-code-head diff and release acceptance remain with the primary agent or another reviewer; the implementation agent does not accept its own changes.
