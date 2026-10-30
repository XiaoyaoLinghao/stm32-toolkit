# v1.3.5 local closeout checkpoint

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
