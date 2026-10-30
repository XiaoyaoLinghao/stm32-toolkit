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
