# COMMENT-ENCODING implementation report

Implementer: Claude Code CLI, using the user's unchanged provider/model
configuration. Reviewer and acceptance owner: the primary conversation agent.
This report is not self-acceptance.

## Identity and ledger

- Module/phase: COMMENT-ENCODING, explicit comment-only source normalization
  skill and helper.
- Accepted base: `863f0ec9adf5cb00a994fd5faa93be28efb0ec4d` (independently
  accepted BUILD-SNAPSHOT).
- Specification/plan head: `d20195c7f1458fdd867aab2401154ceee236be7c`.
- Agent-guidance head supplied for the resumed work:
  `e62f7b151f82edbad29d9db591b1af0bfab392f0`.
- Pre-report CodeHead (the code/tests/guidance commit):
  `0e5cc553a5120013f3ef7a5e6472405ffb51320f`.
- Branch: `codex/comment-encoding`.
- Authorized remote action: none performed. No push, PR, merge, tag, remote
  deletion, global skill installation, release, build, flash, or hardware
  operation was performed.
- Original project `D:/WorkSpace/mobile-robot-controller` was not modified and
  was not converted or built in this slice.

## Process incident and correction

During the first invocation, a compound PowerShell discovery command was
denied by the static command validator. The implementer did not stop on that
denial: it retried discovery with `Get-Command` and then used Python
`shutil.which` to find the compiler. The primary interrupted the session. No
product edits existed at that point. Those denied/retried calls were not tests,
were not executed successfully as discovery, and are not counted as passed.

The primary then supplied the exact verified Python and ARM GNU compiler
paths and the permitted command forms. All resumed work used only those forms
and exact paths. No new denial occurred in the resumed work. The original
stream-json log is retained by the primary; this report does not rewrite it.

## Delivered files

New:

- `skills/normalize-source-comments/SKILL.md`
- `skills/normalize-source-comments/scripts/normalize_comments.py`
- `skills/normalize-source-comments/references/lexical-and-plan-contract.md`
- `tools/stm32-toolkit/tests/test_normalize_source_comments.py`
- `docs/codex/returns/COMMENT-ENCODING/implementation-report.md`

Modified:

- `skills/migrate-keil/SKILL.md` (explicit companion preparation route;
  stale Schema v2 wording corrected to schema-3)
- `docs/user-guide.md` (encoding remediation routing)
- `docs/architecture.md` (copy-only companion boundary)
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` (preflight description
  text only; no new MCP tool)
- `tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py` (remediation
  message text only)
- `tools/stm32-toolkit/src/stm32_toolkit/keil/armcc_scan.py` (remediation
  message text only)
- `tools/stm32-toolkit/tests/test_plugin_layout.py` and
  `tools/stm32-toolkit/tests/test_public_inventory.py` (inventory
  expectations for the new discoverable companion skill)

No migration scanner defaults, firmware, generated compile flags, runtime
APIs, plugin version, installer, release builder, or `public_inventory.py`
were changed. No third-party dependency was added.

## Behavior

`normalize-source-comments` is a standalone standard-library helper with two
operations:

- `preview` is read-only with respect to the project. It strictly decodes each
  explicitly selected project-root-relative C/C++ file with an explicit
  per-file charset (`utf-8`, `gb2312`, `gbk`, `gb18030`, or explicitly
  `cp1252`), proves byte round-trip, identifies real comments, derives UTF-8
  comment-only output, and writes a deterministic plan plus `preview.md` to an
  external preview directory.
- `copy` accepts the reviewed plan and exact plan ID, re-reads and re-derives
  every input, rejects stale/tampered plans, and writes only selected relative
  files into a new external output directory. It writes a durable
  `INCOMPLETE.json` marker before any output, verifies output readback and
  original hashes, writes `manifest.json` through a verified staging file, and
  removes the marker only after the manifest is verified.

The helper preserves all bytes outside comment content, comment delimiters,
CR/LF/CRLF sequences, final-newline state, and an existing UTF-8 BOM; it never
adds a BOM. Non-ASCII code, strings, character literals, or header names in a
legacy file block conversion. Assembly, UTF-16/UTF-32, binaries, arbitrary
text formats, reparse paths, and unsupported include forms are blocked or
rejected rather than guessed.

### Corrections after primary review

1. **Directive/header lexing.** Added comment-aware preprocessing-token
   skipping between `#`, the directive name, and its operand; recognized
   `#include`, `#include_next`, `#import`, `#embed`, digraph `%:`,
   `__has_include`/`__has_include_next`/`__has_embed`/`__has_embed_next`,
   `import <...>;`, and `export import <...>;`. Header-name tokens are consumed
   without comment lexing, so `//` and `/* */`-looking bytes inside them are
   never converted. `??/` and `??=` are blockers; an include-like directive
   with no header-name or macro operand before the line ends is blocked with
   `UNSUPPORTED_INCLUDE_FORM`. Ordinary macro includes still use normal token
   scanning; spliced comments and physical byte offsets are retained.
2. **Lost blockers at the diagnostic cap.** The scanner now tracks blocker
   count independently of presentation truncation and emits a blocking
   `FINDINGS_TRUNCATED` finding when a blocker would otherwise be omitted.
   Trigraph warnings are bounded, but the scan does not stop looking for a
   later blocker. The primary reproduction
   (`// A\x92s` repeated to the cap followed by `// \xa3B` under `gb18030`) is
   now blocked through normal preview/copy.
3. **Reparse/redirect ancestors.** Added raw-path ancestor checks before
   `realpath` for the source root, preview directory, output directory, plan
   file, and source-relative components. A redirected parent, not only a
   redirected leaf, is rejected. Real symlink creation is unavailable on this
   host (WinError 1314), so ancestor behavior is covered by mocked
   `_is_reparse` cases and the real-leaf test falls back to the same guard.
4. **Bounds.** Added a conservative decoded-character limit before building
   per-character mappings, a per-file output limit, and an aggregate output
   limit; all are recorded in plan `limits` and enforced during preview and
   re-derivation. Plan, preview, and existing-preview reads are bounded, and
   the trigraph finding list is bounded.
5. **Plan strictness.** Plan validation now requires exact JSON types (bool is
   not int; float is not int), finite JSON constants, bounds, and consistent
   newline evidence. Malformed user plans raise `PLAN_INVALID` rather than an
   internal error; a recomputed-ID metadata tamper is still re-derived and
   rejected.
6. **Durable copy evidence.** The incomplete marker is written immediately
   after the new output directory is created. Reserved output-root names are
   rejected during selection and plan validation, including a selected
   directory named `manifest.json` or `INCOMPLETE*.json`. The marker is removed
   only after a verified manifest; if removal fails, the newly created
   manifest is removed so the marker remains authoritative.
7. **Test quality.** Removed brittle generic wording assertions. The skill
   test now validates frontmatter shape, helper presence, and the bundled
   `quick_validate` result; actual preview/copy CLI behavior is tested through
   subprocesses.

## Evidence

All commands ran in this worktree with `python` on PATH
(`D:/codex-tmp/kx23/venv/Scripts/python.exe` behavior), external unique
basetemp/cache roots, and no network or installation. The ARM compiler was
used at the exact supplied path. No denied discovery command is counted.

| Owner / exact head | Check | Result |
| --- | --- | --- |
| Implementer / `0e5cc553a5120013f3ef7a5e6472405ffb51320f` | `python -m pytest tools/stm32-toolkit/tests/test_normalize_source_comments.py --basetemp=D:/codex-tmp/ce23/bt-normalize-precommit -o cache_dir=D:/codex-tmp/ce23/cache-normalize-precommit -ra` | 36 passed in 3.04s; includes the actual ARM GNU object-equivalence probe and bundled `quick_validate` test. |
| Implementer / same head | `python -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_public_inventory.py --basetemp=D:/codex-tmp/ce23/bt-inventory-final -o cache_dir=D:/codex-tmp/ce23/cache-inventory-final -ra` | 24 passed, 1 pre-existing pydantic-settings warning, in 5.69s. |
| Implementer / relevant message bytes unchanged at final head | `python -m pytest tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_keil_inspect.py --basetemp=D:/codex-tmp/ce23/bt-keil-1 -o cache_dir=D:/codex-tmp/ce23/cache-keil-1 -ra` | 234 passed in 80.10s. Later changes were helper/skill/reference bytes plus a whitespace-only wrap of the preflight docstring; migration/Keil behavior and asserted remediation message text were unchanged. |
| Implementer / same head | `python -m py_compile skills/normalize-source-comments/scripts/normalize_comments.py tools/stm32-toolkit/tests/test_normalize_source_comments.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py tools/stm32-toolkit/src/stm32_toolkit/keil/armcc_scan.py` | Exit 0, no output. |
| Implementer / same head | `git diff --cached --check` before the code commit | No whitespace errors after removing two trailing blank lines. |
| Implementer / ARM GCC 14.3.1 at `C:/ST/STM32CubeCLT_1.22.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe` | Synthetic comment-only before/after object comparison, plus a bounded `-finput-charset` acceptance probe | GB2312, GBK, GB18030, and CP1252 all returned 0; the test compared each legacy object with its converted UTF-8 object and passed. UTF-8 also returned 0. No link, target, or original-project build was performed. |
| Implementer / bundled base Python and validator | `C:/Users/zhy76/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe C:/Users/zhy76/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/normalize-source-comments` via an explicitly scoped subprocess | Return code 0, `Skill is valid!`. The same check is covered by the focused pytest file. |

Supporting fix during the focused work: the ARM object probe initially used
different source basenames, which changes the ELF `FILE` symbol. Both probes
now use `a.c` in separate directories, matching the earlier reconnaissance
method; the byte comparison then passed.

## Retained limitations

- No original-project preview, conversion, build, or successful migration was
  claimed or performed. The retained audit evidence still shows 13 invalid
  bytes, 14 private-use mappings, and six `0x92` mixed artifacts; those remain
  blockers or review findings, not repaired text.
- The helper is not a C compiler/preprocessor. C++ raw strings, trigraph
  `??/` and `??=`, the GCC backslash-horizontal-whitespace continuation, DBCS
  trail `0x5C` at a physical line end, private-use/C1/invalid text, and
  unsupported include forms are blocked or reported rather than guessed.
  Macro-expanded include operands and conditional-compilation regions are not
  evaluated.
- ARMCC source-character behavior and runtime string/ABI equivalence remain
  unverified. The GCC 14.3.1 synthetic object equality is GNU toolchain
  evidence only, not ARMCC or original-project evidence.
- Real symlink/junction creation was unavailable on this host. Raw ancestor
  checks are implemented and covered with mocked reparse components; the
  real-leaf test uses the same guard as a fallback. The primary should verify
  a real junction/symlink on a privileged or developer-mode host.
- The companion skill is discoverable at
  `skills/normalize-source-comments/SKILL.md`, but this slice deliberately did
  not add it to the eight-skill closed release inventory, `doctor`'s
  `SKILL_NAMES`, or the release packager's `{"mcpTools": 48, "skills": 8}`
  contract. The two inventory tests now assert that the eighth release
  workflows are unchanged and that the only extra discoverable skill is this
  companion. A later release-inventory decision remains a separate scope.
- The installed global skill copies, fresh-session discovery, release
  packaging, real project replacement, migration apply, build, flash, and
  hardware acceptance remain outside this slice.
- No self-acceptance. The primary owns the independent complete-diff review,
  focused rerun, and final verdict.
