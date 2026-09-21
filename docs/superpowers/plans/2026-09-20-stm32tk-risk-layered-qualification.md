# Risk-layered qualification implementation plan

Accepted base: `4bb612beabfdaf1ab4c845b966061832add38482`.
Specification: [risk-layered qualification v2](../../superpowers/specs/2026-09-20-stm32tk-risk-layered-qualification.md).
Primary owns dispatch/integration, shared test configuration, evidence aggregation
and cleanup. Luna/max agents implement tests in disjoint clean worktrees. No
product source, shared fixture, lockfile or coverage configuration changes are
delegated. Product findings return to primary for a bounded design decision.

## Execution waves

1. Run the existing generic-recovery remainder as one finite current-source group
   (21 functions; parametrized case count comes from JUnit), excluding the three
   already current-source PASS functions/13 cases. Existing launcher with fresh
   evidence/temp roots, 600-second budget, first failure stops. Then qualify the
   four existing continuation and five software physical-protocol selectors as
   one 300-second group if their current fixture prerequisites are valid.
   Exclude the routing-only dispatch mock and the CubeMX profile test whose
   SimpleNamespace project factory has no current-source qualification. Retain
   their historical scope; neither establishes a real identity-chain PASS.
   These checks do not depend on changing the coverage denominator.
2. Independently review the frozen v2 scope. Three Luna/max owners may then
   supplement distinct test families in parallel. First return a compact case
   matrix (entry, valid factory, supported variation, first guard, observable
   invariant, owner, and retained/new/uncovered disposition); main
   resolves overlap/contract ambiguity before implementation. Reuse accepted
   tests and identify true remaining behaviors, not a test per uncovered arc.
3. Review each complete accepted-base-to-test-head diff. Integrate accepted test
   commits locally. Run new coherent selector groups once with isolated roots;
   timing, process-global/shared-state and integration checks run serially.
   Combine complete passing native databases once per coherent wave, with
   current-source identity checks and an independent data review.
4. Report measured gaps and remaining critical behaviors. Test counts or document
   changes are not product progress. Release remains unaccepted until mandatory
   gates and named native/artifact evidence are complete.

## Disjoint implementation ownership

| Owner | Worktree | Test-only file scope | Behavior |
| --- | --- | --- | --- |
| Luna/max A | `r10/v2a` | `test_risk_recovery_contracts.py` in Toolkit tests | Diagnostic/recovery persisted integrity, supported availability failures, idempotency/CAS |
| Luna/max P | `r10/v2p` | `test_risk_project_probe_contracts.py` in Toolkit tests | Project rollback/write ownership and probe provider lifecycle/settlement |
| Luna/max M | `r10/v2m` | `test_risk_monitor_contracts.py` in Monitor tests | Analysis/replay authority, history/export and lifecycle |

Test files may import existing reusable factories without changing them. If an
existing module must instead be extended, primary reassigns its entire ownership
before edits. No agent changes conftest or generic infrastructure. Each returns
one coherent diff and exact selectors, source pin and evidence; it cannot accept
its own work. Main reviews all diffs; independent reviewer handles risk/contract
questions and native data. Subagents do not recursively delegate.

All roots above are children of `D:\codex-tmp\v10b-0918`. Test temp/cache roots
are `r10/t/v2a`, `r10/t/v2p`, `r10/t/v2m`; evidence roots are
`r10/e/risk-v2/a`, `/p`, `/m`. Set TEMP/TMP/TMPDIR, pytest basetemp/cache and native
coverage paths before Python starts. Main is sole cleanup owner. Retain raw
evidence and minimum failures; never retry previously policy-denied deletion.

## Acceptance and reuse

Required for each batch: meaningful assertions, no hardware access, complete
terminal PASS, exact source/candidate/command, diff review and source-qualified
native coverage. Targeted lint only on changed tests. No whole-release rerun for
test/report changes. An environment/platform barrier is recorded, not repaired
by weakening an assertion or faking capability.

Already accepted VS10-A/B, attempt7, UI, unchanged product verification and
current-source finalization7/Diagnostic2/generic13 remain valid within their
original bounds. Seven native Windows checks, final artifact/deployment and
release acceptance remain pending. No package, deployment, hardware or remote
action belongs to this offline wave.

## Critical behaviors retained in this wave

Evidence owner for this table is primary; A/P/M are maintenance owners, not
attribution of the original run. `e/python-final/{toolkit,monitor}/junit.xml`
records the named PASS cases at `87699308535bd36431c2e44be8bf131e245d460d`.
The context, migration, DWARF, auth, service and runtime product files below
are byte-identical in Git at the accepted base. Test additions since that run
do not delete or alter the named existing tests. These are retained module
conclusions, not a rerun or a claim that every later cross-module combination
passed. Changed recovery/replay/configuration/environment evidence stays under
its separately accepted current-source qualification.

| Owner / status | Public entry and legal setup | Variation / first guard | Observable assertion / existing selector |
| --- | --- | --- | --- |
| P / retained | `build_project_context`; `prepare_project` plus successful build | Change persisted buildId; `_evidence_fresh` manifest/identity match | `elfFresh` false; `test_context_stale_after_identity_tampered` |
| P / retained | `plan_keil_conversion` then `apply_keil_conversion`; `build_repo` with real C source | Unsupported pragma; `scan_sources` produces blocker and apply refuses | `MIGRATION_BLOCKED`, exact blocker codes, full tree unchanged; `test_apply_blocked_plan_refuses_without_writes` |
| P / retained | Same plan/apply path; valid `standard_repo` plan | Alter proposed bytes with recomputed plan ID; apply patch digest validation | `MIGRATION_PLAN_INVALID`, `patchDigest`, tree unchanged; `test_apply_forged_after_bytes_with_consistent_plan_id` |
| P / retained | `DwarfCatalog.from_binding/revalidate`; real ELF fixture and valid binding | Append ELF bytes; bound file size/digest guard | `DWARF_INPUT_CHANGED` then `DWARF_PROVENANCE_MISMATCH`; `test_catalog_construction_and_revalidation_reject_changed_evidence` |
| P / retained | Valid catalog and binding | Different binding; exact binding guard | `DWARF_PROVENANCE_MISMATCH`; `test_revalidation_requires_the_exact_binding` |
| P / existing assertion mapped | `DwarfCatalog.from_elf().lookup`; fixture with limited readable regions | Symbol outside allowed region; final address-range guard | `DWARF_ADDRESS_OUTSIDE_READABLE_MEMORY`, no hardware provider involved; `test_address_must_be_inside_explicit_readable_regions` |
| M / retained | `MonitorAuth.authorize`; valid loopback auth fixture | Wrong token/origin; auth boundary | Authorization refusal; `test_bearer_auth_accepts_exact_loopback_origin_and_rejects_wrong_token` |
| M / retained | Real HTTP `MonitorService`; `_with_service` valid fixture | Bad Host/Origin or target override; request authentication/closed body guard | HTTP 403/403/400 and runtime calls empty; `test_host_origin_and_forbidden_identity_overrides_fail_closed` |
| M / retained | `MonitorRuntime.start/stop`; supported controlled service dependency | Repeated cancellation during stop; owned shutdown settlement | stop once, runtime record absent, replacement can acquire lock and stop; `test_repeated_cancellation_cannot_interrupt_owned_shutdown` |

The remaining A/P/M matrices add only distinct valid contract scenarios; they
must be frozen for each independent line before its test implementation. A scenario with no new valid
case may return “retained/no new test” instead of manufacturing a branch target.

### M line frozen supplement

Primary reviewed M-01/02/03/05 against the real implementation; M-04 reuses the
existing export-authorization conclusion and does not add a duplicate test.
The independent scope review confirmed Monitor's unchanged whole-file scope.
These tests do not depend on a new denominator and may proceed while A/P finish
preparing their disjoint matrices. No v2 acceptance is implied.

| ID / owner / disposition | Public entry and valid setup | Variation / first guard | Required assertion |
| --- | --- | --- | --- |
| M-01 / M / new | `analyze_monitor_windows`; canonical two-position windows rebuilt through public SampleBatch/reference factories | Empty scalar type; `_trusted_sample` type length guard (non-NFC input is blocked earlier by replay canonicalization and is not targeted) | INVALID/INCONCLUSIVE/INSUFFICIENT_VALID_PAIRS, one aligned and one excluded position; inputs unchanged |
| M-02 / M / new | Same entry and valid windows | Wrong request type; `type(request) is AnalysisRequest` guard | ANALYSIS_REQUEST_INVALID and exact message; inputs unchanged |
| M-03 / M / new | Valid `AnalysisBundleRef.to_dict` payload passed to `from_value` | Nested artifact None/list; ArtifactRef decoder then public exception translation | ANALYSIS_WORKFLOW_INVALID, exact public message, input unchanged; no claim of reaching the later constructor guard |
| M-05 / M / new | `ProbeSession.revalidate/prepare_read_plan/read`; supported observation factory and real admission | `_read_prepared` provider raises CancelledError; cancellation handler invalidates current plan | Cancellation propagated, plan/admission cleared exactly once, no retry/fallback or stale-plan reuse |

### P line frozen supplement

Primary reviewed P-01/03/04/05 against the actual apply/ProbeService guards and
nearest retained tests. P-02 (read-only missing-manifest conversion) is prepared
but not selected. The scenarios operate independently of core reclassification.

| ID / owner / disposition | Public entry and valid setup | Variation / first guard | Required assertion |
| --- | --- | --- | --- |
| P-01 / P / new | `apply_project_configuration`; existing real project/plan factory | Directory fsync fails after a real destination replacement; `_FsyncError` to fsync phase | GENERATION_APPLY_FAILED/phase=fsync; prove mutation preceded failure, complete bytes/modes restored and owned temporary/staging paths absent |
| P-03 / P / new | `ProbeService.start`; canonical service/backend inventory | Provider capability preflight raises RuntimeError; pre-lease preflight mapping | PROBE_BACKEND_ERROR, exact message, one preflight, zero attach/lease/endpoint |
| P-04 / P / new | start, client attach, debug_handoff_metadata; canonical supported provider | Metadata mapping lacks boardId; DebugHandoffMetadata decoder | PROBE_BACKEND_ERROR, attachment cleared, tasks settled, service still usable; final stop releases owned endpoint/lease |
| P-05 / P / new | `ProbeService.start/stop`; canonical backend | Backend closes then raises TimeoutError; cleanup classification plus lease finalizer | PROBE_CLOSE_FAILED, exact failed-close/successful-release fragments, endpoint removed, released lease and successful successor acquisition |

### A line frozen supplement

Primary accepted R1/R2/R3 from A's matrix, using the union24 residuals. Existing
CAS/idempotency/lock scenarios retain their source-qualified 36+10 PASS and are
not repeated. Constructor-unreachable conjunctions remain visible, unclaimed.

| ID / owner / disposition | Public entry and valid setup | Variation / first guard | Required assertion |
| --- | --- | --- | --- |
| R1 / A / new | `DiagnosticStore.load_creation_intent`, `load_durable`, `load`; existing created-target/failed-evidence factory | Missing diagnostic root, regular-file root, or missing referenced evidence in clone; root-shape or evidence resolution guard | NOT_FOUND / CHAIN_CORRUPT; durable read still returns exact persisted session while resolving read gives EVIDENCE_MISSING; sentinel and caller input graph unchanged |
| R2 / A / new | `diagnostic_show_verification`; real `_prepare_completion_graph`, clone data root | Remove only published analysis root; analysis authority lookup/conversion | Exact DIAGNOSTIC_CHAIN_CORRUPT wire; no new envelope/root/event/checkpoint; clone unchanged by caller, original project/data graph unchanged |
| R3 / A / new | `show_acceptance_attempt`, `resume_acceptance_attempt`; real public physical-protocol rev0/1 graph, clone data root | Public EvidenceStore publishes same envelope metadata with unknown attempt schema and root points to it; wrapper schema dispatch | Exact ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED show/resume wire; read-only rejection and both source and modified clone unchanged by callers |

Clone-only fixture corruption is an explicit test input, not authorization for a
production caller to overwrite authority. Each row compares the post-corruption,
pre-call clone snapshot to its post-call snapshot, and separately preserves the
unmodified source graph. No private production reader or mocked decision is used.

## First execution wave

The existing current-source recovery groups completed 36 and 10 PASS. The new
M/P/A files completed 5/4/5 PASS at 7744cf83, d8b7a328 and 79323b98 respectively.
M's later 2d4ea2c changes only an import blank line and a descriptive docstring;
its valid runtime evidence is retained without a repeated test run. Primary
reviewed the full accepted-base diffs in separate clean review worktrees and
integrated the three files at code head
`6355a6ba324f60e4af2e22bec90155b1de799c75`. Product source remains 8a11caef.
The initial P/A fixture-construction failures were corrected without product
changes; their raw coverage is excluded. The result report records the final
independent native-data decision and remaining numeric gaps.

Further supplementation stays in coherent scenario groups: recovery and
Diagnostic authority transitions, project/probe failure settlement, and Monitor
replay/history/analysis boundaries. Reuse accepted assertions before selecting
additional valid cases. Preserve constructor-inaccessible residual branches as
visible gaps; do not manufacture impossible objects to reach them. Overall 90%
and frozen risk-core 95% are evaluated independently after each complete wave.

## Second wave: owned creation-transaction failure settlement

Accepted base: `40608fdbf4746db80d2f93a2c43347586af2ebbc`. Product source stays
8a11caef; union25 remains authoritative until the next independent native review.
One Luna/max owner in `r10/w2p` owns only the new
`tools/stm32-toolkit/tests/test_risk_creation_settlement.py`. Primary owns this
plan and full-diff acceptance in a separate clean checkout. No shared helper,
product, dependency, schema or coverage-scope changes belong to this group.

Reuse `test_creation_apply` authorization/provider factories and public
`apply_creation`/`CreationApplyRequest`. The three legal caller scenarios each
have successful-cleanup and targeted-filesystem-cleanup-failure variants:

| Scenario | Entry, first guard and required observation |
| --- | --- |
| Adapter produces a child with missing required native files | Use the actual default native parser, not a mocked validation decision. It raises `CubeMXNativeProjectError`, mapped by apply to `CUBEMX_NATIVE_OUTPUT_INVALID`; normal cleanup leaves no owned roots and records validation-phase failure. If deletion of that exact owned generation root fails, return `CREATION_ACTIVATION_ROLLBACK_FAILED` and preserve the actual failed-cleanup root. |
| Generation provider raises OSError after creating owned output | Exercise the existing public provider seam and real generation-root lifecycle. Normal cleanup returns `CREATION_ACTIVATION_FAILED` and leaves no staging; failed deletion returns `CREATION_ACTIVATION_ROLLBACK_FAILED` with the actual retained owned root. No configure/build/activation call occurs. |
| Configuration provider raises OSError after relocation | Use the existing successful validation fixture to reach the supported configure delegate. Prove generation output was relocated before the delegate fails. Normal cleanup removes owned activation staging; failed deletion returns `CREATION_ACTIVATION_ROLLBACK_FAILED` and retains that exact staging root. No build or destination activation occurs. |

All six variants must assert the exact public result wire, consumed authorization
state, unchanged absent/empty destination and unrelated user sentinel, bounded
provider call order, and the actual retained/removed owned roots. Inject only the
filesystem/provider failure; never replace cleanup decisions, authorization,
parser or result predicates. Persistent deletion failure is a deterministic
test input, not an attempt to bypass a previously denied cleanup command.
No real CubeMX, hardware or external application is invoked.

After full Ruff and constructor/first-guard inspection, execute one complete
six-case native-coverage group with first-failure stop and a 300-second bound.
Use existing launch patterns, Python `r10/py/Scripts/python.exe`, all temporary
variables/basetemp/cache under `r10/t/w2p/run1`, and durable raw/JUnit/argv/source
evidence under `r10/e/risk-v2/wave2/p/run1`. Do not rerun the earlier M/P/A groups.
Primary accepts only complete source-pinned results after independent full-diff
review. A failure stops this group for classification before a bounded correction.

## Second wave: Monitor history and replay failure settlement

Accepted base: `ee1031922f421498b34428e4da29747f773f8758`; product source
remains 8a11caef and the independently accepted union25 scope is unchanged.
One Luna/max owner in `r10/w2m` owns only the new file
`tools/stm32-monitor/tests/test_risk_history_replay_settlement.py`.
Primary owns integration and independent complete-diff acceptance. Existing
fixtures remain read-only; do not change shared schemas or product modules.

Use the public factories and supported provider seams in the existing replay,
physical-publication, History and continuation tests. The grouped scenarios are:

| Scenario | Public contract and required assertion |
| --- | --- |
| Incoming replay exceeds the value window | `ingest_monitor_replay` receives a valid document within MAX_REPLAY_BATCHES but with total values above MAX_HISTORY_VALUES. It refuses with EVIDENCE_INTEGRITY_FAILURE before transcript/reference roots, History rows or evidence mutations. This differs from the retained oversized-existing-history case. |
| Physical History ends with a partial batch | `publish_physical_monitor_run` receives a valid TestRun binding and a publicly constructed HistoryPage/HistoryBatchSlice with a final incomplete fragment. Assert the exact incompatible-identity error/message, no publication roots or manifests, and store closure. Never forge an impossible fragment or bypass earlier binding guards. |
| Atomic append window contains an oversized encoding | `HistoryStore.append_batches` receives a valid public SampleBatch exceeding MAX_HISTORY_BATCH_BYTES through existing payload construction. Assert history.appendbatches/MONITOR_REQUEST_INVALID, unchanged SQLite rows/accounting, then successful ordinary append/query. |
| Persisted batch identity is corrupt | Publicly append a valid batch, then change the persisted batch identity and corresponding value rows to zero using the existing corruption-fixture pattern. Public `query_history` must return MONITOR_STORAGE_CORRUPT without deleting/mutating rows or accounting; reopen confirms the same refusal. Snapshot after injecting corruption and before calling the reader. |
| Trusted append meets a hardlinked WAL sidecar | A successful ordinary append establishes the supported write path. Inject a hardlink from an unrelated sentinel to the WAL sidecar using the existing native fixture pattern. The next public append must return MONITOR_STORAGE_INVALID, preserve sentinel bytes/link count and prior history/accounting, and release its writer slot. Remove only the newly injected run-owned sidecar before proving a later normal write can proceed. |
| Continuation disagrees with both run bindings | Reuse a valid public continuation graph and physical MonitorRunRefV2 pair; rebuild both refs with the same changed valid probe identity using public decoders/digest rules. After normal pair validation, compare_monitor_runs must return the exact INCOMPATIBLE_IDENTITY / continuation does not match runs error with no analysis/diagnostic/history/evidence mutation. If public construction or an earlier real authority check prevents this boundary, record that limit rather than mocking the decision. |

A malformed public input may be legal test input; an object that cannot exist
through supported constructors is not. Do not target XML/parser private branches,
forged HMAC state, manufactured races or impossible model internals. Reuse valid
historical assertions, but assert newly introduced failure paths explicitly.

Run full Ruff, AST and diff checks before one complete new-file batch, native
coverage, first-failure stop, maximum 300 seconds. Use Python `r10/py`, all temp
variables/cache/basetemp beneath `r10/t/w2m/run1`, and durable evidence beneath
`r10/e/risk-v2/wave2/m/run1`. Commit the candidate before executing and record
actual base/HEAD/source/argv/process outcome. Inspect constructor and first-guard
ordering before runtime; a failed group stops for classification and cannot be
included in the native union. No hardware, install, packaging or remote action.

#### Monitor review disposition and bounded correction

Independent complete-diff review of a0b20a265e172343633193e3035b1a347e109be6
returned REVISION_REQUIRED. Its six tests passed on unchanged product source;
four planned scenarios are valid. The oversized replay is rejected by the 1 MiB
safe-read guard before decoding, and also contains duplicate selectors and a
stale fixture digest. Retain that observed safe-read refusal, rename its claim,
and leave the planned value-count guard unproven. This single fixture does not
prove the guard universally unreachable. Do not alter limits or bypass decoding.
The reachable persisted-corruption case changes history_values.batch_id to zero;
history_batches.batch_id zero is filtered by the query and remains unproven.

The WAL test must retain the SAME HistoryStore instance from its successful first
append through the injected-sidecar rejection. Recreating the instance resets the
trusted fingerprint and only tests cold-start refusal. Preserve the cold-start
result as its actual evidence, then correct this lifecycle test, retain exact
sentinel/SQLite invariants, and prove subsequent recovery. No private trust-field
mutation or removal of a pre-existing real WAL is permitted.

The existing Luna owner keeps the same file and branch. Full-file static checks
precede a correction commit; run only the changed WAL selector once with native
coverage, first-failure stop and a 180-second budget. Use r10/t/w2m/run2 and
r10/e/risk-v2/wave2/m/run2. The replay rename changes no inputs/assertions and
does not trigger a rerun; the other four unchanged cases retain their evidence.
Primary independently reviews the complete final diff and both evidence scopes.
Neither a renamed test nor six PASS cases imply the two original guards passed.

### Second-wave existing recovery qualification

Primary executes one current-source seven-case group using existing, previously
reviewed tests; no test or product implementation changes. Candidate is the clean
plan commit derived from `90d68d25f3d112452d722074a013ab9f8bd04602`.
The native raw in these older groups predates recovery source 8a11caef and is not
qualified for that file. Preserve historical functional conclusions independently.

- The two `test_vs08b_scenarios.py::test_real_replay_diagnostic_acceptance_chain_reaches_revision_seven` parameters cover legacy-keil and new-cubemx replay through public begin/checkpoint/authorize/Diagnostic/fixed replay to revision7/show.
- `test_continuation_monitor.py::test_public_continuation_terminal_checkpoint_and_wrong_fix_retry` and `test_public_continuation_checkpoint_times_out_before_terminal_root` cover real continuation completion, wrong-fix retry and the terminal deadline, with no unauthorized root advancement.
- `test_acceptance_finalization.py::test_finalization_persisted_authority_mutations_refuse_without_new_revision` parameters `rev1-previous-checkpoint-show`, `rev1-immutable-session-show`, and `rev1-envelope-session-show` cover persisted previous-checkpoint, immutable-session and envelope-session refusals before any new revision.

Do not repeat generic13, current risk-existing/risk-chain, finalization7 or
Diagnostic2. Exclude the known-indeterminate persisted-continuation lock-contention
case, monkeypatched handler-only routing, constructor-impossible timestamp
regression and SimpleNamespace profile fixtures. This is software evidence only.

Reuse the existing guarded native launcher; pin actual clean HEAD, product source,
exact selectors and Python3.12.10. Budget600 seconds, first failure stops, no
automatic retry. All temp/cache/basetemp under `r10/t/w2r`; raw/JUnit/argv/process
and source evidence under `r10/e/risk-v2/wave2/recovery/run1`. Primary owns result
reconciliation and cleanup. Only complete PASS raw is eligible for native union.

## Sampler in-flight group lookup qualification

Accepted base: `bf4b070f29dec6a25a3e30ba3fad29ce268c6492`.
Primary owns this bounded plan and independent complete-diff review. One
Luna/max owner owns only the new
`tools/stm32-monitor/tests/test_risk_sampler_group_epoch.py` in `r10/w3s`.
Product source remains8a11caef. The concurrent History/replay owner has a
different new test file and worktree; existing helpers are read-only.

Scenario: a caller pauses and resumes while a supported group-store lookup is
pending. The lookup belongs to the preceding sampling epoch. Its late result
must neither block the resumed sampler nor supply the resumed tick's authority.
This is distinct from retained in-flight memory-read cancellation coverage.

Reuse `test_sampler` public WatchGroup/_group, FakeObservation/_binding and
FakeHistory factories. Use a provider implementing the existing synchronous
`get_group` seam; let the initial start lookup succeed, and hold the first
producer lookup with bounded threading Events. Call public start, pause and
resume; release the old lookup only after resume succeeds. Later provider
lookups return the original valid group. Parameterize the held provider outcome:

1. Raise an ordinary provider RuntimeError.
2. Return a valid failed `ProtocolResult` for groups.get.
3. Return a public WatchGroup with a changed revision.
4. Return the unchanged valid WatchGroup.

These exercise `_current_group`'s epoch-sensitive failure/revision guards and
`_produce`'s successful-but-obsolete epoch guard through real public lifecycle
operations. Do not set sampler state, epoch, gates, queues or private tasks;
do not patch `_current_group`, `_produce`, `_block` or any decision predicate.
An Event-held external lookup is the legal overlap under test; no fabricated
filesystem race or invalid model is needed. Use supported observation-provider
instrumentation only to record when the first read occurs.

Assert exact successful start/pause/resume results and the same run identity,
no PAUSED_BLOCKED transition or blocked code, and a fresh successful group lookup
AFTER the held result and BEFORE the first probe read. Require a real canonical
subscriber batch with sequence0 and matching run/group identity, then public
stop/close with no owned tasks. Check persisted history contains the same valid
batch once and no stale/failed publication. This positive continuation and event
order must make removal of either epoch guard observably fail; absence of an
exception alone is insufficient. Always release the provider Event in finally
before close, so failed assertions cannot strand worker threads.

Use bounded Events and existing `_next` helpers, not arbitrary timing sleeps.
No product change, hardware, sampling-period upgrade or shared fixture mutation.
Full new-file Ruff --no-cache, AST and diff check precede a candidate commit.
Then run one complete four-case file with native coverage, -x, budget180seconds.
Python is `r10/py/Scripts/python.exe`; all TEMP/TMP/TMPDIR/basetemp/cache stay
under `r10/t/w3s/run1`, evidence under `r10/e/risk-v2/wave3/sampler/run1`.
Reuse the established guarded launch pattern with current exact identities.
First failure stops for classification, no automatic retry. Primary accepts the
full diff independently and owns cleanup. No remote action is authorized.

### Sampler public subscription lifecycle clarification

The sampler run2 wire-shape failure and run3 late-subscription timeout require
correcting the scenario contract before another execution. Creating the async
generator does not subscribe; its first anext registers the queue. The initial
plan omitted this precondition. Run3 proves the late lookup was discarded and
a fresh lookup preceded the first read; it does not prove a sampler publication
failure, because consumption began only after that read. Its raw is excluded.

Reuse the established test_sampler pattern: create the pending public _next
consumer before awaiting start. Start's normal async provider boundary lets the
consumer register before the held producer lookup is released. Retain the pending
result and await it after the unchanged event-order assertions; never request a
second first batch. Bound that consumer at 10 seconds because it now spans the
entire controlled pause/resume setup, not just the final receive. This changes no
sampling interval, delivery contract or product timeout. In finally, release the
provider, cancel and await an unfinished consumer, then close stream and sampler.
Do not inspect/modify subscriber queues or add arbitrary sleeps/private hooks.

The same Luna owner changes only test_risk_sampler_group_epoch.py. Primary will
review the complete corrected diff and cleanup ordering. After static checks and
a new commit, one complete four-case run4 uses the existing Monitor selector,
-x and 180-second budget; evidence and temporary roots are wave3/sampler/run4
and r10/t/w3s/run4. Any failure stops again for evidence-based diagnosis. There
is no authorized product change or automatic retry.

## Target preparation identity qualification

Accepted base: `df259d69261ff629be978fe8bbfe04f943b9cb2a`.
Primary owns this plan and independent review. One Luna/max owner owns only
`tools/stm32-toolkit/tests/test_risk_target_prepare_identity.py` in `r10/w3t`.
The source remains 8a11caef. Existing target-runner factories are read-only;
no product, shared fixture, runtime configuration or hardware change is needed.

Two caller scenarios extend existing mailbox refusal coverage without repeating
its four accepted variants or any real flash/test operation:

1. A caller prepares protocol v2 with inconsistent inventory identity: malformed
   case-inventory digest, a well-formed digest for a different valid inventory,
   non-boolean git_dirty, or malformed optional input_snapshot_sha256. Invoke
   public TargetTestRunner.prepare, never private record validation. The first
   two guards are target.py:1254 and :1261, the git_dirty guard is :1265, and
   optional input identity is validated at :1465 through :1286. The changed
   valid inventory must return TEST_INVENTORY_CHANGED / Target case inventory
   changed; malformed digest and git_dirty return TEST_PROTOCOL_INVALID with
   their exact public messages; malformed optional input returns
   TEST_PROTOCOL_INVALID / Target run binding is invalid.
2. A caller prepares a supported transport whose declared support disagrees with
   the frozen project configuration: RTT channel mismatch, UART baud mismatch,
   or semihosting runtime ELF digest mismatch. Reuse valid support/config shapes
   from test_target_runner and change one semantic field only. These are reached
   through public prepare and _validate_prepared_record, then target.py:160,
   :167 and :172 respectively. Each must return TEST_PROTOCOL_INVALID /
   Target run binding is invalid before authorization publication.

Use seven parameter cases across the two scenarios. Every case first prepares
and reloads a valid control with the same transport/protocol, proving the prefix
is reachable through public constructors. Snapshot the complete persisted
relative-file inventory and bytes after that control. The invalid prepare must
leave it exactly unchanged, must not invoke probe identity/control, flash or
transport factory, and must not create a new authorization. Existing valid
control remains publicly reloadable; a following valid prepare must succeed
with its own nonce/action digest and reload to the original input identities.
Use ordinary observer providers or existing fakes at supported seams; do not
patch product guards, record validators, hashing, randomness or private state.
The malformed values are caller inputs, not fabricated persisted signed state.
No ELF file needs to be opened and no transport may connect.

Preflight actual constructor and first-guard ordering; if an earlier guard stops
a case, report its actual proof instead of manufacturing a bypass. Reuse the
existing guarded native launcher, Python r10/py, full new-file Ruff --no-cache,
AST and diff checks, then commit before one complete seven-case run, -x,
180-second budget. TEMP/TMP/TMPDIR/cache/basetemp stay under r10/t/w3t/run1;
raw coverage, JUnit, argv, environment and process outcomes stay under
r10/e/risk-v2/wave3/target/run1. Only complete accepted raw is eligible for
aggregation. First failure stops for classification; no automatic retry.
Primary owns cleanup. There is no packaging, install or remote authorization.

## Fresh Diagnostic Monitor-authority corruption qualification

Accepted base: `11fe9a0d06b0a5c1e7eb750a83f166de474ff0ec`.
Primary owns the contract and complete-diff acceptance. One Luna/max owner owns
only `tools/stm32-toolkit/tests/test_risk_monitor_authority_load.py` in r10/w3d.
Product source remains 8a11caef. Existing factories and all product files are
read-only; no new hardware, publication framework or production behavior change.

Scenario: a persisted Diagnostic session references a valid failed-before V2
physical Monitor fact. A local root metadata field is then corrupted. Fresh
load/show must reject that authority without changing the event graph, and
restoring the exact original root bytes must recover the same accepted session.
These are offline software fixtures; no new physical PASS is claimed.

Use _supplementary_physical_fact_fixture and the public prefix in
`test_fresh_failed_physical_monitor_fact_v2_persists_and_replays`: convert the
failed-before selector to physical-monitor-fact/2 and remove continuation proof,
add_plan at revision3, run_plan at revision4, assess_hypothesis at revision5,
then verify revision6, observed value3 and the failed-before transcript evidence
ID through a fresh DiagnosticStore load and public show. The continuation-backed
V1 route rejects earlier and is excluded from this group.

Parameterize six root-metadata-only mutations on an independently valid graph:

| Root type | Field/value | First reader boundary on current source |
| --- | --- | --- |
| monitor-run-ref | scenario_role = fixed-after | diagnostic_workflows.py:1818-1834 |
| monitor-run-ref | source_record_sha256 = 64 zeroes | diagnostic_workflows.py:1818-1834 |
| monitor-run-ref | origin_workspace_id = tampered-workspace | diagnostic_workflows.py:1818-1834 |
| monitor-run-ref | run_ref_sha256 = a different valid 64-character digest | diagnostic_workflows.py:1836-1844, root/envelope disagreement |
| monitor-run | source_record_sha256 = 64 zeroes | diagnostic_workflows.py:1734-1752 |
| monitor-run | run_ref_sha256 = a different valid 64-character digest | diagnostic_workflows.py:1914-1925, transcript/reference disagreement |

Locate the existing typed root with the established _typed_root_path fixture
pattern. This metadata is not the root's content address, so do not recompute or
rewrite artifacts, envelope metadata, reference digests, selector or events.
Assert the selected replacement differs from the original. Save original bytes
and restore exactly those bytes in finally, even if a refusal assertion fails.
Do not patch readers/validators or forge a newly signed graph.

After injecting the one mutation, snapshot all diagnostic/evidence relative-file
names and bytes. Fresh DiagnosticStore.load must raise DiagnosticValidationError
with DIAGNOSTIC_CHAIN_CORRUPT; diagnostic_show must return ok=False and that code.
Public load_durable must remain at revision6. Both readers leave the post-injection
snapshot exactly unchanged. Restoring the root bytes must restore a fresh valid
load at revision6 with observed value3 and the original transcript evidence ID.
The complete mutation/control journey is one parameter case, not a private
branch assertion. Native coverage may confirm the stated internal boundaries;
if an earlier guard fires, record the actual proof rather than bypass it.

Do not repeat artifact-tamper cases already refused by EvidenceStore size/hash
validation or repeat unchanged successful physical/Diagnostic acceptance tests.
Full-file Ruff --no-cache, AST and diff checks precede a committed candidate.
Then one complete six-case batch with -x, native coverage, 600-second budget,
Python r10/py, and TEMP/TMP/TMPDIR/cache/basetemp under r10/t/w3d/run1. Keep
raw/JUnit/argv/source/process evidence in r10/e/risk-v2/wave3/diagnostic/run1.
Validate the exact Toolkit selector path before execution. First failure stops
for classification, no automatic retry; main owns cleanup and final acceptance.
No hardware, packaging, deployment or remote action is included.

## Recovery authorization and output-identity qualification

Accepted base: `2cba63f2808d27cb4c2ec1dbba041e9633d830e5`.
Primary owns the contract and complete-diff review; one Luna/max owner owns only
`tools/stm32-toolkit/tests/test_risk_recovery_authority_outputs.py` in r10/w4r.
Product source, all shared fixtures and the frozen coverage scope stay unchanged.
This is an offline authority contract journey, not new build/hardware evidence.

Reuse test_vs08b_scenarios._prepare_real_diagnostic_before_source with one Keil
schema3 fixture and real public replay/Diagnostic/Evidence stores. Reuse the
existing _build_project_context external build-result seam and documented
snapshot provider from that same scenario. These stand in for the compiler and
input scanner only; explicit before/after mappings must be taken from the legal
fixture identities and satisfy all arm-debug, freshness and digest requirements.
They may not replace public readers, repository loads, recovery decisions or
validators. No actual compiler success or physical acceptance is claimed.

Use the public begin/checkpoint prefix: revisions0,1,2,3,4 correspond to begin,
project-materialized, firmware-built-before, target-failure-replayed and
diagnosis-completed as required by the selected case. Use four independent cases
on this single Keil fixture, covering caller authorization and output identity:

1. A caller supplies a valid failed replay from a different build at revision2.
   Publish a separate caller input with a new run ID using the existing decoder,
   frame encoder, canonical descriptor and public target_replay_run. Change only
   its build identity and all corresponding stream identity fields consistently;
   recompute stream size/hash, terminal event digest and replay ID normally.
   Never edit a published root/envelope or original reference. The alternate
   public TestRun must first load successfully. Checkpoint must refuse with
   ACCEPTANCE_ATTEMPT_OUTPUT_INVALID at the cross-output identity comparison
   (891->902), preserving revision2. The original valid reference remains usable.
2. At revision4 request firmware-built-after without consuming the public resume
   actionDigest through authorize_acceptance_source_change. Expect
   ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED (939->940), no build-provider call
   and no new authority. Then authorize with the real current actionDigest and
   verify revision5; never fabricate an unauthorized revision5 model.
3. After real public authorization at revision5, the build-result provider still
   reports the unchanged legal before identity. Expect
   ACCEPTANCE_ATTEMPT_OUTPUT_INVALID (942->943), with revision5 preserved. The
   unchanged result models a caller rebuilding without the declared source fix;
   no product guard is patched to reach it.
4. At revision5 use public diagnostic_declare_source_change with the existing
   real diff artifact and fixed-after identities. Return a different valid build
   identity from the build-result seam while preserving well-formed output. The
   declaration must load normally and first pass the one-declaration/revision
   checks. Expect ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH (969->977). Restore the
   provider's exact declared after mapping and use the same public checkpoint to
   publish revision6 as the positive control.

For each refusal, snapshot all persisted evidence and Diagnostic file names and
bytes after preparing its valid inputs; compare unchanged bytes, public show /
resume revision and next-stage, and the still-loadable input reference. Assert
complete response fields against the producing API's actual serialized shape;
do not equate raw caller input with enriched persisted models. Reuse prior passed
full success journeys rather than rerunning them wholesale. New negative cases
must retain their described local positive controls.

Preflight constructor order and legal prefix before runtime; an earlier refusal
is a finding, not authorization to inject around it. Check Ruff --no-cache, AST
and full diff, commit, then one complete four-case native batch, -x, budget600s,
using the existing guarded launcher and both src paths. All generated files
stay under r10/t/w4r/run1 and e/risk-v2/wave4/recovery/run1. First failure stops
for classification; no automatic retry. Primary owns integration and cleanup.

Run1 contract correction: _current_identity also calls the snapshot provider on
begin and each published checkpoint. The consumed-on-read fixture queue exhausted
before the first build; run1 raw is excluded. Keep the existing build wire shape.
Make the snapshot adapter stable for the current completed build (before identity
until the first build, then the snapshot associated with the latest build call).
Count reads for refusal/no-dispatch assertions without equating them to build
calls. Case1 must stop its legal prefix at revision2, preserve that state on the
alternate replay refusal, then checkpoint the original failed replay to revision3.
Cases2-4 retain revision4. Resume at revision4 yields a real64-hex actionDigest;
authorize with that returned digest, then expect null at revision5/6. Assert the
actual complete public success wire shape and revision outputs at these prefixes,
including the source-change declaration response. No new CubeMX fixture is needed.
The same owner may return a corrected, static-checked commit for independent
review before any second runtime batch. No new test execution is yet authorized.

## Physical-history publication window and recovery qualification

Accepted base: `3abb5faf296c6c7424d9ce43559967c3175a5672`.
Primary owns design/review; one Luna/max owner owns only the new
`tools/stm32-monitor/tests/test_risk_physical_history_window.py` in r10/w4m.
Existing test_physical_publication helpers and product source are read-only.
All data are offline software fixtures; no physical PASS or board access.

One complete caller journey covers rejection followed by usable recovery. Reuse
_physical_context, _publish_physical_test_run and _append_large_physical_history
to persist the existing legal 40 batches x250 values. Append one additional legal
SampleBatch with sequence40, matching binding/group/run/revision, later scheduled
and captured times, and exactly one legal SampleValue. Use public HistoryStore
append, never forged HistoryPage/HistoryBatchSlice or a patched query/guard.

Request publish_physical_monitor_run for the full 41-batch time/sequence window.
The public History pages expose10001 values cumulatively, respecting both the
value and serialized-byte page limits. Do not assume an exact first-page count.
When the cumulative value count exceeds10000, replay.py1785->1786 must reject with
INCOMPATIBLE_IDENTITY / physical Monitor history window is too large. Snapshot
all evidence relative-file names and bytes before the request and compare them
after refusal: no monitor-run/ref root, manifest or artifact may appear. Compare
the complete public History pages and the publicly loaded TestRun before/after
to prove they were preserved. Bound all cursor loops and close every HistoryStore
in finally. Do not infer storage corruption from SQLite housekeeping file times.

As this new case's recovery control, request the original legal 40-batch window
through the same public publisher, then reload its reference from a fresh
EvidenceStore and assert exact identity/window equality. The extra History value
remains unchanged. Retain the existing 10000-value/>1MiB success result; do not
rerun that old test separately. This does not claim reachability of the ingest
document's later value limit, whose size guard is a separate contract.

Preflight public model fields, exact serialized result shape, and first guard;
Ruff --no-cache, AST and diff checks precede the candidate commit. Run the complete
new file once with native coverage, -x,180s via the existing guarded launcher and
both src paths. All output stays under r10/t/w4m/run1 and
e/risk-v2/wave4/monitor/run1. Stop on first failure; do not auto-retry or alter
constants/private state. Main owns independent acceptance, integration and cleanup.

Run1 correction decision: the exact refusal and unchanged Evidence files passed,
but the preservation assertion compared opaque nextCursor strings from different
HistoryStore instances. Each instance owns a newly generated HMAC key, so those
tokens are not a persistent record identity (history.py973-980,580-641). The
failed run remains excluded; complete History preservation is not yet accepted.
The same owner may correct only this test: use each returned token unchanged
within its originating query loop, while comparing complete batch/value wire
data, valueCount, serializedBytes and presence/absence of a next page across
fresh stores. Verify every fragment's ordinal span and values against the
original forty SampleBatch objects plus the extra batch, with contiguous,
nonduplicated coverage. Do not reduce preservation to counts alone. Alias the
imported TestRunRepository to avoid pytest collection of that production class.
After static checks and a correction commit, run the complete one-case file once
under the same180s limit in r10/t/w4m/run2 and e/risk-v2/wave4/monitor/run2.
First failure stops again; no product change or wider test run is authorized.

Run2 stopped before publication because the new comparator incorrectly treated
SampleBatch and HistoryBatchSlice as the same wire schema. After two failed test
rounds, pause execution and recheck the whole observation contract. Source
models.py580-598 and889-909 establish exactly fourteen shared metadata fields
plus values; only HistoryBatchSlice adds startOrdinal and batchValueCount.
Compare shared metadata directly, batchValueCount against len(expected.values),
and each slice's values against the contiguous original ordinal range. The full
before/after stable-page comparison remains required. Primary has re-read both
complete serializers and the complete test. The same owner may implement this
bounded comparator correction and return a static-checked commit; no third run
until primary independently reviews that correction against this schema mapping.

## Tool-support admission and adapter-failure qualification

Accepted base: `e9e40c9fe69eac471a756056a4d341b20b357757`.
Primary owns the contract and review. One Luna/max owner owns only
`tools/stm32-toolkit/tests/test_risk_tool_support_adapters.py` in r10/w4s.
Use the existing test_tool_support helpers, _RunnerStream and public
SupportProfileRequest/discover_tool_support. Product and shared helpers are
read-only. Three caller scenarios comprise one bounded eleven-case group:

1. Profile/runtime admission (three cases). Reuse _nested_public_profile_fixture.
   A tools.gcc list instead of an entry, or duplicate top-level gcc plus tools.gcc,
   must raise exact SupportProfileError / support profile schema is invalid before
   any process dispatch. A valid profile with a scoped runtime-version provider
   representing3.11 must retain tool facts and add exactly PYTHON_UNSUPPORTED /
   python / Use CPython >=3.12,<3.13. The injected version supports both slicing
   and major/minor/micro attributes like the real sys.version_info. Replace only
   this module's runtime-version provider, not global interpreter state. This
   proves the rejection contract, not an actual3.11 execution qualification.
2. Selected GCC version-provider failures (four cases). Use the complete nested
   fixture with only GCC's version hint removed, so the public resolver reaches
   its explicit executable and preserves other declared tool facts. At the real
   _REAL_POPEN external process seam model: spawn OSError; stdout/stderr read
   OSError with no captured version; invalid UTF8 bytes; and timeout followed by
   terminate OSError, another timeout, successful kill and final wait returning
   a terminal code. Use actual _run_bounded and _version_probe; do not replace
   them. Assert GCC_PROBE_FAILED, no successful GCC fact or lower-tier executable
   dispatch, other facts unchanged, shell=False/stdin=DEVNULL, and exact bounded
   wait/terminate/kill order for the timeout case. Readers actually finish before
   return. A fake process's terminal response is adapter evidence only, not a
   real process-exit claim. Do not claim unknown children are gone if kill/wait
   fail; such unconfirmed-termination variants are excluded from this group.
3. GUI executable metadata failures (four cases). Remove only CubeMX/VS Code
   version hints from the complete valid fixture. At ctypes.windll.version,
   model size=0, GetFileVersionInfoW failure, translation-query failure, and an
   OSError. Keep actual _windows_file_version and public resolver. These paths
   never dereference a failed/uninitialized pointer; do not invent a successful
   translation pointer or test ProductVersion query without a valid owned buffer.
   Assert CUBEMX_PROBE_FAILED and VSCODE_PROBE_FAILED, no GUI fact, no process
   launch at all, and unchanged GCC/CMake/Ninja declared facts. This is Win32
   adapter contract evidence, not one of the seven native symlink checks.

All cases snapshot fixture file names/bytes after arranging caller inputs and
assert no persistent mutation. For valid-profile failure cases, preserve the
unchanged fact fields from a public control result with declared versions, then
assert the exact changed fields and sorted issue codes/remediation. Do not copy
the failing actual result to manufacture its expected result. Restore the exact
profile inputs or version provider and prove public discovery works afterward;
do not rerun the old successful test suite wholesale. Do not override resolver,
fact, schema-validation or path-safety decisions. No fabricated reparse metadata,
private-model corruption, real external tool installation or hardware is needed.

Preflight actual constructors, optional-version schema, adapter call order and
serialized profile shape; missing helper capability is a finding. Check Ruff
--no-cache, AST and full diff, commit, then one complete eleven-case native batch
with -x,180s, the existing guarded launcher and both src paths. All generated
output remains r10/t/w4s/run1 and e/risk-v2/wave4/support/run1. First failure stops
for diagnosis; no automatic retry. Primary owns independent acceptance/cleanup;
no shared config, packaging, deployment or remote change is authorized.

## Failed startup cancellation and cleanup ownership

Accepted base: `e1870c442d35f08e7e59d059bcde2cfc48377bc9`.
One Luna/max owner owns only the new
`tools/stm32-monitor/tests/test_risk_runtime_failed_start_cancellation.py` in
r10/w4l. Main owns design and independent complete-diff acceptance. Reuse
test_runtime FakeStore, FakeEndpoint, _project and _protocol_runtime; product
and shared tests stay read-only. This is an offline lifecycle contract check.

One bounded caller journey exercises a real start failure followed by caller
cancellation during owned cleanup. A public service factory returns an invalid
endpoint, causing the real runtime endpoint guard to raise ValueError. Its close
method signals an asyncio.Event and waits on a second event. Only after cleanup
has begun does the caller cancel the task awaiting runtime.start. No original
start cancellation, patched cleanup guard, private runtime state or sleeps used
as synchronization are allowed. Assert that the start task has not finished while
cleanup remains blocked, and that another runtime cannot start in the same
workspace during that interval. Release the event, then require the original
caller to receive CancelledError (runtime.py564-565) after service/exporter/
history/groups each close exactly once. Start and normally stop a fresh runtime
on the exact same project/data/session to prove the workspace lock is released.
Use bounded event waits and a finally block that always releases barriers and
awaits/cancels owned tasks; all replacement runtimes must also be stopped. Record
close order/count and terminal task state through injected provider interfaces,
not private state. Keep the existing double-cancel-at-original-start and endpoint
cleanup-failure successes; they need not be rerun.

Preflight constructor and cleanup call order. Ruff --no-cache, AST and complete
diff checks precede a candidate commit. Run the one new file with -x,180s and
native coverage of both packages via the existing guarded launcher, using only
r10/t/w4l/run1 and e/risk-v2/wave4/runtime/run1. First failure stops for diagnosis.
No packaging, deployment, hardware, remote change, or worker cleanup.

## ProbeSession backend admission and superseded-operation qualification

Accepted base: `d868c50daac16695b9891885c9c1d66578d33996`.
One Luna/max owner owns only the new
`tools/stm32-monitor/tests/test_risk_probe_session_admission.py` in r10/w5p.
Main owns design, complete-diff review and acceptance. Existing FakeObservation,
_binding and WatchItem helpers in test_probe_session stay read-only. Two caller
scenarios contain eleven independent cases; no hardware access or physical PASS.

1. Unprepared public read (two cases). A valid adapter returns an ordinary
   OperationResult.failure with empty code, or success with data=None, at its
   _read_batch boundary. The first produces an isolated ERROR SampleValue with
   MONITOR_PROVENANCE_CHANGED and no whole-read block; the second yields an empty
   blocked result and fixed 'Monitor observation report is invalid'. Restore the
   backend and prove the same public session reads its original watch normally.
   Targets are probe_session.py161-162 and175-176; no private mapping call.
2. Public revalidate/prepare/read lifecycle (nine cases). Three prepare-result
   variants return an unknown failure code, success without a plan, or a valid
   plan after the backend's admission token changes. Expect the exact current
   public code/message and invalidation behavior (267-280). Four supersession
   cases hold an older prepare failure, prepared-read cancellation, prepared-read
   exception, or revalidation failure behind Events; a newer public operation
   revalidates and installs its own plan before the older operation settles.
   Assert the old outcome and that the newer plan remains usable, including no
   stale backend invalidation (242,303,307,337). Two adapter capability cases omit
   the optional invalidation hook on pre-admission prepare, or supply no admission
   token after otherwise successful binding revalidation (218,376). Restore a
   complete adapter and prove public revalidate/prepare/read succeeds afterward.

The named underscored methods are external Observation adapter seams, not
permission to edit ProbeSession private plan/admission fields or guards. Use valid
constructors and public session operations throughout. For the optional-hook case,
the constructor still requires valid binding/catalog/_read_batch/revalidate.
Use bounded Event waits and explicit finally cleanup for all pending tasks; do
not use timing sleeps or count an unstarted async operation as pending work.
Preflight all response shapes and fallback semantics against their public
serializers before execution. Keep the complete meaningful values, code/message,
backend calls and recovery assertions; no generic diagnostic framework. Private
uncalled _read_group and _revalidate_lightweight gaps remain unqualified here.

After Ruff --no-cache, AST and diff checks, commit and run the complete eleven-case
file once, -x,180s, with the existing guarded launcher/native coverage of both
packages. Generated files stay r10/t/w5p/run1; durable evidence/raw coverage stays
e/risk-v2/wave5/probe-session/run1. First failure stops for diagnosis. Main owns
cleanup and integration; no product, shared helper, deployment or remote changes.

### ProbeSession run1 contract correction

Candidate `6811122f243f4a1f7d46fdf7cd6942c398be6f97` stopped at its first
case with a TEST_EXPECTATION failure. WatchItem stores `selector` internally but
serializes a variable watch as `expression` (models.py286-288); the independent
SampleValue definition intentionally still uses `selector` (probe_session.py167).
Only the watch wire expectation changes. Preserve the exact error code, typed
value null, definition, no-block outcome and recovery assertions. Strengthen the
shared successful-read assertion to compare the complete expected SampleValue:
the existing FakeObservation returns TypedValue("counter", "uint32_t", 1,
"0x00000001", 32), code null and the variable selector definition. Construct this
expected value through the public models rather than inventing another wire
schema. This adds no scenario, product change or instrumentation.

The primary reviewed all eleven cases, OperationResult/ProtocolResult,
WatchItem/SampleValue serialization, FakeObservation and all relevant public
ProbeSession branches in clean exact-head r10/w5pr. The same Luna/max owner returns
a separate correction commit with Ruff/AST/diff checks before any execution.
Primary checks that diff first, then releases one complete run2 with the existing
180-second first-error stop. Preserve run1 evidence and exclude its raw coverage.
Use r10/t/w5p/run2 and e/risk-v2/wave5/probe-session/run2 only. This static review
before first execution also applies to the concurrently prepared analysis group
because repeated public-return-shape errors are a verified test-entry risk.

## Continuation association is bound to actual TestRun records

Accepted base: `a649025d930c770b0e395c38ef8b529ade8046a6`.
One Luna/max owner owns only
`tools/stm32-monitor/tests/test_risk_analysis_continuation_association.py` in
r10/w5a. Main owns design and independent review. One complete offline caller
journey covers before-only, after-only and both-side alternate TestRun links,
with the original association remaining usable. These are software evidence
fixtures and must not be presented as physical execution.

Reuse Toolkit test_acceptance_continuation.prepare_pair and its real public
begin_acceptance_attempt continuation bind. Obtain the proof ID from the public
response and authenticate it normally. Reuse the existing
test_acceptance_physical_recovery._append_physical_monitor_history helper with
the fixture's actual identity/workspace/flash/lease and PHYSICAL_RAW_PROBE; do
not use the unrelated Monitor _physical_context helper's fixed project/target.

Publish the original Monitor pair through publish_physical_monitor_run. Build
alternate TestRun records through public constructors/publishers only: replace
the original manifest's run_id, ingest its new canonical manifest file, retain
its exact identity/cases/state/transport/raw_events, then publish a fresh
EvidenceEnvelope with the original physical provenance and new manifest artifact.
Use EvidenceStore.put_envelope and TestRunPublisher.publish_target_physical;
TestRunRepository must freshly load the new records. This physical publication
contract authenticates the raw artifact reference, not embedded replay run IDs;
no published root/file is rewritten or removed. Generate distinct Monitor UUIDs
and matching public History for the alternate records, then fresh-load references.

Use the existing public AnalysisRequest helper/constructor with the actual
Diagnostic hypothesis, source declaration and continuation evidence. First prove
the original pair compares successfully. For each of the three alternate-link
combinations, snapshot all Evidence/Diagnostic file names and bytes after its
valid inputs exist; compare_monitor_runs must first refuse with exact
INCOMPATIBLE_IDENTITY / Monitor TestRuns differ from continuation
(analysis_workflows.py1100-1104). No derived evidence may appear and original and
alternate TestRuns/references must remain loadable. The original request must
still return the same published result after all refusals. Keep stable record
identity separate from opaque cursor/lease tokens; close all owned History stores.

Do not implement the proposed export final-ID check: it is dominated by earlier
source/publication association guards. No fabricated AnalysisPublication, patched
reader, authorization bypass, model corruption or new generic framework. Preflight
every constructor and earlier guard, fixture identity and complete public result
shape before execution. Static checks and commit precede one complete new-file
run, -x,300s, through the existing guarded launcher with both src and required
Toolkit test-helper import path. Generated files stay r10/t/w5a/run1 and durable
evidence/raw coverage e/risk-v2/wave5/analysis/run1. First error stops. No existing
full journey suite rerun, product/shared-helper edits, cleanup, hardware or remote.

### Wave5 independent entry review and existing Recovery qualification

ProbeSession candidate22404e9 passed all11 cases in1.794s after complete-diff
review; it is accepted and integrated at6468af64, outside native union28 until
the next combined review. Its initial failed raw remains excluded. Analysis
candidate813227fb had the same WatchItem wire expectation mistake caught before
pytest; correction65574d78 uses the public model. Primary reviewed the complete
322-line journey, its original/alias publication constructors, continuation
identity checks and first refusal guard in clean r10/w5ar. Source148 matches;
one300s execution is released, without any earlier failed analysis run.

Accepted base for existing Recovery qualification:
`6468af64d73e5228c9d756fbb854fdf5cb1327ba`. The read-only selector/evidence audit
found five existing public tests lacking current8a11 source evidence after the
old recovery_workflows.py coverage was invalidated. Reuse these exact selectors;
do not create or change tests or product code:

- test_acceptance_physical_recovery.py::test_public_physical_checkpoint_rejects_nonmatching_stale_revision
- test_acceptance_finalization.py::test_malformed_b_requests_are_input_invalid_without_persisted_mutation
- test_acceptance_finalization.py::test_unexpected_revision_rejected_by_read_mutation_and_fresh_process
- test_acceptance_finalization.py::test_final_deadline_check_rejects_new_root_after_envelope_persist
- test_acceptance_finalization.py::test_final_deadline_check_rejects_rev1_root_after_envelope_persist

All files are under tools/stm32-toolkit/tests. Two complete caller scenarios are
qualified together: stale physical-stage revision refusal with unchanged
show/resume, and finalization request/revision/deadline refusal with no accepted
new root. The deadline tests wrap an existing recheck only to observe completion,
call its real implementation, and inject the public clock; they do not bypass
authorization or substitute guard results. Real file-backed stores/fresh process
readers are used on software evidence fixtures, not hardware. Primary inspected
the existing assertions; historical individual PASS is not current-source raw
qualification. Already qualified generic13/36, continuation10, finalization7 and
Recovery groups remain reused.

One Luna/max execution owner uses clean r10/w5r, with no repository write
ownership. Run exactly the five selectors as one -x batch with a600s process
budget, existing guarded launcher and double-package native coverage. All temp
roots stay r10/t/w5r/run1; durable evidence/raw stays
e/risk-v2/wave5/recovery-existing/run1. Pin actual argv, source148, HEAD, JUnit and
process outcome. First failure stops for classification, without modification or
retry. Primary owns evidence review/aggregation/cleanup. No hardware, dependency
installation, packaging, deployment, remote changes or new framework.

### Analysis run1: keep Monitor and Target ID domains distinct

Run1 at65574d786959dd147ea6f2cb1ee770cb95c66aa4 terminated normally with one
TEST_EXPECTATION failure before compare. Continuation bind/authentication and
the original before-Monitor publication/fresh load succeeded. The test and
primary preflight wrongly interpreted origin_run_id as the linked TestRun ID.
replay.py1637-1682 defines operation_id, origin_run_id and projected_run_id as
the Monitor UUID; transcript metadata and payload carry test_run_id separately.
The retained run1 transcript manifest24b22802 and artifact679a5387 show this
exact distinction. Its raw coverage is excluded and failure evidence retained.

The same Luna owner changes only the owned analysis test. In each publication
control, compare all three Monitor IDs to the requested monitor_run_id. After
load_monitor_run_reference authenticates the reference/transcript/TestRun graph,
load its transcript_evidence_id with the public EvidenceStore.get_envelope and
require metadata.test_run_id to equal the explicit requested Target TestRun ID.
Freshly load that expected TestRun and require manifest.run_id equality. Keep
the original/before-alias/after-alias expected IDs explicit in the three
combinations; never feed a Monitor UUID to TestRunRepository.load. The rest of
the complete public refusal/no-mutation/original-result recovery journey stays
unchanged. Alias the imported TestRunPublisher name to avoid pytest attempting
to collect that product class. No product or shared helper changes.

This corrects the relationship model as a whole instead of removing the failed
assertion. A read-only independent reviewer checks the remaining unexecuted
alias/publication/compare assertions concurrently. The worker returns a separate
static correction commit. Primary integrates any substantiated findings and
checks the full correction before releasing at most one new300s -x run2, using
r10/t/w5a/run2 and e/risk-v2/wave5/analysis/run2. No execution is authorized merely
by producing the correction; the existing first-error stop remains in force.

## Wave6: debug handoff identity race and settlement recovery

Accepted implementation base: `9865c88a7f8b9e1ee297957657e623556f8642ae`.
The primary conversation owns this design, orchestration and independent review;
one Luna/max worker owns only the new
`tools/stm32-toolkit/tests/test_risk_handoff_identity_settlement.py`.
No product behavior or public contract changes are planned. All 148 qualified
source files remain pinned to runtime source8a11; union29 is still under its
separate independent native-data review. Existing valid tests are not rerun.

The read-only lease/handoff audit found that default-health malformed response
paths could add two branches, but adding a loopback server/process harness for
those alone is disproportionate. Existing ticket binding, consumed tombstones,
acknowledgement refusal/retry, corrupt records and cleanup tests are retained.
Directory-descriptor/Linux branches require their real platform and are not
simulated as Windows native acceptance. The next bounded group instead covers
two whole caller scenarios using existing handoff fixtures:

1. Firmware identity changes during an admitted handoff operation. Cover both
   begin (after initial readback, before the final fresh identity check) and end
   (after endpoint reacquisition/attach, before its fresh identity check). Use
   the existing public build-document fixture publisher with a different valid
   ELF `text_size`, not a patched firmware reader, model or identity predicate.
   The original request, original flash receipt and ticket remain unchanged.
   The first refusal must be `HANDOFF_IDENTITY_MISMATCH` / `Firmware identity
   changed during debug handoff`. Begin must publish no handoff state/companion,
   reservation or stop. End must close transport and release the temporary
   claim, retain the exact reservation and ticket in `reacquiring`, and perform
   no consume/finalize/acknowledge. Re-publishing the original valid build bytes
   through the same fixture publisher restores the original deterministic
   buildId (builtAtUtc is excluded by identity.py719-764). The same caller path
   must then complete normally and restore the exact watch selection once.
2. The external supervisor reports finalization unavailable after transport and
   temporary ownership have been released. Use a subclass of the existing
   FakeSupervisor external adapter, whose public finalize method returns false
   once at the post-consume boundary, then delegates normally. Do not patch
   handoff's `_finish_consumed_handoff`, guards, state reader or lease logic.
   The first end returns `HANDOFF_REACQUIRE_FAILED` / `Consumed handoff ownership
   could not be finalized`, with no live endpoint/transport, exact consumed
   ticket evidence preserved, and handoff state still `reacquiring`. A subsequent
   public end completes settlement without another start, attach, readback or
   consume; it restores the watch selection once, clears the ticket and releases
   the lease. A replay must return `HANDOFF_TICKET_INVALID` without mutation.

Reuse `test_debug_handoff` FakeSupervisor/FakeClient, build/flash fixtures and
real file-backed handoff state. Test-owned adapter hooks are allowed only at
public external supervisor/client methods. Snapshot persisted state/lease and
event counts at each refusal, and assert complete success payloads and cleanup.
No private production-state assignment, fabricated Analysis/Target records,
coverage-driven unreachable states, new generic framework or shared-fixture
edits. These are software tests, not physical device evidence.

Worker uses a clean isolated `r10/w6h` worktree and the existing guarded launcher.
Before pytest, return a committed static candidate for primary complete-diff
review, with exact constructor/return-shape and first-guard source pointers.
After release, run only the new file once, `-x`, with a300s process budget and
double-package native coverage. Run roots: `r10/t/w6h/run1` and durable evidence
`e/risk-v2/wave6/handoff/run1`. Pin HEAD, argv, environment, source148, JUnit,
native raw hashes and process termination. First unexpected error stops for
classification. Main owns integration, aggregation and any permitted cleanup;
no worker cleanup, hardware, dependency changes, packaging, deployment or remote
actions. This test-only group does not invalidate existing VS10/attempt7 PASS.

### Wave6 handoff static entry review

The initial358-line draft was inspected before any pytest execution. Two findings
must be closed in the same owned test file: the first begin call legitimately
creates `.debug-handoff.guard` containing one NUL byte (handoff.py363-410), so
assert every original session file byte-identical plus exactly that new guard,
not an impossible unchanged directory. Handoff state/companion, reservation and
stop remain forbidden on the identity refusal. The draft also covered only the
begin identity race; the already-frozen end race after reacquisition/attach must
still be implemented, with exact external reservation/ticket preservation and
same-ticket recovery. No runtime test failure or product defect is claimed.

Candidatef9738f89 fixed the guard artifact but placed the end mutation in
FakeClient.after_read. A second static review rejected this before execution:
end_debug_handoff attaches at1521, loads/checks current identity at1523-1533,
and only then reads segments at1543. That convenience callback cannot reach
the claimed guard. Stop patching the callback locally and use this explicit
phase contract: a test-owned FakeClient subclass overrides public async attach,
awaits super().attach, publishes the changed valid build, then returns the same
ProbeAttachmentEvidence. Only the first end factory uses it; the recovery
factory uses ordinary FakeClient. The rejected client's exact trace is attach,
close with no read; the recovered client's trace is attach, read, close. This
reconsiders the external test adapter boundary after two review rounds, without
changing production interfaces, guard results or the approved caller scenario.
Return a separate static correction commit before any run is released.

## Wave6: actual observation supersession through the public adapter

Accepted base: `7e2940c4d806e56df97dd57ec6852abafc7b798d`. Product source148 remains
8a11 and accepted native union29 is reused. Primary owns design/integration and
independent complete-diff review; one separate Luna/max owner writes only
`tools/stm32-monitor/tests/test_risk_observation_supersession.py` in clean
`r10/w6m`. It shares no mutable resources with the handoff worktree.

The existing ProbeSession11 uses FakeObservation, so it does not qualify actual
Toolkit MonitorObservationSession behavior. The read-only audit proved that
neither actual lower session nor the outer ProbeSession holds a lifecycle/read
lock across backend read or bind awaits (monitor_observation.py800-830;
probe_session.py87-105). The following two complete caller scenarios are valid:

1. Open a real software MonitorObservationSession through open_monitor_observation,
   wrap it with public ProbeSession, revalidate and prepare a plan for signed32
   and GPIOA.IDR. Pause the first backend read at the existing ObservationClient
   I/O seam with asyncio.Event; through public prepare_read_plan, admit a new
   plan. Resume the old read with normal data, RuntimeError or CancelledError.
   The normal/error variants must return ProbeReadOutcome with empty values,
   code MONITOR_PROVENANCE_CHANGED and message Monitor observation changed;
   cancellation propagates CancelledError and has no fabricated JSON result.
   None may discard the newer plan: a subsequent public read succeeds with
   complete public SampleValue/TypedValue assertions and no fallback/rebind.
   The real lower guard and cleanup paths are exercised, not replaced.
2. With an existing admitted plan, pause a public revalidate in the declared
   MonitorObservationSeams.bind callback. The initial open bind delegates to the
   existing Harness normally. While the next bind waits, admit a new plan through
   public prepare_read_plan. Release the old bind with a legitimate adapter
   OperationResult failure PROBE_LEASE_LOST, or CancelledError. Failure returns
   monitor ProtocolResult operation sampling.revalidate, protocol
   stm32-toolkit-monitor/1, code MONITOR_PROVENANCE_CHANGED, message Monitor
   observation changed, data null and details empty; cancellation propagates.
   The new plan remains readable, with no hidden rebind or retry.

The reachability proof is generation-based: lower prepare discards the old plan
at913-916 and installs its new plan at994-1005; outer installs at278-285 only if
admission is unchanged. Old prepared read retains its original local object and
fails the lower881-893 ownership check. Old revalidate captures generation and
admission before bind; its1242-1251 invalidator sees the new generation and must
not clear the new state. The bind seam is explicitly constructor-supported
Callable[[object,object],Awaitable[OperationResult]] at131-143, not a patched
product predicate or private state. Use Event barriers with bounded waits,
not sleeps, manufactured tokens or private assignments.

Reuse Toolkit test_monitor_observation DebugEnv/Harness, real DwarfCatalog and
SvdSelection fixtures, and ObservationClient. Read exact helper constructors and
wire models before implementation. The two parameterized scenarios comprise
three old-read outcomes plus two old-revalidate outcomes. Finally close the real
session, require client.closed, supervisor.stopped, endpoint None and empty
Harness registry; repeat close and verify closed-session access causes no new
backend read. Harness exposes no root-guard closed flag, so do not invent that
telemetry or claim exact root-close counts. No extra private instrumentation.

No product/shared-helper changes, direct private admission/plan calls, guard
patching, global environment changes, hardware or physical PASS claims. The
stale-admission-token, typed cleanup-fragment and platform-specific guards are
outside this group; no forced coverage of dominated paths. Return a committed
static candidate first for primary full-diff/first-guard review. Only after that
release, run the new file once with -x and a300s child budget using the existing
guarded launcher and both package src paths plus required Toolkit test helpers.
Temp root `r10/t/w6m/run1`; durable evidence/raw `e/risk-v2/wave6/observation/run1`.
Pin HEAD/source148/argv/environment/JUnit/raw/process outcome. First error stops
for diagnosis, no retry. Primary owns cleanup/integration/native aggregation;
worker does not package, deploy, clean, install dependencies or act remotely.

## Wave6: PyOCD failures through the actual owned worker

Accepted base: `af9c0d2e4ed1f66fffb2341400fbfbeb79f73521`. Product source148 remains8a11. Primary owns design, integration and independent complete-diff review. One Luna/max implementer owns only `tools/stm32-toolkit/tests/test_risk_pyocd_worker_settlement.py` in isolated `r10/w6p`, branch `codex/STM32TK-1.0-pyocd-worker-settlement`. No helper or production modifications.

Existing backend unit tests do not establish the combined public supervisor, spawned worker, client error and fresh-worker recovery contract for these failure variants. The read-only audit proved two complete caller journeys:

1. Start ProbeServiceSupervisor with a ProbeBackendWorker wrapping actual PyOCDBackend and an external FakePyOCDDriver. Enumerate the real software adapter, attach valid probe-a/stm32f407vg, with target_profile={} and a fake session whose open raises RuntimeError before discovery (target=None). Public attach must return PROBE_ATTACH_FAILED / Probe worker operation failed. Stage=session-open; primary diagnostic is stage=session-open, reason=unknown, sourceCode=UNTYPED. Public cleanup must include successful session-close, probe-open-check-before-close, probe-close, probe-open-check-after-close and worker-parent-abort. Stop owned service, prove worker terminal/dead, endpoint and lease release. Use a fresh healthy worker/supervisor to attach successfully and settle normally; never reuse terminal proxy.
2. Start MODIFY supervisor with real run-owned project and verified firmware file, attach normally, then public program_verified_elf(path,sha256,size) through service validation and actual PyOCDBackend.flash_elf. The only failure seam is external driver.program_file. Three variants cover a valid preexisting programDiagnostic, a typed ProbeBackendError caused by OSError, and a typed error without cause. Public code PROBE_PROGRAM_FAILED, message Probe worker operation failed, exact safe programDiagnostic schema/content; no attach diagnostic injected. Settle terminal worker and lease, then fresh healthy worker performs the same verified program request successfully. The software fixture bytes do not claim a real ELF or physical programming result.

Use existing worker/supervisor test constructors, public ProbeClient, OperationLevel, fake driver and mature diagnostic schema. Spawn requires a module-level importable child factory (partial supported); do not use local lambdas. Parent workers list provides owned_pid/is_alive/is_terminal. Parent in-memory child-driver lists are not cross-process evidence. When child event evidence is necessary, reuse existing run-owned marker/JSONL sink pattern with events recorded before failure and after actual cleanup. Never manufacture closed flags. Backend normal error cleanup and parent worker abort are distinct; assert the public diagnostic and independently observable process settlement, not assumed causality.

Guard proof: attach924-933 admits valid inputs,986-999 creates/opens session,1051-1076 rediscovery/direct-close branch; worker321-341 sanitizes the public message,486-574 aborts owned execution on operation failure. Program client408-424/service1966-2064 validate digest and size then backend1519-1548 calls external programmer. backend.py177-220 defines diagnostic shape. Invalid image guards and malformed diagnostics are excluded because earlier public guards dominate them. Do not call private error helpers or patch product predicates to force coverage.

Return one committed static candidate plus Ruff/format/AST/diff checks first; no pytest until primary complete-diff release. Then one new-file -x run with300s child ceiling through existing guarded launcher, source148/head/argv/environment/JUnit/raw/process evidence. Temp `r10/t/w6p/run1`, durable `e/risk-v2/wave6/pyocd/run1`. First unexpected failure stops for classification, no automatic edits/retry. No real hardware, product change, dependencies, cleanup, packaging, deployment or remote action. Main owns any permitted cleanup and later native union. Existing VS10/attempt7 and unaffected release evidence remain valid.

### Wave6 observation execution-source correction

Run1 at d696e3b00cd07fa80b6021ea559b359c13c65243 stopped before pytest/process creation: the implementation checkout w6m stores LF bytes, while frozen source148 and clean exact-head review checkout w6mr store CRLF bytes. Primary verified148/148 equal after CRLF-to-LF text normalization,141 raw mismatches only in w6m,0 raw mismatches in w6mr; Git working/index content is clean. Classification ENVIRONMENT, not product failure; strict raw identity guard worked correctly. Preserve run1 preflight diagnostics, no JUnit/raw/PASS exists.

Reuse existing clean exact-head w6mr solely as execution checkout for the same unchanged five-case test. Main grants original Luna owner one run2 with the same -x300s boundary, temp r10/t/w6m/run2 and evidence e/risk-v2/wave6/observation/run2. Reuse the launcher with only verified root/run paths changed. Recheck148 raw hashes before starting. No normalization/registry rewrite, source edit, new framework or persistent/shared Git setting change. This is the first possible pytest execution after a diagnosed preflight stop; any unexpected failure stops again. No other authority changes.

## Wave6 PyOCD native multiprocessing measurement correction

Behavior candidate80c2f09049cdc0e24b4bc98f4e7111f39d07cde1 passed all4 worker journeys, integrated1bfc4201605a8beee29c2d153cb8d30f7dc400b8. Preserve this behavior PASS. Native run1 pyocd_backend.py has0/324 branches,104 definition lines; its coverage config enables patch=subprocess only. Production worker uses multiprocessing.get_context('spawn') atworker.py366. Installed coverage7.15.4 control.py573-576 installs child tracing only for concurrency=multiprocessing; multiproc.py starts tracing in bootstrap and saves in finally. Production worker abort560-574 may terminate a child immediately after error reply, so normal exit-time coverage save alone is not a reliable error-path measurement.

Classify this as INFRASTRUCTURE measurement omission, not product failure. Union30's native candidate(+9Toolkit,0Monitor) remains a truthful partial calculation but is not promoted while this qualification gap is corrected. Do not infer worker coverage from4PASS, rewrite native data, change source scope or alter worker termination behavior.

Same Luna/max owner may change ONLY test_risk_pyocd_worker_settlement.py to add a test-only subclass of actual PyOCDBackend wrapping its public open_attach and flash_elf calls. Each wrapper calls super unchanged, and in finally saves Coverage.current() when an active native collector exists. This flush occurs before a result/exception reaches the real worker's reply and parent termination, preserving actual measured arcs without patching guards, success/failure semantics, IPC, scheduling or cleanup. Use the existing coverage test dependency; no new engine/framework. Ordinary no-coverage test execution remains valid. A coverage save failure must not be silently counted as measurement success. Factory returns this subclass around the same external fake driver. Exact existing public result/resource assertions remain unchanged.

Run2 coverage config adds concurrency=multiprocessing to the existing branch/parallel/subprocess settings. No global environment or dependency change. Because original child trace was never captured and cannot be recovered, one repeat of these4 cases is required solely for native child measurement; unrelated tests and prior behavior evidence are reused. Return committed static candidate plus config delta first; primary complete-diff review precedes execution. Use original w6p ownership, source148-qualified checkout, temp r10/t/w6p/run2 and durable e/risk-v2/wave6/pyocd/run2, -x300s, first failure stops. Acceptance requires4PASS, owned processes settled, native child shard evidence and actual expected PyOCD branch arcs; no synthesized imports/data. Preserve run1 and union30 output unchanged, no cleanup/hardware/deployment/remote.

## Wave7: persisted finalization binding refusal and restoration

Accepted base: `23804c43a6f8b4b523f5fd5aaa4da2d6dbcd1d87`; product source148
remains8a11. Primary owns specification, integration and independent review.
One Luna/max implementation owner writes only
`tools/stm32-toolkit/tests/test_risk_finalization_binding_authority.py` in
`r10/w7r`, branch `codex/STM32TK-1.0-finalization-binding-authority`.
No overlapping writers, shared-helper or product changes.

Two caller scenarios share the existing synthetic persisted finalization fixture:
authenticated begin/show/checkpoint control; external stored-authority corruption
followed by read-only refusal and restoration. This is software evidence only.
The existing mutation selector uses private writers and rewrites parents, so it
cannot establish the missing parent-binding check or full no-write oracle.
Reuse its public setup, `_context`, `_begin`, `_proof`, `_checkpoint`,
`_journey_public_root_path` and `_persisted_snapshot`; do not reuse
`_replace_attempt_root`, private snapshots, or production root/envelope writers.

Create revision0 through public begin. Save the original root bytes and public
proof before corrupting an isolated test-owned store. Read its root and envelope
through get_root/get_envelope. For each of three independent parameterized cases,
change one attempt payload field, recompute checkpointId from canonical payload
without that key, validate with PhysicalFinalizationAttempt.from_value, construct
a new public EvidenceEnvelope retaining identity/operation/time/parents/artifacts,
and put_envelope. Replace only the test-owned root bytes using public RootRecord
serialization with the same root ID, authentic new manifest ID and matching
attempt_sha256/revision/workspace_id/logical_project_id metadata. All earlier
digest/decoder/constructor/root checks must remain valid.

- continuationEvidenceId becomes the real failed-physical envelope ID, keeping
  the original parent tuple. recovery_workflows.py3583 rejects the chain before
  looking up a continuation proof: ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED.
- fixedAfterTestRunId becomes the existing failed_run_id; original continuation
  and parents remain valid. Proof-bound reload3587-3590 returns
  ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH.
- fixedAfterEvidenceId becomes the existing failed-physical envelope ID; the
  same proof-bound reload returns ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH.

For each variant, public show, explicit begin retry and checkpoint must return
the exact expected public code, with full data-root bytes identical before and
after each call. Revision1/2 must stay absent; no new envelope, Diagnostic event
or authority root may be created. Reuse the original valid proof for checkpoint,
not a fabricated proof derived from corrupted fields. Restore the saved root
bytes, require public show to return the original revision0 wire values, then
public checkpoint must publish revision1 with the original valid binding.
Unreachable old manifests may remain; compare full snapshots after deliberate
corruption so that intentional setup writes are not mistaken for product writes.

Independent source audit confirmed constructor-valid identities and first-guard
ordering. Implementation must still return exact construction and serializer
pointers with its static candidate; never assert guessed wire container types.
No private predicate/provider replacement, clock manipulation, hardware, global
configuration, dependencies, cleanup or remote operation. Existing valid results
remain applicable; the12 previously dominated arcs do not shrink any denominator.

Return committed static candidate, Ruff/format/AST/diff results first. After
primary complete-diff release only, run the new three-case file once with -x,
300s child budget, existing guarded launcher and native double-package coverage.
Temp `r10/t/w7r/run1`, durable `e/risk-v2/wave7/recovery/run1`. Pin actual HEAD,
source148, argv/environment/JUnit/raw/process outcome. First unexpected failure
stops for classification without automatic edits or retry. Primary owns cleanup
disposition, native aggregation and final acceptance.

## Wave7: stored physical Monitor reference authority and restoration

Accepted base: `ad4fe8a1230f0767b4a7e32f0148b1e2b34457d8`; product source148
remains8a11. Primary owns design, integration and independent review. One separate
Luna/max owner writes only
`tools/stm32-monitor/tests/test_risk_physical_reference_authority.py` in
`r10/w7m`, branch `codex/STM32TK-1.0-physical-reference-authority`.
Recovery's w7r owner and files remain independent.

Caller scenarios are valid publication/fresh reload and externally damaged
persisted authority/refusal/restoration. Reuse the synthetic public physical
publication setup from test_physical_publication.py: _physical_context,
_publish_physical_test_run, _append_physical_history and _physical_request, then
publish_physical_monitor_run and load_monitor_run_reference. These are software
fixtures and confer no physical PASS. Keep both Monitor batches and original
Target TestRun, binding, hashes, schema and lease identities coherent.

Independent construction audit confirmed five first-failure paths. Root records
have a create-or-reuse public API, so corruption setup may unlink only the
disposable test-owned old root and use a public RootRecord plus put_root for its
replacement. Read authority with get_root/get_envelope; rebuild EvidenceEnvelope
without supplying its old ID, and publish via put_envelope. New reference JSON
uses MonitorRunRefV2.to_dict, recomputed run_ref_sha256 over the canonical payload
without that key, from_value, ingest_file and an authentic new envelope.
Do not call private production envelope/root writers or substitute provider
results. Existing helper _replace_persisted_physical_transcript is a construction
reference only; do not reuse its direct root-byte writer.

Five independent parameterized cases in this one persisted-authority journey:

1. Reference envelope operation becomes the valid but wrong
   monitor-physical-window value; preserve original identity/time/parent/artifact/
   metadata and repoint reference root. replay.py2243-2248 must reject envelope
   structure before reading its payload.
2. Keep original operation, parent and artifact; change only the envelope's
   scenario_role metadata to the other valid role while root metadata/reference
   bytes remain original. Assert the setup value actually differs.2265-2266
   must reject envelope metadata.
3. Reference transcript_evidence_id becomes a distinct existing Target TestRun
   manifest ID. Recompute the reference digest, artifact and envelope; retain
   the envelope parent as the ORIGINAL transcript-root manifest ID (the private
   reference-envelope helper would incorrectly follow the changed field).
   Reference root/envelope metadata match the changed reference; update the
   transcript root run_ref_sha256 coherently. Original transcript bytes/envelope
   stay unchanged.2287-2288 must reject the evidence-ID relation.
4. Change only reference group_revision from valid baseline1 to2, recompute
   digest/artifact/envelope and reference metadata, and update transcript-root
   run_ref_sha256. Transcript bytes/envelope and all earlier identities remain
   unchanged.2307-2350 must reject the window relation.
5. Keep both roots intact; unlink only the reference manifest file. Actual
   get_envelope FileNotFoundError must reach2400-2401. A missing root instead
   fails as incomplete before this handler and is not this case.

Each public reload must raise MonitorReplayError with exact
EVIDENCE_INTEGRITY_FAILURE / physical Monitor Evidence is corrupt. Verify first
cause respectively: physical reference envelope is invalid; physical reference
envelope metadata is invalid; physical transcript evidence ID differs from
reference; physical transcript and reference windows differ; FileNotFoundError.
Snapshot the full disposable data root after deliberate corruption and require
byte-for-byte equality after refusal. Save all originals before setup; restore
replaced roots using unlink plus put_root, or missing manifest using put_envelope.
Fresh reload must equal the original MonitorRunRefV2 wire data, including schema,
physical_transport_evidence, hashed probe, window, source digest and lease.
Unused new content-addressed objects may remain; no physical evidence claim.

Return one committed static candidate with exact serializer/first-guard pointers
and Ruff no-cache/format/AST/diff results before execution. No shared helpers,
product changes, artificial guard patches, filesystem races, clock changes,
dependencies or global configuration. Only after primary complete-diff release:
one new-file five-case -x run,300s child ceiling, existing guarded launcher and
both source packages. Temp r10/t/w7m/run1; durable e/risk-v2/wave7/monitor/run1.
Source148/head/argv/environment/JUnit/raw/process records are required. Stop at
the first unexpected failure, no automatic edits/retry. Main owns cleanup and
aggregation. No hardware, deployment, packaging or remote operation.

## User-directed offline concurrency policy — 2026-09-21

Preserve existing owners: finalization_binding_impl owns Recovery/diagnostic/
evidence integrity in w7r; physical_reference_impl owns Monitor in w7m;
target_prepare_identity_impl owns Probe/worker settlement in w6p. Keep
union30_native_review as the dedicated independent reviewer. Primary owns all
design, dispatch, integration, acceptance and shared-ledger writes. This uses
the five-agent capacity without splitting trivial tasks or introducing a lead
intermediary. Silence alone never transfers ownership or starts a duplicate run.

The first concurrent execution batch selects two ready, independently reviewed
suites among the Recovery three-case journey, Monitor five-case journey and a
diagnosed Probe measurement correction. Readiness rather than model silence
determines which two start. Each reuses its own guarded
launcher, clean exact candidate checkout,300-second ceiling, TEMP/TMP/TMPDIR,
pytest cache/basetemp, durable log/JUnit and raw coverage directory. No unreviewed
test may start just to create overlap. Record actual child PIDs and UTC interval
overlap; if one completes before the other is ready, retain that result and
validate concurrency on the next necessary independent batch without rerunning
an already valid test solely to demonstrate overlap.

Each launcher records elapsed time, exit/timeout/termination status and, when
available from its owned process, total CPU time and peak working set. Primary
records host physical memory availability before and after the pair; missing
telemetry remains unavailable, never zero. Parent-process figures do not include
unmeasured descendants. Existing subprocess-native coverage must be checked for
actual collection, persistence and combine completeness; behavior PASS and
coverage completeness remain separate. Preserve child raw shards using native
combine --keep. No fabricated coverage or new diagnostic framework.

Expand only after two independent suites complete without infrastructure error,
timeout or resource-pressure evidence, within their fixed budgets, and host
available memory stays at least15 percent with combined measured peak working
sets below25 percent of physical RAM. Inspect any missing descendant telemetry
before treating parent totals as a bound. These are execution-capacity criteria,
not product acceptance gates; no claim of speedup without a comparable baseline.
At most three implementation lines can execute simultaneously while retaining
the reviewer and primary under the current agent limit. Four suites require a
separately justified batching arrangement and are not enabled by this first pair.

Formal native aggregation, shared-ledger updates, exclusive performance tests,
final builds/deployment and same-probe hardware remain serial under primary.
An unexpected suite failure stops that suite; other demonstrably independent
work may continue. PyOCD run2 retains4PASS but is native-measurement partial;
parallelism does not authorize another measurement retry before diagnosis and
review. No frozen denominator,90/95 gate, remote authority or denied-cleanup
boundary changes. Report completed public behaviors and native new-branch deltas,
remaining thresholds and specific blockers; after consecutive low-yield groups,
reassess remaining whole-scenario reachability before assigning further tests.

### PyOCD run2 measurement diagnosis and bounded native-input correction

Run2 a05476a798b75e0b149e5a28cc658700c8cd9719 has4PASS22.520s, exit0,
no timeout. Raw SHA7617359952680106634769B387B6B42AE34C8C079572F54141BC5FC754A20C84.
Attach failure arcs1051->1057 and1065->1075 are captured; program-diagnostic
516/519/524 and1543 are absent. This is partial native qualification, not a
behavior failure. Preserve all old results and the original 9-shard hash manifest.

The installed Coverage7.15.4 source establishes a distinct aggregation fault:
sqldata.py897-913 writes a filename H hash only on its first save and sets
_wrote_hash. Later save calls may append trace data without changing that hash.
data.py99-129 uses a filename hash in preference to real file bytes when deciding
which files to skip. The run2 manifest contains six different raw SHA256 values
with the same filename H hash, and combine reports4combined/5skipped. Finally,
cmdline.py886-887 automatically combines during JSON reporting and defaults to
deleting input shards unless --keep-combined is supplied. Current raw directory
has only the combined database; the9 manifest records are pre-combine evidence,
not nine retained originals. Per-skipped-shard program arcs are no longer provable.

Reconsider the measurement boundary, not worker scheduling or product code.
Same Luna owner may prepare only a run-local launcher correction; test source
a054 stays unchanged. Test collection writes into run3/raw-child-shards. Before
any combination, hash/inventory and preserve every actual shard, copy each
byte-identically to run3/merge-inputs with neutral .coverage.shard-NNNN names
that do not match the special filename-hash pattern. Verify original/copy hashes.
Use existing native coverage combine --keep with explicit --data-file pointing
to run3/raw-coverage/.coverage and only those copies as input. Native JSON uses
the combined data path and --keep-combined, with no raw originals in its automatic
combine directory. Do not modify database contents, library globals, dependencies
or original filenames. Native CoverageData read-only inspection must show the
target program arcs in child shards and the final combined/JSON results, with
original shard hashes unchanged after reporting. This reuses the existing
launcher/native engine, not a new diagnostic framework.

Static launcher review precedes one necessary run3 of only the existing
three-case program-failure test (exclude the already qualified attach-only case),
-x300s, own temp r10/t/w6p/run3 and durable e/risk-v2/wave6/pyocd/run3. It may
overlap one other independently released suite under the two-suite ceiling.
Require3PASS and exact child/combined native arcs516->517,519->520,524->525 and
524->526 with reached error line1543. Retain run1/run2 behavior and actual native
contributions separately; no automatic retry, product change, hardware, cleanup,
deployment or remote action. Primary and dedicated reviewer decide qualification.

## Wave8 bounded protocol assembly scenarios — 2026-09-21

Accepted base: 018392f579b2dc76f4e17e4fe5d7639868739155. Product identity
remains 8a11caef14df16c5e56c0be2363d4ef5530110eb with all148 source hashes
unchanged. Primary owns design, integration and acceptance; the existing
finalization_binding_impl Luna/max owner implements this evidence-integrity
slice. Independent review is required for acceptance. User authorization is the
current instruction to execute independent offline supplementation without
changing the 1.0 gates; no hardware, packaging, deployment or remote permission.

Two runnable scenarios use exported public assembly APIs and existing test
fixtures, in one new owned file:
tools/stm32-toolkit/tests/test_risk_protocol_assembly_authority.py.
No existing test, source, schema, scope, dependency, launcher framework or shared
ledger is in the implementation scope. Worktree r10/w8r; run-owned temp
r10/t/w8r/run1; durable evidence e/risk-v2/wave8/protocol/run1. Primary is cleanup
owner; preserve current failure/native evidence and all denied roots.

1. v1 caller supplies a frozen inventory and sequence-numbered event stream.
   Cover eight meaningful outcomes: invalid record shape; second run_start with
   correct sequence1; run_start selecting an undiscovered case; changed start
   inventory digest; duplicate case_start with correct next sequence; premature
   run_end; a complete valid stream containing a log; terminal count mismatch.
   Reuse valid inventory/artifact/terminal builders. Assert exact public
   TestProtocolError code AND message for each refusal, distinguishing sequence
   validation from state checks. For the log outcome assert successful manifest
   identity, case results and terminal state, not merely absence of an exception.
   Expected missing arcs:300->301,312->313,315->316,317->318,324->325,
   342->343,347->299,363->364. Payload validity and renumbering must be proven
   before the target state guard; unknown kinds cannot reach346->299.
2. v2 caller encodes real bytes, obtains frames from a fresh public
   TargetFrameDecoder(expected_version=2), then invokes assemble_target_v2_run
   with an ArtifactRef for the exact bytes. Seven outcomes: invalid host timeout;
   inventory not first; run_start not second; terminal inventory mismatch;
   consecutive case starts; result without an active case; invalid middle kind.
   All sequences/monotonic counters and payload schemas remain valid. Recompute
   the terminal digest over actual preceding bytes after mutations. Assert exact
   public code/message, and demonstrate decoder feed/finish succeeds before the
   assembler refusal. Expected arcs:411->420,445->446,449->450,480->481,
   491->492,499->500,515->518. Do not mutate TargetFrame cached metadata or
   private product state.502->503 is dominated by raw-decoder monotonic checking.

The 428->429 non-TargetFrame guard is outside this decoder-derived scenario,
not globally unreachable: a caller could pass an invalid public argument.
Leave it untested here without removing it from any denominator. Likewise all
precheck-dominated branches remain in the frozen native coverage scope.

This groups15 currently missing arcs into two complete public boundary scenarios;
15 is a static upper bound, not measured progress. Do not duplicate existing
covered timeout, start-inventory, terminal-state or raw-artifact checks. No
private production helper calls, predicate patches, clock/scheduler changes or
invented physical facts. Test helpers may be reused as fixture builders.

Return one clean committed candidate with complete diff, first-guard mapping,
Ruff no-cache/format/AST/diff checks. Primary may release one exact-file -x run,
300s ceiling, after complete static review; independent review is a condition
of acceptance, not a duplicate execution-release wait. Reuse an accepted guarded
launcher with only run identity/path/selector/configuration substitutions; do
not create another diagnostic framework. Record branch coverage of actual
Python subprocesses, source148, argv/head/JUnit/process, and keep original
shards through combine and JSON. Stop on first unexpected failure; classify
before any correction. Do not repeat valid runs solely to demonstrate overlap.
The two-suite limit and serial formal aggregation/shared ledger remain in force.

## Wave9 bounded protocol producer contract — 2026-09-21

Accepted code base: 1b7a763d2be33a4789f3023a161d5b53a4034112. Source148 remains
8a11caef14df16c5e56c0be2363d4ef5530110eb. Current user approval covers these
offline supplements with unchanged release gates. Primary owns specification,
review and acceptance; existing finalization_binding_impl Luna/max owns the
sole new test file tools/stm32-toolkit/tests/test_risk_protocol_payload_authority.py.
Worktree r10/w9r, temp r10/t/w9r/run1, evidence e/risk-v2/wave9/protocol/run1.
No existing tests, product bytes, shared fixtures, dependencies or scope change.

The prior15-case assembly journey is accepted; do not repeat it. Two complementary
public producer scenarios group14 currently missing protocol branches. This is
static expected reachability, not measured coverage. Source inspection and
union32 native candidate identify these same residuals from accepted union31
minus the15 executed assembly branches; no pending aggregate claim is required
to establish that these14 have not been exercised.

1. A caller supplies a v2 payload to public encode_frame(version=2). Reuse the
   valid _v2_payloads fixture in test_target_protocol_v2.py; change only the named
   public payload field. Ten refusal variants cover case_ids empty (170->171),
   duplicate (173->174), or not UTF-8 sorted (175->176); inventory mode host
   (187->188); valid-format incorrect inventory digest (191->192) or run_start
   digest (197->198); invalid case_result state (205->206); invalid terminal
   state (211->212); wrong counts keys (216->217); unsupported log stream
   (222->223). The closed schema, other fields, frame kind and sequence remain
   valid so the named guard is first. Assert exact TestProtocolError code AND
   message. These are producer refusals before bytes exist, not malformed-wire
   decoder acceptance. One successful real encode/decode/assemble journey uses
   a non-None case_result message (208->209), recomputes the terminal digest over
   actual bytes, and asserts preserved message, manifest identity, cases,
   terminal state and raw artifact digest. Existing _v2_stream and _assemble_v2
   test fixtures already call the real public APIs and may be reused.
2. A caller declares a target inventory through the exported public
   calculate_case_inventory_digest. Three invalid declarations are a string
   instead of sequence (152->153), empty sequence (154->155), duplicate case IDs
   (159->160). Assert exact public code/message. Retain existing successful
   canonical digest and size-limit evidence; do not repeat it. This public
   declaration boundary intentionally rejects before encoding and does not
   fabricate an impossible TestInventory or mutate internal state.

No private product calls, monkeypatched validators, altered cached frames,
forged coverage, hardware, remote actions or general diagnostic framework.
The remaining unsupported-version public argument and precheck-dominated
assembly branches are outside this slice and remain in the denominator.

Return one clean committed candidate with complete diff, first-guard map,
Ruff no-cache/format, AST and diff checks. Do not pytest until primary complete
static review releases one bounded exact-file run; independent review is needed
before integration. Reuse an existing accepted guarded launcher with only batch
inputs changed, -x and300s ceiling, original native shards retained through
combine --keep and JSON --keep-combined. Set runtimeSourceHead from the pinned
source148 runtimeHead, separately from tested codeHead; do not copy the earlier
report-label error. Measure actual subprocesses if any, and distinguish absence
of product subprocesses from missing measurement. Current resource restriction
permits only one suite until the two-suite capacity criterion is revalidated.
Primary alone owns native aggregation/shared ledger/cleanup; no denied-root retry.

## Wave9 Target discovery and settlement — 2026-09-21

Accepted base: 4700cabd8f798afbd65e240f9c9dfc0160dc8ff7. Product source remains
8a11caef14df16c5e56c0be2363d4ef5530110eb/source148. Primary owns design/review/
acceptance; preserved target_prepare_identity_impl Luna/max owns only the new
file tools/stm32-toolkit/tests/test_risk_target_discovery_authority.py. Worktree
r10/w9p; temp r10/t/w9p/run1; durable e/risk-v2/wave9/target/run1. User's current
authorization covers offline supplementation; no product or hardware change.

Six variants cover two runnable public TargetTestRunner.discover caller scenarios:
1. Complete valid v2 inventory handshake with host_identity passed as its public
   to_dict mapping (2240->2241). Assert returned inventory, raw frame, case digest
   and all identity fields. Use a synchronous successful test-owned probe close
   naturally in this positive flow (1167->-1161), with exactly one close of each
   dependency and no flash, control, authorization, manifest or Evidence writes.
2. Five refused handshakes: a valid sequence0 v2 run_start instead of inventory
   (2213->2214); a truncated valid inventory frame ending with EOF (2228->2229);
   valid inventory frame but expected_firmware.case_ids differs (2249->2257);
   valid-format expected inventory_digest differs from the real host/cases digest
   (2268->2271); expected_firmware.build_id differs while host/case inventory
   digest stays correct (2283->2289). All earlier bindings stay valid. Assert
   exact public TEST_TRANSPORT_UNAVAILABLE and message plus the precise cause
   code/message where wrapping occurs, so no earlier refusal is mistaken for the
   named check. Both dependencies close once; flash/control stays unused and
   owned evidence-root bytes/directories remain at their post-construction snapshot.

Use the actual MailboxTransport public open/read_async/identity/close_async over
an in-memory test-owned bounded reader; optional public EOF may be provided by a
small adapter over that reader's served-byte state. The reader's image contains
real producer/consumer header and immutable encoded frame bytes, not hardware.
Reuse existing public identity/frame fixture builders in test_target_runner.py.
Do not reuse FakeTransport.identity: it calls the private _task8_identity_digest.
A test adapter may compose/delegate actual public MailboxTransport methods; it
must not mutate its internal cursor/config or invoke private product functions.
A test-owned forbidden flash dependency may expose run solely to fail on dispatch.
No new generic framework is needed. All fixture/output roots remain under the
owned basetemp; do not create .test-data in the source checkout.

Static target is7 missing arcs, not measured progress. Do not implement2264->2265
(decoder plus2249 dominate it), nor unproven2293/2332 identity-snapshot mutation
paths. The r2 feasibility report supersedes the original wrong first-guard claims;
all those branches stay in the frozen denominator. No private state, validator
patch, false physical PASS, timer/scheduler patch or product behavior change.

Return a clean committed candidate and full diff, source148 and Ruff/AST/diff
checks before pytest. Primary full static review may release one exact-file
-x300s run; independent review precedes integration. Reuse the accepted guarded
launcher/native capture with correct8a11 runtime source distinct from test HEAD;
retain actual raw child shards through combine/report. First unexpected failure
stops; no automatic retry. Two ready independent suites may overlap only with a
fresh resource check above the existing15 percent criterion; there is no reason
to rerun valid results to manufacture overlap. Native union/shared ledger and
cleanup stay with primary; no denied-root retry or remote action.

## Wave10 proportionate execution admission — 2026-09-21

The user's current request authorizes improving offline parallelism while
preserving the release goal, frozen scopes and existing owners. The primary
still freezes each concrete public scenario, first-guard proof, accepted base,
owned file, worktree, temp/evidence roots and exact suite before implementation.
Read-only preflight proposals alone do not authorize implementation or execution.

For subsequent test-only slices, that dispatch may also allocate one of two
exclusive logical execution slots to its existing Luna/max owner. The owner
may commit the bounded candidate, pass Ruff/format/AST/diff and source148 checks,
pin its exact candidate in the existing guarded launcher, then run the specified
suite once without a second primary execution-release round trip. The dispatch
must explicitly grant this admission; absent that grant, keep the existing hold.
The primary allocates each slot to one owner only and does not transfer it until
the previous owner's process and descendant settlement are proved. No new slot
manager, shared-lock framework, product tool or dispatch automation is introduced.

Each admitted owner checks fresh host memory at launch (at least the existing
15 percent free criterion), keeps its own absolute D:/codex-tmp paths and native
coverage files, records the actual runtime/test identities, and retains original
subprocess shards through combine and report. If the resource check fails or any
unexpected test failure/timeout occurs, stop and return evidence; admission does
not permit another attempt. Reuse the accepted launcher rather than rebuilding
it. The normal wall ceiling remains300s unless the frozen scenario explicitly
requires a different bounded budget.

Independent complete-diff review may overlap this first implementation run, but
acceptance and integration require both the independent review and primary
runtime/measurement checks. A substantive test-oracle correction requires only
its affected suite; a report correction requires no test rerun. Old valid
behavior/raw evidence remains retained. At most two suites may execute; a third
or fourth slot remains withheld until real overlap and resource/stability data
justify it. Formal aggregation, shared-ledger writes, exclusive performance,
final builds, deployment and any same-probe operations remain primary-serialized.

Public exported constructors and from_value/new methods are valid caller
boundaries: they may be tested with invalid inputs that their production checks
reject. This does not authorize bypassing constructors, mutating private/frozen
state, forging successful impossible models, or relabeling software as hardware.
Prefer complete roundtrip/refusal caller scenarios and prove each first guard;
do not infer reachability merely from a public root or a missing coverage arc.
## Wave10 public attach-diagnostic boundary slice

Accepted base for this bounded slice: `7b497ad38e16a51cafcfb7c746a03b71a9a8a06e`.
Product remains `8a11caef14df16c5e56c0be2363d4ef5530110eb`; source148 and frozen
coverage scopes must remain identical. Primary owns design/integration; existing
Probe line owner `/root/target_prepare_identity_impl` owns implementation/tests;
`/root/union30_native_review` independently reviews the complete diff. No product,
hardware, deployment, remote, schema or dependency changes are part of this slice.

Two complete public contract scenarios are admitted for design:

1. Decode a valid detached attach diagnostic, reject malformed external cleanup
   payloads and late-attach payloads at their first guards, then decode the intact
   original again. Use exported validate/extract/make APIs and ordinary caller-owned
   wire dictionaries. Check exact refusal, original identity/state preservation and
   detached output. Cover malformed entry keys/stage/outcome, late scope/duplicates,
   a valid late payload on a non-deadline primary, and recursive input lists.
2. Produce a primary and cleanup fragment, append valid and invalid fragments,
   update verified target state, and project legacy compatibility/envelope output.
   Check exact ValueError text for invalid public constructor inputs, atomic
   rejection without partial cleanup or primary replacement, correct accepted
   state/projection, and empty/refused envelopes for invalid prior diagnostics.
   Exported invalid-input refusals are permitted; forged successful frozen
   instances, private helpers, state mutation and predicate patches are not.

Static first-guard proof: `probe/attach_diagnostics.py` exports these APIs in
`__all__` at652-675. External wire entries first enter validation at267/269/271;
valid primary/type prefixes permit late entry scope/duplicate checks305/307 and
non-deadline rejection338. Direct exported producer inputs reach394,408,411,413,
473 and CleanupFragment544/550; exported merge/extract/state/projection APIs
reach508,523,528,582,594,613,627,644 and419/421/427/431/444/447/485. No earlier
check requires an invalid successfully constructed model for these inputs.
Each parameterized input must document its first relevant guard before execution.

Union33 has114/150 covered branches in this file. Its36 missing pairs contain up
to30 candidates above; no gain is claimed until native data is compared. Six
remaining pairs235->236,251->253,360->361,371->372,379->380,381->382 are excluded
from this slice because earlier validated scope/order/uniqueness checks dominate
them. These exclusions do not change the denominator or claim a global bound.
Existing worker/backend/service successes and worker IPC rejection suites are
retained, not repeated. This slice adds only the missing public boundary families.

Only new test file owned by this slice:
`tools/stm32-toolkit/tests/test_risk_attach_diagnostic_boundary.py`.
Implementation tree `r10/w10p`, branch `codex/STM32TK-1.0-attach-diagnostic-boundary`;
temporary root `r10/t/w10p/run1`, evidence `r10/e/risk-v2/wave10/probe/run1`.
All are below `D:/codex-tmp/v10b-0918`. Primary owns integration/cleanup and must
not retry denied cleanup roots. Reuse the existing Wave9 Target run2 guarded
launcher, preserving actual-interpreter raw shards and combine --keep. No product
subprocess is expected; if execution introduces one, prove capture/save/merge for
it before measurement acceptance. Behavior and measurement verdicts stay separate.

Run only this file, once after candidate commit, Ruff/format/AST/diff and source148
checks. Runtime ceiling300s; require a fresh available-memory gate >=15%, isolated
logs/data/temp, no forced retry, and process/descendant settlement. Primary dispatch
must explicitly allocate one of the two execution slots; this plan alone does not
allocate a slot. Independent full-diff review may overlap the first run, but full
review and primary runtime reconciliation are mandatory before integration.

## Wave10 public Monitor analysis model slice

Accepted base: `b6677f8dbafa0bd70bfdeffb85ead623f4da05e5`; product8a11/source148,
whole-file scopes and previous behavior evidence remain unchanged. Primary owns
design/acceptance, existing Monitor owner `/root/physical_reference_impl` implements,
and `/root/union30_native_review` reviews the complete diff independently.
The bounded preflight is `r10/e/risk-v2/wave10/analysis-public-boundary-preflight.md`,
SHA256 `8B85A40CC981652852F4AE5561FB6D2C371AC041E410D93F669109A2904A674A`.

Primary correction before implementation: its proposed881->882 is dominated by
expected_schema=V3 whenever request is non-None at853-865. A legacy schema fails
the earlier schema guard, while V3 takes the other arm. Exclude this input and arc;
retain the original report plus an additive correction, never bypass the guard.
No denominator changes follow. The admitted estimate is11 new arcs, not12.

Scenario A constructs the legal request/computation/lineage/result/reference/marker
graph, verifies exact-instance parsers and canonical wire roundtrips, then uses
valid two-pair native input with minimum_valid_pairs=3 to create and roundtrip the
accepted INVALID/INCONCLUSIVE/INSUFFICIENT_VALID_PAIRS result. Prefer the existing
public analyze_monitor_windows computation over reconstructing algorithm output;
AnalysisResult.new owns the result digest. Intended missing arcs are653->654,
987->988,1082->1083 and889->891. These are software model contracts, not physical
sampling evidence.

Scenario B submits copied public wire input or direct invalid caller arguments to
exported constructors/parsers: unknown computation quality430->436, nonclosed
computation payload520->521, wrong lineage input type622->623, mixed valid reference
families624->625, evidence-reference schema976->977, marker polarity1040->1041 and
marker label1042->1043. Check the preflight's exact ANALYSIS_REQUEST_INVALID code
and message, unchanged valid input graph, and successful reuse of that graph.
No private-state mutation, invalid successful object, helper patch or new framework.

Only owned file: `tools/stm32-monitor/tests/test_risk_analysis_public_boundaries.py`.
Tree `r10/w10m`, branch `codex/STM32TK-1.0-analysis-public-boundaries`; temporary
`r10/t/w10m/run1`, evidence `r10/e/risk-v2/wave10/monitor/run1`, all under approved
D:/codex-tmp/v10b-0918. Reuse existing guarded launcher and both package source paths
needed by Monitor fixtures; capture actual interpreter/native shards, --keep originals,
record behavior and measurement separately, and count only gains against accepted U33
(unchanged Monitor U31). No product subprocess is expected; prove capture if one appears.
Primary must explicitly allocate execution slot2; first run after candidate commit,
Ruff/format/AST/diff/source148 checks, fresh memory>=15%, ceiling300s, first anomaly
stop/no retry. Independent review can overlap execution; acceptance requires both.

## Wave10 Diagnostic native evidence authority journey

Accepted base `2b856214ff1d483cbc1cf2f27ef7afa8df0708b6`; product8a11/source148 and
frozen scopes remain unchanged. Existing Recovery owner `/root/finalization_binding_impl`
implements; primary owns graph design/integration/acceptance and independent reviewer
`/root/union30_native_review` reviews the complete test diff. The bounded preflight is
`r10/e/risk-v2/wave10/diagnostic-graph-preflight.md`, SHA256
`4B66BFBA88BEA64EF348EAD4E35D238B16B618A66ADC7DB038B92935E826EC8E`.
Its twelve static candidates are estimates, not measured coverage. The U32 coverage
for these modules remains equal to accepted U33; compare final arcs to U33.

Two joined public scenarios share one software-only baseline graph:
1. Publish the native before/after Monitor, analysis and continuation graph. Submit
   the eleven pre-plan persisted-input refusal variants through
   diagnostic_add_verification_plan; each leaves the exact Diagnostic event tree,
   revision and state unchanged. Then successfully add/start the original valid plan.
2. Submit the alternate-identity marker through diagnostic_attach_marker and prove
   its exact refusal plus unchanged Diagnostic state; attach the original marker,
   complete verification once, and read from a fresh public context with
   diagnostic_show_verification. Require PASSED/VERIFICATION_PASSED and the exact
   public session/fix_verifications/authoritative serialization.

Primary graph correction: put_root at evidence/gc.py:752-770 refuses a different
payload under an existing key. A clone retaining that key does not solve this.
Never overwrite/remove an accepted root. For each transcript/reference variant
derive a fresh operation UUID, remap operation/origin/projected IDs consistently
except the one deliberately tested relation, and publish new envelope/root identities
using existing public APIs. Recompute all content IDs needed by preceding guards;
read the actual producer-returned workspace/session/build IDs rather than copying
the preflight's illustrative IDs. _same_session_native_baseline actually uses
aaaaaaaa/bbbbbbbb operation UUIDs; the report's3333/4444 values are not authoritative.
For the empty operation metadata variant, a separate valid root key may be unused:
the nonempty-operation guard must reject before any lookup.

Evidence envelopes are immutable inputs; valid prior objects/roots must remain
byte-identical. A new analysis envelope may point at the new transcript graph;
its root and analysis/plan IDs must be consistent through the target first guard.
Original accepted roots stay available, so recovery selects the original request
without rewriting storage. Refusal oracles distinguish intentional caller publication
from forbidden Diagnostic event writes. Reuse the accepted prepare_pair and native
construction helpers only as fixtures; no new private-production helper/state patch,
validator replacement, hardware, product-source edit or generic graph framework.
The existing deterministic fixture providers do not count as new coverage evidence.

Target missing arcs in diagnostic_workflows.py:1691->1706,1709->1710,1717->1722,
1757->1758,1787->1788,1794->1807,1846->1847,1865->1877,1906->1907,1912->1913,
2361->2362 and2563->2564. Use the preflight's exact code/message, not a set of
possible errors. If a preceding guard wins, stop/classify; do not weaken the oracle.

Only owned file `tools/stm32-toolkit/tests/test_risk_diagnostic_native_authority.py`;
tree `r10/w10r`, branch `codex/STM32TK-1.0-diagnostic-native-authority`, temporary
`r10/t/w10r/run1`, evidence `r10/e/risk-v2/wave10/recovery/run1`, all below approved
D:/codex-tmp/v10b-0918. Reuse the existing two-package guarded launcher; preserve
actual child shards and --keep combine, and separate behavior/measurement verdicts.
Ruff/format/AST/diff/source148 plus one exact new-file run are necessary, without
rerunning accepted physical or full regression suites. Runtime ceiling300s, fresh
memory>=15%, first failure/timeout stops. Implementation may proceed in parallel;
pytest waits for an explicit freed slot because the other two owners already hold
both slots. Independent full-diff review and primary result reconciliation precede
integration; formal aggregation and shared-ledger writes remain serial.

## Wave10 sampler partial-start reproducer

The independent sampler review7EC9D3D1A2147DB1929E8580355EBB854EB080B28F776F3FD4063DB8D8AFD745
identifies public task-creation failure after RUNNING is published (sampler.py:243-245).
Treat this as a source-backed candidate defect, not a proven runtime failure or
an excuse to narrow the supported surface/coverage denominator. MonitorSampler is
explicitly exported at596; an asyncio event loop's set_task_factory is a public
host facility. Primary accepts a bounded host allocation-failure reproduction.

Base9cd33a04b2d6cb79a3a4e8ab05f648abadd0cedb; same Monitor Luna/max owner.
Only new test file tools/stm32-monitor/tests/test_risk_sampler_start_transaction.py
in r10/w10s (branch codex/STM32TK-1.0-sampler-start-transaction). Reuse existing
public sampler/ProbeSession/History/group fixtures. Prepare two parameter variants
(first or second owned-task allocation fails), but initially execute only first.
After valid admission, the scoped public task factory raises a unique test-owned
allocation exception; no production predicate/private field patch is allowed.
Restore the caller's previous factory in finally. The factory may close the rejected
coroutine it owns to avoid a fixture-created unawaited-coroutine warning.

Record exception identity, public state/tasks and observable probe plan invalidation
before cleanup. Expected contract: failed start leaves IDLE with no live owned task
and no usable stale read plan; then normal public start/stop/close remains possible.
Use public stop/close in finally to settle the current-source failure before the
assertion reports RED. Do not set private fields to force cleanup. RED evidence
must be retained and excluded from accepted coverage. No product fix is released
until primary reconciles the reproduction and freezes the correction behavior.

Prepare candidate, static checks, source148 and existing guarded launcher with
60s ceiling; r10/t/w10s/run1 and e/risk-v2/wave10/sampler/run1. No execution slot
is currently allocated: Probe/Recovery own the two slots. No deployment, hardware,
remote operation, new framework, threshold change, or repeated prior valid suite.

## Wave10 sampler failed-start correction

The first-case run completed with the exact original injected error and observed
RUNNING instead of IDLE; public cleanup completed and both PIDs exited. Preserve
run1 as PRODUCT RED and exclude its coverage. The removed post-IDLE-stop extra
invalidation assertion was already corrected before that run.

Apply specs/2026-09-21-stm32tk-sampler-start-transaction.md on the same branch/tree
r10/w10s, accepted base9cd33a04b2d6cb79a3a4e8ab05f648abadd0cedb, by the existing
Monitor Luna/max owner. Only sampler.py and test_risk_sampler_start_transaction.py
are owned. Do not change the existing regression files. Correct rollback for first
and second owned task allocation failures, preserve the original exception and
settle the acquired task/coroutine/read plan without re-entering the action lock.

Slot1 remains assigned to this owner. After committing and Ruff/AST/diff checks,
validate147 unchanged source hashes and record sampler.py's intentional new hash
against the frozen148-file registry; do not disable the source guard globally.
Use fresh r10/t/w10s/run2 and e/risk-v2/wave10/sampler/run2, existing guarded launcher,
full candidate SHA, fresh memory>=15%,300s ceiling. Once run the two reproducer
parameters plus test_sampler.py and test_risk_sampler_group_epoch.py, retaining
all raw shards and subprocess capture. First unexpected failure stops; no automatic
retry. Independent review covers the whole base-to-final diff. Primary integrates
and qualifies changed-source coverage serially, retaining unaffected U34 evidence.

## Wave10 sampler review correction and Diagnostic terminal reconciliation

Sampler candidate bc86127b1d92ca06f830ea3e1bf9f292f3cb82a4 run2 passed54 checks.
Review F338FB624147810C3085A6CCB11CE50E4BD402DD7985E2BA86890AE129450116 nevertheless
requires truthful ownership when caller cancellation interrupts failed-start
rollback. Apply the revised sampler specification with the same owner, branch,
accepted base and two files. No passing result is relabeled as covering this path.
Slot1 authorizes one corrected run3 after commit/static/source qualification,
fresh memory>=15%,300s ceiling, using r10/t/w10s/run3 and
e/risk-v2/wave10/sampler/run3. Select the new test file and the same two affected
regression files. Preserve raw subprocess shards; first unexpected failure stops.
Review the complete accepted-base-to-final-head diff before integration.

Diagnostic candidate d3f6cb7d41b720eccb0b0d98adf902e9ca101311 run2 reached all12
target arcs and completion PASSED, then failed its final test oracle because it
compared JSON containers with frozen result containers. The original pytest
result remains FAILED and its raw data remains unaccepted pending reconciliation.
The same owner may change only that test's final expected value to use the
completion result's public to_dict. Existing pytest rebuilds the entire persisted
graph and has no terminal-only replay entry. Therefore a bounded one-use evidence
script is permitted under e/risk-v2/wave10/recovery/oracle-reconciliation: publicly
re-read the accepted completion with its identical operation ID, re-query show
through a fresh context, and check exact normalized equality and immutable input
trees. This uses the existing idempotency path at diagnostic_workflows.py:891;
it must not publish or construct new graph data. Slot2 permits this single120s
operation after identity/source verification, not a full run3. Independent review
must decide the applicability of the preserved prior behavior and raw evidence.

Probe Wave11's two or three transport-binding arcs are deferred as low yield.
The same Probe owner instead assesses target testing and Monitor observation
public lifecycle gaps read-only. No test execution is released from that report.
Suite concurrency remains2: the two completed run2 intervals did not overlap and
their redirector-only resource records do not justify increasing concurrency.

## User-directed release flow: converge, freeze, qualify the real bundle

The 2026-09-21 user instruction changes execution method only. The full1.0 goal,
90% native overall/95% frozen risk-core-v2 targets for each Python package,
broad-core-v1/UI views, seven native Windows checks, two reproducible builds and
all13 outputs, real install/Check,0.9-to1.0 Repair, rollback/security and delivery
documentation remain mandatory. Existing VS10-A/B, attempt7 and applicable
evidence remain accepted within their original boundaries. No remote authority
is granted and no RC is declared by this addendum.

### 1. Defect convergence and pre-RC qualification

Current accepted integration before this addendum is
7450fa53a2b5ceef0e1d263df7849f20bc9d7838. Product source is
78341213b8e5604d5f6a0436c4324d6d9f9e3ead, with148-file registry69D2A724.
U35 canonical8141C5C6 is ACCEPTED_NATIVE_DATA, not release acceptance.
Diagnostic's final-oracle reconciliation and Sampler's startup/rollback ownership
correction are closed; do not restart either. The Sampler correction closed its
second complete implementation/review round. Its original failed runs remain
historical evidence and are not turned into passed tests.

This batch admits no additional product changes. Probe w11p has the frozen
authorization/post-step-result scenarios and one180-second selected run. Recovery
w11r has two public software-producer scenarios, admitted only after proving at
least six genuinely reachable missing arcs, and one300-second selected run.
Monitor's existing storage/history preflight remains bounded to two complete
public candidate families. Existing owners continue preparation, implementation
and the admitted first run without new stepwise approvals. Actual suites remain
at most two, with disjoint worktrees, temp roots, logs and coverage files.

Classify the first failure before action: PRODUCT_CONTRACT, TEST_DATA_SCRIPT_ORACLE,
ENVIRONMENT_INFRASTRUCTURE_PLATFORM, MEASUREMENT_REPORT, or NEW_SCOPE_OPTIMIZATION.
Only a reproducible PRODUCT_CONTRACT finding can trigger a bounded product fix.
Primary first consolidates all known related normal/partial-start/cancellation/
cleanup/recovery paths, ownership, public state transitions and error semantics.
The same root cause/public contract owns one round counter across branch names.
After two implementation/review rounds without convergence, stop local patching
for that module and return to design; independent work can continue.

Fix verification consists of the original-defect oracle, impact-selected
regression and affected critical smoke paths. Public API, shared state, storage
format, dependency or installer changes require a written affected-regression
reason. Coverage gaps, faulty fixtures and report errors do not authorize product
behavior changes. Preserve behavior evidence when only measurement/reporting
changes; rerun only the required measurement scope. Two successive low-yield
batches trigger one grouped reachability/risk/cost reassessment before expansion.

### 2. Candidate freeze

Freeze candidate inputs after critical product defects converge and the intended
source and build inputs are qualified. Bind one clean source commit, source
bytes, closed dependency inventory and toolchain/build configuration; bind the
artifact identity to the actual outputs when the serialized builds finish.
Test-only qualification can continue against these fixed product bytes. The
remaining coverage and seven Windows-native checks are mandatory final release
gates, not an extra prohibition on preparing or freezing candidate inputs. This
addendum itself does not establish a candidate identity. Test/report-only changes
do not silently invalidate source-equal evidence; every reuse decision names
source, dependencies, environment, contract and verification scope. Product or
artifact changes create a new candidate identity and invalidate only affected
evidence.

### 3. Real bundle acceptance

Use the existing builder and the same closed dependency set for both builds;
compare all13 outputs, checksums, licenses, SBOM, assets and compatibility. Test
the actual candidate bundle in the supported clean Windows/Python environment:
fresh install/Check, a genuine0.9 baseline Repair, intended use, failure recovery,
required rollback and refusals/security. Source tests cannot replace these
artifact checks. Prior15b artifact/install evidence remains historical until the
new bundle is qualified. No mandatory requirement can be moved to a backlog or
waived as risk acceptance to complete the goal.

Primary serializes canonical aggregation, shared-ledger writes, exclusive
performance checks, final builds/deployment and same-probe operations. Keep the
existing work-ledger/release-matrix/native-result records; no new report system.
Each batch records actual closed behaviors, accepted/open product findings,
new valid arcs and remaining gates, elapsed run intervals/observed overlap, and
the next fixed scope/exit condition. Task/test/document counts and waiting are
not progress. All temporary artifacts remain under D:/codex-tmp; preserve needed
failures and never retry or bypass previously rejected cleanup.

### Wave11 Probe measurement correction

Candidate32eb3b7c run1 passed its four public behavior cases in19.2165334 seconds,
but retained only parent PID13796's native coverage shard. Treat behavior as
preserved pending complete-diff review and measurement as incomplete. This is
MEASUREMENT_REPORT, not a reason to change product behavior. The run-local ini
enabled patch=subprocess without concurrency=multiprocessing, although the real
worker uses spawn at worker.py:366. Installed coverage/control.py:573-576 only
enables its multiprocessing bootstrap with that concurrency option. In addition,
worker.py:624-630 calls abort immediately after the close reply; bootstrap-only
save can lose the race. The same cause and native correction already appear in
wave6/pyocd/run1/primary-measurement-diagnosis.json and run3/coverage.ini.

The same Luna owner may modify only its new control-result test to record each
real worker PID using public owned_pid and test-owned backend markers, and flush
the active native collector in the external test backend close before its reply.
Reuse the existing Wave6 pattern; do not change production shutdown, process
state or coverage data. Enable the existing native multiprocessing setting in
the run-local configuration. After commit/static/source148 checks, slot1 admits
one180-second measurement reconciliation run of these same four nodes at
r10/t/w11p/run2 and e/risk-v2/wave11/probe/run2, with fresh memory>=15%.
No other behavior suite is repeated. Keep run1 unchanged, match each actual
worker PID to a nonempty source-bearing raw shard, retain all shards through
combine --keep, and inspect required worker.py executed arcs separately from
the parent. A missing child shard, unexpected behavior, timeout or process
failure stops without an automatic retry. Independent review covers the full
accepted-base-to-final-head diff and both behavior and measurement decisions.

### Wave11 history cursor input correction

Monitor d93103aa run1 passed all four public cases in3.5122182 seconds. Its native
data reaches three new history arcs (755->758,1068->1069,1406->1407). Preserve
that behavior and raw evidence. The cursor case does not reach1484->1485: its
empty shortened batch is rejected earlier by _encoded_slice_base_bytes at451-452,
called at1457. Classify this as TEST_DATA_SCRIPT_ORACLE reachability, not PRODUCT.

The same Monitor owner may correct only the admitted cursor scenario's input
and restoration. Create a valid first batch with at least two values and obtain
an ordinal1 cursor through a public limit2 query; shorten the persisted batch
to one coherent nonempty value, including its index/digest/count, so the earlier
slice-size guard passes and start2 exceeds length1 at1484. Restore all original
payload/index rows and reuse the authenticated cursor successfully. No private
state, product mutation or additional scenario belongs in this correction.
After static/source checks and commit, slot1 admits one180-second run of only
test_shortened_cursor_batch_refuses_and_resumes_after_restore, under
r10/t/w11m/run2 and e/risk-v2/wave11/monitor/run2, memory>=15%. Do not repeat the
other three passed cases. First unexpected outcome stops without retry. Final
review reconciles source-equal run1 evidence and the corrected single-node run.

### Probe measurement design consolidation after two incomplete captures

Independent review AE28F9AC accepts the unchanged public behavior and run2's
seven actual worker shards, but finds the service target arcs absent from its
parent raw shard as well as the combined JSON. Do not credit those arcs or
silently combine complementary incomplete runs. This returns the single capture
contract to design before any further run; it does not authorize product changes.

The complete execution topology is pytest's main process, ProbeService's
asyncio.to_thread invoke (service.py:1340), and spawned backend workers. Installed
coverage/collector.py:143-160 enables thread tracing only with explicit thread
concurrency or an empty concurrency list. Specifying multiprocessing alone
disables that thread capture. Therefore the run-local native configuration must
declare concurrency=thread,multiprocessing, retain patch=subprocess, branch=true
and parallel=true, and retain the test-owned pre-reply collector save for the
worker-close termination race. No production call or state is replaced.

The existing Probe owner may use unchanged final test head
ffba4a4a163a0a6f9797e4f66b03cd151cf2a844 and correct only run-local capture/report
configuration. Explicit dictionary-key duplicate grouping closes the already
proven report defect. Verify the effective configuration and source148 before one
180-second run of the same four nodes, with fresh memory>=15%, at
r10/t/w11p/run3 and e/risk-v2/wave11/probe/run3. This remains slot1 and must follow
Monitor's admitted cursor run2 slot; primary hands over the execution slot.
The owner may prepare continuously without an extra approval gate.

Exit requires all four original behavior oracles, actual worker PID-to-raw-shard
binding, all raw hashes retained, and the four exact service arcs
995->999,1178->1179,1181->1182,1184->1185 present in the parent raw data and final
native JSON. Check raw-to-combined retention, not merely file counts or JUnit.
Record actual close/termination facts without asserting unobserved OS exit codes.
Any remaining mismatch stops this capture without another local patch/rerun.
Keep run1/run2 originals and their independent partial verdicts. Other admitted
suites should use both thread and multiprocessing tracking before first execution;
an already started suite is preserved and assessed from its actual raw evidence.

### Wave11 bounded fixture and launcher convergence

Monitor run2 reached the intended cursor guard, then failed in fixture restoration:
the shortened batch retained ordinal0, while restoration inserted both original
rows. This UNIQUE-key failure is TEST_DATA_SCRIPT_ORACLE, not a product defect.
After the input and restoration rounds, reconsider the whole fixture transaction
before further execution: save the exact batch and complete index; mutate both
coherently to one nonempty value; obtain public refusal with no write; replace the
entire affected index with the exact saved rows in the same restoration transaction;
reuse the original authenticated cursor successfully; close the public store.
Final test bf58c846 implements this bounded restoration. Independent complete-diff
review checks this whole sequence. Preserve run1's three valid arcs and run2's
original failure. Once an actual suite slot is free, run only the corrected B3 node
once under monitor/run3 and t/w11m/run3 (180 seconds, memory>=15%). Another failure
returns to this fixture design; it does not authorize product changes or an
unbounded rerun. The other three passing nodes are unchanged and are not repeated.

Probe run3 and Recovery run1 never started pytest. Probe's launcher required a
source148-check.json that had not been produced; Recovery's launcher interpreted
an unquoted SHA256 literal as a command. These are ENVIRONMENT_INFRASTRUCTURE_PLATFORM
launcher failures. Preserve both originals. The existing owners correct only
their run-local inputs and launchers, verify all required inputs together, and
continue the already admitted execution in fresh roots: Probe run4/t/w11p/run4
(slot1,180 seconds, unchanged ffba4a4a) and Recovery run2/t/w11r/run2 (slot2,300
seconds, unchanged14ea39b2). Source148 is actually rehashed against current
registry69D2; no fabricated or merely renamed match report. Check literal hash
values, required input paths, effective thread,multiprocessing/subprocess capture,
dictionary-key grouping and current source metadata before launching. No new
general framework or per-step approval gate is introduced. A pytest behavior or
capture failure stops; these pre-pytest attempts add no behavior or coverage credit.

### Whole replay Diagnostic reference correction after design return

Accepted integration base: `79cf67334e2b78463dc4a3f70d809d35557b250f`.
The Recovery owner retains `f421a4d086ee563adf770c96388cb9f61f98e26f` and all three
run roots. This is the whole-contract design return triggered by the two failed
producer scenarios, not a new name for another local patch. The primary owns
the appended specification and freezes its canonical representation and legacy
compatibility rules. The same owner may implement and first-verify continuously;
independent review checks the design and full returned diff before acceptance.

Expected bounded product scope is replay reference validation/normalization in
`acceptance/model.py`, `acceptance/recovery.py`, `acceptance/workflows.py`,
`acceptance/recovery_workflows.py`, and Diagnostic-reference fields only in
`cli.py`/`mcp_server.py`. A shared representation must have one authority in the
existing Acceptance layer; do not add a generic identity framework. Do not
modify unrelated UUID validation or Diagnostic storage/generation. Existing
owned public-producer tests and corresponding Acceptance model/workflow/CLI/MCP
tests are the test scope. Any additional product file requires a concrete
contract reason assessed by the primary before inclusion.

After design freeze, retain the old candidate ref and bring the existing clean
Recovery worktree forward to this accepted base without discarding its tests.
The owner continuously prepares, implements, commits, and performs the first
bounded verification; no per-step confirmation loop is introduced. Tests must
use public producers or existing valid external-input fixtures. Preserve exact
old persisted bytes and hashes as compatibility oracles. No private factory or
state replacement may manufacture a convenient Diagnostic identity.

Verification first covers the original public-producer failure and complete
reference lifecycle, alias/legacy compatibility, exact refusal/no-write, and
corruption/restoration. Expand affected regression to existing replay Acceptance
models/workflows and CLI/MCP tests because their public field changes; include
physical/continuation/finalization boundary smoke because dispatch shares the
entrypoint. Keep unrelated UI, performance, hardware, and installer evidence.
The owner records exact existing nodes before execution in the same plan; one
bounded suite may run in slot1 with independent D-drive run roots under
`r10/t/diagref/run1` and `e/risk-v2/diagnostic-reference/run1` (600 seconds,
memory available >=15%, first unexpected outcome stops, no automatic retry).
Capture actual child processes using native thread,multiprocessing/subprocess
coverage, preserve raw shards, and separate behavior from measurement verdicts.

First unexpected failure stops and is classified. Do not automatically widen
scope or keep patching a newly exposed related guard; compare it against this
whole-contract decision. Independent review covers the full accepted-base to
final candidate diff. Formal source/coverage migration stays serial and cannot
label U36 raw data as current coverage for changed source files. RC1 build-A
failed its source/wheel identity gate; no build-B or real installation is admitted
for that failed candidate. Freeze a new candidate only after accepted fixes and
build-input convergence, then perform the unchanged real-bundle release matrix.

Independent design review `run3/design-review.md` (92708ADE) requested explicit
field-domain/version compatibility and complete front-door/validator coverage.
The specification now names the complete paths, both CLI/MCP record inputs, and
the 1.0 backward-read/0.9 forward-read boundary. Keep the initial review unchanged;
request one delta review of these decisions. Existing 0.9 UUID evidence must
round-trip unchanged under 1.0. New non-RFC Diagnostic references may be refused
by 0.9 without mutation; final real-package compatibility and deployment notes
must not advertise them as usable after downgrade. This adds no downgrade route,
identity conversion, or installer change. No additional implementation file is
authorized beyond the six-file Diagnostic reference scope and affected tests.

### Next Monitor batch: complete public Analysis refusal and restoration

Accepted integration base: `35a183ded7987d33616ff123e83ecc04a64098be`.
The existing Monitor Luna/max owner retains `r10/w11m` and its accepted history
tests. Bring that tree forward with this plan without discarding any work.
This is test-only scope: `tools/stm32-monitor/tests/test_risk_analysis_public_refusals.py`,
using the existing `test_analysis` valid public fixtures and serialized inputs.
No product, service, export, CLI, dependency, or statistics-scope change is admitted.

Two public scenarios are frozen against U36 and unchanged Analysis source bytes:

1. Public wire/constructor rejection and valid restoration. Exercise bounded
   AnalysisError messages, nested request JSON depth, noncanonical register
   selectors, lineage logical-project-ID type and uppercase identity, inconsistent
   unchanged computation statistics, and a wrong marker schema. The seven target
   arcs in analysis.py are 191->192, 211->212, 253->254, 267->268, 273->274,
   505->509, and 1033->1034. Obtain valid inputs from existing public fixtures,
   vary external input only, assert the precise refusal and unchanged caller data,
   then verify the saved valid input still succeeds.
2. Public analyze_monitor_windows window and continuation rejection. Exercise a
   correctly sized tuple containing an ordinary object, valid SampleBatch objects
   carrying a wrong run or group identity, and a nonempty continuation identity
   without authoritative EvidenceStore support. The four target arcs are
   1141->1145, 1149->1150, 1151->1152, and 1411->1412. Preserve other bindings so
   the stated guard is first; use public constructors or dataclasses.replace,
   exact error/no-write assertions, and the unchanged valid restoration control.

No invalid SampleBatch may be smuggled past its constructor, private state changed,
or production check replaced. Ordinary WebSocket client close is explicitly
excluded: installed aiohttp __anext__ consumes CLOSE/CLOSING/CLOSED and raises
StopAsyncIteration before the proposed service.py:730->731 branch. A protocol
ERROR path would require a separately proven public input; this batch does not
authorize it. Correct the existing feasibility report rather than test the wrong
branch or count ordinary close as new coverage.

The same owner continuously prepares, implements, commits, and first-verifies.
Slot2 permits one 300-second suite at `r10/t/w12m/run1` and
`e/risk-v2/wave12/monitor/run1`, memory available >=15%. Reuse the existing guarded
launcher and native thread,multiprocessing/subprocess capture; retain raw shards
and verify combine --keep, source identity, and per-arc U36 delta. Another suite
may occupy slot1. Record actual times and descendant resources without claiming
overlap or descendant peak memory from a launcher-only PID. Stop at the first
unexpected result; classify before any correction. Independent full-diff review
and distinct behavior/measurement acceptance precede serial aggregation. Eleven
arcs are prospective, not earned; all frozen coverage thresholds remain unchanged.

### Existing generation tests: measurement-only reuse

After the admitted Monitor slot2 run stops, the existing engineering owner may
run only test_generation.py::test_stale_model_is_rejected,
::test_fixed_section_entry_non_dict_is_rejected, and
::test_missing_managed_target_is_recreated, unchanged. Their exact existing
oracles cover the public error code/details and managed-file reconstruction;
do not claim additional snapshot/restoration assertions absent from those tests.
The U36 targets are configure.py:158->159,596->597,1169->1170. Exclude the already
covered target-directory case and Windows-unproven NotADirectoryError branches.
No test or product edits are needed. Use an isolated existing worktree and fresh
`r10/t/w12p/run1`, `e/risk-v2/wave12/probe/run1`; 180 seconds, memory>=15%,
first unexpected result stops. Retain the native thread,multiprocessing/subprocess
capture configuration for consistency, but report no actual child evidence if
none is spawned. Only Toolkit source is measured by this run; frozen formal
package/core scopes remain unchanged. Preserve native raw shards and exact delta.

Diagnostic run1 is excluded from acceptance: its tail Monitor identity fixture
failed, and it loaded installed Monitor replay/sampler bytes older than U36.
Run2 binds both source roots explicitly and checks actual imported paths/hashes.
The same owner corrects the complete test-tail identity mapping from public
producer results; the six product files remain at55d91a23. One bounded run2 in
the already assigned slot1 follows. Another related fixture failure returns to
fixture design; it does not justify changing product behavior.

If Diagnostic run2 completes the three journeys, continue the already required
affected regression in the same ownership line. Add only compact/grouped/RFC
reference variants to the existing public CLI record and MCP record dispatch
tests, plus non-null compact/grouped diagnosis-checkpoint calls to the existing
MCP recovery adapter tests. Their public workflow stub verifies adapter argument
translation only; it is not end-to-end retry or persistence evidence. No private
validator/state substitution or product edit is admitted. Files are limited to
test_acceptance_cli.py, test_acceptance_mcp.py, and test_acceptance_recovery_mcp.py.
Reuse the independent review's exact persisted-model, existing replay refusal,
and physical/continuation/finalization public boundary selectors. Where an old
fixture patches an authoritative private check, use the already admitted real
public-producer journey as the oracle; do not manufacture native coverage from
that patch. Record the final selector list and reason before execution. One
600-second slot1 regression run uses t/diagref/regression1 and
e/risk-v2/diagnostic-reference/regression1, both source roots and loaded hashes,
the same resource/capture guards, and first-error stop. Passing run2 journeys
are not rerun merely because adapter tests change. Independent delta review,
runtime acceptance and six-source native requalification remain required.
