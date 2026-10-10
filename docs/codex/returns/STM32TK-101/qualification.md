# v1.0.1 candidate acceptance and release qualification

2026-10-10. Primary-agent verdict: **A/B/C/D/E implementation ACCEPTED; package verification PASS;
user-authorized coverage exception ACCEPTED with its no-regression condition verified**.
Permanent numerical gates are unchanged and remain numerically unmet where stated below.
Final-package installation/upgrade and the bounded current physical scenarios passed. The first
Target attempt remains a retained failure with unresolved cause; the later fresh successful run
does not erase it. Release qualification is accepted within the scope and limitations below.

The user explicitly approved the v1.0.1 exception on condition that coverage is no lower than v1.0.0.
Supplementary current native measurement now satisfies that condition in every recorded scope under
[release qualification](../../../testing/release-qualification.md). This is a new user decision, not
automatic inheritance of v1.0.0's exception. Original measurements remain intact below.

## Identity, ownership and review

- Accepted remote base: `694c825d29a55a53052a148efa4cc6720c315a04`.
- Frozen artifact source: `0f06c659f5e04aa1f8e53022eae9b5e964da2b4b`.
- Final D product correction: `c75adb430fa1f03cc0dc5a4a9e7f519838978664`.
- Python/UI measurement source: `3d0a8568d6dcaa08d11745e091944e46480c28f7`.
- Integration branch: `codex/v1.0.1-integration`, local `D:\codex-tmp\tk101\w`.
- Implementers: one bounded owner per A/B/C/D/E; every subagent used gpt-6-sol / max.
  The primary agent owned specification, orchestration, complete-diff review, integration and acceptance;
  it did not implement product code. Package and qualification agents independently verified results.
- Each slice's full diff was reviewed at its recorded CodeHead. `review_b` independently reviewed all
  surviving product Python, linker, UI/generated assets and launchers from the accepted remote base to
  the measurement source. The primary agent reviewed every later documentation, cache and SBOM change.
  No unresolved product finding remains within the approved patch scope.

Later report-only commits are not the source of the already-built artifacts. Any future tag or release
must identify the exact artifact source above, or rebuild and revalidate a newly selected source.
GitHub master, tags, releases and existing assets were unchanged at this original acceptance checkpoint.
The authorized follow-up pushed branch `codex/v1.0.1-integration` at
`62a490fe194da9c96aa07a75cc970f62a0e39eea`; subsequent delivery is recorded in the execution ledger.

## Completed user behavior

All 22 report items have an explicit disposition in [issue triage](issue-triage.md).
Safe nested Keil discovery, user editor-file preservation, ELF NOBITS accounting and both linker
templates were corrected. Diagnostics now distinguish historical baseline artifacts, Git changes,
SVD bounds, firmware provenance, unsupported targets and unverified post-flash running state.
Doctor and setup Check do not launch GUI tools. Monitor recovery guidance preserves token and Host
protections. Toolkit, Monitor, plugin, UI and managed runtime version entries are 1.0.1;
1.0.0 upgrade and older project-producer identities retain their controlled compatibility paths.

The current candidate tree removes 417 obsolete historical files and completes the bilingual README,
user guide and eight official skills. Full Git history and v1.0.0 artifacts remain intact.
This cleanup is local until an authorized merge updates master. Offline fixtures do not reproduce
the original report's board behavior or establish its original ELF/MAP numbers.

## Software evidence

| Owner and scope | Result | Applicability |
| --- | --- | --- |
| Slice implementers and primary independent checks | Accepted A/B/C/D/E; exact runs in [execution](execution.md) and C/D/E reports | Changed behavior, refusal paths, ownership, rollback and regressions |
| verify_qualification, 22 existing Toolkit test modules | 1709 passed, 1 skipped, 2 warnings; exit 0; 1348.33 s | Native coverage.py 7.15.4 with subprocess collection, Windows CPython 3.12.10 |
| verify_qualification, complete UI V8 run | 33 files, 269 tests passed; test:coverage and coverage:check exit 0 | 25 positive-denominator source files each meet 90%; four zero-denominator files N/A |
| implement_d, final release suite | 45 passed at final D product correction | Submitted Git archive and trusted bootstrap hashes included |
| Primary, final SBOM/archive correction | 2 passed, 43 deselected; exit 0 | Independent clean worktree, exact corrected source |

The Python skip is the unavailable directory-symlink capability on this Windows test account
(PLATFORM), not a passing check. The two retained warnings concern Pydantic lifespan annotation and
the CLI runpy module being preloaded. The raw terminal result is retained unchanged.

`q-run/artifact-applicability.json` verifies identical Toolkit source, Monitor source and complete UI
Git trees, plus identical blobs for all 22 selected tests, between measurement and artifact sources.
Release-builder changes have their own current tests and the two actual builds below.

## Initial numerical measurement

Native branch numerators and denominators are summed without changing membership or excluding files.
Of 126 Python source files, the 20 changed files use current passing-run native summaries; 106 unchanged
Git blobs reuse the old accepted U64 per-file native summaries. Old arcs are not applied to changed
source. This is explicitly reconciled evidence, not a claim that a new full Python suite was run.

| Permanent gate | Covered / total branches | Result |
| --- | --- | --- |
| Toolkit overall, 90% | 11892 / 13674 = 86.968% | UNMET |
| Toolkit risk-core-v2, 90% | 11262 / 12988 = 86.711% | UNMET |
| Monitor overall, 90% | 2770 / 2956 = 93.708% | PASS |
| Monitor risk-core-v2, 95% | 2770 / 2956 = 93.708% | UNMET |
| UI, 90% for every positive-denominator source file | 794 / 822 = 96.594% aggregate; all 25 files meet gate | PASS |

Broad-core-v1 is separately retained: Toolkit 11892/13674 and Monitor 2770/2956 are both below their
original 95% target. Toolkit core95 is a later target, not an added current gate.
The bounded current test selection covers fewer CLI/MCP branches than the older full suite, so the
lower Toolkit aggregate is not itself evidence of a product regression. Numerical UNMET is classified
as REPORT / release qualification evidence; it remains an unmet permanent release gate. At this
initial measurement checkpoint no threshold exception had been authorized. The subsequent user decision
adds the explicit no-regression condition above; membership changes and unbounded coverage pursuit remain excluded.

## Accepted supplementary coverage evidence

The frozen extra 17 existing Toolkit modules passed: **381 passed, 1 skipped, 1 warning**, exit 0,
324.09 seconds. The original 22-module run was not repeated. Both runs used the same current source
blobs and native branch/subprocess configuration; copied native databases were combined only under
`q2-run/combiner` using coverage.py 7.15.4 `combine --keep` and `json --keep-combined` (both exit 0).
The 20 changed Python files use the resulting complete native per-file summaries; the 106 unchanged
files retain the source-bound U64 summaries. No old-version arcs were imported onto changed source.

UI implementation owner `ui_coverage` added only two tests and strengthened an existing asynchronous
import assertion, committed as `d402e8505ccb46616a2188fabb022edfc64c76b5` and integrated at
`ec7c6b5f9f97404928ba4a496020f7bc63236879`. Public behavior now tested includes a valid HTTP 200
failure envelope without exposing private fields, clearing file input after import, and completing
a real FileReader after component unmount without publishing an import or rebuilding the UI.
No product, dependency, configuration, coverage-membership or generated-asset file changed.

The final UI run passed **271 tests in 33 files**, plus coverage:check and typecheck (all exit 0).
The primary agent reviewed the complete two-file diff in a clean isolated tree and independently
ran both affected modules at the returned commit: **36 passed**, exit 0, 3.91 seconds.
The existing jsdom export-navigation notice is retained in that passing log; no browser or hardware
execution is inferred. The primary also independently checked every Python row's source blob and
native summary, all scope sums, exact fraction comparisons and all UI source-file branch counts.

| Scope | Published v1.0.0 | Current v1.0.1 | Exact no-regression result |
| --- | --- | --- | --- |
| Toolkit overall / broad-core-v1 | 12047/13592 = 88.6330% | 12124/13674 = 88.6646% | PASS |
| Toolkit risk-core-v2 | 11429/12918 = 88.4734% | 11494/12988 = 88.4971% | PASS |
| Monitor overall / broad-core-v1 / risk-core-v2 | 2770/2956 = 93.7077% | 2770/2956 = 93.7077% | PASS, unchanged source |
| UI aggregate | 784/810 = 96.7901% | 796/822 = 96.8370% | PASS |

All 25 positive-denominator UI source files still meet 90%; four remain N/A. Exact fractions, not
rounded percentages, decide acceptance. Toolkit's permanent overall90/risk90 and Monitor core95
remain numerically UNMET; only this user's conditional v1.0.1 exception changes their admission.

An intermediate complete UI run passed 270 tests but measured 795/822, so it did not meet the new
condition. The initial read-only analysis had misidentified the missing direction of GroupPanel's
file-ref guard (REPORT); the real V8 `[5,0]` showed the unmount/false branch was missing. The bounded
unmount scenario produced `[5,1]`; the earlier evidence remains under `u2-run/evidence/first`.

Retained audit records under `D:\codex-tmp\tk101`:

| Record | SHA256 |
| --- | --- |
| q2-run/python-qualification-combined.json | `81876cc562c73381fa480c04310b48e9a1ce235861658948cc2f5025b96b81f5` |
| q2-run/combiner/coverage-combined.json | `fbd5c3990291b0f08fe2871ecae9931b29b8d405a2b4bc32e09f4e52e3db85e4` |
| u2-run/evidence/coverage-final.json | `0db6356643526f31def1a560a9064c8d55ae9b46f539ef1ace24b6f273f9d8f0` |

Exact commands/exits and raw data are in `q2-run/py`, `q2-run/combiner`, `u2-run/evidence` and
`ur2-run`. The supplementary checks do not change the frozen artifact source or replace final-package
installation, remaining rollback/platform evidence or physical qualification.

## Reproducible artifacts

`verify_packages` built clean detached worktrees p3 and p4 from the frozen artifact source.
Both builds exited 0; all 13 output names, sizes and SHA256 values match. An independently extracted
Windows bundle passed its own `verify-bundle --json` with the expected source commit.
Additional checks passed: 12 external checksums, 64 wheel METADATA/version records, 62 runtime pins,
two product wheels, seven UI assets, licenses, bootstrap hashes and 525 exact SBOM relationships.
The read-only input wheelhouse's 64 hashes were unchanged; both worktrees remained clean.

The first candidate's SBOM declared `SPDXRef-DOCUMENT` but referenced `SPDXRef-Document`.
This was a PRODUCT defect, despite matching first-round builds. D corrected the shared ID, extended
the existing test, and updated the bootstrap anchor. The first candidate is not counted as a package
PASS; its original failing SBOM and failure result are retained separately.

Final assets are under `D:\codex-tmp\tk101\p-run\r2\artifacts1`:

| Artifact | SHA256 |
| --- | --- |
| stm32-toolkit-1.0.1-windows-x86_64.zip | `ed51a0e9773acc26010bfadae595fddbf99ba298080784a3d600509d861f1f8b` |
| stm32-toolkit-1.0.1-source.zip | `8c8accdb1001b24b04d76f9d1da3b0834ddffc4796a2ea9f87d47e84d61db873` |
| release-manifest.json | `41fed947caad802f0ea1d7932650e67e3a2f7ab6f831048829d718dc69161a11` |
| sbom.spdx.json | `591c0146613b6893d6cb91d59e4d56e6014c1a1e000727e72aa060e7fe854d15` |
| CHECKSUMS.sha256 | `fd0731e69cc2966cbd254de14ac15ee394d1d05a8a817b537913982920762844` |

The builder SHA256 is `641f58a01c1dad4b17d4a4d4df720e82544faf2a2ee8480bcf6f997155bc155b`;
the policy SHA256 is `980b6f34baca0d025768eba349612f85b8053763cbeb2e267433697afc639bf4`.
All 13 output hashes and exact commands/exits are retained in `p-run/r2/artifact-hashes.json` and
`p-run/r2/logs`. A reproducible, structurally valid package does not establish installation or hardware acceptance.

## External evidence and delivery boundaries

Seven historical native Windows symlink checks may be reused only for their unchanged guards and
test blobs. Their actual owner was the user's elevated Windows run at source
`968cbb69b1f54b95a8fdc18a550481f6ff7c1268`; result 7 passed / 0 skipped / exit 0. They were not rerun
here and add no current coverage credit. The primary admission JSON is retained at
`D:\codex-tmp\v10b-0918\r10\e\python-final\windows-symlinks-rc4-current\primary-admission.json`,
SHA256 `20fd168e637bbb08d149cc0ecb233951cb44a86cbe83363708534cb4a922cdc1`.

Final-package installation/upgrade is **PASS**, executed by verify_packages and independently
reviewed by implement_e. All 21 recorded steps exited zero. Fresh Check/Bootstrap/Check produced
healthy 1.0.1 generation 1. The separate published-1.0.0 installation upgraded through Repair to
healthy 1.0.1 generation 2; the old runtime was quarantined and user/project marker hashes retained.
Installed Toolkit/Monitor report 1.0.1, Python 3.12.10 and PyOCD 0.45.1; pip check passed. Installed
MonitorRuntime UI/authenticated status returned HTTP 200, missing authentication 401 and wrong Host
403; normal stop closed the listener, removed the runtime record and released the lock. This is
backend HTTP evidence, not a browser UI or CLI serve/Ctrl-C lifecycle check. Complete commands,
environment, stdout/stderr and exits are under `D:\codex-tmp\tk101\install-check\logs`.

Current bounded physical qualification is **PASS with retained limitations**. The user confirmed the same STM32F429ZGTx board and
that its firmware need not be retained. A fresh isolated copy of the historical real project was
configured and built with the installed final runtime; offline whole-file SVD selection passed.
One static recovery prepare passed, then one physical Target execute failed on 2026-10-10 with
`TEST_EXECUTION_FAILED` and empty details. That action was consumed, but produced no physical TestRun or
successful flash receipt. The lease was released and worker exited; target running state
is not thereby established. Sampling and register reads stopped. Root cause remains unresolved;
offline inventory confirms the exact target is registered in the existing CMSIS pack. Raw evidence
and classification are retained under `D:\codex-tmp\tk101\h-run`, including
`h1-failure-assessment.md`. Historical hardware evidence is not relabeled as current PASS.
Retention, resource-release and rollback limitations remain in [release status](../../../release-status.md).

A separately reviewed single attach/identity diagnostic passed. A fresh Target prepare then matched
all 20 nonvolatile binding fields. Its single execute passed using a reviewed run-local wrapper that
observes the original workflow exception before delegating to its unchanged mapper; source, runtime,
timeouts and public return semantics were unchanged. Windows spawn and mapping-preservation checks
passed offline. The new physical run is `target-v2-eb5d6d9eb9b9b27a9779d70b0b77ba2a`, evidence
`8db1669e95f6cd789d3b9c54aa019978b5e84d3624f793430df29410973d17e6`; authoritative show agrees.
The flash receipt verifies 7812 bytes. The physical case passed with `timer-and-pe3`, 2200 ms,
one passed/zero failed. Test manifest SHA256 is
`d7279b948654955de49e2b93b5470ad4ecaab8ea39b208a97daf9e3186de2576`.

One variable read returned testtime=13728. One 1000 ms/eight-slot sample delivered three valid
increasing values 17891, 18171 and 18431 at indices 0, 2 and 5, satisfying the predeclared minimum
of two increasing values. Five slots were dropped, seven deadlines missed and actual rate was
0.372 Hz; no top-up sampling or sustained-1-Hz claim. One SVD register read returned GPIOE.ODR=16
(`0x00000010`, 32 bits). Its address/width association comes from offline full-file selection and
the unchanged SVD hash, not additional fields in the public register response. All observations
share the current build/ELF/input/session binding; leases released and final owned process count zero.
verify_qualification executed these checks; hardware_preflight and the primary independently
reviewed raw evidence. Exact commands, native responses and scope are in
`D:\codex-tmp\tk101\h-run\h1b\final-assessment.md` and its referenced files. No new physical
claim covers generated linker aliases, IDE handoff, full Fault, visual LED or external waveforms.

PR #16 merged at `0b3e3bbf9fa4dcb11dac647faed2dfec86a3bac5`. The user subsequently authorized
physical verification followed by v1.0.1 tag/Release publication. The required bounded physical
acceptance is now complete. [v1.0.1](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.0.1)
was published as Latest at 2026-10-10 11:03:42 UTC. The annotated tag
`080cec43a36401f1bf8824e779d423c0e8e54a36` resolves to the exact
frozen artifact source above; later master changes contain documentation and two UI tests, with
no changed product, dependency, configuration or generated distribution bytes.

All 13 uploaded assets were independently verified after download: exact name set, ordinary files,
size and SHA256 match the local double-build list and GitHub's uploaded digests. The downloaded
manifest source/archive identity matches. The raw audit is
`D:\codex-tmp\tk101\delivery\post-upload-verification.json`, SHA256
`596ee2410dacded4f8eb30813fc12fa6c17b51a3b64680b610823667a7fe3adb`.
Primary confirmed the remote peeled tag, published/non-prerelease status and Latest selection.
The v1.0.0 asset names, IDs, URLs, sizes and digests, publication time and target remain unchanged.

## Evidence retention and cleanup

Primary owns cleanup. The first cleanup removed 76 exact disposable directories, including test
junctions removed non-recursively after verifying their targets stayed inside the owning fixture.
Run command logs, raw coverage and source bindings, final assets and minimum failure evidence remain.
Final q/p/dr cleanup removed a further 38 exact paths after preflight, including eight internal test
junctions removed non-recursively. `cleanup-final-candidates.json` and `cleanup-final-result.json`
under the task root record every path; all 38 removals succeeded. The 13 final artifacts, old failing
SBOM, raw coverage, source bindings and logs remain. Isolated source worktrees remain for delivery.
After the follow-up checks, eight additional q2/u2/ur2 disposable directories were preflighted and
removed successfully; exact paths/results are in `cleanup-followup-candidates.json` and
`cleanup-followup-result.json`. Supplementary raw coverage, command logs and both UI runs remain.

Automatic approval rejected A/ar cleanup and D's three new SBOM fixture directories with only
`blocked by policy`; commands did not execute. No other tool or agent retried those deletions.
Retained paths are `a-run/{cache,cache-a,cache-b,cache-5,t,t2,t3a,t3b,t4a,t5,temp}`,
`ar-run/{t,t2,temp,j,outside}`, A source-generated pyc/cache directories, and
`d-run/{pytest-sbom-red,pytest-sbom-green,pytest-release-sbom-head}` under `D:\codex-tmp\tk101`.
The original dirty workspace and shared dependencies were preserved.

After physical and post-upload acceptance, primary cleaned 19 exact run-owned installation,
upgrade, extracted-bundle, cache/temp and download-copy directories. Preflight verified task-root
containment and no ancestor/descendant reparse points; all 19 removals succeeded. Raw runtime-state
copies, marker hashes, commands/results, original H1 failure, subsequent physical evidence, current
real project/ELF/map and the frozen 13 local assets remain. The isolated installed runtimes used for
testing were removed; these records do not describe an upgrade of the user's ordinary runtime.
Exact paths/results are in `delivery/cleanup-release-candidates.json` and
`delivery/cleanup-release-result.json`. Earlier refused cleanup targets were not retried.

Evidence checksums:

| Record under D:\codex-tmp\tk101 | SHA256 |
| --- | --- |
| q-run/python-qualification.json | `df541b8ab7060e070239aded8b45aa9d50cfd7c30a2736270a9a02ae2540c846` |
| q-run/py/coverage-current.json | `e63947148e45ab6342649d53792262006ac02c787be7a5deee06617a57fa163d` |
| q-run/py/.coverage | `d818c0b0294285e3c9d4764efe89d5634afc8db67b6cfa397dbb207529eb2cba` |
| q-run/ui/coverage-final.json | `e23114019d5b3f4ee132b92c02eb1bb4f011c946f4c3809cddf5333bd55cf117` |

The executable evidence entries are `q-run/py/run-python.ps1` and `q-run/ui/run-ui.ps1`;
their logs, exit files and native per-file records are retained. These machine-local paths are
audit provenance, not installation instructions for another computer.
