# v1.0.1 candidate acceptance and release qualification

2026-10-10. Primary-agent verdict: **A/B/C/D/E implementation ACCEPTED; package verification PASS;
release NOT QUALIFIED**. Coverage gates remain unmet, final-package installation/upgrade is unexecuted,
and current physical evidence is pending. This is not `SOFTWARE_COMPLETE_HARDWARE_PENDING`, because
not all software release gates passed. No coverage exception is inferred from v1.0.0.

Follow-up authorization, 2026-10-10: the user approved pushing the candidate and a new v1.0.1
coverage exception conditional on coverage being no lower than v1.0.0. The first measured Toolkit
and UI aggregate fractions below do not yet satisfy that condition. A bounded supplementary
measurement is being prepared under the exact comparison rules in
[release qualification](../../../testing/release-qualification.md). Original results remain historical
facts, and no new installation or hardware action is authorized by this coverage decision.

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

## Numerical qualification

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

New final-package installation/upgrade is **UNEXECUTED**. The passed 1.0.0 upgrade fixtures do not
replace it. A concrete pending execution card is prepared at
`D:\codex-tmp\tk101\delivery\runtime-validation-card.md`, limited to a new `install-check` root.
It requires installation authorization before execution; user runtimes remain untouched.

Current physical qualification is **PENDING**. Firmware identity, linker and hardware/debug code
changed, so historical F429ZGTx/CMSIS-DAP evidence is not transferred wholesale. Historical normal
attach/flash did not pass, under-reset and IDE handoff did; no current physical TestRun or timing/pin
measurement is claimed. Retention, resource-release and rollback limitations remain in
[release status](../../../release-status.md). Further hardware work needs a filled standard execution
card and specific authorization, not an automatic retry of the original report.

The primary agent has prepared PR text and release-note drafts locally. The user's follow-up answers
the preceding explicit push / PR creation / master merge confirmation; that delivery chain proceeds
after the coverage condition is verified. Tag and release retain their separate authorization boundary.
Publication still needs the remaining required evidence and a specific release decision; the new
conditional coverage exception must first satisfy its no-regression condition.

## Evidence retention and cleanup

Primary owns cleanup. The first cleanup removed 76 exact disposable directories, including test
junctions removed non-recursively after verifying their targets stayed inside the owning fixture.
Run command logs, raw coverage and source bindings, final assets and minimum failure evidence remain.
Final q/p/dr cleanup removed a further 38 exact paths after preflight, including eight internal test
junctions removed non-recursively. `cleanup-final-candidates.json` and `cleanup-final-result.json`
under the task root record every path; all 38 removals succeeded. The 13 final artifacts, old failing
SBOM, raw coverage, source bindings and logs remain. Isolated source worktrees remain for delivery.

Automatic approval rejected A/ar cleanup and D's three new SBOM fixture directories with only
`blocked by policy`; commands did not execute. No other tool or agent retried those deletions.
Retained paths are `a-run/{cache,cache-a,cache-b,cache-5,t,t2,t3a,t3b,t4a,t5,temp}`,
`ar-run/{t,t2,temp,j,outside}`, A source-generated pyc/cache directories, and
`d-run/{pytest-sbom-red,pytest-sbom-green,pytest-release-sbom-head}` under `D:\codex-tmp\tk101`.
The original dirty workspace and shared dependencies were preserved.

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
