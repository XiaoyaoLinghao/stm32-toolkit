# v1.3.6 candidate build checkpoint — 2026-10-31

Status: **REPRODUCIBLE_PACKAGE_VERIFIED / INTEGRATION_PENDING**. This is not
release qualification or a publication claim.

Accepted base: `37f69ca4acc2b879d4227a099384241ec39080f4`.
Frozen package source: `9a8b83bb6ee02cea0ab0240b7f3cbd86fbf97a9b`.
Primary owns specification, orchestration, complete diff review and acceptance;
local Claude Code CLI owns implementation and delegated checks, retaining the
configured `deepseek-v4.1-flash[1m]` route. Active branch is
`codex/v136-tool-evidence`, no PR. The user explicitly authorized v1.3.6 builds,
master integration and Release publication. No remote mutation has occurred at
this checkpoint, and no installation or hardware authority is inferred.

Two independent clean detached worktrees (`v136-version` and
`v136-evidence-docs`) were checked against Git archive export bytes under the
existing attributes/line-ending configuration; both needed zero byte restorations.
This is export-byte equality, not a claim that every Windows checkout byte equals
the raw LF Git blob. Each local Claude verify invocation registered only native
PowerShell, passed its no-action inventory and real harmless startup check,
then executed its exact one-command official offline build. Both invocations
were accepted, with CLI/dispatcher exit 0, no unexpected command or scope
violation. Native tool numeric exit fields were absent and stay null; the
bound subprocess records independently establish actual builder exit 0 and
unchanged tracked source (44.999 s and 46.534 s).

The existing official builder used the complete cached inputs: 62 runtime
dependency wheels plus setuptools 84.0.0 and wheel 0.48.0 as isolated temporary
build backends. No existing runtime was replaced or installed into. The 13
output names, byte lengths and SHA-256 digests match exactly across both builds.
Primary independently checked both CHECKSUMS files, extracted the Windows
bundle with containment checks and ran the official `verify-bundle --json`:
actual exit 0, status `ok`, version `1.3.6`, matching source commit, 52 MCP tools
and 9 Skills. The dependency pin remains pyOCD 0.46.0.

- Windows ZIP: `stm32-toolkit-1.3.6-windows-x86_64.zip`, 119413282 bytes.
- SHA-256: `2cdee7a756acfb221908f1692893206ad8334d6d10e9e60d24ee9cc3f97b6303`.
- Raw package comparison: `D:/codex-tmp/v136-evidence/complete-package-verification.json`,
  SHA-256 `60137d02c08b4821a0aabaf57b3e8a3a609a958a5435e23eea16bc22ce11a06b`.
- Build execution records: `package-complete-build-a.json` and
  `package-complete-build-b.json` in that evidence directory; native dispatch
  records are in `package-a-run` and `package-b-run`.

ABI and receipt corrections have targeted passing evidence, including the
three corrected programmable-ELF fixture nodes at this source. The complete
independent build evidence file group and resumed per-file offline regression
are still running. Original assertion/fixture failures, interrupted runs,
out-of-scope read audits and native pending reconciliations remain retained;
none is rewritten as an originally passing invocation.

UI source, tests, configuration, assets and dependencies are unchanged; only
root package versions changed. Primary verified exact binding to the accepted
534-pass/one-platform-skip UI evidence and native 2938/3147 branch result with
the per-file 90% gate met. This is explicit reuse, not a new UI execution.
Python native coverage and final matrix accounting remain pending. The prior
v1.3.5 coverage exception does not transfer, and all permanent floors remain.
No new physical flash, recipient installation, VS Code/MCP or interactive
acceptance is claimed. The bundled prepublication wording is the immutable
build-time state; actual publication will be recorded separately.
