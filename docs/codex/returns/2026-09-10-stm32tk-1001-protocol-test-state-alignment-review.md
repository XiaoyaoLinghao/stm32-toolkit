# Protocol test state alignment review

Verdict: **ACCEPTED** for this test-only correction. The three historical
`test_probe_protocol_v2.py` baseline failures are closed by alignment with the
already approved connection-state contract; earlier failure records remain intact.

- Accepted base: `a46310cbad431ed0f8c56d822db9054d426c4c14`.
- Plan: `e02b141de2eedb85ab1549eb399cc7a271f34f72`.
- Luna implementation CodeHead: `68260c3073b66c0533f63d4846c81075873878c7`.
- Integrated CodeHead before this report: `626d54d68971f6223004a0aa4d6bcd00aa222f53`.
- Review owner: primary conversation, with independent reviewer
  `acceptance_regression_ledger` in clean `D:/codex-tmp/m100-reg-review`.
- Remote authority/actions: none. Deployment/hardware actions: none.

Only the three affected tests changed. The positive halted-only adapter case now
uses explicit `halt_on_connect=True`. The state-failure fake is armed after a
successful attach. Legacy register reads explicitly reject a running target with
`PROBE_REGISTER_UNAVAILABLE`, then establish halted state for the positive read;
closed-profile rejection still produces zero underlying reads. Product code,
shared fakes, and skip/xfail policy did not change.

Luna reproduced all three known failures at the accepted base (3 failed, 2.03s),
then ran the corrected nodes (3 passed, 1.01s) and the complete existing module
(75 passed, 5.20s). Minimum logs and commands are in
`D:/codex-tmp/m100-reg-20260910/validation-evidence.md`, `pytest-output.txt`,
`green-output-2.txt`, and `full-output.txt`.

The primary independently reran the three nodes at the exact implementation
CodeHead: 3 passed in 1.29s. Evidence:
`D:/codex-tmp/stm32tk-owned-wait-monitor-observe-replacement-board-20260910-12/protocol-alignment-review-tests.txt`.
The independent reviewer accepted the complete base-to-implementation diff. The
integrated diff consists only of the plan and this same test patch; test contents
are byte-identical to the reviewed CodeHead, and `git diff --check` passed. No
product-source difference exists from a463 to the integrated CodeHead.

The automatic approval review rejected cleanup of the new run-owned review temp
directories with `blocked by policy` before command execution. They are retained;
no alternative deletion was attempted. This housekeeping limitation does not
change the software evidence. Previous cleanup denials remain untouched.

The deployed runtime stays at a463; no package rebuild or hardware replay is
required for a test/report-only correction. The -12 100ms physical PASS, new-board
flash/readback PASS, and historical attempt7 PASS remain valid within their own
identities. T9, T10, and VS10-A are not accepted by this report.
