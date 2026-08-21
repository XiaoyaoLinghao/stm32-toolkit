# STM32 Toolkit 0.6 VS-03 Task8B Monitor Adapter Plan

## Ledger

- Accepted base: the Task8 contract commit whose parent product head is
  `2fb06f066ba3f8012617d065657d4eac5049e5cf`.
- Slice: Monitor CLI replay ingest, analysis compare, and bundle export.
- Implementer: one GPT-5.6-luna/max agent in an isolated `codex/` worktree.
- Reviewer: GPT-5.6-sol, complete base-to-head diff.
- Remote authority: none. Python: CPython 3.12 only.

## Allowed files

- `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py`
- `tools/stm32-monitor/src/stm32_monitor/protocol.py`
- `tools/stm32-monitor/src/stm32_monitor/cli.py`
- `tools/stm32-monitor/tests/test_analysis_cli.py` (create)
- existing `tools/stm32-monitor/tests/test_analysis_workflows.py`, `test_protocol.py`, or
  `test_cli.py` only for focused wire/compatibility assertions.

No Toolkit workflow, diagnostic, MCP, UI, runtime service, or Evidence model changes are allowed.

## Implementation

1. RED: freeze `AnalysisPublication` closed wire round-trip and rejection tests.
2. RED: add one CLI matrix proving ingest/compare/bundle grammar, Project/Workspace/Evidence binding,
   closed safe files, one workflow call, result projection, and fixed error mapping.
3. Implement the publication wire methods and the four-code additive ProtocolResult extension.
4. Extend the existing CLI without changing `serve`/`open`. Build WorkspacePaths from Project v3,
   bind the exact workspace Evidence root, parse inputs, call one workflow once, and emit one
   ProtocolResult JSON line.
5. Bundle consumes the publication file; it never calls compare. Return decoded canonical bundle
   plus bundle ref without leaking paths or exceptions.

## Verification

```powershell
py -3.12 -m pytest -q -p no:cacheprovider --basetemp <external-temp> tools/stm32-monitor/tests/test_analysis_cli.py tools/stm32-monitor/tests/test_analysis_workflows.py tools/stm32-monitor/tests/test_protocol.py
py -3.12 -m pytest -q -p no:cacheprovider --basetemp <external-temp> tools/stm32-monitor/tests/test_analysis_cli.py tools/stm32-monitor/tests/test_cli.py
```

Also run `py_compile` for the three product files and base-to-head `git diff --check`. Do not run
Toolkit adapter, integration, UI/e2e, release, packaging, hardware, or Python 3.10 Gates.

## Acceptance

Sol reviews a clean detached exact head, runs focused publication/CLI/protocol tests and existing CLI
compatibility, and issues one verdict. Correctable findings stay on this branch with the same Luna
owner.
