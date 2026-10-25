# External firmware integrity regression plan

Accepted base `8e3aa106d07cbc11547d16be035a719c1f2c605f`; [design](../specs/2026-10-26-firmware-integrity-regression-design.md). The user waived a separate plan approval stop.

1. Reuse the clean isolated author worktree on `codex/firmware-integrity-regression`. Supply exact head, full AGENTS instructions, native missing-arc index and sole allowed new test file. Preserve all prior evidence.
2. Claude compares existing tests and writes meaningful non-duplicate public integrity and external filesystem-failure tests using file tools only. No shell or acceptance claims.
3. Primary reviews the complete diff and freezes CodeHead. Prepare a source-bound affected-suite manifest with verified Python 3.12.14 / pytest 8.4.2 / coverage 7.17.0. Claude executes the exact single native PowerShell verification command, at most 1,800 seconds; return first failure without automatic retry.
4. Primary independently executes the new cases plus relevant offline public callers in the clean separate review tree. Return corrections to the same author branch if required; preserve failures and stay within two correction rounds before reconsidering scope.
5. Reconcile native data with original successful matrix shards plus accepted migration supplement. Assert unchanged product bytes, coverage membership and denominators. Record actual gain, unique passed/skipped cohort, owner and source identities. Continue remaining meaningful regression gaps; do not lower release gates or adopt the v1.2.0 exception.
