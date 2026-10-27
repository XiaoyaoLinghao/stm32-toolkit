# v1.3.3 publication and public verification

Date: 2026-10-27. **Published as Latest**, with the user's candidate-specific
**USER_APPROVED_EXCEPTION**. Final installation and independent VS Code validation
remain user-owned **USER_VALIDATION_PENDING**; no original firmware project or hardware
was accessed. Publication does not turn any disclosed limit into PASS.

- Release: [v1.3.3](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.3),
  ID `425062317`, published `2026-10-27T05:22:56Z`, `draft=false`, `prerelease=false`.
- Latest API and tag Release API identify the same release.
- Annotated tag object: `4e06d5fc364cc15782d7a66cf36c00d97080332a`.
- Frozen source/tag target: `46ca09084bbe39f670714d19d7d55f9365ef06be`.
- Initial non-forced atomic push advanced master from `f5d8978a2a60c59ec5afee4fc014707311210fe5`
  to `234e77a96f348a6e584dedf0e3144764d342714c`, and created the exact frozen tag.
- All 13 server asset sizes and SHA-256 digests match the two independent official builds.
- Anonymous downloads of all 13 assets returned HTTP200; actual full byte lengths and
  SHA-256 hashes all match. [Public verification JSON](public-verification.json)
  binds each asset ID, download URL, byte length and digest.
- Windows ZIP: 116,350,730 bytes, SHA-256
  `52829b90bdd2ebf5b8dd61825ba7c423f5679597b23a35487bf3f8ca4c51378a`.

The public Release notes retain the approved coverage/performance/reuse/platform/vendor
limits, link the candidate and acceptance records, and identify user validation as pending.
The [authorization](authorization-2026-10-27.md) applies only to that frozen candidate;
the [permanent qualification contract](../../../testing/release-qualification.md) is unchanged.

## Publication documentation review

Reviewed documentation CodeHead before this report: `7fcd4bbdb783e7f71c95c27c12bceb0942c4b8ec`.
Verdict: **ACCEPTED_WITH_FIXES** for publication documentation; the release's
separately approved qualification exception remains in effect.
Claude Code CLI, using the existing configured provider/model, updated only current
publication guidance; the primary independently reviewed the complete diff from
`234e77a96f348a6e584dedf0e3144764d342714c`, including the bounded final corrections.
Both READMEs now concisely link v1.3.3 Latest. Changelog, user/Windows guides, architecture
and five calling skills describe actual publication, the normal no-Git route and verified
runtime paths while preserving historical introductions and user-owned install/IDE limits.
An obsolete pre-publication assertion was updated to the actual published contract;
existing fields/root/authorization checks were retained. No product implementation,
version identity, asset, frozen tag or checksum was changed after publication.

The first publication-docs invocation completed native edits only in the11 allowed
documents, but its audit rejected13 reads/searches outside its exact read_scope
(repository/skills/test parent searches and one undeclared test-file read). Its CLI
exit0 is not acceptance: dispatcher exit1/file_edit_completed=false remains retained.
It had already ended when that final audit was reconciled; no recovery was invoked
and its violations are not retroactively accepted. The primary reviewed the complete
diff and supplied a separate four-file correction with exact source facts. That task
corrected a misleading version-field paragraph, historical introduction labels and
an obsolete assertion that could pass accidentally on historical1.3.0 wording.
The four-file correction completed with matching native tools, no scope violations
and successful native edits. No product implementation or permission/provider change resulted.

Existing documentation/AI-caller/README/setup contracts at that reviewed head passed:
{'count': 35, 'failures': 0, 'errors': 0, 'skipped': 0}. Bound pytest exit0, source unchanged; native verification
is recorded separately from file editing and independently reconciled by the primary.
No full product regression or rebuild was triggered by this documentation-only update.
Frozen package documentation retains the source's build-time candidate state; current
master documentation and this record supersede that publication status, without replacing
or retagging the approved package. The final documentation/report commit's remote identity
is recorded outside this report after successful push, not embedded as its own SHA.

Raw evidence root: `D:/codex-tmp/r133`; release records `github-v133-create-draft.json`,
`github-v133-upload.json`, `github-v133-publish.json`, `github-v133-public-verification.json`;
documentation edit/verify streams and `d2/execution.json`/JUnit remain retained.
Public verification SHA-256: `a30f48ed6d881b8548b10fee76da5dae7a50ed98a77d79047508144a9059f7f1`.
