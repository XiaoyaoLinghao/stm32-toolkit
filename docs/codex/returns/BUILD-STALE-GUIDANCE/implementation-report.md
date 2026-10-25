# BUILD-STALE-GUIDANCE implementation report

Governing [design](../../../superpowers/specs/2026-10-25-build-stale-guidance-design.md) and [plan](../../../superpowers/plans/2026-10-25-build-stale-guidance-plan.md); raw commands, JUnit XML and hashes in [evidence.json](evidence.json).

## Source state

Accepted base `fefa21fe14de1a3710799e9cf39f33f3a41815d0`; branch `codex/build-stale-guidance`. Tested CodeHeads: `111495b48a53bff36a57b65ef5644edfb31b1407` (initial), `0e287de3f05054d65beff8600a08b8eb63040f6e` (tests corrected), `eb7bacb705b812e217998e063f8db5fb88725feb` (pre-report). Product source is byte-identical across all three; only tests, Skill and docs changed after the initial head. `evidence.json` is primary-authored. Product version remains 1.3.0.

## Completed behavior and files

`BUILD_OUTPUT_STALE` keeps its code, legacy `path`/`rule`, every freshness predicate, success/failure schemas, managed-file drift guards, Git/snapshot provenance, authorization and locking. A single comparison now yields the first bounded failure reason: output unavailable, prior evidence unavailable, previous build not successful, input snapshot mismatch, or a fixed evidence mismatch discriminator (preset/target, identity/build ID, discovery policy, paths/hashes, schema/provenance, project/version, snapshot result). The error adds JSON-safe `reason`, `evidenceField`/`evidenceSource` where useful, validated `preset`, `cleanRequested` and portable log/result/identity paths, and never echoes untrusted recorded values. Remediation for unchanged unverifiable outputs with `clean=false` is `clean-rebuild` with exact CLI token arrays, the required `--project-root` binding, working directory, and MCP tool/arguments omitting `authorized=true`; missing output or `clean=true` yields `inspect-build-log` without rebuild arguments. Advice never executes itself.

Files: `build/runner.py`, `cli.py` clean help, `mcp_server.py` build description; tests `test_build_stale_guidance.py` (new), `test_build_runner.py`, `test_build_snapshot.py`, `test_cli.py`, `test_mcp_migration_build.py`; `skills/build-firmware/SKILL.md`; `docs/user-guide.md`. `test_ai_call_guidance.py` was exercised unchanged; the diff has never modified it.

## Test evidence

| Run (owner) | Head | Tests | Pass | Fail | Skip |
| --- | --- | --- | --- | --- | --- |
| author-first | `111495b4` | 242 | 230 | 12 | 0 |
| review-first | `111495b4` | 242 | 230 | 12 | 0 |
| author-final | `0e287de3` | 51 | 50 | 1 | 0 |
| review-final | `0e287de3` | 51 | 50 | 1 | 0 |
| author-accepted | `eb7bacb7` | 13 | 13 | 0 | 0 |
| review-accepted | `eb7bacb7` | 13 | 13 | 0 | 0 |

Author ran exact native PowerShell pytest commands; commands and result XML are in `evidence.json`. CLI exit was not treated as pytest exit. The author's final invocation printed no explicit exit code; primary's independent run recorded exit 0. Distinct passing cases total 243 after justified reuse: 230 byte-identical-source passes were reused; all changed and guidance-dependent tests were rerun. No full final matrix is claimed.

The first 12 failures were test defects: 8 tuple/list expectations, 2 frozen mapping serialization, 1 expecting `identity.gitHead` although `record.buildId` mismatched first, 1 word-wrap literal. The second failure was an obsolete `workingDirectory` literal in a new description test. Corrections use public `to_dict`, preserve existing validation order, and add an actual identity-`gitHead` case with an aligned record ID.

## Other verification and incident

Primary-owned simulations gave correct initial A/B/C route decisions; later clarified that clean targets may remove generated outputs and named failure paths. Not VS Code or hardware validation. CLI replay success plus missing-root refusal passed; MCP public schema was validated; primary passed the Skill structural validator.

Delegation incident: the first author attempted a disabled Bash `echo no`, received "No such tool available," and continued instead of stopping. The coordinator found this in full logs after sessions ended, preserved work/logs, stopped resuming that session, and used fresh file-only corrections. No shell executed and no permissions widened. A 65-turn limit preserved edits and continued; editing and testing remained separate. No phantom execution is claimed.

## Limits

Offline synthetic projects and fake CMake only; real Git was used only for synthetic fixtures. Original project untouched and unread. No hardware, runtime/global installation, packaging, remote action or version bump. Borrowed 1.3.0 dependency-path and nonfatal `pydantic_settings`/`runpy` warnings retained; they do not indicate wrong Toolkit source. v1.3.1 remains deferred until all agreed optimization is complete. Outstanding: VS Code generated paths/tasks, doctor readiness, flash frequency/failure guidance, memory margin, integrated regression/release. No acceptance verdict is asserted; primary owns acceptance. Cleanup of 8 verified directories under `D:/codex-tmp/bs25` was rejected by automatic policy for native PowerShell with only `blocked by policy`; no deletion executed, no bypass, directories retained.
