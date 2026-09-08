# STM32 Toolkit 1001 Task 8 post-flash boot and v2 terminal correction plan

**Goal:** Start the exact flashed application from reset, then let a complete protocol-v2 mailbox
run terminate at `run_end` without waiting for transport EOF.

**Accepted base:** `f8ff521922ed366e1f1f30ae99220a8ff19f693e` (tree
`f3336fb8c35679c385d15e639f94b83f01aab550`).

**Ownership:** one GPT-5.6-luna/max implementation owner; GPT-5.6-sol specification owner and
independent reviewer. The companion design was approved by the user on 2026-09-08. No hardware,
runtime, project, release, or remote action is part of this plan.

## Task 1 - clean worktree and RED

1. Create one isolated detached implementation worktree from the exact accepted base and prove it
   is clean. The sole continuation branch remains
   `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; do not create a replacement branch.
   Record tracked/untracked, committed/uncommitted, and ahead/behind state without mutating the
   existing source worktree.
2. In `test_target_runner.py`, model the physical flash result as the actual failure context: the
   target remains halted at a flash-algorithm breakpoint. Prove current ordinary resume cannot
   establish reset-vector execution. Freeze the required order: post-flash identity, reset, running
   proof or reset-halted resume fallback, then transport open.
3. Add a v2 runner RED whose mailbox returns one complete valid run ending in `run_end` and then
   forever returns empty data with `eof=False`. Prove current code reaches `TEST_TIMEOUT`.
4. Preserve the focused RED node IDs/output before product mutation. Do not invoke hardware or
   create a firmware/build fixture.

## Task 2 - admit one reset CONTROL operation in the existing Probe protocol

1. Add `target.reset` to both identical Probe request schemas as a CONTROL operation with only the
   existing authorization field and normal CONTROL timeout.
2. Add `target.reset` with empty arguments to the closed authorization store and client allowlists.
   Keep the same identity/state snapshots, five-minute record lifetime, consume-once behavior, and
   authorization error vocabulary.
3. Route `target.reset` in Probe Service through the existing backend `reset()` method. Read and
   validate the resulting closed target state. Return only the agreed closed response and reject
   reset/faulted/invalid results with existing backend errors.
4. Add protocol/client/service tests for exact empty arguments, CONTROL-only admission, state-bound
   consume, one backend reset call, running result, reset-halted result, mismatched/consumed digest,
   invalid result, timeout, and zero implicit resume.

## Task 3 - replace the post-flash resume transition

1. Replace `resume_after_flash` with one bounded adapter-owned start transition. It prepares and
   consumes reset only after flash/readback and post-flash identity proof.
2. Accept an immediate running reset result. For halted reason `reset`, revalidate the live state,
   prepare and consume a distinct resume record, and require running. Reject all other results.
3. Keep each boundary under the original absolute Target deadline. Preserve error mapping and
   cleanup precedence. No path may retry, reflash, reconnect, or open transport before running.
4. Test normal and recovery workflow composition, exact authorization bindings, event order, call
   counts, identity drift, deadline crossings, reset failure, optional resume failure, and no
   TestRun publication on failure.

## Task 4 - terminate v2 collection on run_end

1. In `TargetTestRunner.run`, track whether decoded v2 frames contain kind-5 `run_end`.
2. Process every frame decoded from the current chunk, then leave the polling loop. Do not make
   mailbox `eof` true and do not change the shared transport polling helper.
3. Retain `decoder.finish`, final transport identity, exact raw artifact ingestion, and
   `assemble_target_v2_run` as mandatory gates before publication.
4. Test complete v2/no-EOF success; missing terminal timeout; malformed, bad-digest, bad-count, and
   premature terminal failures; frames after `run_end` in the same chunk; unchanged v1/EOF paths;
   unchanged maximum-byte and deadline behavior.

## Task 5 - focused offline verification

Use CPython 3.12 and a unique external root under `D:\codex-tmp`; run smallest nodes first:

1. exact new reset schema/client/service tests;
2. exact post-flash start order and negative runner tests;
3. exact v2 no-EOF terminal and invalid-terminal tests;
4. complete `test_probe_protocol_v2.py`, `test_probe_service.py`, `test_target_runner.py`, and the
   affected normal/recovery selection from `test_physical_target_workflows.py`;
5. `git diff --check`, allowed-file diff audit, worktree status, and exact CodeHead/tree capture.

Proportionate baseline interpretation for this approved corrective slice:

- Every new test and every existing node whose behavior or assertion is changed by this slice must
  pass. The complete `test_probe_service.py`, `test_target_runner.py`, and selected physical
  workflow risk set remain passing gates.
- The complete `test_probe_protocol_v2.py` run remains required, but it is not represented as a
  full-file pass while the following three pure-code failures reproduce unchanged at both the
  exact accepted base and CodeHead in the same CPython 3.12 environment:
  `test_admitted_pyocd_adapter_exposes_closed_target_operations`,
  `test_pyocd_target_adapter_fails_closed_on_limits_identity_and_partial_output`, and
  `test_pyocd_isolates_legacy_reads_from_closed_target_observation_policy`.
- Those three results are recorded as open `KNOWN_BASELINE_FAILURE` findings, not `PASS`,
  `DEFERRED`, or implementation-owner evidence. Their failure sites are in unchanged PyOCD attach
  and target-state behavior; this slice changes only the operation matrix in that test file and
  does not change `pyocd_backend.py`.
- Acceptance requires the exact same three failure node IDs and failure signatures at base and
  CodeHead, with no additional failure. Any count/signature drift, any failure in a new or affected
  reset/start-transition assertion, or any evidence that these nodes traverse the new reset path
  blocks acceptance and returns to the implementation owner.

Do not run package, release, build, firmware, launcher, full repository, or hardware matrices.
Preserve minimum failure evidence and clean only exact run-owned disposable output after diagnosis.

## Task 6 - independent Sol review

1. Create a fresh detached worktree at CodeHead and review the complete
   `f8ff521922ed366e1f1f30ae99220a8ff19f693e..CODE_HEAD` diff.
2. Confirm both Probe schemas remain identical; reset is CONTROL-only and cannot reuse resume
   authority; the Probe operation enum change is explicit; no backend/worker/CLI/MCP/Skill surface
   changed; all failures are terminal.
3. Re-run the focused reset, start-transition, v2 terminal, and normal/recovery workflow risk set
   under CPython 3.12 with a new external basetemp.
4. Issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Hardware remains deferred even
   after software acceptance.

## Stop boundary

After review, the Sol primary may fast-forward the clean local continuation branch to the reviewed
CodeHead; any dirty or divergent state stops that update. Then stop with local CodeHead and
evidence. Do not promote runtime, modify the campaign
project, prepare/consume a hardware action, attach/read/reset/resume/flash a target, push, mutate a
PR, merge, tag, release, close, or delete a remote branch without separate explicit authorization.
