# STM32TK-0405 CLI, MCP, and 0.4 Release Reconciliation Plan

> **Execution owner:** Codex. Use test-driven development for every behavior
> change, independent subagents only on disjoint paths, and
> verification-before-completion before remote delivery.

**Goal:** Expose the accepted 0.4 probe, flash, handoff, typed-read, sampling,
and Fault contracts through thin project-bound CLI/MCP/Skill workflows, then
reconcile plugin/package/runtime/docs at version 0.4.0 without weakening any
hardware authorization or provenance gate.

**Accepted base:** `32a79a7b84b083b9c94a74357add71dcb7e2dea4`
(`master`, merged `STM32TK-0404-TYPED-DEBUG`).

**Branch:** `codex/STM32TK-0405-CLI-MCP-RELEASE`

**Ownership ledger:** Codex owns specification, implementation, tests, review,
report, push, PR, and ordinary merge under the user's explicit continuation
authorization. OpenClaw remains paused. There is no bounded override from a
different implementer and no active PR at initialization.

**Architecture:** One high-level async workflow module constructs canonical
`WorkspacePaths`, an exact `ProbeLeaseManager`, a `ProbeServiceSupervisor`, and
one authenticated `ProbeClient`. Each CLI invocation and each MCP hardware
tool owns its service lifecycle and closes it cancellation-safely. Probe list
does bounded discovery without opening a target session. Flash uses `MODIFY`;
attach/read/sample/Fault and both handoff endpoints use `OBSERVE`. Handoff begin
persists its one-time ticket state before stopping the transient service, so a
later process can end the handoff only with the same project/workspace/session/
probe and ticket. No client accepts a raw address, command, environment, token,
lease, workspace, or project-root override through MCP.

**Release boundary:** This packet completes the 0.4 software surface and bumps
all shipped components to 0.4.0. A missing physical probe or Linux host does
not become a fabricated PASS: those gates stay named and open. Monitor group,
history, storage, HTTP/WebSocket, and UI behavior remain 0501/0502 scope.

---

## Task 1: Implement one authoritative hardware workflow layer

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_hardware_workflows.py`

- [ ] Write RED tests for canonical project/data roots, stable workspace and
  caller-supplied safe session IDs, exact probe/target/build/ELF pins, operation
  levels, service/client lifecycle, cancellation cleanup, and no raw exception,
  token, lease, endpoint, or absolute-root leakage.
- [ ] Build workspace identity only from the current Schema-v2 model and
  canonical project root. Keep all runtime/session files outside the project;
  reject redirect/reparse components before hardware access.
- [ ] Implement bounded probe discovery that closes its backend and never opens
  a target session. Zero, one, and multiple probes are evidence, never an
  implicit wildcard choice.
- [ ] Implement flash, handoff begin/end, variable read, variable sample,
  register read, and Fault workflows by composing only the accepted 0403/0404
  public contracts. Do not copy or weaken their identity checks.
- [ ] Start the transient service at the least required operation level, build
  clients only from its exact endpoint, and always close client/service under
  success, stable failure, cancellation, and cleanup failure. Cleanup failure
  must not be hidden by an earlier success.
- [ ] Require a real `DwarfCatalog.from_binding()` and exact explicit SVD
  candidates. Callers provide expressions/register paths, never addresses or
  sizes. Handoff end must use the persisted originating session plus one-time
  ticket; it may not steal a busy probe.

---

## Task 2: Add strict JSON CLI commands

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/tests/test_cli.py`
- Create: `tools/stm32-toolkit/tests/test_cli_hardware.py`

- [ ] Write RED grammar tests for `probe list`, `flash`, `debug handoff-begin`,
  `debug handoff-end`, `debug variables`, `debug sample`, `debug registers`,
  and `debug fault` with required `--project`, `--data-root`, `--session-id`,
  exact probe/target/build/ELF arguments, repeatable expressions/paths, explicit
  SVD candidates, bounded intervals/count/duration, and strict booleans.
- [ ] CLI flash and handoff begin require explicit `--authorized`; omitting it
  reaches the workflow as false and can never invoke target modification or
  release ownership. Read/Fault commands expose no control flag.
- [ ] All hardware commands emit one `OperationResult` JSON document and stable
  exit 0/2. Cancellation propagates; internal exceptions are sanitized without
  printing tokens, absolute runtime paths, or backend messages.
- [ ] Prove existing 0.3 commands and project-root precedence remain compatible,
  and CLI execution never changes process cwd or project files except the
  already-authorized flash-result/handoff state contracts.

---

## Task 3: Add project-bound MCP tools and concurrency policy

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Modify: `tools/stm32-toolkit/tests/test_mcp_server.py`
- Modify: `tools/stm32-toolkit/tests/test_mcp_migration_build.py`
- Create: `tools/stm32-toolkit/tests/test_mcp_hardware.py`

- [ ] Write RED schema and invocation tests for exactly 15 project-bound tools:
  the existing seven plus `stm32_probe_list`, `stm32_flash`,
  `stm32_debug_handoff_begin`, `stm32_debug_handoff_end`,
  `stm32_variable_read`, `stm32_variable_sample`, `stm32_register_read`, and
  `stm32_fault_analyze`.
- [ ] MCP hardware schemas accept no project root, data root, workspace, lease,
  endpoint, token, raw address/size, command, environment, or process argument.
  The server's canonical `ServerRuntime` remains the only root/session owner.
- [ ] Preserve client-roots validation before any service/backend creation.
  Exact `authorized is True` is required for flash and handoff begin; strings,
  integers, null, arrays, and objects never enter an intrusive workflow.
- [ ] Serialize hardware lifecycle per MCP runtime so concurrent calls cannot
  overwrite one endpoint/session record or race one supervisor. Cancellation
  waits owned cleanup and propagates; a cleanup error has priority over a
  successful tool result.
- [ ] Return complete `OperationResult.to_dict()` evidence and test partial item
  failures, busy probe ownership, lost lease, stale firmware, replayed handoff
  ticket, and workflow exception sanitization without fake hardware PASS.

---

## Task 4: Ship thin Skills and reconcile version 0.4.0

**Files:**

- Create: `skills/flash-firmware/SKILL.md`
- Create: `skills/debug-firmware/SKILL.md`
- Create: `skills/read-var/SKILL.md`
- Modify: `skills/setup-stm32-env/SKILL.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `bin/stm32-toolkit-mcp.cmd`
- Modify: `bin/setup-stm32-env.ps1`
- Modify: `tools/stm32-toolkit/pyproject.toml`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/__init__.py`
- Modify: `README.md`
- Modify: `README_zh-CN.md`
- Modify: version-sensitive tests under `tools/stm32-toolkit/tests/`

- [ ] Write RED plugin/runtime tests requiring exactly seven discovered Skills,
  one MCP registration, package/plugin/CLI/runtime version 0.4.0, marketplace
  source `./`, and no current launcher/helper selection of runtime 0.3.0.
- [ ] Skills remain thin: gather current context/identity, explain exact probe
  and target, call only named MCP tools, require authorization at flash/handoff
  boundaries, never invent SVD selection, and never claim physical success from
  a skipped or fake gate.
- [ ] Update setup CHECK/Bootstrap/Repair to runtime 0.4.0. An existing 0.3.0
  runtime is reported broken with Repair recommended, quarantined before
  promotion, and never used as MCP fallback; promotion remains atomic.
- [ ] Reconcile English/Chinese READMEs, plugin description, package metadata,
  launcher diagnostics, MCP tool/Skill inventory, deferred physical gates, and
  Monitor deferral without editing historical report facts.
- [ ] Prove a clean isolated plugin install and an isolated 0.3.0-to-0.4.0
  update discover one plugin, one MCP server, and exactly seven Skills.

---

## Task 5: Run release gates, report, review, and merge

**Files:**

- Modify: `docs/superpowers/plans/2026-08-04-stm32-toolkit-0.4-probe-debug.md`
- Modify: `docs/superpowers/plans/2026-08-07-stm32-toolkit-codex-continuation.md`
- Modify: `docs/superpowers/plans/2026-08-08-stm32tk-0404-typed-debug.md`
- Modify: this plan's checkboxes
- Create: `docs/codex/returns/STM32TK-0405-CLI-MCP-RELEASE/implementation-report.md`

- [ ] Run focused hardware-workflow/CLI/MCP/plugin/runtime tests, the full
  Toolkit suite with branch coverage at least 90%, compileall, diff-check,
  changed-file/no-suppression/credential/path-leak scans, and forbidden raw
  address/write/control/process/network/persistence scans.
- [ ] Build/install the 0.4.0 wheel in a fresh external CPython 3.12 venv and
  run all new CLI commands against the fake seam from outside the repository.
- [ ] Run `claude plugin validate .`, isolated marketplace add/install/list,
  isolated 0.3.0-to-0.4.0 update, and verify exact Skill/MCP inventories.
- [ ] Run Windows software/path/cancellation gates. Run the same Linux gates
  when a real Linux environment is available. Discover physical probes once;
  only a selected real probe/board may close non-halting read, flash, handoff,
  reacquire, and Fault smoke gates.
- [ ] If Linux or physical hardware is unavailable, record the exact named
  owner as deferred and leave the 0.4 release checkbox open; software completion
  may merge and Monitor implementation may continue against the frozen protocol.
- [ ] Commit product/tests before a separate report commit. Push a Ready PR,
  verify local/remote/PR identity, review the full accepted-base diff in a clean
  detached worktree, merge without deleting the remote branch after every
  non-deferred gate passes, then start STM32TK-0501 immediately.

