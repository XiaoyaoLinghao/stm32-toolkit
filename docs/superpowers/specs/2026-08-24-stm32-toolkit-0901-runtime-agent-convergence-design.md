# STM32 Toolkit VS09-A Runtime and Agent Adapter Convergence Design

**Status:** Approved design; self-contained slice specification

**Approval:** The user approved this design on 2026-08-24 and authorized the Sol primary
agent to make subsequent local specification, plan, implementation-coordination, review, and
verification decisions without another approval stop. This does not authorize hardware, push,
PR, merge, tag, release, remote-branch mutation, or any other remote mutation prohibited by the
goal.

**Full accepted base:** `9a5a132b74638a39b346848cfad0eeb7db9a0539`

**Specification and plan owner:** GPT-5.6-sol primary agent

**Implementation owner:** exactly one `gpt-5.6-luna` subagent with reasoning effort `max`, to be
recorded in the slice SDD ledger at dispatch

**Independent reviewer and acceptor:** GPT-5.6-sol primary agent

**Implementation branch/worktree:** `codex/STM32TK-0901-RUNTIME-AGENT-CONVERGENCE` /
`C:/tmp/stm32tk-0901-runtime-agent-convergence`

**Active PR and remote authority:** no PR; no push, PR mutation, merge, close, tag, release,
remote-branch deletion, or other remote mutation is authorized

**Bounded ownership override:** none

## 1. Authority and replacement

This specification is the just-in-time VS09-A slice under:

- `docs/superpowers/specs/2026-08-22-stm32-toolkit-0.7-1.0-integrated-product-design.md`;
- `docs/superpowers/plans/2026-08-22-stm32-toolkit-0.7-1.0-vertical-delivery-plan.md`;
- `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`, only where the
  integrated design retains it; and
- repository and user-level `AGENTS.md` governance supplied for this run.

It replaces the 0.5 packaging assumptions that the runtime launcher is Claude-only, that host
Python 3.10+ is supported, that the current managed runtime is `0.5.0`, and that the public MCP
inventory contains fifteen tools. Historical reports and fixtures remain evidence of the versions
that produced them; they are not silently relabelled as 0.9 evidence.

## 2. Reconstructed accepted-base facts

- Read-only `origin/master` identity is exactly the full accepted base above.
- VS08-A and VS08-B are independently accepted. Their product CodeHeads are respectively
  `da0078c949ad17676aebd5fd1ec9fd763fb55cc8` and
  `38972842729f944359a58b3d696752f44d9fd6d5`; later commits through the accepted base are
  report, acceptance, and documentation reconciliation.
- The VS09-A worktree starts clean at the accepted base with no upstream and no local product,
  specification, plan, or report commit.
- The unrelated `D:/workspace/stm32-toolkit` checkout contains user-owned tracked and untracked
  changes and is out of scope.
- The MCP executable already requires explicit `--project-root` and `--data-root`; the CLI still
  falls back to the process current directory when `--project-root` is absent.
- The Claude MCP manifest already registers exactly one server and passes explicit project/data
  roots, but both Windows launchers still select their interpreter from `CLAUDE_PLUGIN_DATA`.
- Toolkit, Monitor, plugin, UI package, launchers, setup helper, Skills, and README still contain
  0.5/3.10 packaging facts. The server registers 48 MCP tools while README still claims fifteen.
- Eight release Skills exist. VS09-A retains exactly those eight and does not promote the
  historical follow-on requirement copies into installed Skills.

## 3. Runnable user scenarios

### Scenario A1: generic CLI from an explicit project

A Windows user with the one managed 0.9 runtime runs `stm32-toolkit` from an arbitrary current
directory. `stm32-toolkit version` returns `0.9.0` without a project. Every other project-bound
command requires exactly one explicit `--project-root`; absence or duplication exits with code 2,
does not infer the current directory, and does not mutate project or data state.

### Scenario A2: generic MCP from any stdio-capable Agent

An Agent configuration invokes the repository's one `bin/stm32-toolkit-mcp.cmd`, supplies an
explicit `STM32_TOOLKIT_DATA_ROOT`, and passes explicit `--project-root` and `--data-root`
arguments. The launcher selects only
`<data-root>/runtime/0.9.0/Scripts/python.exe`, starts the existing project-bound stdio server,
and exposes the frozen 48-tool inventory. A missing variable or runtime fails closed without
trying `python`, `py`, `uv`, another venv, or another MCP registration.

### Scenario A3: retained Claude thin adapter

Claude Code discovers the existing plugin, eight Skills, and bundled `.mcp.json`. The manifest
maps `${CLAUDE_PLUGIN_DATA}` to `STM32_TOOLKIT_DATA_ROOT` and passes
`${CLAUDE_PROJECT_DIR}`/`${CLAUDE_PLUGIN_DATA}` as the same generic explicit MCP roots. The Skills
select workflows and render user guidance only; they do not implement Project, Build, Probe,
Monitor, Test, Diagnostic, Acceptance, runtime, or MCP behavior.

### Scenario A4: one version and support inventory

In a healthy CPython 3.12 managed runtime, CLI `version`, doctor, Toolkit package metadata,
Monitor package/protocol/runtime, plugin manifest, UI package, launcher path, setup helper, Skills,
English/Chinese README, and the actual MCP/Skill inventory agree on release `0.9.0`, Python
`>=3.12,<3.13`, 48 MCP tools, and eight Skills. Doctor reports the current inventory without
probing hardware or mutating the project.

## 4. Explicit non-goals

VS09-A does not:

- implement pinned GitHub-source acquisition, checksums, archives, SBOM, license bundles,
  compatibility/troubleshooting artifacts, secure persisted runtime migration, or downgrade
  refusal; VS09-B owns those behaviors after VS09-A acceptance;
- add an Agent-specific product branch, Skill, command, service, runtime, MCP registration,
  controller, scheduler, provider, backend, or state store;
- add Python 3.10, 3.11, 3.13, Linux, or macOS support;
- alter the 48 MCP operations' domain semantics, the VS08 scenarios, project schemas, Probe,
  Monitor UI behavior, Evidence, Test, Diagnostic, or Acceptance state machines;
- run a release matrix, full coverage gate, browser E2E, performance campaign, external-tool
  installation, hardware test, or remote/release operation; or
- rewrite historical evidence merely to display 0.9.0. Only fixtures that model the current
  runtime/package contract are updated.

## 5. Frozen shared contracts

### 5.1 Release and Python contract

- Release SemVer: `0.9.0`.
- Supported interpreter: CPython satisfying `>=3.12,<3.13`; equivalently major/minor `(3, 12)`.
- `stm32_toolkit.__version__` is the in-process version authority.
- CLI imports that authority rather than maintaining a second Python constant.
- Monitor imports the Toolkit authority for both `TOOLKIT_VERSION` and its release-aligned
  `MONITOR_VERSION`; `stm32_monitor.__version__` exposes the same value.
- Static package/plugin/UI/launcher/helper/Skill/README copies are release artifact declarations
  checked against the authority by behavior-focused package/inventory tests.
- Protocol schema versions (`stm32-toolkit/1`, Probe `/2`, Monitor `/1`) do not change merely
  because the release SemVer changes.

### 5.2 Runtime root and launcher contract

`STM32_TOOLKIT_DATA_ROOT` is the only ambient variable consumed by the two generic Windows
launchers. It is an explicit absolute per-user data root, not an Agent identity. The launchers
select exactly:

```text
<STM32_TOOLKIT_DATA_ROOT>/runtime/0.9.0/Scripts/python.exe
```

The MCP launcher executes `-m stm32_toolkit.mcp_server`; the Monitor launcher executes
`-m stm32_monitor`. Both forward caller arguments and preserve the child exit code. They neither
parse a project root from the current directory nor fall back to another interpreter. Error text
names the generic variable and generic setup command first; Claude namespaced guidance may be
added only by the Claude Skill/README adapter.

### 5.3 Explicit CLI and MCP roots

- `stm32-toolkit version` is the only root-free CLI command.
- Every other CLI command requires `--project-root` exactly once in one of the currently supported
  global or command-local positions. Missing, duplicate, empty, unresolved, non-absolute where an
  absolute root is required by the consuming boundary, or unsafe roots fail before workflow
  invocation. The CLI never substitutes `Path.cwd()`.
- Stateful CLI commands continue to require their existing explicit `--data-root` and
  `--session-id`; VS09-A does not widen or collapse those boundaries.
- `stm32-toolkit-mcp` continues to require exactly one `--project-root` and `--data-root`, binds
  the runtime permanently to the canonical project, rejects data roots at/below the project, and
  rechecks MCP client roots on every request.
- Public MCP tool inputs still do not accept project root, data root, executable, command,
  environment, service credential, target override, SVD override, ELF path, or raw address.

### 5.4 Generic setup helper and lifecycle

`bin/setup-stm32-env.ps1` remains the one runtime setup engine but its public parameters become
Agent-neutral:

```text
-Mode Check|Bootstrap|Repair
-ToolkitRoot <absolute immutable source root>
-DataRoot <absolute per-user data root>
-ProjectRoot <absolute existing project root>
```

The helper does not read Claude environment variables. Claude Skills substitute their paths into
these generic parameters. All supplied paths reject unresolved `${...}` placeholders and unsafe
redirect ancestors before mutation.

The only lifecycle transitions in VS09-A are:

```text
missing --authorized Bootstrap--> unique 0.9.0 staging --validated promotion--> healthy
legacy/broken --authorized Repair--> quarantine --> unique staging --> healthy
healthy --Check--> healthy (read-only)
failed staging --> no promotion; safe disposable staging removed
failed promotion after quarantine --> prior runtime restored
```

`Check` is always read-only and reports `missing`, `healthy`, or `broken`. A discovered 0.3.0 or
0.5.0 runtime is legacy evidence and recommends `Repair`; it is never selected by a launcher.
Bootstrap/Repair use only a discovered CPython 3.12 interpreter to create the one managed runtime.
VS09-A installs the local Toolkit and Monitor source trees as the existing bounded implementation
does; VS09-B replaces the acquisition input with a pinned, checksummed source/artifact contract.

### 5.5 Doctor result

Doctor preserves the existing `OperationResult` envelope and read-only tool/project evidence and
adds these closed fields under `data`:

```json
{
  "runtime": {
    "requiredPython": ">=3.12,<3.13",
    "pythonVersion": "3.12.x",
    "pythonSupported": true,
    "toolkitVersion": "0.9.0",
    "monitorVersion": "0.9.0",
    "versionsCompatible": true
  },
  "publicInventory": {
    "mcpTools": ["48 exact names in section 5.6"],
    "skills": ["8 exact names in section 5.7"]
  }
}
```

If Monitor distribution metadata is absent or unreadable, `monitorVersion` is `null` and
`versionsCompatible` is false; doctor remains a successful evidence collection unless an existing
doctor boundary independently fails. On unsupported Python, `pythonSupported` is false. Doctor
does not install, repair, start a Probe/Monitor, read hardware, or create data directories.

### 5.6 Frozen MCP inventory

The 0.9.0 server exposes exactly these 48 existing names, with no aliases or second server:

```text
stm32_doctor
stm32_project_detect
stm32_project_context
stm32_project_create_plan
stm32_project_create_prepare
stm32_project_create_apply
stm32_project_regenerate_plan
stm32_project_regenerate_prepare
stm32_project_regenerate_apply
stm32_keil_inspect
stm32_keil_convert
stm32_project_configure
stm32_build
stm32_probe_list
stm32_flash
stm32_debug_handoff_begin
stm32_debug_handoff_end
stm32_variable_read
stm32_variable_sample
stm32_register_read
stm32_fault_analyze
stm32_diagnostic_start
stm32_diagnostic_show
stm32_diagnostic_begin
stm32_diagnostic_hypothesis_add
stm32_diagnostic_hypothesis_assess
stm32_diagnostic_plan_add
stm32_diagnostic_plan_run
stm32_test_target_replay
stm32_diagnostic_source_change_declare
stm32_diagnostic_verification_plan_add
stm32_diagnostic_verification_start
stm32_diagnostic_marker_attach
stm32_diagnostic_verification_complete
stm32_diagnostic_verification_show
stm32_test_host_discover
stm32_test_host_run
stm32_test_show
stm32_test_target_prepare
stm32_test_target_execute
stm32_acceptance_scenario_describe
stm32_acceptance_scenario_record
stm32_acceptance_scenario_show
stm32_acceptance_attempt_begin
stm32_acceptance_attempt_checkpoint
stm32_acceptance_attempt_authorize_source_change
stm32_acceptance_attempt_show
stm32_acceptance_attempt_resume
```

### 5.7 Frozen Skill inventory

The Claude adapter exposes exactly these eight thin Skills:

```text
setup-stm32-env
migrate-keil
configure-stm32-project
build-firmware
flash-firmware
debug-firmware
read-var
stm32-monitor
```

Only setup and Monitor launcher wording changes for the generic contract. The other six retain
their accepted public workflows and thin-adapter boundary.

## 6. Dependency direction and single sources of truth

```text
Claude .mcp.json / Skills / generic Agent example
                    |
                    v
        generic launchers + explicit roots
                    |
                    v
        one managed CPython 3.12 runtime
                    |
                    v
     existing CLI / MCP / Monitor product core
```

- Agent adapters depend on the generic launcher contract; the product core never imports or
  branches on an Agent.
- Monitor depends on Toolkit release identity; Toolkit does not depend on Monitor UI behavior.
- The runtime directory selected by `STM32_TOOLKIT_DATA_ROOT` is the sole interpreter authority.
- Canonical CLI/MCP project roots remain the sole workspace location authority.
- Existing Project, Evidence, Probe lease, Monitor, Test, Diagnostic, and Acceptance stores remain
  their own authorities; VS09-A creates no replacement state.

## 7. Error and safety semantics

- Grammar/root errors: exit 2, bounded generic stderr, no workflow invocation or mutation.
- Missing generic data-root variable/runtime interpreter: launcher exit 2, no stdout, no fallback.
- Child process exit: launcher returns the exact child exit code.
- Runtime check mismatch: structured `broken` evidence with expected/observed versions and Repair
  recommendation; it never silently selects a legacy runtime.
- Unsupported bootstrap Python: Bootstrap/Repair fail before staging creation.
- Redirect/unresolved path: fail before creating runtime/data/project content.
- Doctor metadata absence: evidence is unavailable/incompatible, never invented.
- Hardware, platform, environment, infrastructure, report, and product failures retain the
  integrated design classifications. Replay/fixture evidence remains non-physical.

## 8. Documentation contract

README and README_zh-CN must:

- distinguish the local VS09-A candidate from a pushed, tagged, or released artifact;
- show a generic explicit-root CLI example and a generic stdio MCP configuration template using
  the one launcher and `STM32_TOOLKIT_DATA_ROOT`;
- describe the Claude `.mcp.json` as a thin mapping to that same contract;
- state CPython `>=3.12,<3.13`, release `0.9.0`, 48 MCP tools, and eight Skills accurately;
- retain no 15-tool, current-0.5-runtime, or host-Python-3.10 support claim; and
- leave pinned GitHub installation, checksums, SBOM, licenses, compatibility, secure upgrades,
  and troubleshooting deliverables explicitly to VS09-B rather than claiming them early.

## 9. Implementation ownership and file boundary

The sole Luna/max implementer may modify only the files named by the approved implementation plan
within these surfaces:

- Toolkit and Monitor version/inventory/doctor/CLI package code and metadata;
- the existing two launchers and one setup helper;
- the existing Claude manifest, eight Skills, and bilingual README;
- focused Toolkit/Monitor tests and current-runtime fixtures needed to prove these contracts; and
- the VS09-A implementation report and this slice's ignored SDD ledger.

It may not change VS08 domain workflows, Project/Probe/Monitor/Test/Diagnostic/Acceptance schemas
or semantics, release controllers, CI, hardware behavior, remote configuration, or VS09-B product
behavior.

## 10. Proportionate evidence and risk triggers

### Implementer-owned slice evidence

1. RED then GREEN tests for missing/duplicate CLI project roots and no-CWD fallback.
2. RED then GREEN Windows launcher tests proving generic variable selection, exact 0.9 path,
   argument/exit forwarding, and no system fallback.
3. RED then GREEN setup tests for generic parameters, CPython 3.12-only discovery, legacy 0.5
   classification, staging/promotion/rollback, and read-only Check.
4. RED then GREEN doctor/version/inventory/package tests proving 0.9.0, Python range, Monitor
   metadata mismatch/absence, the exact 48 actual MCP names, and the exact eight Skills.
5. Focused affected regression for CLI, MCP startup/roots, doctor, plugin layout/runtime setup,
   Monitor package/protocol/runtime, and bilingual documentation contract.
6. One fresh CPython 3.12 wheel/runtime smoke because package/bootstrap/runtime/asset inventory is
   modified. It builds/installs Toolkit plus Monitor into one disposable venv, validates UI assets,
   runs `version`, doctor, generic MCP startup/listing, and Monitor import/CLI version behavior.

### Sol-owned independent review evidence

- inspect the complete full accepted-base-to-returned-head diff in a clean detached worktree;
- rerun only the focused contract matrix and one independent fresh wheel/runtime smoke;
- reconcile actual MCP/Skill inventories, package metadata, report CodeHead, cleanup, branch,
  upstream, and remote state; and
- issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` under repository governance.

### Explicitly excluded verification

No full Python coverage suite, 0600 release controller, full Monitor UI unit/E2E matrix,
performance gate, CubeMX/CubeCLT native generation, Probe/hardware action, security matrix, SBOM,
license audit, archive publication, or remote action runs in VS09-A. Browser behavior and hardware
bytes are unchanged, so no trigger moves those checks forward.

Every run-scoped basetemp, venv, wheelhouse, build output, log, JUnit file, extracted archive, and
review worktree is removed after useful evidence is reconciled. Source-controlled tests, fixtures,
reports, user files, shared caches, and still-needed failure evidence are never removed.

## 11. Acceptance boundary and handoff

VS09-A is accepted only when all four scenarios pass, the exact affected tests and fresh runtime
smoke are green, the complete diff has no unresolved product defect, the implementation report
records the accepted base and product CodeHead before its own report commit, the SDD ledger is
accurate, disposable verification artifacts are cleaned, and the implementation branch is clean
with its local/unpushed/no-upstream/no-remote-mutation state explicit.

Only after Sol records `ACCEPTED` may it reconstruct and freeze the separate VS09-B specification
at the VS09-A accepted final head. Acceptance does not authorize VS10.
