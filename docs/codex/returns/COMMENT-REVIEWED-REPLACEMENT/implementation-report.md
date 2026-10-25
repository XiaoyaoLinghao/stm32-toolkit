# COMMENT-REVIEWED-REPLACEMENT implementation report

Implementer: Claude Code CLI, using the user's unchanged provider/model
configuration (reported by the CLI as `deepseek-v4.1-flash[1m]`). Reviewer and
acceptance owner: the primary conversation agent. This report is not
self-acceptance and contains no acceptance verdict.

## Identity and ledger

- Module/phase: COMMENT-REVIEWED-REPLACEMENT, explicit reviewed replacement of
  abnormal bytes in external comment-only copies.
- Accepted base: `3cd5eea7ccfa6599782400b8009496424ec99802`.
- Specification/plan head: `1efceb0d` (short SHA as supplied in the verified
  ledger).
- Product implementation: `df46c9a6fb22081522b73ce0203ebd57347efe57`.
- Final tests/guidance correction and pre-report CodeHead:
  `045bea3574dece7ea5740d6eaa76a3a731150cc0`.
- Branch: `codex/comment-reviewed-replacement`, clean at the pre-report
  CodeHead. The report commit and any report-stage edits will be recorded only
  by local Git; this report deliberately contains no final/report commit SHA
  and no moving commit totals.
- Authorized remote action: none performed. No push, PR mutation, merge, tag,
  remote deletion, release, packaging, runtime/global-skill installation,
  original-project build, flash, or hardware operation was performed. The
  existing synthetic GNU object test did execute offline compilation.
- The original firmware project was not modified, converted, copied, built, or
  touched. All tests used synthetic temporary projects under the run-owned
  external root `D:/codex-tmp/nr25`.

## Process

- The initial file-only author invocation reached the 65-turn limit. Its work
  was preserved and resumed. No shell command was denied and no permission
  bypass, global permission change, provider change, or shell switch occurred
  in this task.
- Native PowerShell registration was selected only for the implementation
  process, then verified with the no-action inventory and an actual harmless
  `Get-Location` before verification work. Editing and test execution were
  kept as separate invocations.
- The author's first native pytest tool result explicitly reported pytest exit
  `1` (the test-expectation failure below). Later passing author tool results
  do not print a process exit code; no exit code is inferred from the CLI's own
  exit `0`. The primary's final execution file separately records process exit
  `0`.

## Delivered files

New:

- `tools/stm32-toolkit/tests/test_normalize_comment_replacements.py` (31
  collected replacement cases, including the seam and PUA line-end regressions)
- `docs/codex/returns/COMMENT-REVIEWED-REPLACEMENT/implementation-report.md`

Modified:

- `skills/normalize-source-comments/scripts/normalize_comments.py`
- `skills/normalize-source-comments/SKILL.md`
- `skills/normalize-source-comments/references/lexical-and-plan-contract.md`
- `skills/migrate-keil/SKILL.md`
- `tools/stm32-toolkit/tests/test_normalize_source_comments.py` (canonical
  plan-field expectations only; collected count remains 39)
- `docs/user-guide.md` (replacement routing, confirmation semantics and the
  report-stage trigraph wording clarification described below)

No product path outside the approved plan was changed. Helper version is
`1.1.0`, plan schema is `2`, and manifest schema is `2`. Toolkit, Monitor,
plugin and release package version remains `1.3.0`; no version bump, package,
installation, frozen-asset, global-skill or hardware action was taken.

## Public behavior

### Strict default and explicit opt-in

- Omitted `--replace-invalid-with` preserves the historical strict behavior
  exactly: undecodable bytes, private-use, C1-control, U+FFFD and noncharacter
  code points block a legacy conversion; there is no guessing, probing,
  implicit charset, `errors=ignore` or whole-file replacement.
- `preview --replace-invalid-with '?'` is the sole opt-in. `?` is the only
  accepted value; any other value fails `REPLACEMENT_VALUE_UNSUPPORTED` before
  a preview directory is created.
- The preview mode (`strict`/`replace`), replacement value, source/output
  hashes and replacement records are bound into `planId`. The same selection
  without the flag remains strict.

### Opaque recovery and disallowed code points

- Replacement-mode decode recovery is bounded and windowed. An undecodable
  non-ASCII span is represented internally by an opaque sentinel that is
  non-ASCII and never a delimiter, letter, quote or whitespace, so the lexer
  cannot mistake it for syntax.
- Only a span proven to be comment content may be replaced. A span that would
  consume ASCII syntax or newline bytes is blocked
  (`INVALID_SPAN_ASCII_UNSUPPORTED`); invalid bytes in code, strings,
  character literals or header names remain non-comment blockers; recovery
  work beyond the bounded limit blocks (`RECOVERY_BOUND_EXCEEDED`).
- The four disallowed code-point classes are replaceable only when proven to be
  comment content, with reasons `private-use-code-point`,
  `c1-control-code-point`, `replacement-code-point` (U+FFFD) and
  `noncharacter-code-point`. Valid ordinary comment text still converts to
  UTF-8 normally. The same classes in non-comment content or on a strict plan
  keep their previous blocking/warning behavior.

### Preservation and lexical guards

- All bytes outside the selected comment units are preserved, including ASCII
  punctuation and delimiters, comment delimiters, CR/LF/CRLF sequences, final
  newline state and an existing UTF-8 BOM. No BOM is added. Valid decoded
  comment text not selected for lossy replacement is retained through ordinary
  UTF-8 normalization; its original legacy encoding bytes can therefore change.
- Multibyte units are handled as whole decoded units, never split by a raw
  ASCII test (for example GB18030 `A3 42` and the valid PUA unit `A1 5C`).
  A DBCS unit ending in `0x5C` at a physical line end stays blocked; the same
  unit mid-line is replaceable. Raw strings, the GCC
  backslash-horizontal-whitespace continuation, incomplete constructs and
  unsupported include forms remain blockers.
- Derived output is re-validated for UTF-8 validity, outside-comment digest
  stability and idempotence. Existing source trigraph `??/` and `??=` remain
  blockers; other existing trigraph sequences remain review warnings. A
  replacement that would form `??/` or `??=` is blocked as
  `REPLACEMENT_TRIGRAPH_HAZARD`.

### Loss records and bounds

- Each replacement record contains the project-relative path, absolute source
  byte offset and length, original hex bytes, line and column, reason and the
  replacement value. Records are strictly increasing by byte offset.
- Per-file output adds `lossy`, `replacementCount` and
  `replacementRecords`; the top level adds `mode`, `replacementValue`,
  `lossyFiles` and `totalReplacementCount`.
- Records are capped at `MAX_REPLACEMENT_RECORDS = 512`. Exceeding the cap
  blocks with `REPLACEMENT_BOUND_EXCEEDED` instead of silently omitting
  approval-relevant losses. Recovery work is separately bounded
  (`MAX_INVALID_SPANS = 1024`, 64 KiB recovery feed), and the existing decoded
  character, per-file output and aggregate output bounds remain in force.

### Exact-plan copy and confirmation

- For a replacement plan, `copy` requires one repeatable
  `--confirm-file '<relative path>'` for every file with actual lossy
  replacements, tied to the exact reviewed `planId`.
- Missing, duplicate, unknown, non-lossy or invalid confirmations are rejected
  before the output directory is created (`CONFIRMATION_REQUIRED`,
  `CONFIRMATION_DUPLICATE`, `CONFIRMATION_UNKNOWN`,
  `CONFIRMATION_NOT_LOSSY`, `CONFIRMATION_INVALID`). Strict plans require no
  confirmation and reject any supplied one.
- The helper never manufactures confirmations by iterating `lossyFiles`. If a
  lossy file is declined, the reviewed selection is narrowed and re-previewed;
  the plan is not edited and unapproved files are not copied.
- `copy` re-reads and re-derives every input and replacement using the plan's
  own mode and value. It refuses changed source (`INPUT_CHANGED`), a tampered
  plan (`PLAN_TAMPERED`), a wrong ID (`PLAN_ID_MISMATCH`) and an older
  incompatible plan (`PLAN_UNSUPPORTED`, with actionable re-preview guidance).
- Existing exclusive external-output containment, readback verification,
  durable `INCOMPLETE.json` marker and staging behavior are preserved.
  `manifest.json` schema 2 records mode, replacement value, confirmed files,
  lossy files, per-file counts, original/output hashes,
  `originalsUnchanged: true` and `outputsVerified: true`; it never claims
  migration completion. Originals are never written in either mode.

## Review corrections before the pre-report CodeHead

- **Early allocation bound.** The decoded-character limit is enforced before
  per-unit mapping allocation, and cumulative/windowed recovery enforces the
  same limit across recovery feeds. Covered by
  `test_decoded_limit_blocks_before_per_unit_mapping_allocation`,
  `test_recovered_windows_enforce_cumulative_decoded_limit` and
  `test_recovered_carry_boundary_enforces_decoded_limit`.
- **Valid PUA `A1 5C` at a physical line end.** A valid GB18030 private-use
  unit ending in `0x5C` at a line end remains blocked; the same unit mid-line
  is replaceable. Parametrized tests cover LF, CRLF, block-comment and
  end-of-file forms, plus the mid-line case.
- **First frozen-run outcome.** At `df46c9a6`, the author and the primary each
  independently obtained 80 collected tests: 78 passed, 1 failed, 1 skipped.
  The failure was a test expectation/readback that omitted the literal space
  byte after `FF`, producing an output-hash mismatch; correcting that
  expectation did not change product behavior. The skip was a speculative GBK
  ASCII-span search that this CPython did not produce; it was replaced by a
  real GB18030 EOF `81 30` ASCII-consuming-span case, and the ASCII-span guard
  now runs end-to-end. Two recovery-seam tests were added
  (`test_recovery_window_carries_complete_multibyte_sequence`,
  `test_recovery_window_classifies_invalid_sequence_spanning_seam`). The final
  suite has no skip.
- **Guidance circular precondition.** Guidance now states that an explicit
  user request to replace the named comment units with `?`, together with the
  declared charset, authorizes the read-only replacement preview even when a
  strict `DECODE_ERROR` has not classified those bytes. It does not authorize
  copy: only lexically proven comment records and reviewed per-file choices
  admit a copy. The guidance forbids auto-confirming by looping
  `lossyFiles`, forbids in-place source edits, invents no MCP normalization
  tool, and states that restarting VS Code does not install this source patch.

## Evidence

Author commands ran in the author worktree against product bytes frozen as
`df46c9a6` for the first run and `045bea35` for the final run, with the
verified venv Python, external run-owned basetemp/cache roots, and no network
or installation. No author test rerun is claimed for the report-stage
documentation-only changes. The primary independently repeated the
applicable suite at the exact clean heads. Raw evidence root:
`D:/codex-tmp/nr25`; the primary will add `review.md` and `evidence.json`.

| Owner / source state | Check | Result |
| --- | --- | --- |
| Primary / accepted base `3cd5eea7` | Existing helper suite, `baseline.xml` | 39 tests, 0 failed, 0 skipped. |
| Author / product `df46c9a6` | First frozen targeted suite (existing helper + new replacement + AI guidance), `first.xml` | 80 collected; 78 passed, 1 failed, 1 skipped. Failure: `test_replacement_preview_is_read_only_and_keeps_mixed_valid_text` output-hash expectation omitted the literal space after `FF`. Skip: `test_interpreter_ascii_consuming_span_is_blocked_end_to_end` (platform-only speculative GBK ASCII-span search). Evidence retained, not counted as a pass. |
| Primary / same `df46c9a6` | Independent repeat of the same first frozen suite, `first-review.xml` | 80 collected; 78 passed, 1 failed, 1 skipped — same failure and skip. Preserved outcome. |
| Author / final CodeHead `045bea35` | Same targeted suite via actual native PowerShell, `test-final.jsonl`, `final.xml` | 82 collected; 82 passed, 0 failed, 0 skipped (39 existing helper + 31 replacement + 12 AI guidance). The first native pytest tool result explicitly reported exit `1`; later passing tool results do not print an exit code and none is inferred. |
| Primary / final CodeHead `045bea35` (clean review worktree) | `D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_normalize_source_comments.py tools/stm32-toolkit/tests/test_normalize_comment_replacements.py tools/stm32-toolkit/tests/test_ai_call_guidance.py -q --tb=short` with run-owned basetemp/cache and `--junitxml=D:\codex-tmp\nr25\final-review.xml`; `final-review.log`, `final-review-execution.json` | 82 passed, 0 failed, 0 skipped; recorded process exit code `0`; execution JSON records head `045bea35`. |
| Author / final CodeHead `045bea35` | Bundled skill validation through actual native PowerShell, `skills.jsonl` | `Skill is valid!` for `normalize-source-comments` and `Skill is valid!` for `migrate-keil`. |
| Primary / final CodeHead `045bea35` | Same bundled skill validation | Passed for both skills. The primary's first ad-hoc attempts lacked the YAML/UTF-8 environment; it then used the bundled Python with `-X utf8` and passed. No installation or file fix was needed. `test_skill_frontmatter_and_bundled_quick_validate` also validates the normalize skill. |

The skill validator is structural evidence only. Target hardware, original
firmware, a full release matrix and ARMCC/ABI equivalence were not exercised
and are not claimed.

## Report-stage wording clarification

After the tested CodeHead and before this report commit, two documentation-only
precision edits were made in `docs/user-guide.md`. Both new replacement
statements had said that trigraphs block generally. The helper and reference
make only `??/` and `??=` blockers; other trigraph sequences are review
warnings. The two statements were therefore qualified with exactly those two
sequences:

- The preflight remediation paragraph now says that existing or
  replacement-produced `??/` and `??=` trigraphs still block, while other
  trigraph sequences are review warnings.
- The encoding FAQ entry now says replacement mode still blocks existing
  `??/`/`??=` and replacement-produced `??/`/`??=` trigraphs, while other
  trigraph sequences are review warnings.

No other guide content changed. No helper, test or product behavior changed;
no test rerun is claimed for these wording edits. The tested CodeHead remains
`045bea3574dece7ea5740d6eaa76a3a731150cc0`.

## Retained limitations

Primary evidence reconciliation clarified the synthetic compilation scope,
normal UTF-8 conversion of valid comment text, and report-stage test boundary
above; the original author return remains in the retained CLI log.

- This is a bounded offline software slice, not release acceptance, a full
  release matrix, ARMCC/source-character validation, runtime string/ABI
  equivalence, original-project migration, build, flash or hardware
  acceptance.
- The helper is not a C compiler or preprocessor. Macro-expanded includes,
  conditional compilation, raw strings, unsupported continuations, ambiguous
  DBCS/backslash forms, incomplete constructs and unsupported include forms
  remain blocker/rejection cases rather than being guessed.
- Replacement `?` is a reviewed, recorded content loss, not a repair, an
  encoding conclusion or proof that a project builds. Byte-level fidelity of
  any project copy remains the project owner's responsibility.
- The author did not preview, convert, copy, build or migrate the original
  firmware project. All evidence is synthetic and temporary.
- Global skill installation, frozen runtime/package update, release publication
  and delivery-branch integration are separately owned actions and were not
  performed. Future delivery is targeted at v1.3.1 only after the remaining
  backlog is complete; product version remains 1.3.0 in this slice.
- No self-acceptance. The primary owns the independent complete-diff review,
  applicable focused verification and the final verdict.
