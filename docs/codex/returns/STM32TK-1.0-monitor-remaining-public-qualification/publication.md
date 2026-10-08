# Derived Analysis publication/export qualification

Status: **IMPLEMENTED; TEST EXECUTION NOT_RUN**.

The slice starts at accepted base `87699308535bd36431c2e44be8bf131e245d460d` on
`codex/STM32TK-1.0-derived-publication-qualification`. The implementation test
head before this note was `aad5455654296197e696d1f7ef7300c94861f381a`.
The unchanged release evidence remains `2472/2936` Monitor branches; this
test-only slice claims no measured coverage gain and no release acceptance.

The added nodes use the existing replay fixtures, `EvidenceStore`, and its
fault/provider seams. They snapshot after corruption or provider setup and
before the public operation. Preflight refusals preserve the complete evidence
tree. A reload failure after the analysis root has been durably published
asserts that the analysis prefix remains and the marker root is absent; no
rollback of an immutable publication is promised. Export refusals preserve the
upstream tree and create no analysis-bundle root.

| Added node or parameter | Missing arc | Public trigger | Expected error | State assertion |
|---|---|---|---|---|
| `test_derived_preflight_rejects_corrupt_root_without_mutation` | `_preflight_checkpoint` root validation, `944 -> 947` | Reload an existing publication after its derived root bytes are corrupt | `EVIDENCE_INTEGRITY_FAILURE` | Evidence tree is unchanged after the refusal |
| `test_derived_preflight_maps_root_provider_io_without_mutation` | `_preflight_checkpoint` provider I/O, `958 -> 960` | Derived root provider raises `OSError` during public compare retry | `ENVIRONMENT_FAILURE` | Evidence tree is unchanged and provider detail is redacted |
| `test_derived_preflight_rejects_existing_envelope_intent_conflict` | `_preflight_checkpoint` envelope intent, `954 -> 955` | Provider returns valid envelope bytes with a different intent for the expected derived ID | `OPERATION_CONFLICT` | Evidence tree is unchanged |
| `test_derived_publication_reload_rejects_published_root_mismatch_without_rollback` | `_publish_checkpoint` root reload, `991 -> 992` | Root provider mutates the just-published analysis root before reload | `EVIDENCE_INTEGRITY_FAILURE` | Published analysis prefix remains; marker root is absent |
| `test_derived_publication_reload_rejects_provider_envelope_mismatch_without_rollback` | `_publish_checkpoint` envelope reload, `994 -> 995` | Provider returns a different valid envelope after the analysis root publication | `EVIDENCE_INTEGRITY_FAILURE` | Published analysis prefix remains; marker root is absent |
| `test_derived_publication_reload_rejects_provider_artifact_bytes_without_rollback` | `_publish_checkpoint` artifact reload, `996 -> 997` | Provider returns different bytes for the just-published analysis artifact | `EVIDENCE_INTEGRITY_FAILURE` | Published analysis prefix remains; marker root is absent |
| `test_export_rejects_upstream_derived_authority_without_bundle_mutation[root]` | `_validate_published_derived` root authority, `1024 -> 1025` | Stored analysis root metadata contradicts the authenticated publication | `EVIDENCE_INTEGRITY_FAILURE` | Existing evidence remains; no bundle root is created |
| `...[manifest]` | Upstream manifest absence, `1035 -> 1037` | Stored analysis manifest is absent on export reload | `EVIDENCE_INTEGRITY_FAILURE` | Existing evidence remains; no bundle root is created |
| `...[envelope]` | Upstream envelope authority, `1028 -> 1029` | Provider returns a different valid envelope for the authenticated analysis ID | `EVIDENCE_INTEGRITY_FAILURE` | Existing evidence remains; no bundle root is created |
| `...[bytes]` | Upstream artifact bytes, `1047 -> 1048` | Provider returns bytes that differ from the authenticated analysis payload | `EVIDENCE_INTEGRITY_FAILURE` | Existing evidence remains; no bundle root is created |
| `...[provider]` | Upstream artifact provider I/O, `1041 -> 1043` | Analysis artifact provider raises `OSError` during export validation | `ENVIRONMENT_FAILURE` | Existing evidence remains, provider detail is redacted, and no bundle root is created |

Existing root-intent conflict, artifact-identity mismatch, source/target provider
failures, missing-analysis artifact, and partial-marker repair cases were left
untouched and are not duplicated here.

## Static verification

The pinned interpreter parsed
`tools/stm32-monitor/tests/test_analysis_workflows.py` successfully with
`ast.parse`. `git diff --check` passed. No pytest, collection, package import,
build, install, hardware, cleanup, or remote action was performed in this
implementation wave.

