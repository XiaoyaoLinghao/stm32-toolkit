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
  `e62f7b151f82edbad29d9db591b1af0bfab392f0`; primary orchestration-guidance
  commit: `3b85c395d0e0efb825b0fca90bdc800c82afef44`.
- Pre-report CodeHead (code, tests, and guidance after all review
  corrections): `aae4a733668414edea383c97b4ccead60a22df7a`.
- Branch: `codex/comment-encoding`.
- Authorized remote action: none performed. No push, PR, merge, tag, remote
  deletion, global skill installation, release, build, flash, or hardware
  operation was performed.
- Original project `D:/WorkSpace/mobile-robot-controller` was not modified,
  converted, copied, or built by the implementer.

## Process incidents and correction

During the first invocation, a compound PowerShell discovery command was
denied by the static command validator. The implementer did not stop on that
denial: it retried with `Get-Command` and then Python `shutil.which`.
`shutil.which` did execute successfully, but it was a noncompliant retry and
not a test; neither it nor the denied command is counted as passed evidence.
No product edits existed when the primary interrupted.

During the review follow-up, a chained ledger query
(`git log ... && git status ... && git rev-parse ...`) was denied with
"appears inside a control-flow or chain statement". The implementer again
continued with individual commands instead of stopping. No destructive,
remote, or settings-changing action occurred; the primary interrupted again and
retained the edits and logs. The earlier partial helper edits were preserved.

After each interruption the primary supplied verified interpreter/compiler
paths and an explicit ledger, and narrowed the permitted invocation family to
single `python -m pytest ...` commands, the `quick_validate` wrapper, and file
tools. No permission-bypass flag or global permission change was used. Corrected
calls produced no new permission denial; one Edit no-op error was not a
permission denial. Neither denied command is counted as passed.

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
- `docs/user-guide.md` (encoding remediation routing; companion instructions
  location for clients that do not load `SKILL.md`)
- `docs/architecture.md` (copy-only companion boundary)
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py` (preflight description
  text only; no new MCP tool)
- `tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py` (remediation
  message text only, including inspect -> preflight -> plan ordering)
- `tools/stm32-toolkit/src/stm32_toolkit/keil/armcc_scan.py` (remediation
  message text only)
- `tools/stm32-toolkit/tests/test_plugin_layout.py` and
  `tools/stm32-toolkit/tests/test_public_inventory.py` (inventory
  expectations for the new discoverable companion skill)

No migration scanner defaults or rule semantics, firmware, generated compile
flags, runtime APIs, plugin version, installer, release builder, or
`public_inventory.py` were changed. No third-party dependency was added.

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
rejected rather than guessed. The CLI exits `0` only when every file is ready;
exit `2` covers both a completed blocked plan (`status: blocked`) and an
operational failure (`status: failed`).

### Corrections after the first primary review

1. **Directive/header lexing.** Added comment-aware preprocessing-token
   skipping between `#`, the directive name, and its operand; recognized
   `#include`, `#include_next`, `#import`, `#embed`, digraph `%:`,
   `__has_include`/`__has_include_next`/`__has_embed`/`__has_embed_next`,
   `import <...>;`, and `export import <...>;`. Header-name tokens are consumed
   without comment lexing, so `//` and `/* */`-looking bytes inside them are
   never converted. `??/` and `??=` are blockers; an include-like directive
   with no header-name or macro operand before the line ends is blocked with
   `UNSUPPORTED_INCLUDE_FORM`.
2. **Lost blockers at the diagnostic cap.** The scanner tracks blocker count
   independently of presentation truncation and emits a `FINDINGS_TRUNCATED`
   finding when a blocker would otherwise be omitted. Trigraph warnings are
   bounded separately, but the scan does not stop looking for a later blocker.
3. **Reparse/redirect ancestors.** Raw-path ancestor checks run before
   `realpath` for the source root, preview directory, output directory, plan
   file, and source-relative components, so a redirected parent is rejected
   before canonicalization can erase the evidence. Symbolic-link creation on
   the implementer host failed with `WinError 1314`, so the ancestor regression
   mocks `_is_reparse` as true only for the exact redirected ancestor
   directories and false for every descendant, while unrelated paths still use
   the real check. It asserts each root/preview/output/plan leaf is not
   reported as a reparse point and that each public operation still rejects the
   ancestor, with the failing component named in the error.
4. **Bounds.** Added a conservative decoded-character limit before building
   per-character mappings, a per-file output limit, and an aggregate output
   limit; all are recorded in plan `limits` and enforced during preview and
   re-derivation. Plan, preview, and existing-preview reads are bounded.
5. **Plan strictness.** Plan validation requires exact JSON types (bool is not
   int; float is not int), finite JSON constants, bounds, and consistent
   newline evidence. Malformed user plans raise `PLAN_INVALID` rather than an
   internal error; a recomputed-ID metadata tamper is re-derived and rejected.
6. **Durable copy evidence.** The incomplete marker is written immediately
   after the new output directory is created. The marker is removed only after
   a verified manifest; if removal fails, the newly created manifest is removed
   so the marker remains authoritative.
7. **Test quality.** The skill test validates frontmatter shape, helper
   presence, and the bundled `quick_validate` result; actual preview/copy CLI
   behavior is tested through subprocesses.

### Second-review corrections

- **One shared presentation allowance.** Two independently bounded lexing
  passes (trigraph scan and comment scanner) could produce more findings than
  plan validation accepted, making an authentic ready preview uncopyable.
  Derivation and validation now share `MAX_PRESENTED_FINDINGS =
  MAX_FINDINGS * 2 + 8`. This is a conservative shared upper bound, not an
  exact tight worst case, because some contributing error branches cannot occur
  together. Final bounding keeps blockers ahead of warnings: suppressing only
  warnings yields a warning `FINDINGS_TRUNCATED` marker, while omitting
  blocking findings yields a blocker marker, so blocking state is never lost.
  An earlier partial bound alignment (`904b21c7`) is superseded by this
  definition.
- **Portable reserved metadata names.** `manifest.json`,
  `manifest.json.partial`, and `INCOMPLETE.<n>.json` are folded under Windows
  semantics (case-insensitive, trailing dots and spaces ignored) in both
  selection parsing and plan validation, before any preview or output path is
  created. A ready plan can no longer fail only after output creation.
- **Public regressions.** The combined warning sources
  (`// ??( A\x92s` repeated to the cap under `gb18030`) produce a ready plan
  with 400 findings that previews and copies successfully; the same volume plus
  a late blocker stays blocked; case and trailing-dot/space metadata aliases
  fail with no preview/output directory; exit `2` from an operational failure
  reports `status: failed`; a bounded long token is scanned once.

### Final wording corrections

- Skill guidance states that copy runs when the user's task already authorizes
  reviewed converted copies; that authorization is reused without a mandatory
  extra approval stop. A preview, plan fields, or a `planId` alone never
  authorize the copy or original edits, and the helper has no `authorized`
  flag.
- Helper-path examples are account-independent and anchored to the absolute
  directory the skill was actually loaded from (repository or personal
  directory), not the current working directory and not a substituted global
  path.
- Legacy conversion treats private-use/control/replacement/noncharacter code
  points as blockers; an unchanged UTF-8 file reports them as review warnings.
- Source remediation reruns inspect -> preflight before a plan, and MCP-only
  clients are directed to the skill's own instructions and helper rather than
  an invented normalization tool.
- The `ARMCC_SOURCE_ENCODING_UNSUPPORTED` remediation text now says
  inspect -> preflight -> plan after blockers and prerequisites are resolved.
  Rule semantics are unchanged.

## Evidence

Implementer commands ran in this worktree with the verified venv Python
(`D:/codex-tmp/kx23/venv/Scripts/python.exe`), external unique basetemp/cache
roots, and no network or installation. They ran on the working-tree product
bytes that the primary subsequently recorded as the stated CodeHead; no test
execution is claimed after the primary's commit. The final increment after the
focused runs was limited to comments, guidance, and remediation-message text.

| Owner / source state | Check | Result |
| --- | --- | --- |
| Implementer / working-tree bytes later recorded as `aae4a733` | `python -m pytest tools/stm32-toolkit/tests/test_normalize_source_comments.py --basetemp=D:/codex-tmp/ce23/bt-normalize-review2b -o cache_dir=D:/codex-tmp/ce23/cache-normalize-review2b -ra` | 39 passed in 3.58s; includes the real ARM GNU object-equivalence probe and bundled `quick_validate` test. |
| Implementer / same state | `python -m pytest tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_public_inventory.py --basetemp=D:/codex-tmp/ce23/bt-inventory-review2 -o cache_dir=D:/codex-tmp/ce23/cache-inventory-review2 -ra` | 24 passed, 1 pre-existing pydantic-settings warning, in 5.78s. |
| Implementer / final wording-only increment | `python D:/codex-tmp/ce23/quick_validate_wrapper.py` (verified base interpreter and bundled validator) | Return code 0, `Skill is valid!`. |
| Implementer / earlier pre-review2 source state | `python -m pytest tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_keil_inspect.py --basetemp=D:/codex-tmp/ce23/bt-keil-1 -o cache_dir=D:/codex-tmp/ce23/cache-keil-1 -ra` | 234 passed in 80.10s. Retained at that earlier state; the later message-text edit is covered by the primary's final encoding-message tests below, not by this run. |
| Implementer / earlier heads | `python -m py_compile` on the helper, tests, MCP, migration, and scanner files; staged `git diff --check` | Exit 0; no whitespace errors. |
| Implementer / ARM GCC 14.3.1 | Synthetic comment-only before/after object comparison inside the focused test | GB2312, GBK, GB18030, and CP1252 probes all compiled; each legacy object matched its converted UTF-8 object. No link, target, or original-project build. |
| Primary / clean worktree `C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit` at `aae4a733668414edea383c97b4ccead60a22df7a` | `python -m pytest tools/stm32-toolkit/tests/test_normalize_source_comments.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/tests/test_public_inventory.py tools/stm32-toolkit/tests/test_migration_plan.py::test_invalid_encoding_adds_blocker tools/stm32-toolkit/tests/test_keil_inspect.py::test_invalid_encoding_blocker --basetemp=D:/codex-tmp/ce23/bt-primary-final -o cache_dir=D:/codex-tmp/ce23/cache-primary-final -ra` | 65 passed, 1 pre-existing pydantic-settings warning, in 10.55s; includes the real ARM GNU comparison and bundled validator. Log `D:/codex-tmp/ce23/primary-final.log`, exit-0 file. Primary evidence. |
| Primary / initial code `0e5cc553` | Real Windows Junction `D:/codex-tmp/ce23/junction-eval/linked-input -> D:/codex-tmp/ce23/forward-eval/input`; helper run with project root on an ordinary leaf below it | Exit 2 `REPARSE_PATH`, no preview written; `result.json` and `exit.txt` retained there. Primary evidence. |
| Primary / read-only original preview | `D:/codex-tmp/ce23/original-preview-review1`: `Main/Main.c=gb2312`, `USER/CAN/can1.c=gb18030`, `USER/usart2_rs485_1/usart2_rs485_1.c=gb18030`, `kinematics/kinematics_model.c=utf-8` | `Main` ready, UTF-8 file unchanged, private-use and undecodable files blocked; all 54 registered original hashes still match. No copy and no original edit. Primary evidence. |

## Retained limitations

- The implementer performed no original-project preview, conversion, copy,
  build, or successful migration; primary's read-only preview above is primary
  evidence only. The audit evidence still shows 13 invalid bytes, 14
  private-use mappings, and six `0x92` mixed artifacts; those remain blockers
  or review findings, not repaired text.
- The helper is not a C compiler/preprocessor. C++ raw strings, trigraph
  `??/` and `??=`, the GCC backslash-horizontal-whitespace continuation, DBCS
  trail `0x5C` at a physical line end, private-use/C1/invalid text, and
  unsupported include forms are blocked or reported rather than guessed.
  Macro-expanded include operands and conditional-compilation regions are not
  evaluated.
- ARMCC source-character behavior and runtime string/ABI equivalence remain
  unverified. The GCC 14.3.1 synthetic object equality is GNU toolchain
  evidence only, not ARMCC or original-project evidence.
- Symbolic-link creation on this host failed with `WinError 1314` (a privilege
  failure); this is distinct from Junction support, which works and was
  demonstrated by the primary's real Junction test. The implementer's
  exact-ancestor mock is supplementary regression evidence, and no further
  privileged-host junction verification is required.
- This slice adds a ninth discoverable skill but keeps eight closed release
  workflows: the companion is not in `doctor`'s `SKILL_NAMES`, the release
  packager's `{"mcpTools": 48, "skills": 8}` contract, or the closed public
  inventory. A release-inventory decision is separate scope.
- Global skill installation to personal discovery directories is separately
  user-authorized and primary-owned after acceptance; it was not performed
  here. Fresh-session discovery, release packaging, project replacement,
  migration apply, build, flash, and hardware acceptance remain outside this
  slice. No new MCP tool, version bump, or dependency was introduced.
- No self-acceptance. The primary owns the independent complete-diff review,
  final focused suite, and verdict.
