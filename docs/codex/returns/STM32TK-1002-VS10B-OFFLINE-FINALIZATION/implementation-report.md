# STM32TK-1002 VS10-B offline finalization implementation return

Status: `RETURNED FOR INDEPENDENT REVIEW`; the primary's independent review accepted the
product/test candidate at `5b577dc6a7fe3b830e65d6306504310c690685a3`. The final `22ec7ba6`
addendum removes one unused import from the already reviewed MCP file and is behavior-neutral.
This report records the implementation boundary and evidence; the implementation agent does not
self-accept its own diff.

## Handoff and authority ledger

- Slice: `STM32TK-1002` VS10-B offline finalization vertical.
- Full accepted product base: `abdc2fb5dbde2b6643e26d42e29c7ad6db72f921`.
- Approved design starting head: `1b448632ea6b7d3eb9dd2e5eb73d056df0270274`.
- Specification: `docs/superpowers/specs/2026-09-18-stm32tk-vs10b-offline-finalization-design.md`.
- Plan: `docs/superpowers/plans/2026-09-18-stm32tk-vs10b-offline-finalization.md`.
- Product/tests CodeHead before this report: `22ec7ba68967bcbcacea325848886dd953affb31`.
- Branch: `codex/STM32TK-1002-offline-finalization`.
- Implementation worktree: `D:\codex-tmp\v10b-0918\fin\impl`.
- Product and implementation-test owner: one `gpt-5.6-luna`, maximum-reasoning implementation
  agent. Evidence owner: the same agent for this bounded slice; independent review and acceptance
  remain with the primary agent.
- Remote state: no push, pull request mutation, merge, tag, release, or branch deletion.

The accepted-base-to-CodeHead product/test paths are the approved specification and plan, the
standard test procedure update, and these implementation/test paths:

- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/__init__.py`
- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/finalization.py`
- `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/tests/test_acceptance_finalization.py`
- `tools/stm32-toolkit/tests/test_continuation_adapters.py`

`cli.py` and `acceptance/continuation.py` were not changed. No product implementation, test, or
canonical-data path was changed while preparing this report.

## Delivered behavior

`acceptance/finalization.py` owns the closed `/2` request/proof and `/5` attempt models without
importing Diagnostic or workflow code. `recovery_workflows.py` owns the one full persisted graph
reader and the begin/checkpoint/show/retry/publication routes. It authenticates the predecessor
chain, the completed Diagnostic and FixVerification graph, same-session before/after physical
TestRuns, ordinary analysis and marker evidence, and exact proof/attempt identity bindings.

Publication retains the approved Diagnostic-lock-to-Evidence-lock order. All proof, predecessor,
CAS, current-firmware, and deadline rechecks complete before the commit timestamp is sampled;
the final live deadline check precedes root publication. Existing `/1` through `/4` bytes and
legacy routes remain unchanged. MCP routing uses the strict `/2` union while preserving the
approved legacy empty-object exception.

The portable source-controlled fixture builds a persisted Cubemx-shaped graph through the existing
Target replay, TestRun, Monitor, Diagnostic, FixVerification, and EvidenceStore readers. It is
explicitly synthetic offline evidence and is not physical PASS. Optional card evidence is read
from a disposable byte-identical copy; the canonical store was not mutated and the actual timed
finalization/application was not run by this implementation owner.

## Actor and interpreter

The commands below were executed by the sole implementation/test actor in PowerShell with:

- Interpreter: `C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe`
- Python: `3.12.10`
- Pytest: `8.4.2`
- Source paths: `tools/stm32-monitor/src;tools/stm32-toolkit/src` via `PYTHONPATH`.
- `TEMP`, `TMP`, and `TMPDIR`: run-specific directories below
  `D:\codex-tmp\v10b-0918\fin\t`.

The deployed B runtime at `D:\codex-tmp\v10b-0918\dgdep\data\runtime\0.9.0\Scripts\python.exe`
was inspected as required, but its environment did not provide pytest; it was not substituted for
the system test interpreter.

## Exact verification commands and results

The final portable command used the observed pytest basetemp argument ending in `full-finalization-r2\pytest`:

```powershell
python -m pytest -q --basetemp=D:\codex-tmp\v10b-0918\fin\t\full-finalization-r2\pytest tools/stm32-toolkit/tests/test_acceptance_finalization.py
```

Result: **16 passed, exit 0**. The combined stdout and exit evidence are:

- `D:\codex-tmp\v10b-0918\fin\e\impl-evidence-340ceb50\full-finalization-r2.stdout.txt`
- `D:\codex-tmp\v10b-0918\fin\e\impl-evidence-340ceb50\full-finalization-r2.exit.txt`

The targeted additions were run with the same interpreter/source bindings:

```powershell
python -m pytest -q --basetemp=D:\codex-tmp\v10b-0918\fin\t\focused-finalization-r2\pytest tools/stm32-toolkit/tests/test_acceptance_finalization.py -k "expired_attempt_retry or authority_graph_rejections or final_deadline_check_rejects_rev1 or unexpected_revision_rejected"
```

Result: **4 passed, exit 0**. The explicit external-fixture guard was then checked independently:

```powershell
python -m pytest -q --basetemp=D:\codex-tmp\v10b-0918\fin\t\fixture-guard-r2\pytest tools/stm32-toolkit/tests/test_acceptance_finalization.py -k explicit_external_fixture_paths_fail_closed
```

Result: **1 passed, exit 0**. Evidence for both commands is in
`D:\codex-tmp\v10b-0918\fin\e\impl-evidence-340ceb50\focused-finalization-r2.stdout.txt`,
`focused-finalization-r2.exit.txt`, `fixture-guard-r2.stdout.txt`, and
`fixture-guard-r2.exit.txt`.

The affected compatibility command was:

```powershell
python -m pytest -q --basetemp=D:\codex-tmp\v10b-0918\fin\t\compat-r1\pytest tools/stm32-toolkit/tests/test_acceptance_physical_recovery.py tools/stm32-toolkit/tests/test_acceptance_recovery_mcp.py tools/stm32-toolkit/tests/test_acceptance_recovery_model.py tools/stm32-toolkit/tests/test_continuation_adapters.py
```

Result: **56 passed, exit 0**. Evidence: `compatibility-r1.stdout.txt` and
`compatibility-r1.exit.txt` under `D:\codex-tmp\v10b-0918\fin\e\impl-evidence-340ceb50`.

The unchanged public CLI regression command was:

```powershell
python -m pytest -q --basetemp=D:\codex-tmp\v10b-0918\fin\t\cli-r1\pytest tools/stm32-toolkit/tests/test_acceptance_recovery_cli.py
```

It produced **6 passed, exit 0**. The timestamp/deadline seam command was:

```powershell
python -m pytest -q --basetemp=D:\codex-tmp\v10b-0918\fin\t\clock-r1\b tools/stm32-toolkit/tests/test_acceptance_finalization.py -k "commit_timestamp or final_deadline"
```

It produced **3 passed, exit 0**. Their stdout/exit pairs are `cli-r1.*` and `clock-r1.*` in
the same evidence directory.

Static verification at the final CodeHead used these commands:

```powershell
python -m py_compile tools/stm32-toolkit/src/stm32_toolkit/acceptance/finalization.py tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py tools/stm32-toolkit/src/stm32_toolkit/acceptance/__init__.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py tools/stm32-toolkit/tests/test_acceptance_finalization.py
python -m ruff check --select F401,F821,F811 tools/stm32-toolkit/src/stm32_toolkit/acceptance/finalization.py tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py tools/stm32-toolkit/src/stm32_toolkit/acceptance/__init__.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py tools/stm32-toolkit/tests/test_acceptance_finalization.py
git diff --check
```

All three exited `0` after the final one-line MCP import addendum.

## Card-copy and concurrency boundary

The optional card-copy smoke used the run-owned script
`D:\codex-tmp\v10b-0918\fin\t\finalization-proof-7da00b23-f10.py` and disposable copied data.
Its exit evidence is `finalization-card-r1.stdout.txt` and `finalization-card-r1.exit.txt` under
`D:\codex-tmp\v10b-0918\fin\e\impl-evidence-340ceb50`. It recorded the offline positive rev0→rev1
path, fresh-process read, expiry/idempotent retry/fresh-UUID reuse, public CLI/MCP happy path,
and identity, ancestry, tamper, CAS, source-authorization, and stray-revision failures.

The same output records one native-thread concurrent loser as
`ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED`. That result is retained as an observed integrity
loser and is not reported as a concurrency PASS. The accepted deterministic F4 coverage is the
source-controlled persisted test that creates two independently authenticated proofs and injects
the same-UUID reuse race; it passes in the 16-test run with one conflict winner and the winner's
proof association preserved.

## Explicit non-goals and limitations

- Synthetic replay evidence and the optional evidence-copy smoke are offline software evidence;
  neither is physical hardware PASS.
- No hardware connection, firmware build/flash/reset, Target or Monitor mutation, Diagnostic
  mutation, deployment, canonical-store write, remote action, push, PR, merge, tag, or release was
  performed by this implementation owner.
- Primary owns the later preserved-evidence rehearsal and canonical offline application under the
  approved scope. Those actions are outside this implementation return.
- The report is committed separately from the frozen product/tests CodeHead; its own final commit
  SHA is intentionally not recorded here.
