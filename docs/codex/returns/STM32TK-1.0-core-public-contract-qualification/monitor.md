# STM32 Toolkit 1.0 core monitor/evidence qualification return

Status: `NOT_RUN`.  This return is an implementation and static disposition record.  The
primary release owner must run the selectors below serially and independently review the
accepted-base-to-head diff before assigning any test verdict.

## Ledger and boundary

- Accepted base: `0a6bf2a6c591e5e89c6451050de3087168b77eb4`.
- Code head before this report commit: `fdd5425e68dedc7a25261c0bebf60c7da2d00b19`.
- Runtime baseline: `a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d`, unchanged.
- Branch: `codex/STM32TK-1.0-core-monitor`.
- Scope: public monitor observe/ingest/load/analyze/query/stream contracts and the shared
  evidence/replay wire boundary.  Test-only changes are confined to the owned files.
- No physical connection, real probe, installer, product import, pytest run, collection run,
  build, install, coverage run, or cleanup was performed by this owner.  Python was used only
  to parse the five modified test files with `ast`; the command used the approved temporary
  root `D:\codex-tmp\v10b-0918\r10\t\c95\m`.

The reviewed residual inventory is the existing
`D:\codex-tmp\v10b-0918\r10\e\python-final\core-public-contract-owner-residuals.json`.
Its monitor group contains 21 files and 638 missing arcs (400 monitor, 238 toolkit).  The
counts below are that already-reviewed inventory and remain an upper-bound planning map; they
are not recomputed coverage and are not a pass claim.

## Added or amended public selectors

The following selectors are the finite qualification wave.  Each calls a public constructor,
validator, service, store, or CLI path.  Fixtures are used only to supply valid software input;
they are not physical evidence.

### Shared toolkit contracts

- `tools/stm32-toolkit/tests/test_native_analysis_contract.py:175`
  `test_native_statistics_accepts_supported_object_shaped_batches` — valid object-shaped
  batches reach native statistics and preserve the closed result shape.
- `:325` `test_physical_monitor_facts_recompute_strict_register_and_variable_values` — public
  physical fact evaluation recomputes strict register and variable facts.
- `:375` `test_physical_monitor_fact_policy_and_window_refusals` — policy, window, and minimum
  pair refusals return the exact contract error.
- `:415` `test_physical_monitor_fact_rejects_malformed_selected_wire_samples` — malformed
  selected samples are rejected at the public wire boundary.
- `:470` `test_physical_monitor_fact_rejects_conflicting_widths_and_preserves_input` — a
  conflicting width is rejected and the caller's mapping is unchanged.
- `:485` `test_physical_monitor_fact_rejects_noncanonical_selectors` — selector vocabulary is
  rejected before fact evaluation.
- `:506` `test_native_statistics_rejects_malformed_timestamp_windows_and_digest` — malformed
  timestamp windows and request digest are rejected with the exact public message.
- `:522` `test_native_request_expected_reference_guards_reject_drift` — expected reference
  identity drift is rejected by public request validation.
- `:537` `test_native_statistics_rejects_value_and_position_budget_overflows` — the values
  budget asserts `before values exceed their limit`.  Each side is first bounded to 1,024
  positions by `_timestamps`; therefore the later combined 2,048-position check is
  unreachable through this public caller and is recorded as an earlier-invariant barrier.
- `tools/stm32-toolkit/tests/test_monitor_replay_contract.py:682`
  `test_shared_physical_contract_rejects_nested_wire_mutations` — 26 valid-transcript
  mutations each assert the exact public rejection message.  The captured-time mutation
  updates both `capturedUnixNs` and `capturedAtUtc`, so the intended monotonic guard is reached
  after the scheduled/captured UTC guards.
- `:769` `test_shared_physical_canonicalizer_rejects_unsafe_json_values` and `:777`
  `test_shared_physical_canonicalizer_rejects_cycles_without_mutating_input` — unsafe values
  and cycles are rejected without changing the input mapping.
- `tools/stm32-monitor/tests/test_replay.py:585`
  `test_public_replay_error_constructor_rejects_unknown_or_unbounded_values` — public replay
  error code/message/field bounds are closed.
- Existing selector `test_public_replay_reference_constructor_rejects_identity_and_window_fields`
  is expanded in the same wave to cover the full public reference identity/window matrix.
- `tools/stm32-monitor/tests/test_physical_publication.py:219`
  `test_public_physical_v2_reference_rejects_invalid_identity_and_windows` — physical v2
  reference identity and window guards are asserted through the public constructor.

### Monitor models, history, and CLI

- `tools/stm32-monitor/tests/test_models.py:242`
  `test_live_state_public_validation_rejects_each_inconsistent_status_guard` — the firmware
  row starts from a complete valid firmware object, then changes only `buildId`; every other
  status guard is similarly mutated from a valid status.
- `:281` `test_live_sample_public_validation_rejects_each_batch_guard` — each public batch guard
  is reached from a valid batch and the input remains unchanged.
- `tools/stm32-monitor/tests/test_history.py:1980`
  `test_public_retention_rejects_persisted_accounting_corruption_without_deletion` — public
  retention rejects negative persisted accounting with `MONITOR_STORAGE_CORRUPT` /
  `monitor storage accounting is invalid`, and rejects a negative selected `value_count` with
  `MONITOR_STORAGE_CORRUPT` / `monitor history is corrupt`; the candidate row remains after
  the rejected pass.
- `tools/stm32-monitor/tests/test_analysis_cli.py:524`
  `test_public_analysis_cli_maps_each_adapter_failure_class` — the request file is a real
  `AnalysisRequest` built from two valid public `MonitorRunRef` values and a real project
  descriptor.  Only `compare_monitor_runs` is replaced, and six provider/error classes assert
  exact adapter codes and messages; the model parser is not bypassed.

## Precise residual source-to-seam disposition

The lists give every residual source function and the source line(s) at which the reviewed
inventory starts a missing arc.  A line list is compacted as `function [count: starts]`; the
complete start/end arc pairs remain in the owner inventory cited above.  `PUBLIC` means the
named public selector is the caller seam for the guard.  `EARLIER` means the public contract
rejects the malformed state before the later guard.  `PLATFORM` names a concrete OS/native
capability.  `RACE` names a filesystem identity race that must be exercised only through an
existing public provider seam.  `PHYSICAL` is deferred because this owner has no hardware
authority.

### Toolkit residuals: 238 arcs

- `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py` (2):
  `_manifest_names [2: 231,236]` checks case-fold collisions, regular-file identity, and
  canonical manifest names.  **PUBLIC:** `EvidenceCatalog.rebuild` through
  `test_manifest_directory_rejects_invalid_or_nonregular_entries`,
  `test_corrupt_manifest_fails_rebuild_and_preserves_old_catalog`, and
  `test_query_fails_closed_for_corrupt_or_hard_linked_catalog`.  The remaining alternatives
  require one of those persisted path states; no direct helper call is needed.
- `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` (20):
  `RootRecord.__post_init__ [1:306]`, `_snapshot_entries [3:475,525,550]`,
  `_scan_manifests [1:664]`, `_scan_objects [1:721]`, `get_root [1:792]`,
  `_consume_authorization [2:1012,1030]`, `_delete_identity_bound [9:1107,1114,1145,1150,1157,1176,1186,1187,1187]`,
  `_apply_gc_locked [1:1259]`, and `_apply_reconstructed [1:1387]` cover closed root metadata,
  directory snapshots, reachability, single-use authorization, and identity-bound deletion.
  **PUBLIC:** `test_get_root_*`, `test_apply_*`, `test_reconstructed_*`,
  `test_authorization_*`, and the identity/race selectors from `test_evidence_gc.py` invoke
  plan/get/apply, including hard links, replacement roots, changed bytes, lock ordering, and
  post-snapshot creation.  Win32 handle-only alternatives are bounded by
  `test_win32_identity_helpers_fail_closed_on_invalid_handles_and_shapes`; the other remaining
  arcs require the serialized filesystem mutation seam already used by the named public tests.
- `tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py` (1):
  `_JsonState.visit [1:92]` is recursive canonical JSON freezing.  **PUBLIC:**
  `test_from_dict_rejects_deep_json_before_python_recursion`,
  `test_authoritative_decoder_rejects_bom_duplicate_noncanonical_order_and_non_nfc`, and the
  direct envelope/model boundary tests supply the only supported entry to this guard;
  malformed recursive state is rejected before evidence publication.
- `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` (20):
  `_existing_managed_path [2:126,138]`, `_mutation_lock [4:150,173,182,202]`,
  `_read_file_bytes [7:226,234,236,238,243,247,264]`, `_hash_file [1:302]`,
  `_ingest_file_locked [1:448]`, `get_envelope [2:597,603]`, and `read_artifact
  [3:612,618,632]` enforce root/path identity, lock identity, bounded reads, digest/size
  stability, and verified artifact reads.  **PUBLIC:** the `test_evidence_store.py` ingest,
  source race, second-pass, artifact read, link, path replacement, and publication-fault
  selectors reach these through `EvidenceStore.ingest`, `get_envelope`, and `read_artifact`.
  POSIX/Windows lock implementation alternatives are native capability branches; the public
  path and identity guards remain software-testable through those selectors.
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_analysis_contract.py` (48):
  `_physical_reference [1:107]`, `validate_native_request [4:129,132,136,138]`,
  `_mapping_field [5:161,162,163,166,166]`, `_native_sample [6:176,181,183,185,191,206]`,
  `_strict_monitor_fact_sample [13:228,233,236,241,253,261,263,267,269,272,275,277,294]`,
  `evaluate_physical_monitor_fact [10:319,322,324,331,334,336,344,346,361,368]`,
  `_timestamps [5:377,379,386,391,394]`, and `native_statistics [4:417,423,429,433]` are
  reached by the nine native selectors above.  The explicit `NATIVE_MAX_BATCHES=1024` check
  in `_timestamps` precedes the combined `NATIVE_MAX_POSITIONS=2048` check, so a pair of
  public sides cannot reach the combined branch: this is an exact earlier-invariant barrier,
  not an untested budget claim.
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py` (52):
  `_cleanup_resources [1:210]`, `_canonical_root [1:271]`, `_windows_directory_handle
  [3:333,339,346]`, `_DirectoryGuard.capture [1:433]`, `_DirectoryGuard.close
  [3:480]`, `_safe_mkdir_windows [3:527,532,542]`, `_safe_mkdir_posix
  [3:576,587,611]`, `_prepare [1:662]`, `_read_plan_admission [2:864]`,
  `_verify_admission [1:869]`, `_verify_read_plan [1:882]`,
  `_prepare_read_plan.invalidate_failed_prepare [2:919]`, `_prepare_read_plan
  [5:926,933,948,1012]`, `_read_prepared [7:1042,1043,1055,1065,1069]`, `_read_batch
  [7:1084,1086,1091,1114,1151,1167]`, `revalidate [2:1235,1308]`,
  `revalidate.invalidate_failed_revalidation [1:1246]`,
  `_revalidate_lightweight.revalidate_sources [1:1336]`, `close [3:1365,1367]`, and
  `open_monitor_observation [7:1519,1522,1529,1542,1544,1548,1555]` are reached through
  `test_monitor_closed_worker_selection_and_path_identity_boundaries`, the public supervisor
  tests, `test_posix_directory_creation_*`, `test_windows_directory_creation_*`, guarded
  factory tests, and the public catalog/read-plan tests in `test_monitor_observation.py`.
  POSIX descriptor and Windows handle alternatives are separated by the platform capability;
  cleanup and identity races must stay on those public factory seams.
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_replay_contract.py` (95):
  `_copy_json [9:190,195,204,208,214,216,218,224,226]`, `_copy_physical_json
  [11:320,329,333,335,342,346,352,354,356,366,368]`, typed `scalar [6:388,391,392,395,397]`,
  typed `freeze [8:403,411,415,424,426,432,436,438]`, `_validate_monitor_typed_json
  [3:450,456,460]`, `canonical_physical_json_bytes [1:491]`,
  `decode_physical_transcript_bytes [4:499,501,525,531]` plus its `pairs [1:507]`,
  `_uuid [1:562]`, `_session [1:574]`, `_validate_binding [4:611,617,619,621]`,
  `_validate_watch [2:632,639]`, `_validate_sample [4:650,654,659,659]`, `_validate_batch
  [4:672,687,691,697]`, `_validate_physical_binding [3:720,722,724]`,
  `validate_physical_transcript [12:746,749,751,753,755,757,762,766,770,775,783,785]`,
  `validate_replay_document [10:796,799,801,803,805,810,818,835,837,839]`,
  `_validate_run_reference_common [6:853,855,866,902,904,921]`, and
  `validate_run_reference [5:932,937,943,945,951]` are reached through the shared byte
  decoder, closed document/reference, physical nested mutation, canonicalizer, and typed
  budget selectors in `test_monitor_replay_contract.py`.  The amended matrix preserves valid
  upstream fields before each intended later guard; no branch is reached by bypassing a
  public invariant.

### Monitor residuals: 400 arcs

- `tools/stm32-monitor/src/stm32_monitor/analysis.py` (30):
  `AnalysisError.__init__ [1:191]`, `_reject_tuples [1:211]`, `_watch [1:253]`, `_uuid_text
  [2:267,273]`, `AnalysisComputation.__post_init__ [2:430,505]`,
  `AnalysisComputation.from_value [1:520]`, `AnalysisLineage.new [2:622,624]`,
  `AnalysisLineage.from_value [1:653]`, `_result_unsigned [1:740]`,
  `AnalysisResult.__post_init__ [2:881,889]`, `AnalysisEvidenceRef.__post_init__ [1:976]`,
  `AnalysisEvidenceRef.from_value [1:987]`, `DiagnosticMarker.__post_init__
  [3:1033,1040,1042]`, `DiagnosticMarker.from_value [1:1082]`, `_validate_window
  [4:1131,1141,1149,1151]`, `_trusted_sample [3:1204,1208,1217]`,
  `analyze_monitor_windows [1:1268]`, and `validate_continuation_runs [2:1411,1419]` are
  public model/window seams.  **PUBLIC:**
  the constructor/parser matrix and window tests in `test_analysis.py`, especially
  `test_request_public_parser_and_constructor_refuse_invalid_schema_reference_and_skew`,
  `test_public_window_reference_authority_rejects_count_order_and_boundary_contradictions`,
  the scalar/sample exclusion tests, and continuation lineage tests.  Tuple/subclass and
  invalid typed states are rejected by the public parser before deeper result guards.
- `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py` (55):
  `AnalysisWorkflowError.__init__ [2:105,107]`, `AnalysisPublication.__post_init__
  [4:171,173,175,177]`, `AnalysisBundleRef.__post_init__ [1:211]`,
  `AnalysisBundleRef.from_value [1:224]`,
  `_continuation_for_runs [1:256]`, `_diagnostic_hash [1:262]`, `_safe_text [1:268]`,
  `_validate_transcript [4:331,359,387,452]`, `_validate_reference_authority
  [4:483,494,501,509]`, `_validate_diff_evidence [1:543]`, `_validate_inputs
  [4:576,604,633,661]`, `_load_physical_source [5:730,732,732,735]`, `_query_window
  [4:766,770,772,775]`, `_publish_checkpoint [2:1001]`, `_validate_published_derived
  [1:1030]`, `_test_identity_matches_reference [1:1053]`, `compare_monitor_runs [1:1102]`,
  and `export_analysis_bundle [17:1229,1231,1239,1241,1243,1245,1250,1252,1254,1268,1301,1336,1349,1358,1383,1397,1402]`
  are public workflow seams.  **PUBLIC:** `test_compare_monitor_runs_publishes_changed_analysis_and_marker`,
  `test_export_analysis_bundle_reloads_real_target_runs`, the source/target provider failure
  selectors, public query-page contradiction selectors, and the derived publication reload,
  root, artifact, and upstream-authority selectors in `test_analysis_workflows.py`.  The
  remaining physical-source branches require a physical reference with authenticated
  transcript/TestRun evidence and are `PHYSICAL`; replay bundle branches remain software
  testable through the named reload/provider selectors.
- `tools/stm32-monitor/src/stm32_monitor/auth.py` (1): `MonitorAuth.create [1:43]` is the
  exact token factory boundary.  **PUBLIC:** `test_token_is_exactly_32_random_bytes_and_never_appears_in_repr`,
  `test_token_factory_must_return_exactly_32_bytes`, and the bearer/cookie matrix.  Invalid
  factory output is rejected before an auth object can be published.
- `tools/stm32-monitor/src/stm32_monitor/cli.py` (25): `_AdapterFailure.__init__ [1:70]`,
  `_load_context [1:287]`, `_decode_json_bytes [2:312,323]`, `_load_json_file [1:338]`,
  `_model_wire [3:345,348,354]`, `_load_request [2:364]`, `_load_source_change [2:376]`,
  `_adapter_error [12:475,477,477,479,479,483,484,487,487,490,492,494]`, and
  `_has_provider_io_cause [1:506]` are public CLI adapter seams.  **PUBLIC:** the new real
  request/provider matrix plus `test_adapter_cli_rejects_invalid_project_context_before_workflow`,
  `test_cli_returns_sanitized_json_failure_without_traceback`, and source-change/operation
  tests.  The adapter's `PermissionError` branch is the `OSError` provider class, and the
  catch-all provider branch is reached only by an actual provider exception; the parser is no
  longer mocked around a malformed request.
- `tools/stm32-monitor/src/stm32_monitor/exports.py` (15): `_create_regular_exclusive
  [2:282,284]`, `_read_regular_limited [1:308]`, `_open_verified_regular [2:346,359]`,
  `HistoryExporter._safe_remove_tree [1:703]`, `_validate_record [3:713,725,737]`,
  `_recover_pending [1:799]`, `_recover_all_pending [1:825]`, `create_export
  [3:858,861,881]`, and `get_export [1:934]` are reached through public export creation,
  download, recovery, metadata, path, quota, and tamper selectors in `test_exports.py`.
  Replacement/descriptor branches require the existing public filesystem mutation seam;
  direct helper invocation is not a disposition.
- `tools/stm32-monitor/src/stm32_monitor/groups.py` (7): `_decode_cursor [1:79]`,
  `list_group_page [2:161,175]`, `_check_limits [1:239]`, `update_group.write [1:328]`,
  and `import_groups [2:429,431]` are reached by `test_group_page_cursor_is_deterministic_revision_bound_and_store_local`,
  `test_group_and_item_limits_fail_without_partial_writes`, `test_import_is_bounded_explicit_atomic_and_conflict_safe`,
  and the public storage/path/corruption group selectors.  The cursor and import guards are
  entered only after the public group model has accepted a valid closed document.
- `tools/stm32-monitor/src/stm32_monitor/history.py` (32): `_clone_isolated_verified_page
  [2:354,364]`, `_decode_history_batch [2:755,764]`, `_normalize_v1_batch [1:924]`,
  `_observed_storage_snapshot [1:991]`, `append_batches [2:1068,1081]`,
  `append_batches.write [1:1117]`, `_query_history [1:1256]`, `_query_history.read
  [13:1264,1349,1395,1406,1408,1418,1484,1487,1490,1619,1645,1647,1659]`,
  `_stream_verified_batches.read [2:1847,1874]`, and `run_retention.write
  [7:1915,1918,1934,1956,1959,1965,1973]` are public history seams.  **PUBLIC:** the
  existing v1 migration, canonical row/digest/index corruption, cursor/page, cache, stream,
  append-batch, and analysis workflow query selectors, plus the new retention accounting and
  candidate corruption selector.  The new selector reaches the storage preflight accounting
  guard and the retention `logical_before`/candidate-row/rollback guards using persisted SQL
  corruption setup, while assertions remain on `run_retention` and `query_history`.
- `tools/stm32-monitor/src/stm32_monitor/models.py` (24): `_freeze_json [1:48]` and nested
  `freeze [4:119,125,129,131]`, `_utc_text [1:155]`, model `__post_init__
  [4:200,240,243,812]`, `_validate_live_status [8:641,666,671,683,685,690,706,708]`,
  `_validate_live_batch [5:744,746,749,752,762]`, and `HistoryBatchSlice.immutable_snapshot
  [1:943]` are reached through the public model and history constructors.  **PUBLIC:** the
  new live status/batch matrices, existing `test_analysis.py` closed-model tests, and history
  semantic mismatch tests.  The firmware mutation begins with a complete valid object, so its
  intended `buildId` guard is not masked by `firmware is None`.
- `tools/stm32-monitor/src/stm32_monitor/probe_session.py` (16): `_read_group [2:139]`,
  `_map_read_result [2:161,175]`, `invalidate_read_plan [1:218]`,
  `prepare_read_plan.invalidate_failed_prepare [1:242]`, `prepare_read_plan [3:267,271,279]`,
  `read [3:303]`, `revalidate.invalidate_failed_revalidation [1:337]`, `revalidate [1:376]`,
  and `_revalidate_lightweight [2:385,400]` are reached through the public
  `ProbeSession` selectors: grouped reads, admission/cancellation, provider failures, plan
  drift, revalidation, SVD gates, and malformed report mappings.  A read plan is only created
  after public admission; invalid private plan states are therefore earlier-invariant
  barriers.
- `tools/stm32-monitor/src/stm32_monitor/replay.py` (105): constructor guards
  `MonitorReplayError [2:182,184]`, authenticated model `__post_init__ [8:216,359,381,510,512,521,530,640]`,
  `_require_hash [1:241]`, `_require_uuid [2:247,253]`, `_require_text [3:259,261,263]`,
  `MonitorRunRef.from_value [1:652]`, root/reference helpers `_expected_transcript_envelope
  [1:859]`, `_expected_root [1:897]`, `_reference_metadata [1:924]`,
  `_validate_existing_reference_root [7:1020,1022,1024,1027,1041,1056,1066]`,
  `_validate_existing_root [3:1112,1133,1133]`, `_load_existing_batches [1:1166]`,
  `_publish_transcript [1:1234]`, `_resolve_reference_root_race [4:1258,1273,1273,1282]`,
  `_publish_reference [4:1311,1323,1333,1333]`, `_physical_copy_json [11:1379,1382,1387,1391,1395,1401,1405,1411,1413,1424,1426]`,
  `_physical_transcript_wire [1:1503]`, `_physical_history_batches [9:1774,1785,1833,1859,1868,1872,1878,1880,1894]` plus
  `finish_current [3:1809,1811,1824]`, `_physical_test_run [1:1939]`,
  `_parse_physical_transcript [5:2024,2038,2046,2055,2057]`, `_decode_physical_json_bytes
  [4:2079,2081,2115,2117]` plus `pairs [1:2087]`, `_physical_publish_transcript
  [5:2137,2146,2146,2148,2148]`, `_physical_publish_reference [3:2195,2204,2204]`,
  `_load_monitor_run_authenticated [15:2234,2243,2265,2267,2269,2287,2289,2305,2307,2360,2363,2366,2390,2400,2400]`,
  `publish_physical_monitor_run [2:2452,2542]`, and `ingest_monitor_replay [5:2586,2599,2669,2669,2675]` are reached through
  the public replay constructor/parser, ingest, publication, root recovery, provider mismatch,
  and reload selectors in `test_replay.py`.  **PUBLIC:**
  `test_fixed_after_survives_fresh_history_and_evidence_reload_and_ref_is_stable`, the
  reference/transcript/artifact provider-mismatch tests, malformed-root/no-history-mutation
  tests, exact retry/idempotency tests, and the new constructor matrix.  Replay loading is
  software-testable through those fixtures.  Authenticated physical loading and physical
  TestRun branches require real physical transcript evidence and are `PHYSICAL`; they cannot
  be relabeled from replay fixtures.
- `tools/stm32-monitor/src/stm32_monitor/runtime.py` (23): `_ensure_owned_directory [1:139]`,
  `_WorkspaceLock.acquire [6:196,212,219,223,225,225]`, `_atomic_json [2:273,276]`,
  `MonitorRuntime.start.cleanup_partial [1:539]`, `start [4:556,557,557,564]`,
  `_heartbeat_loop [1:671]`, `_list_probes [2:746,747]` plus `.project [1:772]`,
  `live_subscribe [1:1240]`, and `_stop_owned [4:1297,1297,1304,1304]` are reached through
  the public runtime start/stop, lock, probe catalog, live, heartbeat, and cleanup selectors.
  `msvcrt` versus `fcntl` locking is a concrete OS capability split; replacement/hardlink
  guards use `test_runtime_lock_rejects_hardlink_redirect_and_descriptor_replacement_without_write`
  and the public lock contention tests.
- `tools/stm32-monitor/src/stm32_monitor/sampler.py` (27): `set_state_listener [1:136]`,
  `start [1:214]`, `_current_group [4:258,265,270,274]`, `_block [1:284]`, `_produce
  [5:292,297,299,311,317]`, `_enqueue_history [1:377]`, `_broadcast [1:398]`,
  `_history_writer [2:405,423]`, `_record_history_drop [1:444]`, `pause [1:457]`,
  `resume [1:480]`, `_stop_run [5:489,491,496,500,502]`, `subscribe [1:550]`,
  `subscribe_deliveries [1:565]`, and `_close_owned [1:572]` are reached by the public
  sampler lifecycle, group revision/provenance, cancellation, deadline, bounded queue, drop,
  and subscriber selectors in `test_sampler.py`, plus the runtime lifecycle selectors.
  Producer timing and cancellation alternatives require the existing event/task seams; no
  impossible race is synthesized.
- `tools/stm32-monitor/src/stm32_monitor/service.py` (13): `_start_locked [3:237,239,345]`,
  `_cleanup_runner [1:359]`, `_cleanup_owned_runner [3:371,381,390]`, route `handler [1:550]`,
  `_download [1:599]`, `_live [2:648,730]` plus `send [1:695]`, and `stop [1:747]` are
  reached by the public HTTP/WebSocket route, authenticated download/live, start/stop, and
  partial cleanup selectors in `test_service.py`.  Oversized payloads, route grammar, auth,
  queue eviction, and cleanup priority are already represented at the public server seam.
- `tools/stm32-monitor/src/stm32_monitor/storage.py` (27): `_require_path [1:300]`,
  `_directory_snapshot [1:327]`, `_ensure_parent [2:362,381]`,
  `_inspect_storage_files.accept_deleting_optional [1:453]`, `_inspect_storage_files
  [3:483,487,496]`, `_integrity_fingerprint [1:535]`, `_migrate_v1 [1:749]`, `_initialize
  [1:856]`, `_preflight_existing [6:882,943,945,986,988,996]`, `_create_database_file
  [1:1014]`, `_ensure_sidecars [1:1035]`, `_open_write [7:1068,1077,1082,1086,1101,1105,1111]`,
  and `_refresh_owned_integrity [1:1289]` are reached through the public database
  constructor/read/write/try-write and history/group/export selectors in `test_storage.py`,
  `test_history.py`, `test_groups.py`, and `test_exports.py`.  The existing selectors cover
  missing/replaced/hard-linked files, WAL/SHM identity, metadata/application/schema failures,
  bounded retries, and cancellation.  OS filesystem behavior remains a platform capability
  boundary; no private storage helper is used as a substitute caller.

## Release handoff

The code selectors are committed at `fdd5425e68dedc7a25261c0bebf60c7da2d00b19`; this report
must be committed separately so the code head above remains the pre-report reference.  The
primary owner must inspect the complete `0a6bf2a6c591e5e89c6451050de3087168b77eb4..HEAD` diff,
then run the applicable selectors with `TEMP`, `TMP`, and `TMPDIR` bound under the approved run
root.  Any result remains `NOT_RUN` until that serial execution and independent review occur.
