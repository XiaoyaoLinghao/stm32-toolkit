# STM32 Toolkit VS07-A Discovery Boundary Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. The existing single GPT-5.6-luna/max implementer owns all tasks below as sequential checkpoints; do not dispatch another agent.

**Goal:** Replace the non-converged VS07-A discovery boundary with a fail-closed, deterministic and test-proven implementation while preserving the approved public creation-plan interfaces.

**Architecture:** One candidate resolver enforces the frozen tier order and ambiguity semantics. One injected bounded runner owns the only permitted metadata/build-tool processes, while CubeMX and VS Code use static evidence only. CLI discovers per command; MCP freezes one immutable profile at server startup and reuses it for doctor and creation plans.

**Tech Stack:** CPython `>=3.12,<3.13`, dataclasses, pathlib, subprocess, Windows PE/App Paths, FastMCP, argparse, pytest.

## Global Constraints

- Product accepted base is `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`; rewrite input head is `1679dcca5839324b01187075955cfa2dd6efe595`.
- Governing rewrite specification is `docs/superpowers/specs/2026-08-23-stm32-toolkit-0701-discovery-boundary-rewrite-design.md`.
- The same one GPT-5.6-luna/max implementer owns every product/test/report change.
- CubeMX and VS Code must never execute. Only CubeCLT metadata and GCC/CMake/Ninja fixed version commands may execute through the bounded runner.
- Planning writes no project or destination bytes and performs no install, hardware, Git remote, VS07-B, or VS07-C action.
- Python support remains exactly `>=3.12,<3.13`.
- The Sol reviewer will review `d09e2343...final-head` in a new clean detached worktree and run only the approved slice checks.

---

### Task 1: Replace tool discovery as one coherent boundary

**Files:**
- Rewrite: `tools/stm32-toolkit/src/stm32_toolkit/tool_support.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/doctor.py`
- Rewrite/expand: `tools/stm32-toolkit/tests/test_tool_support.py`
- Modify: `tools/stm32-toolkit/tests/test_doctor.py`

**Interfaces:**
- Preserve the approved public dataclasses and `discover_tool_support(SupportProfileRequest) -> ToolSupportProfile`.
- Produce an internal immutable `ProcessObservation(returncode, stdout, stderr, timed_out, truncated)` and an injectable `_run_bounded` seam.
- Split static facts from probed build-tool facts; no generic helper may silently execute a static-only component.

- [ ] Write RED tests for fail-closed profile content/containment, exact tier order, same-tier ambiguity, Windows registered VS Code without PATH, redirect/non-file candidates, metadata success/timeout/nonzero/oversize/malformed/redirect, native version success/unsupported/nonzero/timeout, and a runner spy proving no CubeMX/VS Code argv.
- [ ] Run `py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py -q` and record the expected failures against `1679dcca...`.
- [ ] Replace the mixed discovery helpers with the spec's candidate resolver, fail-closed profile loader, bounded runner, metadata parser, static fact builder, probed build fact builder, normalized version parser, and closed issues.
- [ ] Re-run the same command; require exit 0, no skip/xfail, legacy doctor keys unchanged, and `creationSupport` sourced from the supplied/frozen support object when present.
- [ ] Commit the coherent rewrite with `git commit -m "fix(project): rewrite creation environment discovery"`.

### Task 2: Close creation-path and runtime adapter contracts

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/generation/creation.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/creation_workflows.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_plan.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_workflows.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_cli.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_mcp.py`
- Modify when needed: `tools/stm32-toolkit/tests/test_mcp_server.py`, `tools/stm32-toolkit/tests/test_mcp_roots.py`

**Interfaces:**
- Keep `CreationPlanWorkflowRequest` exactly as approved; pass frozen support as `plan_creation_workflow(request, *, support_profile: ToolSupportProfile | None = None)`.
- Make `ServerRuntime.support_profile` non-optional for runtimes created by `ServerRuntime.create`; reuse it for MCP doctor and create-plan.
- Keep MCP schema exactly `{sourceKind, source, destination, framework, language}`.

- [ ] Write RED tests for `.ioc` suffix/oversize/invalid UTF-8/unreadable and source/destination redirect parents; absent/empty/populated inventory and digest changes; all three source kinds; duplicate CLI options; closed environment errors; MCP roots; runtime freeze across repeated calls; and normalized CLI/MCP parity under a fixed clock/profile.
- [ ] Run the four creation test files plus `test_generation.py`, `test_cli.py`, `test_mcp_server.py`, and `test_mcp_roots.py`; record failures against the rewrite Task 1 head.
- [ ] Implement component-safe path validation and inventory state, keyword-only support injection, fixed-clock test seam, duplicate CLI rejection, and shared frozen MCP doctor/create-plan facts without adding caller overrides.
- [ ] Re-run the same affected command and require exit 0 with no new skip/xfail and zero destination mutation.
- [ ] Commit with `git commit -m "fix(project): close creation planning contracts"`.

### Task 3: Reconcile evidence and return the replacement candidate

**Files:**
- Modify: `docs/codex/returns/STM32TK-0701-CREATION-PLAN/implementation-report.md`
- Modify: `.superpowers/sdd/2026-08-22-stm32-toolkit-0701-creation-plan-environment-truth/progress.md`

- [ ] Run the exact complete VS07-A slice command from the original detailed plan with this worktree's `src` first on `PYTHONPATH`; require exit 0 and record exact counts/warnings/skip/xfail.
- [ ] In a disposable workspace, snapshot relative names, sizes, and content hashes; run doctor and one MCU create-plan; snapshot again and require equality. Record native metadata/tool facts, CubeMX static PE fact, blockers, and `mutated=false` without running CubeMX.
- [ ] Run `git diff --check d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58..HEAD`, inspect the full stat/status, and confirm no out-of-scope product path.
- [ ] Update the report with the rewrite verdict history, the code head before the report commit, exact evidence, local clean/unpushed state, and separate blocker classes. Do not include the report commit's own SHA or moving commit totals.
- [ ] Commit only report/ledger changes with `git commit -m "docs(project): record VS07-A discovery rewrite"` and return the clean local HEAD for a new Sol review.

## Recovery execution order

The replacement candidate failed independent review. Execute Task 1R, then
Task 2R, then repeat Task 3 against the new code head.

### Task 1R: Replace the optional-fact helper chain with the frozen resolver

This is an interface-level recovery checkpoint after the replacement review,
not another local patch round. Complete it before repeating Task 3. The same
single Luna/max implementer owns the entire checkpoint.

**Files:**
- Rewrite as needed: `tools/stm32-toolkit/src/stm32_toolkit/tool_support.py`
- Expand: `tools/stm32-toolkit/tests/test_tool_support.py`
- Expand only for public propagation: `tools/stm32-toolkit/tests/test_doctor.py`
- Reconcile after GREEN: `docs/codex/returns/STM32TK-0701-CREATION-PLAN/implementation-report.md`
- Reconcile after GREEN: `.superpowers/sdd/2026-08-22-stm32-toolkit-0701-creation-plan-environment-truth/progress.md`

**Required internal interface:** use the exact candidate/tier/resolution states
and `_resolve_component(component, tiers, evidence_builder)` transition table
from section 7 of the governing rewrite design. Do not retain any
`explicit_fact(...) or metadata_fact(...) or path_fact(...)` selector.

- [ ] Add `test_invalid_explicit_candidate_is_fail_closed` using a valid profile
  object whose configured executable is absent; assert `SupportProfileError`
  and a PATH candidate spy remains unused. Run this single test against
  `53bfca30` and require a behavioral failure before product changes.
- [ ] Add `test_invalid_metadata_candidate_does_not_fall_back_to_path`; supply
  successful native metadata JSON containing an outside-root tool path, expose
  a valid PATH tool, and assert the closed metadata/tool issue with no PATH
  selection. Run it against `53bfca30` and require failure.
- [ ] Add table-driven `test_candidate_tier_priority` cases proving explicit,
  metadata, registered/standard and PATH selection when every higher tier is
  truly empty. Each expected source is a hand-written literal.
- [ ] Add `test_path_tier_rejects_two_distinct_candidates` with two PATH
  directories containing distinct safe executables; assert the exact
  `<COMPONENT>_AMBIGUOUS` issue and no arbitrary fact. Run it against
  `53bfca30` and require failure.
- [ ] Add `test_candidate_aliases_to_same_file_are_deduplicated` covering a
  registered plus standard spelling alias to one canonical file; assert one
  selected fact rather than ambiguity. Run it against `53bfca30` and require
  failure.
- [ ] Add `test_vscode_hkcu_registration_survives_missing_hklm` with independent
  fake registry hive behavior and no PATH candidate; assert the HKCU static
  fact. Run it against `53bfca30` and require failure.
- [ ] Add parameterized static-tool tests for CubeMX and VS Code proving the
  injected runner receives no argv for supported, missing-version and wrong-
  version PE evidence.
- [ ] Add metadata/native runner tests that exercise the real parser through
  `_run_bounded`: success, timeout, nonzero, truncated/oversize, invalid UTF-8,
  malformed JSON, redirected output path, non-file path, native wrong version,
  and native timeout. Each test asserts the public fact/issue outcome, not only
  mock calls.
- [ ] Implement `DiscoveryCandidate`, `CandidateTier`,
  `CandidateResolution`, the one resolver, all-candidate PATH enumeration,
  independent HKLM/HKCU collection, canonical deduplication, and separate
  static/probed evidence builders. Delete the optional-fact fallback chain.
- [ ] Run every new test individually or in logically grouped RED/GREEN cycles,
  recording the expected RED reason and later GREEN result in the SDD ledger.
- [ ] Run `py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py -q`; require exit 0 and no skip/xfail.

### Task 2R: Prove every remaining VS07-A public negative path

Complete this checkpoint after Task 1R without changing the frozen public
request or response schemas.

**Files:**
- Expand: `tools/stm32-toolkit/tests/test_creation_plan.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_workflows.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_cli.py`
- Expand: `tools/stm32-toolkit/tests/test_creation_mcp.py`
- Expand when required: `tools/stm32-toolkit/tests/test_mcp_server.py`
- Expand when required: `tools/stm32-toolkit/tests/test_mcp_roots.py`
- Modify product adapters only when a new RED test proves a public defect.

- [ ] Add literal-outcome tests for `.ioc` oversize, invalid UTF-8, unreadable
  file, source redirect parent, destination redirect parent, absent/empty/
  populated inventory and digest changes, all three source kinds, and sorted
  propagation of every non-VS-Code support issue into plan blockers.
- [ ] Add CLI tests proving each repeated scalar option is rejected and that
  invalid source/environment errors remain closed JSON without exception or
  host-path leakage.
- [ ] Add MCP tests creating one real `ServerRuntime`, calling doctor and
  create-plan repeatedly after ambient discovery inputs change, and asserting
  the original immutable support profile is reused. Also prove client-root
  enforcement and the exact five-field MCP input schema.
- [ ] Add fixed-clock/fixed-profile CLI and MCP parity tests comparing normalized
  public creation-plan data with hand-checked literals; do not compute expected
  values through the production serializer under test.
- [ ] For every product defect exposed by these RED tests, make the minimum
  coherent implementation change, then rerun the focused test to GREEN.
- [ ] Run the affected Task 2 command from this plan, then the exact complete
  VS07-A slice command from the original detailed plan. Require exit 0, no
  skip/xfail and no destination mutation.
- [ ] Update the implementation report and SDD ledger to distinguish the prior
  failed candidate from the returned code head. Remove claims not directly
  supported by named tests or real observation, commit product/tests first and
  report/ledger second, and return a clean local HEAD without remote action.
