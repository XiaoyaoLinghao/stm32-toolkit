# STM32TK-1001 Task 3d: Sol independent FPU/ABI review

Verdict: **ACCEPTED**

This verdict accepts only the Keil FPU/ABI normalization and test-isolation
slice. It makes no candidate-runtime, H1, campaign-build, hardware, or release
claim.

## Reviewed lineage

- Full accepted product base:
  `77514c441854bf7a8218eb2974e54abac478e31b`
- Frozen correction design:
  `9f9258c3f321229d5141aba17592397ae79246fe`
- Frozen correction plan:
  `13b991bd0bfb2cffd89063e7e58d9629f9e20cd6`
- Final product/test head:
  `87bfa05290f0aff7db74e69fcf268e3e1f47bf8f`
- Final product/test tree:
  `6499e1711feb70a9e8a1bde271d1dbf7c6b8ed31`
- Implementation-report head reviewed:
  `8520e873be6480c154c05ad8dafa5dfe98e8e356`

Sol reviewed the complete
`77514c441854bf7a8218eb2974e54abac478e31b..87bfa05290f0aff7db74e69fcf268e3e1f47bf8f`
diff and the later report-only commits through `8520e873`. The accepted-base
path set contains the two frozen designs, two frozen plans, the implementation
and review reports, `migration/planner.py`, and `test_migration_plan.py`. The
only product-code path is `migration/planner.py`; the only product-slice test
path is `test_migration_plan.py`.

## Public behavior accepted

The final public tests prove the following without private-helper calls or
forged plans:

1. ARMCLANG + Cortex-M4 + FPU2 + missing raw ABI returns the complete ordered
   plan blocker set
   `MIGRATION_COMPILER_UNSUPPORTED/""` followed by
   `MIGRATION_FLOAT_ABI_REQUIRED/FPU2`. The compiler blocker separately pins
   `(path, evidence) == ("", "")`; repeated planning is deterministic. Apply
   retains the accepted-base `MIGRATION_PLAN_INVALID` result with
   `details={"rule": "type"}`, and none of the three conversion products is
   written.
2. ARMCC + Cortex-M4 + FPU2 + raw ABI `weird` returns exactly the sole blocker
   `MIGRATION_FLOAT_ABI_UNSUPPORTED/weird`. Apply returns
   `MIGRATION_BLOCKED` with the exact one-item blocker-code list, and none of
   the three conversion products is written.
3. With no FPU and no ABI, generated compile and link blocks contain neither
   `-mfpu=` nor `-mfloat-abi=`.
4. The hard-float path gives compile and link blocks exactly one
   `-mfpu=fpv4-sp-d16` token and exactly one `-mfloat-abi=hard` token. The final
   tests collect the complete token lists, so duplicate or unknown conflicting
   FPU/ABI tokens cannot pass the oracle.

## Product-byte boundary

- `migration/apply.py` has identical accepted-base and final blobs:
  `12757fa96af5b0bddba4a17343ea63202522c653`.
- The `MIGRATION_COMPILER_UNSUPPORTED` construction has identical
  accepted-base and final SHA-256:
  `3ce2191db024874e53fccd0abf884350f45076b812bb8991ce0f3334f8f2050d`.
  Its empty path and evidence remain unchanged.
- The final planner change is limited to the frozen atomic FPU/ABI decision
  and blocker-evidence mapping. No generation, schema, inspection, CLI, MCP,
  version, dependency, runtime, candidate, campaign, golden-project,
  controller, provider, backend, or hardware behavior changed in this slice.
- Fresh `git diff --check` over the accepted base through the reviewed report
  head exited 0, and the implementation worktree was clean before this review
  report edit.

## Finding reconciliation

The review history is retained rather than hidden:

- Earlier review found incomplete blocker-set and compiler tuple assertions.
  Tests-only corrections now pin both the complete ordered blocker lists and
  the accepted-base compiler `(path, evidence)` tuple.
- The earlier attempt to change the compiler blocker path was removed. Both
  `MIGRATION_COMPILER_UNSUPPORTED` and `apply.py` are restored to accepted-base
  bytes; the ARMCLANG fixture correctly expects the pre-existing invalid-plan
  result instead of changing adjacent product behavior to reach the ordinary
  blocked-apply gate.
- Final whole-diff review found that line counts did not reject every possible
  additional FPU/ABI token. Commit `87bfa052` closes that gap with exact token
  list assertions and no product-code change.
- The implementation report's stale top-line code identity was corrected in
  report-only commit `8520e873`; both its top and final sections now bind the
  code/test head `87bfa052` and tree `6499e171`.

No Critical, Important, Minor, product, test, or report finding remains open.

## Verification evidence

The implementation owner ran the final code/test head with frozen CPython
3.12, pytest cache disabled, and the plan's run-scoped basetemp:

- four exact Scenario A/B/C nodes: exit 0, 4/4 passed;
- focused `fpu or float_abi or keil_conversion` selection: exit 0, 34/34
  passed;
- complete `tests/test_migration_plan.py`: exit 0, 97/97 passed.

Sol then checked out the exact final code/test head `87bfa052` in the clean
detached review worktree
`C:\tmp\stm32tk-1001-fpu-isolation-review` and independently ran:

- the same four exact Scenario A/B/C nodes: exit 0, four passing dots;
- the focused selection: exit 0, 34 passing dots.

No discrepancy triggered the correction plan's optional expansion to a second
complete migration-file run. The implementation owner's complete 97/97 result
remains valid because the product/test head, dependencies, environment, and
contracts did not change afterward.

## Cleanup and authority boundary

After preserving the results, the two exact disposable basetemps were removed:

- `C:\tmp\stm32tk-1001-fpu-test-isolation-pytest`
- `C:\tmp\stm32tk-1001-fpu-isolation-review-pytest`

Sol verified both paths absent with `Test-Path -LiteralPath`. No deletion
bypass was used. No probe access, target connection, flash, reset, campaign
mutation, runtime replacement, network access, remote Git mutation, push, PR,
merge, tag, or release action occurred in this review.

## Acceptance boundary

The FPU/ABI correction gate is accepted. The next authorized local work is to
rebuild the 0.9.0 candidate package and the unique managed runtime from the
accepted source, then run only the frozen H1 pre-hardware checks. H1 remains
unaccepted, so campaign conversion/build and every physical hardware action
remain prohibited until their later gates pass.
