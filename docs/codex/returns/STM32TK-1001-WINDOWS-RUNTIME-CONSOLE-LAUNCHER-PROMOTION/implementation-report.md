# STM32TK-1001 Windows runtime console-launcher promotion report

Status: `ACCEPTED`

Module/phase: VS10-A Task 8 follow-up; independent Windows install/runtime
transaction correction.

Date: 2026-09-07 (Asia/Shanghai).

## Frozen lineage and ownership

- Full accepted product base: `387e59067cb066d5bb9ccf5d0e2253644a9710f5`;
  tree `fbbf285defe7817e61c3b1b69260a1c6598401ac`.
- Approved design/plan head: `3bf4b05f262b148c384250fe3ac75db7d60d139a`;
  tree `9436dfa9f38ea27d9a0c91ea024abfca6afa1aab`.
- Accepted code/tests head below this report:
  `478f52f71efc54ddaaccfd5ef760ce7f54e6a5a8`; tree
  `05274c0602c4a5c2da1b4bd877e8169880930d5a`.
- Active branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Tracked remote branch remained at
  `93d5b32dd2dc2cb613ba9c68f714abd95df83d14`. No fetch, push, PR mutation,
  merge, tag, release, remote-branch mutation, campaign-runtime installation,
  or hardware action occurred.
- Specification, plan, complete-diff review, and acceptance owner: GPT-5.6-sol
  primary.
- Product/test implementation owner: exactly one GPT-5.6-luna agent at
  reasoning effort `max`. The implementer did not accept its own diff.

This report is committed separately after the code/tests head and intentionally
does not contain its own future commit SHA.

## Commit lineage

1. `98e4716c6363b9109e72373c7241f2d2b6dea732` — real pip/distlib relocation RED.
2. `46c3ca8fc9863108a4ff03e68661e8071d2b9236` — CHECK-only staging-binding test.
3. `2fc5f22ca6565a94b6f31fb72e7f766860891af1` — post-promotion rollback RED.
4. `e55bcc12f9363d4b06f518827ba5d337830ce697` — product GREEN; only
   `bin/setup-stm32-env.ps1` changed.
5. `478f52f71efc54ddaaccfd5ef760ce7f54e6a5a8` — one-line test-fixture
   correction required by Sol review; only `test_setup_runtime.py` changed.

The final accepted-base-to-code-head path set is exactly the approved design,
plan, setup helper, and setup test file. The product/test paths are only:

```text
bin/setup-stm32-env.ps1
tools/stm32-toolkit/tests/test_setup_runtime.py
```

## Implemented public behavior

- Bootstrap and Repair keep the existing verified-wheel staging install, then
  move the candidate to `DATA_ROOT/runtime/0.9.0`.
- Before publishing `runtime-state.json`, the final runtime interpreter
  revalidates the copied manifest entries for exactly `stm32-toolkit==0.9.0`
  and `stm32-monitor==0.9.0` and force-reinstalls only those two wheels with
  the existing offline, binary-only, no-dependency policy.
- The three product launchers `stm32-toolkit.exe`,
  `stm32-toolkit-mcp.exe`, and `stm32-monitor.exe` must be regular,
  non-redirected files bound to the exact final Python and must not contain a
  staging binding.
- Toolkit and Monitor launcher version smokes must each return exactly `0.9.0`.
  The MCP executable is byte/binding checked without starting a server.
- CHECK performs the same launcher validation read-only and reports the
  existing structured `broken`/Repair recommendation for an old relocated
  runtime.
- Finalization stays inside the existing quarantine rollback boundary. A
  failure removes the candidate, restores the prior runtime and prior state
  bytes when present, and never publishes matching new state early.
- One CPython `>=3.12,<3.13` runtime, explicit project-root behavior, generic
  CLI/MCP/Monitor launchers, Claude thin adapter, schemas, inventories,
  packages, and Agent-neutral architecture remain unchanged.

## TDD and implementation evidence

The independent reviewer reconstructed all three new tests at the test-only
head before the product GREEN. Under CPython 3.12.10 they failed as follows:

- Bootstrap: the launcher did not contain the final runtime Python path.
- Repair rollback: Repair incorrectly returned success after an invalid
  post-promotion entry point, proving final validation was absent.
- The first CHECK RED stopped in fixture setup because it tried to replace a
  final binding that the accepted product had never generated. Sol classified
  this as `REPORT/TEST DESIGN`, not a product failure, and returned
  `REVISION_REQUIRED` without changing product code or weakening assertions.

The Luna owner added one fixture line that first creates a final-bound launcher
baseline and then corrupts it to a staging binding. Sol independently applied
that test-only correction over the no-product test head. The corrected RED
reached CHECK and failed exactly with:

```text
assert payload["runtime"]["status"] == "broken"
AssertionError: assert 'healthy' == 'broken'
```

On the final code/tests head the same node passed. The implementer reported:

- initial focused launchers: 2 passed;
- rollback node: 1 passed;
- initial complete setup file: 35 passed in 370.32 seconds;
- corrected CHECK node: 1 passed;
- corrected complete setup file: 35 passed in 373.59 seconds;
- PowerShell parse, `git diff --check`, changed-path audit, final clean status,
  and D-drive run-root cleanup passed.

## Independent Sol review evidence

The Sol reviewer used clean detached worktrees on `D:\codex-tmp` and reviewed
the complete
`387e59067cb066d5bb9ccf5d0e2253644a9710f5..478f52f71efc54ddaaccfd5ef760ce7f54e6a5a8`
diff. Product logic, tests, frozen design, and plan were inspected; no unresolved
product, security, compatibility, lifecycle, or scope finding remains.

Reviewer results on CPython 3.12.10:

- PowerShell parse and complete diff check: pass.
- Three launcher/promotion/rollback nodes at product GREEN: 3 passed in 101.07
  seconds.
- Existing repository Toolkit/MCP/Monitor `.cmd` launcher nodes: 6 passed in
  1.14 seconds.
- Complete `test_setup_runtime.py`: 35 passed in 374.59 seconds.
- Corrected final-head CHECK node: 1 passed in 29.17 seconds.
- Final head/tree and changed paths matched the frozen ledger; implementation
  and detached review statuses were clean.

The first reviewer `.cmd` test command omitted the repository source
`PYTHONPATH` and failed collection with `ModuleNotFoundError:
stm32_toolkit`. It was classified `ENVIRONMENT`; the identical nodes passed
after adding only `tools/stm32-toolkit/src` to `PYTHONPATH`. No product or test
assertion changed for that event.

The clean candidate tree contains no `release/wheels` or release manifest, so
an additional real-release-bundle Bootstrap was not run. This remains
release-layer evidence and is not represented as a PASS. The slice evidence
uses real Windows pip/distlib launcher generation with offline synthetic
product wheels; it does not accept or install a release artifact.

## Cleanup and remaining boundary

All implementation-owner and reviewer-owned `D:\codex-tmp` basetemps were
removed after exact-path inspection. One reviewer full-suite cleanup initially
encountered an access-denied test-created redirect; after the surrounding
contents were removed, the now-empty exact child and parent directories were
deleted. No source, reusable fixture, shared cache, campaign runtime, or
user-owned project path was touched.

The older independent experiment
`C:\tmp\stm32tk-relocation-exp-20260907-01` remains an explicitly reported
`ENVIRONMENT / cleanup-policy` residue because its earlier exact recursive
cleanup was rejected before launch. It is not product evidence and was not
created by the accepted implementation/review runs.

Verdict: `ACCEPTED` for this Windows runtime console-launcher correction. This
does not install it into the active campaign runtime, accept the unresolved
post-flash resume/hardware boundary, complete VS10-A, authorize a further
physical attempt, or authorize any remote/release action.
