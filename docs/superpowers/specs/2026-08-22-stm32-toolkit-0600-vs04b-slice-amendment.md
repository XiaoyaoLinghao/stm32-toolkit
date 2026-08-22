# VS04-B Slice Boundary and Physical Monitor Reference Amendment

## Decision and ledger

The accepted product base is `6d8a593990d176e5ef2b9e051059ab6e5b3fd76b`. VS04-A is
accepted at that commit. GPT-5.6-sol owns this amendment and review; the same bounded VS04-B1
implementation is owned by one GPT-5.6-luna/max agent. No hardware or remote Git operation is
authorized.

The original VS04-B description combines a persistent Monitor schema migration with a later
Analysis/Diagnostics source-policy migration. That is too broad for one controllable implementation
handoff. VS04-B is therefore delivered as two sequential vertical product behaviors:

- **VS04-B1 — physical Monitor reference:** an already committed live History window plus its
  accepted physical TestRun becomes one durable, reloadable physical `MonitorRunRef` v2.
- **VS04-B2 — physical diagnostic verification:** two B1 references and two physical TestRuns flow
  through Analysis, marker, bundle, Diagnostics, and `FixVerification`.

Both are caller-consumable vertical slices. They are not file-oriented subtasks and must not be
recursively split. B2 starts only after B1 is independently accepted.

## B1 user-visible behavior

The public workflow `publish_physical_monitor_run` accepts:

- current `WorkspacePaths` and `EvidenceStore`;
- `scenario_role` (`failed-before` or `fixed-after`);
- one accepted physical `test_run_id`;
- one live Monitor `run_id` and `group_id`;
- exact `start_sequence` and `end_sequence_exclusive`;
- exact `start_captured_unix_ns` and `end_captured_unix_ns_exclusive`;
- the transient raw `probe_id` used by the live observation.

`operation_id` is the canonical lower-case UUID text of `run_id`; the caller does not provide a
second operation identity. The workflow queries only the already committed History window. It does
not connect to a probe, start or stop sampling, acquire a lease, flash, halt, reset, or mutate
History.

Success publishes the physical transcript, a `monitor-run` root, a `MonitorRunRef` v2 artifact and
envelope, and a `monitor-run-ref` root. It returns the v2 reference. A fresh public
`load_monitor_run_reference` call reloads and validates the same reference from Evidence alone.

The Monitor CLI exposes:

```text
physical publish --project ... --data-root ... --session-id ...
  --scenario-role ... --test-run-id ... --run-id ... --group-id ...
  --start-sequence ... --end-sequence-exclusive ...
  --start-captured-unix-ns ... --end-captured-unix-ns-exclusive ...
  --probe-id ... --json
```

The CLI calls the workflow once, returns the workflow result without inventing identity, and emits
only sanitized failures. Monitor has no MCP surface in this slice.

## MonitorRunRef schema migration

Existing replay references remain exact `stm32-monitor-run-ref/1` values. Their fields and
canonical bytes do not change, and they continue to use `fixture_sha256`.

The generic schema is `stm32-monitor-run-ref/2`. It has the same closed reference fields as v1
except that `fixture_sha256` is absent and `source_record_sha256` is present in the same logical
position. A v2 physical reference requires:

- `execution_source="physical"` and `physical_transport_evidence=true`;
- equal origin/import workspace IDs;
- equal origin/projected session IDs and origin/projected run IDs;
- non-replay hardware labels;
- `probe_id` equal to `sha256(UTF-8 raw probe selector)`;
- the exact Project/TestRun/History firmware and target identity;
- a digest over the complete canonical v2 reference excluding `run_ref_sha256`.

One discriminated `MonitorRunRef` model may represent v1 and v2, but serialization and validation
are schema-specific. It must not emit null compatibility fields. `from_value(to_dict(v1))` retains
the exact old v1 bytes; v2 never accepts `fixture_sha256`.

## Physical transcript authority

The physical source record schema is `stm32-monitor-physical-transcript/1`. Its canonical object
contains the scenario role, linked physical `test_run_id`, physical source/flag, and the exact
complete projected `SampleBatch` window.

The publisher reads the requested History window through public `HistoryStore.query_history`,
following bounded cursors. It reconstructs complete batches and requires:

- one run, group, group revision, selector vocabulary, and ObservationBinding;
- exact contiguous sequences and exact requested captured-time boundary;
- no partial batch, repeated cursor, duplicate sequence, gaps, excess values, or changing binding;
- current workspace, logical project, session, firmware, target, and Project v3 debug target;
- the transient raw selector to equal the History binding's raw selector;
- `sha256(UTF-8 raw selector)` to equal the physical TestRun root's `probe_id`;
- History `flash_session_id` and `lease_id` to equal the physical TestRun provenance;
- failed-before to bind a terminal failed TestRun and fixed-after to bind a terminal passed TestRun.

The projected transcript replaces only `ObservationBinding.probe_id` with the hash. Raw selector
bytes are forbidden from the transcript, v2 reference, Evidence metadata/root, and public result.
The existing live History database is not rewritten and remains the live observation authority.

The physical transcript has its own 64 MiB canonical-byte limit, equal to the EvidenceStore
single-object read limit; the existing 1 MiB replay-document limit remains unchanged. A requested
physical window whose complete canonical transcript exceeds 64 MiB is `MONITOR_PHYSICAL_INVALID`
before any artifact, envelope, or root publication. Public History pages may split a batch at a
cursor: the publisher reconstructs contiguous authenticated slices into the original complete
batch and rejects only missing, overlapping, reordered, or contradictory slices.

`source_record_sha256` equals the SHA-256 of the canonical transcript bytes and therefore also the
transcript artifact digest. The transcript Evidence operation is `monitor-physical-window` and its
closed metadata records operation/run ID, scenario role, linked TestRun ID, workspace/session,
source/flag, and source-record digest. The reference Evidence retains operation
`monitor-run-ref`. Both have their existing root types.

## Idempotency, lifecycle, and failures

Publication is append-only and idempotent for the same complete intent and bytes. An existing root
with different transcript/reference bytes is `OPERATION_CONFLICT`. No mutation of the source
History or physical TestRun is permitted.

When a complete reference already exists for the operation ID, caller-visible intent fields that
are available in that reference, including role, group, sequence, and captured-time bounds, are
compared before querying the requested History window. A mismatch is `OPERATION_CONFLICT`, not an
identity error. Matching intent continues through authoritative source validation. A retained
transcript-only prefix is validated against the newly reconstructed complete intent before resume.

The publisher preflights both complete payloads and both root identities before the first durable
root write. Validation, identity, integrity, and pre-existing conflict failures therefore create
neither root. Durable publication then has one ordered commit sequence: transcript artifact,
transcript envelope, `monitor-run` root, reference artifact, reference envelope, and
`monitor-run-ref` root. Because Evidence is append-only rather than transactional across roots, a
provider failure after that sequence starts may retain only the already validated prefix. That
prefix is not rolled back or replaced. The same complete intent must recognize the matching prefix
and resume idempotently to the same final reference; malformed or contradictory retained data is an
integrity failure or conflict. A provider failure is `ENVIRONMENT_FAILURE` and never converts a
partial durable prefix into a successful result.

Invalid arguments or noncanonical identifiers are `MONITOR_PHYSICAL_INVALID`. Cross-source,
identity, firmware, target, window, role/state, or provenance mismatch is
`INCOMPATIBLE_IDENTITY`. Corrupt History or Evidence is `EVIDENCE_INTEGRITY_FAILURE`; provider or
storage inability is `ENVIRONMENT_FAILURE`. A negative path before the durable commit sequence
creates neither `monitor-run` nor `monitor-run-ref` root. A provider failure during commit may
retain only a valid append-only prefix as defined above. Already accepted replay Evidence remains
unchanged.

## B1 acceptance scenarios

1. A real `HistoryStore` contains two or more contiguous live physical batches. An accepted
   physical failed TestRun and exact request publish one v2 failed-before reference. Fresh loader
   returns byte-equivalent data, roots are authoritative, and the raw probe selector is absent from
   all newly published/public bytes.
2. Repeating the same request is idempotent. Changing the requested window or linked TestRun under
   the same run ID conflicts without replacing either root.
3. A replay TestRun, raw-probe/hash mismatch, firmware/target/session/lease drift, incomplete batch,
   sequence gap, role/state contradiction, or corrupted stored batch fails with no new roots.
4. A provider fault at each durable publication boundary returns `ENVIRONMENT_FAILURE`; any retained
   data is an exact valid prefix, and retrying the same intent completes both roots without replacing
   prior data.
5. Existing v1 replay ingestion, exact reference bytes, Analysis inputs, and replay tests remain
   unchanged.

## B2 boundary

B2 will generalize Analysis, marker, bundle, Diagnostics, and FixVerification to the common
execution-provenance policy. B1 must not edit those workflows or claim physical verification.
Physical transcript decoding in B2 will consume the immutable Evidence source record; it will not
need the transient raw probe selector and will not reinterpret live History.
