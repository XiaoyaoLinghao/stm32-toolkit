# Release fixture portability execution

Contract: [fixture portability](../specs/2026-09-19-stm32tk-release-fixture-portability.md).
Accepted base: `47988d34725f97075d3ea69a43a65cb5b2144189`.
Product CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`.

1. Primary commits this plan. The existing release fixture Luna/max owner uses
   clean isolated `r10/lf`, branch `codex/STM32TK-1.0-legacy-fixtures`, at that
   exact commit. It owns only the contract's files and
   `docs/codex/returns/STM32TK-1.0-local-release/legacy-fixtures-report.md`.
   No recursive delegation or overlapping writes. Preserve other workers' work.
2. Reuse the existing diagnosis and 79-row node extraction under
   `r10/e/python-release/toolkit`. Do not explore the same diagnosis again.
   Correct only the frozen fixtures, private self-test seam and two stale tests.
   Tests must not depend on a local historical Git object at runtime; the two
   tracked launcher fixtures carry their origin and verified blob identity.
3. All temp/cache roots are under short `r10/t/lg`; evidence is
   `r10/e/legacy-fixtures`. Use `r10/py/Scripts/python.exe`. Bind TEMP/TMP/TMPDIR,
   remove all COVERAGE_*/COV_CORE_* and inherited PYTEST_ADDOPTS, use -p no:cov,
   and retain expanded argv and per-group JUnit/stdout/stderr/exit. Reuse
   `r10/ui-support/node_modules` only after graph verification and
   `r10/t/alloc/feas0/support` only after complete manifest verification.
4. Implementation and metadata preparation may proceed during retention
   diagnosis; no test, browser, build or dependency copy runs until primary
   releases that exclusive window. Run the four diagnosed groups separately,
   plus the two stale nodes and seam guard checks. Stop and classify each new
   cause before retry; no full-suite restart. No coverage aggregation is claimed
   for intentionally uninstrumented controller checks.
5. Commit implementation/tests locally and report the tested head before the
   report commit, actual outcomes and remaining limitations. Primary reviews
   the complete accepted-base-to-final diff in a clean checkout and verifies
   all shipped product inputs unchanged before retaining artifact/deployment
   evidence. No push, PR, merge to master, tag, Release or cleanup attempt.
