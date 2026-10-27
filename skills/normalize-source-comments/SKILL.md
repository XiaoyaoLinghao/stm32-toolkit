---
name: normalize-source-comments
description: Use when a Keil or legacy C/C++ project reports a source-encoding blocker, including a needed quoted header, and the user wants a reviewed, comment-only UTF-8 copy. Preview explicitly declared per-file charsets first, then copy only selected files to a new external directory; a complete prepared project tree is a separate explicit copy, not this helper's output. An explicit reviewed replacement mode can replace undecodable or disallowed comment units with a literal question mark; it records every loss and needs one confirmation per lossy file. Do not use for implicit transcoding, in-place edits, assembly, binaries, or a claim that migration is complete.
---

# Normalize source comments

Prepare a reviewed UTF-8 copy of selected C/C++ source and header files without
rewriting the original project. This is the supported explicit preparation
route for the Toolkit encoding blocker; it is not part of migration apply.

## Boundaries

- Require an explicit charset for every selected file: `utf-8`, `gb2312`,
  `gbk`, `gb18030`, or explicitly `cp1252`. Different files may use different
  charsets. Never guess, probe, or silently fall back. A successful decode does
  not prove that the decoded human text is intended.
- Convert non-ASCII characters only inside real C/C++ comments. Preserve actual
  ASCII lexical units, comment delimiters, all bytes outside comment content,
  CR/LF/CRLF sequences, final-newline state, and an existing UTF-8 BOM. A
  multibyte unit can contain an ASCII-valued trail byte (for example GB18030
  `A3 42`); preserve or replace the whole decoded unit, never split it by a raw
  ASCII test. Do not add a BOM or normalize line endings.
- Block a legacy file that contains non-ASCII bytes in code, strings,
  character literals, or preprocessing header names. Do not change runtime
  literal bytes to make a conversion appear to work.
- Block or reject rather than guess: invalid input bytes, unterminated
  constructs, C++ raw strings, trigraph `??/`, a backslash followed by
  horizontal whitespace before a newline, and a DBCS character whose bytes end
  in `0x5C` at a physical line end.
- Private-use, C1-control, replacement, and noncharacter code points block a
  legacy conversion. In an already-UTF-8 file the bytes are unchanged, so the
  same code points are review warnings instead; review the decoded text before
  accepting it.
- Strict decoding is the default and its behavior is unchanged. The single
  opt-in is `preview --replace-invalid-with '?'`. An explicit user request to
  replace undecodable comment bytes or existing private-use, C1-control, U+FFFD,
  and noncharacter code points with a literal `?`, together with the declared
  charset, authorizes this read-only preview; the preview itself classifies each
  unit and can block the file. Copy is allowed only for records the lexer
  actually proved to be comment content and that the user reviewed per file,
  including in a declared UTF-8 file. Each replacement is recorded with its
  source byte offset, length, original bytes, line, column, reason, and
  replacement value, and the plan ID binds the mode, the value, and those
  records. Valid ordinary comment text still converts normally.
- No other replacement value is accepted, and replacement never applies to
  code, strings, character literals, preprocessing header names, or any other
  non-comment byte. An error span that would consume ASCII or newline bytes is
  blocked instead of replaced as a unit; incomplete constructs, raw strings,
  trigraph `??/`/`??=`, the GCC continuation form, DBCS/backslash ambiguity,
  bounds, and a trigraph created by the replacement itself also stay blockers.
- Assembly, UTF-16/UTF-32, binaries, and arbitrary text formats are outside
  this helper. Leave them untouched and report the diagnostic.
- The helper is not a C compiler. It does not promise generic charset support,
  runtime string/ABI equivalence, or that a project builds after conversion. Its
  output is a selected-file set, never a complete project; building the complete
  prepared tree is a separate explicit copy described below.

## Run the helper

Run the self-contained standard-library helper from the absolute directory that
contains the loaded `SKILL.md`, not from the current working directory. Set both
paths explicitly once and check that the helper is present:

```powershell
# The absolute directory holding the loaded SKILL.md, exactly as loaded:
#   repository checkout:  <repo>/skills/normalize-source-comments
#   personal install:     <personal-skills-dir>/normalize-source-comments
# Do not substitute a global path when this skill was loaded from a repository.
$SkillDir = '<absolute-path-of-the-loaded-skill-directory>'
$Normalizer = Join-Path $SkillDir 'scripts/normalize_comments.py'
Test-Path $Normalizer
```

Use a verified CPython 3.12 interpreter. Do not invent an MCP normalization tool,
and do not call `pyocd`, a compiler, or a migration apply to perform the copy. A
client that cannot load this file (for example an MCP-only client) must read the
same instructions in the skill directory — this `SKILL.md` and
`references/lexical-and-plan-contract.md` — and invoke the helper directly
rather than expecting a normalization tool from the Toolkit.

### 1. Preview read-only

Choose project-root-relative files and declare one charset per file. Use a new
directory outside the project for the preview:

```powershell
python $Normalizer preview --project-root 'C:\work\robot' --preview-dir 'D:\review\robot-comments-1' --file 'App/main.c=gbk' --file 'App/util.h=gb2312' --file 'App/notes.cpp=cp1252'
```

`preview` reads the project but writes only `plan.json` and `preview.md` under
the external preview directory. It returns JSON with a canonical `planId` and
per-file `status`, `blockers`, and `warnings`. Exit code `0` means every file
is ready. Exit code `2` means either the preview completed with at least one
blocked file (`status: blocked`) or the run failed operationally
(`status: failed`, for example an invalid selection, a preview collision, or an
I/O error). Read `status` and `code` in the JSON before deciding what happened.

#### Explicit reviewed replacement preview

Run the strict preview when it can classify the selection. When the user
explicitly asks to replace undecodable comment bytes, or a private-use/C1-
control/U+FFFD/noncharacter code point in a comment, with a literal `?`, the
explicit intent plus the declared charset authorizes previewing the same
selection read-only with the one supported value. A strict `DECODE_ERROR` does
not by itself classify those bytes; this preview does:

```powershell
python $Normalizer preview --project-root 'C:\work\robot' --preview-dir 'D:\review\robot-comments-1-replace' --file 'App/main.c=gbk' --replace-invalid-with '?'
```

The JSON adds `mode` (`strict` or `replace`), `replacementValue`, `lossyFiles`,
and `totalReplacementCount`; each file adds `lossy`, `replacementCount`, and
its `replacementRecords`. Any value other than `?` fails with
`REPLACEMENT_VALUE_UNSUPPORTED` before a preview directory is created. A file
that ends `blocked` is not copyable even in replacement mode. No automatic
bulk confirmation exists, and the preview never authorizes editing originals.

### 2. Review the plan

Read `preview.md` and `plan.json` before copying:

- `status: blocked` or any blocker finding: do not copy. Resolve the reported
  path, byte offset, line, and reason. A decode failure or a corrupt byte is not
  repaired automatically.
- Warnings such as a DBCS pair with an ASCII trail or a private-use/control
  code point require a human decision about the intended text. Choosing another
  charset is explicit; never infer it from a successful decode. In replacement
  mode the four replaceable code-point classes become review records instead of
  classification warnings, but mixed-single-byte, unassigned, and non-comment
  review evidence is still reported.
- For a replacement plan, read `mode`, `replacementValue`, every
  `replacementRecords` entry (path, byte offset and length, original hex,
  line/column, reason, replacement), and every file's `lossy` and
  `replacementCount`. Verify that each recorded range is comment content whose
  literal loss you intend to accept. `REPLACEMENT_APPLIED` is an informational
  count, never approval; `REPLACEMENT_TRIGRAPH_HAZARD`,
  `REPLACEMENT_BOUND_EXCEEDED`, `INVALID_SPAN_ASCII_UNSUPPORTED`, and
  `NON_COMMENT_NON_ASCII` are blockers. A strict diagnostic may name the
  explicit replacement preview only for a proven comment unit; it never asserts
  eligibility for bytes the lexer has not classified.
- Check `sourceSha256`, `outputSha256`, `outsideCommentSha256`, newline/BOM
  evidence, the human-readable byte diff, and that the plan contains only the
  files you selected.
- A preview, plan field, warning, or replacement record is not authorization to
  modify originals.
- If a human choice is missing — the charset for a file, or acceptance of a
  recorded loss — build the concrete per-file preview first and show its
  findings, byte offsets, and byte diff before asking. Never ask the user to
  accept an unreviewed loss, confirm on their behalf, or treat a prior copy
  authorization as review of a loss.

### 3. Copy reviewed files

Copy only after reviewing the exact `planId`. The output directory must not
exist and must be outside the source root:

```powershell
python $Normalizer copy --project-root 'C:\work\robot' --plan 'D:\review\robot-comments-1\plan.json' --plan-id '<exact 64-character planId>' --output-dir 'D:\review\robot-comments-1-copy'
```

Run `copy` only when the user's request already authorizes producing reviewed
converted copies. Reuse that existing authorization; do not introduce a
mandatory extra approval stop for a copy the user already authorized, and do
not ask again merely because the plan is ready. A preview, plan fields, or a
`planId` on its own never authorizes the copy or any edit to the originals, and
the helper has no `authorized` flag. Always pass the exact `planId` you
reviewed, never one you did not review.

For a replacement plan, pass exactly one `--confirm-file '<relative path>'` for
each lossy file whose recorded loss you reviewed and accept, using that plan's
canonical project-relative paths. These confirmations must reflect the reviewed
per-file choices; never manufacture them by looping over `lossyFiles`, editing
the plan, or confirming on the user's behalf. If any lossy file is declined,
re-preview the narrowed selection rather than copying unapproved files:

```powershell
python $Normalizer copy --project-root 'C:\work\robot' --plan 'D:\review\robot-comments-1-replace\plan.json' --plan-id '<exact 64-character planId>' --output-dir 'D:\review\robot-comments-1-replace-copy' --confirm-file 'App/main.c'
```

Missing (`CONFIRMATION_REQUIRED`), duplicate (`CONFIRMATION_DUPLICATE`),
unknown (`CONFIRMATION_UNKNOWN`), non-lossy (`CONFIRMATION_NOT_LOSSY`), or
invalid (`CONFIRMATION_INVALID`) confirmations fail before the output directory
is created. Strict plans require no confirmation and reject any supplied one.
Confirmation is per-file review evidence tied to the exact plan ID, never bulk
approval, and it never authorizes editing originals. `copy` re-reads and
re-derives every input and every replacement, so a changed source
(`INPUT_CHANGED`), a tampered plan (`PLAN_TAMPERED`), a wrong plan ID
(`PLAN_ID_MISMATCH`), or an older incompatible plan (`PLAN_UNSUPPORTED`, with
re-preview guidance) is refused.

`copy` re-reads every input, re-derives the conversion, verifies the plan ID
and hashes, refuses changed inputs or tampered plans, and writes only the
selected relative files. It never overwrites existing output or originals.
The result includes `manifest.json`, which records output hashes, the plan
`mode` and `replacementValue`, `confirmedFiles`, `lossyFiles`, per-file loss
counts, `originalsUnchanged: true`, and `outputsVerified: true`. It never claims
migration completion. On failure, an owned incomplete staging directory is
marked by `INCOMPLETE.json` and has no final manifest.

The output is a set of converted file copies, not a complete migrated or
buildable project.

### 4. Build and inspect the complete prepared project copy

The helper output is a partial file set, never the project. If the project owner
chooses to prepare a separate project copy, do that as a separate explicit
action outside the original root:

1. Inventory the original tree as portable relative path plus SHA-256 per file,
   omitting `.git` VCS metadata (the directory or a worktree pointer file) from
   both inventory and copy. Refuse symlink, junction or other reparse redirects,
   absolute or escaping paths, case-insensitive duplicate paths, unreadable
   entries and special files. Do not silently skip any other unknown entry.
2. Copy the whole project apart from that omitted `.git` metadata, including
   every unselected source, header, startup or assembly file, resource, license
   and directory needed by the project. Byte-copy files that are not being
   converted: every other prepared file is byte-identical to the original, and
   the original stays unmodified.
3. Overlay only reviewed converted copies whose reviewed `sourceSha256` still
   matches the current original file and whose `outputSha256` matches the helper
   `manifest.json`. On any mismatch, re-preview; never force an overlay, edit the
   plan, or invent a hash.
4. Recompute the prepared inventory and rerun the ordinary read-only migration
   sequence from the prepared root:

```text
stm32_project_context()
stm32_keil_inspect(uvprojx='<same relative .uvprojx>', targetName='<exact target>')
stm32_keil_preflight(uvprojx='<same relative .uvprojx>', targetName='<exact target>')
```

Bind the prepared root explicitly as the workspace and MCP project root. Keep
the same relative `.uvprojx` and exact target. Results from the original project
do not carry over; report every remaining blocker and address it before a
conversion plan is requested. After the reviewed migration apply, bind the
returned `data.outputRoot` for the normal configure/build/flash route. An
existing migration authorization can cover this reversible preparation; each
explicit charset choice, accepted lossy replacement and behavior decision still
needs real user intent, never an inferred approval.

Do not run migration apply, a build, a flash, or `git init`/commit/stash/clean
from this skill. Preparation is reversible and needs no Git repository. Startup,
scoped compiler options, scatter/memory and unsupported-assembly blockers remain
independent of encoding. Replacing the original project in place is a separate
explicit user decision.

## Reference

Read [references/lexical-and-plan-contract.md](references/lexical-and-plan-contract.md)
for the exact plan fields, hash definitions, lexical states, finding codes,
limits, copy invariants, and retained limitations.
