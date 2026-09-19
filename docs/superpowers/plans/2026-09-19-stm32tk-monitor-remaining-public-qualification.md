# Monitor public qualification execution plan

Implementation baseline: 87699308535bd36431c2e44be8bf131e245d460d.
Specification: ../specs/2026-09-19-stm32tk-monitor-remaining-public-qualification.md.
The primary owns integration, scheduling, independent acceptance and cleanup.
All runtime bytes must remain equal to the frozen baseline. No remote action
is authorized. Current Toolkit matrix owner is /root/final_python_qualification;
that sole verification process keeps priority until its terminal result.

## Independent implementation responsibilities

| Slice | Luna/max worktree and branch | Exclusive test ownership | Durable evidence |
|---|---|---|---|
| Replay persisted authority | r10/q1; codex/STM32TK-1.0-replay-authority-qualification | tools/stm32-monitor/tests/test_replay.py and test_physical_publication.py | r10/e/monitor-remaining/replay |
| Analysis public models/scalars | r10/q2; codex/STM32TK-1.0-analysis-model-qualification | tools/stm32-monitor/tests/test_analysis.py | r10/e/monitor-remaining/analysis |
| Derived publication/export | r10/q3; codex/STM32TK-1.0-derived-publication-qualification | tools/stm32-monitor/tests/test_analysis_workflows.py | r10/e/monitor-remaining/publication |

Each owner may add only its own short report under
docs/codex/returns/STM32TK-1.0-monitor-remaining-public-qualification/ with the
matching slice name. Do not change existing shared fixture signatures, cross-
import another owner's new test helpers, production modules, dependencies or
coverage configuration. Preserve others' work and do not recursively delegate.

Use the current final coverage JSON and remaining-gate-feasibility.md together
with existing accepted test helpers. Specify each added parameter's missing arc,
public trigger, expected public code and state assertion in a compact table.
Omit an already tested variant instead of duplicating it for a new test name.
The baseline-to-return diff is the review authority, not the table alone.

## Current wave: implement and inspect only

Create separate branches at the specification/plan commit based on the named
baseline. Workers implement their bounded scenario families and perform AST
syntax inspection. They must not run pytest, collect-only, package imports,
builds or installers while the Toolkit matrix is active. Return the committed
test head, changed paths, concise variant map and syntax outcome. Label test
execution NOT_RUN; do not write PASS from static review.

If public reachability requires an undefined product behavior or an impossible
internal state, report that precise boundary rather than expanding ownership.
Product failures from the running matrix may cause primary to revise dependent
work; no worker independently rewrites the shared public contract.

## Later serial verification and integration

After the current matrix is terminal, primary classifies its failures before
choosing the executable source identity. Each implementation owner then runs
only its newly added/changed nodes in one bounded batch. Reuse the existing
selected-node pytest and owned-child launch pattern; prepare actual commands,
paths and hashes before execution. Existing entries contain historical fixed
selectors and evidence roots, so any run-local adaptation changes only the
selected nodes, frozen source identity and fresh D-drive outputs. Do not edit
old evidence or build another controller. Temp roots are r10/t/mq/r, a and p;
evidence roots are the table above. All raw files remain under preservation hold.

No automatic retry follows a failed batch. Classify product, fixture,
environment or report failure and preserve the full first evidence. Retain
passing nodes and rerun only a justified corrected remainder. Independent
reviewers inspect each full baseline-to-final diff and actual outcomes before
primary accepts integration. Runtime equality permits reuse of already valid
release evidence; final artifacts stay deferred until qualification settles.

The scope may span three parallel implementation owners, but verification is
serial and each stateful run has one owner. No count of added tests or written
reports is a release acceptance claim; only measured public behavior, valid
native branch data and the unchanged mandatory gates decide completion.

## Proven transcript publication mapping defect

Accepted runtime base is `87699308535bd36431c2e44be8bf131e245d460d`; the implementation owner starts at q1 `e4ce6d7d5e0737a9dc05cd7dd924e67a7b28ca4c`, whose first selected run is retained as 7 PASS / 1 FAIL. Primary accepts the independent PRODUCT classification: contradictory ArtifactRef is validly constructed, detected at replay.py:1209-1213, and incorrectly caught by the generic exception wrapper at :1216-1219.

1. The sole Luna/max implementation owner audits q1 tracked/untracked state, takes the appended specification, and changes only replay.py transcript exception mapping plus focused test_replay.py cases. Preserve the original failed assertion. Include a valid-model contradictory provider return, a real direct OSError, and a wrapped EvidenceValidationError with a non-missing OSError cause. Assert exact error/cause and absence of newly published roots/History, not merely that an exception occurs. No bypass of dataclass invariants.
2. Primary independently reviews the complete accepted-runtime-base-to-final-head diff in isolated q1r, including retained test-only changes. No self-acceptance by the owner.
3. First execute only the original failing parameter and newly added I/O regression parameters once. After PASS, run the affected existing test files `test_replay.py`, `test_physical_transcript.py` and `test_analysis_workflows.py` against the same returned source, with native branch coverage and bounded existing launcher. Reuse those fixtures; do not add a framework or rerun the full Python/UI matrix. Exact file availability and selectors must be checked before dispatch; launcher selectors should name parametrized functions rather than guessing generated IDs.
4. Because replay.py bytes change, old replay.py coverage arcs are excluded from the final native merge; other source-equal files retain their measured evidence. Primary reconciles the actual denominator and refreshes candidate identity. Packaging remains pending qualification. No hardware or remote action is necessary or authorized by this correction.

Keep failure evidence, unchanged prior seven successes, and the separate Analysis batch PASS. Publication's zero-test bad-selector result is an entry defect and has its own command-only correction; it is not this product defect.
