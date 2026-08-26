# STM32TK-1001 Keil FPU/ABI Normalization Design

**Status:** Frozen for implementation under the user's standing direction to choose the safest bounded option and continue without repeated approval requests.

**Module and phase:** STM32 Toolkit VS10-A, H1 product-blocker correction before Task 5 configuration and builds.

**Accepted Toolkit base:** `77514c441854bf7a8218eb2974e54abac478e31b`

**Accepted product code head at the base:** `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa`

**Ownership:** GPT-5.6-sol owns this specification, plan, risk decisions, complete-diff review, and acceptance. The same single GPT-5.6-luna/max implementer owns production code and tests. The implementer cannot accept its own diff.

**Active local state:** Toolkit branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`, no PR or authorized remote action. Campaign project head `d701c7142cf0bad9b03a690cf0456ecc97e3484f`, tree `9ff09f73268dade9d0d3cd447e428b0874be273b`, clean with zero remotes. The single active runtime is 0.9.0 generation 1 from product commit `3db9e0013bd2f62c478598e0f95fe2c27aeefdfa` with runtime-state SHA-256 `8404e3f79306aa096ba7e3014256c663852292e9084802277dd174195a1c2c1f`.

## 1. Reproduced defect and root cause

The real derived Keil profile contains `CPUTYPE("Cortex-M4") FPU2`, uses ARMCC 5.06, and has no `uFloatingPoint` element. Public inspect correctly preserves that raw evidence as `fpu="FPU2"`, `float_abi=null`, and `compiler="armcc"`.

The migration planner incorrectly writes raw `FPU2` to `.stm32-project.json` and omits `floatAbi`. Conversion dry-run and apply therefore succeed with an incomplete and non-GCC target pair. Public `project configure --dry-run` then correctly fails closed with `GENERATION_MODEL_INVALID`, field `target.fpu`, rule `pairing`.

This is a migration-boundary PRODUCT defect, not a generation-validator, project-input, environment, or report defect. The generation validator remains the correct safety boundary and must not be relaxed.

Independent scenario evidence fixes the intended target contract:

- historical `Project/OBJ/LWIP.axf` has ARM ELF flags `Version5 EABI, hard-float ABI`;
- the already-frozen compile contract passed all 53 selected C translation units with `-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard`;
- emitting no FPU/ABI pair would discard real target facts, while emitting raw `FPU2` would produce an invalid GCC flag.

## 2. Runnable scenarios

1. Inspecting the real ARMCC Cortex-M4/FPU2 profile continues to report the raw Keil evidence unchanged, including a missing raw float-ABI element.
2. Converting that inspection emits the closed GCC target pair `fpu="fpv4-sp-d16"` and `floatAbi="hard"`; the same manifest immediately reaches a deterministic public configuration plan.
3. A Keil inspection with no FPU and no float ABI continues to omit both fields and configure without FPU flags.
4. An unsupported Keil FPU token, a missing ABI outside the one frozen ARMCC/Cortex-M4/FPU2 case, or an ABI without an FPU fails during conversion with one stable blocker and cannot be applied.

## 3. Non-goals

- Do not change Keil inspect's raw public model or JSON fields.
- Do not relax schema or generation pairing/format validation.
- Do not infer from device names, project names, file paths, the historical AXF at product runtime, or an MCU support matrix.
- Do not add ARMClang, Cortex-M7, double-precision, softfp-default, alternate FPU-token, compiler, Python, Agent, runtime, MCP, provider, backend, controller, CI, or collaboration support.
- Do not edit the campaign manifest by hand, modify the original/derived uvprojx for this defect, rewrite history, or use historical build outputs as GCC build inputs.
- Do not access hardware, the golden project, or any remote Git operation in this slice.

## 4. Considered approaches

### 4.1 Patch the campaign manifest or derived profile — rejected

This bypasses the public conversion contract, consumes a new project exception, and does not by itself prevent raw `FPU2` from becoming an invalid GCC flag.

### 4.2 Relax configure or omit both FPU/ABI fields — rejected

Relaxation would move an incomplete target into generated build files. Omitting both fields would contradict the historical hard-float ELF and the accepted 53-unit compile contract.

### 4.3 Closed migration normalization — selected

Keep raw inspection separate from generated-build semantics. Normalize only the smallest verified real tuple at the migration boundary and reject every unsupported or incomplete tuple before apply.

## 5. Frozen public behavior

### 5.1 Raw inspection

No inspector behavior changes. For the real profile the inspection remains:

```json
{
  "cpu": "Cortex-M4",
  "fpu": "FPU2",
  "float_abi": null,
  "compiler": "armcc"
}
```

### 5.2 Generated target normalization

The migration planner treats FPU and float ABI as an atomic generated pair.

| Raw compiler | Raw CPU | Raw FPU | Raw ABI | Generated FPU | Generated ABI | Result |
|---|---|---|---|---|---|---|
| `armcc` | `Cortex-M4` | `FPU2` | absent/empty | `fpv4-sp-d16` | `hard` | accepted frozen fallback |
| any | any | absent/empty | absent/empty | absent | absent | accepted no-FPU pair |
| any | `Cortex-M4` | `FPU2` | existing supported value | `fpv4-sp-d16` | existing `_normalize_float_abi` result | accepted |
| any | any | unsupported nonempty value | any | absent | absent | `MIGRATION_FPU_UNSUPPORTED` blocker |
| not the frozen fallback | any | supported FPU | absent/empty | absent | absent | `MIGRATION_FLOAT_ABI_REQUIRED` blocker |
| any | any | absent/empty | nonempty | absent | absent | `MIGRATION_FLOAT_ABI_REQUIRES_FPU` blocker |

The existing explicit raw ABI mapping remains unchanged. No incomplete pair or raw Keil FPU token enters the manifest. Blocker ordering and plan identity remain deterministic.

### 5.3 Generated files

For the real scenario `.stm32-project.json` must contain:

```json
"target": {
  "device": "STM32F429ZGTx",
  "core": "cortex-m4",
  "fpu": "fpv4-sp-d16",
  "floatAbi": "hard",
  "devicePack": "Keil.STM32F4xx_DFP.2.17.1"
}
```

The ensuing configuration plan must contain exactly `-mfpu=fpv4-sp-d16` and `-mfloat-abi=hard`. It must not contain `-mfpu=FPU2`, omit only one member of the pair, or create `linker/vs10a.ld` or a mailbox reservation.

## 6. Implementation boundary

Production changes are limited to `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`. Tests are limited to `tools/stm32-toolkit/tests/test_migration_plan.py`, plus one existing public workflow/CLI test file only if required to prove the immediate convert-to-configure path without duplicating implementation details. Generation validation and schemas are not modified.

The planner owns two small pure helpers: one closed Keil-FPU normalization function and one atomic FPU/ABI decision function. `_inspection_blockers()` and `_manifest_proposal()` must consume the same decision so a blocker-producing tuple cannot leak different manifest bytes.

## 7. TDD and proportionate verification

The Luna/max implementer must first add a failing vertical regression that creates an ARMCC Cortex-M4/FPU2 project with no `uFloatingPoint`, plans/applies conversion in a disposable Git repository, loads the produced model, and reaches `plan_project_configuration`. RED must show the current incomplete-pair failure. GREEN must prove the normalized pair and exact flags.

Focused negative tests cover unsupported FPU, required ABI, ABI-without-FPU, no-FPU/no-ABI, deterministic blockers, and blocked apply. Existing explicit ABI normalization and generation pairing tests remain passing. Run only affected migration, generation target-option, workflow/CLI parity tests with an explicit risk reason; do not run the release matrix, hardware, or unrelated suites.

The implementation report records accepted base `77514c441854bf7a8218eb2974e54abac478e31b`, the product code head before its report commit, exact RED/GREEN commands, changed files, and failure classifications. Sol reviews the complete accepted-base-to-code-head diff in a clean isolated worktree and independently reruns the vertical regression plus focused negative/parity tests.

## 8. Candidate invalidation and H1 resume

The active candidate/runtime remains valid for its own bytes but is ineligible for H1 because it produced the defective conversion. Only after Sol accepts the product diff may the same Luna/max implementer build one distinct replacement candidate from the accepted code head.

The 64 frozen runtime wheels are copied from the active runtime only after byte/member/hash equality. The build-only backends are reacquired at most once each, with redirect rejection and exact tuple verification, from:

- `setuptools-84.0.0-py3-none-any.whl`, 818216 bytes, SHA-256 `51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670`, `https://files.pythonhosted.org/packages/95/9c/c510029fc6ef33a6275cd2c5d3cecd6613dfd6aa401d57c54f1c18852ccf/setuptools-84.0.0-py3-none-any.whl`;
- `wheel-0.48.0-py3-none-any.whl`, 33320 bytes, SHA-256 `3217dcc807155e45db462d7ef2431f5ddda0d7273b700d05a67b271ceb1287ab`, BLAKE2b-256 `2e2969cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449`, MD5 `75e4bbe15fefadbb91258c5e79b38aa3`, `https://files.pythonhosted.org/packages/2e/29/69cfbb602cd91690c55d38ba9fe53e6a7e76a6fa647bf38f19c138d25449/wheel-0.48.0-py3-none-any.whl`.

No resolver, index selection, redirect, mirror, alternate artifact, or dependency expansion is allowed. The closed set remains exactly 66 wheels. The usual 13-file/12-checksum candidate, release manifest, SBOM, licenses, compatibility, troubleshooting, Monitor, 48-MCP, 8-Skills, CPython 3.12.10, and single-runtime gates apply.

After candidate verification, retire only the exact campaign-managed runtime and fresh-bootstrap the replacement; same-version upgrade/repair remains forbidden. On clean campaign commit `d701c7142cf0bad9b03a690cf0456ecc97e3484f`, rerun public inspect/convert. The new plan must correct the three conversion artifacts through a new guarded local commit; do not edit or rewrite `d701c714...`. Then resume the frozen public configure and two-build H1 sequence.

## 9. Acceptance criteria

- The real raw inspection remains `FPU2/null/armcc`.
- New conversion emits `fpv4-sp-d16/hard`, never raw `FPU2`, and public configure dry-run succeeds deterministically.
- Unknown/incomplete tuples stop at conversion with the exact stable blocker and cannot apply.
- Focused RED/GREEN and independent review pass; complete diff has no unrelated product, schema, runtime, Agent, MCP, provider, backend, controller, or support-range change.
- Replacement candidate/runtime is source-bound to the accepted code head and passes all frozen inventory/security gates.
- Corrected conversion is a new child commit of `d701c714...`; original Keil inputs, historical outputs, D4/test logic, golden tree, hardware, and remote state remain untouched.
- The project and Toolkit worktrees finish clean, campaign scratch is empty, and only minimum formal evidence remains.
