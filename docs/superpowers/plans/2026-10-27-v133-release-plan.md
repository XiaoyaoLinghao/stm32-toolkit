# v1.3.3 release plan

Accepted base: 39497f89e1ad2e2b5af27181af08385b755961b6. Branch: codex/v133-delivery.
Primary owns specification, orchestration, complete diff review and acceptance;
local Claude Code CLI (existing provider/model) owns implementation and tests.
User explicitly authorizes v1.3.3 source/tag push and Release Latest after validation.
No original firmware projects, hardware, installed runtime or global settings change.
Final actual installation and VS Code validation belong to the user.

## Scope and sequence

1. Align active Toolkit/Monitor/UI/plugin/setup/launchers/release/schema identities
   to 1.3.3. Keep dependency pins and schema/template versions unchanged. Recognize
   1.3.2 as legacy runtime/generator input, retaining all prior guards. Update only
   current-version-dependent test expectations, add 1.3.2 upgrade cases and preserve
   future-version refusal semantics. Rebind setup utility/policy hashes from canonical
   Git bytes; never relax integrity checks. File-only edit and native verification split.
2. Keep both READMEs short and equivalent. Describe the two independent GCC project
   routes and optional Git. Update active examples to 1.3.3, clearly mark the local
   candidate until publication. Explain explicit source-intent choices, destination
   rebinding, complete preparation and normal managed flash with content identity.
   No universal ARMCC equivalence, hardware or vendor-package validation claims.
3. Run complete affected version/setup/Monitor test files with fresh native branch
   evidence; rerun both real GCC / simulated managed-flash journeys at the release
   source. Reuse accepted integration evidence only where exact source/test bindings
   permit. Reconcile all current Python sources, dropping prior arcs on changed bytes.
   UI source changed since 1.3.2: use current complete native UI coverage and bundle
   checks, not historical 1.3.2 UI scores. Actual vendor generation is unverified:
   CubeMX firmware package absent; offline new-project fixture uses synthetic adapter.
4. Freeze reviewed source, make two independent official offline builds from canonical
   exact tracked bytes, compare all 13 assets and verify extracted bundle. Preserve
   failures/skips and coverage limits. Candidate-specific exception needed if permanent
   gates unmet; old approvals do not transfer. Complete concrete checks before asking.
5. Verify Git auth/remote ancestry, non-forced push master and annotated v1.3.3 tag.
   Upload checked files to draft, verify, publish Latest and anonymously download/hash
   every asset. Update publication docs only after observed success.

## Pre-measurement responsibility decision

Retain every existing risk-core-v2 member and threshold. Add complete files
`source_provenance.py`, `migration/delivery.py`, `migration/source_intent.py`, and
`build/model.py`: they validate content provenance, independent delivery ownership,
reviewed semantic-change intent and build identity inputs respectively. This decision
precedes coverage measurement; no scores were consulted. All Python sources remain
in the overall denominator. Final native source mapping records exact membership.

## Evidence and acceptance

Claude runs exact bounded commands; primary independently reviews complete diff and
checks source/asset identity. Source-specific integration evidence is explicitly reused,
never labeled a fresh full-repository final-head run. Native shell missing numeric exit
stays null; bound subprocess exits and fresh JUnit provide separate test evidence.
Permanent 90% Python overall / Toolkit risk and 95% Monitor risk gates unchanged.
Actual installation/VS Code: USER_VALIDATION_PENDING (user). Hardware: not authorized.
No publication until all required gates pass or concrete exceptions are explicitly approved.
