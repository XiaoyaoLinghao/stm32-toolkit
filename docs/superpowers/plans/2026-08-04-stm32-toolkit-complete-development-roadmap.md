# STM32 Toolkit Complete Development Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the installed 0.2.0 foundation into a 1.0.0 Toolkit that completes one real Keil-to-GCC migration and gives Claude Code a safe, observable coding/build/test/flash/debug/monitor loop.

**Architecture:** Keep Skills thin and deterministic behavior in the versioned CLI/MCP core. A loopback-only Probe Service owns PyOCD and arbitrates MCP, Monitor, tests, flash, and Cortex-Debug; project facts stay in the repository while runtime state remains isolated below `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>`.

**Tech Stack:** Python 3.10+, jsonschema, MCP SDK, PyOCD, pyelftools, cmsis-svd, aiohttp, CMake 3.22+, Ninja, ARM GNU Toolchain, Unity/CMock, TypeScript, Vite, ECharts, Vitest, Playwright, STM32CubeMX 6.18+ CLI.

## Global Constraints

- Preserve the Toolkit form: one Claude Code user-scope plugin; no cloud service, external database, Codex-only dependency, or copied project Skills.
- Migrate the current real Keil project only. Do not build batch migration or prewrite compatibility for every STM32 family.
- Keil-to-GCC is one-way; never write `.uvprojx`, synchronize two build systems, or combine compiler migration with SPL/HAL conversion.
- Inspect/plan/dry-run are read-only. Writes require a recoverable Git baseline and digest-checked apply plan.
- Observation is non-halting by default. Halt/step/reset/flash/tests require the approved operation level; no Option Bytes, arbitrary writes, chip erase, or lease stealing.
- One physical probe has one owner. Never kill unrelated PyOCD processes; return owner evidence on conflicts.
- Monitor binds `127.0.0.1`, uses a dynamic port and random token, stores user-created groups per workspace, and ships no named presets.
- Every evidence artifact records Git commit, ELF SHA-256, build preset, target, Toolkit version, and timestamps.
- Support the current and immediately previous project schema; upgrade only through explicit dry-run/apply.
- Never overwrite drifted user files; generate a diff and require new authorization.
- Plugin, CLI, Probe Service, Monitor, Skills, and protocols share one SemVer; bump it for each GitHub release.
- Python branch coverage remains at least 90%; Monitor has browser tests; skipped hardware tests cannot satisfy release gates.

## Release Sequence

| Release | Detailed plan | Mandatory exit condition |
|---|---|---|
| 0.3.0 | `2026-08-04-stm32-toolkit-0.3-project-migration-build.md` | Schema v2, Keil inspect/convert, deterministic GCC/VS Code generation, build and firmware identity |
| 0.4.0 | `2026-08-04-stm32-toolkit-0.4-probe-debug.md` | Probe leases/service, safe flash, Cortex-Debug handoff, typed variable/register/Fault evidence |
| 0.5.0–0.6.0 | `2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md` | Rebuilt Monitor, host/target tests, persistent evidence-backed AI diagnosis |
| 0.7.0–1.0.0 | `2026-08-04-stm32-toolkit-0.7-1.0-creation-acceptance.md` | CubeMX new-project creation and real-board vertical acceptance |

## Progress Tracking

- [x] 0.3.0 migration, managed GCC/CMake configuration, and reproducible build gate
- [ ] 0.4.0 Probe Service, leases, flash, typed reads, and debug handoff gate
- [ ] 0.5.0 project-isolated monitor service and UI gate
- [ ] 0.6.0 host/target tests and evidence-driven AI diagnostics gate
- [ ] 0.7.0 CubeMX-backed project creation gate
- [ ] 1.0.0 non-skippable real-hardware vertical acceptance gate

Implementation commits must update the detailed task checkbox in the corresponding phase plan. A release checkbox above is checked only in the same commit that records all exit-gate evidence; partial work remains visible as unchecked steps rather than being summarized as complete.

## Dependency Flow

```text
0.2 foundation
  → project schema/model
  → Keil inspect/convert
  → generated CMake/VS Code
  → reproducible build + firmware identity
  → Probe Service + leases
  → flash/debug/read/sample/Fault
  → Monitor backend/UI
  → host/target tests
  → diagnostic evidence loop
  → CubeMX new-project creation
  → real Keil project + target-board 1.0 acceptance
```

## Stable Cross-Plan Interfaces

- `load_project_model(project_root: Path) -> ProjectModel`
- `plan_keil_conversion(project_root: Path, inspection: KeilInspection) -> MigrationPlan`
- `plan_project_configuration(model: ProjectModel) -> GenerationPlan`
- `run_build(request: BuildRequest) -> OperationResult[BuildReport]`
- `ProbeLeaseManager.acquire(probe_id, workspace_id, session_id, operation_level) -> ProbeLease`
- `ProbeClient` uses a versioned loopback protocol and token.
- `DwarfCatalog.lookup(expression) -> TypedLocation`; `decode(location, bytes) -> TypedValue`.
- `MonitorRuntime.start(config: MonitorConfig) -> MonitorEndpoint`.
- `run_host_tests(HostTestRequest) -> OperationResult[TestReport]`.
- `run_target_tests(TargetTestRequest, ProbeClient) -> OperationResult[TestReport]`.
- `DiagnosticStore` persists hypotheses, evidence, actions, conclusion, and fix verification.
- `plan_project_creation(request: ProjectCreateRequest) -> ProjectCreationPlan`.

## Requirement Traceability

| Approved requirement | Owning plan/task |
|---|---|
| One-time, read-only-input Keil→GCC migration | 0.3 Tasks 2–3 |
| VS Code/GCC configuration and selected extensions | 0.3 Task 4; 0.7 Task 3 |
| Build identity and reproducibility | 0.3 Task 5 |
| Safe probe ownership, flashing, reads, registers, Fault evidence | 0.4 Tasks 1–3 |
| User-created monitor groups and unchanged monitor capabilities | 0.5–0.6 Tasks 1–2 |
| Host and real-target test execution | 0.5–0.6 Task 3 |
| AI hypotheses, autonomous safe observations, debug control, evidence, and fix verification | 0.5–0.6 Task 4 |
| From-zero CubeMX project creation without a hand-written MCU matrix | 0.7–1.0 Task 1 |
| Per-project data isolation, versioning, GitHub-only installation, and upgrades | all phases; 0.7–1.0 Task 3 |
| Non-skippable real-board vertical proof | 0.7–1.0 Tasks 2 and 4 |
## 1.0.0 Non-Negotiable Acceptance

The real-board command must complete without a skip marker:

```text
Keil inspect/baseline
→ digest-guarded GCC conversion
→ CMake/VS Code generation
→ GCC build and memory/symbol comparison
→ matching-target flash
→ Monitor observation
→ user-reported or reproducible fault
→ ranked hypotheses and evidence collection
→ authorized fix
→ rebuild/reflash
→ target test and Monitor verification
```

The acceptance bundle must contain `inspection.json`, `conversion-report.json`, `build-result.json`, `memory-comparison.json`, `flash-result.json`, `monitor-snapshot.json`, `diagnostic-session.json`, `target-test.json`, and `migration-summary.md`.

## Authoritative Requirements

- `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`
- `requirements/follow-on-skills/migrate-keil/SKILL.md`
- `requirements/follow-on-skills/init-stm32-project/SKILL.md`
- `requirements/follow-on-skills/read-var/SKILL.md`
- `requirements/follow-on-skills/stm32-monitor/SKILL.md`
- Claude plugin structure/versioning: `https://code.claude.com/docs/en/plugins-reference`
- STM32CubeMX CLI: `https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.0/en/docs/markup/CubeMX_CLI.html`
