# v1.3.4 migration readiness implementation and independent review

Date: 2026-10-28. Software verdict: **ACCEPTED_WITH_FIXES**.
Release qualification: **NOT_QUALIFIED** until the concrete frozen candidate is
qualified or receives an explicit candidate-specific disposition. No v1.3.4 remote
mutation, installation, original-project edit or physical hardware operation occurred.

## Ownership and source

- Accepted base: `dc278ca226a0c1d4540657f48eb74fa1d5b361ca`.
- Reviewed CodeHead before this report: `08ff6e82931a0a4ac35cd6f020a2f9eaee67aea5`.
- Branch: `codex/v134-migration-readiness`; complete diff reviewed in the clean
  detached `v134-review` worktree at that exact CodeHead.
- Primary Codex owns the specification, bounded plans, orchestration, complete-diff
  review and acceptance. Local Claude Code CLI authored product, test and user-guide
  changes with the existing `deepseek-v4.1-flash[1m]` model/provider/authentication.
- The user authorized the fixes, regression tests, read-only project plan verification
  and subsequent v1.3.4 publication. Their bounded additional retry authorization
  was retained; no Codex implementation fallback or global permission change occurred.
- [Approved specification](../../../superpowers/specs/2026-10-27-v134-migration-readiness.md)
  and [bounded plan](../../../superpowers/plans/2026-10-27-v134-migration-readiness.md).

## Accepted behavior

`migration/constant_context.py` recognizes a structurally balanced file-level outer
include guard despite independent nested conditional groups. Only the outer open/close
are exempted from conditional depth. Nested macro/include evidence remains conditional;
outer else/elif, malformed guards, premature closure and unbalanced groups still refuse.
Existing duplicate guard, undefinition, redefinition and contained-read checks remain.

The new read-only `migration/header_encoding.py` inventories potential project-contained
headers from the selected C/C++ sources through literal ASCII quoted includes, including
transitive headers behind invalid UTF-8 source/header bytes. It shares the existing raw
contained resolver; semantic parsing remains strict UTF-8. Stable deduplication, cycles,
splices/comments/strings, path/refusal handling and finite read/lookup/depth/directory/
diagnostic budgets have regressions. Every successful raw read, including repeated
references, is charged. An exceeded byte budget stops after at most one bounded file.

Preflight exposes `analysis.encodingDiscovery` and appends one
`ARMCC_HEADER_ENCODING_UNSUPPORTED` needs-user-input blocker per known bad header.
Its totals/readiness use the combined list. Missing optional, dynamic, non-ASCII,
unsupported or limited discovery edges explicitly set `complete=false`; they do not
create new semantic blockers. Selected/excluded paths and angle/system-header boundaries
remain intact. The authoritative PLAN retains its strict/lazy semantic contract.
No implicit transcoding, new macro option, align relaxation, ABI/debug inference change,
installation or hardware behavior was added.

Toolkit, Monitor, UI metadata, plugin, launchers, setup and release identities are 1.3.4.
1.3.3 was added to legacy runtime/producer inputs while older supported inputs, future/
downgrade/source-conflict refusals and schema/template versions remain. Setup utility/
policy pins match canonical Git blobs. The public inventory remains 52 tools / 9 skills.

## Evidence and execution

Raw evidence root: `D:/codex-tmp/r134`. Each bound run records the actual head/argv,
tracked source hashes, actual subprocess exit, source immutability and fresh JUnit.
Native PowerShell numeric exits remain null where absent; they are distinct from the
wrapper's actual subprocess exit. File edits, test startup, completion and passing are
recorded separately. Only actual matched native events count.

| Bound run | Scope | Result |
| --- | --- | --- |
| encoding-first | New guard/header regressions | 30 passed |
| constants-full | Existing constant/ARMCC refusal boundaries | 68 passed |
| preflight-first | Existing preflight/diagnostics | 39 passed |
| migration-plan-full | Complete migration plan file | 98 passed |
| j | Both real-GCC independent-delivery journeys, managed simulated flash | 14 passed |
| vg | Generation/startup versions and legacy producers | 342 passed |
| vb | Complete build runner/version file | 100 passed |
| mf | Final metadata/inventory/release contracts | 78 passed |
| vc | CLI/MCP | 66 passed |
| mo | Six affected Monitor files | 288 passed |
| gf | AI/VS Code/IDE guidance | 93 passed / 1 platform skip |
| sa | Setup upgrade/repair/promotion | 17 passed, coordinator reconciled |
| sb | Other setup cases before final documentation correction | 29 passed / 1 failed |
| sd | Corrected setup documentation node | 1 passed |
| ir | Primary independent guard/header rerun | 30 passed, overlapping |

The affected matrix accounts for **1,263 passed / 1 platform skip**, after the one
setup-documentation correction. This uses exact unchanged code/test evidence across
recorded heads, not a single final-head full-repository or full-setup rerun. The primary
30-case rerun and repeated metadata checks are not added twice. The 46 passing setup
behavior nodes remain separate from the corrected documentation node; their helpers,
fixtures and assertions did not change in that final one-line correction.

The `sa` worker received a genuine structured pending result, then the stream emitted a
second identical init inventory/session. The dispatcher rejected that invocation
(`multiple_init_events`); this rejection is retained. Both actual inventories were
PowerShell with the original model. The primary reconciled the already-started exact
command from its bound exit-0, 17-case JUnit and unchanged-source evidence, without
rerunning, polling through the worker, widening tools or changing its rejected status.

Earlier API-400/abnormal edit invocations and read-scope violations remain unaccepted as
invocations, including cases with retained native edits. All final changes were separately
reviewed and verified; an implementation claim or CLI exit did not approve a diff.
Review corrections through Claude fixed read accounting/unsupported include semantics,
stale version fixtures, weakened/current documentation contracts and inaccurate prose.

Original failures remain: the first 14-case GCC journey had 13 passes / one staging
failure; the explicitly bounded same-source short-root comparison passed all 14. The
nested original path was longer, but the original error exposed no OS errno, so path
length is a supported hypothesis, not proven cause. The original setup fixture matrix
had 13 failures / 3 passes, then the current-version fixtures were corrected. Original
guidance and setup-documentation assertion failures are preserved separately from their
passing corrected checks. No product threshold was relaxed.

## Supplied project verification

Primary public-CLI captures `final-original` and `final-prepared` ran at
`e02d63605bccc1011712b1e458725c51ee51ab79`. All migration/CLI library source and its
version metadata are identical at the reviewed CodeHead; later runtime changes only
correct setup trust pins, which these direct read-only CLI calls do not invoke.

- Original `D:/WorkSpace/mobile-robot-controller`: preflight now lists 36 non-UTF-8 C
  files plus **24 reachable non-UTF-8 headers**, 60 encoding blockers. The tree has
  26 bad headers overall; `SAFE_APP/safe_app.h` and `USER/usart8/usart8.h` belong to
  excluded paths and are correctly outside this dependency inventory.
- Existing UTF-8 copy `D:/WorkSpace/mobile-robot-controller-v132-test`: its original
  include guard remains intact. With the saved explicit WFI, startup, memory-layout
  and extra-region choices, preflight has **0 blockers / planReady=true** and the
  destination dry-run PLAN succeeds with **191 outputs** (175 copied / 3 replaced /
  13 generated) and 5 source/manifest patch entries.
- Discovery remains explicitly incomplete for unresolved quoted standard-library names
  (50 diagnostics on the prepared copy); this is not an exhaustive-header claim and
  does not add a false semantic blocker. The original inventory found 77 dependency
  headers, 130 distinct files and charged 27,637,085 raw read bytes.
- Complete before/after project hashes match; destination remains absent. No apply,
  configure, actual-project build or flash was performed. FPU hard/unverified and
  empty debug metadata remain outside this correction's scope.

## Coverage and release boundary

`coverage-v134/qualification.json` combines native branch data only for exact current
source bytes. Old arcs for changed source are removed; every Python source stays in the
overall denominator. The new advisory preflight inventory was assigned overall-only
responsibility before measurement (`risk-scope-decision.json`, 2026-10-27); contained-read
safety remains in existing risk-core `constant_context.py`. No existing risk member or
threshold was removed. Failed/empty setup coverage datasets were not imported as passes.

| Scope | Native fraction | Percent | Permanent floor | Result |
| --- | --- | ---: | ---: | --- |
| Toolkit overall | 15336 / 18534 | 82.7452% | 90% | UNMET |
| Toolkit risk-core-v2 | 14208 / 17194 | 82.6335% | 90% | UNMET |
| Monitor overall | 3292 / 3564 | 92.3681% | 90% | PASS |
| Monitor risk-core-v2 | 3292 / 3564 | 92.3681% | 95% | UNMET |
| UI aggregate | 2938 / 3147 | 93.3588% | 90% plus per-file 90% | PASS, reused |

UI source/tests/configuration and tracked dist match the accepted v1.3.3 evidence;
only package/lock root versions changed. `ui-reuse.json` binds the retained 534 passing
UI cases / one platform skip, native coverage and per-file gate; no fresh UI/browser
execution is claimed. Unchanged Monitor performance evidence retains the original
124.9428 ms p95 failure and later passing controlled 19.5793 ms comparison separately;
there is no new benchmark PASS or erased failure. Existing platform/historical-data
skips and synthetic external CubeMX adapter limits remain. Actual vendor generation,
physical acceptance and final recipient installation/VS Code have no new PASS; final
installation/VS Code remains **USER_VALIDATION_PENDING**, owned by the user.

The user authorized release publication after review; permanent gates remain unmet and
v1.3.3's one-time exception does not transfer. Next: freeze this reviewed software with
its evidence, build twice in clean canonical trees, verify all 13 files and the extracted
bundle, then seek disposition only for that concrete candidate. No publication yet.
