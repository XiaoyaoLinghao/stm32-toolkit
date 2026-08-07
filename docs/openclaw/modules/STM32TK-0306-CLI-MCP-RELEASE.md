# STM32TK-0306-CLI-MCP-RELEASE: CLI/MCP Workflows, Thin Skills, and 0.3.0 Gate

Status: `READY_FOR_OPENCLAW`
Accepted base commit: `2088e6d375d63e6e00ef0fa50b6aad0d0fd04fb1`
Specification owner: Codex
Implementation owner: OpenClaw
Reviewer: Codex

## 1. Objective and user-visible outcome

- Expose the already accepted STM32TK-0301 through STM32TK-0305 project model, Keil inspection/conversion, managed configuration, and reproducible build through stable CLI and project-bound MCP adapters.
- Ship exactly three new thin Claude Code Skills: `/stm32-toolkit:migrate-keil`, `/stm32-toolkit:configure-stm32-project`, and `/stm32-toolkit:build-firmware`.
- Make conversion and configuration two-phase operations: read-only planning returns a deterministic plan ID; mutation requires the caller to return that exact ID with explicit authorization, then the core independently replans and rechecks all existing digest/Git/drift guards.
- Complete the 0.3.0 release gate without duplicating product logic in CLI, MCP, or Skills, weakening any accepted module contract, or adding hardware/probe behavior.

## 2. Scope

### 2.1 In scope

- One shared workflow adapter translating stable domain results/exceptions to `OperationResult` envelopes.
- CLI commands for Keil inspect, Keil conversion plan/apply, project configuration plan/apply, and build.
- Four MCP tools bound permanently to `ServerRuntime.project_root`: `stm32_keil_inspect`, `stm32_keil_convert`, `stm32_project_configure`, and `stm32_build`.
- Context/detection capability updates so accepted migration, configuration, and build workflows are reported as available only when their prerequisites are present.
- Three thin Skills that start with `stm32_project_context`, display the read-only plan/evidence, request authorization at the mutation boundary, and call only Toolkit MCP tools.
- Unified version bump from `0.2.0` to `0.3.0` across the plugin manifest, Python package, managed runtime launcher/setup contract, current documentation, generated evidence assertions, and tests.
- End-to-end tests for inspect -> conversion plan/apply -> configuration plan/apply -> build, using the real core modules and a deterministic fake CMake process seam; Codex owns the real Windows ARM GNU gate.
- Mark the detailed 0.3 tasks delivered only after their gates pass, and mark the roadmap 0.3 release checkbox only in the final code commit that proves the complete exit gate.

### 2.2 Out of scope

- No probe service, lease, PyOCD invocation, flash, debug handoff implementation, variable/register access, monitor, host/target test runner, diagnostic session, CubeMX creation, or hardware access.
- No new schema, migration rule, generation template, MAP/ELF rule, subprocess behavior, dependency, CI workflow, collaboration app, dispatch automation, telemetry, or network service.
- No direct source/project edits in a Skill, CLI adapter, or MCP adapter. All writes go through `apply_keil_conversion`, `apply_project_configuration`, or `run_build`.
- No plan cache, database, serialized executable plan file, ambient global state, arbitrary project-root argument in MCP, arbitrary command, arbitrary environment, or shell execution.
- No automatic authorization. A Skill may explain and ask; it may not infer consent from a previous read-only call.

### 2.3 Prohibited shortcuts

- Do not retain a Python plan object between requests or trust a caller-supplied serialized plan. Recompute from current disk state and compare the exact deterministic plan ID immediately before apply.
- Do not accept `authorized` values other than the JSON boolean `true`; strings, integers, truthy objects, omitted authorization, missing plan ID, or a stale/mismatched plan ID fail closed without writes.
- Do not expose host absolute paths, environment values, credentials, raw exception text, raw bytes, or unbounded tool output in JSON/MCP results.
- Do not copy conversion/configuration/build logic into `cli.py`, `mcp_server.py`, or Skill prose.
- Do not add skip/xfail for a required pure-code gate, lower branch coverage, alter accepted error meanings, or modify any path outside section 5 plus the implementation report.

## 3. Prerequisites and initialization

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`.
- Branch from exact product base `2088e6d375d63e6e00ef0fa50b6aad0d0fd04fb1` as `openclaw/STM32TK-0306-CLI-MCP-RELEASE/r001`.
- Fetch `origin/master` to read this specification, but do not merge, rebase, or cherry-pick the specification commit into the implementation branch.
- Before editing, read `AGENTS.md`, `OPENCLAW_START_HERE.md`, this work order, the architecture, complete roadmap, 0.3 plan, all STM32TK-0301 through STM32TK-0305 work orders, and their final implementation reports.
- Verify and record: clean worktree, accepted-base match, work-order status, branch name, Python/pytest/dependency versions, OS, and availability of `claude`, CMake, Ninja, and ARM GNU tools.
- Runtime floor stays CPython 3.10+. Protocol stays `stm32-toolkit/1`. Dependencies remain jsonschema 4.23.x, mcp 1.27.x, pyelftools 0.33, Jinja2 3.1.x, pytest 8.3.x, and pytest-cov 5/6; add no dependency.
- Portable paths use `/`. Hashes and plan IDs are lowercase SHA-256 hex. JSON is UTF-8, `ensure_ascii=False`, `indent=2`, and exactly one final LF.
- Visual and hardware acceptance are `NOT_APPLICABLE` for this module.

## 4. Architecture and dependency direction

```text
CLI argparse --------------------+
                                 +--> workflows.py --> accepted core modules
project-bound FastMCP tools -----+         |
                                           +--> OperationResult JSON snapshot

thin Skills --> stm32_project_context --> read-only plan/evidence
                                      --> explicit authorization
                                      --> exact planId + authorized=true apply
```

- `workflows.py` owns input validation, exception translation, replan/plan-ID comparison, and public operation envelopes. It imports accepted core modules; core modules never import it.
- `cli.py` owns parsing, exit codes, stdout/stderr discipline, and calls workflow functions only.
- `mcp_server.py` owns root binding, MCP roots validation, tool schemas, and calls workflow functions only.
- Skills contain orchestration and user communication only. They never parse XML, rewrite source, render templates, run CMake directly, or fabricate success.
- Existing `OperationResult` protocol and core public types remain unchanged.

## 5. Exact file plan

| Status | Path | Responsibility |
|---|---|---|
| M | `.claude-plugin/plugin.json` | unified plugin version/0.3 description |
| M | `bin/stm32-toolkit-mcp.cmd` | fail-closed managed runtime path `runtime/0.3.0` |
| M | `bin/setup-stm32-env.ps1` | exact 0.3.0 bootstrap/repair/check target |
| M | `README.md` | current 0.3 workflows, commands, authorization, upgrade notes |
| M | `README_zh-CN.md` | byte-equivalent factual Chinese documentation |
| M | `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.3-project-migration-build.md` | check delivered Task 3-6 steps only after evidence passes |
| M | `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md` | check only the 0.3.0 release item in the final gated commit |
| M | `skills/setup-stm32-env/SKILL.md` | managed runtime 0.3.0 contract and available workflow handoff |
| A | `skills/migrate-keil/SKILL.md` | thin inspect/plan/authorize/apply workflow |
| A | `skills/configure-stm32-project/SKILL.md` | thin configuration plan/authorize/apply workflow |
| A | `skills/build-firmware/SKILL.md` | context/doctor/authorize/build/evidence workflow |
| M | `tools/stm32-toolkit/pyproject.toml` | Python distribution version 0.3.0 only |
| M | `tools/stm32-toolkit/src/stm32_toolkit/__init__.py` | `__version__ = "0.3.0"` |
| M | `tools/stm32-toolkit/src/stm32_toolkit/cli.py` | exact CLI grammar and adapter dispatch |
| M | `tools/stm32-toolkit/src/stm32_toolkit/context.py` | migration/configuration/build capability evidence |
| M | `tools/stm32-toolkit/src/stm32_toolkit/detection.py` | accepted actions reported available |
| M | `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` | four project-bound tools and roots guard reuse |
| A | `tools/stm32-toolkit/src/stm32_toolkit/workflows.py` | shared stable workflow adapters |
| M | `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` | generated VS Code build argv matches the shipped CLI and explicit user invocation contract |
| M | `tools/stm32-toolkit/tests/test_cli.py` | CLI grammar/results/exit/error/no-write tests |
| M | `tools/stm32-toolkit/tests/test_context.py` | capability transition tests |
| M | `tools/stm32-toolkit/tests/test_detection.py` | action availability tests |
| M | `tools/stm32-toolkit/tests/test_generation.py` | generated task argv snapshot and 0.3 evidence assertions |
| M | `tools/stm32-toolkit/tests/test_mcp_server.py` | exact seven-tool registry/root binding |
| M | `tools/stm32-toolkit/tests/test_plugin_layout.py` | exact four discovered Skills and unified version |
| M | `tools/stm32-toolkit/tests/test_setup_runtime.py` | 0.3.0 setup/upgrade/rollback paths |
| M | `tools/stm32-toolkit/tests/test_migration_plan.py` | unified version assertion only |
| M | `tools/stm32-toolkit/tests/test_build_runner.py` | unified version assertion only |
| M | `tools/stm32-toolkit/tests/test_result.py` | unified version assertion only |
| A | `tools/stm32-toolkit/tests/test_workflows.py` | shared adapter and authorization/replan regressions |
| A | `tools/stm32-toolkit/tests/test_mcp_migration_build.py` | MCP schemas, full two-phase flow, and end-to-end gate |
| A | `docs/openclaw/returns/STM32TK-0306-CLI-MCP-RELEASE/r001-implementation-report.md` | report-only final commit |

No other path is approved. In particular do not modify schemas, accepted core Keil/migration/generation/build/process modules other than the single approved generated-task argv site in `generation/configure.py`, templates, fixtures, `.mcp.json`, dependencies, historic architecture/spec documents, earlier work orders/reports, or `requirements/follow-on-skills/`.

## 6. Shared workflow contracts

`workflows.py` exposes these typed functions. Optional portable paths enter as `str | None`; convert to a relative `Path` only after rejecting NUL, absolute, drive/UNC, `.`/`..`, backslash ambiguity, and empty components.

```python
def inspect_keil_workflow(
    project_root: Path,
    *,
    uvprojx: str | None = None,
    target_name: str | None = None,
    include_baseline: bool = True,
) -> OperationResult[dict[str, object]]: ...

def convert_keil_workflow(
    project_root: Path,
    *,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> OperationResult[dict[str, object]]: ...

def configure_project_workflow(
    project_root: Path,
    *,
    plan_id: str | None = None,
    authorized: bool = False,
) -> OperationResult[dict[str, object]]: ...

def build_firmware_workflow(
    project_root: Path,
    *,
    preset: str,
    clean: bool = False,
    timeout_seconds: int = 300,
    authorized: bool,
) -> OperationResult[object]: ...
```

### 6.1 Inspect

- Canonicalize/bind `project_root`, call `inspect_keil`, and by default call `capture_keil_baseline` with that exact inspection.
- Success operation is `keil-inspect`; data keys in order are `inspection`, `baseline`. With `include_baseline=false`, `baseline` is `null`; inspection remains read-only.
- Translate only stable `KeilInspectionError` fields (baseline capture uses the same accepted error type). Filesystem and unexpected failures return bounded `KEIL_INSPECTION_UNAVAILABLE`; do not leak exception text.

### 6.2 Convert plan/apply

- Every call freshly inspects and calls `plan_keil_conversion`; no cache.
- `authorized is False`: require `plan_id is None`; return success operation `keil-conversion-plan` with `plan.to_dict()`. This is read-only and must leave bytes, names, mtimes, modes, Git state, and untracked inventory unchanged.
- `authorized is True`: require `plan_id` to be exactly 64 lowercase hex and equal to the freshly recomputed `plan.plan_id`, otherwise return `AUTHORIZATION_REQUIRED` or `PLAN_CHANGED` without calling apply. Call `apply_keil_conversion` only after equality.
- Return the core apply `OperationResult` unchanged so existing digest, Git, blocker, atomicity, and rollback errors retain their accepted codes.

### 6.3 Configure plan/apply

- Every call freshly loads `ProjectModel` and calls `plan_project_configuration`; no cache.
- `authorized is False`: require no plan ID; return success operation `project-configuration-plan` with `plan.to_dict()` and no writes.
- `authorized is True`: require a valid exact current plan ID, otherwise `AUTHORIZATION_REQUIRED`/`PLAN_CHANGED`; then call `apply_project_configuration` and preserve its result unchanged.

### 6.4 Build

- `stm32_build` is not a dry-run/apply plan: `BuildRequest` plus the accepted snapshot/build lock is its complete preflight. MCP requires the explicit JSON boolean `authorized=true` before invoking it.
- CLI invocation is itself the user's explicit process-level action and passes `authorized=True` internally; there is no CLI `--authorized` flag.
- Validate preset exactly `arm-debug|arm-release`, `clean` exact bool, timeout exact int `1..3600`; then call `run_build` and return its result unchanged.
- Missing/false/non-boolean MCP authorization returns `AUTHORIZATION_REQUIRED`, operation `build`, before filesystem writes or process launch.

### 6.5 Stable adapter errors

Use only these adapter-owned codes: `WORKFLOW_INPUT_INVALID`, `AUTHORIZATION_REQUIRED`, `PLAN_CHANGED`, `KEIL_INSPECTION_UNAVAILABLE`, `MIGRATION_PLAN_UNAVAILABLE`, and `CONFIGURATION_PLAN_UNAVAILABLE`. Details contain only field/rule, portable path, allowed values, or current plan ID as appropriate. Accepted core error codes pass through unchanged.

## 7. CLI contract

All workflow commands accept `--project <path>` with alias `--project-root <path>`. They emit exactly one JSON `OperationResult` document to stdout and nothing to stderr for expected domain failure. Success returns 0, expected failure 2, parser error 2, and unexpected internal error 1 with bounded stderr and empty stdout. Never change cwd.

```text
stm32-toolkit keil inspect [--project PATH] [--uvprojx REL] [--target-name NAME] [--no-baseline] --json
stm32-toolkit keil convert [--project PATH] [--uvprojx REL] [--target-name NAME] --dry-run --json
stm32-toolkit keil convert [--project PATH] [--uvprojx REL] [--target-name NAME] --apply --plan-id SHA256 --authorized --json
stm32-toolkit project configure [--project PATH] --dry-run --json
stm32-toolkit project configure [--project PATH] --apply --plan-id SHA256 --authorized --json
stm32-toolkit build [--project PATH] --preset {arm-debug,arm-release} [--clean] [--timeout-seconds N] [--json]
```

- `--dry-run` and `--apply` are required mutually exclusive modes. `--authorized` is valid only with apply and exact plan ID.
- Build JSON is default so generated VS Code tasks remain machine-readable; optional `--json` is accepted for consistency.
- Preserve all existing foundation CLI grammar and results. `version` prints only `0.3.0` plus LF.
- Update generated Debug/Release task argv to the exact supported `build --preset ... --project ${workspaceFolder}` contract; do not expose flash/debug commands as implemented in this release.

## 8. MCP contract

- The server registers exactly seven tools: the existing three plus the four below. No tool accepts `projectRoot`, `dataRoot`, command, environment, or arbitrary path.
- Every new request wrapper runs the existing `_client_roots_failure` check before adapter work; cancellation/timeout behavior from STM32TK-0301 remains unchanged.

```text
stm32_keil_inspect(uvprojx?: string, targetName?: string, includeBaseline: boolean = true)
stm32_keil_convert(uvprojx?: string, targetName?: string, planId?: string, authorized: boolean = false)
stm32_project_configure(planId?: string, authorized: boolean = false)
stm32_build(preset: "arm-debug"|"arm-release", clean: boolean = false, timeoutSeconds: integer = 300, authorized: boolean = false)
```

- Tool schemas must expose only those properties, correct required/default/type/enum constraints, and no additional properties where FastMCP supports it.
- Server instructions say it is project-bound and exposes read-only inspection/planning plus explicitly authorized conversion/configuration/build operations; remove the obsolete “only read-only foundation tools” claim.
- Direct helper tests, in-memory FastMCP calls, stdio startup, roots mismatch/unavailable/cancellation, and multi-root rejection all remain green.

## 9. Context, detection, and Skills

- Detection actions `migrate-keil` and `configure-project` become `available=true` with factual 0.3 explanations. `create-project` remains unavailable.
- Context capabilities add booleans `keilInspect`, `keilConvert`, and `configure`; retain existing `build`, `flash`, `hostTest`, `targetTest`, `monitor`, and `breakpointDebug` keys. Keil inspect/convert are true only for a detected Keil project; configure is true only for valid Schema v2; build is true only when the accepted managed configuration prerequisites are present. Hardware capabilities remain false.
- Each new Skill is valid YAML-frontmatter Markdown, concise, and contains exact MCP tool names/argument shapes.
- First action in every new Skill is `stm32_project_context`. If the required capability is false, report its evidence and stop.
- Migration Skill: inspect -> show selected target/baseline/warnings -> conversion plan -> show blockers and exact changed paths/diffs -> ask explicit authorization tied to the displayed plan ID -> apply exact plan ID -> return result.
- Configuration Skill: context -> read-only plan -> show file statuses/diffs/blockers -> ask exact-plan authorization -> apply -> return result.
- Build Skill: context -> `stm32_doctor` -> show preset/clean/toolchain evidence -> ask authorization for this build invocation -> call `stm32_build(..., authorized=true)` -> report build ID, Git HEAD/dirty state, ELF/MAP hashes, memory, warnings, and portable artifact paths.
- A Skill never says “wait for Codex”, never waits in a subsystem after completion, and immediately returns the complete work result to the caller.

## 10. Unified 0.3.0 release

- The only current runtime version after the change is `0.3.0`: plugin manifest, Python distribution, `__version__`, CLI, launcher, setup script, setup Skill, READMEs, and relevant generated/report assertions agree exactly.
- Setup Check reports existing 0.2.0 as non-current and recommends the existing safe Repair flow. Bootstrap/Repair stage only under `runtime/.staging/0.3.0-<id>`, validate exact 0.3.0 plus doctor, promote to `runtime/0.3.0`, and preserve existing quarantine/rollback/redirect protections.
- MCP launcher fails closed if the exact 0.3.0 runtime is absent/broken and directs the user to `/stm32-toolkit:setup-stm32-env`; it never falls back to 0.2.0 or system Python.
- Plugin discovery contains exactly four Skills: setup plus the three new workflows. `requirements/follow-on-skills/` remains undiscovered and unchanged.
- Historic specs, earlier work orders/reports, and recorded old-version evidence remain historical and are not mass-rewritten.

## 11. Required TDD and verification

### 11.1 RED evidence

Before product implementation, add focused tests and record their exact failure output against accepted base. At minimum RED must prove missing workflow APIs/tools/Skills and obsolete version/capability assertions. Do not manufacture RED by changing expected values after implementation.

Required regression classes:

1. Convert/configure plan calls preserve complete tree bytes/names/mtimes/modes/Git inventory.
2. Apply without authorization, false/string/integer authorization, missing/malformed/stale plan ID, and a disk change between plan/apply never call the core apply seam and never write.
3. Exact current plan ID plus boolean true calls apply once; the core independently catches a post-replan race.
4. MCP cannot override bound root; roots mismatch/unavailable/cancellation remains stable for every new tool.
5. CLI/MCP return identical operation/code/data for equivalent requests and contain no absolute root or exception leakage where the underlying public protocol uses portable paths.
6. CLI mode conflicts and invalid types fail without mutation; cwd is preserved; one JSON document is emitted.
7. The four-Skill discovery set, first-context rule, tool names, authorization boundary, and absence of embedded XML/source-rewrite/CMake logic are asserted.
8. 0.2.0 runtime is never selected after bump; setup upgrade/rollback and 0.3.0 external-wheel load are proven.
9. End-to-end copy of the Keil fixture runs inspect -> conversion plan/apply -> configuration plan/apply -> fake build and links plan IDs, conversion report, managed manifest, build result, identity, hashes, and Git HEAD.

### 11.2 Required commands

Use the exact pinned environment and set `PYTHONPATH=tools/stm32-toolkit/src` for source-tree tests.

```text
python -m pytest tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_mcp_migration_build.py -q
python -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_detection.py -q
python -m pytest tools/stm32-toolkit/tests -q --cov=stm32_toolkit --cov-branch --cov-report=term
python -m compileall -q tools/stm32-toolkit/src tools/stm32-toolkit/tests
git diff --check 2088e6d375d63e6e00ef0fa50b6aad0d0fd04fb1..HEAD
git diff --name-status 2088e6d375d63e6e00ef0fa50b6aad0d0fd04fb1..HEAD
```

- Branch coverage is at least 90% overall and at least 90% for new `workflows.py`; do not exclude files or lines.
- No new skip/xfail. Existing platform skips must be enumerated and attributed.
- Performance on a warm local filesystem, 20 measured runs after 3 warmups: inspect/plan adapter < 500 ms median, configure plan < 500 ms median, MCP in-memory adapter overhead excluding core operation < 25 ms median. No timing assertion in ordinary unit tests.
- Wheel gate: build/install the wheel into a fresh external venv, use a cwd outside the repository, assert version 0.3.0, four CLI workflows, packaged schemas/templates, and a full fake-toolchain build.
- Plugin gate: run `claude plugin validate .` when available and record exact version/exit/output. Validate a clean isolated plugin install/update from 0.2.0 to 0.3.0 without a second MCP registration.
- Secret/placeholder scan: no plaintext credential, unfinished `pass`/ellipsis/pending marker, debug print, raw exception disclosure, or copied business logic in Skills.

## 12. Evidence ownership matrix

| Gate | Required environment | Evidence owner | Deferred rule |
|---|---|---|---|
| Focused/full Python, branch coverage, compileall, diff/scope, read-only/authorization/atomicity, performance, wheel | Linux x86_64, CPython 3.10.11, pinned deps | OpenClaw | Not deferrable |
| Windows focused/full including roots cancellation, path/case behavior, setup Repair/rollback, launcher | Windows NTFS, CPython 3.12.13 | Codex | `DEFERRED_TO_CODEX` only |
| Real CLI/MCP arm-debug + arm-release using CMake 4.3.1, Ninja 1.13.2, ARM GNU 14.3.1/binutils 2.44 | Codex Windows toolchain | Codex | `DEFERRED_TO_CODEX` only |
| Claude plugin validate and clean isolated 0.2.0 -> 0.3.0 install/update | Machine with Claude Code | OpenClaw if available; otherwise Codex | Name actual owner; never claim another actor's run |
| Visual/hardware | N/A | N/A | `NOT_APPLICABLE` |

A pure-code failure cannot be deferred because it happens on one OS. Report the actual environment, exact commit tested, command, exit code, counts, versions, and observed result.

## 13. Commit, report, and remote contract

- Use TDD with separately reviewable RED, workflow/MCP/CLI, Skills/version, gate/docs, and report commits. Do not amend, rebase, cherry-pick, or force-push.
- The implementation report is the last commit and records accepted base plus the code head before the report commit. It must not contain its own final SHA or moving commit totals.
- Push only `openclaw/STM32TK-0306-CLI-MCP-RELEASE/r001`; create/update one Draft PR targeting `master`.
- Authorized remote actions for OpenClaw: normal push of this branch and create/update its Draft PR. Not authorized: push `master`, merge, approve, close, delete any branch, rewrite history, or mutate another PR.
- Keep the worktree clean and prove local HEAD = remote branch HEAD = PR head OID.
- On completion, return the result immediately and terminate the OpenClaw task. Do not enter a waiting state and do not say “waiting for Codex acceptance.”

## 14. Required return payload

Return one concise result containing:

- `Status: IMPLEMENTED` or `BLOCKED`;
- module/attempt/branch, accepted base, code head, final remote head, PR URL/state/base/head;
- exact changed-path inventory and confirmation it matches section 5;
- RED evidence, focused/full counts, coverage, compileall, diff check, clean status;
- authorization/read-only/replan/end-to-end/wheel/performance/plugin evidence;
- environment-separated deferred gates with named owner;
- report path, limitations, and three-way local/remote/PR identity proof.

Do not return a progress-only message. Do not wait for a follow-up after the work is complete.
