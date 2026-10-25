# ARMCC-FLOAT-ABI implementation report

## Ledger

- Module/slice: `ARMCC-FLOAT-ABI` bounded offline compatibility slice.
- Repository/branch: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`, branch `codex/armcc-float-abi`.
- Accepted base: `386d63bc2fc5c633c1296c87601ae188cf09ebfd`.
- Tested CodeHead (source state before this report commit): `1bf7a7a3b44538a13d826e1790d15bde2bf15532`.
- Governing design/plan: `docs/superpowers/specs/2026-10-25-armcc-float-abi-design.md`, `docs/superpowers/plans/2026-10-25-armcc-float-abi-plan.md`.
- Ownership: the primary conversation agent owns requirements, specification, plan, orchestration, independent complete-diff review and acceptance. The local Claude Code CLI implemented product code, tests and product guidance. This report is author evidence and cannot approve its own diff.
- Execution route: local Claude Code CLI with the user's existing provider/model configuration, which reported `deepseek-v4.1-flash[1m]`; it is not relabeled as an Anthropic model.
- The source ledger, accepted base, tested CodeHead, test results and environment facts below were supplied by the primary. The author did not run Git in this report phase.

## Implementation summary

The slice removes the unjustified numeric `uFloatingPoint` -> `soft`/`softfp` mapping. Numeric values are not proven ABI evidence and now produce a stable blocker. Literal `soft`/`softfp`/`hard` text remains an explicit project declaration only. One narrow, explicitly inferred and unverified candidate remains for ARMCC + Cortex-M4 + FPU2 when the selected target's raw `ArmAdsMisc/RvdsVP` is absent/empty or the historical value `2`; every other nonempty selector, unsupported compiler/CPU/FPU tuple, and unknown value fails closed. An explicit literal ABI cannot suppress a conflicting selector or unsupported FPU evidence. Existing target/group/file misc-control blockers remain in force.

One deterministic evidence object is re-derived from the bound/fresh inspection and exposed at preflight `analysis.floatAbi`, PLAN `floatAbi`, and the successful conversion report `floatAbi`. It includes raw compiler/version/CPU/FPU/ABI/RvdsVP evidence, normalized FPU/selected ABI, `origin` (`inferred`/`declared`/`blocked`/`not-applicable`), rule ID/reason, `baselineVerified: false`, a warning and compatibility `nextStep`. `nextStep` is used instead of `remediation` so the evidence does not violate the existing invariant that `remediation` is preflight-only blocker presentation. PLAN evidence participates in the deterministic plan ID and APPLY validation because it is derived from the bound inspection.

Guidance correction after the tested CodeHead was documentation-only: a blocked preflight stops progression toward APPLY, but when Git/root prerequisites permit, a read-only diagnostic PLAN can still be returned with blockers, and its plan ID is not applicable. No product behavior or validation was changed.

## Changed files at tested CodeHead

- `tools/stm32-toolkit/src/stm32_toolkit/keil/model.py` — raw selected-target `rvds_vp` inspection field with a default.
- `tools/stm32-toolkit/src/stm32_toolkit/keil/uvprojx.py` — capture selected target `ArmAdsMisc/RvdsVP` raw text.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/float_abi.py` (new) — bounded resolver and deterministic evidence serialization.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` — delegate normalization to the helper; expose shared analysis evidence; keep blocker precedence.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py` — derive PLAN `floatAbi` and bind it into the plan-ID payload.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py` — expose `analysis.floatAbi` and remediate the new selector blocker.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py` — record `floatAbi` in the conversion report.
- `tools/stm32-toolkit/tests/test_armcc_float_abi.py` (new) — ABI evidence, parity, options, selector, tamper/stale and no-write coverage.
- `tools/stm32-toolkit/tests/test_migration_plan.py` — absent-ABI fixture default, literal/numeric expectations, derived-evidence checks.
- `tools/stm32-toolkit/tests/test_migration_apply.py` — shared fixture no longer injects a numeric ABI.
- `tools/stm32-toolkit/tests/test_keil_inspect.py` — selected-target raw selector capture and scoping; final repair passes `simple_project(...).parent` to inspection.
- `tools/stm32-toolkit/tests/test_ai_call_guidance.py` — new selector remediation classification.
- `docs/user-guide.md` — ABI evidence and diagnostic-PLAN guidance.
- `skills/migrate-keil/SKILL.md` — ABI evidence, authorization and diagnostic-PLAN guidance.

After the tested CodeHead, only documentation changed: `docs/user-guide.md`, `skills/migrate-keil/SKILL.md` and this report. No code, test, specification or plan was edited.

## Test evidence

Environment supplied by the primary: Windows CPython 3.12.14 at `D:/codex-tmp/kx23/venv/Scripts/python.exe`; current toolkit/monitor `PYTHONPATH`; read-only dependencies under `C:/data/stm32-toolkit/runtime/1.3.0/Lib/site-packages`; run-owned roots under `D:/codex-tmp/ab25`. Exact native argv and JUnit evidence are retained there.

Final 8-module suite, run independently by both the author and the primary:

- Modules: `test_armcc_float_abi.py`, `test_keil_inspect.py`, `test_migration_plan.py`, `test_migration_apply.py`, `test_keil_preflight.py`, `test_ai_call_guidance.py`, `test_mcp_migration_build.py`, `test_generation.py`.
- Result as reported by both owners: 672 passed, 0 failed, 0 errors, 0 skipped (32 ABI + 118 inspect + 98 plan + 55 apply + 20 preflight + 12 AI guidance + 19 MCP + 318 generation).
- The author's execution is supported by native PowerShell `tool_use`/`tool_result` events and JUnit. The final native output did not print an explicit pytest exit code; no CLI exit `0` is substituted for it. The primary's subprocess result recorded actual exit `0`.

Initial final-state attempt at `4eea45d61048f68d3be1d5d7376ad8a7e0fe1370`: each owner observed 671 passed and 1 failed. The single failure was the new selected-target scoping test using `simple_project`'s returned `.uvprojx` file as `inspect_keil`'s root. The repair changed exactly two calls to `.parent`; no product code, validation or assertions were relaxed.

Primary broader shared-fixture consumers: 311 passed, 0 failed, 0 skipped at `4eea45d6`; reused for `1bf7a7a3` because product code and shared fixtures were unchanged. Primary baseline at accepted base: 172 passed. Skill `quick_validate` at `1bf7a7a3` reported `Skill is valid!`.

Non-failing `pydantic_settings` and broad CLI `runpy` warnings were retained. No original-project modification, hardware access, runtime/global change, installation, packaging, version bump or remote action was performed.

## Limitations

- The original project was observed read-only only; its configuration SHA remained unchanged and the expected AXF/MAP were absent. Binary ABI/calling-convention compatibility is therefore unverified, and `baselineVerified` is false in every evidence object.
- This slice does not parse AXF, objects, libraries or real compiler command lines. It is a bounded compatibility rule, not a generic `RvdsVP` decoder or proof that `hard` is the original ABI.
- Tests are offline synthetic/GNU-generation checks; no hardware or release matrix was run. This report is not release qualification.
- Toolkit version remains 1.3.0; the integration target is 1.3.1 after the remaining improvements. The frozen/installed 1.3.0 does not contain this source behavior.
- This report deliberately records no final commit SHA; the report commit follows the tested CodeHead.
