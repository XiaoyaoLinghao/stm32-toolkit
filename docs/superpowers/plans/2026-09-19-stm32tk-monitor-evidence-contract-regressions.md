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
