# v1.3.4 publication and anonymous verification — 2026-10-28

[v1.3.4 Release](https://github.com/XiaoyaoLinghao/stm32-toolkit/releases/tag/v1.3.4)
is public and Latest. Release **426198381** was published at **2026-10-28T02:39:44Z**
(10:39:44 Asia/Shanghai), `draft=false`, `prerelease=false`.
All13 attached files were anonymously downloaded and matched the frozen sizes and SHA-256.
The candidate-specific **USER_APPROVED_EXCEPTION** remains limited to the exact frozen
source and assets; permanent unmet gates and disclosed limits have not become PASS.

## Source and authority

- Frozen source/target/peeled tag: `a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead`.
- Annotated tag object: `648baf06428773ac69b05de8aecf3e75ae926ea7`.
- First published source master: `8f2a37f974e77faf298b5e856525275192b1425d`.
- Atomic non-force master/tag push succeeded; remote refs were read back before draft creation.
- [Specific authorization](authorization-2026-10-28.md), [frozen inventory](candidate-build.md),
  [independent software review](implementation-report.md), [bounded recovery](upload-recovery-2026-10-28.md).
- Only the authorized release client used existing GCM credentials inside its process.
  No credential was printed, saved, supplied to Claude, or changed; no model/provider/auth/global policy change.

## Remote and public verification

Draft creation, completed upload, independent draft verification and Latest publication each
returned actual exit0. Every server asset reports uploaded state, exact length and matching
SHA-256 digest. The first Windows ZIP upload had a retained URLError and left only a starter;
read-only inspection confirmed8successful assets. The user authorized one bounded recovery:
only failed starter683571874 was deleted, binary timeout180->600seconds, Windows ZIP re-uploaded
once, then4previously unexecuted files uploaded. The new Windows ZIP asset is683590327.
Existing successful assets and every approved package byte remained unchanged.

Anonymous verification separately read public release/tag and Latest endpoints, asserted
matching IDs/target and downloaded all13files without credentials. Each completed HTTP200
and matched the local double-build candidate. This is public-download evidence, not just
server metadata or upload startup.

| Asset | Downloaded bytes | SHA-256 | HTTP |
| --- | ---: | --- | ---: |
| CHECKSUMS.sha256 | 1073 | `678494db066e3324cd82063449749dc5491eee91c134a922cf1de8a8e59d8095` | 200 |
| LICENSE | 1075 | `55edb314745f2b0d3fe09e512726c3bf67cb20ba99fa3cd66859a64f3e6b6af5` | 200 |
| THIRD-PARTY-NOTICES.md | 2615 | `9409e2a310ddfebaea7524df5beaaf9a1b10fe93393d4064ec5d1d116e3f7903` | 200 |
| compatibility.md | 2014 | `675e20fc295606b4efca5dfdcc22a48801c931243929042baf598d12eb099b00` | 200 |
| licenses.zip | 413750 | `69229e251c4ac0de3d9c4c793df114af5ff0d54d31df8ea2d37ff05f44c035c1` | 200 |
| monitor-assets.json | 970 | `058d8399c49ce412285b94aa14b2837fa93c1438b232a2f493b47cc2a6862eff` | 200 |
| release-manifest.json | 15814 | `20b681c782c7e7b9283aaa7550c36647c6a5b049abdf7b1d39730a9f8df2639d` | 200 |
| sbom.spdx.json | 191430 | `90c6e46f8e799058a3b80f363b9a4f70300a7d8d9d7e817c57ef4f7596d4ddf1` | 200 |
| stm32-toolkit-1.3.4-source.zip | 19720017 | `b28f9e3f5339facff1b72d11aa829fdc42f17d4a1926e4dfe9721729f34aeeb5` | 200 |
| stm32-toolkit-1.3.4-windows-x86_64.zip | 116715146 | `4e75811adcac0e1e2c24a4cfc01a9a7f0ae8e08e458c639d2f361ffb1eec3cdc` | 200 |
| stm32_monitor-1.3.4-py3-none-any.whl | 1556130 | `01102ebd17c0e9c6b5d5f6ad63b3214c11561fd6629bbdcdf497197eaf771b6c` | 200 |
| stm32_toolkit-1.3.4-py3-none-any.whl | 4266060 | `ec8428fb0e0e4601e32b3981cdbc92055e2672ca132b7b65b914f88aad4ebfc0` | 200 |
| troubleshooting.md | 1737 | `1b9d4a30edb64ee497ba8c893c627e6d4964d1b19777565a804c5570e7f953de` | 200 |

## Retained limits and current documentation

Toolkit overall/risk82.7452%/82.6335% remain below90%, Monitor risk92.3681% remains below95%.
Exact-source reuse, original failures and bounded passing comparisons, platform/historical-data
skips and unverified real vendor generation remain disclosed. Final recipient installation
and independent VS Code checks remain **USER_VALIDATION_PENDING**, owned by the user.
No original-project edits, installed-runtime replacement or physical hardware action occurred.

Frozen package documents retain their build-time candidate state. Current source guidance
was updated through local Claude Code CLI and independently reviewed; final contracts at
`713327c86c2a9c88d7ff82732caca1b95ca6f75f` passed172cases with1platform skip. See
[guidance review](publication-guidance-review.md). Current master guidance supersedes that
build-time status without rebuilding or replacing any approved release asset.

## Evidence

[Structured publication evidence](publication-evidence.json) records public downloads, server
asset IDs/digests, ref identities and raw record hashes. Local evidence: `D:/codex-tmp/r134`.
Public verification SHA-256: `a1ee3e26f903c94d56f4967d8c0240189c264133f4f0d08d73e55ce218aa667a`.
Frozen verification SHA-256: `7f4f6f00191e17f263da4ac63e8121a881977d5723cb154f328e21353a8e6e9f`.
