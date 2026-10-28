# POST134 usability corrections and offline flash investigation

Date: 2026-10-28. Accepted base: `7e578ca1395ffa3b9743bef5a9fe55c40912eed6`.
The user approved the preceding triage and explicitly authorized fixes 1, 3, 4+5 and 8,
plus offline investigation of 2. Primary Codex owns this specification, bounded plans,
integration, complete-diff review and acceptance. Local Claude Code CLI using the
existing model/provider/auth owns implementation, tests and delegated exploration.
No ownership override, hardware, installation, packaging, version bump, remote push,
PR mutation, tag or Release authority exists. Existing user projects are read-only.
The old Codex-subagent sentence in docs/development.md conflicts with current AGENTS.md
and is superseded; do not edit it as unrelated scope. No matching installed engineering-
lessons skill was found in the supplied skill roots.

## A. Preset-specific build evidence
Ordinary debug -> release -> debug -> release builds without clean must retain valid
incremental evidence for both supported presets. Avoid automatic clean or weaker freshness
checks. Preserve the existing debug consumer contract:
- arm-debug owns artifacts/migration/build-result.json and artifacts/migration/build.log.
- arm-release owns artifacts/migration/arm-release/build-result.json and build.log in
  that same arm-release directory.
- Existing build/<preset>/firmware-identity.json and ELF/MAP locations do not change.
- All success/failure publication, report paths, stale guidance and process diagnostics
  name the selected preset's paths. A release failure cannot overwrite debug evidence,
  and vice versa. No mutable module-global path switching.
- Context, flash, debug and Monitor remain debug-only consumers and retain their existing
  debug paths. Prove by integration tests that a release build does not hide valid debug.
- For pre-patch release builds ONLY, if the new release result path is truly absent,
  allow reading the legacy global record using its legacy artifact-path expectations
  and the existing complete same-preset identity/snapshot/hash validation. Never fallback
  from present malformed/failed/redirected canonical evidence. Never borrow a debug record
  as release evidence or synthesize lost historical debug evidence. Successful release
  builds publish only the new release paths. A preexisting legacy release global record
  may still require the established one-time debug clean remedy if debug evidence was
  already lost; disclose this migration limitation, do not pretend to recover it.
- Preserve schema 1/2 validation, input/artifact integrity, path/reparse checks, lock,
  bounded process behavior and no-hardware boundaries.

Evidence: new switching/refusal regressions for both Git and snapshot provenance, failure
isolation, legacy release fallback and invalid canonical refusal; applicable build runner,
stale guidance, snapshot, context and managed firmware-admission regressions. Include one
real GCC synthetic-project debug/release/debug incremental journey; flash is simulated.

## B. Safe CLI flash-region diagnostics
Keep exit code 2 and no echo of arbitrary caller values for grammar errors. For
--flash-regions emit bounded fixed diagnostics identifying JSON/list/item shape, required
start/length fields, duplicate fields and integer types (bool is not int), including a
bounded item index where meaningful. The schema stays exactly 1..32 objects with start
and length integers; range/security validation remains in its existing layer.
Help must show schema plus one example. Do not globally restore argparse's raw message.
Unrelated argument failures remain sanitized. Exercise actual public CLI parser including
the supplied origin/name shape, valid schema, malformed/duplicate/type cases and payload
redaction/control characters. No hardware/backend calls.

## C. Migration/debug handoff guidance and release documentation
Keep migration build-only and debug:{} valid, without inferred backend/target or hardware.
Destination PLAN and successful APPLY results expose the shared post-migration
debugConfiguration shape (status, missingFields, diagnostics, nextSteps, non-blocking)
and readable followUp retains its string type. Include the existing project configure
dry-run command with --debug-backend pyocd and user-chosen --debug-target, then exact-plan
apply, before build/flash identity is established. Explain binding the destination root.
Surface the actual handoff flow: handoff-begin yields data.cortexDebugLaunch.configuration;
use it in an independent external IDE workspace, detach, then end with the original ticket.
Do not write a static bypass launch configuration, persist tickets, change generated
launch.json, automate actions or change authorization. Explain why launch.json is empty.
Reuse the shared debug guidance rather than conflicting command copies where practical.
Check deterministic PLAN/apply and CLI/MCP exposure without additional hardware calls.

In CHANGELOG v1.3.4 add the already-implemented version alignment and 1.3.3 supported
legacy runtime/producer recognition, preserving explicit Repair/configure and old refusals.
Clarify that frozen v1.3.4 package documents retain their build-time candidate status,
where current release status/Release notes record publication. Do not rewrite published
assets/tags or claim these local corrections are in v1.3.4 released bytes. Add an Unreleased
entry for actual local corrections after integration and update relevant user guide only.
No behavioral changes to memory margin, ABI inference or encoding discovery.

## D. Flash investigation, offline only
Retain supplied fresh-flash-1.json and v130-test/flash-2.json / flash-3.json as read-only
evidence. Trace normal versus recovery options, session/target initialization, flash
algorithm invocation, error mapping and cleanup using pinned source/evidence.
Separate facts, hypotheses, missing evidence and any future finite discriminating
experiment. In particular 1 MHz vs 100 kHz and normal vs under-reset are independent
variables; do not infer a frequency fix from combined recovery success. Do not claim
IPSR alone proves root cause. No probe discovery, connect, flash, reset, halt, resume,
installation, network downloads or new hardware tests. Documentation and offline fake
contract tests may support the report; no product flash behavior changes in this slice.

## Acceptance and boundaries
Read standard-test-procedure.md and its current referenced report before checks.
Each slice has one clean worktree, exact allowed/read files, file-only edit run and a
separate native PowerShell verification run with exact commands. Dispatcher inventory and
verify smoke must pass; inspect all native events, retain abnormal runs and null native
exit codes. No blanket retries. A correctable code finding can receive a specifically
scoped correction, with at most two rounds per issue. No permission/tool-denial bypass.
Primary reviews complete base-to-CodeHead changes in a clean exact-head worktree and
independently runs proportionate affected checks. Record owner, argv, source, result,
limitations and code-head before report commit. Offline acceptance is not release or
hardware qualification.
