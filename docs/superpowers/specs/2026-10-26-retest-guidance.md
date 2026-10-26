# Retest diagnostics and correct AI usage

Accepted base: `f5d8978a2a60c59ec5afee4fc014707311210fe5`.
Primary owns specification, orchestration, complete-diff review and acceptance;
local Claude CLI (existing configured provider) implements and tests. Branch:
`codex/v132-retest-diagnostics`; no PR or remote action is authorized for this slice.
User steering: do not implement every suggested grammar extension mechanically;
provide reasonable guidance so the tool can be used correctly. Offline only;
original firmware project, user test copy, installed runtime and hardware stay read-only.

## Findings and behavior

The supplied preflight has eight blockers: three alignment, four absolute
placement, and one embedded assembly function. Existing rules already support
macro bounds, literal and macro addresses and section/fixedSections rewrites.
The supplied malloc.c is UTF-8 while malloc.h is not UTF-8. Constant dependency
resolution currently collapses this cause into `unreadable` or declaration grammar.

1. Preserve the bounded integer evaluator, strict UTF-8 dependency contract and
   all existing grammar/placement/ownership guards. Improve diagnostics to name
   the project-relative dependency and cause (especially a non-UTF-8 header),
   and distinguish array-bound resolution failures from unsupported declaration
   grammar. Give actionable comment-normalization guidance for headers as well
   as sources, with explicit per-file charset and external reviewed copies.
   Never guess encoding, skip a failed include, or silently accept unresolved bounds.
   Do not expose absolute host paths or raw exception text. Error codes remain compatible.
2. An embedded `__asm void ... { WFI; }` with no explicit return remains blocked.
   Explain the missing return and potential fall-through; obtain a Keil
   disassembly/control-flow baseline before deciding intended behavior. Never
   manufacture BX LR, insert CMSIS intrinsics or remove a blocker by guessing.
   ARM reference: https://documentation-service.arm.com/static/5eb946b50f1c1e0dae6ee21e
   section 7.30 describes possible fall-through when a return is omitted.
3. CLI structured JSON output must be decodable as UTF-8 independent of a
   Windows legacy stdout codec. Prefer ASCII JSON escapes (`ensure_ascii=True`),
   preserving parsed Unicode values, result shape and exit status. Do not
   globally alter console encoding or environment settings.
4. Update the migration skill and detailed VS Code/AI calling guidance with a
   root-cause decision path, complete diagnostic reading, header preparation,
   literal/macro placement support and the WFI boundary. Distinguish frozen
   package build-time docs from current master publication docs; no README
   expansion, version bump, retag, package replacement or release operation.

## Evidence

Claude supplies synthetic regression cases for the reported declaration shapes,
non-UTF-8 quoted headers, transitive failures, missing/cyclic/ambiguous dependencies,
literal-only cases and unchanged unsafe syntax guards. Verify that a UTF-8 header
with 200*1024/60*1024 macros resolves fixed addresses and all alignments through
existing rules. Missing-return WFI stays blocked with useful diagnostic, valid
explicit-return wrappers keep passing. Run a real child CLI under legacy stdout
encoding with Chinese and non-BMP text; capture raw bytes, UTF-8 decode/JSON parse,
unchanged values/status. Primary reviews whole diff and exact native test evidence.
No actual migration apply, installation, flash or runtime equivalence claim.
