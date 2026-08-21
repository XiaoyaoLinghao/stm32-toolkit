# STM32 Toolkit 0.6 VS-03 Task8 Adapter Contract

## Status and authority

This amendment resolves the adapter ambiguities left by the approved VS-03 design. It supersedes
only Task8 adapter details; Target replay, Monitor replay/analysis/bundle, diagnostic workflow, data
model, identity, Evidence, and completion contracts remain authoritative.

Accepted product base is `2fb06f066ba3f8012617d065657d4eac5049e5cf`. GPT-5.6-sol owns this
contract and final review. GPT-5.6-luna/max owns implementation. No remote operation is authorized.

## Product boundary

Task8 has two independent vertical caller surfaces:

- **8A Toolkit adapters:** a shell or MCP caller can publish a Target replay and drive source-change,
  verification-plan, verification start/complete/show, and Marker attachment through the already
  accepted Toolkit workflows.
- **8B Monitor adapters:** a shell caller can import Monitor replay, compare two runs, carry the
  resulting publication through a closed wire document, and export the deterministic bundle.

Adapters parse bounded input, construct the established context, call exactly one application
workflow once, and project its result. They own no orchestration, fallback, Evidence mutation,
identity inference, status decision, or retry policy.

## AnalysisPublication wire authority

Freeze this closed schema in `stm32_monitor.analysis_workflows`:

```json
{
  "schema": "stm32-monitor-analysis-publication/1",
  "analysis_result": {},
  "analysis_evidence_ref": {},
  "diagnostic_marker": {},
  "diagnostic_marker_ref": {}
}
```

`AnalysisPublication.to_dict()` emits exactly those fields. `AnalysisPublication.from_value()`
requires an exact dict, rebuilds each object using its existing closed parser, and reruns the
publication cross-object invariants. The CLI bundle command consumes this schema; it must not call
compare again or invent a second publication format.

## Monitor CLI contract

Keep existing `serve` and `open` behavior byte-compatible. Add:

```text
replay ingest
  --project --data-root --session-id --operation-id --document-file --json

analysis compare
  --project --data-root --session-id --request-file
  --diagnostic-session-id --hypothesis-id --polarity --rationale
  [--source-change-file] --json

analysis bundle
  --project --data-root --session-id --request-file --publication-file
  --failed-before-test-run-id --fixed-after-test-run-id
  [--source-change-file] --json
```

The adapter loads Project v3, constructs `WorkspacePaths.from_roots(data, project,
logical_project_id, session_id)`, and binds `EvidenceStore` to
`workspace.workspace_root / "evidence"`. It never treats `data-root` itself as Evidence authority.

All JSON inputs are regular, non-link/non-reparse files, bounded by the owning model limit, UTF-8,
closed, and canonical where the producer contract requires canonical bytes. File/parse errors expose
only a fixed public code/message and never a path or native exception.

Monitor analysis commands emit the existing `ProtocolResult.to_dict()` wire:

- operations: `monitor.replay.ingest`, `monitor.analysis.compare`, `monitor.analysis.bundle`;
- success data respectively `{monitor_run_ref}`, `{analysis_publication}`, and
  `{analysis_bundle, analysis_bundle_ref}` where `analysis_bundle` is the decoded canonical object;
- `AnalysisWorkflowError` preserves its closed code and bounded message;
- grammar/model/file errors use `ANALYSIS_WORKFLOW_INVALID`;
- filesystem/provider inability uses `ENVIRONMENT_FAILURE`.

The Monitor protocol code validator is extended only for the four established analysis-boundary
codes: `ANALYSIS_WORKFLOW_INVALID`, `INCOMPATIBLE_IDENTITY`, `EVIDENCE_INTEGRITY_FAILURE`, and
`ENVIRONMENT_FAILURE`. Existing `OK|MONITOR_*` behavior remains unchanged.

## Toolkit CLI contract

Keep all accepted commands byte-compatible. Add:

```text
test replay --project-root --data-root --session-id --operation-id
            --descriptor-file --stream-file --json

diagnose source-change declare SESSION --project-root --data-root --tool-session-id
         --operation-id --expected-revision --declaration-file [--actor] --json
diagnose verification-plan add SESSION ... --plan-file ...
diagnose verification start SESSION ... --verification-plan-id ...
diagnose marker attach SESSION ... --marker-file ...
diagnose verification complete SESSION ... --executed-operation-id ID...
         [--cancelled] ...
diagnose verification show SESSION --project-root --data-root --tool-session-id --json
```

Names may follow the existing parser's root-option conventions, but each command must unambiguously
supply project, data, and Toolkit session roots. Nested object files use the existing bounded safe
JSON loader rules and are passed to the corresponding public workflow. The CLI prints the workflow's
unchanged `OperationResult` and calls one workflow once.

## Toolkit MCP contract

Add tools:

```text
stm32_test_target_replay
stm32_diagnostic_source_change_declare
stm32_diagnostic_verification_plan_add
stm32_diagnostic_verification_start
stm32_diagnostic_marker_attach
stm32_diagnostic_verification_complete
stm32_diagnostic_verification_show
```

Each tool runs `_client_roots_failure()` exactly once before workflow access and uses the runtime's
project/data/session authority. Diagnostic object inputs are nested closed JSON objects; schemas are
closed through `_close_tool_input_schemas()` and admit no extra fields.

Target replay MCP input is exactly `{operationId, descriptorPath, streamPath}`. Both paths are NFC
portable project-relative paths using `/`. Reject empty, absolute, drive/UNC, `.`/`..`, backslash,
NUL/control, overlong, nonexistent, non-regular, symlink, and Windows reparse components. Resolve
under the runtime project root without accepting a caller-supplied root. The workflow still owns
descriptor/stream content validation.

MCP returns each workflow result unchanged and never leaks server paths or raw exceptions.

## Verification and non-goals

Slice tests prove parser/tool schema, context/Evidence binding, one-call projection, path containment,
closed nested inputs, stable error mapping, and compatibility of existing commands. Task8 does not
run Scenario B, a release matrix, packaging, hardware, Python 3.10, or remote operations. Those stay
with Task9/release owners.
