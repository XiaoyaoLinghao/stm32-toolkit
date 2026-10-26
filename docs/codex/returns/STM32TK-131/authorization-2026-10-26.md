# v1.3.1 continuation authorization — 2026-10-26

The subsequent Git Credential Manager login and authorized source/tag push are
recorded in [the GitHub delivery record](github-delivery-2026-10-26.md).
Authentication failures below retain the earlier checkpoint, not the current state.

The human explicitly authorized existing PowerShell7 for the isolated candidate
installation, without changing execution policy, and approved only the previously
disclosed limits of frozen source `7ff99e50011b6321ae3f0c9bb2edfab91724be3e`.
Other acceptance remains required. The subsequent bundled answers confirm these
decisions; the earlier answer to leave installation pending is superseded by the
specific interpreter-correction approval. Original project and hardware remain
out of scope. No future candidate inherits this exception.

Current source/report base before this governance update is
`5203647abb29c4e208ffc515bf75a1fd77061efb`; frozen assets remain unchanged.
The goal resumes work from its blocked checkpoint with a fresh blocker audit.
Primary owns orchestration/review/acceptance, Claude Code CLI retains its existing
provider/model and owns delegated execution. No Codex implementation subagent.

PowerShell7 at the recorded bundled path was rechecked: LocalMachine RemoteSigned,
all other execution-policy scopes Undefined. Native Claude inventory session
`5db94fe5-b7c2-45bc-8f65-9cca08a99c65` registered PowerShell with zero tool calls;
session `f3bd07d1-b850-4d29-baf1-0a7462834bfd` executed the actual harmless
Get-Location in the bound package-review tree. No permission settings changed.

The first new wrapper attempt stopped before setup because the coordinator
compared archived CRLF script bytes directly with Git's LF blob. Primary verified
that the bundle equals the frozen source archive exactly and that line endings
are the only difference. The wrapper now compares exact `git archive` bytes,
retaining the repository's archive attributes; it does not normalize away a
potential product change. Original abort logs remain retained. The corrected
Check ran successfully, reported `mutated=false`, missing runtime, and recommended
Bootstrap. The subsequent Bootstrap and final Check both exited zero. Primary
independently read the retained native output and runtime-state file: final runtime
is healthy at version 1.3.1, state is matching at install generation 1, and final
Check reported `mutated=false`. Source and release-manifest identities match the
frozen package. This accepts the bounded fresh-install sequence only.

Evidence is retained under `D:/codex-tmp/r131/`; each stem below has `.stdout`,
`.stderr`, and `-execution.json` files. All three stderr files are empty.

| Step / evidence stem | Claude session | Exit | stdout SHA-256 |
| --- | --- | --- | --- |
| Check before / `install-ps7-check-before-b` | `713abc3c-605f-4f83-9aa3-69bf80ba942d` | 0 | `c8e4aa134b572149d4ffa2f50a5b6b423fc8b6aa39d78cd893d465d92fa928f6` |
| Bootstrap / `install-ps7-bootstrap` | `682d93f8-f3ee-444a-bbb5-06548a6c9107` | 0 | `54c55c10bf7f60b4a3d6f0c3986295abe51043cb1b7fd3a9aea743d4676eed29` |
| Check after / `install-ps7-check-after` | `334f7be6-1671-465f-83dd-5558a2100abf` | 0 | `9c6f573e9ea87f73ba7229c8821c97b07e00de8d4baebc4ed430616d2c3fe6eb` |

Installed DataRoot is `D:/codex-tmp/r131/ide-data`; the synthetic project is
`D:/codex-tmp/r131/ide-project`. Runtime state binds source
`7ff99e50011b6321ae3f0c9bb2edfab91724be3e` and manifest
`f0e66a549f4c15b3b401112d7fc5cd54267bba5ef797f45d65a4609d1b1ad849`.
The installed doctor reports compatible Toolkit/Monitor 1.3.1, 52 MCP tools and
9 Skills. CLI extension discovery is not interactive VS Code acceptance.

The user reported Git login complete and authorized read-only rechecking. The
actual system Git executable still failed the noninteractive dry-run push with
`unable to get password from user`; credential helper is Git Credential Manager
2.9.1, and its GitHub account list was empty. A follow-up asks the user to complete
that specific client's login. No credentials were printed or copied, no auth
settings changed and no remote mutation occurred. Browser/connector login is not
substituted for Git transport authentication.

The latest explicit user instruction transfers final actual installation and
VS Code verification to the user and authorizes pushing GitHub. The agent has
stopped IDE automation. The synthetic workspace was opened in Restricted Mode;
no trust setting was altered, and no IDE task or MCP call was executed there.
The previous workspace-trust question is superseded and need not be answered
for source delivery. Final installation/IDE acceptance is
**USER_VALIDATION_PENDING**, not PASS; upgrade/rollback also has no new PASS.
These pending checks do not block the source push explicitly requested by the
user. Publication and downloaded asset verification must be reported separately
if performed; this record claims neither. The original firmware project and
hardware remain untouched.
