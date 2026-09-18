# Monitor public regression implementation plan

Contract: [public refusal and lifecycle regression evidence](../specs/2026-09-19-stm32tk-monitor-public-regressions.md).
Accepted product base: `15b1a70e9bd684285da5557104deff529f537e49`.
Authorization is the user's ongoing local-release goal, including necessary
implementation, tests and independent review without repeated approval.

1. One Luna/max owner works in `r10/mg` on
   `codex/STM32TK-1.0-monitor-public-regressions`. Own only the existing Monitor
   `tests/test_cli.py`, `tests/test_probe_session.py`, `tests/test_sampler.py`,
   and one concise implementation report. Other owners are running final tests
   in `r10/verify`; never alter their files or processes.
2. Reuse the public entries and fixtures identified in
   `r10/e/monitor-public-test-gaps.md`. Correct that diagnosis if the actual
   callable contract contradicts it. Cover the four user scenarios with the
   smallest meaningful regression set; no count target or private-branch quota.
3. Set TEMP/TMP/TMPDIR, cache, basetemp and coverage under `r10/t/monitor-gaps`
   before tests; retain exact commands, interpreter, environment, JUnit, complete
   failure output and coverage under `r10/e/monitor-gaps`. Use the existing
   `r10/py/Scripts/python.exe`. No performance measurement under concurrent load.
   Local slice coverage is informational; it is not the package release gate.
4. Commit test changes locally and report accepted base, test CodeHead, actual
   results and any failure. Do not approve the diff or change the frozen product
   candidate. One independent reviewer examines the complete 15b-to-final diff
   in a clean checkout, verifies public-scenario assertions and scope, and
   compares all product source blobs against 15b. Correct findings go back to
   the same owner; two nonconverging rounds return to the contract.
5. Primary integrates only accepted test/document changes and the verification
   owner appends their coverage using exact source mapping/equality. Do not run
   another full suite, change coverage thresholds, or repackage merely because
   the evidence tests changed. Keep both shipped product CodeHead and test head
   explicit. The initial coverage failure remains recorded.

Primary owns cleanup; retain minimum failures and accepted evidence. Do not retry
previous policy-denied cleanup. No hardware or remote operations are authorized
by this plan.
