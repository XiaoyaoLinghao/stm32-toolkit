# STM32TK-0901 runtime and Agent adapter convergence — implementation report

Status: implementation complete; pending independent Sol review. This report does not record an
acceptance verdict.

## Ownership and commit identity

- Module/phase: STM32 Toolkit 0.9 / VS09-A.
- Accepted base: `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Specification: `4073ea1e8450bd189d416350bf5742befd222399`.
- Plan: `3a35404428ac23fa805fc6f28977bd290854da8e`.
- Implementer: GPT-5.6-luna, max, `/root/vs09a_implementer`.
- Reviewer/acceptor: GPT-5.6-sol primary agent.
- Branch/worktree: `codex/STM32TK-0901-RUNTIME-AGENT-CONVERGENCE` /
  `C:/tmp/stm32tk-0901-runtime-agent-convergence`.
- Starting HEAD: `3a35404428ac23fa805fc6f28977bd290854da8e`.
- Product CodeHead before this report commit: `b547803c10bf9944b9f7a33178343b8c32bfd717`.
- No upstream, PR, remote action, hardware, VS09-B, or bounded override was authorized.
- Handoff Git state: tracked product/report work is committed; no uncommitted tracked or untracked
  product files remain; only the ignored SDD workspace is present; the two local commits are
  unpushed, the branch has no upstream, and no remote branch contains the head.

## Delivered behavior

The product now has one 0.9.0 authority across Toolkit, Monitor, UI, plugin metadata, and the
doctor report; an exact 48-name MCP/8-Skill public inventory; explicit project-root CLI binding;
generic `STM32_TOOLKIT_DATA_ROOT` launchers; CPython `>=3.12,<3.13` setup probing; current/legacy
runtime CHECK and fail-closed Bootstrap/Repair; Monitor protocol/runtime identity convergence; and
bilingual VS09-A/VS09-B boundary documentation. Monitor also exposes the frozen `version`
subcommand used by the fresh runtime smoke.

The current-runtime fixture
`tools/stm32-toolkit/tests/fixtures/minimal-gcc/.stm32-project.json` intentionally moves its
generatedBy authority to 0.9.0. It is not run-scoped output. Historical 0.5 producer/release
evidence remains unchanged and labelled historical.

## Verification

- Launcher/setup: 42 passed (19 plugin layout, 23 setup lifecycle), including unsupported 3.11
  refusal, hostile environment, redirects, staging, quarantine/rollback, legacy ambiguity, probe
  metadata, UI assets, and project read-only behavior.
- Generation: 283 passed after keeping historical 0.5 malformed-producer records and using current
  0.9 identity only for structural hash/type cases.
- Monitor affected suite: 219 passed, 0 failed, 0 errors.
- Root/MCP matrix: 67 passed / 5 failed / 0 errors out of 72. The five failures are the known
  pre-existing fake-CMake child import issue caused by the intentionally scrubbed `PYTHONPATH`,
  classified ENVIRONMENT/INFRASTRUCTURE; no unrelated workflow workaround was retained.
- The exact combined Step 12 invocation also has a duplicate `test_cli` module basename
  collection collision between Toolkit and Monitor, classified REPORT/INFRASTRUCTURE. The same
  frozen node sets were executed split by package.
- Full Toolkit split matrix: 814 collected, 753 passed and 61 failed before the final three
  historical-manifest expected-rule corrections; the remaining 58 are the same fake-CMake
  environment failures. The corrected generation suite is green as recorded above.
- Compileall and `git diff --check` passed.

## Fresh local 3.12 smoke

The host initially lacked setuptools, so the exact wheel command first produced an
ENVIRONMENT/INFRASTRUCTURE `Cannot import 'setuptools.build_meta'` failure. A disposable local
build-dependency root was then used; this is not VS09-B dependency or release evidence.

| wheel | bytes | SHA-256 (slice evidence only) |
| --- | ---: | --- |
| `stm32_toolkit-0.9.0-py3-none-any.whl` | 531210 | `b8b4e3028df6469820671b3ee6b963bc3966236610fb583eb81550d5c9910691` |
| `stm32_monitor-0.9.0-py3-none-any.whl` | 324810 | `d96022958840cb7d57d21e6f28a8a82dc19c6d8250eb3eb593bed510d215d64a` |

Fresh `C:/tmp/p0901-runtime` installed both wheels offline from `C:/tmp/p0901-wheelhouse`.
Observed: Toolkit `0.9.0`; Monitor `0.9.0`; doctor `ok=true`, CPython `3.12.10`, compatible
Toolkit/Monitor 0.9.0, 48 MCP tools, 8 Skills; MCP count `48`; UI index and Vite manifest both
`true`; `stm32_monitor version` `0.9.0`. No hardware was touched.

## Evidence classifications and handoff

- PRODUCT: all current 0.9 contracts, adapters, lifecycle behavior, docs, and fixture/test updates.
- ENVIRONMENT/INFRASTRUCTURE: fake-CMake child import failures and absent host setuptools.
- REPORT: combined pytest collection collision; split evidence is retained.
- PLATFORM: no extra platform-only PASS claimed.
- HARDWARE: deferred; no physical evidence claimed.

## Cleanup and handoff

After evidence capture, all disposable `C:/tmp/p0901-*` roots were removed, including baseline,
RED/GREEN roots, split matrix roots, wheelhouse, build-dependency, runtime, project, and data roots;
the matching JUnit XML files were removed as well. A final `C:/tmp` check found no `p0901*` files or
directories. Generated repository `build/`, `*.egg-info/`, `.pytest_cache/`, `__pycache__/`,
`*.pyc`, and `*.pyo` artifacts were removed. Source-controlled fixtures, historical evidence, and
the ignored SDD ledger were retained. The branch remains local and unpushed; Sol owns the
complete-diff review and verdict.

## Sol review round 1 correction evidence — 2026-08-25

Sol reviewed the prior returned head `591a71242bfbcbd29433634cae4cd433fe9e9725` and issued
`REVISION_REQUIRED` for five Important findings. The same GPT-5.6-luna/max implementer
`/root/vs09a_implementer` retained ownership under corrected plan commit
`f67caab726b924c963e92c145d0e110bf9f45034`; Sol remains the independent reviewer/acceptor. No
remote, PR, merge, tag, release, hardware, or VS09-B action occurred.

Correction RED evidence:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_cli.py -k "workflow_contexts or invalid_project_root_values or redirected_project_root" -q --basetemp C:/tmp/p0901-correction-cli-red
```

Result: `8 failed` before the shared root action/type fix (duplicate global/local roots and invalid
roots reached parser/workflow paths).

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_mcp_server.py -k "duplicate" -q --basetemp C:/tmp/p0901-correction-mcp-red
```

Result: `2 failed` (`DID NOT RAISE`) before duplicate project/data guards.

The setup negative tests in `C:/tmp/p0901-correction-setup-red2` and
`C:/tmp/p0901-correction-setup-red4` showed an incomplete `ok=true,data={}` doctor incorrectly
reported healthy and Bootstrap incorrectly returned `0` instead of `2`. The UI identity/docs
RED showed current UI `0.5.0` and `--preset Debug`; the independent inventory oracle was already
green. The direct parser RED was:

```powershell
C:/tmp/p0901-correction-runtime/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_cli.py::test_parser_rejects_relative_project_root_before_dispatch -q --basetemp C:/tmp/p0901-correction-parser-relative-red2
```

Result: `1 failed` (`DID NOT RAISE`) before the shared root type rejected relative values.

Correction GREEN commands and exact results:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_cli.py -k "workflow_contexts or global_project_root or invalid_project_root_values or redirected_project_root" -q --basetemp C:/tmp/p0901-correction-root-cli-green2
py -3.12 -m pytest tools/stm32-toolkit/tests/test_mcp_server.py -k "duplicate" -q --basetemp C:/tmp/p0901-correction-root-mcp-green2
py -3.12 -m pytest tools/stm32-toolkit/tests/test_cli.py::test_parser_rejects_relative_project_root_before_dispatch tools/stm32-toolkit/tests/test_creation_cli.py -q --basetemp C:/tmp/p0901-correction-parser-relative-green
py -3.12 -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py -q --basetemp C:/tmp/p0901-correction-setup-all-green
```

These returned root CLI `8 passed` plus global-root coverage (`7 passed`), MCP duplicate roots
`2 passed`, parser/creation `15 passed`, plugin layout `19 passed`, and setup runtime `25 passed`.
The final focused CLI/parser set collected `157`, with `156 passed`, `1 skipped` (directory
junction unavailable on that node), and zero failures.

The installed CPython 3.12 candidate was used for the final package-split Step 12 matrix to keep
the two `test_cli.py` modules isolated:

```powershell
$env:PYTHONPATH = 'tools/stm32-toolkit/src;tools/stm32-monitor/src'
C:/tmp/p0901-correction-runtime/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cubemx_project.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_result.py tools/stm32-toolkit/tests/test_target_transports.py -q --basetemp C:/tmp/p0901-correction-slice-toolkit-final --junitxml=C:/tmp/p0901-correction-slice-toolkit-final.xml
C:/tmp/p0901-correction-runtime/Scripts/python.exe -m pytest tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_protocol.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py -q --basetemp C:/tmp/p0901-correction-slice-monitor --junitxml=C:/tmp/p0901-correction-slice-monitor.xml
```

Toolkit's 16 exact Step 12 files returned `832 tests`, zero failures/errors/skips; Monitor's 7
files returned `219 passed in 85.16s`. Compileall and `git diff --check` both exited `0`. The
pre-candidate fake-CMake subprocess/import failures remain ENVIRONMENT/INFRASTRUCTURE evidence;
no VS08 workflow behavior was changed.

Product fixes were committed before the final smoke as Product CodeHead
`b547803c10bf9944b9f7a33178343b8c32bfd717` (`fix(vs09): address runtime convergence review
findings`). Fresh offline wheels from that head:

| wheel | bytes | SHA-256 |
| --- | ---: | --- |
| `stm32_toolkit-0.9.0-py3-none-any.whl` | 532058 | `47ed9114fab1383a605610f8048b36a14c003a6844272b1323b12c76b7aa5404` |
| `stm32_monitor-0.9.0-py3-none-any.whl` | 324810 | `641ffbbe5200d6dae565bb7455213e4566f8921d30811f38cd520981323ad021` |

The fresh offline candidate runtime reported Toolkit/Monitor `0.9.0`, doctor `ok=true` with
CPython `3.12.10`, `pythonSupported=true`, compatible Toolkit/Monitor `0.9.0`, exact 48 MCP/8
Skill inventory, MCP count `48`, UI index/manifest `true`, and `stm32_monitor version` `0.9.0`.
No hardware was touched.

After evidence capture, all verified `C:/tmp/p0901*` correction roots and matching JUnit XML were
removed, including RED/GREEN roots, candidate/runtime/project/data roots, build-dependency and
wheelhouse roots. Final `C:/tmp` verification found no `p0901*` entries. Generated repository
build/egg-info/pytest-cache/Python-cache artifacts were removed; the tracked
`tools/stm32-toolkit/src/stm32_toolkit/build` source package and the ignored SDD report/ledger
were preserved. This correction report remains evidence only and records no acceptance verdict.
