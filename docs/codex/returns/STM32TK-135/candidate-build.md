# v1.3.5 local candidate and package acceptance — 2026-10-30

Verdict: **ACCEPTED_WITH_FIXES for the authorized local closeout and packaging**.
The source/docs/integration/package objective is complete. Broader release status is
**LOCAL_CANDIDATE_NOT_QUALIFIED_PENDING_EXTERNAL_VALIDATION**; nothing is published
or installed into an existing/recipient runtime by this work.

Accepted base: `946b1ec5c0dd3c79bb5b5e73ce1650afa5ecb432`. CodeHead before this report commit: `56f51bfcb9318e31e61bc397a7dd61612bf893a3`.
Reviewed product/test CodeHead: `fa3613cb7b24a0f0532aff5248acb9ad919a112a`. Frozen package source: `eac81a00a9c0cb0f78dcc0b423945605897b4806`.
Subsequent source-branch changes are governance/evidence only; frozen artifacts remain
bound to the source above. Bundled documentation is the truthful build-time snapshot.
Primary owns specification, orchestration, complete-diff review and acceptance; local
Claude Code CLI retained `deepseek-v4.1-flash[1m]` and its existing provider/auth/permissions
for implementation and delegated build checks. Branch `codex/v135-release-closeout`,
no active PR and no remote mutation authorized.

## Build and verification evidence

The user explicitly authorized one A re-delegation after the retained failed entry;
B was the original-unstarted first build. Both used independent clean canonical
worktrees at the same frozen source and separate short temporary/output roots.
No-action inventories matched PowerShell exactly, with no inventory calls; each
startup smoke executed the real harmless command. Each main made exactly one allowed
native PowerShell call, with no extra whitespace, errors, scope violations or extra
commands. These were ordinary build checks, not designated test commands.

| Side | Actual build exit | Wrapper elapsed | CLI/dispatcher exit | Native state / numeric exit |
| --- | --- | --- | --- | --- |
| A | 0 | 30.280s | 0/0 | executed_success / null |
| B | 0 | 30.475s | 0/0 | executed_success / null |

Native numeric exits remain null where the matched tool result supplies none; worker
prose is not used to invent them. Actual build exit0 comes separately from the bound
subprocess report. Tracked source remained unchanged. The outer wrapper uses the exact
`-I -B -X utf8` command; its pinned real-Python child invokes the official utility as
specified, clears inherited Python source overrides and uses isolated backend Python
with `-I`. No unrequested change to product or invocation semantics was made.

The original runtime-only62-wheel input omitted the fixed build backends. The complete
offline build input has62 unchanged runtime dependency wheels plus setuptools84.0.0
and wheel0.48.0, copied from existing cache with SHA256/RECORD verified. Only the
builder's owned disposable backend environments were populated offline; no existing
or recipient runtime was installed/replaced. The delivered64 wheels instead comprise
62 dependencies plus Toolkit1.3.5 and Monitor1.3.5. Backend-only inputs are not shipped
as runtime dependencies. All62 dependency hashes/sizes/versions match the admitted input.
pyOCD is0.46.0, wheel SHA256 `f37c1ef65a1e78b42c9bccf4f34fbde98c4ea225e87534ee872e324aae230ba5`.

Primary compared names, lengths and SHA256 of **all13 files**, including CHECKSUMS;
both builds are byte-identical. Safe ZIP extraction and the existing official
`build_0900_artifacts.py verify-bundle --toolkit-root <extracted> --json` returned0/ok.
Manifest/source closure, wheel records/licenses, required inventory52MCP tools/9Skills
and all149 measured Python source hashes matched. The official build source archive
contains exactly the measured canonical Python bytes. See [candidate-build.json](candidate-build.json)
for source/input/native evidence hashes and [integration-evidence.json](integration-evidence.json)
for the software matrix/reuse ledger. Raw artifacts and reports: `D:/codex-tmp/r135`.

## Software outcome and retained limits

The source-bound selected matrix finished3,204 distinct passing cases,3 real file-symlink
capability skips, zero unresolved code failures/errors. Three original failures and
authorized single-node rechecks remain separate; original passing siblings were retained,
not rerun. Two native pending results were reconciled from their already-started bound
reports without rerun/worker polling/restart/kill. Primary's overlapping328 generation
cases are separate evidence. This is not a fresh whole-repository/single-final-head run.

Each user's1.3.5-only exact non-regression comparison passes: Toolkit15530/18734
(82.8974%) and risk14399/17394 (82.7814%); Monitor overall/risk3292/3564 (92.3681%);
UI2938/3147 (93.3588%, exact source/config/dependency reuse, per-file90 met). Permanent
Toolkit overall/risk90 and Monitor risk95 remain UNMET. Broad-core-v1 retains its
whole-source totals and historical disposition. UI534pass/1 platform skip is explicitly
reused; its original historical performance failure remains recorded. No failed raw
aggregate, changed-source prior arcs, removed member or favorable denominator was used.

Three file-symlink checks remain DEFERRED to Primary's later explicitly scoped release
validation on a capable Windows/Linux host; no privilege/policy change occurred.
Final installed upgrade/rollback, VS Code/MCP and interactive validation remain user-owned
with Primary release support. The prior one original-pair100kHz physical PASS retains
its recorded candidate/SDK/image scope and consumed authority; no new hardware or final
installed1.3.5 acceptance is claimed. Firmware ABI/CCM work stayed outside scope.

The original failed A invocation remains NOT_ACCEPTED: a one-leading-space command
actually executed and exited2 on the incomplete backend input. Its CLI0/dispatcher1,
missing pip stderr, input omission and raw logs remain in [packaging-entry-review.json](packaging-entry-review.json).
One explicit retry was consumed; no retrospective allowlist expansion or automatic retry.

Temporary worktree A was archived recoverably after verification. The app rejected
archiving B because it is this chat's primary checkout; B is retained, with no bypass
or retry. Needed artifacts, logs and input/source identities remain outside those roots.
Other sessions/worktrees were not cleaned or changed. No hardware, push, PR, merge,
tag, Release or publication operation occurred.

## Exact artifact inventory

Both `D:/codex-tmp/r135/complete-package-a` and `complete-package-b` contain this inventory.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| LICENSE | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` |
| THIRD-PARTY-NOTICES.md | 2615 | `264eedb55fef41747e83efbd7bce817aa761d4d9f4df7923c4785c0fb390c707` |
| compatibility.md | 2014 | `7b868f96f2e1445076ee13ee0300569d17fd96af018bc6134670199c6bd73910` |
| licenses.zip | 413750 | `debe50472f22dd6ce70059700316a44bd87236b04084cc1c75dfc649f600bdb0` |
| monitor-assets.json | 970 | `a6ef07b1c80cad512dbbe1623e7dd631ecf56a93694a6d7170bda9d11a30ef33` |
| release-manifest.json | 15814 | `fc4501946786dd3e7931560bf5faecbc81e59360fc04fea884b03b4767d167bc` |
| sbom.spdx.json | 191430 | `4dc77ec018e769af0b953d5a9c0f3a2f20f226ee0a8a1afa632b7d7a50b8bb6a` |
| stm32-toolkit-1.3.5-source.zip | 20792828 | `443f4613c0733dd35689797d3fe8dc64de67e1795508a0a62e8b597ad328faaf` |
| stm32-toolkit-1.3.5-windows-x86_64.zip | 119000802 | `19d317d4ddd5838d2902ca7bbc3b41b58fce63f357df16a2d829e1ee2a6d469d` |
| stm32_monitor-1.3.5-py3-none-any.whl | 1556130 | `daa22a04c81ebf83c2e90b181a946c27630564f150e7c9f998c38d70bc4fcce1` |
| stm32_toolkit-1.3.5-py3-none-any.whl | 4315937 | `4966fe31948787ed17b8adf2102775e176bf603f2bbb5a6d0d4fc3cb3a96f48e` |
| troubleshooting.md | 1737 | `641cbb8c6a7acbab1cfc1fa813cbf5cf07cff4ec6f7c595d07db298db532ab89` |
| CHECKSUMS.sha256 | 1073 | `5c260bd2eeb969ef129a1b53f1e2808c22f5bae0beed8342486d10d279c6b49b` |

Raw package-verification SHA256: `917e159e2a104f2bb31955db3c035ec67bd1880e4601d165bbbf6568c6612572`.
Independent candidate acceptance SHA256: `a218bbd3a82471f0813302e1b1dbb1fab8299eb80289b439ba0045843d5a0b67`.
Final report commit identity is recorded externally after commit, never inside this report.
