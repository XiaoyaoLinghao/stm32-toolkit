# STM32TK-0901 Sol independent review report

## Verdict

`ACCEPTED`

- Accepted base: `9a5a132b74638a39b346848cfad0eeb7db9a0539`.
- Returned report head reviewed: `8c57f0ecf6b812ddaba9f19cedf394d3fbe50edc`.
- Product CodeHead: `b547803c10bf9944b9f7a33178343b8c32bfd717`.
- Sole implementer: GPT-5.6-luna/max, `/root/vs09a_implementer`.
- Independent reviewer/acceptor: GPT-5.6-sol primary agent.
- Review worktree: clean detached `C:/tmp/stm32tk-0901-sol-r1-review-8c57f0ec`.
- Remote/hardware actions: none.

Sol reviewed both the bounded correction range
`591a71242bfbcbd29433634cae4cd433fe9e9725..8c57f0ecf6b812ddaba9f19cedf394d3fbe50edc`
and the complete accepted-base range
`9a5a132b74638a39b346848cfad0eeb7db9a0539..8c57f0ecf6b812ddaba9f19cedf394d3fbe50edc`.
No unresolved product defect remains in VS09-A.

## Finding reconciliation

1. **Root cardinality and safety — ADDRESSED.** One shared CLI action/type now rejects a global
   plus command-local root and rejects empty, unresolved, relative, or redirected project roots
   before dispatch across workflow, hardware, testing, and diagnostic parsers. MCP project/data
   roots reject duplicates. Existing aliases and workflow behavior remain intact.
2. **Managed-runtime health evidence — ADDRESSED.** Check and pre-promotion validation require the
   exact Python contract, compatible Toolkit/Monitor 0.9.0 identity, and ordered 48 MCP/eight Skill
   inventories. Missing, false, malformed, or mismatched evidence is broken and cannot promote.
3. **Monitor/UI identity — ADDRESSED.** Current package-lock roots and fake/runtime/bootstrap/main
   fixtures are 0.9.0; explicitly historical 0.5 evidence remains historical.
4. **Independent inventory oracle — ADDRESSED.** Tests contain a frozen expected 48-name mapping
   and separately compare production authority and actual server registrations against it.
5. **Executable documentation — ADDRESSED.** English and Chinese examples use the existing
   `--preset arm-debug` value and focused tests assert that exact command.

## Independent verification

All commands ran in the clean detached returned-head worktree on Windows with CPython 3.12.10.

```powershell
$env:PYTHONPATH='tools/stm32-toolkit/src'
py -3.12 -m pytest tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_doctor.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_setup_runtime.py -q --basetemp C:/tmp/p0901-sol-r1-focused
```

Result: exit `0`, progress reached 100%, zero failures/errors. The only output warning was the
existing in-process `runpy` warning for the CLI module guard.

```powershell
$env:PYTHONPATH='tools/stm32-monitor/src;tools/stm32-toolkit/src'
py -3.12 -m pytest tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_protocol.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py -q --basetemp C:/tmp/p0901-sol-r1-monitor
```

Result: `219 passed in 53.12s`.

`git diff --check 9a5a132b74638a39b346848cfad0eeb7db9a0539..8c57f0ecf6b812ddaba9f19cedf394d3fbe50edc`
returned exit `0`.

Sol also built both wheels offline with `--no-deps --no-build-isolation --no-cache-dir`, installed
them into a fresh CPython 3.12 venv, changed to a directory outside the repository, and ran the
candidate with `-I`. Observed evidence:

| wheel | bytes | SHA-256 |
| --- | ---: | --- |
| `stm32_toolkit-0.9.0-py3-none-any.whl` | 532095 | `9c732184740f64620196a892352629d0f35654a3cac23756229cf420141e4656` |
| `stm32_monitor-0.9.0-py3-none-any.whl` | 324797 | `fb934afce110ca428137cae0844da5585b54d7a38e35f02153e9f7a42304ddfa` |

The installed candidate reported Toolkit/Monitor `0.9.0`, Python `3.12.10` supported, compatible
versions, doctor inventory 48 MCP/eight Skills, actual MCP count 48, and present UI index/Vite
manifest. Imports resolved from the fresh venv's `site-packages`, not the source checkout.

The first smoke venv made from the desktop bundled build interpreter could not import `elftools`
because that interpreter exposes dependencies outside its venv-visible site-packages. This was
classified `ENVIRONMENT`; the same product wheels passed unchanged in the fresh host CPython 3.12
venv with the declared runtime dependencies visible.

## Cleanup and boundary

The exact `C:/tmp/p0901-sol-r1-focused`, `C:/tmp/p0901-sol-r1-monitor`, and
`C:/tmp/p0901-sol-r1-wheel-smoke` roots were verified and removed. The detached review worktree
remained clean. No hardware, push, PR mutation, merge, tag, release, remote branch, CI, or
collaboration automation action occurred. VS09-B may begin only from this accepted local VS09-A
line; this verdict does not authorize any remote or release action.
