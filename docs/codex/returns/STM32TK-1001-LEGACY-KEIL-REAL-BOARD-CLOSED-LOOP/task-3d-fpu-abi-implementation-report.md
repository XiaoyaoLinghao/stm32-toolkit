# STM32TK-1001 Task 3d: FPU/ABI normalization implementation report

Implementation status: complete; independent GPT-5.6-sol review required.

This report covers Task 1 of the frozen Keil FPU/ABI normalization plan. It is
implementation evidence only: it is not self-acceptance and makes no hardware
or H1 claim. The stale intermediate compiler-path narrative from an earlier
revision is superseded by the accepted-base facts recorded below.

## Lineage

- Accepted product base: `77514c441854bf7a8218eb2974e54abac478e31b`
- Design commit: `9f9258c3f321229d5141aba17592397ae79246fe`
- Plan commit: `13b991bd0bfb2cffd89063e7e58d9629f9e20cd6`
- Task 1 code/tests head before this report-only commit:
  `6bf7fb3ad3fafe8c9068957c647bb5546018231b`
- Task 1 code/tests tree at that head:
  `73733549c501872c6402b2e3f64fefb13a0e3b88`

The report is committed separately from the code/tests commits. It deliberately
does not record the SHA of its own report-only commit or moving commit totals.

## Implementation

`planner.py` now defines the closed evidence mapping
`("cortex-m4", "FPU2") -> "fpv4-sp-d16"` and the pure
`_normalize_target_fpu_abi()` helper. It consumes only the existing
`KeilInspection.cpu`, `.fpu`, `.float_abi`, and `.compiler` evidence. Its result is
exactly either a normalized atomic pair, an all-absent pair, or one stable blocker.
Both `_inspection_blockers()` and `_manifest_proposal()` use this helper, so a
blocker cannot emit either manifest member. The existing explicit ABI mappings
(`0/1/2/soft/softfp/hard`) remain covered and unchanged.

`test_migration_plan.py` contains the vertical conversion/configuration test and
negative coverage for unsupported FPU, missing ABI, ABI without FPU, all-absent
evidence, guarded apply, and explicit ABI mappings.

## RED/GREEN evidence

The required vertical RED was observed before production implementation. The frozen
Python 3.12 command was:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures','-q']))"
```

It exited 1 with the old manifest value `FPU2` instead of the expected
`fpv4-sp-d16`; the original inspection was verified as `FPU2` with no raw ABI. The
seven new vertical/negative tests likewise produced the expected RED before the
helper and call sites existed.

After implementation, the exact brief GREEN command was:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','tests/test_generation.py','-q','-k','fpu or float_abi or keil_conversion']))"
```

It selected 32 tests and exited 0 with 32 passed (10 generation tests and 22
migration tests). The exact affected-file migration command was:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','-q']))"
```

It selected 95 tests and exited 0 with 95 passed. A first vertical rerun found only
a generic test-fixture directory assumption (`Common` was not present); the fixture
was made explicit within the authorized test file and the rerun passed. The setup
issue was classified `TEST_FIXTURE`, not `PRODUCT`.

The initial implementation-stage identities below are retained as historical
evidence; the final Task 1 identities before this report-only commit are given
in the reconciliation section below.

| path | bytes | SHA-256 |
| --- | ---: | --- |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | 32277 | `68753a2618f7789882e7282e91674b7c3c6b6eb48875bc34b640f9bd8c7af467` |
| `tools/stm32-toolkit/tests/test_migration_plan.py` | 88803 | `541ec6519d4497b3e448c9e64a822ed5e28d74ea9c4fd2e8b6763b4ab076a579` |

## Scope and boundaries

The code commit changes only:

- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`
- `tools/stm32-toolkit/tests/test_migration_plan.py`

The before/after source identities are recorded in the SDD run report. No generation,
schema, inspection, CLI, MCP, version, dependency, plan, specification, project, or
runtime files were changed. No campaign, golden project, hardware, network, remote
Git, candidate build, or runtime build was accessed for this implementation slice.

Independent Sol review must inspect the complete accepted-base-to-head diff and issue
the acceptance verdict.

## Revision 1 review correction

The revision addresses the independent review's FPU/ABI evidence finding and
coverage gaps. `_inspection_blockers()` now maps raw evidence by blocker code:
`MIGRATION_FPU_UNSUPPORTED` and `MIGRATION_FLOAT_ABI_REQUIRED` use
`inspection.fpu`; `MIGRATION_FLOAT_ABI_REQUIRES_FPU` and
`MIGRATION_FLOAT_ABI_UNSUPPORTED` use `inspection.float_abi`. The normalized
FPU/ABI pair behavior is unchanged.

`test_migration_plan.py` covers a real ARMCLANG + Cortex-M4/FPU2 + missing-ABI
project through public `plan_keil_conversion`, verifies the complete ordered
blocker list including `MIGRATION_COMPILER_UNSUPPORTED / ""` and
`MIGRATION_FLOAT_ABI_REQUIRED / "FPU2"`, repeats planning for deterministic
output, and checks guarded apply returns `MIGRATION_PLAN_INVALID` with
`details={"rule": "type"}`. The three conversion products remain absent. This
is the accepted-base behavior: the empty compiler-blocker path is retained and
the existing validator rejects it before the blocked-apply gate.

The ARMCC Scenario B public case verifies the complete one-item blocker list
`MIGRATION_FLOAT_ABI_UNSUPPORTED / "weird"`, guarded apply returns
`MIGRATION_BLOCKED` with the exact blocker-code list, and all three conversion
products remain absent. The no-FPU/no-ABI case runs conversion, reloads the
model, and verifies that generated compile/link options contain no `-mfpu=` or
`-mfloat-abi=`. The hard-float case verifies one correct normalized pair per
compile/link block and rejects raw `FPU2`, wrong ABI, and duplicate pair
spellings.

An intermediate adjacent planner correction changed the compiler-blocker path
to `inspection.project_file` so the ARMCLANG combined fixture could reach
`MIGRATION_BLOCKED`. That correction and its acceptance narrative are
superseded and are not present in the final Task 1 code/tests head. Restoring
the accepted-base empty path reproduced the existing `MIGRATION_PLAN_INVALID`
(`rule=type`) result. The conflict is classified
`TEST_DESIGN_CONFLICT/EXISTING_BLOCKER`, not a product acceptance. The final
test separately pins the accepted-base compiler `(path, evidence)` tuple to
`[("", "")]` while retaining the complete blocker-list oracle.

## Final Task 1 verification

All final local commands used the frozen CPython 3.12 interpreter, disabled the
pytest cache provider, and reused the brief's exact run-scoped basetemp
`C:/tmp/stm32tk-1001-fpu-test-isolation-pytest`.

The ARMCLANG Scenario A and ARMCC Scenario B nodes were run together:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker','tests/test_migration_plan.py::test_unsupported_float_abi_public_blocker_prevents_apply_without_writes','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Exit 0; 2/2 passed. Scenario A's complete ordered blocker list is
`[(MIGRATION_COMPILER_UNSUPPORTED, ""),
(MIGRATION_FLOAT_ABI_REQUIRED, "FPU2")]`, with the separate compiler
`(path, evidence)` assertion `[("", "")]`; apply returns
`MIGRATION_PLAN_INVALID` with `{"rule": "type"}` and writes none of
`.stm32-project.json`, `artifacts/migration/conversion.patch`, or
`artifacts/migration/conversion-report.json`. Scenario B's complete list is
`[(MIGRATION_FLOAT_ABI_UNSUPPORTED, "weird")]`; apply returns
`MIGRATION_BLOCKED` with exactly
`["MIGRATION_FLOAT_ABI_UNSUPPORTED"]` and writes none of those three
conversion products.

The two exact Scenario C nodes were run together:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures','tests/test_migration_plan.py::test_neither_fpu_nor_abi_stays_absent_from_manifest_and_flags','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Exit 0; 2/2 passed. The ARMCC Cortex-M4/FPU2/no-ABI path produces
`fpv4-sp-d16` plus `hard`, exactly once in each compile/link block. The
no-FPU/no-ABI path leaves both manifest members absent and emits neither
`-mfpu=` nor `-mfloat-abi=` in compile or link text.

The required focused selection was:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','tests/test_generation.py','-q','-k','fpu or float_abi or keil_conversion','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Exit 0; 34/34 passed.

The complete affected-file command was:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','-q','-p','no:cacheprovider','--basetemp=C:/tmp/stm32tk-1001-fpu-test-isolation-pytest']))"
```

Exit 0; 97/97 passed. The same complete command was rerun after the final
tests-only fix commit and again reached 100% with exit 0.

## Final identities, scope, and cleanup

Final code/tests head before this report-only commit is
`6bf7fb3ad3fafe8c9068957c647bb5546018231b` with tree
`73733549c501872c6402b2e3f64fefb13a0e3b88`. The final source identities are:

| path | bytes | SHA-256 |
| --- | ---: | --- |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | 32433 | `c4b64a6179a254e02c7e0449384204e48b2cd641f6e16b6801226aa4f82e7a70` |
| `tools/stm32-toolkit/tests/test_migration_plan.py` | 93627 | `bb9d9df7fd6b331cbf51c3a1be91ab1901097f42604f81fde514e4516c8b892d` |

`MIGRATION_COMPILER_UNSUPPORTED` is restored to the accepted-base empty path
and empty evidence bytes. The final commit history includes the tests-only
complete-list oracle fix and the tests-only compiler path/evidence oracle fix;
the implementation report records the code/tests head before this separate
report commit and does not contain its own future SHA.

Only `planner.py` and `test_migration_plan.py` are product-slice code/test
paths. No generation, schema, inspection, CLI, MCP, version, dependency, plan,
specification, project, campaign, runtime, golden, hardware, network, or remote
Git state was changed or accessed. The earlier adjacent path correction and
the earlier review report's acceptance wording are superseded; independent
Sol review of the complete accepted-base-to-head diff remains required.

The exact disposable basetemp remains because exact recursive cleanup was
rejected by the execution environment destructive-action policy before
execution. It was not removed through a deletion bypass. This is classified
`ENVIRONMENT/cleanup-policy`; it does not alter the test results. The report
does not claim cleanup success and does not self-accept the implementation.
