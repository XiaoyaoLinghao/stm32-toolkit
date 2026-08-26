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
