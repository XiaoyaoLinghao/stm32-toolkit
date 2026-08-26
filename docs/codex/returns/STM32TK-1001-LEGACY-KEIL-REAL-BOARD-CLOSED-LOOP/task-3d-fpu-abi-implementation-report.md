# STM32TK-1001 Task 3d: FPU/ABI normalization implementation report

Implementation status: complete; independent Sol review required.

This report covers Task 1 of the frozen Keil FPU/ABI normalization plan. It is not
self-acceptance and makes no hardware or H1 claim.

## Lineage

- Brief worktree baseline before code changes: `bf7549a9a42afba81b75b4c78ef51143deb11ad0`
- Brief baseline tree: `44ac62b31f351b7c0c7ca8fd4247a59402435978`
- Design commit: `a14048e8f371bc652a282a9644cfd6f0980b73d5`
- Plan commit: `bf7549a9a42afba81b75b4c78ef51143deb11ad0`
- Accepted base required by the brief's report step: `77514c441854bf7a8218eb2974e54abac478e31b`
- Product code head before this report-only commit: `30d06c23e79eee3f83a28de196986de70ff89e28`
- Product code tree at that head: `fe4fd351d24517791cafd948ce3e47bb9248d632`

The code head was committed first with:

```text
fix(vs10a): normalize Keil FPU ABI conversion
```

The final report is committed separately. This report deliberately does not record
the SHA of that report-only commit.

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

The final code-head identities were:

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

`test_migration_plan.py` now covers a real ARMCLANG + Cortex-M4/FPU2 + missing
ABI project through public `plan_keil_conversion`, verifies one deterministic
`MIGRATION_FLOAT_ABI_REQUIRED` blocker with raw evidence `FPU2`, repeats the
plan for deterministic output, and checks guarded apply returns
`MIGRATION_BLOCKED` without writing `.stm32-project.json`,
`artifacts/migration/conversion.patch`, or
`artifacts/migration/conversion-report.json`. The no-FPU/no-ABI case runs
conversion, reloads the model, and verifies that generated compile/link options
contain no `-mfpu=` or `-mfloat-abi=`. The hard-float case verifies one correct
normalized pair per compile/link block and rejects raw `FPU2`, wrong ABI, and
duplicate pair spellings.

The ARMCLANG guarded-apply case exposed an adjacent existing contract issue:
with the historical empty path on `MIGRATION_COMPILER_UNSUPPORTED`, apply
returned `MIGRATION_PLAN_INVALID` (`rule=type`) during blocker validation before
the intended `MIGRATION_BLOCKED` gate. Sol approved retaining the minimal
planner-side correction that binds this existing compiler blocker to
`inspection.project_file`; the blocker code and compiler semantics were not
changed. A precise regression assertion pins the path. TDD RED was observed
while that path was temporarily empty: actual `('', '')` versus expected
`('app.uvprojx', '')`, exit 1. Restoring the approved correction produced the
required guarded `MIGRATION_BLOCKED` result.

## Revision 1 verification

All local commands used the frozen CPython 3.12 interpreter.

ARMCLANG public/guarded-apply node:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py::test_armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker','-q']))"
```

Exit 0; 1 passed. It confirmed the compiler blocker path equals
`inspection.project_file`, the FPU blocker evidence is `FPU2`, guarded apply
returns `MIGRATION_BLOCKED`, and all three conversion products remain absent.

Focused revision selection:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','tests/test_generation.py','-q','-k','fpu or float_abi or keil_conversion']))"
```

Exit 0; 33 passed (10 `test_generation.py`, 23 `test_migration_plan.py`).

Complete affected migration suite:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -c "import sys,pytest; sys.path.insert(0,'src'); raise SystemExit(pytest.main(['tests/test_migration_plan.py','-q']))"
```

Exit 0; 96 passed. Collection-only checks independently reported the same 33
focused and 96 migration tests. Git fixture creation emitted only the configured
LF-to-CRLF advisory; no pytest warning summary or test failure occurred.
`git diff --check` exited 0.

The Sol read-only diagnostic separately reported 9/9 parameterized cases across
four focused nodes. That reviewer evidence is retained as a boundary and is not
used in place of the local 1/1, 33/33, and 96/96 runs above.

## Revision 1 lineage and identities

- Prior code head: `30d06c23e79eee3f83a28de196986de70ff89e28`
- Revision code commit: `266b6d40bac3a0fee095204fb7c933b726cf3f78`
- Revision code tree: `f4701a43d884aa38eb68e3bcbb5182bddf1a6284`
- Tests-only follow-up commit: `dc8f642e7708625c5707e0694512b915e819bc7b`
- Code/tests head before this report-only commit: `dc8f642e7708625c5707e0694512b915e819bc7b`
- Code/tests tree before this report-only commit: `1318fe0cbea97550d6211a058012c4599c430971`

Final source/test identities before the report-only commit:

| path | bytes | SHA-256 |
| --- | ---: | --- |
| `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` | 32454 | `0f21b2591c24c18f15298676a529a47474fc8edc96ad6963f0facef354908fb7` |
| `tools/stm32-toolkit/tests/test_migration_plan.py` | 92835 | `390b71667653a4a68e1f03d0c36319d6d24a98ee87cb0265284148ba3809332f` |

The report deliberately does not contain the SHA of its own report-only commit.
This remains implementation evidence only; acceptance is reserved for the
independent Sol reviewer. No generation, schema, inspection, CLI, MCP, version,
dependency, plan, specification, project, runtime, campaign, golden, hardware,
network, or remote Git files were modified or accessed in this revision.
