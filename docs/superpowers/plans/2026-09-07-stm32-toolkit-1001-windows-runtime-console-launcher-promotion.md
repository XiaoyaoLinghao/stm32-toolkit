# STM32 Toolkit 1001 Windows runtime console-launcher promotion plan

## 1. Ledger and gate

- Approved design target:
  `docs/superpowers/specs/2026-09-07-stm32-toolkit-1001-windows-runtime-console-launcher-promotion-design.md`.
- Full accepted product base:
  `387e59067cb066d5bb9ccf5d0e2253644a9710f5`.
- Accepted base tree:
  `fbbf285defe7817e61c3b1b69260a1c6598401ac`.
- One implementation owner: `gpt-5.6-luna`, reasoning `max`.
- Independent reviewer/acceptor: GPT-5.6-sol primary.
- Local branch:
  `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Remote/hardware authority: none for this plan.

Implementation begins only after the user explicitly approves both the design
and this plan. The implementer is not alone in the repository, must preserve
all unrelated work, must not amend the accepted post-flash slice, and must not
accept, push, publish, install into the campaign data root, or perform hardware
actions.

## 2. Ownership and allowed files

The one Luna/max owner owns only:

```text
bin/setup-stm32-env.ps1
tools/stm32-toolkit/tests/test_setup_runtime.py
```

The Sol primary owns the design, plan, complete-diff review, verdict, SDD/report
reconciliation, and any later authorization decision about installing the
accepted correction. Shared schemas, pyprojects, README, launchers, release
utility, package code, Target code, hardware artifacts, and project bytes are
read-only for this slice.

## 3. Task 1 — freeze the real RED and test fixtures

### 3.1 Audit before edit

Record:

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git diff --check
git diff --name-only 387e59067cb066d5bb9ccf5d0e2253644a9710f5...HEAD
```

Stop if the implementation worktree is not at the approved docs head or if any
unexplained tracked/untracked change overlaps the two owned files.

### 3.2 Add a real console-entry-point test fixture

Extend the existing fake Toolkit and Monitor wheels in
`test_setup_runtime.py` only enough to declare the same three console scripts as
the real product and to return exact `0.9.0` version output. Do not add a new
package, interpreter, external index, or test-only branch in production code.

The fixture must keep the existing doctor, 48-tool, eight-Skill, PyOCD, and
Monitor UI contracts intact.

### 3.3 RED tests

Add focused Windows tests that run from a data root and project root containing
spaces and prove the accepted base currently fails after successful Bootstrap:

- final `Scripts/stm32-toolkit.exe version` is not usable because it binds the
  removed staging interpreter;
- final `Scripts/stm32-monitor.exe version` has the same failure;
- the three public console launchers expose a staging interpreter binding
  rather than the exact final Python;
- CHECK currently misses that broken public CLI (the target GREEN assertion is
  CHECK=`broken` without mutation).

Commit the RED tests before product changes. The RED commit may touch only
`tools/stm32-toolkit/tests/test_setup_runtime.py`. If the fixture cannot expose
the real distlib behavior, stop and return `BLOCKED_TEST_DESIGN`; do not replace
the assertion with a byte fixture that never passes through setup/pip.

## 4. Task 2 — final-path launcher regeneration transaction

### 4.1 Add bounded internal helpers

In `bin/setup-stm32-env.ps1`, add internal functions that:

1. select exactly one manifest wheel for `stm32-toolkit==0.9.0` and exactly one
   for `stm32-monitor==0.9.0`, failing closed on missing, duplicate, malformed,
   redirected, wrong-size, or wrong-hash inputs;
2. after promotion, recompute their locations below the final runtime's
   `release-wheels` directory and revalidate them;
3. invoke only `runtime/0.9.0/Scripts/python.exe -I -m pip install` with the
   existing offline/no-dependency/binary-only flags plus the bounded reinstall
   option and those exact two wheel paths;
4. validate exact regular/non-redirected files for final Python and
   `stm32-toolkit.exe`, `stm32-toolkit-mcp.exe`, `stm32-monitor.exe`;
5. inspect bounded launcher records/bytes to require the exact final Python and
   reject `.staging` bindings without starting MCP; and
6. invoke bounded `stm32-toolkit.exe version` and `stm32-monitor.exe version`,
   requiring exactly `0.9.0`.

All path comparisons are absolute and case-aware according to the existing
Windows path policy. No shell interpolation, PATH lookup, glob-based selection,
or arbitrary entry-point execution is permitted.

### 4.2 Place finalization inside the existing rollback boundary

Keep the current staging install and all pre-promotion validation unchanged.
Inside the existing `try` block:

```text
quarantine old runtime if Repair
move staging candidate to runtime/0.9.0
regenerate public product launchers from exact final wheel paths
repeat final pip/package/launcher/doctor validation
write runtime-state.json atomically
```

Do not publish state before final validation. Preserve the current catch path so
any finalization failure deletes only the new final candidate, restores the
quarantined runtime, and restores prior state bytes. Bootstrap failure leaves no
runtime/state candidate.

### 4.3 Make CHECK cover the public CLI

Extend `Get-RuntimeEvidence` to call the same read-only public-launcher
validation after the existing runtime interpreter checks. A relocated old
runtime must return structured `broken` evidence and recommend Repair; CHECK
must never regenerate or rewrite it.

Commit the product GREEN separately after the RED commit. The product commit
may touch only `bin/setup-stm32-env.ps1`.

## 5. Task 3 — GREEN and affected regression

Use CPython 3.12 and external, uniquely named basetemps. Start with the exact new
nodes; then run only risk-linked existing nodes and the complete setup file.

Required GREEN behavior:

1. Fresh Bootstrap under paths with spaces returns success, final Toolkit and
   Monitor executables both report `0.9.0`, all three public launcher bindings
   name exact final Python and no staging Python, runtime state matches, and
   CHECK reports healthy/read-only.
2. A deliberately staging-bound public launcher makes CHECK report broken,
   authorization required, Repair recommended, and no mutation.
3. Repair quarantines the old runtime, increments generation once, publishes a
   healthy final runtime, and leaves project bytes unchanged.
4. Deterministic post-promotion failure proves rollback/no-state publication.
   If it cannot be injected without adding a product-only test hook, stop at the
   frozen `BLOCKED_TEST_DESIGN` rule.

Risk-linked regressions include:

- existing Bootstrap/Repair/staging/quarantine tests;
- unsupported Python, invalid bundle/hash, source conflict, downgrade refusal,
  redirect/reparse, hostile Python environment, pip check, doctor inventory,
  and setup trust-anchor tests affected by the helper transaction;
- `test_plugin_layout.py` MCP/Monitor repository `.cmd` launcher tests, because
  the correction must not replace or weaken them;
- complete `tools/stm32-toolkit/tests/test_setup_runtime.py`.

Do not run Target, hardware, project-build, full repository, full release, or
unrelated platform matrices without a new written risk trigger.

Before each commit and return, run:

```powershell
git diff --check
git diff --name-only
git status --short --branch
```

After tests, inspect and remove only exact run-owned disposable basetemps and
generated fixtures that are no longer needed. Preserve minimum failure evidence
and report any executor-policy or ACL residue by exact path and classification.

## 6. Implementation return contract

The Luna/max implementer returns:

- RED commit SHA and exact failing command/output;
- GREEN product commit SHA and tree;
- exact accepted-base-to-code-head changed paths;
- focused and affected-regression commands/results;
- failure classification for every non-pass;
- cleanup/status/diff evidence;
- confirmation of no project, campaign runtime, hardware, remote, release,
  schema, inventory, Agent adapter, or unowned-file mutation.

The implementer must not write the final report or self-accept. The Sol primary
will create a fresh clean isolated review worktree at the returned code head,
review the complete diff from `387e59067cb066d5bb9ccf5d0e2253644a9710f5`,
repeat proportionate Windows checks, reconcile the terminal hardware result
separately, and issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`.
