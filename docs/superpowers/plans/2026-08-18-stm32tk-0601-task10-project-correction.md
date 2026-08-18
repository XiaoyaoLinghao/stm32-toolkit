# STM32TK-0601 Task 10 Project Correction Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use subagent-driven development or executing-plans
> one unit at a time. This project plan freezes boundaries and ordering; every implementation unit
> still requires its own self-contained plan and fresh read-only reviews.

**Goal:** Replace the rejected monolithic T10.1 patch cycle with a frozen, mechanically reviewable
Evidence boundary matrix and eleven independently accepted implementation units, without changing
the Task 10 public workflow contract.

**Architecture:** One atomic typed-error ABI migration is followed by ten single-state-machine
Store, Catalog, and GC units. Each unit consumes only its immediate CLEAN parent, owns exact product
and test paths, and advances through a fail-fast eight-stage gate ladder.

**Tech stack:** Git worktrees and local commits; Python 3.10 and 3.12; pytest; branch coverage;
Markdown specifications and SHA-bound evidence.

## Global constraints

- Local Codex and its local subagents own implementation, tests, review, and acceptance. Do not
  dispatch work to another AI or an external cluster.
- Do not use network, remote Git, push, PR, merge, tag, hardware, probe, UART, or semihosting.
- One implementation agent may modify the shared implementation worktree at a time. Every reviewer
  is read-only.
- Preserve every user file and all existing untracked plans. Never discard, overwrite, or expose a
  dirty candidate to another owner.
- Fix only a direct frozen-spec requirement that is stably reproducible and causes an actual safety
  or correctness failure. Record theoretical hardening or threat-model expansion as non-blocking
  future work.
- No T10.1a–T10.1k unit may add protocol, Project, Probe, publication-controller, or
  release-controller behavior.
- The normative matrix is
  [2026-08-18-stm32tk-0601-task10-evidence-boundary-matrix.md](../specs/2026-08-18-stm32tk-0601-task10-evidence-boundary-matrix.md).
- The public workflow contract and exact delivery ordering are in
  [2026-08-17-stm32tk-0601-task10-public-workflows-design.md](../specs/2026-08-17-stm32tk-0601-task10-public-workflows-design.md).

---

## 1. Frozen status ledger

This ledger was reconstructed from local Git, the retained reports, and the process table before
the correction was persisted. Moving historical messages are not authority.

| Item | Frozen fact |
|---|---|
| Task 9 accepted head | `d4b43ff1bf74f7ac5058e93c708bfb49a5371304` |
| Task 10 public-contract commit | `4ffa927a2c6d10c6b693a31a06adf7e739e5cc30` |
| T10.P1 | `c57f17f450f6395367149e3c850b5e77bf38a655`, independently CLEAN |
| T10.P2 | `cf8057479b24e7a2e1e3905a98014706994feacc`, independently CLEAN |
| T10.P3 / correction parent | `9db31c12711c1bac40a43a7fbf8427f9aaa93c86`, independently CLEAN |
| Rejected r001 | `1c90cc984e3a0671dfde615563e87dd95287ac8f`, retained on its rejected branch |
| Frozen monolithic audit candidate | `ee2b153e031e45710cd7da5e60b00757678da07c`, one unpublished nine-path commit outside the accepted lineage |
| Matrix review | external SHA-256 `6D7F763342812DADB15C587D4F0B5AE94EA2219991DA71E788EA10B1554D0D67`; `SPEC/QUALITY/Overall/Matrix: CLEAN` |
| Remote/hardware authority | none; no remote, network, or hardware operation is permitted |

The docs-only correction starts at the exact P3 head. Its own commit SHA is deliberately not written
inside itself; Git and the independent review package bind that identity. It becomes the T10.1a
implementation base only after a fresh independent CLEAN verdict.

The external candidate `ee2b153e031e45710cd7da5e60b00757678da07c` is frozen and preserved. It
must not be amended, used as a parent, or cherry-picked as a whole. Its tests and implementation
ideas may be consulted as diagnostic source only; every selected byte is reintroduced and reviewed
inside the unit that owns the corresponding matrix cells.

The following five untracked plans remain user-owned in the retained candidate worktree and are not
modified by this correction:

- `docs/superpowers/plans/2026-08-17-stm32tk-0601-t10-1-evidence-error-taxonomy.md`
- `docs/superpowers/plans/2026-08-17-stm32tk-0601-t10-2-evidence-read-primitives.md`
- `docs/superpowers/plans/2026-08-18-stm32tk-0601-t10-p1-project-mutation-decoupling.md`
- `docs/superpowers/plans/2026-08-18-stm32tk-0601-t10-p2-probe-authorization-decoupling.md`
- `docs/superpowers/plans/2026-08-18-stm32tk-0601-t10-p3-project-regression-exception-realism.md`

### Review and evidence eligibility

The most recent completed implementation review covered the older candidate `a50fe430` and returned
`REVISION_REQUIRED`. Its two Important findings concerned Catalog SQLite cleanup and mutation-lock
cleanup masking a primary error. Run11b artifacts are authentic and byte-bound to `ee2b153`, and
report dual-Python targeted `13/13`, focused `96/96`, affected `580/580`, release `716/716`, plus
changed-file coverage `100/90/90/98/90`. They remain diagnostic only: they preceded the new review
ladder and no complete independent CLEAN review accepts `ee2b153`.

Invalid acceptance evidence includes the r001 editable-import RED/coverage artifacts, every GREEN
from superseded candidate SHAs, run11 Store coverage at 89%, and the zero-byte post-review-10 patch.
Historical evidence may explain a defect but cannot qualify new bytes.

## 2. Project problem ledger

| Category | Symptom | Root cause | Impact | Existing evidence | Prevention rule | Responsible unit |
|---|---|---|---|---|---|---|
| Task decomposition and dependencies | T10.1 combined Model, Store, Catalog, GC, nine paths, and a large single diff, although the exception ABI must change atomically across five product files | A deliverable named “taxonomy” mixed a mechanical ABI migration with multiple resource lifecycles | Review could not close in one pass; candidate identity changed repeatedly | Git diff/reflog; accepted-base raise inventory `43/42/19/27` | T10.1a is only the five-file ABI migration; every later unit owns one state machine | T10.1a–k |
| Hidden multiple state machines | Stable read, source copy, lock cleanup, SQLite, GC planning/auth/delete, and progress truth were reviewed together | Decomposition followed module names instead of transitions and commit points | Adjacent phases repeatedly produced new findings | Helper/caller graph and review rounds 6–10 | Every unit plan lists states, commit point, cleanup truth, and all exits | Each unit owner |
| Missing boundary cross-product | `iterdir`, exact EOF, lost-create, WAL/SHM/journal, and primary×cleanup cells appeared late | No complete matrix existed before implementation | Every point amendment invalidated later gates | r001 findings and accumulated r002 review | Freeze and independently review every executable B cell before product work | Matrix owner, then unit owner |
| Reviewer missed adjacent callers | A helper fix was followed by the same defect at a neighboring caller or exit | Review followed findings instead of mechanically reversing helper→all callers and caller→all exits | Ten review rounds still did not establish CLEAN | Accumulated review reports and caller inventory | Specialist reviewer reconciles every S/C/G ID and direct-site count; two consecutive misses force resplit | Gate 4 reviewer |
| Gate ordering | Affected and release suites ran repeatedly before specialist review | Expensive gates preceded the cheapest high-information gate | Large quantities of later-invalid evidence | Run01–run11b histories | Use the exact eight-stage fail-fast ladder in section 5 | Every unit owner |
| Test-environment contamination | Editable import targeted T08, parallel release roots collided, replay lacked ignored assets, and worktrees accumulated | Environments and evidence roots were not uniquely bound to candidate SHA | False failures and ambiguous evidence | r001 coverage and post-review environment reports | Unit/SHA-specific worktree, venv, basetemp, JUnit, import-path proof, and serial expensive gates | Environment/evidence owner |
| Evidence/report truth | Real artifacts and hashes existed although the latest completed review applied to an older failing SHA | Authenticity, SHA binding, and acceptance eligibility were conflated | A non-CLEAN candidate could be reported as accepted | Report/package/replay/JUnit audit | Reports record the three properties separately; a byte change invalidates every later gate | Report owner |
| Scope/threat-model drift | The original 131+7 classification grew into many additional race/cleanup combinations | No A–E classification separated frozen defects from theoretical hardening | Unit size and stopping criteria drifted | AST inventory and review history | Only A/B enter the unit; C has a named native owner; D is deferred to its named unit; E is non-blocking | Matrix and scope owner |
| Git/candidate management | One apparent commit was amended sixteen times and branch naming no longer described the work | Multiple state machines were stored in one moving candidate before the correction was tracked | Packages, coverage, and release evidence repeatedly expired | Reflog and worktree audit | Freeze `ee2b153`; land one docs-only correction; then create one immutable candidate commit per CLEAN unit | Integration owner |

## 3. A/B/C/D/E scope discipline

- **A:** frozen specification, executable now, and already represented by an exact test/control.
- **B:** frozen specification and executable now, but implementation or exact-test coverage is
  missing or conflicts with the frozen outcome. A unit cannot be CLEAN while one of its B cells is
  open.
- **C:** frozen platform-only behavior. The named native platform owner supplies the evidence;
  another platform cannot sign it.
- **D:** valid requirement owned by a later independent unit. It is recorded but cannot enter the
  current candidate.
- **E:** theoretical hardening, threat-model expansion, or an explicitly retained raw
  fault/publication seam. It does not block the current unit.

Only A/B cells may drive a unit's product change. C carries its exact owner and script. D/E are
retained without “while here” implementation.

## 4. Eleven-unit acyclic rebuild

Dependencies are strictly linear:

```text
docs-only CLEAN → 1a → 1b → 1c → 1d → 1e → 1f → 1g → 1h → 1i → 1j → 1k
```

| Unit | One primary state machine | Exact product allowlist | Exact test allowlist | Immediate dependency |
|---|---|---|---|---|
| T10.1a | Typed-error ABI atomic mechanical migration; exception/export, 131+7 literal codes, and mechanical catches only; no I/O flow change | `tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/model.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py`; `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_model.py`; `tools/stm32-toolkit/tests/test_evidence_store.py`; `tools/stm32-toolkit/tests/test_evidence_catalog.py`; `tools/stm32-toolkit/tests/test_evidence_gc.py` | docs-only correction CLEAN |
| T10.1b | Store mutation-lock acquire/body/release | `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` | `tools/stm32-toolkit/tests/test_evidence_store.py` | T10.1a CLEAN |
| T10.1c | Store managed stable-read/hash O0–O8 | `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` | `tools/stm32-toolkit/tests/test_evidence_store.py` | T10.1b CLEAN |
| T10.1d | Store caller-source first/second-pass ingest | `tools/stm32-toolkit/src/stm32_toolkit/evidence/store.py` | `tools/stm32-toolkit/tests/test_evidence_store.py` | T10.1c CLEAN |
| T10.1e | Catalog SQLite authoritative main/sidecar/query/cleanup | `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py` | `tools/stm32-toolkit/tests/test_evidence_catalog.py` | T10.1d CLEAN |
| T10.1f | Catalog rebuild pre-publication manifest scan/read taxonomy | `tools/stm32-toolkit/src/stm32_toolkit/evidence/catalog.py` | `tools/stm32-toolkit/tests/test_evidence_catalog.py` | T10.1e CLEAN |
| T10.1g | `put_root` existing-read/lost-create taxonomy | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` | T10.1f CLEAN |
| T10.1h | GC planning/snapshot taxonomy | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` | T10.1g CLEAN |
| T10.1i | GC authorization/ledger CREATE_NEW and cleanup truth | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` | T10.1h CLEAN |
| T10.1j | GC identity-bound delete primitive and commit truth | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` | T10.1i CLEAN |
| T10.1k | GC apply orchestration, exact progress, and outer cleanup | `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py` | `tools/stm32-toolkit/tests/test_evidence_gc.py` | T10.1j CLEAN |

The publication/durability seams named class E remain unchanged in T10.1d/T10.1f/T10.1j. T10.1k
cannot modify the Store API; if its frozen contract needs a new Store interface, stop and create a
separate docs-only prerequisite design unit before any cross-domain edit.

Every unit must have:

- one self-contained implementation plan written against its full immediate accepted-parent SHA;
- one primary module domain and one state machine;
- an exact product/test allowlist and a static out-of-scope diff gate;
- one independent candidate commit;
- Formal RED, targeted and complete-matrix focused evidence;
- changed-file branch coverage of at least 90%;
- independent specialist and complete-diff CLEAN reviews;
- a report that separates authenticity, SHA binding, and acceptance eligibility.

## 5. Mandatory eight-stage gate ladder

1. **Formal RED** against the exact immediate accepted parent, on both Python versions except named
   platform-only cells.
2. **Targeted GREEN** for the unit's single state machine.
3. **Complete boundary-matrix focused gate** for every A/B cell and retained control assigned to the
   unit.
4. **Independent specialist review CLEAN** before any broad suite.
5. **Affected suite plus changed-file branch coverage ≥90%** on Python 3.10 and 3.12.
6. **Complete immediate-parent-to-candidate diff independent acceptance CLEAN.**
7. **Dual-Python release suite**, serially, only after gates 1–6.
8. **Read-only final acceptance** with no active scope expansion.

Any failure stops all later gates. Any product or test byte change creates a new run ID and resets to
gate 1. Two consecutive rounds that find an adjacent missed seam force a return to the complete
matrix and a new split; another point amendment is forbidden. A release failure returns to the
matrix/RED stage. Nothing may change product or test bytes after release evidence begins.

## 6. Platform and evidence ownership

Windows owns native reparse/file ID, `msvcrt` lock/cleanup, and Win32 identity-bound delete cells.
The boundary matrix names `local Codex POSIX acceptance reviewer` as the POSIX C-cell owner and
contains the exact SHA-bound, offline, dual-Python script. A unit may be Windows CLEAN with
`DEFERRED(POSIX)`, but cumulative Task 10 acceptance requires native POSIX PASS for every C cell.

Every test run uses a clean candidate worktree, candidate-specific external venvs and evidence
roots, explicit import-resolution proof, unique JUnit files, skip/reason inventory, final Git status,
and scoped process audit. Expensive gates run serially. A report may retain older evidence for
diagnosis but must mark it ineligible after any candidate byte change.

## 7. Execution checkpoints

- [x] Freeze the project problem ledger and complete Store/Catalog/GC matrix.
- [x] Obtain independent `SPEC/QUALITY/Overall/Matrix: CLEAN` for the external correction material.
- [ ] Obtain independent CLEAN for this three-path docs-only correction commit.
- [ ] Write and independently review the T10.1a unit plan against that CLEAN docs-only commit.
- [ ] Execute T10.1a through T10.1k sequentially; advance only after each unit is CLEAN.
- [ ] Resume T10.2 only from the accepted T10.1k head and rebase its independent plan on that exact
  SHA.

This project plan does not authorize product implementation before the docs-only correction is
CLEAN and does not itself substitute for any unit-level plan, test, evidence package, or review.
