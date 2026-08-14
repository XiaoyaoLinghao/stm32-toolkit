# STM32TK-0602 Evidence-Driven Diagnostic Loop Design

**Status:** Approved module design baseline
**Date:** 2026-08-14
**Module:** `STM32TK-0602-DIAGNOSTIC-LOOP`
**Accepted base:** the accepted report commit of `STM32TK-0601-TEST-EVIDENCE`
**Fixed program base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** Codex and its local derived agents under the permanent project policy
**Review and acceptance owner:** Codex
**Remote actions authorized by this document:** none

## 1. Objective

Turn build, test, Probe, Fault, and Monitor observations into a deterministic, auditable
diagnostic loop. The product preserves competing hypotheses, records why evidence supports or
refutes them, permits only bounded authorized hardware controls, and proves a proposed fix with
new identity-bound evidence.

The AI client may propose reasoning and source edits outside the product. Toolkit owns the
state machine, validation, authorization digest, evidence links, hardware actions, and final
verification decision. It does not embed a model, silently edit source, or auto-flash.

## 2. Scope

### 2.1 Included

- append-only `stm32-diagnostic/1` sessions and hash-chained events;
- hypotheses with supporting, refuting, and unresolved evidence;
- deterministic observation plans and bounded OBSERVE operations;
- Probe protocol v2 halt/resume/step, temporary breakpoints, registers, bounded memory reads,
  Fault capture, and log capture;
- exact CONTROL/MODIFY action digests and single-action authorization;
- explicit source-change declaration and before/after snapshot binding;
- rebuild, reflash, Host/Target retest, Monitor assertion, and fix-verification decision;
- portable diagnostic bundle export plus authorized two-phase verify/import;
- CLI, MCP, and a thin `diagnose-firmware` Skill;
- Windows software, fake-backend, replay, security, performance, isolation, and candidate evidence.

### 2.2 Excluded

- arbitrary target memory/register writes;
- permanent flash breakpoints, Option Bytes, chip erase, or probe lease stealing;
- authorization reuse, background debugging, or unattended retries;
- automatic source patch generation/application inside Toolkit;
- Monitor cross-run UI and annotations, owned by 0603;
- a probabilistic or model-generated PASS decision.
- Linux shards, owners, browser handoff, and ZIP transfer in this module; Linux acceptance is
  deferred to a later separately frozen activity.
- the real failed-before/fixed-after board run during the 0602 candidate; it is deferred to the
  unified 0.4+0.6 real-hardware activity after the 0603 candidate.

## 3. Source layout and boundaries

```text
schemas/diagnostic-session.schema.json
tools/stm32-toolkit/src/stm32_toolkit/
├── diagnostics/
│   ├── {__init__,model,events,store,session}.py
│   ├── {hypotheses,observations,actions,verification,bundle}.py
│   └── policy.py
├── probe/{protocol,service,client,backend,pyocd_backend}.py
├── debug/{control,breakpoints,registers,logs}.py
├── cli.py
└── mcp_server.py
skills/diagnose-firmware/SKILL.md
```

The diagnostic package refers to 0601 evidence by immutable ID and uses the public evidence
store API. It does not open catalog SQLite directly. Probe operations remain in the Probe
Service; diagnostics cannot import a hardware backend implementation.

## 4. Diagnostic session model

### 4.1 Identity and revisions

The schema is `stm32-diagnostic/1`:

```python
@dataclass(frozen=True)
class DiagnosticSession:
    session_id: str
    revision: int
    state: DiagnosticState
    identity: EvidenceIdentity
    event_head: str
    hypotheses: tuple[Hypothesis, ...]
    active_plan_id: str | None
    conclusion: DiagnosticConclusion | None
```

Session IDs are random 128-bit lowercase hex values. Session creation publishes the immutable
`session.created` event with `sequence=0`, `revision_before=0`, and materializes revision zero.
Every later accepted event increments sequence and resulting revision together, so an event with
`sequence=n>0` has `revision_before=n-1` and materializes revision `n`. The identity binds the
workspace, logical project, input snapshot, build, ELF, target, and Toolkit version. An identity
transition is not implicit: rebuild or reflash creates a typed event that carries old and new
identities.

The complete state transition table is:

| Before | Accepted event | After |
|---|---|---|
| none | `session.created` | `OPEN` |
| `OPEN` | `investigation.started` | `INVESTIGATING` |
| `INVESTIGATING` | `change.declared` | `FIX_PROPOSED` |
| `FIX_PROPOSED` | `verification.started` | `VERIFYING` |
| `VERIFYING` | `verification.passed` | `RESOLVED` |
| `VERIFYING` | `verification.failed` | `INVESTIGATING` |
| `OPEN`, `INVESTIGATING`, `FIX_PROPOSED`, or `VERIFYING` | `session.abandoned` | `ABANDONED` |

All other state-changing edges are invalid. `RESOLVED` and `ABANDONED` are terminal and cannot
be reopened, resumed, or abandoned again. `RESOLVED` requires deterministic verification.
`ABANDONED` records a reason and does not mean fixed. A failed verification remains in history.
No state or event is deleted or overwritten.

### 4.2 Event chain

Each event is immutable canonical JSON:

```python
@dataclass(frozen=True)
class DiagnosticEvent:
    schema: Literal["stm32-diagnostic-event/1"]
    session_id: str
    sequence: int
    revision_before: int
    event_type: str
    occurred_at_utc: str
    actor: Literal["user", "tool", "ai-client"]
    previous_digest: str | None
    payload: Mapping[str, object]
    digest: str
```

The digest is SHA-256 of canonical event JSON without `digest`. The creation event at sequence
zero has `revision_before=0` and no previous digest; every later event binds the prior digest and
uses the synchronized sequence/revision rule above. Opening or cold-materializing a session verifies
the complete chain once and records an in-process verified checkpoint bound to session, head,
store generation, and immutable file identities. `append_event()` holds a per-session lock,
requires that checkpoint (or performs the cold verification), rechecks `head.json`, the latest
event, expected revision, and store generation, publishes the new event atomically, then replaces
`head.json` and advances the checkpoint. This makes a warm append O(1) without treating the head
as standalone authority. Authoritative full reads and bundle exports still verify the complete
chain. A stale revision fails `DIAGNOSTIC_REVISION_CONFLICT`. A broken chain fails closed as
`DIAGNOSTIC_CHAIN_CORRUPT`; repair means restore evidence, not truncate history.

Limits: 10,000 events/session, 256 hypotheses, 1,024 evidence links/hypothesis, 1 MiB/event,
64 MiB/session metadata excluding referenced artifacts, and 64 active sessions/workspace.

## 5. Hypotheses and evidence reasoning

A hypothesis has exact fields:

```python
@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    statement: str
    status: Literal["open", "supported", "refuted", "inconclusive"]
    confidence_basis: Literal["unrated", "weak", "moderate", "strong"]
    supporting: tuple[EvidenceAssessment, ...]
    refuting: tuple[EvidenceAssessment, ...]
    unresolved_questions: tuple[str, ...]
```

`confidence_basis` is an ordinal user-facing summary, not a probability. Every assessment binds
an existing verified evidence ID, a fact selector, polarity, and a short rationale. The product
never invents facts from prose. A selector must resolve in the referenced evidence envelope or
the event is rejected. The same evidence may support one hypothesis and refute another, but the
same evidence/selector cannot appear on both sides of one hypothesis.

Only explicit `hypothesis.added`, `hypothesis.assessed`, and `hypothesis.status_changed` events
change the view. A conclusion records the selected root cause, rejected alternatives, remaining
uncertainties, and exact evidence IDs. `RESOLVED` does not require all alternatives refuted, but
does require every unrefuted alternative to be recorded as a residual risk.

## 6. Observation planning

An `ObservationPlan` is an ordered set of typed operations with purpose, expected discriminating
result, safety level, prerequisites, timeout, and output evidence type. Supported observations:

- build/source/FirmwareIdentity and prior evidence reads;
- variables, registers, bounded memory, Fault frame, stack unwind, and samples;
- CTest/Target-test inventory and selected test runs;
- Probe log capture through RTT, UART, semihosting, or SWO if the existing backend supports it;
- Monitor live/history assertions through Monitor's public authenticated API.

Plans are data, not executable scripts. The dispatcher recognizes a closed operation enum and
typed arguments. Independent OBSERVE operations may run concurrently; hardware operations for
one probe/target are serialized through the existing lease. A prerequisite failure produces a
recorded blocked observation, not an omitted step or a fabricated result.

## 7. Probe v2 debug contract

0601's frozen `stm32-toolkit-probe/2` root and packaged schemas are the sole canonical Probe v2
contract. 0602 implements that schema byte-for-byte and may not add, rename, widen, narrow, or
reinterpret any operation, common-envelope field, exact argument object, success result, error,
or limit. The complete 0602 inventory and semantic limits copied from 0601 are:

| Operation | Class | Exact operation arguments | Exact success result |
|---|---|---|---|
| `target.state.read` | `OBSERVE` | `{}` | `{state,reason}` |
| `target.halt` | `CONTROL` | `{}` | `{state:"halted",reason}` |
| `target.resume` | `CONTROL` | `{}` | `{state:"running"}` |
| `target.step` | `CONTROL` | `{}` | `{state:"halted",reason,pc_before,pc_after}` |
| `target.breakpoint.set` | `CONTROL` | `{address,kind:"temporary",size}` | `{breakpoint_id,address,kind:"temporary",size}` |
| `target.breakpoint.clear` | `CONTROL` | `{breakpoint_id}` | `{breakpoint_id,cleared:true}` |
| `target.registers.read` | `OBSERVE` | `{names}` | `{registers:[{name,value,width_bits}]}` |
| `target.memory.read` | `OBSERVE` | `{address,length}` | `{address,length,data_base64,sha256}` |
| `target.fault.capture` | `OBSERVE` | `{max_stack_bytes}` | `{fault_registers,stack_artifact,stack_bytes,truncated}` |
| `target.logs.capture` | `OBSERVE` | `{channel,max_bytes,duration_ms}` | `{channel,artifact,bytes,duration_ms,truncated}` |

Every request and result is closed and uses the 0601 common envelope carrying lease ID and
deadline. `state` is exactly `running`, `halted`, `reset`, or `faulted`; `reason` is exactly
`requested`, `breakpoint`, `watchpoint`, `fault`, `exception`, or `reset`. One `target.step`
performs exactly one instruction step and has a hard 5-second deadline; `pc_before` and `pc_after`
are unsigned integers. Breakpoint size is 1, 2, or 4 bytes and a session may hold at most eight
temporary breakpoints. Register names are 1..64 unique profile-allowlisted names and results
preserve request order. Memory length is 1..4096 bytes inside a profile-declared readable region.
`max_stack_bytes` is 0..4096; `fault_registers` contains exactly `cfsr`, `hfsr`, `dfsr`, `afsr`,
`mmfar`, `bfar`, `shcsr`, and `icsr`, and `stack_artifact` is a verified `ArtifactRef` or null when
zero bytes were requested. Log channel is exactly `rtt`, `uart`, `semihosting`, `swo`, or `probe`;
`max_bytes` is 1..10485760 and `duration_ms` is 1..300000. Addresses, register values, widths,
lengths, byte counts, durations, and program counters are unsigned JSON integers; binary content
is canonical base64 inside the referenced artifact.

The exact common error object is `{code,message,details}` and the closed code set is
`PROBE_PROTOCOL_INVALID`, `PROBE_VERSION_MISMATCH`, `PROBE_OPERATION_UNAVAILABLE`,
`PROBE_LEASE_INVALID`, `PROBE_AUTHORIZATION_REQUIRED`, `PROBE_AUTHORIZATION_INVALID`,
`PROBE_IDENTITY_MISMATCH`, `PROBE_LIMIT_EXCEEDED`, `PROBE_TIMEOUT`, `PROBE_BACKPRESSURE`, and
`PROBE_BACKEND_ERROR`. There is no partial success or ad-hoc error. Unknown-field rejection,
lease/workspace/version checks, and all numeric/string bounds are exactly those frozen by 0601.
Before implementation the service returns `PROBE_OPERATION_UNAVAILABLE`. The root and packaged
Probe v2 schemas remain byte-identical before and after 0602; an implementation needing a schema
change stops for a new architecture decision rather than editing the schema.

Preparing a CONTROL or MODIFY action persistently records a CSPRNG-generated 32-byte one-time nonce
encoded as exactly 64 lowercase hexadecimal characters, the exact action digest, issued-at UTC,
and `expiresAt` UTC no later than five minutes after issuance. Prepare performs exactly one combined
OBSERVE-only identity/state read of the complete target identity/state required by the 0601
contract and binds that single snapshot into the digest together with the nonce, session ID,
expected revision, workspace/project, target/probe, firmware identity, operation, typed arguments,
and expiry. Its counters are exactly `identity_state_read=1`, `control=0`, `modify=0`, `reset=0`,
`halt=0`, `write=0`, and `flash=0`; a second observation or any CONTROL/MODIFY attempt fails
preparation. Prepare is itself OBSERVE-only; it never requests authorization, pre-authorizes, or
performs the requested CONTROL/MODIFY action.

Execution must match every bound field and the current identity/revision, then perform an OBSERVE
recheck immediately before the prepared action. Any identity/state change from the prepare snapshot
rejects and closes the preparation without executing CONTROL/MODIFY. A live process also records a
monotonic deadline and rejects the action if either the UTC or monotonic deadline has expired,
preventing a wall-clock rollback from extending a live authorization. After restart the persisted
UTC expiry remains authoritative and cannot be extended. `authorized=true` without the exact nonce
and digest is invalid. Success, user refusal, state/identity mismatch, backend failure, and timeout
all close the prepared action; replay, retry, or later approval requires a new prepare operation.

Temporary breakpoints are RAM comparator resources or session-scoped software breakpoints only
when the backend proves reversible restoration. They are cleared in `finally`, on disconnect,
and on session close. The service records any cleanup failure and refuses later MODIFY actions
until target recovery. Step/halt timeouts attempt bounded recovery and never kill unrelated
debug servers.

Register and memory reads are range-checked against MCU metadata and server policy before the
backend sees them. Peripheral reads with documented destructive side effects are denied.
There is no generic `write_memory`, `write_register`, raw backend command, or server-side shell.

## 8. Change proposal and modification boundary

Toolkit records but does not create or apply source changes. The AI client/user supplies a
`SourceChangeDeclaration`:

```python
@dataclass(frozen=True)
class SourceChangeDeclaration:
    before_snapshot_sha256: str
    after_snapshot_sha256: str
    changed_paths: tuple[str, ...]
    diff_artifact: ArtifactRef
    claimed_hypothesis_ids: tuple[str, ...]
    validation_plan_id: str
```

Paths are canonical workspace-relative tracked files. Before/after snapshots cover the complete
declared build input inventory, not just the diff. Applying edits is outside this module. When a
declaration is registered, Toolkit verifies the diff artifact, changed path set, snapshot
digests, expected session revision, and absence of unrelated changed inputs. Mismatch returns
`DIAGNOSTIC_CHANGE_MISMATCH` and no flash/test step becomes available.

Automated tests may copy the fixed diagnostic fixture to a temporary workspace and have the test
harness, acting explicitly outside Toolkit, apply the repository-owned fixed patch. The harness
must prove the original fixture and product worktree remain unchanged and must pass only the
resulting snapshots, diff artifact, and declaration to Toolkit.

Build, flash, Target test, and any reset remain separate MODIFY actions. Each requires a fresh
authorization digest binding the output of the previous step. A failure never authorizes an
automatic retry. The session records user denial as an event without changing hardware.

## 9. Fix verification

A `VerificationPlan` freezes before the change is accepted:

```python
@dataclass(frozen=True)
class VerificationPlan:
    plan_id: str
    reproduce_evidence_ids: tuple[str, ...]
    required_host_tests: tuple[str, ...]
    required_target_tests: tuple[str, ...]
    monitor_assertions: tuple[MonitorAssertion, ...]
    regression_gate_ids: tuple[str, ...]
    timeout_seconds: int
```

Verification follows this exact causal chain:

```text
failed-before evidence
 -> declared source snapshot/diff
 -> new build + new FirmwareIdentity
 -> authorized flash with read-back identity
 -> exact Host/Target tests
 -> Monitor assertion against the new run
 -> selected regression gates
 -> deterministic FixVerification
```

`FixVerification` is PASS only if every frozen requirement passes, every artifact verifies, the
new source/build/ELF/target identities form a consistent chain, and no required result is stale,
missing, skipped, blocked, or from the before identity. It returns FAIL for reproduced symptoms,
test failures, assertion failures, or identity mismatch; ERROR for corrupt/incomplete evidence.
Only PASS permits `RESOLVED`. A Monitor assertion is exact and bounded: selector, type, operator,
threshold/range, duration/sample count, quality requirements, and run identity.

## 10. Diagnostic bundle

Explicit export creates a deterministic ZIP64-disabled archive containing at most 65,536 entries
and at most 1 GiB of verified uncompressed content:

```text
bundle.json
session/events/*.json
evidence/manifests/*.json
evidence/objects/<digest>
source/change.diff                 # when declared
inventory.json
```

`bundle.json` binds the session head, evidence graph, redaction policy, creator version, inventory
digest, entry count, uncompressed byte count, and SHA-256 of every other member. Entries use ascending
UTF-8 byte ordering, DOS timestamp `1980-01-01T00:00:00`, regular-file mode `0644`, and DEFLATE
level 9; no platform-dependent extra fields are emitted. Duplicate, Unicode-normalization,
case-fold, path-escape, drive, ADS, link, and special-file names are rejected. Secrets, absolute
paths, auth tokens, probe access URLs, and unrelated environment variables are never exported.

Import is a two-phase CLI/MCP operation. `bundle verify` reads and verifies every byte, limit,
digest, graph edge, session head, and policy without publishing, then returns an expected bundle
digest—the SHA-256 of the complete ZIP bytes—and bounded summary. `bundle import` requires that
exact expected digest plus a freshly
prepared explicit MODIFY authorization bound to destination workspace and current catalog/session
state. It re-verifies before atomically publishing through public evidence/session APIs. Reimport
of the same bundle digest is idempotent; reuse of a logical evidence/session ID with different
content is rejected. Import never edits source, performs hardware actions, or creates or changes
Monitor groups or annotations.

## 11. CLI, MCP, and Skill

CLI commands:

```text
stm32 diagnose start --evidence <id>
stm32 diagnose show <session-id>
stm32 diagnose hypothesis add|assess|set-status ...
stm32 diagnose plan add|run ...
stm32 diagnose control prepare|execute ...
stm32 diagnose change register ...
stm32 diagnose verify <session-id>
stm32 diagnose export <session-id> --output <path>
stm32 diagnose bundle verify <path>
stm32 diagnose bundle import <path> --expected-digest <sha256> --action-digest <sha256> --nonce <hex> --authorized
```

MCP tools are narrower typed counterparts: session create/read, event append, hypothesis update,
observation plan/execute, control prepare/execute, change register, verification run, bundle
export, bundle verify, and authorized bundle import. They return `OperationResult`; artifacts
remain references. Read and bundle-verify calls are OBSERVE.
CONTROL/MODIFY calls surface the exact digest and summary before requiring `authorized=true`.

`diagnose-firmware` guides evidence-first reasoning: reproduce, list competing hypotheses,
choose discriminating observations, request action-specific authorization, preserve failures,
and verify the exact frozen plan. It may never say a fix is proven without PASS evidence from
`diagnostic_verify`.

## 12. Error model

New stable codes include:

- `DIAGNOSTIC_NOT_FOUND`, `DIAGNOSTIC_INVALID_EVENT`, `DIAGNOSTIC_INVALID_TRANSITION`;
- `DIAGNOSTIC_REVISION_CONFLICT`, `DIAGNOSTIC_CHAIN_CORRUPT`, `DIAGNOSTIC_LIMIT_EXCEEDED`;
- `DIAGNOSTIC_EVIDENCE_MISSING`, `DIAGNOSTIC_CHANGE_MISMATCH`;
- `DIAGNOSTIC_VERIFICATION_FAILED`, `DIAGNOSTIC_VERIFICATION_INCOMPLETE`;
- `DIAGNOSTIC_BUNDLE_INVALID`, `DIAGNOSTIC_BUNDLE_DIGEST_MISMATCH`,
  `DIAGNOSTIC_BUNDLE_ID_CONFLICT`;
- `PROBE_TARGET_STATE_MISMATCH`, `PROBE_RANGE_DENIED`, `PROBE_CONTROL_TIMEOUT`;
- `PROBE_BREAKPOINT_LIMIT`, `PROBE_CLEANUP_REQUIRED`, `AUTHORIZATION_DIGEST_MISMATCH`.

All errors include a safe message, retryability, current revision where relevant, and structured
details without secrets or raw backend exception text.

## 13. Test contract

### 13.1 Automated partitions

1. event canonicalization, hash chain, legal/illegal transitions, crash points, concurrency;
2. hypotheses/assessments/selectors/residual risks and immutable historical views;
3. observation-plan closed enum, dependency graph, cancellation, evidence linking;
4. authorization digest mutation tests for every bound field and single-use behavior;
5. Probe v2 version/schema/lease/state/range/backpressure/timeout/cleanup tests;
6. pyOCD fake backend halt/resume/step/breakpoint/register/memory/Fault/log tests;
7. source declaration inventory/diff/snapshot mismatch tests;
8. verification truth table, stale identity, partial/error/skipped/blocked/corrupt cases;
9. deterministic bundle, import atomicity, zip-slip/casefold/bomb/secret redaction;
10. CLI/MCP typed schema, limits, auth dialogue, cross-workspace/session isolation;
11. branch coverage at or above 90% for every changed product Python file;
12. Windows, CPython 3.10/3.12, offline wheel and managed launcher regressions.

Property tests generate event sequences and action digest mutations. Fault injection covers a
crash before/after event publish, head replacement, breakpoint creation, cleanup, flash, test
capture, and bundle import. Tests assert evidence remains recoverable and no unauthorized next
step occurs.

### 13.2 Performance

Before implementing `events.py`, `store.py`, `session.py`, or `bundle.py`, 0602 adds and commits
the exact correctness-first measured workloads, data generators, warm/cold boundary, sample count,
three-batch nearest-rank calculation, and the following design maxima. Characterization occurs
only after the corresponding correct implementation exists; the committed workload and maximum
cannot change to make an implementation pass.

| Operation | Dataset | Design maximum |
|---|---|---:|
| append and reload diagnostic event | warm verified 10,000-event session | p95 250 ms |
| read materialized session | 1,000 events, 64 hypotheses | p95 500 ms |
| authoritatively verify session chain | 10,000 events | 3 s |
| export and reverify bundle | 10 MiB reachable artifacts | 5 s |

If provisional calculated thresholds exceed these maxima, improve the implementation without
changing workload or maxima and repeat characterization. Only within-maximum baselines and
thresholds are added atomically to `performance_0600.json`; they freeze before optional
post-baseline optimization and candidate. The accepted-baseline regression limit is 15%, measured
independently on CPython 3.10 and 3.12 with the common program method. No global GC state is toggled
in a request path; optimizations must be local, thread-safe, and covered by concurrent tests.

### 13.3 Deferred unified real-board diagnostic scenario

The mandatory final-v0.6.0 scenario starts with a firmware fixture that deterministically fails a
Target test and violates a Monitor assertion. It is not a 0602 candidate gate. After the 0603
candidate, the unified 0.4+0.6 real-hardware activity runs it on one named supported Windows
target and records evidence showing:

1. failed-before Host/Target/Monitor evidence and exact firmware identity;
2. at least two hypotheses with one discriminating observation each;
3. register/Fault/log OBSERVE evidence;
4. authorized halt, temporary breakpoint, step, resume, and cleanup;
5. a user-supplied source change declaration;
6. separately authorized build, flash, and Target test actions;
7. new firmware identity, passing exact test, and passing Monitor assertion;
8. deterministic verification PASS and resolved session;
9. a verified portable diagnostic bundle.

The 0602 candidate must complete the product, fake-backend, deterministic fixture, temporary-
workspace fixed-patch, and read-only replay coverage needed to make this later activity
executable. Fake/replay PASS permits the module state `SOFTWARE_COMPLETE_HARDWARE_PENDING`; it is
not real-board PASS and cannot satisfy final v0.6.0 acceptance. The final v0.6.0 release remains
blocked until the unified activity produces real-hardware PASS.

## 14. Candidate matrix and exit criteria

Before implementing each measured hot path, 0602 freezes its exact performance workload and design
maximum; before candidate it freezes its within-maximum accepted calibration. After all 0602
product, packaging, fake-backend, replay, and deferred-hardware fixture tests exist and before
candidate, it replaces only its reserved catalog entries with exact commands and an exact
collected node inventory. The Windows-only 0602 candidate matrix runs 0601 release-contract/
immutability gates, complete affected Toolkit/Probe regressions selected by the catalog impact
map, dual Python, coverage, performance, isolation, offline installation, bundle security,
fake-backend, and read-only replay gates. It does not schedule Linux, a hardware shard, or the
real-board diagnostic scenario. It also verifies that:

- the gate schema/families, frozen evidence/test schemas, and 0601 public semantics did not change;
- exact 0602 entries replaced only their declared reserved families and no new family appeared;
- no generic write/raw-command/shell/cloud/model surface exists;
- every CONTROL/MODIFY trace has an exact single-use authorization event;
- the worktree remains clean and all retained evidence hashes verify.

Candidate runtime uses two different records. External orchestration may write only a
non-authoritative input record named exactly `candidate-invocation-context.json`; it cannot create,
update, replace, or satisfy the wrapper ledger. The candidate wrapper is the only actor permitted
to create or update `<candidateRoot>/candidate-ledger.json`. That ledger has exactly
`schema:"stm32-candidate-ledger/1"`, `module:"STM32TK-0602"`, `candidate_run_id`,
`expected_code_head`, `controller_path`, `candidate_root`,
`evidence_root`, `catalog_sha256`, `performance_sha256`, `support_profile_sha256`, `checkpoint`,
`state`, `created_at_utc`, and `updated_at_utc`. Controller, candidate/evidence roots, and non-null
checkpoint are normalized absolute paths; the controller resolves inside the frozen exact-CodeHead
worktree. State is exactly `prepared`, `running`, `passed`, `failed`, or `blocked`; hashes and run
identity are immutable after creation. Caller code must never synthesize or rewrite this ledger.

Every Windows absolute-path check reuses 0601's one committed
`tools/release/path_contract_0600.ps1` implementation of `ConvertTo-CanonicalAbsolutePath`, not
any newer-runtime-only path convenience API; 0602 cannot define a substitute. The helper rejects
null/empty/whitespace, drive-relative, root-relative, device/extended/NT aliases, dot segments,
mixed/trailing/redundant separators, and every other normalization mismatch. It accepts only an
already-rooted input whose `Path.GetFullPath()` output is ordinally identical to the input.
Controller contract tests execute this helper under Windows PowerShell 5.1 and cover every
accepted/rejected class.

The only resumable classification is `RECOVERABLE_INFRA_ERROR`. Its reviewer-authored canonical
JSON contains exactly `classification`, `event`, `reviewer`, `recorded_at_utc`, `run_kind`,
`run_id`, `code_head`, `checkpoint`, and `interrupted_attempt_digest`. `event` is exactly one of
`HOST_POWER_OR_REBOOT`, `RUNNER_LOSS_BEFORE_CHILD_RESULT`, `PHYSICAL_USB_OR_PROBE_REMOVAL`, or
`TARGET_POWER_LOSS`; `run_kind` is exactly `candidate-0602`; `run_id` is a canonical lowercase
hyphenated UUID (`8-4-4-4-12`); `code_head` and
`interrupted_attempt_digest` are lowercase hashes; `recorded_at_utc` uses the program UTC format;
and `checkpoint` is a normalized absolute path to the retained checkpoint. Candidate resume uses only the closed
wrapper interface `-ResumeCandidateRun -CandidateLedger <absolute-ledger-json> -RecoveryRecord
<absolute-recovery-json>`. The wrapper reconstructs and binds the original base inputs from its
ledger and rejects changed paths/digests/run ID/CodeHead/checkpoint, a mismatched prior-attempt
digest, noncanonical/additional fields, a completed child result, or a second resume. No legacy
resume or orchestration-context-as-ledger form is accepted. Reconciliation resolves controller and
verifier from the frozen worktree, re-reads the wrapper ledger, verifies its digest has not changed
since the terminal wrapper result, and rejects any immutable-field difference from the original
invocation context. Before reconciliation it independently verifies the frozen worktree's exact
HEAD, exact origin URL `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`, and empty porcelain
status including untracked files. It derives controller, verifier, catalog, and performance paths
only by joining frozen relative paths to that verified worktree; context executable paths are never
executed. The path helper and each re-derived file must have working bytes equal to its Git blob at
the exact CodeHead. Actual controller/verifier/catalog/performance SHA-256 values must match the
frozen context and the applicable ledger digests before the re-derived verifier path is executed. The
exact ledger schema has no verifier-digest field, so the verifier binds to the immutable
invocation context's `verifier_sha256`; catalog, performance, and support-profile digests bind to
both records.

After Windows candidate PASS, the module records `SOFTWARE_COMPLETE_HARDWARE_PENDING`. The Codex-
owned module report is created only then at
`docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md` and changes only that
path. It records the deferred unified real-hardware gate explicitly; its report commit becomes
0603's accepted base without claiming real-hardware acceptance.

## 15. Completion conditions

0602 succeeds when:

1. diagnostic history is append-only, hash-chained, recoverable, and concurrency-safe;
2. competing hypotheses and evidence polarity remain explicit through conclusion;
3. Probe v2 performs bounded debug controls without exposing arbitrary writes;
4. each CONTROL/MODIFY action consumes exact current authorization once;
5. source changes are externally supplied and cryptographically bound to verification;
6. the deterministic failed-before/fixed-after fixture, fake backend, and replay chain pass on
   Windows, and the module is marked `SOFTWARE_COMPLETE_HARDWARE_PENDING` rather than hardware PASS;
7. bundles are deterministic, portable, secret-free, and verified before import;
8. all Windows coverage, performance, security, offline, isolation, and prior-regression gates pass;
9. a Codex report-only child commit records the accepted 0602 software CodeHead and deferred gate;
10. final v0.6.0 acceptance remains blocked until the post-0603 unified 0.4+0.6 real-hardware
    activity passes the full Target and Monitor scenario.
