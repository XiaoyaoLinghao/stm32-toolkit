# Normal100kHz entry review plan

Base `65e5b637069342b2472fad50fcf771801e7337c8`, branch
codex/v135-normal-flash-entry. Governing
[design](../specs/2026-10-30-normal-flash-entry-design.md). Primary owns planning,
procedure/card, orchestration, complete-diff review and acceptance. Local Claude
CLI owns independent delegated review and any later bounded implementation/tests,
retaining its configured route. No hardware/install/remote/retry authority.

1. Read maintained procedure/current report and reconstruct ledger. Preserve
   constructor PASS only at its original scope. Use source reads, current
   SDK/runtime hashes and pure firmware admission/parser observation, not CLI main
   or backend/worker execution. Exact expected pins/segments are in
   D:/codex-tmp/st135-normal-flash-entry/firmware-observation.json; request-count
   arithmetic is explicitly corrected by firmware-observation-reconciled.json.
2. Primary freezes source analysis, actual normal-flash card and procedure update.
   Separate SDK-intrinsic polling/reconnect/algorithm controls from external
   retry/recovery. Bound positive and failure criteria; record the candidate
   program+cleanup diagnostic loss as a blocker, not an assumed pass.
3. Prepare output-size-bounded hash/line-number source packets. Two separate fresh
   Claude verify review tasks cover public CLI/workflow/lifecycle/IPC and backend/
   SDK programming/reset/readback. Exact read-only PowerShell commands only,
   maximum18 commands per invocation, no tests or writes. Each printed packet is
   below18000 UTF-8 bytes including Windows newlines; no persisted-output fallback.
   Include constants, parser and all helper dependencies in the fixed read set.
   Actual inventory must be PowerShell only and native harmless smoke must execute.
   Failure/refusal/pending/scope issues stop that invocation; no automatic retry.
4. Primary audits every effective model-visible line/END marker, tool pair and
   native result (numeric exit may be null). Combine the two domain verdicts,
   independently review the entire documentation diff in a clean exact-head tree
   and reconcile existing evidence without unnecessary reruns. These are source
   checks, not test passes. No code or test edit is initially delegated.
5. If review confirms a necessary product correction, record exact public behavior,
   allowed files and proportionate checks before a separate Claude edit/verify
   task. Do not execute a defective entry or disguise a software finding as a
   platform deferral. Current task's entry gate stays REVISION_REQUIRED until a
   required correction is implemented and independently verified.

2026-10-30 execution: original tasks completed14/15 authorized reads, then
requested nonexistent unlisted A12/B13 and were stopped after permission
refusals. Both remain REVIEW_INCOMPLETE. The user allowed one bounded supplement:
26 complete packets supplied in the task, no main tool calls/edits/tests. That
grant is consumed. Public verdict REVISION_REQUIRED; backend/SDK ordering
NO_BLOCKERS within excerpts. Primary reviewed both assistant messages and
reconciled missing helper/constants and incorrect proposals. No product fix in
this preparation task. The completed blocked card is not READY: capture fix,
offline regression and independent entry recheck remain mandatory.

Primary documentation paths: this plan, design, standard procedure,
docs/testing/cards/2026-10-30-normal-100khz-flash.md,
docs/codex/returns/NORMAL-FLASH-ENTRY/source-review.md and implementation-report.md.
Run-local source readers/task/evidence under D:/codex-tmp are orchestration only,
not added product automation. No new full regression/package/deploy cycle is
triggered by documenting the entry. Future hardware needs separate finite
authorization and current original-board/probe readiness plus source/runtime/
firmware/output/lease gates; existing constructor authority is consumed.
