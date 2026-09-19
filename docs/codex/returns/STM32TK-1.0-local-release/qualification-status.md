# STM32 Toolkit 1.0 local qualification status

Status: **NOT ACCEPTED**. This is a release qualification status, not a new
hardware acceptance, publication approval, or a replacement for historical logs.

VS10-A and VS10-B remain locally accepted. The B acceptance base is
`1df30a0f4070805488687a67f907dbaa1867d681`. Retained artifacts were built from
`15b1a70e9bd684285da5557104deff529f537e49`. Runtime package source remains
byte-identical to that revision. Later qualification tests and the accepted
deployment-guide/trusted-utility-pin correction are not in that source ZIP.
No replacement artifact or deployment is claimed by this document.

The Diagnostic public-refusal slice was independently accepted from
`04bdd539597ec8dcb38bca34eb2256e970ecaa25` to
`4a39eb1cb96b1f674adef77461810842d9e6043f`. Its final 15 cases passed against
the frozen product. The primary complete-diff verdict is retained at
`r10/e/diagnostic-public-refusals/independent-review-final.md` beneath the
local release root `D:\codex-tmp\v10b-0918`.

The current original-order named backend performance run passed: append p95
25.0313ms, query p95 42.3386ms, export p95 1638.8022ms, retention p95 322.4248ms,
and retention ticker maximum 16.4967ms. Actual D-drive execution provenance and
independent qualification are in `r10/e/performance-final-followup`. The stdout's
old C-drive command text was not executed; it is a retained report-field defect.

The earlier retention failure remains unresolved: the caller timed out after
180ms, a worker interruption followed, and 512 values were durably deleted.
BUSY does not promise rollback after a write starts. The failed stage is still
unknown; the later passing run does not establish a repair. No timeout increase
or another blind benchmark repetition is approved by this status.
After the controlled cancellation checks and independent disposition review,
primary specification commit 02fdee1ee4881abb69bd31b9c8d323d943f8a4b9 retains
this as `KNOWN_TIMING_LIMITATION_ROOT_CAUSE_UNKNOWN`, replacing only the
historical administrative blocker. The current named 3+20 performance gate
passed without changing its per-call assertions or thresholds. Final release
limitations must disclose the historical uncertainty and post-start BUSY
semantics. See `r10/e/retention-cancellation/release-disposition-final-review.md`.

Python package branch coverage remains below the approved 90% gate. The native
aggregates currently record Toolkit 10824/13564 (79.7995%) and Monitor 2491/2936
branches. The accepted TestRun publication and regeneration raw coverage was
combined once in toolkit-aggregate-r4, without rerunning tests. A separately
accepted earlier official Diagnostic JSON projection retains a Toolkit lower
bound of 10830/13564 (79.8437%); it has not been recomputed with r4, and its
increment must not be added without checking overlap. Monitor r7 is 2491/2936
(84.8433%). The Diagnostic projection is supplementary
JSON evidence, not a native coverage database: the implementer deleted the raw
Diagnostic database before primary aggregation. No raw database has been
fabricated or restored. Future raw coverage and shards
are durable evidence subject to primary-only cleanup and a preservation hold.

The four regeneration public cases are independently accepted at code
ab3e3fef43af7146a743319e477e7a4d352384e5 and report
b79f8dcd1bd2a9fbc83937dc4ae3c43aa64396b1, integrated at
af7e54ce9dc53f5ae609983ba35a85c2aa81a18e. They prove IOC drift refusal,
valid candidate target mismatch refusal, configuration failure preserving the
destination, and real rollback after forward activation failure. Their r2
evidence is 4 passed with actual exit 0. The earlier pre-body authorization
failure is retained as a path-boundary environment result; its native exception
was not captured and is not inferred from a different run.

The three Monitor lifecycle cases were accepted and integrated, with their raw
coverage included once in the current aggregates. The retention cancellation
qualification is now independently accepted at final report head
53f47b2b0236aacbd0a0d2c0806d9f4cdd78cfcb and integrated at
163d3446e4f663eeb6326026f126ea502df026d1. Its r3 run passed both controlled
SQLite cases with actual child exit 0, complete cancellation/exception graphs,
consistent durable accounting and public queries, writer reuse and settled
cleanup. The post-commit case preserved its deletion; the pre-commit case
rolled back. This confirms the bounded cancellation contract, not the cause of
the historical large-run timeout. Its accepted r3 raw coverage was combined
with Monitor r6 into r7 without rerunning tests; both source inputs remain
unchanged. Failed earlier retention runs are excluded.

The earlier retention runs remain separately attributed. The first omitted
the actual writer outcome; r2 reported one pass and one failure at an
internal-exception identity assertion. Its callback native leaf was not
captured, and its PowerShell PID variable error invalidates the child-exit
manifest. Neither r2 corruption nor its native cause is established; retain
the JUnit/stdout without aggregating that run or repeating the benchmark.

The release delivery audit found two portability omissions: standalone
PowerShell installation examples and unambiguous archive-relative instructions
for finding the IDE guide. The bounded correction was independently accepted and
integrated at 45b09455f469a423a45ee933d575364a8b5bf040. Separate Check, Bootstrap
and Repair examples preserve host-adapter paths and legacy upgrade semantics.
The final artifacts will need one refresh;
the existing 15b artifacts and deployment checks remain retained evidence, not
artifacts of the corrected candidate. No runtime or hardware change is implied.

The original full Toolkit suite was not a clean pass. Scoped accepted corrections
and their retained successful checks do not rewrite its historical output. In
particular, the original continuation failure's native cause remains unknown.
The later covered isolated run in r10/e/continuation-covered/r3 now directly
captures a current Windows lock defect: the existing concurrent checkpoint
test failed at line 1540, with one OK result and one integrity error. The first
caller reached post-publication result authentication at
acceptance/recovery_workflows.py:3364. Its msvcrt.locking(LK_LOCK, 1) call at
diagnostics/store.py:384 failed after 9.110 seconds with OSError errno 36,
Resource deadlock avoided. The other same-process caller released and reacquired
the same lock during that interval. The catch at store.py:396-397 maps the
lock error to DIAGNOSTIC_CHAIN_CORRUPT, and recovery_workflows.py:204-205 maps
it to ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED. The observed native error
does not establish evidence corruption or a cyclic deadlock.

That run exited 1 normally (105.351 seconds in pytest); its complete lock
timeline and exception chain are retained. The two earlier launcher attempts
failed before creating a test child and remain infrastructure evidence. No
product correction, diagnostic rerun or hardware operation is claimed. Next
product scope is the same-workspace DiagnosticStore lock coordination and the
existing concurrent checkpoint contract; preserve lock identity validation,
cross-process exclusion, publication order and completed-result authentication.
The bounded correction is now specified at a6e3888c35af853ce571c58036b063a69be409fd
and assigned to one Luna/max owner. It adds narrow native contention retries,
explicit Busy propagation including nested Diagnostic results, and a regression
for Busy after revision-1 publication. Implementation is not yet accepted.

Valid UI, browser, deterministic packaging, isolated fresh/upgrade deployment,
state-preservation, workspace-composition and A/B hardware evidence are retained.
Do not repeat them solely for test/report changes. New verification is limited
to meaningful uncovered public contracts and discriminating failure hypotheses;
the mandatory release coverage requirement is the reason for this qualification
work, not a reason to invent tests for impossible private states.

No push, PR mutation, merge, tag or release is authorized by this status.
