# Complete source preparation before GCC delivery

Encoding preparation is a reviewed, reversible step between the read-only Keil project
and migration. It uses the existing `normalize-source-comments` helper, which is a
selected-file copy helper, not a project generator and not a migration apply. There is no
second transcoder, no normalization MCP tool and no automatic charset detection.

## Pipeline

```text
original complete Keil tree (read-only)
  -> explicit charset preview for selected sources and needed quoted headers
  -> reviewed converted copies in a new external directory (a partial file set)
  -> complete separate prepared tree (all other files copied byte for byte)
  -> reviewed inspect -> preflight -> PLAN -> APPLY from the prepared root
  -> separate complete GCC/CMake output directory
```

The partial helper output is never called a project. The prepared tree is a complete copy
of the original project, with only the accepted converted files overlaid. The migration
destination is a different, independent output tree; its build inputs must not depend on
the original project or on the prepared source tree after delivery.

## When preparation is required

- Preflight reports `ARMCC_SOURCE_ENCODING_UNSUPPORTED` for a compiled C/C++ source, or an
  align/placement diagnostic names a quoted include such as
  `quoted include "Inc/malloc.h" is not UTF-8` because the bounded expression evaluator
  must read it.
- The affected bytes are really legacy text. A missing, unreadable, redirected or
  ambiguous dependency is not an encoding problem: collect read-only path and
  scoped-include evidence instead of transcoding or widening include search paths.
- Assembly, UTF-16/UTF-32, binaries and arbitrary text formats are outside the helper.
  Report their diagnostics unchanged.

## Declare charsets explicitly

Choose the helper loaded from the absolute directory containing its `SKILL.md` and set
`$Normalizer` to that directory's `scripts/normalize_comments.py`, as its `SKILL.md`
describes. Use a verified CPython 3.12 interpreter and declare exactly one charset per
selected file:
`utf-8`, `gb2312`, `gbk`, `gb18030` or explicitly `cp1252`. Different files may use
different charsets. Never guess from the extension, locale, a successful decode or a
previous project. A successful decode does not prove the decoded human text is intended.

The selection must include every needed header named by the diagnostics, even when the
header is not listed in the `.uvprojx`. Include only files whose change is required for
the blocked operation; do not normalize unrelated sources merely because they are legacy.

```powershell
python $Normalizer preview --project-root 'C:\work\robot' `
  --preview-dir 'D:\review\robot-comments-1' `
  --file 'App/main.c=gbk' --file 'Inc/malloc.h=gb2312'
```

`preview` is read-only and writes only `plan.json` and `preview.md` under the new external
preview directory. Read each file's `status`, `blockers`, `warnings`, `sourceSha256`,
`outputSha256`, `outsideCommentSha256`, newline/BOM evidence and the byte diff. Do not copy
a blocked file. A warning about a DBCS trail byte, private-use/C1-control/U+FFFD/noncharacter
code point, or unassigned text needs a real human decision; choosing another charset is an
explicit new preview, never an inference.

Only non-ASCII characters inside real C/C++ comments are converted. Runtime strings,
character literals, preprocessing header names, code, delimiters, all bytes outside
comment content, CR/LF/CRLF sequences, final-newline state and an existing BOM stay as they
are. A legacy file with non-ASCII bytes outside comments is blocked. Never change runtime
literal bytes to make a conversion appear to work.

## Strict versus reviewed lossy copies

Strict decoding is the default. Use option `preview --replace-invalid-with '?'` only when
the user explicitly asks to replace undecodable comment units, or existing private-use,
C1-control, U+FFFD or noncharacter code points, with a literal `?`, and has declared the
charset. The replacement preview is read-only and classifies each unit; it can still block
the file. Only records the lexer proved to be comment content are copyable.

For each accepted lossy file, pass exactly one `copy --confirm-file '<relative path>'` as
reviewed per-file evidence. Never loop over `lossyFiles`, edit the plan or confirm on the
user's behalf. If a lossy file is declined, re-preview the narrowed selection. Missing,
duplicate, unknown, non-lossy or invalid confirmations fail before the output directory is
created. Strict plans require no confirmation and reject one.

```powershell
python $Normalizer copy --project-root 'C:\work\robot' `
  --plan 'D:\review\robot-comments-1\plan.json' `
  --plan-id '<exact reviewed planId>' `
  --output-dir 'D:\review\robot-comments-1-copy'
```

`copy` re-reads and re-derives every input and refuses a changed source
(`INPUT_CHANGED`), a tampered plan (`PLAN_TAMPERED`), a wrong plan ID
(`PLAN_ID_MISMATCH`) or an older incompatible plan (`PLAN_UNSUPPORTED`). Its
`manifest.json` records output hashes, mode, replacement value, confirmed files, lossy
files, per-file counts, `originalsUnchanged: true` and `outputsVerified: true`. The copy
never overwrites existing output or originals and never claims migration completion.

## Build the complete prepared tree

Do this as a separate explicit file operation after reviewing the copies:

1. Choose a new prepared root outside the original project. Refuse a source or prepared
   root reached through a symlink, junction or other reparse point.
2. Inventory the original tree before copying. Record every file as an exact portable
   relative path plus SHA-256, omitting `.git` VCS metadata (the directory or a worktree
   pointer file) from both the inventory and the copy. Refuse absolute paths, `..` escapes,
   paths outside the selected root, case-insensitive duplicate paths, unreadable entries,
   special files and redirects. Do not silently skip any other unknown entry; `.git` is the
   only exclusion.
3. Copy the whole project, not only compiled files. Preserve every unselected source,
   header, startup/assembly file, resource, license, documentation file, project file and
   directory layout needed by the project, apart from the omitted `.git` metadata. Byte-copy
   files that are not being converted: every other prepared file is byte-identical to the
   original, and the original stays unmodified.
4. Overlay only reviewed converted copies. For each overlay, require the current original
   file hash to equal the reviewed plan's `sourceSha256` and the converted copy hash to
   equal its `outputSha256`. Any mismatch means re-preview; never force the overlay.
5. Recompute the prepared inventory and compare it with the original inventory plus the
   expected changed files. Unexpected added, missing, redirected or changed files are a
   stop condition, not a reason to edit the manifest or invent a hash.
6. Re-run the ordinary read-only sequence from the prepared root:
   `stm32_project_context`, `stm32_keil_inspect` with the same relative `.uvprojx` and
   exact target, then `stm32_keil_preflight`. Results from the original tree do not carry
   over. Any remaining blocker must still be reported and resolved before a PLAN.

Do not run migration apply, a build or a flash from the normalizer. Do not run `git init`,
commit, stash or clean; preparation needs no Git repository. Never rewrite the original in
place. Replacing the original project is a separate explicit user decision.

## Authorization and current review boundaries

An existing user instruction that authorizes this migration task can cover the reversible
preparation it implies: producing reviewed converted copies and a complete prepared tree
outside the original project. Do not invent a new universal confirmation stop for every
copy. Still require real user intent for each explicit charset choice, each accepted lossy
replacement and each behavior decision such as a WFI normal-return selection; those are
not inferred from a decoder, a diff or a previous authorization.

A preview, plan ID, diagnostic or generated manifest is evidence, not approval. Copy only
what the user's instruction and your review cover. If the scope grows, ask about the new
scope rather than treating the earlier authorization as unlimited.

## Root rebinding and delivery

The prepared root becomes the migration input root. Bind it explicitly as the workspace and
MCP server's project root, and keep the same relative `.uvprojx` and target. Never change an
existing server binding behind the user's back or fabricate a path. After the reviewed PLAN
and authorized APPLY, bind the returned `data.outputRoot` as the new project root for
configuration, build and the normal managed route.

The original project stays unchanged and is not the build input of the delivered output.
Source and destination are disjoint; the destination must be absent or verified empty. If
anything in the original, prepared tree or reviewed copies changes after review, re-inspect
and re-plan rather than reusing the old plan ID.

On this local source tree, content snapshot identity is accepted by the same managed firmware
admission as Git-backed identity. A delivered project without Git builds, flashes, debugs, runs Target tests and
Monitor through the normal managed routes once it has a current successful build, the bound
model/debug target, an explicitly selected probe and real authorization. Git is optional
traceability only: do not `git init`, commit or fabricate provenance, and do not present the
separate external firmware import route as a workaround for Toolkit GCC output.
