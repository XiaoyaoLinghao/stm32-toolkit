# v1.3.1 published Latest — 2026-10-26

The user explicitly requested publication as v1.3.1 and Latest before their
independent testing. Primary owns publication and public verification. Accepted
report base before this documentation-only update is
`2ab4f6eb20b9c153182c445c121b5853b9bebe94`; the report commit is outside the
frozen bundle and does not record its own final SHA.

GitHub Release `423752112` was published at `2026-10-26T01:40:23Z`
(2026-10-26 09:40:23 Asia/Shanghai). Both unauthenticated versioned-release and
Latest API reads identify that release, with `draft=false`, `prerelease=false`,
tag `v1.3.1` and full target `7ff99e50011b6321ae3f0c9bb2edfab91724be3e`.
The annotated tag independently resolves to that same frozen source.

- [Public Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.1)
- [Windows bundle](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/download/v1.3.1/stm32-toolkit-1.3.1-windows-x86_64.zip)
- [Checksums](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/download/v1.3.1/CHECKSUMS.sha256)

Before publication, primary rechecked all 13 local and remote asset identities.
The release update changed only the body, draft/prerelease disposition and Latest
designation; no package, asset or tag was rebuilt or replaced. After publication,
primary anonymously downloaded all 13 public assets, each returning HTTP 200,
and independently recomputed their sizes and SHA-256. Every file matches the
frozen build. Full evidence is in
[`public-verification-evidence.json`](public-verification-evidence.json).

Windows ZIP: 113,475,542 bytes, SHA-256
`ec3eb4e9ccadecd832c570288b3449a5b6553b260cd734e1ac82dfc647fe6a08`.
Current master documentation records publication after the freeze; documentation
inside the unchanged frozen archive retains its build-time candidate wording.

The candidate-specific coverage/reuse exception remains explicit in the public
Release body and [qualification contract](../../../testing/release-qualification.md).
Toolkit overall/risk 87.3566%/87.5597% and Monitor risk 92.2527% remain below their
permanent gates; the 19 skips and source-bound reuse remain disclosed. Publication
does not convert those limitations into PASS or extend the exception to a new
candidate. Isolated fresh Check -> Bootstrap -> Check passed previously.

Final actual installation and VS Code/MCP independent testing remain user-owned
and **USER_VALIDATION_PENDING**. The user expressly chose publication first.
Upgrade/rollback has no new PASS, and no new hardware qualification is claimed.
The original firmware project, hardware and installed user environment were not
modified during publication. The agent's authorized optimization/build/delivery
work is complete; independent user testing remains a separate follow-up.
