# v1.3.1 GitHub delivery and user validation handoff — 2026-10-26

This is the draft-delivery checkpoint. The subsequent user-authorized Latest
publication and anonymous download verification are recorded in
[the publication record](publication-2026-10-26.md).

The user confirmed Git Credential Manager login and explicitly requested the
v1.3.1 GitHub push, retaining ownership of final actual installation and VS Code
validation. Primary owns this delivery record; no product or test source changed.
Accepted source/report base before this record is
`a1bb1908fb1fa992cc3e9f6b9bb802b309157d78`. This documentation commit is outside
the frozen package and does not record its own final SHA.

## Source delivery

The actual system Git Credential Manager reported the `XiaoyaoLinghao` account.
Noninteractive push preflight passed. The authorized, non-forced push advanced
`master` from `89f76ee5551dfdc313f3f37d2d9e760af47daac8` to
`a1bb1908fb1fa992cc3e9f6b9bb802b309157d78`, preserving the complete local history.
The previous remote head was independently verified as an ancestor.

The annotated `v1.3.1` tag was pushed separately. Remote `ls-remote` confirmed:

- Tag object: `9bf2346411e7eac676faf9eb62e6ca6bffa48b7d`.
- Peeled source: `7ff99e50011b6321ae3f0c9bb2edfab91724be3e`.

That source matches the two reproducible builds and the approved candidate-only
exception. Later master changes contain report documentation only. No tag or
existing release was replaced.

## Release preparation

GitHub Release draft `423752112` is bound to `v1.3.1` and full target source
`7ff99e50011b6321ae3f0c9bb2edfab91724be3e`, with `draft=true` and
`prerelease=false`. Its [draft page](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/untagged-aff55a88d47e10641571)
includes the accepted coverage/reuse limitations and final user-owned validation.
It is not a public release or a Latest designation. The previously published
v1.2.0 release was not modified.

All 13 assets were uploaded from the frozen build. Before upload, primary
rehashed every local file against the committed build evidence. After upload,
GitHub's asset size and SHA-256 digest matched every expected file. A separate
fresh API read confirmed the same 13 distinct names, uploaded states, sizes and
digests; no asset was overwritten. The adjacent
[`github-delivery-evidence.json`](github-delivery-evidence.json) preserves the
release identity and asset metadata. This is authenticated draft-asset
verification, not an anonymous public-download test.

Windows ZIP: 113,475,542 bytes; SHA-256
`ec3eb4e9ccadecd832c570288b3449a5b6553b260cd734e1ac82dfc647fe6a08`.
An independent anonymous latest-release API read still returned v1.2.0,
release `420935068`, with `draft=false` and `prerelease=false`.

The release operation uses the existing Git Credential Manager through Git's
standard credential broker. Credentials are used only in process memory, never
printed, persisted, committed, placed in command arguments or copied from a
connector. No authentication or permission settings changed.

## Remaining owner

Final actual installation and VS Code/MCP validation remain
**USER_VALIDATION_PENDING**. The agent stopped IDE automation when the user took
ownership. Fresh isolated Check -> Bootstrap -> Check has already passed, as
recorded in [the installation evidence](authorization-2026-10-26.md); it does not
stand in for the user's final validation. Upgrade/rollback has no new PASS.

The original firmware project and hardware remain untouched. This source push
does not claim physical qualification, public asset download verification or a
completed final user acceptance. The frozen build and approved exception remain
unchanged.
