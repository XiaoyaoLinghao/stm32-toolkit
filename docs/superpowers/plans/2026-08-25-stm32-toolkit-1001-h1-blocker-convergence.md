# STM32TK-1001 H1 Blocker Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. The repository ownership rule overrides the skill's fresh-agent default: the same existing GPT-5.6-luna/max implementer owns every implementation task, and GPT-5.6-sol reviews each complete task diff.

**Goal:** Correct the generic Keil inspect/SPL behavior exposed by the real project, rebuild the exact candidate, apply one digest-bound project portability correction, and complete reproducible no-hardware H1 as P1c.

**Architecture:** Toolkit keeps one public inspect/convert/configure/build path and gains only two conservative parser/evidence fixes. Unknown encodings and ARM assembly remain rejected by Toolkit; the named campaign project handles them in a preserved, derived GCC profile whose exact diff is authorized before apply.

**Tech Stack:** CPython 3.12.10, pytest, `xml.etree.ElementTree`, STM32 Toolkit 0.9.0, local Git, strict GB18030/UTF-8, ARM GCC 14.3.1, CMake 4.3.1, Ninja 1.13.2.

## Global Constraints

- Accepted Toolkit base is `12d0d3be1f59a5ed44b84a1244575cb853b97173`; project P0 is `e7b2408fb615748ca5d67a2006f31e2377a09942` with no remote.
- One existing GPT-5.6-luna/max agent implements all product and project changes; GPT-5.6-sol independently reviews and accepts. The implementer never approves its own diff.
- Use only CPython `>=3.12,<3.13`, the exact campaign candidate/runtime, explicit roots, and the H0-pinned CubeCLT paths.
- No Agent-specific logic, second runtime/MCP/provider/backend/controller, Python range, CI, collaboration automation, private conversion/build bypass, or system Monitor.
- No Probe/PyOCD/open/attach/reset/flash/read, no golden write, and no remote mutation in this plan.
- The original uvprojx, ARMCC startup, historical Keil outputs, D4/test logic, and non-volatile `testtime` remain unchanged. No mailbox or instrumentation is introduced.
- After each check, remove only its exact disposable basetemp/scratch after preserving minimum failure evidence; retain formal campaign evidence and P1c artifacts needed by Task 7.

## File map

- Modify `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py`: standard output-field nesting, listing-directory MAP path, and generic SPL source-set evidence.
- Modify `tools/stm32-toolkit/tests/test_keil_inspect.py`: core RED/GREEN tests for both fixes and ambiguity/containment boundaries.
- Modify `tools/stm32-toolkit/tests/test_keil_baseline.py`: real split OBJ/LIST baseline capture and fallback behavior.
- Modify `tools/stm32-toolkit/tests/test_migration_plan.py`: corrected SPL project reaches planning while encoding/assembly still fail closed.
- Modify only if directly required for thin parity assertions: `tools/stm32-toolkit/tests/test_workflows.py`, `test_cli.py`, `test_mcp_server.py`, or `test_mcp_migration_build.py`; no production CLI/MCP schema change is expected.
- Create in the campaign project after digest approval: `Project/LWIP.gcc.uvprojx` and `Migration/startup_stm32f429xx.c`; mechanically normalize exactly 36 frozen source paths.
- Create campaign evidence: corrected inspection/conversion/configuration/build records, portability proposal/authorization/correction, vector equivalence, `memory-comparison.json`, and `p1c.json`.

---

### Task 1: Resolve standard Keil AXF/MAP paths

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py:840-870`
- Test: `tools/stm32-toolkit/tests/test_keil_inspect.py`
- Test: `tools/stm32-toolkit/tests/test_keil_baseline.py`

**Interfaces:**
- Consumes: `TargetOption/TargetCommonOption` selected by `inspect_keil`.
- Produces: unchanged `KeilOutputSettings` shape with correct `object_directory`, `listing_directory`, `output_name`, `axf`, and `map_file`.

- [ ] **Step 1: Add real-nesting RED tests.** Build a fixture with `OutputDirectory=.\OBJ\`, `OutputName=LWIP`, and `ListingPath=.\LIST\` under `TargetCommonOption`; place minimal readable `OBJ/LWIP.axf` and valid fixture `LIST/LWIP.map`. Assert:

```python
assert inspection.output.object_directory == "OBJ"
assert inspection.output.listing_directory == "LIST"
assert inspection.output.output_name == "LWIP"
assert inspection.output.axf == "OBJ/LWIP.axf"
assert inspection.output.map_file == "LIST/LWIP.map"
assert baseline.axf.path == "OBJ/LWIP.axf"
assert baseline.map_file.path == "LIST/LWIP.map"
```

- [ ] **Step 2: Add fallback and security RED tests.** With no `ListingPath`, assert MAP falls back to `OBJ/LWIP.map`. Keep traversal/absolute path cases failing with the existing stable containment code; no filesystem basename search is allowed.
- [ ] **Step 3: Run RED.** Run the exact new nodes with `py -3.12 -m pytest ... -q -o addopts='' --basetemp C:\tmp\vs10a-h1-t1-red`; expect null output paths or wrong OBJ MAP path at base.
- [ ] **Step 4: Implement the minimal parser fix.** Read all three fields from `common`; compute:

```python
map_directory = listing_directory or object_directory
map_file = f"{map_directory}/{output_name}.map" if map_directory and output_name else None
```

Retain `_normalize_keil_path` and all existing containment behavior.
- [ ] **Step 5: Run GREEN and affected regression.** Run new tests plus all of `test_keil_inspect.py` and `test_keil_baseline.py`; require PASS. Remove only the exact RED/GREEN basetemps after checking resolved paths.
- [ ] **Step 6: Commit.** Commit only the parser and its tests as `fix(vs10a): resolve standard Keil output paths`.

### Task 2: Select SPL from a conservative source-set signature

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py:704-770`
- Test: `tools/stm32-toolkit/tests/test_keil_inspect.py:1339-1520`
- Test: `tools/stm32-toolkit/tests/test_migration_plan.py:1416-1435`

**Interfaces:**
- Consumes: included `KeilSource` records already normalized by inspection.
- Produces: one `KeilEvidence(category="source", value="standard-peripheral-source-set", framework="spl")` only for the exact two-file-class signature in the design.

- [ ] **Step 1: Add source-set RED tests.** Cover `USE_STDPERIPH_DRIVER` + included `misc.c` + `stm32f4xx_gpio.c` selecting SPL and removing only the framework blocker from migration planning.
- [ ] **Step 2: Add fail-closed RED tests.** Parameterize lone define, lone `misc.c`, lone peripheral source, `stm32f4xx_it.c`, `system_stm32f4xx.c`, `_hal_`, `_ll_`, excluded sources, and mixed qualified HAL/SPL evidence. Assert no false SPL selection and unchanged warning/blocker semantics.
- [ ] **Step 3: Run RED.** Run exact new nodes with `--basetemp C:\tmp\vs10a-h1-t2-red`; expect the real positive case to remain framework-null at base.
- [ ] **Step 4: Implement the minimal evidence helper.** Require an ASCII basename and lowercase membership in the design's exact 29-name STM32F4 SPL set; require both source classes before appending the one stable evidence item. Do not form a family/peripheral cross-product, use Unicode-aware case folding, inspect directory/project names, or add a public option.
- [ ] **Step 5: Run GREEN and focused parity.** Run `test_keil_inspect.py`, the framework/migration nodes, `test_workflows.py -k inspect`, `test_cli.py -k keil`, and the existing MCP inspect/migration nodes. Run `git diff --check` and verify no public schema/tool count change.
- [ ] **Step 6: Write `task-6r-toolkit-report.md` and commit.** Record Task 1 base, current head before report commit, tests, changed paths, cleanup, and no project/hardware/remote action; commit as `fix(vs10a): recognize canonical SPL source sets`.
- [ ] **Step 7: Stop for Sol review.** Sol reviews the complete `12d0d3be..Task2Head` diff in a clean exact-head worktree. Any finding returns to the same Luna/max agent; no candidate/project work begins before `ACCEPTED`.

### Task 3: Rebuild and replace the campaign candidate

**Files:**
- Create: campaign `runtime/replacement-candidate/` and `runtime/replacement-candidate-extracted/stm32-toolkit-0.9.0/`.
- Modify: campaign `data/runtime/runtime-state.json` only through the shipped setup helper.
- Create: `evidence/toolkit-correction.json`, replacement candidate/build/verify/runtime records.

**Interfaces:**
- Consumes: Sol-accepted clean Toolkit CodeHead and the previously pinned 66-wheel closed wheelhouse inputs by exact hashes.
- Produces: one verified 0.9.0 candidate and one active managed runtime whose `sourceCommit` is that CodeHead.

- [ ] **Step 1: Freeze the final source-identity diagnostic preconditions.** Record CodeHead/status, design/plan SHAs, old candidate/runtime identity, Python 3.12.10/OpenSSL versions, empty campaign scratch, official PyPI SHA-256/BLAKE2b-256/MD5 metadata, exact URL, and both prior response/evidence digests. Require runtime/project/golden/remote/hardware state still unchanged.
- [ ] **Step 2: Perform the one final evidence-only wheel request.** Use the same frozen interpreter with `-I`, standard-library `urllib.request`, a redirect handler that raises on every redirect, and the exact URL. Write only to `C:\tmp\stm32tk-vs10a-legacy-campaign\scratch\task-6r-wheel-multidigest-20260825\wheel-0.48.0-py3-none-any.whl`. Require HTTP 200, final URL equality, `Content-Length=33320`, size 33320, and the same 20-member ZIP with `ZipFile.testzip() is None`.
- [ ] **Step 3: Compute independent actual-byte identity and wheel integrity.** Compute lowercase SHA-256, BLAKE2b-256, and MD5 from the retained file. Require SHA-256 to reproduce `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`; compare BLAKE2b-256 to `2e2969cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449` and MD5 to `75e4bbe15fefadbb91258c5e79b38aa3`. Parse the wheel `RECORD`: every non-`RECORD` member must have the declared `sha256=` URL-safe-base64 digest and exact size; `RECORD` must have empty hash/size. Record every gate and member count in `evidence/task-6r-wheel-multidigest.json`.
- [ ] **Step 4: Stop for Sol source-identity reconciliation.** Do not reacquire setuptools, form the wheelhouse, build a candidate, retire/bootstrap runtime, inspect P0, mutate the project, access hardware, or perform a remote action. Retain the exact diagnostic wheel only when every non-SHA gate passes; otherwise preserve minimum evidence and remove the exact scratch tree. Sol independently verifies actual-byte digests, archive/RECORD results, response provenance, and prior mismatch history. Only a new explicit spec/plan authorization may correct the SHA anchor and resume Step 5.
- [ ] **Step 5: Resolve the classified input blocker under the single-use Sol authorization.** Recheck the retained wheel is size 33320, corrected SHA-256 `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`, BLAKE2b-256 `2e2969cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449`, and MD5 `75e4bbe15fefadbb91258c5e79b38aa3`; recheck authorization CodeHead/P0/runtime/evidence pins before copy. Copy that retained exact file into the temporary closed wheelhouse, reacquire the already-passing setuptools wheel once through the same CPython transport and exact tuple gates, and require the final set to contain the original 64 runtime wheels plus exactly those two backends. Preserve correction/recovery evidence and clean only the exact diagnostic/recovery scratch roots after copy-in. Any drift stops.
- [ ] **Step 6: Build from a canonical CRLF detached worktree.** Reuse the accepted Task 5 pattern, require source/wheel member equality and bootstrap trust-anchor equality before invoking `build_0900_artifacts.py build` with all default verifiers enabled.
- [ ] **Step 7: Verify candidate.** Require 12/12 checksums, collision-safe extraction, `verify-bundle status=ok`, release manifest sourceCommit/utility hashes, SBOM/licenses/compatibility/troubleshooting/Monitor asset presence, and Toolkit/Monitor wheel binding.
- [ ] **Step 8: Replace the campaign runtime without violating same-version security.** First preserve the old runtime-state, release-manifest, package hashes, and no-process proof. Do not run upgrade or repair with different bytes under the same `0.9.0` version. Resolve and verify the exact campaign-managed `data/runtime` path under the campaign root, clear only its read-only attributes, remove that exact retired runtime tree, verify absence, then use only the replacement candidate's extracted `setup-stm32-env.ps1 -Mode Bootstrap` with explicit ToolkitRoot/DataRoot/ProjectRoot. Require a fresh state with `activeVersion=highestInstalledVersion=0.9.0`, install generation 1, new sourceCommit/manifest SHA, Python isolated imports under managed site-packages, doctor `ok=true`, 8 Skills, and 48 MCP tools. There must be no second active runtime.
- [ ] **Step 9: Rerun unchanged-P0 inspect/dry-run.** Require baseline paths/hashes for `Project/OBJ/LWIP.axf` and `Project/LIST/LWIP.map`, `framework=spl`, and exactly 37 remaining blockers: the frozen 36 encodings plus one ARMCC assembly. Any different set stops.
- [ ] **Step 10: Preserve evidence and clean.** Remove only the exact detached build worktree, wheelhouse, extraction diagnostics, and basetemps after recording hashes. Retain old/new candidate lineage and the active extracted Toolkit root. Write `task-6r-candidate-report.md`; do not touch project P0.

### Task 2b: Parse ARM linker image-component program sizes

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/keil/baseline.py`.
- Modify: `tools/stm32-toolkit/tests/test_keil_baseline.py`.
- Modify only if public parity needs an explicit regression: existing Keil inspect/workflow/CLI/MCP tests.
- Create: SDD `task-2b-report.md`.

**Interfaces:**
- Consumes: contained UTF-8 MAP bytes and the existing `KeilProgramSize`/`KEIL_MAP_INVALID` contract.
- Produces: the same `KeilProgramSize` type from either the existing `Program Size` line or the design's exact ARM linker component-totals section.

- [ ] **Step 1: Add the real-format RED test.** Use a minimal generic MAP fixture with exact component header, six-column `Grand Totals` row `62772 5540 1004 1576 406440 534601`, `Total RO Size 63776`, and `Total RW Size 408016`. Assert Code/RO/RW/ZI `62772/1004/1576/406440` and derived ROM/RAM `65352/408016`. Run only the new node with exact basetemp; base must fail with `programSize`.
- [ ] **Step 2: Add fail-closed RED cases.** Cover a totals row without the exact section/header, five or seven columns, multiple totals, uint64 overflow, missing RO/RW cross-checks, incorrect RO/RW cross-checks, and conflicting classic/component tuples. Preserve existing classic `Program Size` tests unchanged.
- [ ] **Step 3: Implement the minimal fallback.** Parse ASCII decimal values only inside the bounded exact component section. Map columns 1/3/4/5 to Code/RO/RW/ZI, validate columns 2/6 but do not publish them, require the two arithmetic cross-checks, and reuse stable `KEIL_MAP_INVALID` with explicit bounded `rule` values. Do not inspect project/path/object names or add a public field.
- [ ] **Step 4: Run focused GREEN and affected parity.** Run all `test_keil_baseline.py`, focused Keil inspect/migration/workflow/CLI/MCP baseline nodes, `git diff --check`, and a direct read-only parse of the copied P0 MAP fixture only if the fixture is copied into an exact basetemp. Remove exact basetemps after evidence.
- [ ] **Step 5: Commit and report.** Record accepted base `171a46060225479a6031c2499cbb6298e4b83d6a`, code head before report, RED/GREEN counts, changed paths, cleanup, and no candidate/runtime/project/hardware/remote action. Commit only the bounded product/tests as `fix(vs10a): parse ARM linker component totals`.
- [ ] **Step 6: Stop for complete Sol review.** Sol reviews the complete `12d0d3be1f59a5ed44b84a1244575cb853b97173..Task2bHead` product diff in a clean exact-head worktree, reruns only focused affected checks, and returns one verdict. Task 3b cannot begin before `ACCEPTED`.

### Task 3b: Rebuild the map-fix candidate and close unchanged-P0 inspect

**Files:**
- Create: campaign `runtime/mapfix-candidate/` and `runtime/mapfix-candidate-extracted/stm32-toolkit-0.9.0/`.
- Replace: campaign `data/runtime/` only through exact retirement plus fresh Bootstrap after candidate acceptance.
- Create: map-fix backend recovery/build/verify/runtime/inspect/dry-run evidence and final `task-6r-mapfix-report.md`.

**Interfaces:**
- Consumes: independently accepted Task 2b head, current `171a4606...` candidate/runtime lineage, frozen 64 runtime wheels, and the exact two backend identities in design Section 7.5.
- Produces: one verified map-fix candidate, one active matching runtime, and unchanged-P0 public evidence with real baseline/SPL/exact 37 blockers.

- [ ] **Step 1: Freeze invalidation and recovery preconditions.** Record accepted Task 2b CodeHead, current candidate/runtime state/manifests/hashes, P0/head/tree/status/no remote, empty scratch, and exact official URLs/filenames/sizes/digests. Make exactly one CPython/OpenSSL direct request per backend into a new exact scratch root, reject redirects, and require the corrected wheel SHA+BLAKE2b plus setuptools SHA. No other network operation is permitted.
- [ ] **Step 2: Form and verify the temporary 66-wheel set.** Copy the retained 64 runtime wheels plus only the two verified backends; require exact count, closed filename/hash manifest, zero missing/extra/mismatch/reparse. Preserve acquisition/member evidence.
- [ ] **Step 3: Build from a canonical CRLF detached head.** Create one clean detached `core.autocrlf=true` worktree at the exact Task 2b CodeHead. Require 117 Toolkit and 25 Monitor source/wheel member equality, changed `baseline.py` equality, source archive equality, and utility/policy trust anchors before invoking the default builder into `runtime/mapfix-candidate`.
- [ ] **Step 4: Verify and extract the candidate.** Require exit `0`, 13 top files, 12/12 checksums, collision-safe two-root extraction, byte-equal duplicated release trees, shipped `verify-bundle status=ok`, exact sourceCommit/manifest/utility/policy, 64 runtime wheels, required release assets, product bindings, 48 MCP tools, and 8 Skills.
- [ ] **Step 5: Fresh-replace the managed runtime.** Preserve current `171a4606...` runtime state/manifest/package hashes and no-process proof. Resolve/check/remove only exact campaign `data/runtime`, then Bootstrap the map-fix candidate with explicit ToolkitRoot/DataRoot/ProjectRoot. Require one 0.9.0 runtime, generation 1, exact new sourceCommit/manifest, CPython 3.12.10 isolated imports, doctor `ok=true`, 8 Skills, 48 MCP tools, no staging/second runtime, and unchanged P0.
- [ ] **Step 6: Run unchanged-P0 public inspect and dry-run.** Preserve before/after P0 and historical hashes. Require AXF `Project/OBJ/LWIP.axf` SHA-256 `65f5b98c970befbea2c7fd529f54a51438b3c635d794e20519d284c33976c225`, MAP `Project/LIST/LWIP.map` SHA-256 `6fca9fc30bd964f81da0c2417d46fe6930f6317ce96ee30d63fbf2981e8bbe9f`, design Section 4.4 exact program sizes, F429ZG, SPL from define+source evidence, and exactly 37 blockers: the frozen 36 encodings plus one ARMCC assembly, with no framework/other blocker.
- [ ] **Step 7: Clean, report, and stop for Sol review.** Remove only exact detached worktree, acquisition/wheelhouse/source-binding roots and disposable diagnostics after evidence. Retain all candidate/runtime lineages and formal evidence; scratch ends empty, Toolkit/P0 clean, no hardware/remote. Sol reconciles Task 2b product diff and all Task 3b evidence before Task 4.

### Task 2c: Reject unrepresentable scoped Keil compiler options

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`.
- Modify: `tools/stm32-toolkit/tests/test_migration_plan.py` and only directly required public parity tests.
- Create: SDD `task-2c-report.md`.

**Interfaces:**
- Consumes: accepted Toolkit head `7c28986406f8932e96c3976b7e925bfd1c2eba44` and existing `KeilInspection.scoped_options`.
- Produces: stable fail-closed `ARMCC_OPTION_UNSUPPORTED` blockers for non-target scoped defines/include paths/misc controls; no new schema/model/CLI/MCP field.

- [ ] **Step 1: Add focused RED tests.** Construct minimal convertible inspections/projects with include-only group options and define-only file options. Require exactly one blocker per scoped option record, file path only for file scope, empty path for group scope, line/column zero, and evidence `scope:<owner>`. Add mixed-field, two-group deterministic-order, target defines/includes supported, and target/group/file misc-regression cases. Base must show the scoped include/define cases incorrectly plan without those blockers.
- [ ] **Step 2: Implement the minimal planner gate.** For target scope, preserve supported defines/includes and reject only misc as today. For group/file scope, reject the record when any defines, include paths, or misc controls are non-empty. Do not merge, normalize away, special-case duplicates, or inspect project names/paths.
- [ ] **Step 3: Run focused GREEN and affected parity.** Run the new nodes, all migration-plan tests, and only workflow/CLI/MCP nodes that assert blocker parity; run `git diff --check`. Use exact basetemps and clean them after evidence.
- [ ] **Step 4: Commit and report.** Commit only product/tests as `fix(vs10a): reject scoped Keil compiler options`; record accepted base, code head before report, RED/GREEN counts, exact paths, cleanup, and no candidate/runtime/project/hardware/remote mutation.
- [ ] **Step 5: Stop for Sol complete review.** Sol reviews `7c28986406f8932e96c3976b7e925bfd1c2eba44..Task2cHead` and the cumulative `12d0d3be1f59a5ed44b84a1244575cb853b97173..Task2cHead`, reruns only focused applicable checks, and accepts before Task 3c.

### Task 3c: Rebuild the scoped-option candidate/runtime and prove the eleven blockers

**Files:**
- Create: campaign `runtime/scoped-options-candidate/` and `runtime/scoped-options-candidate-extracted/stm32-toolkit-0.9.0/`.
- Replace: campaign `data/runtime/` only through exact retirement plus fresh Bootstrap after candidate acceptance.
- Create: scoped-option rebuild/runtime/unchanged-project evidence and report.

**Interfaces:**
- Consumes: independently accepted Task 2c head, map-fix candidate/runtime lineage, frozen 64 runtime wheels, and exact Section 7.6 backend identities.
- Produces: one verified replacement candidate, one matching active runtime, and unchanged `b83b404...` public evidence with exactly eleven blockers.

- [ ] **Step 1: Freeze preconditions and acquire only two backends.** Record Task2c CodeHead/status, all candidate/runtime/project identities, empty scratch, and accepted backend URLs/sizes/digests. Make one redirect-rejecting direct request per backend and require exact filename/hash/archive identity; no resolver/index/dependencies.
- [ ] **Step 2: Build and verify from a canonical CRLF detached head.** Form the exact 66-wheel closed set, prove source/wheel/archive/trust-anchor bindings, invoke the default builder into the distinct scoped-options path, and require the complete prior 13-file/12-checksum/release/SBOM/licenses/compatibility/troubleshooting/Monitor/48-MCP/8-Skills verification inventory.
- [ ] **Step 3: Fresh-replace the campaign runtime.** Preserve the map-fix runtime identity and no-process proof; resolve/remove only exact campaign `data/runtime`; bootstrap only from the accepted extracted replacement with explicit roots. Require one 0.9.0 generation-1 runtime, exact new sourceCommit/manifest, CPython 3.12.10 isolated imports, doctor OK, and no staging/second runtime.
- [ ] **Step 4: Verify unchanged project behavior.** On clean/no-remote `b83b404c8da6993658586fa1b553d715f95993c1`, public inspect must retain exact AXF/MAP hashes, program sizes, F429ZG, SPL, 53 selected C units, 37 target includes, and the two group scoped options. Two public convert dry-runs must be deterministic and return exactly eleven blockers, including distinct `group:Main` and `group:USER` `ARMCC_OPTION_UNSUPPORTED` findings.
- [ ] **Step 5: Clean, report, and stop for Sol review.** Remove only exact build/acquisition/basetemp scratch after preserving formal evidence; project/Toolkit clean, no hardware/remote, scratch empty. Sol reconciles candidate/runtime/source binding before the five-path project proposal resumes.

### Task 4: Propose and authorize the exact project portability correction

**Files:**
- Create in scratch only: proposed UTF-8 source copies, proposed `Project/LWIP.gcc.uvprojx`, proposed `Migration/startup_stm32f429xx.c`.
- Create: `evidence/portability-proposal.json`.
- Create after Sol acceptance: `evidence/portability-authorization.json`.

**Interfaces:**
- Consumes: unchanged P0, exact 37-blocker plan, original XML/startup hashes.
- Produces: one canonical Git binary diff SHA-256 and a closed manifest of target paths/before/after hashes; it does not mutate P0.

- [ ] **Step 1: Verify all encoding preconditions in scratch.** Require exactly 36 unique blocker paths and strict UTF-8 failure for every original. For the exact 34-path strict set, this round trip must hold:

```python
decoded = original.decode("gb18030", errors="strict")
assert decoded.encode("gb18030", errors="strict") == original
converted = decoded.encode("utf-8", errors="strict")
assert converted.decode("utf-8", errors="strict") == decoded
```

For the two Section 5.1 pinned inputs, require exact path/size/SHA and the exact thirteen one-byte failure offset/value pairs. Use the frozen GB18030 valid-span decoder with literal ASCII `\xHH` emission only for those invalid bytes; require every event to occur after an optional-whitespace full-line `//`, no line continuation, no replacement character, strict UTF-8 output, identical valid-span scalars and newline characters, a reversible event manifest, and unchanged token-bearing text. Preserve decoded newline characters and record before/after/text or valid-span digests plus the conversion mode. Any path/hash/event drift stops before proposal generation.
- [ ] **Step 2: Create and validate the derived profile in scratch.** Parse the original securely, copy it, and change exactly one selected source node from `Startup_config/startup_stm32f429_439xx.s` to `Migration/startup_stm32f429xx.c` with C type. Normalize neither unrelated XML nor original project bytes. A semantic comparison must prove all other selected-target fields and source ordering equal.
- [ ] **Step 3: Create the C startup proposal.** Transcribe all original DCD vector entries in exact order, use `0x20030000` initial SP, implement data copy/BSS zero/SystemInit/main, and weak aliases. Parse both files to assert equal vector count/names/reserved slots and exactly one strong project `TIM3_IRQHandler` candidate.
- [ ] **Step 4: Compile the startup proposal in scratch.** Invoke only the frozen ARM GCC for a compile-only syntax/object check using the project CMSIS include/defines. Inspect the object for `.isr_vector`, Thumb `Reset_Handler`, and undefined linker boundary symbols expected from the managed linker.
- [ ] **Step 5: Build the canonical proposal digest without applying.** Materialize a temporary Git worktree/copy at P0, apply only proposed bytes there, run `git diff --binary --full-index P0`, hash those exact bytes, and record closed path lists, sizes/hashes, invariants, commands, and result in `portability-proposal.json`. Remove the temporary proposal tree after preserving the diff bytes in formal evidence.
- [ ] **Step 6: Return for Sol authorization.** Sol independently verifies that the digest changes exactly 38 paths: 36 encoding-normalized files plus the two new files, with the original uvprojx/startup untouched. Sol writes authorization binding P0, proposal schema, exact diff SHA-256, allowed paths, and standing user direction. Any mismatch requires a new proposal; no mutation is allowed yet.

### Task 5: Apply portability correction and complete guarded P1c H1

**Files:**
- Modify: exactly the authorized 36 campaign project sources.
- Create: campaign project `Project/LWIP.gcc.uvprojx`, `Migration/startup_stm32f429xx.c`.
- Create/modify: Toolkit-managed project files only through exact conversion/configuration plans.
- Create: corrected formal H1 evidence, `memory-comparison.json`, `p1c.json`, `task-6-report.md`.

**Interfaces:**
- Consumes: single-use exact portability authorization and accepted replacement candidate/runtime.
- Produces: clean local P1c commit/tree and two byte-identical public firmware builds eligible for Task 7 review.

- [ ] **Step 1: Apply only the authorized bytes.** Recheck P0/head/tree/status/no-remote and current input hashes; apply the preserved exact diff; recompute its SHA and require authorization equality. Commit the portability input locally. If any pin drifts, reject without partial apply.
- [ ] **Step 1b: Converge the revealed five-path ARMCC/GCC/project-profile correction before retrying Step 2.** Treat the retained three-path and four-path-v2 proposals as diagnosis-only `PROJECT_INPUT/BLOCKED`; neither can be authorized or applied. After Task 2c/3c acceptance, from clean portability commit `b83b404c8da6993658586fa1b553d715f95993c1`, create a replacement scratch-only proposal for exactly `Common/common.c`, `MALLOC/malloc.c`, `USER/usart1/usart1.c`, `Main/string.h`, and `Project/LWIP.gcc.uvprojx` under design Sections 4.5, 5.2, and 5.4. Preserve the complete legacy ARMCC header body byte-for-byte behind an outer non-GNU branch and make only the GNU branch forward with `#include_next` to the pinned CubeCLT newlib header. In the derived profile correct the startup path to `..\Migration\startup_stm32f429xx.c`, add target include `..\USER\IWDG` exactly once, and clear only the `Main`/`USER` group include values; prove the unique-header/global-promotion facts and original uvprojx identity. Compile the three directly corrected units and inspect intrinsic/allocator facts; then compile every selected C source in isolation with the corrected frozen contract and prove all selected `string.h` consumers traverse the forwarding header to CubeCLT newlib. Any compile error stops with classified evidence; warnings are recorded. In a disposable exact project worktree, require public inspect PASS with no non-target scoped options and two identical public convert dry-runs with zero blockers. Preserve one canonical five-path `git diff --binary --full-index`, closed before/after hashes, dependency-resolution evidence, and self-contained v3 evidence; remove scratch. Sol independently verifies and writes an exact digest authorization. Only then apply the identical diff to the campaign project, commit locally, and record authorization consumption. No conversion apply, configuration, build, hardware, or remote action is allowed before that commit.
- [ ] **Step 2: Rerun public inspect and convert dry-run on `Project/LWIP.gcc.uvprojx`.** Require real baseline, F429ZG, SPL, one startup, 0 blockers, deterministic plan ID, and proposed managed files only. Preserve full output and before-tree digest.
- [ ] **Step 3: Apply the exact conversion plan.** Parse `$conversionPlanId` only from the successful preceding dry-run envelope and invoke `keil convert --project-root C:\tmp\stm32tk-vs10a-legacy-campaign\project --uvprojx Project/LWIP.gcc.uvprojx --target-name "Target 1" --apply --plan-id $conversionPlanId --authorized --json`; require independent replan equality, `git diff --check`, original Keil input hashes unchanged, and no historical output used as GCC input. Commit conversion locally.
- [ ] **Step 4: Configure through the exact public cycle.** Run `project configure --project-root C:\tmp\stm32tk-vs10a-legacy-campaign\project --dry-run --json`, inspect the managed inventory and frozen tool/target facts, parse `$configurePlanId` only from that successful envelope, then invoke the same command with `--apply --plan-id $configurePlanId --authorized`. Do not create `linker/vs10a.ld` or reserve mailbox. Commit configuration; this is the P1c source/config head.
- [ ] **Step 5: Run two public builds with no intervening source change.** Invoke `C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime\0.9.0\Scripts\python.exe -I -m stm32_toolkit.cli build --project-root C:\tmp\stm32tk-vs10a-legacy-campaign\project --preset arm-debug --json` twice. Copy each envelope/result/identity/ELF/MAP/HEX/log to immutable evidence before the next run.
- [ ] **Step 6: Require reproducibility.** Assert both runs have identical input snapshot SHA-256, build ID, ELF SHA-256, MAP SHA-256, entry/vector/reset facts, project Git head, and toolchain pins. Preserve and classify any mismatch; do not patch timestamps around it.
- [ ] **Step 7: Produce H1 memory/symbol proof.** Compare historical Keil and GCC FLASH/RAM/code/RO/RW/ZI; validate executable/readable/writable ELF segments, `.isr_vector`, SP `0x20030000`, Thumb entry/`Reset_Handler`, `main`, `TIM3_IRQHandler`, typed/DWARF `testtime`, no unresolved strong symbol/overflow/stale input, no mailbox section, and the entire `0x2002EFF0..0x20030000` interval free.
- [ ] **Step 8: Recheck semantic preservation.** Prove the normalized D4/test source Unicode text equals P0 text, original uvprojx/startup and historical hashes equal P0, `testtime` remains non-volatile, and P1c adds no instrumentation/fault/hardware-control behavior.
- [ ] **Step 9: Commit evidence state and report.** Write `p1c.json`, update campaign manifest, write SDD Task 6 report with P0/portability/conversion/P1c commits and exact evidence. Update progress only if all H1 gates pass. End clean/no remote/no hardware, scratch empty, and retain only Task 7-needed firmware/formal evidence.
- [ ] **Step 10: Stop for Sol review.** Sol reviews the complete P0-to-P1c project diff and accepted Toolkit base-to-final Toolkit head, reruns only applicable H1 checks, reconciles report/evidence, and issues `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Task 7 cannot begin before acceptance.
