# STM32TK-1001 Production SVD Compatibility Implementation Plan

> One `gpt-5.6-luna/max` implementer executes this plan by strict TDD. A
> `gpt-5.6-sol` reviewer independently reviews and accepts the complete diff.

**Goal:** Make the existing public schema-v3 SVD register workflow consume the
pinned official STM32F429 SVD through explicit project facts and a separate
read-only observation policy, without changing caller inputs or build behavior.

**Design:**
`docs/superpowers/specs/2026-08-27-stm32-toolkit-1001-production-svd-compatibility-design.md`

**Product accepted base:**
`0cdd142f80421c6aea59e81e963936779b05f00f`. Documentation commits through
`b528fc88` are Sol-owned planning bytes, not product implementation.

**Implementation root:** `C:\tmp\stm32tk-1001-legacy-hardware-impl`.

**Boundaries:** No project-repository write during this product slice; preserve its
uncommitted manifest/SVD correction. No hardware/backend/probe action, runtime
installation, remote/network action, version bump, migration change, raw override,
or direct PyOCD use.

## Task 1: RED/GREEN explicit schema-v3 SVD observation facts

**Tests:**

- `tools/stm32-toolkit/tests/test_project_model.py`
- `tools/stm32-toolkit/tests/test_generation.py`

**Product:**

- `schemas/stm32-project.schema.json`
- `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json`
- `tools/stm32-toolkit/src/stm32_toolkit/project_model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py`

- [ ] Write RED behavior tests first. Name the production mutations they catch:
  missing `svdDevice` binding, debug regions leaking into linker memory, absent
  model-hash participation, schema-v2 accidental acceptance, booleans accepted as
  integers, duplicate/overlap/overflow/empty region policy, and incomplete coupled
  fields. Use literal expected values, not production helpers.
- [ ] Run only the new nodes against `0cdd142f...`; require expected assertion
  failures caused by missing fields/behavior. Retain command, exit, selected count,
  and failure excerpts as RED evidence. Tests that error or pass immediately must
  be corrected before product code.
- [ ] Add optional schema-v3 `debug.svdDevice` and `debug.readableRegions` exactly
  as designed. Root and packaged schema bytes remain identical. The packaged v2
  validator must remove both fields, just as it removes existing schema-v3-only
  fields.
- [ ] Extend frozen `DebugSpec` with exact document device and an immutable tuple of
  read-only regions. Validate coupling, 1..64 count, integer/range/overflow,
  canonical unique names, and non-overlap after schema validation. Do not add an
  independent serializer.
- [ ] Include both fields in the existing generation model payload. Prove missing
  legacy fields preserve the old model and generated build/linker bytes, while
  explicit values alter only model/managed configuration identity.
- [ ] Run GREEN for Task 1 plus existing schema parity, schema2/schema3, explicit
  schema, native linker, standard-math, and generation contract nodes. Clean the
  exact basetemp after retaining failures if any.
- [ ] Run `git diff --check` and commit tests plus product as one Task 1 GREEN
  commit. The retained RED evidence must prove tests preceded product bytes.

## Task 2: RED/GREEN pinned decimal syntax and explicit document identity

**Tests:** `tools/stm32-toolkit/tests/test_svd.py`.

**Product:** `tools/stm32-toolkit/src/stm32_toolkit/debug/svd.py`.

- [ ] Write RED tests using small real XML fixtures. Cover decimal `00000010` as
  literal 10, ordinary decimal/hex compatibility, malformed/negative/binary/suffix
  rejection, exact firmware target plus different explicitly declared SVD document
  device, missing/wrong/casefold document identity rejection, and provenance
  revalidation of both devices and regions.
- [ ] Preserve and rerun every existing exact/family/partial/casefold rejection
  assertion. The new path passes only when `svd_device` is explicit; no prefix
  inference is allowed.
- [ ] Run RED and retain evidence. Each new test must fail for the missing product
  behavior, not because of fixture construction.
- [ ] Replace `int(value, 0)` with a bounded explicit decimal-or-hex parser. Decimal
  with optional `+` and leading zeros is base 10. Keep existing length/range and
  failure codes.
- [ ] Extend selection/provenance with exact firmware target and exact document
  device while preserving the default exact-equality behavior for old callers.
  Every register still must fit one trusted region.
- [ ] Run GREEN for the complete `test_svd.py` and affected `test_debug_read.py`.
  Run mutation checks for ignoring `svd_device`, reverting decimal base, skipping
  target provenance, and bypassing the range check.
- [ ] Run `git diff --check` and commit Task 2 tests/product separately.

## Task 3: RED/GREEN separate SVD regions through production composition

**Tests:**

- `tools/stm32-toolkit/tests/test_debug_firmware.py`
- `tools/stm32-toolkit/tests/test_debug_read.py`
- `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- `tools/stm32-toolkit/tests/test_monitor_observation.py`
- `tools/stm32-toolkit/tests/test_cli_hardware.py`
- `tools/stm32-toolkit/tests/test_mcp_hardware.py`

**Product:**

- `tools/stm32-toolkit/src/stm32_toolkit/debug/model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/debug/firmware.py`
- `tools/stm32-toolkit/src/stm32_toolkit/debug/read.py`
- `tools/stm32-toolkit/src/stm32_toolkit/hardware_workflows.py`
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`

- [ ] Write RED tests proving the production binding keeps linker
  `memory_regions` separate from immutable `svd_readable_regions`; region drift
  invalidates selection; register workflow and Monitor pass exact target/document/
  regions from the loaded project model; and `SvdError` retains its stable public
  code instead of becoming `HARDWARE_INTERNAL_ERROR`.
- [ ] Add one public scenario with a firmware target such as `STM32F429ZGTx`, SVD
  document `STM32F429`, and `GPIOE.ODR` inside an explicit debug region. Assert CLI
  and MCP adapter request shapes remain unchanged and no target/SVD/region/address
  can be supplied by the caller.
- [ ] Run RED against real production composition with only the slow/external probe
  boundary faked. Keep model load, selector, binding construction, request creation,
  result mapping, and cleanup real.
- [ ] Add `svd_readable_regions` to `DebugFirmwareBinding`; bind it only from
  schema-v3 debug regions. DWARF continues to use linker `memory_regions`.
- [ ] Pass explicit `svd_device` and separate regions through register and Monitor
  selection. Add only `SvdError` to the existing stable hardware exception set;
  preserve sanitization and unknown-exception behavior.
- [ ] Run GREEN for the six Task 3 files plus `test_mcp_server.py` and
  `test_mcp_roots.py`. Confirm MCP inventory count/names are unchanged.
- [ ] Run `git diff --check` and commit Task 3 tests/product separately.

## Task 4: Focused integration, external-input proof, and implementation return

- [ ] Run Tasks 1-3 test files together under CPython 3.12 with
  `-p no:cacheprovider` and a unique worktree-external `--basetemp`. Add the
  directly affected generation, debug binding/read, CLI/MCP inventory, and Monitor
  nodes only; do not run the whole release matrix without a new risk trigger.
- [ ] With no backend import or hardware access, load the exact campaign project and
  copied SVD SHA-256
  `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`
  through product code using the twelve frozen read-only address runs derived from
  the pinned document. Require 1,536 registers and `GPIOE.ODR` address
  `0x40021014`, size 4, field `ODR4` offset 4/width 1.
- [ ] Run these diff gates before return:

```powershell
git diff --check 0cdd142f80421c6aea59e81e963936779b05f00f..HEAD
git diff --name-only 0cdd142f80421c6aea59e81e963936779b05f00f..HEAD
git status --short --branch
```

  Stop on migration planner, FPU/ABI, compiler blocker, build templates, version,
  README, CLI/MCP signature/inventory, runtime, or unrelated product changes.
- [ ] Clean every disposable basetemp, coverage file, generated fixture, cache, and
  scratch output created by this slice after retaining minimum failure evidence.
  Preserve source tests, reusable fixtures, campaign project/SVD, shared caches, and
  report evidence. List exact residual cleanup failures and classify them.
- [ ] Commit a tracked implementation report separately at
  `docs/codex/returns/STM32TK-1001-SVD-COMPAT/implementation-report.md`. It records
  the product base, code/tests head before the report commit, exact commands/exits/
  counts, RED-before-GREEN evidence, external-input proof, diff scope, cleanup, and
  implementer verdict. It does not accept its own diff.

## Task 5: Sol independent acceptance and later integration

- [ ] In a clean isolated review worktree, Sol audits the complete
  `0cdd142f...`-to-returned-code-head diff and the separate report commit. Review
  every changed product/test file, public/error/security compatibility, schema2/3
  behavior, provenance, build/debug separation, and evidence accuracy.
- [ ] Sol independently runs only the focused tests and exact external-input proof
  justified by the diff. It verifies both implementation and review worktrees,
  diff checks, untracked state, and cleanup.
- [ ] Issue one verdict. `REVISION_REQUIRED` returns to the same Luna/max owner;
  Sol does not patch product code. H2 remains closed unless the verdict is
  `ACCEPTED`.
- [ ] After acceptance only, build/source-bind/checksum a new offline 0.9.0
  candidate from the accepted code head, install it through the existing pinned
  local runtime workflow, then return to the previously frozen project correction
  plan. Runtime packaging/install, project configure/build, and hardware H2 are
  integration stages, not evidence attributed to the product implementer.

No push, PR mutation, merge, close, tag, release, remote branch operation, network,
hardware, or direct backend action is part of this implementation plan.
