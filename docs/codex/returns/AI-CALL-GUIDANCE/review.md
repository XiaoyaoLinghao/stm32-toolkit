# AI-CALL-GUIDANCE independent review

Date: 2026-10-24. Verdict: **ACCEPTED_WITH_FIXES**, for the bounded offline guidance slice only.

Accepted base: `c6cf5cda7a25e4aa0b1335558ab0ffe16fbb32be`.
Final CodeHead: `e02365f4ba7ec3c3bcaef3efae6d473215d6f7e6`.
Initial tested head: `d78cd4b18d8966b6e4a1a8094dde0590b6d33f75`.
Branch: `codex/ai-call-guidance`. No active PR, remote authorization or ownership exception.

The primary agent owns the [specification](../../../superpowers/specs/2026-10-24-ai-call-guidance-design.md), [plan](../../../superpowers/plans/2026-10-24-ai-call-guidance-plan.md), orchestration, this independent review and acceptance. Local Claude Code CLI, retaining the user's configured provider/model, authored all product changes, tests and corrections. No Codex-hosted implementation subagent or primary-authored product patch was used.

## Reviewed result

The complete accepted-base-to-CodeHead diff was inspected in the clean independent `build-snapshot-final/STM32-Toolkit` worktree. The final recorded binary diff SHA-256 is `5ed766a5f97c0390f9b1311c6972b0da273d0d4717cce81b26df96362a3083be`; the evidence copy is `D:/codex-tmp/ag24/reviewed.diff`.

Only context/preflight diagnostic presentation and MCP descriptions change runtime source. Existing capability booleans, error envelopes, binding guards, migration plans/digests, source identity, import admission and hardware behavior remain intact. Context's imported route is always `not-evaluated`; it performs no import or probe action and never substitutes for managed debug, Monitor, Target or recovery. The optional remediation `tool` and `skill` references remain distinct. No new tool, dependency, version or protocol was added: the inventory remains 52 tools and 9 skills at version 1.3.0.

The skills and VS Code guide now distinguish discovery, managed flash and explicit imported firmware before applying route-specific prerequisites. Live MCP doctor/client schema evidence is distinguished from a separate CLI process. Complete diagnostics are read before summarization; `not-evaluated` is not a refusal. Import PLAN and ADMIT are read-only; immutable-copy APPLY and hardware flash are the two write authorization boundaries.

## Findings closed

| Location | Observed issue and required correction | Evidence and verification |
| --- | --- | --- |
| `migration/preflight.py` | Initial draft called a Skill an MCP tool and suggested modifying FPU/ABI evidence or dropping options. Separate typed references, condition encoding-copy advice on explicit charset/comment-only eligibility, and preserve actual compilation semantics. | Retained `author.jsonl`/`continue.jsonl` drafts; final `test_ai_call_guidance.py` checks real references, supported classifications and unchanged blocker/plan content. |
| `context.py`, flash/setup/debug skills | Broad managed prerequisites and stop rules could block an independent import or imply imports repair managed debug. Scope provenance rules to the managed route; discovery needs no model; import stays explicitly selected and unevaluated. | Full diff plus final context/snapshot tests and primary semantic scenario review. |
| `docs/user-guide.md` | Draft example stopped when managed status was not `available`, although normal status is `not-evaluated`; ADMIT was incorrectly described as needing write authorization. Correct independent branches, status meaning and the two authorization boundaries. | Final `test_documentation_keeps_route_and_authorization_contracts` and direct comparison to registered tool arguments. |
| Guide and relevant skills | Residual CLI-as-MCP wording and blanket not-installed claims conflicted with the actual workflow. Require actual MCP client results, distinguish frozen package field absence from stale sessions, and scope installation/qualification statements to this slice. | Final documentation delta and independent semantic review; no session repair subsystem or new checker. |
| `tests/test_context.py` | Initial full regression failed because the Keil exact-dict assertion omitted additive `firmwareRoutes`; its seven original entries matched. Assert the new route contract, then retain every old exact-dict and read-only assertion. | Initial JUnit records the failure; final author context module and independent corrected case pass. |

## Verification and reuse

All runs used Windows CPython 3.12.14, same-tree Toolkit/Monitor sources and read-only installed 1.3.0 dependencies. Temporary/cache roots were isolated under `D:/codex-tmp/ag24`. Claude's native PowerShell registration and actual `Get-Location` execution were verified before dispatch; all verification calls used exact single-command allow rules and strict empty MCP configuration. There were no permission denials or shell fallbacks. Two initial file-only calls hit their 65-turn bound; edits/logs were retained and resumed, never counted as tests.

| Owner / source | Evidence | Outcome |
| --- | --- | --- |
| Claude CLI / d78cd4b1 | `new.xml` | 12 new tests passed. |
| Claude CLI / d78cd4b1 | `regression.xml` | 256 passed, 1 failed out of 257; the failure above is retained honestly. |
| Claude CLI / final e02365f4 | `final.xml` | 80 passed: new 12 + context 48 + plugin layout 20; no errors or skips. |
| Claude CLI / d78cd4b1, reused | Seven unaffected regression modules | 189 passes reused: doctor 25, preflight 20, snapshot 50, MCP roots 61, MCP migration/build 19, external routing 10, public inventory 4. |
| Primary / clean d78cd4b1 | `review.xml`, `review-execution.json` | 103 passed; process exit 0. |
| Primary / clean final e02365f4 | `review-final.xml`, `review-final-execution.json` | 33 passed: new 12 + corrected context case 1 + plugin layout 20; process exit 0. |
| Claude CLI / d78 then final | `validate.jsonl`, `test-final.jsonl` | All five affected skill frontmatters valid; final changed build/flash/migrate skills revalidated. Debug/setup unchanged. |

The final delta after d78cd4b1 changes only four guide/skill files and one test assertion. All product source, the seven reused modules and their relevant fixtures/contracts are unchanged. Thus the scoped 269 unique cases have passing evidence (80 final + 189 reused); this is **not** a new all-green full 257-case run at the final commit. The MCP-root tests emit one nonfatal dependency `IncompleteFieldDefinitionWarning` about `lifespan`; no fix or suppression was applied.

Exact author commands are recorded in [the implementation report](implementation-report.md). Primary commands are retained in the execution JSONs; logs/JUnit SHA-256 values and tree identities are recorded in [evidence.json](evidence.json). Skill validation checks structure only; its result is not a substitute for this semantic review. There are no remaining blocking findings for this slice.

## Boundaries and next stage

The original `mobile-robot-controller` project and physical hardware were not modified or operated. No package rebuild, installation, runtime/cache/global-skill mutation, VS Code restart, remote push, PR, tag or Release occurred. The 12 manifest-listed frozen v1.3.0 files plus CHECKSUMS (13 files total) still verify; CHECKSUMS, release-manifest and runtime-state hashes match the recorded baseline.

This source patch is absent from frozen source `1e6ea849c21fb3786d60dba0254acb375d016a62` ZIP/runtime. Restarting VS Code refreshes an installed MCP server; it does not install this patch. The user will perform interactive retesting after a later matching build/install. This acceptance grants no release or hardware qualification and does not cover the separate migration grammar/ABI/RAM/encoding/backend improvements.
