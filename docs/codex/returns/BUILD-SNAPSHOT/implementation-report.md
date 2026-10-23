# BUILD-SNAPSHOT implementation report

## Identity and disposition

- Repository: `C:/Users/zhy76/.codex/worktrees/build-snapshot/STM32-Toolkit`
- Branch: `codex/build-snapshot`
- Accepted base: `690f579d4efe1d2616e0c1d9289263c24069134a`
- Task starting head (approved specification/plan only): `2f594a71`
- Implementation CodeHead before this report commit: `a3d20144164c4d29f25c9d5193724ad124db7779`
- Reviewer: primary conversation agent (independent). This report is not acceptance and does not self-approve the diff.
- Authority used: local implementation, focused offline tests, local commits, and the primary-authorized restoration attempt of one existing byte fixture. No push, PR, merge, tag, release, version bump, packaging, installation, deployment, provider change, real probe enumeration, or hardware operation was performed.

## Implemented scope

1. Added a build-specific Git collector (`collect_build_git_evidence`) that maps only the strict collector's stable availability error to bounded diagnostics. The strict `git_evidence` API is unchanged and still raises `BUILD_GIT_INVALID`. Unknown/unhashable rule details are bounded to the fixed public `head`/`status` values, and non-availability errors still propagate.
2. A Git-available build keeps the exact schema-1 identity/record key order, bytes, and build-ID semantics. An unavailable Git build emits schema 2 with `sourceBaseline: "input-snapshot-v1"`, null `gitHead`/`gitDirty`, and bounded `gitEvidence` `{status, code, rule}`; no commit hash is invented and Git state is never modified.
3. Both `firmware-identity.schema.json` copies now carry strict conditional contracts: schema 1 requires non-null Git fields and forbids snapshot fields; schema 2 requires `sourceBaseline`, `gitEvidence`, and null Git fields. Typed `FirmwareIdentity` serialization round-trips both schemas, and the runner verifies the round-trip before publishing success evidence.
4. `context.py` recognizes schema-2 evidence as fresh only when the strict success-record shape, identity digest, project/toolkit identity, target/preset/model, exact current input snapshot, contained ELF/MAP paths, and artifact hashes all agree. Schema-2 freshness never spawns Git. Schema-1 freshness keeps its existing Git behavior. `data.build` now reports `sourceBaseline`, `gitDirty`, and `gitEvidence`, so unavailable Git is never presented as clean.
5. No-op reuse requires a compatible current prior success record in the same provenance mode, strict schema-2 record shape, matching identity/source baseline/inputs/artifacts. Missing, extra, forged-null, mistyped, unhashable, malformed-artifact, cross-schema, changed-source, stale, and failed records are rejected.
6. The shared firmware admission in `probe/flash.py` validates a current snapshot identity and record, then returns `FIRMWARE_PROVENANCE_UNSUPPORTED` with build-only guidance before any probe, lease, or attach effect. `debug/firmware.py` preserves that code through its adapter. Schema-1 hardware behavior is unchanged. Context marks `flash`, `targetTest`, `monitor`, and `breakpointDebug` as `blocked` with the provenance remediation for a fresh snapshot build; probe discovery remains independent.
7. Schema-1 failure records restore their established legacy bytes (`gitHead: null`, `gitDirty: false`) regardless of collected Git details. Schema-2 unavailable-Git failures use null/null with bounded diagnostics at every post-collection failure point, including pre-build snapshot and drift failures.
8. Updated MCP build/flash and firmware-consuming tool descriptions, both affected skills, `docs/user-guide.md`, and `docs/architecture.md` with the exact fields, no-fake-hash rule, build-only scope, and structured capability blocker.

## Changed files (implementation commit `a3d20144`)

Modified:

- `docs/architecture.md`
- `docs/user-guide.md`
- `schemas/firmware-identity.schema.json`
- `skills/build-firmware/SKILL.md`
- `skills/flash-firmware/SKILL.md`
- `tools/stm32-toolkit/src/stm32_toolkit/build/identity.py`
- `tools/stm32-toolkit/src/stm32_toolkit/build/model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/build/runner.py`
- `tools/stm32-toolkit/src/stm32_toolkit/context.py`
- `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/firmware-identity.schema.json`
- `tools/stm32-toolkit/tests/test_build_runner.py`
- `tools/stm32-toolkit/tests/test_context.py`

Added:

- `tools/stm32-toolkit/tests/test_build_snapshot.py`

No Monitor/UI, version, packaging, installer, migration-write, acceptance-wire, or unrelated product files changed. No test was skipped or weakened to hide a failure.

## Test evidence

All test processes were offline and used the dedicated venv (`python` on PATH), temporary roots under `D:/codex-tmp/kg23`, unique pytest basetemp/cache directories per run, fake `cmake`/`git` process doubles, and fake probe clients only. No real probe enumeration, attach, or hardware occurred.

| Check | Command summary | Result |
| --- | --- | --- |
| New snapshot suite (final) | `python -m pytest tools/stm32-toolkit/tests/test_build_snapshot.py --basetemp=D:/codex-tmp/kg23/bt-snap-r2 -o cache_dir=D:/codex-tmp/kg23/cache-snap-r2 -q` | 42 passed |
| Snapshot + build runner (final corrections A/B and publication order) | `python -m pytest tools/stm32-toolkit/tests/test_build_snapshot.py tools/stm32-toolkit/tests/test_build_runner.py --basetemp=D:/codex-tmp/kg23/bt-corr2-2a -o cache_dir=D:/codex-tmp/kg23/cache-corr2-2a -q` | **146 passed** |
| Context + flash + debug binding | `python -m pytest tools/stm32-toolkit/tests/test_context.py tools/stm32-toolkit/tests/test_flash.py tools/stm32-toolkit/tests/test_debug_firmware.py --basetemp=D:/codex-tmp/kg23/bt-corr2-2 -o cache_dir=D:/codex-tmp/kg23/cache-corr2-2 -q` | **236 passed** |
| MCP migration/build, MCP server, plugin layout, public inventory | `python -m pytest tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_public_inventory.py --basetemp=D:/codex-tmp/kg23/bt-adapt-1 -o cache_dir=D:/codex-tmp/kg23/cache-adapt-1 -q` | 61 passed, 1 dependency warning |
| CLI, workflows, hardware workflows, MCP hardware, debug read | `python -m pytest tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_mcp_hardware.py tools/stm32-toolkit/tests/test_debug_read.py --basetemp=D:/codex-tmp/kg23/bt-adapt-2 -o cache_dir=D:/codex-tmp/kg23/cache-adapt-2 -q` | 360 passed, 2 warnings |
| Firmware identity suite (environment test excluded only from this command) | `python -m pytest tools/stm32-toolkit/tests/test_firmware_identity.py -k "not real_linked_toolkit_template_stack_symbols" --basetemp=D:/codex-tmp/kg23/bt-ident-corr2 -o cache_dir=D:/codex-tmp/kg23/cache-ident-corr2 -q` | 100 passed |
| Formerly failing fixture test (run alone, not skipped) | `python -m pytest tools/stm32-toolkit/tests/test_firmware_identity.py::test_real_linked_toolkit_template_stack_symbols --basetemp=D:/codex-tmp/kg23/bt-fixture-2 -o cache_dir=D:/codex-tmp/kg23/cache-fixture-2 -q` | **1 failed: ENVIRONMENT** (checkout CRLF fixture; see below) |
| Whitespace | `git diff --check` / `git diff --cached --check` | No errors; only Git autocrlf informational notices |

The 146 combined result includes the final guard, legacy-failure, and publication-order changes; earlier passing runs (`bt-snap-r1`, `bt-snap-r2`, `bt-hw-r1`, `bt-corr2-1`, `bt-corr2-2`) are retained in the stream transcript and are not re-run solely for logs.

## Corrections and failures

1. **Round-2 finding A (unhashable diagnostics).** `validate_snapshot_build_result` and `collect_build_git_evidence` originally used membership against a frozenset without a string guard, so JSON `gitEvidence.rule` arrays/objects could raise `TypeError`. Both now require an exact string before membership; malformed objects produce a stable invalid-record/stale result, and collector details are bounded to `head`. New regressions cover array/object/number/null rules and non-object evidence through context and no-op build paths, plus unhashable collector details.
2. **Round-2 finding B (legacy schema-1 failure bytes).** An intermediate `_publish_failure` change read collected `GitEvidence.head/dirty` into schema-1 failure records, broadening legacy semantics. Restored `gitHead: null`/`gitDirty: false` for schema 1; schema-2 unavailable failures remain null/null with `sourceBaseline` and `gitEvidence`. Regressions cover a dirty-repository schema-1 configure failure and the changed-input failure shape.
3. **Round-1 finding 1 (strict snapshot records).** Added strict schema-2 success-record validation (exact fields, integer schema version, `status=success`, `stage=""`, `code=OK`, typed digests, bounded evidence, exact five-artifact shape/paths) at context and no-op admission. Regressions cover removed nullable fields, float/cross schema, extra fields, malformed/non-current stage, and artifact tampering without stale acceptance.
4. **Round-1 finding 2 (project/toolkit identity).** Schema-2 context and no-op admission now require the current `logicalProjectId` and runtime `toolkitVersion`; recomputed-identity tampering tests fail closed.
5. **Round-1 finding 3 (hardware blocker visibility).** A fresh snapshot build now yields `blocked` capability details with `FIRMWARE_PROVENANCE_UNSUPPORTED` remediation for flash, Target tests, Monitor, and breakpoint debug. A public MCP context-adapter regression asserts this and that host-test/probe-discovery semantics are not implicated.
6. **Round-1 finding 4 (post-collection failures).** The second pre-build snapshot and pre-build drift failure paths now receive the known unavailable provenance, so their records publish schema 2 with null Git state. Dedicated regressions cover both paths.
7. **Round-1 finding 5 (bounded collector rule).** Availability rules are limited to the two fixed public phases; an arbitrary detail string cannot enter the identity. Collector and build-path regressions assert the bound.
8. **Earlier test-author error.** The first cross-mode reuse regression leaked `FAKE_CMAKE_NO_OUTPUT` into the second fixture build, causing a test setup failure. The test now clears that variable; no product behavior changed.
9. **Approved Git-failure behavior change.** Four legacy `test_git_invalid_*` build-runner tests that expected `BUILD_GIT_INVALID` now assert the approved snapshot success and bounded identity; the strict `git_evidence` rejection remains separately tested.
10. **Fixture byte failure (ENVIRONMENT, unresolved).** The working `tools/stm32-toolkit/tests/fixtures/build-nobits/template-rendered.ld` is 1118 bytes with 74 CRLF pairs while its committed HEAD blob is 1044 bytes with none (`git ls-files --eol`: `i/lf w/crlf attr/(none)`; `git diff` clean). Before the approved action, the fixture diff was verified clean. The explicitly authorized command `git -c core.autocrlf=false checkout-index -f -- tools/stm32-toolkit/tests/fixtures/build-nobits/template-rendered.ld` executed with exit 0, but the raw bytes were unchanged; the required post-check (`raw bytes == git show HEAD:<path>`) did not pass. Per the correction boundary, no alternate writer or loop was used. The single fixture test therefore still fails at the pre-existing byte comparison between generated LF output and the CRLF working fixture. This is classified ENVIRONMENT, not a product defect; the earlier claim that restoration had succeeded was inaccurate and is retained here as such.
11. **Earlier tool/environment notes.** `git restore --source=HEAD` was not permitted to me as a single validated PowerShell command, and the approved `checkout-index` action did not change bytes. No global or repository Git configuration was changed.

## Limitations and pending review

- This report is **not** acceptance. The primary owns independent complete-diff review and the final verdict after the report commit.
- No real compiler smoke, probe enumeration, attach, flash, reset, halt, IDE/VS Code session, physical target, packaging, installation, deployment, version bump, or remote publication was performed.
- The fixture byte mismatch remains an environment-level failing test and is not deferred as product work; a reviewer with the correct checkout environment must confirm it. The rest of the identity suite passes, but the full identity suite was not reported as fully passing.
- Schema-2 snapshot provenance intentionally remains build-only. Flash, debug, Target tests, Monitor, and acceptance still require Git-shaped provenance; broader hardware protocol versioning is a separate future slice.
- Existing broader release matrices, browser/UI checks, and hardware qualification remain out of scope and were not run.
