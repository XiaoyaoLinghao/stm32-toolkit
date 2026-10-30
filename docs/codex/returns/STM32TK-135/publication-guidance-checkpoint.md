# v1.3.5 publication-guidance checkpoint — 2026-10-30

Publication itself is complete: [formal Latest v1.3.5](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.5),
release428722744, frozen source `eac81a00a9c0cb0f78dcc0b423945605897b4806`, all13 anonymous downloads
HTTP200 with exact candidate lengths/SHA256. This checkpoint does not rebuild or replace those assets.

Current guidance slice verdict: **REVISION_REQUIRED_GUIDE_THREE_PROSE_FINDINGS**.
Accepted base `1ff0b69603449f17b0fb246e72d6d3b733c2dd35`; CodeHead before this report commit `59ccc4695bf33e4bd570dc7898a989196a6014c8`.
Primary Codex owns specification, orchestration, complete-diff independent review and acceptance;
local Claude Code CLI implemented the12 changed guidance/test-contract files using the unchanged
`deepseek-v4.1-flash[1m]` route. Branch `codex/v135-release-closeout`, no active PR.
The clean independent review tree was frozen at this exact CodeHead. Canonical complete-diff SHA256
`57c2288c00ff8689d6f293a82e74e9cd7746ca45947f0d3556e3fd67fe76874d` is identical between implementation and independent review trees;
frozen product/runtime/release paths are unchanged. See [structured evidence](publication-guidance-evidence.json).

Landing and four-file architecture/Skills invocations completed normally. The seven-file guide
invocation reached native `error_max_turns` (100), CLI/dispatcher1, after62 matched successful
edits; it remains **NOT_ACCEPTED**, file-edit-completion false, tests not run in that invocation.
There were no tool failures, denials, read/write scope violations or shell calls. All edits/logs are
retained, with no restart or retry. The entire candidate diff was independently read, not accepted
from model claims. Three prose findings remain in `docs/user-guide.md`:

1. Line9: explicitly select separately authorized Bootstrap only for missing; Repair for repairable/broken.
2. Line38: v1.3.3 is a historical route; v1.3.4 is the previous public release.
3. Line549: current100kHz default is published1.3.5 behavior; remove the leftover candidate label.

A separate exact three-edit, one-file Claude continuation is prepared but **not launched**.
Explicit bounded authorization is pending because the user's global instructions require
“Any retry needs explicit, bounded authorization”. No Codex implementation fallback is used.

The original unexecuted focused verification was completed independently of that editing request:

| Group | Passed | Skipped | Actual pytest exit |
| --- | ---: | ---: | ---: |
| meta | 79 | 0 | 0 |
| guidance | 93 | 1 | 0 |
| contract | 1 | 0 | 0 |

Total173passed/1platform skip/0failures/errors, all at `59ccc4695bf33e4bd570dc7898a989196a6014c8`, with fresh JUnit and unchanged tracked
bytes. All three exact PowerShell commands and a real harmless startup smoke have native matched
events; CLI/dispatcher0. The skip is `test_vscode_configuration.py::test_redirect_targets_are_refused`,
host unable to create a real file symlink, retained for Primary on a later capable host. These are
overlapping documentation checks, not additions to the3204 distinct integration count and not a
new final-head/full-repository release qualification or coverage comparison.

Before the first verification CLI launch, Primary supplied an invalid empty `read_scope`.
The coordinator's schema validator rejected that input before creating a run directory or
starting Claude/tests. Original input/error retained; the admitted task added only the seven
exact existing test-file metadata entries, with identical PowerShell commands and tools. No
worker permission refusal, retry of a test, package installation or runtime change occurred.

Current publication evidence is durable locally; the12-file source-guidance candidate has **not**
been pushed while these findings await disposition. Product/tag publication remains successful.
The user owns final installation/upgrade/rollback, VS Code/MCP and interactive validation;
previous original-pair100kHz evidence retains its limited source/SDK/image scope. No hardware,
original-project edit, installed-runtime replacement, new release mutation or credential reuse.
Raw evidence: `D:/codex-tmp/r135-publication`.
