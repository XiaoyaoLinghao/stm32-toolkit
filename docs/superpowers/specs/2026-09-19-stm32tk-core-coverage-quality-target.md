# Core branch coverage quality target

The user's 2026-09-19 direction adds a preferred core branch-coverage target of
at least 95%, while preserving the mandatory package release floor of 90%.
This is a measurement and prioritization change, not a product behavior change.
The primary owns this scope and acceptance; Luna/max owns any later test or
product implementation. The frozen runtime baseline is
87699308535bd36431c2e44be8bf131e245d460d.

## User scenarios and scope

1. Create or migrate a real project, regenerate managed files safely, and build
   an artifact with consistent project, input, and firmware identity.
2. Authorize and perform bounded flash/debug/test operations, sample a running
   target, and release processes, sessions and probe leases correctly.
3. Persist, reload, compare and export authenticated observations, diagnose a
   failure, and advance recovery/acceptance through valid evidence and state.

The fixed file-selection rule below covers the deterministic Python
implementation of these scenarios, including public-boundary validators and
provider/platform files with lifecycle or failure semantics. Mixed files remain
whole; file names such as CLI, MCP, adapter, service or workflow do not exempt
their embedded contracts.

The source inventory initially proposed separate treatment for doctor and UI
assets. The primary includes both: doctor.py owns bounded subprocess capture,
termination and reaping; ui_assets.py owns resource allowlisting and CSP/header
behavior. Toolkit's top-level __init__.py is also included because its lazy
public export function has runtime behavior. Only the specifically listed
re-export-only package initializers and Monitor's pure forwarding __main__.py
are outside core. They remain in the overall package measurement.

Scope v1 includes every tracked `.py` file under
`tools/stm32-toolkit/src/stm32_toolkit/` and
`tools/stm32-monitor/src/stm32_monitor/`, except these exact relative paths:

```text
tools/stm32-monitor/src/stm32_monitor/__init__.py
tools/stm32-monitor/src/stm32_monitor/__main__.py
tools/stm32-toolkit/src/stm32_toolkit/acceptance/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/build/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/debug/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/evidence/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/generation/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/keil/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/migration/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/probe/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py
tools/stm32-toolkit/src/stm32_toolkit/testing/transports/__init__.py
```

At the frozen runtime baseline this resolves to 113 core files and 13 remaining
Python files; these counts identify scope, not completion. A run-owned inventory
records resolved paths and source hashes alongside the coverage evidence. It is
measurement data, not an additional product manifest, validator or test runner.

UI TypeScript/TSX has the separate full-source scope below. Schemas, templates,
binaries, launchers and external engines are not Python source; their existing
contract, packaging, setup, security and physical gates remain unchanged. No new
product feature, hardware scenario, coverage exclusion, generic test framework
or function-level scope is added.

### Companion UI scope

Apply the preferred 95% branch target to the complete existing UI executable
source selection, `src/**/*.{ts,tsx}`, excluding only the declaration-only
`src/env.d.ts`. This reuses the established full-source coverage configuration;
it does not select a smaller subset based on the achieved percentage. Keep the
existing mandatory per-file 90% UI gate. CSS and declaration-only files have no
executable branch denominator.

Report the UI's native Vitest/V8 branch counts separately from both Python
packages; do not combine their denominators. The retained UI result at source
15b1a70e9bd684285da5557104deff529f537e49 covers all 29 executable source files,
with no missing or extra records. Its 784/810 branches (96.79%), 260 passing
tests and successful per-file gate are reusable at the frozen runtime baseline:
UI source, configuration and dependencies are unchanged. Retained evidence is
`r10/e/ui-static`, including `coverage-final.json` and terminal command results.
This proves the UI source target only; final bundle dist/manifest verification
remains part of the artifact refresh. Report statement, function and line
coverage separately; a branch-target result does not imply those metrics are
also at 95%.

## Metrics and evidence

- Evaluate each Python package separately. The overall native branch ratio
  must be at least 0.90; the same package's frozen core subset targets 0.95.
- Compute each ratio as sum(covered_branches) / sum(num_branches), using native
  coverage data. Do not average file percentages or substitute the combined
  line-and-branch percent. Report statement coverage as a separate statistic.
- Report per-module/core-group breakdowns and uncovered public behaviors so a
  high aggregate cannot hide a weak critical module. A group is not required
  to meet an invented per-file threshold; material correctness failures still
  block acceptance independently of coverage.
- Resolve and freeze scope before evaluating its score. Missing source/data,
  mismatched hashes or unresolved file mappings mean INCOMPLETE. A zero-branch
  module is N/A, not a fabricated 100% measurement.
- Reuse retained data only for matching source bytes and valid run attribution.
  Do not merge old line numbers into changed runtime files, relabel fixture
  evidence as physical PASS, or rerun solely to recreate lost coverage data.
- Keep the approved native 90% floor intact. The preferred 95% core target is
  separately REACHED or UNMET; never claim it achieved when it is not. Any
  remaining gap and disposition must be explicit in the local release report.

This specification is the source of truth for the additional subset. Source
changes update hashes and invalidate only affected evidence; newly introduced
behavior-bearing files enter scope before measurement. Removing a file requires
a reviewed architectural reason, never an unfavorable percentage. The full
package denominator remains unchanged by this subset classification.

## Proportionate execution

Finish the already running candidate qualification without interruption. Its
existing package coverage JSON/raw databases can supply both views, so the new
target does not require a second full run. Complete only the three already
reviewed Monitor selected-node batches after primary classifies the terminal
Toolkit result. Then reconcile source-correct retained data, publish the actual
overall/core gaps, and define a finite contract-based remainder before dispatching
further implementation. Reuse valid functional and A/B hardware evidence within
its original source and environment bounds. The current 1.0 release remains
unaccepted until its mandatory requirements are verified.
