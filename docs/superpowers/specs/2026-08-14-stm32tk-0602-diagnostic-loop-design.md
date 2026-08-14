# STM32TK-0602 Evidence-Driven Diagnostic Loop Design

**Status:** Approved module design baseline
**Date:** 2026-08-14
**Module:** `STM32TK-0602-DIAGNOSTIC-LOOP`
**Accepted base:** the accepted report commit of `STM32TK-0601-TEST-EVIDENCE`
**Fixed program base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** OpenClaw, when a work order is authorized
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
- portable diagnostic bundle export/import verification;
- CLI, MCP, and a thin `diagnose-firmware` Skill;
- software, security, performance, isolation, and real-board acceptance evidence.

### 2.2 Excluded

- arbitrary target memory/register writes;
- permanent flash breakpoints, Option Bytes, chip erase, or probe lease stealing;
- authorization reuse, background debugging, or unattended retries;
- automatic source patch generation/application inside Toolkit;
- Monitor cross-run UI and annotations, owned by 0603;
- a probabilistic or model-generated PASS decision.

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

Session IDs are random 128-bit lowercase hex values. Revision begins at zero and increments by
one per accepted event. The identity binds the workspace, logical project, input snapshot,
build, ELF, target, and Toolkit version. An identity transition is not implicit: rebuild or
reflash creates a typed event that carries old and new identities.

States are:

```text
OPEN -> INVESTIGATING -> FIX_PROPOSED -> VERIFYING -> RESOLVED
  |          |                |             |
  +----------+----------------+-------------+-> ABANDONED
```

`RESOLVED` requires deterministic verification. `ABANDONED` records a reason and does not mean
fixed. A session may move from `VERIFYING` back to `INVESTIGATING` after failed verification;
the failed result remains in history. No state or event is deleted or overwritten.

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

The digest is SHA-256 of canonical event JSON without `digest`. Sequence zero has no previous
digest; every other event binds the prior digest. Opening or cold-materializing a session verifies
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

0602 implements the operations already frozen in 0601's `stm32-toolkit-probe/2` schema:

| Operation | Level | Bound |
|---|---|---|
| `target.state.read` | OBSERVE | exact target/lease |
| `target.halt` / `target.resume` | CONTROL | one transition |
| `target.step` | CONTROL | one source/instruction step, 5 s maximum |
| `breakpoint.temporary.set` | CONTROL | executable address, max 8/session |
| `breakpoint.temporary.clear` | CONTROL | exact owned breakpoint ID |
| `registers.read` | OBSERVE | allowlisted core register names |
| `memory.read` | OBSERVE | declared readable RAM/peripheral range, <=4 KiB/call |
| `fault.capture` | OBSERVE | core Fault registers plus bounded stack |
| `logs.capture` | OBSERVE | named channel, <=10 MiB or <=5 min |

CONTROL action digests bind session ID, expected revision, workspace/project, target/probe,
firmware identity, operation, typed arguments, current target state, and a monotonic expiry no
later than five minutes. `authorized=true` without the exact digest is invalid. Authorization is
consumed once even when the backend reports failure.

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

Explicit export creates a deterministic ZIP64-disabled archive up to 1 GiB containing:

```text
bundle.json
session/events/*.json
evidence/manifests/*.json
evidence/objects/<digest>
source/change.diff                 # when declared
inventory.json
```

`bundle.json` binds the session head, evidence graph, redaction policy, creator version, and
inventory digest. Entries are sorted, timestamps fixed, modes normalized, compression policy
fixed, and duplicate/case-fold/path-escape names rejected. Secrets, absolute paths, auth tokens,
probe access URLs, and unrelated environment variables are never exported. Imports verify every
byte before publishing any object and never merge events into an existing different chain.

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
```

MCP tools are narrower typed counterparts: session create/read, event append, hypothesis update,
observation plan/execute, control prepare/execute, change register, verification run, and bundle
export. They return `OperationResult`; artifacts remain references. Read calls are OBSERVE.
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
12. Windows/Linux, CPython 3.10/3.12, offline wheel and managed launcher regressions.

Property tests generate event sequences and action digest mutations. Fault injection covers a
crash before/after event publish, head replacement, breakpoint creation, cleanup, flash, test
capture, and bundle import. Tests assert evidence remains recoverable and no unauthorized next
step occurs.

### 13.2 Performance

In addition to unchanged 0.5 and 0601 thresholds:

| Operation | Dataset | Ceiling |
|---|---|---:|
| append diagnostic event | warm verified 10,000-event session | p95 50 ms |
| read materialized session | 1,000 events, 64 hypotheses | p95 100 ms |
| verify session chain | 10,000 events | 1 s |
| export verified bundle | 10 MiB reachable artifacts | 2 s |

The accepted-baseline regression limit is 15%, measured independently on CPython 3.10 and 3.12
with the common program method. No global GC state is toggled in a request path; optimizations
must be local, thread-safe, and covered by concurrent tests.

### 13.3 Real-board diagnostic scenario

The mandatory scenario starts with a firmware fixture that deterministically fails a Target
test and violates a Monitor assertion. Evidence must show:

1. failed-before Host/Target/Monitor evidence and exact firmware identity;
2. at least two hypotheses with one discriminating observation each;
3. register/Fault/log OBSERVE evidence;
4. authorized halt, temporary breakpoint, step, resume, and cleanup;
5. a user-supplied source change declaration;
6. separately authorized build, flash, and Target test actions;
7. new firmware identity, passing exact test, and passing Monitor assertion;
8. deterministic verification PASS and resolved session;
9. a verified portable diagnostic bundle.

The scenario is run on one named supported target on Windows and the read-only/replay portion on
Linux. Fake-backend integration is additional evidence, not a substitute.

## 14. Candidate matrix and exit criteria

The 0602 candidate matrix runs all 0601 release-contract/integrity gates, complete affected
Toolkit/Probe regressions, dual Python, platform, coverage, performance, isolation, offline
installation, bundle security, and the real-board diagnostic scenario. It also verifies that:

- `gates_0600.json`, frozen evidence/test schemas, and 0601 public semantics did not change;
- any allowed catalog addition was already declared by the 0601 final catalog extension slots;
- no generic write/raw-command/shell/cloud/model surface exists;
- every CONTROL/MODIFY trace has an exact single-use authorization event;
- the worktree remains clean and all retained evidence hashes verify.

The module report is created only after candidate PASS and changes only its report path. The
report commit becomes 0603's accepted base.

## 15. Completion conditions

0602 succeeds when:

1. diagnostic history is append-only, hash-chained, recoverable, and concurrency-safe;
2. competing hypotheses and evidence polarity remain explicit through conclusion;
3. Probe v2 performs bounded debug controls without exposing arbitrary writes;
4. each CONTROL/MODIFY action consumes exact current authorization once;
5. source changes are externally supplied and cryptographically bound to verification;
6. a failed-before/fixed-after real-board chain passes Target and Monitor assertions;
7. bundles are deterministic, portable, secret-free, and verified before import;
8. all coverage, performance, platform, security, and prior-regression gates pass;
9. a report-only child commit records the accepted 0602 product CodeHead.
