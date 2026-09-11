# STM32 Toolkit 1.0 VS10-A Legacy Keil Real-Board Closed-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the named read-only STM32F429 Keil project into a reproducible local GCC project, add an honest host-bound Target frame v2 path, and prove the safe D4/PE4 failure-diagnosis-fix loop on the named physical board with exact local evidence.

**Architecture:** Extend the one existing Target runner with a backward-compatible `stm32-target-frame/2` mode whose MCU payload contains only case facts and monotonic time. The existing host runtime binds those bytes to the exact same-run verified flash, project/workspace/session, Probe/target, and host UTC. Keep v1 replay behavior, the single Probe/PyOCD backend, memory-mailbox read-only transport, TestRun/Diagnostic/Evidence stores, CLI/MCP server, and Monitor authority. The real project lives in a separate local no-remote Git repository created from a hashed read-only intake; the Toolkit repository records only product code, focused tests, design/plan, and the final report.

**Tech Stack:** CPython 3.12.10, STM32 Toolkit/Monitor 0.9.0, pytest 8.4.2, JSON Schema 2020-12, CMake 4.3.1, Ninja 1.13.2, CubeCLT GNU Arm Embedded 14.3.1, PyOCD 0.45.1, CMSIS-DAP, STM32F429ZGT6, Keil uVision project input, Cortex-Debug, PowerShell 5+.

## Global Constraints

- Full accepted base is `9b7839bb01f88a9e3d2c13203f38aa0d11647232`; governing specification is `docs/superpowers/specs/2026-08-25-stm32-toolkit-1001-legacy-keil-real-board-closed-loop-design.md` at `56a8c5261cbcdd1dbc0f7be8c380c96dc4e4d0bb`.
- The implementation branch starts from the final plan commit, but every product review covers the complete accepted-base-to-final-head range.
- Exactly one `gpt-5.6-luna` implementation owner with reasoning effort `max` owns all product/project implementation and implementation tests. GPT-5.6-sol independently reviews and accepts the full diff.
- The user pre-approved the specification/plan workflow and all actions inside the named disconnected-load hardware boundary. Every public flash, handoff, Target execute, or source-change operation still consumes its own existing exact pins/authorization.
- Toolkit worktree: `C:\tmp\stm32tk-1001-legacy-hardware-impl`. Campaign root: `C:\tmp\stm32tk-vs10a-legacy-campaign`. Golden source: `D:\workspace\WDS_CODE\test`; never write, format, Git-initialize, build, or clean it.
- Campaign layout is exactly `runtime`, `intake`, `project`, `data`, `evidence`, and `scratch`. The project Git repository has no remote. Formal evidence never lives in either Git repository.
- D4 is LED1 on PE4, active-low. Motors, relays, mechanical loads, charging circuits, 24 V/12 V loads, and unrelated actuators stay disconnected and undriven.
- Do not add a second runtime, MCP registration, Target runtime/controller/provider/backend/store, transport, Agent-specific branch, Python range, CI, collaboration automation, or release machinery.
- Do not push, create/mutate/merge/close a PR, tag, release, or mutate a remote branch. Do not enter VS10-B or VS11.
- v1 public/replay bytes remain accepted unchanged. v2 is explicit in Project schema v3 and uses the same memory-mailbox and Probe backend without target writes.
- Run only the focused protocol/project/runner/public-entry regression plus the gates whose evidence can change in this campaign. No full release, browser, performance, coverage, multi-Python, or multi-platform matrix absent a classified trigger.
- Classify every failure before a product change as PRODUCT, INFRASTRUCTURE, ENVIRONMENT, PLATFORM, HARDWARE, or REPORT. A project defect is not a Toolkit defect.
- After each verification, remove only resolved run-scoped basetemps, scratch, logs, build intermediates, downloaded files, and subprocess state. Keep minimal failing evidence until reconciled, source tests/fixtures, P0-P4 project commits, intake, formal evidence, and user files.

---

## File structure and responsibility map

**Create in the Toolkit repository:**

- `tools/stm32-toolkit/tests/test_target_protocol_v2.py` — v2 canonical case inventory, framing, payload closure, monotonic validation, stream digest, and v1 isolation.
- `tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py` — fake-Probe public workflow proving exact flash/readback, v2 host binding, physical flags, and CLI/MCP parity without claiming hardware PASS.
- `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/implementation-report.md` — accepted base, product CodeHead, project P0-P4, classified evidence, verification, cleanup, and local/remote state.

**Modify Toolkit product contracts:**

- `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json` — optional closed `testing.target.protocol` enum, default semantics retained in the model.
- `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` — `TargetTestConfig.protocol`, v1 default, v2 explicit parsing/serialization behavior.
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json` — version-discriminated closed v1/v2 frame payload definitions; existing TestRun manifest remains version 1.
- `tools/stm32-toolkit/src/stm32_toolkit/testing/protocol.py` — version-aware payload validation and host assembly of v2 monotonic events into the existing TestRun model.
- `tools/stm32-toolkit/src/stm32_toolkit/testing/target.py` — explicit-version decoder, v2 validator/discovery, same-run host binding, authorization fields, and exact raw-event retention.
- `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py` — propagate project protocol and both inventory digests through prepare/execute; no caller-supplied identity.
- `README.md`, `README_zh-CN.md` — concise v1 compatibility/v2 physical-mode and reference-hardware limitation text; MCP tool count/name inventory stays unchanged.

**Modify focused tests only where their public contract changes:**

- `tools/stm32-toolkit/tests/test_project_v3.py`
- `tools/stm32-toolkit/tests/test_project_model.py`
- `tools/stm32-toolkit/tests/test_target_protocol.py`
- `tools/stm32-toolkit/tests/test_target_runner.py`
- `tools/stm32-toolkit/tests/test_testing_workflows.py`
- `tools/stm32-toolkit/tests/test_physical_target_workflows.py`
- `tools/stm32-toolkit/tests/test_cli_hardware.py`
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`
- `tools/stm32-toolkit/tests/test_plugin_layout.py` only if README/inventory assertions require current wording; do not change 48 tool names.

**Create/modify only in the external campaign project Git:**

- `.stm32-project.json` — conversion/configuration authority; P2 adds protocol v2 and mailbox address/size.
- `linker/vs10a.ld` — project-owned native linker with RAM ending at `0x2002EFF0` and a `0x1010` MAILBOX region.
- `USER/VS10/vs10_target.h`, `USER/VS10/vs10_target.c` — v2 frame/CRC/ring emitter and heartbeat case state machine.
- Existing selected user source containing `main` and `TIM3_IRQHandler` — only the minimum P2 poll/tick hooks, P3 held-off line, and P4 authorized restoration.
- No Cube/vendor generated source receives test business logic.

**Create outside both Git repositories:**

- `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\campaign-manifest.json`
- `intake-manifest.json`, `inspection.json`, `conversion.json`, `build-*.json`, `memory-comparison.json`
- `flash-*.json`, `handoff.json`, `typed-observation.json`, `register-observation.json`, `fault-observation.json`, `monitor-observation.json`
- `target-normal.json`, `target-failed.json`, `target-fixed.json`, `diagnostic.json`, `source-authorization.json`
- `campaign-summary.json`, `checksums.sha256`

## Frozen interfaces

- `TARGET_FRAME_V1 = "stm32-target-frame/1"` and
  `TARGET_FRAME_V2 = "stm32-target-frame/2"` are the only accepted protocol names.
- `TargetTestConfig` adds `protocol: str = TARGET_FRAME_V1` after its existing executable,
  timeout, and transport members.
- `calculate_case_inventory_digest(case_ids: Sequence[str]) -> str` implements the single formula
  below; it rejects empty, duplicate, invalid, or over-limit case IDs before hashing.
- The `TargetFrameDecoder` constructor gains keyword `expected_version: int = 1` and binds that
  one explicit header version for its lifetime.
- `validate_event_payload(kind: str, payload: object, *, frame_version: int = 1)` selects one closed
  payload schema without negotiation.

The one-case canonical preimage is exactly:

```json
{"case_ids":["d4-heartbeat"],"mode":"target","protocol":"stm32-target-frame/2"}
```

Its digest is `966a489bdde16562885cc4ac3c3e2b9b9bde0b477f9c06aae25f4916be52c2b5`.

For v2, `TargetFrame.version == 2`; payloads are exactly those frozen in the specification. `monotonic_ms` is an exact integer in `0..9223372036854775807` and never decreases. The host anchors `run_start` to one captured UTC and derives event UTC values from monotonic deltas; deltas beyond the authorized timeout fail. `event_stream_digest` hashes every exact raw frame before `run_end`. The published `EvidenceIdentity` comes only from current host facts after same-run verified flash.

---

### Task 1: Add the Project v3 protocol selector with v1 byte compatibility

- [ ] **Step 1: Create the clean implementation worktree and ledger.** From a clean clone/worktree at the plan head, create branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`, confirm `git merge-base --is-ancestor 9b7839bb01f88a9e3d2c13203f38aa0d11647232 HEAD`, confirm no upstream, and create ignored `.superpowers/sdd/2026-08-25-stm32-toolkit-1001-legacy-keil-real-board-closed-loop/progress.md` with accepted base, spec/plan heads, owner, branch, remote authority `none`, hardware boundary, and current task.

- [ ] **Step 2: Write RED schema/model tests.** Add cases proving an absent `testing.target.protocol` produces v1, explicit v1/v2 load, unknown/case-changed/extra-field values fail closed, v2 survives `to_dict` or equivalent public serialization, and a v1 fixture's canonical bytes are unchanged.

- [ ] **Step 3: Run RED.** Use a fresh external basetemp:

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest tools/stm32-toolkit/tests/test_project_v3.py tools/stm32-toolkit/tests/test_project_model.py -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-vs10a-t1-red
```

Expected: new protocol assertions fail because the field/model member is absent; existing v1 cases collect.

- [ ] **Step 4: Implement the smallest selector.** Update schema/model only. Default v1 in Python, never rewrite an absent JSON field, and keep protocol out of Probe transport options.

- [ ] **Step 5: Run GREEN, clean the basetemps, and commit.** Expected all selected tests pass. Commit `feat(testing): add explicit target frame protocol selector`.

### Task 2: Implement closed v2 framing and host-bound assembly by TDD

- [ ] **Step 1: Write RED protocol tests.** In `test_target_protocol_v2.py`, bind exact bytes for every v2 kind, the one-case digest above, fragmented reads, CRC, oversize, invalid UTF-8, duplicate JSON keys, mixed versions, nonzero flags, sequence gaps, monotonic rollback, timeout delta, inventory/count/state contradictions, and raw stream digest. Add assertions that all current v1 golden bytes/digests and error codes remain unchanged.

- [ ] **Step 2: Run RED.** Run `test_target_protocol_v2.py test_target_protocol.py test_testing_model.py`; expected only new v2 tests fail on absent APIs/version 2 rejection.

- [ ] **Step 3: Implement version discrimination.** Add a `version` member to decoded frames; make `encode_frame`/decoder/payload validation explicit-version with default v1. Implement the closed v2 shapes and `calculate_case_inventory_digest`. Do not loosen v1 validators or accept automatic version negotiation.

- [ ] **Step 4: Implement v2 assembly into existing models.** Add one host-bound assembly path that accepts host `EvidenceIdentity`, host run ID/UTC anchor, target monotonic events, and exact raw artifact; it returns the existing `TestInventory`, `TestCaseResult`, and `TestRunManifest`. Do not add another manifest schema/store/controller. Derive null stdout/stderr and reject target attempts to supply host identity, UTC, artifact refs, or run ID.

- [ ] **Step 5: Run GREEN and commit.** Run the Task 2 RED set plus `test_target_replay.py test_target_replay_publication.py`; clean basetemps. Commit `feat(testing): add host-bound target frame v2`.

### Task 3: Bind v2 discovery, authorization, flash, and publication

- [ ] **Step 1: Write RED runner/workflow tests.** Add v2 cases proving discovery accepts only the first valid inventory frame and records only its exact raw bytes even if the same read has trailing run frames; prepare binds `protocol`, `case_inventory_digest`, and full inventory digest; execute consumes one action, guarded-flashes and readbacks before accepting frames; target/Probe/lease/ELF/build/revision/protocol/inventory drift fail; retry reuses neither authorization nor stale bytes; v1 discovery still requires its historical single inventory behavior.

- [ ] **Step 2: Add physical-publication RED cases.** Using the existing fake Probe v2 boundary, prove v2 success/failure publishes `execution_source=physical` and `physical_transport_evidence=true` only after the production composition path performs program/readback/transport identity. Replay/fake-only helpers must not acquire those flags outside that seam.

- [ ] **Step 3: Run RED.** Run `test_target_runner.py test_testing_workflows.py test_physical_target_workflows.py`; expected the new protocol binding fields/path fail while v1 passes.

- [ ] **Step 4: Implement the smallest runner/workflow changes.** Carry protocol from the model. For v2 discovery, decode to the first complete inventory frame, slice exact first-frame bytes, close immediately, construct host identity/inventory, and retain both digests. For v2 execute, clear stale capture through the existing flash/reset path, verify exact flash/readback and identities, then decode/validate/assemble. Keep authorization records closed and versioned: legacy v1 records preserve their accepted shape; new v2 records require both added bindings.

- [ ] **Step 5: Run GREEN and commit.** Run Task 3 tests plus `test_target_transports.py test_probe_service.py test_probe_protocol_v2.py test_testing_publication.py`; clean basetemps. Commit `feat(testing): bind target v2 to verified physical runs`.

### Task 4: Prove unchanged CLI/MCP entry points and document v2

- [ ] **Step 1: Write RED public scenario tests.** `test_vs10a_target_v2_public.py` must drive the existing CLI prepare/execute and the existing MCP tools against equivalent isolated fake sessions, assert identical operation/code/data semantics and the same v2 protocol/full identity/case digest, assert MCP inventory remains exactly 48 names, and assert neither caller can inject identity/ELF/target/address beyond the project/probe contract.

- [ ] **Step 2: Run RED.** Run the new scenario with `test_cli_hardware.py test_mcp_hardware.py test_mcp_server.py test_mcp_roots.py`; expected only new v2 parity assertions fail if propagation is incomplete.

- [ ] **Step 3: Add only required adapter propagation.** Prefer no CLI/MCP signature change: both tools read `testing.target.protocol` from the explicit project root. Update English/Chinese README with v1 replay compatibility, v2 physical host binding, the single reference `memory-mailbox`, and RTT/UART/semihosting as not physically qualified. Do not add a tool or Skill.

- [ ] **Step 4: Run GREEN and focused software integration.** Run Tasks 1-4 test files together with `test_plugin_layout.py`, `git diff --check`, and a placeholder scan:

```powershell
rg -n "TODO|TBD|PLACEHOLDER|<insert|待补" tools/stm32-toolkit/src tools/stm32-toolkit/tests/test_target_protocol_v2.py tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py README.md README_zh-CN.md
```

Expected: tests pass; scan has no instructional residue in changed lines. Commit `test(vs10a): close target v2 public workflow`.

### Task 5: Create the immutable intake and P0 project baseline

- [ ] **Step 1: Reconfirm H0 before any hardware session.** Verify Toolkit head/worktree, CPython/CubeCLT/GCC/CMake/Ninja/PyOCD versions and resolved executable paths, candidate runtime hashes, remote `master` SHA, golden exact path, named Probe passive inventory, and disconnected loads. Record results in campaign manifest; no flash/attach yet.

- [ ] **Step 2: Create campaign directories with resolved absolute paths.** Abort if `C:\tmp\stm32tk-vs10a-legacy-campaign` exists with unrecognized content. Create the six frozen children, then hash/copy the golden tree without following reparse points. Require 529 files, 53 directories, 83,846,939 bytes and the frozen key hashes; rehash intake to exact equality. Set intake files read-only.

- [ ] **Step 3: Create project from intake, local Git only.** Copy intake bytes to `project`, clear read-only only in this copy, `git init -b master`, configure a local identity if needed, verify `git remote -v` is empty, commit every intake byte as P0, and record the full SHA/tree hash. Historical AXF/HEX/MAP/log remain baseline inputs only.

- [ ] **Step 4: RED the absent Toolkit migration.** From the exact 0.9 candidate runtime and explicit project/data roots, run context/inspect prerequisites and record that `.stm32-project.json` is absent before conversion. This expected failure is PROJECT-STATE RED, not a product defect.

### Task 6: Produce P1 with guarded conversion/configuration and prove the GCC image

- [ ] **Step 1: Run exact inspect and conversion TDD cycle.** Invoke public `keil inspect` for `Project/LWIP.uvprojx`, `Target 1`; save the JSON. Run convert dry-run, capture plan ID/input digests/diff, then apply that exact unchanged plan with its public authorization. Commit the conversion result only after `git diff --check` and source ownership review.

- [ ] **Step 2: Configure by the same guarded cycle.** Run project configure dry-run/apply with the exact plan ID. Verify managed files inventory, no guessed second startup, and no Keil output used as build input.

- [ ] **Step 3: Build twice without source changes.** Run public `build --preset arm-debug` twice. Require identical `inputSnapshotSha256`, `buildId`, ELF SHA, MAP SHA, entry/vector/reset facts; classify timestamp/non-determinism rather than editing around it.

- [ ] **Step 4: Create memory comparison and H1 evidence.** Compare historical Keil MAP/AXF facts to GCC MAP/ELF: FLASH/RAM regions, code/RO/RW/ZI, vector, SP, Thumb reset, `main`, `TIM3_IRQHandler`, `testtime`, unresolved strong symbols, and top SRAM1 interval. Require `0x2002EFF0..0x20030000` entirely free before reserving it.

- [ ] **Step 5: Handle `testtime` only if evidence triggers P1c.** First retain original non-volatile declaration. If GCC/DWARF/physical smoke proves optimization makes ISR/main observation stale, obtain the existing Toolkit exact source-change digest for only the declaration and change it to `volatile`; commit P1c and repeat all H1 checks. Otherwise record P1c `NOT_TRIGGERED` and do not edit it.

### Task 7: Safely flash P1/P1c and prove the uninstrumented board path

- [ ] **Step 1: Prepare exact current flash pins.** Re-read fresh firmware identity, current clean project Git, target `stm32f429zgtx`, Probe hash, data root/session, and successful build evidence. Any mismatch stops H2.

- [ ] **Step 2: Execute one public flash and readback.** Consume `--authorized` only with current expected build ID/ELF SHA/Probe. Require every programmed segment readback and exact target identity. Do not flash the golden Keil output.

- [ ] **Step 3: Collect independent observations.** Record the user's D4 approximately one-second toggling observation, bounded typed reads showing `testtime` activity, SVD GPIOE ODR PE4 changes, no active Cortex-M Fault, and one Monitor snapshot with the same firmware/probe/workspace identity.

- [ ] **Step 4: Stop on any mismatch.** Do not add the mailbox until P1/P1c migration is independently proven. Classify and preserve minimal evidence.

### Task 8: RED/GREEN the project-owned v2 mailbox and normal P2 run

- [ ] **Step 1: Create a project RED before the emitter.** Add protocol v2, exact mailbox address `0x2002EFF0` and ring size `4096` to a guarded manifest candidate and reserve the native linker region, but before adding the emitter run the focused project build/Target discovery expectation. Build must prove `.stm32tk_mailbox` is absent or discovery returns `TEST_TRANSPORT_UNAVAILABLE`; record RED without claiming physical PASS.

- [ ] **Step 2: Implement the project-owned linker and emitter.** Copy the managed linker to `linker/vs10a.ld`, set ordinary RAM length `0x2EFF0`, define `MAILBOX` origin `0x2002EFF0` length `0x1010`, and place one `NOLOAD`, 16-byte-aligned, `KEEP`ed `.stm32tk_mailbox` there with an `ASSERT` of exact size. Configure `generation.nativeLinkerScript` and rerun guarded configure.

The C storage is exactly one 4112-byte object:

```c
typedef struct {
    volatile uint64_t producer;
    volatile uint64_t consumer;
    uint8_t ring[4096];
} vs10_mailbox_t;

__attribute__((section(".stm32tk_mailbox"), used, aligned(16)))
static vs10_mailbox_t g_vs10_mailbox;
```

Initialize it at boot, never accept target input, and write bounded frames only while total unread bytes stay at most 4096. Use CRC-32/ISO-HDLC and canonical JSON key order. `vs10_target_tick_10ms()` advances a 64-bit monotonic counter from the existing TIM3 ISR; `vs10_target_poll()` in the main loop emits inventory first, observes at least two heartbeat epochs over at least 2200 ms, and emits a complete passed/failed run. Normal requires timer progress and at least one PE4 transition; P3 will preserve timer progress but produce no PE4 transition.

- [ ] **Step 3: Build P2 and prove bytes before hardware.** Require section address/size, RAM non-overlap, symbol ownership, frame fixture decoded by the Toolkit v2 decoder, one-case digest exact match, and no target write API. Commit P2.

- [ ] **Step 4: Run public prepare/execute.** Discovery reads the P2 inventory prefix. Prepare records both digests and exact pins. Execute consumes the action, reflashes/readbacks P2, captures the reset run, and publishes a physical passed TestRun. Correlate D4, typed `testtime`, PE4 ODR, and Monitor PASS.

### Task 9: Prove Cortex-Debug handoff and CLI/MCP parity on P2

- [x] **Step 1: Begin the existing public handoff with exact P2 pins.** Record ticket/owner state. Open VS Code/Cortex-Debug through the generated configuration, attach to the current ELF, observe `testtime` or halted state, and detach normally. Do not kill or steal a competing owner.

- [x] **Step 2: Finish handoff and reacquire.** Consume the matching handoff completion, require Toolkit reacquisition, and repeat a typed read. Record no stale external owner/session.

- [x] **Step 3: Invoke one equivalent observation through the other public entry.** If the first observation used CLI, use MCP now (or vice versa). Require the same project/workspace/session/build/ELF/probe/variable value semantics and existing envelope; caller supplies no derived identity.

Acceptance 2026-09-11: generated IDE/handoff slice independently accepted at source e88c012b; Step 2 reuses attempt 09 end/reacquire then CLI testtime=10; Step 3 reuses 814b1683 CLI/MCP parity. This is explicit unchanged-behavior evidence reuse, not one new DataRoot run. See [T9 evidence mapping](../../codex/returns/2026-09-11-stm32tk-t9-generated-ide-delivery.md). Task7/T10/VS10-A remain incomplete.

### Task 10: Produce P3 failure, evidence-driven diagnosis, and authorized P4 fix

- [ ] **Step 1: Create only the P3 defect.** Change the heartbeat branch from `LED1=!LED1` to `LED1=1`, retain timer/test instrumentation, commit P3, rebuild, and prove only the intended source behavior plus expected build/ELF identity changed.

- [ ] **Step 2: Execute a fresh Target action.** Never reuse P2 authorization. Flash/readback P3 and require D4 off, `testtime`/monotonic timer alive, PE4 high, Monitor agreement, and a physical failed `d4-heartbeat` TestRun.

- [ ] **Step 3: Run the existing diagnostic workflow.** Start from the failed TestRun. Add and assess, in evidence order, timer/interrupt stopped, GPIO/board path failed, and application continuously writes high. Bind typed/DWARF, SVD, source diff, schematic D4/R13/VCC3.3 active-low facts, Monitor, and TestRun. Conclude only when evidence supports the application logic defect.

- [ ] **Step 4: Generate the exact source-change authorization.** Declare only the P3-to-P4 restoration, checkpoint the correct acceptance attempt, and consume the single-use authorization for that exact diff. Reject an altered file/digest as a focused negative check without touching hardware.

- [ ] **Step 5: Restore toggle as P4, rebuild, and reflash with fresh pins.** Commit P4, require new build ID/ELF SHA, run a new Target prepare/execute, and collect D4/typed/SVD/Monitor plus physical passed TestRun.

- [ ] **Step 6: Complete diagnostic verification.** Bind failed-before P3 and fixed-after P4, exact project/workspace/session/probe/target lineage, revisions, states, and source authorization. Do not create or relabel a VS08 AcceptanceRecord.

### Task 11: Reconcile evidence, report, and implementation return

- [ ] **Step 1: Build the formal campaign bundle.** Use canonical JSON without secrets or absolute golden contents. Include all frozen artifacts, tool/source/project/firmware identities, authorizations, commands/result codes, physical flags, classifications, user D4 observations as corroboration only, and a deterministic sorted SHA-256 manifest.

- [ ] **Step 2: Run only the final affected software matrix.** Re-run Tasks 1-4 focused tests if product bytes changed since their last PASS, plus `git diff --check`. Do not rerun hardware stages whose relevant product/project bytes and bindings have not changed; cite still-valid evidence.

- [ ] **Step 3: Write the tracked implementation report.** Record accepted base, spec/plan commits, one Luna/max owner, Toolkit CodeHead before report commit, P0-P4 full SHAs, commands/outcomes, product/project/environment/hardware classification, evidence bundle digest, cleanup, Toolkit/project worktree status, no project remote, and remote `master` SHA. Do not include the report commit's own SHA or moving commit totals.

- [ ] **Step 4: Self-review the full range.** Inspect `git diff --stat` and every line in `9b7839bb01f88a9e3d2c13203f38aa0d11647232..HEAD`; map every spec clause to code/test/evidence, scan placeholders/secrets/absolute user paths, verify v1 fixtures unchanged, ensure no Agent/second-runtime/backend/tool inventory expansion, and correct only implementation-owner findings.

- [ ] **Step 5: Clean and return.** Stop Probe/Monitor/Cortex-Debug subprocesses normally. Resolve and delete disposable basetemps/scratch/build intermediates only after evidence reconciliation. Require clean Toolkit implementation and project worktrees, empty project remotes, no Toolkit upstream/push, and explicit remote `master` state. Commit the report, update ignored SDD ledger, and return the final local head plus evidence bundle digest to Sol for independent review.

### Task 12: Independent Sol review and acceptance gate

This task is owned by GPT-5.6-sol, not by the Luna implementation owner.

- [ ] Create a separate clean review worktree at the returned head and reconstruct tracked/untracked, committed/uncommitted, pushed/unpushed, project/evidence, owner, hardware, and remote state.
- [ ] Resolve the returned full local head from Git and review every line from `9b7839bb01f88a9e3d2c13203f38aa0d11647232` through that head, including specifications, plan, product/tests, README, and report. Confirm the self-reference/discovery issue is genuinely closed and v1 is unchanged.
- [ ] Re-run only focused checks whose evidence needs independent confirmation; reconcile physical evidence without relabeling another actor's observation as Sol-run hardware PASS.
- [ ] Issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` with path/behavior/evidence/command for every finding. Any correction returns to the same Luna/max owner; Sol does not implement product code.
- [ ] On `ACCEPTED`, confirm both worktrees clean, disposable artifacts cleaned, local unpushed head and remote `master` explicit, update the report/SDD only through the implementation owner if inaccurate, and stop. Do not start VS10-B automatically.

---

## Risk-triggered verification table

| Trigger | Added check | Owner/environment |
|---|---|---|
| Project schema/model bytes changed | project v3/model/current fixtures | Luna then Sol; CPython 3.12 |
| v2 framing/runner bytes changed | protocol, runner, workflow, publication, v1 replay regression | Luna then Sol; CPython 3.12/fake Probe |
| CLI/MCP adapter bytes changed | CLI/MCP hardware and 48-tool inventory parity | Luna then Sol; CPython 3.12 |
| Mailbox/linker/project source changed | fresh MAP/ELF section/range/symbol/frame proof | Luna; ARM GCC 14.3.1 |
| Flashable ELF/project revision changed | new public authorization, flash/readback, affected physical observation | Luna; named board/Probe |
| P3/P4 changed | new Target action and diagnostic lineage | Luna; named board/Probe |
| Monitor product bytes unchanged | no Monitor full suite; one campaign identity/observation path only | Luna; installed 0.9 candidate |
| Packaging/release bytes unchanged | no release matrix/artifact rebuild | none |

## Stop conditions

Stop without improvising if golden/intake hashes differ, loads are connected, Probe/target identity changes, MAP cannot prove the reserved range, vector/entry/stack is unsafe, flash/readback differs, another owner holds the Probe, v2 requires a target write, a Toolkit defect falls outside the frozen v2 correction, or a second review round does not converge. Preserve minimum evidence, classify the blocker, and do not enter VS10-B, release, or any remote operation.
