---
name: normalize-source-comments
description: Use when a Keil or legacy C/C++ project reports a source-encoding blocker and the user wants a reviewed, comment-only UTF-8 copy. Preview explicitly declared per-file charsets first, then copy only selected files to a new external directory. Do not use for implicit transcoding, in-place edits, assembly, binaries, or a claim that migration is complete.
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
- Convert non-ASCII characters only inside real C/C++ comments. Preserve every
  other byte, comment delimiter, CR/LF/CRLF sequence, final-newline state, and
  an existing UTF-8 BOM. Do not add a BOM or normalize line endings.
- Block a legacy file that contains non-ASCII bytes in code, strings,
  character literals, or preprocessing header names. Do not change runtime
  literal bytes to make a conversion appear to work.
- Block or reject rather than guess: invalid input bytes, private-use or
  control code points, unterminated constructs, C++ raw strings, trigraph
  `??/`, a backslash followed by horizontal whitespace before a newline, and a
  DBCS character whose bytes end in `0x5C` at a physical line end.
- Assembly, UTF-16/UTF-32, binaries, and arbitrary text formats are outside
  this helper. Leave them untouched and report the diagnostic.
- The helper is not a C compiler. It does not promise generic charset support,
  runtime string/ABI equivalence, or that a project builds after conversion.

## Run the helper

Run the self-contained standard-library helper from this skill directory with
a verified CPython 3.12 interpreter. In the Toolkit repository the helper is
`skills/normalize-source-comments/scripts/normalize_comments.py`. After the
approved personal-skill installation, use
`C:/Users/zhy76/.claude/skills/normalize-source-comments/scripts/normalize_comments.py`
for Claude Code or
`C:/Users/zhy76/.agents/skills/normalize-source-comments/scripts/normalize_comments.py`
for Codex. A client that copied only this skill can use
`scripts/normalize_comments.py` directly. Do not invent an MCP normalization
tool or call `pyocd`, a compiler, or a migration apply to perform the copy.

Set the helper path once for the commands below to the actual installed path:

```powershell
$Normalizer = 'skills/normalize-source-comments/scripts/normalize_comments.py'
```

### 1. Preview read-only

Choose project-root-relative files and declare one charset per file. Use a new
directory outside the project for the preview:

```powershell
python $Normalizer preview --project-root 'C:\work\robot' --preview-dir 'D:\review\robot-comments-1' --file 'App/main.c=gbk' --file 'App/util.h=gb2312' --file 'App/notes.cpp=cp1252'
```

`preview` reads the project but writes only `plan.json` and `preview.md` under
the external preview directory. It returns JSON with a canonical `planId` and
per-file `status`, `blockers`, and `warnings`. Exit code `0` means every file
is ready; exit code `2` means the preview completed but at least one file is
blocked.

### 2. Review the plan

Read `preview.md` and `plan.json` before copying:

- `status: blocked` or any blocker finding: do not copy. Resolve the reported
  path, byte offset, line, and reason. A decode failure or a corrupt byte is not
  repaired automatically.
- Warnings such as a DBCS pair with an ASCII trail or a private-use/control
  code point require a human decision about the intended text. Choosing another
  charset is explicit; never infer it from a successful decode.
- Check `sourceSha256`, `outputSha256`, `outsideCommentSha256`, newline/BOM
  evidence, the human-readable byte diff, and that the plan contains only the
  files you selected.
- A preview, plan field, or warning is not authorization to modify originals.

### 3. Copy reviewed files

Copy only after reviewing the exact `planId`. The output directory must not
exist and must be outside the source root:

```powershell
python $Normalizer copy --project-root 'C:\work\robot' --plan 'D:\review\robot-comments-1\plan.json' --plan-id '<exact 64-character planId>' --output-dir 'D:\review\robot-comments-1-copy'
```

`copy` re-reads every input, re-derives the conversion, verifies the plan ID
and hashes, refuses changed inputs or tampered plans, and writes only the
selected relative files. It never overwrites existing output or originals.
The result includes `manifest.json`, which records output hashes,
`originalsUnchanged: true`, and `outputsVerified: true`. On failure, an owned
incomplete staging directory is marked by `INCOMPLETE.json` and has no final
manifest.

The output is a set of converted file copies, not a complete migrated or
buildable project.

### 4. Inspect the deliberately prepared project copy

If the project owner chooses to prepare a separate project copy, do that as a
separate explicit action: copy the project, replace only the selected files
with the reviewed converted copies, and point the Toolkit at that copy. Then
use the ordinary read-only migration sequence:

```text
stm32_project_context()
stm32_keil_inspect(uvprojx='<same relative .uvprojx>', targetName='<exact target>')
stm32_keil_preflight(uvprojx='<same relative .uvprojx>', targetName='<exact target>')
```

Do not run migration apply, `git init`/commit, a build, or a flash from this
skill. If all encoding blockers disappear, startup, scoped compiler options,
scatter/memory, Git/apply, and baseline blockers remain independent. Replacing
the original project in place is a separate explicit user decision.

## Reference

Read [references/lexical-and-plan-contract.md](references/lexical-and-plan-contract.md)
for the exact plan fields, hash definitions, lexical states, finding codes,
limits, copy invariants, and retained limitations.
