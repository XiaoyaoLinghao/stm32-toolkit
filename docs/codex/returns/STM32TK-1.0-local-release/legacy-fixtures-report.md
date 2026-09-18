# STM32TK 1.0 legacy fixture portability report

- Accepted base: `47988d34725f97075d3ea69a43a65cb5b2144189`
- Product CodeHead: `15b1a70e9bd684285da5557104deff529f537e49`
- Tested code head before this report commit: `06e45a095018ee04b1fcff229707d90099eb9570`
- Branch: `codex/STM32TK-1.0-legacy-fixtures`
- Review status: independent primary review pending; this report is not a self-acceptance.

## Implemented scope

The 0502 tests now use two tracked launcher fixtures extracted from local commit `eae54be02cd28a707488f15f58b8f58e66db1a2c`. Their recorded Git blob identities are `43be14c9c2b1c5fc0fa34cb7b6e85751be2e366b` (`stm32-monitor.cmd`) and `ad7eaa864a53dd7e6d871f152587eba1de80d56d` (`stm32-toolkit-mcp.cmd`). The fixture directory has two exact `-text` rules in `.gitattributes`; no root or global Git attributes were changed. Fresh-checkout raw-byte proof is retained in `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\fixture-raw-byte-equivalence.json`.

The 0600 private self-test seam accepts test-owned temporary-root and support-profile paths only for pytest callers, validates canonical absolute existing paths and all ancestors, and keeps the public `C:\tmp` defaults unchanged. The unit support fixture was generated through the existing `_write_support` helper under `D:\codex-tmp\v10b-0918\r10\t\lg\support-unit-fake`; offline `verify_support_root` validation is recorded in `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\support-unit-preflight.json`. It contains 17 manifest members and the frozen profile versions, including PowerShell `5.1.26100.9168`. The original approved support root at `D:\codex-tmp\v10b-0918\r10\t\alloc\feas0\support` was retained as the source authority and was not edited.

The stale test expectations were corrected for the approved 12-kind evidence GC registry and absolute regeneration CLI project-root arguments. No package source, product launcher, schema, dependency lock, threshold, or release controller public contract was changed.

## Focused evidence

All focused invocations used `D:\codex-tmp\v10b-0918\r10\py\Scripts\python.exe`, explicit `TEMP`/`TMP`/`TMPDIR` below `D:\codex-tmp\v10b-0918\r10\t\lg`, explicit basetemp/cache below that root, `PYTHONPATH` pointing at the verify checkout sources, cleared inherited pytest/coverage variables, `-p no:cov`, and per-group command/stdout/stderr/JUnit/result files under `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures`.

| Group | Tested head | Actual JUnit result | Evidence |
| --- | --- | --- | --- |
| no-coverage-51 | `35fdb2323c14117e46e20ee12af7cf59c632eb3a` | 51 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\no-coverage-51` |
| Node fixed slice | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 2 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\node-2-r2` |
| Support first attempt (retained failure) | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 469 collected, 450 passed, 2 failed, 17 errors, exit 1; this was the accidental whole-module-selector run and is not a 16-node result | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\support-16` |
| Support exact slice, before binding fix (retained failure) | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 16 collected, 14 passed, 2 failed, 0 errors, exit 1; both failures were the public-default support-profile reread | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\support-16-r2` |
| Support corrected failures only | `06e45a095018ee04b1fcff229707d90099eb9570` | 2 collected, 2 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\support-2-r3` |
| Historical 0502 launcher slice | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 10 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\historical-10` |
| GC contract | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 1 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\gc-1` |
| Regeneration CLI contract | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 1 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\cli-1-r2` |
| Private seam guards | `d3f1f55d2f075e06b2e119269dc6f992e071e32c` | 3 passed, 0 failed, 0 errors, exit 0 | `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\seam-guard-3` |

The support group is represented by the valid 14-node result in `support-16-r2` plus the two corrected nodes in `support-2-r3`; the two records are intentionally kept separate and are not presented as one single pytest invocation. The prior UI adapter failure in `node-2` and all other superseded failures remain preserved under their original evidence directories.

The final two-node invocation used only these exact selectors, with no module selectors:

```text
tools/stm32-toolkit/tests/release/test_release_verifier_0600.py::test_candidate_evidence_recursively_verifies_catalog_inventory_package_and_retained_files
tools/stm32-toolkit/tests/release/test_release_verifier_0600.py::test_final_evidence_recursively_binds_checkpoint_and_shard_package
```

Its expanded argv, environment, exit code, stdout, stderr, and JUnit are in `D:\codex-tmp\v10b-0918\r10\e\legacy-fixtures\support-2-r3\command.json`, `result.json`, `stdout.log`, `stderr.log`, and `junit.xml`.

No hardware, browser, packaging, remote operation, performance command, cleanup, or full-matrix rerun was performed by this slice. The primary agent owns independent review and final release acceptance.
