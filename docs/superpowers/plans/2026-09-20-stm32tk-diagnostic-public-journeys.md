# Diagnostic public journeys implementation plan

Accepted base: `569de655ab28fedff5e23d4f26cb604ddc0eecdc`.
Specification: same-date Diagnostic public caller journeys. Ongoing approved
core-public-contract qualification authorizes these offline implementation
tests; no new external or hardware authority is implied.

1. One Luna/max owner implements only test_fix_verification_workflows.py in
   clean `D:\codex-tmp\v10b-0918\r10\c107d`, branch
   `codex/STM32TK-1.0-diagnostic-public-journeys`, created at this plan commit.
   Use exactly two new journey selectors, at most two real graph constructors,
   and the finite variants in the specification. No existing test/helper edits.
2. Static checks only by implementer: AST, diff-check, installed Ruff no-cache
   F821; no product import, pytest, coverage, hardware or cleanup. Return exact
   Git HEAD, selectors and public-prefix/first-guard map. Other agents are
   present: preserve their changes and do not write outside owned files.
3. Primary reviews the complete accepted-base-to-candidate diff in a clean
   review worktree. Resolve construction/first-guard defects with the same
   owner. No weaker assertion, changed expected code, fake reader or scope
   expansion merely to make a candidate pass.
4. Primary alone executes the two selectors serially with the existing bounded
   native launcher after source identity and environment preflight. Reserve
   600 seconds total (two real constructors plus 12 authority clones and the
   lifecycle journey); first failure stops, no automatic retry. Record actual
   fixture/call durations, exact public wire results and immutable-byte oracles.
   Approved roots: r10/t/dj1 and r10/e/n95/diagnostic-journeys/run1.
5. Product recovery repair may proceed independently in its owned source/test
   files. No concurrent pytest; before integration reconcile source identity
   and any changed-file coverage invalidation explicitly. Accepted historical
   hardware and unrelated checks remain retained. Failed batch raw is excluded;
   preserve passing functional results without rerunning solely for coverage.
6. After complete PASS, main locally integrates and uses the existing native
   union helper once with other accepted data. Do not claim coverage gains from
   static case counts. Package90 and preferred core95 remain separate from
   scenario acceptance and seven pending native Windows checks.

Main owns evidence retention and attributed cleanup. Preserve required failure
evidence; never retry a policy-denied root deletion. No remote, package, deploy,
new framework, external capability probe or recursive delegation is authorized.
