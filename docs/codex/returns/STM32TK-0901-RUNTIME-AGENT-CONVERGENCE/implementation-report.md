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
- Product CodeHead before this report commit: `a203ff526273d8a234799a1c0a1a3bc9beb9453e`.
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
