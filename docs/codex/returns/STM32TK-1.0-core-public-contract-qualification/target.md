# Target public-contract qualification return

## Ownership and source identity

- Owner: Target qualification test implementation.
- Accepted base: 0a6bf2a6c591e5e89c6451050de3087168b77eb4.
- Runtime source identity required by the plan: a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d.
- Test head before this report commit: 7f1eaba05c6b7378cea6b1466a9c1195479560d0 (test: validate replay parent before publication writes).
- Product/runtime source files changed: none.
- Test-only files changed by this wave:
  - tools/stm32-toolkit/tests/test_target_runner.py
  - tools/stm32-toolkit/tests/test_testing_workflows.py
  - tools/stm32-toolkit/tests/test_hardware_workflows.py
  - tools/stm32-toolkit/tests/test_testing_mcp.py
  - tools/stm32-toolkit/tests/test_target_replay_publication.py
  - tools/stm32-toolkit/tests/test_probe_lease.py
  - tools/stm32-toolkit/tests/test_probe_service.py

The wave reaches the target lifecycle, workflow, MCP, controlled-fault,
publication/reload, lease-record, and handoff-metadata contracts through the
existing fake provider, fake transport, EvidenceStore, and service seams. It
does not invoke real pyOCD, probe discovery, hardware, build, package, or
install paths.

## Actual function selectors

The selectors below are the functions added or materially extended by this
head. Parameterized selectors have the bounded case count in parentheses.

### Target runner and workflow

- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_cancellation_closes_transport_but_preserves_borrowed_probe
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_failed_stream_settles_authority_and_borrowed_probe
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_borrowed_probe_success_reloads_published_evidence
- tools/stm32-toolkit/tests/test_target_runner.py::test_physical_target_publication_and_reload_bind_retained_run_evidence
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_prepare_rejects_cross_bound_support_before_authority_write (four support mutations)
- tools/stm32-toolkit/tests/test_target_runner.py::test_target_runner_rejects_malformed_consumed_value_before_dispatch
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_prepare_rejects_malformed_public_request_before_provider (four request mutations)
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_prepare_binds_fixed_facts_and_settles_provider (normal and recovery)
- tools/stm32-toolkit/tests/test_testing_workflows.py::test_target_execute_rejects_invalid_authority_before_loading_state

The workflow binding test now uses canonical hexadecimal workspace, firmware,
snapshot, and revision values, patches the post-attach
load_fresh_firmware_facts seam with an identical fresh record, and asserts
the complete immutable binding: workspace, project, session, revision,
snapshot, build, ELF, target identity, inventory digest, cases, and recovery
intent.

### Public hardware and MCP boundaries

- tools/stm32-toolkit/tests/test_hardware_workflows.py::test_controlled_fault_rejects_invalid_binding_before_target_control (two invalid binding shapes)
- tools/stm32-toolkit/tests/test_hardware_workflows.py::test_controlled_fault_requires_running_target_before_authorizing_halt
- tools/stm32-toolkit/tests/test_hardware_workflows.py::test_controlled_fault_rejects_invalid_halt_response_and_restores_target (two malformed halt responses)
- tools/stm32-toolkit/tests/test_testing_mcp.py::test_registered_target_prepare_rejects_invalid_case_ids_before_workflow (six schema-invalid case-ID matrices)

These selectors enter through fault_workflow and the registered
stm32_test_target_prepare tool. They assert refusal before target control or
workflow delegation, exact response classification, restoration ordering,
and the absence of delegate calls.

### Publication, lease, and handoff boundaries

- tools/stm32-toolkit/tests/test_target_replay_publication.py::test_target_replay_publication_rejects_rehashed_descriptor_parent_before_write (two rehashed-parent mutations)
- tools/stm32-toolkit/tests/test_probe_lease.py::test_heartbeat_replace_failure_preserves_record_and_cleans_temporary_file
- tools/stm32-toolkit/tests/test_probe_service.py::test_debug_handoff_metadata_reads_the_committed_attachment_identity

The replay selector constructs a valid rehashed parent that retains the
existing descriptor and stream artifact identities, then enters the public
Publisher.publish_target_replay path. It requires the exact stream or role
contradiction message, EVIDENCE_CORRUPT, and byte-identical evidence and
results roots before any write. The lease selector injects a record
replacement failure through the public heartbeat path and requires the old
record to remain intact with no temporary file left behind. The handoff
selector reads metadata through a committed Observe attachment and checks the
provider dispatch and returned identity.

## Public trigger, guard, and assertion map

| Public trigger | Guard family reached | Required assertion |
| --- | --- | --- |
| TargetTestRunner.run with caller cancellation during transport polling | Transport cancellation, dependency settlement, and borrowed-probe ownership | Cancellation propagates; transport closes; borrowed probe remains open; consumed authorization remains terminal; no pass manifest is rooted. |
| TargetTestRunner.run with an incomplete stream | Decoder/validator failure after guarded flash | Stable stream error; transport closes; borrowed probe remains open; consumed record remains; no terminal manifest is created. |
| TargetTestRunner.run with a valid stream and physical provenance | Guarded flash, transport lifecycle, physical Evidence envelope, and repository reload | Raw stream and manifest retain exact identity; physical provenance is true; publication and authoritative reload return the same envelope/root/manifest. |
| TargetTestRunner.prepare with cross-bound backend, target, mailbox, or extra support data | Closed support profile and nested transport binding | TEST_PROTOCOL_INVALID before authority record creation. |
| TargetTestRunner.run with a malformed consumed value | Public authorization model validation | TEST_AUTHORIZATION_INVALID before flash or transport dispatch; owned probe cleanup still occurs. |
| target_test_prepare with malformed request fields | Public workflow request validation and recovery boundary | TEST_PROTOCOL_INVALID before project state/provider construction; no provider call. |
| target_test_prepare with normal and recovery provider seams | Fixed firmware facts, fresh-facts revalidation, attach/cleanup lifecycle | Exact facts and recovery intent are bound; normal mode starts/attaches/closes provider; recovery mode skips physical provider startup. |
| target_test_execute with a malformed action digest | Public authorization gate | TEST_AUTHORIZATION_INVALID before state loading or provider access. |
| fault_workflow with invalid binding, halted initial target, or malformed halt response | Controlled binding, running-state precondition, halt response validation, and recovery | No control for invalid binding/initial state; malformed halt response is classified; resume is authorized once and returns the target to running. |
| Registered stm32_test_target_prepare with empty, duplicate, noncanonical, oversized, or non-string case IDs | MCP Pydantic model boundary | Schema refusal occurs before the request delegate is called. |
| publish_target_replay with a valid rehashed descriptor parent whose role or stream metadata contradicts its descriptor | _target_parent public publication provenance checks | Exact role or stream contradiction message and EVIDENCE_CORRUPT; evidence and results bytes remain unchanged before publication. |
| publish_target_physical followed by Repository.load | Physical manifest/raw artifact membership, provenance, root binding, and reload | Physical envelope/root is accepted only with exact retained artifacts and reload returns the same immutable objects. |
| ProbeLease.heartbeat with replacement failure | Atomic record write and temporary-file cleanup | PROBE_REGISTRY_UNAVAILABLE; prior record is unchanged and temporary write is removed. |
| ProbeService.debug_handoff_metadata through an attached fake backend | Attachment identity, backend invocation, metadata model validation | One provider call returns the committed probe/target/board identity. |

## Residual source disposition

The accepted native residual map is source-file ownership based. Its target
group contains 44 files and 937 missing arcs; that value is an upper bound and
is not a test quota. Every file in that group is accounted for below. The
table records public trigger families and their boundaries; it does not claim
that the named matrices cover every listed arc. Hardware, real pyOCD, native
process, and OS-only paths remain in the denominator because this wave is
forbidden from claiming those environments.

| Residual source files and native upper bound | Existing public trigger or this wave | Disposition for this wave |
| --- | --- | --- |
| cli.py (16), context.py (5), doctor.py (4), mcp_server.py (73), testing_workflows.py (38): 136 | test_mcp_server.py, test_mcp_roots.py, test_testing_mcp.py schema/root/delegate matrices; new target case-ID matrix; new fixed-facts workflow matrix; test_context.py, test_doctor.py, and test_cli.py when present | Public root binding, strict MCP models, workflow refusal, and context/doctor construction are represented by existing callers and the new target routes. CLI startup, platform process discovery, and other unexecuted arcs remain visible unresolved for the released batch; no private helper padding is added. |
| hardware_workflows.py (61), debug/dwarf.py (36), debug/fault.py (12), debug/firmware.py (4), debug/model.py (6), debug/read.py (2), debug/sampling.py (2), debug/svd.py (40), debug/types.py (10), execution_provenance.py (5): 178 | Existing test_hardware_workflows.py, test_fault.py, test_debug_firmware.py, test_debug_read.py, test_svd.py, and test_debug_handoff.py; new fault_workflow controlled binding/state/response matrix | _controlled_fault_action now has public software-provider triggers for invalid binding, non-running target, malformed halt response, and restoration. Existing debug/SVD/fault matrices cover malformed public models and provenance. DWARF/SVD toolchain, real symbol files, and physical target state branches are the native/toolchain subset eligible for later external deferral; all other residual arcs remain unresolved pending runtime evidence. |
| testing/target.py (71), testing/protocol.py (33), testing/transports/mailbox.py (3), testing/transports/rtt.py (3), testing/transports/semihosting.py (2), testing/transports/uart.py (1): 113 | test_target_protocol.py golden/fragmentation/CRC/sequence/identity/replay matrices; test_target_protocol_v2.py version/monotonic/assembly matrices; test_target_transports.py bounded adapter/failure/cleanup matrices; new runner lifecycle and physical publication selectors | Public decoder, validator, transport, flash, cancellation, and publication paths have concrete fake triggers. Real pyOCD API, device memory, transport driver, and platform-specific adapter branches are the prohibited native subset; the remaining arcs stay visible unresolved under the no-hardware/no-pyOCD boundary. |
| probe/attach_diagnostics.py (36), probe/authorization.py (12), probe/backend.py (20), probe/client.py (14), probe/flash.py (9), probe/handoff.py (45), probe/lease.py (64), probe/model.py (1), probe/protocol.py (2), probe/pyocd_backend.py (32), probe/selector.py (1), probe/service.py (75), probe/supervisor.py (4), probe/worker.py (24), probe/worker_windows.py (12), process.py (4): 355 | test_probe_service.py, test_probe_lease.py, test_probe_backend.py, test_probe_client.py, test_probe_flash.py, test_probe_worker.py, test_probe_supervisor.py, test_debug_handoff.py, and related probe protocol/selector tests; new atomic lease-write and handoff-metadata selectors | Existing fake service/lease/worker matrices reach ownership, cancellation, timeout, cleanup, handoff, and authorization seams. The new lease test reaches _write_record_path through heartbeat; the new service test reaches debug_handoff_metadata.invoke through an attached provider. Windows child-process, real pyOCD, USB/discovery, and OS identity branches are the native/platform subset eligible for external deferral; other residual arcs stay visible unresolved in this wave. |
| testing/_ctest_junit_bridge.py (3), testing/artifacts.py (2), testing/host.py (17), testing/model.py (8), testing/native_output.py (1), testing/publication.py (98), testing/replay.py (26): 155 | test_testing_publication.py Host publication/reload and stored-corruption matrices; test_target_replay_publication.py public replay publication, provenance, conflict, parent, and reload matrices; test_target_replay_workflows.py; new public parent-guard and physical publication/reload selectors | _target_parent, _load_target_replay, physical publication, and public repository reload have explicit caller triggers. CTest/JUnit/native-output and external process conversion are reporting/process subsets; the remaining arcs stay visible unresolved rather than being claimed from replay or padded with direct private calls. |

The five row totals sum to the accepted target upper bound of 937. This table
is a source-based accounting, not a blanket deferral: all 937 missing arcs
remain visible and unresolved until the released run supplies source-matched
coverage. Only prohibited real pyOCD, device, and OS-specific paths may later
be marked deferred external evidence. No coverage or pass claim is made by
this implementation return.

## Static verification

Only static checks were performed in this implementation/revision wave:

    python -c "import ast,pathlib; ..."  # AST parse of all seven changed test files
    git diff --check
    PowerShell AST parse of the prepared launcher

All seven changed test files and the prepared launcher parsed successfully and
the diff was clean. Pytest, pytest collection, product imports, coverage,
build, install, hardware, and runtime execution were intentionally not
performed. The tests remain NOT_RUN until the primary releases the serial
execution batch.

Prepared serial launcher, not executed:

- Path: D:\codex-tmp\v10b-0918\r10\e\core95\target\run1\launch.ps1.
- Candidate guard is set to the final report commit head; runtime source guard: a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d.
- Invocation properties: `-x`, `--cov=stm32_toolkit`, 16 function selectors expanding to 31 bounded pytest items, and a 300-second wall budget.
- Evidence root: D:\codex-tmp\v10b-0918\r10\e\core95\target\run1.
- Temporary/cache/basetemp root: D:\codex-tmp\v10b-0918\r10\t\c95t\run1.
- All launcher-owned result paths were absent when prepared; the launcher file itself is the only file under the evidence root.

Reserved runtime evidence paths, not populated by this implementation turn:

- D:\codex-tmp\v10b-0918\r10\e\core95\target\run1
- D:\codex-tmp\v10b-0918\r10\t\c95t\run1

## Remaining barriers

The code head and report are ready for primary independent complete-diff review.
The primary must release the bounded serial batch against source identity
a270d7332c3ad2d09cd0b9adfa96ca80042bcf9d, retain command/exit/JUnit/stdout/
stderr/raw coverage evidence under the approved roots, classify any failure
before changing tests, and own cleanup after evidence retention. This return
contains no execution result and no physical acceptance claim.
