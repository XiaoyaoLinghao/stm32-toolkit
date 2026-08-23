# STM32 Toolkit VS07-B Authorized Creation and Build Implementation Plan

> **Worker requirement:** use `executing-plans`, `test-driven-development`, and
> `verification-before-completion`. One GPT-5.6-luna/max implementer owns all
> Tasks 1-4 as sequential checkpoints. Do not dispatch another implementation
> agent and do not self-approve the diff.

**Goal:** Consume a single-use authorization to generate one validated CubeMX
project in isolation, reuse Toolkit configure/build for Debug and Release, and
transactionally activate the complete destination.

**Architecture:** VS07-A remains the deterministic planning boundary. A durable
authorization store binds one plan to one immutable execution-environment
digest. The orchestration layer consumes that capability before calling a
bounded CubeMX adapter. Native output is parsed into the existing project model,
configured and built in sibling staging, then activated under an exclusive
destination lock.

**Tech stack:** CPython `>=3.12,<3.13`, dataclasses, pathlib, JSON, hashlib,
uuid, existing bounded process/configure/build workflows, argparse, FastMCP,
pytest, Windows STM32CubeMX `6.18.x` CLI.

## Global constraints

- Accepted base: `bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e`.
- Governing design:
  `docs/superpowers/specs/2026-08-23-stm32-toolkit-0702-authorized-creation-build-design.md`.
- Branch/worktree: `codex/STM32TK-0702-CREATION-APPLY` at
  `C:/tmp/stm32tk-0702-creation-apply`.
- One Luna/max owns every product, test, report, ledger, and local commit in this
  plan. Tasks are checkpoints, not separate agents or approval gates.
- Sol writes no product code and later reviews the complete accepted-base diff
  in a new clean detached worktree.
- Do not push, create/mutate a PR, merge, tag, release, install software or
  packages, touch hardware, or implement VS07-C.
- Never expose ambient credentials, inherit an open process environment, invoke
  the detaching CubeMX wrapper, or relabel fake evidence as native PASS.
- Preserve the current host's missing offline firmware repository as an
  `ENVIRONMENT` observation. Do not repair it by installation.
- Use short disposable `--basetemp` paths because long Windows TEMP paths have
  caused environmental ACL/path failures.

## Task 1: Single-use preparation and execution environment

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/creation_authorization.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/creation_environment.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/generation/creation.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/creation_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_creation_authorization.py`
- Create: `tools/stm32-toolkit/tests/test_creation_environment.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_plan.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_workflows.py`

**Frozen interfaces:**

- Immutable `CreationExecutionEnvironment` with normalized CubeMX, sibling
  Java, offline repository/package and existing build-tool facts plus one
  deterministic digest.
- Immutable prepare request/result carrying the exact VS07-A request,
  `plan_id`, `action_digest`, expiry, and `authorization_digest`.
- `CreationAuthorizationStore.prepare(...)` and atomic
  `consume(authorization_digest, *, authorized: bool)`; no public reset or
  unconsume operation.

- [ ] Write RED tests for safe sibling-Java binding; missing/invalid/ambiguous
  repository and package; deterministic environment digest; plan/action/tool/
  repository/destination drift; exact `authorized is True`; expiry; malformed
  record; replay; and two concurrent consumers where exactly one wins.
- [ ] Add a RED workflow test proving prepare invokes neither CubeMX nor any
  destination write and returns `mutated=false`.
- [ ] Run:

  ```powershell
  py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py -q --basetemp C:\tmp\p0702-t1-red
  ```

  Record expected missing-interface/behavior failures before product edits.
- [ ] Implement closed parsing/containment, atomic record transitions, fixed
  clock/random seams, bounded JSON records, and preparation re-planning. Reuse
  public VS07-A error serialization; do not broaden `ToolSupportProfile`.
- [ ] Rerun the same files with `C:\tmp\p0702-t1-green`; require exit 0 and no
  skip/xfail.
- [ ] Commit product/tests with
  `git commit -m "feat(project): add single-use creation authorization"`.

## Task 2: Authorized CubeMX adapter and native project model

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/cubemx_adapter.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/cubemx_project.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/process.py` only if a RED test
  proves a missing general bounded-process primitive
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py`
  only for the distinct CubeMX ownership manifest boundary
- Create: `tools/stm32-toolkit/tests/test_cubemx_adapter.py`
- Create: `tools/stm32-toolkit/tests/test_cubemx_project.py`
- Expand: `tools/stm32-toolkit/tests/test_process.py` only when process code
  changes
- Expand: `tools/stm32-toolkit/tests/test_generation.py`

**Frozen interfaces:**

- The adapter accepts an internal consumed capability and one validated staging
  context. It exposes no caller argv, script, environment, home, repository,
  timeout, or executable override.
- Process argv is sibling Java + fixed JVM properties + `-jar CubeMX.exe -q
  script`; the runner receives a closed environment.
- Native parsing is declarative and bounded. It parses the closed generated
  CMake/.ioc/linker-script subset; it never executes CMake or guesses MCU,
  framework, or language conversions.
- `.stm32-toolkit/cubemx-ownership.json` stores portable generated-file hashes
  and source/tool/package bindings. `.stm32-project.json` remains schema 2.

- [ ] Write RED tests proving direct adapter rejection; one runner call; exact
  argv/env/script; no network/install commands; HAL handling; LL and C++ closed
  preconditions; nonzero/timeout/truncation/`KO`/missing `OK`/missing `Bye bye`;
  and tolerance of unrelated log `[ERROR]` text when protocol succeeds.
- [ ] Write RED validation tests for file/byte/depth/path limits, reparse and
  escape rejection, missing/ambiguous variables, unsafe CMake constructs,
  source/include/define/CPU/FPU/ABI/linker extraction, `.ioc`/package agreement,
  deterministic logical UUID, and literal ownership-manifest output.
- [ ] Run:

  ```powershell
  py -3.12 -m pytest tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py -q --basetemp C:\tmp\p0702-t2-red
  ```

  Record expected failures before product edits.
- [ ] Implement the minimum coherent adapter/parser/manifest boundary. Reuse
  the existing process result and schema-2 generation model rather than adding
  parallel abstractions.
- [ ] Rerun with `C:\tmp\p0702-t2-green`; require exit 0 and no skip/xfail.
- [ ] Commit with
  `git commit -m "feat(project): add authorized CubeMX generation adapter"`.

## Task 3: Staging, configure/build reuse, and activation

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/creation_apply.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/creation_workflows.py`
- Reuse/modify only when a RED integration proof requires it:
  `tools/stm32-toolkit/src/stm32_toolkit/workflows.py`
- Reuse/modify only when a RED integration proof requires it:
  `tools/stm32-toolkit/src/stm32_toolkit/build/runner.py`
- Create: `tools/stm32-toolkit/tests/test_creation_apply.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_workflows.py`
- Expand only for affected regression:
  `tools/stm32-toolkit/tests/test_workflows.py`
- Expand only for affected regression:
  `tools/stm32-toolkit/tests/test_build_runner.py`

**Frozen orchestration:** consume -> revalidate -> create sibling staging ->
CubeMX once -> validate/model/ownership -> existing configure -> existing Debug
build -> existing Release build -> lock/revalidate -> transactional activation.

- [ ] Write RED integration tests with recording fakes proving the exact order,
  one CubeMX call, configure/build reuse, Debug and Release identities, absent
  destination activation, empty destination activation, populated/drifted
  rejection, concurrent activation exclusion, and no activation before both
  builds succeed.
- [ ] Add failure-injection tests at every lifecycle boundary, including first
  and second rename, backup cleanup, rollback, and staging cleanup. Assert the
  destination is exactly absent/empty after every recoverable failure and that
  rollback failure is separately typed with bounded evidence.
- [ ] Run:

  ```powershell
  py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py -q --basetemp C:\tmp\p0702-t3-red
  ```

- [ ] Implement the orchestration with injected filesystem/clock/adapter seams,
  safe same-volume sibling paths, exclusive locks, final drift checks, and
  sanitized attempt evidence. Do not initialize or commit Git.
- [ ] Rerun with `C:\tmp\p0702-t3-green`; require exit 0 and no skip/xfail.
- [ ] Commit with
  `git commit -m "feat(project): activate complete generated projects"`.

## Task 4: CLI/MCP integration, evidence, and return

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_cli.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_mcp.py`
- Expand: `tools/stm32-toolkit/tests/test_cli.py`
- Expand: `tools/stm32-toolkit/tests/test_mcp_server.py`
- Expand: `tools/stm32-toolkit/tests/test_mcp_roots.py`
- Modify: `README.md`
- Modify: `README_zh-CN.md`
- Create:
  `docs/codex/returns/STM32TK-0702-CREATION-APPLY/implementation-report.md`
- Update:
  `.superpowers/sdd/2026-08-23-stm32-toolkit-0702-authorized-creation-build/progress.md`

- [ ] Write RED CLI/MCP tests for exact schemas, duplicate scalar rejection,
  exact boolean authorization, parity with fixed runtime/clock/random seams,
  client-root containment, runtime-pinned environment, no caller overrides,
  replay, typed failures, and absence of raw host/staging/process data.
- [ ] Implement the two CLI commands and two MCP tools as thin adapters over the
  shared workflows. Update English/Chinese docs without claiming native PASS.
- [ ] Run the focused public command:

  ```powershell
  py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-t4-public
  ```

- [ ] Run the exact complete VS07-B slice command:

  ```powershell
  py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_authorization.py tools/stm32-toolkit/tests/test_creation_environment.py tools/stm32-toolkit/tests/test_cubemx_adapter.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_creation_apply.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_process.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q --basetemp C:\tmp\p0702-slice
  ```

  Require exit 0, zero failures/errors, and no new skip/xfail.
- [ ] On the real host, run read-only doctor and create-prepare against a
  disposable workspace. Require the installed CubeMX/CubeCLT facts and the
  typed missing-repository/package environment failure, no CubeMX process, and
  unchanged destination snapshot. Do not install the missing package.
- [ ] If and only if an appropriate offline firmware package is already present,
  run one disposable `.ioc` and one MCU native apply through Debug and Release;
  otherwise record positive native acceptance as `ENVIRONMENT` blocked, not
  `PASS` or `DEFERRED` product evidence.
- [ ] Run `git diff --check
  bff9cc120923b0e9f2ba29a1b3511f1bcc26ab6e..HEAD`, inspect full diff/status,
  and confirm no VS07-C, hardware, install, release, or remote scope.
- [ ] Write the implementation report with accepted base, CodeHead before its
  report commit, exact commands/counts, RED/GREEN evidence, real environment
  observation, product/environment classifications, local branch/worktree and
  unpushed state. Do not include the report commit's own SHA or moving totals.
- [ ] Commit product/docs first as appropriate, then report/ledger only with
  `git commit -m "docs(project): record VS07-B implementation evidence"`.
- [ ] Return a clean local HEAD to Sol. Do not start VS07-C.

## Sol review and stop condition

Sol creates a new clean detached review worktree at the returned HEAD, reviews
the complete accepted-base diff, reruns the exact VS07-B slice command, and
repeats the real read-only environment observation. Correctable findings return
to this same Luna owner and branch. If the same issue fails to converge in two
rounds, stop local patching and revisit this design.

VS07-B is `ACCEPTED` only after all non-environment gates and both required real
positive native scenarios pass. With the currently missing offline repository,
the expected interim outcome is an implementation-complete local candidate with
an explicit `ENVIRONMENT` acceptance blocker. VS07-C implementation begins only
after VS07-B is accepted.
