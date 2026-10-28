# v1.3.4 bounded upload recovery — 2026-10-28

Source/master and annotated v1.3.4 tag push succeeded. Master is
`8f2a37f974e77faf298b5e856525275192b1425d`; tag object is
`648baf06428773ac69b05de8aecf3e75ae926ea7`, peeled source
`a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead`. Draft Release426198381 exists.

The first upload exited1 with URLError at the Windows ZIP; sensitive transport
details were withheld. Read-only connected GitHub asset inspection established
8 uploaded assets with exact frozen sizes/digests, one Windows ZIP starter
ID683571874 with no digest, and4 genuinely unexecuted uploads: both wheels,
troubleshooting.md and CHECKSUMS.sha256. Original logs and remote snapshot remain
under D:/codex-tmp/r134; no prior success is rewritten or re-uploaded.

The user explicitly approved **“批准这一次有界续传”**: delete only failed starter
683571874, increase binary-transfer timeout180->600seconds, allow at most one
additional Windows ZIP upload, and first upload the four unexecuted files. The
existing authorized verification/publication sequence then continues on success.
No automatic retry or other asset deletion is authorized. A fresh failure stops
this bounded attempt; no package bytes, source/tag or successful assets change.

Only the already authorized client D:/codex-tmp/r134/github_v134_delivery.py is used.
The amendment adds exact failed-starter guards/204 handling, binary-only timeout
headroom and non-sensitive error type/errno reporting; credential acquisition,
redirect refusal and host/repository limits remain. Original client SHA-256:
`e2135bd9ec95e20133e7ec77b1634643acc3ba64b40a7371d844c06783fc3d57`;
reviewed amended client SHA-256:
`a72e6070750fe03dcd31cc7d8f79ce72d1bc6d3a0f03415fa4a5a5b14ef6f11d`.
No credential is printed, saved or changed. The earlier candidate-specific
qualification and in-process credential authorization remain bounded and unchanged.

The exact failed starter deletion completed successfully; the follow-up GET returned
8remaining successful assets. The single authorized Windows ZIP re-upload is pending;
publication has not yet occurred. Local cleanup evidence: github-v134-cleanup-failed-starter.json.
