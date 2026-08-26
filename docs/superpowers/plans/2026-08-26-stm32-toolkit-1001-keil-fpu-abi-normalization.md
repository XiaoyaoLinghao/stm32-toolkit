# STM32TK-1001 Keil FPU/ABI Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Repository ownership overrides fresh-agent defaults: the same existing GPT-5.6-luna/max implementer owns every implementation task, and GPT-5.6-sol independently reviews each complete task diff.

**Goal:** Make the public Keil conversion emit one valid, source-evidenced GCC FPU/ABI pair for the smallest real ARMCC Cortex-M4/FPU2 scenario, then rebuild the exact candidate/runtime and resume H1 without a project workaround.

**Architecture:** Keil inspect remains the raw source-of-truth adapter. One closed pure decision in `migration/planner.py` converts raw FPU/ABI evidence into either an atomic GCC pair or one stable blocker; generation validation remains unchanged. After product acceptance, the candidate is rebuilt from the accepted source, the managed runtime is fresh-replaced, and the prior conversion commit receives a new guarded child correction before configure/build resumes.

**Tech Stack:** CPython 3.12.10, pytest 8.4.2, Python dataclasses/JSON, STM32 Toolkit 0.9.0, local Git, CMake 4.3.1, Ninja 1.13.2, GNU Arm Embedded 14.3.1.

## Global Constraints

- Frozen design: `docs/superpowers/specs/2026-08-26-stm32-toolkit-1001-keil-fpu-abi-normalization-design.md` at commit `a14048e8f371bc652a282a9644cfd6f0980b73d5`.
- Full accepted Toolkit base: `77514c441854bf7a8218eb2974e54abac478e31b`; accepted product code head at that base: `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa`.
- Product implementation owner: the existing GPT-5.6-luna/max agent. Specification, review, and acceptance owner: GPT-5.6-sol primary.
- Production scope is `migration/planner.py`; test scope is `test_migration_plan.py`. Generation validation, schemas, inspect, CLI/MCP public schemas, version, dependencies, runtime model, and project input are unchanged.
- No hardware/probe, golden mutation, push, PR, merge, tag, release, remote branch, new runtime family, Python range, Agent logic, MCP registration, provider, backend, controller, CI, or collaboration automation.
- Classify every failure before changing code. A pure code failure is PRODUCT and cannot be deferred. Keep release verification out of Task 1.
- Remove disposable pytest, build, acquisition, object, and scratch artifacts after preserving minimum formal evidence. Never remove source-controlled fixtures or failure evidence still needed for diagnosis.

---

### Task 1: Normalize the atomic Keil-to-GCC FPU/ABI pair with TDD

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`
- Modify: `tools/stm32-toolkit/tests/test_migration_plan.py`
- Create: `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-implementation-report.md`

**Interfaces:**
- Consumes: `KeilInspection.cpu`, `.fpu`, `.float_abi`, and `.compiler`; existing `_normalize_float_abi(raw)`; existing `MigrationBlocker` and guarded apply lifecycle.
- Produces: `_normalize_target_fpu_abi(inspection: KeilInspection) -> tuple[str | None, str | None, str | None]`, interpreted as `(generated_fpu, generated_float_abi, blocker_code)`. Exactly one of an atomic pair, an all-absent pair, or one blocker is returned.

- [ ] **Step 1: Freeze RED preconditions.** Require current Toolkit HEAD to be the single plan-only child of design commit `a14048e8f371bc652a282a9644cfd6f0980b73d5`, clean status, unchanged product files from `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa`, campaign head `d701c7142cf0bad9b03a690cf0456ecc97e3484f` clean/remote0, runtime-state SHA-256 `8404e3f79306aa096ba7e3014256c663852292e9084802277dd174195a1c2c1f`, and no hardware/network/remote access. Record the full current HEAD plus the exact two source/test before hashes.

- [ ] **Step 2: Write the vertical failing test first.** In `test_migration_plan.py`, add a test that creates a Git-backed ARMCC project with `CPUTYPE("Cortex-M4") FPU2`, no `uFloatingPoint`, one `main.c`, valid memory/output facts, and no migration blockers. Plan and apply conversion, load the resulting model, and call `plan_project_configuration`. Assert:

```python
from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.project_model import load_project_model

assert manifest["target"]["fpu"] == "fpv4-sp-d16"
assert manifest["target"]["floatAbi"] == "hard"
configuration = plan_project_configuration(load_project_model(repo))
cmake = next(file for file in configuration.files if file.path == "CMakeLists.txt")
text = cmake.after_bytes.decode("utf-8")
assert "-mfpu=fpv4-sp-d16" in text
assert "-mfloat-abi=hard" in text
```

The test must also assert the original inspection still contains `fpu == "FPU2"` and `float_abi is None`.

- [ ] **Step 3: Run the one RED test and preserve failure text.** From `tools/stm32-toolkit`, run with the frozen user interpreter:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures','-q']))"
```

Expected RED: the manifest contains raw `FPU2` without `floatAbi`, or configuration raises `GENERATION_MODEL_INVALID` with pairing rule. Any unrelated failure is classified before proceeding.

- [ ] **Step 4: Write negative RED tests.** Add exact tests for: unsupported raw FPU produces one deterministic `MIGRATION_FPU_UNSUPPORTED`; recognized FPU with absent ABI outside the frozen ARMCC tuple produces `MIGRATION_FLOAT_ABI_REQUIRED`; explicit ABI without FPU produces `MIGRATION_FLOAT_ABI_REQUIRES_FPU`; neither field produces neither manifest key nor flag; every blocker prevents apply; existing explicit `0/1/2/soft/softfp/hard` mappings remain unchanged.

- [ ] **Step 5: Implement the one closed decision.** In `planner.py`, add the frozen mapping and pure helper:

```python
_KEIL_FPU_EVIDENCE = {("cortex-m4", "FPU2"): "fpv4-sp-d16"}

def _normalize_target_fpu_abi(
    inspection: KeilInspection,
) -> tuple[str | None, str | None, str | None]:
    raw_fpu = (inspection.fpu or "").strip()
    raw_abi = (inspection.float_abi or "").strip()
    if not raw_fpu:
        if raw_abi:
            return None, None, "MIGRATION_FLOAT_ABI_REQUIRES_FPU"
        return None, None, None
    fpu = _KEIL_FPU_EVIDENCE.get((inspection.cpu.casefold(), raw_fpu.upper()))
    if fpu is None:
        return None, None, "MIGRATION_FPU_UNSUPPORTED"
    if raw_abi:
        abi, blocker = _normalize_float_abi(raw_abi)
        if blocker is not None:
            return None, None, blocker
        assert abi is not None
        return fpu, abi, None
    if inspection.compiler == "armcc" and inspection.cpu.casefold() == "cortex-m4" and raw_fpu.upper() == "FPU2":
        return fpu, "hard", None
    return None, None, "MIGRATION_FLOAT_ABI_REQUIRED"
```

The implementation order is: normalize empty strings to absence; accept all-absent; reject ABI-without-FPU; map only the exact FPU tuple; reject unknown FPU; preserve existing explicit ABI normalization; use `hard` only for `compiler == "armcc"`, `cpu.casefold() == "cortex-m4"`, raw `FPU2`, and absent raw ABI; otherwise require ABI. `_inspection_blockers()` and `_manifest_proposal()` call this same helper. A blocker path emits neither member of the pair. Use stable messages tied to each exact code; do not change blocker ordering outside this decision.

- [ ] **Step 6: Run GREEN focused tests.** Run the vertical test, all FPU/ABI migration tests, guarded apply tests, and generation target-option tests. Exact command:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','tests/test_generation.py','-q','-k','fpu or float_abi or keil_conversion']))"
```

Require exit 0. Record collected/passed counts and explain the `-k` risk selection; do not run unrelated release/hardware matrices.

- [ ] **Step 7: Run the affected migration file once.** Run all of `tests/test_migration_plan.py` with the same source-prepend harness. Require exit 0 and clean `.pytest_cache`/temporary output cleanup after recording results.

- [ ] **Step 8: Inspect scope and commit product code/tests.** Require only the two authorized product/test files changed, `git diff --check` passes, no dependency/lock/schema/version/public CLI/MCP change, and campaign/runtime remain unchanged. Commit with `fix(vs10a): normalize Keil FPU ABI conversion`. Record the resulting product code head.

- [ ] **Step 9: Write and commit the implementation report.** The report records accepted base `77514c441854bf7a8218eb2974e54abac478e31b`, design/plan commits, product code head before the report commit, exact RED/GREEN evidence, path scope, failure classification, and no self-acceptance. It must not claim hardware/H1 PASS or contain its own report commit SHA. Commit only the report with `docs(vs10a): report FPU ABI normalization` and stop for Sol review.

---

### Task 2: Independent Sol complete-diff review and acceptance

**Files:**
- Review: complete `77514c441854bf7a8218eb2974e54abac478e31b..Task1CodeHead` diff
- Create: `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-3d-fpu-abi-sol-review.md`

**Interfaces:**
- Consumes: Task 1 code head and report; real blocker evidence `C:\tmp\stm32tk-vs10a-legacy-campaign\evidence\task-6-configure-blocker.json` SHA-256 `0720b0d3b829497808eca874f5b644c1a4f89a59b80ab6163206abaea68d3fe9`.
- Produces: one `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED` verdict. Task 3 cannot begin without `ACCEPTED`.

- [ ] **Step 1: Create a clean detached review worktree at the returned code head.** Audit tracked/untracked, committed/uncommitted, and pushed/unpushed state first. The review worktree has no local edits and no campaign mutation.

- [ ] **Step 2: Review the complete diff.** Confirm the pure helper is the only source of both blockers and manifest fields, raw inspect remains unchanged, frozen mapping is exact, explicit mappings are preserved, generator validation is not relaxed, blockers cannot apply, and no product special case or support-range expansion exists.

- [ ] **Step 3: Independently rerun the vertical test and focused negatives.** Use the same CPython 3.12.10 source-prepend harness in the review worktree. Run only the vertical regression, FPU/ABI negatives, guarded apply, and generation pairing/flag tests. Require exit 0 and reconcile counts with Task 1.

- [ ] **Step 4: Issue and commit the verdict.** Every finding cites path, observed/expected behavior, evidence, and command. `ACCEPTED` requires no unresolved product defect. Remove the exact review worktree and disposable pytest artifacts after preserving the report.

---

### Task 3: Build the accepted replacement candidate and fresh-replace the runtime

**Files:**
- Create in campaign evidence: FPU-fix precondition, backend acquisition, closed wheelhouse, candidate build/verify/repeat, runtime retirement/replacement records.
- Create only in campaign scratch: exact backend downloads, closed wheelhouse, canonical CRLF source worktree, repeat-build directory.
- Do not modify campaign project or Toolkit source in this task.

**Interfaces:**
- Consumes: Sol-accepted Task 1 product code head, active 64-wheel runtime set, exact two backend identities from the design, existing candidate builder and verifiers.
- Produces: one verified 0.9.0 replacement candidate and exactly one matching active runtime. Task 4 consumes its source commit and release-manifest hash.

- [ ] **Step 1: Freeze preconditions.** Require Sol `ACCEPTED`, exact code head/tree/clean branch, campaign project `d701c7142cf0bad9b03a690cf0456ecc97e3484f` clean/remote0, old runtime identity/state, empty scratch, official backend URLs/hashes/sizes, and no process holding the exact runtime path.

- [ ] **Step 2: Acquire only the two build backends.** Use CPython 3.12.10 `-I` and a standard-library redirect-rejecting handler. Make at most one request per exact URL. Require HTTP 200, final URL equality, Content-Length/size/hash, ZIP CRC, member identity, and RECORD integrity. No resolver, index, mirror, redirect, dependency, or alternate artifact.

- [ ] **Step 3: Form the exact 66-wheel closed set.** Copy the active runtime's exact 64 wheels only after member/hash equality, add the two verified backends, require count 66 and the frozen filename/path-set digest. No installed package or shared cache is a wheel source.

- [ ] **Step 4: Build twice from a canonical CRLF detached worktree.** Run `tools/release/build_0900_artifacts.py build` with all default verifiers into a distinct `runtime/fpu-abi-candidate` path, then a disposable repeat path. Require source archive equality after canonical normalization and byte-identical 13-file releases.

- [ ] **Step 5: Verify the candidate.** Require 13 top-level assets, 12/12 checksums, collision-safe extraction, `verify-bundle status=ok`, sourceCommit/release manifest binding, 64 runtime wheels, SBOM/licenses/compatibility/troubleshooting/Monitor assets, Toolkit/Monitor wheel member binding, 48 MCP tools, 8 Skills, and no duplicate archive member.

- [ ] **Step 6: Fresh-replace only the managed runtime.** Preserve old state/manifest/package hashes and no-process proof. Resolve and validate the exact campaign `data/runtime` path, retire only that path, and Bootstrap only from the accepted extracted candidate with explicit ToolkitRoot/DataRoot/ProjectRoot. Same-version upgrade/repair is forbidden.

- [ ] **Step 7: Verify the single runtime.** Require active/highest 0.9.0, generation 1, accepted sourceCommit and manifest SHA, CPython 3.12.10 isolated imports, doctor `ok=true`, 48 MCP tools, 8 Skills, no staging/second runtime/process holder, and zero campaign project changes.

- [ ] **Step 8: Clean and report.** Preserve formal evidence and the verified candidate/extraction; remove exact acquisition/wheelhouse/canonical-source/repeat scratch after path validation. Require scratch empty, Toolkit clean, campaign project clean/remote0, no hardware/golden/remote action, then stop for Sol source/runtime reconciliation.

---

### Task 4: Correct the conversion child commit and resume P1c H1

**Files:**
- Modify through public conversion only: `.stm32-project.json`, `artifacts/migration/conversion-report.json`, `artifacts/migration/conversion.patch`
- Create through public configuration only: Toolkit-managed project configuration files from the accepted plan
- Create in campaign evidence: corrected conversion/configuration records, two immutable build runs, `memory-comparison.json`, `p1c.json`, updated campaign manifest, and H1 implementation report
- Create tracked report: `docs/codex/returns/STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP/task-5-p1c-h1-implementation-report.md`

**Interfaces:**
- Consumes: clean project head `d701c7142cf0bad9b03a690cf0456ecc97e3484f`, accepted replacement runtime, frozen Task 5 Steps 2-10 behavior.
- Produces: clean local corrected-conversion commit, P1c configuration head, two reproducible public builds, complete H1 evidence, and a stop for Sol review. Hardware remains prohibited.

- [ ] **Step 1: Rerun fresh inspect and two conversion dry-runs.** Require raw inspect still reports ARMCC/Cortex-M4/FPU2/null, F429ZG/SPL, 53 C/0 asm/38 includes/one startup/no blockers. Both plans must be deterministic and propose only the three existing conversion artifacts; proposed manifest must contain exact `fpv4-sp-d16/hard`.

- [ ] **Step 2: Apply only the fresh plan.** Parse its plan ID only from the immediately preceding successful envelope, replan internally, apply with `--authorized`, require `git diff --check`, original Keil input/historical-output hashes unchanged, and commit the three corrected conversion artifacts as a child of `d701c7142cf0bad9b03a690cf0456ecc97e3484f`.

- [ ] **Step 3: Run the exact public configuration cycle.** Dry-run `project configure --project-root <campaign-project> --json`, inspect exact managed inventory and `-mfpu=fpv4-sp-d16`/`-mfloat-abi=hard`, parse the fresh plan ID, then apply the same plan with `--authorized`. Do not create `linker/vs10a.ld` or a mailbox reservation. Commit the managed configuration; this is the P1c source/config head.

- [ ] **Step 4: Build twice with no intervening source/config change.** Invoke the managed runtime public `build --project-root <campaign-project> --preset arm-debug --json` twice. After each run copy envelope/result/input identity/ELF/MAP/HEX/log into distinct immutable evidence before the next run.

- [ ] **Step 5: Prove reproducibility and H1 semantics.** Require identical input snapshot, build ID, ELF/MAP/HEX hashes as contracted, entry/vector/reset facts, source/config Git head, and toolchain pins. Validate memory/segments, vector SP `0x20030000`, Thumb Reset_Handler, `main`, `TIM3_IRQHandler`, typed DWARF non-volatile `testtime`, no unresolved strong symbol/overflow/stale input/mailbox, and free `0x2002EFF0..0x20030000`.

- [ ] **Step 6: Preserve the semantic boundary.** Prove D4/test source Unicode equals the accepted project input, original uvprojx/ARMCC startup/historical AXF/MAP/HEX hashes remain unchanged, and P1c adds no instrumentation, fault, hardware-control, or mailbox behavior.

- [ ] **Step 7: Write evidence/report and clean.** Record conversion/config/P1c commits and all exact evidence hashes. The tracked report names the P1c code/config head before its report commit and does not self-accept. Remove only run-scoped build/scratch/temp artifacts after preserving immutable formal evidence. Require campaign and Toolkit worktrees clean, scratch empty, runtime unchanged, remote0, and no hardware/golden/network/remote mutation.

- [ ] **Step 8: Stop for independent Sol H1 review.** Sol reviews complete `b83b404c8da6993658586fa1b553d715f95993c1..P1cHead` campaign diff plus complete accepted Toolkit-base-to-final product diff, reruns proportionate H1 checks, and issues one verdict. Hardware Task 7 remains blocked until `ACCEPTED`.
