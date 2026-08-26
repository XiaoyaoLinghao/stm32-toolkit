# STM32 Toolkit 1001 Keil Standard-Math Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one bounded Schema-3 selector that preserves Keil standard-runtime math linkage as GNU `libm` without changing existing generic or native output when the selector is absent.

**Architecture:** The existing project model remains the single source of truth. A schema-validated boolean flows through `BuildSpec`, the existing canonical generation-model hash, Keil's single manifest proposal, and the existing CMake renderer; one template condition unifies generic opt-in and native built-in math linkage. No arbitrary library or linker-input API is introduced.

**Tech Stack:** CPython 3.12, frozen dataclasses, JSON Schema draft 2020-12, Jinja2 CMake templates, pytest, Git, PowerShell 7.

## Global Constraints

- Product accepted base is `29d063a2b922dd636e0865ae3c0c6a825592dfb3`, tree `21e90bb5e7b904c284b389351fcf7ac930586aab`.
- Approved specification commit is `f105db0a2852b87464710bbdb824144c91e39dfd`.
- One existing `gpt-5.6-luna` agent at reasoning effort `max` owns all product and implementation-test writes; GPT-5.6-sol owns design, complete-diff review, acceptance, candidate/runtime work, and campaign integration.
- The implementation agent may make local commits only. Hardware, network, push, PR, merge, tag, release, remote-branch mutation, and remote deletion are forbidden.
- `MIGRATION_COMPILER_UNSUPPORTED`, ARMCLANG blocking, FPU/ABI blocker/evidence mappings, complete blocker sets, guarded apply refusal, three-product non-write behavior, and `MIGRATION_MANIFEST_EXISTS` remain accepted-base behavior.
- `build.linkStandardMath` is optional, accepts only JSON booleans, defaults to `False` in `BuildSpec`, and is never inferred from source text.
- Missing/false generic generation retains accepted-base CMake bytes; the characterized generic `CMakeLists.txt` is 1116 bytes with SHA-256 `9fd3c7787345e6660506b176ca6e41cbba43c8f2dfd1e63af0a42072d7aae4ff`.
- Generic true emits exactly one `target_link_libraries(firmware PRIVATE m)` while retaining `-nostartfiles` and omitting nano/nosys specs.
- Native absent/false/true emits the same CMake bytes and exactly one `target_link_libraries(firmware PRIVATE m)`.
- Root and packaged Schema-3 files must be byte-identical; root and packaged CMake templates must be byte-identical. Schema-1 resource bytes and existing manifests that omit the field remain unchanged.
- No arbitrary library names, link flags, paths, response files, CMake text, environment injection, second model, serializer, runtime, MCP registration, controller, provider, backend, Python range, CI, or collaboration automation.
- Each pytest run uses `-p no:cacheprovider` and a unique exact `--basetemp`. Remove only that run-owned directory after recording the result; if policy rejects exact cleanup, record the absolute path as `ENVIRONMENT/cleanup-policy` and do not bypass.
- The already rejected cleanup target `C:\tmp\stm32tk-1001-link-plan-characterization` is an environment cleanup-policy item, not a product failure.

---

## File Structure

- Modify `schemas/stm32-project.schema.json`: public Schema-3 optional boolean.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json`: packaged byte-identical copy.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/project_model.py`: append `BuildSpec.link_standard_math` and load it without coercion.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py`: include the boolean in the existing canonical model hash payload.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`: write the boolean in the single Keil manifest proposal.
- Modify `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py`: pass the boolean to the existing CMake context.
- Modify `templates/cmake/CMakeLists.txt.j2` and `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakeLists.txt.j2`: use one unified native-or-selector condition.
- Modify `tools/stm32-toolkit/tests/test_project_model.py`: model defaults, booleans, invalid types, schema parity.
- Modify `tools/stm32-toolkit/tests/test_generation.py`: byte compatibility, unique math linkage, model-hash identity, template parity.
- Modify `tools/stm32-toolkit/tests/test_migration_plan.py`: exact proposal field and unchanged blocker/non-write oracles.
- Create `docs/codex/returns/STM32TK-1001-KEIL-STANDARD-MATH-LINK/implementation-report.md`: accepted base, code head, RED/GREEN evidence, scope, cleanup boundary; it must not claim its own report commit SHA.

### Task 1: TDD the bounded public selector and Keil mapping

**Files:**

- Modify: `schemas/stm32-project.schema.json:68-110`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json:68-110`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/project_model.py:85-94,710-722`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py:232-286`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py:524-602`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py:944-974`
- Modify: `templates/cmake/CMakeLists.txt.j2:61-63`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakeLists.txt.j2:61-63`
- Test: `tools/stm32-toolkit/tests/test_project_model.py`
- Test: `tools/stm32-toolkit/tests/test_generation.py`
- Test: `tools/stm32-toolkit/tests/test_migration_plan.py`

**Interfaces:**

- Consumes: existing `load_project_model(root: Path) -> ProjectModel`, `model_sha256_for(model: ProjectModel) -> str`, `plan_keil_conversion(root, inspection) -> MigrationPlan`, and `plan_project_configuration(model: ProjectModel) -> GenerationPlan`.
- Produces: `BuildSpec.link_standard_math: bool = False`, JSON `build.linkStandardMath`, Jinja context `link_standard_math: bool`, and no new public function.

- [ ] **Step 1: Add focused model tests in RED state**

Add these tests using the existing `_v2_payload()`, `_write_manifest()`, and `load_project_model()` helpers. Set `schemaVersion` to `3` for the new field contract.

```python
def test_schema3_link_standard_math_defaults_false_and_binds_booleans(tmp_path: Path):
    missing = _v2_payload()
    missing["schemaVersion"] = 3
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    _write_manifest(missing_root, missing)
    assert load_project_model(missing_root).build.link_standard_math is False

    for name, value in (("false", False), ("true", True)):
        payload = _v2_payload()
        payload["schemaVersion"] = 3
        payload["build"]["linkStandardMath"] = value
        root = tmp_path / name
        root.mkdir()
        _write_manifest(root, payload)
        assert load_project_model(root).build.link_standard_math is value


@pytest.mark.parametrize("bad", ["true", 1, 0, None, [], {}])
def test_schema3_link_standard_math_rejects_non_booleans(tmp_path: Path, bad: object):
    payload = _v2_payload()
    payload["schemaVersion"] = 3
    payload["build"]["linkStandardMath"] = bad
    _write_manifest(tmp_path, payload)
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(tmp_path)
    assert caught.value.code == "PROJECT_SCHEMA_INVALID"
    assert caught.value.details == {"field": "build.linkStandardMath", "rule": "type"}
```

- [ ] **Step 2: Run the model RED nodes and classify the failure**

From `tools/stm32-toolkit` run:

```powershell
$env:PYTHONPATH = (Resolve-Path '.\src').Path
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_project_model.py -q -k 'link_standard_math' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-model-red
```

Expected: PRODUCT/RED because the schema rejects the new property and `BuildSpec` has no member. Any unrelated collection or environment failure must be fixed as environment setup, not by weakening the tests.

- [ ] **Step 3: Add focused generation and identity tests in RED state**

Extend `standard_payload()` scenarios by setting `schemaVersion = 3`. Add this helper and the bounded assertions:

```python
def generated_cmake_bytes(root: Path, payload: dict) -> bytes:
    project = write_project(root, payload)
    plan = plan_for(project)
    return next(
        entry.after_bytes for entry in plan.files if entry.path == "CMakeLists.txt"
    )


def test_generic_standard_math_selector_is_bounded_and_byte_compatible(tmp_path):
    missing = standard_payload()
    missing["schemaVersion"] = 3
    missing_bytes = generated_cmake_bytes(tmp_path / "missing", missing)
    assert len(missing_bytes) == 1116
    assert sha256(missing_bytes) == "9fd3c7787345e6660506b176ca6e41cbba43c8f2dfd1e63af0a42072d7aae4ff"

    explicit_false = deepcopy(missing)
    explicit_false["build"]["linkStandardMath"] = False
    false_bytes = generated_cmake_bytes(tmp_path / "false", explicit_false)
    assert false_bytes == missing_bytes

    explicit_true = deepcopy(missing)
    explicit_true["build"]["linkStandardMath"] = True
    true_bytes = generated_cmake_bytes(tmp_path / "true", explicit_true)
    text = true_bytes.decode("utf-8")
    assert text.count("target_link_libraries(firmware PRIVATE m)") == 1
    assert "-nostartfiles" in text
    assert "--specs=nano.specs" not in text
    assert "--specs=nosys.specs" not in text


def test_link_standard_math_participates_in_generation_model_hash(tmp_path):
    roots = {}
    for name, present, value in (
        ("missing", False, False),
        ("false", True, False),
        ("true", True, True),
    ):
        payload = standard_payload()
        payload["schemaVersion"] = 3
        if present:
            payload["build"]["linkStandardMath"] = value
        roots[name] = write_project(tmp_path / name, payload)
    missing_hash = model_sha256_for(load_project_model(roots["missing"]))
    false_hash = model_sha256_for(load_project_model(roots["false"]))
    true_hash = model_sha256_for(load_project_model(roots["true"]))
    assert missing_hash == false_hash
    assert true_hash != missing_hash


def test_native_standard_math_selector_never_duplicates_or_changes_output(tmp_path):
    outputs = []
    for name, present, value in (
        ("missing", False, False),
        ("false", True, False),
        ("true", True, True),
    ):
        payload = standard_payload()
        payload["schemaVersion"] = 3
        payload["generation"]["nativeLinkerScript"] = "STM32F429_FLASH.ld"
        if present:
            payload["build"]["linkStandardMath"] = value
        root = write_project(tmp_path / name, payload)
        (root / "STM32F429_FLASH.ld").write_bytes(b"MEMORY {}\n")
        cmake = next(
            entry.after_bytes
            for entry in plan_for(root).files
            if entry.path == "CMakeLists.txt"
        )
        assert cmake.decode("utf-8").count(
            "target_link_libraries(firmware PRIVATE m)"
        ) == 1
        outputs.append(cmake)
    assert outputs[0] == outputs[1] == outputs[2]
```

Continue to run the existing root/package template byte-parity assertion.

- [ ] **Step 4: Add focused migration tests in RED state**

In `test_manifest_mapping_and_deterministic_uuid()` add:

```python
assert payload["build"]["linkStandardMath"] is True
```

Add the same exact assertion to the successful ARMCC FPU/ABI configuration scenario. Keep the existing ARMCLANG complete blocker/evidence, guarded-apply result, and non-write assertions byte-for-byte unchanged. That ARMCLANG fixture also carries a co-occurring FPU/ABI blocker and is not used to prove the proposal field. Do not remove any existing assertion about `MIGRATION_COMPILER_UNSUPPORTED`, guarded apply, or the three absent conversion products.

- [ ] **Step 5: Run generation and migration RED nodes**

```powershell
$env:PYTHONPATH = (Resolve-Path '.\src').Path
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_generation.py tests/test_migration_plan.py -q -k 'standard_math or manifest_mapping_and_deterministic_uuid or armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures or armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-behavior-red
```

Expected: PRODUCT/RED only because the proposal, model hash, renderer context, and template condition do not yet implement the frozen selector. If an existing blocker prevents a test from independently proving its target oracle, stop and report a test-design conflict; do not delete assertions or change blocker behavior.

- [ ] **Step 6: Implement the minimal schema and model changes**

Add the optional property to both Schema-3 copies without adding it to `required`:

```json
"linkStandardMath": {
  "type": "boolean"
}
```

Append the dataclass field and load it directly after schema validation:

```python
@dataclass(frozen=True)
class BuildSpec:
    sources: tuple[str, ...]
    include_paths: tuple[str, ...]
    defines: tuple[str, ...]
    compile_options: tuple[str, ...]
    assembly_sources: tuple[str, ...]
    presets: tuple[str, ...]
    elf: str | None
    link_standard_math: bool = False
```

```python
link_standard_math=build_data.get("linkStandardMath", False),
```

Do not use `bool(...)`, `or False`, or any other truthiness coercion.

- [ ] **Step 7: Bind the selector to existing identity, proposal, and rendering paths**

In `_model_payload()` add exactly:

```python
"link_standard_math": model.build.link_standard_math,
```

In `_manifest_proposal()` insert after `compileOptions`:

```python
"linkStandardMath": True,
```

In the CMake context add:

```python
"link_standard_math": model.build.link_standard_math,
```

Change both template copies to the same bytes:

```jinja2
{% if native_linker_script or link_standard_math %}
target_link_libraries({{ target_name }} PRIVATE m)
{% endif %}
```

Do not modify `cubemx_project.py`; native serialization continues to omit the selector.

- [ ] **Step 8: Run focused GREEN nodes**

```powershell
$env:PYTHONPATH = (Resolve-Path '.\src').Path
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_project_model.py tests/test_generation.py tests/test_migration_plan.py -q -k 'link_standard_math or standard_math or schema3_bytes_are_identical or generic_link_contract_restores_pre_runtime_recovery_bytes or manifest_mapping_and_deterministic_uuid or armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures or armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker or unsupported_float_abi_public_blocker_prevents_apply_without_writes' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-focused-green
```

Expected: every selected test passes. Record exact collected/pass counts and exit code.

- [ ] **Step 9: Run the complete affected files**

```powershell
$env:PYTHONPATH = (Resolve-Path '.\src').Path
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tests/test_project_model.py tests/test_project_v3.py tests/test_generation.py tests/test_migration_plan.py tests/test_plugin_layout.py -q -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-affected-green
```

Expected: exit `0`, no deleted test, no xfail introduced, and all collected tests pass except only pre-existing platform skips if any. Record exact counts rather than predicting them.

- [ ] **Step 10: Audit scope and commit product/tests only**

```powershell
git diff --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git diff --name-only
git status --short
```

Allowed product/test paths are exactly the eleven modify paths listed for Task 1. Stop on any other product-code path. Then stage those exact files, inspect `git diff --cached --name-only` and `git diff --cached --check`, and commit:

```powershell
git commit -m "fix(vs10a): preserve Keil standard math linkage"
```

Return the full code head and tree. Do not write the implementation report before this code/test commit exists.

### Task 2: Record the implementation evidence separately

**Files:**

- Create: `docs/codex/returns/STM32TK-1001-KEIL-STANDARD-MATH-LINK/implementation-report.md`

**Interfaces:**

- Consumes: accepted base `29d063a2...`, specification `f105db0a...`, the Task 1 code head, exact RED/GREEN command results, and exact cleanup outcomes.
- Produces: one immutable implementation return that names the code head but not its own report commit.

- [ ] **Step 1: Write the report with exact evidence boundaries**

Use these headings and populate them only with observed facts:

```markdown
# STM32TK-1001 Keil standard-math link implementation report

## Ledger
## Product behavior
## RED evidence
## GREEN evidence
## Complete affected-file verification
## Diff and scope audit
## Cleanup
## Deferred controller work
```

The ledger must state implementer `GPT-5.6-luna/max`, reviewer `GPT-5.6-sol primary`, full accepted base, full code head, branch, and remote/hardware authority `none`. The deferred controller section must say candidate/runtime replacement, restarted campaign builds, H1 evidence, and acceptance have not yet been performed by the implementer.

- [ ] **Step 2: Validate and commit only the report**

```powershell
git diff --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git diff --name-only
git add -- 'docs/codex/returns/STM32TK-1001-KEIL-STANDARD-MATH-LINK/implementation-report.md'
git diff --cached --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git diff --cached --name-only
git commit -m "docs(vs10a): report Keil standard math linkage"
```

Return the full final head and tree, `git status --short --branch`, all remaining untracked paths, and every cleanup-policy path. Do not approve the diff.

### Task 3: Sol independent complete-diff review and bounded verification

**Files:**

- Review: every path in `git diff --name-status 29d063a2b922dd636e0865ae3c0c6a825592dfb3..<code-head>`
- Review: `docs/codex/returns/STM32TK-1001-KEIL-STANDARD-MATH-LINK/implementation-report.md`
- Create after verdict: `docs/codex/returns/STM32TK-1001-KEIL-STANDARD-MATH-LINK/review-report.md`

**Interfaces:**

- Consumes: the Luna code head and separate report head.
- Produces: `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`; only `ACCEPTED` permits candidate/runtime construction.

- [ ] **Step 1: Reconstruct the exact ledger in a clean review worktree**

Verify the accepted base, code head, report head, tree IDs, branch, tracked/untracked state, remote configuration without contacting it, and the complete accepted-base-to-code-head diff. Confirm no product path outside Task 1 changed and no test/assertion was deleted.

- [ ] **Step 2: Inspect every changed hunk against the four scenarios**

Trace schema validation to `BuildSpec`, canonical model hash, Keil proposal, CMake context, and the single template condition. Explicitly test the mutants: missing coerces to true; string accepted; model hash ignores selector; generic false gains `m`; generic true duplicates `m`; native true duplicates `m`; ARMCLANG blocker disappears; apply writes while blocked.

- [ ] **Step 3: Run only risk-justified independent verification**

Use a fresh basetemp and run the exact focused selector nodes plus complete `test_migration_plan.py` because the planner proposal changes every Keil plan:

```powershell
$env:PYTHONPATH = (Resolve-Path '.\tools\stm32-toolkit\src').Path
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_generation.py -q -k 'link_standard_math or standard_math or schema3_bytes_are_identical or generic_link_contract_restores_pre_runtime_recovery_bytes' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-sol-focused
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -m pytest tools/stm32-toolkit/tests/test_migration_plan.py -q -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-sol-migration
```

Record exact counts and clean or classify both exact roots.

- [ ] **Step 4: Issue the verdict and commit the review report separately**

`ACCEPTED` requires all scenario oracles, the complete diff, and both independent commands to pass with no unresolved product, security, compatibility, test-design, or scope finding. A correctable finding returns to the same Luna owner on the same branch. The report commit cannot modify product/tests.

### Task 4: Rebuild the local runtime and resume the frozen campaign

**Files:**

- Generate locally: `C:\tmp\stm32tk-vs10a-legacy-campaign\runtime\standard-math-candidate-a`
- Generate locally: `C:\tmp\stm32tk-vs10a-legacy-campaign\runtime\standard-math-candidate-b`
- Preserve: `C:\tmp\stm32tk-vs10a-legacy-campaign\data\runtime`
- Preserve: project commits `d701c7142cf0bad9b03a690cf0456ecc97e3484f`, `ba528f6bd3196e063fef6742298133ca1dd0e107`, and `8417f02459942a0097cb14c5d8af367dfdcfe0fa`
- Resume from: project parent `718c37ed5d381f01680e64abe8c3810d62723b2a`

**Interfaces:**

- Consumes: Sol-accepted code head, the existing closed 66-wheel input at `C:\tmp\stm32tk-vs10a-legacy-campaign\scratch\task-3f-fpu-abi-isolation-wheelhouse-20260826`, and the frozen campaign/H1 plan.
- Produces: one uniquely active CPython 3.12 runtime bound to the accepted code head, corrected conversion/config commits, two reproducible public builds, complete H1 evidence, and no hardware action.

- [ ] **Step 1: Build two candidates from the exact accepted code head**

From the clean Toolkit worktree, set `$codeHead = (git rev-parse HEAD).Trim()` and require it to equal the Sol-accepted code head. Run twice:

```powershell
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -I tools/release/build_0900_artifacts.py build --repo-root 'C:\tmp\stm32tk-1001-legacy-hardware-impl' --code-head $codeHead --wheelhouse 'C:\tmp\stm32tk-vs10a-legacy-campaign\scratch\task-3f-fpu-abi-isolation-wheelhouse-20260826' --output-root 'C:\tmp\stm32tk-vs10a-legacy-campaign\runtime\standard-math-candidate-a'
& 'C:\Users\ZhangYang\AppData\Local\Programs\Python\Python312\python.exe' -I tools/release/build_0900_artifacts.py build --repo-root 'C:\tmp\stm32tk-1001-legacy-hardware-impl' --code-head $codeHead --wheelhouse 'C:\tmp\stm32tk-vs10a-legacy-campaign\scratch\task-3f-fpu-abi-isolation-wheelhouse-20260826' --output-root 'C:\tmp\stm32tk-vs10a-legacy-campaign\runtime\standard-math-candidate-b'
```

Require the same sorted 13 top-level files and identical SHA-256 per relative path. Verify the archive checksum, release manifest, 64 runtime wheels, Toolkit/Monitor `0.9.0`, CPython `>=3.12,<3.13`, 48 MCP tools, eight Skills, Monitor assets, SBOM, licenses, compatibility, and troubleshooting. Preserve both candidates until the runtime transaction is accepted.

- [ ] **Step 2: Replace the runtime through the existing fail-closed setup path**

Extract candidate A's Windows archive to a unique `standard-math-candidate-extracted` root, run its `tools/release/build_0900_artifacts.py verify-bundle --toolkit-root ... --json`, and preflight `bin/setup-stm32-env.ps1 -Mode Check` against the current runtime. Preserve the current `runtime-state.json`, installed wheel hashes, source commit `87bfa052...`, and release-manifest hash before authorizing `Repair`. The transaction must leave the prior runtime recoverable under a retired generation and the new `data\runtime\0.9.0\Scripts\python.exe` uniquely active with state `sourceCommit=$codeHead`. If holder, staging, quarantine, redirect, state, or compatibility checks fail, stop and classify; do not manually splice site-packages.

- [ ] **Step 3: Restart conversion/configuration from the frozen project parent**

Create a new protected local `codex/STM32TK-1001-P1C-STANDARD-MATH-CORRECTED` branch from exact `718c37ed5d381f01680e64abe8c3810d62723b2a`. Using only the new active runtime with `-I` and explicit `--project-root`, rerun fresh inspect, two conversion dry-runs, guarded conversion apply, and commit the three conversion products. Require exact `fpv4-sp-d16/hard` and `build.linkStandardMath=true`. Then run public configure dry-run/apply and commit only its managed configuration. Preserve old branches, commits, failure evidence, and original Keil/history hashes unchanged.

- [ ] **Step 4: Run two public builds and H1 verification**

Run public `arm-debug` build twice without source/config changes. Freeze build 1 result/log/ELF/MAP/HEX before build 2. Require identical input snapshot, build ID, ELF, MAP, HEX, entry/vector/reset/main/TIM3/testtime DWARF/memory/top-SRAM facts, no strong unresolved symbol, overflow, stale input, mailbox, or unexpected write; classify both compiler warnings independently. Verify the historical Keil project and AXF/MAP/HEX hashes and D4/LED1 source semantics remain unchanged.

- [ ] **Step 5: Report, clean, accept, and stop**

Update the existing P1c/H1 implementation report and SDD ledger with exact code/runtime/project/build identities and evidence hashes. Clean only run-owned disposable outputs after preserving minimum failure evidence. Sol reviews the complete campaign diff and accepted Toolkit-base-to-final diff and may issue `H1 ACCEPTED` only if no product defect remains. Confirm both tracked worktrees clean, project remote count `0`, runtime uniquely active, and no hardware/remote action occurred. Then stop at the hardware gate.
