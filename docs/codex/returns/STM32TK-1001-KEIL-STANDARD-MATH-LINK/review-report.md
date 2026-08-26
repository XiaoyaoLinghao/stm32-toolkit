# STM32TK-1001 Keil standard-math link review report

## Verdict

`ACCEPTED` for the bounded product slice.

This verdict permits local candidate/runtime construction and the frozen
VS10-A campaign restart. It is not `H1 ACCEPTED`, physical acceptance, release
approval, or remote-operation authority.

## Review ledger

- Product accepted base: `29d063a2b922dd636e0865ae3c0c6a825592dfb3`
- Accepted-base tree: `21e90bb5e7b904c284b389351fcf7ac930586aab`
- Approved specification: `f105db0a2852b87464710bbdb824144c91e39dfd`
- Approved plan: `f2df7c929a6a91df509398d7786f40b9a04fef17`
- Initial implementation code head: `ea8300647e53027173e8f67cfd354a8ece37d12e`
- Accepted correction code head: `0cdd142f80421c6aea59e81e963936779b05f00f`
- Accepted code tree: `c33729b55bcfcb40ff782e81548f5e2cba8a8e2f`
- Implementation report head reviewed: `ea3ad7c723e0268a6a6575765624d70bfa5aa311`
- Implementation owner: GPT-5.6-luna/max
- Independent reviewer and acceptor: GPT-5.6-sol primary
- Additional independent reviewer: GPT-5.6-sol/max review agent
- Detached review worktree:
  `C:\tmp\stm32tk-1001-standard-math-sol-review-ea830064`
- Remote, release, and hardware authority: none

## Complete-diff review

The complete
`29d063a2b922dd636e0865ae3c0c6a825592dfb3..0cdd142f80421c6aea59e81e963936779b05f00f`
diff was inspected. It contains the approved specification and plan, the
bounded schema/model/hash/planner/renderer/template implementation, tests, the
initial implementation report, and the round-1 correction.

The initial review found one material scope defect: the shared packaged schema
clone allowed `build.linkStandardMath` in Schema 2, although the selector is
Schema-3-only and the accepted base rejected that property. The same Luna owner
added a test-first correction at `0cdd142f...`: the existing Schema-2 validator
deep copy now removes only the new build property, preserving the exact
`PROJECT_SCHEMA_INVALID`, `field=build.linkStandardMath`,
`rule=additionalProperties` boundary. Explicit caller-supplied schemas,
Schema-3 behavior, the existing `nativeLinkerScript` precedent, and all
migration planner/apply behavior remain unchanged.

No unresolved product, security, compatibility, test-design, or scope finding
remains. No arbitrary library name, link option, path, response file, CMake
text, shell/environment channel, Agent logic, runtime, MCP registration,
controller, provider, backend, Python range, CI, or collaboration automation
was added. No assertion was deleted.

## Independent verification

- Initial Sol focused model/generation review: 12 passed, exit 0.
- Initial Sol complete `test_migration_plan.py`: 97 passed, exit 0.
- Luna round-1 RED: one failure with `DID NOT RAISE`, proving the Schema-2
  leak before correction.
- Luna round-1 regression GREEN: one passed, exit 0.
- Luna corrected selector-focused set: 17 passed, exit 0.
- Luna complete corrected affected set: 614 collected, 612 passed, two
  pre-existing skips, exit 0.
- Independent Sol/max correction re-review: 15 passed, exit 0.
- Final primary Sol verification against exact head `0cdd142f...`: 15 passed,
  exit 0.
- `git diff --check` passed for the complete accepted-base-to-code-head diff.
- Detached review worktree tracked/untracked status remained clean.

The final 15-test command covered the Schema-2 rejection, Schema-3
missing/true/false and invalid types, root/package schema parity, explicit
Schema-2 schema behavior, native linker model binding, accepted generic bytes,
selector model identity, generic standard-math linkage, and native uniqueness.
The 97-test migration evidence remained applicable after round 1 because the
correction did not change planner, proposal, blocker, evidence, apply, or
non-write bytes.

## Cleanup and authority boundary

Exact recursive cleanup of review basetemps was rejected before execution by
host policy. These are `ENVIRONMENT/cleanup-policy`, not product failures, and
no bypass was attempted:

- `C:\tmp\stm32tk-1001-link-sol-focused`
- `C:\tmp\stm32tk-1001-link-sol-migration`
- `C:\tmp\stm32tk-1001-link-sol-rereview-v2`
- `C:\tmp\stm32tk-1001-link-sol-rereview-focused`
- `C:\tmp\stm32tk-1001-standard-math-sol-final-focused`
- `C:\tmp\stm32tk-1001-standard-math-sol-review-ea830064-focused-913a`
- `C:\tmp\stm32tk-1001-standard-math-sol-review-ea830064-migration-913a`
- `C:\tmp\stm32tk-1001-standard-math-sol-review-ea830064-v2-repro-7d6f`
- `C:\tmp\stm32tk-1001-standard-math-sol-r1-0cdd142f-focused-a42c`

Implementation basetemp cleanup boundaries are enumerated in the implementation
report. No hardware, network, push, PR, merge, tag, release, or remote branch
operation occurred.

## Next gate

The next permitted work is local-only: reproduce the accepted 0.9 candidate,
replace the active runtime through the existing fail-closed transaction,
restart the preserved project campaign from exact `718c37e...`, and collect two
public builds plus complete pre-H1 evidence. Hardware remains forbidden until
the separate complete campaign review issues `H1 ACCEPTED`.
