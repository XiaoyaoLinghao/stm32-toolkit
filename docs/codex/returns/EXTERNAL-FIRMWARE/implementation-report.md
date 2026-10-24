# EXTERNAL-FIRMWARE Implementation Report

## Identity

- Module: `EXTERNAL-FIRMWARE`
- Phase: report authored during local v1.3.0 version integration after the accepted offline software review
- Historical feature source branch: `codex/external-firmware`
- Report authoring branch: `codex/v1.3.0`
- Accepted base: `6b4c13b6fa76f320503b14679c8eb7bfc712c9af`
- Approved specification and plan (primary-owned inputs): `docs/superpowers/specs/2026-10-23-external-firmware-design.md`, `docs/superpowers/plans/2026-10-23-external-firmware-plan.md`
- Historical feature CodeHead: `4f002cd1479dc98c2dc9c48d7e75dddf896de2f2`
- Working tree: the historical feature state was the source branch `codex/external-firmware` at CodeHead `4f002cd1`. This report was authored during local v1.3.0 version integration on `codex/v1.3.0`, when multiple version metadata and documentation edits were pending in the working tree; it was not the only change created at its authoring stage. It records the accepted base and the historical feature CodeHead, and it has no own report commit SHA and does not contain future commit SHAs or moving commit totals.

The primary review record is `docs/codex/returns/EXTERNAL-FIRMWARE/review.md`: **ACCEPTED_WITH_FIXES for the approved offline software slice**, not hardware, installation or release qualification. This report is not a new acceptance verdict.

## Ownership and review status

The primary conversation agent owns the specification, orchestration, independent review and acceptance. The local Claude Code CLI 2.1.308, using the unchanged configured `deepseek-v4.1-flash[1m]` route, owns implementation, tests and corrections. The implementer does not approve its own diff. The primary reviewed the complete accepted-base-to-CodeHead diff in a clean exact-head checkout and recorded the verdict separately. No hardware, original-project, installation, packaging, version-bump or remote action was performed in this slice.

## Delivered behavior

- Added three source-only public MCP tools with the normal project/data/session root guards:
  - `stm32_firmware_import(firmwarePath, expectedSha256, format, target, flashRegions, baseAddress=None, planId=None, authorized=False)` returns a deterministic read-only PLAN without `planId`; with the exact `planId` and `authorized=true` it re-reads and re-analyzes the source before persisting an immutable import. `authorized=true` without `planId` is an error.
  - `stm32_firmware_admit(importId, expectedSha256)` is offline and read-only, rebuilds the normalized image from the stored source and parameters, and reports `offlineReady=true`/`hardwareVerified=false`.
  - `stm32_flash_imported(probeId, importId, expectedSha256, authorized)` revalidates admission before any supervisor/lease/worker effect and again inside the owned action before attach/program; it writes a distinct external-flash receipt only after full readback and cleanup.
- Import identity and storage: original source copy, normalized `image.elf` and strict `record.json` live under a deterministic external workspace; the identity binds the Toolkit version, both root digests, portable source path/format/SHA-256/size, base address, target, reviewed Flash regions, image SHA-256/size, segment summaries and entry metadata. Timestamps do not participate in identity; conflicting imports are never overwritten.
- Source parsing covers strict ELF32 little-endian EM_ARM ET_EXEC (AXF is ELF), Intel HEX and BIN with explicit `baseAddress`. The normalized programming image is a minimal ARM ELF32 with PT_LOAD segments; the source SHA-256 and image SHA-256 are distinct public fields. BIN carries no debug symbols.
- Backend admission rejects the whole image before the first driver call unless every byte is covered by the attached target's declared contiguous Flash intervals; gaps, non-Flash intervals and ambiguous overlapping maps are rejected. Normalized sector erase, `trustCrc=false`, `keepUnwritten=true`, bounded readback and owned cleanup are reused. No chip erase, unlock fallback, recovery-under-reset, reset, resume, handoff, debug, Monitor or Target-test capability was added.
- CLI mirrors the route as `firmware import` (explicit `--dry-run` or `--apply --plan-id`/`--authorized`), `firmware admit` and `flash-imported`, with the existing root/session/JSON conventions and the documented parameter names.
- Updated public inventory, architecture/user/README guidance and the affected flash/build/migrate skills. Guidance keeps plan/apply/admit order explicit, separates hardware authorization, states that imported receipts do not admit debug/Monitor/Target tests, and documents `postFlash` as applying to successful flashes rather than every failure result.

## Changed files (implementation slice)

- `README.md`
- `README_zh-CN.md`
- `docs/architecture.md`
- `docs/user-guide.md`
- `schemas/probe-protocol.schema.json`
- `skills/build-firmware/SKILL.md`
- `skills/flash-firmware/SKILL.md`
- `skills/migrate-keil/SKILL.md`
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/src/stm32_toolkit/external_firmware.py`
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/supervisor.py`
- `tools/stm32-toolkit/src/stm32_toolkit/probe/worker.py`
- `tools/stm32-toolkit/src/stm32_toolkit/public_inventory.py`
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/probe-protocol.schema.json`
- `tools/stm32-toolkit/tests/fakes/fake_probe.py`
- `tools/stm32-toolkit/tests/fakes/fake_pyocd.py`
- `tools/stm32-toolkit/tests/test_debug_firmware.py`
- `tools/stm32-toolkit/tests/test_doctor.py`
- `tools/stm32-toolkit/tests/test_external_firmware.py`
- `tools/stm32-toolkit/tests/test_external_firmware_routing.py`
- `tools/stm32-toolkit/tests/test_external_firmware_workflow.py`
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`
- `tools/stm32-toolkit/tests/test_probe_protocol_v2.py`
- `tools/stm32-toolkit/tests/test_public_inventory.py`
- `tools/stm32-toolkit/tests/test_vs10a_target_v2_public.py`

Version `1.3.0` metadata, the integrated inventory counts and release packaging are owned by `STM32TK-130`, not by this slice. Any v1.3.0 final integrated test or build evidence is supplied by that integration phase and is not attributed retroactively to the original feature phase.

## Evidence

The primary review parsed the JUnit results and treated native `tool_use`/`tool_result` events and JUnit files, not CLI prose counts, as authority. Evidence is retained under `D:/codex-tmp/fi24`.

| Check | Identity | Result |
| --- | --- | --- |
| Initial feature fixture run | `c585` | 45 tests: 40 passed, 5 failed; failures corrected by the author |
| Broad regression | `6abb73bf3ef952405bbb146d0dba74912ce15291` | 1115 tests: 1113 passed, 2 failed (`feature.xml`); both failures were the two old `sys.modules` assertions expecting the previous lazy-import order after the intentional offline `pyocd.FileProgrammer` import |
| Native CLI follow-up | final correction; working-tree-equivalent to CodeHead `4f002cd1` | 191 tests: 191 passed, 0 skipped/failed/error (`feature-final.xml`), including all 52 new tests plus the full 139 `test_debug_firmware.py` tests in that order |
| Reused broad cases | unchanged production/test bytes at `6abb` | remaining 924 broad regression cases reused; not re-run merely to restate them |
| Primary clean checkout, feature tests | `6abb` | 52 new tests passed (`primary-feature.xml`) |
| Primary exact-head lazy-import tests | `4f002cd1` | 2 corrected tests passed (`primary-lazy.xml`) |

- Commands: `python -m pytest` with the exact file lists and temporary roots stored in `D:/codex-tmp/fi24/test-feature.jsonl` and `feature-final-command.txt`.
- Environment: Python 3.12.14, same-tree Toolkit/Monitor `PYTHONPATH`, read-only dependency donor `C:/data/stm32-toolkit/runtime/1.2.0/Lib/site-packages`, native Windows PowerShell, strict empty per-invocation MCP configuration.
- All programming, attach and readback paths used injected fakes. Production import/admission tests use constructors that fail if a backend path is touched, and missing-dependency regression blocks `pyocd` imports. No probe enumeration or physical driver was accessed.
- The native CLI follow-up prompt carried a stale clean-head label after a failed identity-less commit attempt. The actual test bytes were the staged correction, unchanged throughout and identical to CodeHead `4f002cd1`; the result is recorded as working-tree-equivalent evidence, not falsely labeled as the clean `6abb` evidence.
- Retained nonfatal warning: a dependency `pydantic` lifespan warning. No test was skipped or weakened to hide a failure.

## Limits

- This report covers an offline, synthetic/isolated software slice only. It does not establish physical target, flash, readback, run-state, power, timing or board-level qualification. Programming success in fakes is not a hardware PASS.
- No imported receipt admits debug, Monitor, Target tests, legacy flash evidence or a managed build identity. An imported image is an immutable snapshot, not the current project build.
- Native Keil UV4, automatic snapshot-to-managed admission and migration-baseline comparison are not implemented.
- Version alignment to `1.3.0`, build reproduction, package construction, installation/upgrade/rollback, release qualification and any publication remain separate `STM32TK-130` or later work. The `v1.2.0`-only qualification exception does not transfer.
- The primary conversation agent records the final full-diff verdict separately; this report is not acceptance.
