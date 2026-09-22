# Current native coverage result

## Current U41 and frozen RC2 result

Integrated test/code head before this report:
`cb13aed97c3e43386b5e31bff95eb3f73e8c1c73`.
Frozen RC2 source (unchanged by the subsequent test-only work):
`c71b13f2562985d27b3865e367f6d33334f3a16a`.
Product source remains `55d91a23a5a2f16fc47d324a9077dfcebf130be9`.
U41 is **ACCEPTED_NATIVE_DATA**; release1.0 remains **NOT_ACCEPTED**.
Canonical SHA256:
`DFF61BC35FE8461958FED752249E3ECE4F2D6424C8CBAB20935B56D8886F0685`.
Independent review:
`0DDBFDAFB363563CE8DBDB971E7375084A106374E4660471B9A6296408C1D4A6`.
Primary admission:
`510552A5BE563CE333ED0EB5E6C2765BF0F05F8DE2DB9C30BE4B0398A8B13E1B`.

| Package / frozen scope | Covered / total branches | Branch ratio | Remaining gate |
| --- | ---: | ---: | ---: |
| Toolkit overall / broad-core-v1 | 11,821 / 13,592 | 86.9703% | 412 for overall90%; broad-v1 retains1,092 for95% |
| Toolkit risk-core-v2 | 11,203 / 12,918 | 86.7240% | 1,070 for95% |
| Monitor overall / broad-v1 / risk-v2 | 2,725 / 2,944 | 92.5611% | overall90% met;72 for95% |
| UI, retained separately | 784 / 810 | 96.7901% | retained gate met |

Current batch closes all six scoped RC2 refusal/restoration cases and the
harmless native Ctrl+C facility. The real shipped Monitor service/authentication/
Ctrl+C/resource-reuse package gate, coverage thresholds and seven Windows checks
remain incomplete. No product source or frozen RC2 artifact changed.

### Current finite batch: entry preparation, no new measurement

The S18 physical checkpoint retry candidate44388c9a2487d1626e5486e6c5afb8c004386453
adds one test file in its isolated worktree. Its first launcher stopped before
pytest because it read an absent sourceCommitAuthority property; the existing
source-binding document already uses productSourceRevision. Original failure
153EAF55DE6E054BED77B1333DE2901921A0A745B7BDAF37670AA8DC88C74489 is preserved.
The same owner corrected the launcher field contract; source binding and test
bytes are unchanged. Correction15BB14D042EEB01ED23D085206B6508482E63F0E03DDF646E78C61EB484CEAE8
records the static checks. Complete independent review0AF6B79972A7BFC3769FCB265928B436AC00FC938014CCF76F63F6EAD13BF8AA
returns REVISION_REQUIRED: the manual fixture does not match the Keil scenario,
its declared Src/main.c does not match the test's App/main.c, the intent uses
an aggregate hash instead of the per-file hash, and post-processing lies outside
the stated overall600s budget. These are fixture/collector failures, not product
defects. Plan cb13aed9 consolidates all four plus the stale coverage-policy
comment into one correction with the same owner and permits one first actual
offline suite after static validation. The approved backend seam creates no
ProbeBackendWorker; actual thread/subprocess collection remains mandatory,
without fabricating a worker shard. No pytest process, child shard or native
increment exists for the rejected candidate; eleven remains a static estimate.

Plan51120ae consolidates the actual shipped Monitor adapter around one native
suspended package launch. Independent inspection identified duplicate data-root
creation, a sessions-directory/workspace-ID comparison error, and incomplete
deadline/process/output ownership in the prior adapter. These are test-facility
defects, not evidence of product failure. The same implementation owner prepares
the fixed entry while the real service attempt remains held for complete review.
Preserve the accepted harmless capabilityA32B9859; do not rerun it or relabel it
as package-service acceptance. Product ready output contains a bearer URL and
must remain in bounded memory. Package/authentication/Ctrl+C130/resource reuse
requirements and the120s/15s lifecycle budget remain mandatory.

Windows capability was checked read-only again. Evidence66FA034F2C98C5C101A3291BA25D7446F7FB5E809E5C3CBB695FC57337F8EF00
still records a medium token, no enabled Developer Mode and no
SeCreateSymbolicLinkPrivilege. No setting changed, symlink was created or native
test run; the same seven exact selectors remain pending. Probe residual audit
1ADCE39F29C2F62651FE0CA4E4417D28AD75755D355C41F84DF6A26B1B446D09
establishes one public transport identity refusal/reuse family with three static
targets. Primary withholds a separate low-yield run while the current two bounded
deliverables converge. This neither excludes those branches nor declares the
other residuals unreachable.

This preparation batch adds zero accepted branches and has no actual suite
overlap. Keep the limit at two; do not claim resource or stability evidence from
parallel preparation alone. U41, all13 RC2 build comparisons, installation,
genuine0.9 Repair, rollback, all six refusal cases and historical physical PASS
remain applicable. Next exit is independently qualified S18 behavior/measurement
and one reviewed actual Monitor package attempt; neither is complete yet.


### Retained SVD and initial facility convergence evidence

The SVD supplement candidate6df8334b2196fa75f4ad6970353f5fb1797dade9 has
been independently inspected by primary in clean w17svdr and integrated as
065361b237cac294a7f87cd5358b31dd5a99188d. Only one198-line test file was
added. Both product trees remain byte-identical to frozen RC2. The public
selection scenario proves inherited register address/metadata. Four public
refusals cover depth, undeclared ancestor, missing base and address overflow,
with unchanged inputs and successful reuse after exact restoration.

Run2 completed in3.717459s, exit0, with all five observations passing. Its
retained raw hash is245FFFC2D0DE640B2313E5D0A5952EE15714AFCEE58EBA1961E86A20BC451E6D.
Independent raw/source/environment review8E60B8D39F6621EC71D2801C4081EEBB510B4A473E7F5AAB49D861BB76A10027
accepts seven unique SVD native branches, with zero loss against U40. Copied
candidate/timestamp labels are report-only: original9B443 source-binding bytes
remain preserved, while source-binding-reconciliation.json identifies the actual
candidate/run and excludes the unverifiable copied generation time. All148
source rows and actual runtime/raw bindings were independently checked. No test
was rerun. The seven accepted branches have now been included by the independently
reviewed U41 serial aggregation reported above; U40 is preserved.

The first4.915989s run failed the fixture's missing singleton-tuple comma
before the target branches. The subsequent launch-only attempt stopped before
pytest because its baseline guard incorrectly required the immediate parent.
The corrected guard binds the exact candidate and checks accepted-base ancestry.
Both failures are preserved and excluded. From scope-freeze commit d06fa95c
at05:24:07+08 to local integration at05:57:57+08, the SVD slice took33m50s;
fixture/launcher correction and review dominated its actual runtime. Do not
repeat the existing successful suite or add isolated low-yield variants.

One harmless Monitor console experiment took0.955628s. Native marker130,
CMD130, helper0, empty Job and clean settlement were observed, but the batch
termination prompt violated that capability contract. The original FAIL is
retained under settlement27DF9DF19BD024942DC3F4B6AFC19D81FCB01DDB21CFFC577EA245CC4E8B8107;
no prompt was answered and no Monitor service ran. Primary and independent
review distinguish the test-only CMD barrier from the actual product contract.
Plan083f63f3 replaces that barrier with native suspended startup; preparation
only is released to the same owner. The actual shipped command/service,
authentication, Ctrl+C130, cleanup and reuse gate remains mandatory and held.

The remaining three package refusal cases have not run. Runner9184 was
independently rejected; successor76E111 removes exception-path restoration
but still does not implement immediate process ownership or the final deadline
check. It is rejected as DESIGN_NOT_IMPLEMENTED, not a product defect. The
same owner must fulfill the complete fail-closed transition design50ecfe06;
no additional case execution or accepted-case rerun is allowed before review.
The original two failure rounds and this incomplete design implementation are
retained as one lifecycle problem. Run1's three accepted refusals remain valid.

The actual capability and SVD suites did not overlap; max concurrency stays2,
and zero-valued process peak-working-set readings remain unavailable evidence.
No build, deployment, hardware or remote action occurred in this batch. Next
scope is fixed: close the two execution facilities, independently admit the
SVD raw contribution, and establish a complete public continuation producer
path before selecting another coverage family. No mandatory gate is waived.

U40 adds23 Toolkit branches:12 recovery_workflows and11 workflows. The accepted
acceptance-reader/run3 and physical-reader/run3 contribute13 and10 respectively,
with no overlap and no Monitor increment. The complete raw union is87,200 arcs
for Toolkit and61,062 for Monitor, with no loss. One native aggregation took
8.5102s and reran no tests. Four original inputs, neutral copies, all148 source
bindings and frozen scope denominators were independently checked. Native raw
arcs are not interchangeable with the23 decision-branch increment. U39 and the
reviewed pending candidate remain preserved alongside the promoted canonical.

The original U40 candidate-stats report incorrectly labeled overall108/18 files
as broad-v1. The existing U39 updater corrected the candidate to broad97/16,
risk90/16 and overall108/18 without repeating aggregation. Toolkit38,047 broad
statements and38,105 overall statements are valid distinct scopes. The original
incorrect report remains evidence; neither denominator nor product changed.

The predecessor U39 union added267 Toolkit branches (262 recovery_workflows,1
recovery,4 build runner) and7 Monitor analysis_workflows branches. It uses the
two U38 baseline databases and three separately accepted inputs: finalization
run3, its distinct fresh-show scenario, and Monitor run2. Exact native raw
unions, original shards, all148 source bindings, frozen scopes and zero lost
prior arcs were independently verified. Aggregation took9.1569 seconds, ran no
tests and performed no purge. U38 and earlier physical evidence remain intact.

The current public-firmware journey took131.1827 seconds; separate fresh-show
took11.3621 seconds; Monitor DTO/export refusal and recovery took9.4582 seconds.
The additional v1 Recovery run passed in25.2596 seconds but yielded zero new
arcs and is excluded. Its92-arc function-cluster estimate was not a reachable
yield proof. The non-NFC Monitor scenario was withdrawn because an earlier
public canonical-input guard dominates it; its frozen denominator remains.
These actual suites did not overlap. Read-only preparation/review did overlap;
the two-suite ceiling remains unchanged because complete resource/descendant
peak measurements do not justify increasing it. No product source changed.

RC2 source/build inputs are frozen independently of remaining final coverage
and Windows gates. With one closed64-file dependency inventory and process-local
Git LF settings, two real builds took71.4094 and215.1972 seconds. All13 outputs
are byte-identical. The extracted Windows bundle passed verify-bundle; source,
wheel, manifest, licenses, SBOM and assets received independent artifact verdict
`ACCEPTED_ARTIFACT_EVIDENCE` (review SHA
`6D300296300A1DD06CFAD0C0772C958A41E8E6B8E6560DF8633FFFD4990B6008`).
Manifest SHA:
`55C296C198C9898D9C29E347E031CC21097E58D9D4DCBD0B165557E6A0FF631C`.

Real isolated Bootstrap101.4748s and Check20.6728s passed. Genuine0.9 Repair
94.3065s and subsequent Check21.0508s passed, with generation1 to2, healthy
runtime and all5775 old files byte-preserved at the returned quarantine path.
Independent installation review SHA
`BDC55AFF75CF0F1DE374ACA79FBAF09D6FDA71F43FB150F8A38A8839E210719C`
accepts that scoped evidence. A separate missing-runtime Check16.7381s returned
Bootstrap guidance without creating the data root. Installed console doctor,
shipped MCP initialize/list48tools and Monitor version1.0.0 also passed; no
matching unique MCP-session process remained after client close. These last
small public-entry checks were executed and admitted by primary.

Two post-check assertions were corrected without product changes or repeated
build/Repair: normalized ZIP metadata differs from raw Git archive metadata
while all988 source member bytes match; Repair preserves the old runtime under
its returned quarantine path rather than its former path. Original failure
records and corrections are retained under e/rc2.

The first real RC2 refusal batch ran for144.1520s, serially, and stopped at a
test oracle error after two complete state cases and the utility refusal.
Independent review
`DC3418C4FEF1B6A3F66BFB78DDD4956E42FAF6D363144C87E4F4FEC6B4FB4FC6`
accepts source-conflict and downgrade-refused for exact public classifier and
Repair refusals, unchanged data/project snapshots, exact restoration and
healthy matching generation1 Check with mutated=false. It also accepts the
utility refusal and restored public control by offline reconciliation: all70
manifest-derived basename/size entries and64 complete wheelEntries match.
The original failure remains preserved; the public wire has `files`, not an
`artifacts` array. No successful case was repeated. Recorded direct commands
exited without timeout and their PIDs are absent; complete descendant
ownership was not recorded and is not inferred from direct-PID absence.

Policy, manifest-identity and Toolkit-wheel tamper remain unexecuted. The
prepared run2 corrects both the output oracle and the false runtime detection
caused by searching Python cache mirrors by basename. Primary review holds
execution until its180s case budget, bounded process settlement and restoration
after confirmed termination are implemented coherently. This is test-facility
work; no product or RC2 artifact changed, and the combined refusal/security
gate is still incomplete. The batch contributes zero native coverage branches.

Monitor capability-v1 was statically rejected before execution. Primary full
review SHA
`682180DCD31DB1E44F88D19A568DFEDA6A61C9E0F1B057C86D08163F610F5A1B`
identifies buffered short-READY deadlock, cleanup exceptions/descendant
settlement gaps and inherited out-of-root TMPDIR. These continue the same
previously rejected lifecycle contract; round counts are not reset by naming
the script differently. No capability or actual Monitor service run occurred.
The primary returns to a smaller fixed-flow design before implementation.

The latest host Diagnostic audit stops at the public target-authority guard;
a host failed-run publication cannot legitimately reach verification start,
cancel and retry. Existing target cancellation/retry branches are covered.
The external-holder candidate adds at most one native branch plus missing
lines, and the Monitor node-limit candidate at most one branch. Neither is
released in this batch; no private-state fabrication or denominator change is
accepted. U40 and all preserved physical, build and installation evidence remain
unchanged. Preparation and review overlapped; no new suites ran concurrently,
so the two-suite ceiling remains.

The later acceptance-reader family now has independent and primary acceptance
for five persisted-authority refusals, per-call evidence/project/data no-write
checks, exact restoration and successful public reuse. Candidate
`9f003c718ba61350a258dfe4ab76f61b72eb927a` was integrated as test-only commits;
the integrated Git test blob is identical. Run3 took97.1258s (pytest94.979s),
exit0, without timeout or retry. Its13 new native branches against U39 are
accepted and **included once in U40**. Run2 and run3 have the
same combined raw SHA and contribute only once:
`639B6AC1755B4B5CDF488B5A61764247568C525948C5898D527173DAC217EAF8`.
Run3 independent review SHA:
`453342C5B567BDF8F4BBCFDD4D8B8D5E935AB58E2364254DC94CD422C9B64E3B`.
The initial failure was a test-oracle error, not a product defect. The recorded
wrapper variable error and incomplete descendant peak measurement remain;
runtime dependencies use the accepted shared-runtime bridge, not a newly
captured immutable pre-run snapshot. No extra product regression or RC rebuild
is triggered by these assertion/report corrections.

The eight-case physical-schema reader family is now independently accepted and
integrated as test-only commits. Candidate
`a5969a9b76a01f40558b122e953292f0b1ace911` passed in9.3445s, with all148 product
source files exactly matching RC2. Its eight persisted-wire refusal guards,
per-call no-write snapshots, exact restoration and public reuse are proved.
The original shard and combined native data have exactly the same126 files and
14,569 arcs; ten recovery-workflow branches are new against U39 (eight targeted
guards and two journey branches). These are **included once in U40**.
Independent review SHA:
`4F73B7FF4BAD3D1837917E7A5C391FE9A3DD0E22D91E90AD0AC9E8F22F292CB1`.
Run1 and run2 remain excluded fixture failures, not product defects. The run3
pre-run dependency snapshot and independent64-wheel verification bind the actual
runtime. Its copied run2 reconciliation is reference evidence only; stale launcher
fields in environment.json/heads.json cannot replace the actual run3 pre-execution,
wrapper and process records. P6 proves immutable openedAt identity despite an
inaccurate generated label. These report corrections need no behavior rerun.
This proves software evidence identity only, never a physical device PASS.
A dedicated real healthy RC2
installation for package refusals was created once at r10/t/rc2rf/fixture-state;
it does not replace or repeat the accepted fresh-install or0.9 Repair results.
The deployment-document audit passed for the five documented files and packaged
guide identity (e/rc2/deployment-docs-audit.json, SHA
`9B5F4C226A365AC00FE16AC859790CBF2F4C66C4C612728BCB9FA0C1C9D4F074`).

One real failed-publication Repair on that disposable installation is now
independently accepted. A read-only state handle allowed earlier reads and
caused the actual File.Replace sharing violation after promotion. Repair exited2
in77.3501s; all5778 runtime files, state generation1 and project bytes were
restored/preserved exactly. After releasing the handle, one Check exited0 in
20.3210s with healthy runtime, matching state, bundle status ok and mutated=false.
No staging/quarantine contents, temporary state residue or owned process remained.
Review SHA `A71ADFEC7074783543C0A262B5325E37207790DDB3E9D2158571B4C1AFE559A0`.
This proves the selected failed Replace recovery contract; it does not claim
successful fallback WriteAllBytes under lock or recovery after a partial state
write. Source-conflict, downgrade and package trust refusals remain unexecuted.

Remaining: actual Monitor service auth/Ctrl+C130/resource release, applicable
package refusal/security and use checks, seven Windows-native checks and all
outstanding coverage thresholds. The Monitor console facility's fourth revision
failed independent review: duplicate data-root creation, wrong workspace identity
oracle, incomplete shared-deadline and cleanup ownership, and late output-failure
handling. All four rounds remain test-infrastructure failures, with zero real
Monitor service starts and no product change. The whole facility is held at design;
no fifth local patch or real service run is released. A harmless tool-managed
console probe proved SIGINT delivery but not the child's exit130 or complete
owned cleanup, so it does not satisfy the package gate. Builds,
deployment and formal ledger updates remain serialized. VS10-A/B and attempt7
physical PASS are retained; no hardware, remote mutation or denied cleanup was
performed. Details remain in the existing work ledger and release matrix.

## Preserved predecessor U38 source-qualified result

Integrated code head before this report:
`d8e134ce803c8b6f70fd8960ee7c117c903f51d1`.
Product source remains `55d91a23a5a2f16fc47d324a9077dfcebf130be9`;
source registry is `84F2A89603F776D7A27ADF968073E6A2685A1C227095B8CC9EDFDC710E852ECD`.
U38 verdict: **ACCEPTED_NATIVE_DATA**. Release 1.0 remains **NOT_ACCEPTED**.
Canonical SHA256:
`EBAFCFB4B09443DE10DF60982890669768D9FE249F39FAE8BB7AAAC80777C4BE`.
Independent native review:
`77F8AEBF133F9C793BFE953BA93A3FA0DF596F0937FD21CD4569DE4B2991085B`.
Primary admission/report correction:
`86CEAF963B7F10B28EBA52B544DF3E22650B45365AEB234A54BD39C813CF1553`.

| Package / frozen scope | Covered / total branches | Branch ratio | Remaining gate |
| --- | ---: | ---: | ---: |
| Toolkit overall / broad-core-v1 | 11,524 / 13,592 | 84.7852% | 709 for overall90%; broad-v1 retains 1,389 for95% |
| Toolkit risk-core-v2 | 10,906 / 12,918 | 84.4248% | 1,367 for95% |
| Monitor overall / broad-v1 / risk-v2 | 2,718 / 2,944 | 92.3234% | overall90% met; 79 for95% |
| UI, retained separately | 784 / 810 | 96.7901% | retained gate met |

This single aggregate took19.6391 seconds and ran no tests or product imports.
Independent review proved exact native unions (Toolkit85,112 arcs; Monitor55,865),
all ten inputs, source148, frozen scopes and six-path purge. All original raws and
ten prepared copies remained byte-identical. One stale History annotation was
corrected from324/352 to328/352 using the actual native summary; raw coverage and
union were not rerun. The review prose's eight current inputs is a count typo:
there are four legacy and six current inputs; eight qualified rows include two
legacy Wave13 rows. The primary admission records that correction.

Unchanged product paths gained13 unique branches. The six changed source files
now have976/1,760 measured branches, replacing the predecessor's1,417/1,748.
Those different-source counters are not a product regression delta and may not
be spliced together. The U37 artifact and its valid historical behavior remain
preserved. Current source qualification and all original 1.0 gates stay mandatory.

The separate public-firmware finalization candidate4378b38d passed its complete
journey in129.35 seconds pytest time (131.1827 seconds launcher child interval).
Its fixture target-domain repair changed two test files and no product source.
Run2 stopped before pytest because coverage.ini was missing; run3 passed after
that setup omission was corrected. The selected journey does not call fresh-show;
zero fresh-show shards are a missing selected scenario, not a proven collector
failure. Reuse the persisted completed record for one separate fresh-show read;
do not repeat the valid journey or its firmware builds. Its raw data is not yet
admitted into U38. All these records are offline fixtures, not physical PASS.

Next bounded Monitor work contains public DTO refusal/reuse, non-NFC sample
exclusion and physical-shaped export identity refusal/recovery. Eight potential
arcs remain estimates until native verification. At most two actual suites may
overlap; no evidence here justifies increasing that cap. RC/build/install/Repair
and the seven Windows checks remain incomplete. Hardware and remote state were
not changed, and denied cleanup was not retried.

## Preserved predecessor U37 result

Accepted aggregation baseline: union36, canonical SHA256
`566401658A8EE59BCE92FABD536B77264B2C925951E1495695B5E66B7608460B`.
Integrated code head before this report: `22ee8efbb37b79f6fbe39601a3011e805ae7b67b`.
U37 measured code head: `e0c8f3ffe0bc283901c7805d3865202e32505405`.
U37-qualified product source: `78341213b8e5604d5f6a0436c4324d6d9f9e3ead`.
Integrated Diagnostic source: `55d91a23a5a2f16fc47d324a9077dfcebf130be9`,
reviewed final candidate `60a39d44f2416e3417d9c36a4076ca35945c366c`.
The U37 Toolkit counters below describe the predecessor, not the changed candidate.
Union37 native data verdict: **ACCEPTED_NATIVE_DATA**. Release 1.0: **NOT_ACCEPTED**.
Canonical SHA256: `E41F381604588F3092F3F3A7E6A6A0332C59F65A66947BF07F79AA3620913961`.
Independent review: `24F5C1C7919A8E1FEDE603124C6BF673479F6690963C298BC1D0E097C67FB1B4`.

| Package | Covered / total branches | Overall and broad core v1 | More for 90% | More for v1 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,952 / 13,580 | 88.0118% | 270 | 949 |
| Monitor | 2,718 / 2,944 | 92.3234% | 0 | 79 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Frozen risk-core-v2 is Toolkit 11,334/12,906 (87.8196%, 927 more for95%)
and Monitor 2,718/2,944 (92.3234%,79 more). Inventories remain unchanged.
U37 adds three existing public configure refusal/reconstruction branches and
11 public Analysis input/refusal/restoration branches. Source148 hashes, native
raw/shard preservation, exact raw union, no removed arcs, denominators and UI
retention were independently verified. The statistics specification's original
7,181-byte prefix remains exact; only its previously approved Diagnostic appendix
changed the whole-document hash. The first metadata preflight refusal is kept.
Aggregation ran no tests and changed no product bytes. See e/risk-v2/union37.

Wave12 engineering took3.3819 seconds and Monitor4.1078 seconds; these actual
suites did not overlap. Launcher-only PIDs and missing descendant peak data do
not justify raising the two-suite cap. Earlier failed/pre-pytest inputs remain
excluded. After U36's nine and U37's fourteen total new branches, the primary
reassessed yield and froze a grouped public creation/generation batch, necessary
Diagnostic current-source measurement, and a read-only Monitor residual audit.
The plan c55a1967 forbids further percentage-driven product modifications.

Diagnostic reference correction55d91a23 changes six product files to honor the
public arbitrary32hex identifier contract while preserving backward evidence
reading and the separate UUID domains. Complete base79cf6733-to55d91a23 product
review and c1f6-to60a39d44 final test-delta review accept current-source behavior:
run2's full alias-to-final-record journey, run3's two remaining refusal/corruption
journeys (26.5095s), and64 affected regression nodes (187.8666s). Failed run1 and
mixed run2 raw remain excluded. A report field incorrectly attributing the alias
behavior to run3 is a report-only correction; the behavior source is run2 and
producer-reacquire later acquires its admissible measurement. No repeated behavior acceptance is claimed.

Candidate60a39d44 is integrated at c7d3d73b after behavior and complete-diff
acceptance; six-source native requalification remains pending. Merge checkout
changed the six files' raw representation relative to measured w11r. The other142
source files match. Exact-pair reviewDFCFBB17 confirms that all six differences
are newline-only; all148 qualification/worktree/Git source representations have
matching normalized bytes, line boundaries and Python code/line tables. Their
raw identities remain separate. This does not waive release source-wheel binding.
Independent measurement review61AF9EC7 rejects regression1's entire raw: private
fact/reader/validator/model substitutions and an unrecorded synthetic fixture
switch are inseparable in its one context-free shard. The64 behavior results
remain bounded to what each test actually proved. Its896/1760 read-only union
with run3 was diagnostic arithmetic and is not admissible native qualification.
The old U37 six-file1417/1748 arcs also cannot transfer to the new semantic source.
The candidate's total denominator is13,592, not13,580; file scope is unchanged.

A separate model-gap run passes140 in3.7871s and has valid source/shard evidence.
JUnit proves112 planned cases plus28 unintended repeated public cases, not the
execution owner's initial34 estimate. Wrong pytest-root deselect IDs caused the
selection deviation; all actual cases are legitimate public model/front-door
calls, so the primary accepts their data without a repeat. Valid run3 plus this
model input currently qualify76/80 model and291/296 recovery-model branches;
the remaining four-file qualification is incomplete. Alias behavior stays at
run2. Its isolated measurement now passes1 in44.3021s with one retained shard;
independent native reviewB99DDAF9 accepts this bounded input. This is not a new
behavior claim. Neither coverage counters nor behavior are invented.

The CLI group on isolated sourcew11r passes177 in46.1725s with one planned native
symlink deselection. Independent reviewB7C686BB accepts its native input: eight
retained shards have an exact combined union. The empty shard is authenticated
as pyocd.EXE --version; the seven product-bearing shards resolve to qualified
w11r source. Public parser/delegate translation evidence is not producer or
physical acceptance. This is source remeasurement, not177 new product behaviors.

The independent w13mcp group passes259 in306.4550s, but its measurement is
INCOMPLETE. The actual test marker records spawned ProbeBackendWorker PID28820;
the eight retained shards contain no such PID. The reported PID30524 is the
FastMCP stdio server. The original incorrect audit is preserved beside its
correction. Retain all behavior and raw evidence, but do not admit this input
as complete or rerun the whole group. Existing child-save collection is under
independent review for a bounded correction; no product change is justified.

CLI and MCP actual execution intervals did not overlap. Their worktrees, temp
roots, logs and native outputs are independent. The two-suite ceiling remains;
launcher CPU and unavailable peak memory do not justify expansion. Source-input
and raw-input review/preparation proceeded independently; those are not suites.
The real-input finalization journey stops at its first begin in24.9875s. Native
execution records identify recovery_workflows.py:382 wrapping the firmware-version
refusal in probe/flash.py:383-384. Historical build identity toolkitVersion0.9.0
does not equal current runtime1.0.0. A direct call to the existing read-only
load_fresh_firmware_facts reproduces FIRMWARE_IDENTITY_MISMATCH, field toolkitVersion,
rule current (firmware-version-diagnosis.json SHA70E08823ADA477E5ED19C0D214334160303A3A657EA153A6217BB04C22961B77).
The initial static input admission missed this runtime requirement. This is
TEST_INPUT_COMPATIBILITY, not an established product defect. Original project,
data and bind request remain unchanged; checkpoint/show and its child were not
reached. Exclude this failed run from native aggregation. Do not rerun the same
input, rewrite historical evidence, or relax the product version check. A bounded
read-only audit of existing current-version public build fixtures is pending;
it is not a new physical PASS or an authorization to implement a new fixture.

Engineering candidate8dde6cab is independently accepted and integratedca700646.
Its two complete public discovery/generation risk families add13 unique native
arcs, pending the next serial aggregate. Run1 takes3.1361s;13 strengthened-oracle
nodes take3.2485s in run3. The unchanged three runner-output cases retain run1.
The plan-to-integration interval is25m24s; suites did not overlap. Run2 executed
zero tests because whitespace parameter IDs were split by the launcher; stable
IDs resolved selection without a new framework or product change. No duplicated
arc credit is taken. U37 remains the canonical source-compatible aggregate.
RC1 remains stopped after build-A's source/wheel binding refusal; no build-B or
installation retry. The Sampler raw12FF/mixed-newline and archiveD198/CRLF pair
has independent Python3.12.10 normalized-byte/AST/code-object/line-table equality
proof, bounded to that exact pair. Raw identities remain different and the
release source/wheel byte guard remains mandatory. This does not accept a release
package or authorize reuse of the six semantic Diagnostic changes. A genuine0.9
runtime remains healthy at generation1 for later Repair. All Windows-native,
coverage, closed-dependency two-build/all13-output and actual-bundle installation,
Repair/rollback/security/documentation gates remain mandatory and incomplete.
The repeat-bind product correction remains accepted with its seven current-source
PASS. Source changes invalidate old coverage for recovery_workflows.py, so union21
removed that file's old-source arcs and incorporated only accepted current-source
evidence. The historical union20 result, 11,795/13,578 on source 465249d, remains
archived and must not be presented as the current product's coverage.

The two complete Diagnostic caller journeys passed in 90.370 seconds: lifecycle
through resolution/retry, and twelve authority-refusal variants with exact graph
preservation. Union22 incorporated the complete run and added 23 native branches.
Its three failed construction batches remain excluded, with diagnostic evidence
retained. See diagnostic-public-journeys.md for the accepted implementation scope.

An explicit primary source-qualification decision then reused three existing
generic recovery selectors: build-provider failure, six build-output refusals and
six target-replay refusals. All **13 PASS in 8.541 seconds**, exit 0, no timeout or
forced termination. No tests or product code changed. Union23 adds 87 Toolkit
branches; recovery_workflows.py then had 399/860 current-source branches. The run
did not import Monitor, so its accepted union22 object and UI are retained unchanged.

The risk-layered wave then qualified the remaining existing generic-recovery
group (36 PASS, 10.944 seconds) and the continuation/software physical-protocol
chain group (10 PASS, about 175 seconds). Both completed with exit 0 and no
timeout/forced termination. Union24 adds 138 current-source Toolkit branches;
recovery_workflows.py reached 537/860. Monitor counts and UI remained unchanged.
These software protocol checks are not hardware evidence. Finalization7,
Diagnostic2 and generic13 were retained, not repeated.

Three separate Luna/max owners then added the frozen M/P/A contract groups:
M5 PASS at 7744cf83 (2.661s), P4 PASS at d8b7a328 (3.02s), A5 PASS at 79323b98
(24.06s). M's final 2d4ea2c is formatting/docstring-only, so its earlier runtime
result remains valid. Primary reviewed complete accepted-base diffs in clean
separate review worktrees; all final test files passed Ruff and diff checks.
P/A's initial fixture failures remain classified as test defects, with failed
raw databases excluded. No product source changed.

Union25 adds four Toolkit and three Monitor native branches. The accepted
source recovery file reaches 539/860. Most new cases strengthen observable
rejection, exact rollback and resource settlement assertions over already
covered paths; fourteen PASS cases do not mean fourteen new covered branches.

Union26 adds the complete SVD2, recovery7 and creation-settlement P6 groups:
2 PASS in 1.673s, 7 PASS in 378.276s and 6 PASS in 1.224s (JUnit durations),
all exit 0 without timeout. The full P diff was independently reviewed at
33c299ae before integration. Its first run observed a file after successful
cleanup; that test defect was corrected and the failed raw remains excluded.
The independent native review verified all 148 product source identities,
eight native inputs, per-file totals and frozen scope arithmetic. Toolkit gains
62 branches with no denominator change or coverage regression; Monitor is
unchanged. The immutable candidate and prior accepted union25 are preserved.
The following Monitor/sampler results were outside union26.

Union27 adds accepted M6 plus the corrected same-store WAL case, Target prepare7,
Diagnostic authority6 and sampler overlap4: 24 complete PASS across five inputs.
Primary reviewed each full diff in clean exact-head worktrees; independent native
review verified all input/copy hashes, source148 and frozen scope arithmetic.
Toolkit gains11 and Monitor gains10 branches, with no denominator or coverage
regression. Earlier failed construction/timing batches remain excluded. M's
oversized input proves the earlier safe-read refusal, not the later value limit;
its original WAL case proves cold start and the corrected case proves trusted
same-store refusal. Sampler's public consumer is armed before start; its earlier
late-subscription timeout was a test error. All product bytes remain unchanged.

Union28 adds four complete accepted groups: cumulative History publication limit
and recovery (1 PASS), external tool support failures (11 PASS), startup
cancellation while cleanup retains ownership (1 PASS), and Recovery authorization
and output identity refusals (4 PASS). All 17 passed with exit0; primary reviewed
each complete diff. Independent native review checked input/copy hashes, all148
source identities, frozen scopes and arithmetic. Toolkit gains10 and Monitor
gains2 branches with unchanged denominators. History's cursor/model expectation
failures and Recovery's snapshot fixture failure remain excluded; runtime's
initial insufficient cancellation-window case is also excluded. No product
source changed. Wave5 results were outside union28 until their separate review.

Union29 adds complete ProbeSession11, Analysis1 and existing Recovery5 batches:
17 PASS, each exit0 without timeout. The Analysis journey covers the original
continuation association and all three alternate TestRun refusals, immutable
evidence and successful reuse of the original request. Recovery reuses five
existing tests on the qualified source. Complete test diffs, source148, all eight
raw inputs/copies and unchanged frozen scopes were independently checked.
Toolkit gains9 and Monitor gains12 branches. Failed ProbeSession/Analysis run1
databases remain excluded. The first aggregation attempt failed because new
aliases were in the wrong INI section; correcting the map and parsing it with
coverage.py allowed native-only aggregation, with no pytest rerun. The immutable
candidate and prior accepted union28 are retained. A stale representation note
was corrected at promotion to history.py summary324/352 versus arrays323/351;
native totals and original arrays were not altered. Product source is unchanged.

Union31 adds the accepted Handoff and Observation journeys, persisted Recovery
binding and Monitor-reference integrity/refusal/restoration journeys, and corrected
PyOCD child measurement. The complete test diffs were reviewed before integration;
no product bytes changed. Native totals gain17 Toolkit and5 Monitor branches over
union29. Nine Toolkit branches had already appeared in the immutable partial
union30 candidate; the latest Recovery/Probe work adds8 Toolkit and Monitor adds5.

The three new authority/measurement suites completed independently: Recovery3
(164.308s JUnit), Monitor5 (7.860s), and the three program-failure outcomes
(18.827s). Their process intervals did not overlap. Existing PyOCD4 behavior and
attach measurements remain valid; program-only rerun3 addressed missing child
capture. Seven actual native shards and seven neutral byte-identical copies are
retained. Both child and combined data contain program diagnostic arcs516->517,
519->520,524->525/526 and error-line1543 through1540->1543. Run2's lost original
shards and partial status remain explicit; it is not retroactively relabeled
complete. No hardware, deployment, packaging or remote operation occurred.

Independent union31 review verified all12 native inputs/copies, source148, frozen
v1/v2 scopes, per-file arithmetic, failure exclusions and retained UI. Primary
rechecked source148 at promotion. Canonical SHA256 is
21D1CF7DE3E64164BCBBCAA35FAFEE2672ED9782241A35EC1BD6B45F27177B86;
independent review SHA256 is
615B4D2DA87CE1EF31C703C842A7336A61CBA94233426ACB02F0B41532D4F235.
Immutable candidate, input history and review are under r10/e/risk-v2/union31.
The accepted aggregate does not satisfy the remaining90/95 gates.

Three original Luna/max owners continue Recovery/evidence, Monitor and Probe
lines with one dedicated independent reviewer. Two actual suites may run at once;
three have not been released because overlapping-run and complete descendant
resource evidence is still missing. All known batch execution PIDs have exited.
The two public protocol assembly scenarios have since completed15PASS in3.446s
JUnit and6.930s process time, exit0 without timeout. Exact code/message refusals
and the successful manifest are verified; original native child shard is retained.
Primary and independent review accepted the complete test diff at08e2b8c,
locally integrated as1b7a763d. Union32 adds exactly15 Toolkit branches, all in
protocol.py, with no denominator change. Monitor and UI reuse their accepted
union31 bytes without a test or native recombination. Runtime source remains
8a11; candidate-head labels in the original run metadata were corrected in the
primary review using source148, without rewriting originals or rerunning behavior.

Union32 canonical SHA256 is
E335DFC50A8CBC8E41409297B22D34195AA3447A1577B08EB38280928C11FA78;
independent review SHA256 is
C02F74AAF18B77CEFAEDC0294797881FB509BA2B5DE86CD61248E50D7A6DAFEA.
Toolkit native raw SHA256 is
900E3279543A1BF4402A4FC47B12D61F59B54536B99D0E3FDBF3A3246E683136;
JSON SHA256 is
432C1922B1C6AA10547D13BBF71A154065375A8F9A7249906E3585D2B472E093.
Prior immutable candidate/input history/review are under r10/e/risk-v2/union32.

Union33 adds public protocol producer/declaration refusal and round-trip scenarios
(14 PASS, 3.171s JUnit), plus Target discovery over the real MailboxTransport
(6 PASS, 2.011s). Target checks a valid seven-field identity and five first-guard
refusals, unchanged evidence, no flash/control calls, and exact transport/probe
settlement. Its common negative no-control oracle was strengthened and only those
six cases rerun. Metadata-only template corrections did not trigger a rerun.
Both original actual-interpreter shards remain retained. These suites do not
spawn product subprocesses and do not claim hardware behavior.

Independent full-diff review and native review accepted all three Toolkit inputs
(prior union32 plus these two runs), their neutral copies, all148 source hashes,
and frozen scope arithmetic. Native aggregation ran zero tests and added exactly
22 Toolkit branches: protocol14, target7 and mailbox1. No prior arc regressed;
Monitor/UI bytes remained unchanged. Historical union33 candidate/input/review are
under r10/e/risk-v2/union33. Its accepted canonical SHA256 was
2319CDF1B2A2592D424D997079BFD8CD6EF20D1DCB74C2FC0D66385CAE39DDFC;
independent review SHA256 is
B13E46EDC772F03CAAA9A765DAB24D8C2CDC8AA2CA3E72246BDF4EC0582F7EB1.
Toolkit raw SHA256 is
DE90709231272DC7E2B2817685660F5F4DE3EEA29244AD72575D1637F773CC52;
JSON SHA256 is
8560B44329F43E29C805C5D939A39F67D4BF753C48EBC14BF416223EFFAD5ADF.
The review's truncated wrapper-hash literal is corrected additively in promotion
metadata against the actual64-character hash; native data and tests are unchanged.

Union34 adds public attach-diagnostic validation/merge/detachment/refusal scenarios
and Monitor analysis model/native-threshold/roundtrip/refusal scenarios. Both complete
diffs passed independent review; Probe2 PASS(1.725s) and Monitor3 PASS(1.392s)
retained their actual interpreter shards. The Probe first launch stopped before
pytest on a wrong full SHA; only corrected run2 executed. Native aggregation added
28 Toolkit and11 Monitor arcs, removed none, preserved five input/copy hashes,
source148, frozen v1/v2/UI and native history summary/array representation.
Canonical SHA256:3FD740FF19EBD3D3B612F8F2A5208DD71D6E78DFFCC245515D2634BA68682A1E.
Independent review:55FF7EDB1EA6C37F8190A9BACE1B93D8C44BA40D3640768A578151B198E96974.
See r10/e/risk-v2/union34. No tests were rerun by aggregation.

A separate public task-factory reproduction confirmed failed sampler start leaves
RUNNING after task allocation fails. Its cleanup completed; the original RED input
remains excluded. The correction is now independently ACCEPTED through final
candidate419e908eb5173eec7fdf00614136d96623b19fa1. It retains STOPPING and resource
ownership until rollback settles, closes rejected coroutines, waits through caller
cancellation, and preserves a public stop/restart path if cleanup allocation fails.
Run3's55 passing checks and run4's one new double-refusal check share the exact
current Sampler bytes; the55 were not repeated for the appended scenario.

Union35 incorporates that accepted source correction and the Diagnostic authority
journey's explicit oracle reconciliation. Diagnostic run2 remains FAILED at its
final JSON-versus-frozen-container comparison; an independently reviewed public
idempotent completion/fresh-show reconciliation passed with no input mutations.
Its12 measured authority/refusal arcs are accepted, while the uninstrumented
terminal reconciliation contributes no inferred coverage. This is software
protocol evidence, not physical acceptance or an all-pass original pytest run.

The148-file registry changes only sampler.py;147 files remain byte-identical.
Old Sampler arcs were purged only from neutral copies of every old-source raw,
including Toolkit and Diagnostic inputs. Original raw files and child shards are
preserved. Native Sampler coverage is150/168, replacing143/164 on different source;
that is source requalification, not a comparable seven-arc gain. The actual new
denominator increases Monitor by4. Frozen108/18 overall files,97/16 broad-core
files,90/16 risk-core files and UI are retained. Every unaffected prior arc remains.
Aggregation ran no tests and imported no product modules.

U35 canonical SHA256:8141C5C62C0C3630BB1CBE8718AFEAEEEF1C98F6BF38F51656ABC58F884AD87E.
Source registry SHA256:69D2A724BE181F715FF82E776FFA16F86F2410ADD16780B0C8F17AC9B01BB28A.
Independent native review:0E70AA8A32C63284F5B92414886176A7672F3E2706EA5965A3D4F31BBE002B60.
See r10/e/risk-v2/union35. No source denominator or file selection was reduced.

Wave10 keeps the three original owners and independent reviewer. A frozen bounded
implementation dispatch may allocate one of two execution slots, avoiding another
release round trip; full independent review remains required before acceptance.
No three-suite expansion is released without actual overlap/resource evidence.
New low-yield preflights are not coverage claims. Public exported constructors
may be tested for genuine input refusals; manufacturing invalid successful
objects or bypassing production guards remains prohibited.

Risk-core v2 was selected by whole-file responsibility and independently frozen
at scope commit 9fff3f43 before scoring. Its 90 Toolkit and 16 Monitor files are
reported separately; the 108/18 overall files and old v1 statistics remain.

| Risk-core v2 | Covered / total branches | Coverage | More for 95% |
| --- | ---: | ---: | ---: |
| Toolkit | 11,331 / 12,906 | 87.7964% | 930 |
| Monitor | 2,707 / 2,944 | 91.9497% | 90 |

Native v1 scope remains 108/18 Python files overall and 97/16 core files. The excluded
forwarders have zero branches, so overall/core ratios coincide. Per-package native
summaries are authoritative; the previously recorded distinction between literal
JSON branch pairs and native summaries remains applicable. No raw splicing,
scope reduction, cross-package pooling or unreviewed failed-batch reuse is used.
The changed-source Sampler denominator and reviewed Diagnostic reconciliation
are explicitly qualified above.

Historical union23 evidence: `D:/codex-tmp/v10b-0918/r10/e/n95/union23`.
Generic run raw SHA256: `C565BD64F56D1F25FF7DF3F2073D476D8D289FA6C05C9B8A5C7C823F4DCE9780`.
Union23 Toolkit raw SHA256: `3B4FEC0818FA7F176A5E936EB627E2AB5AE115666529D620956634B88110A51B`.
Native JSON SHA256: `8A04CDF8C0AF1833BC0A76F0362518F117C6B48185296537AFB258DE710C7852`.
Independent review SHA256: `604D2971C58B08BAC9E851E2C9D78B57BCDE57E5287E0160D0610D30D743BB73`.
Historical snapshot SHA256: `1A1161097F4C2EA960C9E3C8B3005EF82050089853B51CD4C188DB42B5A450E6`.

Historical union29 evidence: `D:/codex-tmp/v10b-0918/r10/e/risk-v2/union29`.
Toolkit native raw: `730E59EC30CAA4E2C44694240CC85E755E60EC005EF7E13971D619E82F9A97AF`.
Toolkit native JSON: `F05B652753981E27683A81202D1D1B9D159D5B5C69AB658C0ACEFB3BAEA33337`.
Monitor native raw: `6AD87712E72AC43E6887B259B8FC89F09BFC47FBEDB06EAC43F429ACE6C63FD2`.
Monitor native JSON: `C99DB5E35E5131AD197905C08486926EF9D3D1B7F1F385B20AAAC386980D2B14`.
Immutable candidate: `CC7FB0FEB69CAC53F2FDFD85F804CDA0A66AAAAD527A90ACC212F9530DC91AB8`.
Independent review: `CD62ED005A212DAED7BDA3ABDCEA01B655BBFB15911B9E442BA48EF1201AA8C5`.
Accepted canonical snapshot: `73F815323E7C57691712C156B8E306479F693A91573829C01220A7F3963CCC6B`.
The accepted prior union28 snapshot is retained in this evidence directory.

Overall 90% remains mandatory. The approved risk-layered redesign keeps broad-core
v1 statistics and introduces separately reviewed risk-core v2; its scope and
critical-scenario matrix are now frozen. All three numeric views remain visible. VS10-A/B
acceptance and attempt 7 are retained. Coverage qualification, seven pending native
Windows checks, final artifact creation and final deployment remain incomplete.
No hardware, packaging, deployment or remote action occurred in this offline
qualification batches. No clean full-suite PASS or physical PASS is inferred.

Supplementation follows the 2026-09-20 risk-layered specification and plan with
disjoint A/P/M ownership. No product changes solely for coverage, repeated valid
hardware evidence or branch-by-branch task sequence is authorized.

A metadata-only PowerShell variable-type error overwrote the local work ledger
during this wave. Its current authoritative state was recovered from the original
tool-output snapshot and the complete new run evidence. Some obsolete top-level
historical fields were not reconstructed; original raw evidence, source and
tracked historical reports were unchanged. The failure and recovery limits are
explicitly recorded in `risk-v2/ledger-write-failure.json` and `work-ledger.json`.

One cleanup attempt for the five verified success-run/copy roots t/dj4, t/u21,
t/u22, t/gq1 and t/u23 was rejected by automatic approval before process start
with `blocked by policy`. Zero files were deleted; all five remain present. No
retry or alternate deletion mechanism was used. Failure roots and authoritative
evidence remain preserved; disposition is recorded in union23/cleanup.json.

This wave's cleanup for vr1/vr2/u24/v2m-run1/v2a-run2 was likewise rejected before
process start with only `blocked by policy`; zero files were removed and there
was no retry. Later P-run2 and u25 roots remain pending cleanup, not relabeled as
explicitly rejected. Raw evidence and source/review worktrees remain retained.
See `risk-v2/cleanup-success.json` for the precise attempted targets.

Union27 cleanup of six new accepted-run/copy roots was rejected before process
start with blocked by policy. All roots remain, zero files were deleted, and no
retry or alternative deletion was attempted. See union27/cleanup.json.

Union28 cleanup of six newly qualified run/copy roots was also rejected before
process start with blocked by policy. All remain present, zero files were
deleted, and no retry was attempted. See union28/cleanup.json. Failed-run
evidence and all source/review worktrees remain preserved.

Union29 cleanup of five newly qualified run/copy roots was rejected before
process start with blocked by policy. All remain present, zero files were
deleted, and no retry or alternative mechanism was used. See union29/cleanup.json.

Union31 cleanup of five new verified success-run/copy roots was rejected before
process start with blocked by policy. Zero files were deleted; all five roots
remain present. No retry or alternate deletion was attempted, and older denied
roots were not included. Durable raw evidence and review/source worktrees remain
preserved. See union31/cleanup-plan.json and union31/cleanup.json.

Union33 cleanup of eight newly verified success-run/copy roots was rejected before
process start with only `blocked by policy`. Zero files were deleted; all eight
remain present. No retry or alternate deletion was attempted. Earlier rejected
roots were untouched; see union33/cleanup-plan.json and union33/cleanup.json.

## Current batch: remaining package refusals accepted

RC2 policy-tamper, manifest-identity-tamper and Toolkit-wheel-integrity-tamper
ran once, serially, from2026-09-21T22:23:18.007912Z to22:24:12.514032Z
(54.506120s including discovery/copy preparation). Each public Bootstrap
returned2 with the exact refusal wire before data/project/runtime writes.
After forward restoration each public verify-bundle returned0 and matched
64wheels plus6artifacts. Primary independently rehashed every one of1,147
restored files in each of the three copied packages and compared full
before/mutated/after inventories; only the declared mutation changed.
Six direct command processes returned terminal/drained without timeout;
the bounded synchronous guard scope does not claim arbitrary descendant census.

Run-resultDB6703CA1B7066E3626F8233A25CEF9F8A09F455BA6CFE8089843D85D4866516
and independent primary-result-reviewD64ACD9E895CA255ABD5904255D0A6C765F30F1B59DE9DC9DE0F0D1BB51E9D02
are retained under e/rc2/refusals/run2. The original result's inherited3D6
entry-review label remains preserved; the result review binds actual full
entry-review67E8 and primary admission2DEC without rerunning commands.
Together with the three accepted run1 cases and earlier real rollback,
these close the six-case refusal/restoration scope. They add no source
coverage and do not constitute complete1.0 release acceptance.

U41 reused existing native aggregation/report functions in7.313s. It adds
exactly the seven already accepted SVD branch tuples, loses none, preserves
148source bindings and leaves Monitor/UI data unchanged. A first adapter
preflight stopped before combine because the reused normalizer had not yet
received its exact root/registry configuration; both originals are retained.
The corrected aggregation has no purge and reruns no test. Candidate127E689
passed independent review0DDBFDAF and primary serial promotion510552A5.
U41 is now canonical; U40 and the unmodified reviewed candidate are preserved.

The corrected native console capability ran once at22:20:29.706363Z through
22:20:30.6443767Z,0.93825s. One Ctrl+C produced actual130, exact17-byte READY,
empty marker stderr and empty Job; owned processes settled. Controller stderr,
however, recorded CPython Handle.Close WinError6. Primary traced this to closing
subprocess.Handle through raw win32api.CloseHandle before its owning object
finalized. Preserve the valid signal facts but reject complete cleanup acceptance.
Classification457AF356D7F0798EF6855CE772198E042624FA54B2F5BAB66668BC2207629FD2
freezes native-PyHANDLE versus CPython-Handle ownership before a bounded
facility correction. The summary noPrompt discrepancy is REPORT only.
No Monitor product service or new hardware operation ran.

The harmless capability and package runs did not actually overlap. Their
roots/logs/process ownership were isolated, but the two-slot permission alone
is not concurrency evidence. Peak working set0 remained unavailable. No third
slot or performance claim is admitted. Product source, RC2 inputs, prior
build/install/Repair/security/physical evidence and frozen denominators remain
unchanged. Next exits are clean native capability settlement and real shipped
Monitor service/auth/Ctrl+C/resource reuse; independent U41 qualification;
and one concrete producer-to-continuation reachability proof under the frozen
external-provider substitution rule before any new coverage tests.

The bounded B4AE helper-handle correction has passed primary full-predecessor
and complete-diff review. Its first outer launcher lost tool session35417 before
returning a shell status; read-only checks found no new outer/candidate roots or
matching process. Preserve launch-failure43A9A903 as TEST_INFRASTRUCTURE; do not
invent an exit code or call this an approval rejection. Primary7D8B59C8 admits
one direct invocation of the unchanged corrected candidate with retained output,
removing the unnecessary outer background/session wrapper. A clean actual result
is still required; no product service acceptance follows from preparation.

The next recovery slice is fixed by plana6921d8d: one public failed-target to
Diagnostic/authorized after-build journey, repeating exactly five completed
checkpoints with their original public arguments and prior revision. Eleven
physical checkpoint idempotence edges are static targets, not measured gain.
External backend substitution is allowed by the frozen specification; private
facts/readers/validators/state and direct authority fabrication are not. The same
Luna/max Recovery owner implements and runs the first bounded targeted validation
in isolated w18r/evidence/temporary roots. No new continuation600->607 success
edge is claimed; that prior mapping was explicitly withdrawn.

### Native facility result accepted after direct primary verification

After the lost-session wrapper, the replacement inline launcher failed before
candidate invocation on an unquoted PowerShell false token. Preserve43A9 and740E
as pre-invocation infrastructure failures, with no invented candidate exit or
approval rejection. Stop adding outer-launcher scaffolding. Primary independently
invoked the unchanged, already reviewed B4AE controller directly with D-root
environment and retained stdout/stderr; the implementation owner did not self-accept.

The actual run completed in0.8757483s with controller0, marker27432 exit130,
helper18852 exit0, one Ctrl+C, Job containment/empty, exact17-byte READY,
empty marker AND controller stderr, matching top-level noPrompt and no cleanup
failure. Marker and launch exit labels explicitly describe the same native
handle. Actual controller12100 and both owned child PIDs were absent afterward.
VerificationA32B98595956761002ECFB0B9575E5195ED0FC51FF85BD4F117BEBF7562AF2B3
is retained under t/rc2mc-native/primary-direct-acceptance. CPU and peak working
set were not measured. The earlier warning failure remains unchanged.

This accepts only the harmless signal/ownership facility. The real shipped
stm32-monitor.cmd service remains unexecuted. Its next design reuses existing
public authentication, runtime-record, listener and lock-reuse assertions and
the verified native startup boundary; secrets must remain in bounded memory.
Independent reviewer is checking the exact reusable boundary before the same
Monitor owner implements the smallest package-acceptance entry. No product
change, packaging repeat, hardware, remote action or third suite slot is released.

### Verification-entry failures returned to primary design

S18 corrected test candidate572b328f1938b921da422ac8455e040c6ccdd3bc
has not executed pytest. The first corrected launcher stopped in1.338s on an
existing empty stderr stream; its stream-consumer correction then passed the
bounded output probes, but run2 stopped in1.487s because Start-Process flattened
the Python -c argument. Preserve failure40CBB90A and76C21664 and both run roots.
These are TEST_INFRASTRUCTURE, with no behavior result, native shards or new
branches. Following the repeated-contract rule, primary stopped further suite
invocations and returned the complete argument/stream/deadline boundary to
design, with the original Recovery owner and independent corrected-test review.

Complete independent review6F11CACF rejects Monitor entry8BBC before any service
run. The blockers are the credential scanner rejecting a legitimate workspace
digest, venv-versus-base process identity confusion, missing real service130,
incomplete identity-module binding, helper reader/handle ownership gaps, and
blocking operations outside the shared deadline. Primary pland18cf5d9 freezes
one consolidated correction of this same contract; earlier review rounds remain
counted. The shipped launcher and installed product stay unchanged. The public
lock-control fixture uses the pinned base interpreter and exact installed API
origins so its retained native handle identifies the actual executing process.
No real Monitor invocation is released before complete independent review.

Canonical U41 is unchanged: Toolkit11821/13592 overall, risk-v2
11203/12918; Monitor2725/2944; UI784/810. Remaining branch gates are412 Toolkit
overall,1070 Toolkit risk-v2 and72 Monitor risk-v2. No actual suites overlapped.
Prior physical, RC2 reproducibility, installation, Repair, refusal, rollback and
security evidence remains valid within its recorded scope. The seven Windows
native checks still lack the required host capability. The1.0 goal is unmet;
entry preparation and review are not product acceptance.

### Actual RC2 Monitor use and bounded remaining-only verification

Primary ran the reviewed1197 fixture once: shipped startup, unauthenticated401, bodyless bootstrap200 and cookie-backed status200 passed. The fixture then failed on PyHANDLE conversion; emergency Job cleanup succeeded. Result60C5D08CD9A3E9466EDA59D7F18D6FE80F4D289EB2CA5A9F16EEA83A4B4CFB3B remains FAIL. The exact existing image helper reproduced TypeError on an own-process PyHANDLE (BED529C1); this is TEST_INFRASTRUCTURE, not a product defect.

After the minimal integer-handle conversion and independentD5A10B8A review, one5F7CD704 attempt completed real startup/auth and one Ctrl+C. The actual service and shipped CMD independently exited naturally130; the runtime record disappeared, the Job became empty without emergency termination, all handles closed, no listener was observed and project bytes were preserved. Result9FA131201AF00D84BDF01A501B66B50C65729FCD29E16F682E96A122445CC7FE remains FAIL only because its2s connect_ex measurement returned10035 before public resource reuse. Controller elapsed62.1765s; no other actual suite overlapped. These normal-stop observations are retained and do not justify repeating the full flow.

A single later post-stop socket observation on the same bound port59711 obtained exact10061 in2.031s with a5s cap (AEDAC2F20FEB9222E1C80101422A1362987A833B47BD7A919DF2316513AC2D6A). No Monitor restart occurred. This supplies a later refused-port observation, not a rewrite of the original deadline/result. The remaining method reuses only existing public_reacquire on the same owned data root and frozen RC2 identity, with a fresh control session. It retains exact10061, extends only the per-socket measurement allowance to5s inside the same120s total/15s cleanup budget, and does not rerun startup/auth/Ctrl+C. Preparation and changed-boundary review are each limited to15minutes; another unresolved entry failure ends the batch and returns method selection.

S18 complete review5178AB58 closed its latest collection corrections but still rejected the custom entry's deadline/handle/preflight boundary. Do not continue that launcher patch chain. PreserveD069, test572b and all valid probes. A simpler alternative is being prepared using existing pytest/coverage CLI stages in a tool-managed terminal under primary control, with source-bound original subprocess shards and serial measurement admission. No actual S18 test or new native coverage has run. U41 remains Toolkit11821/13592 overall and11203/12918 risk-v2, Monitor2725/2944, UI784/810; gaps412/1070/72.

Target55 has been grouped using the existing list:12 high-risk,6 public-scenario,16 module/provider-boundary,18 special environment/persistence,3 unknown. These labels neither shrink the denominator nor prove all edges reachable. Do not release isolated Probe3/Target5 supplements. The seven Windows native symlink checks remain capability-blocked in the current Medium token; no privilege or system setting was changed. The1.0 release goal remains unmet, and no remote action occurred.

### Installed Monitor use accepted; native S18 prefix failure retained

Primary executed the reviewed residual-only public start/stop once on the exact prior data root. CandidateC37049C9, preflightDA82685D and static reviewED74F641 produced resultD61867A8EF724E191BCABC42FD39B940D7CDD08C4D996AE0EDAF63F81D6C1E48 in7.281s. The real public runtime record, workspace/session/path/token-hash checks passed; the record disappeared after stop, no listener remained and connect_ex returned10061. The actual base-Python process was Job-owned, the Job ended empty, all handles closed, no emergency cleanup or output failure occurred,227 bounded output bytes contained no secret, and project bytes remained unchanged. Independent result review25A1FA9DB96592F9D72E46337696C8A8FE1B0674BA2A95B343FCBF74A54DA1F6 accepts the residual package-use sub-gate. Together with f8h's actual startup/authentication/natural130 and the later port observation, the required package-use behaviors are now accepted. The original f8h FAIL is preserved; no claim is made that its interrupted composite scenario passed.

S18's existing native CLI entered pytest successfully after manifest-only correctionEF7FBE37. The test failed at test.target.prepare with TEST_AUTHORIZATION_INVALID before target execution or checkpoint coverage. Native invocation elapsed6.4649s, pytest reported4.67s; the first failure stopped execution. Preserve batch result805B7DF17ECC0AC187B6E61540D6B0278DE752E18E27A4D035F1579BEEE2E025, terminalCA0DACF6, stdout1B9188A7, JUnit and the original585728-byte shard76F4C204 from observed executing Python PID26548. The venv redirector PID3036 and executor were separately observed and are now absent. No combine, JSON generation or formal aggregation occurred; this is neither behavior PASS nor complete accepted measurement. The public-prefix failure is under read-only contract diagnosis by the same owner; product violation is unproven. Static acceptance of572b did not predict runtime success and remains explicitly static.

Actual Monitor execution and S18 did not overlap. This batch adds zero formally accepted coverage branches; U41 and frozen denominators remain unchanged (gaps412/1070/72). Windows successor5C6E5B77 binds seven unchanged test blobs to current RC2 LF source; execution remains environment-blocked by66FA034F. Builds, installation, Repair, rollback, security and physical evidence are retained without rerun. Remaining work is grouped coverage and seven native Windows checks plus final matrix reconciliation; the1.0 goal remains active and unmet.

### U42: accepted checkpoint and Target module evidence, frozen RC2 retained

Code head before this report is5ef06370d2895bd4d8d2bafc6cc922d59c8ba98c. Only the independently reviewed Luna test commits and plan updates were integrated; both product source trees have zero diff against55d91a23a5a2f16fc47d324a9077dfcebf130be9. RC2c71b13f2562985d27b3865e367f6d33334f3a16a, its closed dependency set and the accepted physical/build/install/Repair/rollback/security evidence remain unchanged. Actual installed Monitor startup/authentication/natural stop/public resource reuse is already accepted by the composed evidence; its original failed composite remains FAIL.

S18fd87 run3 closes the public five-checkpoint retry/no-write/revision/show/resume scenario, contributing14 new native branches. Target61f run2 closes public malformed-frame/facade/runner-output rejection and owned-resource cleanup, contributing10 new branches. Its planned456->458 branch is not reached: it requires the same decoder to first record a version mismatch and then a CRC mismatch; ordinary456->457 was already covered. Keep that edge missing, rather than calling it lost measurement or adding an isolated test. The two native invocations took21.2398313s and4.513s, with zero actual overlap. Executing Python PIDs20400 and30524 each have their original retained shard; redirector PIDs are recorded separately. All actual relevant Python coverage is included; native Git helpers do not contain Python product source. These are offline public-provider results, not physical acceptance.

Independent input reviewsA1B09FF696F8236EF105E6D8B61616ECFD419D291F13832E02493C17D8592A88 andB0F441F01D69B4962C3202D8767E434F8D201CA1DB266DE6AF837EF1965D5082 accept behavior/data separately. Failed S18 native runs1/2 and Target run1 remain excluded and preserved. The S18 path-length and tuple/list failures were environment/test-oracle defects; its timestamp precheck failure was a report-only UTC conversion error corrected using the retained raw data. None establishes a product-contract violation or requires another behavior run.

One native U42 aggregation using the unchanged mature helpers completed in6.063s. Manifest30C5154F5CF151AF9F63374EE7B58F5EE00B01788CD87980D3A7642444BE9F6E binds148 sources and the three exact inputs. ResultB8E0CE95844DE9CC827881792AF61CC2DC284C55378C3080C9EF72F023C90F93 has an exact87,283-arc raw union, zero missing/extra arcs, no purge, unchanged originals and exactly24 new Toolkit branches with no removals. Native review0B4ABE3465E6E181DEC072A95D50EAAF75DFDC829778124AE8650D8BB0E0AAC6 accepts the data. The candidate inherited an earlier accepted risk-v2 status while its top-level status was pending; primary admissionBA391993ED478DBC1E798ACDDDF21F6E634C0EFC353EF707B13FDAF86FD262C8 aligns only those report labels at promotion. Immutable candidate62464406AE19B091698C52B860B7C45264F6D8338F61D617FAAEE4346902B576 remains preserved; no metric/raw-data correction or test rerun was needed.

Accepted U42 totals are Toolkit11845/13592=87.1469% overall (388 branches to90%) and risk-v2 11227/12918=86.9097% (1046 to95%). Monitor2725/2944=92.5611% still meets overall90 and needs72 branches for core95. Broad-v1 and UI784/810 are retained in the canonical report; Monitor/UI are unchanged. Seven current-RC2 Windows native checks remain ENVIRONMENT_BLOCKED: this Medium-token host has neither enabled Developer Mode nor SeCreateSymbolicLinkPrivilege. No qualified alternative environment has been verified, and no elevation/system setting change or native-check substitution is authorized. The release is not accepted.

Cost assessment: the current accepted invocations total25.753s and aggregation6.063s; preparation and independent reconciliation dominate wall time. Recent7-24 new branches per comparable group mechanically imply44-150 such groups for the remaining1046 Toolkit core branches, before Monitor and native-environment work. This is a conditional effort warning, not a delivery-date estimate or an assumption that all unknown paths are reachable. Stop isolated low-yield additions: storage25 currently yields only2 medium-cost public candidates; replay's isolated3 remains held. The next low-preparation Monitor group instead covers lock contention, cleanup failure and partial startup with fresh-instance reuse (up to5 arcs); Recovery preparation is restricted to existing generic-v1/shared-context inventories. Unknown paths remain in the frozen denominator. Subsequent new-input and aggregate checks will be reconciled in one independent review per batch, reusing valid source/behavior evidence instead of repeating staged reviews.

### U43: source-evidence refusal/recovery and cleanup-failure native evidence

Code head before this report isf7bed6b067e92d42ec5534c5744bd20300ff2224. The Monitor and Recovery test-only changes were independently reviewed and integrated locally; product55d91a23a5a2f16fc47d324a9077dfcebf130be9, RC2c71b13f2562985d27b3865e367f6d33334f3a16a, dependencies and prior physical/package/install/Repair/rollback/security evidence remain unchanged. No remote action or hardware operation occurred.

Recovery closes the offline public generic-v1 unsupported-input/unchanged-build/missing-declaration refusals with unchanged persistence, legitimate source-edit/declaration/finalization recovery, and exact idempotent begin after diagnosis revision4. Run1 at414400896b41287e5b2cf2975fefb03890a43362 passed and retains the originalF0EEB230 shard, combinedF8F7DDA2 and JSONE80B9794. Run2 at final61ea462617fde1d6c0e83f49afdca363f8526787 failed before pytest because malformed native arguments made coverage.ini the Python target; preserve that infrastructure failure with zero behavior/coverage credit. Primary then invoked the existing CLI directly once: final run3 passed in39.4933s, with executing Python22184 and parent4592 recorded inside that same process. Its original shard was subsequently lost when coverage json auto-combined without --keep-combined. Preserve measurement failureA0A9E9F8; do not claim raw retention for run3. Run3's combined bytes equal run1 byte-for-byte. Independent review accepts retained run1 for native data and run3 only for the changed final assertion. The absent live run1 parent-edge observation is disclosed; the selected product route is in-process with native Git subprocesses, without an expected missing Python worker. Offline producer fixtures are not hardware or real compiler acceptance.

Monitor closes independent cleanup-error handling and fresh-instance recovery through public factories and an actual owned runtime-record directory obstruction. Its invalid-token path reached real service binding and then refused the token. That input did not independently assert original-port release; do not declare that behavioral sub-gate closed. Existing actual installed-package startup/authentication/natural stop/public reuse remains separately accepted. Monitor run1 atb816a7311d007288e628784ec3fcb10ca9e146a9 passed in3.9973s and retains its originalA14B5910 shard, combined93126880 and JSON4FBA15FB. Final1ace4512d3cd7ec9a820160e1f3fec9bdee47eee removes a duplicate test and narrows a name while retaining equivalent bodies; no rerun was required for that maintenance.

Independent review9CBFC7192848A1EAA5E2B5FE8D4994D956A44882188930F95914A857284F2AD6 accepts the complete new-test/behavior/data/aggregate chain once. Manifest07C36E8E binds six native inputs and148 source rows; the known sampler CRLF/LF pair remains explicit. Aggregation84B8CDCD completed in7.406s using existing helpers, with exact87,327 Toolkit and63,053 Monitor raw arcs, unchanged originals/copies and no purge or tests. Primary admission7784A652 updates inherited source-binding/status/inspection annotations only; immutable candidate311CB32B remains preserved. Native counts add Toolkit7 (recovery_workflows956->957,982->983,1130->1131,1139->1146,1183->1204,1204->1205,1400->1401) and Monitor1 (runtime1297->1299), with no removed branches.

Accepted U43 totals are Toolkit11852/13592=87.1984% overall (381 to90%) and risk-v2 11234/12918=86.9639% (1039 to95%); Monitor2726/2944=92.5951% (overall90 met,71 to95%). Broad-core-v1 and UI784/810 remain visible, with unchanged frozen scope. Seven Windows checks still lack an already authorized symlink-capable environment. The final release matrix remains unfinished and releaseAccepted=false.

Actual suites did not overlap: Monitor run1, Recovery run1 and final behavioral run3 total84.7795s, plus0.5323s for the failed pre-pytest entry. The interval from first native start to the independent report was63.4minutes; preparation/reconciliation dominates. Together with U42's24-branch/about55-minute cycle, the current rates mechanically imply roughly45-150hours of comparable serial turnaround for1110 remaining risk branches. This is a cost warning, not a schedule or a claim that unknown paths are reachable; Windows availability and final reconciliation are excluded. Existing Monitor replay3/Probe lease2 proposals are held as low yield. The next fixed scope is one20-minute read-only public Diagnostic store/external-dependency reachability decision; no new implementation is released before a coherent risk family, exact gain basis, budget and recovery oracle are proven.

That Diagnostic decision returned one real filesystem-lock family and only one missing branch409->410; supporting open refusal adds lines only. The53 missing store tuples are unchanged from U40. No SQLite dependency exists, and external OSError alone does not cover the remaining identity/semantic branches. Primary holds the low-yield proposal without new files/tests and moves to a single30-minute feasibility reconciliation of the existing inventories, actual native tuples and environment dependencies. No new product defect, coverage increment, scope exclusion or permission was inferred from this preparation.

### U43 feasibility checkpoint: bounded next families, no new coverage yet

Read-only remaining-feasibility.json A11D9684 binds current native JSON and frozen risk scope622D6DF9. Toolkit has1684 risk gaps and needs1039;865 gaps are outside the nine repeatedly reconciled families. Recovery376 has no newly proven admissible public predecessor group; Target45 keeps static paths separate from accepted U42 evidence. Its old1332->1341 report label is corrected to actual native1332->1333 without rerun. Monitor218 is partitioned without overlap into3 simple public inputs,5 complete public journey candidates,32 earlier-guard/trusted-internal cases,84 conditional environment/provider/lifecycle cases and94 unknowns. The32 are not executable public candidates, the84 are not84 confirmed platform blockers, and no unknown is excluded. Even all8 design-supported Monitor cases leave63 branches to95. The current inventory cannot support a finite completion forecast.

Primary selected the coherent5-tuple replay-import integrity/publication/refusal/recovery family under planddc135aa and the public Diagnostic model/event integrity family under planacb82411. The latter bounded proof identifies up to30 model/reducer targets using ordinary public constructors, wire/digest functions and real create_event/reduce_event prefixes. The same Luna owners now work in isolated w22m/w23d, with one first-error-stopping native validation each, distinct D-root evidence and600-second collection-inclusive budgets. No new native test result or branch credit exists at this checkpoint. Product55d, RC2c71b, canonical U43, all prior accepted package/hardware evidence and the seven-check environment blocker remain unchanged.


### U44: replay-publication native admission and retained incomplete inputs

Independent review B1D5F613 accepts U44 exact native data, requiring report-provenance correction before promotion. Primary admission BB6994B0 corrects inherited method/runtime labels and six derived Toolkit source hashes against manifest85B432B4; frozen risk scope622D6DF9 retains membership and historical hashes with explicit current-source binding. The original pending candidate, all raw shards and the known sampler LF/CRLF qualification remain intact. Canonical F7EDB6F3 now contains the accepted result; no test or aggregation rerun occurred for this correction.

Formal increment: Toolkit0, Monitor4 (replay1234->1235,1333->1334,1333->1338,1382->1383). Totals: Toolkit11852/13592 overall (381 to90), risk11234/12918 (1039 to95); Monitor2730/2944=92.7310% (overall90 met,67 to95). Broad-v1/UI and denominators are unchanged. Native aggregation took7.629seconds; the Monitor suite took21.054seconds. Its first-guard limitation and HOLD execution-order incident remain in the evidence, without retroactive authority or extra coverage credit.

The separate debug-artifact3PASS input measured14 new branches after a collection-only basename correction; it is not yet in this canonical union. Diagnostic run2 retained2PASS/1FAIL with no formal branch credit: ObservationPlan received the unrelated plan_digest key and stale plan_id before the reducer. The new bounded construction design preserves the two passed model scenarios and releases only the remaining reducer verification. All three completed suite intervals were non-overlapping; the maximum remains2. No product defect was demonstrated, product55d/RC2c71b and all unaffected physical/package/install/upgrade/rollback/security evidence remain frozen. Seven Windows-native checks still lack an authorized capable environment; coverage and final release gates remain unmet, releaseAccepted=false.

### U45: accepted debug and Diagnostic native inputs

Code head before this report is41c4e466a91862a2a54efb70d07990eea5c31165. The complete reviewed Debug307c test and Diagnostic01e16 test blob were integrated locally. Both product trees remain equal to55d91a23a5a2f16fc47d324a9077dfcebf130be9; RC2c71b13f2562985d27b3865e367f6d33334f3a16a and applicable physical/build/install/Repair/rollback/security/actual Monitor-use evidence remain frozen. No remote, system-permission or hardware action occurred.

Independent native review1CBB9FDF67244C2C9DC252FDACEC68B400299A564699B5AB2DF95AFE5E852D93 accepts manifest6EDF77700D3C987558E14615FC0D2153E55C1781A028C91175FED09340646289 and aggregation859F5387511DDC51728AC786A4D1FA813D306FF2F89A22C1B400F7F82EF76126. Four original Toolkit inputs and neutral copies retain byte/hash identity; their normalized126-file/87471-arc SQLite union has no missing/extra arcs and no purge. The148-source binding and known sampler newline pair are explicit. Monitor reuses unchanged U44 raw/JSON/metrics. Primary admission31243F5CE823CC99B1416B7A986434658851D12799D0AB8E89D04A1C1C90AE2D normalizes current admission/method/runtime labels while preserving immutable candidate5DD86559DDFB43F6E79F9037E51C243E0EC4F43427CF6B40CCA2F99E0146B654 and historical qualifications. Canonical accepted SHA256 isA898732B8B5B32A1AD1C47C25C2DD224DEA1618072F50B5000D4AF9902254C0F.

Formal increment is39 Toolkit branches: DWARF7, SVD7, Diagnostic events5 and model20. Debug's initial raw-basename discovery failure was repaired from its original shard without rerunning tests. Diagnostic run2 retains two unchanged model PASS cases and one reducer fixture FAIL; final run3 executes only the corrected reducer and passes. Independent composed reviewB894254624548FAF9A9BA6BB91F1412775584ABCB845FC30E6D36E374E750A0A accepts this limited composition. Raw run2 data is not per-test isolated; its original whole-run FAIL is never rewritten. The final reducer uses the public ObservationPlan constructor with canonical coupled IDs. Missing SVD cache and Diagnostic earlier-guard/no-caller targets remain visible, with no exclusions.

Accepted totals: Toolkit11891/13592=87.4853% overall (342 to90), risk-v2 11273/12918=87.2658% (1000 to95); Monitor2730/2944=92.7310% (overall90 met,67 to95). Frozen risk membership90/16, broad-v1, UI784/810 and all denominators are unchanged. Toolkit input runs took2.368,3.449 and2.242 seconds with no overlap; native aggregation took5.817 seconds without tests. The earliest reused Diagnostic run began05:23:10Z and admission completed06:27:55Z, approximately64.8 minutes including nonexclusive preparation/review and U44 work. This improves the observed batch yield but does not justify a delivery date or expanded suite concurrency.

Seven Windows checks remain blocked by the unchanged unsupported token capability; no authorized alternative environment is yet verified. Regeneration is held as low yield; the current18 Sampler gaps are public-invariant dominated and stay in scope. The old physical-reader20-candidate label is narrowed by dispatcher/model proof to6 concrete,8 earlier-guard and6 external/unknown tuples. Next selections use coherent replay-publication, Monitor analysis and persisted-reader public scenarios; no extra coverage is credited for preparation. The final matrix remains incomplete and releaseAccepted=false.

Successor preparation correction: the initial physical-reader six-target label overstated the short rev0/rev1 prefix. Timestamp and inherited-output invariants block those cases before their intended checks. No test code or execution was produced at that stop. The same owner reconciled all six cases once:1727 uses rev0, and the other five use authentic public rev5 plus the public firmware-built-after rev6 checkpoint, then negative persisted mutations with earlier guards preserved. This remains static design support pending runtime evidence, not six new branches or a product defect. Original preparation budget and failure history continue. Monitor Analysis25 yields only four design-supported low-gain candidates and is held. Existing feasibility inventories do not prove the frozen95% target unattainable; Sampler18 belongs to Monitor, and no unknown is excluded. The conditional Toolkit-only turnaround illustration is28-151hours using the actual7-to39 Toolkit branch range; no finite upper bound or release date is established.

### U46: qualified Replay loader evidence; Reader fixture chain held

Code head before this report is6df76440d1d349b558f353f3a9823104ee0862e4. It integrates the exact reviewed final Replay test blob frombe3a331ac92454097fe3933f2dfc090a23b19f17, SHA851EEAC430156A066EAF5FC8E0BE0D9C0FEA8B0FA05A6F9C4A95371A98C8E766. Git checkout initially converted LF to CRLF; Git blob identity matched, and the reviewed LF bytes were restored before commit. Both product trees remain unchanged from55d91a23a5a2f16fc47d324a9077dfcebf130be9. RC2c71b13f2562985d27b3865e367f6d33334f3a16a, dependencies, physical/package/build/install/Repair/rollback/security and actual Monitor-use evidence remain frozen.

Replay run1 failed at the nonhex guard before its uppercase-normalization oracle. Run2 completed all13 loader refusal/no-write/restoration cases, then failed because a redundant positive publication fixture used an operation ID contradicting its immutable stream ID. Both whole-run failures remain recorded. After two fixture failures, primary stopped the local patch chain and simplified the verification method: retain the unchanged executed loader prefix and reuse existing accepted publication/repository evidence. The final test removes only that invalid redundant block and unused imports. Prefix/helper AST proof3B8B40260AA369CAA3905BE442808CF867916D57AFB6E1EF65735499AF147FCE and independent review86D2450EB2550C4193C3E20D6521D4DB8614C694EBC190D577F8ABC2DA289825 qualify this partial behavior. The final test is NOT_RERUN; no whole-test PASS, per-test raw isolation or new positive-publication credit is claimed.

The original run2 shard18549C6AFA7A070306012CB00971B6541034A0B14258A9DC8E362CB8488C88C4 is retained. Its measurement-only combine/json succeeded; a PowerShell summary could not read an empty JSON key, and primary read the JSON directly and proved raw-set equality without repeating tests or collection. U46 manifestE5A24B6F11A72BF314DD1DB6062746093E65A27AD53AB13BDEEBC9261EEE965F combines only accepted U45 Toolkit raw and that original run2 shard. ResultB5D09A96D55199CE09469CF2431EA523B473020E79727460E33DC4A02AEC643F has the exact126-file/87502-arc native union, no purge, unchanged original/copy hashes and148 current source rows with the known sampler newline qualification. No raw-phase filtering occurred. Monitor U44 raw/JSON/metrics are reused unchanged. Primary admission35729A9802E8193199A2FB8D1E5ED0C746E17490805AF52DED18D37676B0DBD6 corrects only current admission/source-pointer labels; immutable candidate67C20CF20C38ACD36734FC7A8498AEECAF6124914F965809B7CCF32C5AA84446 remains retained. Canonical accepted SHA isD9360D6B149A57CE96140E417AFB11810D3CB898930D7D47FD5E025BAE83C59E.

Formal increment is13 Toolkit branches, all in testing/replay.py:110->111,113->114,115->116,132->133,134->135,222->223,228->229,247->248,274->275,277->278,279->280,345->346,370->371. Toolkit overall11904/13592=87.5809% needs329 to90%; risk-v2 11286/12918=87.3665% needs987 to95%. Monitor2730/2944=92.7310% still needs67 to95%. Frozen denominators, broad-v1 and UI784/810 remain unchanged. The four original invocations took4.412,3.853,5.371 and5.666seconds with no overlap; aggregation took5.490seconds without tests. Replay first run to U46 admission took47.3minutes including nonexclusive preparation/review. The previous28-151hour Toolkit-only rate illustration is historical, not a remaining-work forecast; no finite upper bound is justified while public reachability and Windows capability remain unresolved.

Reader run1 failed because the owned fixture parent was absent. Run2 at8aa622144c859510f1f5f30ae690d545cafb8795 created authentic public revision0 but the helper still requested revision1, contrary to the corrected design. The resulting missing-root error preceded all six intended target assertions. Preserve rawFBE8AC7E andC235CE3C plus original failures, exclude both from U46, and record zero target/coverage credit. This is TEST_FIXTURE/implementation omission, not a product-contract violation. The same owner retains the held family; no third constant patch or run is released. The next preparation is a bounded10-minute read-only Monitor evidence-integrity/publication-family decision using existing public compare and fault-injector boundaries, without new tests until its complete graph and recovery oracle are established. Seven Windows checks remain environment-blocked; final acceptance remains PENDING and releaseAccepted=false.

### U47 — Wire integrity and qualified Monitor reference behavior

The exact independently reviewed Wire8d940fc1de05fd2184680ad32f3fce76be20e84d and Monitor selection5ad645412b16816d978ac3c795b6bd56bdf676fa tests are integrated at e01a3a806d51d5437f4637e18761d7a782bc2977. Product55d91a23a5a2f16fc47d324a9077dfcebf130be9 and RC2c71b13f2562985d27b3865e367f6d33334f3a16a remain frozen. Integration proof7A9B5A3CCAA42C9BA46B60009CB42EEADE08A0FB960B9EF54BCF7C7311695DB9 retains actual CRLF test bytes and the identical reviewed LF Git blobs. An initial pre-mutation byte-comparison guard stopped on that newline distinction; only the comparison interpretation changed, with no test or collection repeat.

Wire run1 completed both public input/refusal/restoration scenarios, reaching12/15 proposed branches. The other3 remain held; the owner's unnormalized319-arc comparison is not coverage credit. Monitor run1 failed before its target because the changed-firmware pair lacked a declaration. Run2 atfc08ea9f completed all3 reference envelope/artifact/bytes refusal, no-evidence-write, authentic restoration and idempotent reuse cases. Its first publication fault verified OPERATION_CONFLICT, sanitized message, callback ordering and preservation of preexisting bytes, then failed an oracle that omitted legitimate SQLite WAL/SHM files. Later prefix/root/recovery assertions and the second fault variant did not run. Both original failures remain recorded; no product defect was established. After two fixture/oracle failures, the family was held. Final selection removes the whole failed fault test, retaining the passed function/decorators/helpers AST-identically (C68D88C7E501FD4D6E66A77DB983157C67F5B01121684DA43FA8A39FB6DFD678). Final selection is NOT_RERUN; this does not close fault recovery.

U47 manifestAB169620F4132038A9830B4B66AE39F602D6FDECD6463F3B8C3C548FD9421409 combines each accepted package baseline with complete original Wire550BBE0C and Monitor6D2C57DC shards. No phase filtering, purge, source exclusion or denominator change occurred. Exact native unions have126 files and87540/63141 arcs; all148 source rows match apart from the known sampler newline pair. Original shards and neutral copies are unchanged. Aggregation8A0C1068208283A417D293549FEB753CFCCA6AF17304BFF0C77801C755609000, independent review551BDD00330775A77656B61800F9BDBE6E80D6D382724AF880E69939328562F1 and primary admissionFB79EC904C783F858F83F801F992489098141F1F550E2D15112593CC9934A84E accept the data with those partial-behavior limits. Accepted canonical SHA isB9B22F4E060E62FC7C7A3DAE146A4E0C603532C969193C06C99EE0C938003253.

Formal increments are12 Toolkit branches in monitor_replay_contract.py and4 Monitor branches in analysis_workflows.py (483->492,494->495,501->502,1001->1002). The last is observed execution only, not fault-recovery PASS;1001->1003 remains uncovered. Toolkit11916/13592=87.6692% needs317 to90%; risk-v2 11298/12918=87.4594% needs975 to95%. Monitor2734/2944=92.8668% needs63 to95%. Broad-v1/UI784/810 and frozen scope remain visible. Native invocations total17.504s without overlap; resource peaks were unavailable after exit, not zero. Serial union took8.057s, with no tests. U46-to-U47 admission took60.4minutes; first current native start to admission35.9minutes.

The read-only Recovery audit's initial blanket exclusion of run-owned negative persisted inputs was incorrect: public models, exact refusal/no-write and authentic restoration are allowed; no private guard replacement was found. Existing recoveryPublicRun1 remains BEHAVIOR_RETAINED_MEASUREMENT_VERIFIED_NO_NEW_BRANCH_YIELD. A historical Git label or stale expected registry hash alone does not invalidate the already-qualified actual current source. No recovery rerun follows this audit correction.

After two low-yield batches, the next action is a bounded existing-inventory reachability/cost decision, not another isolated branch patch. Recent observed Toolkit rates mechanically suggest27-82hours for the current deficit if reachable supply and rates persisted; this conditional illustration excludes Monitor and Windows and establishes no release deadline or finite upper bound. The seven Windows checks remain capability-blocked; all unaffected real-package/physical evidence is retained. No remote mutation, hardware operation or denied cleanup occurred. The active1.0 goal and final acceptance remain unfinished.

### 2026-09-22 user-approved Toolkit core threshold amendment

The user explicitly changed only the Toolkit risk-core-v2 release floor from
95% to 90%. Toolkit overall remains 90%; Monitor remains overall 90% and core
95%. Toolkit core 95% is later, non-blocking quality work. It remains unmet,
and this amendment is not a PASS against the former standard. Once all amended
release requirements pass, stop this acceptance effort without starting that
later optimization. UI, Windows seven, all package/physical requirements,
scope membership, denominators, native method and subprocess collection remain
unchanged. No product or test change, test execution or aggregation is caused
by this policy/report update; formally added branches: Toolkit 0, Monitor 0.

The unchanged accepted U47 measurement is
`e/risk-v2/union47/core-coverage-accepted.json`, SHA256
B9B22F4E060E62FC7C7A3DAE146A4E0C603532C969193C06C99EE0C938003253.
Its policy-only derived current report has SHA256
B39E3ADC2E23F27CD657B21E3DC5EA4F3E5C2E9727455C59A35DC7584C80C382.
The amendment and original snapshot are retained under
`e/risk-v2/union47/user-toolkit-core90-20260922/`. All original raw/native,
immutable U47 admission and broad-core-v1 history remain intact.

| Current measure | Accepted branches | Current release gap |
| --- | ---: | ---: |
| Toolkit overall | 11916/13592 = 87.6692% | 317 to 90% |
| Toolkit frozen risk-core-v2 | 11298/12918 = 87.4594% | 329 to 90% |
| Monitor overall/risk-core-v2 | 2734/2944 = 92.8668% | overall met; 63 to core 95% |

The Toolkit gaps overlap and must not be added. Its original risk-core-v2
95% deficit of 975 remains historical and non-blocking. No current release
deadline is inferred from earlier cost illustrations for that larger deficit.

Critical behavior evidence is reconciled separately from percentages:

- Execution refusal: retain accepted Target/Recovery authorization, expiry,
  identity and dispatch-refusal evidence plus RC2 security refusals. An
  additional RC2-specific expiry combination is not a frozen requirement and
  is not added as a new blocker.
- Recovery integrity: retain accepted repeated-request, revision-conflict,
  corrupt-evidence refusal and no-new-root evidence. The pending Acceptance
  public-root group strengthens refusal/restoration across upstream records;
  preparation alone supplies no additional behavioral or coverage credit.
- Resource release: retain existing timeout/cancellation/Observation lifecycle
  and actual installed Monitor stop/reuse evidence. The Windows path-based
  probe lease refusal/cleanup/reacquire evidence mapping is still to be
  reconciled; a historical POSIX-descriptor deferral alone does not prove a
  current Windows behavioral gap. Do not automatically add a new test from
  that label. The seven frozen Windows-native checks remain environment-blocked.
- Rollback and user files: retain the actual RC2 post-promotion state-publication
  failure and restoration PASS. The independent rollback review confirms all
  5778 baseline files, generation 1, project bytes, residue and public Check.
  State replacement itself was refused; post-success state corruption is not
  claimed or newly required by this amendment.
- Evidence identity and complete publication: retain U47 reference-integrity,
  accepted Replay publication and real-package identity results. U47 Monitor
  publication-fault recovery remains unaccepted: its assertions stopped at a
  WAL/SHM file-count oracle, before later root/recovery/idempotence assertions.
  Preserve both failures and the hold after two fixture/oracle failures; no
  third local patch/run is authorized by this amendment.

The next existing batch retains `/root/finalization_binding_impl` and
`/root/union30_native_review`, isolated `r10/w29a`, temp
`D:\codex-tmp\29a1` and `risk-v2/acceptance-existing-public/run1`. It uses the
six unchanged public Acceptance selectors already specified in the release
plan: exact root/upstream refusal, no unintended publication, and the existing
matrix's authentic byte restoration plus identical reread. Preparation budget
10 minutes, one first-error-stopping run capped at 600 seconds; expected 3-11
new branches is a reachability estimate, not credit. Preserve actual child raw
data and assess behavior separately from measurement. Missing source binding,
unexpected first failure, missing raw or timeout stops for classification; the
alternative is a bounded review of that exact public guard, not another held
Reader/publication-fault retry. No run is claimed here.

All accepted RC2 and physical results remain valid within their original scope.
Final acceptance remains pending. The effective goal in the plan and ledger
uses these amended floors. The current Goal backend still exposes the old
paused objective; available tools cannot edit its text or resume it. This
synchronization limitation does not change the user's instruction to continue
local work, and no false completion or replacement goal is recorded.

### U48: public Acceptance evidence refusal and restoration

Code head before this report is b852ed2fd66c6d3fb5e5117f4ef9b2ca127db9d2.
The unchanged public Acceptance selectors ran once at ae40d0f5: corrupt,
missing, misbound, unresolved and nonpassing upstream evidence is refused with
the specified result and no unintended writes. The corruption matrix restores
authentic bytes and obtains the same public reread. All seven cases passed;
elapsed native invocation was 156.266 seconds. This is offline behavior, not
new hardware evidence. No product or existing test file changed.

Actual coverage Python PID11632 is bound to the retained original shard
894D5BA93A8B8FFB6EC97DE15134151AC27F31041A4BBE05022AF7AE71DADDEC.
The venv redirector PID9436 was later reused and is not a surviving test child.
All 148 source files match the accepted-base Git bytes, and match current
integration after LF/CRLF normalization; 141 pairs differ in raw bytes. The
original raw and combined data have equal 24565-arc sets. Existing mature
native functions combined the unchanged U47 inputs and whole original shard
in 8.375 seconds, with no test rerun or raw filtering.

Independent review ED982357AF469CB78C89C47C7C4917F6A061FEE8AC5147FC39AA73AB51E4E887
accepts manifest CDEF247A5C18008B33081094AE2F805219766BBF11CDAD87FFEE7345F449AA01
and aggregation D051CA83EF496063942B7CA08174A2EDCCCEA967000134A7BE4D28C2C873AE99.
Primary admission 2DFA7F9646390F757347CE69AD290CB3886E99F6DE3F11EAC403F275CCAB8B3E
binds the exact 126-file unions (87582/63230 arcs), unchanged inputs/copies,
source representation and user-approved policy. Accepted report SHA256 is
7C0186CD156934ADE17010CD3C9D65C68C72F023909FCCA5275515983D873862.

Formal increment is Toolkit 11, Monitor 0. All new branches are in
acceptance/workflows.py: 190->191,195->197,226->227,226->234,227->228,228->230,
248->249,249->250,423->424,451->458,527->529. Toolkit overall11927/13592
(87.7501%) needs306 to90; risk-v2 11309/12918 (87.5445%) needs318 to90.
Monitor2734/2944 still needs63 to95. Original Toolkit95 unmet history975,
current later-quality gap964, broad-v1, UI and all denominators are retained.

Independent scoped review also permits reuse of the named accepted baseline
analysis assertions in analysis-evidence-integrity/accepted-baseline-reuse.json
(97B9F88D): artifact-failure refusal and retry, partial marker repair/reload/
idempotence, and conflicting-root no-write refusal. Relevant production bytes
and exercised helper behavior remain applicable. This adds zero coverage and
does not close the separate held U47 root.after_publish fault variants.

The Windows public-authority supplement remains independently pending at this
checkpoint. Its first generated-launcher attempt failed before pytest; the
same owner switched to the proven direct entry, preserving that failure.
The separate seven Windows-native checks remain capability-blocked. A bounded
creation/import failure audit found the proposed rollback/user-file scenarios
already covered, so no duplicate supplement is released. Product55d, RC2c71b
and all unaffected physical/package/build/install/Repair/rollback/security/use
results remain accepted within scope. The Goal backend is now active; its old
objective text does not supersede the explicit Toolkit90 policy amendment.
Final acceptance remains incomplete.


### Windows public authority refusal and reuse accepted

Code head before this report is3cb3b748fb9d29ad40841c1c364c7223034acb09.
It integrates the complete test-only diff27dd55e..875a4ff9 after independent
review53038FC0F480435C413ABB2862047BE609503A903B0E1C0F7D63DE5E4F572F16.
The two actual Windows refusal/reuse cases passed in4.32seconds: registry-file
and guard-directory obstructions fail before firmware binding, preserve the
project/refusal artifacts, close the external backend and clear the real
supervisor endpoint. The awaited production rollback precedes asyncio.run
shutdown. Removal of each owned obstruction permits two public default-manager
acquire/release cycles. No direct TCP close probe or stale-owner health reclaim
is claimed, and no hardware was accessed.

Primary admission5C8EEE4CDDB425FE69F854991F61F5C8D6C4426EE5766E191420622B58425808
binds the reviewed test and runtime evidence. The executed and integrated test
have the same Git blob, normalized bytes and AST; checkout raw hashes differ
only by LF/CRLF. All148 production files are normalized-equal,147 raw-equal.
Original shard848CCA3D and corrected combined1C3568BC contain equal108-file,
11106-arc sets. Monitor was configured but never imported and supplies no data
or credit. Original run1 launcher failure and stale default-path report are
retained; corrected measurement/shard sidecars govern without a test rerun.
The additional Toolkit lease932->934 arc is held for the next serial union,
so formal totals remain U48:11 new Toolkit,0Monitor, gaps306/318/63.

The U48 canonical/ledger promotion preserves every accepted package, physical,
UI/performance and recovery result. One stale final-matrix pending-requirement
string was corrected from Toolkit core95 to the user-approved90; the before
snapshot and original95 unmet history remain. Resource-release evidence now
includes this Windows public scenario. Named baseline Monitor publication,
repair and retry evidence remains applicable; held U47 fault variants do not
become PASS. The seven separate Windows-native checks still require a capable
authorized environment. Product55d and RC2c71b remain frozen.

No new product defect is demonstrated. The next bounded work is a20-minute
public-reachability assessment of each Recovery and Replay group by existing
owners, using existing gap maps and fixtures. Creation/import rollback and
file-preservation scenarios were already covered, so no duplicate suite is
added. Only a coherent, reachable and previously unverified risk group can
release another supplement. No final release acceptance or95 optimization is
claimed.
