# STM32 Toolkit 0.9 VS09-B Installation, Upgrade, Security, and Release Artifact Design

**Status:** Frozen for implementation

**Slice:** `STM32TK-0902-INSTALL-UPGRADE-SECURITY-RELEASE`

**Version accepted base:** `9a5a132b74638a39b346848cfad0eeb7db9a0539`

**VS09-B slice base / accepted VS09-A head:**
`22bff0061e54e37eba22d892a3b8c34949c3b130`

**Specification owner:** GPT-5.6-sol primary agent

**Implementation owner:** one GPT-5.6-luna agent at reasoning effort `max`

**Independent reviewer/acceptor:** GPT-5.6-sol primary agent

## 1. Outcome

VS09-B turns the accepted Agent-neutral VS09-A runtime into a locally releasable Windows 0.9.0
candidate. One release utility builds a deterministic offline bundle from an exact clean Git
CodeHead and a closed Windows CPython 3.12 wheelhouse. The existing
`bin/setup-stm32-env.ps1` remains the only runtime lifecycle engine and installs only the bundle's
verified wheels. It records one atomic runtime-state authority, upgrades legacy state without
destroying it, and refuses downgrades or same-version source collisions before mutation.

The candidate contains checksummed product wheels, a pinned source archive, the complete offline
runtime wheel set, a Monitor asset inventory, an SPDX SBOM, product and third-party license
material, a compatibility statement, and troubleshooting guidance. It rejects malicious artifact
names, archive paths, manifest shapes, path redirects, command metacharacter payloads, secret/token
leakage, forged leases, and unsafe audit evidence at the owning boundary.

This slice creates no remote release. Push, PR mutation, merge, tag, GitHub Release publication,
remote branch mutation, hardware, and VS10 remain outside the authorized actions.

## 2. Runnable user scenarios

### Scenario B1: clean Windows offline install from a pinned GitHub CodeHead

A release owner checks out the official repository at one full 40-hex commit, supplies a closed
Windows CPython 3.12 wheelhouse, and runs the release utility twice. Both runs produce byte-identical
product wheels, source archive, offline bundle, manifests, SBOM, license output, compatibility,
troubleshooting, and checksums. A clean Windows user extracts the bundle, runs the existing generic
setup command with explicit Toolkit/Data/Project roots, and receives one healthy 0.9.0 runtime.

The installation performs no dependency resolution and no network access. It verifies every
bundle member before creating staging, installs the exact manifest-listed wheels with `--no-index`
and `--no-deps`, runs `pip check`, then runs the existing Toolkit/Monitor/pyOCD/doctor validation
before atomic promotion. CLI, MCP, Monitor, and Claude's thin adapter use that same runtime.

### Scenario B2: safe runtime and persisted-schema upgrade

A user with a supported legacy 0.3.0 or 0.5.0 runtime and existing project/Monitor state runs
Check, sees explicit legacy evidence, and authorizes Repair from the pinned 0.9.0 bundle. The old
runtime is quarantined, the new runtime is staged and validated, and runtime state is written only
as part of successful promotion. Existing project Schema v1/v2 explicit upgrade transactions and
Monitor database transactional upgrades preserve their prior bytes/rows according to their
accepted contracts.

If promotion or state publication fails, the old runtime and old runtime-state bytes are restored.
Unknown future runtime-state schemas, a recorded higher installed version, or a different source
manifest for the same version are refused before staging or quarantine.

### Scenario B3: malicious release/install input fails closed

A caller supplies hostile artifact names or manifest members: traversal, absolute/UNC/drive paths,
backslashes, alternate-data-stream colons, Windows device names, control characters, non-NFC text,
trailing dots/spaces, case-fold collisions, duplicate JSON keys, oversized documents, forged
hashes, symlink/reparse redirects, shell metacharacters, or secret-looking token values. Build and
install reject the input with bounded generic errors, no hostile value echo, no process-shell
interpretation, no extraction outside the exact root, no runtime promotion, and no project write.

The named security regression also proves existing bearer/token redaction, foreign/expired lease
rejection, and audit/evidence containment. A failure in those existing public contracts is a
product defect in this slice; the slice does not add a second security service.

### Scenario B4: a reviewer can audit the candidate without executing hardware

A reviewer verifies `CHECKSUMS.sha256`, the release manifest, Monitor assets, SPDX SBOM, product
license, extracted third-party notices/licenses, compatibility, and troubleshooting. Every file is
bound to the product CodeHead and 0.9.0 identity. The report distinguishes product, environment,
platform, report, and hardware evidence. No fixture or replay is relabeled physical PASS.

## 3. Explicit non-goals

VS09-B does not:

- publish, push, open or mutate a PR, merge, tag, create a GitHub Release, or mutate remote state;
- run or claim hardware, flash, Probe, target, browser, or VS10 physical acceptance;
- add an Agent-specific command, Skill, environment branch, or product implementation;
- add a second runtime, MCP registration, MCP tool, controller, provider, backend, scheduler,
  state store, package manager, or installer lifecycle;
- change the exact 48 MCP tools, eight Skills, one Claude server mapping, protocol semantics,
  project workflows, Monitor UI behavior, or CPython `>=3.12,<3.13` range;
- add Linux/macOS, another Python minor, another CPU architecture, CI, collaboration automation,
  package publication, signing, code signing, or an auto-updater;
- silently rewrite project schemas, Monitor history, user files, or incompatible runtime state;
- vendor a compiler, debugger, build system, package index, or dependency resolver; or
- turn a report-format failure into a product mutation or automatic verdict change.

## 4. One dependency direction and one authority per state

```text
official Git tree at exact CodeHead + closed CPython 3.12 Windows wheelhouse
                              |
                              v
          deterministic tools/release artifact utility
                              |
                              v
       immutable release bundle + external CHECKSUMS.sha256
                              |
                              v
             existing bin/setup-stm32-env.ps1
                              |
                              v
     DataRoot/runtime/0.9.0 + runtime-state.json
                              |
                              v
       existing generic launchers -> CLI / MCP / Monitor
```

The Git tree is the source authority. The release manifest is the immutable artifact authority.
`DataRoot/runtime/runtime-state.json` is the sole installed-runtime history authority. Existing
`.stm32-project.json`, Monitor SQLite, authorization, lease, token, and evidence stores keep their
existing ownership. The release utility and setup helper may validate those stores but never
replace them.

## 5. Frozen release artifact contract

### 5.1 Source and builder preconditions

The release utility is a bounded artifact builder, not a release controller. Its public command is:

```text
py -3.12 tools/release/build_0900_artifacts.py
  --repo-root <absolute clean repository root>
  --code-head <40 lowercase hex commit>
  --wheelhouse <absolute existing offline Windows CPython 3.12 wheel directory>
  --output-root <absolute new empty directory outside the repository>
```

It requires:

- `HEAD == --code-head`, the commit exists, and tracked/index bytes equal that commit;
- official source identity `https://github.com/XiaoyaoLinghao/stm32-toolkit.git` in the manifest;
- output outside the repository, data roots, project roots, and wheelhouse;
- no redirect/reparse ancestor or leaf on any mutable input/output boundary;
- CPython 3.12 and the repository's existing build backend only;
- a closed wheelhouse containing exactly one compatible wheel for every selected runtime
  distribution and no selected sdist; and
- no network call, package publication, signing, or Git mutation.

Untracked files are not source inputs. The builder reads source bytes from `git archive` at the
exact CodeHead, not from arbitrary untracked files. Dirty tracked/index state is rejected because
it makes the operator's provenance claim ambiguous.

### 5.2 Deterministic files

The retained candidate output contains exactly:

```text
CHECKSUMS.sha256
stm32_toolkit-0.9.0-py3-none-any.whl
stm32_monitor-0.9.0-py3-none-any.whl
stm32-toolkit-0.9.0-source.zip
stm32-toolkit-0.9.0-windows-x86_64.zip
release-manifest.json
monitor-assets.json
sbom.spdx.json
THIRD-PARTY-NOTICES.md
LICENSE
licenses.zip
compatibility.md
troubleshooting.md
```

The Windows archive contains the pinned source tree under one
`stm32-toolkit-0.9.0/` prefix plus `release/` members for the manifest, every selected runtime
wheel, the asset inventory, SBOM, license material, compatibility, and troubleshooting. It never
contains Git metadata, caches, build output, test evidence, user paths, tokens, or the release
report.

All ZIP members are sorted, use `/`, fixed permissions, a timestamp derived from the commit's
UTC epoch clamped to ZIP's valid range, and `ZIP_STORED`. Product wheels are built with
`SOURCE_DATE_EPOCH`, then normalized by sorted fixed-metadata ZIP rewriting. `RECORD` remains the
wheel content authority. Two independent builds from the same CodeHead and wheelhouse must produce
identical bytes and hashes for every listed output.

### 5.3 `release-manifest.json`

The manifest is canonical UTF-8 JSON (`ensure_ascii=false`, sorted keys, compact separators, one
final LF), at most 1 MiB, with no duplicate keys and this closed shape:

```json
{
  "schema": "stm32-toolkit-release/1",
  "productVersion": "0.9.0",
  "requiredPython": ">=3.12,<3.13",
  "platform": {"os": "windows", "architecture": "x86_64", "python": "cp312"},
  "source": {
    "repository": "https://github.com/XiaoyaoLinghao/stm32-toolkit.git",
    "commit": "<40 lowercase hex>",
    "archive": "stm32-toolkit-0.9.0-source.zip",
    "sha256": "<64 lowercase hex>"
  },
  "runtimeStateSchema": "stm32-toolkit-runtime-state/1",
  "wheels": [
    {"name": "<normalized distribution>", "version": "<PEP 440>",
     "file": "release/wheels/<safe wheel filename>", "sha256": "<64 hex>",
     "size": 1, "direct": true, "license": "<closed SPDX expression>"}
  ],
  "artifacts": [
    {"kind": "monitor-assets|sbom|notices|license|compatibility|troubleshooting",
     "file": "release/<safe relative path>", "sha256": "<64 hex>", "size": 1}
  ],
  "publicInventory": {"mcpTools": 48, "skills": 8}
}
```

Arrays have no duplicate file, distribution, or case-folded name. Both product wheels are direct
and exact 0.9.0; every transitive runtime distribution is indirect. The selected wheel set is the
closed dependency solution. Setup installs every manifest wheel in one `pip install --no-index
--no-deps` invocation and then requires `pip check` success. It never asks pip to resolve or
download.

### 5.4 Checksums and self-reference

`CHECKSUMS.sha256` is external to the bundle and contains lower-case SHA-256, two spaces, and the
safe basename for every top-level retained file except itself, sorted by UTF-8 basename bytes.
The manifest hashes every mutable member it consumes but does not hash itself. The outer checksum
hashes the manifest and the final Windows archive, avoiding recursive self-reference.

## 6. Monitor assets, SBOM, and licenses

`monitor-assets.json` is canonical JSON containing the Monitor version, Vite manifest hash, and
the sorted relative path/size/SHA-256 of `index.html`, `.vite/manifest.json`, and every referenced
asset embedded in the Monitor wheel. Missing, duplicate, unreferenced required, escaping, or
case-colliding assets fail the build.

`sbom.spdx.json` is deterministic SPDX 2.3 JSON. It contains:

- the Toolkit, Monitor, every selected Python runtime wheel, and every `package-lock.json`
  production/development package included in the shipped Monitor build provenance;
- exact name/version, download location when declared, SHA-256 for shipped wheels/assets,
  declared/concluded license, supplier when declared, and stable SPDX IDs;
- `DESCRIBES`, `DEPENDS_ON`, and `GENERATED_FROM` relationships sufficient to distinguish runtime
  Python dependencies from UI build dependencies; and
- creation information derived from the product CodeHead, never wall-clock time or a user name.

The builder parses wheel `METADATA` and the checked-in `package-lock.json`; it does not execute
packages. Missing exact versions, unknown license expressions, duplicate normalized packages, or
unresolved runtime requirements fail closed.

The repository gains a root MIT `LICENSE`, accurate package metadata/repository URLs, a closed
license policy for every selected Python/UI package, canonical texts for the SPDX identifiers used,
and extracted package NOTICE/license files when a wheel ships them. Those texts are retained under
`release/licenses/` inside the Windows archive and in the deterministic top-level `licenses.zip`.
`THIRD-PARTY-NOTICES.md` is generated deterministically from that authority. An unknown or absent
required license is a build failure, not `NOASSERTION` silently accepted.

## 7. Existing setup engine and runtime state

### 7.1 Bundle consumption

The generic setup signature remains `Check|Bootstrap|Repair` with explicit Toolkit/Data/Project
roots. A released ToolkitRoot contains `release/release-manifest.json` and
`release/wheels/`. Check is read-only and may report a missing/unavailable bundle. Bootstrap and
Repair require a valid bundle before they create `runtime/.staging`.

The helper reads manifest/checksum files with bounded size, strict duplicate-key rejection, closed
fields, exact types, safe relative names, and SHA-256 verification. It never extracts an untrusted
archive during installation: the user extracts the already checksummed outer bundle, and setup
operates only on verified ordinary files below ToolkitRoot. Redirects, hard-link ambiguity where
detectable, and changed bytes between hash and install are rejected. The helper copies verified
wheels into the unique staging boundary before invoking pip so a source-tree race cannot swap them.

### 7.2 Runtime-state model

`DataRoot/runtime/runtime-state.json` is canonical JSON at most 64 KiB:

```json
{
  "schema": "stm32-toolkit-runtime-state/1",
  "activeVersion": "0.9.0",
  "highestInstalledVersion": "0.9.0",
  "releaseManifestSha256": "<64 lowercase hex>",
  "sourceCommit": "<40 lowercase hex>",
  "installGeneration": 1
}
```

It contains no project path, user name, token, credential, command, or environment. Exact built-in
integers are required; booleans are invalid. State is opened without following redirects, parsed
strictly, and written by create-new temporary file plus flush and atomic replace. The prior bytes
are retained until runtime promotion and state publication both succeed.

The transitions are:

```text
no runtime/no state + Bootstrap(valid 0.9 bundle)
  -> validated staging -> runtime 0.9 + state schema 1 generation 1

legacy 0.3/0.5 and no state + Repair(valid 0.9 bundle)
  -> quarantine legacy -> validated 0.9 -> state schema 1 generation 1

broken 0.9 + valid matching state + Repair(same manifest)
  -> quarantine -> validated replacement -> same highest, generation + 1

candidate version < highestInstalledVersion
  -> DOWNGRADE_REFUSED before staging/quarantine/mutation

candidate version == activeVersion but manifest/source differs
  -> VERSION_SOURCE_CONFLICT before mutation

unknown/malformed/future state schema
  -> STATE_UNSUPPORTED or STATE_INVALID; no automatic repair
```

If publication fails after quarantine, both the prior runtime and exact prior state bytes are
restored. Check never creates or rewrites state. Runtime directories not explained by the state or
the closed legacy set make Repair ambiguous and fail closed.

### 7.3 Persisted product schemas

VS09-B does not add a project-upgrade CLI/MCP operation because VS09-A froze 48 MCP tools and the
existing public upgrade transactions already own Schema v1->v2->v3. The security matrix must prove:

- project upgrade plan/apply remains explicit, digest-authorized, atomic, and downgrade-free;
- unsupported future project schema is read-only rejected;
- Monitor storage structural upgrade preserves accepted legacy rows and rolls back injected
  failures; and
- runtime state migration is only absent legacy state -> schema 1. Unknown future state is never
  guessed or rewritten.

## 8. Malicious-name and security contract

Every release/bundle member and manifest path must reject:

- empty, `.`, `..`, traversal, repeated separator ambiguity, absolute POSIX, UNC, drive-absolute,
  drive-relative, or device namespace paths;
- backslashes, colons/alternate data streams, NUL/control characters, CR/LF/tab, shell
  metacharacters, percent/bang expansion forms, and unresolved `${...}` placeholders;
- Windows reserved basenames `CON`, `PRN`, `AUX`, `NUL`, `COM1..9`, and `LPT1..9`, including
  extension/trailing-dot/space aliases;
- non-NFC text, trailing dot/space components, components over 255 UTF-8 bytes, paths over 4096
  UTF-8 bytes, duplicate normalized names, and Unicode/case-fold collisions; and
- symlink, junction, reparse, non-regular, multi-link, or changed-after-hash files at a consumed
  installation boundary.

Hostile values never appear in stderr/stdout, manifest, SBOM, checksums, troubleshooting, or
reports. Process execution always uses an executable plus argument array; no `Invoke-Expression`,
`cmd /c`, shell string, batch interpolation, or environment-derived package path is added.

The affected security regression must also prove the existing contracts:

- Monitor bearer token remains random, fragment-only/bootstrap-scrubbed, excluded from repr,
  errors, persisted data, audit output, and generated release artifacts;
- forged, expired, foreign-workspace, or wrong-level lease/authorization identifiers cannot steal,
  release, or execute another owner's operation;
- audit/evidence files reject escape, redirect, duplicate-key, oversized, secret-bearing, and
  inconsistent identity input; and
- archive/bundle verification is read-only and never follows attacker-controlled members.

## 9. Compatibility and troubleshooting deliverables

`compatibility.md` is generated from frozen authority and states only:

- Windows x86_64;
- CPython `>=3.12,<3.13` (CPython 3.12 only);
- Toolkit/Monitor/plugin/UI 0.9.0;
- one generic explicit-root CLI/MCP runtime and the retained Claude thin adapter;
- project schemas v2/v3 readable, v1 only through explicit upgrade, and runtime-state schema 1;
- the exact dependency/wheel versions in the manifest and the existing external-tool support
  evidence without claiming missing tools or hardware PASS; and
- no Linux/macOS/other Python/hardware promise.

`troubleshooting.md` maps closed observations to safe action: checksum mismatch, source commit
mismatch, invalid bundle name, missing CPython 3.12, missing/broken runtime, unsupported runtime
state, downgrade refusal, same-version source conflict, pip-check failure, missing Monitor asset,
license/SBOM failure, redirect path, and doctor mismatch. It never tells users to bypass hashes,
delete unknown state, use system Python fallback, disable TLS, run unsigned remote code, expose a
token, force a downgrade, or remove user/project data.

README English/Chinese and the setup Skill point to the same pinned-source/offline-bundle flow and
state that publication remains unperformed.

## 10. Error and lifecycle semantics

The Python artifact utility returns exit `0` only for a complete output and `2` for a closed input,
policy, integrity, or reproducibility rejection. Unexpected environment/build failures return `1`.
It writes one bounded JSON result to stdout only when requested and bounded generic diagnostics to
stderr. A failed output remains in a unique staging directory until the utility safely removes it;
the final output path is created atomically only after all checks pass.

The setup helper retains exit `0` for successful Check/Bootstrap/Repair and exit `2` for a closed
setup refusal. Check reports structured `bundle` and `runtimeState` evidence. Bootstrap/Repair
errors produce no stdout success payload and never partially promote.

Product test failures are never deferred. Missing physical hardware is not a B blocker because no
B public behavior requires hardware. A live package-index outage is ENVIRONMENT only if the exact
offline wheelhouse already exists; candidate assembly itself cannot PASS without that closed
wheelhouse.

## 11. Proportionate verification and evidence ownership

### 11.1 Luna slice evidence

The sole Luna/max implementer owns RED/GREEN tests for:

- release manifest/name/archive/hash/SBOM/license/asset determinism and hostile inputs;
- setup bundle verification, offline install, atomic runtime state, legacy upgrade, rollback,
  downgrade refusal, future-state rejection, and same-version source conflict;
- package metadata, root license, compatibility/troubleshooting, README/Skill alignment;
- affected project-upgrade, Monitor-storage, token, lease/authorization, and audit/evidence
  security regressions; and
- two independent artifact builds plus one clean-profile extracted-bundle install/smoke.

The implementer records the product CodeHead before committing the implementation report. It may
perform read-only HTTP downloads needed to assemble the exact public dependency wheelhouse, but it
must not upload, publish, authenticate to, or mutate any remote service. The final verification
uses `--no-index`; network-backed installation is not acceptance evidence.

### 11.2 Sol independent review

Sol reviews the complete
`22bff0061e54e37eba22d892a3b8c34949c3b130..Product-CodeHead` diff in a clean detached worktree,
and also audits the final
`9a5a132b74638a39b346848cfad0eeb7db9a0539..final-local-head` range. Sol reruns only the security,
setup/upgrade, release determinism, package/install, and affected schema/storage checks plus one
fresh offline install smoke.

### 11.3 Checks intentionally not run

No hardware/Probe/flash/Target/VS10 gate runs. No browser E2E runs unless product UI bytes or
browser-visible behavior change; hashing/package-boundary checks cover unchanged Monitor assets.
No extra Python/platform matrix, performance campaign, old 0502/0600 controller campaign, CI, or
remote publication runs. Unaffected accepted VS07/VS08 product evidence remains valid unless the
implementation changes those bytes or contracts.

## 12. Cleanup and completion

After each run, disposable basetemps, extracted test bundles, temporary wheelhouses, venvs,
staging/quarantine fixtures, logs, JUnit, coverage, build/egg-info, and Python/UI caches are removed
after preserving minimum failure evidence. Source-controlled tests, license texts, policies,
fixtures, reports, and the one final named candidate artifact directory are not disposable.

VS09-B is complete only when:

1. all four scenarios are implemented and independently accepted;
2. both artifact builds are byte-identical and the retained candidate verifies from checksums;
3. clean-profile offline install, legacy upgrade, rollback, downgrade refusal, and future-state
   refusal pass without project/Monitor data loss;
4. the named malicious-input matrix passes with no secret/path leakage;
5. wheels/source/archive/Monitor assets/SBOM/licenses/compatibility/troubleshooting are complete;
6. the implementation report and SDD ledger name the accepted base, Product CodeHead, artifact
   hashes, exact evidence owners, classifications, cleanup, and local/remote Git state;
7. Sol's full accepted-base-to-final-head review has no unresolved product defect;
8. the final local candidate worktree is clean and no branch is pushed or published; and
9. work stops at the accepted 0.9 candidate without starting VS10.
