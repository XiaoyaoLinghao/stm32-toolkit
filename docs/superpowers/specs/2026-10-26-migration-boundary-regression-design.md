# Migration boundary regression design

Accepted base: `763d7745ca8821bb3d6d9fa4eb5fda7028235858`. This is an offline test-only slice within the user-requested v1.3.1 regression and delivery goal. Product Python is unchanged from accepted `bb027fd3d0663a4e3310a011ecfc7b21b416f44b`. Primary owns this design, orchestration, complete independent review and acceptance. Local Claude Code CLI with the existing provider owns test implementation and implementation verification. No remote action is assigned.

## Contract

Recently added Keil migration must refuse ambiguous or unsupported input without guessing addresses, accepting unknown ARMCC startup semantics, or modifying the original project. This slice adds meaningful regression evidence for those existing decisions. It does not alter behavior, error codes, supported syntax, source paths, limits, coverage membership or release thresholds.

Cover missing scenarios after comparison with existing tests and native evidence:

- Integer expressions and object-like macro context: real boundary values, invalid arithmetic/unsupported tokens, expansion cycles and bounded resource exhaustion. Assert the stable `ConstantResolutionError` category or public migration diagnostic and useful neighboring valid cases; do not instantiate parser branches merely to trace them.
- Header/source context: conditional/redefined/function-like/unavailable constants, containment and ambiguous include resolution, invalid encoding and changed input. Use synthetic contained files, declared includes and the existing `SourceSymbols`/scan/preflight interfaces. Preserve original bytes and avoid generated output on refusal.
- Startup whole-grammar decisions: incomplete or contradictory microlib boilerplate, unknown statements within each supported stage, malformed vector ordering/handlers, and stack/heap boundaries. Use the existing authored synthetic startup fixture. Assert exact diagnostic and relevant location, no generated startup for a blocked analysis, and source preservation. Do not copy vendor/user source.

Prefer public preflight or exported analysis/evaluation entry points plus existing test helpers. A deterministic injected external filesystem outcome is allowed only when it verifies a real refusal/ownership contract, is explicitly described as injected, and leaves the decision under test intact. Do not replace validation functions with predetermined answers. Use real small boundary fixtures; do not lower production limits just to increase coverage. Real symlink capability remains a separate platform gate; do not convert its skip into a fake PASS.

## Boundaries

Allowed implementation files are two new tests: `tools/stm32-toolkit/tests/test_migration_constant_boundaries.py` and `tools/stm32-toolkit/tests/test_migration_startup_boundaries.py`. Reuse helpers from existing test modules without editing them. No product, release builder, global conftest, docs/Skill, dependency, configuration or existing-test modification. If a product defect or an existing helper blocks a valid scenario, return exact evidence for primary scope review rather than patching outside the slice. No hardware, original firmware project, installed runtime, global Skill, installation, network or remote mutation.

The coverage audit's claimed stale acceptance/startup regions was rejected: native executed lines show the successful paths. Target missing refusal behavior only; no duplicate success tests based on that false claim. The actual branch index is planning input, never a denominator-change authority or a promised measured gain.

## Acceptance

Claude returns exact working-tree state, changed files, implemented scenarios and limitations. File-only implementation is not a test PASS. Verification uses a separate native PowerShell invocation with the exact coordinator-supplied command and paths. Run the new tests and existing constant/common-syntax/startup/preflight callers as one bounded affected suite; preserve any failures. Primary reviews every changed line at the frozen CodeHead in a clean separate tree and independently runs the new cases plus relevant integration callers. Native branch data is source-bound and additive to retained complete-matrix evidence only after successful verification and reconciliation. No final coverage or release acceptance is inferred from this slice alone.
