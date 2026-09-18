# Monitor evidence-contract regression execution

Contract: [evidence-contract regressions](../specs/2026-09-19-stm32tk-monitor-evidence-contract-regressions.md).
Accepted integration base: `bab6c8e8d698aa3bddd88a0d20e94a7864980633`.
Frozen product CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`.

1. Primary commits this shared contract, then creates clean isolated worktrees
   `r10/rv` and `r10/av` at that exact commit. Replay and analysis are independent
   test slices with one Luna/max owner each; no recursive delegation. The ongoing
   user's local-release authorization covers this necessary regression work.
2. Replay owner adds public import/reference, persisted authority and prefix/retry
   cases only in `test_replay.py` and `test_physical_publication.py`. Analysis
   owner adds public model/comparison/export/adapter cases only in
   `test_analysis.py`, `test_analysis_workflows.py` and `test_analysis_cli.py`.
   Reuse existing helpers unchanged. Shared production contracts remain frozen.
3. Use `r10/py/Scripts/python.exe` and absolute final `r10/verify` Toolkit/Monitor
   source roots on PYTHONPATH. Replay owns temp/cache/basetemp/COVERAGE_FILE under
   `r10/t/re` and evidence under `r10/e/replay-regressions`; analysis owns
   `r10/t/an` and `r10/e/analysis-regressions`. Set TEMP, TMP and TMPDIR together
   and record child tempfile.gettempdir(). Keep one coverage database per run.
4. Run only the affected test modules, retaining branch coverage and JUnit.
   Scoped --cov-fail-under=0 is informational, not release acceptance; do not
   change repository thresholds. Re-run only changed/failed cases after a narrow
   correction unless a concrete dependency risk requires the affected modules.
   No performance measurement during this ordinary concurrent test work.
5. Owners commit locally and return a concise report with exact accepted base,
   product head, test CodeHead before report commit, commands/results and remaining
   gaps. Replay report is `docs/codex/returns/STM32TK-1.0-monitor-evidence-regressions/replay-report.md`;
   analysis report is `analysis-report.md` in that directory. No self-acceptance,
   hardware, package, deployment, remote action or cleanup attempt.
6. A separate reviewer examines complete base-to-final diffs in clean pinned
   checkouts. Correct findings return to the same owner; two nonconverging rounds
   trigger a primary contract reconsideration. Primary integrates only accepted
   tests/reports and the verification owner combines coverage by one source
   identity. Product15b packages and unaffected tests retain valid evidence.

The running Toolkit matrix is not restarted. A read-only diagnosis independently
owns its two detected Diagnostic failures; these implementers must not silently
adjust those tests. Primary owns cleanup and preserves policy-denied roots without
retry. All broad release gates remain unchanged.

## Remaining public-contract cases after accepted supplements

The first Replay and Analysis supplements are accepted. Actual combined Monitor
coverage remains 2417/2936 branches (82.322888%); this is an unmet release gate,
not permission for private-branch or impossible-state tests. Read-only maps in
`r10/e/replay-regressions/remaining-public-gaps.md` and
`r10/e/analysis-regressions/remaining-public-gaps.md` identify public scenarios
still missing from the frozen contract. The next accepted integration base is
`39bf982af688b7653735b0de02ce75a19804c2b4`; product 15b remains unchanged.

- Replay's same Luna/max owner uses `r10/rm` and owns the two existing Replay
  test modules plus `replay-remaining-report.md`. Cover closed public document
  and reference constructors/parsers, persisted authority mismatch, coherent
  History fragment/window contradictions, and authenticated physical reload.
- Analysis has one Luna/max owner in `r10/am`, owning only `test_analysis.py`,
  `test_analysis_workflows.py` and `analysis-remaining-report.md`. Cover versioned
  request/result/lineage and publication/bundle relationships, public window and
  scalar validity, History page authority, and durable derived publication.

Both reports live in the existing evidence-regressions return directory. Shared
fixture signatures/defaults, source code, schemas, dependency direction, public
error categories and mutation boundaries stay frozen. Construct new values
through public models or closed external JSON; if an input is already rejected
by its public typed model, do not bypass that validator to force a later branch.
Use existing provider seams and assert the intended seam was reached where a
generic error could otherwise mask the case. No generic matrix generator.

Replay temp/evidence roots are `r10/t/re2` and `r10/e/replay-remaining`; Analysis
uses `r10/t/an2` and `r10/e/analysis-remaining`. Execution starts only after the
primary releases the narrow retention-diagnosis exclusive window. Then run the
owned affected modules once with recorded final source paths, all three temp
variables and distinct coverage files. Preserve accepted earlier evidence and
combine valid databases; do not rerun the full suite or change the 90% gate.
