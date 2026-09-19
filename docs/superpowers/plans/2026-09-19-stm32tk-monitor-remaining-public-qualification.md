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
