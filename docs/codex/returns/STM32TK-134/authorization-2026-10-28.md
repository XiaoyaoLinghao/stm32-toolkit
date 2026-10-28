# v1.3.4 candidate-specific authorization — 2026-10-28

The user explicitly answered **“批准此候选例外并发布”** for frozen source
`a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead` and its 13 reproducible, verified files. Disposition:
**USER_APPROVED_EXCEPTION**, limited to this candidate; authorize source/tag push,
draft creation/upload/verification and v1.3.4 publication as Latest, then anonymous
asset verification. Subsequent “继续” resumes this authorized sequence.

Accepted disclosed limits: Toolkit overall 15336/18534=82.7452% and risk
14208/17194=82.6335% below90%; Monitor risk3292/3564=92.3681% below95%; exact-source
reuse, original failures retained separately from passing comparisons, platform and
historical-data skips, synthetic external vendor adapter, and no new actual
installation/VS Code/hardware PASS. Permanent gates and memberships remain unchanged;
unmet values and skips do not become PASS. Final installation/VS Code remains
USER_VALIDATION_PENDING, owned by the user. No original-project/hardware authority.

Windows ZIP:116,715,146bytes; SHA-256
`4e75811adcac0e1e2c24a4cfc01a9a7f0ae8e08e458c639d2f361ffb1eec3cdc`.
[Exact candidate inventory](candidate-build.md); verification record SHA-256
`7f4f6f00191e17f263da4ac63e8121a881977d5723cb154f328e21353a8e6e9f`.

The user also explicitly answered **“允许仅此发布进程复用”**: only
`D:/codex-tmp/r134/github_v134_delivery.py` may obtain the existing Git Credential
Manager credential inside its release process and use it for this repository's
`api.github.com` / `uploads.github.com` requests. No credential is displayed,
persisted, placed in arguments or reports, or changed. Script SHA-256:
`e2135bd9ec95e20133e7ec77b1634643acc3ba64b40a7371d844c06783fc3d57`.
This is a bounded exception to the current never-read-credentials instruction,
not permission to inspect credentials or change the Claude model/provider/auth.
The script retains redirect refusal, host/repository checks and exact asset binding.

At authorization recording, remote master remains accepted base
`dc278ca226a0c1d4540657f48eb74fa1d5b361ca`, v1.3.4 tag is absent, and no release-client
operation has run. Publication is recorded only after observed remote success.
