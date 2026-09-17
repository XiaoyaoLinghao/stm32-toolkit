# Restored integration, deployment and one P4 Monitor window

## Result and ownership

The restored integration was migrated and reconciled, the accepted continuation fix was deployed, and the single authorized P4 Monitor window passed. The subsequent offline comparison is blocked by two existing analysis-contract gaps. T10 G/H and VS10-A Task11/12 remain incomplete.

- Accepted base: `9975bcd3466f949c56801c81d618b2b57493a5a7`.
- Independently accepted CodeHead: `30ceae845f7770dfd01db90104bd01e5c3a70894`.
- Deployed source: `ee2152b497e62389a103ea4ff9ce2ebf92aae160`.
- Canonical integration: `D:\codex-tmp\stm32tk-integration`, branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Primary owned migration, deployment, physical dispatch and integration. Luna/max adapted the run-owned Monitor entry; `t10_continuation_review` independently accepted its complete two-constant diff and configuration. No product code changed in this run. The previous product-ownership exception remains closed.
- Current user authorized migration, deployment and testing, then separately confirmed the unchanged site and exactly one 30s/100ms P4 acquisition. That one hardware operation is consumed. No flash, reset, retry or remote operation occurred.

## Migration and deployment

The user restored `D:\workspace\stm32tk-1001-legacy-hardware-impl`. Its index exactly matched historical commit `89f463e5ab05d7f7a5ed0ae3360c579683e80542`, while its branch already pointed to the accepted source. The sole unstaged change was the known GC scope line already included in that source. This was a restored-checkout ENVIRONMENT mismatch, not a new product regression.

Original index, staged/unstaged binary patches and the plan were preserved under `D:\codex-tmp\t10d-0917`. `git worktree move` migrated all 1,374 files; every file except Git's managed backlink retained identical bytes. Only after that verification were tracked files/index reconciled to the accepted source. The resulting worktree was clean before deployment and hardware. Ignored historical artifacts were preserved. Twelve other restored historical worktrees were clean and are not inputs to this deployment; they were inventoried without deletion. Existing `t10c-0917\impl` and `review` already meet the temporary-root boundary.

One clean LF packaging worktree and one build used the existing release builder and closed wheelhouse. Bundle verification and `setup-stm32-env.ps1` Check → Bootstrap → Check passed. New persistent runtime:

`D:\stm32tk-data\fault-controlled-20260911\candidates\continuation-20260917\runtime\0.9.0`

- Final Check: `healthy / matching`; 146 installed package files match the verified wheels.
- Actual final `pyocd.exe --version`: `0.45.1`.
- Manifest SHA256: `9da979cfbc86eb76e92b27d2b3693da8acf8d08331f0c683a72561088fa4ff4b`.
- Runtime-state SHA256: `0dde04489c3a430e127ff075736a70a09fa5afea0d7cb0d1e51ff537b4cbb3af`.
- Previous candidate runtime and all 68 pinned original business-evidence files retain their hashes. Firmware was not edited or rebuilt.

Fresh installed CLI processes read the isolated v3 record and the actual predecessor/Diagnostic, then bound the original P3/P4 evidence successfully. Immutable continuation evidence is `6af4ea4fddebe07a0a2899ce1adf142c869ddd10d5d8645f5254ca61f9d4e4be`; v3 attempt `13093342-58d9-41b7-b78d-f4b86dc7bafa` remains revision0/verification-pending, with deadline `2026-09-17T08:42:49.371973Z`. It was not renewed to work around the later comparison blocker. Original sessions, predecessor revision6 and Diagnostic revision6/FIX_PROPOSED remain intact.

Two deployment-check invocation/report mistakes were corrected offline without reinstalling: a PowerShell argument-index error and the report's wrong manifest key. The initial pretty-printed comparison JSON was also rejected before analysis; the existing canonical serializer produced valid inputs. These are execution/report defects, not product failures. Their original responses are retained.

## Real P4 result

The accepted entry copy changes only its fixed session to `p4-recovery-20260917-03` and its output root to this run. Entry SHA256: `7086a9e09604774a85062381cded8ba1213b090f55ee9696d2aad11ba28d38d7`; configuration SHA256: `0d1bc558f5ec551eb1d9bd622ec043debccd95941862b349efb840e3bbf9b925`. Existing configuration and offline-preflight entries passed against the deployed runtime; unchanged selfcheck evidence was reused.

One process exited0 after 73.439s, within the 120s outer budget. Its 30s continuous window contains 300 complete correlated batches, 10.0Hz, zero drops; interval P95=102.7207ms, P99=106.9158ms, maximum=153.3844ms. All frozen performance gates passed. `testtime` has 100 distinct valid values; PE3 and PE4 each contain both 0 and 1. Sampling stopped, probe released, runtime stopped, registry released, and related processes=0. The user confirmed D3/D4 still alternate normally afterwards.

The original-session P4 physical publication succeeded: run `eb431e10-2256-4a81-b941-b1f76c0ef8e6`, group `04818252-be17-42cf-9a18-0d7ad674c9b2`, sequences `[0,300)`, reference SHA256 `b0dc159e198a9885e026f60cc58bea89d90ee90cd0cb1844ecd5bc4683572e7a`. No further hardware is needed to diagnose or fix the comparison of these stored windows.

## Exact remaining blocker and minimum correction

Canonical compare accepted and authenticated the actual P3/P4 references and continuation proof, but published `INVALID / INCONCLUSIVE / INSUFFICIENT_VALID_PAIRS`: 0 valid pairs across 599 relative positions. Its analysis ID is `c28979be1bf12dc862e7c5f9592e91180cf707fceac713915697eea7511ff83e`, evidence `58a90581b5fcff012ada656dc2d18e8b1bd61a1260fd790e698f302e676ab77f`. This inconclusive evidence is retained; no bundle, verification-plan, completion or final checkpoint was claimed.

1. `tools/stm32-monitor/src/stm32_monitor/analysis.py:1088` expects exactly `{type,value}`. Authenticated native `GPIOE.ODR` values instead contain `{bitWidth,expression,rawHex,typeName,value}`. Before: `uint32_register`, 32bit, `0x0000fbb0`, value64432; after: same type/width, `0x0000fba8`, value64424. `_trusted_sample` rejects all 300 samples on each side despite their `OK` status.
2. The same file at lines1166–1185 requires exact equality of independent run-relative scheduled nanoseconds. Before offsets begin `[0,100593900,200411000]`; after begin `[0,99876200,199847000]`. Their intersection is only `{0}`. At index1 the difference is 717700ns; the maximum same-index relative skew is 1468200ns. These measurements explain the mismatch; index pairing here is diagnostic arithmetic, not an accepted replacement algorithm.

Classification: PRODUCT contract mismatch in offline numeric decoding and alignment. Evidence identity validation and hardware acquisition succeeded. Neither lowering minimum pairs nor relabeling raw timestamps is a correction.

Next bounded slice should add strict native register scalar decoding and an explicitly versioned, bounded one-to-one relative alignment, preserving v1 exact behavior and all stored bytes. Primary must freeze the native shape/range/hex consistency checks, alignment tolerance/ambiguity rules and request/result persistence together before Luna/max implementation. Expected files are Monitor `analysis.py`, its existing tests and continuation-consumer tests; CLI/workflow/model and Toolkit persistent-reader changes are permitted only where the frozen new schema actually requires them. No sampling/backend/firmware changes, general diagnostic framework or new hardware are needed. Necessary evidence is focused native/independent-clock regression plus the existing real windows through compare, bundle, Diagnostic completion and fresh-process final graph validation. Already-valid deployment, acquisition and unrelated tests remain valid.

## Evidence and cleanup

Run root: `D:\codex-tmp\t10d-0917`. Main records: `migration-ledger.json`, `deployment-result.json`, `entry-independent-review.json`, `monitor-summary.json`, `analysis-blocker.json`, `alignment-design-facts.json`, `original-evidence-after.json` and `execution-ledger.json`. Full physical data remains in the business store and run-owned `entries\fixed-after` export/result; the single-use marker is retained.

Automatic approval rejected deletion of four run-owned packaging build/egg-info directories with `blocked by policy`. Nothing was deleted and no alternate tool/path was tried. Preserve those directories and all older holds. Attempt7, T9, prior 100ms, P3/P4 native and this P4 acquisition evidence remain valid within their original scope.
