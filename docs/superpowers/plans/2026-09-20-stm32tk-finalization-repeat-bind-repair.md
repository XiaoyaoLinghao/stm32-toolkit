# Finalization repeat-bind repair plan

Accepted integration base: `6ea381515457bf4705682b0d812e8a6026e9354d`.
Governing specification: same-date finalization repeat-bind repair.

1. Continue with the same Luna/max owner and c106r worktree; preserve existing
   qualification candidate f63bf9fba3f256f7463213af7411966f834f5071. Bring only
   this spec/plan commit into that tree. Ownership expands by the approved
   goal's product-fix authority to recovery_workflows.py and the existing owned
   test_acceptance_finalization.py. No other product/test file changes.
2. Resolve persisted proof ID only for the deliberately unbound association,
   validate with existing public evidence/typed proof reader, preserve pinned
   associations, parent/identity checks, D->E lock ordering and read-only history.
   Report the exact complete wire on failed success assertions in the journey.
3. Luna performs AST, Ruff no-cache F821 and diff-check only; no pytest/import,
   hardware, deployment, cleanup or remote. Return exact Git SHA and diff map.
   Main reviews in r106r and obtains an independent focused contract/code check.
4. Main sole executor runs one bounded regression batch, first failure stop,
   900-second wall limit, using the existing native launcher at new run2 roots:
   t/rw2 and e/n95/public-recovery/run2. Selectors in test_acceptance_finalization:
   test_public_finalization_workflow_journey;
   test_finalization_persisted_round_trip_and_exact_explicit_retry;
   test_expired_attempt_retry_and_fresh_uuid_proof_reuse_lifecycle;
   test_b_authority_graph_rejections_use_persisted_proof_and_context;
   test_same_uuid_two_authenticated_reuse_proofs_cannot_cross_return;
   test_commit_timestamp_is_sampled_after_begin_authority_recheck.
   Add at most one bounded public existing-proof refusal selector if required
   by the focused review. Clear external VS10B fixture overrides and preserve
   source hashes, full stdout/JUnit, raw/shards, actual durations and exit.
5. Correct unexpected failures only after classification; no blind retry.
   Keep run1's continuation functional PASS and all diagnostic failure evidence.
   Integrate only after required regression and independent diff acceptance.
   Reconcile changed-file native coverage once with the independent Diagnostic
   journey batch; never relabel historical union20 as current product coverage.

Main owns cleanup. t/rw-static is held after actor-reported policy rejection;
do not retry. No new hardware/platform permission request is needed for this
offline product repair. The existing seven Windows checks remain pending.
