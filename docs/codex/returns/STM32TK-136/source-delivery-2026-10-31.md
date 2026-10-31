# v1.3.6 source delivery and publication checkpoint

The tool repair is **ACCEPTED_WITH_FIXES**. The user-authorized master integration
has been completed and pushed; formal Release publication remains
**COVERAGE_DECISION_PENDING**. No tag or Release was created at this checkpoint.

Primary owns this delivery record and independent acceptance. Product implementation
and tests were delegated to local Claude Code CLI with the unchanged configured
`deepseek-v4.1-flash[1m]` route. No PR, provider/authentication change, credential
read, force push, installation, original-project edit or hardware action occurred.

## Source and actual remote evidence

- Accepted remote base: `37f69ca4acc2b879d4227a099384241ec39080f4`.
- Reviewed frozen package source: `b00cbc4edee191712dd6da7e1beb073ff4a74f28`.
- Reviewed acceptance-report commit: `0d60bbb67e3cb5757a8ea8a89db9ce8a1a2c829b`.
- The local master was unattached to any other worktree and an ancestor of the
  reviewed commit. It was checked out in the owned clean integration-review tree
  and fast-forward merged with `git merge --ff-only`; actual exit 0.
- `git push --porcelain origin master:master` actually exited 0, advancing remote
  master from `37f69ca4` to `0d60bbb6` without force or retry.
- `git ls-remote origin refs/heads/master refs/tags/v1.3.6` actually exited 0 and
  returned full master SHA `0d60bbb67e3cb5757a8ea8a89db9ce8a1a2c829b`, with no
  v1.3.6 tag. The local integration tree was clean.

This record follows that verified push. Its own later commit is not embedded here;
the final remote head is recorded in run-local delivery evidence after readback.
The package/tag source remains the frozen product commit, independent of later
acceptance and delivery documentation.

## Ready candidate and remaining decision

The [complete acceptance report](implementation-report.md) records all 265 Python
test files: 9,720 distinct passes, 20 explicit platform/archive-input skips and no
unresolved failure. The [targeted acceptance](acceptance.md) includes actual GNU
release/debug switching without clean, context identities, toolkitVersion and ABI
provenance. Original failures, corrections and source-bound evidence reuse remain
visible. No new physical flash or final recipient installation/IDE PASS is claimed.

Two independent official builds at the frozen source produced 13 byte-identical
assets; official bundle verification actually exited 0 with status=ok and
productVersion=1.3.6. Final files are retained at
`D:/codex-tmp/v136-evidence/final-package-a/`, with the complete immutable asset
inventory in [integration-evidence.json](integration-evidence.json).

Windows ZIP: 119432768 bytes, SHA-256
`61170df3c700e1fceb0fc9e9c3f3845d92f7e6a17bca54614f707630d14bdbc1`.

| Scope | v1.3.6 native branches | Permanent floor | Result |
| --- | --- | --- | --- |
| Toolkit overall | 16414/18836 (87.1416%) | 90% | UNMET |
| Toolkit risk | 15281/17496 (87.3400%) | 90% | UNMET |
| Monitor overall | 3293/3564 (92.3962%) | 90% | PASS |
| Monitor risk | 3293/3564 (92.3962%) | 95% | UNMET |

Each group is no lower than v1.3.5 using exact native ratios and unchanged scope.
UI reuses the unchanged-source 2938/3147 result with its per-file gate met. The
permanent floors remain unchanged and the three unmet gates remain UNMET.

[Release qualification](../../../testing/release-qualification.md) explicitly says:
“Historical measurements and one-time exceptions do not transfer automatically
to a later release.” The existing v1.3.5-only exception therefore does not authorize
this candidate. A new decision must explicitly identify frozen source `b00cbc4e`
and its 13 files; ordinary push/merge/Release authority is already granted.

If this candidate is approved for an exception, the remaining sequence is a new
tag bound to the full frozen SHA, upload of these exact 13 files, formal publication
and independent public download/hash verification. No rebuild, moved existing tag,
replacement runtime, original-project edit or hardware test is implied.
