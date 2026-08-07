# STM32 Toolkit Codex Continuation Plan (0.4.0 to 1.0.0)

> **Execution owner:** Codex. OpenClaw coordination is paused by the user as of
> 2026-08-07. Use `test-driven-development`, `systematic-debugging`, and
> `verification-before-completion` for every implementation packet.

**Goal:** Continue from the accepted 0.3.0 release baseline to a safe,
observable, evidence-backed STM32 hardware development loop and ultimately a
non-skippable 1.0.0 real-board acceptance.

**Accepted starting point:**
`f2d0b0c875779a680cad86f02f9a58f8fd07e1a9` (`master`, merged PR #7,
`STM32TK-0306-CLI-MCP-RELEASE` verdict `ACCEPTED_WITH_FIXES`).

**Architecture:** Keep Skills thin. Versioned Python CLI/MCP code owns
deterministic behavior. A loopback-only Probe Service is the sole PyOCD owner;
all later flash, debug, monitor, and target-test functions use its authenticated
client and global lease registry. Project facts remain in Git while mutable
runtime state is isolated below `${CLAUDE_PLUGIN_DATA}`.

**Primary references:**

- `docs/superpowers/specs/2026-07-29-stm32-toolkit-ai-development-design.md`
- `docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md`
- `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.4-probe-debug.md`
- `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md`
- `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.7-1.0-creation-acceptance.md`

## 1. Ownership and delivery rules

- Codex owns architecture, implementation, tests, review, reports, pushes, PR
  state, and ordinary merges for the continuation work.
- Do not dispatch new work to OpenClaw unless the user explicitly resumes that
  collaboration.
- Each implementation packet starts from the current remote `master` full SHA
  in an isolated worktree on `codex/<MODULE-ID>`.
- Each packet uses RED -> minimal GREEN -> refactor -> focused gates -> full
  gates -> platform/real-tool gates -> report-only final commit.
- Never combine unrelated release packets in one branch. Correct review findings
  on the same branch and PR unless architecture requires replacement.
- Preserve the user's remote branches. Do not delete them without a new explicit
  request.
- Reports record accepted base and code head before the report commit; the final
  SHA remains in PR metadata and the return message.

## 2. Global non-negotiable gates

Every packet must satisfy the gates applicable to its surface:

1. Exact accepted-base ancestry and clean accepted-base-to-head inventory.
2. Python branch coverage at least 90%; no new skip/xfail used to hide an
   implementable software failure.
3. `compileall`, `git diff --check`, package-data byte identity, and clean
   external wheel installation.
4. Windows NTFS plus Linux behavior for paths, locks, cancellation, process
   trees, and atomic replacement.
5. Read-only operations preserve bytes, names, modes, mtimes, and Git porcelain.
6. Mutating operations require an exact boolean authorization, current plan or
   identity, recoverable Git state, and rollback evidence.
7. No shell command strings, wildcard process termination, arbitrary memory
   writes, Option Bytes, chip erase, lease stealing, token logging, or external
   network/runtime CDN.
8. All evidence links Toolkit version, Git HEAD, project/workspace/session,
   target/probe, firmware build ID, ELF hash, operation level, timestamps, and
   outcome.
9. A fake backend can prove deterministic behavior but cannot satisfy a named
   real-tool or real-hardware release gate.
10. Version changes happen only in a release-integration packet after all
    component gates pass.

## 3. Delivery sequence

| Order | Module / release | Deliverable | Exit condition |
|---:|---|---|---|
| 1 | `STM32TK-0401-PROBE-CORE` | Protocol/schema, portable global lease registry, loopback service/client, FakeProbe | Two workspaces cannot own one probe; stale-owner recovery is safe; authentication/version/operation-level checks fail closed on Windows and Linux |
| 2 | `STM32TK-0402-PYOCD-BACKEND` | Exact-probe PyOCD adapter, service supervision, attach-only observation | No wildcard selection or unrelated process kill; probe/target ambiguity and partial reads are structured failures; FakeProbe and available real-probe smoke pass |
| 3 | `STM32TK-0403-FLASH-HANDOFF` | Fresh-identity flash plus Cortex-Debug ownership handoff | Stale/wrong-target images never flash; modify authorization is mandatory; one-time handoff restores only the originating workspace |
| 4 | `STM32TK-0404-TYPED-DEBUG` | DWARF types, exact SVD, typed reads/sampling, Fault evidence | Types are never inferred from size; side-effect registers are guarded; samples/faults bind to exact firmware identity |
| 5 | `STM32TK-0405-CLI-MCP-RELEASE` | CLI/MCP/Skills, packaging, doctor, 0.4.0 release reconciliation | Full fake integration, plugin install/upgrade, Windows/Linux gates, and available real-board smoke pass; all 0.4 checkboxes close together |
| 6 | `STM32TK-0501-MONITOR-SERVICE` | Workspace-isolated monitor service/storage/sampler | Empty workspaces have no groups; auth/isolation/retention/lease coordination pass |
| 7 | `STM32TK-0502-MONITOR-UI` | Bundled TypeScript UI, history, exports | Vitest + Playwright pass offline; two projects cannot cross-read groups, samples, or exports; release 0.5.0 |
| 8 | `STM32TK-0601-HOST-TARGET-TEST` | Host CTest and target RTT/UART/semihosting/mailbox runners | Immutable identity-bound artifacts; cancellation releases leases; each documented transport has real-board evidence |
| 9 | `STM32TK-0602-DIAGNOSTICS` | Hypothesis/evidence/action/fix-verification state machine | Fake vertical diagnosis passes; intrusive actions require authorization and complete audit; release 0.6.0 |
| 10 | `STM32TK-0701-CUBEMX-CREATION` | Transactional CubeMX/IOC project creation | Fake and real CubeMX gates pass; generated/user ownership and drift are explicit; release 0.7.0 |
| 11 | `STM32TK-0801-ACCEPTANCE-HARNESS` | Resumable signed vertical harness | Keil migration and new-project fake verticals pass concurrently without state crossover |
| 12 | `STM32TK-0901-RELEASE-HARDENING` | Install/upgrade/security/compatibility/SBOM | Clean Windows profile install and supported upgrades pass; security suite has no release blocker |
| 13 | `STM32TK-1000-REAL-HARDWARE` | Non-skippable 1.0.0 board acceptance | Both real scenarios complete migrate/create -> build -> flash -> observe -> diagnose -> fix -> rebuild/reflash -> target test with archived evidence |

Packets 1-5 are sequential because they share the probe policy and protocol.
Monitor work starts only after the 0.4 protocol is frozen. Target testing starts
after monitor/probe coordination exists. The 1.0 release cannot substitute fake
evidence for hardware evidence.

## 4. Immediate packet: STM32TK-0401-PROBE-CORE

**Branch:** `codex/STM32TK-0401-PROBE-CORE`

**Accepted base:**
`f2d0b0c875779a680cad86f02f9a58f8fd07e1a9`

**Scope:** Software-only probe protocol, models, lease ownership, loopback
service/client, and deterministic FakeProbe. Do not expose flash/debug/monitor
product commands in this packet.

### Task 4.1: Freeze protocol and data contracts

**Files:**

- Create: `schemas/probe-protocol.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/protocol.py`
- Create: `tools/stm32-toolkit/tests/test_probe_protocol.py`
- Modify: `tools/stm32-toolkit/pyproject.toml`

- [x] Write schema/model RED tests for exact protocol and Toolkit version,
  bounded identifiers, enums, timestamps, redacted owner evidence, deterministic
  JSON, unknown fields, and root/packaged schema byte identity.
- [x] Define operation levels `observe`, `control`, and `modify`; a request may
  use only the level granted by the live lease.
- [x] Define stable error codes for bad token, incompatible protocol/version,
  invalid request, probe busy, lease lost, target mismatch, backend unavailable,
  partial read, and internal failure without raw exception leakage.
- [x] Bound request body, read length, batch size, identifier length, and timeout
  before backend execution.
- [x] Run:
  `python -m pytest tools/stm32-toolkit/tests/test_probe_protocol.py -q`.

### Task 4.2: Implement a portable global lease registry

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/lease.py`
- Create: `tools/stm32-toolkit/tests/test_probe_lease.py`

- [x] Write RED tests for exclusive creation, same/different workspace conflict,
  same process with a different start identity, heartbeat expiry, crashed owner,
  live-but-unresponsive owner, forged release, replacement race, truncated lock,
  permission failure, symlink/junction escape, process cancellation, and two
  independent processes racing for the same probe.
- [x] Store registry records only under the canonical
  `${CLAUDE_PLUGIN_DATA}/probe-registry`; reject reparse/symlink redirection and
  non-directory intermediate components before the first write.
- [x] Acquire by atomic exclusive file creation and durable metadata promotion.
  Include schema/protocol/toolkit versions, probe/workspace/session/lease IDs,
  PID, process-start identity, boot identity when available, health endpoint,
  operation level, created time, and heartbeat.
- [x] Treat a live or ambiguously identified process as busy. Reclaim only when
  process identity and authenticated service health both prove the owner dead.
  Never signal or terminate the owner.
- [x] Release only when lease ID and full owner identity match the current
  record. A stale client cannot delete a successor's lease.
- [x] Run the focused suite on Windows, including a real cross-process
  contention test.
- [ ] Run the same real path/lock/cancellation suite on Linux during the unified
  `STM32TK-0405-CLI-MCP-RELEASE` platform gate.

### Task 4.3: Implement backend protocol and FakeProbe

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- Create: `tools/stm32-toolkit/tests/fakes/__init__.py`
- Create: `tools/stm32-toolkit/tests/fakes/fake_probe.py`
- Create: `tools/stm32-toolkit/tests/test_probe_backend.py`

- [x] Define a narrow `ProbeBackend` protocol for enumerate, exact attach,
  bounded memory/register reads, halt/resume/step/reset, verified program, and
  close. Packet 0401 exposes only enumerate/attach/read/close through the
  service.
- [x] FakeProbe must record ordered calls, target state, deterministic memory and
  register values, partial item failures, delays, cancellation, disconnects,
  and reconnects without relying on wall-clock sleeps.
- [x] Write RED/GREEN contract tests that every later backend must pass.

### Task 4.4: Implement authenticated loopback service and client

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- Create: `tools/stm32-toolkit/tests/test_probe_service.py`
- Create: `tools/stm32-toolkit/tests/test_probe_client.py`
- Modify: `tools/stm32-toolkit/pyproject.toml`

- [x] Add the narrowly pinned runtime dependency required for the loopback
  transport; do not add monitor/UI dependencies to the Toolkit package.
- [x] Bind only `127.0.0.1` on port 0. Generate a 32-byte random token, store the
  endpoint/token atomically in the owning session directory with user-only
  access where supported, and never include the token in logs/errors/repr.
- [x] Authenticate token, lease ID, workspace/session, protocol, Toolkit
  version, operation level, content type, body bounds, and loopback peer before
  dispatch. Reject browser cross-origin calls; allow the non-browser client
  without fabricating an Origin header.
- [x] Heartbeat lease and service state independently. Shutdown stops accepting
  work, cancels/awaits bounded in-flight requests, closes the backend, releases
  only its own lease, and removes only its own endpoint record.
- [x] Client deadlines and caller cancellation must propagate without orphaning
  service tasks or converting outer cancellation into an ordinary error.
- [x] Test bad/missing tokens, version skew, stale/replaced lease, wrong
  workspace/session, wrong operation level, non-loopback bind attempt, Host and
  Origin attacks, oversized/slow bodies, partial item failures, shutdown races,
  endpoint tampering, and token redaction.

### Task 4.5: Integrate, package, and verify packet 0401

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/doctor.py`
- Modify: `tools/stm32-toolkit/tests/test_doctor.py`
- Create: `docs/codex/returns/STM32TK-0401-PROBE-CORE/implementation-report.md`

- [x] Add read-only doctor evidence for optional probe-core dependencies and
  registry path safety. Do not start a service or enumerate hardware in doctor.
- [x] Build/install a wheel outside the repository and prove the packaged schema
  and probe modules load from a fresh environment.
- [x] Run focused tests, full pytest with branch coverage >=90%, compileall,
  `git diff --check`, schema byte identity, and placeholder/credential scan.
- [x] Verify a clean worktree after the report commit.
- [x] Run Windows NTFS path/lock/cancellation gates.
- [ ] Run Linux path/lock/cancellation gates during
  `STM32TK-0405-CLI-MCP-RELEASE`; record environment ownership honestly.
  Unavailable real hardware is not claimed by packet 0401.
- [x] Commit product/tests first and reconcile the report in a separate final
  commit.
- [x] Push the Codex branch, update the PR targeting `master`, review the
  complete base-to-head diff, and merge only when all software gates pass.

## 5. Release-level acceptance strategy

### 0.4.0

- Software gate: all FakeProbe, protocol, lease, flash, handoff, DWARF, SVD,
  sample, fault, CLI/MCP, install, and upgrade tests pass on Windows and Linux.
- Real gate: selected physical probe can attach non-halting, read a harmless
  variable/register, flash the exact fresh image, hand off to Cortex-Debug, and
  reacquire without killing unrelated processes or crossing workspace state.
- If hardware is unavailable, Codex continues all software packets but leaves
  the 0.4 release checkbox open and reports the exact unmet hardware gate.

### 0.5.0 and 0.6.0

- Monitor service/UI is offline, loopback-only, token-authenticated, accessible,
  and project-isolated. Fresh workspaces contain zero named groups.
- Host and target test artifacts bind to exact source/toolchain/firmware/probe.
- Diagnostic sessions preserve competing hypotheses, supporting/refuting
  evidence, intrusive action authorization, and fix verification.

### 0.7.0 to 0.9.x

- CubeMX/IOC creation reuses the managed generation/build pipeline and never
  writes Keil files.
- Acceptance harness is versioned, resumable, concurrent-workspace safe, and
  rejects skipped hardware steps for the release profile.
- Clean GitHub installation, upgrade/downgrade safety, compatibility matrix,
  dependency/license review, SBOM, and malicious-input security tests pass.

### 1.0.0

- Archive one complete real legacy-Keil scenario and one complete new-CubeMX
  scenario on a named supported board/probe pair.
- Neither scenario may contain a hardware skip. Both must build, flash, observe,
  reproduce a fault, collect evidence, apply an authorized source fix,
  rebuild/reflash, run target tests, and verify monitor assertions.
- Only then update all component versions, roadmap checkbox, changelog, signed
  release commit/tag, compatibility claims, and known limitations.

## 6. Progress accounting

Progress is gate-based, not line-count based:

- 0.3.0 migration/build foundation: complete and accepted.
- 0.4.0 hardware access/debug: STM32TK-0401 and STM32TK-0402 are integrated;
  STM32TK-0403 has a verified software implementation. The release remains open
  for 0404, 0405, and the named Linux/real-probe gates.
- 0.5.0 monitor, 0.6.0 tests/diagnostics, 0.7.0 creation, and 1.0.0 vertical
  acceptance: not started.

Do not report a release complete because its software code exists. Its release
percentage advances only when the corresponding exit evidence is committed.
