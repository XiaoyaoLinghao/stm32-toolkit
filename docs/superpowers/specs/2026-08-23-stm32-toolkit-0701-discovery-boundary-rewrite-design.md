# STM32 Toolkit VS07-A Discovery Boundary Rewrite Design

**Status:** approved under the user's standing authorization to select the optimal option without another approval stop

**Owner and final reviewer:** GPT-5.6-sol primary agent

**Implementation owner:** one replacement GPT-5.6-luna/max implementer,
explicitly authorized by the user on 2026-08-23 for remaining Tasks 1R–2R.
The prior implementer no longer owns or edits this slice.

**Product accepted base:** `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`

**Rewrite input head:** `1679dcca5839324b01187075955cfa2dd6efe595`

## 1. Reason for the rewrite

The first two independent review rounds found the same discovery-boundary defects: an explicit invalid profile could be ignored, CubeMX could still be executed by a fallback version probe, PATH still preceded registered/standard candidates, ambiguous candidates were not rejected, bounded process timeout cleanup was incomplete, nonzero probes could be accepted, and the new tests did not exercise those paths. Per the project stop-loss rule, these are no longer treated as isolated patches. The discovery interface is replaced as one coherent unit.

The creation request, plan schema, CLI command name, MCP tool name, Python range, and VS07-A read-only scope remain unchanged.

## 2. Rejected alternatives

1. More local conditionals in the current discovery functions are rejected because two rounds did not converge and the subprocess/static evidence responsibilities remain mixed.
2. Requiring an explicit profile for every caller is rejected because it would remove the approved current-host discovery scenario.
3. The selected design uses one candidate resolver and one injected bounded process runner, with static evidence and executable probes separated by type.

## 3. Frozen discovery pipeline

Discovery runs in this exact order for each component:

1. one trusted explicit profile candidate;
2. CubeCLT metadata or the one known CubeCLT 1.22.0 root;
3. bounded Windows registered/standard candidates;
4. bounded PATH candidates.

Each tier collects safe canonical regular files before selection. Zero candidates advances to the next tier. One candidate is selected. More than one distinct candidate at the same tier returns `<COMPONENT>_AMBIGUOUS`; discovery never selects one arbitrarily. A redirect, reparse point, duplicate alias to a different file, invalid profile field, invalid metadata path, unsupported version, failed probe, or unavailable file returns a closed issue or `SupportProfileError` without exposing a host path in public failure text.

The support profile is fail-closed. When `profile_path` is supplied, `data_root` must exist and every existing component from `data_root` through the profile must be a non-reparse directory/file. The profile must be a bounded UTF-8 JSON object with the supported field types. Missing, oversize, invalid UTF-8, invalid JSON, or invalid schema raises `SupportProfileError`; it never falls back to ambient discovery.

## 4. Static evidence versus executable probes

CubeMX and VS Code are static-only facts. Their executable bytes may be hashed and Windows PE version resources may be read. They are never passed to `Popen`, including when a version resource is missing. A trusted explicit profile may supply their version; otherwise missing version evidence produces a closed unsupported/probe issue.

Only these commands may execute during discovery:

- `STM32CubeCLT_metadata.bat -j`;
- `arm-none-eabi-gcc.exe --version`;
- `cmake.exe --version`;
- `ninja.exe --version`.

They all use one injected `_run_bounded(argv, timeout_seconds, capture_limit) -> ProcessObservation` seam. The production runner uses `shell=False`, no stdin, a fixed argv, bounded stdout/stderr, and on timeout terminates/kills and waits before returning. Nonzero, timeout, oversize, invalid UTF-8, or malformed output is not version evidence. Tests inject the runner itself and assert argv, timeout, exit handling, capture limit, and cleanup outcome; they do not monkeypatch the parser under test.

Metadata paths must remain inside the selected CubeCLT root, traverse no redirect/reparse component, and end at the expected executable leaf. GCC, CMake, and Ninja versions come from native probe output and are normalized to exactly `14.3.1`, `4.3.1`, and `1.13.2`. Different or unknown versions produce `GCC_UNSUPPORTED`, `CMAKE_UNSUPPORTED`, or `NINJA_UNSUPPORTED`. No directory layout may invent a version.

CubeMX accepts only a version beginning with `6.18.`; the current `6.18.1-RC2` PE evidence is therefore supported for VS07-A. No other major/minor is added.

## 5. Creation and runtime boundaries

Portable `.ioc` and destination paths are checked component by component from the canonical workspace root. Existing parent components and final objects may not be symlinks, junctions, reparse points, or the wrong file type. `.ioc` input must have the `.ioc` suffix, be readable UTF-8, and remain within the size limit. Destination inventory canonical JSON distinguishes `absent`, `empty`, `populated`, and `unsafe` states, so each state changes the digest without writing the workspace.

`CreationPlanWorkflowRequest` retains the exact fields in the approved VS07-A plan. A frozen `ToolSupportProfile` is supplied to `plan_creation_workflow` as a keyword-only dependency, not added as caller-controlled request data. CLI may discover once per command, including a trusted profile. `ServerRuntime.create` discovers once; MCP doctor and create-plan reuse the same immutable object for the lifetime of the server. MCP input exposes no root, executable, environment, command, or support-profile override.

## 6. Verification contract

Slice tests must prove, rather than merely mention:

- explicit > metadata > registered/standard > PATH and same-tier ambiguity rejection;
- real metadata JSON parsing through an injected runner, including timeout, nonzero, oversize, malformed JSON, redirect, and non-file cases;
- native version parsing and unsupported/failure issues without hard-coded evidence;
- a spy runner receives no CubeMX or VS Code argv;
- fail-closed profile containment and content validation;
- `.ioc` suffix/size/UTF-8/readability, source/destination parent redirects, absent/empty/populated inventory, blocker order, digest changes, and zero mutation;
- all three source kinds, invalid/duplicate CLI inputs, closed workflow errors, MCP client-root enforcement, frozen runtime facts, and normalized CLI/MCP parity;
- doctor legacy keys plus the same creation-support facts used by the runtime.

The exact existing VS07-A slice command remains the only aggregate check. No coverage gate, platform matrix, packaging, hardware, CubeMX generation, VS07-B, or VS07-C work is added.

## 7. Candidate-resolution interface reset

The replacement review proved that returning `ToolFact | None` from each
discovery helper is structurally insufficient: `None` currently means both
"this tier has no candidate" and "this tier supplied invalid evidence". The
subsequent `explicit or metadata or PATH` expression therefore turns a
fail-closed contract into ambient fallback. The per-component functions also
cannot share correct canonical deduplication or same-tier ambiguity handling.

The implementation must replace that control flow with these immutable
internal concepts (names may use leading underscores, but the fields and state
transitions are frozen):

```python
@dataclass(frozen=True)
class DiscoveryCandidate:
    path: Path
    source: str
    version_hint: str | None = None

@dataclass(frozen=True)
class CandidateTier:
    source: str
    candidates: tuple[DiscoveryCandidate, ...]
    invalid: bool = False

@dataclass(frozen=True)
class CandidateResolution:
    fact: ToolFact | None
    issue: ToolSupportIssue | None
```

`_resolve_component(component, tiers, evidence_builder) -> CandidateResolution`
is the only selector. For each tier it performs the following transition:

1. `invalid=True` returns `<COMPONENT>_INVALID` immediately.
2. Canonicalize every supplied path as a safe existing regular file. Any
   supplied unsafe, redirected, missing, or non-file path returns
   `<COMPONENT>_INVALID`; it is not equivalent to an empty tier.
3. Deduplicate by the platform-normalized canonical absolute path. Registry,
   standard, duplicate PATH entries, spelling aliases, and case aliases to the
   same file count once.
4. Zero canonical candidates advances to the next tier; two or more distinct
   candidates return `<COMPONENT>_AMBIGUOUS`; exactly one candidate is passed
   to the component's evidence builder.
5. Evidence failure returns `<COMPONENT>_PROBE_FAILED`; an observed but wrong
   version returns `<COMPONENT>_UNSUPPORTED`; neither advances to a lower tier.
6. Exhausting every empty tier returns `<COMPONENT>_MISSING`.

An explicit profile is validated before tiers are built. A supplied tool entry
whose path is unsafe, missing or the wrong type raises `SupportProfileError`;
it never becomes an empty tier. A present CubeCLT metadata command whose
execution or JSON/path evidence is invalid returns a closed metadata/tool issue
and suppresses known-layout and PATH fallback. The known CubeCLT layout is used
only when the metadata command is genuinely absent.

PATH discovery must enumerate all bounded candidates rather than call
`shutil.which` once. It splits the current `PATH`, examines each directory once,
uses the component's exact executable basename plus Windows `PATHEXT` rules,
and passes every safe match in one PATH tier to the common resolver. Registry
lookups query HKLM and HKCU independently: a missing key in either hive adds no
candidate and cannot suppress the other hive. Registered and known standard
candidates form one tier and are canonically deduplicated before ambiguity is
decided.

The existing public dataclasses, CLI/MCP schemas and positive-environment JSON
remain unchanged. New closed issue codes affect only negative discovery paths.
Issue messages contain the component and remediation, never the rejected host
path.
