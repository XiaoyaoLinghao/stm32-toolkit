# KEIL-READINESS implementation report

## Identity and disposition

- Repository: `C:/Users/zhy76/.codex/worktrees/keil-ux/STM32-Toolkit`
- Branch: `codex/keil-readiness`
- Accepted base: `89f76ee5551dfdc313f3f37d2d9e760af47daac8`
- Task starting head (approved policy/specification only): `68a1e0e1d849a425cb34a5df78657bc5a10ce618`
- CodeHead before this report commit: `7e63af70018e228fb3171346e6259cd784e4c14d`
- Reviewer: primary conversation agent (independent). This report is not acceptance and does not self-approve the diff.
- Authority used: local implementation, focused offline tests and local commits only. No push, PR, merge, tag, release, version bump, packaging, installation, deployment, provider change, physical probe or hardware operation was performed.

## Implemented scope

1. Added read-only `stm32_keil_preflight` (MCP) and `keil preflight` (CLI) with the same project-relative `uvprojx` and exact `targetName` selection as inspect/convert.
2. Factored one shared technical analysis out of the conversion planner. Preflight and plan now derive the same blockers, inputs, fixed sections and manifest conflict rules; the planner's Git-bound behavior and plan ID payload are preserved.
3. Preflight does not require Git, returns exact input hashes and typed blockers, and separates:
   - `analysis.complete` (technical analysis completed, blockers may remain),
   - `planReadiness` (`ready-for-plan` or `blocked`, with technical/Git prerequisites),
   - `applyReadiness` (always `ready=false`, `status=requires-reviewed-plan`, `planId=null`).
   It never produces an applicable plan ID, writes no files, and does not run `git init`.
4. Preflight now enforces the same 64 MiB serialized output bound as a conversion plan.
5. Context keeps the legacy capability booleans and adds `capabilityDetails` with `available`, `blocked` or `not-evaluated`, reasons and next steps. Hardware booleans are documented as not evaluated rather than unavailable. Context does not scan all sources or enumerate probes.
6. Hardware admission keeps legacy `HARDWARE_INPUT_INVALID` where practical and adds bounded safe `field`, `rule`, `projectKind`, `sourceCode`, `sourceField`/`sourceRule`, `expectedSchema` and `guidance` details for session, roots, model load/schema, backend, target, SVD, probe and firmware pins. Non-string pins fail closed without a backend.
7. `probe_list` / `stm32_probe_list` is decoupled from a mandatory model/backend/target/SVD. Bound root, external data root, session and MCP client roots remain validated. A valid configured project preserves `workspaceId`; absent/malformed models return `workspaceId: null` plus `discovery.status=unbound` and a safe `modelError`. No manifest, workspace, lease, attach or project/data-root write is introduced by discovery.
8. Public MCP descriptions, six skills, architecture/user guide/README inventory text and the standard test procedure's current ownership sentence were updated. MCP-only guidance now covers exact project/target selection (`omit targetName`; `KEIL_TARGET_SELECTION_REQUIRED` + `details.targets`; preserve `data.inspection.target_name`), PLAN `data.plan_id` versus APPLY `planId`, `data.build.buildId`/`elfSha256` versus `expectedBuildId`/`expectedElfSha256`, discovery-only branching, and the OBSERVE attach side effect on variable reads/samples.
9. README distinguishes the 49-tool current source inventory from the frozen 48-tool published v1.2.0 runtime without changing version or packaging files.

Existing convert plan/apply authorization, digest, Git, drift and manifest safeguards; flash identity/authorization; path containment; and worker cancellation/cleanup were not relaxed.

## Changed files (implementation commit)

Modified:

- `README.md`
- `README_zh-CN.md`
- `docs/architecture.md`
- `docs/testing/standard-test-procedure.md`
- `docs/user-guide.md`
- `skills/build-firmware/SKILL.md`
- `skills/configure-stm32-project/SKILL.md`
- `skills/debug-firmware/SKILL.md`
- `skills/flash-firmware/SKILL.md`
- `skills/migrate-keil/SKILL.md`
- `skills/read-var/SKILL.md`
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/src/stm32_toolkit/context.py`
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/__init__.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`
- `tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py`
- `tools/stm32-toolkit/src/stm32_toolkit/workflows.py`
- `tools/stm32-toolkit/tests/test_context.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`
- `tools/stm32-toolkit/tests/test_mcp_migration_build.py`
- `tools/stm32-toolkit/tests/test_planned_actions.py`
- `tools/stm32-toolkit/tests/test_plugin_layout.py`
- `tools/stm32-toolkit/tests/test_public_inventory.py`

Added:

- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py`
- `tools/stm32-toolkit/tests/test_keil_preflight.py`

No Monitor/UI, version, packaging policy/schema, installer, or hardware files changed.

## Test evidence

All test processes were offline and used the dedicated venv (`D:/codex-tmp/kx23/venv`, CPython 3.12.14), temporary roots under `D:/codex-tmp/kx23`, new pytest basetemp/cache directories per run, and injected/fake probe backends only. Real probe enumeration was never invoked.

| Check | Command summary | Result |
| --- | --- | --- |
| New preflight suite | `python -m pytest tools/stm32-toolkit/tests/test_keil_preflight.py --basetemp=D:/codex-tmp/kx23/bt-impl-11 -o cache_dir=D:/codex-tmp/kx23/cache-impl-11` | 11 passed |
| Hardware workflows | `python -m pytest tools/stm32-toolkit/tests/test_hardware_workflows.py --basetemp=D:/codex-tmp/kx23/bt-impl-12 -o cache_dir=D:/codex-tmp/kx23/cache-impl-12` | 116 passed |
| MCP migration/build + plugin/skills | `python -m pytest tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_plugin_layout.py --basetemp=D:/codex-tmp/kx23/bt-impl-14 -o cache_dir=D:/codex-tmp/kx23/cache-impl-14` | 39 passed, 1 dependency warning |
| Context, planned actions, inventory, migration plan/apply, Keil inspect | `python -m pytest tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_planned_actions.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_keil_inspect.py --basetemp=D:/codex-tmp/kx23/bt-impl-15 -o cache_dir=D:/codex-tmp/kx23/cache-impl-15` | 323 passed |
| Final combined relevant suite | `python D:/codex-tmp/kx23/run_final_suite.py` (the script runs the 16-module pytest list with `--basetemp=D:/codex-tmp/kx23/bt-impl-17 -o cache_dir=D:/codex-tmp/kx23/cache-impl-17`) | **801 passed, 2 warnings, exit 0** |

Final combined modules: preflight, migration plan, migration apply, Keil inspect, context, planned actions, hardware workflows, MCP migration/build, MCP hardware, MCP roots, MCP server, CLI, CLI hardware, public inventory, plugin layout, workflows.

Durable evidence outside the repository:

- `D:/codex-tmp/kx23/final-suite.log` (full stdout/stderr, command, `EXIT=0`)
- `D:/codex-tmp/kx23/final-suite.exit.txt` (`0`)
- Initial focused run outputs are retained in the CLI tool-result transcript for basetemps `bt-impl-1` through `bt-impl-16`.

`git diff --check` reported no whitespace errors (only Git's informational LF/CRLF notices). Worktree was clean immediately after the implementation commit.

## Earlier failures, corrections and attribution

1. **Inherited MCP fixture failure (primary-confirmed at accepted base).** `test_in_memory_configure_and_build_fail_closed` failed because `tool_support` prioritizes CubeCLT/metadata/standard installed CMake before `PATH`, so startup discovery did not hit the test's PATH-only fake CMake. The primary independently reproduced this on untouched accepted-base source in `D:/WorkSpace/STM32-Toolkit`, preserved in `D:/codex-tmp/kx23/baseline-mcp.log` with exit recorded in `D:/codex-tmp/kx23/baseline-mcp.exit.txt` (`1`). The fix was test-only: inject an explicit trusted support profile inside the test data root pointing at the fake CMake, preserving all authorization/preset/build-hit assertions. No production discovery order or skip/xfail was introduced.
2. **Test-author error in stale-input regression.** The first preflight stale-input attempt changed file size, so the correct existing guard returned `MIGRATION_INPUT_INVALID` rather than `MIGRATION_INSPECTION_CHANGED`. The test was corrected to same-size byte drift; no product behavior changed.
3. **Earlier CLI tool-selection issue.** Before PowerShell was exposed, the implementation session had no shell tool: Bash was unavailable, so no tests or commits were produced in that phase. After the primary corrected per-invocation tool selection, an allowed PowerShell smoke check and the full test runs above were completed. No unexecuted test was reported as passing.
4. **MCP-only description regression.** One description assertion failed because the context docstring dropped the explicit `stm32_keil_preflight` name during the target-selection rewrite. The docstring was corrected and the MCP/plugin suite rerun to 39 passed.

## Limitations and pending review

- This report is **not** acceptance. `REVISION_REQUIRED`/`ACCEPTED` remain the primary's decision after independent complete-diff review.
- No real probe, attach, flash, reset, halt, IDE/VS Code session, physical target or hardware qualification was performed. Probe discovery tests used injected fake backends only.
- No packaging, installation, deployment, version bump or remote publication was performed; the published v1.2.0 runtime remains the frozen 48-tool package and does not contain `stm32_keil_preflight`.
- Preflight output is bounded at 64 MiB; normal complete blocker diagnostics fit within that bound. The plan limit remains unchanged and is not weakened.
- `test_in_memory_configure_and_build_fail_closed` now isolates startup discovery through a controlled profile; this changes test setup only. No claim is made that ambient CubeCLT discovery is a product defect.
- Existing broader release matrices, browser/UI checks and hardware qualification were intentionally out of scope and were not run.
