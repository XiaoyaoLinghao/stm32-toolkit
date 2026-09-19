# Generation apply root classification correction

Primary owns this bounded correction under the active local release goal. Runtime
accepted base is `a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d`; qualification accepted
base is `0a6bf2a6c591e5e89c6451050de3087168b77eb4`. The reviewed Project test candidate
is `e22d858494cdc8135052f8ac066d8ee370f8c0a4`, whose first run retained 10 passes
and exposed one product contradiction. It is not an accepted complete test run.

## Scenarios and behavior

1. A digest-consistent generation plan names a missing root or a file. Public
   `apply_project_configuration` returns `GENERATION_PLAN_INVALID`, details
   `{"rule":"projectRoot"}`, before entering the shared mutation lock or writing.
2. A valid directory encounters a genuine mutation-lock failure. Preserve
   `GENERATION_APPLY_FAILED`, details `{"phase":"projectMutationLock"}`.
3. A valid plan applies normally. Preserve lock ownership, under-lock root
   revalidation, transaction semantics, rollback and published output bytes.

The current wrapper acquires `project_mutation_lock` before `_apply` validates
its root. Missing-root strict resolution therefore bypasses the existing
`_canonical_root` mapping. Reuse that existing validator immediately after plan
validation and before lock acquisition. Retain `_apply` validation for drift
between preflight and protected execution. Do not change lock implementation,
plan identity, schemas, other errors, CLI/MCP, firmware, or hardware behavior.

## Ownership and necessary verification

Luna/max owner `/root/final_python_qualification` owns only
`tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py`, the bounded new
root-refusal case in `tools/stm32-toolkit/tests/test_generation.py`, and its
existing Project return report. No other owner touches these files. Primary
independently reviews the complete `0a6bf2a6c591e5e89c6451050de3087168b77eb4..final`
diff in the detached review worktree and integrates only after passing evidence.

Keep the failure evidence. Strengthen root refusal to assert the shared lock is
never entered, original project/file bytes are unchanged and no owned staging
state is created. Existing successful apply, genuine lock-failure, transaction
and rollback tests provide the affected regression. Runtime source changes
justify one current `test_generation.py` file run (not the whole package), plus
only the four still-unrun regeneration functions from Project run1. Use the
existing bounded launcher with native Toolkit branch coverage, a 300-second
wall limit, first failure stop, and D-drive roots `r10/e/core95/project/run2`
and `r10/t/c95/p/run2`. Primary is the single executor. No product import or
pytest before entry review.

The changed configure.py invalidates retained native arcs for that file only.
Purge that file from copies of all old Toolkit inputs before the final native
union; use the current affected-file run for its coverage. Retain all source-equal
functional/UI/physical evidence and the unchanged Monitor inputs. No coverage
exclusion, threshold adjustment, new diagnostic framework, packaging, deployment,
hardware operation, cleanup or remote action is part of this correction.
