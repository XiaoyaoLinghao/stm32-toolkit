# v1.3.5 packaging entry checkpoint — 2026-10-30

Current phase: **PACKAGE_ENTRY_REVISION_REQUIRED / RETRY_AUTHORIZATION_PENDING**.
Offline software remains ACCEPTED_WITH_FIXES (3,204 distinct passes,3 platform skips;
all user-authorized coverage non-regression groups met). Local closeout is incomplete.
Accepted base `946b1ec5c0dd3c79bb5b5e73ce1650afa5ecb432`; frozen build CodeHead before this report commit
`eac81a00a9c0cb0f78dcc0b423945605897b4806`. No product/test edits or existing-runtime/hardware/remote changes.

One ordinary Claude build check actually ran and exited2 with `closed build backend
is unavailable`; source unchanged. The native command had one leading ASCII space
outside its exact allowlist, so the invocation remains **NOT_ACCEPTED** (CLI0,
dispatcher1, actual native exit2). The summary's exact-planned command not_invoked
does not erase the separately recorded unexpected command's actual execution.
No test command was designated. No second build, artifact comparison or bundle
verification ran. No retry or permission normalization occurred.

Primary found a concrete input omission: the prepared62-wheel runtime dependency
copy lacked the fixed setuptools84.0.0/wheel0.48.0 build backends. The utility captures
but does not retain their pip stderr in this generic failure, so no additional pip
trace or exclusive cause is invented. An offline64-wheel input is now prepared from
the unchanged62 and the two existing pinned cache wheels, with hashes/RECORD verified;
this copies files only, installs nothing and does not retry the build. Runtime/policy
and frozen source stay unchanged. See [packaging-entry-review.json](packaging-entry-review.json).

Proposed next step requires explicit bounded authorization under AGENTS.md: one A
Claude re-delegation with exact no-leading-space command, separate output/temp/evidence
paths and the complete input; PASS then permits the original-unstarted B build and
13-file/official bundle checks. Errors/refusals/scope violations stop; no automatic
retry, product edit, recipient install, hardware, runtime replacement or publication.
Raw evidence: `D:/codex-tmp/r135`. Earlier checkpoints are retained below.

---

# v1.3.5 offline integration checkpoint — 2026-10-30

Status: **ACCEPTED_WITH_FIXES for offline software / PACKAGE_BUILD_PENDING**.
Overall release remains **LOCAL_CANDIDATE_NOT_QUALIFIED**; no publication or installation.
Accepted base `946b1ec5c0dd3c79bb5b5e73ce1650afa5ecb432`; reviewed product/test CodeHead before this report commit
`fa3613cb7b24a0f0532aff5248acb9ad919a112a`, branch `codex/v135-release-closeout`, no active PR or remote authorization.
Primary owns specification, orchestration, independent complete-diff review and acceptance.
Local Claude Code CLI retained the existing `deepseek-v4.1-flash[1m]` route for all
implementation/test changes and delegated verification. The governing [specification](../../../superpowers/specs/2026-10-30-v135-release-closeout.md)
and [plan](../../../superpowers/plans/2026-10-30-v135-release-closeout.md) remain in force.

## Behavior and independent review

Toolkit/Monitor/UI/plugin/setup/launchers/release authorities align to1.3.5, with
additional1.3.4 legacy runtime/producer recognition and existing refusal guards.
Unpublished candidate guidance, canonical setup trust anchors and published1.3.4
history are aligned. Inherited accepted fixes retain SDK0.46.0, ordinary100kHz,
controlled pre-program reset/HALTED gate, attach progress and initiating diagnostic
preservation. This closeout changes no production timeout, schema or hardware policy.
Primary reviewed every phase diff and the complete43-file closeout diff in the clean
exact-head independent checkout. An earlier328-case independent generation run passed;
its product/generation bytes remain unchanged and its overlapping cases are not added.

## Integration and retained original outcomes

The bounded matrix has **3,204 distinct passing cases,3 platform skips, zero unresolved
failures/errors**, across26 original groups plus39 direct CLI/MCP consumer files in10
additional groups. All39 command executions, including3 single-node rechecks, are
terminal. This is a source-bound multi-entry evidence set, not a fresh full-repository
or single-final-head rerun. [integration-evidence.json](integration-evidence.json)
records per-run identities, actual pytest exits, JUnit/raw hashes and native dispositions.

- Monitor's original89pass/1failure was a bare-interpreter `-I` child missing jsonschema.
  An explicitly authorized disposable dependency-complete test venv uses the same real
  CPython3.12.14/SDK0.46.0/existing dependencies without package installation. Only the
  failed node reran and passed; `-I` and all assertions stayed. Strict PID/trace/worker
  checks retain their original real-interpreter evidence and validation.
- API recovery's original20pass/1failure exposed an existing dummy-model snapshot gap.
  Authorized Claude correction touched only that test body, retained real public begin/CLI
  and all refusal assertions; one-node recheck passed.17 native edit calls/2 edits, no
  errors/scope violations. Other20 passing cases were retained, not rerun.
- Planned actions' original8pass/1failure expected the old preflight message. Both test
  and product were identical to published1.3.4; the required separate absolute output
  directory guidance is correct. Authorized Claude correction changed only the independent
  expected literal, preserving both test functions/full equality.4 native calls/1 edit,
  no errors/scope violations; one-node recheck passed, original8 passes retained.
- Original pending build t07 later passed102 cases (actual pytest0, wrapper180.369s); pending
  consumer c03 later passed70 cases (actual pytest0, wrapper705.204s). Workers stopped after native
  structured pending results. Primary reconciled existing bound reports/JUnit/coverage,
  with no rerun, worker polling, restart or kill. Original CLI/dispatcher1 and native
  numeric exitnull remain; the pending invocations are not retrospectively accepted.
- Failed aggregate inputs t25/c01/c08 are excluded from raw coverage. The two original
  stopped edit calls remain NOT_ACCEPTED with zero writes/tests; historical logs remain.
  Primary Git identity/task-preparation errors also remain separately recorded, with no
  additional delegated test startup or product edit caused by those errors.

## Exact native coverage comparison

| Group | v1.3.4 | v1.3.5 | User condition | Permanent result |
| --- | --- | --- | --- | --- |
| toolkit-overall | 15336/18534 | 15530/18734 (82.8974%) | PASS | 90%: UNMET |
| toolkit-risk-core-v2 | 14208/17194 | 14399/17394 (82.7814%) | PASS | 90%: UNMET |
| monitor-overall | 3292/3564 | 3292/3564 (92.3681%) | PASS | 90%: PASS |
| monitor-risk-core-v2 | 3292/3564 | 3292/3564 (92.3681%) | PASS | 95%: UNMET |
| UI overall | 2938/3147 | 2938/3147 (93.3588%) | PASS, exact-source reuse | Per-file90: PASS |

Every applicable exact ratio meets the user's1.3.5-only non-regression condition;
comparison uses integer cross-products, with no averaging or rounded threshold decision.
Permanent unmet gates remain UNMET. Broad-core-v1 equals each package's whole-source
overall totals and retains its separate historical disposition; no new gate is invented.
All149 Python source files are mapped, with the new probe responsibility included and
no prior member removed. Changed-source prior arcs are dropped; unchanged arcs retain
exact hashes and relevant SDK-dependent paths have fresh offline evidence. Measured
source bytes for all149 files equal canonical Git bytes. UI source/config/dependencies
and shipped assets match accepted evidence; root metadata alone changed version, so
534pass/1 platform skip and coverage are explicitly reused. No fresh UI run is claimed;
the original historical performance failure remains alongside the prior accepted evidence.

## External checks and next phase

These actual platform skips remain, not PASS:

- `tests.test_diagnostic_cli::test_unsafe_steps_symlink_is_generic_error_without_dispatch`: symlink capability unavailable.
- `tests.test_linker_fragment::test_read_linker_fragment_rejects_a_real_symlinked_file`: unprivileged Windows file symlinks are unavailable; mocked coverage applies.
- `tests.test_vscode_configuration::test_redirect_targets_are_refused`: host cannot create a file symlink for this check.

Owner: Primary, at later explicitly scoped release validation on a Windows/Linux host
with real file-symlink capability. No privilege/policy change is authorized here.
Final installed upgrade/rollback, VS Code/MCP and interactive user validation remain
USER_VALIDATION_PENDING (user with Primary release support). No new browser, installed
runtime or final1.3.5 hardware acceptance is claimed. The prior original-pair100kHz
physical PASS keeps its recorded source/SDK/image scope and consumed authority.
ABI/CCM firmware work remains outside scope at the user's direction.

Next: freeze this documentation-only source checkpoint, perform two independent official
offline builds from clean canonical Git bytes, compare all13 outputs and run official
extracted-bundle verification. The closed62-wheel input is prepared; only each builder's
owned disposable backend environment may be populated offline. No recipient/existing
runtime installation, hardware, push, PR, merge, tag or publication is authorized.
Evidence root: `D:/codex-tmp/r135`; immutable matrix SHA256
`947b2e923dc15bc5e2abd180fc2bd54d19cc003d2ebed5057ef37735ba951c0c`; coverage qualification SHA256
`b75d51148cf45b76359097d501b23e5cd8f6c862ffe1fa762367fcfeb78c1b4c`.

---

The following checkpoints are retained historical snapshots, not the current status.

# v1.3.5 local closeout checkpoint

## Version/documentation review checkpoint — 2026-10-30

Current status: **VERSION_DOCS_REVIEW_ACCEPTED / INTEGRATION_PENDING**.
Accepted base remains946b1ec5c0dd3c79bb5b5e73ce1650afa5ecb432. Reviewed CodeHead
before this report commit:9604da7f3479513bc2b5f3db3255bac52ed97bca, branch
codex/v135-release-closeout. Primary independently reviewed all phase diffs and
the complete base-to-CodeHead inventory in the clean post134-independent-review
checkout. All changes stay within the approved closeout and governance scope.
This checkpoint does not claim tests, coverage comparison or packages passed.

Local Claude Code CLI, unchanged deepseek-v4.1-flash[1m] route, implemented:

-13 core version files at09d2f0638d806bf5557b64b9ea27feb51f1e86ca;65 native calls,
  20 edits, no error/scope violation, CLI/dispatcher0. Product authorities align
  to1.3.5;1.3.4 joins legacy runtime/producer lists, all older entries/guards stay.
-15 of17 allowed version-test files at988765589ab0368b69d4a5a4a9d5c9b8a49e2d2c;
  180 native calls,45 edits, no error/scope violation, CLI/dispatcher0. Historical
 1.3.4 publication tests remain unchanged where correct; new legacy coverage is
  added and future-version refusal moves to1.3.6. No assertions are weakened.
-10 documentation/anchor files at75c911429ddf84a3a8f326d9092be487ab3b861a;
  103 native calls,34 edits, no error/scope violation, CLI/dispatcher0. Current
  setup anchors bind canonical1.3.5 utility/policy bytes. SDK remains0.46.0 and
  normal flash100kHz; dependency/schema/template/timeout/hardware contracts stay.
-Normal content-review rounds under the approved delivery workflow fixed
  'only published release' versus current Latest, made candidate-guide status
  point to maintained evidence, and separated declared producer support from
  firmware evidence. Three-file round:16 calls/8 edits; final one-file wording
  round:7 calls/2 edits. Both native invocations completed normally with zero
  errors/scope violations, CLI/dispatcher0. A coordinator brief had accidentally
  joined article 'a' to1.3.4; the final one-file correction removes that typo.
  These normal review corrections retried no failed/denied native operation;
  the two original stopped calls below remain NOT_ACCEPTED.

All five edit inventories matched exactly Read/Edit/Write/Glob/Grep and made no
inventory calls. Edit completion and tests are separate: **zero product tests
have executed in this closeout so far**. Next is the frozen26-group offline
integration matrix and independent risk verification, followed by source-bound
native coverage reconciliation against the explicit v1.3.4 ratios. Final candidate
freeze, two canonical builds and official bundle verification remain pending.

Direct CPython3.12.14 and SDK347 source pins passed offline environment admission;
coverage7.17.0, pytest8.4.2 and existing win32 paths are available. No SDK/Toolkit
was imported by that environment probe, and no hardware or runtime installation
occurred. The fresh62-wheel input copy is prepared but not officially validated
as a package. A fresh unauthenticated GitHub API GET confirms public Latestv1.3.4,
release426198381; no remote mutation. Detailed native logs/tasks and source/input
pins remain in D:/codex-tmp/r135. No installed runtime, original firmware or
hardware changed; no push/publication. ABI/CCM work remains outside this scope.

## Earlier stopped-entry checkpoint (retained)

2026-10-30 status: **ENTRY_REDESIGN_PENDING_AUTHORIZATION / NOT_IMPLEMENTED**.
Accepted base:946b1ec5c0dd3c79bb5b5e73ce1650afa5ecb432.
Specification/plan frozen at f9026a0a617b065b3a13937260f6d7c1b8e332af;
inherited product/test CodeHead remains bfa56c21fa67e53649ec0c9c15b5ab4e9b79ae4d.
Branch codex/v135-release-closeout, clean isolated v135-pyocd046-hid checkout.
Primary owns specification, orchestration, review and acceptance; local Claude
Code CLI retains the existing deepseek-v4.1-flash[1m] route and implementation
ownership. No Codex product/test implementation fallback occurred.

## Stopped version-edit calls

Both no-action inventories registered exactly Read/Edit/Write/Glob/Grep with zero
native inventory calls. Main calls ran native file tools only; no shell/test ran.

| Invocation | Native evidence and disposition |
| --- | --- |
| version-edit-once |23 native calls, zero edits/tests. Root Grep outside module-only read scope. Primary stopped its owned CLI after detecting the violation; original result retained, NOT_ACCEPTED. |
| version-edit-redelegation-once |User explicitly authorized one re-delegation with repository-wide reads and the same30 write files.19 native calls, zero edits/tests. A Read followed a tool-created spill file under .claude/projects outside the repository. Primary stopped the owned CLI on detection; original result retained, NOT_ACCEPTED. |

Both owned CLI processes ended4294967295, dispatcher1; termination was by Primary,
so the dispatcher's own stopped=false field is not evidence of normal completion.
Owned-process identity was matched to exact dispatch task/parent/image before stop;
other sessions were not stopped. No retrospective scope expansion or automatic
retry. The authorized one re-delegation is consumed. Product metadata still1.3.4;
integration tests, current coverage comparison and package builds have not run.

## Concrete preparation and remaining gates

The rewritten entry splits13 core files and17 version-test files. Prepared tasks
bound Read to<=160 lines and exact-file Grep to<=30 lines; outside-cwd spill-file
reads are forbidden. Explicit bounded authorization is still required before launch.
After those edits: canonical setup trust anchors and current documentation via a
dependent Claude edit; Primary full-diff review; delegated offline integration;
native source-bound coverage >=v1.3.4; candidate freeze/double build/bundle verifier.

An external fresh closed wheelhouse is prepared with62 distributions: retained
offline wheels plus the already verified official pyOCD0.46.0 wheel, replacing
0.45.1 only in the new copy. No network or installation; old wheelhouse unchanged.
The first pure metadata scan included nested vendored METADATA and failed before
destination creation. Original script/failure retained; corrected root-only
metadata scan passed. This is input preparation, not official closure/license/
platform validation or a package-build PASS.

User-approved1.3.5 coverage non-regression comparison remains pending; permanent
gates are separately retained. Existing one-shot100kHz physical PASS remains scoped
to its recorded candidate/source/SDK/original pair. No new hardware, installed
runtime replacement, original firmware edits, package installation or remote action.
Firmware ABI/CCM diagnostics are outside this closeout scope and remain unchanged.

Evidence root:D:/codex-tmp/r135. Includes both tasks/raw native streams/analyses,
prepared redesigned tasks, wheelhouse-preparation.json, retained failed input scan
and fresh wheelhouse. This checkpoint is neither software nor release acceptance.
