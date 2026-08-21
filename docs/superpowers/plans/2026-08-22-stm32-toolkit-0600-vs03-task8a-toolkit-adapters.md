# STM32 Toolkit 0.6 VS-03 Task8A Toolkit Adapter Plan

## Ledger

- Accepted base: the Task8 contract commit whose parent product head is
  `2fb06f066ba3f8012617d065657d4eac5049e5cf`.
- Slice: Toolkit CLI + MCP Target replay and diagnostic verification callers.
- Implementer: one GPT-5.6-luna/max agent in an isolated `codex/` worktree.
- Reviewer: GPT-5.6-sol, complete base-to-head diff.
- Remote authority: none. Python: CPython 3.12 only.

## Allowed files

- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- `tools/stm32-toolkit/tests/test_fix_verification_cli.py` (create)
- `tools/stm32-toolkit/tests/test_fix_verification_mcp.py` (create)
- existing `test_testing_cli.py`, `test_testing_mcp.py`, `test_diagnostic_cli.py`, or
  `test_diagnostic_mcp.py` only for a minimal compatibility assertion.

No workflow/model/Evidence/Monitor/product changes are allowed.

## Implementation

1. RED: add one CLI behavior matrix and one MCP behavior matrix for all commands/tools in the Task8
   contract. Use spies to prove roots/context, one workflow call, unchanged result, closed inputs,
   and no call after grammar/root/path failure.
2. Implement CLI grammar, bounded object-file parsing, contexts, and direct workflow dispatch. Reuse
   existing safe parser/file helpers rather than creating an alternate protocol.
3. Implement MCP runtime methods and registered tools. Add a single reusable portable relative-path
   resolver for Target replay and close every new schema.
4. Preserve existing CLI/MCP names, outputs, startup, Host tests, and diagnostic commands.

## Verification

```powershell
py -3.12 -m pytest -q -p no:cacheprovider --basetemp <external-temp> tools/stm32-toolkit/tests/test_fix_verification_cli.py tools/stm32-toolkit/tests/test_fix_verification_mcp.py
py -3.12 -m pytest -q -p no:cacheprovider --basetemp <external-temp> tools/stm32-toolkit/tests/test_fix_verification_cli.py tools/stm32-toolkit/tests/test_fix_verification_mcp.py tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_diagnostic_mcp.py
```

Also run `py_compile` for the two product files and base-to-head `git diff --check`. Do not run
Monitor, integration, release, packaging, hardware, or Python 3.10 Gates.

## Acceptance

Sol reviews a clean detached exact head, runs the focused new tests and affected compatibility set,
and issues one verdict. Correctable findings stay on this branch with the same Luna owner.
