# STM32TK-1001 FPU/ABI Test-Isolation Correction Design

**Status:** Approved design, pending written-spec review

**Date:** 2026-08-26

**Specification owner and reviewer:** GPT-5.6-sol

**Implementation owner:** one GPT-5.6-luna agent at reasoning effort `max`

**Accepted product base:** `77514c441854bf7a8218eb2974e54abac478e31b`

**Active implementation branch:** `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`

**Remote authority:** none; no push, PR mutation, merge, tag, release, closure, or remote deletion

## 1. Purpose

Correct the FPU/ABI revision tests so each public scenario proves one causal
contract without changing adjacent accepted-base product behavior. This is a
test-isolation correction, not a product redesign.

The current ARMCLANG fixture produces two independent blockers:

1. legacy `MIGRATION_COMPILER_UNSUPPORTED`, whose accepted-base path is the
   empty string; and
2. `MIGRATION_FLOAT_ABI_REQUIRED`, whose corrected evidence is raw `FPU2`.

Accepted-base guarded apply rejects the empty compiler-blocker path as
`MIGRATION_PLAN_INVALID` before it can reach the ordinary
`MIGRATION_BLOCKED` gate. Therefore that combined fixture can prove the public
planning tuple and no-write safety, but cannot independently prove the
ordinary FPU/ABI blocked-apply result.

## 2. Runnable scenarios

### Scenario A: ARMCLANG planning remains faithful to accepted behavior

Create a public Git-backed Keil project with ARMCLANG, Cortex-M4, raw `FPU2`,
and no raw float ABI. Through `plan_keil_conversion()` require:

- raw inspection remains `compiler="armclang"`, `fpu="FPU2"`, and
  `float_abi=None`;
- `MIGRATION_COMPILER_UNSUPPORTED` retains accepted-base
  `(path, evidence) == ("", "")`;
- `MIGRATION_FLOAT_ABI_REQUIRED` has exact evidence `FPU2`;
- a repeated public plan returns the same FPU/ABI blocker tuple;
- guarded apply retains accepted-base `MIGRATION_PLAN_INVALID` behavior;
- `.stm32-project.json`, `artifacts/migration/conversion.patch`, and
  `artifacts/migration/conversion-report.json` are all absent.

This scenario must not be used to claim that ARMCLANG has gained support or
that its legacy compiler blocker now reaches the ordinary blocked-apply gate.

### Scenario B: an isolated FPU/ABI blocker reaches the public no-write gate

Create a public Git-backed ARMCC Cortex-M4/FPU2 project with an unsupported,
nonempty raw float-ABI token and no other blocker. Through
`plan_keil_conversion()` and `apply_keil_conversion()` require:

- one exact `MIGRATION_FLOAT_ABI_UNSUPPORTED` blocker;
- blocker evidence equals the raw unsupported ABI token;
- guarded apply returns `ok=False` and code `MIGRATION_BLOCKED`;
- `blockerCodes` contains `MIGRATION_FLOAT_ABI_UNSUPPORTED`;
- the same three conversion products are all absent.

This scenario isolates the ordinary FPU/ABI blocked-apply and no-write
contract from the legacy compiler blocker.

### Scenario C: all-absent and hard-float generation remain exact

Keep the existing public conversion-to-configuration tests and require:

- with no FPU and no ABI, neither the compile block nor the link block contains
  `-mfpu=` or `-mfloat-abi=`;
- for the frozen ARMCC Cortex-M4/FPU2/no-raw-ABI fallback, compile and link each
  contain exactly one `-mfpu=fpv4-sp-d16` and exactly one
  `-mfloat-abi=hard`;
- neither block contains raw `FPU2`, `soft`, or `softfp` alternatives.

## 3. Product-byte boundary

The final accepted-base-to-code-head product diff may change only the existing
FPU/ABI decision and blocker-evidence mapping in
`tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`.

The following accepted-base behavior must be byte-identical:

- `MIGRATION_COMPILER_UNSUPPORTED` construction, including its empty path;
- `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py`;
- blocker validation, ordering, plan identity, and forged-plan defenses;
- all adjacent compiler, migration, generation, CLI, MCP, schema, runtime,
  backend, provider, controller, dependency, and version behavior.

No test is deleted. The ARMCLANG public planning test remains. Its incompatible
`MIGRATION_BLOCKED` assertion is relocated to Scenario B while Scenario A pins
the real accepted-base `MIGRATION_PLAN_INVALID` result and retains the same
three no-write assertions.

## 4. Alternatives rejected

### Change the compiler blocker path

Rejected because it changes explicitly frozen adjacent product bytes and
would turn this correction into a compiler-migration behavior change.

### Relax guarded apply validation

Rejected because it changes forged-plan defenses and the meaning of accepted
legacy blockers, expanding product scope beyond FPU/ABI evidence mapping.

### Forge or hand-edit a plan in the test

Rejected because it would not prove the public planner/apply path and could
hide a mismatch between fresh-plan identity and the tested object.

## 5. TDD and verification

One GPT-5.6-luna/max implementer owns the code/test correction. It first makes
the isolated Scenario B assertion fail or confirms the existing public
coverage gap, then performs only the bounded test correction. Product code is
not changed except to retain the already implemented FPU/ABI evidence mapping
and restore the compiler blocker to accepted-base bytes.

Before the code/test commit, require:

1. the exact Scenario A, B, and C target tests pass under CPython 3.12;
2. the complete focused FPU/ABI migration and generation target-option test
   selection passes;
3. `git diff --check` exits zero;
4. `git diff --name-only` contains only the authorized planner and migration
   test files;
5. accepted-base comparison proves no diff in `apply.py` and no diff in the
   `MIGRATION_COMPILER_UNSUPPORTED` construction;
6. run-scoped temporary outputs are removed after retaining minimum useful
   failure evidence.

Commit code/tests first. Then update the implementation report accurately and
commit only that report. The implementer stops without accepting its own diff.

GPT-5.6-sol then reviews the complete
`77514c441854bf7a8218eb2974e54abac478e31b`-to-final-code-head diff in a clean
worktree, independently reruns only the risk-mapped target tests, reconciles
the report and SDD ledger, and issues a new verdict. The earlier acceptance
report is stale under this correction and cannot be reused as acceptance.

## 6. Exit and continuation gates

This correction is accepted only when all three scenarios pass, the complete
product diff respects the byte boundary, no product finding remains, reports
are accurate, and disposable verification outputs are cleaned.

Only after the new Sol verdict is `ACCEPTED` may the candidate/runtime be
rebuilt from the accepted source and H1 preparation resume. Hardware access,
flash, reset, probe use, remote Git operations, release actions, and VS10
follow-on scope remain unauthorized by this design.
