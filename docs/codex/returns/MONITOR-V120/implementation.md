# Monitor v1.2.0 source alignment implementation return

- Accepted full source base: `45e1acde2e89a4d14570efe9c0f4d9b4e5e2f907`.
- Specification and plan commit: `4772b360bda4d99d4fff4eccbf0ca06f943ca683`.
- Product, direct tests, and current documentation CodeHead before this report: `e6cdf2c7625f6e68aecfcafbfd4a0d26ca2c5eec` on `codex/v1.2.0` in `D:\codex-tmp\v12021\i`. This report does not record its own commit SHA.
- Implementation owner: `v120_impl`, `gpt-6-sol` / `max`. The primary owns independent full-diff review, acceptance, remote delivery, local service decisions, and run-root cleanup. The implementer did not approve the diff or perform remote, browser, HTTP, hardware, firmware, installation, or service operations.

## Delivered behavior

The plugin, Toolkit and Monitor Python distributions, Toolkit import/CLI, UI root package and lock root, release builder/policy/schema, managed runtime setup, two command launchers, and setup skill identify v1.2.0. Monitor's Toolkit dependency is exactly `stm32-toolkit==1.2.0`. The lock dependency graph, other package pins, API/protocol/wire/storage schema identifiers, and accepted Monitor feature code remain unchanged. The tracked UI asset tree is the same Git tree as the accepted base (`b13ea69f4928d58826015169561bf493d99fab2b`); a local build regenerated seven byte-identical assets.

The existing runtime legacy list now includes 1.1.2 alongside earlier entries. Read-only `Check` recognizes that runtime; explicit `Repair` uses the existing quarantine/transaction behavior. Generated-project producer allowlists now include 1.1.2; the original project `generatedBy` and old managed-manifest identity remain truthful until an explicit configure transaction, and eligible unowned editor files remain untouched. Existing exports still require exact Toolkit and Monitor versions. The current documentation distinguishes this source candidate from the latest published v1.0.1 and retains the earlier v1.1.2 source-delivery history.

Producer compatibility does not authorize old firmware for the new runtime. The primary's separate offline check found that `flash.py` requires a build's Toolkit version to equal the current runtime version; a v1.1.2 build is rejected with `FIRMWARE_IDENTITY_MISMATCH` under v1.2.0. The local 8765 service remains on its already verified v1.1.2 firmware identity. Rebuild, flash, and v1.2.0 physical observation are deferred to a later authorized owner; this implementation neither changes that contract nor claims physical qualification.

The release setup trust anchors are SHA256 of the committed Git bytes of `tools/release/build_0900_artifacts.py` (`111de40cc48a71489b7f69d047ab8c72157fd671c4e5d51e869dbdd6af12c782`) and `tools/release/release_0900_policy.json` (`1c3701cd6764fa7fea56135df33e8f535370d73753a11612b64e5fb0ad045f86`). The exact CodeHead `git archive` anchor test passed, including the CRLF checkout versus LF archive boundary.

## Implementer verification

All run-owned output is under `D:\codex-tmp\v12021`. PowerShell 7.6.7 and Python 3.12.10 used `-B`, `PYTHONDONTWRITEBYTECODE=1`, and absolute `PYTHONPATH` for this tree's Toolkit and Monitor `src` directories. `TEMP`, `TMP`, `TMPDIR`, `XDG_CACHE_HOME`, pytest basetemp/cache, pip/npm cache, and wheel output were bound under that root. Each pytest invocation used `-o addopts=''` and a unique `--basetemp`/`cache_dir`. Full outputs are retained in `checks/*.log`; observed commands, exit codes, and log SHA256 values are recorded in `checks/results.json`. `run_ui.ps1` retains the exact UI command sequence.

| Check and scope | Result | Evidence |
| --- | --- | --- |
| `test_public_inventory.py`, `test_cli.py`, `test_plugin_layout.py` | 64 passed, one existing `runpy` warning | `checks/core1.log` |
| `test_generation.py -k 'legacy_generation_producer or generation_producer_allowlist or unowned or user_drift or mixed_editor_ownership'` | 14 passed, 301 deselected | `checks/generation.log` |
| Full `release/test_0900_artifacts.py` and `test_0900_security.py` | 74 passed | `checks/release.log` |
| `test_setup_runtime.py -k 'existing_legacy_runtime or setup_rejects_replaced_release_utility or setup_rejects_policy_swap or check_accepts_probe_distribution or repair_rejects_multiple_legacy_runtimes or post_promotion_validation_failure'` | 13 passed, 29 deselected; includes 1.1.2 Check/Repair/quarantine and older versions | `checks/setup.log` |
| Legacy producer build/identity, exact build identity, migration payload/manifest, and fake MCP conversion/configure/build node tests | 8 passed | `checks/build.log` |
| Monitor package boundary, CLI version, protocol result, export manifest and old-version export refusal node tests | 14 passed after the test-boundary correction | `checks/monitor2.log` |
| Exact CodeHead Git archive trust-anchor test | 1 passed against `e6cdf2c7625f6e68aecfcafbfd4a0d26ca2c5eec` | `checks/anchor.log` |
| UI `typecheck`, `typecheck:e2e`, `lint`, wire/catalog-tree Vitest, `build`, and `verify:dist` | All exit 0; 20 tests and 7 byte-identical assets | `checks/ui-summary.log`, individual `checks/ui-*.log` |
| Current UI lock compared with accepted lock excluding only top/root versions; copied Windows dependencies compared with current lock | Dependency JSON identical; installed entries had no version/integrity mismatch or missing required package (51 absent optional platform packages) | `checks/ui-graph.log` and `checks/ui-deps.log` (`npm ls --depth=0 --offline`, exit 0) |
| Offline source-copy `pip wheel --no-index --no-deps --no-build-isolation` with CPython 3.12.14, setuptools 84.0.0 and wheel 0.48.0 | Both wheels built; real METADATA says 1.2.0, Monitor requires Toolkit exactly 1.2.0 and contains seven UI assets | `checks/wheel-toolkit.log`, `checks/wheel-monitor.log`, `checks/wheel-metadata.log` |
| `git diff --check` and tracked UI tree comparison against accepted base | Passed, UI tree equal | local Git checks |

The initial Monitor package-boundary run reported **13 passed, 1 failed** (`checks/monitor.log`). This was **INFRASTRUCTURE**: the existing `test_public_models_expose_no_raw_address_override` walked every annotation in every module and treated private `source_catalog._Node.address` as a public model field. The accepted base contains the same private field at line 112 and the source file did not change in this slice. The test now checks annotated fields of every top-level public class, including public dataclasses, across all modules; it still rejects public `address` and `raw_address`. No product model or private catalog behavior changed. The corrected package-boundary and version/export selection passed in `checks/monitor2.log`.

The full release tests ran at the first product commit and the other listed checks used identical affected product bytes later fixed at CodeHead. Documentation-only commits did not change those contracts. The archive check was rerun against the exact final pre-report CodeHead. The local wheels demonstrate package metadata and asset inclusion; they are not a qualified Windows release bundle or an installation/upgrade result. Existing accepted Monitor functional evidence is reusable only for unchanged behavior; no fresh browser or physical PASS is inferred.

The primary owns cleanup of disposable `checks/pt-*`, `checks/cache-*`, `tmp`, `xdg`, `npmcache`, `pipcache`, copied `node_modules`, and `package-build` after evidence reconciliation. Retain the small `checks/*.log` files, original failing Monitor log, corrected result, and trust-anchor proof needed for review. This implementer did not remove any source, reusable fixture, shared cache, failure evidence, or another owner's files.
