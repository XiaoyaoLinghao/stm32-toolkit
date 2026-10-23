# Keil readiness independent review

Verdict: **ACCEPTED_WITH_FIXES** for this local software slice. All required offline gates passed; there are no outstanding blocking findings. This verdict does not qualify a release or an installed VS Code/hardware runtime.

## Ownership and immutable identities

- Accepted base: `89f76ee5551dfdc313f3f37d2d9e760af47daac8`.
- Specification, bounded plan, orchestration, independent complete-diff review and acceptance: primary conversation agent.
- Product implementation, test writing and corrections: local Claude Code CLI 2.1.308 using the user's unchanged `deepseek-v4.1-flash[1m]` configuration. No Codex-hosted implementation subagents were used.
- Initial implementation CodeHead: `7e63af70018e228fb3171346e6259cd784e4c14d`.
- Final CodeHead: `500b328c349c38888d1943d3beca98047ba08419`.
- Final implementer report head: `a60d7a9072efe65e9ee8d00499ab81bac1cf6993`.
- Branch: `codex/keil-readiness`. Authorized scope: local source, tests, guidance and agent configuration. No remote mutation, installation, deployment, version/release change or physical operation.

## Complete-diff review

Reviewed all 32 changed/added files from accepted base to report head in the clean isolated `keil-readiness-review` worktree. The 31 pre-report files were reconciled against the previously inspected implementation content; only Git checkout newline normalization differed. The final correction changed only `migration/preflight.py` and its test file; the later report commit changed documentation only. Full diffs are retained in `D:/codex-tmp/kx23/review-codehead-initial.diff` and `review-codehead-final.diff`. `git diff --check` passed and the reviewed worktree was clean.

The shared planner extraction preserves Git/HEAD ordering, deterministic plan identity, input-drift/containment/size rules and guarded apply. Preflight reports complete technical analysis separately from plan prerequisites and keeps apply readiness false with no usable plan ID. Repository, HEAD and status OS failures now become bounded Git evidence without masking technical failures or cancellation.

Probe discovery validates project/data/session roots independently of a project model. A valid model retains workspace identity; unavailable or malformed models produce explicit unbound discovery. Enumeration retains list/close, timeout and cancellation behavior and creates no lease, attachment, target selection or project files. Other hardware entry points retain model, target, SVD, identity and authorization checks. Structured errors expose actionable fields and safe causes; non-string identity pins fail before backend access.

MCP descriptions and skills were checked against actual response shapes: target selection via `details.targets`, inspection's `data.inspection.target_name`, PLAN `data.plan_id` to APPLY `planId`, and context `data.build.buildId`/`elfSha256` to flash pins. Discovery-only guidance precedes build prerequisites. Published 48-tool v1.2.0 and current 49-tool source are explicitly distinguished. The global and project AGENTS policies record actual CLI inventory discovery, verified PowerShell selection and the existing provider preference.

## Independent execution evidence

Dedicated external venv: `D:/codex-tmp/kx23/venv`; CPython 3.12; explicit review-worktree PYTHONPATH; TEMP/TMP/TMPDIR=`D:/codex-tmp/kx23/tmp-review`; all probes injected/fake. No actual board access.

| Owner / exact source | Check | Result |
| --- | --- | --- |
| Primary / accepted base | Original context, migration plan, hardware workflow and inventory baseline | 253 passed, exit 0; `baseline.log` |
| Primary / accepted base | Isolated existing CMake discovery fixture | Failed as reported, exit 1; `baseline-mcp.log`. Ambient CubeCLT took priority over a PATH-only fake. |
| Claude CLI / initial implementation bytes | 16-module combined affected suite | 801 passed, 2 warnings, exit 0; `final-suite.log`. Reused only for unchanged surrounding bytes after the correction. |
| Claude CLI / final CodeHead bytes | Preflight + MCP migration/build, including OS-error correction | 39 passed, 1 warning, exit 0; `claude-revision3.jsonl`, basetemp `bt-impl-18`. |
| Primary / clean initial CodeHead | Hardware workflows, MCP hardware/roots, context, inventory, skill layout and two guarded apply cases | 316 passed, 1 warning, exit 0; `review-integration.log`. These files and exercised surrounding behavior are unchanged at final CodeHead. |
| Primary / clean final CodeHead | Full preflight and MCP migration/build suites | 39 passed, 1 warning, exit 0; `review-final.log`. |

Exact primary commands, run from the repository root using the venv interpreter:

```text
python -m pytest tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_migration_apply.py::test_apply_no_writes_on_any_preflight_failure tools/stm32-toolkit/tests/test_migration_apply.py::test_apply_existing_identical_manifest_is_not_rewritten --basetemp=D:/codex-tmp/kx23/bt-review-1 -o cache_dir=D:/codex-tmp/kx23/cache-review-1
python -m pytest tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_mcp_migration_build.py --basetemp=D:/codex-tmp/kx23/bt-review-2 -o cache_dir=D:/codex-tmp/kx23/cache-review-2
```

Matching `.exit.txt` files record 0 for each primary passing run. Warnings are the existing Pydantic lifespan forward-reference warning and, in the implementer's combined suite, a runpy import-order warning. No failures were skipped or relabeled. The CMake fixture correction only pins the test's fake executable through a supported profile; production discovery priority and fail-closed assertions are unchanged.

## Findings resolved and retained boundaries

Review corrections covered nested Git-root output shape, separation of plan and apply readiness, accurate target/plan/pin guidance, non-string pin validation, public unbound discovery tests, and OS-level Git failures. The final OS-error regression covers repository/HEAD/status, preserved blockers, no exception-text leak, unchanged files, retained stale-input failure and propagated KeyboardInterrupt. Corrections were implemented by the CLI and independently reviewed and verified by the primary.

The initial Bash tool selection was unavailable on this Windows CLI; those unexecuted tests were never counted. Initialization metadata and a harmless allowed PowerShell command established the corrected invocation contract. Global `C:/Users/zhy76/.codex/AGENTS.md` and repository `AGENTS.md` contain the preventative rule. Raw CLI logs remain outside the repository.

No native Keil build backend, non-Git build identity, charset conversion, startup generation, external firmware import, RAM placement redesign or real extension readiness is claimed. No package, installed runtime, GitHub Release, VS Code UI, physical probe/flash or full release qualification was changed or validated. The existing v1.2.0 runtime does not gain this source slice automatically.
