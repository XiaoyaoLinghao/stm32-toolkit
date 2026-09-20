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
