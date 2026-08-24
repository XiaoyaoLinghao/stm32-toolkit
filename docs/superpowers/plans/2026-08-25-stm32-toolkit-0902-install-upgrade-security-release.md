# STM32 Toolkit 0.9 VS09-B Installation, Upgrade, Security, and Release Artifact Plan

> **Implementation owner:** exactly one GPT-5.6-luna agent, reasoning effort `max`.
> **Reviewer/acceptor:** GPT-5.6-sol primary agent. The implementer must not approve its own diff.

**Goal:** Deliver one reproducible, pinned-source, offline-installable Windows CPython 3.12 STM32
Toolkit 0.9.0 candidate with atomic runtime upgrade/downgrade refusal, malicious-input defenses,
and complete checksums/Monitor assets/SBOM/licenses/compatibility/troubleshooting.

**Architecture:** Build one immutable release bundle from an exact clean Git CodeHead and closed
wheelhouse. Keep `bin/setup-stm32-env.ps1` as the only runtime lifecycle engine; it consumes the
verified bundle and publishes one `runtime-state.json`. Add no runtime, MCP tool/registration,
controller, provider, backend, installer state machine, Agent-specific product branch, or Python
range.

**Version accepted base:** `9a5a132b74638a39b346848cfad0eeb7db9a0539`

**VS09-B slice base / accepted VS09-A head:**
`22bff0061e54e37eba22d892a3b8c34949c3b130`

**Frozen specification commit:** `4f91a92dcdd1a3b5a0efb2b535fb0274ee075d1b`

**Branch/worktree:** `codex/STM32TK-0902-INSTALL-UPGRADE-RELEASE` /
`C:/tmp/stm32tk-0902-install-upgrade-release`

**Remote authority:** none. Do not push, publish, tag, mutate a PR, merge, close, delete a remote
branch, upload an artifact, authenticate to a remote service, run hardware, or begin VS10.

## 1. Frozen contracts and boundaries

- Product/runtime/plugin/UI version stays `0.9.0`.
- Python stays exactly `>=3.12,<3.13`; candidate platform is Windows x86_64 CPython 3.12.
- MCP stays one stdio server with the accepted 48 names; Skills stay the accepted eight.
- Direct runtime pins are:
  - `jsonschema==4.26.0`
  - `mcp==1.29.0`
  - `pyelftools==0.33`
  - `Jinja2==3.1.6`
  - `aiohttp==3.14.3`
  - probe extra: `pyocd==0.45.1`, `pyserial==3.5`
- Build backend pins are `setuptools==84.0.0` and `wheel==0.48.0`.
- The full transitive Windows wheel solution is frozen by exact file/version/size/SHA-256/license
  in the generated release manifest. The selected wheelhouse contains no sdist and final install
  uses no index or resolver.
- `release-manifest.json` schema is `stm32-toolkit-release/1`.
- installed state schema is `stm32-toolkit-runtime-state/1` at
  `DataRoot/runtime/runtime-state.json`.
- Candidate outputs and transitions are exactly those in the frozen specification. A failure may
  not weaken them or add a fallback.

## 2. Intended file map

Create or modify only the coherent delivery surface below, plus narrowly affected existing product
files discovered by a failing named security test:

- `LICENSE` — repository/product MIT license.
- `schemas/stm32-release.schema.json` — closed manifest schema used as packaged documentation and
  cross-checked by the release utility tests.
- `tools/release/build_0900_artifacts.py` — one stdlib-first artifact build/verify utility with
  `build`, `verify-bundle`, and `verify-runtime-state` modes; no orchestration of product behavior.
- `tools/release/release_0900_policy.json` — version, repository, platform, direct pins, allowed
  license expressions, exact license overrides after wheelhouse reconciliation, inventory counts,
  and deterministic path limits.
- `tools/release/licenses/` — only canonical license texts actually referenced by the reconciled
  Python/UI set; no unused bulk license corpus.
- `tools/stm32-toolkit/pyproject.toml` and `tools/stm32-monitor/pyproject.toml` — exact pins and
  accurate MIT/repository metadata, without changing package names, entry points, or Python range.
- `bin/setup-stm32-env.ps1` — verified bundle install and one atomic runtime-state authority,
  preserving Check/Bootstrap/Repair and existing launchers.
- `skills/setup-stm32-env/SKILL.md`, `README.md`, `README_zh-CN.md` — same pinned source/bundle,
  upgrade, refusal, compatibility, and troubleshooting contract.
- `tools/stm32-toolkit/tests/release/test_0900_artifacts.py` — builder/verifier determinism,
  manifest, wheel, asset, SBOM, license, archive/name, and atomic-output tests.
- `tools/stm32-toolkit/tests/test_setup_runtime.py` — bundle verification, clean offline install,
  runtime state, upgrade/rollback/downgrade/future-state/source-collision tests.
- `tools/stm32-toolkit/tests/test_0900_security.py` — the named release/path/command/token/lease/
  audit security regression; use public boundaries and existing fixtures instead of copying
  implementation logic.
- `tools/stm32-toolkit/tests/test_plugin_layout.py` and
  `tools/stm32-toolkit/tests/test_public_inventory.py` — static release/docs/package/inventory
  consistency only when needed.
- `docs/codex/returns/STM32TK-0902-INSTALL-UPGRADE-SECURITY-RELEASE/implementation-report.md` —
  accurate final implementer evidence with Product CodeHead before the report commit.

Do not edit old 0502/0600 release controllers merely to rename or re-version historical evidence.
Do not add a second setup/install script. Do not commit generated candidate wheels, archives,
venvs, wheelhouses, SBOMs, or run logs into Git.

## 3. Utility interface and implementation rules

`tools/release/build_0900_artifacts.py` uses argparse with `allow_abbrev=False`, bounded generic
errors, explicit absolute roots, and these modes:

```text
build --repo-root ROOT --code-head SHA --wheelhouse DIR --output-root NEW_DIR
verify-bundle --toolkit-root EXTRACTED_ROOT [--json]
verify-runtime-state --state PATH --candidate-manifest MANIFEST [--json]
```

`build`:

1. validates CPython 3.12, roots, redirect ancestry, exact Git HEAD/index/tracked bytes, full SHA,
   official repository identity, empty/nonexistent output, and disjoint roots;
2. resolves no dependency from the network: it parses wheel filenames/METADATA, follows exact
   `Requires-Dist` markers for Windows CPython 3.12, selects exactly one wheel per normalized
   distribution, requires all direct pins, and rejects extras that collide with selected names;
3. builds Toolkit and Monitor twice using exact backend pins and `SOURCE_DATE_EPOCH` from the Git
   commit, normalizes sorted `ZIP_STORED` wheel entries, verifies RECORD/METADATA/tags/package data,
   and compares bytes;
4. invokes `git archive` twice at CodeHead for the prefixed source archive and compares bytes;
5. reads Monitor wheel resources, requires the Vite manifest and referenced assets, and emits the
   canonical asset inventory;
6. derives the exact SPDX package graph from selected wheel METADATA and package-lock, reconciles
   every license against policy/texts/notices, and emits deterministic SPDX 2.3 and notices;
7. emits compatibility and troubleshooting only from policy/manifest facts;
8. builds the fixed-metadata Windows bundle twice, compares it, writes the external checksums, then
   atomically activates the final output; and
9. immediately runs its own `verify-bundle` against an extracted copy. Any mismatch removes only
   verified run-scoped staging and leaves no final output.

`verify-bundle` is read-only. It strictly loads the bounded manifest, rejects duplicate keys and
unknown fields/types, validates every hostile-name rule, verifies every hash/size and closed wheel
set, checks product/Monitor/asset/SBOM/license/docs identity, and returns only sanitized paths below
ToolkitRoot. It never extracts an archive or executes a wheel.

`verify-runtime-state` is read-only. It strictly validates state and returns one of `missing`,
`matching`, `repairable`, `downgrade-refused`, `source-conflict`, `unsupported`, or `invalid` plus
only bounded non-secret facts. Setup owns mutation and must not infer a different transition.

## 4. Sequential TDD implementation tasks

### Task 1: establish the VS09-B baseline and RED artifact contract

- [ ] Confirm branch HEAD contains spec and plan commits, worktree is clean, no upstream/PR/remote
  head contains it, and CPython is 3.12.
- [ ] Create a unique `C:/tmp/p0902-baseline-*` root; run only existing setup/public-inventory,
  package-boundary, project-upgrade, Monitor-storage/auth, lease/authorization, and evidence/path
  tests named by this slice. Classify every baseline failure before product changes.
- [ ] Add `test_0900_artifacts.py` RED tests for the closed CLI, exact manifest, safe names,
  duplicate keys, hash/size mismatch, exact direct pins, no sdists, normalized wheel RECORD,
  deterministic timestamps/ordering, two-build identity, atomic output, Monitor assets, SPDX,
  notices/licenses, compatibility, troubleshooting, and source CodeHead/dirty-tree checks.
- [ ] Use tiny local fake wheels and a tiny disposable Git repo for unit RED. Never download in
  unit tests or treat a source fixture as a real candidate.
- [ ] Record the expected RED count and causes in the ignored SDD ledger; clean baseline roots.

Focused RED:

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src;tools/stm32-monitor/src'
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_0900_artifacts.py -q --basetemp C:/tmp/p0902-artifacts-red
```

Expected: nonzero only because the 0900 utility/schema/policy/license authority does not exist.

### Task 2: implement deterministic release artifacts

- [ ] Add the root MIT license, closed manifest schema, policy, only needed license texts, and the
  one artifact utility.
- [ ] Pin package/build dependencies exactly and correct both package repository/license metadata.
- [ ] Implement strict JSON duplicate-key detection, canonical JSON/text, name/path validation,
  redirect checks, safe bounded file reads, normalized distribution/PEP 440 checks, wheel parser,
  requirement-marker evaluation, license reconciliation, SPDX relationships, Monitor asset
  closure, fixed ZIP writing, Git archive/build subprocess arrays, hash/checksum creation, and safe
  staging activation.
- [ ] Never use `shell=True`, `cmd /c`, `Invoke-Expression`, current-directory authority, ambient
  package paths, or a package-index fallback.
- [ ] Keep hostile values out of errors/results. Tests assert both no mutation and no echo.
- [ ] Turn the full artifact RED green and run `git diff --check`.

Focused GREEN:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_0900_artifacts.py -q --basetemp C:/tmp/p0902-artifacts-green
```

### Task 3: write runtime-state and offline-install RED

- [ ] Extend setup test fakes to create a complete signed-by-hash release tree with fake wheels;
  do not weaken the accepted doctor/Monitor/pyOCD validation.
- [ ] Add RED for Bootstrap installing only manifest wheels with `--no-index --no-deps`, copying
  them into staging before pip, and refusing a missing/invalid manifest before runtime staging.
- [ ] Add RED for exact runtime-state schema/type/hash/source/generation, read-only Check, legacy
  absent-state upgrade, matching Repair generation, same-version different-manifest conflict,
  recorded 1.0.0 downgrade refusal, unknown schema, duplicate keys, redirected state, changed
  wheel after hash, pip-check failure, state-write failure rollback, runtime-promotion failure
  rollback, and multiple unexplained runtime directories.
- [ ] Snapshot DataRoot and ProjectRoot before each refusal; assert exact equality afterward.

Focused RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py -k "bundle or runtime_state or downgrade or source_conflict or offline" -q --basetemp C:/tmp/p0902-setup-red
```

### Task 4: make the existing setup engine consume the bundle

- [ ] Discover CPython 3.12 as before, then invoke the release utility in `verify-bundle` and
  `verify-runtime-state` modes using executable/argument arrays and bounded output.
- [ ] Check remains read-only and adds sanitized `bundle` and `runtimeState` evidence. A source
  checkout without a release directory is `bundle.status=missing`, not a host-Python fallback.
- [ ] Bootstrap/Repair require verified bundle evidence before creating staging. Copy exact wheels
  to unique staging, rehash copies, install all in one `pip --no-index --no-deps` command, run
  `pip check`, then retain all accepted VS09-A package/doctor validation.
- [ ] Implement the exact state transitions, create-new/flush/atomic-replace publication, prior
  state byte backup, quarantine and rollback ordering, and generation increment. A refusal happens
  before staging/quarantine.
- [ ] Safe cleanup resolves the exact staging path below `.staging`, refuses redirects, clears only
  run-owned read-only files when needed, and never removes source, wheelhouse, user state, failure
  evidence still needed, or unknown runtime directories.
- [ ] Run all setup/plugin tests and the artifact utility tests green.

Focused GREEN:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/release/test_0900_artifacts.py -q --basetemp C:/tmp/p0902-setup-green
```

### Task 5: close the named malicious-input security matrix

- [ ] Add `test_0900_security.py` with table-driven hostile release/member/path values: traversal,
  absolute/UNC/drive/device namespace, drive-relative, backslash, ADS colon, NUL/control/CRLF/tab,
  `${...}`, `&|<>^%!`, reserved devices with extensions/trailing aliases, non-NFC, trailing dot/
  space, overlong components/path, duplicate JSON keys, duplicate normalized names, and case-fold/
  Unicode collisions.
- [ ] Prove every case rejects before process invocation/extraction/promotion/project write and the
  hostile value is absent from stdout/stderr/result artifacts.
- [ ] Exercise existing public token, lease/authorization, and audit/evidence tests for secret
  redaction, fragment/query behavior, foreign/expired/wrong-level ownership, path containment,
  redirects, duplicate keys, bounds, and identity consistency.
- [ ] If an existing product defect is observed, add the narrow RED to its owning existing test
  file and fix only that owning boundary. Do not introduce a security facade, new store, or copied
  validation implementation.
- [ ] Run the affected security GREEN, not the entire hardware or physical matrix.

Required GREEN set is selected by observed imports/changed files and recorded exactly in the
report. It must include `test_0900_security.py`, Monitor auth, Probe lease/authorization, and the
specific evidence/path files actually touched. Skipped platform behavior cannot be called PASS.

### Task 6: complete metadata, compatibility, troubleshooting, and user guidance

- [ ] Update English/Chinese README and setup Skill with the exact official repository, full-SHA
  pinned checkout/candidate build, external checksum verification, extracted-bundle generic setup,
  Check/Bootstrap/Repair, upgrade, downgrade/source conflict, compatibility, troubleshooting,
  and local-unpublished status.
- [ ] Do not document `pip install` from an index, system-Python fallback, hash bypass, forced
  deletion, token exposure, an extra MCP registration, or a remote release that does not exist.
- [ ] Update static tests to require root/package licenses, official URLs, exact pins, release files,
  48/8 inventory, and bilingual command equivalence.
- [ ] Run public-inventory/plugin/package-boundary tests. Monitor UI E2E is not triggered unless UI
  source or browser-visible behavior changed.

### Correction round 2: close the bootstrap trust anchor and full-license authority

The first correction closed source/release membership after the release utility started, but Sol
proved that the setup helper still executed an attacker-replaced extracted utility before any
independent trust decision. The replacement wrote a marker and returned self-computed hashes;
read-only Check exited `0` with `bundle.status=ok`. This is the same installation-boundary issue,
so the second correction must fix the interface rather than add another post-execution hash.

- [ ] Treat the externally checksummed, already-running `setup-stm32-env.ps1` as the bootstrap
  trust root. Before the first release-utility byte can execute, compare ordinary/non-redirected
  utility and policy bytes with frozen SHA-256 constants owned by setup. The builder must reject a
  CodeHead whose constants do not match its exact committed utility/policy bytes.
- [ ] Execute only the bytes that were read and hash-verified, through the existing bootstrap
  CPython process and argument array. Do not hash one path and later ask Python to reopen mutable
  utility/policy paths. A small in-memory launcher over the existing utility is allowed; a second
  verifier, runtime, controller, provider, backend, public command, or setup argument is not.
- [ ] Add a RED fixture replacing the extracted utility with code that writes a marker and returns
  plausible self-hashes/manifest facts. Both Check and authorized Bootstrap must reject before the
  marker exists, staging is created, or any attacker byte executes. Add a policy-swap equivalent
  and a changed-after-read test at the owning bootstrap boundary.
- [ ] Replace hand-authored SPDX summaries with complete canonical license texts. Store exact
  source-controlled full texts under the release authority (or another frozen source path), bind
  each used SPDX identifier to an exact policy SHA-256, and fail the build on missing, truncated,
  substituted, or unlisted text. `licenses.zip` and `release/licenses/` must contain those full
  texts plus wheel-shipped license/NOTICE/COPYING files.
- [ ] Rebuild twice only after the corrected Product CodeHead is frozen; repeat the fake-utility
  non-execution probe, full-license hash audit, affected artifact/security/setup tests, one fresh
  offline Bootstrap/Check, legacy Repair, and downgrade/source-conflict refusal. Do not rerun the
  full Toolkit or historical release-controller suites.
- [ ] Correct the implementation report: the parent stopped the accidental broad Toolkit run
  because it exceeded the frozen affected matrix; it did not request that run to finish. Record it
  as non-gating, interrupted out-of-scope verification and do not attribute unrelated PASS/FAIL.

### Task 7: assemble and verify the real candidate twice

- [ ] Create exact disposable roots `C:/tmp/p0902-candidate-a`, `...-b`, `...-wheelhouse`, and
  `...-clean-profile`. Verify each resolved absolute path before use/deletion.
- [ ] From read-only public package sources, download the exact Windows x86_64 CPython 3.12 binary
  wheel closure into the disposable wheelhouse. This is input acquisition only: do not upload,
  publish, authenticate, or mutate Git/GitHub. Record exact URLs/versions/hashes/licenses. The
  actual candidate build/install must run with `--no-index` or the utility's direct wheel parser.
- [ ] Run the artifact build twice at Product CodeHead with the same wheelhouse. Compare recursive
  relative file lists, sizes, and SHA-256; every byte must match.
- [ ] Verify external checksums, extract one Windows bundle with a safe standard-library extractor
  into the clean-profile root, and run `verify-bundle` read-only.
- [ ] With hostile Python/PATH/user environment variables removed, run setup Bootstrap against a
  fresh explicit project/data root. Require healthy Check, runtime state schema 1, Toolkit/Monitor
  0.9.0, CPython 3.12 supported, 48/8 doctor, MCP actual 48, Monitor version/assets, imports from
  managed runtime, and zero network access during install.
- [ ] Run legacy runtime Repair/preservation and separate recorded-1.0 downgrade refusal byte
  snapshots. Run existing explicit project Schema upgrades and Monitor storage rollback/preserve
  checks; do not modify real user data.
- [ ] Run the named malicious bundle verification against copied fixtures, not the retained
  candidate.
- [ ] Retain exactly one named final candidate output outside the Git worktree for Sol review;
  remove the duplicate build, extracted profile, wheelhouse, venvs, basetemps, logs, build/
  egg-info, pytest/UI/Python caches after evidence capture.

### Task 8: affected regression, report, and local return

- [ ] Run `python -m compileall` only for changed Python product/release modules and
  `git diff --check` for the slice range.
- [ ] Run the exact affected package/install/security/schema/storage matrix determined above.
  Do not run hardware, Probe/flash/Target, browser E2E without a UI trigger, another Python,
  another OS/architecture, CI, or old 0502/0600 release campaigns.
- [ ] Audit `git diff --name-status 22bff006..HEAD` for scope, and search for a second runtime/MCP/
  controller/provider/backend, Agent-specific product logic, stale repository URLs, unpinned direct
  dependencies, secret/private paths, and generated artifacts accidentally tracked.
- [ ] Commit all product and tests as Product CodeHead. Then write the implementation report with:
  accepted base, spec/plan commits, implementer identity, Product CodeHead, exact file inventory,
  RED/GREEN evidence, candidate hashes/sizes/path, reproducibility comparison, install/upgrade/
  refusal/security results, classifications, cleanup, and Git local/remote state.
- [ ] The report must not claim its own final commit SHA or Sol acceptance. Commit the report
  separately, leave the branch clean/local/unpushed, and return to Sol for complete-diff review.

## 5. Evidence matrix

| Layer | Evidence | Owner | Required environment | Trigger |
| --- | --- | --- | --- | --- |
| Slice | builder/manifest/name/hash/archive/SBOM/license/asset unit RED/GREEN | Luna/max | Windows, CPython 3.12, fake wheels/repos | new release contract |
| Slice | setup bundle/runtime-state upgrade/refusal/rollback RED/GREEN | Luna/max | Windows PowerShell 5+/7, CPython 3.12, fake release tree | setup/runtime mutation |
| Slice | named path/command/token/lease/audit security regression | Luna/max | existing fakes/fixtures; no hardware | security boundary |
| Integration | two byte-identical real builds and checksum verify | Luna/max, reconciled by Sol | exact Product CodeHead + closed cp312 win_amd64 wheelhouse | artifact reproducibility |
| Integration | clean-profile extracted-bundle offline install/smoke | Luna/max, independently repeated by Sol | fresh roots, hostile ambient env removed, `--no-index` | package/install change |
| Integration | legacy upgrade/preservation, rollback, 1.0 downgrade refusal, schema/storage checks | Luna/max, focused Sol repeat | disposable state/project/DB only | migration/state change |
| Review | complete slice-base-to-CodeHead diff and final version-base-to-head audit | Sol | clean detached worktree | mandatory governance |
| Deferred | hardware/physical/browser/full multi-platform matrices | VS10 or only a new UI/platform trigger | named external assets | no trigger in B |

`PASS` belongs only to the actor who ran the command against the recorded commit. Public-download
acquisition is not install PASS. Fake wheels prove code paths, not the real candidate. A report
format issue is REPORT and does not rewrite product evidence; a pure code failure is PRODUCT and
cannot be deferred.

## 6. Stop-loss and review rules

- One Luna/max agent owns all implementation and implementation tests in this slice.
- Sol writes no product code. Correctable findings return to the same branch and one Luna/max
  implementation owner.
- If the same issue fails two implementation/review rounds, stop patching and return to this
  interface/design.
- If exact binary wheel closure or license authority cannot be established, candidate assembly is
  blocked; do not relax to sdists, index resolution, `NOASSERTION`, or a partial SBOM.
- If implementation needs another runtime, public tool, controller, provider, backend, package
  manager, platform, or Agent branch, stop and return to design.
- Preserve minimum failure evidence, then clean run-scoped artifacts under exact verified roots.
- Do not start VS10 after VS09-B acceptance.

## 7. Completion checklist

- [ ] Four frozen user scenarios run with the specified public outcomes.
- [ ] Direct/build dependencies are exact and the transitive selected wheel set is manifest-closed.
- [ ] Builder outputs are byte-identical across two runs and external checksums verify.
- [ ] Setup installs offline from verified wheels, publishes one atomic state, and validates doctor.
- [ ] Legacy upgrade/preservation and rollback pass; downgrade/future/source conflict refuse before mutation.
- [ ] Named malicious inputs, token, lease/authorization, and audit/evidence security tests pass.
- [ ] Product/third-party licenses, SPDX SBOM, Monitor assets, compatibility, and troubleshooting are complete.
- [ ] No 49th MCP tool, ninth Skill, second runtime/registration/controller/provider/backend, Agent logic, Python/platform, CI, remote, or hardware action appears.
- [ ] Implementation report and ignored SDD ledger are accurate; candidate artifacts are retained outside Git.
- [ ] Luna branch is clean/local/unpushed; Sol complete-diff review has no unresolved product defect.
- [ ] Final version-base-to-local-head diff is clean, remote state is explicit, and work stops before VS10.

## 8. Execution and acceptance record

The task boxes above preserve the frozen scheduling plan. Execution is complete and independently
accepted:

- [x] Sole GPT-5.6-luna/max implementer returned Product CodeHead
  `464878d6f08eddcfaa641ffac96834a13b2d70b6` and report head
  `e28861c5da046b1cd65d67849894f37a1b4c0059`.
- [x] Sol reviewed the complete slice-base and version-base diffs with no unresolved product
  defect and issued `ACCEPTED`.
- [x] The four frozen scenarios, closed dependencies/artifacts, offline install, lifecycle
  repair/refusal, malicious-input boundary, licenses/SBOM/assets/docs and 48/8 inventory passed
  their named slice/integration/review evidence.
- [x] One final candidate remains at `C:/tmp/p0902-final-candidate-vs09b-r3`; disposable
  verification roots are cleaned after evidence capture.
- [x] The final branch is local, clean, unpushed and has no upstream; no remote, release, hardware,
  CI, collaboration automation or VS10 action occurred.
