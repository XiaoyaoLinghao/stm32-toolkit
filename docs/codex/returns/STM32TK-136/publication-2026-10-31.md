# v1.3.6 publication and guidance acceptance — 2026-10-31

**Release: PUBLISHED_LATEST / PUBLIC_ASSETS_VERIFIED.**
**Publication guidance: ACCEPTED_WITH_FIXES.**

The tool repair and version were already merged and pushed to master. The exact
remote head before publication-doc closeout is `4a0404387d603f14bd641772256d5cbd200ffbc3`.
The annotated v1.3.6 tag object is `0376b7136ea9f6cb12bde0037f1f39fe14c58890`,
peeled to frozen source `b00cbc4edee191712dd6da7e1beb073ff4a74f28`.
Normal Git push/readback succeeded; no tag was moved and no asset was replaced.

[Release v1.3.6](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.6)
(ID429783935) was published at 2026-10-31T07:22:13Z / 15:22:13 Asia/Shanghai,
with draft=false, prerelease=false, and public Latest pointing to this same release.
All 13 frozen attachments were uploaded, matched by server filenames/sizes/digests,
and independently downloaded anonymously with HTTP200. Every download byte count
and SHA-256 matched the frozen package; the public verifier actually exited0.
Windows ZIP:119432768bytes, SHA256
`61170df3c700e1fceb0fc9e9c3f3845d92f7e6a17bca54614f707630d14bdbc1`.
GitHub also lists two automatic source archives; these are not part of the13-file
release inventory. Exact commands, results and hashes are in
[publication-evidence.json](publication-evidence.json).

## Authorization and delivery mechanism

Primary owns specification, plan, orchestration, full independent review and release
acceptance. The user explicitly authorized v1.3.6 release/master integration and the
[frozen-candidate coverage exception](authorization-2026-10-31.md). Browser upload
was blocked twice by file-URL permission; those failures were retained without bypass.
The user then explicitly authorized official gh installation and command-line publishing,
and personally completed normal gh browser login. Primary installed portable official
gh2.103.3 only after verifying its official ZIP digest/checksum; no PATH/global Git
authentication configuration or credential extraction was performed. The prior-version
credential bridge was not reused. Actual gh create-draft, draft check, publish-as-Latest
and published readback all exited0; no command was retried. No toolkit runtime,
original project, firmware, device, frequency, reset, lease or identity contract changed.

## Source guidance review and actual checks

Documentation base:`4a0404387d603f14bd641772256d5cbd200ffbc3`.
Final reviewed guidance CodeHead:`119fe0b0f1783224a532bd44c8edffd71a704caf`.
Earlier29-check checkpoint:`a8d09f5ac97b68e6237b1012ac365eb5bed9e8d7`.
Primary independently reviewed all9 changed files in the clean integration worktree;
complete diff SHA256:`7190bb492a70d76ed9fc6ddab5301d9b8692093713c30727f202ee2648ee72d8`.
Diff-check exited0; v1.3.5-and-older CHANGELOG sections remain byte-identical.
Executable implementation, schemas, version metadata and release policy are unchanged.
Post-publication document/Skill source differs from the frozen archive deliberately;
no package rebuild or moved tag is implied.

The configured local Claude Code CLI route remains `deepseek-v4.1-flash[1m]`.
Initial guide task and its two-paragraph factual follow-up have accepted native audits.
Guidance taskA had one string-not-found Edit and continued against its stop rule;
its CLI exited0 but dispatcher exited1 and the invocation remains NOT_ACCEPTED.
The bounded subsequent facts task had two further string-not-found Edits and three
read-scope violations (test directory twice and test_setup_runtime.py); dispatcher
exited1 and this invocation also remains NOT_ACCEPTED. All logs and successful edits
are preserved; failed invocations are never retrospectively accepted, and later
verification does not change these audit dispositions. No Codex implementation fallback occurred.

Separate native-PowerShell verification ran exactly two bound commands against the
earlier clean combined head: test_plugin_layout.py20passed; test_public_inventory.py plus
three AI documentation contracts, standalone setup and paired debug guidance9passed.
Both actual test exits0, fresh JUnit records29passed/0skipped/0failures/0errors, and
all tracked source hashes unchanged. Inventory and harmless smoke passed on each
launch; main commands have matched native tool_use/tool_result. Native numeric tool
exit fields were absent and remain null; the test subprocess exits0 are separately
recorded. These29 checks overlap the earlier source-bound software matrix and are
not added to its distinct-case total.

The user then explicitly replied **“允许这一次有界文档收尾”**, authorizing one
four-file closeout. Primary checked the actual old text and supplied six exact
replacements. Local Claude performed exactly those changes in release-status,
setup Skill, architecture and CHANGELOG: native audit accepted, CLI0/dispatcher0,
no failed call or read/write scope violation. Original failed invocations retain
their NOT_ACCEPTED disposition; the newly authorized invocation is recorded
separately. Primary reviewed the complete final diff in the clean
independent tree and verified exact implementation bytes and historical CHANGELOG
preservation. All four prose findings are resolved.

At the final guidance head, a separate native PowerShell command ran the five
existing contracts affected by the final Skill changes: read-only/authorized setup,
inline roots/shell policy, unified version, pyOCD/VSCode guidance and standalone
setup. Actual test exit0, fresh JUnit5passed/0skipped/0failures/0errors, source hashes
unchanged, matched inventory/smoke/main and accepted dispatcher/CLI0. These five
overlap the earlier29 checks; no distinct-case total is inflated. Documentation
acceptance is ACCEPTED_WITH_FIXES; no required publication-guidance work remains.

This report precedes its own documentation commit and authorized normal master
fast-forward/push. Its commit and actual remote readback are recorded separately
in run-local delivery evidence after that operation, avoiding a self-referential
commit identity. Package/tag/asset source remains frozen at b00cbc4e; the later
master documentation records observed publication and acceptance only.

The [implementation report](implementation-report.md) and [targeted acceptance](acceptance.md)
retain9720 distinct Python passes/20 named skips, both no-clean preset directions,
actual toolkitVersion1.3.6/ABI provenance/context identity and null/value/zero telemetry
checks. The permanent unmet coverage gates, original failures, source-bound reuse,
platform/archive skips and user-owned final installation/IDE/MCP validation remain.
This release is under the exact candidate-specific exception, not new hardware acceptance.
