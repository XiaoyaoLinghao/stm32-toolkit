# STM32 Toolkit 0.6 Evidence, Test, Diagnostics, and Analytics Program Design

**Status:** Approved design baseline for implementation planning
**Date:** 2026-08-14
**Program:** `STM32TK-0600-EVIDENCE-DIAGNOSTICS-PROGRAM`
**Accepted product base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** assigned per module in the later work order
**Remote actions authorized by this document:** none

## 1. Purpose

Version 0.6 completes the deferred test and evidence-driven diagnostic loop without
repeating the 0.5 release cycle failure mode. It delivers:

1. reproducible host and target test execution with immutable evidence;
2. deterministic diagnostic sessions with safe observation, control, and fix verification;
3. Monitor cross-run analytics, quality views, annotations, diagnostic markers, and
   an AI-readable analysis bundle.

This specification and its three module specifications are the authoritative 0.6
contract. They supersede only the 0.6 Tasks 3--4 and 0.6 exit text in
`docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md`.
That older document remains historical evidence for 0.5; it must not be used as an
implementation work order for 0.6.

The release is one `0.6.0` product, but implementation is split into three independently
reviewed modules and CodeHeads. Each module has its own specification, plan, candidate
matrix, retained evidence, and report-only commit. The third module's product CodeHead is
the sole final `0.6.0` CodeHead.

## 2. Why the program is split

The 0.5 retrospective identified six process failures:

- the acceptance contract became executable after product implementation;
- product and acceptance-tool corrections both invalidated the CodeHead;
- a linear fail-fast matrix revealed one late problem per run;
- CPython 3.10 performance entered too late;
- product coverage was mixed with subprocess-heavy controller tests;
- support/evidence infrastructure became an unplanned product during release closure.

0.6 therefore freezes the acceptance catalog and evidence format in the first module,
uses quick and candidate matrices to discover all failures before release freeze, and
runs one fail-fast final matrix only after every final gate has already passed in ordered
preflight.

## 3. Module sequence

| Module | Product result | Contract frozen at exit |
|---|---|---|
| `STM32TK-0601-TEST-EVIDENCE` | shared evidence store, Project Schema v3, Host/Target tests, four target transports, 0.6 gate controllers | evidence/test schema, gate catalog, coverage boundary, performance method |
| `STM32TK-0602-DIAGNOSTIC-LOOP` | append-only diagnostic state machine, Probe protocol v2 debug/log controls, evidence-driven fix verification | diagnostic events, authorization/action digest, debug safety contract |
| `STM32TK-0603-MONITOR-ANALYTICS` | cross-run comparison, quality analytics, annotations/markers, AI bundle, final 0.6 release | Monitor history v2, analytics API/UI, final release inventory |

The accepted base of each later module is the previous module's report commit. A later
module may consume earlier public interfaces but must not silently rewrite their evidence.

## 4. Program architecture

```text
Claude Code Plugin
├── thin Skills: test and diagnostic strategy, authorization dialogue
├── STM32 Toolkit CLI/MCP
│   ├── testing: host/target orchestration
│   ├── evidence: immutable manifests and content-addressed objects
│   └── diagnostics: hypotheses, evidence, actions, verification
├── Probe Service v2
│   ├── OBSERVE: reads, samples, Fault, logs
│   ├── CONTROL: halt/resume/step/temporary breakpoints
│   └── MODIFY: reset/flash/target tests
└── STM32 Monitor
    ├── existing 0.5 live/history service
    ├── history v2 quality metadata
    └── read-only analytics and explicit annotations/bundles
```

Toolkit and Monitor remain local-only. No product component calls a cloud model, embeds
an API key, uploads evidence, or provides an unreviewed automatic code editor. The AI
client reasons through Skills and MCP; deterministic code validates and records every
state transition and hardware operation.

## 5. Shared evidence contract

### 5.1 Protocol

The authoritative envelope protocol is `stm32-evidence/1`.

```python
@dataclass(frozen=True)
class EvidenceIdentity:
    workspace_id: str
    logical_project_id: str
    session_id: str
    git_head: str
    git_dirty: bool
    input_snapshot_sha256: str
    build_id: str
    elf_sha256: str
    target_device: str
    toolkit_version: str
    produced_at_utc: str

@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    media_type: str
    relative_path: str
    bytes: int
    sha256: str

@dataclass(frozen=True)
class EvidenceEnvelope:
    schema: str
    evidence_id: str
    operation: str
    identity: EvidenceIdentity
    parents: tuple[str, ...]
    artifacts: tuple[ArtifactRef, ...]
    facts: Mapping[str, object]
```

All structures use exact types, immutable containers, UTC timestamps, NFC text, POSIX
relative paths, finite numbers, bounded JSON depth/nodes/strings, lowercase SHA-256,
and fresh JSON-safe `to_dict()` output. Exported evidence contains no absolute root,
token, access URL, ambient environment, or unrelated workspace data.

### 5.2 Storage

```text
${CLAUDE_PLUGIN_DATA}/projects/<workspaceId>/evidence/
├── objects/sha256/<first-two>/<digest>
├── manifests/<evidenceId>.json
├── catalog.sqlite3
├── tests/<runId>.json
├── diagnostics/<sessionId>/events/<sequence>-<digest>.json
├── diagnostics/<sessionId>/head.json
└── annotations/<annotationId>.json
```

Objects, manifests, diagnostic events, and annotation revisions are immutable. The
SQLite catalog is a derived index and can be rebuilt solely from verified manifests.
Writes use same-directory temporary files, flush/fsync, and atomic replacement. Every
ancestor is inspected; symlinks, junctions, reparse points, hard-link aliases, special
files, case-fold collisions, digest mismatches, and path escapes fail closed.

Garbage collection is explicit. It marks all references reachable from test runs,
diagnostic heads, analysis bundles, and annotation revisions, produces a dry-run plan,
requires confirmation, and never deletes unknown or corrupt evidence.

## 6. Protocol and version decisions

| Surface | 0.6 contract |
|---|---|
| Product SemVer | Toolkit, Monitor, Plugin, active Skills, CLI/MCP all `0.6.0` |
| Python | `>=3.10`; recommended and managed runtime 3.12; 3.10/3.12 mandatory |
| Project Schema | write v3; read v2/v3; explicit dry-run/apply upgrade |
| Evidence | `stm32-evidence/1` |
| Test events | `stm32-test/1` |
| Probe | `stm32-toolkit-probe/2`; same-version local components only |
| Monitor history | write v2; read v1/v2; no in-place rewrite of 0.5 history |
| OperationResult | retain `stm32-toolkit/1` shape; add only typed data/error codes |

## 7. Safety and authorization

The existing levels remain authoritative:

- `OBSERVE`: source/build/evidence reads, variables/registers/Fault/logs/Monitor history;
- `CONTROL`: halt/resume/step and temporary breakpoints;
- `MODIFY`: reset, build, flash, target tests, and fix verification.

CONTROL and MODIFY calls bind `authorized=true` to the exact action digest, expected
diagnostic revision, workspace, session, target, and firmware identity. Authorization is
per action, is never persisted as a reusable capability, and never permits Option Bytes,
chip erase, arbitrary memory writes, lease stealing, or killing unrelated processes.

## 8. Cross-module data flow

```text
source + Project Schema v3
  -> build + FirmwareIdentity
  -> Host/Target TestRunManifest
  -> immutable EvidenceEnvelope
  -> DiagnosticSession hypotheses/actions/conclusion
  -> authorized fix + new build/flash/test evidence
  -> Monitor history/assertion and RunComparison
  -> FixVerification
  -> explicit AI analysis bundle and final release evidence
```

Monitor does not become the program database. It exposes verified read-only history
queries and analysis bundles. The shared evidence store does not open Monitor's SQLite
files. Links are by immutable IDs and identity fields.

## 9. Acceptance architecture

Module 0601 first adds and self-tests:

```text
tools/release/gates_0600.json
tools/release/run_0600_quick.ps1
tools/release/run_0600_candidate.ps1
tools/release/run_0600_final.ps1
tools/release/verify_0600_release.py
```

The gate catalog records exact command, owner, tools, timeout, node inventory, evidence,
coverage mode, and matrix membership. Product implementation cannot introduce an
unlisted final gate. Controller/helper/verifier tests never inherit product coverage.

| Matrix | Trigger | Behavior | Reference budget |
|---|---|---|---:|
| Quick | every important commit | all independent partitions run; no fail-fast | 10 min |
| Candidate | each module CodeHead | full module software/install/hardware/integrity gates; collect all failures | 25 min |
| Final | frozen 0603 CodeHead only | one fail-fast complete release run | 45 min |

The final run includes the complete 0.5 regression, Windows and Linux dual Python,
Node/browser, four real target transports, offline wheels/managed runtime, security,
accessibility, five-minute live/analytics performance, coverage, artifact inventory,
source hashes, and clean-tree checks.

## 10. Performance method

Before each new hot path is implemented, its acceptance test records a baseline on the
named Windows reference host and separately on CPython 3.10 and 3.12. Measurement uses
at least three warmup rounds and ten measured rounds, without coverage instrumentation,
and records p50/p95/max, GC, CPU, memory, I/O, and data scale. Each gate combines a
fixed absolute user-facing ceiling with at most 15% regression from its accepted base.
Thresholds are frozen before GREEN implementation and cannot move after a failure.

All 0.5 product performance thresholds remain unchanged.

### 10.1 Windows reference profile

Absolute and relative release-blocking performance measurements use this frozen profile:

| Component | Reference |
|---|---|
| CPU | AMD Ryzen 7 5800U, 8 cores / 16 logical processors |
| Memory | 16 GB installed (at least 15.3 GiB visible) |
| Storage | local WDC PC SN530 512 GB NVMe for source/temp/evidence |
| OS baseline | Windows 11 Professional x64, build 26200 |
| Power | AC power, High performance scheme `8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c` |
| Python | CPython 3.10.11 and 3.12.10, isolated environments |
| Node | Node 24.18.0 and npm 11.16.0 from the verified support root |
| Browser | package-lock Playwright 1.56.1 managed Chromium |

The runner records exact CPU, visible memory, storage model/bus, OS build, power scheme, Python,
Node/npm, browser, antivirus/exclusion state, AC/battery state, free disk, and background-load
preflight in each result. Source, temp, and evidence stay on local NVMe and outside the product
worktree where applicable. Network is disabled for release gates.

If an OS build, interpreter patch, Node/browser binary, storage device, or power profile changes,
relative comparison requires an environment-calibration run of the frozen prior accepted
CodeHead before any new hot-path implementation. Calibration may establish the new same-machine
baseline but may not relax an absolute threshold or happen in response to a product failure.
Linux and non-reference browser runs are mandatory correctness/security gates, not owners of the
absolute performance verdict; their exact environment is still retained with the evidence.

## 11. Platform and hardware truthfulness

Mandatory 0.6 evidence includes:

- Windows 11 AMD64, CPython 3.10/3.12, Node/npm, Chromium;
- Linux x86_64, CPython 3.10/3.12, Node/npm, Chromium/Firefox/WebKit core flows;
- real-board memory-mailbox, RTT, UART, and semihosting target-test runs;
- a real-board diagnostic loop containing OBSERVE, CONTROL, MODIFY, failed-before,
  fixed-after, Target test, and Monitor assertion evidence.

A transport without real hardware evidence returns `TEST_TRANSPORT_UNAVAILABLE` and is
not documented as supported. If it is part of the declared 0.6 release surface, the
release remains RC/BLOCKED rather than converting the gate to PASS or deferring it.

## 12. CodeHead and report lifecycle

```text
v0.5.0
 -> 0601 CodeHead -> candidate PASS -> 0601 report-only commit
 -> 0602 CodeHead -> candidate PASS -> 0602 report-only commit
 -> 0603/final CodeHead
 -> ordered preflight of every final gate
 -> freeze
 -> one final matrix
 -> final report-only commit
 -> v0.6.0
```

Any product, test, helper, protocol, dependency, version, README, roadmap, or active
Skill correction creates a new CodeHead. Reports are created only after overall PASS.
The final candidate accepts no new optimization, test feature, or gate. Two consecutive
candidate cycles exposing new acceptance-contract gaps trigger an acceptance-architecture
audit before another candidate is created.

## 13. Program non-goals

0.6 does not:

- add CubeMX project creation (0.7 scope);
- generalize to every MCU, framework, board, probe, or test framework;
- embed a model provider or cloud service;
- allow browser-side AI or remote analytics;
- auto-create Monitor groups or annotations;
- automatically edit/flash without current-task authorization;
- add Option Bytes, arbitrary writes, chip erase, or probe lease stealing;
- rewrite 0.5 history/evidence in place;
- claim a transport/platform supported from fake or skipped tests.

## 14. Program success criteria

0.6 is complete only when:

1. Host and Target tests emit verified identity-bound immutable evidence.
2. All four target transports have parser, replay, integration, and real-board PASS.
3. A diagnostic session preserves competing hypotheses and supporting/refuting evidence.
4. Safe observations and authorized debug/modify actions are fully audited.
5. A real failure is reproduced, fixed, rebuilt, reflashed, retested, and verified by
   Target tests plus a Monitor assertion.
6. Monitor provides bounded cross-run comparison, quality analytics, annotations,
   diagnostic markers, and explicit AI bundle creation.
7. Two concurrent workspaces remain isolated across every product and evidence surface.
8. Windows/Linux, dual Python, browser, coverage, performance, offline install, source
   integrity, and artifact evidence gates pass at one immutable final CodeHead.
9. The final report is a report-only child commit and `v0.6.0` points to the accepted head.

## 15. Requirement-to-spec map

| Requirement | Owning specification |
|---|---|
| Evidence store, Schema v3, Host/Target runners, transports, gate framework | `2026-08-14-stm32tk-0601-test-evidence-design.md` |
| Diagnostic state machine, Probe v2 controls, authorization, fix verification | `2026-08-14-stm32tk-0602-diagnostic-loop-design.md` |
| Monitor history v2, comparison, quality, annotations, AI bundle, final release | `2026-08-14-stm32tk-0603-monitor-analytics-design.md` |
