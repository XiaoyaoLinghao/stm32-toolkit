# STM32TK-0701 VS07-A implementation report

Status: `REWRITE_REQUIRED` after independent GPT-5.6-sol recovery review. The
implementation evidence below is retained as the implementer's record and is
superseded where the independent verdict identifies missing proof or behavior.

## Ownership and source ledger

- Product accepted base: `d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58`.
- Implementation branch base: `6007fafc33ee801b8bda64540dcefa50eef8b26a`.
- Specification source: `fa9a3c4aa349d296f5de9704ecb4300fc420a71f` (`2026-08-22-stm32-toolkit-0.7-1.0-integrated-product-design.md`).
- Implementation plan: `docs/superpowers/plans/2026-08-22-stm32-toolkit-0701-creation-plan-environment-truth.md`.
- Implementer: one GPT-5.6-luna implementation agent, reasoning `max`.
- Reviewer/acceptor: GPT-5.6-sol primary agent; this report is not an approval.
- CodeHead before this report commit: `aa47d500` (full code head; report does not record its own final SHA).
- Remote authority: none. No push, fetch, PR, merge, tag, release, remote branch, hardware action, installation, or CubeMX execution was performed.

## Delivered behavior

VS07-A now has a replacement discovery boundary with fail-closed trusted profiles, bounded CubeCLT metadata/native version probes, static CubeMX/VS Code inspection, deterministic `CreationPlan`/action digests, read-only destination and `.ioc` inspection, a common workflow, CLI `project create-plan`, and MCP `stm32_project_create_plan`. The planner never executes CubeMX or writes a destination. Python support is CPython `>=3.12,<3.13`.

Task 1–4 were performed sequentially by this same implementation owner. No VS07-B/C, hardware, new backend, release matrix, coverage gate, or Python 3.10/3.11 support was added.

## TDD and slice verification evidence

The candidate package was imported from this worktree with `PYTHONPATH=tools/stm32-toolkit/src`; pytest temporary files were redirected to the disposable `C:\tmp\p0701` directory because the host default temp root denied access.

- Replacement RED coverage was added for profile containment, metadata runner failure modes, static executable non-execution, runtime profile reuse, and exact request fields; the pre-rewrite baseline review had already demonstrated these cases failing. Replacement GREEN focused command: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_mcp.py -q` — exit 0; all collected tests passed, no skips/xfails.
- Creation slice GREEN command: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py -q` — exit 0; all collected tests passed, no skips/xfails.
- Task 4 complete slice: `py -3.12 -m pytest tools/stm32-toolkit/tests/test_tool_support.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_creation_plan.py tools/stm32-toolkit/tests/test_creation_workflows.py tools/stm32-toolkit/tests/test_creation_cli.py tools/stm32-toolkit/tests/test_creation_mcp.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py -q` — exit 0; all collected tests passed, no skips/xfails (one existing runpy warning).
- Diff hygiene: `git diff --check d09e2343ab970f4ddeaa4c24dbf581c9bbe96f58..a8e6851f` — exit 0 before documentation changes.

## Real read-only environment observation

Disposable workspace: `C:\tmp\stm32tk-0701-observe-20260823`. The workspace was snapshotted by relative names and sizes before and after both commands; `snapshotEqual=true`.

- `py -3.12 -m stm32_toolkit.cli doctor --project-root C:\tmp\stm32tk-0701-observe-20260823 --json` — exit 0.
- `py -3.12 -m stm32_toolkit.cli project create-plan --project-root C:\tmp\stm32tk-0701-observe-20260823 --source-kind mcu --source STM32F429ZITx --destination generated --framework hal --language c --json` — exit 0; `mutated=false`, `blockers=[]`.
- CubeMX was found through the bounded Windows App Paths registration at `D:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe`; observed version is exactly `6.18.1-RC2`, source `standard`, and it is accepted by the 6.18.x rule. CubeMX was not run.
- CubeCLT root: `C:\ST\STM32CubeCLT_1.22.0`; observed facts are GCC `14.3.1`, CMake `4.3.1`, and Ninja `1.13.2`.
- Doctor reported `VSCODE_MISSING` as an environment issue; it did not block the creation plan. No product or hardware failure was inferred from that fact.
- Test fixtures retain explicit `CUBEMX_MISSING` blocker coverage; the real host observation correctly does not report that blocker after the authorized user installation.

## Local state and blockers

The implementation branch contains only local commits and has no configured remote mutation. Before the implementation report commit, tracked product changes were committed through CodeHead above. The current environment fact requiring operator attention is `VSCODE_MISSING`; it is not required to produce the VS07-A plan. The independent Sol verdict below records unresolved PRODUCT blockers and is the acceptance authority.

## Sol review round 1 correction evidence

Recovery Tasks 1R–2R introduced typed candidate-resolution states and a common resolver, with canonical path deduplication, registered/standard precedence, bounded PATH enumeration, strict profile/metadata trust, creation blocker propagation, IOC negative paths, duplicate CLI rejection, and frozen MCP reuse. Focused and exact aggregate suites passed; independent Sol review remains the acceptance authority.

## Independent Sol recovery verdict

Verdict: `REWRITE_REQUIRED` at implementation head `1f02801ec5444a7e6bfecd84a93f44108e126d55`.

The exact aggregate slice passed with exit 0 under short disposable TEMP
`C:\tmp\p07sol1f`, with no skip/xfail and one existing runpy warning. A first
run under the much longer review-tree TEMP produced five existing staging
failures; the unchanged command passed under the short TEMP, so those failures
are classified `ENVIRONMENT`, not as VS07-A product evidence.

Fresh read-only doctor and MCU create-plan observations both exited 0. CubeMX
`6.18.1-RC2`, CubeCLT `1.22.0`, GCC `14.3.1`, CMake `4.3.1`, and Ninja `1.13.2`
were observed; `VSCODE_MISSING` remained the only creation-support environment
issue, plan blockers were empty, `mutated=false`, and the names/sizes/content-
hash snapshot was unchanged.

The candidate is not accepted because the same load-bearing recovery contract
remained incomplete after two rounds:

- `test_tool_support.py` was unchanged from the rejected candidate, so the
  named tier-priority, PATH ambiguity, canonical-alias, independent HKCU,
  metadata failure, native runner failure, and static non-execution tests were
  not added.
- VS Code still queries HKLM and HKCU inside one exception scope; a missing HKLM
  key suppresses HKCU discovery.
- CubeMX and VS Code still use one `shutil.which` result instead of enumerating
  the complete PATH tier, so same-tier ambiguity cannot be reported.
- Invalid registered/standard candidates are prefiltered as absent, and typed
  resolution is not consistently preserved through every public issue path.
- Task 2R proof remains partial: only one duplicate option, partial `.ioc`
  inputs, and doctor-only frozen runtime reuse were added; redirect parents,
  inventory states, all repeated scalar options, create-plan runtime reuse,
  client-root enforcement, and fixed-clock CLI/MCP parity remain unproved.

Per `AGENTS.md`, the same issue did not converge in two recovery rounds. Local
patching by the current implementation owner has stopped. No remote, install,
hardware, CubeMX execution, VS07-B, or VS07-C action is authorized or implied.
