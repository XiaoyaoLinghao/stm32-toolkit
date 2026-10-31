# v1.3.6 frozen-candidate publication authorization

The user replied **“同意”** to the explicit request to accept and publish only
frozen candidate `b00cbc4edee191712dd6da7e1beb073ff4a74f28` and its 13 verified
files under a coverage-not-lower-than-v1.3.5 condition. This is new authorization,
not transfer of the v1.3.5-only exception.

Disposition: **USER_APPROVED_EXCEPTION / CONDITION_MET_NON_REGRESSION**.
The exact comparisons are 16414/18836 >= 15530/18734 for Toolkit overall,
15281/17496 >= 14399/17394 for Toolkit risk, and 3293/3564 >= 3292/3564 for
both Monitor scopes. UI remains 2938/3147 with its per-file gate met through
explicit unchanged-source reuse. Permanent thresholds remain 90%/90%/90%/95%;
the three unmet permanent gates remain UNMET, not PASS.

The immutable 13-file inventory is in
[integration-evidence.json](integration-evidence.json). Windows ZIP size is
119432768 bytes and SHA-256 is
`61170df3c700e1fceb0fc9e9c3f3845d92f7e6a17bca54614f707630d14bdbc1`.
Both independent builds and the official bundle verification have passed.
The [implementation report](implementation-report.md) retains 9720 distinct
Python passes, 20 named skips, original failures, bounded corrections, native
pending reconciliation and source-bound reuse. Final recipient installation,
VS Code/MCP/interactive validation remains user-owned and unverified.

The existing explicit delivery authorization plus this candidate-specific
decision authorizes a new annotated v1.3.6 tag at the full frozen SHA, normal
non-force push, upload of the exact 13 files, publication as formal Latest,
public download/hash verification and master publication-document updates.
No existing tag or asset replacement, credential read, permission/provider
change, runtime installation, original-project edit, hardware access or new
physical acceptance is authorized. Use the existing Git authentication flow
and logged-in browser; no prior credential-bridge exception transfers.

Primary owns source/authority reconciliation, tag/release delivery, independent
verification and acceptance. Product-facing publication documentation is
delegated to local Claude Code CLI, retaining the configured route. Each remote
operation is finite, its actual result retained, and no retry is implicit.
Package source and bytes stay fixed; later report commits record observed facts.
This authorization itself does not claim that publication has already occurred.
