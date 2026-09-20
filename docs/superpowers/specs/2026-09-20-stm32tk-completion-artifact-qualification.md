# Completion artifact qualification

Accepted integration base: `313cd9c0ee60d57a1d6be578664512d1a704a087`.
Runtime source: `465249dba5560f7c08b1172794fec8fedd9b8d96`, unchanged.
This is a bounded continuation of the approved core public-contract qualification
and the user's active local release goal. Primary owns this design and acceptance;
one Luna/max owner implements tests. No remote action is authorized.

## Public scenarios

1. Complete a valid software/replay diagnostic verification with its real analysis
   and marker graph. Return `PASSED/VERIFICATION_PASSED`, revision 11, `RESOLVED`.
2. Complete with a marker root whose persisted structure or envelope contract is
   corrupt. Return `INCONCLUSIVE/MANDATORY_EVIDENCE_CORRUPT`, revision 11,
   `INVESTIGATING`, and retain the previous revision-10 checkpoint.
3. Complete with a content-addressed marker artifact whose kind/media contract or
   canonical JSON contract is invalid. Return the same corrupt outcome after
   the real store has verified the referenced bytes.

These are software tests. VS10-A/B physical evidence remains retained separately.
No product, schema, dependency, coverage scope, package, deployment or hardware
change is part of this slice. Overall native branch coverage >=90% remains
mandatory; core >=95% remains preferred. union18 is the unchanged native baseline.

## Shared graph and lifecycle

Reuse `_prepare_real_diagnostic_before_source` and the public replay/Monitor/
Diagnostic sequence already in `test_vs08b_scenarios.py`. Use only `cubemx` origin.
The new small fixture stops after `diagnostic_attach_marker`, at revision 10,
`VERIFYING`, with one active plan. Do not run acceptance recovery/build stages or
copy their fake readers/build facts. Public model/store constructors and the
existing deterministic session-id seam remain the only construction mechanisms.

Prepare this valid prefix once within one matrix test. Each case copies its data
tree into a distinct child of that test's temporary root, while retaining the
same project path, logical project ID and runtime session ID. `WorkspacePaths`
derives workspace identity from project ID and project path, not data root
(`paths.py:59-61`). Confirm equal workspace identity and a real public diagnostic
read of revision 10 for every copy before mutation. Never rewrite production
identity fields to make a clone pass. Keep the original baseline immutable.

The original marker envelope/object must remain intact: DiagnosticStore replay
revalidates those references before completion (`diagnostics/store.py:817-835`).
Deleting that object would test the earlier `DIAGNOSTIC_EVIDENCE_MISSING` guard,
not completion classification, and is outside this matrix.

## Frozen mutations and oracles

Publish replacement objects/envelopes through `EvidenceStore.ingest_file` and
`put_envelope`, using the original valid `EvidenceIdentity`. Root mutation is
explicit corruption of fixture-local persisted bytes: construct a public
`RootRecord`, serialize with public `canonical_json_bytes`, and replace only the
known marker root file. Its key is the SHA-256 of canonical root_type/root_id.
The immutable `put_root` API must not be bypassed by a mocked success response.

| Cases | Intended first completion check |
| --- | --- |
| Root metadata differs; envelope operation differs; zero artifacts | Structural guard `diagnostic_workflows.py:1472-1480` |
| Root bytes `{}`; valid root JSON with noncanonical serialization | Real `get_root` failure classified at `1500-1514` |
| One real artifact with wrong kind; wrong media type | Artifact guard `1482-1483` |
| Content-addressed array JSON; noncanonical object JSON | Decode/canonical guard `1492-1494` |

Together with the positive control this is ten variants in one coherent matrix.
Do not add redundant two-artifact, invalid-JSON, old-object corruption, provider
OS fault, or duplicate post-read hash cases. They are covered elsewhere, preempted,
or lack an appropriate real provider boundary. Do not call private decisions or
replace public readers. No generic fault-mutation framework is needed.

Every completion has exact outer wire: protocol `stm32-toolkit/1`, ok true,
operation `diagnostic.verification.complete`, code `OK`, empty message/details.
Assert the full FixVerification identity and outcome fields, session revision,
state, cleared active plan, appended verification ID, and the new completion
event's sequence/revision-before 10. Assert one new revision-11 diagnostic root,
unchanged prior checkpoint, and unchanged mutation bytes after completion.
The completion result, real DiagnosticStore replay and persisted checkpoint must
agree. A matching terminal status alone does not establish target-guard coverage.

Static union18 candidates are seven source pairs: 1472->1480, 1482->1483,
1493->1494, 1501->1504, 1507->1508, 1507->1513, 1509->1512. They are estimates;
only actual native measurement establishes a gain. This slice alone cannot close
Toolkit's remaining 459-branch gap. Its value is a reusable, valid consumer graph
and the caller-visible persistence contract, not a promised percentage.
