# STM32TK-1001 FPU/ABI Test-Isolation Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the accepted-base compiler/apply behavior while proving the corrected FPU/ABI blocker evidence, ordinary blocked-apply no-write gate, all-absent flags, and exact hard-float flags through causally isolated public tests.

**Architecture:** The product contract remains the frozen FPU/ABI decision in `migration/planner.py`; no apply or compiler-migration behavior changes. One ARMCLANG public scenario pins the real accepted-base invalid-plan result plus exact FPU/ABI planning evidence, while one ARMCC public scenario isolates an FPU/ABI blocker that reaches the ordinary `MIGRATION_BLOCKED` no-write gate.

**Tech Stack:** CPython 3.12.10, pytest, STM32 Toolkit public Keil migration and project-generation APIs, Git worktrees, PowerShell 7.

## Global Constraints

- Accepted product base is exactly `77514c441854bf7a8218eb2974e54abac478e31b`.
- Frozen design is `docs/superpowers/specs/2026-08-26-stm32-toolkit-1001-fpu-abi-test-isolation-correction-design.md` at commit `9f9258c3f321229d5141aba17592397ae79246fe`.
- One `gpt-5.6-luna` implementation owner at reasoning effort `max` owns all code, test, and implementation-report corrections.
- GPT-5.6-sol owns task boundaries, complete-diff review, evidence reconciliation, and acceptance; the implementer cannot accept its own diff.
- Product code may change only in `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`, and the final accepted-base diff there may contain only the frozen FPU/ABI decision and blocker-evidence mapping.
- `MIGRATION_COMPILER_UNSUPPORTED`, `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py`, and all adjacent accepted-base behavior remain byte-identical.
- No independent-review behavior is deleted: exact public blocker/evidence, guarded blocked apply, three-product no-write, all-absent flags, and exact hard-float compile/link flags must all remain executable assertions.
- Do not modify generation, schema, inspection, CLI, MCP, version, dependency, lock, runtime, candidate, campaign project, golden project, backend, controller, provider, or hardware behavior.
- Do not access a probe, connect/reset/flash a target, run hardware tests, push, mutate a PR, merge, tag, release, close, or delete a remote branch.
- Run only the exact scenario nodes, focused FPU/ABI selection, and complete affected migration test file justified below; do not run release or hardware matrices.
- Commit code/tests first, then commit only the implementation report. Do not self-accept.

---

## File ownership map

- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`: retain the already implemented FPU/ABI decision/evidence mapping; restore only the compiler blocker construction to accepted-base bytes.
- `tools/stm32-toolkit/tests/test_migration_plan.py`: own Scenario A/B/C public assertions and no-write evidence.
- `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-implementation-report.md`: accurately supersede the stale revision narrative after the code/test commit.
- `.superpowers/sdd/2026-08-26-stm32-toolkit-1001-keil-fpu-abi-normalization/`: ignored local execution ledger only; update exact heads, commands, counts, classifications, and cleanup state, but never stage it.
- `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-sol-review.md`: GPT-5.6-sol review verdict only; the implementer does not edit it.

### Task 1: Isolate the FPU/ABI public tests and commit code/tests

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py:388`
- Modify: `tools/stm32-toolkit/tests/test_migration_plan.py:1973-2020`
- Modify: `tools/stm32-toolkit/tests/test_migration_plan.py:2198-2210`

**Interfaces:**
- Consumes: `plan_keil_conversion(root: Path, inspection: KeilInspection) -> MigrationPlan`, `apply_keil_conversion(plan: MigrationPlan) -> MigrationApplyResult`, accepted-base compiler blocker `(path, evidence) == ("", "")`, and `CONVERSION_PRODUCTS`.
- Produces: isolated executable public proofs for `MIGRATION_FLOAT_ABI_REQUIRED/FPU2`, `MIGRATION_FLOAT_ABI_UNSUPPORTED/<raw>`, `MIGRATION_PLAN_INVALID`, `MIGRATION_BLOCKED`, and zero conversion-product writes.

- [ ] **Step 1: Audit and freeze the inherited dirty state**

Run from `C:\tmp\stm32tk-1001-legacy-hardware-impl`:

```powershell
git rev-parse HEAD
git status --porcelain=v2 --untracked-files=all
git diff --check
git diff --name-only
git diff -- tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py tools/stm32-toolkit/tests/test_migration_plan.py
```

Require HEAD to descend from design commit `9f9258c3f321229d5141aba17592397ae79246fe`, no staged or ordinary untracked file, and exactly the inherited two-line restoration: compiler blocker path `inspection.project_file -> ""` and its test expectation `(inspection.project_file, "") -> ("", "")`. Stop if any other unstaged product or test change exists.

- [ ] **Step 2: Reproduce the test-design RED before editing tests**

Run from `tools/stm32-toolkit` with one dedicated basetemp:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Require exit 1 with actual `MIGRATION_PLAN_INVALID` versus expected `MIGRATION_BLOCKED`. Confirm all preceding assertions already prove accepted-base compiler tuple `("", "")` and exact FPU/ABI tuple `("MIGRATION_FLOAT_ABI_REQUIRED", "FPU2")`. Classify this as `TEST_DESIGN_CONFLICT/EXISTING_BLOCKER`, not a product failure.

- [ ] **Step 3: Pin Scenario A to the real accepted-base apply result without weakening no-write safety**

In `test_armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker`, replace only the incompatible result-code assertion and add the exact accepted-base rule:

```python
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details == {"rule": "type"}
    for rel in CONVERSION_PRODUCTS:
        assert not (repo / rel).exists()
```

Keep unchanged the public inspection assertions, compiler blocker tuple `[("", "")]`, exact `MIGRATION_FLOAT_ABI_REQUIRED/FPU2` tuple, repeated-plan tuple, and all three no-write assertions. Do not add a compiler special case or touch `apply.py`.

- [ ] **Step 4: Add Scenario B as an isolated public FPU/ABI blocked-apply test**

Add this test next to the existing unknown/ambiguous ABI coverage so the raw token and no-write gate are visible together:

```python
def test_unsupported_float_abi_public_blocker_prevents_apply_without_writes(tmp_path):
    repo = build_repo(
        tmp_path,
        files={"Main/main.c": "int main(void) { return 0; }\n"},
        uvprojx_kwargs={
            "fpu": "weird",
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )
    inspection = fixture_inspection(repo)
    assert inspection.compiler == "armcc"
    assert inspection.fpu == "FPU2"
    assert inspection.float_abi == "weird"

    plan = plan_keil_conversion(repo, inspection)
    blockers = [
        blocker
        for blocker in plan.blockers
        if blocker.code == "MIGRATION_FLOAT_ABI_UNSUPPORTED"
    ]
    assert [(blocker.code, blocker.evidence) for blocker in blockers] == [
        ("MIGRATION_FLOAT_ABI_UNSUPPORTED", "weird")
    ]
    assert not [
        blocker
        for blocker in plan.blockers
        if blocker.code == "MIGRATION_COMPILER_UNSUPPORTED"
    ]

    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert result.details["blockerCodes"].count("MIGRATION_FLOAT_ABI_UNSUPPORTED") == 1
    for rel in CONVERSION_PRODUCTS:
        assert not (repo / rel).exists()
```

Do not call a private planner helper, forge a plan, remove existing parameterized coverage, or replace public plan/apply calls.

- [ ] **Step 5: Run the exact Scenario A and B nodes**

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker','tests/test_migration_plan.py::test_unsupported_float_abi_public_blocker_prevents_apply_without_writes','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Require 2 passed. If either scenario encounters an additional blocker or writes any conversion product, stop and report instead of weakening assertions.

- [ ] **Step 6: Run the exact Scenario C generation nodes**

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures','tests/test_migration_plan.py::test_neither_fpu_nor_abi_stays_absent_from_manifest_and_flags','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Require 2 passed. The tests themselves must prove compile and link each have one exact hard-float pair, and that all-absent compile/link blocks contain neither flag.

- [ ] **Step 7: Run the risk-mapped focused selection**

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','tests/test_generation.py','-q','-k','fpu or float_abi or keil_conversion','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Require exit 0 and record exact collected/passed counts. This selection covers the changed planner decision, blocker evidence, public conversion/apply behavior, and generated target flags; it does not authorize broader integration, release, or hardware tests.

- [ ] **Step 8: Run the complete affected migration test file**

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Require exit 0 and record exact counts. A failure caused by any other existing blocker is a test-design conflict and must stop the task; do not change unrelated product behavior.

- [ ] **Step 9: Clean only the run-scoped basetemp**

Resolve `C:\tmp\stm32tk-1001-fpu-test-isolation-pytest`, verify its final absolute path remains directly under `C:\tmp`, then remove only that exact directory. Do not remove the pre-existing inaccessible `.pytest_cache`, reusable fixtures, source files, campaign evidence, or failure evidence still needed for diagnosis.

- [ ] **Step 10: Prove the final product-byte and path boundary**

Run:

```powershell
git diff --check
git diff --name-only
git diff --exit-code 77514c441854bf7a8218eb2974e54abac478e31b -- tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py
git diff 77514c441854bf7a8218eb2974e54abac478e31b -- tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py
git diff 77514c441854bf7a8218eb2974e54abac478e31b -- tools/stm32-toolkit/tests/test_migration_plan.py
```

Require `git diff --check` exit 0; `git diff --name-only` exactly the planner and migration-test files; no `apply.py` diff; and manual complete-diff inspection showing no `MIGRATION_COMPILER_UNSUPPORTED` construction change. Stop before staging if any other product path or adjacent compiler/apply behavior changed.

- [ ] **Step 11: Stage and commit code/tests only**

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py tools/stm32-toolkit/tests/test_migration_plan.py
git diff --cached --check
git diff --cached --name-only
git commit -m "fix(vs10a): isolate FPU ABI blocker evidence tests"
```

Before committing, require the cached path set to contain exactly those two paths. Record the resulting code/tests head and tree. Do not stage the design, plan, report, SDD ledger, or any generated artifact.

### Task 2: Correct the implementation report and commit it separately

**Files:**
- Modify: `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-implementation-report.md`
- Update locally, never stage: `.superpowers/sdd/2026-08-26-stm32-toolkit-1001-keil-fpu-abi-normalization/progress.md`
- Update locally, never stage: `.superpowers/sdd/2026-08-26-stm32-toolkit-1001-keil-fpu-abi-normalization/task-1-report.md`

**Interfaces:**
- Consumes: Task 1 code/tests head, exact RED/GREEN commands and counts, accepted base, design/plan commits, path audit, and cleanup result.
- Produces: one accurate implementation report that reserves acceptance for GPT-5.6-sol and one ignored local execution ledger consistent with Git and test evidence.

- [ ] **Step 1: Replace the stale revision narrative with the accepted test-isolation facts**

The report must state:

- accepted product base `77514c441854bf7a8218eb2974e54abac478e31b`;
- design commit `9f9258c3f321229d5141aba17592397ae79246fe` and this plan commit;
- Task 1 code/tests head before the report commit;
- `MIGRATION_COMPILER_UNSUPPORTED` was restored to accepted-base bytes;
- ARMCLANG Scenario A returns `MIGRATION_PLAN_INVALID`, rule `type`, while still proving exact `MIGRATION_FLOAT_ABI_REQUIRED/FPU2` and zero writes;
- ARMCC Scenario B returns `MIGRATION_BLOCKED` for exact `MIGRATION_FLOAT_ABI_UNSUPPORTED/weird` and zero writes;
- Scenario C exact flag results;
- exact test counts, commands, cleanup, and path scope;
- failure class `TEST_DESIGN_CONFLICT/EXISTING_BLOCKER`;
- no campaign, runtime, hardware, network, or remote action;
- independent Sol review remains required.

Delete or supersede every stale claim that the compiler blocker path equals `inspection.project_file`, that the ARMCLANG combined fixture returns `MIGRATION_BLOCKED`, or that the earlier review report remains an acceptance verdict. Do not include the report commit's own future SHA or moving commit totals.

- [ ] **Step 2: Reconcile the ignored SDD ledger**

Record the inherited dirty-state audit, RED, implementation decisions, exact code/tests head, test counts, cleanup status, and pending Sol review. Preserve prior evidence history but mark the previous adjacent compiler-path correction and old acceptance as superseded. Do not stage `.superpowers/sdd`.

- [ ] **Step 3: Verify and commit the report only**

```powershell
git diff --check -- docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-implementation-report.md
git add -- docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-implementation-report.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs(vs10a): report FPU ABI test isolation"
```

Require the cached path set to contain exactly the implementation report. Record the report commit in the return message, but do not edit it into the tracked report. Stop without acceptance.

### Task 3: Independent Sol complete-diff review and verdict

**Files:**
- Review: complete `77514c441854bf7a8218eb2974e54abac478e31b..Task1CodeHead` diff
- Modify: `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-sol-review.md`

**Interfaces:**
- Consumes: Task 1 code/tests head, Task 2 report commit, frozen design and plan, ignored SDD evidence, and the accepted-base tree.
- Produces: one independent `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` verdict. Candidate/runtime rebuild and H1 remain gated on `ACCEPTED`.

- [ ] **Step 1: Create a clean detached review worktree at the returned code/tests head**

Use the `using-git-worktrees` skill. Audit tracked/untracked, committed/uncommitted, and pushed/unpushed state. Do not review from the dirty implementation worktree or mutate campaign/runtime/hardware state.

- [ ] **Step 2: Review the complete accepted-base-to-code-head diff**

Require:

- only the frozen FPU/ABI decision/evidence mapping appears in product code;
- `MIGRATION_COMPILER_UNSUPPORTED` construction is byte-identical to accepted base;
- `apply.py` is byte-identical to accepted base;
- Scenario A pins exact public plan evidence, deterministic repetition, accepted invalid-plan result, and zero writes;
- Scenario B pins exact public plan evidence, ordinary blocked apply, and zero writes;
- Scenario C pins all-absent and exact hard-float compile/link flags;
- no assertion, product boundary, support range, or forged-plan defense was weakened.

Every finding must cite path, observed behavior, expected behavior, local evidence, and verification command. Correctable findings return to the same Luna/max owner; Sol does not implement product code.

- [ ] **Step 3: Independently run the four exact scenario nodes and focused selection**

Use a fresh review-only basetemp and `-p no:cacheprovider`. Run the same Scenario A/B/C commands and the focused `fpu or float_abi or keil_conversion` selection from Task 1. Require exit 0 and reconcile counts with the implementation report. Expand to the complete migration file only if a discrepancy creates a written affected-regression risk.

- [ ] **Step 4: Reconcile report, SDD ledger, and cleanup**

Verify the tracked implementation report names the accepted base and code head before its own commit, contains no stale compiler-path or ARMCLANG blocked-apply claim, and does not claim hardware/H1 acceptance. Verify the ignored SDD ledger matches Git/test evidence. Remove only the exact review basetemp and review worktree after preserving the verdict.

- [ ] **Step 5: Issue the independent verdict**

Update the stale Sol review report with the new complete-diff range, commands, counts, byte-boundary evidence, and verdict. Commit only that review report. `ACCEPTED` requires every non-deferred gate above to pass and no unresolved product defect. Do not push or enter candidate/runtime, H1, or hardware work in the same review step.

---

## Post-acceptance handoff

After Sol `ACCEPTED`, return to the frozen VS10-A plan at candidate/runtime rebuild. Rebuild the 0.9.0 candidate from the newly accepted source, replace the unique managed runtime, and re-run only the already specified H1 pre-hardware evidence. The existing candidate/runtime built from `dc8f642e7708625c5707e0694512b915e819bc7b` is ineligible because it contains the rejected adjacent compiler-blocker behavior.
