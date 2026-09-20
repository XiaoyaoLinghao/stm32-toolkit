# Diagnostic public caller journeys

Status: **ACCEPTED for the two offline caller scenarios**. STM32 Toolkit 1.0
release acceptance remains **NOT_ACCEPTED**; coverage and the pending native
Windows checks are separate gates. Existing VS10-A/VS10-B acceptance is retained.

- Accepted base: `a1c579e686d79b2bab190bdd54fa890833b36285`.
- Tested candidate: `a695f397260ebb815059d3df598dadf4c884924c`.
- Integrated code head before this report: `daacedaa2cebb6b4830068d58fffe8298499adc5`.
- Product source remains `8a11caef14df16c5e56c0be2363d4ef5530110eb`; this slice
  changes only `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`.
- Implementation: GPT-5.6-luna/max. Full-diff review, integration and runtime
  evidence: primary agent; separate authority and construction audits retained.

The first scenario uses the real offline replay graph and completes declaration,
plan addition, verification start, marker attachment, resolution, reload and exact
retry. Invalid requests are rejected at the appropriate lifecycle boundary.
The second scenario checks three diff and nine analysis authority variants, then
successfully adds the unchanged valid plan. Refusals preserve both the cloned
and original graph bytes. Successful transitions preserve prior bytes and add
exactly the expected canonical event, artifact, envelope, root and directories.

The primary ran these two selectors serially on Windows/Python 3.12.10:

```text
test_public_diagnostic_caller_journey_replay_to_resolution
test_public_diagnostic_caller_journey_authority_refusals_preserve_graph
```

Run4: **2 PASS, 0 failures/errors/skips, 90.370 seconds**, exit 0, no timeout or
forced termination. All 148 product source files match the accepted repair source.
Evidence is retained under `r10/e/n95/diagnostic-journeys/run4`, including full
JUnit, output, command/environment, native raw/JSON coverage and guard branches.
Complete raw SHA256:
`FE4E6463114F8797CC93B68AD86275BB50C897496852E8834A45B3F0AF09C0A8`.

Earlier runs exposed test construction issues: unsorted changed paths, a
260-character Windows copy target, and forbidden identical before/after evidence
IDs. The final candidate uses canonical ordering, compact fixture roots, and a
distinct real analysis evidence ID. A complete constructor/first-guard audit
preceded the final retry. All three failed batch databases are excluded from
coverage; their minimum diagnostic evidence is retained. No product or hardware
regression was established by those failures.

No hardware, packaging, deployment or remote action was performed. The preceding
repeat-bind product fix and its seven PASS remain valid. Native package/core
coverage is reconciled separately without changing the frozen scope or thresholds.
