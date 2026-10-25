# COMMENT-REVIEWED-REPLACEMENT independent review

Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline source slice.

Accepted base `3cd5eea7ccfa6599782400b8009496424ec99802`; tested CodeHead `045bea3574dece7ea5740d6eaa76a3a731150cc0`. Primary owns specification, orchestration, complete accepted-base diff review and acceptance. Local Claude Code CLI with the user's configured `deepseek-v4.1-flash[1m]` owns implementation, tests and product guidance. Author branch `codex/comment-reviewed-replacement`; no remote action or ownership override. Review used the clean detached `build-snapshot-final/STM32-Toolkit` worktree at the exact CodeHead. See [design](../../../superpowers/specs/2026-10-25-comment-reviewed-replacement-design.md), [plan](../../../superpowers/plans/2026-10-25-comment-reviewed-replacement-plan.md), [implementation report](implementation-report.md) and [machine evidence](evidence.json).

## Accepted behavior

The standalone helper adds explicit `preview --replace-invalid-with '?'` and repeatable `copy --confirm-file REL`. Omission preserves strict conversion behavior. Charset is still declared per file. Invalid non-ASCII spans remain opaque until lexical classification; only proven comment content can be replaced. Private-use, C1-control, U+FFFD and noncharacter comment units are also eligible. Every loss binds its original byte range/hex/location/reason and replacement into the exact reviewed plan ID. The output still converts other valid comment text to UTF-8 and preserves actual ASCII units, delimiters, newline/BOM state and all non-comment bytes. ASCII-valued trail bytes inside a multibyte character belong to that decoded unit.

Copy requires exactly the reviewed lossy files, rejects missing/duplicate/unknown/non-lossy confirmations before creating output, re-reads and re-derives every input/record, and retains existing containment/reparse/exclusive output/incomplete-marker/readback/original-hash protections. Confirmation is not inferred from `lossyFiles`. A declined file requires a narrowed new preview. Defaults, original files, hardware and firmware workflows are not broadened.

Unclassified strict decode errors may lead to an explicitly requested read-only replacement preview, which can still block; they do not establish comment-only eligibility. Strings, character literals, header names, incomplete constructs, DBCS line-end ambiguity, dangerous `??/`/`??=` trigraphs, recovery/loss limits and stale/tampered plans remain protected. Helper version1.1.0 and plan/manifest schema2 make incompatible old plans fail with re-preview guidance. Toolkit version stays1.3.0.

## Findings and corrections

| Finding | Correction and evidence |
| --- | --- |
| Early draft decoder allocated unit maps before enforcing the decoded-character limit. | Check before each decoded segment and opaque unit is appended, including carried windows. New allocation/cumulative/carry regression checks pass. |
| Early replacement branch skipped the existing DBCS line-end check for valid private-use GB18030 pairs. | Suppress only the replaceable code-point classifications while retaining other lexical checks. A1 5C/U+E4E2 at LF/CRLF/block/EOF stays blocked, with no copy output; mid-line positive control passes. |
| Initial new expected output omitted a literal space after FF. | Correct the test expectation and verify exact external copy bytes/original preservation; product behavior was already correct. Original failure is retained. |
| Initial ASCII-error-span end-to-end test searched GBK and skipped. | Deterministic GB18030 EOF81 30 proves ASCII-containing error rejection; valid/invalid recovery seams additionally pass. The old skip is not carried as a final deferral. |
| Chinese guidance required lexical proof before the preview that establishes it; inventory text referred to the old eight-skill state. | Separate explicit preview intent from proven records required at copy; forbid manufactured confirmations, handle declined files by re-preview, distinguish current source/nine skills from old installed helper, and clarify ASCII trail bytes. |

No blocking findings remain for this slice. The report-stage user-guide clarification names only the two dangerous trigraphs; it is documentation only after tested CodeHead, with unchanged helper/tests and no new runtime claims.

## Verification

Windows CPython3.12.14, run-owned `D:/codex-tmp/nr25` temporary/cache/evidence roots, same-worktree Toolkit/Monitor sources. Dependencies were read-only. Tests used synthetic projects only; the existing GNU object check is offline compiler evidence, not original firmware or ARMCC equivalence.

| Owner / source | Result |
| --- | --- |
| Primary / accepted base |39 existing helper tests pass,0fail,0skip. |
| Claude and primary independently / df46c9a6 |Each78pass,1fail,1skip out of80; retained. |
| Claude and primary independently / final CodeHead |Each82pass,0fail,0skip:39 existing helper,31 new replacement,12 AI-call-guidance. |
| Claude and primary / final CodeHead |Both affected skills structurally valid. Primary ad-hoc validator calls first lacked dependency/UTF-8 environment; bundled Python `-X utf8` passed without code/install changes. |

Native `tool_use`/`tool_result` and JUnit establish author execution. First author pytest explicitly returned exit1; final native output did not print an exit code, so CLI exit0 is not substituted for it. Primary final subprocess exit0 is recorded. No extra platform deferral is introduced. This is the applicable slice suite, not a full repository or release matrix. Original failures and the65-turn CLI continuation are retained in raw evidence. No denied shell operation or bypass occurred; file editing and exact native verification were separate invocations.

## Delivery boundary

A fresh, read-only Claude CLI session forward-tested the skill instructions against three hypothetical VS Code cases (`skill-audit.jsonl`): an unclassified decode failure with explicit replacement intent, accepting one lossy file while declining another, and an old installed helper. It chose preview/classification before copy, a narrowed new plan rather than manufactured confirmations, and recognized that restart does not install a helper. Primary adjudication: current-source versus installed availability is a documented distinction, not an unresolved contradiction. A matching repository skill/helper may be explicitly loaded without installation; do not silently substitute it under a loaded global skill. The auditor's exact error-code claim for an old helper is not adopted: old implementations may reject new plans at shape validation first. These are instruction simulations, not actual IDE/installation or hardware evidence, and the auditor has no acceptance authority.

No original `D:/WorkSpace/mobile-robot-controller` access or modification, hardware operation, installed runtime/global skill update, package rebuild, remote push/PR/tag/merge or publication occurred. Frozen/installed1.3.0 lacks this new helper behavior; restarting VS Code does not install it. Future integration target is **v1.3.1 after the remaining agreed improvements**, not a version bump or release in this slice. Existing release/hardware acceptance obligations remain outstanding.
