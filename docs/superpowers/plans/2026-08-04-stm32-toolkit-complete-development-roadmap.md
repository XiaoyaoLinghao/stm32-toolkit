# STM32 Toolkit Complete Development Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the installed 0.2.0 foundation into a 1.0.0 Toolkit that completes one real Keil-to-GCC migration and gives Claude Code a safe, observable coding/build/test/flash/debug/monitor loop.

**Architecture:** Keep Skills thin and deterministic behavior in the versioned CLI/MCP core. A loopback-only Probe Service owns PyOCD and arbitrates MCP, Monitor, tests, flash, and Cortex-Debug; project facts stay in the repository while runtime state remains isolated below `${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>`.

**Tech Stack:** Python 3.10+, jsonschema, MCP SDK, PyOCD, pyelftools, cmsis-svd, aiohttp, CMake 3.22+, Ninja, ARM GNU Toolchain, Unity/CMock, TypeScript, Vite, ECharts, Vitest, Playwright, STM32CubeMX 6.18+ CLI.

## Layered Implementation Boundary

This reconciliation remains a written-plan candidate until the user confirms its exact local
CodeHead. Before that confirmation, frozen CodeHead
`a31f997e0be87f6e14ad85b7cd033b4f4073b62f` remains authoritative and no implementation task may
use this section to change an external product contract or the source/order of Task 8 and later.

Future work is planned by responsibility layer before it is assigned to a release:

| Layer | Ownership | Required implementation rule |
|---|---|---|
| L0 external execution engines | ARM GNU Toolchain; CMake/Ninja/CTest/JUnit; PyOCD; pyserial; pyelftools; STM32CubeMX; CMSIS/CMSIS-Pack; SQLite/aiohttp/Preact/ECharts/Vitest/Playwright | Pin, invoke, bound, parse, and verify the engine; do not reproduce its mature compiler, build, debug, serial, device-generation, storage, HTTP, chart, or browser-test internals. |
| L1 Toolkit kernel | CLI/MCP/Skills, closed schemas and `OperationResult`, project/workspace/session/firmware identity, path/process isolation, authorization, probe lease, Evidence/Test contracts, and controlled adapters | Toolkit remains the sole control plane and public contract owner. External output is untrusted until identity-bound immutable Evidence and verifier acceptance. |
| L2 STM32 domain platform | project/build/ELF/DWARF/SVD, Probe/flash/memory/register/Fault, Host/Target test, four transports, Monitor sampling/history/service | Implement STM32 semantics as narrow adapters over L0 and L1; do not add a second debugger, build system, Monitor, or test lifecycle. |
| L3 product and intelligence | Keil migration, Monitor UI, 0602 diagnostic loop, 0603 analytics/annotations/bundles, 0.7 project creation | Implement only user-visible domain behavior not already supplied by L0/L1/L2. |
| L4 delivery and acceptance | managed runtime/offline package, performance/security/dependency audit, candidate/resume/reconcile/final, browser and physical-hardware acceptance | Reuse one shared 0600 controller, verifier, catalog, and native-output adapter. A gate proves product behavior; it is not another product runtime. |

Completed 0.2--0.5 public behavior and accepted 0601 Tasks 1--7 are compatibility baselines. A
future adapter may be added behind those contracts, but it may not silently migrate an old project,
change an identity or authorization rule, rewrite persisted Monitor/Evidence data, or select another
engine after failure and claim the same operation succeeded.

## Bounded Component Proof-of-Fit

Before coding any not-yet-implemented generic execution capability, its owning task records one
bounded proof-of-fit with all of the following concrete evidence:

- exact version, LICENSE/NOTICE/SBOM identity, and offline installation source;
- the real Windows argv and exit code from the frozen environment;
- a real sanitized native-output fixture plus a closed parser that cross-checks exit, summary, and
  node outcomes while consuming only business-required fields;
- path, credential, network, concurrency, timeout, cancellation, crash, and partial-output tests;
- project/firmware/run identity, authorization, Evidence, and error-code binding;
- measured performance/package-size cost and the specific unimplemented code and maintenance it
  eliminates; and
- the complete affected 0.2--0.5 compatibility regression.

Failure of any proof is a fail-closed rejection of that component, not permission to lower a
product requirement or add a silent fallback. Do not build a provider marketplace, dynamic loader,
parallel controller/runtime/product platform, collaboration integration, CI system, or remote
scheduler as part of this work. Optional remote-lab or simulation providers require their own
later approved proof and can never satisfy a physical-hardware PASS.

### Reconciled component decisions at this plan CodeHead

| Component | Observed/planned version and license | Decision before further coding |
|---|---|---|
| ARM GNU Toolchain | `14.3.1` from STM32CubeCLT 1.22.0; GPL toolchain terms/runtime exceptions must be archived | Adopt existing managed compiler; no compiler implementation. |
| CMake/CTest and Ninja | CMake/CTest `4.3.1` (BSD-3-Clause), Ninja `1.13.2` (Apache-2.0) | Adopt; preserve real CTest native fixtures and the shared strict adapter. |
| PyOCD | `0.45.1`, Apache-2.0 | Adopt as the sole local probe execution engine behind Probe v2. |
| pyserial | `3.5`, BSD | Adopt for the closed UART transport only. |
| pyelftools | `0.33`, public domain | Adopt for ELF/DWARF parsing and verification. |
| SQLite/aiohttp | managed CPython SQLite `3.41.2` (3.10) and `3.49.1` (3.12), public domain; aiohttp `3.12.15`/`3.14.3`, Apache-2.0 AND MIT | Adopt existing Monitor stack; the 0.6 package task must select one frozen offline set per supported interpreter. |
| Preact/ECharts/Vitest/Playwright | `10.29.8` MIT / `6.1.0` Apache-2.0 / `4.1.10` MIT / `1.56.1` Apache-2.0 | Adopt the package-lock versions; Chromium only for current Windows scope. |
| STM32CubeMX CLI | planned `6.18`; ST proprietary license; executable and offline source absent from the current host | Pending mandatory 0.7 proof-of-fit; Task 1 remains blocked until PASS. |
| CMSIS-Toolbox/CMSIS-Pack | exact Toolbox version not yet selected; Apache-2.0 upstream; commands absent from the current host | Pending bounded Pack/device/SVD proof; csolution/cbuild/cbridge remain rejected unless a later proof avoids a second project model. |
| Ceedling and pytest-embedded | not pinned | Reject as defaults; reconsider only for a named CMock/DUT fixture that passes a separate proof. |
| Serial Studio, OpenHTF, Zephyr Twister | not pinned | Reject from the product core because each duplicates an existing product/test/Monitor lifecycle. |
| labgrid and Renode | not pinned | Deferred optional providers; neither is a local 1.0 prerequisite and simulation never counts as physical PASS. |

The license labels above are planning identities, not a substitute for the exact LICENSE/NOTICE/
SBOM and offline-source evidence required by the owning package or proof task.

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
| 0.5.0 | `../specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md` | Rebuilt project-isolated Monitor service and offline UI; unified 0.5.0 release; zero presets; explicit connect/start |
| 0.6.0 | `../specs/2026-08-14-stm32tk-0600-evidence-diagnostics-program-design.md` | Immutable test evidence, four Target transports, safe diagnostic loop, Monitor analytics, and one frozen final matrix |
| 0.7.0–1.0.0 | `2026-08-04-stm32-toolkit-0.7-1.0-creation-acceptance.md` | CubeMX new-project creation and real-board vertical acceptance |

The 0.6 execution bundle is ordered as
`2026-08-14-stm32tk-0601-test-evidence.md`,
`2026-08-14-stm32tk-0602-diagnostic-loop.md`,
`2026-08-14-stm32tk-0603-monitor-analytics.md`, then
`2026-08-14-stm32tk-0600-release-acceptance.md`.

## Progress Tracking

Codex continuation ownership, packet boundaries, and the detailed first 0.4
execution packet are recorded in
`2026-08-07-stm32-toolkit-codex-continuation.md`.

- [x] 0.3.0 migration, managed GCC/CMake configuration, and reproducible build gate
- [x] 0.4.0 Probe Service, leases, flash, typed reads, and debug handoff gate
- [x] 0.5.0 project-isolated monitor service and UI gate
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
| User-created monitor groups and unchanged monitor capabilities | 0.5 Tasks 1–2 (delivered in 0502) |
| Host/Target test, Evidence, transports, and Probe v2 | STM32TK-0601 Tasks 3--13 |
| AI hypotheses, bounded observations/control, evidence assessment, and fix verification | STM32TK-0602 Tasks 1--12 |
| Cross-run analytics, quality, annotations, bundles, and Monitor UI | STM32TK-0603 Tasks 1--13 |
| Shared candidate/final governance and real-hardware reconciliation | STM32TK-0600 release acceptance |
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
