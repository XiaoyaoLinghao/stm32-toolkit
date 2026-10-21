# Monitor v1.2.0 source-delivery acceptance

Verdict: **ACCEPTED** for version alignment and source delivery. This is not binary-release or physical qualification.

- Accepted base: `45e1acde2e89a4d14570efe9c0f4d9b4e5e2f907`.
- Final product/tests/current-docs CodeHead: `e6cdf2c7625f6e68aecfcafbfd4a0d26ca2c5eec`.
- Implementation report head: `e1fd32fe0a43ec0e014dce29a8a901f2e0b4ec41`; its only additional file is [implementation.md](implementation.md).
- Prior remote master: `3edd82e6b8f2ebd5df88dcafde1e75f722357c3e`; prior source delivery: `dcd0a21f605782929051c26773a01e18c02ff55f`. Both are ancestors of the accepted source.
- Primary owns specification, plan, integration, complete-diff review, acceptance, remote actions and cleanup. `v120_impl` is the sole implementer; `v120_review` independently reviewed the complete 39-file base-to-CodeHead diff. Both subagents used gpt-6-sol/max. No ownership override.
- User explicitly authorized v1.2.0, tests, independent review, push, merge into master and historical-branch cleanup. Browser/hardware work, tags, GitHub Releases and PR mutations are outside this delivery.

## Scope and verification

All current version authorities identify 1.2.0, including both Python distributions, their exact dependency, CLI/import/protocol facts, plugin, UI package roots, release policy/schema/builder, setup and launchers. Existing 1.1.2 runtimes and project producers are recognized through the original migration contracts. Old exports still require exact runtime versions. No third-party dependency graph, Monitor feature source or generated UI asset changed in this version slice. The previous accepted Monitor functionality, including schema3 composite groups, remains present.

The primary inspected the complete accepted-base diff and all supplemental commits, reconciled the implementation report, and ran both public version CLIs plus metadata, lock-graph and Git-blob trust-anchor checks from clean `D:\codex-tmp\v12021\r` at the exact CodeHead. `primary-check.json` and `primary-check-final.log` retain the results. Independent final static checks used actual Git archive bytes and also passed.

| Owner / check | Result and retained evidence under `D:\codex-tmp\v12021` |
| --- | --- |
| Implementer: CLI/plugin/public inventory | 64 passed; `checks/core1.log` |
| Implementer: generation compatibility and user-owned files | 14 passed; `checks/generation.log` |
| Implementer: release artifacts and security | 74 passed; `checks/release.log` |
| Implementer: runtime Check/Repair, legacy versions, rejection and rollback | 13 passed; `checks/setup.log` |
| Implementer: build identity and legacy project producers | 8 passed; `checks/build.log` |
| Implementer: Monitor version, public model boundary and export identity | 14 passed; `checks/monitor2.log` |
| Implementer: exact CodeHead archive anchors | 1 passed; `checks/anchor.log` |
| Implementer: UI typecheck, e2e typecheck, lint, wire/catalog-tree tests, build and distribution | 20 tests passed; all commands exit 0; seven rebuilt files byte-identical; `checks/ui-*.log` |
| Implementer: offline local wheel builds | Both real METADATA versions 1.2.0; Monitor requires Toolkit exactly 1.2.0 and includes seven UI assets; `checks/wheel-*.log` |
| Independent version reviewer | 52 focused tests on unchanged affected product bytes and 5 final-head tests passed; `rv/focused.log`, `rv/final-focused.log`; exact commands/exit codes in `rv/*command.txt` |
| Independent final static review | NO BLOCKERS; both archive anchors match, lock graph unchanged outside root versions, clean diff and clean review tree; `rv/final-static.log` |

The initial Monitor selection produced 13 passes and one inherited test-boundary false positive. The existing scanner treated private `_Node.address` as a public model field. The implementer restricted it to direct annotated fields of top-level public classes; the independent reviewer verified the baseline private field and the retained public-field prohibition. This is classified INFRASTRUCTURE, with original `checks/monitor.log` preserved. No product model was relaxed. A report-only archive check also completed successfully; it is not additional product coverage.

## Supplementary review of unpublished history

The publication audit found three historical slices without a tracked independent verdict. These were reviewed now against the accepted `45e1acde` tree; this does not assert that independent acceptance happened at their original delivery time.

| Historical complete diff | Independent reviewer / present-tree evidence |
| --- | --- |
| DWARF/source-live: `60079d49ab85adb7166ffbc60ebf2c8c61495536` to `4d69bf64237d92281e27a4cc4f385db18093165d`, 39 files | `v120_source_gap_review`: NO BLOCKERS after following historical issues to their current fixes |
| GNU AST compatibility: `f6495c0bd6e00619ba07793e991614ef19fab295` to `011c1b50b65c0a22239ba31b6c956255c5a459a4`, 8 files | Same reviewer: 189 source/AST/DWARF/catalog tests and 2 source-route tests passed; `sr/python-focused.log`, `sr/python-source-routes.log` |
| ENTRY02: `095a81e48e5e0cf698b23da12cd02dbe71a3f9a1` to `68ba222de3775ff8ec45aba27b6fe2bb4c522f3a`, 22 files | `v120_entry_gap_review`: NO BLOCKERS; 76 CLI/auth/dist tests and 40 bootstrap/main UI tests passed; `er/python-cli-auth-dist.log`, `er/ui-bootstrap-main.log` |

Both gap reviewers used gpt-6-sol/max, read complete product/test/documentation/asset diffs and ran Python from the clean historical review tree `v12021\h`. ENTRY02 UI tests used a run-owned copy with eight source/config/lock hashes checked against that tree. The entry report correction `34256353d3b7ab0f8eacaa9b8065759299855933` is report-only. The version implementer's successful normal-layout UI build and seven-file verification closes the historical asset-rebuild evidence boundary. None of these checks is browser or physical evidence.

The remote-master-to-accepted-base publication audit scanned 32,569 added patch lines with targeted credential patterns, found zero matches, and reviewed unexpected paths. Three sanitized fixture records, two design PNGs and seven documents with local paths were understood. This is a bounded audit, not an absolute secret-free guarantee. See local `publication-audit.json` for exact branch candidates and review assignments.

## Local service and deferred evidence

The primary's read-only actual-project admission check failed under 1.2.0 with `FIRMWARE_IDENTITY_MISMATCH`, details `field=toolkitVersion`, `rule=current`. This is the pre-existing exact-version contract in `probe/flash.py`, not a version-slice regression. The original failure remains in `primary-check.log`; the reconciled check asserts that same rejection without admitting the old build. Project-producer compatibility and physical firmware admission are distinct contracts.

Local promotion is **DEFERRED**. Keep the existing 8765 listener PID 30040 and source `D:\codex-tmp\ur1021\review` at `45e1acde2e89a4d14570efe9c0f4d9b4e5e2f907`, version 1.1.2. Its unchanged project is `D:\codex-tmp\mr1019\p`, session `mr-stable-20261019`, data root `D:\codex-tmp\mr1019\data`; the existing service card is `D:\codex-tmp\ur1021\service.json`. No service restart, authentication delivery, database promotion, probe access, firmware rebuild or flash was performed. Later authorized rebuild/flash and a new valid identity are required before local 1.2.0 physical observation. Browser, hardware and full release/install qualification remain deferred to their later authorized owners.

## Delivery and cleanup boundary

Source acceptance precedes remote mutation. Primary will refresh remote heads and permissions, atomically push this accepted source plus documentation to master and `codex/v1.2.0` without rewriting history, then verify equal remote heads. Delete only live historical branches whose exact observed heads are wholly contained in master and which have no active PR/protection. The final remote head and deletion outcomes belong in the execution record `D:\codex-tmp\v12021\delivery.json`, avoiding a self-referential report SHA. No tag or GitHub Release is authorized.

The original dirty workspace is preserved. Run-owned source worktrees and small evidence files remain. Primary cleanup removed 29 disposable directories and retained one reparse hold at `checks\pt-core1` (test fixture `test_redirected_project_root_f0\redirected`). The earlier attempt to remove `sr\bt`, `sr\bt2`, `sr\tmp` was denied by automatic approval before execution; these three policy holds were not retried. Exact results are in `cleanup.json`. No prior-run hold, active service source, shared dependency cache or user data was removed.
