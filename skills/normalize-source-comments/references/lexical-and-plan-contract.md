# Lexical and plan contract

This reference records the deterministic behavior of
`scripts/normalize_comments.py`. `SKILL.md` is the workflow entrypoint; read this
file when inspecting a plan, diagnosing a blocker, or reviewing the helper.

## Supported inputs

- Explicit project-root-relative C/C++ source or header files with one of these
  suffixes: `.c`, `.h`, `.cc`, `.cpp`, `.cxx`, `.hpp`, `.hh`, `.hxx`, `.inl`.
- One explicit charset per file: `utf-8`, `gb2312`, `gbk`, `gb18030`, or
  `cp1252`. There is no detection, recommendation, fallback, or automatic
  switch. A file may contain different declared charsets from another file.
- Selection is explicit; the helper never recursively scans a project.
- Assembly, UTF-16/UTF-32, binaries, arbitrary text formats, symbolic links,
  junctions, and reparse components are rejected or blocked. The original
  project is never written.

## Decode and source mapping

The helper first decodes with the declared codec, then proves the exact byte
round-trip for every decoded unit. It builds a per-character byte mapping and
enforces a conservative decoded-character limit before those mappings are
allocated, including across recovered windows and carried partial sequences.
`errors=ignore` and blind whole-file replacement are never used.

In the default strict mode a decode failure reports the path, byte offset,
line, column, and invalid byte, and blocks the file. In the explicit
`--replace-invalid-with '?'` mode the helper decodes in a bounded, windowed
recovery pass: each undecodable byte span becomes one **opaque unit** with its
exact physical byte range, and the lexer decides whether that unit is comment
content. An error span whose bytes include any ASCII or newline byte is blocked
(`INVALID_SPAN_ASCII_UNSUPPORTED`) and never replaced as a unit, because the
single replacement byte could consume source syntax or a line break. Recovery
is bounded by `MAX_INVALID_SPANS`; exceeding it is a blocker, not a truncated
recovery. A recovered file's whole-file strict round-trip is not claimed
(`decodeMode: recovery`, `decodeRoundTrip: false`), while `unitRoundTrip` still
records that every decoded unit reproduced its source bytes.

An existing UTF-8 BOM is preserved for `utf-8`; no BOM is added or removed. A
UTF-8 BOM combined with a declared legacy charset is a blocker. The source
character limit, per-file byte limit, aggregate source limit, per-file output
limit, and aggregate output limit are recorded in the plan's `limits` object.
Exceeding a limit is a blocker or a bounded failure, never a silent truncation.

## Lexical model

The helper does not claim to be a C compiler. It builds a phase-2 logical view
that removes backslash-newline continuations while retaining a mapping to the
original physical characters. It then recognizes comments conservatively:

- Normal quoted strings, character literals, escapes, `//`, `/* */`, and
  preprocessor lines are distinguished from comment-looking literal content.
- A backslash followed by horizontal whitespace before a physical newline is a
  GCC extension. The helper blocks it rather than risk misclassifying the next
  line.
- A non-ASCII character whose source bytes end in `0x5C` at a physical line end
  is blocked because a raw-byte lexer and a decoded lexer can disagree.
- C++ raw strings are rejected explicitly. Unterminated comments, strings,
  character literals, and preprocessing header names are blockers.
- Trigraph `??/` and `??=` are blockers. Other trigraph sequences are reported
  as review warnings and are not translated.
- An opaque recovery unit is never a delimiter, letter, quote, or whitespace; it
  can only be comment content. Any opaque unit outside comment content —
  including in a string, character literal, or preprocessing header name — is a
  blocking `NON_COMMENT_NON_ASCII`. The DBCS trail-`0x5C` ambiguity is checked
  for an opaque span and for every valid non-ASCII comment character, including
  one selected for replacement, so a private-use pair such as GB18030 `A1 5C`
  at a physical line end stays blocked in both modes.
- The scanner tracks blocking status and blocker count independently of the
  presentation finding cap. If a blocker is omitted from the displayed list,
  a blocking `FINDINGS_TRUNCATED` diagnostic is emitted, so a file can never
  become ready merely because earlier warnings filled the list.
- Each lexing pass presents at most `MAX_FINDINGS` findings. The final list is
  bounded once more at `MAX_PRESENTED_FINDINGS` (`MAX_FINDINGS * 2 + 8`), a
  conservative bounded allowance shared by derivation and plan validation; some
  of the contributing error branches cannot occur together, so this is an upper
  bound rather than a tight count. Because validation enforces the same
  allowance, a ready preview is always copyable. When findings must be omitted,
  blockers are kept ahead of warnings: suppressing only warnings yields a
  warning `FINDINGS_TRUNCATED` marker, while omitting blocking findings yields a
  blocker `FINDINGS_TRUNCATED` marker. The bound therefore never turns a blocked
  file into a ready one.

### Preprocessing and header names

A preprocessing header-name token is consumed without comment recognition, so
comment-looking bytes inside it are never converted. The helper recognizes:

- `#include`, `#include_next`, `#import`, and `#embed` with optional comments
  and whitespace between `#`, the directive name, and the header name.
- Digraph `%:` in place of `#`.
- `__has_include`, `__has_include_next`, `__has_embed`, and
  `__has_embed_next` with a direct header-name operand.
- C++ header-unit forms `import <header>;`, `import "header";`, and
  `export import <header>;`.

Trigraph `??=` is blocked instead of translated. A direct header name may not
contain a physical newline. A directive whose operand is a macro is left in
ordinary token scanning; if the macro form is unsupported or ambiguous, the
normal lexical rules and non-ASCII blocker still apply. This is intentionally
not a full preprocessor.

Comments between preprocessing tokens are still real comments: their content
is marked for conversion and counted, while a header-name token is never
comment content. A `//` inside `<...>` or `"..."` is therefore not a line
comment.

## Conversion and verification

Only non-ASCII characters inside comment content are rewritten. Normally they
become their UTF-8 encoding. In the explicit replacement mode a comment unit
selected for replacement becomes one ASCII `?` instead:

- an opaque undecodable span (reason `invalid-byte-unit`), or
- an existing private-use (`private-use-code-point`), C1-control
  (`c1-control-code-point`), U+FFFD (`replacement-code-point`), or
  noncharacter (`noncharacter-code-point`) code point.

Unassigned code points and `MIXED_SINGLE_BYTE_ARTIFACT` stay review warnings
even when the same unit is selected for replacement. ASCII bytes, comment
delimiters, all bytes outside comment content, CR/LF/CRLF sequences,
final-newline state, and an existing UTF-8 BOM are preserved. The derived output
must decode as strict UTF-8 and must pass these checks:

- The outside-comment byte digest is unchanged.
- Re-deriving the output as `utf-8` is a no-op (idempotence).
- The per-file and aggregate output bounds hold.
- Every source file's bytes still match the reviewed plan at copy time.
- In replacement mode the derived output contains no `??/` or `??=` sequence.
  The source scan already rejects those, so any occurrence was created by the
  replacement; it is a blocking `REPLACEMENT_TRIGRAPH_HAZARD`.
- The number of recorded replacements does not exceed
  `MAX_REPLACEMENT_RECORDS`; otherwise `REPLACEMENT_BOUND_EXCEEDED` blocks
  rather than omitting approval-relevant losses.

The outside-comment digest is SHA-256 over the preserved byte segments. It is
computed from a count of segments, each segment's 8-byte big-endian length, and
the segment bytes, with a BOM segment included when present. Cache this
definition; do not substitute a plain hash of the concatenated segments.

## Findings

Severity is `blocker`, `warning`, or `info`. Warnings require human review but
do not by themselves prevent copy. Examples:

- `PRIVATE_USE_CODE_POINT`, `C1_CONTROL_CODE_POINT`,
  `REPLACEMENT_CODE_POINT`, and `NONCHARACTER_CODE_POINT` block a legacy file;
  for an already-UTF-8 file they are review warnings. These four findings are
  suppressed only in the explicit replacement mode, where a unit inside comment
  content becomes a recorded loss instead; the DBCS/backslash,
  mixed-single-byte, unassigned, and non-comment checks are never suppressed.
- `UNASSIGNED_CODE_POINT` is a review warning.
- `MIXED_SINGLE_BYTE_ARTIFACT` reports a DBCS pair whose lead is in
  `0x80-0x9F` and whose trail is an ASCII letter next to an ASCII word. The
  decoded character may have consumed the ASCII byte; choose the charset
  explicitly rather than accepting the mutation silently.
- `NON_COMMENT_NON_ASCII` blocks non-ASCII code, string/character literals, or
  header names in a legacy file. In a UTF-8 file the output is unchanged, so it
  is a warning.
- Other blockers include decode/round-trip failures, the decoded-character
  limit, unterminated constructs, raw strings, the GCC continuation form, DBCS
  trail `0x5C`, trigraph `??/` and `??=`, `UNSUPPORTED_INCLUDE_FORM` when an
  include-like directive has no direct header-name or macro operand before the
  line ends, output bound failures, and internal output verification failures.
- Replacement-mode codes: `INVALID_SPAN_ASCII_UNSUPPORTED`,
  `RECOVERY_BOUND_EXCEEDED`, `REPLACEMENT_BOUND_EXCEEDED`, and
  `REPLACEMENT_TRIGRAPH_HAZARD` are blockers. `REPLACEMENT_APPLIED` is an
  informational count and never approval. `NON_COMMENT_NON_ASCII` also covers
  an opaque span outside comment content.
- A strict-mode diagnostic for one of the four replaceable code-point classes
  was raised from proven comment content, so it may name the explicit reviewed
  replacement preview for that unit; it still does not resolve other findings.
  A strict `DECODE_ERROR` may mention the replacement preview only as a
  possible classification pass, because the bytes are not yet lexically
  classified. Neither hint asserts that replacement will succeed or suggests a
  different charset.

## Plan schema

`plan.json` is a deterministic UTF-8 JSON object with exactly these top-level
fields:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Integer plan schema version (currently 2). |
| `kind` | `stm32-comment-normalization-plan`. |
| `helperVersion` | Helper version that produced the plan (currently `1.1.0`). |
| `sourceRoot` | Resolved source root recorded for the copy check. |
| `mode` | `strict` or `replace`. Omitted CLI option means `strict`. |
| `replacementValue` | `null` for `strict`, otherwise the single supported value `?`. |
| `limits` | Exact enforced limits, including decoded-character and output bounds. |
| `status` | `ready` or `blocked`. Copy refuses anything but `ready`. |
| `files` | Sorted per-file entries with status, hashes, findings, newline/BOM evidence, counts, and replacement records. |
| `planId` | SHA-256 of canonical JSON of the plan without `planId`; binds the mode, replacement value, hashes, and records. |

Each file entry contains the relative path, declared charset, status, source
and output sizes/SHA-256 values, outside-comment digests, comment/non-ASCII/
changed counts, newline evidence, BOM flag, `decodeMode` (`strict` or
`recovery`), whole-file `decodeRoundTrip`, per-unit `unitRoundTrip`,
`invalidByteUnits`, `lossy`, `replacementCount`, `replacementRecords`,
idempotence proof, and findings. A blocked file has `null` output fields.

A `replacementRecords` entry has exactly `path`, `byteOffset` (absolute source
byte offset), `byteLength`, `originalBytes` (lowercase hex, `2 * byteLength`
characters), `line`, `column`, `reason`, and `replacement`. Reasons are
`invalid-byte-unit`, `private-use-code-point`, `c1-control-code-point`,
`replacement-code-point`, or `noncharacter-code-point`. Records are strictly
increasing by byte offset, bounded by `MAX_REPLACEMENT_RECORDS`, and
`lossy` is true exactly when at least one record exists.

A plan with a different `schemaVersion` or `helperVersion` is refused with
`PLAN_UNSUPPORTED` and re-preview guidance instead of being reinterpreted, so an
older plan can never silently change meaning.

The canonical plan ID is SHA-256 over sorted-key, compact, UTF-8 JSON of the
plan body. Preview and copy both recompute it. Copy additionally re-reads and
re-derives every selected file and requires exact equality with the reviewed
file entry before writing. Exact JSON types are enforced: booleans are not
integers, floats are not integers, and malformed metadata is `PLAN_INVALID`
rather than an internal error.

## Preview

`preview` is read-only with respect to the project. The preview directory must
be outside the source root and must not contain it. It writes `plan.json` and
a human-readable `preview.md` containing per-file evidence, findings, and a
byte-level diff. An existing file is reused only when its bytes are identical;
otherwise the preview fails with `PREVIEW_COLLISION`. Existing preview files
are read through the configured bound, and the plan, preview, and finding lists
are bounded.

`preview --replace-invalid-with '?'` additionally renders one row per
replacement record in `preview.md`, and the CLI JSON adds `mode`,
`replacementValue`, `lossyFiles`, and `totalReplacementCount`. Any other
replacement value fails with `REPLACEMENT_VALUE_UNSUPPORTED` before a preview
directory is created. A ready replacement plan can still contain recorded
losses, so readiness is never copy authorization and never bulk confirmation.

The CLI exits `0` only when every file is ready. Exit code `2` covers both a
completed preview with at least one blocked file (`status: blocked`) and an
operational failure (`status: failed`, with a `code` such as `PATH_INVALID`,
`PREVIEW_COLLISION`, or `IO_FAILURE`). Inspect the JSON status rather than
treating every exit code `2` as a reviewed blocked plan.

## Copy

`copy` accepts the reviewed plan path, the exact expected plan ID, a new output
directory outside the source root, and repeatable `--confirm-file REL` options.
It:

1. Rejects redirected or reparse ancestors in the raw plan, source, and output
   paths before canonicalization. Source-relative components are also checked.
2. Revalidates the plan shape, exact types, limits, plan ID, source root, file
   list, reserved output paths, freshness, and deterministic re-derivation.
   Re-derivation uses the plan's own `mode` and `replacementValue`, so the copy
   cannot diverge from the reviewed options.
3. Validates confirmations before creating any output directory. A `replace`
   plan requires exactly one canonical, selected, lossy `--confirm-file` per
   lossy file: missing (`CONFIRMATION_REQUIRED`), duplicate
   (`CONFIRMATION_DUPLICATE`), unknown (`CONFIRMATION_UNKNOWN`), non-lossy
   (`CONFIRMATION_NOT_LOSSY`), and malformed (`CONFIRMATION_INVALID`) sets are
   refused. A `strict` plan accepts no confirmation and rejects any supplied
   one (`CONFIRMATION_INVALID`).
4. Creates only the new output directory and writes an `INCOMPLETE.json`
   marker immediately, before any converted file, so interruption cannot leave
   an apparently complete directory without a marker.
5. Writes each selected relative path with exclusive creation, preserving
   layout, and verifies the bytes read back. Existing output is never
   overwritten. `manifest.json`, `manifest.json.partial`, and `INCOMPLETE*.json`
   are reserved at the output root. A selected first component that matches one
   of those names under Windows semantics — case-insensitively, or after
   trailing dots and spaces are ignored — is rejected when the selection is
   parsed or the plan is validated, before any preview or output path is
   created.
6. Re-reads every original, proves its hash is unchanged, builds a final
   `manifest.json` through a verified staging file, and only then removes the
   incomplete marker. If marker removal fails, the newly created manifest is
   removed so the marker remains authoritative.
7. On a failure after creating the directory, updates the incomplete marker
   with the failure code, message, and the files actually written. It does not
   broaden cleanup or delete unrelated files.

The manifest records `copyOnly: true`, `notAProject: true`, the plan ID, mode,
replacement value, `confirmedFiles`, `lossyFiles`, total and per-file
replacement counts, source and output roots, per-file source/output hashes and
sizes, outside-comment digests, `originalsUnchanged: true`, and
`outputsVerified: true`. The output is a set of converted file copies, not a
complete migrated or buildable project.

## Retained limitations

- The helper is not a C compiler or preprocessor. Macro-expanded headers,
  conditional-compilation regions, and unsupported preprocessing forms are
  outside its guarantee; they are blocked or left under ordinary lexical rules
  rather than guessed.
- ARMCC source-character behavior and runtime string/ABI equivalence are not
  established. The optional GCC object probe is synthetic GNU toolchain
  evidence, not ARMCC or original-project evidence.
- The original robot project is read-only. A real preview may return blockers
  for corrupted, private-use, or mixed comments; do not repair them
  heuristically. The explicit replacement mode is an owner-approved, recorded
  content loss — `?` does not recover the intended characters, and it must not
  be presented as a repaired comment, a guessed charset, a text encoding
  claim, or authorization to edit originals.
- The companion skill is discoverable under `skills/normalize-source-comments`
  but is intentionally not added to the eight-skill closed release inventory or
  release packager in this slice. `doctor` therefore continues to report the
  release workflow skills only.
