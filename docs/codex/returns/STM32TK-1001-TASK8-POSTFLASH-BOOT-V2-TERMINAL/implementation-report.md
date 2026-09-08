# STM32TK-1001 Task 8 post-flash boot and v2 terminal implementation report

## Status

Software slice verdict: `ACCEPTED`. Overall status:
`SOFTWARE_COMPLETE_HARDWARE_PENDING`. This is not VS10 closure or release acceptance.

## Ledger and scope

- Accepted base: `f8ff521922ed366e1f1f30ae99220a8ff19f693e`.
- Final implementation CodeHead: `b9cfbcf3e0eb0d1ed8fadc91b2fd0cf1bf21f5c2`
  (tree `e3be9d1507e70f570e9741e4c600d32079605768`).
- Implementation and implementation tests: GPT-5.6-luna/max.
- Specification, plan, and independent review: GPT-5.6-sol.
- Product diff is limited to the approved six product files and four test files.

The candidate adds the CONTROL-authorized `target.reset` Probe operation, starts a successfully
flashed physical target through reset with the bounded reset-halted resume fallback, and lets a
complete protocol-v2 `run_end` stop mailbox collection before the existing final identity,
artifact, assembly, publication, and cleanup gates. The correction head also maps the two
start-transition operation/service-unavailable failures to `TEST_EXECUTION_FAILED`.

## Implementation evidence

At previous GREEN `27923529c02c6c1d4064dd02c19f535cdee4fb7d`, the implementation owner reported
three focused passing batches of 309, 46, and 72 tests. These results belong to that head and are
not represented as reruns against the final correction head.

The mapping correction was established separately:

- RED commit `5b189ab9`: 4/4 focused start-transition cases reproduced the old
  `TEST_TRANSPORT_UNAVAILABLE` mapping.
- Final CodeHead `b9cfbcf3e0eb0d1ed8fadc91b2fd0cf1bf21f5c2`: the same 4/4 cases passed with
  `TEST_EXECUTION_FAILED`.
- Final CodeHead: 23/23 affected Target runner cases passed, including the four mapping cases,
  reset order, v2 terminal, identity, and transport boundaries.

The exact logs are retained under `D:\codex-tmp`, including
`rv279-start-mapping-red.log`, `rv279-start-mapping-green.log`, and
`rv279-affected-runner.log`.

## Known baseline failures

The complete protocol-v2 file is not reported as passing. At final CodeHead it produced 72 passed
and exactly three failed tests. Those three pure-code failures reproduce with the same node IDs
and signatures on the exact accepted base and CodeHead in the same CPython 3.12 environment:

- `test_admitted_pyocd_adapter_exposes_closed_target_operations`
- `test_pyocd_target_adapter_fails_closed_on_limits_identity_and_partial_output`
- `test_pyocd_isolates_legacy_reads_from_closed_target_observation_policy`

They remain open `KNOWN_BASELINE_FAILURE` product findings. They are neither `PASS` nor
`DEFERRED`; their failure sites are in unchanged PyOCD attach and target-state behavior. The
independent review confirmed that CodeHead adds no protocol-file failure and that all new and
affected reset/start-transition assertions pass.

## Review and external evidence

Independent GPT-5.6-sol review issued `ACCEPTED` at final CodeHead after reviewing the complete
accepted-base-to-CodeHead diff. Exactly the ten approved files changed; `git diff --check` passed;
the review worktree was clean; both Probe schemas were byte-identical; and `pyocd_backend.py`
remained unchanged.

The reviewer independently passed the four P2 mapping cases under CPython 3.12.10. Earlier R1
verification passed 31 focused reset, CONTROL, runner, and v2 assertions. Six physical workflow
cases first failed because a long Windows basetemp exceeded the authorization directory bound,
then passed 6/6 with a short D-drive basetemp; this was classified `ENVIRONMENT`, not product.
Review evidence is retained in
`D:\codex-tmp\stm32tk-1001-boot-terminal-sol-review-b9cfbcf3.md`,
`D:\codex-tmp\rvb9m\mapping-risk.log`, `D:\codex-tmp\rvb9p\protocol-full.log`, and
`D:\codex-tmp\rv279a\physical-risk.log`.

No hardware/probe action, firmware or campaign-project mutation, runtime installation/promotion,
push, PR mutation, merge, tag, release, or other remote action was performed for this software
correction. Physical confirmation of the corrected post-flash application start remains pending
separate authorization after software acceptance.

Implementation-owned temporary test output was cleaned. Cleanup of retained review basetemp
directories was attempted after their evidence was classified, but command execution was blocked
by automatic policy without a more specific reason. The review logs and those directories remain
under `D:\codex-tmp`; this cleanup limitation does not change the recorded test or code results.
