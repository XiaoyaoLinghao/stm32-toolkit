# GCC content provenance in live Monitor

Governing specification: ../specs/2026-10-26-gcc-delivery-contract.md. Accepted base: `b0f5807bb8b8f2149a7499fed3b2b03d3e610c33` (B1 evidence accepted). Primary owns architecture, plan, dispatch, full clean-diff review and acceptance. Local Claude Code CLI owns code/tests, retaining the user's provider/model. The clean B1 checkout is reused sequentially on `codex/gcc-monitor-live`. No original projects, installed runtime, global policy, remote, version or hardware changes.

## B2a contract

Live firmware status and observation/history bindings preserve the same two closed source forms as B1/A. Legacy Git records retain exactly their old fields/canonical bytes and accepted case behavior: FirmwareStatus lowercases Git HEAD, while ObservationBinding validates but preserves its accepted casing. Do not tighten legacy behavior by blindly using a lowercase-only helper. Snapshot form uses null Git fields plus `sourceBaseline="input-snapshot-v1"` and bounded `gitEvidence={status:"unavailable",code:"BUILD_GIT_INVALID",rule:"head"|"status"}` and a real input digest. Keep the evidence immutable. Decoders reject partial, present-null, unknown or mixed forms; adding null defaults to legacy wire output is not permitted.

Runtime firmware projection must not stringify null or coerce it to a clean flag. Projection from Toolkit DebugFirmwareBinding and comparisons used for probe-session reuse/rebinding carry the complete pair as well as existing build/ELF/input/target/session/probe/lease bindings. Changed content or pair invalidates dependent state before access. Missing Git alone is ordinary supported state. Preserve observer ownership, finite sampling and cleanup; no reset/resume/halt fallback or new authority.

The TypeScript FirmwareStatus, DebugFirmwareBinding and ObservationBinding contracts become discriminated unions with strict guards for the same two closed forms. Status, batch and history decoding must all accept valid snapshot records and reject mixed/partial/extra keys. Reducer binding/firmware equality and sourceContextKey include the pair so cached state cannot survive a relevant change. IdentityBar shows the input snapshot and an honest Git-unavailable label, while preserving legacy display. Use existing localization without unrelated redesign.

## Allowed implementation

Monitor Python: models.py, runtime.py, probe_session.py. UI: api/contract.ts, state/model.ts, state/reducer.ts, components/IdentityBar.tsx, presentation/zh.ts. Focused new tests: tests/test_content_monitor_live.py and ui/tests/content-provenance.test.tsx. Existing test_models.py, test_runtime.py, test_probe_session.py and UI contract/reducer/components test files may receive only necessary relevant regression additions. No replay.py/analysis/source-catalog/Toolkit diagnostic changes in this slice: those are B2b after this acceptance. Report required scope additions before editing.

## Verification

Read the maintained standard procedure/current checkpoint. File-only authoring and exact-command native PowerShell verification remain separate. After source freeze, Claude runs focused and related Monitor Python tests, UI typecheck/unit tests, then the normal Vite build and dist verification through explicit coordinator commands. Primary reviews the full exact-head diff and independently checks representative complete snapshot status -> fake connection -> observation/history -> disconnect and UI identity/invalidation tests. Test partial/mixed pairs, input/ELF/session/probe changes, immutable metadata and unchanged legacy canonical output/casing. Fake providers are never physical PASS.

Node v24.19.0 is verified at the bundled runtime path. Existing offline developer node_modules from the prior build-snapshot-review checkout may be copied into this isolated checkout: package-lock is identical except root version 1.3.1/1.3.2, and installed version/resolved/integrity entries match. No install/download or modification of that prior checkout. UI generated assets change only through the normal reviewed build command, after source tests; review and commit derived output separately, then freeze the final head and verify dist. Do not manually edit hashed assets.

## Next boundary

B2b extends Monitor replay/publication/references, analysis/source consumers, Toolkit diagnostic/continuation and MCP run references with complete snapshot propagation and legacy-byte compatibility. Final integration joins migration/creation/regeneration and verifies both GCC/managed-fake-flash journeys. This slice alone does not claim replay, physical or release completion.
