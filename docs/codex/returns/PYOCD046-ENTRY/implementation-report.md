# PYOCD046-ENTRY offline review report

2026-10-30 checkpoint: **REVISION_REQUIRED — independent entry review incomplete**,
no hardware executed. The selected offline tests pass; do not mark the
procedure/card independently accepted or hardware READY.
Accepted base `22f047189fbb0cf1fa7de98e86a2955eb13c5ac1`; product/test CodeHead
`694e1e912adfc017c31b52630a323bd733567688`, unchanged by this documentation slice.
Branch codex/v135-pyocd046-entry-review; Primary Codex owns source analysis,
specification/plan, procedure/card, orchestration, independent complete-diff
review and acceptance. Local Claude Code CLI owns any product/test changes
and delegated verification, retaining its current model/provider/permissions.
No product/test edit has been required; no ownership override, new dependency
installation, active-runtime replacement, hardware or remote authority.

Governing [design](../../../superpowers/specs/2026-10-30-pyocd046-entry-budget-design.md)
and [plan](../../../superpowers/plans/2026-10-30-pyocd046-entry-budget-plan.md).
The Primary source findings/budget decision are in
[source review](source-review-2026-10-30.md); the conditional, non-executable
[card](../../../testing/cards/2026-10-30-pyocd046-constructor.md) links the
actual runtime/project/source/SDK pins and missing authority/ownership gates.
Reviewed/tested documentation source before this report update:
`8123cdc04b011f590e60050d0b71298e8a902d2a`.
The prior software/hardware evidence remains at its original head/owner.

## Source decision and independent complete-diff review

Primary reviewed all six changed documentation paths in the clean exact-head
post134-independent-review checkout, including the complete base-to-8123 diff.
No product/test/helper/backend/worker/lease byte was changed. All347 candidate
SDK Python sources still match the verified official wheel; project model,
reference ELF and old lease bytes match the read-only snapshot. Actual raw
helper identity is newly pinned for this checkout's line endings; its Git blob
equals the accepted helper blob. No root-cause/USB cleanup/board-state inference.

Keep attach request5s and per-HID-read10s; preserve existing service/worker
cleanup, worker30s RPC/5s close and305s HTTP envelope. No aggregate5s/8s/15s
command bound is claimed. Constructor diagnostic remains20s+2s cooperative
only, not a production timeout change. SDK suppression/partial-open and inert
unopened close are explicit: constructor ok does not mean healthy USB. Existing
late-MODIFY attach resume/state-check/close must be included in a future
production card; this constructor card forbids Session.open and target control.

## Fresh offline tests: passed

One Claude verify invocation completed actual PowerShell-only inventory and
native harmless smoke, then all five exact commands once, with no tool error,
denial, pending result, scope/unexpected command or source edit. Existing
configured deepseek-v4.1-flash[1m] route was retained. CLI/dispatcher exits0;
native successful numeric exits remain null. Primary separately audited each
command's real pytest exit0, source/SDK/runtime/selector bindings and fresh JUnit.

| Selected existing cases | Fresh passes at8123 |
| --- | ---: |
| Real-SDK HID timeout/payload/empty response and distribution/origin guards |6 |
| Fake spawned worker late attach, unresponsive attach and hanging close |3 |
| Private-injected helper success, constructor error and surviving inert child timeout |3 |
| Distinct delegated total |12 |

Primary ran three overlapping risks in the clean exact-head review checkout:
HID empty response, unresponsive worker attach and surviving inert child timeout.
**3passed,0failure/error/skip**; delegated **12passed,0failure/error/skip**.
All source hashes unchanged; no new test source was authored or suite-wide run
claimed. Fake backends/unique temporary leases and software children do not
access the physical probe or C:/data registry. These are not native HID timing,
physical responsiveness, normal100kHz flash or release qualification.

Evidence: D:/codex-tmp/st135-p46-entry01/{verify-task.json,verify-run,
test-manifest.json,final-evidence-audit.json}; execution/log/JUnit under
D:/codex-tmp/p46e/t01..t05 and p01,p02. The audit checks exact case-name
multisets, fresh reports, actual exits and unchanged source/347 SDK sources.
Earlier504 admitted SDK-slice cases remain at their separately recorded heads;
no redundant full matrix was run for documentation.

## Independent entry review: incomplete, original evidence retained

A separate Claude verify invocation completed inventory/smoke and all18 exact
ordinary source-view commands with native matched success. There were no tool
errors/refusals, edits, tests, unexpected commands or scope deviations; native
numeric exits remain null, CLI/dispatcher0. Dispatcher accepted execution of the
listed commands; it did **not** accept the procedure's review verdict.

Primary audited effective model-visible tool content as well as structured
stdout. Seventeen packets have every numbered line and END marker matching
their pinned source. Inventory output was44.9KB and persisted/truncated by the
tool: only a2KB preview was visible; structured stdout was also clipped to30000
characters. An underlying successful process or a persisted file outside the
allowed commands does not make that content independently reviewed. No attempt
was made to read that persisted file or bypass tools. Verdict **REVIEW_INCOMPLETE**.

The reviewer found no blocking source/document inconsistency within the17
complete packets. Three evidence gaps remain:

1. Supply the entire433-line inventory and its supplemental native binding,
   environment/config and lease metadata in output-safe chunks.
2. Supply helper constant definitions for the2s cooperative wait,1s trace and
   polling interval, previously outside current excerpts (though in old full
   helper review). Do not represent reused coverage as new source viewing.
3. Supply actual parser/CLI spans for the literal card argv, rather than rely
   solely on the unchanged prior full-helper review.

The first review's non-blocking comment observation does not require product
editing: client.py:280–282 explains the maximum300s native operation plus5s
response/cleanup envelope; total305 is consistent with that context. It must
not be interpreted as a per-attach5s HTTP bound. The procedure already says305.

Evidence: review-task.json, review-run, independent-review-verdict.md and
final-evidence-audit.json under D:/codex-tmp/st135-p46-entry01. Original logs,
effective truncation and incomplete verdict remain unchanged. Coordinator
preparation range assertions/command-shape/search mistakes are retained in the
inventory supplement; none ran hardware or a product test.

## Concrete supplement and remaining authority

Prepare a new finite read-only review of four inventory chunks and one small
helper/supplement packet, with output size prechecked below the native limit.
Retain the17 complete source packets and all12+3 passing tests; no rerun of them
is required. No product fix is identified. The global AGENTS rule says
"Any retry needs explicit, bounded authorization"; the current task provided
no retry grant. The supplemental Claude call must await that authorization.

The card stays BLOCKED_NOT_EXECUTED, target UNKNOWN. Future hardware separately
needs current original-board/probe power/exclusivity/change confirmation,
fresh finite authority, real pre-run identity/config/lease checks and an accepted
entry review. No physical operation, lease acquisition/health query/deletion,
new dependency installation, installed-runtime replacement, packaging or remote
action occurred. The ordered three-item goal remains open.
