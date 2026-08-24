# STM32TK-0902 VS09-B implementation report

## Ownership and frozen inputs

- Module/slice: STM32 Toolkit 0.9, VS09-B installation, upgrade, security, and release artifacts.
- Implementer: GPT-5.6-luna, reasoning effort `max`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent; this report does not issue a review verdict.
- Accepted VS09-A slice base: `22bff0061e54e37eba22d892a3b8c34949c3b130`.
- Version accepted base: `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Frozen specification commit: `4f91a92dcdd1a3b5a0efb2b535fb0274ee075d1b`.
- Frozen implementation-plan commit: `d452d5e782d5829efacc9f961e4d4c0847ed1e76`.
- Branch: `codex/STM32TK-0902-INSTALL-UPGRADE-RELEASE`.
- Product CodeHead recorded before this report commit:
  `5840dd3261731f53cc99247e9dc08ce0e3c4769d`.
- Worktree: `C:/tmp/stm32tk-0902-install-upgrade-release`.

The implementation keeps one setup/runtime lifecycle and registration authority, the accepted
48 MCP tools and 8 Skills, and adds no controller/provider/backend, Agent-specific product logic,
second runtime, Python/platform target, CI, collaboration automation, hardware behavior, VS10, or
remote mutation.

## Product changes

Product and test files changed from the accepted VS09-A base:

- `LICENSE`
- `README.md`
- `README_zh-CN.md`
- `bin/setup-stm32-env.ps1`
- `schemas/stm32-release.schema.json`
- `skills/setup-stm32-env/SKILL.md`
- `tools/release/build_0900_artifacts.py`
- `tools/release/release_0900_policy.json`
- `tools/stm32-monitor/pyproject.toml`
- `tools/stm32-monitor/tests/test_package_boundary.py`
- `tools/stm32-toolkit/pyproject.toml`
- `tools/stm32-toolkit/tests/release/test_0900_artifacts.py`
- `tools/stm32-toolkit/tests/test_0900_security.py`
- `tools/stm32-toolkit/tests/test_setup_runtime.py`

The release utility is stdlib-first and verifies strict JSON, safe paths, wheel compatibility and
RECORD hashes, dependency closure, license/notices/SBOM/Monitor asset closure, deterministic ZIPs,
and the pinned source archive. Setup verifies the extracted bundle, copies and rehashes every
manifest wheel into unique staging, installs once with `--no-index --no-deps --only-binary=:all:`,
runs `pip check` and the existing doctor/pyOCD/Monitor validations, then publishes one atomic
`runtime-state.json` with generation and source/manifest binding. Refusals occur before staging
or quarantine.

## TDD evidence and classifications

Baseline focused tests were run before product edits under CPython 3.12.10 and exited 0. The
baseline covered setup runtime, plugin layout, public inventory, explicit project upgrade/v3,
Monitor storage/auth, probe lease, creation authorization, evidence schema/store, and path
contracts.

RED was recorded before GREEN for each behavior slice:

- Artifact utility: `py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_0900_artifacts.py -q --basetemp C:/tmp/p0902-artifacts-red-3` — 20 tests, 2 expected failures for the absent release policy/utility behavior (PRODUCT RED).
- Setup bundle/runtime-state: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_setup_runtime.py -k "bundle or runtime_state or downgrade or source_conflict or offline" -q --basetemp C:/tmp/p0902-setup-red` — 3 expected failures for absent bundle/state/staging-before-validation behavior (PRODUCT RED).
- Security: the initial DEL-byte hostile-name and malformed runtime-state cases failed before the utility fixes (PRODUCT RED); the same focused file later passed completely.
- Candidate assembly exposed four product defects before finalization: case-sensitive official-remote comparison, nondeterministic/empty license archive retention, release authority outside the extracted source root, and source archive not retained in that root. Each was classified PRODUCT, fixed, and rebuilt before freezing the Product CodeHead.
- A final-matrix collection attempt with `PYTHONPATH` deliberately cleared failed to import source packages. This was classified ENVIRONMENT, corrected by supplying the two explicit source roots, and was not treated as a product failure.

GREEN evidence:

- Artifact utility: 22 passed.
- Security suite: 27 passed.
- Complete setup suite and plugin/layout checks: passed.
- Final affected regression (explicit `PYTHONPATH=tools/stm32-toolkit/src;tools/stm32-monitor/src`, `-p no:cacheprovider`) collected 478 tests and exited 0: 477 passed, 1 skipped.
- `py -3.12 -m compileall -q tools/release/build_0900_artifacts.py`: exit 0.
- `git diff --check 22bff0061e54e37eba22d892a3b8c34949c3b130..5840dd3261731f53cc99247e9dc08ce0e3c4769d`: exit 0.

## Candidate and reproducibility evidence

The exact Windows x86_64 CPython 3.12 binary wheel closure was downloaded read-only to a
disposable wheelhouse. Candidate assembly and install used no index; no upload, authentication,
Git/GitHub mutation, or release publication was performed.

Two builds from Product CodeHead `5840dd3261731f53cc99247e9dc08ce0e3c4769d` using the same
wheelhouse produced `C:/tmp/p0902-candidate-a` and `C:/tmp/p0902-candidate-b`. Both contained 13
files; recursive relative path, size, and SHA-256 comparison returned `DIFF_COUNT=0`. External
checksum verification returned `CHECKSUM_LINES=12 CHECKSUM_PASS=12`.

Final retained candidate: `C:/tmp/p0902-candidate-a`

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `CHECKSUMS.sha256` | 1073 | `92a4431c37e6c527ec5c5f4b2c325bd69b43d17eba71570e6728e79c4307f5a2` |
| `compatibility.md` | 1742 | `309159534892c68f938000c09177b1ad34a34594f690be2828c64ca6ea6fa439` |
| `LICENSE` | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` |
| `licenses.zip` | 1205 | `85aa59213ea18e93c8a2697eec5dfbfa4951235de4204467f8eb6ccdd6933c43` |
| `monitor-assets.json` | 975 | `e08692c6b519cc90c82cae2ce972ae9f9636ea6796196d6418fe44c4479403c6` |
| `release-manifest.json` | 15329 | `dc3d0d94c42945be9d60f1eb116fa5cef9bc514ebf2f2852799e150bc4d39e3d` |
| `sbom.spdx.json` | 126634 | `bcc5ca279df786f700380244b20cfc66603152809284ac8a4e3c09016392ad5d` |
| `stm32_monitor-0.9.0-py3-none-any.whl` | 1244802 | `9a734a3188d0c6c36a39c03e65f98f777c162f7c1f0dfc34acd152f5f90dafc4` |
| `stm32_toolkit-0.9.0-py3-none-any.whl` | 2510618 | `674ecb6070e2d8233d5401af6f0129f5a5eb8427a85552d2c7795367b495d6ae` |
| `stm32-toolkit-0.9.0-source.zip` | 12803377 | `f6229fb2d4e8f3188e6b929c4e97755ad1c61924826818b96a7a33f4cbd43637` |
| `stm32-toolkit-0.9.0-windows-x86_64.zip` | 96955398 | `2d7aa6402df42784f6530bb462119cb8b316962ceb73faf35a852bcb55de9f13` |
| `THIRD-PARTY-NOTICES.md` | 2130 | `3d674a54bd1416609f3bc1f08266d676fa99b194b5bd3ab2bd20e5a3d73af022` |
| `troubleshooting.md` | 675 | `86d99f7cdb22964ec039887aafc4bf41a9c0a22a5def8fa24418b52da0976762` |

Safe standard-library extraction of the Windows archive into the disposable clean profile
passed. Extracted-root `verify-bundle` passed. The release manifest passed
`schemas/stm32-release.schema.json` validation, contains 64 wheels (62 external closure wheels
plus the two product wheels), and records public inventory `mcpTools=48`, `skills=8`.

## Candidate install, upgrade, refusal, and storage evidence

- With hostile Python/PATH/user package variables removed, extracted-bundle Bootstrap exited 0.
  Read-only Check exited 0 with healthy managed CPython 3.12.10, Toolkit 0.9.0, Monitor 0.9.0,
  matching runtime state generation 1, exact 48 MCP tools/8 Skills, and doctor validation.
- Managed-runtime `pip check` exited 0 (`No broken requirements found`). Direct managed-runtime
  metadata/import checks reported Toolkit and Monitor 0.9.0; Monitor UI `index.html` and Vite
  manifest/assets were validated. The setup install command is one `pip install` with
  `--no-index --no-deps --only-binary=:all:` and no package-index fallback.
- Same-version Repair exited 0, quarantined the prior managed runtime, and atomically advanced
  state generation from 1 to 2; subsequent state verification returned `matching`.
- A disposable legacy 0.5.0 runtime with a marker and absent state was repaired successfully.
  The marker was preserved under `.quarantine`, the new state was schema 1 generation 1, the
  managed runtime was healthy, and the explicit project file remained unchanged.
- A disposable profile with recorded `activeVersion`/`highestInstalledVersion` 1.0.0 returned
  utility `downgrade-refused` (exit 2) and setup refusal (exit 2). State, runtime marker,
  project, and full profile tree were byte-equivalent before/after; neither `.staging` nor
  `.quarantine` was created.
- Existing explicit project Schema upgrade and Monitor storage rollback/preserve paths are
  included in the final 478-test regression. No real user data or hardware was used.

## Failure/deferred classifications

- PRODUCT: intentional RED cases and the four candidate assembly defects listed above; all were
  corrected and covered by GREEN evidence before the Product CodeHead.
- ENVIRONMENT: one source-test collection attempt without the explicit source import roots;
  corrected without product changes.
- HARDWARE: real-board/probe/flash/debug evidence is deferred to the named later owner; no
  physical hardware was claimed.
- PLATFORM/INFRASTRUCTURE/REPORT: no unresolved failures in the returned evidence.

## Cleanup and Git state

After evidence capture, the duplicate candidate, extracted install profiles, wheelhouse, all
p0902 basetemps/logs/failure outputs, and ignored build/egg-info/pytest/Python cache directories
were removed using guarded exact-path cleanup. Exactly one named final candidate directory remains:
`C:/tmp/p0902-candidate-a`.

The branch is local, clean, unpushed, and has no upstream. No push, PR, merge, tag, release,
remote branch deletion, authentication, upload, or other remote mutation was performed. The
ignored SDD ledger records the same evidence and cleanup state.
