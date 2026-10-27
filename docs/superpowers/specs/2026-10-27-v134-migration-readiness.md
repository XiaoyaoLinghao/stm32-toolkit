# v1.3.4 migration readiness corrections

Approved scope: the user's 2026-10-27 instruction to implement the two audited
corrections, add regressions, verify the supplied project reaches a zero-blocker
migration plan, independently review, and publish v1.3.4 after acceptance.
Accepted base: `dc278ca226a0c1d4540657f48eb74fa1d5b361ca` (current remote master).
Primary owns specification, plan, orchestration, complete-diff review and acceptance.
Local Claude Code CLI, retaining its existing configured provider/model, owns all
product/test implementation. No original project edits, installed runtime changes,
hardware access, ABI policy changes, implicit WFI intent or debug defaults.

## Guard contract

Recognize a structural whole-file `#ifndef NAME` immediately followed by an empty
object-like `#define NAME`, closed by its matching final `#endif`. Permit balanced
nested conditional groups. Only the outer guard's opening and closing directives
are exempted from conditional depth. Macros/includes inside nested groups remain
conditional; no preprocessor branch evaluation is introduced. An outer-level
`#else`/`#elif`, premature close, malformed/unbalanced nesting, unrelated or nonempty
guard definition remains unproven. Retain guard-name collision, redefinition,
undefinition, conditional include and dependency identity refusals. Exact guard
identifier matching must not accept trailing tokens.

The audited `MALLOC/malloc.h` has a nested `#ifndef NULL` block before unconditional
MEM constants. These constants must resolve with both guards retained. This fixes
the three alignment and four absolute-placement blockers without relaxing the
declaration grammar, array bounds, address/size checks or adding macro overrides.

## Encoding discovery contract

Preflight must report all discovered non-UTF-8 quoted header dependencies in one
response, including multiple siblings and transitive dependencies, even when a
selected C/C++ source or earlier header itself has an encoding blocker. Deduplicate
by canonical project-relative path, with stable ordering and actionable remediation.
Only the inspected target's included C/C++ sources and its reviewed include search
paths participate; excluded sources, unrelated project files and system headers
are not swept into a recursive whole-project encoding scan.

Discovery is read-only and advisory to the existing semantic analysis. It may use
an explicit lossless byte-to-character projection solely to lex ASCII quoted
include directives in an already-reported invalid file; this is not a charset
guess, transcoding, accepted source text, or macro evaluation. Comments, strings,
line continuations and non-ASCII include operands must not invent paths. Strict
UTF-8 semantic resolution remains unchanged. Preserve original bytes and report
invalid encoding rather than ignoring or replacing it. If discovery cannot prove
a dependency edge, report its limitation rather than claiming exhaustive discovery.

Reuse existing contained, case-aware include lookup and redirect checks rather
than weakening them. Bound total files/bytes/depth/directories and deduplicate
cycles. Continue independent sibling discovery after an encoding error. Missing,
ambiguous, redirecting, nonportable or budget-limited edges must be represented as
incomplete discovery; do not follow them or invent additional semantic acceptance.
Do not introduce unrelated missing-optional-include blockers for previously valid
literal-only conversions. The existing lazy semantic resolver remains authoritative
for PLAN/APPLY, and all existing refusal and freshness contracts remain in force.
Known invalid headers add explicit encoding blockers to preflight readiness.

## Acceptance and release

Add positive nested-guard regressions and negative branch/collision/undef/malformed
guard controls. Add multi-header, transitive, invalid-source, comment/string,
excluded-source, deduplication, path-containment and budget discovery regressions;
prove files are unchanged and diagnostics deterministic.

Primary rechecks the UTF-8 supplied copy at
`D:/WorkSpace/mobile-robot-controller-v132-test`, with the original guarded header,
using the same reviewed WFI, extra-region, memory-layout and startup options as
`C:/work/stm32/retest-convert.json`. Require zero preflight blockers and a successful
read-only destination PLAN, unchanged source hashes and absent destination. The
unconverted original is read-only evidence for early header-encoding discovery.
Zero blockers do not imply successful GCC build or hardware equivalence.

Version alignment and official offline packaging are a separate bounded task after
software acceptance. Preserve permanent release qualification gates and accurately
reuse only source-bound evidence; v1.3.3's candidate exception does not transfer.
The user authorizes the source/tag/asset publication necessary for v1.3.4 after
review and applicable qualification. If the concrete candidate needs a gate
exception, finish and present its evidence before requesting that decision.
