# STM32TK-1001 Keil standard-math link implementation report

## Ledger

- Module/phase: VS10-A Keil standard-runtime standard-math linkage, Task 1 and Task 2.
- Product accepted base: 29d063a2b922dd636e0865ae3c0c6a825592dfb3.
- Accepted-base tree: 21e90bb5e7b904c284b389351fcf7ac930586aab.
- Approved specification commit: f105db0a2852b87464710bbdb824144c91e39dfd.
- Approved implementation plan / starting HEAD: f2df7c929a6a91df509398d7786f40b9a04fef17.
- Implementation owner: GPT-5.6-luna/max.
- Independent reviewer: GPT-5.6-sol primary.
- Active branch: codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl.
- Code head before this report-only change: ea8300647e53027173e8f67cfd354a8ece37d12e.
- Code tree before this report-only change: 66f2c0e84d7c2e3e7cee876fdd5641e77518f4d3.
- Remote, release, and hardware authority: none. No remote operation was performed.

## Product behavior

- Both Schema-3 copies accept optional build.linkStandardMath only as a JSON boolean; it is not added to required. Schema-1 resources were not modified.
- BuildSpec binds the field directly with a missing value defaulting to False; no truthiness coercion is used.
- The existing canonical generation-model payload includes link_standard_math, so true has distinct model identity while missing and explicit false remain equivalent.
- The single Keil manifest proposal writes build.linkStandardMath=true. Existing compiler/FPU/ABI blocker and guarded-apply behavior was not changed.
- The existing CMake context passes the boolean to both byte-identical templates. Generic true emits exactly one target_link_libraries(firmware PRIVATE m); missing/false preserves the characterized generic bytes (1116 bytes, SHA-256 9fd3c7787345e6660506b176ca6e41cbba43c8f2dfd1e63af0a42072d7aae4ff). Native absent/false/true retains one math-library directive without duplication.
- No arbitrary library/linker input, source scanning, source shim, new public function, runtime, or environment channel was added.

## RED evidence

Model RED command:

~~~powershell
$env:PYTHONPATH=(Resolve-Path '.\\tools\\stm32-toolkit\\src').Path
& 'C:\\Users\\ZhangYang\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -m pytest tools/stm32-toolkit/tests/test_project_model.py -q -k 'link_standard_math' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-model-red
~~~

- Exit 1; 7 selected tests failed. The missing-field node observed BuildSpec.link_standard_math absent; invalid-type nodes observed the expected pre-implementation schema additionalProperties failure rather than the requested type rule. This was PRODUCT/RED for the unimplemented selector, not a fixture or environment error.

Behavior RED command:

~~~powershell
$env:PYTHONPATH=(Resolve-Path '.\\tools\\stm32-toolkit\\src').Path
& 'C:\\Users\\ZhangYang\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -m pytest tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_migration_plan.py -q -k 'standard_math or manifest_mapping_and_deterministic_uuid or armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures or armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-behavior-red
~~~

- Exit 1; 6 selected tests produced 5 failures and 1 pass. The existing ARMCLANG blocker/non-write oracle passed; new generation and Keil proposal assertions failed because the selector was not yet implemented.

## GREEN evidence

Focused GREEN command:

~~~powershell
$env:PYTHONPATH=(Resolve-Path '.\\tools\\stm32-toolkit\\src').Path
& 'C:\\Users\\ZhangYang\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_migration_plan.py -q -k 'link_standard_math or standard_math or schema3_bytes_are_identical or generic_link_contract_restores_pre_runtime_recovery_bytes or manifest_mapping_and_deterministic_uuid or armcc_cortex_m4_fpu2_without_raw_abi_normalizes_and_configures or armclang_cortex_m4_fpu2_without_raw_abi_has_one_public_blocker or unsupported_float_abi_public_blocker_prevents_apply_without_writes' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-focused-green
~~~

- Exit 0; 16 passed.

Complete affected-file command:

~~~powershell
$env:PYTHONPATH=(Resolve-Path '.\\tools\\stm32-toolkit\\src').Path
& 'C:\\Users\\ZhangYang\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -m pytest tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_project_v3.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-affected-green-rerun
~~~

- The first invocation reached completion but its wrapper handle did not retain the final exit/output. The same affected-file command was rerun with the independent basetemp above and completed with exit 0: 613 collected, 611 passed, 2 skipped.
- A no-cacheprovider collect-only check counted generation 286, migration 97, plugin layout 19, project model 136, and project v3 75 tests.

## Complete affected-file verification

- The affected set included the complete model, Schema-3, generation, migration, and plugin-layout files required by the plan. No test assertion was deleted; the pre-existing ARMCLANG blocker, guarded-apply, and three-product non-write assertions remained in place.
- Root/package schema and template byte-parity checks passed within the focused/complete verification.
- The two template copies remained the same change, and the generic accepted-base linker contract test passed.

## Diff and scope audit

- Before the product/tests commit, git diff --check passed.
- Before commit, git diff --name-only listed exactly these eleven Task 1 paths:

  - schemas/stm32-project.schema.json
  - templates/cmake/CMakeLists.txt.j2
  - tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py
  - tools/stm32-toolkit/src/stm32_toolkit/generation/managed_files.py
  - tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py
  - tools/stm32-toolkit/src/stm32_toolkit/project_model.py
  - tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json
  - tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakeLists.txt.j2
  - tools/stm32-toolkit/tests/test_generation.py
  - tools/stm32-toolkit/tests/test_migration_plan.py
  - tools/stm32-toolkit/tests/test_project_model.py

- The product/tests commit was ea8300647e53027173e8f67cfd354a8ece37d12e with parent f2df7c929a6a91df509398d7786f40b9a04fef17 and tree 66f2c0e84d7c2e3e7cee876fdd5641e77518f4d3.
- Staged name-only and staged diff check also passed for exactly those eleven paths. The report was intentionally not part of that commit.
- No candidate/runtime replacement, campaign restart, build, H1 evidence, or acceptance was performed by this implementation owner.

## Cleanup

- Per the plan, exact run-scoped basetemp cleanup was attempted after each test run. The environment rejected recursive removal before execution; no policy bypass was attempted.
- Unresolved exact cleanup-policy paths:
  - C:\\tmp\\stm32tk-1001-link-model-red
  - C:\\tmp\\stm32tk-1001-link-behavior-red
  - C:\\tmp\\stm32tk-1001-link-focused-green
  - C:\\tmp\\stm32tk-1001-link-affected-green
  - C:\\tmp\\stm32tk-1001-link-affected-green-rerun
  - C:\\tmp\\stm32tk-1001-link-affected-collect
- The pre-existing plan characterization path C:\\tmp\\stm32tk-1001-link-plan-characterization remains an ENVIRONMENT/cleanup-policy item as specified by the plan.
- These cleanup-policy items are environmental/reporting concerns, not product failures. Source, tests, reusable fixtures, shared caches, and failure evidence were not removed.

## Deferred controller work

- Sol primary must independently review the complete accepted-base-to-code-head diff and issue the verdict.
- Candidate/runtime construction, fresh runtime replacement, restarted campaign conversion/configuration, two campaign builds, H1 evidence, hardware evidence, and acceptance have not been performed by this implementer.
- No hardware, network, push, PR, merge, tag, release, or remote branch action occurred.

## Revision round 1: Schema-3-only selector correction

- Independent review finding: the packaged Schema-2 validator cloned the shared
  schema and removed `testing` but left the Schema-3-only
  `build.linkStandardMath` property enabled. Consequently, a Schema-2 manifest
  containing `build.linkStandardMath=true` loaded as a model instead of being
  rejected by the accepted-base contract.
- Test-first RED command:

  ~~~powershell
  $env:PYTHONPATH=(Resolve-Path '.\\tools\\stm32-toolkit\\src').Path
  & 'C:\\Users\\ZhangYang\\AppData\\Local\\Programs\\Python\\Python312\\python.exe' -m pytest tools/stm32-toolkit/tests/test_project_model.py -q -k 'schema2_rejects_schema3_only_link_standard_math' -p no:cacheprovider --basetemp=C:/tmp/stm32tk-1001-link-schema2-red
  ~~~

  Exit 1 with the expected product RED: `DID NOT RAISE`. The regression
  asserted the accepted-base details
  `{"field":"build.linkStandardMath","rule":"additionalProperties"}`.
- The narrow production correction removes `linkStandardMath` only from the
  deep-copied packaged Schema-2 build properties, alongside the existing
  Schema-2 `testing` removal. Explicit caller-supplied schemas, Schema 3,
  `nativeLinkerScript`, and all planner/apply behavior remain unchanged.
- Exact regression GREEN command used a fresh no-cache basetemp and exited 0
  with 1 passed. The selector-focused rerun exited 0 with 17 passed (the
  newly-added Schema-2 regression accounts for the additional selected test).
- Complete affected-file rerun covered `test_project_model.py`,
  `test_project_v3.py`, `test_generation.py`, `test_migration_plan.py`, and
  `test_plugin_layout.py`; it exited 0 with 614 collected, 612 passed, and 2
  skipped. No test assertion or unrelated product behavior was changed.
- Product/tests correction commit: `0cdd142f80421c6aea59e81e963936779b05f00f`,
  tree `c33729b55bcfcb40ff782e81548f5e2cba8a8e2f`, parent
  `991090e88f9c37dd6c2ccf80ba01f7c68a126e2e`.
- Revision scope audit passed: `git diff --check` passed and the pre-commit
  name-only set was exactly `tools/stm32-toolkit/src/stm32_toolkit/project_model.py`
  and `tools/stm32-toolkit/tests/test_project_model.py`. The report is not in
  the product/tests commit.
- Fresh exact basetemp cleanup attempts for the revision RED, regression
  GREEN, selector-focused GREEN, and complete affected GREEN paths were
  rejected by the environment policy before execution. No bypass was used;
  these remain `ENVIRONMENT/cleanup-policy` concerns.
